from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urlparse

from app.ai_research import research_products
from app.domain import (
    MIN_NET_MARGIN,
    RISKY_BRANDS,
    Opportunity,
    Supplier,
    SupplierProduct,
    analyze_product,
    calculate_financials,
    money,
)


PIPELINE_STAGES = ["discover", "extract", "verify", "compare", "score", "plan", "monitor"]


@dataclass
class EvidenceScore:
    evidence_type: str
    url: str
    label: str
    source_quality_score: float
    directness_score: float
    freshness_score: float
    field_supported: list[str] = field(default_factory=list)


@dataclass
class OpportunityPlan:
    product_id: int
    product_title: str
    supplier_name: str
    supplier_url: str
    marketplace_url: str
    recommendation: str
    recommendation_label: str
    expected_profit: float
    expected_profit_adjusted: float
    opportunity_rank_score: float
    confidence_score: float
    evidence_score: float
    demand_score: float
    competition_score: float
    supplier_score: float
    risk_score: float
    suggested_price: float
    net_margin_rate: float
    net_profit: float
    validation_tasks: list[str]
    action_steps: list[str]
    evidence_urls: list[str]
    evidence_items: list[dict[str, Any]]
    risks: list[str]
    decision_summary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_opportunity_pipeline(query: str | None = None) -> dict[str, Any]:
    result = research_products(query)
    candidates = result.get("candidates", [])
    result["pipeline_stages"] = PIPELINE_STAGES
    result["candidate_scores"] = [score_candidate(candidate) for candidate in candidates]
    return result


def score_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    cost = number(candidate.get("estimated_cost_mxn"))
    shipping = number(candidate.get("estimated_shipping_mxn"))
    market_price = number(candidate.get("suggested_sale_price_mxn") or candidate.get("estimated_market_price_mxn"))
    supplier = Supplier(
        id=None,
        name=str(candidate.get("supplier_name") or "Proveedor IA"),
        country="Mexico",
        website=str(candidate.get("supplier_website") or first_url(candidate)),
        contact=str(candidate.get("supplier_contact") or "Validar contacto"),
        terms="Proveedor encontrado por IA; validar condiciones",
        shipping_type="Validar envio nacional",
        reliability=int(normalized_confidence(candidate) * 100),
        invoices=bool(candidate.get("invoice_evidence")),
        authorized_assets=False,
    )
    product = make_supplier_product(
        id=0,
        supplier_id=0,
        sku="CANDIDATE",
        title=str(candidate.get("product_title") or "Producto candidato"),
        brand=str(candidate.get("brand") or "Generico"),
        category=str(candidate.get("category") or "perifericos").lower(),
        cost=cost,
        supplier_shipping=shipping,
        stock=stock_from_signal(str(candidate.get("stock_signal") or "desconocido")),
        warranty=str(candidate.get("warranty") or "Validar con proveedor"),
        lead_time_days=int(candidate.get("lead_time_days") or 3),
        image_url="",
        product_url=str(candidate.get("supplier_product_url") or first_url(candidate)),
        assets_authorized=False,
        market_competition_price=market_price,
        competition_level=competition_level_from_candidate(candidate),
    )
    opportunity = analyze_product(product, supplier)
    evidence = evaluate_evidence(candidate)
    demand_score = demand_model(candidate=candidate, product=product, evidence=evidence)
    competition_score = competition_model(product=product, evidence=evidence)
    supplier_score = supplier_reliability_model(supplier=supplier, evidence=evidence)
    policy_risk = policy_risk_model(product=product, supplier=supplier)
    expected_adjusted = expected_value_model(
        opportunity=opportunity,
        evidence_score=evidence["evidence_score"],
        demand_score=demand_score,
        competition_score=competition_score,
        supplier_score=supplier_score,
        policy_risk_score=policy_risk,
    )
    expected_adjusted = money(expected_adjusted - price_position_penalty(product, opportunity))
    recommendation = recommendation_for(
        opportunity=opportunity,
        evidence=evidence,
        demand_score=demand_score,
        competition_score=competition_score,
        supplier_score=supplier_score,
        policy_risk_score=policy_risk,
        expected_profit_adjusted=expected_adjusted,
    )
    return {
        "recommendation": recommendation,
        "expected_profit_adjusted": expected_adjusted,
        "opportunity_rank_score": opportunity_rank_score(
            expected_adjusted,
            demand_score,
            evidence["evidence_score"],
            opportunity_risk_score(opportunity),
            competition_score,
        ),
        "evidence_score": evidence["evidence_score"],
        "demand_score": demand_score,
        "competition_score": competition_score,
        "supplier_score": supplier_score,
        "risk_score": opportunity_risk_score(opportunity),
        "validation_tasks": validation_tasks_for(opportunity, evidence, recommendation),
        "evidence_items": evidence["items"],
    }


