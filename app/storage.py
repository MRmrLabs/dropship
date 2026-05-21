from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from app.domain import Supplier, SupplierProduct


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT / "data"))
DB_PATH = DATA_DIR / "dropshipping.db"


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS suppliers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                country TEXT NOT NULL,
                website TEXT NOT NULL,
                contact TEXT NOT NULL,
                terms TEXT NOT NULL,
                shipping_type TEXT NOT NULL,
                reliability INTEGER NOT NULL,
                invoices INTEGER NOT NULL,
                authorized_assets INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS supplier_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                supplier_id INTEGER NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
                sku TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                brand TEXT NOT NULL,
                category TEXT NOT NULL,
                cost REAL NOT NULL,
                supplier_shipping REAL NOT NULL,
                stock INTEGER NOT NULL,
                warranty TEXT NOT NULL,
                lead_time_days INTEGER NOT NULL,
                image_url TEXT NOT NULL,
                product_url TEXT NOT NULL,
                assets_authorized INTEGER NOT NULL,
                market_competition_price REAL NOT NULL,
                competition_level TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                source_type TEXT NOT NULL DEFAULT 'manual'
            );

            CREATE TABLE IF NOT EXISTS opportunities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL REFERENCES supplier_products(id) ON DELETE CASCADE,
                platform TEXT NOT NULL,
                suggested_price REAL NOT NULL,
                net_margin_rate REAL NOT NULL,
                net_profit REAL NOT NULL,
                score INTEGER NOT NULL,
                signal TEXT NOT NULL,
                risks TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS listing_drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL REFERENCES supplier_products(id) ON DELETE CASCADE,
                opportunity_id INTEGER REFERENCES opportunities(id) ON DELETE SET NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                price REAL NOT NULL,
                stock INTEGER NOT NULL,
                status TEXT NOT NULL,
                attributes TEXT NOT NULL,
                image_url TEXT NOT NULL,
                marketplace_item_id TEXT,
                marketplace_permalink TEXT,
                marketplace_status TEXT,
                marketplace_error TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS purchase_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_reference TEXT NOT NULL,
                product_id INTEGER NOT NULL REFERENCES supplier_products(id),
                listing_draft_id INTEGER REFERENCES listing_drafts(id),
                supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
                supplier_sku TEXT NOT NULL,
                product_title TEXT NOT NULL,
                supplier_cost REAL NOT NULL,
                supplier_shipping REAL NOT NULL,
                expected_margin_rate REAL NOT NULL,
                supplier_url TEXT NOT NULL,
                checklist TEXT NOT NULL,
                status TEXT NOT NULL,
                tracking_number TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS ai_research_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                status TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        ensure_column(conn, "supplier_products", "status", "TEXT NOT NULL DEFAULT 'active'")
        ensure_column(conn, "supplier_products", "source_type", "TEXT NOT NULL DEFAULT 'manual'")
        ensure_column(conn, "listing_drafts", "marketplace_permalink", "TEXT")
        ensure_column(conn, "listing_drafts", "marketplace_status", "TEXT")
        ensure_column(conn, "listing_drafts", "marketplace_error", "TEXT")


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def seed_demo_data() -> None:
    purge_demo_data()


def purge_demo_data() -> None:
    demo_skus = ("NT-CAB-100", "NT-HUB-441", "GF-IPH-020", "NT-SOP-77")
    demo_suppliers = ("Distribuidora Norte Tech", "Importadora Gadget Flash")
    with connect() as conn:
        placeholders = ",".join("?" for _ in demo_skus)
        product_ids = [
            row["id"]
            for row in conn.execute(
                f"SELECT id FROM supplier_products WHERE sku IN ({placeholders})",
                demo_skus,
            ).fetchall()
        ]
        if product_ids:
            id_placeholders = ",".join("?" for _ in product_ids)
            conn.execute(f"DELETE FROM purchase_orders WHERE product_id IN ({id_placeholders})", product_ids)
            conn.execute(f"DELETE FROM listing_drafts WHERE product_id IN ({id_placeholders})", product_ids)
            conn.execute(f"DELETE FROM opportunities WHERE product_id IN ({id_placeholders})", product_ids)
        conn.execute(f"DELETE FROM supplier_products WHERE sku IN ({placeholders})", demo_skus)
        placeholders = ",".join("?" for _ in demo_suppliers)
        conn.execute(f"DELETE FROM suppliers WHERE name IN ({placeholders})", demo_suppliers)


