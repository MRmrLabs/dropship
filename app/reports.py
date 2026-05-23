from __future__ import annotations

import html
import json
from datetime import UTC, datetime
from typing import Any

from app.branding import app_name


def build_investment_plan(item: dict[str, Any]) -> dict[str, Any]:
    intel = item.get("intelligence") or {}
    financials = intel.get("financials") or {}
    quantity = suggested_quantity(item)
    unit_cost = float(item.get("cost") or 0)
    supplier_shipping = float(item.get("supplier_shipping") or 0)
    suggested_price = float(item.get("suggested_price") or 0)
    net_profit = float(item.get("net_profit") or 0)
    total_investment = (unit_cost * quantity) + supplier_shipping
    expected_revenue = suggested_price * quantity
    expected_profit = net_profit * quantity
    roi = expected_profit / total_investment if total_investment else 0
    break_even_units = int((total_investment / max(net_profit, 1)) + 0.999)
    risks = list(item.get("risks") or []) + list(intel.get("alerts") or [])
    steps = [
        "Abrir la URL oficial del proveedor y confirmar que el precio sigue vigente.",
        f"Comprar {quantity} unidad(es) del SKU {item.get('sku') or 'pendiente'} si el stock esta disponible.",
        "Solicitar factura o comprobante y guardar evidencia del pedido.",
        "Publicar o actualizar Mercado Libre con el precio sugerido y stock conservador.",
        "Cuando llegue una venta, comprar/surtir el producto exacto y subir tracking.",
    ]
    if item.get("supplier_invoices") in {0, False}:
        steps.insert(1, "Antes de pagar, pedir confirmacion escrita de factura o comprobante fiscal.")
    if item.get("assets_authorized") in {0, False}:
        steps.insert(1, "Usar fotos propias o confirmar permiso de imagenes antes de publicar.")

    verdict = intel.get("verdict") or "Riesgosa"
    return {
        "product_id": item.get("product_id"),
        "title": item.get("title"),
        "supplier_name": item.get("supplier_name"),
        "supplier_url": item.get("product_url") or item.get("supplier_website"),
        "verdict": verdict,
        "score": intel.get("potential_score", item.get("score", 0)),
        "quantity": quantity,
        "unit_supplier_cost": round(unit_cost, 2),
        "supplier_shipping": round(supplier_shipping, 2),
        "total_investment": round(total_investment, 2),
        "suggested_sale_price": round(suggested_price, 2),
        "expected_revenue": round(expected_revenue, 2),
        "expected_profit": round(expected_profit, 2),
        "net_margin_rate": item.get("net_margin_rate", 0),
        "roi": round(roi, 4),
        "break_even_units": break_even_units,
        "lead_time_days": item.get("lead_time_days", 0),
        "saturation": intel.get("saturation", "Media"),
        "return_risk": intel.get("return_risk", "Medio"),
        "visual_potential": intel.get("visual_potential", "Medio"),
        "risks": unique(risks),
        "steps": steps,
        "financials": financials,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
    }


def suggested_quantity(item: dict[str, Any]) -> int:
    stock = int(item.get("stock") or 0)
    score = int((item.get("intelligence") or {}).get("potential_score") or item.get("score") or 0)
    margin = float(item.get("net_margin_rate") or 0)
    if score >= 80 and margin >= 0.30:
        return max(1, min(stock, 5))
    if score >= 65 and margin >= 0.20:
        return max(1, min(stock, 3))
    return max(1, min(stock, 1))


