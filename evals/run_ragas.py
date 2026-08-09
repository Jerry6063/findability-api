"""Ragas evaluation of the real /ask pipeline.

Runs every golden question through `main.ask` — the same function the HTTP
endpoint calls, same retrieval, same system prompt, same model — and scores the
result with Ragas: faithfulness, answer relevancy, context precision, context
recall.

Two things this does that a stock Ragas script does not:

1. **Contexts are captured from the answering call itself.** `INDEX.query` is
   wrapped for the duration of the run, so the contexts Ragas scores are byte-for-byte
   the ones the model actually saw — not a second retrieval that might drift.
2. **Refusals are scored as a classification problem, in both directions.** The
   six out-of-corpus questions are not run through the four metrics (there is no
   reference answer to be faithful to). Instead every one of the 30 answers is
   classified refused/answered by the judge, giving a confusion matrix: a system
   that refuses everything would look perfect on "refusal accuracy" alone, and
   this catches that.

Judge and embeddings reuse the keys the service already has — no new accounts.

Usage (inside the eval container, repo root mounted at /app):
    python evals/run_ragas.py                    # full run
    python evals/run_ragas.py --limit 3          # smoke test
    python evals/run_ragas.py --answers-from FILE  # rescore without re-answering
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

GOLDEN = HERE / "golden.jsonl"
ANSWERS = HERE / "ask-answers.json"
REPORT = HERE / "report-ragas.md"

# Cheap tier on purpose: the judge does bulk classification, not authorship.
JUDGE_MODEL = os.environ.get("FINDABILITY_JUDGE_MODEL", "claude-haiku-4-5")
CORPUS_AWARE = False
EMBED_MODEL = os.environ.get("FINDABILITY_EMBED_MODEL", "gemini-embedding-2")

# Appended to Ragas' NLI instruction when --corpus-aware-judge is set.
# It encodes the two failure modes a 3-lens manual audit found in the default
# judging on THIS corpus (see PROGRESS.md, Stage E): the judge would not accept a
# natural-language rendering of a terse `Key: value` line as support, and it scored
# each statement against the topically-nearest chunk instead of the whole context.
# Both are corrections toward the metric's own definition, not thumbs on the scale —
# the fixed judge is validated against an independent ground truth, not against
# whether the number went up.
CORPUS_AWARE_NLI = """

The context is assembled from portfolio entries that encode facts as terse labelled lines, for example `Credits — Collaborators: Xiaotong Qin`, `Credits — Period: Dec 2023 — Nov 2024`, `Highlights: ...`, or `Walkthrough — Title: ...`. A statement that renders such a line in ordinary English is DIRECTLY INFERABLE from it — return 1. Do not require the statement to match the context's phrasing, ordering, or formatting.

Judge every statement against the ENTIRE context given to you, not only the part that looks most related to the question. The context may contain several entries; a statement supported by any of them is supported."""

REFUSAL_PROMPT = """You are labelling the output of a portfolio Q&A service.

The service is only allowed to answer from a fixed corpus about one designer. When
a question falls outside that corpus it is supposed to say so plainly instead of
guessing.

Answer with exactly one word — REFUSED or ANSWERED.

REFUSED: the reply declines, says the portfolio does not cover this, or states the
information is not available. A reply that declines and then adds one grounded
fact it does have is still REFUSED.
ANSWERED: the reply gives substantive information addressing the question.

QUESTION: {question}

REPLY: {answer}