def row_to_supplier(row: sqlite3.Row) -> Supplier:
    return Supplier(
        id=row["id"],
        name=row["name"],
        country=row["country"],
        website=row["website"],
        contact=row["contact"],
        terms=row["terms"],
        shipping_type=row["shipping_type"],
        reliability=row["reliability"],
        invoices=bool(row["invoices"]),
        authorized_assets=bool(row["authorized_assets"]),
    )


def row_to_product(row: sqlite3.Row) -> SupplierProduct:
    return SupplierProduct(
        id=row["id"],
        supplier_id=row["supplier_id"],
        sku=row["sku"],
        title=row["title"],
        brand=row["brand"],
        category=row["category"],
        cost=row["cost"],
        supplier_shipping=row["supplier_shipping"],
        stock=row["stock"],
        warranty=row["warranty"],
        lead_time_days=row["lead_time_days"],
        image_url=row["image_url"],
        product_url=row["product_url"],
        assets_authorized=bool(row["assets_authorized"]),
        market_competition_price=row["market_competition_price"],
        competition_level=row["competition_level"],
    )


def fetch_suppliers() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM suppliers ORDER BY reliability DESC").fetchall()
        return [dict(row) for row in rows]


def fetch_products() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT p.*, s.name AS supplier_name, s.reliability AS supplier_reliability
            FROM supplier_products p
            JOIN suppliers s ON s.id = p.supplier_id
            WHERE p.status = 'active'
            ORDER BY p.id DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]


def get_product_and_supplier(product_id: int) -> tuple[SupplierProduct, Supplier]:
    with connect() as conn:
        product_row = conn.execute("SELECT * FROM supplier_products WHERE id = ?", (product_id,)).fetchone()
        if not product_row or product_row["status"] != "active":
            raise KeyError("Producto no encontrado")
        supplier_row = conn.execute("SELECT * FROM suppliers WHERE id = ?", (product_row["supplier_id"],)).fetchone()
        return row_to_product(product_row), row_to_supplier(supplier_row)


def upsert_opportunity(opportunity: Any) -> int:
    with connect() as conn:
        conn.execute("DELETE FROM opportunities WHERE product_id = ?", (opportunity.product_id,))
        cur = conn.execute(
            """
            INSERT INTO opportunities
            (product_id, platform, suggested_price, net_margin_rate, net_profit, score, signal, risks)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                opportunity.product_id,
                opportunity.platform,
                opportunity.suggested_price,
                opportunity.net_margin_rate,
                opportunity.net_profit,
                opportunity.score,
                opportunity.signal.value,
                json.dumps(opportunity.risks, ensure_ascii=True),
            ),
        )
        return int(cur.lastrowid)


def fetch_opportunities() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT o.*, p.sku, p.title, p.brand, p.category, p.stock, p.cost, p.supplier_shipping,
                   p.image_url, p.product_url, p.source_type, s.name AS supplier_name
            FROM opportunities o
            JOIN supplier_products p ON p.id = o.product_id
            JOIN suppliers s ON s.id = p.supplier_id
            WHERE p.status = 'active'
            ORDER BY
              CASE o.signal WHEN 'green' THEN 1 WHEN 'yellow' THEN 2 ELSE 3 END,
              o.score DESC
            """
        ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["risks"] = json.loads(item["risks"])
            output.append(item)
        return output


def insert_listing_draft(draft: dict[str, Any], opportunity_id: int | None) -> int:
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO listing_drafts
            (product_id, opportunity_id, title, description, price, stock, status, attributes, image_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                draft["product_id"],
                opportunity_id,
                draft["title"],
                draft["description"],
                draft["price"],
                draft["stock"],
                draft["status"],
                json.dumps(draft["attributes"], ensure_ascii=True),
                draft["image_url"],
            ),
        )
        return int(cur.lastrowid)


def update_listing_status(draft_id: int, status: str) -> None:
    with connect() as conn:
        cur = conn.execute(
            "UPDATE listing_drafts SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, draft_id),
        )
        if cur.rowcount == 0:
            raise KeyError("Borrador no encontrado")


