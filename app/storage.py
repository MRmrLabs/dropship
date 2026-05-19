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
                competition_level TEXT NOT NULL
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
            """
        )


def seed_demo_data() -> None:
    with connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS total FROM suppliers").fetchone()["total"]
        if count:
            return
        suppliers = [
            (
                "Distribuidora Norte Tech",
                "Mexico",
                "https://proveedor-demo.mx/norte-tech",
                "ventas@norte-tech.example",
                "Mayoreo desde 1 pieza, factura disponible",
                "Paqueteria nacional",
                86,
                1,
                1,
            ),
            (
                "Importadora Gadget Flash",
                "Mexico",
                "https://proveedor-demo.mx/gadget-flash",
                "catalogo@gadget-flash.example",
                "Catalogo CSV, garantia 30 dias",
                "Envio proveedor",
                68,
                0,
                1,
            ),
        ]
        conn.executemany(
            """
            INSERT INTO suppliers
            (name, country, website, contact, terms, shipping_type, reliability, invoices, authorized_assets)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            suppliers,
        )
        products = [
            (
                1,
                "NT-CAB-100",
                "Cable USB-C Nylon 1m Carga Rapida",
                "Voltix",
                "cables",
                79,
                22,
                42,
                "30 dias proveedor",
                1,
                "https://images.unsplash.com/photo-1603539444875-76e7684265f6?auto=format&fit=crop&w=900&q=80",
                "https://proveedor-demo.mx/norte-tech/nt-cab-100",
                1,
                189,
                "medium",
            ),
            (
                1,
                "NT-HUB-441",
                "Hub USB-C 4 Puertos Aluminio",
                "Voltix",
                "hubs",
                169,
                28,
                18,
                "30 dias proveedor",
                2,
                "https://images.unsplash.com/photo-1625842268584-8f3296236761?auto=format&fit=crop&w=900&q=80",
                "https://proveedor-demo.mx/norte-tech/nt-hub-441",
                1,
                349,
                "medium",
            ),
            (
                2,
                "GF-IPH-020",
                "Cargador Compatible iPhone 20W",
                "Apple",
                "cargadores",
                155,
                35,
                9,
                "Sin garantia extendida",
                4,
                "https://images.unsplash.com/photo-1583863788434-e58a36330cf0?auto=format&fit=crop&w=900&q=80",
                "https://proveedor-demo.mx/gadget-flash/gf-iph-020",
                1,
                289,
                "high",
            ),
            (
                1,
                "NT-SOP-77",
                "Soporte Ajustable Para Laptop",
                "ErgoLine",
                "soportes",
                210,
                45,
                3,
                "30 dias proveedor",
                2,
                "https://images.unsplash.com/photo-1612010167108-3e6b327405f0?auto=format&fit=crop&w=900&q=80",
                "https://proveedor-demo.mx/norte-tech/nt-sop-77",
                1,
                399,
                "low",
            ),
        ]
        conn.executemany(
            """
            INSERT INTO supplier_products
            (supplier_id, sku, title, brand, category, cost, supplier_shipping, stock, warranty,
             lead_time_days, image_url, product_url, assets_authorized, market_competition_price, competition_level)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            products,
        )


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
            ORDER BY p.id DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]


def get_product_and_supplier(product_id: int) -> tuple[SupplierProduct, Supplier]:
    with connect() as conn:
        product_row = conn.execute("SELECT * FROM supplier_products WHERE id = ?", (product_id,)).fetchone()
        if not product_row:
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
                   p.image_url, p.product_url, s.name AS supplier_name
            FROM opportunities o
            JOIN supplier_products p ON p.id = o.product_id
            JOIN suppliers s ON s.id = p.supplier_id
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
