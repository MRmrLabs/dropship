from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

from app.ai_research import (
    candidate_quality_score,
    dedupe_candidates,
    has_bad_availability,
    max_attempts,
    request_research,
    required_candidates,
    valid_candidates,
    build_research_prompt,
)
from app.meli_marketplace import compare_market_query, fetch_trends
from app.provider_verifier import verify_provider_page
from app.storage import (
    insert_market_snapshot,
    insert_rejected_candidate,
    insert_supplier_snapshot,
    insert_trend_snapshot,
    is_recently_rejected,
)


DEFAULT_POOL_SIZE = 24
DEFAULT_REJECT_MEMORY_DAYS = 30


@dataclass
class VerificationResult:
    accepted: bool
    reason: str
    candidate: dict[str, Any]
    score: dict[str, Any]
    market: dict[str, Any]
    evidence: dict[str, Any]


def deep_search_products(query: str | None = None) -> dict[str, Any]:
    engine = DeepSearchEngine()
    return engine.run(query)


class DeepSearchEngine:
    def __init__(
        self,
        research_request: Callable[[str, str], tuple[dict[str, Any], dict[str, Any]]] | None = None,
        market_compare: Callable[[str, float], dict[str, Any]] | None = None,
        trends_fetcher: Callable[[str | None], dict[str, Any]] | None = None,
        provider_verify: Callable[[str], dict[str, Any]] | None = None,
    ) -> None:
        self.research_request = research_request or request_research
        self.market_compare = market_compare or compare_market_query
        self.trends_fetcher = trends_fetcher or fetch_trends
        self.provider_verify = provider_verify or verify_provider_page

    def run(self, query: str | None = None) -> dict[str, Any]:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key and self.research_request is request_research:
            raise ValueError("Falta configurar OPENAI_API_KEY")

        target = required_candidates()
        pool_size = candidate_pool_size()
        stages: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        accepted: list[VerificationResult] = []
        raw_candidates: list[dict[str, Any]] = []
        sources: list[dict[str, str]] = []
        started_at = time.monotonic()

        trends = self.safe_fetch_trends()
        stages.append({"stage": "buscando tendencias", "items": len(trends.get("items", [])), "ok": True})

        for attempt in range(1, max_attempts() + 1):
            if time.monotonic() - started_at > deep_search_max_seconds():
                stages.append({"stage": "limite de tiempo", "attempt": attempt, "accepted": len(accepted), "ok": False})
                break
            if len(raw_candidates) >= pool_size and len(accepted) >= target:
                break
            prompt = build_deep_prompt(query, attempt, target, raw_candidates, trends)
            parsed, raw = self.research_request(api_key, prompt)
            batch = valid_candidates(parsed.get("candidates", []))
            raw_candidates = dedupe_candidates(raw_candidates + batch)[:pool_size]
            sources.extend(extract_raw_sources(raw))
            stages.append(
                {
                    "stage": "generando candidatos",
                    "attempt": attempt,
                    "returned": len(parsed.get("candidates", [])),
                    "pool": len(raw_candidates),
                    "summary": parsed.get("summary", ""),
                }
            )
            accepted, rejected = self.verify_pool(raw_candidates, accepted, rejected, target)
            stages.append(
                {
                    "stage": "verificando candidatos",
                    "attempt": attempt,
                    "accepted": len(accepted),
                    "rejected": len(rejected),
                }
            )
            if len(accepted) >= target:
                break

        if len(accepted) < target:
            self.store_rejections(rejected[-30:])
            raise ValueError(
                f"PrimeLoot reviso {len(raw_candidates)} candidato(s), pero solo {len(accepted)} pasaron. "
                "No se importo basura: revisa Descargados/Descartados y prueba otra categoria o mas intentos."
            )

        winners = sorted(accepted, key=lambda item: item.score["total"], reverse=True)[:target]
        for result in winners:
            candidate = result.candidate
            insert_supplier_snapshot(
                str(candidate.get("supplier_name") or ""),
                str(candidate.get("supplier_buy_url") or ""),
                result.evidence.get("supplier", {}),
            )
            insert_market_snapshot(None, str(candidate.get("product_title") or ""), result.market)
        self.store_rejections(rejected[-40:])

        return {
            "query": query or default_deep_query(trends),
            "summary": f"PrimeLoot encontro {len(winners)} oportunidades fuertes tras revisar {len(raw_candidates)} candidato(s).",
            "engine": "primeloot_deep_search_v2",
            "stages": stages,
            "candidates": [self.public_candidate(result) for result in winners],
            "rejected": rejected[-20:],
            "sources": sources,
            "trends": trends,
        }

    def store_rejections(self, rejected: list[dict[str, Any]]) -> None:
        for item in rejected:
            reason = str(item.get("reason") or "rechazado")
            if is_source_error_reason(reason):
                continue
            insert_rejected_candidate(item.get("candidate", {}), reason)

    def safe_fetch_trends(self) -> dict[str, Any]:
        trends = self.trends_fetcher(None)
        insert_trend_snapshot("MLM", None, trends)
        return trends

    def verify_pool(
        self,
        candidates: list[dict[str, Any]],
        accepted: list[VerificationResult],
        rejected: list[dict[str, Any]],
        target: int,
    ) -> tuple[list[VerificationResult], list[dict[str, Any]]]:
        accepted_keys = {candidate_key(item.candidate) for item in accepted}
        rejected_keys = {candidate_key(item["candidate"]) for item in rejected}
        for candidate in candidates:
            key = candidate_key(candidate)
            if key in accepted_keys or key in rejected_keys:
                continue
            result = OpportunityVerifier(self.market_compare, self.provider_verify).verify(candidate)
            if result.accepted:
                accepted.append(result)
                accepted_keys.add(key)
            else:
                rejected.append({"candidate": candidate, "reason": result.reason, "score": result.score})
                rejected_keys.add(key)
            if len(accepted) >= target:
                break
        return accepted, rejected

    def public_candidate(self, result: VerificationResult) -> dict[str, Any]:
        candidate = dict(result.candidate)
        candidate["score_details"] = result.score
        candidate["market_snapshot"] = result.market
        candidate["evidence"] = result.evidence
        candidate["risk_flags"] = list(dict.fromkeys((candidate.get("risk_flags") or []) + result.evidence.get("warnings", [])))
        candidate["notes"] = (
            f"{candidate.get('notes', '')} | PrimeLoot: {result.reason}. "
            f"Score {result.score['total']}/100."
        ).strip()
        return candidate


