from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import ceil
import os
import re
from typing import Any


MIN_NET_MARGIN = 0.15
ML_COMMISSION_RATE = float(os.environ.get("ML_COMMISSION_RATE", "0.145"))
IVA_RATE = float(os.environ.get("MX_IVA_RATE", "0.16"))
ADS_RATE = float(os.environ.get("ESTIMATED_ADS_RATE", "0.06"))
RETURN_BUFFER_RATE = float(os.environ.get("RETURN_BUFFER_RATE", "0.03"))
STRIPE_FEE_RATE = float(os.environ.get("STRIPE_FEE_RATE", "0.036"))
STRIPE_FIXED_FEE = float(os.environ.get("STRIPE_FIXED_FEE_MXN", "3.00"))
PLATFORM_COMMISSION_RATE = float(os.environ.get("STRIPE_PLATFORM_COMMISSION_RATE", "0.10"))
SAFE_CATEGORIES = {
    "cables",
    "cargadores",
    "adaptadores",
    "soportes",
    "perifericos",
    "hubs",
    "fundas",
    "micas",
    "usb",
    "organizadores tech",
}
RISKY_BRANDS = {
    "apple",
    "samsung",
    "xiaomi",
    "sony",
    "huawei",
    "nintendo",
    "playstation",
    "dell",
    "hp",
    "lenovo",
}


