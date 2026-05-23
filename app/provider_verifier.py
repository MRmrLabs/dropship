from __future__ import annotations

import re
from html import unescape
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


BAD_AVAILABILITY = (
    "agotado",
    "sin stock",
    "no disponible",
    "descontinuado",
    "preventa",
    "consultar disponibilidad",
    "proximamente",
    "próximamente",
)
BUY_SIGNALS = (
    "agregar al carrito",
    "añadir al carrito",
    "comprar ahora",
    "cotizar",
    "solicitar cotización",
    "agregar",
)
INVOICE_SIGNALS = ("factura", "facturación", "rfc", "razón social", "razon social")


def verify_provider_page(url: str, timeout: int = 20) -> dict[str, Any]:
    if not url.startswith(("http://", "https://")):
        return snapshot(url, False, "URL proveedor invalida")
    try:
        request = Request(
            url,
            headers={
                "User-Agent": "PrimeLoot/1.0 (+local opportunity verifier)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(400_000).decode("utf-8", errors="replace")
    except (URLError, TimeoutError, OSError) as exc:
        return snapshot(url, False, f"No se pudo abrir proveedor: {exc}")

    text = html_to_text(raw)
    lower = text.lower()
    bad_terms = [term for term in BAD_AVAILABILITY if term in lower]
    price = extract_price(text)
    has_buy_signal = any(signal in lower for signal in BUY_SIGNALS)
    has_invoice_signal = any(signal in lower for signal in INVOICE_SIGNALS)
    available = not bad_terms and (has_buy_signal or price > 0)
    reason = "Proveedor verificable"
    if bad_terms:
        reason = f"Proveedor indica mala disponibilidad: {', '.join(bad_terms[:3])}"
    elif not available:
        reason = "No hay precio ni señal clara de compra/cotización"

    data = snapshot(url, available, reason)
    data.update(
        {
            "price_visible": price,
            "has_buy_signal": has_buy_signal,
            "has_invoice_signal": has_invoice_signal,
            "bad_terms": bad_terms,
            "text_excerpt": text[:1800],
            "source": "provider_page_http",
        }
    )
    return data


def snapshot(url: str, available: bool, reason: str) -> dict[str, Any]:
    return {
        "url": url,
        "available": available,
        "reason": reason,
        "price_visible": 0.0,
        "has_buy_signal": False,
        "has_invoice_signal": False,
        "bad_terms": [],
        "text_excerpt": "",
    }


def html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    raw = unescape(raw)
    return re.sub(r"\s+", " ", raw).strip()


def extract_price(text: str) -> float:
    patterns = [
        r"\$\s*([0-9]{2,6}(?:[,.][0-9]{2})?)",
        r"MXN\s*([0-9]{2,6}(?:[,.][0-9]{2})?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        value = match.group(1).replace(",", "")
        try:
            return float(value)
        except ValueError:
            continue
    return 0.0
