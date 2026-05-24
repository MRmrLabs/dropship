from __future__ import annotations

import re
from html import unescape
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
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
        data = snapshot(url, False, "URL proveedor invalida")
        data["failure_kind"] = "invalid_url"
        return data
    try:
        raw = read_provider_html(url, timeout)
    except HTTPError as exc:
        return failed_http_snapshot(url, exc, timeout)
    except (URLError, TimeoutError, OSError) as exc:
        data = snapshot(url, False, f"No se pudo abrir proveedor: {exc}")
        data["failure_kind"] = "network_error"
        return data

    return analyze_provider_html(url, raw)


def read_provider_html(url: str, timeout: int) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "PrimeLoot/1.0 (+local opportunity verifier)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return response.read(400_000).decode("utf-8", errors="replace")


def analyze_provider_html(url: str, raw: str) -> dict[str, Any]:
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
            "failure_kind": "",
            "status_code": 200,
        }
    )
    return data


def failed_http_snapshot(url: str, exc: HTTPError, timeout: int) -> dict[str, Any]:
    status_code = int(getattr(exc, "code", 0) or 0)
    failure_kind = "http_404" if status_code in {404, 410} else "http_error"
    data = snapshot(url, False, f"No se pudo abrir proveedor: HTTP {status_code}")
    data.update({"failure_kind": failure_kind, "status_code": status_code})
    root = root_url(url)
    if root and root.rstrip("/") != url.rstrip("/"):
        data["root_url"] = root
        try:
            root_data = analyze_provider_html(root, read_provider_html(root, timeout))
            data["root_available"] = bool(root_data.get("available") or root_data.get("has_buy_signal") or root_data.get("has_invoice_signal"))
            data["root_reason"] = root_data.get("reason")
            data["root_excerpt"] = root_data.get("text_excerpt", "")[:600]
        except Exception as root_exc:
            data["root_available"] = False
            data["root_reason"] = str(root_exc)
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
        "failure_kind": "",
        "status_code": 0,
        "root_url": "",
        "root_available": False,
        "root_reason": "",
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


def root_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"