class OpportunityVerifier:
    def __init__(
        self,
        market_compare: Callable[[str, float], dict[str, Any]] | None = None,
        provider_verify: Callable[[str], dict[str, Any]] | None = None,
    ) -> None:
        self.market_compare = market_compare or compare_market_query
        self.provider_verify = provider_verify or verify_provider_page

    def verify(self, candidate: dict[str, Any]) -> VerificationResult:
        title = str(candidate.get("product_title") or "")
        buy_url = str(candidate.get("supplier_buy_url") or "")
        evidence = {"warnings": [], "survived_because": []}
        if is_recently_rejected(title, buy_url, reject_memory_days()):
            return self.reject(candidate, "Producto rechazado recientemente por memoria", {}, evidence)
        reason = reject_reason(candidate)
        if reason:
            return self.reject(candidate, reason, {}, evidence)
        provider_snapshot = self.provider_verify(buy_url)
        evidence["supplier"] = provider_snapshot
        if not provider_snapshot.get("available"):
            if is_broken_product_url(provider_snapshot):
                root_status = "dominio proveedor abre" if provider_snapshot.get("root_available") else "dominio proveedor no verificable"
                return self.reject(
                    candidate,
                    f"URL directa de proveedor rota ({root_status}); no se opera sin URL exacta de producto",
                    {},
                    evidence,
                )
            return self.reject(candidate, str(provider_snapshot.get("reason") or "Proveedor no verificable"), {}, evidence)

        if os.environ.get("ML_MARKET_VERIFY_ENABLED", "true").lower() in {"1", "true", "yes"}:
            market = self.market_compare(title, float(candidate.get("estimated_market_price_mxn") or 0))
        else:
            market = synthetic_market(candidate)
        score = score_candidate(candidate, market)
        if score["total"] < 70:
            return self.reject(candidate, f"Score insuficiente ({score['total']}/100)", market, evidence, score)
        if score["subscores"]["competencia"] < 42:
            return self.reject(candidate, "Competencia ML demasiado fuerte", market, evidence, score)
        if score["subscores"]["margen"] < 48:
            return self.reject(candidate, "Margen real insuficiente tras comparar mercado", market, evidence, score)

        evidence["survived_because"] = survival_reasons(candidate, score, market)
        return VerificationResult(True, "Sobrevivio verificacion multi-fuente", candidate, score, market, evidence)

    def reject(
        self,
        candidate: dict[str, Any],
        reason: str,
        market: dict[str, Any],
        evidence: dict[str, Any],
        score: dict[str, Any] | None = None,
    ) -> VerificationResult:
        return VerificationResult(False, reason, candidate, score or empty_score(), market, evidence)


