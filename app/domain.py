from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import ceil
from typing import Any


MIN_NET_MARGIN = 0.15
ML_COMMISSION_RATE = 0.145
RETURN_BUFFER_RATE = 0.03
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
    floor_price = (product.cost + product.supplier_shipping) / (
        1 - ML_COMMISSION_RATE - RETURN_BUFFER_RATE - MIN_NET_MARGIN
    )
    suggested_price = max(target_price, floor_price)
    suggested_price = ceil(suggested_price / 5) * 5 - 1

    fees = suggested_price * ML_COMMISSION_RATE
    return_buffer = suggested_price * RETURN_BUFFER_RATE
    total_cost = product.cost + product.supplier_shipping + fees + return_buffer
    net_profit = suggested_price - total_cost
    net_margin_rate = net_profit / suggested_price if suggested_price else 0

    return {
        "suggested_price": money(suggested_price),
        "fees": money(fees),
        "return_buffer": money(return_buffer),
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
        risks.append("Competencia agresiva")
        score -= 20
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
        signal = Signal.YELLOW if score >= 55 else Signal.RED
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
    title = f"{product.title} - Envio rapido Mexico"
    description = (
        f"{product.title}\n\n"
        f"SKU proveedor: {product.sku}\n"
        f"Categoria: {product.category}\n"
        f"Garantia: {product.warranty}\n"
        "Producto evaluado para venta con proveedor mexicano. "
        "Confirma compatibilidad antes de aprobar la publicacion."
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


def build_purchase_checklist() -> list[str]:
    return [
        "Confirmar stock con proveedor antes de pagar",
        "Comprar exactamente el SKU vendido",
        "Solicitar factura o comprobante",
        "Evitar empaques/documentos de otro marketplace",
        "Guardar numero de guia y fecha estimada",
        "Actualizar tracking en la venta",
    ]

