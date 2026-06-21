"""App Controller / API Layer — FastAPI application wiring every layer together."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request, Response

from app import __version__
from app.automation import webhook
from app.config import Settings, get_settings
from app.discovery.scanner import CommitDiscovery
from app.exporter import export_collection, to_json_bytes
from app.github.client import GitHubClient, GitHubError
from app.github.url_parser import GitHubURLError, RefKind, parse_github_url
from app.models import (
    CommitRequest,
    FeatureMetadata,
    JobResult,
    OrgRequest,
    RepoRequest,
)
from app.observability.telemetry import Telemetry
from app.processing.engine import ProcessingEngine
from app.storage.stores import StorageBundle


class AppState:
    """Process-wide singletons (storage + telemetry survive across requests)."""

    def __init__(self) -> None:
        self.storage = StorageBundle()
        self.telemetry = Telemetry()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.ctx = AppState()
    yield


app = FastAPI(
    title="Commits-Metadata API",
    description="Extract structured feature-metadata from GitHub commits.",
    version=__version__,
    lifespan=lifespan,
)


# --------------------------------------------------------------------------- #
# Dependencies
# --------------------------------------------------------------------------- #
def get_state(request: Request) -> AppState:
    return request.app.state.ctx


def make_client(settings: Settings, state: AppState) -> GitHubClient:
    return GitHubClient(settings, cache=state.storage.cache)


def make_engine(client: GitHubClient, state: AppState, *, enable_llm: bool) -> ProcessingEngine:
    return ProcessingEngine(client, state.storage, state.telemetry, enable_llm=enable_llm)


# --------------------------------------------------------------------------- #
# Health & meta
# --------------------------------------------------------------------------- #
@app.get("/health", tags=["meta"])
async def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/", tags=["meta"])
async def root() -> dict:
    return {
        "name": "commits-metadata",
        "version": __version__,
        "docs": "/docs",
        "endpoints": [
            "/process/commit",
            "/process/repo",
            "/process/org",
            "/commits",
            "/commits/{repo}/{sha}",
            "/dashboard",
            "/export",
            "/webhook/github",
            "/metrics",
        ],
    }


# --------------------------------------------------------------------------- #
# Processing endpoints
# --------------------------------------------------------------------------- #
@app.post("/process/commit", response_model=FeatureMetadata, tags=["processing"])
async def process_commit(
    req: CommitRequest,
    state: AppState = Depends(get_state),
    settings: Settings = Depends(get_settings),
) -> FeatureMetadata:
    try:
        ref = parse_github_url(req.commit_url)
    except GitHubURLError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if ref.kind != RefKind.COMMIT:
        raise HTTPException(status_code=422, detail="URL is not a commit URL")

    client = make_client(settings, state)
    engine = make_engine(client, state, enable_llm=req.config.enable_llm or settings.enable_llm_analyzer)
    try:
        return await engine.process_commit(
            ref.owner, ref.repo, ref.sha, include_patch=req.config.include_diff
        )
    except GitHubError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc))
    finally:
        await client.close()


@app.post("/process/repo", response_model=JobResult, tags=["processing"])
async def process_repo(
    req: RepoRequest,
    state: AppState = Depends(get_state),
    settings: Settings = Depends(get_settings),
) -> JobResult:
    try:
        ref = parse_github_url(req.repo_url)
    except GitHubURLError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if ref.kind not in (RefKind.REPO, RefKind.COMMIT):
        raise HTTPException(status_code=422, detail="URL is not a repository URL")

    client = make_client(settings, state)
    discovery = CommitDiscovery(client)
    engine = make_engine(client, state, enable_llm=req.config.enable_llm or settings.enable_llm_analyzer)
    try:
        discovered = await discovery.discover_repo(
            ref.owner,
            ref.repo,
            branches=req.config.branches,
            max_commits=req.config.max_commits,
            dedupe=req.config.dedupe,
        )
        return await engine.process_batch(
            ref.owner,
            ref.repo,
            discovered.shas,
            include_patch=req.config.include_diff,
            max_retries=req.config.max_retries,
        )
    except GitHubError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc))
    finally:
        await client.close()


@app.post("/process/org", tags=["processing"])
async def process_org(
    req: OrgRequest,
    state: AppState = Depends(get_state),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        ref = parse_github_url(req.org_url)
    except GitHubURLError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    client = make_client(settings, state)
    discovery = CommitDiscovery(client)
    engine = make_engine(client, state, enable_llm=req.config.enable_llm or settings.enable_llm_analyzer)
    results: list[JobResult] = []
    try:
        repos = await discovery.discover_org(ref.owner)
        for full_name in repos:
            owner, repo = full_name.split("/", 1)
            discovered = await discovery.discover_repo(
                owner, repo, max_commits=req.config.max_commits, dedupe=req.config.dedupe
            )
            results.append(
                await engine.process_batch(
                    owner, repo, discovered.shas, include_patch=req.config.include_diff
                )
            )
        return {
            "organization": ref.owner,
            "repositories_processed": len(results),
            "jobs": [r.model_dump() for r in results],
        }
    except GitHubError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc))
    finally:
        await client.close()


# --------------------------------------------------------------------------- #
# Output layer: search / browse / dashboard / export
# --------------------------------------------------------------------------- #
@app.get("/commits", response_model=list[FeatureMetadata], tags=["output"])
async def search_commits(
    repository: str | None = Query(default=None),
    change_type: str | None = Query(default=None),
    text: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    state: AppState = Depends(get_state),
) -> list[FeatureMetadata]:
    return state.storage.metadata.search(
        repository=repository, change_type=change_type, text=text, limit=limit, offset=offset
    )


@app.get("/commits/{owner}/{repo}/{sha}", response_model=FeatureMetadata, tags=["output"])
async def get_commit_metadata(
    owner: str, repo: str, sha: str, state: AppState = Depends(get_state)
) -> FeatureMetadata:
    meta = state.storage.metadata.get(f"{owner}/{repo}", sha)
    if meta is None:
        raise HTTPException(status_code=404, detail="commit not processed")
    return meta


@app.get("/dashboard", tags=["output"])
async def dashboard(state: AppState = Depends(get_state)) -> dict:
    return state.storage.metadata.dashboard()


@app.get("/export", tags=["output"])
async def export_json(
    repository: str | None = Query(default=None),
    state: AppState = Depends(get_state),
) -> Response:
    items = state.storage.metadata.search(repository=repository, limit=10_000)
    payload = export_collection(items)
    filename = f"commits-metadata-{repository.replace('/', '_')}.json" if repository else "commits-metadata.json"
    return Response(
        content=to_json_bytes(payload),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/metrics", tags=["observability"])
async def metrics(state: AppState = Depends(get_state)) -> dict:
    snap = state.telemetry.metrics.snapshot()
    snap["errors"] = len(state.telemetry.errors)
    return snap


# --------------------------------------------------------------------------- #
# Automation: webhook
# --------------------------------------------------------------------------- #
@app.post("/webhook/github", tags=["automation"])
async def github_webhook(
    request: Request,
    state: AppState = Depends(get_state),
    settings: Settings = Depends(get_settings),
) -> dict:
    body = await request.body()
    sig = request.headers.get("X-Hub-Signature-256")
    if not webhook.verify_signature(settings.webhook_secret, body, sig):
        raise HTTPException(status_code=401, detail="invalid signature")

    event = request.headers.get("X-GitHub-Event", "")
    if event != "push":
        return {"status": "ignored", "event": event}

    payload = await request.json()
    refs = webhook.extract_push_commits(payload)
    if not refs:
        return {"status": "no-commits"}

    client = make_client(settings, state)
    engine = make_engine(client, state, enable_llm=settings.enable_llm_analyzer)
    processed = 0
    try:
        for ref in refs:
            try:
                await engine.process_commit(ref.owner, ref.repo, ref.sha)
                processed += 1
            except GitHubError:
                state.telemetry.errors.record(
                    repository=ref.full_name or "", sha=ref.sha or "", error="fetch failed"
                )
    finally:
        await client.close()
    return {"status": "ok", "processed": processed}
