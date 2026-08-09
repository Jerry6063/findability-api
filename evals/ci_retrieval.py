"""CI gate: recompute retrieval metrics from cached vectors and fail on regression.

Pure standard library — no numpy, no chromadb, no API key, no network, no cost.
`golden-embeddings.json` already holds both the 13 corpus vectors and one vector
per golden question, so the whole metric is a few thousand dot products.

It also checks the two ways this dataset rots in practice: a question added to
`golden.jsonl` without regenerating the cache, and an `expected_citations` entry
pointing at a node id the corpus no longer has.

    python evals/ci_retrieval.py            # enforce thresholds, exit 1 on failure
    python evals/ci_retrieval.py --report   # print the numbers and exit 0
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / "golden-embeddings.json"
GOLDEN = HERE / "golden.jsonl"

# Baseline measured 2026-08-09: hit@3 0.9167, hit@5 1.0000, MRR 0.8958.
# Floors sit a little under that so honest corpus growth does not trip the build,
# while a real retrieval regression does.
THRESHOLDS = {"hit@3": 0.85, "hit@5": 0.95, "mrr": 0.85}
TOP_K = 5


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    sys.exit(1)


def load() -> tuple[dict, list[dict]]:
    if not CACHE.exists():
        fail(f"{CACHE.name} missing — run `python evals/run_retrieval.py` and commit it")
    cache = json.loads(CACHE.read_text(encoding="utf-8"))
    golden = [json.loads(l) for l in GOLDEN.read_text(encoding="utf-8").splitlines() if l.strip()]
    return cache, golden


def check_consistency(cache: dict, golden: list[dict]) -> None:
    doc_ids = {d["id"] for d in cache["docs"]}
    cached_q = {q["id"]: q for q in cache["queries"]}

    missing = [e["id"] for e in golden if e["id"] not in cached_q]
    if missing:
        fail(f"golden.jsonl has entries with no cached embedding: {missing} — "
             "re-run `python evals/run_retrieval.py` and commit golden-embeddings.json")

    stale = [qid for qid in cached_q if qid not in {e["id"] for e in golden}]
    if stale:
        fail(f"cache holds embeddings for entries no longer in golden.jsonl: {stale}")

    for entry in golden:
        drifted = [c for c in entry["expected_citations"] if c not in doc_ids]
        if drifted:
            fail(f"{entry['id']} cites node id(s) not in the corpus: {drifted}")
        cached = cached_q[entry["id"]]
        if cached["question"] != entry["question"]:
            fail(f"{entry['id']}: the question changed but its embedding did not — "
                 "re-run `python evals/run_retrieval.py`")
        if cached["expected_citations"] != entry["expected_citations"]:
            fail(f"{entry['id']}: expected_citations changed since the cache was built")

    ids = [e["id"] for e in golden]
    if len(set(ids)) != len(ids):
        fail("duplicate ids in golden.jsonl")
    for entry in golden:
        is_refusal = entry.get("category") == "refusal"
        if is_refusal and entry["expected_citations"]:
            fail(f"{entry['id']} is a refusal entry but carries citations")
        if not is_refusal and not entry["expected_citations"]:
            fail(f"{entry['id']} is not a refusal entry but has no citations")


def score(cache: dict) -> dict:
    docs = cache["docs"]
    doc_ids = [d["id"] for d in docs]
    doc_vecs = [d["embedding"] for d in docs]

    hits3, hits5, rr = [], [], []
    for query in cache["queries"]:
        expected = set(query["expected_citations"])
        if not expected:          # refusal entries carry no retrieval ground truth
            continue
        qv = query["embedding"]
        ranked = sorted(
            ((doc_ids[i], sum(a * b for a, b in zip(qv, doc_vecs[i]))) for i in range(len(doc_ids))),
            key=lambda pair: pair[1], reverse=True,
        )
        order = [doc_id for doc_id, _ in ranked]
        hits3.append(1.0 if expected & set(order[:3]) else 0.0)
        hits5.append(1.0 if expected & set(order[:5]) else 0.0)
        reciprocal = 0.0
        for position, doc_id in enumerate(order[:TOP_K], 1):
            if doc_id in expected:
                reciprocal = 1.0 / position
                break
        rr.append(reciprocal)

    if not hits3:
        fail("no scorable entries — every golden entry is a refusal?")
    mean = lambda xs: sum(xs) / len(xs)
    return {"n": len(hits3), "hit@3": mean(hits3), "hit@5": mean(hits5), "mrr": mean(rr)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="store_true", help="print metrics without enforcing")
    args = parser.parse_args()

    cache, golden = load()
    check_consistency(cache, golden)
    metrics = score(cache)

    print(f"corpus: {len(cache['docs'])} chunks · golden: {len(golden)} entries "
          f"({metrics['n']} scorable) · model: {cache['embed_model']}")
    for key in ("hit@3", "hit@5", "mrr"):
        floor = THRESHOLDS[key]
        status = "ok " if metrics[key] >= floor else "LOW"
        print(f"  {status} {key:6} {metrics[key]:.4f}  (floor {floor:.2f})")

    if args.report:
        return
    failures = [k for k in THRESHOLDS if metrics[k] < THRESHOLDS[k]]
    if failures:
        fail("below threshold: " + ", ".join(
            f"{k} {metrics[k]:.4f} < {THRESHOLDS[k]:.2f}" for k in failures))
    print("retrieval metrics within thresholds")


if __name__ == "__main__":
    main()
