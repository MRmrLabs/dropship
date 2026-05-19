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
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_MAX_OUTPUT_TOKENS = 1600


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
        "request_timeout_seconds": int(os.environ.get("OPENAI_REQUEST_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)),
    }


def research_products(query: str | None = None) -> dict[str, Any]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("Falta configurar OPENAI_API_KEY")

    prompt = build_research_prompt(query)
    payload = {
        "model": os.environ.get("OPENAI_WEB_MODEL", DEFAULT_MODEL),
        "max_output_tokens": int(os.environ.get("OPENAI_MAX_OUTPUT_TOKENS", DEFAULT_MAX_OUTPUT_TOKENS)),
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
    parsed.setdefault("query", query or default_query())
    parsed.setdefault("candidates", [])
    parsed["candidates"] = parsed["candidates"][: max_candidates()]
    parsed["raw_response_id"] = raw.get("id")
    parsed["sources"] = extract_sources(raw)
    return parsed


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
    return max(1, min(8, int(os.environ.get("AI_MAX_CANDIDATES", DEFAULT_MAX_CANDIDATES))))


def build_research_prompt(query: str | None) -> str:
    search_query = query or default_query()
    return f"""
Busca en internet proveedores reales en Mexico para mayoreo o dropshipping de accesorios tecnologicos.
Prioriza distribuidores mexicanos, factura, envio nacional, precios visibles o catalogos consultables.
No inventes datos. Si un costo, stock o envio no esta claro, marca el campo como estimado y explica el riesgo.

Consulta: {search_query}

Devuelve solamente JSON valido, sin markdown, con esta forma exacta:
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
      "stock_signal": "alto|medio|bajo|desconocido",
      "warranty": "texto breve",
      "lead_time_days": 3,
      "source_urls": ["https://..."],
      "risk_flags": ["riesgo"],
      "confidence": 0.0,
      "notes": "por que podria venderse y que validar"
    }}
  ]
}}

Limita a {max_candidates()} candidatos. Responde compacto. Evita marcas con restricciones fuertes si no hay evidencia clara de autorizacion.
""".strip()


def default_query() -> str:
    return (
        "proveedores mayoristas Mexico accesorios tecnologia cables usb c hubs cargadores "
        "soportes laptop perifericos con factura envio nacional"
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