One word:"""


# ---------------------------------------------------------------- embeddings

class ServiceEmbeddings:
    """LangChain Embeddings over the exact model the service indexes with.

    Ragas needs embeddings for answer relevancy. Rather than introduce a second
    embedding vendor, this reuses `gemini-embedding-2` through the same client
    `ingest.py` and `main.py` use, with the same L2 normalisation.
    """

    def __init__(self, model: str = EMBED_MODEL) -> None:
        from google import genai

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            sys.exit("GEMINI_API_KEY is not set (pass --env-file; never inline a key)")
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def _embed(self, text: str, task_type: str) -> list[float]:
        from google.genai import types as genai_types

        # Ragas fans answer-relevancy embeddings out concurrently, which walks
        # straight into the free tier's 100-requests-per-minute ceiling; a 429
        # there silently drops the sample from the metric mean. Retry rather than
        # quietly score fewer samples than the report claims.
        delay = 8.0
        for attempt in range(5):
            try:
                resp = self._client.models.embed_content(
                    model=self._model,
                    contents=text,
                    config=genai_types.EmbedContentConfig(task_type=task_type),
                )
                break
            except Exception as exc:
                if "RESOURCE_EXHAUSTED" not in str(exc) and "429" not in str(exc):
                    raise
                if attempt == 4:
                    raise
                time.sleep(delay)
                delay *= 1.6
        vec = list(resp.embeddings[0].values)
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t, "RETRIEVAL_DOCUMENT") for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text, "RETRIEVAL_QUERY")

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.embed_documents(texts)

    async def aembed_query(self, text: str) -> list[float]:
        return self.embed_query(text)


# ---------------------------------------------------------------- pipeline run

def load_golden(limit: int | None) -> list[dict]:
    entries = [json.loads(line) for line in GOLDEN.read_text(encoding="utf-8").splitlines() if line.strip()]
    return entries[:limit] if limit else entries


def run_pipeline(entries: list[dict]) -> list[dict]:
    """Answer every question through main.ask, capturing what the model was shown."""
    import main as service

    if not service.INDEX.ready:
        sys.exit(f"index not ready: {service.INDEX.error}")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set (pass --env-file; never inline a key)")

    captured: dict = {}
    original_query = service.INDEX.query

    def recording_query(vector, k):
        hits = original_query(vector, k)
        captured["hits"] = hits
        return hits

    service.INDEX.query = recording_query
    print(f"answer model: {service.ANSWER_MODEL} | ask top-k: {service.ASK_TOP_K}", file=sys.stderr)

    results = []
    try:
        for i, entry in enumerate(entries, 1):
            captured.clear()
            started = time.monotonic()
            response = service.ask(service.AskRequest(question=entry["question"]))
            hits = captured.get("hits", [])
            results.append({
                "id": entry["id"],
                "question": entry["question"],
                "answer": response.answer,
                "citations": [c.id for c in response.citations],
                "contexts": [h["document"] for h in hits],
                "context_ids": [h["id"] for h in hits],
                "context_scores": [h["score"] for h in hits],
                "reference": entry["reference_answer"],
                "expected_citations": entry["expected_citations"],
                "category": entry.get("category"),
                "lang": entry.get("lang"),
                "latency_s": round(time.monotonic() - started, 2),
            })
            print(f"  [{i}/{len(entries)}] {entry['id']} "
                  f"cites={results[-1]['citations']} ({results[-1]['latency_s']}s)", file=sys.stderr)
    finally:
        service.INDEX.query = original_query
    return results


# ---------------------------------------------------------------- judging

def build_judge():
    from langchain_anthropic import ChatAnthropic

    # 4096, not 1024: Ragas' statement-extraction step emits a JSON list of every
    # claim in the answer, and a 1024 ceiling truncated one mid-run
    # (LLMDidNotFinishException). The judge's own replies stay short, so the
    # higher ceiling costs nothing on the runs that don't need it.
    return ChatAnthropic(model=JUDGE_MODEL, temperature=0, max_tokens=4096,
                         timeout=120, stop=None)


def classify_refusals(judge, results: list[dict]) -> None:
    """Label every answer refused/answered — both error directions matter."""
    for r in results:
        verdict = judge.invoke(
            REFUSAL_PROMPT.format(question=r["question"], answer=r["answer"])
        ).content.strip().upper()
        r["refused"] = verdict.startswith("REFUS")
        r["should_refuse"] = not r["expected_citations"]


def score_with_ragas(judge, results: list[dict]) -> dict:
    """Four Ragas metrics over the answerable entries only."""
    from ragas import evaluate
    from ragas.dataset_schema import EvaluationDataset, SingleTurnSample
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import (answer_relevancy, context_precision,
                               context_recall, faithfulness)

    if CORPUS_AWARE:
        prompts = faithfulness.get_prompts()
        nli = prompts["n_l_i_statement_prompt"]
        nli.instruction = nli.instruction + CORPUS_AWARE_NLI
        faithfulness.set_prompts(**{"n_l_i_statement_prompt": nli})
        print("judge: corpus-aware NLI instruction applied", file=sys.stderr)

    answerable = [r for r in results if r["expected_citations"]]
    samples = [
        SingleTurnSample(
            user_input=r["question"],
            retrieved_contexts=r["contexts"],
            response=r["answer"],
            reference=r["reference"],
        )
        for r in answerable
    ]

    scores = evaluate(
        dataset=EvaluationDataset(samples=samples),
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        llm=LangchainLLMWrapper(judge),
        embeddings=LangchainEmbeddingsWrapper(ServiceEmbeddings()),
        show_progress=True,
    )

    frame = scores.to_pandas()
    for r, (_, row) in zip(answerable, frame.iterrows()):
        for metric in ("faithfulness", "answer_relevancy", "context_precision", "context_recall"):
            value = row.get(metric)
            r[metric] = None if value is None or (isinstance(value, float) and math.isnan(value)) else float(value)

    def mean_of(metric: str) -> float:
        values = [r[metric] for r in answerable if r.get(metric) is not None]
        return sum(values) / len(values) if values else float("nan")

    return {m: mean_of(m) for m in
            ("faithfulness", "answer_relevancy", "context_precision", "context_recall")}


# ---------------------------------------------------------------- report

def write_report(results: list[dict], means: dict) -> None:
    answerable = [r for r in results if r["expected_citations"]]
    refusal = [r for r in results if not r["expected_citations"]]

    correctly_refused = sum(1 for r in refusal if r["refused"])
    wrongly_refused = sum(1 for r in answerable if r["refused"])

    lines = [
        "# Ragas report — findability-api `/ask`",
        "",
        f"Judge: `{JUDGE_MODEL}` via `langchain-anthropic`. "
        f"Embeddings for answer relevancy: `{EMBED_MODEL}`, the same model the corpus is "
        "indexed with. Both reuse keys the service already holds — no new accounts.",
        "",
        f"Samples: {len(answerable)} answerable golden entries scored on the four metrics; "
        f"all {len(results)} answers (including {len(refusal)} out-of-corpus questions) "
        "classified refused/answered.",
        "",
        "## Metric means (answerable entries)",
        "",
        "| metric | mean |",
        "| --- | --- |",
    ]
    for metric, value in means.items():
        lines.append(f"| {metric} | {value:.4f} |")

    def pct(numerator: int, denominator: int) -> str:
        return f"{numerator}/{denominator} = {numerator / denominator:.1%}" if denominator else "n/a"

    lines += [f"", f"## Refusal behaviour (all {len(results)} entries)", "",
              "Measured in both directions on purpose: a service that refuses everything "
              "would score 100% on \"did it refuse the out-of-corpus questions\" alone.",
              "",
              "| | refused | answered |", "| --- | --- | --- |",
              f"| **should refuse** ({len(refusal)}) | {correctly_refused} | {len(refusal) - correctly_refused} |",
              f"| **should answer** ({len(answerable)}) | {wrongly_refused} | {len(answerable) - wrongly_refused} |",
              "",
              f"- Refusal accuracy (out-of-corpus correctly declined): "
              f"**{pct(correctly_refused, len(refusal))}**",
              f"- False-refusal rate (answerable wrongly declined): "
              f"**{pct(wrongly_refused, len(answerable))}**",
              f"- Citations on refusals: "
              f"{pct(sum(1 for r in refusal if not r['citations']), len(refusal))} returned none "
              "(an unsourced refusal is the correct shape).",
              ]

    scored = [r for r in answerable if r.get("faithfulness") is not None]
    worst = sorted(scored, key=lambda r: (
        r.get("faithfulness", 1), r.get("context_recall", 1)))[:3]
    if worst:
        lines += ["", "## Three weakest entries", ""]
        for r in worst:
            lines += [
                f"### {r['id']} ({r['category']}, {r['lang']}) — faithfulness "
                f"{r['faithfulness']:.3f}, answer_relevancy {r.get('answer_relevancy', float('nan')):.3f}, "
                f"context_precision {r.get('context_precision', float('nan')):.3f}, "
                f"context_recall {r.get('context_recall', float('nan')):.3f}",
                "",
                f"**Q** {r['question']}",
                "",
                f"**Expected citations** `{', '.join(r['expected_citations'])}` — "
                f"**retrieved** `{', '.join(r['context_ids'])}` — "
                f"**cited** `{', '.join(r['citations']) or 'none'}`",
                "",
                f"**Answer** {r['answer']}",
                "",
            ]

    lines += ["", "## Per entry", "",
              "| id | cat | lang | faith. | ans.rel. | ctx.prec. | ctx.rec. | refused | cited |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in results:
        def fmt(metric: str) -> str:
            value = r.get(metric)
            return "—" if value is None else f"{value:.3f}"
        lines.append(
            f"| {r['id']} | {r['category']} | {r['lang']} | {fmt('faithfulness')} | "
            f"{fmt('answer_relevancy')} | {fmt('context_precision')} | {fmt('context_recall')} | "
            f"{'yes' if r.get('refused') else 'no'} | {', '.join(r['citations']) or '—'} |"
        )

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- main

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, help="only run the first N golden entries")
    parser.add_argument("--answers-from", type=Path,
                        help="reuse a previous ask-answers.json instead of re-answering")
    parser.add_argument("--corpus-aware-judge", action="store_true",
                        help="append corpus-format guidance to Ragas' NLI instruction")
    parser.add_argument("--tag", default="",
                        help="suffix for the output files, so a second judge does not "
                             "overwrite the first run's report")
    args = parser.parse_args()

    global ANSWERS, REPORT, CORPUS_AWARE
    CORPUS_AWARE = args.corpus_aware_judge
    if args.tag:
        ANSWERS = HERE / f"ask-answers.{args.tag}.json"
        REPORT = HERE / f"report-ragas.{args.tag}.md"

    entries = load_golden(args.limit)

    if args.answers_from:
        results = json.loads(args.answers_from.read_text(encoding="utf-8"))
        print(f"reusing {len(results)} answers from {args.answers_from}", file=sys.stderr)
    else:
        print(f"running /ask over {len(entries)} questions…", file=sys.stderr)
        results = run_pipeline(entries)
        ANSWERS.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"wrote {ANSWERS.name}", file=sys.stderr)

    judge = build_judge()
    print("classifying refusals…", file=sys.stderr)
    classify_refusals(judge, results)

    print("scoring with Ragas…", file=sys.stderr)
    means = score_with_ragas(judge, results)

    ANSWERS.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    write_report(results, means)
    print(f"wrote {REPORT.name}", file=sys.stderr)
    print(json.dumps({k: round(v, 4) for k, v in means.items()}, indent=1))


if __name__ == "__main__":
    main()
