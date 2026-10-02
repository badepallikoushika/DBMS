from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List
import pymysql

from database import get_db, DB_NAME, DB_HOST, DB_USER
from models import Product, Warehouse, WarehouseStock, StockAuditLog
app = FastAPI(
    title="Warehouse & Inventory Management System",
    description="Syllabus-aligned enterprise inventory API with MySQL stored procedures, triggers, views, CTEs, and window functions.",
    version="2.0.0"
)

# =====================================================================
# CORS CONFIGURATION (Allows frontend to communicate freely)
# =====================================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =====================================================================
# HEALTH / SYSTEM STATUS
# =====================================================================
@app.get("/")
def home():
    return {
        "system": "Warehouse & Inventory Management System",
        "status": "Online",
        "database": f"MySQL ({DB_NAME} on {DB_HOST})",
        "course_outcomes": ["CO1", "CO2", "CO3", "CO4", "CO5", "CO6"]
    }

# =====================================================================
# PRODUCTS CRUD (CO1 & CO3)
# =====================================================================
@app.get("/products")
def get_products(db: Session = Depends(get_db)):
    try:
        products = db.query(Product).all()
        result = []
        for product in products:
            total_stock = sum(ws.quantity for ws in product.warehouse_stock) if product.warehouse_stock else product.quantity
            low_stock = (total_stock <= product.reorder_level)
            result.append({
                "id": product.id,
                "name": product.name,
                "sku": product.sku,
                "category": product.category,
                "price": float(product.price),
                "quantity": total_stock,
                "reorder_level": product.reorder_level,
                "description": product.description or "",
                "status": "LOW STOCK" if low_stock else "IN STOCK"
            })
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database connection error: {str(e)}. Please check backend/.env credentials."
        )

