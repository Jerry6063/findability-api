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
   reference answer to be faithful to). Instead they and the fully-answerable
   entries are classified refused/answered by the judge, giving a confusion
   matrix: a system that refuses everything would look perfect on "refusal
   accuracy" alone, and this catches that.
3. **`partial` entries are measured by a different instrument, not by that one.**
   A `partial` golden entry asks for several things at once where the corpus
   carries some and not the rest, and the correct reply answers the supported half
   and names the missing half. Both binary labels are wrong for that shape; the
   binary judge called it REFUSED and printed it as a false refusal
   (PROGRESS.md, 2026-08-11). Those entries now go through a two-sided check of
   their own and the refusal matrix is left to the populations it can label.

Judge and embeddings reuse the keys the service already has — no new accounts.

Usage (inside the eval container, repo root mounted at /app):
    python evals/run_ragas.py                    # full run
    python evals/run_ragas.py --limit 3          # smoke test
    python evals/run_ragas.py --answers-from FILE  # rescore without re-answering
    python evals/run_ragas.py --answers-from FILE --reuse-metrics
                                                 # relabel + re-render only
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

METRIC_NAMES = ("faithfulness", "answer_relevancy", "context_precision", "context_recall")

# Deliberately unchanged, byte for byte, from the run that produced the 6/6 and
# 0/28 figures. Its clause "a reply that declines and then adds one grounded fact it
# does have is still REFUSED" is what makes it wrong on `partial` entries — a partial
# answer has exactly that surface shape — so `partial` entries are no longer sent
# through it at all (see PARTIAL_PROMPT and PROGRESS.md, 2026-08-11 instrument-fix
# section). On the two populations it *can* label, refusal and fully-answerable, it
# stays as it was, so those cells of the matrix remain comparable across runs.
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

# Applied ONLY to golden entries whose category is `partial` — questions that ask for
# several things at once where the corpus carries some and not the rest. Refusing and
# answering are both wrong there, so the binary judge above has no label that fits;
# this asks the two-sided question the category actually poses.
#
# The prompt states the category's premise (the corpus covers part of this question)
# because that premise is ground truth from golden.jsonl, not a verdict. It does not
# say which part, and failure is reachable in both directions: a reply that declines
# outright fails the first half, and one that answers without flagging the gap fails
# the second.
#
# The two halves are asked separately and the verdict is composed in Python rather
# than emitted by the model. That is not decoration either: asked for a single
# BOTH/MISSING token, this judge returned MISSING on g35 three times out of three,
# and the same judge on the same rubric returned BOTH with correct reasoning the
# moment it had somewhere to put the reasoning. A label that flips on whether the
# model is allowed to think is not a label; splitting it removes the snap judgement
# and makes both halves auditable in the answers file.
PARTIAL_PROMPT = """You are checking two specific properties of a reply from a
portfolio Q&A service.

The service answers only from a fixed corpus about one designer. The question below
asks for several things at once, and the corpus carries some of them but not the rest.
A correct reply does two things: it answers the part the corpus supports, naming
concrete portfolio facts, and it states plainly that the remaining part is not in the
portfolio.

QUESTION: {question}

REPLY: {answer}

Answer in exactly two lines, nothing else:

ANSWERED_PART: yes or no — does the reply name concrete portfolio facts (projects,
roles, tools, counts, dates) that answer part of what was asked?
STATED_GAP: yes or no — does the reply say that some part of what was asked is not
in the portfolio?"""


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


def expected_outcome(entry: dict) -> str:
    """What the golden set says the right shape of reply is.

    Ground truth, read off golden.jsonl — never shown to the judge.
    """
    if not entry["expected_citations"]:
        return "refused"
    return "partial" if entry.get("category") == "partial" else "answered"


def partial_halves(reply: str) -> dict:
    """Parse the two-line partial check. Verdict is composed here, not by the model."""
    halves = {"answered_part": False, "stated_gap": False}
    for line in reply.splitlines():
        for key, marker in (("answered_part", "ANSWERED_PART"), ("stated_gap", "STATED_GAP")):
            if line.strip().startswith(marker):
                halves[key] = line.split(":", 1)[-1].strip().startswith("YES")
    return halves


def classify_outcomes(judge, results: list[dict]) -> None:
    """Label every answer with the instrument that can actually label it.

    Refusal and fully-answerable entries go through the unchanged binary judge.
    `partial` entries go through the two-sided partial check instead: a binary
    refused/answered verdict on a partial answer is not a measurement of the
    service, it is an artefact of the label set.
    """
    for r in results:
        r["expected_outcome"] = expected_outcome(r)
        r["should_refuse"] = r["expected_outcome"] == "refused"

        if r["expected_outcome"] == "partial":
            reply = judge.invoke(
                PARTIAL_PROMPT.format(question=r["question"], answer=r["answer"])
            ).content.upper()
            halves = partial_halves(reply)
            r["partial_check"] = halves
            r["answered_in_part"] = halves["answered_part"] and halves["stated_gap"]
            r["refused"] = None          # the binary judge is not run on these
            r["outcome"] = "partial" if r["answered_in_part"] else "not-partial"
        else:
            verdict = judge.invoke(
                REFUSAL_PROMPT.format(question=r["question"], answer=r["answer"])
            ).content.strip().upper()
            r["refused"] = verdict.startswith("REFUS")
            r["answered_in_part"] = None
            r["outcome"] = "refused" if r["refused"] else "answered"


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
        for metric in METRIC_NAMES:
            value = row.get(metric)
            r[metric] = None if value is None or (isinstance(value, float) and math.isnan(value)) else float(value)

    return means_from(results)