def build_opportunity_plan(
    product: SupplierProduct,
    supplier: Supplier,
    opportunity: Opportunity | None = None,
    evidence_items: list[dict[str, Any]] | None = None,
    candidate: dict[str, Any] | None = None,
) -> OpportunityPlan:
    opportunity = opportunity or analyze_product(product, supplier)
    evidence = evaluate_evidence(candidate or {}, evidence_items=evidence_items, product=product, supplier=supplier)
    demand_score = demand_model(candidate=candidate or {}, product=product, evidence=evidence)
    competition_score = competition_model(product=product, evidence=evidence)
    supplier_score = supplier_reliability_model(supplier=supplier, evidence=evidence)
    policy_risk = policy_risk_model(product=product, supplier=supplier)
    expected_adjusted = expected_value_model(
        opportunity=opportunity,
        evidence_score=evidence["evidence_score"],
        demand_score=demand_score,
        competition_score=competition_score,
        supplier_score=supplier_score,
        policy_risk_score=policy_risk,
    )
    expected_adjusted = money(expected_adjusted - price_position_penalty(product, opportunity))
    recommendation = recommendation_for(
        opportunity=opportunity,
        evidence=evidence,
        demand_score=demand_score,
        competition_score=competition_score,
        supplier_score=supplier_score,
        policy_risk_score=policy_risk,
        expected_profit_adjusted=expected_adjusted,
    )
    validation_tasks = validation_tasks_for(opportunity, evidence, recommendation)
    evidence_urls = [item["url"] for item in evidence["items"] if item.get("url")]
    marketplace_url = first_evidence_url(evidence["items"], "marketplace_comparable")
    supplier_url = (
        first_evidence_url(evidence["items"], "supplier_product_page")
        or first_evidence_url(evidence["items"], "supplier_catalog")
        or product.product_url
        or supplier.website
    )
    return OpportunityPlan(
        product_id=int(product.id or 0),
        product_title=product.title,
        supplier_name=supplier.name,
        supplier_url=supplier_url,
        marketplace_url=marketplace_url,
        recommendation=recommendation,
        recommendation_label=recommendation_label(recommendation),
        expected_profit=opportunity_expected_profit(opportunity),
        expected_profit_adjusted=expected_adjusted,
        opportunity_rank_score=opportunity_rank_score(
            expected_adjusted,
            demand_score,
            evidence["evidence_score"],
            opportunity_risk_score(opportunity),
            competition_score,
        ),
        confidence_score=opportunity_confidence_score(opportunity, evidence),
        evidence_score=evidence["evidence_score"],
        demand_score=demand_score,
        competition_score=competition_score,
        supplier_score=supplier_score,
        risk_score=max(opportunity_risk_score(opportunity), policy_risk),
        suggested_price=opportunity.suggested_price,
        net_margin_rate=opportunity.net_margin_rate,
        net_profit=opportunity.net_profit,
        validation_tasks=validation_tasks,
        action_steps=action_steps_for(recommendation, validation_tasks),
        evidence_urls=evidence_urls,
        evidence_items=evidence["items"],
        risks=opportunity.risks,
        decision_summary=decision_summary_for(recommendation, opportunity, evidence, demand_score, expected_adjusted),
    )


