"""Trace the real /ask pipeline into a local Arize Phoenix instance.

Phoenix is open-source and runs on localhost — no account, no vendor key, nothing
leaves the machine. The Anthropic call is auto-instrumented by OpenInference; the
two steps that happen *before* it (query embedding, Chroma retrieval) are wrapped
here so the trace shows the whole RAG path rather than just the completion:

    ask (chain)
      ├─ embed_query (embedding)   gemini-embedding-2, 3072-d
      ├─ retrieve (retriever)      top-4 chunks with ids + scores
      └─ Messages (llm)            claude-sonnet-4-5, auto-instrumented

Nothing in `main.py` is edited — `embed_query` and `INDEX.query` are wrapped for
the duration of the run, so what gets traced is the production code path.

    # 1. start Phoenix (separate shell / background)
    phoenix serve
    # 2. send traced questions at it
    python evals/trace_ask.py --questions 6
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

COLLECTOR = os.environ.get("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006")
PROJECT = os.environ.get("PHOENIX_PROJECT_NAME", "findability-ask")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=int, default=6,
                        help="how many golden questions to send (default 6)")
    args = parser.parse_args()

    import json

    from openinference.instrumentation.anthropic import AnthropicInstrumentor
    from openinference.semconv.trace import (DocumentAttributes, EmbeddingAttributes,
                                             SpanAttributes)
    from phoenix.otel import register

    tracer_provider = register(project_name=PROJECT, endpoint=f"{COLLECTOR}/v1/traces",
                               auto_instrument=False)
    AnthropicInstrumentor().instrument(tracer_provider=tracer_provider)
    tracer = tracer_provider.get_tracer("findability.ask")

    import main as service

    if not service.INDEX.ready:
        sys.exit(f"index not ready: {service.INDEX.error}")

    original_embed = service.embed_query
    original_query = service.INDEX.query

    def traced_embed(text: str):
        with tracer.start_as_current_span("embed_query") as span:
            span.set_attribute(SpanAttributes.OPENINFERENCE_SPAN_KIND, "EMBEDDING")
            span.set_attribute(SpanAttributes.EMBEDDING_MODEL_NAME, service.EMBED_MODEL)
            span.set_attribute(
                f"{SpanAttributes.EMBEDDING_EMBEDDINGS}.0.{EmbeddingAttributes.EMBEDDING_TEXT}",
                text)
            vector = original_embed(text)
            span.set_attribute("embedding.dimensions", len(vector))
            return vector

    def traced_query(vector, k):
        with tracer.start_as_current_span("retrieve") as span:
            span.set_attribute(SpanAttributes.OPENINFERENCE_SPAN_KIND, "RETRIEVER")
            span.set_attribute("retrieval.top_k", k)
            hits = original_query(vector, k)
            for i, hit in enumerate(hits):
                prefix = f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}"
                span.set_attribute(f"{prefix}.{DocumentAttributes.DOCUMENT_ID}", hit["id"])
                span.set_attribute(f"{prefix}.{DocumentAttributes.DOCUMENT_SCORE}", hit["score"])
                span.set_attribute(f"{prefix}.{DocumentAttributes.DOCUMENT_CONTENT}",
                                   hit["document"][:2000])
            span.set_attribute("retrieval.hit_ids", json.dumps([h["id"] for h in hits]))
            return hits

    service.embed_query = traced_embed
    service.INDEX.query = traced_query

    golden = [json.loads(l) for l in (HERE / "golden.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    # A deliberate mix: answerable entries plus the out-of-corpus ones, so the
    # trace view shows both a grounded answer and an honest refusal.
    answerable = [e for e in golden if e["expected_citations"]]
    refusals = [e for e in golden if not e["expected_citations"]]
    take = max(1, args.questions - 2)
    selected = answerable[:take] + refusals[:2]

    print(f"tracing {len(selected)} questions into Phoenix project '{PROJECT}' at {COLLECTOR}",
          file=sys.stderr)

    try:
        for i, entry in enumerate(selected, 1):
            with tracer.start_as_current_span("ask") as span:
                span.set_attribute(SpanAttributes.OPENINFERENCE_SPAN_KIND, "CHAIN")
                span.set_attribute(SpanAttributes.INPUT_VALUE, entry["question"])
                span.set_attribute("golden.id", entry["id"])
                span.set_attribute("golden.category", entry.get("category", ""))
                span.set_attribute("golden.expects_refusal", not entry["expected_citations"])
                response = service.ask(service.AskRequest(question=entry["question"]))
                span.set_attribute(SpanAttributes.OUTPUT_VALUE, response.answer)
                span.set_attribute("ask.citations", json.dumps([c.id for c in response.citations]))
            print(f"  [{i}/{len(selected)}] {entry['id']} "
                  f"cites={[c.id for c in response.citations]}", file=sys.stderr)
    finally:
        service.embed_query = original_embed
        service.INDEX.query = original_query

    # OTLP export is batched; give the processor a moment to flush before exit.
    tracer_provider.force_flush()
    time.sleep(2)
    print(f"done — open {COLLECTOR} and select project '{PROJECT}'", file=sys.stderr)


if __name__ == "__main__":
    main()
