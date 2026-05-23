from __future__ import annotations

import os
import threading
import time
import uuid
from typing import Any

from app.deep_search import OpportunityVerifier, candidate_pool_size, deep_search_products, required_candidates, score_candidate
from app.meli_marketplace import compare_market_query, fetch_trends
from app.provider_verifier import verify_provider_page


JOBS: dict[str, dict[str, Any]] = {}
LOCK = threading.Lock()


def local_search_status() -> dict[str, Any]:
    return {
        "enabled": os.environ.get("LOCAL_SEARCH_ENABLED", "true").lower() in {"1", "true", "yes"},
        "profile": os.environ.get("LOCAL_SEARCH_PROFILE", "balanced"),
        "max_hours": float(os.environ.get("LOCAL_SEARCH_MAX_HOURS", "6")),
        "pool_size": int(os.environ.get("LOCAL_SEARCH_POOL_SIZE", "300")),
        "openai_final_judge_only": os.environ.get("OPENAI_FINAL_JUDGE_ONLY", "true").lower() in {"1", "true", "yes"},
        "openai_finalists_limit": int(os.environ.get("OPENAI_FINALISTS_LIMIT", "10")),
        "seed_urls_configured": bool(seed_urls()),
    }


def start_local_search(query: str | None = None) -> dict[str, Any]:
    if not local_search_status()["enabled"]:
        raise ValueError("LOCAL_SEARCH_ENABLED esta apagado")
    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id,
        "status": "queued",
        "query": query or "",
        "progress": [],
        "result": None,
        "error": None,
        "stop_requested": False,
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    with LOCK:
        JOBS[job_id] = job
    thread = threading.Thread(target=run_local_search_job, args=(job_id,), daemon=True)
    thread.start()
    return public_job(job)


def get_local_search_job(job_id: str) -> dict[str, Any]:
    with LOCK:
        job = JOBS.get(job_id)
        if not job:
            raise KeyError("Job local no encontrado")
        return public_job(job)


def stop_local_search_job(job_id: str) -> dict[str, Any]:
    with LOCK:
        job = JOBS.get(job_id)
        if not job:
            raise KeyError("Job local no encontrado")
        job["stop_requested"] = True
        job["updated_at"] = time.time()
        return public_job(job)


def run_local_search_job(job_id: str) -> None:
    job = require_job(job_id)
    set_job(job_id, status="running")
    try:
        add_progress(job_id, "recolectando candidatos", "Leyendo tendencias Mercado Libre y proveedores semilla")
        trends = fetch_trends(None)
        local_candidates = collect_seed_candidates(job_id)
        if should_stop(job_id):
            set_job(job_id, status="stopped", result={"candidates": [], "local_candidates": local_candidates})
            return

        add_progress(job_id, "verificando proveedor", f"{len(local_candidates)} candidato(s) locales desde URLs semilla")
        verified = verify_local_candidates(local_candidates, job_id)
        if should_stop(job_id):
            set_job(job_id, status="stopped", result={"candidates": verified})
            return

        add_progress(job_id, "comparando Mercado Libre", "Calculando competencia y score local")
        local_winners = [item for item in verified if item.get("accepted")]
        local_winners = sorted(local_winners, key=lambda item: item["score"]["total"], reverse=True)

        result: dict[str, Any] = {
            "engine": "primeloot_local_search",
            "query": job.get("query") or "",
            "trends": trends,
            "local_candidates": verified,
            "candidates": [item["candidate"] for item in local_winners[: required_candidates()]],
            "stages": job.get("progress", []),
        }
        if needs_openai(local_winners):
            add_progress(job_id, "evaluando finalistas", "Usando OpenAI solo para completar/verificar finalistas")
            try:
                result = deep_search_products(str(job.get("query") or ""))
                result["engine"] = "primeloot_local_plus_openai"
            except Exception as exc:
                add_progress(job_id, "openai opcional", f"OpenAI no completo finalistas: {exc}", ok=False)

        add_progress(job_id, "seleccionando top 4", f"{len(result.get('candidates', []))} candidato(s) final(es)")
        set_job(job_id, status="completed", result=result)
    except Exception as exc:
        set_job(job_id, status="failed", error=str(exc))