def rank_opportunities(plans: list[OpportunityPlan | dict[str, Any]]) -> list[dict[str, Any]]:
    output = [plan.to_dict() if isinstance(plan, OpportunityPlan) else dict(plan) for plan in plans]
    return sorted(output, key=lambda item: item.get("opportunity_rank_score", 0), reverse=True)


def evaluate_evidence(
    candidate: dict[str, Any] | None,
    evidence_items: list[dict[str, Any]] | None = None,
    product: SupplierProduct | None = None,
    supplier: Supplier | None = None,
) -> dict[str, Any]:
    raw_items = raw_evidence_items(candidate or {}, evidence_items or [], product, supplier)
    scored = [classify_evidence_item(item) for item in raw_items]
    unique = dedupe_evidence(scored)
    has_supplier_direct = any(
        item.evidence_type in {"supplier_product_page", "supplier_catalog"} for item in unique
    )
    has_marketplace_comparable = any(item.evidence_type == "marketplace_comparable" for item in unique)
    has_supplier_contact = any(item.evidence_type == "supplier_contact_or_invoice" for item in unique)
    if not unique:
        evidence_score = 0.05
    else:
        weighted = sum(
            item.source_quality_score * 0.45 + item.directness_score * 0.4 + item.freshness_score * 0.15
            for item in unique
        ) / len(unique)
        coverage_bonus = (
            (0.12 if has_supplier_direct else 0)
            + (0.12 if has_marketplace_comparable else 0)
            + (0.08 if has_supplier_contact else 0)
        )
        evidence_score = clamp(weighted + coverage_bonus, 0.05, 0.98)
    return {
        "evidence_score": round(evidence_score, 2),
        "has_supplier_direct": has_supplier_direct,
        "has_marketplace_comparable": has_marketplace_comparable,
        "has_supplier_contact": has_supplier_contact,
        "items": [asdict(item) for item in unique],
    }


def demand_model(candidate: dict[str, Any], product: SupplierProduct, evidence: dict[str, Any]) -> float:
    base_by_category = {
        "hubs": 67,
        "soportes": 62,
        "cables": 56,
        "cargadores": 55,
        "adaptadores": 58,
        "perifericos": 52,
        "organizadores tech": 50,
        "usb": 48,
        "fundas": 40,
        "micas": 34,
    }
    score = base_by_category.get(product.category.lower(), 42)
    buyer_reason = str(candidate.get("buyer_reason") or "")
    if len(buyer_reason) >= 35:
        score += 8
    if evidence.get("has_marketplace_comparable"):
        score += 10
    if product.competition_level.lower() == "low":
        score += 8
    elif product.competition_level.lower() == "high":
        score -= 14
    if product.market_competition_price > 799:
        score -= 8
    if product.stock < 5:
        score -= 10
    return round(clamp(score, 0, 100), 2)


def competition_model(product: SupplierProduct, evidence: dict[str, Any]) -> float:
    score_by_level = {"low": 22, "medium": 48, "high": 78}
    score = score_by_level.get(product.competition_level.lower(), 55)
    if product.brand.lower() in RISKY_BRANDS:
        score += 12
    if not evidence.get("has_marketplace_comparable"):
        score += 8
    return round(clamp(score, 0, 100), 2)


def supplier_reliability_model(supplier: Supplier, evidence: dict[str, Any]) -> float:
    score = float(supplier.reliability)
    if supplier.invoices:
        score += 8
    if supplier.authorized_assets:
        score += 6
    if evidence.get("has_supplier_direct"):
        score += 8
    if evidence.get("has_supplier_contact"):
        score += 6
    if supplier.country.lower() not in {"mexico", "méxico", "mx"}:
        score -= 30
    return round(clamp(score, 0, 100), 2)