def update_listing_marketplace(
    draft_id: int,
    item_id: str | None,
    permalink: str | None,
    marketplace_status: str | None,
    status: str,
    error: str | None = None,
) -> None:
    with connect() as conn:
        cur = conn.execute(
            """
            UPDATE listing_drafts
            SET marketplace_item_id = ?,
                marketplace_permalink = ?,
                marketplace_status = ?,
                marketplace_error = ?,
                status = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (item_id, permalink, marketplace_status, error, status, draft_id),
        )
        if cur.rowcount == 0:
            raise KeyError("Borrador no encontrado")


def get_listing_draft(draft_id: int) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT d.*, p.sku, p.title AS product_title, s.name AS supplier_name
            FROM listing_drafts d
            JOIN supplier_products p ON p.id = d.product_id
            JOIN suppliers s ON s.id = p.supplier_id
            WHERE d.id = ?
            """,
            (draft_id,),
        ).fetchone()
        if not row:
            raise KeyError("Borrador no encontrado")
        item = dict(row)
        item["attributes"] = json.loads(item["attributes"])
        return item


def fetch_listing_drafts() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT d.*, p.sku, p.title AS product_title, s.name AS supplier_name
            FROM listing_drafts d
            JOIN supplier_products p ON p.id = d.product_id
            JOIN suppliers s ON s.id = p.supplier_id
            ORDER BY d.created_at DESC
            """
        ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["attributes"] = json.loads(item["attributes"])
            output.append(item)
        return output


def update_product_market_snapshot(product_id: int, reference_price: float, competition_level: str) -> None:
    with connect() as conn:
        cur = conn.execute(
            """
            UPDATE supplier_products
            SET market_competition_price = ?, competition_level = ?
            WHERE id = ? AND status = 'active'
            """,
            (reference_price, competition_level, product_id),
        )
        if cur.rowcount == 0:
            raise KeyError("Producto no encontrado")


def insert_purchase_order(order: dict[str, Any]) -> int:
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO purchase_orders
            (sale_reference, product_id, listing_draft_id, supplier_id, supplier_sku, product_title,
             supplier_cost, supplier_shipping, expected_margin_rate, supplier_url, checklist, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order["sale_reference"],
                order["product_id"],
                order.get("listing_draft_id"),
                order["supplier_id"],
                order["supplier_sku"],
                order["product_title"],
                order["supplier_cost"],
                order["supplier_shipping"],
                order["expected_margin_rate"],
                order["supplier_url"],
                json.dumps(order["checklist"], ensure_ascii=True),
                order["status"],
            ),
        )
        return int(cur.lastrowid)


def fetch_purchase_orders() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM purchase_orders ORDER BY created_at DESC").fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["checklist"] = json.loads(item["checklist"])
            output.append(item)
        return output


def insert_ai_research_run(query: str, status: str, result: dict[str, Any]) -> int:
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO ai_research_runs (query, status, result_json)
            VALUES (?, ?, ?)
            """,
            (query, status, json.dumps(result, ensure_ascii=True)),
        )
        return int(cur.lastrowid)


def fetch_ai_research_runs() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM ai_research_runs ORDER BY created_at DESC LIMIT 10"
        ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["result"] = json.loads(item.pop("result_json"))
            output.append(item)
        return output


def count_ai_research_runs_today() -> int:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM ai_research_runs
            WHERE status = 'completed' AND date(created_at) = date('now')
            """
        ).fetchone()
        return int(row["total"])


def latest_ai_research_run() -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM ai_research_runs ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


def import_ai_candidate(run_id: int, candidate_index: int) -> int:
    with connect() as conn:
        run = conn.execute("SELECT * FROM ai_research_runs WHERE id = ?", (run_id,)).fetchone()
        if not run:
            raise KeyError("Investigacion IA no encontrada")
        result = json.loads(run["result_json"])
        candidates = result.get("candidates", [])
        if candidate_index < 0 or candidate_index >= len(candidates):
            raise KeyError("Candidato IA no encontrado")
        candidate = candidates[candidate_index]
        supplier_id = ensure_supplier_from_candidate(conn, candidate)
        sku = f"AI-{run_id}-{candidate_index + 1}"
        existing = conn.execute("SELECT id FROM supplier_products WHERE sku = ?", (sku,)).fetchone()
        if existing:
            return int(existing["id"])
        cost = float(candidate.get("estimated_cost_mxn") or 0)
        market_price = float(candidate.get("estimated_market_price_mxn") or 0)
        if cost <= 0 or market_price <= 0:
            raise ValueError("El candidato no tiene costo o precio estimado suficiente para analizar")
        stock_signal = str(candidate.get("stock_signal") or "desconocido").lower()
        stock = {"alto": 30, "medio": 12, "bajo": 3}.get(stock_signal, 1)
        cur = conn.execute(
            """
            INSERT INTO supplier_products
            (supplier_id, sku, title, brand, category, cost, supplier_shipping, stock, warranty,
             lead_time_days, image_url, product_url, assets_authorized, market_competition_price, competition_level,
             status, source_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                supplier_id,
                sku,
                str(candidate.get("product_title") or "Producto investigado por IA")[:120],
                str(candidate.get("brand") or "Generico")[:80],
                str(candidate.get("category") or "perifericos").lower(),
                cost,
                float(candidate.get("estimated_shipping_mxn") or 0),
                stock,
                str(candidate.get("warranty") or "Validar con proveedor")[:120],
                int(candidate.get("lead_time_days") or 3),
                "",
                first_source_url(candidate),
                candidate_assets_authorized(candidate),
                market_price,
                "medium",
                "active",
                "ai",
            ),
        )
        return int(cur.lastrowid)


