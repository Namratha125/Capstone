"""
compute_similar_facts.py
========================
Generates sentence embeddings for all cleaned cases and creates
SIMILAR_FACTS edges in Neo4j for pairs with cosine similarity ≥ 0.7.

Run this on Kaggle (free T4 GPU):
    !pip install -q sentence-transformers faiss-gpu neo4j tqdm
    !python compute_similar_facts.py \
        --folder  /kaggle/input/cleaned-fact-layer \
        --uri     bolt://<your-aura-or-ngrok-host>:7687 \
        --user    neo4j \
        --password YOUR_PASSWORD

On CPU (fallback — slower, ~2–3 hrs for 26k cases):
    !pip install -q sentence-transformers faiss-cpu neo4j tqdm
    !python compute_similar_facts.py --folder ... --uri ... --cpu

WHAT IT DOES
------------
  1. Loads all cleaned JSONs.
  2. Builds embedding text: issue + first 5 facts (info-dense, noise-free).
  3. Encodes with all-MiniLM-L6-v2 (384-dim, fast, legal-agnostic but
     good for sentence-level similarity).
  4. Builds FAISS index (Inner Product = cosine sim since vectors are L2-
     normalized).
  5. For each case, retrieves top-K neighbors; keeps pairs with score ≥ 0.7.
  6. Saves embeddings.npy + similar_pairs.json (checkpoints).
  7. MERGEs SIMILAR_FACTS edges into Neo4j in batches.

NOTE: Embeddings are NOT stored as node properties in Neo4j — they stay
in embeddings.npy. Neo4j doesn't do vector search natively (would need
GDS 2.x), and the FAISS index is the right tool for retrieval anyway.
"""

import argparse
import json
import os
import sys
import time
import numpy as np
from pathlib import Path

try:
    from neo4j import GraphDatabase
except ImportError:
    print("pip install neo4j")
    sys.exit(1)


# ──────────────────────────────────────────────────────────────────────────────
# TEXT BUILDER
# ──────────────────────────────────────────────────────────────────────────────

def build_embedding_text(case_json: dict) -> str:
    """
    Concatenates issue + up to 5 facts.
    Chosen because:
      - issue is always the clearest semantic signal
      - facts are factual propositions (less noise than arguments)
      - principles / summary are redundant at similarity-detection level
    """
    issue = (case_json.get("issue") or "").strip()
    facts = case_json.get("facts") or []
    facts_text = " ".join(str(f) for f in facts[:5] if f)
    return f"{issue} {facts_text}".strip()


# ──────────────────────────────────────────────────────────────────────────────
# EMBEDDING + FAISS
# ──────────────────────────────────────────────────────────────────────────────

def load_cases(folder: str):
    cases, texts, case_ids = [], [], []
    for f in sorted(Path(folder).glob("*.json")):
        if f.name == "done_keys.json":
            continue
        try:
            d = json.loads(f.read_text(encoding='utf-8'))
        except Exception:
            continue
        if not isinstance(d, dict) or not d.get("case_id"):
            continue
        cid = d.get("case_id")
        txt = build_embedding_text(d)
        if cid and txt:
            cases.append(d)
            case_ids.append(cid)
            texts.append(txt)
    print(f"Loaded {len(cases)} cases with embedding text")
    return case_ids, texts


def generate_embeddings(texts: list[str], use_gpu: bool,
                         emb_path: str = "embeddings.npy") -> np.ndarray:
    if os.path.exists(emb_path):
        print(f"Loading cached embeddings from {emb_path}")
        return np.load(emb_path)

    print("Loading sentence-transformers model...")
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("pip install sentence-transformers")
        sys.exit(1)

    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    device = "cuda" if use_gpu else "cpu"
    print(f"Encoding {len(texts)} texts on {device} ...")

    t0 = time.time()
    embeddings = model.encode(
        texts,
        batch_size=512 if use_gpu else 64,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,   # L2-normalize → cosine sim = inner product
        device=device,
    )
    print(f"Encoded in {time.time()-t0:.1f}s — shape: {embeddings.shape}")
    np.save(emb_path, embeddings)
    print(f"Saved embeddings to {emb_path}")
    return embeddings