def policy_risk_model(product: SupplierProduct, supplier: Supplier) -> float:
    score = 0
    if product.brand.lower() in RISKY_BRANDS:
        score += 40
    if not product.assets_authorized:
        score += 25
    if not supplier.authorized_assets:
        score += 20
    if not supplier.invoices:
        score += 12
    return round(clamp(score, 0, 100), 2)


def expected_value_model(
    opportunity: Opportunity,
    evidence_score: float,
    demand_score: float,
    competition_score: float,
    supplier_score: float,
    policy_risk_score: float,
) -> float:
    financials = {
        "suggested_price": opportunity.suggested_price,
        "net_profit": opportunity.net_profit,
    }
    sale_probability = clamp(0.15 + demand_score / 140 - competition_score / 260, 0.05, 0.88)
    fulfillment_success_probability = clamp(0.25 + supplier_score / 130 + evidence_score * 0.18, 0.08, 0.96)
    expected_return_cost = financials["suggested_price"] * 0.03 * (1 + policy_risk_score / 120)
    support_cost = 10 + opportunity_risk_score(opportunity) * 0.25
    capital_cost = max(financials["suggested_price"] - financials["net_profit"], 0) * 0.012
    policy_risk_penalty = financials["suggested_price"] * policy_risk_score / 100 * 0.06
    competition_penalty = financials["suggested_price"] * competition_score / 100 * 0.035
    value = (
        financials["net_profit"] * sale_probability * fulfillment_success_probability * evidence_score
        - expected_return_cost
        - support_cost
        - capital_cost
        - policy_risk_penalty
        - competition_penalty
    )
    return money(value)


def price_position_penalty(product: SupplierProduct, opportunity: Opportunity) -> float:
    market_price = float(product.market_competition_price or 0)
    if market_price <= 0:
        return 0
    premium = max(0, opportunity.suggested_price - market_price * 1.05)
    return premium * 0.18


def opportunity_rank_score(
    expected_profit_adjusted: float,
    demand_score: float,
    evidence_score: float,
    risk_score: float,
    competition_score: float,
) -> float:
    return round(
        expected_profit_adjusted
        + demand_score * 0.35
        + evidence_score * 35
        - risk_score * 0.22
        - competition_score * 0.18,
        2,
    )


def recommendation_for(
    opportunity: Opportunity,
    evidence: dict[str, Any],
    demand_score: float,
    competition_score: float,
    supplier_score: float,
    policy_risk_score: float,
    expected_profit_adjusted: float,
) -> str:
    if opportunity.net_margin_rate < MIN_NET_MARGIN:
        return "reject"
    if (demand_score < 38 or competition_score >= 75) and expected_profit_adjusted > -60:
        return "monitor"
    if expected_profit_adjusted < -20:
        return "reject"
    if policy_risk_score >= 45 or any("Marca con posible restriccion" in risk for risk in opportunity.risks):
        return "validate_supplier"
    if not evidence.get("has_supplier_direct") or not evidence.get("has_marketplace_comparable"):
        return "validate_supplier"
    if demand_score < 38 or competition_score >= 75:
        return "monitor"
    if (
        expected_profit_adjusted >= 6
        and evidence["evidence_score"] >= 0.62
        and opportunity_confidence_score(opportunity, evidence) >= 0.55
        and supplier_score >= 65
        and opportunity_risk_score(opportunity) <= 55
    ):
        return "buy_test"
    if expected_profit_adjusted > 0:
        return "monitor"
    return "reject"


def validation_tasks_for(opportunity: Opportunity, evidence: dict[str, Any], recommendation: str) -> list[str]:
    tasks = list(getattr(opportunity, "required_validations", []))
    if not evidence.get("has_supplier_direct"):
        tasks.append("Conseguir URL directa o catalogo del proveedor")
    if not evidence.get("has_marketplace_comparable"):
        tasks.append("Conseguir comparable en Mercado Libre o retail")
    if not evidence.get("has_supplier_contact"):
        tasks.append("Validar contacto, factura o RFC del proveedor")
    if recommendation == "buy_test":
        tasks.append("Confirmar precio y stock para prueba de 3 a 5 unidades")
    return dedupe(tasks)


