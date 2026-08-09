"""findability-api — semantic layer behind haozhengrui.work/#findability.

Rebuilds the 2024 "AI-Enabled Findability" research as a live feature: the
portfolio's projects / experience / lab entries are embedded once by `ingest.py`
into a Chroma collection, and this service answers three questions over it —
what matches this phrase (/search), what else should I look at (/related),
and what does the body of work say about X (/ask, Claude grounded in retrieved
chunks only).

Two-layer by design: the site ships `findability-data.json` and degrades to
static graph + keyword search when this service is unreachable. Nothing here is
required for the page to work; it is the online upgrade path.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from collections import defaultdict, deque
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

# --- configuration (env only; no secret ever lands in code or git) ----------

EMBED_MODEL = os.environ.get("FINDABILITY_EMBED_MODEL", "gemini-embedding-2")
ANSWER_MODEL = os.environ.get("FINDABILITY_ANSWER_MODEL", "claude-sonnet-4-5")
CHROMA_DIR = os.environ.get("FINDABILITY_CHROMA_DIR", "./chroma")
DATA_PATH = os.environ.get("FINDABILITY_DATA", "./findability-data.json")
COLLECTION = "findability"

SEARCH_TOP_K = 5
# 5, not 4: measured on the golden set. hit@4 is already 1.0000, so a fifth chunk
# never decides *whether* an answer is possible — it decides whether an enumerating
# question ("which of his projects use X") can be answered completely. At k=4 the
# ML/CV question saw one of its three supporting chunks and honestly declined; at
# k=5 it sees two and answers. The fifth chunk is a wanted citation only 2/24 of
# the time and costs ~300 input tokens, which is the trade being made here.
ASK_TOP_K = 5
ASK_MAX_TOKENS = int(os.environ.get("FINDABILITY_MAX_TOKENS", "600"))
RATE_LIMIT = int(os.environ.get("FINDABILITY_RATE_LIMIT", "10"))  # requests
RATE_WINDOW = 60.0  # seconds

ALLOWED_ORIGINS = [
    "https://haozhengrui.work",
    "https://www.haozhengrui.work",
]
ALLOWED_ORIGINS += [o for o in os.environ.get("FINDABILITY_CORS", "").split(",") if o]
LOCALHOST_ORIGIN_RE = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"

app = FastAPI(
    title="findability-api",
    version="0.1.0",
    description="Semantic search / related-work / grounded Q&A over Jerry Hao's portfolio.",
)


# --- rate limit: in-memory, per client IP -----------------------------------

_hits: dict[str, deque] = defaultdict(deque)
_hits_lock = threading.Lock()
EXEMPT_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def rate_limit(request: Request, call_next):
    if request.url.path in EXEMPT_PATHS or request.method == "OPTIONS":
        return await call_next(request)
    ip, now = client_ip(request), time.monotonic()
    with _hits_lock:
        bucket = _hits[ip]
        while bucket and now - bucket[0] > RATE_WINDOW:
            bucket.popleft()
        if len(bucket) >= RATE_LIMIT:
            retry_after = int(RATE_WINDOW - (now - bucket[0])) + 1
            return JSONResponse(
                status_code=429,
                content={"detail": f"Rate limit is {RATE_LIMIT} requests per minute."},
                headers={"Retry-After": str(retry_after)},
            )
        bucket.append(now)
    return await call_next(request)


# Order matters: rate limit is added first so CORS ends up the OUTER layer and
# 429 responses still carry Access-Control-Allow-Origin.
app.add_middleware(BaseHTTPMiddleware, dispatch=rate_limit)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=LOCALHOST_ORIGIN_RE,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# --- index + static data ----------------------------------------------------

class _Index:
    """Chroma collection + the precomputed node/related tables."""

    def __init__(self) -> None:
        self.nodes: dict[str, dict] = {}
        self.related: dict[str, list] = {}
        self.collection = None
        self.error: Optional[str] = None
        self.load()

    def load(self) -> None:
        try:
            with open(DATA_PATH, encoding="utf-8") as fh:
                payload = json.load(fh)
            self.nodes = {n["id"]: n for n in payload["nodes"]}
            self.related = payload.get("related", {})
        except Exception as exc:
            self.error = f"{DATA_PATH} unreadable: {exc}"
            return
        try:
            import chromadb

            client = chromadb.PersistentClient(path=CHROMA_DIR)
            self.collection = client.get_collection(COLLECTION, embedding_function=None)
        except Exception as exc:
            self.error = f"chroma collection unavailable: {exc}"

    @property
    def ready(self) -> bool:
        return self.collection is not None and bool(self.nodes)

    def query(self, vector: list[float], k: int) -> list[dict]:
        res = self.collection.query(
            query_embeddings=[vector],
            n_results=k,
            include=["documents", "metadatas", "distances"],
        )
        hits = []
        for i, doc_id in enumerate(res["ids"][0]):
            distance = res["distances"][0][i]
            node = self.nodes.get(doc_id, {})
            hits.append({
                "id": doc_id,
                "title": node.get("title") or res["metadatas"][0][i].get("title", doc_id),
                "type": node.get("type") or res["metadatas"][0][i].get("type", ""),
                # cosine space: distance = 1 - cosine similarity
                "score": round(max(0.0, min(1.0, 1.0 - distance)), 4),
                "document": res["documents"][0][i],
            })
        return hits


INDEX = _Index()


def embed_query(text: str) -> list[float]:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(503, "GEMINI_API_KEY is not configured")

    from google import genai
    from google.genai import types as genai_types

    client = genai.Client(api_key=api_key)
    try:
        resp = client.models.embed_content(
            model=EMBED_MODEL,
            contents=text,
            config=genai_types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
        )
    except Exception as exc:
        raise HTTPException(502, f"Embedding call failed: {exc}") from exc
    vec = list(resp.embeddings[0].values)
    norm = sum(x * x for x in vec) ** 0.5 or 1.0
    return [x / norm for x in vec]


def require_index() -> None:
    if not INDEX.ready:
        raise HTTPException(503, f"Index not loaded ({INDEX.error or 'unknown reason'})")


# --- wire types -------------------------------------------------------------

class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)


class SearchHit(BaseModel):
    id: str
    title: str
    type: str
    score: float


class SearchResponse(BaseModel):
    query: str
    results: list[SearchHit]


class RelatedItem(BaseModel):
    id: str
    title: str
    type: str
    summary: str = ""


class RelatedResponse(BaseModel):
    id: str
    related: list[RelatedItem]


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=300)


class Citation(BaseModel):
    id: str
    title: str


class AskResponse(BaseModel):
    answer: str
    citations: list[Citation]


# --- endpoints --------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    return {
        "status": "ok" if INDEX.ready else "degraded",
        "embed_model": EMBED_MODEL,
        "answer_model": ANSWER_MODEL,
        "nodes": len(INDEX.nodes),
        "vectors": INDEX.collection.count() if INDEX.collection is not None else 0,
        "gemini_key": bool(os.environ.get("GEMINI_API_KEY")),
        "anthropic_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "error": INDEX.error,
    }


@app.post("/search", response_model=SearchResponse)
def search(req: SearchRequest) -> SearchResponse:
    require_index()
    hits = INDEX.query(embed_query(req.query), SEARCH_TOP_K)
    return SearchResponse(
        query=req.query,
        results=[SearchHit(**{k: h[k] for k in ("id", "title", "type", "score")}) for h in hits],
    )


@app.get("/related/{item_id}", response_model=RelatedResponse)
def related(item_id: str) -> RelatedResponse:
    require_index()
    if item_id not in INDEX.nodes:
        raise HTTPException(404, f"Unknown item id: {item_id}")
    items = [
        RelatedItem(
            id=rid,
            title=INDEX.nodes[rid]["title"],
            type=INDEX.nodes[rid]["type"],
            summary=INDEX.nodes[rid].get("summary", ""),
        )
        for rid in INDEX.related.get(item_id, [])
        if rid in INDEX.nodes
    ]
    return RelatedResponse(id=item_id, related=items)


ASK_SYSTEM = """You answer questions about the portfolio of Zhengrui (Jerry) Hao, \
a designer-engineer working on HCI, wearables and interactive systems.

