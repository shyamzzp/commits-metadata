"""Gradio UI — thin front-end over the API layer for the Hugging Face Space.

Importing this module does not require gradio; ``build_ui`` imports it lazily so
the API and tests stay dependency-light. Run with ``python -m app.ui``.
"""

from __future__ import annotations

import asyncio

from app.config import Settings, ProcessingConfig
from app.discovery.scanner import CommitDiscovery
from app.github.client import GitHubClient
from app.github.url_parser import RefKind, parse_github_url
from app.processing.engine import ProcessingEngine
from app.storage.stores import StorageBundle


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


async def _process(url: str, max_commits: int, include_diff: bool, enable_llm: bool) -> dict:
    settings = Settings()
    storage = StorageBundle()
    client = GitHubClient(settings, cache=storage.cache)
    engine = ProcessingEngine(client, storage, enable_llm=enable_llm)
    discovery = CommitDiscovery(client)
    try:
        ref = parse_github_url(url)
        if ref.kind == RefKind.COMMIT:
            meta = await engine.process_commit(ref.owner, ref.repo, ref.sha, include_patch=include_diff)
            return meta.model_dump()
        if ref.kind == RefKind.REPO:
            discovered = await discovery.discover_repo(ref.owner, ref.repo, max_commits=max_commits)
            result = await engine.process_batch(ref.owner, ref.repo, discovered.shas, include_patch=include_diff)
            return result.model_dump()
        repos = await discovery.discover_org(ref.owner)
        return {"organization": ref.owner, "repositories": repos}
    finally:
        await client.close()


def build_ui():  # pragma: no cover - requires gradio at runtime
    import gradio as gr

    def handler(url, max_commits, include_diff, enable_llm):
        return _run(_process(url, int(max_commits), include_diff, enable_llm))

    with gr.Blocks(title="Commits-Metadata") as demo:
        gr.Markdown("# 🧬 Commits-Metadata\nExtract structured feature-metadata from GitHub commits.")
        url = gr.Textbox(label="Commit / Repository / Organization URL")
        with gr.Row():
            max_commits = gr.Slider(1, 500, value=50, step=1, label="Max commits")
            include_diff = gr.Checkbox(value=True, label="Include diff/patch")
            enable_llm = gr.Checkbox(value=False, label="Enable LLM analyzer")
        out = gr.JSON(label="Feature Metadata (fixed JSON)")
        gr.Button("Process", variant="primary").click(
            handler, [url, max_commits, include_diff, enable_llm], out
        )
    return demo


if __name__ == "__main__":  # pragma: no cover
    build_ui().launch(server_name="0.0.0.0", server_port=7860)