def action_steps_for(recommendation: str, validation_tasks: list[str]) -> list[str]:
    if recommendation == "buy_test":
        return [
            "Contactar proveedor con guion de validacion y pedir precio final por 3 a 5 unidades.",
            "Confirmar factura, stock, tiempo de surtido y permiso de imagenes.",
            "Crear borrador Mercado Libre solo despues de confirmar los datos criticos.",
        ]
    if recommendation == "validate_supplier":
        return [
            "Completar validaciones pendientes antes de considerar compra.",
            "Guardar URLs de proveedor, comparable y evidencia de factura/stock.",
            "Recalcular la oportunidad despues de validar costo, precio y stock.",
        ]
    if recommendation == "monitor":
        return [
            "Monitorear precio proveedor y comparable Mercado Libre antes de operar.",
            "Revisar si baja competencia o mejora margen esperado.",
            "Reevaluar con nuevo snapshot antes de crear borrador.",
        ]
    return [
        "Rechazar o archivar la oportunidad.",
        "No gastar tiempo operativo salvo que cambien precio, stock o evidencia.",
    ]


def decision_summary_for(
    recommendation: str,
    opportunity: Opportunity,
    evidence: dict[str, Any],
    demand_score: float,
    expected_profit_adjusted: float,
) -> str:
    label = recommendation_label(recommendation)
    if recommendation == "buy_test":
        return (
            f"{label}: utilidad ajustada {money(expected_profit_adjusted)} MXN, "
            f"demanda {int(demand_score)}/100 y evidencia {int(evidence['evidence_score'] * 100)}%."
        )
    if recommendation == "validate_supplier":
        return (
            f"{label}: la economia puede servir, pero faltan fuentes criticas para operar sin inventar datos."
        )
    if recommendation == "monitor":
        return (
            f"{label}: no conviene operar todavia; vigila precio, competencia o demanda antes de invertir tiempo."
        )
    return f"{label}: margen, riesgo o evidencia no justifican avanzar."


def recommendation_label(recommendation: str) -> str:
    return {
        "buy_test": "Comprar prueba controlada",
        "validate_supplier": "Validar proveedor",
        "monitor": "Monitorear",
        "reject": "Rechazar",
    }.get(recommendation, recommendation)


def raw_evidence_items(
    candidate: dict[str, Any],
    evidence_items: list[dict[str, Any]],
    product: SupplierProduct | None,
    supplier: Supplier | None,
) -> list[dict[str, str]]:
    raw: list[dict[str, str]] = []
    for item in evidence_items:
        raw.append(
            {
                "evidence_type": str(item.get("evidence_type") or ""),
                "url": str(item.get("url") or ""),
                "label": str(item.get("label") or item.get("evidence_type") or "Fuente"),
            }
        )
    candidate_sources = [
        ("supplier_product_url", candidate.get("supplier_product_url"), "Producto proveedor"),
        ("marketplace_comparable_url", candidate.get("marketplace_comparable_url"), "Comparable marketplace"),
        ("invoice_evidence", candidate.get("invoice_evidence"), "Factura/RFC/contacto"),
        ("stock_evidence", candidate.get("stock_evidence"), "Stock/disponibilidad"),
    ]
    for evidence_type, url, label in candidate_sources:
        if url:
            raw.append({"evidence_type": evidence_type, "url": str(url), "label": label})
    for url in candidate.get("source_urls") or []:
        raw.append({"evidence_type": "source_url", "url": str(url), "label": "Fuente IA"})
    if product and product.product_url:
        raw.append({"evidence_type": "supplier_product_url", "url": product.product_url, "label": "Producto proveedor"})
    if supplier and supplier.website:
        raw.append({"evidence_type": "supplier_website", "url": supplier.website, "label": "Proveedor"})
    return raw


