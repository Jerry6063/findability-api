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
