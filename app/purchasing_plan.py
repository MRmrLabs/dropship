from __future__ import annotations

from typing import Any

from app.domain import MIN_NET_MARGIN, money
from app.reports import build_investment_plan


MIN_PURCHASE_CONFIDENCE = 0.80
SCORING_VERSION = "purchase_plan_conservative_v1"


def build_purchase_plan(budget_mxn: float, opportunities: list[dict[str, Any]]) -> dict[str, Any]:
    budget = money(number(budget_mxn))
    if budget <= 0:
        raise ValueError("El presupuesto debe ser mayor a cero")

    candidates = [score_purchase_candidate(item) for item in opportunities]
    ranked = sorted(candidates, key=lambda item: item["rank_score"], reverse=True)
    remaining = budget
    items: list[dict[str, Any]] = []
    rejected_or_reserved: list[dict[str, Any]] = []

    for candidate in ranked:
        if candidate["confidence"] < MIN_PURCHASE_CONFIDENCE:
            rejected_or_reserved.append(rejection(candidate, "Confianza menor a 80%; no se usa presupuesto."))
            continue
        if candidate["expected_value_unit"] <= 0:
            rejected_or_reserved.append(rejection(candidate, "Utilidad esperada ajustada menor o igual a cero."))
            continue
        if candidate["risk_score"] >= 0.72:
            rejected_or_reserved.append(rejection(candidate, "Riesgo operativo o de politica demasiado alto."))
            continue

        quantity = suggested_purchase_quantity(candidate, remaining)
        if quantity <= 0:
            rejected_or_reserved.append(rejection(candidate, "Presupuesto restante insuficiente para una compra conservadora."))
            continue

        investment = total_investment_for(candidate, quantity)
        expected_profit = money(candidate["expected_value_unit"] * quantity)
        remaining = money(remaining - investment)
        items.append(
            {
                "product_id": candidate["product_id"],
                "title": candidate["title"],
                "quantity": quantity,
                "unit_cost": candidate["unit_cost"],
                "total_investment": investment,
                "suggested_sale_price": candidate["suggested_sale_price"],
                "expected_profit": expected_profit,
                "expected_roi": round(expected_profit / investment, 4) if investment else 0,
                "confidence": candidate["confidence"],
                "recommendation": recommendation_for(candidate, allocated=True),
                "why": why_buy(candidate),
                "max_buy_price": max_buy_price(candidate),
                "supplier_name": candidate["supplier_name"],
                "supplier_url": candidate["supplier_url"],
                "steps": action_steps(candidate, quantity),
            }
        )

    allocated = money(sum(item["total_investment"] for item in items))
    expected_profit = money(sum(item["expected_profit"] for item in items))
    confidence = weighted_confidence(items)
    expected_roi = round(expected_profit / allocated, 4) if allocated else 0
    reserved = money(budget - allocated)
    verdict = plan_verdict(allocated, reserved)
    summary = plan_summary(budget, allocated, reserved, expected_profit, confidence)

    if not ranked:
        summary = "No hay oportunidades analizadas todavia. Ejecuta busqueda IA o analiza productos antes de invertir."
    elif not items:
        best = ranked[0]
        summary = (
            f"No recomiendo invertir ${budget:,.0f} MXN todavia: la mejor oportunidad solo llega a "
            f"{int(best['confidence'] * 100)}% de confianza y no supera la regla minima de 80% con riesgo aceptable."
        )

    return {
        "budget_mxn": budget,
        "allocated_mxn": allocated,
        "reserved_mxn": reserved,
        "expected_profit_mxn": expected_profit,
        "expected_roi": expected_roi,
        "confidence": confidence,
        "verdict": verdict,
        "summary": summary,
        "profile": "conservador",
        "min_confidence": MIN_PURCHASE_CONFIDENCE,
        "scoring_version": SCORING_VERSION,
        "items": items,
        "rejected_or_reserved": rejected_or_reserved,
    }


def score_purchase_candidate(item: dict[str, Any]) -> dict[str, Any]:
    plan = build_investment_plan(item)
    unit_cost = money(number(plan.get("unit_supplier_cost") or item.get("cost")))
    supplier_shipping = money(number(plan.get("supplier_shipping") or item.get("supplier_shipping")))
    suggested_price = money(number(plan.get("suggested_sale_price") or item.get("suggested_price")))
    unit_profit = money(number(item.get("net_profit")) or unit_profit_from_plan(plan))
    confidence = candidate_confidence(item, plan)
    risk_score = purchase_risk_score(item)
    sellability = sellability_score(item)
    holding_cost = unit_cost * (0.018 + (number(item.get("lead_time_days")) / 60))
    risk_penalty = (suggested_price * 0.075 * risk_score) + (unit_cost * 0.025 * risk_score)
    expected_value_unit = money(unit_profit * confidence * sellability - risk_penalty - holding_cost)
    risk_weight = 1 + (risk_score * 2.2)
    rank_score = round((expected_value_unit * confidence * max(sellability, 0.15)) / risk_weight, 4)
    stock = max(0, int(number(item.get("stock"))))
    return {
        "product_id": int(number(item.get("product_id") or item.get("id"))),
        "title": str(item.get("title") or "Producto"),
        "supplier_name": str(item.get("supplier_name") or "Proveedor"),
        "supplier_url": str(plan.get("supplier_url") or item.get("product_url") or item.get("supplier_website") or ""),
        "unit_cost": unit_cost,
        "supplier_shipping": supplier_shipping,
        "suggested_sale_price": suggested_price,
        "unit_profit": unit_profit,
        "expected_value_unit": expected_value_unit,
        "confidence": confidence,
        "evidence_score": evidence_score(item),
        "sellability_score": round(sellability, 2),
        "risk_score": round(risk_score, 2),
        "rank_score": rank_score,
        "stock": stock,
        "net_margin_rate": number(item.get("net_margin_rate")),
        "score": number((item.get("intelligence") or {}).get("potential_score") or item.get("score")),
        "risks": candidate_risks(item),
        "plan": plan,
    }


