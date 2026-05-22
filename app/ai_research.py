from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any
from urllib.request import Request, urlopen


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_DAILY_LIMIT = 3
DEFAULT_MIN_INTERVAL_SECONDS = 300
DEFAULT_MAX_CANDIDATES = 4
DEFAULT_MODEL = "gpt-4.1-mini"
DEFAULT_TIMEOUT_SECONDS = 240
DEFAULT_MAX_OUTPUT_TOKENS = 2600
DEFAULT_REQUIRED_CANDIDATES = 4
DEFAULT_MAX_ATTEMPTS = 5


def openai_status() -> dict[str, Any]:
    return {
        "configured": bool(os.environ.get("OPENAI_API_KEY")),
        "model": os.environ.get("OPENAI_WEB_MODEL", DEFAULT_MODEL),
        "tool": "web_search",
        "daily_limit": int(os.environ.get("AI_DAILY_SEARCH_LIMIT", DEFAULT_DAILY_LIMIT)),
        "min_interval_seconds": int(
            os.environ.get("AI_MIN_SECONDS_BETWEEN_SEARCHES", DEFAULT_MIN_INTERVAL_SECONDS)
        ),
        "max_candidates": int(os.environ.get("AI_MAX_CANDIDATES", DEFAULT_MAX_CANDIDATES)),
        "required_candidates": required_candidates(),
        "max_attempts": max_attempts(),
        "request_timeout_seconds": int(os.environ.get("OPENAI_REQUEST_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)),
    }


def research_products(query: str | None = None) -> dict[str, Any]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("Falta configurar OPENAI_API_KEY")

    target = required_candidates()
    attempts = []
    accepted: list[dict[str, Any]] = []
    sources: list[dict[str, str]] = []
    response_ids: list[str] = []

    for attempt in range(1, max_attempts() + 1):
        missing = target - len(accepted)
        if missing <= 0:
            break
        prompt = build_research_prompt(query, attempt, missing, [item["product_title"] for item in accepted])
        parsed, raw = request_research(api_key, prompt)
        candidates = valid_candidates(parsed.get("candidates", []))
        before = len(accepted)
        accepted = dedupe_candidates(accepted + candidates)
        attempts.append(
            {
                "attempt": attempt,
                "requested": missing,
                "returned": len(parsed.get("candidates", [])),
                "accepted": len(accepted) - before,
                "summary": parsed.get("summary", ""),
            }
        )
        response_ids.append(str(raw.get("id") or ""))
        sources.extend(extract_sources(raw))

    if len(accepted) < target:
        raise ValueError(
            f"No junte {target} productos perfectos; solo {len(accepted)} pasaron filtros estrictos. "
            "Intenta una busqueda mas especifica o sube AI_RESEARCH_MAX_ATTEMPTS/OPENAI_REQUEST_TIMEOUT_SECONDS."
        )

    return {
        "query": query or default_query(),
        "summary": f"Se encontraron {len(accepted[:target])} oportunidades validas tras {len(attempts)} intento(s).",
        "candidates": accepted[:target],
        "attempts": attempts,
        "raw_response_id": ",".join(response_id for response_id in response_ids if response_id),
        "sources": unique_sources(sources),
    }


def request_research(api_key: str, prompt: str) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = {
        "model": os.environ.get("OPENAI_DEEP_ANALYSIS_MODEL", os.environ.get("OPENAI_WEB_MODEL", DEFAULT_MODEL)),
        "max_output_tokens": int(os.environ.get("OPENAI_DEEP_MAX_OUTPUT_TOKENS", os.environ.get("OPENAI_MAX_OUTPUT_TOKENS", DEFAULT_MAX_OUTPUT_TOKENS))),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "dropshipping_research",
                "strict": True,
                "schema": research_schema(),
            }
        },
        "tools": [
            {
                "type": "web_search",
                "external_web_access": True,
                "user_location": {
                    "type": "approximate",
                    "country": "MX",
                    "city": "Mexico City",
                    "region": "CDMX",
                    "timezone": "America/Mexico_City",
                },
            }
        ],
        "tool_choice": "auto",
        "include": ["web_search_call.action.sources"],
        "input": prompt,
    }
    request = Request(
        OPENAI_RESPONSES_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    timeout = int(os.environ.get("OPENAI_REQUEST_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
    with urlopen(request, timeout=timeout) as response:
        raw = json.loads(response.read().decode("utf-8"))

    output_text = extract_output_text(raw)
    parsed = parse_json_object(output_text)
    parsed.setdefault("candidates", [])
    return parsed, raw


def enforce_usage_limits(today_count: int, latest_run: dict[str, Any] | None) -> None:
    limit = int(os.environ.get("AI_DAILY_SEARCH_LIMIT", DEFAULT_DAILY_LIMIT))
    if today_count >= limit:
        raise ValueError(f"Limite diario de busquedas IA alcanzado ({limit}). Intenta manana.")
    min_seconds = int(os.environ.get("AI_MIN_SECONDS_BETWEEN_SEARCHES", DEFAULT_MIN_INTERVAL_SECONDS))
    if not latest_run:
        return
    created_at = str(latest_run.get("created_at") or "")
    try:
        latest = datetime.fromisoformat(created_at.replace(" ", "T")).replace(tzinfo=timezone.utc)
    except ValueError:
        return
    elapsed = (datetime.now(timezone.utc) - latest).total_seconds()
    if elapsed < min_seconds:
        wait = int(min_seconds - elapsed)
        raise ValueError(f"Espera {wait} segundos antes de otra busqueda IA.")


def max_candidates() -> int:
    return max(required_candidates(), min(8, int(os.environ.get("AI_MAX_CANDIDATES", DEFAULT_MAX_CANDIDATES))))


def required_candidates() -> int:
    return max(4, min(8, int(os.environ.get("AI_REQUIRED_CANDIDATES", DEFAULT_REQUIRED_CANDIDATES))))


def max_attempts() -> int:
    return max(1, min(8, int(os.environ.get("AI_RESEARCH_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS))))


def research_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary": {"type": "string"},
            "candidates": {
                "type": "array",
                "maxItems": max_candidates(),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "supplier_name": {"type": "string"},
                        "supplier_website": {"type": "string"},
                        "supplier_contact": {"type": "string"},
                        "product_title": {"type": "string"},
                        "brand": {"type": "string"},
                        "category": {"type": "string"},
                        "estimated_cost_mxn": {"type": "number", "minimum": 20},
                        "estimated_shipping_mxn": {"type": "number", "minimum": 0},
                        "estimated_market_price_mxn": {"type": "number", "minimum": 50},
                        "suggested_sale_price_mxn": {"type": "number", "minimum": 50},
                        "stock_signal": {"type": "string"},
                        "warranty": {"type": "string"},
                        "lead_time_days": {"type": "integer", "minimum": 1, "maximum": 10},
                        "source_urls": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                        "supplier_buy_url": {"type": "string"},
                        "meli_reference_urls": {"type": "array", "items": {"type": "string"}},
                        "competition_count_estimate": {"type": "integer", "minimum": 0},
                        "saturation_signal": {"type": "string"},
                        "demand_signal": {"type": "string"},
                        "why_it_can_sell": {"type": "string"},
                        "investment_plan": {"type": "string"},
                        "risk_flags": {"type": "array", "items": {"type": "string"}},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "notes": {"type": "string"},
                    },
                    "required": [
                        "supplier_name",
                        "supplier_website",
                        "supplier_contact",
                        "product_title",
                        "brand",
                        "category",
                        "estimated_cost_mxn",
                        "estimated_shipping_mxn",
                        "estimated_market_price_mxn",
                        "suggested_sale_price_mxn",
                        "stock_signal",
                        "warranty",
                        "lead_time_days",
                        "source_urls",
                        "supplier_buy_url",
                        "meli_reference_urls",
                        "competition_count_estimate",
                        "saturation_signal",
                        "demand_signal",
                        "why_it_can_sell",
                        "investment_plan",
                        "risk_flags",
                        "confidence",
                        "notes",
                    ],
                },
            },
        },
        "required": ["summary", "candidates"],
    }


def build_research_prompt(query: str | None, attempt: int = 1, missing: int | None = None, exclude_titles: list[str] | None = None) -> str:
    search_query = query or default_query()
    needed = missing or required_candidates()
    exclusions = "\n".join(f"- {title}" for title in (exclude_titles or [])) or "- ninguno"
    return f"""
Actua como comprador experto de e-commerce en Mexico. Busca oportunidades reales, no productos genericos faciles de descartar.

Objetivo: encontrar productos concretos, comprables y revendibles en Mercado Libre Mexico con margen neto mayor a 15%.
Haz una investigacion profunda por candidato. No premies solo margen: califica si realmente puede venderse.
Esta es la busqueda interna #{attempt}. Necesito {needed} candidato(s) NUEVOS que pasen filtros estrictos.
No repitas estos productos ya aceptados:
{exclusions}

Busca proveedores reales en Mexico para mayoreo, distribucion autorizada o venta B2B.
Cada candidato debe ser un producto especifico, no una categoria. Ejemplos buenos:
- "Hub USB-C 7 en 1 UGREEN CM512" con liga directa de proveedor, costo estimado y precio sugerido;
- "Soporte laptop aluminio ajustable marca X modelo Y";
- "Cable USB-C a USB-C 100W 2m marca/modelo especifico".

Prioriza candidatos con evidencia publica de:
- factura o RFC/razon social;
- envio nacional en Mexico;
- catalogo, precio, lista de mayoreo o producto con precio visible;
- proveedor mexicano o distribuidor con operacion clara en Mexico;
- productos de bajo riesgo: hubs USB-C, soportes, organizadores, accesorios ergonomicos, cables certificados genericos, perifericos sin marca restringida.
- una URL donde se pueda comprar o solicitar mayoreo.
- referencias de Mercado Libre para comparar precio, saturacion y vendedores.
- disponibilidad real: evita agotado, sin stock, consultar disponibilidad, proximamente, preventa, descontinuado.

Evita traer candidatos si solo encuentras:
- marketplaces retail sin margen claro;
- publicaciones de otros vendedores de Mercado Libre/Amazon como "proveedor";
- marcas restringidas o sensibles sin autorizacion;
- productos con precio proveedor casi igual al precio de venta;
- proveedor sin forma clara de validar factura/contacto.
- stock bajo, agotado, sin precio, solo cotizacion sin producto claro.

No inventes datos. Si no hay al menos una fuente que apoye proveedor + producto, no incluyas el candidato.
Nunca uses 0, 1, 9.99 ni valores placeholder en precios. Si no puedes confirmar un precio realista de proveedor y un precio realista de mercado, omite ese candidato.
Si el costo/stock/envio no esta claro pero el proveedor parece real, marca el riesgo y baja la confianza.
Busca productos con nombre/modelo concreto. Ejemplo malo: "cables USB-C". Ejemplo bueno: "Cable USB-C a USB-C 100W 2m nylon trenzado marca X modelo Y".

Por cada candidato explica:
- comprarlo aqui: URL oficial del proveedor;
- venderlo en ML a: precio sugerido;
- cuanto pedir al inicio: 1, 3 o 5 unidades segun riesgo;
- por que podria venderse;
- que validaciones faltan antes de invertir;
- si la saturacion es baja, media o alta.

Consulta: {search_query}

Devuelve datos estructurados con esta forma:
{{
  "summary": "resumen breve",
  "candidates": [
    {{
      "supplier_name": "nombre",
      "supplier_website": "https://...",
      "supplier_contact": "email, telefono o pagina de contacto",
      "product_title": "producto",
      "brand": "marca o Generico",
      "category": "cables|cargadores|adaptadores|soportes|perifericos|hubs|fundas|micas|usb|organizadores tech",
      "estimated_cost_mxn": 0,
      "estimated_shipping_mxn": 0,
      "estimated_market_price_mxn": 0,
      "suggested_sale_price_mxn": 0,
      "stock_signal": "alto|medio|bajo|desconocido",
      "warranty": "texto breve",
      "lead_time_days": 3,
      "source_urls": ["https://..."],
      "supplier_buy_url": "https://...",
      "meli_reference_urls": ["https://..."],
      "competition_count_estimate": 12,
      "saturation_signal": "baja|media|alta",
      "demand_signal": "baja|media|alta",
      "why_it_can_sell": "razon comercial",
      "investment_plan": "pide 3, cuesta X, vendes a Y, tarda Z dias, valida A/B/C",
      "risk_flags": ["riesgo"],
      "confidence": 0.0,
      "notes": "comprarlo aqui, venderlo a este precio y que validar"
    }}
  ]
}}

Limita a {max_candidates()} candidatos. Responde compacto.
Ordena primero los mejores candidatos: producto mas especifico, liga de compra mas clara, menor riesgo, margen estimado mas sano.
Si no encuentras candidatos perfectos y disponibles, devuelve "candidates": [] y explica en summary que no hubo evidencia suficiente. No rellenes con productos flojos.
""".strip()


def valid_candidates(candidates: Any) -> list[dict[str, Any]]:
    if not isinstance(candidates, list):
        return []
    valid: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        cost = as_float(candidate.get("estimated_cost_mxn"))
        shipping = as_float(candidate.get("estimated_shipping_mxn"))
        market = as_float(candidate.get("estimated_market_price_mxn"))
        suggested = as_float(candidate.get("suggested_sale_price_mxn"))
        urls = candidate.get("source_urls")
        buy_url = str(candidate.get("supplier_buy_url") or "").strip()
        title = str(candidate.get("product_title") or "").strip()
        supplier = str(candidate.get("supplier_name") or "").strip()
        stock = str(candidate.get("stock_signal") or "").strip().lower()
        saturation = str(candidate.get("saturation_signal") or "").strip().lower()
        confidence = as_float(candidate.get("confidence"))
        text = candidate_text(candidate)
        if cost < 20 or market < 50 or suggested < 50:
            continue
        if suggested <= cost + shipping:
            continue
        if not isinstance(urls, list) or not [url for url in urls if str(url).startswith("http")]:
            continue
        if not buy_url.startswith("http"):
            continue
        if len(title) < 10 or len(supplier) < 3:
            continue
        if stock not in {"alto", "medio"}:
            continue
        if saturation == "alta":
            continue
        if confidence < 0.58:
            continue
        if has_bad_availability(text):
            continue
        valid.append(candidate)
    return valid


def dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for candidate in candidates:
        title = normalize_key(str(candidate.get("product_title") or ""))
        buy_url = str(candidate.get("supplier_buy_url") or "").split("?")[0].rstrip("/")
        duplicate = False
        for existing in output:
            existing_title = normalize_key(str(existing.get("product_title") or ""))
            existing_url = str(existing.get("supplier_buy_url") or "").split("?")[0].rstrip("/")
            if title == existing_title or (buy_url and buy_url == existing_url):
                duplicate = True
                break
        if not duplicate:
            output.append(candidate)
    return sorted(output, key=candidate_quality_score, reverse=True)


def candidate_quality_score(candidate: dict[str, Any]) -> float:
    margin = (as_float(candidate.get("suggested_sale_price_mxn")) - as_float(candidate.get("estimated_cost_mxn")) - as_float(candidate.get("estimated_shipping_mxn"))) / max(as_float(candidate.get("suggested_sale_price_mxn")), 1)
    score = as_float(candidate.get("confidence")) * 100 + margin * 80
    if str(candidate.get("stock_signal") or "").lower() == "alto":
        score += 10
    if str(candidate.get("saturation_signal") or "").lower() == "baja":
        score += 10
    return score


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def candidate_text(candidate: dict[str, Any]) -> str:
    parts = [
        candidate.get("product_title"),
        candidate.get("stock_signal"),
        candidate.get("notes"),
        candidate.get("investment_plan"),
        " ".join(str(flag) for flag in candidate.get("risk_flags") or []),
    ]
    return " ".join(str(part or "") for part in parts).lower()


def has_bad_availability(text: str) -> bool:
    blocked = (
        "agotado",
        "sin stock",
        "no disponible",
        "descontinuado",
        "preventa",
        "proximamente",
        "próximamente",
        "consultar disponibilidad",
        "stock bajo",
    )
    return any(term in text for term in blocked)


def as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def default_query() -> str:
    return (
        "distribuidor mayorista Mexico accesorios tecnologia factura hubs usb c soportes ergonomicos "
        "organizadores escritorio perifericos bajo riesgo precio mayoreo envio nacional"
    )


def extract_output_text(raw: dict[str, Any]) -> str:
    chunks: list[str] = []
    for item in raw.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            text = content.get("text")
            if text:
                chunks.append(text)
    return "\n".join(chunks).strip()


def parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    candidates = [cleaned]
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        candidates.append(match.group(0))
    for candidate in candidates:
        for variant in (candidate, repair_json_text(candidate)):
            try:
                return json.loads(variant)
            except json.JSONDecodeError:
                continue
    raise ValueError("La IA devolvio JSON invalido. Intenta de nuevo con una busqueda mas especifica.")


def repair_json_text(text: str) -> str:
    repaired = text.replace("\u201c", '"').replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'")
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
    return repaired


def extract_sources(raw: dict[str, Any]) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw.get("output", []):
        if item.get("type") != "web_search_call":
            continue
        action = item.get("action", {})
        for source in action.get("sources", []):
            url = source.get("url")
            if not url or url in seen:
                continue
            seen.add(url)
            sources.append({"url": url, "title": source.get("title", url)})
    return sources


def unique_sources(sources: list[dict[str, str]]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for source in sources:
        url = source.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        output.append(source)
    return output
