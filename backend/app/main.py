from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import auth, public, review, system, technique, videos
from app.config import get_settings


def create_app() -> FastAPI:
    app = FastAPI(title="Swim Analysis", version="0.1.0")
    app.middleware("http")(auth.require_login)
    app.include_router(auth.router)
    app.include_router(public.router)
    app.include_router(system.router)
    app.include_router(videos.router)
    app.include_router(review.router)
    app.include_router(technique.router)

    static: Path = get_settings().static_dir
    if (static / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            if path.startswith("api/"):
                raise HTTPException(404)
            f = static / path
            if path and f.is_file() and static in f.resolve().parents:
                return FileResponse(f)
            return FileResponse(static / "index.html")

    return app


app = create_app()
