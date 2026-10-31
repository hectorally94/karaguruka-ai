import hashlib
import hmac
import time

from fastapi import Cookie, HTTPException, Response

from .settings import ADMIN_PASSWORD, AGENT_PASSWORD, SECURE_COOKIES, SESSION_SECRET

COOKIE = "karaguruka_session"
MAX_AGE = 12 * 60 * 60


def _sign(payload: str) -> str:
    return hmac.new(SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()


def role_for_password(password: str) -> str | None:
    if ADMIN_PASSWORD and hmac.compare_digest(password.encode(), ADMIN_PASSWORD.encode()):
        return "admin"
    if AGENT_PASSWORD and hmac.compare_digest(password.encode(), AGENT_PASSWORD.encode()):
        return "agent"
    return None


def set_session(response: Response, role: str) -> None:
    payload = f"{role}.{int(time.time()) + MAX_AGE}"
    response.set_cookie(COOKIE, f"{payload}.{_sign(payload)}", max_age=MAX_AGE, httponly=True, samesite="lax", secure=SECURE_COOKIES, path="/")


def clear_session(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/")


def read_role(karaguruka_session: str | None = Cookie(default=None)) -> str | None:
    if not karaguruka_session or not SESSION_SECRET:
        return None
    parts = karaguruka_session.split(".")
    if len(parts) != 3:
        return None
    role, expires, signature = parts
    if not hmac.compare_digest(signature, _sign(f"{role}.{expires}")) or not expires.isdigit() or int(expires) < time.time():
        return None
    return role if role in ("admin", "agent") else None


def require_admin(karaguruka_session: str | None = Cookie(default=None)) -> str:
    role = read_role(karaguruka_session)
    if not role:
        raise HTTPException(401, "Connexion requise.")
    if role != "admin":
        raise HTTPException(403, "Accès réservé aux administrateurs.")
    return role


def require_staff(karaguruka_session: str | None = Cookie(default=None)) -> str:
    role = read_role(karaguruka_session)
    if not role:
        raise HTTPException(401, "Connexion requise.")
    return role
