from __future__ import annotations

import json
import os
from dataclasses import dataclass
from statistics import median
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.domain import SupplierProduct
from app.meli_auth import get_access_token


API_BASE = "https://api.mercadolibre.com"
SITE_ID = "MLM"


@dataclass
class MarketplaceListing:
    item_id: str
    permalink: str
    status: str
    raw: dict[str, Any]


def compare_market(product: SupplierProduct) -> dict[str, Any]:
    query = " ".join(part for part in (product.brand, product.title) if part).strip()
    payload = api_get(
        f"/sites/{SITE_ID}/search",
        {"q": query, "limit": 12, "condition": "new"},
        auth=False,
    )
    results = payload.get("results", [])
    parsed = []
    for item in results:
        price = safe_float(item.get("price"))
        title = str(item.get("title") or "")
        if price <= 0 or not title:
            continue
        if product.brand and product.brand.lower() not in {"generico", "genérico"}:
            if product.brand.lower() not in title.lower():
                continue
        parsed.append(
            {
                "id": item.get("id"),
                "title": title,
                "price": price,
                "permalink": item.get("permalink"),
            }
        )
    clean = remove_price_outliers(parsed)
    prices = [item["price"] for item in clean]
    if not prices:
        return {
            "query": query,
            "count": 0,
            "reference_price": product.market_competition_price,
            "median_price": product.market_competition_price,
            "min_price": product.market_competition_price,
            "competition_level": product.competition_level,
            "items": [],
        }
    min_price = min(prices)
    median_price = float(median(prices))
    competition_level = "high" if min_price < product.market_competition_price * 0.9 else "medium"
    return {
        "query": query,
        "count": len(clean),
        "reference_price": round(median_price, 2),
        "median_price": round(median_price, 2),
        "min_price": round(min_price, 2),
        "competition_level": competition_level,
        "items": clean[:5],
    }


def publish_listing(draft: dict[str, Any], product: SupplierProduct) -> MarketplaceListing:
    access_token = get_access_token()
    category_id = predict_category(str(draft["title"]), access_token)
    payload: dict[str, Any] = {
        "site_id": SITE_ID,
        "title": str(draft["title"])[:60],
        "category_id": category_id,
        "price": float(draft["price"]),
        "currency_id": "MXN",
        "available_quantity": max(1, min(int(draft["stock"]), 10)),
        "buying_mode": "buy_it_now",
        "listing_type_id": os.environ.get("MELI_LISTING_TYPE_ID", "gold_special"),
        "condition": "new",
        "channels": ["marketplace"],
        "attributes": build_attributes(draft, product),
    }
    pictures = build_pictures(str(draft.get("image_url") or product.image_url or ""))
    if pictures:
        payload["pictures"] = pictures
    item = api_post("/items", payload, access_token)
    item_id = str(item.get("id") or "")
    if not item_id:
        raise ValueError("Mercado Libre no devolvio item_id")
    description = str(draft.get("description") or "").strip()
    if description:
        api_post(f"/items/{item_id}/description", {"plain_text": description[:50000]}, access_token)
    return MarketplaceListing(
        item_id=item_id,
        permalink=str(item.get("permalink") or f"https://articulo.mercadolibre.com.mx/{item_id}"),
        status=str(item.get("status") or "published"),
        raw=item,
    )


def predict_category(title: str, access_token: str) -> str:
    payload = api_get(
        f"/sites/{SITE_ID}/domain_discovery/search",
        {"q": title, "limit": 1},
        access_token,
        auth=True,
    )
    if not payload:
        raise ValueError("Mercado Libre no pudo predecir categoria para este titulo")
    category_id = payload[0].get("category_id")
    if not category_id:
        raise ValueError("La categoria predicha por Mercado Libre no trae category_id")
    return str(category_id)


def build_attributes(draft: dict[str, Any], product: SupplierProduct) -> list[dict[str, str]]:
    attrs = draft.get("attributes") if isinstance(draft.get("attributes"), dict) else {}
    brand = str(attrs.get("brand") or product.brand or "Generico").strip()
    model = str(attrs.get("model") or product.sku or product.title[:40]).strip()
    return [
        {"id": "ITEM_CONDITION", "value_id": "2230284"},
        {"id": "BRAND", "value_name": brand[:60]},
        {"id": "MODEL", "value_name": model[:60]},
        {"id": "SELLER_SKU", "value_name": str(product.sku)[:60]},
    ]


def build_pictures(image_url: str) -> list[dict[str, str]]:
    if image_url.startswith(("http://", "https://")):
        return [{"source": image_url}]
    return []


def api_get(path: str, params: dict[str, Any] | None = None, token: str | None = None, auth: bool = True) -> Any:
    query = f"?{urlencode(params)}" if params else ""
    headers = {"Accept": "application/json"}
    if auth and token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(f"{API_BASE}{path}{query}", headers=headers)
    with urlopen(request, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


def api_post(path: str, payload: dict[str, Any], token: str) -> dict[str, Any]:
    request = Request(
        f"{API_BASE}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ValueError(f"Mercado Libre rechazo la publicacion: {body}") from exc


def remove_price_outliers(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prices = sorted(item["price"] for item in items if item["price"] > 0)
    if not prices:
        return []
    mid = float(median(prices))
    return [item for item in items if mid * 0.35 <= item["price"] <= mid * 2.5]


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
