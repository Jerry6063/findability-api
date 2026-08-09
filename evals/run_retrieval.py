"""Retrieval metrics for findability-api — hit-rate@3 / @5 and MRR, no LLM judge.

Embeds every golden question exactly the way `main.py` does (same model, same
RETRIEVAL_QUERY task type, same L2 normalisation), queries the persisted Chroma
collection, and scores the ranking against each entry's `expected_citations`.

Refusal entries (empty `expected_citations`) carry no retrieval ground truth, so
they are excluded from the metrics and reported separately — what a refusal
question retrieves is still worth seeing, because a low top score is the signal
/ask needs to decline.

Also writes `golden-embeddings.json`: the query vectors plus the 13 document
vectors, so CI can recompute these exact numbers with pure vector math — no API
key, no cost, no network.

Usage (inside the eval container, repo root mounted at /app):
    python evals/run_retrieval.py                 # embed via API, write cache + report
    python evals/run_retrieval.py --from-cache    # recompute from the cache only
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

GOLDEN = HERE / "golden.jsonl"
CACHE = HERE / "golden-embeddings.json"
REPORT = HERE / "report-retrieval.md"

EMBED_MODEL = os.environ.get("FINDABILITY_EMBED_MODEL", "gemini-embedding-2")
CHROMA_DIR = os.environ.get("FINDABILITY_CHROMA_DIR", str(ROOT / "chroma"))
COLLECTION = "findability"

TOP_K = 5
KS = (3, 5)
# Vectors are stored at this many decimals. Normalised 3072-d vectors carry
# ~1e-6 of error at 6dp, far below the similarity gaps that decide a rank.
ROUND = 6


# ---------------------------------------------------------------- data loading

def load_golden() -> list[dict]:
    if not GOLDEN.exists():
        sys.exit(f"{GOLDEN} not found — write the golden set first")
    entries = []
    for lineno, line in enumerate(GOLDEN.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            sys.exit(f"{GOLDEN}:{lineno} is not valid JSON: {exc}")
        for field in ("id", "question", "expected_citations"):
            if field not in entry:
                sys.exit(f"{GOLDEN}:{lineno} is missing '{field}'")
        entries.append(entry)
    if not entries:
        sys.exit(f"{GOLDEN} is empty")
    return entries


def load_docs() -> tuple[list[str], list[list[float]], dict[str, str]]:
    """The 13 corpus vectors, straight out of the collection the service queries."""
    import chromadb

    collection = chromadb.PersistentClient(path=CHROMA_DIR).get_collection(
        COLLECTION, embedding_function=None
    )
    got = collection.get(include=["embeddings", "metadatas"])
    ids = list(got["ids"])
    vectors = [list(map(float, v)) for v in got["embeddings"]]
    titles = {
        doc_id: (got["metadatas"][i] or {}).get("title", doc_id)
        for i, doc_id in enumerate(ids)
    }
    return ids, vectors, titles


def embed_questions(questions: list[str]) -> list[list[float]]:
    """Identical to main.embed_query: RETRIEVAL_QUERY, then L2-normalise."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("GEMINI_API_KEY is not set (pass --env-file; never inline a key)")

    from google import genai
    from google.genai import types as genai_types

    client = genai.Client(api_key=api_key)
    out = []
    for i, question in enumerate(questions, 1):
        resp = client.models.embed_content(
            model=EMBED_MODEL,
            contents=question,
            config=genai_types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
        )
        vec = list(resp.embeddings[0].values)
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        out.append([x / norm for x in vec])
        print(f"  embedded {i}/{len(questions)}", file=sys.stderr)
    return out


# ---------------------------------------------------------------- scoring

def rank(query: list[float], doc_ids: list[str], doc_vecs: list[list[float]]) -> list[tuple[str, float]]:
    """Cosine similarity over unit vectors == dot product. Highest first."""
    scored = [
        (doc_id, sum(q * d for q, d in zip(query, doc_vecs[i])))
        for i, doc_id in enumerate(doc_ids)
    ]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored


def score_entry(ranked: list[tuple[str, float]], expected: list[str]) -> dict:
    """hit@k (any expected in top-k), recall@k (share of expected in top-k), RR."""
    order = [doc_id for doc_id, _ in ranked]
    expected_set = set(expected)
    result: dict = {"top": order[:TOP_K], "scores": [round(s, 4) for _, s in ranked[:TOP_K]]}

    for k in KS:
        in_k = expected_set & set(order[:k])
        result[f"hit@{k}"] = 1.0 if in_k else 0.0
        # Refusal entries have no ground truth; they are reported, never averaged in.
        result[f"recall@{k}"] = len(in_k) / len(expected_set) if expected_set else 0.0

    result["rr"] = 0.0
    result["first_rank"] = None
    for position, doc_id in enumerate(order, 1):
        if doc_id in expected_set:
            result["rr"] = 1.0 / position
            result["first_rank"] = position
            break
    # MRR convention: only credit hits inside the retrieved window.
    if result["first_rank"] is not None and result["first_rank"] > TOP_K:
        result["rr"] = 0.0
    return result


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


# ---------------------------------------------------------------- report

def write_report(rows: list[dict], refusals: list[dict], titles: dict[str, str], overall: dict) -> None:
    lines = [
        "# Retrieval report — findability-api",
        "",
        f"Index: {len(titles)} chunks, `{EMBED_MODEL}`, cosine over L2-normalised vectors.",
        f"Scored entries: {len(rows)} (of {len(rows) + len(refusals)} golden entries; "
        f"{len(refusals)} refusal entries carry no retrieval ground truth and are "
        "excluded from the metrics).",
        "",
        "## Totals",
        "",
        "| metric | value |",
        "| --- | --- |",
    ]
    for key in ("hit@3", "hit@5", "recall@3", "recall@5", "mrr"):
        lines.append(f"| {key} | {overall[key]:.4f} |")

    lines += ["", "## By category", "", "| category | n | hit@3 | hit@5 | MRR |", "| --- | --- | --- | --- | --- |"]
    for group in ("direct", "cross"):
        subset = [r for r in rows if r["entry"].get("category") == group]
        if subset:
            lines.append(
                f"| {group} | {len(subset)} | {mean([r['hit@3'] for r in subset]):.4f} | "
                f"{mean([r['hit@5'] for r in subset]):.4f} | {mean([r['rr'] for r in subset]):.4f} |"
            )

    lines += ["", "## By question language", "",
              "The corpus is English throughout, so the `zh` row measures cross-lingual retrieval.",
              "", "| lang | n | hit@3 | hit@5 | MRR |", "| --- | --- | --- | --- | --- |"]
    for lang in ("en", "zh"):
        subset = [r for r in rows if r["entry"].get("lang") == lang]
        if subset:
            lines.append(
                f"| {lang} | {len(subset)} | {mean([r['hit@3'] for r in subset]):.4f} | "
                f"{mean([r['hit@5'] for r in subset]):.4f} | {mean([r['rr'] for r in subset]):.4f} |"
            )

    lines += ["", "## Per entry", "",
              "| id | lang | question | expected | rank of first hit | hit@3 | hit@5 | top-1 (score) |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        e = r["entry"]
        question = e["question"].replace("|", "\\|")
        question = question if len(question) <= 62 else question[:59] + "…"
        expected = ", ".join(e["expected_citations"])
        first = r["first_rank"] if r["first_rank"] is not None else "—"
        top_id = r["top"][0]
        lines.append(
            f"| {e['id']} | {e.get('lang','en')} | {question} | {expected} | {first} | "
            f"{int(r['hit@3'])} | {int(r['hit@5'])} | {top_id} ({r['scores'][0]:.4f}) |"
        )

    if refusals:
        lines += ["", "## Refusal entries (no ground truth — reported, not scored)", "",
                  "What the retriever returns for an out-of-corpus question. A low top score is "
                  "the signal `/ask` uses to decline; these rows are the evidence that the "
                  "ceiling really is lower than for answerable questions.", "",
                  "| id | lang | question | top-1 | top-1 score |",
                  "| --- | --- | --- | --- | --- |"]
        for r in refusals:
            e = r["entry"]
            question = e["question"].replace("|", "\\|")
            question = question if len(question) <= 62 else question[:59] + "…"
            lines.append(
                f"| {e['id']} | {e.get('lang','en')} | {question} | {r['top'][0]} | {r['scores'][0]:.4f} |"
            )
        answerable_top = mean([r["scores"][0] for r in rows])
        refusal_top = mean([r["scores"][0] for r in refusals])
        lines += ["",
                  f"Mean top-1 similarity — answerable: **{answerable_top:.4f}**, "
                  f"refusal: **{refusal_top:.4f}** (gap {answerable_top - refusal_top:+.4f})."]

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- main

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-cache", action="store_true",
                        help="reuse golden-embeddings.json instead of calling the embedding API")
    args = parser.parse_args()

    golden = load_golden()
    doc_ids, doc_vecs, titles = load_docs()
    print(f"golden entries: {len(golden)} | corpus vectors: {len(doc_ids)}", file=sys.stderr)

    known = set(doc_ids)
    for entry in golden:
        unknown = [c for c in entry["expected_citations"] if c not in known]
        if unknown:
            sys.exit(f"{entry['id']} cites unknown node id(s): {unknown}")

    if args.from_cache:
        if not CACHE.exists():
            sys.exit(f"{CACHE} not found — run without --from-cache once to build it")
        cached = json.loads(CACHE.read_text(encoding="utf-8"))
        by_id = {q["id"]: q["embedding"] for q in cached["queries"]}
        missing = [e["id"] for e in golden if e["id"] not in by_id]
        if missing:
            sys.exit(f"cache is stale — no embedding for {missing}; re-run without --from-cache")
        query_vecs = [by_id[e["id"]] for e in golden]
    else:
        print("embedding questions…", file=sys.stderr)
        query_vecs = embed_questions([e["question"] for e in golden])

    # Persist the vectors before scoring: embedding costs API calls, scoring is
    # free and rerunnable, so a scoring bug must never burn the calls again.
    if not args.from_cache:
        CACHE.write_text(json.dumps({
            "note": "Precomputed vectors so CI can recompute retrieval metrics with pure "
                    "vector math — no API key, no cost. Regenerate whenever golden.jsonl "
                    "or the corpus changes.",
            "embed_model": EMBED_MODEL,
            "dim": len(doc_vecs[0]),
            "normalised": True,
            "docs": [{"id": doc_ids[i], "title": titles[doc_ids[i]],
                      "embedding": [round(x, ROUND) for x in doc_vecs[i]]}
                     for i in range(len(doc_ids))],
            "queries": [{"id": e["id"], "question": e["question"],
                         "expected_citations": e["expected_citations"],
                         "category": e.get("category"), "lang": e.get("lang"),
                         "embedding": [round(x, ROUND) for x in v]}
                        for e, v in zip(golden, query_vecs)],
        }, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {CACHE.name} ({CACHE.stat().st_size // 1024} KB)", file=sys.stderr)

    rows, refusals = [], []
    for entry, qvec in zip(golden, query_vecs):
        ranked = rank(qvec, doc_ids, doc_vecs)
        scored = score_entry(ranked, entry["expected_citations"])
        scored["entry"] = entry
        (refusals if not entry["expected_citations"] else rows).append(scored)

    overall = {
        "hit@3": mean([r["hit@3"] for r in rows]),
        "hit@5": mean([r["hit@5"] for r in rows]),
        "recall@3": mean([r["recall@3"] for r in rows]),
        "recall@5": mean([r["recall@5"] for r in rows]),
        "mrr": mean([r["rr"] for r in rows]),
    }

    write_report(rows, refusals, titles, overall)
    print(f"wrote {REPORT.name}", file=sys.stderr)

    print(json.dumps({k: round(v, 4) for k, v in overall.items()}, indent=1))
    by_lang = defaultdict(list)
    for r in rows:
        by_lang[r["entry"].get("lang", "en")].append(r)
    for lang, subset in sorted(by_lang.items()):
        print(f"  {lang}: n={len(subset)} hit@3={mean([r['hit@3'] for r in subset]):.4f} "
              f"MRR={mean([r['rr'] for r in subset]):.4f}", file=sys.stderr)


if __name__ == "__main__":
    main()
