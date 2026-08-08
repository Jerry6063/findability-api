"""ingest.py — build the Findability corpus, vector store and static graph.

Pipeline:

    personal-web/main.js
        -> jsdata.load_site_data()        (JS object-literal parse, no build step)
        -> one chunk per entry            (every human-readable field, concatenated)
        -> Gemini embeddings              (task_type RETRIEVAL_DOCUMENT)
        -> a) Chroma collection persisted to ./chroma/     (online semantic layer)
           b) findability-data.json                        (static fallback layer)

`findability-data.json` is what the site ships: nodes + similarity edges +
a precomputed related-items table, so the graph, the related rail and keyword
search keep working with the API switched off entirely.

Usage:
    python ingest.py [--main-js PATH] [--out-dir PATH] [--edge-threshold F]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
import time
from typing import Any, Iterable

from jsdata import load_site_data

# Lab entries that are titles with no work behind them — placeholders left in
# main.js as layout filler. They would pollute the corpus (and the graph), so
# they are excluded by id, not by heuristic.
PLACEHOLDER_LAB_IDS = {
    "d3-chart",
    "map-widget",
    "shader-gradient",
    "ui-playground",
    "timing-test",
}

# Keys that hold asset paths / URLs / flags rather than prose.
SKIP_KEYS = {
    "id", "cover", "hero", "heroPoster", "preview", "media", "mediaType",
    "poster", "link", "url", "repo", "theme", "embedLive", "projectId", "src",
}

# Field label prettification for the chunk text handed to the embedder / LLM.
LABELS = {
    "subtitle": "Summary",
    "org": "Organization",
    "dates": "Dates",
    "bullets": "Highlights",
    "type": "Category",
    "next": "Next steps",
    "credits": "Credits",
    "chapters": "Walkthrough",
    "links": "Links",
}

EMBED_MODEL = os.environ.get("FINDABILITY_EMBED_MODEL", "gemini-embedding-2")
COLLECTION = "findability"
SUMMARY_MAX = 140
TOP_K_EDGES = 3
# Every chunk is one person's design work, so cosine similarity has a high floor
# (observed pair range 0.62–0.89, median 0.70). Measured sweep over the real
# corpus — edges / components / isolated nodes:
#   0.68 -> 28 / 1 / 0    0.70 -> 26 / 1 / 0    0.72 -> 21 / 2 / 1    0.76 -> 17 / 4 / 2
# 0.70 is the highest cut that still leaves the graph in a single component with
# no isolated node, at 33% of the max possible edges (not a hairball).
DEFAULT_EDGE_THRESHOLD = 0.70


# --------------------------------------------------------------------------
# chunk building
# --------------------------------------------------------------------------

def _label(key: str) -> str:
    return LABELS.get(key, key[:1].upper() + key[1:])


def _flatten(value: Any, prefix: str, out: list[str]) -> None:
    """Append `Label: text` lines for every human-readable string in `value`."""
    if isinstance(value, str):
        text = value.strip()
        if text:
            out.append(f"{prefix}: {text}" if prefix else text)
    elif isinstance(value, (int, float, bool)):
        return
    elif isinstance(value, list):
        strings = [v for v in value if isinstance(v, str)]
        if strings and len(strings) == len(value):
            out.append(f"{prefix}: {', '.join(strings)}")
        else:
            for item in value:
                _flatten(item, prefix, out)
    elif isinstance(value, dict):
        for k, v in value.items():
            if k in SKIP_KEYS:
                continue
            child = f"{prefix} — {_label(k)}" if prefix else _label(k)
            _flatten(v, child, out)


def build_chunk_text(entry: dict, kind: str) -> str:
    lines: list[str] = []
    for key, value in entry.items():
        if key in SKIP_KEYS:
            continue
        _flatten(value, _label(key), lines)
    header = {"project": "Project", "work": "Experience", "lab": "Lab experiment"}[kind]
    return f"{header}\n" + "\n".join(lines)


def _clip(text: str, limit: int = SUMMARY_MAX) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    if " " in cut:
        cut = cut[: cut.rindex(" ")]
    return cut.rstrip(",;:—-") + "…"


def _work_title(entry: dict) -> str:
    """`org` reads 'Lab, School · City, ST' — keep the institution, drop place."""
    parts = [p.strip() for p in entry.get("org", "").split("·") if p.strip()]
    return parts[0] if parts else entry.get("role", entry["id"])


def build_nodes(data: dict[str, list]) -> list[dict]:
    nodes: list[dict] = []

    for entry in data["projects"]:
        summary = entry.get("subtitle") or entry.get("overview") or entry.get("problem", "")
        nodes.append({
            "id": entry["id"],
            "title": entry["title"],
            "type": "project",
            "tags": list(entry.get("tags", [])),
            "summary": _clip(summary),
            "subtitle": entry.get("role", ""),
            "year": entry.get("year", ""),
            "url": entry.get("link", ""),
            "_chunk": build_chunk_text(entry, "project"),
        })

    for entry in data["work"]:
        bullets = entry.get("bullets", [])
        nodes.append({
            "id": entry["id"],
            "title": _work_title(entry),
            "type": "work",
            "tags": [],
            "summary": _clip(bullets[0] if bullets else entry.get("role", "")),
            "subtitle": entry.get("role", ""),
            "year": entry.get("dates", ""),
            "url": "",
            "_chunk": build_chunk_text(entry, "work"),
        })

    for entry in data["lab"]:
        if entry["id"] in PLACEHOLDER_LAB_IDS:
            continue
        # lab `type` is e.g. 'Generative · 2026' — category plus year.
        bits = [p.strip() for p in entry.get("type", "").split("·") if p.strip()]
        category = bits[0] if bits else ""
        year = bits[1] if len(bits) > 1 else ""
        nodes.append({
            "id": entry["id"],
            "title": entry["title"],
            "type": "lab",
            "tags": [category] if category else [],
            "summary": _clip(entry.get("description", "")),
            "subtitle": category,
            "year": year,
            "url": entry.get("url", ""),
            "_chunk": build_chunk_text(entry, "lab"),
        })

    return nodes


# --------------------------------------------------------------------------
# embeddings
# --------------------------------------------------------------------------

def embed_texts(texts: Iterable[str], task_type: str) -> list[list[float]]:
    """Embed one text at a time (corpus is tiny; avoids batch-size limits)."""
    from google import genai
    from google.genai import types as genai_types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("GEMINI_API_KEY is not set (use --env-file / source, never inline)")
    client = genai.Client(api_key=api_key)

    vectors: list[list[float]] = []
    for n, text in enumerate(texts, 1):
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                resp = client.models.embed_content(
                    model=EMBED_MODEL,
                    contents=text,
                    config=genai_types.EmbedContentConfig(task_type=task_type),
                )
                vectors.append(list(resp.embeddings[0].values))
                break
            except Exception as exc:  # transient 429/5xx
                last_err = exc
                time.sleep(2 * (attempt + 1))
        else:
            raise RuntimeError(f"embedding failed for chunk #{n}: {last_err}")
        print(f"  embedded {n} ({len(vectors[-1])} dims)", flush=True)
    return vectors


def normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


# --------------------------------------------------------------------------
# graph
# --------------------------------------------------------------------------

def build_graph(nodes: list[dict], vectors: list[list[float]], threshold: float):
    ids = [n["id"] for n in nodes]
    sims = {
        ids[i]: sorted(
            ((ids[j], cosine(vectors[i], vectors[j])) for j in range(len(ids)) if j != i),
            key=lambda p: p[1],
            reverse=True,
        )
        for i in range(len(ids))
    }

    related = {i: [t for t, _ in sims[i][:TOP_K_EDGES]] for i in ids}

    edges: dict[tuple[str, str], float] = {}
    for src, ranked in sims.items():
        for dst, weight in ranked[:TOP_K_EDGES]:
            if weight < threshold:
                continue
            key = (src, dst) if src < dst else (dst, src)
            edges[key] = max(edges.get(key, 0.0), weight)

    edge_list = [
        {"s": s, "t": t, "w": round(w, 4)}
        for (s, t), w in sorted(edges.items(), key=lambda kv: -kv[1])
    ]
    return edge_list, related, sims


def graph_report(nodes: list[dict], edges: list[dict], sims: dict) -> dict:
    """Connectivity stats — used to justify the similarity threshold."""
    adj: dict[str, set] = {n["id"]: set() for n in nodes}
    for e in edges:
        adj[e["s"]].add(e["t"])
        adj[e["t"]].add(e["s"])

    seen: set[str] = set()
    components = []
    for start in adj:
        if start in seen:
            continue
        stack, comp = [start], []
        seen.add(start)
        while stack:
            cur = stack.pop()
            comp.append(cur)
            for nxt in adj[cur] - seen:
                seen.add(nxt)
                stack.append(nxt)
        components.append(sorted(comp))

    all_w = sorted((w for ranked in sims.values() for _, w in ranked), reverse=True)
    n = len(nodes)
    return {
        "nodes": n,
        "edges": len(edges),
        "max_possible_edges": n * (n - 1) // 2,
        "isolated": sorted(i for i, nb in adj.items() if not nb),
        "components": components,
        "degree": {i: len(nb) for i, nb in sorted(adj.items())},
        "similarity_percentiles": {
            "max": round(all_w[0], 4),
            "p75": round(all_w[len(all_w) // 4], 4),
            "median": round(all_w[len(all_w) // 2], 4),
            "min": round(all_w[-1], 4),
        },
    }


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Build the Findability corpus + index")
    ap.add_argument("--main-js", default=os.environ.get("PERSONAL_WEB_MAIN_JS", "./main.js"))
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--edge-threshold", type=float,
                    default=float(os.environ.get("FINDABILITY_EDGE_THRESHOLD",
                                                 DEFAULT_EDGE_THRESHOLD)))
    ap.add_argument("--dry-run", action="store_true",
                    help="parse + build chunks only, no API calls, no writes")
    args = ap.parse_args()

    print(f"reading {args.main_js}")
    data = load_site_data(args.main_js)
    print(f"  projectsData={len(data['projects'])} workData={len(data['work'])} "
          f"labData={len(data['lab'])}")

    nodes = build_nodes(data)
    dropped = sorted(PLACEHOLDER_LAB_IDS & {e["id"] for e in data["lab"]})
    print(f"  corpus entries: {len(nodes)} (dropped placeholders: {', '.join(dropped)})")
    for node in nodes:
        print(f"    {node['type']:8} {node['id']:28} {len(node['_chunk']):5} chars")

    if args.dry_run:
        print(json.dumps({"chunks": {n["id"]: n["_chunk"] for n in nodes}}, indent=2,
                         ensure_ascii=False))
        return

    print(f"embedding {len(nodes)} chunks with {EMBED_MODEL}")
    vectors = [normalize(v) for v in embed_texts((n["_chunk"] for n in nodes),
                                                 "RETRIEVAL_DOCUMENT")]

    edges, related, sims = build_graph(nodes, vectors, args.edge_threshold)
    report = graph_report(nodes, edges, sims)
    print("graph report:", json.dumps(report, indent=2))

    out_dir = args.out_dir
    os.makedirs(out_dir, exist_ok=True)

    # ---- a) Chroma ----
    import chromadb

    chroma_dir = os.path.join(out_dir, "chroma")
    if os.path.isdir(chroma_dir):
        shutil.rmtree(chroma_dir)
    client = chromadb.PersistentClient(path=chroma_dir)
    collection = client.create_collection(
        name=COLLECTION,
        embedding_function=None,  # vectors are supplied, never computed by Chroma
        configuration={"hnsw": {"space": "cosine"}},
    )
    collection.add(
        ids=[n["id"] for n in nodes],
        embeddings=vectors,
        documents=[n["_chunk"] for n in nodes],
        metadatas=[{"title": n["title"], "type": n["type"],
                    "tags": ", ".join(n["tags"]), "summary": n["summary"]} for n in nodes],
    )
    print(f"chroma: collection '{COLLECTION}' persisted to {chroma_dir} "
          f"({collection.count()} docs, {len(vectors[0])} dims)")

    # ---- b) static JSON ----
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "embed_model": EMBED_MODEL,
        "edge_threshold": args.edge_threshold,
        "nodes": [{k: v for k, v in n.items() if not k.startswith("_")} for n in nodes],
        "edges": edges,
        "related": related,
        "report": report,
    }
    data_path = os.path.join(out_dir, "findability-data.json")
    with open(data_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    print(f"wrote {data_path} ({len(nodes)} nodes, {len(edges)} edges)")

    # corpus text is kept alongside so /ask can build context without Chroma
    corpus_path = os.path.join(out_dir, "corpus.json")
    with open(corpus_path, "w", encoding="utf-8") as fh:
        json.dump({n["id"]: n["_chunk"] for n in nodes}, fh, indent=2, ensure_ascii=False)
    print(f"wrote {corpus_path}")


if __name__ == "__main__":
    main()
