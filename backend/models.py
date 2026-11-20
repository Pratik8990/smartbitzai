from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Text
from backend.database import Base

class DBCustomer(Base):
    __tablename__ = "customers"

    id = Column(String(50), primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    phone = Column(String(50), nullable=True)
    tier = Column(String(50), default="Standard")
    spend = Column(Float, default=0.0)

class DBCustomerAuditLog(Base):
    __tablename__ = "customer_audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(String(50), nullable=False, index=True)
    action = Column(String(20), nullable=False)
    actor = Column(String(50), nullable=False)
    changed_fields = Column(Text, nullable=False, default="[]")
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
    )

class DBProduct(Base):
    __tablename__ = "products"

    id = Column(String(50), primary_key=True, index=True)
    sku = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(150), nullable=False)
    category = Column(String(100), default="General")
    price = Column(Float, nullable=False)
    stock = Column(Integer, default=0)
    min_stock = Column(Integer, default=5)

class DBInvoice(Base):
    __tablename__ = "invoices"

    id = Column(String(50), primary_key=True, index=True)
    customer_id = Column(String(50), ForeignKey("customers.id"), nullable=True)
    customer_name = Column(String(100))
    date = Column(String(50))
    amount = Column(Float)
    status = Column(String(20), default="PENDING")
    item = Column(String(150))
    qty = Column(Integer, default=1)
    unit_price = Column(Float)

class DBExpense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String(50))
    description = Column(String(255), nullable=False)
    category = Column(String(100))
    amount = Column(Float, nullable=False)
    vendor = Column(String(100))
    anomaly = Column(Boolean, default=False)

class DBArchivedExpense(Base):
    __tablename__ = "archived_expenses"

    expense_id = Column(Integer, ForeignKey("expenses.id"), primary_key=True)
    archived_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False)

class DBUser(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(50), default="Admin")
    is_active = Column(Boolean, default=True)