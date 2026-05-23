from __future__ import annotations

import hmac
import os
from http.cookies import SimpleCookie


COOKIE_NAME = "primeloot_admin"


def auth_status() -> dict[str, object]:
    return {
        "enabled": bool(admin_password()),
        "configured": bool(admin_password()),
    }


def admin_password() -> str:
    return os.environ.get("ADMIN_PASSWORD", "").strip()


def auth_secret() -> str:
    return os.environ.get("ADMIN_SESSION_SECRET", admin_password() or "primeloot-dev-session")


def is_auth_enabled() -> bool:
    return bool(admin_password())


def signed_session_value() -> str:
    digest = hmac.new(auth_secret().encode("utf-8"), b"admin", "sha256").hexdigest()
    return f"admin.{digest}"


def verify_password(password: str) -> bool:
    configured = admin_password()
    return bool(configured) and hmac.compare_digest(password, configured)


def is_authenticated(cookie_header: str | None) -> bool:
    if not is_auth_enabled():
        return True
    if not cookie_header:
        return False
    cookie = SimpleCookie()
    cookie.load(cookie_header)
    morsel = cookie.get(COOKIE_NAME)
    if not morsel:
        return False
    return hmac.compare_digest(morsel.value, signed_session_value())


def login_cookie() -> str:
    value = signed_session_value()
    secure = "; Secure" if os.environ.get("RENDER") == "true" else ""
    return f"{COOKIE_NAME}={value}; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800{secure}"


def logout_cookie() -> str:
    return f"{COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