def means_from(results: list[dict]) -> dict:
    """Per-metric means over the answerable entries, from values already on the rows."""
    answerable = [r for r in results if r["expected_citations"]]

    def mean_of(metric: str) -> float:
        values = [r[metric] for r in answerable if r.get(metric) is not None]
        return sum(values) / len(values) if values else float("nan")

    return {m: mean_of(m) for m in METRIC_NAMES}


# ---------------------------------------------------------------- report

CONTEXT_PRECISION_NOTE = """\
`context_precision` is printed for continuity and **is not read as a retrieval
signal on this corpus** — the mechanism is below, under "Why `context_precision`
collapses on multi-source questions". `faithfulness` is not a valid gate here
either (PROGRESS.md, Stage E). The two metrics that survived audit are
`answer_relevancy` and `context_recall`; the deterministic retrieval metrics in
`report-retrieval.md` are what CI actually gates on."""


def context_precision_section(results: list[dict]) -> list[str]:
    """Break context_precision out by how many sources the reference aggregates.

    Computed from the data rather than hard-coded, so it stays honest if the
    golden set changes.
    """
    scored = [r for r in results
              if r["expected_citations"] and r.get("context_precision") is not None]
    if not scored:
        return []

    groups = {
        "one expected source": [r for r in scored if len(r["expected_citations"]) == 1],
        "two or more expected sources": [r for r in scored if len(r["expected_citations"]) > 1],
    }

    lines = [
        "",
        "## Why `context_precision` collapses on multi-source questions",
        "",
        "Ragas asks its judge, once per retrieved chunk, whether that chunk \"was useful "
        "in arriving at the given answer\" — where the answer it is shown is the **whole** "
        "golden reference. When the reference aggregates several projects, no single "
        "chunk supports the whole of it, the judge votes 0 on every chunk, and average "
        "precision is `0 / (0 + 1e-10)` = exactly 0.000. The verdict is driven by the "
        "shape of the reference, not by whether retrieval was right.",
        "",
        "| reference aggregates | n | mean ctx.prec. | entries at exactly 0.000 |",
        "| --- | --- | --- | --- |",
    ]
    for label, subset in groups.items():
        if not subset:
            continue
        mean = sum(r["context_precision"] for r in subset) / len(subset)
        zeros = sum(1 for r in subset if r["context_precision"] < 1e-6)
        lines.append(f"| {label} | {len(subset)} | {mean:.4f} | {zeros} |")

    worst = [r for r in scored
             if r["context_precision"] < 1e-6 and set(r["expected_citations"]) & set(r["context_ids"])]
    if worst:
        lines += [
            "",
            "Entries scoring 0.000 while retrieval actually found expected chunks:",
            "",
        ]
        for r in sorted(worst, key=lambda r: r["id"]):
            found = [c for c in r["context_ids"] if c in r["expected_citations"]]
            lines.append(
                f"- `{r['id']}` ({r['category']}) — retrieved {len(found)} of "
                f"{len(r['expected_citations'])} expected ids "
                f"(`{', '.join(found)}`) and still scores 0.000."
            )
    lines += [
        "",
        "Verified in isolation against the same judge: replaying a 0.000 entry chunk by "
        "chunk and trimming the reference to the half each chunk covers flips every "
        "verdict from 0 to 1, with the retrieval byte-identical. A number that can be "
        "moved from 0.000 to 1.000 by editing `golden.jsonl` alone is not measuring the "
        "service.",
    ]
    return lines