Rules:
- Use ONLY the CONTEXT entries provided in the user message. They are the whole
  of your knowledge about Jerry. Never use outside knowledge about him and never
  guess.
- If the context does not contain the answer, say plainly that his portfolio does
  not cover it. Do not speculate about him and do not offer to help with it.
- Decline anything unrelated to Jerry's work in one short sentence.
- Answer in at most 120 words of plain prose. No markdown at all: no headings,
  no bullet lists, no ** bold **.
- Output ONE JSON object and absolutely nothing else — no prose before or after it:
  {"answer": "<your answer>", "cited_ids": ["<id of each context entry you used>"]}
  cited_ids must be a subset of the context ids, and empty when you could not answer."""


def _parse_answer(text: str) -> tuple[str, list[str]]:
    """Extract {answer, cited_ids}; tolerate fences or stray prose around the JSON."""
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    candidates = [cleaned]
    if "{" in cleaned and "}" in cleaned:
        candidates.append(cleaned[cleaned.index("{"): cleaned.rindex("}") + 1])
    for candidate in candidates:
        try:
            obj = json.loads(candidate)
        except Exception:
            continue
        if isinstance(obj, dict) and str(obj.get("answer", "")).strip():
            cited = [str(c) for c in obj.get("cited_ids", []) if isinstance(c, (str, int))]
            return str(obj["answer"]).strip(), cited
    # Model ignored the format: keep its prose, drop anything that looks like the
    # JSON envelope leaking into the user-visible answer.
    fallback = cleaned[: cleaned.index("{")].strip() if "{" in cleaned else cleaned
    return (fallback or cleaned), []


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    require_index()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(503, "ANTHROPIC_API_KEY is not configured")

    hits = INDEX.query(embed_query(req.question), ASK_TOP_K)
    context = "\n\n".join(
        f"<entry id=\"{h['id']}\" title=\"{h['title']}\" type=\"{h['type']}\">\n"
        f"{h['document']}\n</entry>"
        for h in hits
    )

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    try:
        resp = client.messages.create(
            model=ANSWER_MODEL,
            max_tokens=ASK_MAX_TOKENS,
            system=ASK_SYSTEM,
            messages=[
                {"role": "user",
                 "content": f"CONTEXT:\n{context}\n\nQUESTION: {req.question}"},
                # Prefill the opening brace so the reply is JSON from the first token.
                {"role": "assistant", "content": "{"},
            ],
        )
    except Exception as exc:
        raise HTTPException(502, f"Answer model call failed: {exc}") from exc

    raw = "{" + "".join(
        block.text for block in resp.content if getattr(block, "type", "") == "text"
    )
    answer, cited_ids = _parse_answer(raw)

    retrieved = {h["id"]: h["title"] for h in hits}
    citations = [Citation(id=i, title=retrieved[i]) for i in dict.fromkeys(cited_ids)
                 if i in retrieved]
    return AskResponse(answer=answer, citations=citations)