def candidate_confidence(item: dict[str, Any], plan: dict[str, Any]) -> float:
    potential = clamp(number((item.get("intelligence") or {}).get("potential_score") or item.get("score")) / 100, 0, 1)
    evidence = evidence_score(item)
    margin = clamp((number(item.get("net_margin_rate") or plan.get("net_margin_rate")) - MIN_NET_MARGIN) / 0.25, 0, 1)
    supplier = clamp(number(item.get("supplier_reliability")) / 100, 0, 1)
    demand = demand_component(item)
    availability = clamp(number(item.get("stock")) / 12, 0, 1)
    risk = purchase_risk_score(item)
    confidence = (
        0.10
        + potential * 0.30
        + evidence * 0.25
        + margin * 0.15
        + supplier * 0.10
        + demand * 0.06
        + availability * 0.04
        - risk * 0.14
    )
    if item.get("signal") == "red":
        confidence -= 0.18
    if number(item.get("net_profit")) <= 0:
        confidence -= 0.20
    return round(clamp(confidence, 0.02, 0.98), 2)


def evidence_score(item: dict[str, Any]) -> float:
    evidence = item.get("evidence") or {}
    score_details = evidence.get("score_details") or item.get("score_details") or {}
    total = number(score_details.get("total"))
    if total > 0:
        return round(clamp(total / 100, 0, 1), 2)

    score = 0.30
    if item.get("product_url"):
        score += 0.18
    if item.get("supplier_website"):
        score += 0.10
    if item.get("supplier_contact"):
        score += 0.08
    if truthy(item.get("supplier_invoices")):
        score += 0.12
    if number(item.get("market_competition_price")) > 0:
        score += 0.08
    if item.get("source_type") and item.get("source_type") != "manual":
        score += 0.08
    if number(item.get("stock")) > 0:
        score += 0.05
    if not item.get("product_url") and not evidence:
        score -= 0.15
    return round(clamp(score, 0.05, 0.95), 2)


def purchase_risk_score(item: dict[str, Any]) -> float:
    risks = " ".join(candidate_risks(item)).lower()
    score = 0.06
    weights = {
        "marca": 0.34,
        "restriccion": 0.34,
        "satur": 0.24,
        "factura": 0.20,
        "imagenes": 0.18,
        "stock": 0.16,
        "margen": 0.34,
        "lento": 0.12,
        "devolucion": 0.16,
        "proveedor no mexicano": 0.28,
    }
    for token, weight in weights.items():
        if token in risks:
            score += weight
    if item.get("signal") == "yellow":
        score += 0.12
    elif item.get("signal") == "red":
        score += 0.45
    if str(item.get("competition_level") or "").lower() == "high":
        score += 0.20
    elif str(item.get("competition_level") or "").lower() == "medium":
        score += 0.08
    if number(item.get("stock")) <= 0:
        score += 0.35
    elif number(item.get("stock")) < 3:
        score += 0.12
    if number(item.get("supplier_reliability")) and number(item.get("supplier_reliability")) < 70:
        score += 0.16
    if not truthy(item.get("supplier_invoices")):
        score += 0.10
    if not truthy(item.get("assets_authorized")) or not truthy(item.get("supplier_authorized_assets")):
        score += 0.08
    return clamp(score, 0, 1)


def sellability_score(item: dict[str, Any]) -> float:
    intel = item.get("intelligence") or {}
    category = str(item.get("category") or "").lower()
    category_base = {
        "hubs": 0.78,
        "adaptadores": 0.70,
        "soportes": 0.68,
        "cables": 0.64,
        "cargadores": 0.62,
        "perifericos": 0.58,
        "usb": 0.56,
        "organizadores tech": 0.54,
        "fundas": 0.50,
        "micas": 0.44,
    }.get(category, 0.50)
    competition = str(item.get("competition_level") or intel.get("competition") or "").lower()
    if competition in {"low", "baja"}:
        category_base += 0.10
    elif competition in {"high", "alta"}:
        category_base -= 0.16
    if str(intel.get("return_risk") or "").lower() == "alto":
        category_base -= 0.12
    if number(item.get("stock")) >= 8:
        category_base += 0.05
    return clamp(category_base, 0.18, 0.94)


