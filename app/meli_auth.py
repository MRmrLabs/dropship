from __future__ import annotations

import json
import secrets
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.config import get_meli_config
from app.storage import DATA_DIR


AUTH_BASE_URL = "https://auth.mercadolibre.com.mx/authorization"
TOKEN_URL = "https://api.mercadolibre.com/oauth/token"
ME_URL = "https://api.mercadolibre.com/users/me"
TOKEN_PATH = DATA_DIR / "meli_tokens.json"
STATE_PATH = DATA_DIR / "meli_oauth_state.json"


def integration_status() -> dict[str, Any]:
    config = get_meli_config()
    token = read_tokens()
    return {
        "configured": config.is_complete,
        "client_id_present": bool(config.client_id),
        "client_secret_present": bool(config.client_secret),
        "redirect_uri": config.redirect_uri,
        "connected": bool(token.get("access_token")),
        "user_id": token.get("user_id"),
        "expires_at": token.get("expires_at"),
    }


def build_authorization_url() -> str:
    config = get_meli_config()
    if not config.is_complete:
        raise ValueError("Falta configurar MELI_CLIENT_ID, MELI_CLIENT_SECRET y MELI_REDIRECT_URI en .env")
    DATA_DIR.mkdir(exist_ok=True)
    state = secrets.token_urlsafe(24)
    STATE_PATH.write_text(json.dumps({"state": state, "created_at": int(time.time())}), encoding="utf-8")
    params = {
        "response_type": "code",
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri,
        "state": state,
    }
    return f"{AUTH_BASE_URL}?{urlencode(params)}"


def exchange_code(code: str, state: str) -> dict[str, Any]:
    validate_state(state)
    config = get_meli_config()
    payload = urlencode(
        {
            "grant_type": "authorization_code",
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "code": code,
            "redirect_uri": config.redirect_uri,
        }
    ).encode("utf-8")
    token = normalize_token(post_form(TOKEN_URL, payload))
    write_tokens(token)
    return token


def refresh_access_token() -> dict[str, Any]:
    config = get_meli_config()
    current = read_tokens()
    refresh_token = current.get("refresh_token")
    if not refresh_token:
        raise ValueError("No hay refresh_token guardado; vuelve a conectar Mercado Libre")
    payload = urlencode(
        {
            "grant_type": "refresh_token",
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "refresh_token": refresh_token,
        }
    ).encode("utf-8")
    token = normalize_token(post_form(TOKEN_URL, payload))
    write_tokens(token)
    return token


def get_access_token() -> str:
    token = read_tokens()
    if not token.get("access_token"):
        raise ValueError("Mercado Libre no esta conectado")
    if int(token.get("expires_at", 0)) <= int(time.time()) + 120:
        token = refresh_access_token()
    return str(token["access_token"])


def fetch_me() -> dict[str, Any]:
    request = Request(
        ME_URL,
        headers={"Authorization": f"Bearer {get_access_token()}", "Accept": "application/json"},
    )
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def post_form(url: str, payload: bytes) -> dict[str, Any]:
    request = Request(
        url,
        data=payload,
        headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def normalize_token(data: dict[str, Any]) -> dict[str, Any]:
    data["expires_at"] = int(time.time()) + int(data.get("expires_in", 0))
    return data


def read_tokens() -> dict[str, Any]:
    if not TOKEN_PATH.exists():
        return {}
    return json.loads(TOKEN_PATH.read_text(encoding="utf-8"))


def write_tokens(token: dict[str, Any]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    TOKEN_PATH.write_text(json.dumps(token, indent=2, ensure_ascii=True), encoding="utf-8")


def validate_state(state: str) -> None:
    if not STATE_PATH.exists():
        raise ValueError("No hay state OAuth pendiente")
    payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    if not secrets.compare_digest(str(payload.get("state", "")), state):
        raise ValueError("State OAuth invalido")
    if int(payload.get("created_at", 0)) < int(time.time()) - 900:
        raise ValueError("State OAuth expirado; inicia conexion otra vez")

