from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"


def load_dotenv() -> None:
    if not ENV_PATH.exists():
        return
    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass
class MeliConfig:
    client_id: str
    client_secret: str
    redirect_uri: str

    @property
    def is_complete(self) -> bool:
        return bool(self.client_id and self.client_secret and self.redirect_uri)


def get_meli_config() -> MeliConfig:
    load_dotenv()
    return MeliConfig(
        client_id=os.environ.get("MELI_CLIENT_ID", ""),
        client_secret=os.environ.get("MELI_CLIENT_SECRET", ""),
        redirect_uri=os.environ.get("MELI_REDIRECT_URI", "http://127.0.0.1:8787/auth/meli/callback"),
    )