def reject_reason(candidate: dict[str, Any]) -> str | None:
    text = candidate_text(candidate)
    if has_bad_availability(text):
        return "Disponibilidad mala o agotado"
    if not str(candidate.get("supplier_buy_url") or "").startswith("http"):
        return "Sin URL directa de compra proveedor"
    if not str(candidate.get("supplier_website") or "").startswith("http"):
        return "Sin sitio proveedor verificable"
    if float(candidate.get("estimated_cost_mxn") or 0) < 20:
        return "Costo proveedor no verificable"
    if str(candidate.get("stock_signal") or "").lower() not in {"alto", "medio"}:
        return "Stock bajo o incierto"
    if str(candidate.get("saturation_signal") or "").lower() == "alta":
        return "Saturacion declarada alta"
    if float(candidate.get("confidence") or 0) < 0.62:
        return "Confianza baja"
    urls = candidate.get("source_urls") or []
    if len([url for url in urls if str(url).startswith("http")]) < 1:
        return "Sin fuentes verificables"
    return None


def score_candidate(candidate: dict[str, Any], market: dict[str, Any]) -> dict[str, Any]:
    suggested = float(candidate.get("suggested_sale_price_mxn") or 0)
    cost = float(candidate.get("estimated_cost_mxn") or 0)
    shipping = float(candidate.get("estimated_shipping_mxn") or 0)
    margin_rate = (suggested - cost - shipping) / max(suggested, 1)
    competition = str(market.get("competition_level") or candidate.get("saturation_signal") or "medium")
    count = int(market.get("count") or 0)
    source_confidence = int(float(candidate.get("confidence") or 0) * 100)
    subscores = {
        "demanda": demand_score(candidate),
        "margen": clamp(int(margin_rate * 220), 0, 100),
        "competencia": competition_score(competition, count),
        "proveedor": supplier_score(candidate),
        "riesgo": risk_score(candidate),
        "ejecucion": execution_score(candidate),
        "confianza_fuentes": source_confidence,
    }
    weights = {
        "demanda": 0.18,
        "margen": 0.24,
        "competencia": 0.18,
        "proveedor": 0.16,
        "riesgo": 0.12,
        "ejecucion": 0.12,
        "confianza_fuentes": 0.0,
    }
    total = int(sum(subscores[key] * weights[key] for key in subscores))
    signal = "red"
    if total >= 88:
        signal = "elite"
    elif total >= 76:
        signal = "green"
    elif total >= 66:
        signal = "yellow"
    return {
        "total": clamp(total, 0, 100),
        "signal": signal,
        "subscores": subscores,
        "estimated_margin_rate": round(margin_rate, 4),
        "sellability_score": clamp(int((subscores["demanda"] * 0.45) + (subscores["competencia"] * 0.35) + (subscores["ejecucion"] * 0.20)), 0, 100),
        "profit_survival_score": clamp(int((subscores["margen"] * 0.70) + (subscores["riesgo"] * 0.30)), 0, 100),
        "source_confidence_score": source_confidence,
    }


def demand_score(candidate: dict[str, Any]) -> int:
    demand = str(candidate.get("demand_signal") or "").lower()
    if demand == "alta":
        return 88
    if demand == "media":
        return 70
    return 52


def competition_score(level: str, count: int) -> int:
    level = level.lower()
    if level == "low":
        return 88
    if level == "medium":
        return 68 if count < 120 else 54
    if level == "unknown":
        return 52
    return 35


def supplier_score(candidate: dict[str, Any]) -> int:
    score = 55
    text = candidate_text(candidate)
    if "factura" in text or "rfc" in text:
        score += 18
    if str(candidate.get("supplier_buy_url") or "").startswith("http"):
        score += 15
    if str(candidate.get("stock_signal") or "").lower() == "alto":
        score += 12
    return clamp(score, 0, 100)


def risk_score(candidate: dict[str, Any]) -> int:
    risks = candidate.get("risk_flags") or []
    score = 88 - len(risks) * 12
    text = candidate_text(candidate)
    if any(term in text for term in ("marca restringida", "sin autoriz", "garantia sensible")):
        score -= 25
    return clamp(score, 0, 100)


def execution_score(candidate: dict[str, Any]) -> int:
    lead_time = int(candidate.get("lead_time_days") or 10)
    score = 86
    if lead_time > 3:
        score -= 16
    if lead_time > 7:
        score -= 20
    if not candidate.get("investment_plan"):
        score -= 10
    return clamp(score, 0, 100)