def demand_component(item: dict[str, Any]) -> float:
    return sellability_score(item)


def suggested_purchase_quantity(candidate: dict[str, Any], budget_left: float) -> int:
    if candidate["confidence"] < MIN_PURCHASE_CONFIDENCE:
        return 0
    if candidate["risk_score"] <= 0.20 and candidate["confidence"] >= 0.90:
        cap = 5
    else:
        cap = 3
    cap = min(cap, max(0, int(candidate["stock"])))
    quantity = 0
    for possible in range(1, cap + 1):
        if total_investment_for(candidate, possible) <= budget_left:
            quantity = possible
    return quantity


def total_investment_for(candidate: dict[str, Any], quantity: int) -> float:
    if quantity <= 0:
        return 0
    return money(candidate["unit_cost"] * quantity + candidate["supplier_shipping"])


def recommendation_for(candidate: dict[str, Any], allocated: bool = False) -> str:
    if candidate["confidence"] >= MIN_PURCHASE_CONFIDENCE and allocated:
        return "comprar_prueba"
    if candidate["confidence"] >= 0.70:
        return "validar_antes"
    if candidate["risk_score"] < 0.45 and candidate["expected_value_unit"] > 0:
        return "monitorear"
    return "rechazar"


def why_buy(candidate: dict[str, Any]) -> str:
    parts = [
        f"confianza {int(candidate['confidence'] * 100)}%",
        f"evidencia {int(candidate['evidence_score'] * 100)}%",
        f"utilidad ajustada por unidad ${candidate['expected_value_unit']:.2f}",
    ]
    if candidate["risk_score"] <= 0.20:
        parts.append("riesgo bajo")
    else:
        parts.append("riesgo controlado")
    return "Compra de prueba por " + ", ".join(parts) + "."


def action_steps(candidate: dict[str, Any], quantity: int) -> list[str]:
    steps = [
        "Confirmar stock hoy con proveedor antes de pagar.",
        "Pedir factura o comprobante y confirmar precio final por escrito.",
        f"Comprar {quantity} unidad(es), no mas, para prueba controlada.",
        f"No pagar mas de ${max_buy_price(candidate):.2f} MXN por unidad.",
        "Publicar o preparar venta con stock conservador despues de validar imagenes.",
    ]
    if candidate["supplier_url"]:
        steps.insert(0, f"Abrir proveedor: {candidate['supplier_url']}")
    return steps


def max_buy_price(candidate: dict[str, Any]) -> float:
    margin_room = max(0, candidate["suggested_sale_price"] * MIN_NET_MARGIN)
    return money(min(candidate["unit_cost"] * 1.08, candidate["unit_cost"] + margin_room * 0.18))


def rejection(candidate: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "product_id": candidate["product_id"],
        "title": candidate["title"],
        "reason": reason,
        "confidence": candidate["confidence"],
        "recommendation": recommendation_for(candidate),
        "risk_score": candidate["risk_score"],
        "expected_value_unit": candidate["expected_value_unit"],
    }


def weighted_confidence(items: list[dict[str, Any]]) -> float:
    total = sum(number(item.get("total_investment")) for item in items)
    if total <= 0:
        return 0
    value = sum(number(item.get("total_investment")) * number(item.get("confidence")) for item in items) / total
    return round(value, 2)


def plan_verdict(allocated: float, reserved: float) -> str:
    if allocated <= 0:
        return "No invertir todavia"
    if reserved > 0:
        return "Invertir parcial"
    return "Invertir presupuesto completo"


def plan_summary(budget: float, allocated: float, reserved: float, expected_profit: float, confidence: float) -> str:
    if allocated <= 0:
        return f"No recomiendo usar ${budget:,.0f} MXN porque no hay oportunidades con confianza >= 80%."
    if reserved > 0:
        return (
            f"Con ${budget:,.0f} recomiendo invertir ${allocated:,.0f}. "
            f"Ganancia esperada: ${expected_profit:,.0f}. Confianza del plan: {int(confidence * 100)}%. "
            f"No uso ${reserved:,.0f} porque no hay suficientes oportunidades con evidencia >= 80%."
        )
    return (
        f"Con ${budget:,.0f} recomiendo invertir todo el presupuesto disponible. "
        f"Ganancia esperada: ${expected_profit:,.0f}. Confianza del plan: {int(confidence * 100)}%."
    )


def unit_profit_from_plan(plan: dict[str, Any]) -> float:
    quantity = max(1, int(number(plan.get("quantity"))))
    return money(number(plan.get("expected_profit")) / quantity)


def candidate_risks(item: dict[str, Any]) -> list[str]:
    intel = item.get("intelligence") or {}
    risks = list(item.get("risks") or []) + list(intel.get("alerts") or [])
    output: list[str] = []
    seen: set[str] = set()
    for risk in risks:
        text = str(risk).strip()
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return output


def number(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def truthy(value: Any) -> bool:
    return value in {True, 1, "1", "true", "True", "yes", "si", "sí"}


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, float(value)))