def plan_to_html(plan: dict[str, Any]) -> str:
    rows = [
        ("Proveedor", plan["supplier_name"]),
        ("URL proveedor", plan["supplier_url"]),
        ("Cantidad sugerida", plan["quantity"]),
        ("Inversion total", money(plan["total_investment"])),
        ("Precio venta sugerido", money(plan["suggested_sale_price"])),
        ("Ganancia esperada", money(plan["expected_profit"])),
        ("Margen neto", pct(plan["net_margin_rate"])),
        ("ROI", pct(plan["roi"])),
        ("Punto de equilibrio", f"{plan['break_even_units']} unidad(es)"),
        ("Llegada estimada", f"{plan['lead_time_days']} dias"),
    ]
    table = "".join(f"<tr><th>{html.escape(str(k))}</th><td>{html.escape(str(v))}</td></tr>" for k, v in rows)
    risks = "".join(f"<li>{html.escape(str(risk))}</li>" for risk in plan.get("risks", [])) or "<li>Sin alertas bloqueantes.</li>"
    steps = "".join(f"<li>{html.escape(str(step))}</li>" for step in plan.get("steps", []))
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>Plan de inversion {html.escape(app_name())}</title>
  <style>
    body {{ font-family: Arial, sans-serif; color: #15181d; margin: 32px; }}
    h1 {{ font-size: 26px; margin-bottom: 6px; }}
    p {{ color: #5f6b7a; }}
    table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
    th, td {{ text-align: left; border-bottom: 1px solid #e4e8ef; padding: 10px; }}
    th {{ width: 32%; color: #5f6b7a; }}
    .badge {{ display: inline-block; padding: 6px 10px; border-radius: 999px; background: #e8f7f1; color: #0f7a5f; font-weight: 700; }}
  </style>
</head>
<body>
  <span class="badge">{html.escape(str(plan["verdict"]))} · Score {html.escape(str(plan["score"]))}/100</span>
  <h1>{html.escape(str(plan["title"]))}</h1>
  <p>Plan generado por {html.escape(app_name())} el {html.escape(str(plan["generated_at"]))}. Validar precio, stock y factura antes de pagar.</p>
  <table>{table}</table>
  <h2>Pasos de ejecucion</h2>
  <ol>{steps}</ol>
  <h2>Riesgos y validaciones</h2>
  <ul>{risks}</ul>
</body>
</html>"""


def plan_to_pdf_bytes(plan: dict[str, Any]) -> bytes:
    lines = [
        f"{app_name()} - Plan de inversion",
        str(plan.get("title") or ""),
        f"Veredicto: {plan.get('verdict')} / Score {plan.get('score')}/100",
        f"Proveedor: {plan.get('supplier_name')}",
        f"URL: {plan.get('supplier_url')}",
        f"Cantidad sugerida: {plan.get('quantity')}",
        f"Inversion total: {money(plan.get('total_investment'))}",
        f"Precio sugerido: {money(plan.get('suggested_sale_price'))}",
        f"Ganancia esperada: {money(plan.get('expected_profit'))}",
        f"Margen: {pct(plan.get('net_margin_rate'))}",
        f"ROI: {pct(plan.get('roi'))}",
        "",
        "Pasos:",
        *[f"- {step}" for step in plan.get("steps", [])],
        "",
        "Riesgos:",
        *[f"- {risk}" for risk in plan.get("risks", [])],
    ]
    return simple_pdf(lines)


def simple_pdf(lines: list[str]) -> bytes:
    escaped_lines = [pdf_escape(line) for line in lines[:42]]
    text = "BT /F1 11 Tf 50 770 Td 14 TL " + " T* ".join(f"({line}) Tj" for line in escaped_lines) + " ET"
    stream = text.encode("latin-1", "replace")
    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n",
        b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
        f"5 0 obj << /Length {len(stream)} >> stream\n".encode("ascii") + stream + b"\nendstream endobj\n",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(output))
        output.extend(obj)
    xref_at = len(output)
    output.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(f"trailer << /Root 1 0 R /Size {len(offsets)} >>\nstartxref\n{xref_at}\n%%EOF\n".encode("ascii"))
    return bytes(output)


def pdf_escape(value: str) -> str:
    clean = str(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return clean.encode("latin-1", "replace").decode("latin-1")


def unique(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return output


def money(value: Any) -> str:
    return f"${float(value or 0):,.2f} MXN"


def pct(value: Any) -> str:
    return f"{float(value or 0) * 100:.1f}%"


def plan_json(plan: dict[str, Any]) -> str:
    return json.dumps(plan, ensure_ascii=True)
