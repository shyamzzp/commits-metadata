---
title: Commits Metadata
emoji: 🧬
colorFrom: indigo
colorTo: purple
sdk: gradio
sdk_version: 4.44.0
app_file: app.py
pinned: false
license: mit
---

# 🧬 commits-metadata

Extract structured **feature metadata** from GitHub commits — for a single
commit, an entire repository, or a whole organization — and emit a fixed,
schema-validated JSON document. Runs as a FastAPI service and as a Hugging Face
Space (Gradio UI).

[![CI](https://github.com/shyamzzp/commits-metadata/actions/workflows/ci.yml/badge.svg)](https://github.com/shyamzzp/commits-metadata/actions/workflows/ci.yml)

## What it does

Given a GitHub URL it runs a deterministic pipeline:

```
parse URL → discover commits → fetch → extract diff → classify files →
rule-based metadata (+ optional LLM) → build → JSON-schema validate → store → serve
```

Each commit becomes a [`FeatureMetadata`](app/schema/feature_metadata.schema.json)
record with change type (`feature`/`bugfix`/`refactor`/…), issue references,
breaking-change detection, per-file classification, language detection, diff
stats, and tags.

See [`docs/architecture.md`](docs/architecture.md) for the full Mermaid design
and the component → code map.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# run the API
export GITHUB_TOKEN=ghp_xxx          # optional but recommended (higher rate limit)
uvicorn app.main:app --reload        # http://127.0.0.1:8000/docs

# run the Gradio UI (Hugging Face Space entrypoint)
pip install gradio
python app.py                        # http://127.0.0.1:7860
```

## API

| Method | Path | Description |
|---|---|---|
| `GET`  | `/health` | Liveness probe |
| `POST` | `/process/commit` | Process a single commit URL |
| `POST` | `/process/repo` | Discover + batch-process a repository |
| `POST` | `/process/org` | Process every repo in an org/user |
| `GET`  | `/commits` | Search/browse processed commits |
| `GET`  | `/commits/{owner}/{repo}/{sha}` | Fetch one stored record |
| `GET`  | `/search/features` | **Semantic feature search** — rank stored features by relevance to a query |
| `GET`  | `/search/suggest` | Autocomplete suggestions for the search box |
| `GET`  | `/dashboard` | Aggregate counts by type/repo |
| `GET`  | `/export` | Download bundled JSON |
| `POST` | `/webhook/github` | GitHub push webhook (incremental) |
| `GET`  | `/metrics` | Counters + error count |

Example:

```bash
curl -X POST http://127.0.0.1:8000/process/commit \
  -H 'content-type: application/json' \
  -d '{"commit_url":"https://github.com/octocat/Hello-World/commit/<sha>"}'
```

A ready-made **Postman collection** lives at
[`postman/commits-metadata.postman_collection.json`](postman/commits-metadata.postman_collection.json).

### Semantic feature search

Once commits are processed, query the corpus in natural language:

```bash
curl "http://127.0.0.1:8000/search/features?q=building+pagination&limit=10"
```

returns the most relevant features ranked by score (0..1), e.g. *per-page
limits / offset cursor*, *autocomplete search box*, *action buttons on
paginated rows*. How it works:

1. Every stored `FeatureMetadata` is indexed into a searchable feature document
   (subject + tags + file categories + languages + filenames).
2. The query is tokenized and **expanded via a domain synonym lexicon**
   (`pagination` → page / offset / limit / scroll …) so related features surface
   even without exact word matches.
3. Documents are scored with **BM25**; scores are normalized to `0..1` and
   bucketed into `high` / `medium` / `low` relevance.
4. Pass `ai=true` for **hybrid re-ranking** that blends BM25 with embedding
   cosine similarity. The default embedder is deterministic and key-free; inject
   a real model (`Embedder(embed_fn=...)`) for true semantic matching.

`/search/suggest?prefix=pag` powers the autocomplete dropdown; `limit`/`offset`
on `/search/features` give per-page result paging.

## Configuration

Copy [`.env.example`](.env.example) to `.env`:

| Variable | Purpose |
|---|---|
| `GITHUB_TOKEN` | PAT for higher rate limits / private repos |
| `GITHUB_WEBHOOK_SECRET` | Verify `X-Hub-Signature-256` on webhooks |
| `ENABLE_LLM_ANALYZER` | Turn on the additive LLM summary |
| `GITHUB_API_BASE` | Override for GitHub Enterprise |

## Testing (TDD)

The whole project is built test-first; the suite is fully offline (GitHub calls
are mocked via `httpx.MockTransport`).

```bash
pytest                      # 120+ tests
pytest --cov=app            # coverage report (>90%)
```

## License

MIT