def survival_reasons(candidate: dict[str, Any], score: dict[str, Any], market: dict[str, Any]) -> list[str]:
    reasons = [
        f"Margen estimado {score['estimated_margin_rate'] * 100:.1f}%",
        f"Competencia {market.get('competition_level', 'unknown')} con {market.get('count', 0)} resultado(s)",
        f"Stock {candidate.get('stock_signal')}",
        f"Confianza {float(candidate.get('confidence') or 0) * 100:.0f}%",
    ]
    return reasons


def synthetic_market(candidate: dict[str, Any]) -> dict[str, Any]:
    saturation = str(candidate.get("saturation_signal") or "media").lower()
    level = {"baja": "low", "media": "medium", "alta": "high"}.get(saturation, "unknown")
    return {
        "query": candidate.get("product_title") or "",
        "count": int(candidate.get("competition_count_estimate") or 0),
        "reference_price": float(candidate.get("estimated_market_price_mxn") or 0),
        "median_price": float(candidate.get("estimated_market_price_mxn") or 0),
        "min_price": float(candidate.get("estimated_market_price_mxn") or 0),
        "seller_count": 0,
        "full_shipping_count": 0,
        "competition_level": level,
        "items": [],
    }


def build_deep_prompt(
    query: str | None,
    attempt: int,
    target: int,
    existing: list[dict[str, Any]],
    trends: dict[str, Any],
) -> str:
    trend_terms = trend_keywords(trends)
    base = build_research_prompt(query or default_deep_query(trends), attempt, target, [item.get("product_title", "") for item in existing])
    return (
        base
        + "\n\nUsa estas tendencias Mercado Libre como senales, no como unica verdad:\n"
        + "\n".join(f"- {term}" for term in trend_terms[:12])
        + "\nGenera candidatos distintos entre si para construir un pool amplio antes del filtro final."
    )


def default_deep_query(trends: dict[str, Any]) -> str:
    terms = " ".join(trend_keywords(trends)[:8])
    return (
        "accesorios tecnologia Mercado Libre Mexico proveedor mexicano factura stock alto margen "
        f"{terms}"
    ).strip()


def trend_keywords(trends: dict[str, Any]) -> list[str]:
    output: list[str] = []
    for item in trends.get("items", []):
        if isinstance(item, str):
            output.append(item)
        elif isinstance(item, dict):
            output.append(str(item.get("keyword") or item.get("name") or item.get("title") or item.get("query") or ""))
    return [term for term in output if term]


def extract_raw_sources(raw: dict[str, Any]) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    for item in raw.get("output", []):
        if item.get("type") != "web_search_call":
            continue
        for source in (item.get("action") or {}).get("sources", []):
            url = source.get("url")
            if url:
                sources.append({"url": url, "title": source.get("title", url)})
    return sources


def candidate_pool_size() -> int:
    return max(required_candidates(), min(60, int(os.environ.get("AI_CANDIDATE_POOL_SIZE", DEFAULT_POOL_SIZE))))


def reject_memory_days() -> int:
    return max(1, int(os.environ.get("REJECT_MEMORY_DAYS", DEFAULT_REJECT_MEMORY_DAYS)))


def deep_search_max_seconds() -> int:
    return max(60, int(os.environ.get("DEEP_SEARCH_MAX_MINUTES", "20")) * 60)


def candidate_key(candidate: dict[str, Any]) -> str:
    title = normalize_key(str(candidate.get("product_title") or ""))
    url = normalize_key(str(candidate.get("supplier_buy_url") or ""))
    return f"{title}:{url}"


def candidate_text(candidate: dict[str, Any]) -> str:
    parts = [
        candidate.get("product_title"),
        candidate.get("supplier_contact"),
        candidate.get("stock_signal"),
        candidate.get("notes"),
        candidate.get("investment_plan"),
        " ".join(str(flag) for flag in candidate.get("risk_flags") or []),
    ]
    return " ".join(str(part or "") for part in parts).lower()


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def is_broken_product_url(snapshot: dict[str, Any]) -> bool:
    return str(snapshot.get("failure_kind") or "") == "http_404"


def is_source_error_reason(reason: str) -> bool:
    text = reason.lower()
    return (
        "url directa de proveedor rota" in text
        or "no se pudo abrir proveedor: http 404" in text
        or "no se pudo abrir proveedor: http error 404" in text
    )


def empty_score() -> dict[str, Any]:
    return {
        "total": 0,
        "signal": "red",
        "subscores": {
            "demanda": 0,
            "margen": 0,
            "competencia": 0,
            "proveedor": 0,
            "riesgo": 0,
            "ejecucion": 0,
            "confianza_fuentes": 0,
        },
        "estimated_margin_rate": 0,
        "sellability_score": 0,
        "profit_survival_score": 0,
        "source_confidence_score": 0,
    }


def clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(upper, value))
