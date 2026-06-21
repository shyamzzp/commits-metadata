"""Hugging Face Space entrypoint.

HF Spaces look for ``app.py`` at the repo root. This launches the Gradio UI.
For the pure HTTP API, run ``uvicorn app.main:app`` instead.
"""

from app.ui import build_ui

if __name__ == "__main__":
    build_ui().launch(server_name="0.0.0.0", server_port=7860)