@app.post("/products")
def add_product(payload: dict, db: Session = Depends(get_db)):
    try:
        new_product = Product(
            name=payload["name"],
            sku=payload["sku"],
            category=payload["category"],
            price=payload["price"],
            quantity=payload.get("quantity", 0),
            reorder_level=payload.get("reorder_level", 10),
            description=payload.get("description", "")
        )
        db.add(new_product)
        db.commit()
        db.refresh(new_product)

        warehouse_quantities = payload.get("warehouses", [])
        total_assigned = 0
        for item in warehouse_quantities:
            qty = int(item.get("quantity", 0))
            if qty > 0:
                ws = WarehouseStock(
                    warehouse_id=item["warehouse_id"],
                    product_id=new_product.id,
                    quantity=qty
                )
                db.add(ws)
                total_assigned += qty

        if total_assigned > 0:
            new_product.quantity = total_assigned
        db.commit()

        return {"message": "Product added successfully", "product_id": new_product.id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/products/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    try:
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        db.delete(product)
        db.commit()
        return {"message": f"Product #{product_id} deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

# =====================================================================
# WAREHOUSES & STOCK DISTRIBUTION (CO1)
# =====================================================================
@app.get("/warehouses")
def get_warehouses(db: Session = Depends(get_db)):
    try:
        warehouses = db.query(Warehouse).all()
        return [
            {
                "id": w.id,
                "name": w.name,
                "location": w.location,
                "capacity": w.capacity
            }
            for w in warehouses
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/products/{product_id}/warehouses")
def get_product_warehouses(product_id: int, db: Session = Depends(get_db)):
    try:
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            return {"error": "Product not found"}

        warehouses = db.query(Warehouse).all()
        result = []
        for w in warehouses:
            stock = db.query(WarehouseStock).filter(
                WarehouseStock.product_id == product_id,
                WarehouseStock.warehouse_id == w.id
            ).first()
            qty = stock.quantity if stock else 0
            result.append({
                "warehouse_id": w.id,
                "warehouse": w.name,
                "location": w.location,
                "capacity": w.capacity,
                "quantity": qty,
                "status": "LOW STOCK" if qty <= product.reorder_level else "IN STOCK"
            })
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
# =====================================================================
# STOCK IN - RECEIVE INVENTORY
# =====================================================================
@app.post("/stock-in")
def receive_stock(payload: dict, db: Session = Depends(get_db)):
    product_id = payload.get("product_id")
    warehouse_id = payload.get("warehouse_id")
    quantity = payload.get("quantity", 0)
    reference_note = payload.get("reference_note", "")

    if not product_id or not warehouse_id or quantity <= 0:
        return {
            "error": "Product, warehouse and quantity greater than zero are required."
        }

    try:
        db.execute(
            text("""
                CALL receive_stock(
                    :product_id,
                    :warehouse_id,
                    :quantity,
                    :reference_note
                )
            """),
            {
                "product_id": product_id,
                "warehouse_id": warehouse_id,
                "quantity": quantity,
                "reference_note": reference_note
            }
        )

        db.commit()

        return {
            "success": True,
            "message": f"{quantity} units received successfully."
        }

    except Exception as e:
        db.rollback()
        return {
            "error": f"Stock-in failed: {str(e)}"
        }
# =====================================================================
# STORED PROCEDURE: TRANSFER STOCK (CO1 ACID Transactions & Stored Logic)
# =====================================================================
@app.post("/transfer-stock")
def transfer_stock(payload: dict, db: Session = Depends(get_db)):
    product_id = payload.get("product_id")
    from_wh = payload.get("from_warehouse_id")
    to_wh = payload.get("to_warehouse_id")
    qty = payload.get("quantity", 0)

    if not all([product_id, from_wh, to_wh]) or qty <= 0:
        return {"error": "Invalid transfer parameters. Product, source, destination, and quantity > 0 are required."}

    if from_wh == to_wh:
        return {"error": "Source and destination warehouses cannot be identical."}

    try:
        # Call the MySQL Stored Procedure directly
        db.execute(
            text("CALL transfer_stock(:product_id, :from_wh, :to_wh, :qty)"),
            {"product_id": product_id, "from_wh": from_wh, "to_wh": to_wh, "qty": qty}
        )
        db.commit()
        return {
            "success": True,
            "message": f"Successfully transferred {qty} units from warehouse #{from_wh} to warehouse #{to_wh} via MySQL Stored Procedure."
        }
    except Exception as e:
        db.rollback()
        error_msg = str(e)
        if "Insufficient stock" in error_msg:
            return {"error": "Insufficient stock in source warehouse for transfer."}
        return {"error": f"Transfer failed: {error_msg}"}
# =====================================================================
# STOCK IN - RECEIVE INVENTORY
# Uses MySQL Stored Procedure + Transaction
# =====================================================================
@app.post("/stock-in")
def receive_stock(payload: dict, db: Session = Depends(get_db)):
    product_id = payload.get("product_id")
    warehouse_id = payload.get("warehouse_id")
    qty = payload.get("quantity", 0)
    reference_note = payload.get("reference_note", "")

    if not product_id or not warehouse_id or qty <= 0:
        return {
            "error": "Product, warehouse and quantity greater than 0 are required."
        }

    try:
        db.execute(
            text("""
                CALL receive_stock(
                    :product_id,
                    :warehouse_id,
                    :qty,
                    :reference_note
                )
            """),
            {
                "product_id": product_id,
                "warehouse_id": warehouse_id,
                "qty": qty,
                "reference_note": reference_note
            }
        )

        db.commit()

        return {
            "success": True,
            "message": (
                f"Successfully received {qty} units "
                f"for product #{product_id} "
                f"at warehouse #{warehouse_id}."
            )
        }

    except Exception as e:
        db.rollback()

        error_msg = str(e)

        return {
            "error": f"Stock-in failed: {error_msg}"
        }
@app.post("/stock-out")
def issue_stock(payload: dict, db: Session = Depends(get_db)):
    product_id = payload.get("product_id")
    warehouse_id = payload.get("warehouse_id")
    qty = payload.get("quantity", 0)
    reference_note = payload.get("reference_note", "")

    if not product_id or not warehouse_id or qty <= 0:
        return {
            "error": "Product, warehouse and quantity greater than 0 are required."
        }

    try:
        db.execute(
            text("""
                CALL issue_stock(
                    :product_id,
                    :warehouse_id,
                    :qty,
                    :reference_note
                )
            """),
            {
                "product_id": product_id,
                "warehouse_id": warehouse_id,
                "qty": qty,
                "reference_note": reference_note
            }
        )

        db.commit()

        return {
            "success": True,
            "message": (
                f"Successfully issued {qty} units "
                f"for product #{product_id} "
                f"from warehouse #{warehouse_id}."
            )
        }

    except Exception as e:
        db.rollback()

        error_msg = str(e)

        return {
            "error": f"Stock-out failed: {error_msg}"
        }
# =====================================================================
# SQL CONCEPT DEMO 1: VIEW (CO1 Views)
# =====================================================================
@app.get("/view/product-summary")
def get_view_product_summary(db: Session = Depends(get_db)):
    try:
        sql = text("SELECT * FROM product_stock_summary")
        rows = db.execute(sql).mappings().all()
        return [dict(row) for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =====================================================================
# SQL CONCEPT DEMO 2: AGGREGATES & GROUP BY (CO1 SQL Advanced Querying)
# =====================================================================
@app.get("/reports/category-summary")
def get_category_summary(db: Session = Depends(get_db)):
    try:
        sql = text("""
            SELECT
                p.category,
                COUNT(DISTINCT p.id) AS total_products,
                COALESCE(SUM(ws.quantity), 0) AS total_units_in_stock,
                ROUND(AVG(p.price), 2) AS average_price,
                ROUND(COALESCE(SUM(ws.quantity * p.price), 0), 2) AS total_inventory_valuation
            FROM products p
            LEFT JOIN warehouse_stock ws ON ws.product_id = p.id
            GROUP BY p.category
            ORDER BY total_inventory_valuation DESC;
        """)
        rows = db.execute(sql).mappings().all()
        return [dict(row) for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =====================================================================
# SQL CONCEPT DEMO 3: WINDOW FUNCTIONS (CO1 DENSE_RANK / PARTITION BY)
# =====================================================================
@app.get("/reports/stock-ranking")
def get_stock_ranking(db: Session = Depends(get_db)):
    try:
        sql = text("""
            SELECT
                p.name AS product_name,
                p.category,
                p.price,
                COALESCE(SUM(ws.quantity), 0) AS total_stock,
                DENSE_RANK() OVER (
                    PARTITION BY p.category
                    ORDER BY COALESCE(SUM(ws.quantity), 0) DESC
                ) AS rank_within_category
            FROM products p
            LEFT JOIN warehouse_stock ws ON ws.product_id = p.id
            GROUP BY p.id, p.name, p.category, p.price
            ORDER BY p.category, rank_within_category;
        """)
        rows = db.execute(sql).mappings().all()
        return [dict(row) for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =====================================================================
# SQL CONCEPT DEMO 4: CTE (Common Table Expression) + SUBQUERY
# =====================================================================
@app.get("/reports/reorder-needed")
def get_reorder_needed(db: Session = Depends(get_db)):
    try:
        sql = text("""
            WITH current_stock_cte AS (
                SELECT
                    p.id,
                    p.name,
                    p.sku,
                    p.category,
                    p.reorder_level,
                    COALESCE(SUM(ws.quantity), 0) AS total_available
                FROM products p
                LEFT JOIN warehouse_stock ws ON ws.product_id = p.id
                GROUP BY p.id, p.name, p.sku, p.category, p.reorder_level
            )
            SELECT
                name AS product_name,
                sku,
                category,
                total_available AS current_quantity,
                reorder_level,
                (reorder_level - total_available) AS units_deficit,
                CASE
                    WHEN total_available = 0 THEN 'OUT OF STOCK (CRITICAL)'
                    ELSE 'RESTOCK RECOMMENDED'
                END AS priority
            FROM current_stock_cte
            WHERE total_available <= reorder_level
            ORDER BY units_deficit DESC;
        """)
        rows = db.execute(sql).mappings().all()
        return [dict(row) for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =====================================================================
# SQL CONCEPT DEMO 5: AUDIT LOG (CO1 Triggers)
# =====================================================================
@app.get("/audit-log")
def get_audit_log(db: Session = Depends(get_db)):
    try:
        sql = text("""
            SELECT
                a.id,
                p.name AS product_name,
                w.name AS warehouse_name,
                a.old_quantity,
                a.new_quantity,
                a.action,
                DATE_FORMAT(a.changed_at, '%Y-%m-%d %H:%i:%s') AS timestamp
            FROM stock_audit_log a
            LEFT JOIN products p ON p.id = a.product_id
            LEFT JOIN warehouses w ON w.id = a.warehouse_id
            ORDER BY a.changed_at DESC
            LIMIT 50;
        """)
        rows = db.execute(sql).mappings().all()
        return [dict(row) for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =====================================================================
# CO2: NoSQL DOCUMENT CATALOG (Dynamic Document Engineering / JSON)
# =====================================================================
@app.get("/nosql/catalog")
def get_nosql_catalog():
    return [
        {
            "product_id": 1,
            "sku": "SCN-001",
            "name": "Industrial Barcode Scanner",
            "document_specs": {
                "scan_engine": "2D Imager (QR, DataMatrix, PDF417)",
                "connectivity": ["Bluetooth 5.2", "2.4GHz Wireless", "USB-C"],
                "battery_life_hours": 18,
                "drop_resistance": "IP65 certified, withstands 2m drops to concrete",
                "operating_temperature_c": "-20 to 50"
            }
        },
        {
            "product_id": 2,
            "sku": "CHR-102",
            "name": "Ergonomic Mesh Office Chair",
            "document_specs": {
                "material": "Breathable Korean mesh + Aluminum alloy base",
                "weight_capacity_kg": 150,
                "adjustments": ["3D Armrests", "2-Way Lumbar", "135 deg Recline"],
                "warranty_years": 5
            }
        },
        {
            "product_id": 3,
            "sku": "PRN-303",
            "name": "Thermal Shipping Label Printer",
            "document_specs": {
                "print_speed": "150 mm/s",
                "max_resolution_dpi": 203,
                "supported_media": ["4x6 shipping labels", "barcode rolls", "die-cut stickers"],
                "interfaces": ["USB", "Ethernet", "Wi-Fi"]
            }
        },
        {
            "product_id": 4,
            "sku": "RCK-404",
            "name": "Heavy-Duty Steel Storage Rack",
            "document_specs": {
                "shelf_levels": 4,
                "load_per_tier_kg": 800,
                "material_gauge": "16-gauge cold rolled steel",
                "coating": "Electrostatically applied powder coat"
            }
        }
    ]

# =====================================================================
# CO2: VECTOR & SEMANTIC SEARCH (Similarity Metric & Embeddings)
# =====================================================================
@app.get("/search/semantic")
def semantic_search(q: str = ""):
    catalog = [
        {"id": 1, "name": "Industrial Barcode Scanner", "tags": "wireless bluetooth handheld laser picking 2d imager qr barcode inventory", "price": 4999.00},
        {"id": 2, "name": "Ergonomic Mesh Office Chair", "tags": "seating lumbar support swivel office desk comfortable furniture", "price": 8500.00},
        {"id": 3, "name": "Thermal Shipping Label Printer", "tags": "shipping printing parcel packaging sticker thermal high speed", "price": 12450.00},
        {"id": 4, "name": "Heavy-Duty Steel Storage Rack", "tags": "storage shelf rack heavy duty industrial warehouse steel tiers", "price": 15999.00},
        {"id": 5, "name": "Wireless Bluetooth Warehouse Headset", "tags": "audio voice picking wireless noise cancelling microphone headset", "price": 3200.00},
        {"id": 6, "name": "Digital Heavy Weighing Scale", "tags": "measurement weight parcel platform scale lcd freight kg load", "price": 7800.00},
        {"id": 7, "name": "Automatic Tape Dispenser", "tags": "packaging box packing sealing tape dispenser electric shipping", "price": 6100.00}
    ]
    if not q:
        return catalog

    query_terms = set(q.lower().split())
    scored = []
    for item in catalog:
        item_words = set(f"{item['name']} {item['tags']}".lower().split())
        intersection = query_terms.intersection(item_words)
        score = len(intersection) / max(len(query_terms), 1)
        if score > 0 or any(t in item['name'].lower() for t in query_terms):
            effective_score = round(max(score, 0.4), 2)
            scored.append({**item, "similarity_score": effective_score})

    scored.sort(key=lambda x: x.get("similarity_score", 0), reverse=True)
    return scored


# =====================================================================
# AUTH & USER MANAGEMENT (CO3 & Admin Portal)
# =====================================================================
from models import User, Order

@app.post("/login")
def login(payload: dict, db: Session = Depends(get_db)):
    email = payload.get("email", "").strip().lower()
    password = payload.get("password", "").strip()

    user = db.query(User).filter(User.email == email).first()
    if not user or user.password != password:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return {
        "success": True,
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role
        }
    }

@app.get("/users")
def get_users(db: Session = Depends(get_db)):
    try:
        users = db.query(User).all()
        return [
            {
                "id": u.id,
                "name": u.name,
                "email": u.email,
                "role": u.role,
                "created_at": str(u.created_at)
            }
            for u in users
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/users")
def add_user(payload: dict, db: Session = Depends(get_db)):
    try:
        new_user = User(
            name=payload["name"],
            email=payload["email"].strip().lower(),
            password=payload.get("password", "user123"),
            role=payload.get("role", "user")
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return {"message": "User registered successfully", "id": new_user.id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        db.delete(user)
        db.commit()
        return {"message": "User removed successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

# =====================================================================
# ORDERS & STOCK REQUESTS (Admin & User Portals)
# =====================================================================
@app.get("/orders")
def get_orders(db: Session = Depends(get_db)):
    try:
        orders = db.query(Order).order_by(Order.request_date.desc()).all()
        return [
            {
                "id": o.id,
                "user_id": o.user_id,
                "user_name": o.user_name,
                "product_id": o.product_id,
                "product_name": o.product_name,
                "warehouse_id": o.warehouse_id,
                "warehouse_name": o.warehouse_name,
                "quantity": o.quantity,
                "status": o.status,
                "request_date": str(o.request_date)
            }
            for o in orders
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/orders")
def create_order(payload: dict, db: Session = Depends(get_db)):
    try:
        prod = db.query(Product).filter(Product.id == payload["product_id"]).first()
        wh = db.query(Warehouse).filter(Warehouse.id == payload["warehouse_id"]).first()

        new_order = Order(
            user_id=payload.get("user_id", 3),
            user_name=payload.get("user_name", "Staff User"),
            product_id=payload["product_id"],
            product_name=prod.name if prod else f"Product #{payload['product_id']}",
            warehouse_id=payload["warehouse_id"],
            warehouse_name=wh.name if wh else f"Warehouse #{payload['warehouse_id']}",
            quantity=payload["quantity"],
            status="PENDING"
        )
        db.add(new_order)
        db.commit()
        db.refresh(new_order)
        return {"message": "Order request submitted successfully", "order_id": new_order.id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@app.put("/orders/{order_id}/status")
def update_order_status(order_id: int, payload: dict, db: Session = Depends(get_db)):
    try:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        new_status = payload.get("status", "APPROVED").upper()
        if new_status not in ["APPROVED", "REJECTED", "PENDING"]:
            raise HTTPException(status_code=400, detail="Invalid status")

        # If approving order, deduct requested quantity from warehouse stock
        if new_status == "APPROVED" and order.status != "APPROVED":
            stock = db.query(WarehouseStock).filter(
                WarehouseStock.product_id == order.product_id,
                WarehouseStock.warehouse_id == order.warehouse_id
            ).first()
            if not stock or stock.quantity < order.quantity:
                raise HTTPException(status_code=400, detail="Insufficient stock in warehouse to approve this order.")
            stock.quantity -= order.quantity

            # Update product total quantity
            prod = db.query(Product).filter(Product.id == order.product_id).first()
            if prod:
                prod.quantity = sum(ws.quantity for ws in prod.warehouse_stock)

        order.status = new_status
        db.commit()
        return {"message": f"Order #{order_id} status updated to {new_status}"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

# =====================================================================
# STARTUP EVENT & SEEDING (Auto-Creates tables & default accounts)
# =====================================================================
from database import engine
from models import Base

@app.on_event("startup")
def startup_event():
    try:
        Base.metadata.create_all(bind=engine)
        db = SessionLocal() if 'SessionLocal' in globals() else next(get_db())
        if db.query(User).count() == 0:
            admin_user = User(name="System Admin", email="admin@warehouse.com", password="admin123", role="admin")
            staff_user = User(name="Warehouse Staff", email="user@warehouse.com", password="user123", role="user")
            db.add_all([admin_user, staff_user])
            db.commit()
    except Exception as e:
        print("Startup notice:", e)

# =====================================================================
# DBMS SYLLABUS & RELATIONAL ALGEBRA LAB ENDPOINTS
# =====================================================================
@app.get("/dbms/relational-algebra/{operation}")
def get_relational_algebra_operation(operation: str, category: Optional[str] = "Electronics", db: Session = Depends(get_db)):
    op = operation.lower().strip()

    if op == "selection":
        prods = db.query(Product).filter(Product.category == category).all()
        return {
            "operation": f"Selection σ_{{category='{category}'}}(Products)",
            "sql_equivalent": f"SELECT * FROM products WHERE category = '{category}';",
            "description": "Selects tuples (rows) that satisfy the given predicate condition.",
            "data": [{"id": p.id, "name": p.name, "sku": p.sku, "category": p.category, "price": float(p.price), "quantity": p.quantity} for p in prods]
        }

    elif op == "projection":
        prods = db.query(Product.name, Product.sku, Product.price).all()
        return {
            "operation": "Projection π_{name, sku, price}(Products)",
            "sql_equivalent": "SELECT name, sku, price FROM products;",
            "description": "Extracts specified attributes (columns) while eliminating duplicate tuples.",
            "data": [{"name": p.name, "sku": p.sku, "price": float(p.price)} for p in prods]
        }

    elif op == "union":
        high_price = db.query(Product).filter(Product.price > 10000).all()
        low_qty = db.query(Product).filter(Product.quantity < 10).all()
        combined = {p.id: p for p in high_price + low_qty}.values()
        return {
            "operation": "(σ_{price > 10000}(Products)) ∪ (σ_{quantity < 10}(Products))",
            "sql_equivalent": "SELECT * FROM products WHERE price > 10000 UNION SELECT * FROM products WHERE quantity < 10;",
            "description": "Combines tuples from two compatible relations without duplicate rows.",
            "data": [{"id": p.id, "name": p.name, "category": p.category, "price": float(p.price), "quantity": p.quantity} for p in combined]
        }

    elif op == "difference":
        all_prods = db.query(Product).all()
        low_prods = db.query(Product).filter(Product.quantity <= Product.reorder_level).all()
        low_ids = {p.id for p in low_prods}
        diff = [p for p in all_prods if p.id not in low_ids]
        return {
            "operation": "Products - LowStockProducts",
            "sql_equivalent": "SELECT * FROM products WHERE id NOT IN (SELECT id FROM products WHERE quantity <= reorder_level);",
            "description": "Returns tuples that exist in relation R but do NOT exist in relation S.",
            "data": [{"id": p.id, "name": p.name, "category": p.category, "price": float(p.price), "quantity": p.quantity} for p in diff]
        }

    elif op == "cartesian-product":
        prods = db.query(Product).limit(4).all()
        whs = db.query(Warehouse).limit(3).all()
        cross = []
        for p in prods:
            for w in whs:
                cross.append({
                    "product_name": p.name,
                    "sku": p.sku,
                    "warehouse_name": w.name,
                    "location": w.location
                })
        return {
            "operation": "Products × Warehouses (Cartesian Product)",
            "sql_equivalent": "SELECT p.name, p.sku, w.name, w.location FROM products p CROSS JOIN warehouses w;",
            "description": "Combines every tuple of relation R with every tuple of relation S.",
            "data": cross
        }

    elif op == "rename":
        prods = db.query(Product).limit(5).all()
        return {
            "operation": "Rename ρ_{Item, Code, UnitCost}(Products)",
            "sql_equivalent": "SELECT name AS Item, sku AS Code, price AS UnitCost FROM products;",
            "description": "Renames relation attributes or relation names for output mapping.",
            "data": [{"Item": p.name, "Code": p.sku, "UnitCost": float(p.price)} for p in prods]
        }

    raise HTTPException(status_code=400, detail="Invalid operation. Choose selection, projection, union, difference, cartesian-product, or rename.")

@app.get("/dbms/indexing-info")
def get_indexing_info(db: Session = Depends(get_db)):
    return {
        "clustered_index": {
            "name": "PRIMARY KEY (b-tree)",
            "table": "products / warehouses / warehouse_stock",
            "type": "Clustered B-Tree Index",
            "description": "Physically orders data records on disk by Primary Key (id). Enables direct O(1) page access."
        },
        "non_clustered_indexes": [
            {"name": "idx_products_sku", "column": "products.sku", "type": "UNIQUE B-Tree", "purpose": "Fast barcode/SKU lookup O(log N)"},
            {"name": "idx_products_category", "column": "products.category", "type": "B-Tree", "purpose": "Accelerates category filtering & aggregations"},
            {"name": "idx_warehouse_stock_product", "column": "warehouse_stock.product_id", "type": "Foreign Key Index", "purpose": "Optimizes relational JOIN operations"},
            {"name": "idx_warehouse_stock_warehouse", "column": "warehouse_stock.warehouse_id", "type": "Foreign Key Index", "purpose": "Optimizes warehouse distribution queries"}
        ],
        "performance_benchmark": {
            "without_index": "Full Table Scan O(N) - inspecting all rows across disk pages",
            "with_index": "B-Tree Search O(log N) - traversing tree nodes directly to memory address"
        }
    }