def classify_evidence_item(item: dict[str, str]) -> EvidenceScore:
    url = str(item.get("url") or "").strip()
    label = str(item.get("label") or "Fuente")
    original_type = str(item.get("evidence_type") or "")
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    text = f"{original_type} {label} {url}".lower()
    evidence_type = "weak_source"
    fields: list[str] = []
    quality = 0.35
    directness = 0.25
    freshness = 0.55

    if any(domain in host for domain in ("mercadolibre", "amazon.com.mx", "walmart", "cyberpuerta")):
        evidence_type = "marketplace_comparable"
        fields = ["precio mercado", "demanda"]
        quality = 0.72
        directness = 0.7
    elif "invoice" in original_type or any(token in text for token in ("factura", "rfc", "contacto", "contact")):
        evidence_type = "supplier_contact_or_invoice"
        fields = ["proveedor", "factura"]
        quality = 0.68
        directness = 0.62
    elif "stock" in original_type or any(token in text for token in ("stock", "disponibilidad", "inventario")):
        evidence_type = "stock_or_price_signal"
        fields = ["stock", "costo"]
        quality = 0.58
        directness = 0.55
    elif any(token in path for token in ("producto", "product", "item", "sku", "p/")):
        evidence_type = "supplier_product_page"
        fields = ["costo", "proveedor"]
        quality = 0.78
        directness = 0.82
    elif any(token in path for token in ("catalog", "catalogo", "productos", "tienda")):
        evidence_type = "supplier_catalog"
        fields = ["proveedor", "costo"]
        quality = 0.64
        directness = 0.58
    elif host:
        evidence_type = "weak_source"
        fields = ["proveedor"]
        quality = 0.38
        directness = 0.28

    return EvidenceScore(
        evidence_type=evidence_type,
        url=url,
        label=label,
        source_quality_score=round(quality, 2),
        directness_score=round(directness, 2),
        freshness_score=round(freshness, 2),
        field_supported=fields,
    )


def dedupe_evidence(items: list[EvidenceScore]) -> list[EvidenceScore]:
    output: list[EvidenceScore] = []
    seen: set[str] = set()
    for item in items:
        key = item.url.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def first_evidence_url(items: list[dict[str, Any]], evidence_type: str) -> str:
    for item in items:
        if item.get("evidence_type") == evidence_type and item.get("url"):
            return str(item["url"])
    return ""


def first_url(candidate: dict[str, Any]) -> str:
    urls = candidate.get("source_urls") or []
    if isinstance(urls, list) and urls:
        return str(urls[0])
    return str(candidate.get("supplier_website") or "")


def make_supplier_product(**values: Any) -> SupplierProduct:
    fields = SupplierProduct.__dataclass_fields__
    return SupplierProduct(**{key: value for key, value in values.items() if key in fields})


def opportunity_expected_profit(opportunity: Opportunity) -> float:
    return float(getattr(opportunity, "expected_profit", opportunity.net_profit))


def opportunity_risk_score(opportunity: Opportunity) -> float:
    return float(getattr(opportunity, "risk_score", max(0, 100 - opportunity.score)))


def opportunity_confidence_score(opportunity: Opportunity, evidence: dict[str, Any]) -> float:
    return float(getattr(opportunity, "confidence_score", evidence.get("evidence_score", 0.5)))


def number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def normalized_confidence(candidate: dict[str, Any]) -> float:
    value = number(candidate.get("confidence") or 0.35)
    if value > 1:
        value = value / 100
    return clamp(value, 0.05, 0.98)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def stock_from_signal(signal: str) -> int:
    return {"alto": 30, "medio": 12, "bajo": 3}.get(signal.lower(), 1)


def competition_level_from_candidate(candidate: dict[str, Any]) -> str:
    flags = " ".join(str(flag).lower() for flag in candidate.get("risk_flags") or [])
    if "competencia alta" in flags or "satur" in flags:
        return "high"
    if candidate.get("marketplace_comparable_url"):
        return "medium"
    return "medium"


def dedupe(items: list[str]) -> list[str]:
    output = []
    seen = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output
