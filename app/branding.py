from __future__ import annotations

import os


def app_name() -> str:
    return os.environ.get("APP_NAME", "PrimeLoot").strip() or "PrimeLoot"


def store_brand() -> str:
    return os.environ.get("STORE_BRAND", f"{app_name()} Store").strip() or f"{app_name()} Store"


def app_tagline() -> str:
    return os.environ.get("APP_TAGLINE", "Opportunity Engine").strip() or "Opportunity Engine"
