from sqlalchemy import Column, Integer, String, Numeric, ForeignKey, DateTime, Text, func
from sqlalchemy.orm import relationship
from database import Base

# =========================
# PRODUCT (CO1: Relational Entity)
# =========================
class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    sku = Column(String(50), unique=True, nullable=False, index=True)
    category = Column(String(100), nullable=False, index=True)
    price = Column(Numeric(10, 2), nullable=False)
    quantity = Column(Integer, nullable=False, default=0)
    reorder_level = Column(Integer, nullable=False, default=10)
    description = Column(Text, nullable=True)

    warehouse_stock = relationship(
        "WarehouseStock",
        back_populates="product",
        cascade="all, delete-orphan"
    )

# =========================
# WAREHOUSE (CO1: Relational Entity)
# =========================
class Warehouse(Base):
    __tablename__ = "warehouses"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    location = Column(String(150), nullable=False)
    capacity = Column(Integer, nullable=False, default=1000)

    stock = relationship(
        "WarehouseStock",
        back_populates="warehouse",
        cascade="all, delete-orphan"
    )

# =========================
# WAREHOUSE STOCK (Associative Table M:N with composite unique constraint)
# =========================
class WarehouseStock(Base):
    __tablename__ = "warehouse_stock"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    quantity = Column(Integer, nullable=False, default=0)

    warehouse = relationship("Warehouse", back_populates="stock")
    product = relationship("Product", back_populates="warehouse_stock")

# =========================
# STOCK AUDIT LOG (Populated by MySQL Trigger)
# =========================
class StockAuditLog(Base):
    __tablename__ = "stock_audit_log"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    product_id = Column(Integer, nullable=True)
    warehouse_id = Column(Integer, nullable=True)
    old_quantity = Column(Integer, nullable=True)
    new_quantity = Column(Integer, nullable=True)
    action = Column(String(50), default="UPDATE")
    changed_at = Column(DateTime, server_default=func.now())


# =========================
# USERS (CO1 & CO3 Authentication & RBAC)
# =========================
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False, index=True)
    password = Column(String(100), nullable=False)
    role = Column(String(20), nullable=False, default="user")
    created_at = Column(DateTime, server_default=func.now())

# =========================
# ORDERS / STOCK REQUESTS
# =========================
class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    user_name = Column(String(100), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    product_name = Column(String(100), nullable=False)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False)
    warehouse_name = Column(String(100), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="PENDING")
    request_date = Column(DateTime, server_default=func.now())
class StockIn(Base):
    __tablename__ = "stock_in"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    product_id = Column(
        Integer,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False
    )
    warehouse_id = Column(
        Integer,
        ForeignKey("warehouses.id", ondelete="CASCADE"),
        nullable=False
    )
    quantity = Column(Integer, nullable=False)
    received_date = Column(
        DateTime,
        server_default=func.now()
    )
    reference_note = Column(String(255), nullable=True)