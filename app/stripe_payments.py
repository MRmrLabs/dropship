from __future__ import annotations

import hmac
import json
import os
import time
from hashlib import sha256
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


STRIPE_API = "https://api.stripe.com/v1"


def stripe_status() -> dict[str, Any]:
    return {
        "configured": bool(os.environ.get("STRIPE_SECRET_KEY")),
        "connect_base": True,
        "connected_account": bool(os.environ.get("STRIPE_CONNECTED_ACCOUNT_ID")),
        "commission_rate": commission_rate(),
        "mode": "connect" if os.environ.get("STRIPE_CONNECTED_ACCOUNT_ID") else "platform_checkout",
    }


def commission_rate() -> float:
    return max(0.0, min(0.50, float(os.environ.get("STRIPE_PLATFORM_COMMISSION_RATE", "0.10"))))


def create_checkout_session(order_id: int, items: list[dict[str, Any]], subtotal: float) -> dict[str, Any]:
    api_key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if not api_key:
        raise ValueError("Falta STRIPE_SECRET_KEY para cobrar con Stripe")
    base_url = os.environ.get("PUBLIC_BASE_URL", "http://127.0.0.1:8787").rstrip("/")
    success_url = os.environ.get("STRIPE_SUCCESS_URL", f"{base_url}/tienda?payment=success&order_id={order_id}")
    cancel_url = os.environ.get("STRIPE_CANCEL_URL", f"{base_url}/tienda?payment=cancel&order_id={order_id}")
    data: dict[str, Any] = {
        "mode": "payment",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": str(order_id),
        "metadata[storefront_order_id]": str(order_id),
        "metadata[source]": "neobot_storefront",
    }
    for index, item in enumerate(items):
        title = str(item.get("title") or "Producto NEOBOT")[:90]
        unit_amount = int(round(float(item.get("unit_price") or 0) * 100))
        quantity = int(item.get("quantity") or 1)
        data[f"line_items[{index}][quantity]"] = str(quantity)
        data[f"line_items[{index}][price_data][currency]"] = "mxn"
        data[f"line_items[{index}][price_data][unit_amount]"] = str(unit_amount)
        data[f"line_items[{index}][price_data][product_data][name]"] = title
    connected = os.environ.get("STRIPE_CONNECTED_ACCOUNT_ID", "").strip()
    if connected:
        fee = int(round(float(subtotal) * commission_rate() * 100))
        data["payment_intent_data[application_fee_amount]"] = str(fee)
        data["payment_intent_data[transfer_data][destination]"] = connected
    payload = urlencode(data).encode("utf-8")
    request = Request(
        f"{STRIPE_API}/checkout/sessions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urlopen(request, timeout=int(os.environ.get("STRIPE_TIMEOUT_SECONDS", "30"))) as response:
        return json.loads(response.read().decode("utf-8"))


def verify_webhook_signature(payload: bytes, signature_header: str | None) -> bool:
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
    if not secret:
        return False
    if not signature_header:
        return False
    parts = dict(part.split("=", 1) for part in signature_header.split(",") if "=" in part)
    timestamp = parts.get("t")
    signature = parts.get("v1")
    if not timestamp or not signature:
        return False
    if abs(time.time() - int(timestamp)) > 300:
        return False
    signed = f"{timestamp}.".encode("utf-8") + payload
    expected = hmac.new(secret.encode("utf-8"), signed, sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def parse_webhook(payload: bytes, signature_header: str | None) -> dict[str, Any]:
    if not verify_webhook_signature(payload, signature_header):
        raise ValueError("Firma Stripe invalida")
    return json.loads(payload.decode("utf-8"))
