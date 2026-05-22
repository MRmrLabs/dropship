from __future__ import annotations

from typing import Any


def supplier_order_route(product: Any, supplier: Any, quantity: int = 1) -> dict[str, Any]:
    url = getattr(product, "product_url", "") or getattr(supplier, "website", "")
    contact = getattr(supplier, "contact", "")
    steps = [
        "Abrir el enlace oficial del proveedor.",
        f"Buscar o confirmar el SKU {getattr(product, 'sku', 'pendiente')}.",
        f"Agregar {quantity} unidad(es) al carrito o cotizacion.",
        "Confirmar precio, stock, factura y tiempo de envio antes de pagar.",
        "Guardar comprobante, folio y fecha estimada.",
    ]
    route_type = "official_url" if url else "contact_supplier"
    if not url and contact:
        steps[0] = f"Contactar al proveedor: {contact}."
    return {
        "type": route_type,
        "url": url,
        "contact": contact,
        "automation_level": "max_safe",
        "requires_final_confirmation": True,
        "steps": steps,
    }