def compute_similar_pairs(embeddings: np.ndarray, case_ids: list[str],
                           threshold: float = 0.7, top_k: int = 30,
                           pairs_path: str = "similar_pairs.json") -> list[dict]:
    if os.path.exists(pairs_path):
        print(f"Loading cached similar pairs from {pairs_path}")
        with open(pairs_path) as f:
            return json.load(f)

    print(f"Building FAISS index for {len(case_ids)} cases ...")
    try:
        import faiss
    except ImportError:
        print("pip install faiss-gpu  (or faiss-cpu on CPU-only env)")
        sys.exit(1)

    d = embeddings.shape[1]
    index = faiss.IndexFlatIP(d)   # Inner Product (= cosine since normalized)
    index.add(embeddings)

    print(f"Searching top-{top_k} neighbors with threshold {threshold} ...")
    pairs = []
    QUERY_BATCH = 2000

    for i in range(0, len(embeddings), QUERY_BATCH):
        batch = embeddings[i:i + QUERY_BATCH]
        scores, indices = index.search(batch, top_k + 1)  # +1 because self is included

        for j, (score_row, idx_row) in enumerate(zip(scores, indices)):
            src_idx = i + j
            for score, tgt_idx in zip(score_row, idx_row):
                # Skip self-matches and below-threshold pairs
                if tgt_idx == src_idx or score < threshold:
                    continue
                # Only keep src < tgt to avoid duplicate pairs
                a, b = min(src_idx, tgt_idx), max(src_idx, tgt_idx)
                pairs.append({
                    "src": case_ids[a],
                    "tgt": case_ids[b],
                    "score": round(float(score), 4),
                })

        if (i // QUERY_BATCH) % 5 == 0:
            print(f"  [{i:>6}/{len(embeddings)}]  pairs so far: {len(pairs)}")

    # Deduplicate (same (src,tgt) from different batch windows)
    seen = set()
    deduped = []
    for p in pairs:
        key = (p["src"], p["tgt"])
        if key not in seen:
            seen.add(key)
            deduped.append(p)

    print(f"Total unique similar pairs (≥{threshold}): {len(deduped)}")
    with open(pairs_path, 'w') as f:
        json.dump(deduped, f)
    print(f"Saved to {pairs_path}")
    return deduped


# ──────────────────────────────────────────────────────────────────────────────
# NEO4J LOADING
# ──────────────────────────────────────────────────────────────────────────────

_MERGE_SIMILAR = """
UNWIND $rows AS r
MATCH (a:Case {case_id: r.src})
MATCH (b:Case {case_id: r.tgt})
MERGE (a)-[rel:SIMILAR_FACTS {tgt_id: r.tgt}]->(b)
SET rel.similarity_score = r.score
MERGE (b)-[rel2:SIMILAR_FACTS {tgt_id: r.src}]->(a)
SET rel2.similarity_score = r.score
"""

# Create BOTH directions so Cypher queries can use (a)-[:SIMILAR_FACTS]-(b)
# without UNION. The storage overhead is small (one extra property per pair).


def load_similar_facts(driver, pairs: list[dict], batch_size: int = 500):
    print(f"\nCreating SIMILAR_FACTS edges ({len(pairs)} pairs, "
          f"both directions) ...")
    total = 0
    t0 = time.time()
    with driver.session() as session:
        for i in range(0, len(pairs), batch_size):
            batch = pairs[i:i + batch_size]
            session.run(_MERGE_SIMILAR, rows=batch)
            total += len(batch)
            if total % 10000 == 0 or total == len(pairs):
                elapsed = time.time() - t0
                print(f"  [{total:>7}/{len(pairs)}]  {elapsed:.1f}s")
    print(f"  Done. {len(pairs)} SIMILAR_FACTS pairs ({len(pairs)*2} directed edges)")


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Compute embeddings and SIMILAR_FACTS edges"
    )
    parser.add_argument("--folder",     required=True)
    parser.add_argument("--uri",        default=os.environ.get("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument("--user",       default=os.environ.get("NEO4J_USER", "neo4j"))
    parser.add_argument("--password",   default=os.environ.get("NEO4J_PASSWORD", ""))
    parser.add_argument("--threshold",  type=float, default=0.7,
                        help="Cosine similarity threshold (default 0.7)")
    parser.add_argument("--top-k",      type=int,   default=30,
                        help="FAISS search top-K per case (default 30)")
    parser.add_argument("--cpu",        action="store_true",
                        help="Force CPU even if GPU available")
    parser.add_argument("--emb-path",   default="embeddings.npy",
                        help="Where to save/load embeddings")
    parser.add_argument("--pairs-path", default="similar_pairs.json",
                        help="Where to save/load computed pairs")
    parser.add_argument("--no-neo4j",  action="store_true",
                        help="Generate embeddings + pairs but skip Neo4j load")
    args = parser.parse_args()

    # Check GPU availability
    use_gpu = not args.cpu
    if use_gpu:
        try:
            import torch
            if not torch.cuda.is_available():
                print("No CUDA GPU found — falling back to CPU")
                use_gpu = False
            else:
                print(f"GPU: {torch.cuda.get_device_name(0)}")
        except ImportError:
            use_gpu = False

    # Load cases
    case_ids, texts = load_cases(args.folder)
    if not case_ids:
        print("No cases found. Check --folder path.")
        sys.exit(1)

    # Generate embeddings
    embeddings = generate_embeddings(texts, use_gpu, args.emb_path)

    # Compute similar pairs
    pairs = compute_similar_pairs(
        embeddings, case_ids,
        threshold=args.threshold,
        top_k=args.top_k,
        pairs_path=args.pairs_path,
    )

    if args.no_neo4j:
        print("--no-neo4j set — skipping Neo4j load.")
        print(f"Pairs saved to {args.pairs_path}. Run again without --no-neo4j to load.")
        return

    if not args.password:
        print("--password required to load into Neo4j. "
              "Re-run without --no-neo4j and with --password set.")
        return

    print(f"\nConnecting to Neo4j at {args.uri} ...")
    driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))
    driver.verify_connectivity()
    print("Connected.")

    load_similar_facts(driver, pairs)
    driver.close()

    print("\nDone. SIMILAR_FACTS graph layer is ready.")
    print("This enables the symbolic reasoning engine's precedent traversal")
    print("via SIMILAR_FACTS and FOLLOWS relationships.")


if __name__ == "__main__":
    main()
