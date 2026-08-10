# findability-api

Semantic layer behind **haozhengrui.work/#findability** — the 2024 *AI-Enabled
Findability* research rebuilt as a live feature over the portfolio itself.

`ingest.py` reads the content arrays out of the site's `main.js`
([Jerry6063/personal-web](https://github.com/Jerry6063/personal-web) — vanilla JS,
no build step, no JSON export), turns every project / role / lab entry into one
chunk, embeds them with Gemini, and emits two layers:

| layer | artifact | used for |
| --- | --- | --- |
| online | Chroma collection in `chroma/` | true semantic `/search` and grounded `/ask` |
| static | `findability-data.json` | graph nodes + edges + related table the site ships and renders with the API switched off |

The site never depends on this service: with `FINDABILITY_API` empty (or the
service down) it falls back to the static graph and substring search.

## Endpoints

| method | path | body / params | returns |
| --- | --- | --- | --- |
| GET | `/health` | — | index status, model ids, whether keys are present |
| POST | `/search` | `{"query": "…"}` (≤200 chars) | top-5 `[{id,title,type,score}]` |
| GET | `/related/{id}` | — | precomputed top-3 related entries (no API call, no key) |
| POST | `/ask` | `{"question": "…"}` (≤300 chars) | `{answer, citations:[{id,title}]}` |

`/ask` retrieves the top-4 chunks and hands them to Claude with a system prompt
that allows **only** the supplied context; out-of-corpus questions get an explicit
"not covered in his portfolio" instead of a guess. Citations are the context
entries the model reports using, intersected with what was actually retrieved.

Rate limit: 10 requests/minute/IP (in-memory), `429` + `Retry-After` past that;
`/health` is exempt. CORS: `haozhengrui.work`, `www.haozhengrui.work`, and any
`localhost` / `127.0.0.1` port.

## Evaluation

`evals/` holds the measurement layer — a 30-entry golden set and the scripts that
score retrieval and `/ask` against it. Full numbers and methodology in `PROGRESS.md`
(Stage E); the short version:

| what | number |
| --- | --- |
| retrieval hit-rate@3 / @5 | 0.9167 / 1.0000 |
| retrieval MRR | 0.8958 |
| cross-lingual (Chinese questions, English corpus) hit@3 | 1.0000 |
| refusal accuracy (out-of-corpus correctly declined) | 6/6 |
| false-refusal rate (answerable wrongly declined) | 1/24 |

```
python evals/run_retrieval.py     # metrics + regenerate the CI vector cache
python evals/run_ragas.py         # Ragas over the real /ask pipeline (needs both keys)
python evals/ci_retrieval.py      # what CI runs: stdlib only, no key, no network
python evals/trace_ask.py         # send traced calls to a local Phoenix
```

`ci_retrieval.py` recomputes the retrieval metrics from vectors committed in
`evals/golden-embeddings.json`, so the GitHub Actions job needs no API key and
costs nothing. It also fails when the golden set and its cached embeddings drift
apart.

One finding worth flagging before you trust the Ragas numbers: **faithfulness is
not a valid gate on this corpus.** A three-perspective manual audit put the true
figure at 0.968 where the judge reported 0.52 — the metric penalises natural-language
restatements of terse `Credits — …` metadata lines. A stronger judge made it *worse*,
not better. See PROGRESS.md Stage E.

## Configuration

Secrets come from the environment only — never from a file in this repo.

| var | default | note |
| --- | --- | --- |
| `GEMINI_API_KEY` | — | required for `/search`, `/ask` and ingestion |
| `ANTHROPIC_API_KEY` | — | required for `/ask` |
| `FINDABILITY_EMBED_MODEL` | `gemini-embedding-2` | must match the model used at ingest time |
| `FINDABILITY_ANSWER_MODEL` | `claude-sonnet-4-5` | |
| `FINDABILITY_CHROMA_DIR` | `./chroma` | |
| `FINDABILITY_DATA` | `./findability-data.json` | |
| `FINDABILITY_RATE_LIMIT` | `10` | requests per minute per IP |
| `FINDABILITY_MAX_TOKENS` | `600` | `/ask` answer cap |
| `FINDABILITY_EDGE_THRESHOLD` | `0.70` | minimum cosine similarity for a graph edge |
| `FINDABILITY_CORS` | — | extra allowed origins, comma separated |
| `FINDABILITY_DAILY_ASK_LIMIT` | `150` | global `/ask` answers per UTC day, all callers combined |
| `FINDABILITY_STATE_DIR` | app directory | where `ask-usage.json` (the daily counter) is kept |

`FINDABILITY_RATE_LIMIT` shapes bursts but does not bound money: at 10/min/IP and
~$0.0066 per answered `/ask`, one IP could spend ~$95/day. `FINDABILITY_DAILY_ASK_LIMIT`
is the actual brake — global, not per IP, counted per UTC day, and persisted to
`ask-usage.json` so Fly's scale-to-zero restarts cannot reset it. Over the cap,
`/ask` returns `429 {"detail": "...", "reason": "daily_limit"}`; the per-IP 429 has
no `reason` field, which is how the frontend tells them apart. `/search` and
`/related` are never capped. `/health` reports `asks_today` / `daily_ask_limit`.

## Re-running ingestion

Whenever `personal-web/main.js` gains or edits an entry:

```bash
docker build -t findability-api .
docker run --rm --env-file .env \
  -v "$PWD":/work \
  -v /path/to/personal-web/main.js:/site/main.js:ro \
  -w /work findability-api \
  python ingest.py --main-js /site/main.js --out-dir /work
docker build -t findability-api .        # bake the refreshed index into the image
```

`--dry-run` parses and prints the chunks without calling any API — use it to check
a `main.js` change before spending embeddings.

## Run

```bash
docker run --env-file .env -p 8200:8200 findability-api
curl 127.0.0.1:8200/health
curl -X POST 127.0.0.1:8200/search -H 'Content-Type: application/json' \
  -d '{"query":"haptic navigation for blind users"}'
curl -X POST 127.0.0.1:8200/ask -H 'Content-Type: application/json' \
  -d '{"question":"What has Jerry built for blind navigation?"}'
```

Interactive docs: `http://127.0.0.1:8200/docs`. On Railway the container honours
`$PORT`; set `GEMINI_API_KEY` and `ANTHROPIC_API_KEY` as service variables.

## Corpus

13 entries: 6 projects, 4 roles, 3 lab pieces. The five content-free lab
placeholders in `main.js` (`d3-chart`, `map-widget`, `shader-gradient`,
`ui-playground`, `timing-test`) are excluded by id in `ingest.py`.