def write_report(results: list[dict], means: dict) -> None:
    answerable = [r for r in results if r["expected_citations"]]
    refusal = [r for r in results if r["expected_outcome"] == "refused"]
    partial = [r for r in results if r["expected_outcome"] == "partial"]
    full_answer = [r for r in results if r["expected_outcome"] == "answered"]

    correctly_refused = sum(1 for r in refusal if r["refused"])
    wrongly_refused = sum(1 for r in full_answer if r["refused"])
    partial_ok = sum(1 for r in partial if r["answered_in_part"])

    lines = [
        "# Ragas report — findability-api `/ask`",
        "",
        f"Judge: `{JUDGE_MODEL}` via `langchain-anthropic`. "
        f"Embeddings for answer relevancy: `{EMBED_MODEL}`, the same model the corpus is "
        "indexed with. Both reuse keys the service already holds — no new accounts.",
        "",
        f"Samples: {len(answerable)} answerable golden entries scored on the four metrics; "
        f"{len(refusal) + len(full_answer)} answers (including {len(refusal)} out-of-corpus "
        f"questions) classified refused/answered, and {len(partial)} `partial` entries "
        "checked separately.",
        "",
        "## Metric means (answerable entries)",
        "",
        "| metric | mean |",
        "| --- | --- |",
    ]
    for metric, value in means.items():
        lines.append(f"| {metric} | {value:.4f} |")
    lines += ["", CONTEXT_PRECISION_NOTE]

    def pct(numerator: int, denominator: int) -> str:
        return f"{numerator}/{denominator} = {numerator / denominator:.1%}" if denominator else "n/a"

    lines += [f"", f"## Refusal behaviour ({len(refusal) + len(full_answer)} of "
              f"{len(results)} entries)", "",
              "Measured in both directions on purpose: a service that refuses everything "
              "would score 100% on \"did it refuse the out-of-corpus questions\" alone.",
              "",
              f"The {len(partial)} `partial` entries are **not** in this table. They ask for "
              "several things at once where the corpus carries some and not the rest, so "
              "both binary labels are wrong for them; folding them in is what made this "
              "report print a 6.7% false-refusal rate on 2026-08-11 while the service had "
              "in fact refused nothing it could answer. They are measured below instead.",
              "",
              "| | refused | answered |", "| --- | --- | --- |",
              f"| **should refuse** ({len(refusal)}) | {correctly_refused} | {len(refusal) - correctly_refused} |",
              f"| **should answer** ({len(full_answer)}) | {wrongly_refused} | {len(full_answer) - wrongly_refused} |",
              "",
              f"- Refusal accuracy (out-of-corpus correctly declined): "
              f"**{pct(correctly_refused, len(refusal))}**",
              f"- False-refusal rate (fully-answerable wrongly declined): "
              f"**{pct(wrongly_refused, len(full_answer))}**",
              f"- Citations on refusals: "
              f"{pct(sum(1 for r in refusal if not r['citations']), len(refusal))} returned none "
              "(an unsourced refusal is the correct shape).",
              ]

    if partial:
        lines += ["", f"## Partial answers ({len(partial)} entries)", "",
                  "A separate two-sided check, not a third value in the matrix above: does the "
                  "reply answer the part the corpus supports **and** state that the rest is not "
                  "in the portfolio? Failing either half fails the check.",
                  "",
                  f"- Answered in part and flagged the gap: **{pct(partial_ok, len(partial))}**",
                  ""]
        for r in partial:
            lines.append(
                f"- `{r['id']}` ({r['lang']}) — "
                f"{'both halves present' if r['answered_in_part'] else '**MISSING a half**'}; "
                f"cited `{', '.join(r['citations']) or 'none'}`"
            )

    lines += context_precision_section(results)

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
              "| id | cat | lang | faith. | ans.rel. | ctx.prec. | ctx.rec. | outcome | expected | cited |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in results:
        def fmt(metric: str) -> str:
            value = r.get(metric)
            return "—" if value is None else f"{value:.3f}"
        mark = "" if r["outcome"] == r["expected_outcome"] else " **✗**"
        lines.append(
            f"| {r['id']} | {r['category']} | {r['lang']} | {fmt('faithfulness')} | "
            f"{fmt('answer_relevancy')} | {fmt('context_precision')} | {fmt('context_recall')} | "
            f"{r['outcome']}{mark} | {r['expected_outcome']} | {', '.join(r['citations']) or '—'} |"
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
    parser.add_argument("--reuse-metrics", action="store_true",
                        help="skip the Ragas call and take the four per-entry metric "
                             "values already stored in the answers file. For changes "
                             "that only touch the outcome labeller or the report: "
                             "re-running Ragas would swing faithfulness by judge noise "
                             "alone (±0.8 on a single entry, PROGRESS.md 2026-08-11) and "
                             "move numbers the change is not supposed to touch.")
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

    if args.reuse_metrics and not args.answers_from:
        sys.exit("--reuse-metrics only makes sense with --answers-from")

    judge = build_judge()
    print("labelling answer outcomes…", file=sys.stderr)
    classify_outcomes(judge, results)

    if args.reuse_metrics:
        missing = [r["id"] for r in results
                   if r["expected_citations"] and r.get("faithfulness") is None]
        if missing:
            sys.exit(f"--reuse-metrics: no stored metrics for {', '.join(missing)}")
        print("reusing stored Ragas metrics (no metric calls)", file=sys.stderr)
        means = means_from(results)
    else:
        print("scoring with Ragas…", file=sys.stderr)
        means = score_with_ragas(judge, results)

    ANSWERS.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    write_report(results, means)
    print(f"wrote {REPORT.name}", file=sys.stderr)
    print(json.dumps({k: round(v, 4) for k, v in means.items()}, indent=1))


if __name__ == "__main__":
    main()
