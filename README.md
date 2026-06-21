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