class Signal(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


class ListingStatus(str, Enum):
    DRAFT = "draft"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    PUBLISHED = "published"
    PAUSED = "paused"
    REJECTED = "rejected"


class PurchaseOrderStatus(str, Enum):
    NEW_SALE = "new_sale"
    PURCHASE_NEEDED = "purchase_needed"
    ORDERED = "ordered"
    TRACKING_ADDED = "tracking_added"
    DELIVERED = "delivered"
    ISSUE = "issue"


@dataclass
class Supplier:
    id: int | None
    name: str
    country: str
    website: str
    contact: str
    terms: str
    shipping_type: str
    reliability: int
    invoices: bool
    authorized_assets: bool


@dataclass
class SupplierProduct:
    id: int | None
    supplier_id: int
    sku: str
    title: str
    brand: str
    category: str
    cost: float
    supplier_shipping: float
    stock: int
    warranty: str
    lead_time_days: int
    image_url: str
    product_url: str
    assets_authorized: bool
    market_competition_price: float
    competition_level: str


@dataclass
class Opportunity:
    product_id: int
    platform: str
    suggested_price: float
    net_margin_rate: float
    net_profit: float
    score: int
    signal: Signal
    risks: list[str] = field(default_factory=list)


def money(value: float) -> float:
    return round(float(value) + 0.00001, 2)


def calculate_financials(product: SupplierProduct) -> dict[str, float]:
    target_price = product.market_competition_price * 0.98
    variable_cost_rate = (
        ML_COMMISSION_RATE
        + IVA_RATE
        + ADS_RATE
        + RETURN_BUFFER_RATE
        + STRIPE_FEE_RATE
        + PLATFORM_COMMISSION_RATE
        + MIN_NET_MARGIN
    )
    floor_price = (product.cost + product.supplier_shipping + STRIPE_FIXED_FEE) / (1 - variable_cost_rate)
    suggested_price = max(target_price, floor_price)
    suggested_price = ceil(suggested_price / 5) * 5

    marketplace_fee = suggested_price * ML_COMMISSION_RATE
    iva = suggested_price * IVA_RATE
    ads = suggested_price * ADS_RATE
    return_buffer = suggested_price * RETURN_BUFFER_RATE
    stripe_fee = suggested_price * STRIPE_FEE_RATE + STRIPE_FIXED_FEE
    platform_commission = suggested_price * PLATFORM_COMMISSION_RATE
    total_cost = (
        product.cost
        + product.supplier_shipping
        + marketplace_fee
        + iva
        + ads
        + return_buffer
        + stripe_fee
        + platform_commission
    )
    net_profit = suggested_price - total_cost
    net_margin_rate = net_profit / suggested_price if suggested_price else 0

    return {
        "suggested_price": money(suggested_price),
        "marketplace_fee": money(marketplace_fee),
        "fees": money(marketplace_fee),
        "iva": money(iva),
        "ads": money(ads),
        "return_buffer": money(return_buffer),
        "stripe_fee": money(stripe_fee),
        "platform_commission": money(platform_commission),
        "total_cost": money(total_cost),
        "net_profit": money(net_profit),
        "net_margin_rate": round(net_margin_rate, 4),
    }


def analyze_product(product: SupplierProduct, supplier: Supplier) -> Opportunity:
    financials = calculate_financials(product)
    risks: list[str] = []
    score = 100

    if supplier.country.lower() not in {"mexico", "méxico", "mx"}:
        risks.append("Proveedor no mexicano")
        score -= 35
    if supplier.reliability < 70:
        risks.append("Confiabilidad de proveedor baja")
        score -= 25
    if not supplier.invoices:
        risks.append("Proveedor sin factura clara")
        score -= 20
    if product.stock < 5:
        risks.append("Stock bajo o incierto")
        score -= 35
    if product.category.lower() not in SAFE_CATEGORIES:
        risks.append("Categoria fuera del foco inicial")
        score -= 20
    if product.brand.lower() in RISKY_BRANDS:
        risks.append("Marca con posible restriccion o garantia sensible")
        score -= 30
    if not product.assets_authorized or not supplier.authorized_assets:
        risks.append("Imagenes/textos sin autorizacion confirmada")
        score -= 30
    if product.competition_level.lower() == "high":
        risks.append("Producto saturado en Mercado Libre")
        score -= 25
    if financials["net_margin_rate"] < MIN_NET_MARGIN:
        risks.append("Margen neto menor a 15%")
        score -= 45
    if product.lead_time_days > 3:
        risks.append("Tiempo de surtido alto")
        score -= 15

    score = max(0, min(100, score))
    if financials["net_margin_rate"] < MIN_NET_MARGIN or product.stock <= 0:
        signal = Signal.RED
    elif risks:
        signal = Signal.YELLOW if score >= 45 else Signal.RED
    else:
        signal = Signal.GREEN

    return Opportunity(
        product_id=product.id or 0,
        platform="mercado_libre_mx",
        suggested_price=financials["suggested_price"],
        net_margin_rate=financials["net_margin_rate"],
        net_profit=financials["net_profit"],
        score=score,
        signal=signal,
        risks=risks,
    )


def build_listing_draft(product: SupplierProduct, opportunity: Opportunity) -> dict[str, Any]:
    status = ListingStatus.DRAFT if opportunity.signal == Signal.GREEN else ListingStatus.NEEDS_REVIEW
    title = optimize_marketplace_title(product.title, product.brand)
    description = (
        f"{product.title}\n\n"
        f"SKU proveedor: {product.sku}\n"
        f"Categoria: {product.category}\n"
        f"Garantia: {product.warranty}\n"
        "Producto evaluado para venta con proveedor mexicano. "
        "Confirma compatibilidad, stock y derechos de imagen antes de publicar."
    )
    return {
        "product_id": product.id,
        "title": title[:60],
        "description": description,
        "price": opportunity.suggested_price,
        "stock": min(product.stock, 10),
        "status": status.value,
        "attributes": {
            "seller_sku": product.sku,
            "brand": product.brand,
            "category": product.category,
            "warranty": product.warranty,
        },
        "image_url": product.image_url,
    }


def optimize_marketplace_title(title: str, brand: str = "") -> str:
    cleaned = re.sub(r"\s+", " ", title).strip()
    cleaned = re.sub(r"\b(al mayoreo|mayoreo|dropshipping|promocion|oferta)\b", "", cleaned, flags=re.I)
    cleaned = cleaned.replace("  ", " ").strip(" -")
    if brand and brand.lower() not in {"generico", "genérico"} and brand.lower() not in cleaned.lower():
        cleaned = f"{cleaned} {brand}"
    replacements = {
        "usb c": "USB-C",
        "tipo c": "Tipo C",
        "hdmi": "HDMI",
        "laptop": "Laptop",
    }
    for old, new in replacements.items():
        cleaned = re.sub(old, new, cleaned, flags=re.I)
    return cleaned[:60].strip()


def product_intelligence(product: SupplierProduct, supplier: Supplier, opportunity: Opportunity) -> dict[str, Any]:
    financials = calculate_financials(product)
    saturation = "Baja"
    if product.competition_level.lower() == "high":
        saturation = "Alta"
    elif product.competition_level.lower() == "medium":
        saturation = "Media"

    return_risk = "Bajo"
    if product.category.lower() in {"cargadores", "perifericos"} or product.brand.lower() in RISKY_BRANDS:
        return_risk = "Medio"
    if product.stock < 5 or product.lead_time_days > 5:
        return_risk = "Alto"

    visual = "Medio"
    if product.category.lower() in {"soportes", "organizadores tech", "hubs", "fundas", "micas"}:
        visual = "Alto"
    if not product.image_url and not product.assets_authorized:
        visual = "Bajo"

    potential = opportunity.score
    if financials["net_margin_rate"] >= 0.35:
        potential += 8
    if saturation == "Baja":
        potential += 8
    if visual == "Alto":
        potential += 6
    if return_risk == "Alto":
        potential -= 12
    potential = max(0, min(100, potential))

    if potential >= 75 and opportunity.signal == Signal.GREEN:
        verdict = "Recomendada"
        verdict_signal = "green"
    elif potential < 45 or saturation == "Alta":
        verdict = "Saturada"
        verdict_signal = "red"
    else:
        verdict = "Riesgosa"
        verdict_signal = "yellow"

    alerts: list[str] = []
    if saturation == "Alta":
        alerts.append("Producto muy saturado")
    if financials["net_margin_rate"] < MIN_NET_MARGIN:
        alerts.append("Margen insuficiente")
    if product.lead_time_days > 3:
        alerts.append("Envio de proveedor lento")
    if not product.assets_authorized or not supplier.authorized_assets:
        alerts.append("Imagenes pendientes de validar")
    if return_risk == "Alto":
        alerts.append("Riesgo de devolucion alto")

    return {
        "potential_score": potential,
        "verdict": verdict,
        "verdict_signal": verdict_signal,
        "saturation": saturation,
        "competition": saturation,
        "return_risk": return_risk,
        "visual_potential": visual,
        "auto_action": auto_action(opportunity, financials, saturation, return_risk),
        "alerts": alerts,
        "financials": financials,
    }


def auto_action(
    opportunity: Opportunity,
    financials: dict[str, float],
    saturation: str,
    return_risk: str,
) -> str:
    if opportunity.signal == Signal.RED or financials["net_margin_rate"] < MIN_NET_MARGIN:
        return "rechazar"
    if saturation == "Alta" or return_risk == "Alto":
        return "revision"
    if financials["net_margin_rate"] >= 0.28 and opportunity.score >= 75:
        return "aprobar"
    return "revision"


def build_purchase_checklist() -> list[str]:
    return [
        "Confirmar stock con proveedor antes de pagar",
        "Comprar exactamente el SKU vendido",
        "Solicitar factura o comprobante",
        "Evitar empaques/documentos de otro marketplace",
        "Guardar numero de guia y fecha estimada",
        "Actualizar tracking en la venta",
    ]
