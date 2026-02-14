from __future__ import annotations

from zenclaude.web.app import create_app


def run_dashboard(host: str = "127.0.0.1", port: int = 7777) -> None:
    import uvicorn

    app = create_app()
    uvicorn.run(app, host=host, port=port)