def collect_seed_candidates(job_id: str) -> list[dict[str, Any]]:
    candidates = []
    for index, url in enumerate(seed_urls(), start=1):
        if should_stop(job_id):
            break
        candidates.append(
            {
                "supplier_name": host_name(url),
                "supplier_website": root_url(url),
                "supplier_contact": "Validar contacto/factura en pagina",
                "product_title": f"Producto proveedor semilla {index}",
                "brand": "Generico",
                "category": "accesorios tech",
                "estimated_cost_mxn": 100,
                "estimated_shipping_mxn": 50,
                "estimated_market_price_mxn": 299,
                "suggested_sale_price_mxn": 349,
                "stock_signal": "medio",
                "warranty": "Validar con proveedor",
                "lead_time_days": 5,
                "source_urls": [url],
                "supplier_buy_url": url,
                "meli_reference_urls": [],
                "competition_count_estimate": 0,
                "saturation_signal": "media",
                "demand_signal": "media",
                "why_it_can_sell": "Candidato local desde proveedor semilla",
                "investment_plan": "Validar precio visible, stock y factura antes de comprar",
                "risk_flags": ["Validacion local semilla"],
                "confidence": 0.55,
                "notes": "Generado por PrimeLoot Local Search sin OpenAI",
            }
        )
    return candidates[: int(os.environ.get("LOCAL_SEARCH_POOL_SIZE", "300"))]


def verify_local_candidates(candidates: list[dict[str, Any]], job_id: str) -> list[dict[str, Any]]:
    output = []
    verifier = OpportunityVerifier(compare_market_query, verify_provider_page)
    for candidate in candidates:
        if should_stop(job_id):
            break
        result = verifier.verify(candidate)
        item = {
            "accepted": result.accepted,
            "reason": result.reason,
            "candidate": result.candidate,
            "score": result.score,
            "market": result.market,
            "evidence": result.evidence,
        }
        if result.accepted:
            item["candidate"]["score_details"] = result.score
            item["candidate"]["market_snapshot"] = result.market
            item["candidate"]["evidence"] = result.evidence
        output.append(item)
    return output


def needs_openai(local_winners: list[dict[str, Any]]) -> bool:
    if os.environ.get("OPENAI_API_KEY"):
        profile = os.environ.get("LOCAL_SEARCH_PROFILE", "balanced").lower()
        if profile == "cheap" and len(local_winners) >= required_candidates():
            return False
        return len(local_winners) < required_candidates() or os.environ.get("OPENAI_FINAL_JUDGE_ONLY", "true").lower() in {"1", "true", "yes"}
    return False


def add_progress(job_id: str, stage: str, message: str, ok: bool = True) -> None:
    with LOCK:
        job = JOBS[job_id]
        job["progress"].append({"stage": stage, "message": message, "ok": ok, "at": time.time()})
        job["updated_at"] = time.time()


def set_job(job_id: str, **updates: Any) -> None:
    with LOCK:
        job = JOBS[job_id]
        job.update(updates)
        job["updated_at"] = time.time()


def require_job(job_id: str) -> dict[str, Any]:
    with LOCK:
        if job_id not in JOBS:
            raise KeyError("Job local no encontrado")
        return JOBS[job_id]


def should_stop(job_id: str) -> bool:
    with LOCK:
        return bool(JOBS.get(job_id, {}).get("stop_requested"))


def public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in job.items() if key != "stop_requested"}


def seed_urls() -> list[str]:
    raw = os.environ.get("LOCAL_SUPPLIER_URLS", "")
    return [url.strip() for url in raw.split(",") if url.strip().startswith(("http://", "https://"))]


def host_name(url: str) -> str:
    clean = url.split("//", 1)[-1].split("/", 1)[0]
    return clean.replace("www.", "")[:80] or "Proveedor local"


def root_url(url: str) -> str:
    prefix = "https://" if url.startswith("https://") else "http://"
    return prefix + url.split("//", 1)[-1].split("/", 1)[0]
