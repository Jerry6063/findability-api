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
from datetime import datetime, timezone
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

# Global spend brake on /ask. The per-IP limit above shapes bursts; it does not
# bound money. At 10 req/min/IP and ~$0.0066 per answered /ask, one IP can spend
# ~$95/day and ten can spend ~$950/day, which is the whole exposure of putting
# this behind a public portfolio page. /search and /related are not capped: a
# Gemini query embed is ~$0.0000015, four orders of magnitude cheaper, and they
# are what the page actually leans on.
DAILY_ASK_LIMIT = int(os.environ.get("FINDABILITY_DAILY_ASK_LIMIT", "150"))
STATE_DIR = os.environ.get("FINDABILITY_STATE_DIR", os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(STATE_DIR, "ask-usage.json")

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


# --- global daily spend brake on /ask ---------------------------------------

class _DailyBudget:
    """Global, disk-persisted count of answered /ask calls for the current UTC day.

    Persisted, not in-memory, because this runs on Fly with scale-to-zero: the
    process is stopped and woken constantly, so an in-memory counter would reset
    on every wake and the cap would enforce nothing. The file is the source of
    truth on every call — cheap (one small read/write against a call that costs
    ~$0.0066) and correct across restarts.

    Failure policy, deliberately asymmetric:

      * file missing -> treat as 0. This is the normal cold start (fresh machine,
        first deploy). Refusing here would mean the feature never works at all.
      * file present but corrupt/unparseable -> FAIL CLOSED (refuse /ask).
      * increment cannot be written -> FAIL CLOSED (refuse /ask).

    The last two are the defensible half. Writes are atomic (tmp file + fsync +
    os.replace), so a torn write cannot produce corruption; if the file is
    unreadable or the disk is unwritable, something is wrong that we cannot
    reason about, and an unwritable disk specifically means the counter can never
    advance -- i.e. the cap cannot be enforced at all and spend becomes unbounded
    again. Fail-open costs real money with no ceiling; fail-closed costs a
    degraded demo feature on a page that is explicitly built to work without it
    (see module docstring: the site falls back to static graph + keyword search).
    Money is the irreversible side, so it is the side we protect.

    Scope note: the count is per machine filesystem. It is a *global* cap only
    while the app runs a single machine, which is the intended deployment
    (min_machines_running = 0, one machine in ewr). Scaling to N machines would
    give N independent budgets.
    """

    def __init__(self, path: str, limit: int) -> None:
        self.path = path
        self.limit = limit
        self._lock = threading.Lock()
        # Why the last reservation was refused on state grounds, if it was. Sticky
        # on purpose: an unwritable disk is invisible to a read-only health check,
        # so the last write failure is the only evidence /health can show.
        self.last_error: Optional[str] = None

    @staticmethod
    def _today() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _load(self) -> int:
        """Calls already made today. 0 if the file is absent or from an earlier day."""
        try:
            with open(self.path, encoding="utf-8") as fh:
                payload = json.load(fh)
        except FileNotFoundError:
            return 0
        if not isinstance(payload, dict):
            raise ValueError("state file is not a JSON object")
        if payload.get("date") != self._today():
            return 0                     # UTC rollover: yesterday's count is spent history
        count = payload.get("count")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ValueError(f"bad count value: {count!r}")
        return count

    def _store(self, count: int) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"date": self._today(), "count": count}, fh)
            fh.flush()
            os.fsync(fh.fileno())        # survive a machine suspend/stop, not just a clean exit
        os.replace(tmp, self.path)       # atomic: readers never see a half-written file

    def reserve(self) -> tuple[bool, Optional[str]]:
        """Consume one unit of today's budget. Returns (allowed, state_error).

        Reserved BEFORE the model call, never after: a crash or timeout mid-call
        still consumes budget, so a crash loop cannot spend without limit.

        state_error is returned rather than read back off the instance, so a
        concurrent request cannot rewrite it between the refusal and the reply.
        """
        with self._lock:
            try:
                count = self._load()
            except Exception as exc:
                self.last_error = f"unreadable ({exc})"
                return False, self.last_error
            if count >= self.limit:
                self.last_error = None      # a plain cap hit is not a state fault
                return False, None
            try:
                self._store(count + 1)
            except Exception as exc:
                self.last_error = f"unwritable ({exc})"
                return False, self.last_error
            self.last_error = None
            return True, None

    def peek(self) -> tuple[Optional[int], Optional[str]]:
        """Read-only view for /health. Never raises, never consumes budget."""
        with self._lock:
            try:
                return self._load(), None
            except Exception as exc:
                return None, f"unreadable ({exc})"


BUDGET = _DailyBudget(STATE_PATH, DAILY_ASK_LIMIT)

# Body shape for the global cap. `reason` is a contract with the frontend; the
# per-IP 429 above deliberately has no `reason` field so the two are told apart.
DAILY_LIMIT_BODY = {
    "detail": (
        f"The live Q&A has used its daily budget of {DAILY_ASK_LIMIT} answers. "
        "Search and related work are unaffected; Q&A resets at 00:00 UTC."
    ),
    "reason": "daily_limit",
}
DAILY_STATE_BODY = {
    "detail": (
        "The live Q&A is paused: its daily spend guard cannot be read or updated, "
        "so answers are held back until it can."
    ),
    "reason": "daily_limit",
}


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
    # /health is exempt from the per-IP limiter and never touches a paid API, so
    # today's spend can be checked without costing anything. daily_ask_state is
    # read live here; daily_ask_last_error is the last write failure seen by an
    # actual /ask, which a read-only check cannot detect on its own.
    asks_today, budget_error = BUDGET.peek()
    return {
        "status": "ok" if INDEX.ready else "degraded",
        "embed_model": EMBED_MODEL,
        "answer_model": ANSWER_MODEL,
        "nodes": len(INDEX.nodes),
        "vectors": INDEX.collection.count() if INDEX.collection is not None else 0,
        "gemini_key": bool(os.environ.get("GEMINI_API_KEY")),
        "anthropic_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "asks_today": asks_today,
        "daily_ask_limit": DAILY_ASK_LIMIT,
        "daily_ask_state": budget_error or "ok",
        "daily_ask_last_error": BUDGET.last_error,
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
def ask(req: AskRequest) -> AskResponse | JSONResponse:
    require_index()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(503, "ANTHROPIC_API_KEY is not configured")

    # Spend brake, taken before any paid call (embedding included) so nothing
    # downstream — a hang, a 500, a crash loop — can spend outside the budget.
    # Returned as a JSONResponse rather than HTTPException because the body needs
    # the `reason` field the frontend keys on, which HTTPException cannot carry.
    allowed, state_error = BUDGET.reserve()
    if not allowed:
        return JSONResponse(
            status_code=429,
            content=DAILY_STATE_BODY if state_error else DAILY_LIMIT_BODY,
        )

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
