"""Senha da área do treinador.

Com SWIM_ADMIN_PASSWORD definido, toda a API exige login, menos as rotas públicas do cliente
(envio de vídeo e link de entrega) e a saúde do sistema. Sem senha, o app funciona como antes,
para uso só no próprio computador.
"""

from __future__ import annotations

import hashlib
import hmac
import time

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import get_settings

COOKIE = "swim_session"
PUBLIC = ("/api/public/", "/api/auth/", "/api/health")

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _session_value(password: str) -> str:
    return hmac.new(password.encode(), b"fluxi-swim-coach", hashlib.sha256).hexdigest()


def is_logged_in(request: Request) -> bool:
    pw = get_settings().admin_password
    if not pw:
        return True
    got = request.cookies.get(COOKIE, "")
    return hmac.compare_digest(got, _session_value(pw))


async def require_login(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and not path.startswith(PUBLIC) and not is_logged_in(request):
        return JSONResponse({"detail": "faça login"}, status_code=401)
    return await call_next(request)


class Login(BaseModel):
    password: str


@router.get("/me")
def me(request: Request) -> dict:
    return {
        "auth_required": bool(get_settings().admin_password),
        "logged_in": is_logged_in(request),
    }


@router.post("/login")
def login(body: Login, request: Request, response: Response) -> dict:
    pw = get_settings().admin_password
    if not pw:
        return {"logged_in": True}
    if not hmac.compare_digest(body.password, pw):
        time.sleep(0.8)  # tentativas em série ficam lentas
        raise HTTPException(401, "senha incorreta")
    response.set_cookie(
        COOKIE,
        _session_value(pw),
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )
    return {"logged_in": True}


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE)
    return {"logged_in": False}
