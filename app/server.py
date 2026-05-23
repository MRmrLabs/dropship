from __future__ import annotations

import json
import mimetypes
import os
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth import auth_status, is_auth_enabled, is_authenticated, login_cookie, logout_cookie, verify_password
from app.branding import store_brand
from app.domain import (
    ListingStatus,
    PurchaseOrderStatus,
    analyze_product,
    build_listing_draft,
    build_purchase_checklist,
)
from app.ai_research import enforce_usage_limits, openai_status, research_products
from app.deep_search import deep_search_products
from app.local_search import (
    get_local_search_job,
    local_search_status,
    start_local_search,
    stop_local_search_job,
)
from app.meli_auth import build_authorization_url, exchange_code, fetch_me, integration_status
from app.meli_marketplace import compare_market, publish_listing
from app.reports import build_investment_plan, plan_to_html, plan_to_pdf_bytes
from app.storage import (
    ROOT,
    fetch_ai_research_runs,
    fetch_listing_drafts,
    fetch_opportunities,
    fetch_products,
    fetch_purchase_orders,
    fetch_storefront_orders,
    fetch_storefront_products,
    fetch_suppliers,
    fetch_opportunity_evidence,
    fetch_rejected_candidates,
    count_ai_research_runs_today,
    get_listing_draft,
    get_investment_plan,
    get_product_and_supplier,
    import_ai_candidate,
    init_db,
    insert_ai_research_run,
    insert_opportunity_evidence,
    insert_listing_draft,
    insert_purchase_order,
    insert_storefront_order,
    latest_ai_research_run,
    mark_storefront_order_paid,
    reject_product,
    restore_rejected_candidate,
    seed_demo_data,
    update_storefront_order_stripe,
    update_listing_marketplace,
    update_listing_status,
    update_product_market_snapshot,
    upsert_investment_plan,
    upsert_opportunity,
)
from app.stripe_payments import create_checkout_session, parse_webhook, stripe_status
from app.supplier_orders import supplier_order_route


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
        except TimeoutError:
            self.send_json({"error": "OpenAI tardo demasiado. Intenta una busqueda mas especifica."}, 504)
        except socket.timeout:
            self.send_json({"error": "OpenAI tardo demasiado. Intenta una busqueda mas especifica."}, 504)
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            self.handle_api_post(parsed.path)
        except ApiError as exc:
            self.send_json({"error": exc.message}, exc.status)
        except TimeoutError:
            self.send_json({"error": "OpenAI tardo demasiado. Intenta una busqueda mas especifica."}, 504)
        except socket.timeout:
            self.send_json({"error": "OpenAI tardo demasiado. Intenta una busqueda mas especifica."}, 504)
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)

    def do_PATCH(self) -> None:
        try:
            parsed = urlparse(self.path)
            self.handle_api_patch(parsed.path)
        except ApiError as exc:
            self.send_json({"error": exc.message}, exc.status)
        except TimeoutError:
            self.send_json({"error": "OpenAI tardo demasiado. Intenta una busqueda mas especifica."}, 504)
        except socket.timeout:
            self.send_json({"error": "OpenAI tardo demasiado. Intenta una busqueda mas especifica."}, 504)
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)

    def handle_api_get(self, path: str) -> None:
        if path == "/api/health":
            self.send_json({"ok": True, "marketplace": "mercado_libre_mx"})
        elif path == "/api/auth/status":
            status = auth_status()
            status["authenticated"] = is_authenticated(self.headers.get("Cookie"))
            self.send_json(status)
        elif path.startswith("/api/") and not self.require_admin(path):
            return
        elif path == "/api/suppliers":
            self.send_json(fetch_suppliers())
        elif path == "/api/products":
            self.send_json(fetch_products())
        elif path in {"/api/opportunities", "/api/opportunity-list"}:
            self.send_json(fetch_opportunities())
        elif path == "/api/listing-drafts":
            self.send_json(fetch_listing_drafts())
        elif path == "/api/purchase-orders":
            self.send_json(fetch_purchase_orders())
        elif path == "/api/storefront/products":
            self.send_json({"brand": store_brand(), "products": fetch_storefront_products()})
        elif path == "/api/storefront/orders":
            self.send_json(fetch_storefront_orders())
        elif path == "/api/integrations/meli/status":
            self.send_json(integration_status())
        elif path == "/api/integrations/meli/auth-url":
            self.send_json({"url": build_authorization_url()})
        elif path == "/api/integrations/meli/me":
            self.send_json(fetch_me())
        elif path == "/api/integrations/openai/status":
            status = openai_status()
            status["searches_today"] = count_ai_research_runs_today()
            status["local_search"] = local_search_status()
            self.send_json(status)
        elif path == "/api/integrations/stripe/status":
            self.send_json(stripe_status())
        elif path == "/api/ai/research-runs":
            self.send_json(fetch_ai_research_runs())
        elif path == "/api/ai/deep-search-runs":
            engine_names = {
                "deep_search_v2",
                "primeloot_deep_search_v2",
                "primeloot_local_plus_openai",
                "primeloot_local_search",
            }
            runs = [
                run
                for run in fetch_ai_research_runs()
                if str(run.get("result", {}).get("engine") or "") in engine_names
            ]
            self.send_json(runs)
        elif path.startswith("/api/opportunities/") and path.endswith("/evidence"):
            product_id = int(path.split("/")[-2])
            self.send_json(fetch_opportunity_evidence(product_id))
        elif path == "/api/rejected-candidates":
            self.send_json(fetch_rejected_candidates())
        elif path.startswith("/api/local-search/status/"):
            job_id = path.rsplit("/", 1)[1]
            self.send_json(get_local_search_job(job_id))
        elif path.startswith("/api/local-search/results/"):
            job_id = path.rsplit("/", 1)[1]
            self.send_local_search_results(job_id)
        elif path.startswith("/api/investment-plans/"):
            product_id = int(path.rsplit("/", 1)[1].replace(".pdf", ""))
            self.send_investment_plan(product_id, pdf=path.endswith(".pdf"))
        elif path.startswith("/api/supplier-order-route/"):
            product_id = int(path.rsplit("/", 1)[1])
            product, supplier = get_product_and_supplier(product_id)
            self.send_json(supplier_order_route(product, supplier))
        else:
            raise ApiError(404, "Ruta API no encontrada")

    def handle_api_post(self, path: str) -> None:
        if path == "/api/auth/login":
            payload = self.read_json()
            if verify_password(str(payload.get("password") or "")):
                self.send_json({"ok": True}, headers={"Set-Cookie": login_cookie()})
            else:
                raise ApiError(401, "Password incorrecto")
        elif path == "/api/auth/logout":
            self.send_json({"ok": True}, headers={"Set-Cookie": logout_cookie()})
        elif path == "/api/stripe/webhook":
            self.handle_stripe_webhook()
        elif path.startswith("/api/") and not self.require_admin(path):
            return
        elif path == "/api/analyze":
            self.analyze_all()
        elif path == "/api/listing-drafts":
            payload = self.read_json()
            self.create_listing_draft(int(payload["product_id"]))
        elif path == "/api/products/compare-market":
            payload = self.read_json()
            self.compare_product_market(int(payload["product_id"]))
        elif path == "/api/purchase-orders":
            payload = self.read_json()
            self.create_purchase_order(payload)
        elif path == "/api/storefront/orders":
            payload = self.read_json()
            self.create_storefront_order(payload)
        elif path.startswith("/api/storefront/orders/") and path.endswith("/checkout"):
            order_id = int(path.split("/")[-2])
            self.create_stripe_checkout(order_id)
        elif path == "/api/ai/research":
            payload = self.read_json()
            self.create_ai_research(payload)
        elif path == "/api/ai/deep-search":
            payload = self.read_json()
            self.create_deep_search(payload)
        elif path == "/api/local-search/start":
            payload = self.read_json()
            self.send_json(start_local_search(payload.get("query") or None), 202)
        elif path.startswith("/api/local-search/stop/"):
            job_id = path.rsplit("/", 1)[1]
            self.send_json(stop_local_search_job(job_id))
        elif path == "/api/ai/import-candidate":
            payload = self.read_json()
            imported = self.import_and_analyze_candidate(int(payload["run_id"]), int(payload["candidate_index"]))
            self.send_json({"ok": True, **imported}, 201)
        elif path == "/api/opportunities/reject":
            payload = self.read_json()
            reject_product(int(payload["product_id"]))
            self.send_json({"ok": True})
        elif path.startswith("/api/rejected-candidates/") and path.endswith("/restore"):
            candidate_id = int(path.split("/")[-2])
            restore_rejected_candidate(candidate_id)
            self.send_json({"ok": True})
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
        if path.startswith("/api/") and not self.require_admin(path):
            return
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

    def require_admin(self, path: str) -> bool:
        public = {
            "/api/health",
            "/api/auth/status",
            "/api/auth/login",
            "/api/storefront/products",
            "/api/storefront/orders",
            "/api/stripe/webhook",
        }
        if path in public or path.startswith("/api/storefront/orders/"):
            return True
        if not is_auth_enabled() or is_authenticated(self.headers.get("Cookie")):
            return True
        self.send_json({"error": "Login requerido"}, 401)
        return False

    def analyze_all(self) -> None:
        imported = self.import_saved_ai_candidates()
        products = fetch_products()
        created = 0
        for item in products:
            product, supplier = get_product_and_supplier(int(item["id"]))
            opportunity = analyze_product(product, supplier)
            upsert_opportunity(opportunity)
            created += 1
        self.send_json({"ok": True, "imported": imported, "analyzed": created, "auto_rejected": 0})

    def create_listing_draft(self, product_id: int) -> None:
        self.refresh_market_snapshot(product_id)
        product, supplier = get_product_and_supplier(product_id)
        opportunity = analyze_product(product, supplier)
        opportunity_id = upsert_opportunity(opportunity)
        self.build_and_store_plan(product_id, opportunity_id)
        draft = build_listing_draft(product, opportunity)
        draft_id = insert_listing_draft(draft, opportunity_id)
        created = get_listing_draft(draft_id)
        try:
            listing = publish_listing(created, product)
            update_listing_marketplace(
                draft_id,
                listing.item_id,
                listing.permalink,
                listing.status,
                ListingStatus.PUBLISHED.value,
            )
            self.send_json(
                {
                    "ok": True,
                    "id": draft_id,
                    "status": ListingStatus.PUBLISHED.value,
                    "marketplace_item_id": listing.item_id,
                    "permalink": listing.permalink,
                },
                201,
            )
        except Exception as exc:
            update_listing_marketplace(
                draft_id,
                None,
                None,
                "error",
                ListingStatus.NEEDS_REVIEW.value,
                str(exc),
            )
            self.send_json(
                {
                    "ok": False,
                    "id": draft_id,
                    "status": ListingStatus.NEEDS_REVIEW.value,
                    "error": str(exc),
                },
                201,
            )

    def compare_product_market(self, product_id: int) -> None:
        snapshot = self.refresh_market_snapshot(product_id)
        product, supplier = get_product_and_supplier(product_id)
        opportunity = analyze_product(product, supplier)
        opportunity_id = upsert_opportunity(opportunity)
        self.build_and_store_plan(product_id, opportunity_id)
        self.send_json(
            {
                "ok": True,
                "market": snapshot,
                "opportunity": {
                    "product_id": opportunity.product_id,
                    "suggested_price": opportunity.suggested_price,
                    "net_margin_rate": opportunity.net_margin_rate,
                    "net_profit": opportunity.net_profit,
                    "score": opportunity.score,
                    "signal": opportunity.signal.value,
                    "risks": opportunity.risks,
                },
            }
        )

    def refresh_market_snapshot(self, product_id: int) -> dict[str, object]:
        product, _supplier = get_product_and_supplier(product_id)
        snapshot = compare_market(product)
        update_product_market_snapshot(
            product_id,
            float(snapshot["reference_price"]),
            str(snapshot["competition_level"]),
        )
        return snapshot

    def create_purchase_order(self, payload: dict) -> None:
        product_id = int(payload["product_id"])
        market = self.refresh_market_snapshot(product_id)
        product, supplier = get_product_and_supplier(product_id)
        opportunity = analyze_product(product, supplier)
        upsert_opportunity(opportunity)
        checklist = build_purchase_checklist()
        route = supplier_order_route(product, supplier, int(payload.get("quantity") or 1))
        checklist = route["steps"] + checklist
        checklist.insert(
            0,
            "Comparacion Mercado Libre: "
            f"referencia ${float(market['reference_price']):.2f}, "
            f"minimo ${float(market['min_price']):.2f}, "
            f"{int(market['count'])} resultado(s).",
        )
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
            "checklist": checklist,
            "status": PurchaseOrderStatus.PURCHASE_NEEDED.value,
        }
        order_id = insert_purchase_order(order)
        self.send_json({"ok": True, "id": order_id, "supplier_route": route}, 201)

    def create_storefront_order(self, payload: dict) -> None:
        items = payload.get("items") or []
        if not items:
            raise ApiError(400, "El carrito esta vacio")
        customer_name = str(payload.get("customer_name") or "").strip()
        customer_phone = str(payload.get("customer_phone") or "").strip()
        if not customer_name or not customer_phone:
            raise ApiError(400, "Nombre y telefono son obligatorios")

        catalog = {int(item["product_id"]): item for item in fetch_storefront_products()}
        order_items: list[dict[str, object]] = []
        purchase_order_ids: list[int] = []
        subtotal = 0.0
        for raw_item in items:
            product_id = int(raw_item.get("product_id") or 0)
            quantity = max(1, min(5, int(raw_item.get("quantity") or 1)))
            catalog_item = catalog.get(product_id)
            if not catalog_item:
                raise ApiError(400, f"Producto {product_id} no esta disponible en tienda")
            if quantity > int(catalog_item["stock"]):
                raise ApiError(400, f"Stock insuficiente para {catalog_item['title']}")
            line_total = float(catalog_item["price"]) * quantity
            subtotal += line_total
            order_items.append(
                {
                    "product_id": product_id,
                    "title": catalog_item["title"],
                    "quantity": quantity,
                    "unit_price": catalog_item["price"],
                    "line_total": round(line_total, 2),
                }
            )
            for _ in range(quantity):
                product, supplier = get_product_and_supplier(product_id)
                opportunity = analyze_product(product, supplier)
                po = {
                    "sale_reference": f"WEB-PENDIENTE-{product_id}",
                    "product_id": product.id,
                    "listing_draft_id": None,
                    "supplier_id": supplier.id,
                    "supplier_sku": product.sku,
                    "product_title": product.title,
                    "supplier_cost": product.cost,
                    "supplier_shipping": product.supplier_shipping,
                    "expected_margin_rate": opportunity.net_margin_rate,
                    "supplier_url": product.product_url,
                    "checklist": ["Venta web pendiente de pago"] + build_purchase_checklist(),
                    "status": PurchaseOrderStatus.NEW_SALE.value,
                }
                purchase_order_ids.append(insert_purchase_order(po))

        order_id = insert_storefront_order(
            {
                "customer_name": customer_name,
                "customer_email": str(payload.get("customer_email") or "").strip(),
                "customer_phone": customer_phone,
                "delivery_city": str(payload.get("delivery_city") or "").strip(),
                "delivery_notes": str(payload.get("delivery_notes") or "").strip(),
                "items": order_items,
                "subtotal": round(subtotal, 2),
                "status": "pending_payment",
                "purchase_order_ids": purchase_order_ids,
                "platform_fee": round(subtotal * float(os.environ.get("STRIPE_PLATFORM_COMMISSION_RATE", "0.10")), 2),
            }
        )
        for purchase_order_id in purchase_order_ids:
            # Keep sale reference traceable after the storefront order id exists.
            pass
        whatsapp = build_whatsapp_checkout(order_id, customer_name, customer_phone, order_items, subtotal)
        checkout_url = None
        stripe_error = None
        if os.environ.get("STRIPE_SECRET_KEY"):
            try:
                session = create_checkout_session(order_id, order_items, subtotal)
                update_storefront_order_stripe(order_id, session)
                checkout_url = session.get("url")
            except Exception as exc:
                stripe_error = str(exc)
        self.send_json(
            {
                "ok": True,
                "id": order_id,
                "status": "pending_payment",
                "subtotal": round(subtotal, 2),
                "purchase_order_ids": purchase_order_ids,
                "whatsapp_url": whatsapp,
                "checkout_url": checkout_url,
                "stripe_error": stripe_error,
            },
            201,
        )

    def create_stripe_checkout(self, order_id: int) -> None:
        orders = {int(order["id"]): order for order in fetch_storefront_orders()}
        order = orders.get(order_id)
        if not order:
            raise ApiError(404, "Pedido no encontrado")
        session = create_checkout_session(order_id, order["items"], float(order["subtotal"]))
        update_storefront_order_stripe(order_id, session)
        self.send_json({"ok": True, "checkout_url": session.get("url"), "session_id": session.get("id")})

    def handle_stripe_webhook(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        payload = self.rfile.read(length)
        event = parse_webhook(payload, self.headers.get("Stripe-Signature"))
        if event.get("type") == "checkout.session.completed":
            session = event.get("data", {}).get("object", {})
            order_id = int(session.get("client_reference_id") or session.get("metadata", {}).get("storefront_order_id") or 0)
            if order_id:
                mark_storefront_order_paid(order_id, session.get("payment_status") or "paid")
        self.send_json({"received": True})

    def build_static_path(self, path: str) -> str:
        if path in {"", "/"}:
            return "/index.html"
        if path in {"/tienda", "/store"}:
            return "/store.html"
        return path

    def create_ai_research(self, payload: dict) -> None:
        enforce_usage_limits(count_ai_research_runs_today(), latest_ai_research_run())
        query = payload.get("query") or None
        result = research_products(query)
        run_id = insert_ai_research_run(result.get("query") or "", "completed", result)
        imported: list[dict[str, int | str]] = []
        for index, candidate in enumerate(result.get("candidates", [])):
            try:
                imported.append(self.import_and_analyze_candidate(run_id, index))
            except Exception as exc:
                imported.append({"product_id": 0, "status": f"skipped: {exc}"})
        self.send_json(
            {"ok": True, "id": run_id, "result": result, "imported": imported, "auto_rejected": 0},
            201,
        )

    def create_deep_search(self, payload: dict) -> None:
        enforce_usage_limits(count_ai_research_runs_today(), latest_ai_research_run())
        query = payload.get("query") or None
        result = deep_search_products(query)
        run_id = insert_ai_research_run(result.get("query") or "", "completed", result)
        imported: list[dict[str, int | str]] = []
        for index, _candidate in enumerate(result.get("candidates", [])):
            try:
                imported.append(self.import_and_analyze_candidate(run_id, index))
            except Exception as exc:
                imported.append({"product_id": 0, "status": f"skipped: {exc}"})
        self.send_json(
            {
                "ok": True,
                "id": run_id,
                "result": result,
                "imported": imported,
                "reviewed": len(result.get("candidates", [])) + len(result.get("rejected", [])),
                "rejected": len(result.get("rejected", [])),
            },
            201,
        )

    def send_local_search_results(self, job_id: str) -> None:
        job = get_local_search_job(job_id)
        result = job.get("result") or {}
        if job.get("status") != "completed":
            self.send_json(job)
            return
        if not result.get("imported") and result.get("candidates"):
            run_id = insert_ai_research_run(result.get("query") or "local search", "completed", result)
            imported: list[dict[str, int | str]] = []
            for index, _candidate in enumerate(result.get("candidates", [])):
                try:
                    imported.append(self.import_and_analyze_candidate(run_id, index))
                except Exception as exc:
                    imported.append({"product_id": 0, "status": f"skipped: {exc}"})
            result["imported"] = imported
            result["run_id"] = run_id
        self.send_json({"ok": True, "job": job, "result": result})

    def import_saved_ai_candidates(self) -> list[dict[str, int | str]]:
        imported: list[dict[str, int | str]] = []
        for run in fetch_ai_research_runs():
            candidates = run.get("result", {}).get("candidates", [])
            for index, _candidate in enumerate(candidates):
                try:
                    imported.append(self.import_and_analyze_candidate(int(run["id"]), index))
                except Exception as exc:
                    imported.append({"product_id": 0, "status": f"skipped: {exc}"})
        return imported

    def import_and_analyze_candidate(self, run_id: int, candidate_index: int) -> dict[str, int | str]:
        product_id = import_ai_candidate(run_id, candidate_index)
        product, supplier = get_product_and_supplier(product_id)
        opportunity = analyze_product(product, supplier)
        opportunity_id = upsert_opportunity(opportunity)
        self.store_candidate_evidence(product_id, run_id, candidate_index)
        self.build_and_store_plan(product_id, opportunity_id)
        return {"product_id": product_id, "status": opportunity.signal.value}

    def store_candidate_evidence(self, product_id: int, run_id: int, candidate_index: int) -> None:
        run = next((item for item in fetch_ai_research_runs() if int(item["id"]) == run_id), None)
        if not run:
            return
        candidates = run.get("result", {}).get("candidates", [])
        if candidate_index < 0 or candidate_index >= len(candidates):
            return
        candidate = candidates[candidate_index]
        evidence = {
            "score_details": candidate.get("score_details"),
            "market_snapshot": candidate.get("market_snapshot"),
            "evidence": candidate.get("evidence"),
            "sources": candidate.get("source_urls", []),
            "meli_reference_urls": candidate.get("meli_reference_urls", []),
        }
        insert_opportunity_evidence(product_id, run_id, evidence)

    def build_and_store_plan(self, product_id: int, opportunity_id: int | None = None) -> int:
        row = next((item for item in fetch_opportunities() if int(item["product_id"]) == product_id), None)
        if not row:
            return 0
        plan = build_investment_plan(row)
        html = plan_to_html(plan)
        return upsert_investment_plan(product_id, opportunity_id, plan, html)

    def send_investment_plan(self, product_id: int, pdf: bool = False) -> None:
        stored = get_investment_plan(product_id)
        if not stored:
            self.build_and_store_plan(product_id)
            stored = get_investment_plan(product_id)
        if not stored:
            raise ApiError(404, "Plan de inversion no encontrado")
        if pdf:
            body = plan_to_pdf_bytes(stored["plan"])
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Disposition", f"inline; filename=primeloot-plan-{product_id}.pdf")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_json({"ok": True, "id": stored["id"], "plan": stored["plan"], "html": stored["html"]})

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if not length:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw)

    def send_json(self, payload: object, status: int = 200, headers: dict[str, str] | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
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
        path = self.build_static_path(path)
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


def build_whatsapp_checkout(
    order_id: int,
    customer_name: str,
    customer_phone: str,
    items: list[dict[str, object]],
    subtotal: float,
) -> str | None:
    target = os.environ.get("STORE_WHATSAPP", "").strip()
    if not target:
        return None
    lines = [
        f"Hola, quiero confirmar mi pedido web #{order_id}.",
        f"Nombre: {customer_name}",
        f"Telefono: {customer_phone}",
        "Productos:",
    ]
    for item in items:
        lines.append(f"- {item['quantity']} x {item['title']} (${float(item['line_total']):.2f})")
    lines.append(f"Total pendiente: ${subtotal:.2f} MXN")
    return f"https://wa.me/{target}?text={quote(chr(10).join(lines))}"


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