def reject_product(product_id: int) -> None:
    with connect() as conn:
        cur = conn.execute(
            "UPDATE supplier_products SET status = 'rejected' WHERE id = ?",
            (product_id,),
        )
        if cur.rowcount == 0:
            raise KeyError("Producto no encontrado")
        conn.execute("DELETE FROM opportunities WHERE product_id = ?", (product_id,))


def reject_red_opportunities() -> int:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT product_id
            FROM opportunities
            WHERE signal = 'red' OR score < 45
            """
        ).fetchall()
        product_ids = [row["product_id"] for row in rows]
        if not product_ids:
            return 0
        placeholders = ",".join("?" for _ in product_ids)
        conn.execute(f"UPDATE supplier_products SET status = 'rejected' WHERE id IN ({placeholders})", product_ids)
        conn.execute(f"DELETE FROM opportunities WHERE product_id IN ({placeholders})", product_ids)
        return len(product_ids)


def ensure_supplier_from_candidate(conn: sqlite3.Connection, candidate: dict[str, Any]) -> int:
    name = str(candidate.get("supplier_name") or "Proveedor IA").strip()
    existing = conn.execute("SELECT id FROM suppliers WHERE name = ?", (name,)).fetchone()
    if existing:
        return int(existing["id"])
    cur = conn.execute(
        """
        INSERT INTO suppliers
        (name, country, website, contact, terms, shipping_type, reliability, invoices, authorized_assets)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            "Mexico",
            str(candidate.get("supplier_website") or first_source_url(candidate))[:300],
            str(candidate.get("supplier_contact") or "Validar contacto")[:160],
            "Proveedor encontrado por IA; validar precio, stock, factura y autorizacion de imagenes",
            "Validar envio nacional",
            int(float(candidate.get("confidence") or 0.5) * 100),
            candidate_has_invoice_evidence(candidate),
            candidate_assets_authorized(candidate),
        ),
    )
    return int(cur.lastrowid)


def candidate_has_invoice_evidence(candidate: dict[str, Any]) -> int:
    text = candidate_text(candidate)
    if any(term in text for term in ("sin factura", "factura no", "facturacion no", "sin rfc")):
        return 0
    return int("factura" in text or "rfc" in text or bool(candidate.get("supplier_contact")))


def candidate_assets_authorized(candidate: dict[str, Any]) -> int:
    text = candidate_text(candidate)
    if any(term in text for term in ("imagen sin", "foto sin", "no autoriz", "validar imagen", "validar foto")):
        return 0
    return int("imagen autoriz" in text or "foto autoriz" in text or not candidate.get("risk_flags"))


def candidate_text(candidate: dict[str, Any]) -> str:
    fields = [
        candidate.get("supplier_contact"),
        candidate.get("warranty"),
        candidate.get("notes"),
        " ".join(str(flag) for flag in candidate.get("risk_flags") or []),
    ]
    return " ".join(str(field or "") for field in fields).lower()


def first_source_url(candidate: dict[str, Any]) -> str:
    urls = candidate.get("source_urls") or []
    if isinstance(urls, list) and urls:
        return str(urls[0])
    return str(candidate.get("supplier_website") or "")
