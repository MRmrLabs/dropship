from __future__ import annotations

import json
import mimetypes
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.domain import (
    ListingStatus,
    PurchaseOrderStatus,
    analyze_product,
    build_listing_draft,
    build_purchase_checklist,
)
from app.meli_auth import build_authorization_url, exchange_code, fetch_me, integration_status
from app.storage import (
    ROOT,
    fetch_listing_drafts,
    fetch_opportunities,
    fetch_products,
    fetch_purchase_orders,
    fetch_suppliers,
    get_product_and_supplier,
    init_db,
    insert_listing_draft,
    insert_purchase_order,
    seed_demo_data,
    update_listing_status,
    upsert_opportunity,
)


WEB_DIR = ROOT / "web"


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class Handler(BaseHTTPRequestHandler):
    server_version = "DropshippingTechMX/0.1"

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                self.handle_api_get(parsed.path)
                return
            if parsed.path == "/auth/meli/callback":
                self.handle_meli_callback(parsed)
                return
            self.serve_static(parsed.path)
        except ApiError as exc:
            self.send_json({"error": exc.message}, exc.status)
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            self.handle_api_post(parsed.path)
        except ApiError as exc:
            self.send_json({"error": exc.message}, exc.status)
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)

    def do_PATCH(self) -> None:
        try:
            parsed = urlparse(self.path)
            self.handle_api_patch(parsed.path)
        except ApiError as exc:
            self.send_json({"error": exc.message}, exc.status)
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)

    def handle_api_get(self, path: str) -> None:
        if path == "/api/health":
            self.send_json({"ok": True, "marketplace": "mercado_libre_mx"})
        elif path == "/api/suppliers":
            self.send_json(fetch_suppliers())
        elif path == "/api/products":
            self.send_json(fetch_products())
        elif path == "/api/opportunities":
            self.send_json(fetch_opportunities())
        elif path == "/api/listing-drafts":
            self.send_json(fetch_listing_drafts())
        elif path == "/api/purchase-orders":
            self.send_json(fetch_purchase_orders())
        elif path == "/api/integrations/meli/status":
            self.send_json(integration_status())
        elif path == "/api/integrations/meli/auth-url":
            self.send_json({"url": build_authorization_url()})
        elif path == "/api/integrations/meli/me":
            self.send_json(fetch_me())
        else:
            raise ApiError(404, "Ruta API no encontrada")

    def handle_api_post(self, path: str) -> None:
        if path == "/api/analyze":
            self.analyze_all()
        elif path == "/api/listing-drafts":
            payload = self.read_json()
            self.create_listing_draft(int(payload["product_id"]))
        elif path == "/api/purchase-orders":
            payload = self.read_json()
            self.create_purchase_order(payload)
        else:
            raise ApiError(404, "Ruta API no encontrada")

    def handle_meli_callback(self, parsed: object) -> None:
        query = parse_qs(parsed.query)
        if "error" in query:
            message = query.get("error_description", query["error"])[0]
            self.send_html(f"<h1>Mercado Libre no conectado</h1><p>{message}</p>", 400)
            return
        code = query.get("code", [""])[0]
        state = query.get("state", [""])[0]
        if not code or not state:
            self.send_html("<h1>Mercado Libre no conectado</h1><p>Falta code o state.</p>", 400)
            return
        token = exchange_code(code, state)
        self.send_html(
            "<h1>Mercado Libre conectado</h1>"
            f"<p>Usuario ID: {token.get('user_id')}</p>"
            "<p>Ya puedes volver al panel.</p>"
        )

    def handle_api_patch(self, path: str) -> None:
        parts = path.strip("/").split("/")
        if len(parts) == 4 and parts[:2] == ["api", "listing-drafts"] and parts[3] == "status":
            draft_id = int(parts[2])
            payload = self.read_json()
            status = payload.get("status")
            allowed = {item.value for item in ListingStatus}
            if status not in allowed:
                raise ApiError(400, "Estado de publicacion invalido")
            update_listing_status(draft_id, status)
            self.send_json({"ok": True})
            return
        raise ApiError(404, "Ruta API no encontrada")

    def analyze_all(self) -> None:
        products = fetch_products()
        created = 0
        for item in products:
            product, supplier = get_product_and_supplier(int(item["id"]))
            opportunity = analyze_product(product, supplier)
            upsert_opportunity(opportunity)
            created += 1
        self.send_json({"ok": True, "analyzed": created})

    def create_listing_draft(self, product_id: int) -> None:
        product, supplier = get_product_and_supplier(product_id)
        opportunity = analyze_product(product, supplier)
        opportunity_id = upsert_opportunity(opportunity)
        draft = build_listing_draft(product, opportunity)
        draft_id = insert_listing_draft(draft, opportunity_id)
        self.send_json({"ok": True, "id": draft_id, "status": draft["status"]}, 201)

    def create_purchase_order(self, payload: dict) -> None:
        product_id = int(payload["product_id"])
        product, supplier = get_product_and_supplier(product_id)
        opportunity = analyze_product(product, supplier)
        order = {
            "sale_reference": payload.get("sale_reference") or "VENTA-SIMULADA",
            "product_id": product.id,
            "listing_draft_id": payload.get("listing_draft_id"),
            "supplier_id": supplier.id,
            "supplier_sku": product.sku,
            "product_title": product.title,
            "supplier_cost": product.cost,
            "supplier_shipping": product.supplier_shipping,
            "expected_margin_rate": opportunity.net_margin_rate,
            "supplier_url": product.product_url,
            "checklist": build_purchase_checklist(),
            "status": PurchaseOrderStatus.PURCHASE_NEEDED.value,
        }
        order_id = insert_purchase_order(order)
        self.send_json({"ok": True, "id": order_id}, 201)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if not length:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw)

    def send_json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html: str, status: int = 200) -> None:
        body = (
            "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            "<title>Mercado Libre</title></head><body>"
            f"{html}"
            "</body></html>"
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_static(self, path: str) -> None:
        if path in {"", "/"}:
            path = "/index.html"
        requested = (WEB_DIR / path.lstrip("/")).resolve()
        if WEB_DIR.resolve() not in requested.parents and requested != WEB_DIR.resolve():
            raise ApiError(403, "Ruta no permitida")
        if not requested.exists() or not requested.is_file():
            raise ApiError(404, "Archivo no encontrado")
        content_type = mimetypes.guess_type(requested.name)[0] or "application/octet-stream"
        body = requested.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    init_db()
    seed_demo_data()
    default_host = "0.0.0.0" if os.environ.get("RENDER") == "true" else "127.0.0.1"
    host = os.environ.get("HOST", default_host)
    port = int(os.environ.get("PORT", "8787"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Bot Dropshipping Tech MX listo en http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
