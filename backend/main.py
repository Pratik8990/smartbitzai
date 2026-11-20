import importlib
import io
import json
import logging
import os
import re
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from datetime import date as Date
from pathlib import Path
from typing import Any, Dict, List

from backend.config import load_local_env

load_local_env()

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field, field_validator
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

import backend.auth as auth
from backend.database import Base, engine, get_db
import backend.models as models

logger = logging.getLogger(__name__)

app = FastAPI(
    title="SmartBiz AI Backend",
    version="2.4.0",
    description="FastAPI Ledger, Inventory, Automated Invoicing, and AI Assistant with MySQL"
)

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "SMARTBIZ_CORS_ORIGINS",
        "http://127.0.0.1:5500,http://localhost:5500,"
        "http://127.0.0.1:5501,http://localhost:5501",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Automatically create all tables in MySQL if they do not exist
Base.metadata.create_all(bind=engine)


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=12, max_length=128)


@app.post("/api/auth/register", tags=["Authentication"])
def register_user(
    payload: UserCreate,
    current_user: models.DBUser = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role.lower() != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    existing = db.query(models.DBUser).filter(
        (models.DBUser.username == payload.username) | (models.DBUser.email == payload.email)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username or email already registered")

    new_user = models.DBUser(
        username=payload.username,
        email=payload.email,
        hashed_password=auth.get_password_hash(payload.password),
        role="User",
        is_active=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": f"User {new_user.username} created successfully"}


@app.post("/api/auth/token", tags=["Authentication"])
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.DBUser).filter(models.DBUser.username == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = auth.create_access_token(data={"sub": user.username, "role": user.role})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": user.username,
        "role": user.role,
    }


@app.get("/api/auth/me", tags=["Authentication"])
def get_current_user_profile(current_user: models.DBUser = Depends(auth.get_current_user)):
    return {
        "username": current_user.username,
        "email": current_user.email,
        "role": current_user.role,
    }


@app.get("/api/health", tags=["Health"])
def health_check():
    return {"status": "ok"}


# --- Pydantic Schemas ---
class CustomerBase(BaseModel):
    name: str
    email: str
    phone: str
    tier: str = "Standard"

    @field_validator("name")
    @classmethod
    def validate_customer_name(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Enter a company or client name with at least 2 characters.")
        if len(value) > 100:
            raise ValueError("Company or client name must be 100 characters or fewer.")
        if "@" in value:
            raise ValueError("This looks like an email address. Enter a company or client name here.")
        if re.fullmatch(r"[+0-9().\-\s]+", value) and sum(character.isdigit() for character in value) >= 7:
            raise ValueError("This looks like a phone number. Enter the phone number in the Phone Number field.")
        return value

    @field_validator("email")
    @classmethod
    def validate_customer_email(cls, value: str) -> str:
        value = value.strip().lower()
        if len(value) > 100 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("Enter an email address in the format name@company.com.")
        return value

    @field_validator("phone")
    @classmethod
    def validate_customer_phone(cls, value: str) -> str:
        value = value.strip()
        if not re.fullmatch(r"[+0-9().\-\s]+", value):
            raise ValueError("Enter a phone number using digits; +, spaces, parentheses, dots, and hyphens are allowed.")
        digit_count = sum(character.isdigit() for character in value)
        if not 7 <= digit_count <= 15:
            raise ValueError("Phone number must contain between 7 and 15 digits.")
        return value

    @field_validator("tier")
    @classmethod
    def validate_customer_tier(cls, value: str) -> str:
        value = value.strip()
        if value not in {"Enterprise", "Growth", "Standard"}:
            raise ValueError("Choose Enterprise, Growth, or Standard.")
        return value

class CustomerCreate(CustomerBase):
    pass

class Customer(BaseModel):
    id: str
    name: str
    email: str
    phone: str | None = None
    tier: str = "Standard"
    spend: float = 0.0

    class Config:
        from_attributes = True

class CustomerAuditEntry(BaseModel):
    id: int
    action: str
    actor: str
    changed_fields: List[str]
    created_at: datetime

class ProductBase(BaseModel):
    name: str
    category: str
    price: float
    stock: int
    min_stock: int = 5

class ProductCreate(ProductBase):
    pass

class Product(ProductBase):
    id: str
    sku: str
    class Config:
        from_attributes = True

class InvoiceCreate(BaseModel):
    customer_id: str
    product_id: str
    issue_date: date
    quantity: int = Field(gt=0)

class InvoiceUpdate(InvoiceCreate):
    pass

class Invoice(BaseModel):
    id: str
    customer_id: str
    customer_name: str
    date: str
    amount: float
    status: str
    item: str
    qty: int
    unit_price: float
    class Config:
        from_attributes = True

class ExpenseCreate(BaseModel):
    date: Date | None = None
    description: str
    category: str
    amount: float
    vendor: str

class ExpenseUpdate(ExpenseCreate):
    date: Date

class Expense(BaseModel):
    id: int
    date: str
    description: str
    category: str
    amount: float
    vendor: str
    anomaly: bool
    class Config:
        from_attributes = True

class AIQueryRequest(BaseModel):
    query: str

class AIQueryResponse(BaseModel):
    text: str
    meta: str


BUSINESS_DOCS_DIR = Path(__file__).resolve().parents[1] / "business_docs"


def extract_pdf_text(path: Path) -> str:
    try:
        import importlib

        PdfReader = importlib.import_module("pypdf").PdfReader
    except (ImportError, ModuleNotFoundError):
        return ""

    try:
        reader = PdfReader(str(path))
        pages = []
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                pages.append(text)
        return "\n\n".join(pages)
    except Exception:
        return ""


def load_business_documents() -> List[Dict[str, str]]:
    docs_dir = BUSINESS_DOCS_DIR
    if not docs_dir.exists():
        return []

    supported_exts = {".txt", ".md", ".markdown", ".pdf"}
    documents: List[Dict[str, str]] = []

    for file_path in sorted(docs_dir.rglob("*")):
        if not file_path.is_file() or file_path.suffix.lower() not in supported_exts:
            continue

        if file_path.suffix.lower() == ".pdf":
            text = extract_pdf_text(file_path)
        else:
            text = file_path.read_text(encoding="utf-8", errors="ignore")

        if text and text.strip():
            documents.append({
                "source": file_path.name,
                "content": text.strip(),
            })

    return documents


def fallback_document_answer(question: str) -> str | None:
    q = question.lower()
    if any(term in q for term in ("refund", "return policy", "returns policy")):
        return "According to the SmartBiz business policy, enterprise hardware items may be returned within 30 days if they are unused. Cloud SaaS and custom deployment work are non-refundable once provisioning begins. If there is a billing error, finance may issue a credit instead of a refund."

    if any(term in q for term in ("inventory policy", "restock", "reorder policy")):
        return "The inventory policy requires restocking when stock reaches the minimum threshold, and critical items with 5 units or fewer should be reviewed within 48 hours. The operations team should log all restocks in the FastAPI ledger before approving new shipments."

    if any(term in q for term in ("overdue invoice", "receivables policy", "late payment policy", "follow up on invoices")):
        return "Receivables older than 14 days should be followed up with a customer success reminder. Invoices with unusual cost spikes over the baseline should be escalated to finance for approval before payment."

    if any(term in q for term in ("expense policy", "budget approval policy", "marketing budget")):
        return "The sales handbook requires finance and operations to review revenue trends before approving budget increases. Any unusual expense above the usual baseline should be flagged for finance review."

    return None


def ensure_business_rag_index() -> None:
    api_key = os.getenv("LLM_API_KEY", "").strip()
    if not api_key:
        logger.info("Skipping Gemini RAG indexing because LLM_API_KEY is not configured.")
        return

    try:
        Chroma = importlib.import_module("langchain_chroma").Chroma
        Document = importlib.import_module("langchain_core.documents").Document
        RecursiveCharacterTextSplitter = importlib.import_module(
            "langchain_text_splitters"
        ).RecursiveCharacterTextSplitter
        GoogleGenerativeAIEmbeddings = importlib.import_module(
            "langchain_google_genai"
        ).GoogleGenerativeAIEmbeddings
    except (ImportError, ModuleNotFoundError):
        logger.warning("Skipping Gemini RAG indexing: install backend/requirements-rag.txt.")
        return

    docs = load_business_documents()
    if not docs:
        logger.warning("Skipping Gemini RAG indexing because no supported business documents were found.")
        return

    persist_dir = Path(__file__).resolve().parents[1] / ".chromadb"
    persist_dir.mkdir(exist_ok=True)

    documents = [
        Document(
            page_content=item["content"],
            metadata={"source": item["source"]},
        )
        for item in docs
    ]
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
    chunks = splitter.split_documents(documents)
    embeddings = GoogleGenerativeAIEmbeddings(
        model=os.getenv("GEMINI_EMBEDDING_MODEL", "models/gemini-embedding-001"),
        google_api_key=api_key,
    )

    try:
        vector_store = Chroma(
            collection_name="smartbiz_business_docs_gemini",
            embedding_function=embeddings,
            persist_directory=str(persist_dir),
        )
        existing_ids = vector_store.get(include=[])["ids"]
        if existing_ids:
            vector_store.delete(ids=existing_ids)
        chunk_ids = [
            f"{chunk.metadata['source']}:{index}"
            for index, chunk in enumerate(chunks)
        ]
        vector_store.add_documents(documents=chunks, ids=chunk_ids)
        logger.info("Indexed %d business-document chunks with Gemini embeddings.", len(chunks))
    except Exception as exc:
        logger.warning("Gemini RAG indexing failed (%s).", type(exc).__name__)
        return


def ask_langchain_rag(question: str) -> str | None:
    api_key = os.getenv("LLM_API_KEY", "").strip()
    if not api_key:
        return None

    try:
        Chroma = importlib.import_module("langchain_chroma").Chroma
        GoogleGenerativeAIEmbeddings = importlib.import_module(
            "langchain_google_genai"
        ).GoogleGenerativeAIEmbeddings
        ChatGoogleGenerativeAI = importlib.import_module(
            "langchain_google_genai"
        ).ChatGoogleGenerativeAI
    except (ImportError, ModuleNotFoundError):
        logger.warning("Gemini RAG is unavailable: install backend/requirements-rag.txt.")
        return None

    persist_dir = Path(__file__).resolve().parents[1] / ".chromadb"
    if not persist_dir.exists():
        return None

    try:
        embeddings = GoogleGenerativeAIEmbeddings(
            model=os.getenv("GEMINI_EMBEDDING_MODEL", "models/gemini-embedding-001"),
            google_api_key=api_key,
        )
        vector_store = Chroma(
            collection_name="smartbiz_business_docs_gemini",
            embedding_function=embeddings,
            persist_directory=str(persist_dir),
        )
        relevant_docs = vector_store.as_retriever(
            search_kwargs={"k": 4}
        ).invoke(question)
        if not relevant_docs:
            return None

        retrieved_context = "\n\n".join(
            f"Source: {doc.metadata.get('source', 'business document')}\n{doc.page_content}"
            for doc in relevant_docs
        )
        llm = ChatGoogleGenerativeAI(
            model=os.getenv("LLM_MODEL", "gemini-2.0-flash"),
            google_api_key=api_key,
            temperature=0.2,
        )
        result = llm.invoke(
            "Answer the question using only the supplied business-document excerpts. "
            "If they do not contain the answer, say so clearly.\n\n"
            f"Question: {question}\n\nDocument excerpts:\n{retrieved_context}"
        )
        answer = result.content
        if isinstance(answer, list):
            answer = "\n".join(
                item.get("text", "") if isinstance(item, dict) else str(item)
                for item in answer
            )
        return answer.strip() if isinstance(answer, str) and answer.strip() else None
    except Exception as exc:
        logger.warning("Gemini RAG query failed (%s).", type(exc).__name__)
        return None


def build_business_context(db: Session) -> Dict[str, Any]:
    customers = db.query(models.DBCustomer).all()
    products = db.query(models.DBProduct).all()
    invoices = db.query(models.DBInvoice).all()
    expenses = active_expenses_query(db).all()

    return {
        "summary": {
            "customer_count": len(customers),
            "product_count": len(products),
            "invoice_count": len(invoices),
            "expense_count": len(expenses),
            "total_revenue": round(sum(item.amount for item in invoices if item.status == "PAID"), 2),
            "pending_receivables": round(sum(item.amount for item in invoices if item.status not in {"PAID", "VOID"}), 2),
            "total_expense": round(sum(item.amount for item in expenses), 2),
        },
        "top_customers": [
            {"name": c.name, "tier": c.tier, "spend": c.spend} for c in sorted(customers, key=lambda x: x.spend or 0, reverse=True)[:5]
        ],
        "product_catalog": [
            {
                "name": p.name,
                "category": p.category,
                "price": p.price,
                "stock": p.stock,
                "minimum_stock": p.min_stock,
            }
            for p in products
        ],
        "inventory_alerts": [
            {"name": p.name, "stock": p.stock, "min_stock": p.min_stock, "price": p.price}
            for p in products if p.stock <= p.min_stock
        ],
        "recent_invoices": [
            {"id": i.id, "customer": i.customer_name, "amount": i.amount, "status": i.status, "date": i.date}
            for i in sorted(invoices, key=lambda x: x.date or "", reverse=True)[:5]
        ],
        "recent_expenses": [
            {"date": e.date, "description": e.description, "vendor": e.vendor, "amount": e.amount, "category": e.category}
            for e in sorted(expenses, key=lambda x: x.date or "", reverse=True)[:5]
        ],
    }


def ask_llm_business_question(question: str, context: Dict[str, Any]) -> str | None:
    openai_key = os.getenv("OPENAI_API_KEY")
    llm_key = os.getenv("LLM_API_KEY")
    api_key = llm_key or openai_key
    if not api_key:
        return None

    api_url = os.getenv("LLM_API_URL") or os.getenv("OPENAI_API_URL")
    if not api_url:
        api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

    model = os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL") or "gemini-2.0-flash"

    prompt = (
        "You are SmartBiz AI helping answer business operations questions. "
        "Use the following business context only, and answer in a concise but useful way.\n\n"
        f"Question: {question}\n\nBusiness context:\n{json.dumps(context, default=str)}\n\n"
        "If the data does not contain enough evidence, say so clearly and give a likely business recommendation."
    )

    try:
        if "openai.com" in api_url:
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
            }
            request = urllib.request.Request(
                api_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": "Bearer " + api_key,
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"].strip()

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2},
        }
        request_url = f"{api_url}?key={api_key}"
        request = urllib.request.Request(
            request_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except urllib.error.HTTPError as exc:
        logger.warning("LLM request was rejected with HTTP %s.", exc.code)
        return None
    except (TimeoutError, urllib.error.URLError) as exc:
        logger.warning("LLM request failed (%s).", type(exc).__name__)
        return None
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        logger.warning("LLM response could not be parsed (%s).", type(exc).__name__)
        return None

def active_expenses_query(db: Session):
    archived_ids = db.query(models.DBArchivedExpense.expense_id)
    return db.query(models.DBExpense).filter(~models.DBExpense.id.in_(archived_ids))


# --- Auto Seed on Startup ---
@app.on_event("startup")
def seed_database():
    ensure_business_rag_index()
    if os.getenv("SMARTBIZ_SEED_DEMO_DATA", "").lower() not in {"1", "true", "yes"}:
        return

    db = next(get_db())
    if db.query(models.DBCustomer).count() == 0:
        customers = [
            models.DBCustomer(id="CUST-101", name="Acme Global Corp", email="billing@acmeglobal.com", phone="+1 555-0192", tier="Enterprise", spend=28400.0),
            models.DBCustomer(id="CUST-102", name="Nexus Dynamic Labs", email="finance@nexuslabs.io", phone="+1 555-0143", tier="Growth", spend=12600.0),
            models.DBCustomer(id="CUST-103", name="Vanguard Retail Ltd", email="accounts@vanguard.org", phone="+1 555-0188", tier="Standard", spend=4350.0),
            models.DBCustomer(id="CUST-104", name="Horizon Cloud Tech", email="pay@horizontech.co", phone="+1 555-0112", tier="Enterprise", spend=23670.0),
        ]
        db.add_all(customers)

    if db.query(models.DBProduct).count() == 0:
        products = [
            models.DBProduct(id="PROD-01", sku="SKU-104", name="Ergonomic Standing Desk Pro", category="Hardware", price=680.00, stock=12, min_stock=5),
            models.DBProduct(id="PROD-02", sku="SKU-772", name="Wireless Noise Cancelling Pods", category="Peripherals", price=149.00, stock=3, min_stock=8),
            models.DBProduct(id="PROD-03", sku="SKU-890", name="USB-C Dual 4K Display Dock", category="Peripherals", price=219.00, stock=2, min_stock=6),
            models.DBProduct(id="PROD-04", sku="SKU-312", name="Annual Cloud Architecture SLA", category="Services", price=1500.00, stock=85, min_stock=10),
        ]
        db.add_all(products)

    if db.query(models.DBInvoice).count() == 0:
        invoices = [
            models.DBInvoice(id="INV-2026-001", customer_id="CUST-101", customer_name="Acme Global Corp", date="2026-10-12", amount=2720.00, status="PAID", item="Ergonomic Standing Desk Pro", qty=4, unit_price=680.00),
            models.DBInvoice(id="INV-2026-002", customer_id="CUST-102", customer_name="Nexus Dynamic Labs", date="2026-10-10", amount=1500.00, status="PENDING", item="Annual Cloud Architecture SLA", qty=1, unit_price=1500.00),
            models.DBInvoice(id="INV-2026-003", customer_id="CUST-103", customer_name="Vanguard Retail Ltd", date="2026-09-28", amount=1490.00, status="OVERDUE", item="Wireless Noise Cancelling Pods", qty=10, unit_price=149.00),
        ]
        db.add_all(invoices)

    if db.query(models.DBExpense).count() == 0:
        expenses = [
            models.DBExpense(date="2026-10-14", description="AWS Production Cluster Hosting", category="SaaS & Cloud", amount=1250.00, vendor="Amazon Web Services", anomaly=True),
            models.DBExpense(date="2026-10-11", description="Google Workspace Enterprise", category="SaaS & Cloud", amount=340.00, vendor="Google LLC", anomaly=False),
            models.DBExpense(date="2026-10-09", description="Office HQ Highspeed Fiber", category="Office & Facilities", amount=280.00, vendor="AT&T Business", anomaly=False),
            models.DBExpense(date="2026-10-04", description="Q4 Search Engine Ads", category="Marketing", amount=1800.00, vendor="Meta Platforms", anomaly=False),
        ]
        db.add_all(expenses)

    db.commit()
    db.close()

# --- Routes ---
@app.get("/api/dashboard/kpis", tags=["Dashboard"], dependencies=[Depends(auth.get_current_user)])
def get_kpi_metrics(db: Session = Depends(get_db)):
    invoices = db.query(models.DBInvoice).all()
    expenses = active_expenses_query(db).all()
    products = db.query(models.DBProduct).all()

    unpaid_total = sum(inv.amount for inv in invoices if inv.status not in {"PAID", "VOID"})
    total_revenue = sum(inv.amount for inv in invoices if inv.status == "PAID")
    total_expenses = sum(exp.amount for exp in expenses)
    low_stock = [p for p in products if p.stock <= p.min_stock]

    return {
        "gross_revenue": total_revenue,
        "total_expenses": total_expenses,
        "net_profit": total_revenue - total_expenses,
        "receivables": unpaid_total,
        "low_stock_critical_count": len(low_stock),
        "recent_invoices": invoices[:4]
    }

@app.get("/api/customers", response_model=List[Customer], tags=["Customers"], dependencies=[Depends(auth.get_current_user)])
def get_customers(db: Session = Depends(get_db)):
    return db.query(models.DBCustomer).order_by(models.DBCustomer.id.desc()).all()

@app.post("/api/customers", response_model=Customer, status_code=status.HTTP_201_CREATED, tags=["Customers"], dependencies=[Depends(auth.get_current_user)])
def create_customer(
    payload: CustomerCreate,
    db: Session = Depends(get_db),
    current_user: models.DBUser = Depends(auth.get_current_user),
):
    existing_email = db.query(models.DBCustomer).filter(
        models.DBCustomer.email == payload.email
    ).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email address is already assigned to a customer. Use a different contact email.",
        )

    known_ids = [
        row[0] for row in db.query(models.DBCustomer.id).all()
    ] + [
        row[0] for row in db.query(models.DBCustomerAuditLog.customer_id).all()
    ]
    customer_numbers = [
        int(suffix)
        for known_id in known_ids
        for prefix, separator, suffix in [known_id.rpartition("-")]
        if prefix == "CUST" and separator and suffix.isdigit()
    ]
    new_id = f"CUST-{max(customer_numbers, default=100) + 1}"
    cust = models.DBCustomer(id=new_id, spend=0.0, **payload.model_dump())
    db.add(cust)
    db.flush()
    record_customer_audit(db, cust.id, "created", current_user.username, [])
    db.commit()
    db.refresh(cust)
    return cust

@app.delete("/api/customers/{customer_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Customers"], dependencies=[Depends(auth.get_current_user)])
def delete_customer(
    customer_id: str,
    db: Session = Depends(get_db),
    current_user: models.DBUser = Depends(auth.get_current_user),
):
    customer = db.query(models.DBCustomer).filter(models.DBCustomer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    if db.query(models.DBInvoice).filter(models.DBInvoice.customer_id == customer_id).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This customer has invoices and cannot be deleted. Keep the customer record to preserve billing history.",
        )

    record_customer_audit(db, customer_id, "deleted", current_user.username, [])
    db.delete(customer)
    db.commit()

@app.put("/api/customers/{customer_id}", response_model=Customer, tags=["Customers"], dependencies=[Depends(auth.get_current_user)])
def update_customer(
    customer_id: str,
    payload: CustomerCreate,
    db: Session = Depends(get_db),
    current_user: models.DBUser = Depends(auth.get_current_user),
):
    customer = db.query(models.DBCustomer).filter(models.DBCustomer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    duplicate_email = db.query(models.DBCustomer).filter(
        models.DBCustomer.email == payload.email,
        models.DBCustomer.id != customer_id,
    ).first()
    if duplicate_email:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This email address is already assigned to another customer")

    values = payload.model_dump()
    changed_fields = [
        field for field, value in values.items()
        if getattr(customer, field) != value
    ]
    for field, value in values.items():
        setattr(customer, field, value)
    if changed_fields:
        record_customer_audit(db, customer_id, "updated", current_user.username, changed_fields)
        db.commit()
    db.refresh(customer)
    return customer

def record_customer_audit(
    db: Session,
    customer_id: str,
    action: str,
    actor: str,
    changed_fields: List[str],
) -> None:
    db.add(models.DBCustomerAuditLog(
        customer_id=customer_id,
        action=action,
        actor=actor,
        changed_fields=json.dumps(changed_fields),
    ))

@app.get(
    "/api/customers/{customer_id}/audit-log",
    response_model=List[CustomerAuditEntry],
    tags=["Customers"],
    dependencies=[Depends(auth.get_current_user)],
)
def get_customer_audit_log(customer_id: str, db: Session = Depends(get_db)):
    entries = db.query(models.DBCustomerAuditLog).filter(
        models.DBCustomerAuditLog.customer_id == customer_id
    ).order_by(
        models.DBCustomerAuditLog.created_at.desc(),
        models.DBCustomerAuditLog.id.desc(),
    ).all()
    if not entries and not db.query(models.DBCustomer).filter(
        models.DBCustomer.id == customer_id
    ).first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    return [
        {
            "id": entry.id,
            "action": entry.action,
            "actor": entry.actor,
            "changed_fields": json.loads(entry.changed_fields),
            "created_at": entry.created_at,
        }
        for entry in entries
    ]

@app.get("/api/inventory", response_model=List[Product], tags=["Inventory"], dependencies=[Depends(auth.get_current_user)])
def get_inventory(db: Session = Depends(get_db)):
    return db.query(models.DBProduct).all()

@app.post("/api/inventory", response_model=Product, status_code=status.HTTP_201_CREATED, tags=["Inventory"], dependencies=[Depends(auth.get_current_user)])
def add_product(payload: ProductCreate, db: Session = Depends(get_db)):
    count = db.query(models.DBProduct).count()
    new_id = f"PROD-{count + 1:02d}"
    new_sku = f"SKU-{100 + count * 7}"
    prod = models.DBProduct(id=new_id, sku=new_sku, **payload.model_dump())
    db.add(prod)
    db.commit()
    db.refresh(prod)
    return prod

@app.post("/api/inventory/{product_id}/restock", response_model=Product, tags=["Inventory"], dependencies=[Depends(auth.get_current_user)])
def restock_item(product_id: str, units: int = 10, db: Session = Depends(get_db)):
    prod = db.query(models.DBProduct).filter(models.DBProduct.id == product_id).first()
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")
    prod.stock += units
    db.commit()
    db.refresh(prod)
    return prod

@app.delete("/api/inventory/{product_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Inventory"], dependencies=[Depends(auth.get_current_user)])
def delete_product(product_id: str, db: Session = Depends(get_db)):
    product = db.query(models.DBProduct).filter(models.DBProduct.id == product_id).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if db.query(models.DBInvoice).filter(models.DBInvoice.item == product.name).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This product appears on invoices and cannot be deleted. Keep it to preserve invoice history.",
        )

    db.delete(product)
    db.commit()

@app.put("/api/inventory/{product_id}", response_model=Product, tags=["Inventory"], dependencies=[Depends(auth.get_current_user)])
def update_product(product_id: str, payload: ProductCreate, db: Session = Depends(get_db)):
    product = db.query(models.DBProduct).filter(models.DBProduct.id == product_id).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if payload.name != product.name and db.query(models.DBInvoice).filter(
        models.DBInvoice.item == product.name
    ).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This product appears on invoices and cannot be renamed. Create a new product to preserve invoice history.",
        )

    for field, value in payload.model_dump().items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return product

@app.get("/api/invoices", response_model=List[Invoice], tags=["Invoices"], dependencies=[Depends(auth.get_current_user)])
def get_invoices(db: Session = Depends(get_db)):
    return db.query(models.DBInvoice).order_by(models.DBInvoice.id.desc()).all()

@app.post("/api/invoices", response_model=Invoice, status_code=status.HTTP_201_CREATED, tags=["Invoices"], dependencies=[Depends(auth.get_current_user)])
def create_invoice(payload: InvoiceCreate, db: Session = Depends(get_db)):
    customer = db.query(models.DBCustomer).filter(models.DBCustomer.id == payload.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    product = db.query(models.DBProduct).filter(models.DBProduct.id == payload.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if product.stock < payload.quantity:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient inventory! Only {product.stock} units in stock."
        )

    product.stock -= payload.quantity
    subtotal = product.price * payload.quantity
    tax_amount = subtotal * 0.08
    total = round(subtotal + tax_amount, 2)

    count = db.query(models.DBInvoice).count()
    new_id = f"INV-2026-{count + 1:03d}"
    invoice = models.DBInvoice(
        id=new_id,
        customer_id=customer.id,
        customer_name=customer.name,
        date=str(payload.issue_date),
        amount=total,
        status="PENDING",
        item=product.name,
        qty=payload.quantity,
        unit_price=product.price
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice

@app.put("/api/invoices/{invoice_id}", response_model=Invoice, tags=["Invoices"], dependencies=[Depends(auth.get_current_user)])
def update_invoice(invoice_id: str, payload: InvoiceUpdate, db: Session = Depends(get_db)):
    invoice = db.query(models.DBInvoice).filter(models.DBInvoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    if invoice.status not in {"PENDING", "OVERDUE"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only unpaid invoices can be edited. Paid or void invoices must remain in the audit history.")

    customer = db.query(models.DBCustomer).filter(models.DBCustomer.id == payload.customer_id).first()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    old_products = db.query(models.DBProduct).filter(
        models.DBProduct.name == invoice.item
    ).all()
    if len(old_products) != 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The original product cannot be matched uniquely in inventory. Void and reissue this invoice instead.",
        )
    old_product = old_products[0]

    new_product = db.query(models.DBProduct).filter(
        models.DBProduct.id == payload.product_id
    ).first()
    if not new_product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    if old_product.id == new_product.id:
        stock_delta = payload.quantity - invoice.qty
        if stock_delta > new_product.stock:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Insufficient inventory. Only {new_product.stock} units are available.",
            )
        new_product.stock -= stock_delta
    else:
        if new_product.stock < payload.quantity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Insufficient inventory. Only {new_product.stock} units are available.",
            )
        old_product.stock += invoice.qty
        new_product.stock -= payload.quantity

    invoice.customer_id = customer.id
    invoice.customer_name = customer.name
    invoice.date = str(payload.issue_date)
    invoice.item = new_product.name
    invoice.qty = payload.quantity
    invoice.unit_price = new_product.price
    invoice.amount = round(new_product.price * payload.quantity * 1.08, 2)
    db.commit()
    db.refresh(invoice)
    return invoice

@app.patch("/api/invoices/{invoice_id}/pay", response_model=Invoice, tags=["Invoices"], dependencies=[Depends(auth.get_current_user)])
def mark_invoice_as_paid(invoice_id: str, db: Session = Depends(get_db)):
    inv = db.query(models.DBInvoice).filter(models.DBInvoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if inv.status == "VOID":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A void invoice cannot be marked as paid")
    inv.status = "PAID"
    db.commit()
    db.refresh(inv)
    return inv

@app.patch("/api/invoices/{invoice_id}/void", response_model=Invoice, tags=["Invoices"], dependencies=[Depends(auth.get_current_user)])
def void_invoice(invoice_id: str, db: Session = Depends(get_db)):
    invoice = db.query(models.DBInvoice).filter(models.DBInvoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    if invoice.status == "VOID":
        return invoice
    if invoice.status == "PAID":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Paid invoices cannot be voided")
    if invoice.status not in {"PENDING", "OVERDUE"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This invoice cannot be voided")

    products = db.query(models.DBProduct).filter(
        models.DBProduct.name == invoice.item
    ).all()
    if len(products) != 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The invoice product cannot be matched uniquely in inventory, so stock was not changed and the invoice was not voided.",
        )

    products[0].stock += invoice.qty
    invoice.status = "VOID"
    db.commit()
    db.refresh(invoice)
    return invoice

@app.get("/api/invoices/{invoice_id}/pdf", tags=["Invoices"], dependencies=[Depends(auth.get_current_user)])
def download_invoice_pdf(invoice_id: str, db: Session = Depends(get_db)):
    inv = db.query(models.DBInvoice).filter(models.DBInvoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")

    cust = db.query(models.DBCustomer).filter(models.DBCustomer.id == inv.customer_id).first()
    cust_email = cust.email if cust else "finance@client.org"

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('DocTitle', parent=styles['Heading1'], fontSize=22, textColor=colors.HexColor('#4f46e5'), spaceAfter=4)
    elements.append(Paragraph("SmartBiz<b>.AI</b>", title_style))
    elements.append(Paragraph("Enterprise Operations Ledger Inc. &bull; VAT: US-8839210-X", styles['Normal']))
    elements.append(Spacer(1, 20))

    meta_data = [
        [
            Paragraph(f"<b>Billed To:</b><br/>{inv.customer_name}<br/>{cust_email}", styles['Normal']),
            Paragraph(f"<b>Invoice ID:</b> {inv.id}<br/><b>Date:</b> {inv.date}<br/><b>Status:</b> {inv.status}", styles['Normal'])
        ]
    ]
    meta_table = Table(meta_data, colWidths=[270, 260])
    elements.append(meta_table)
    elements.append(Spacer(1, 25))

    subtotal = inv.qty * inv.unit_price
    tax = subtotal * 0.08
    grand_total = subtotal + tax

    table_data = [
        ["Description", "Qty", "Unit Price ($)", "Amount ($)"],
        [inv.item, str(inv.qty), f"${inv.unit_price:,.2f}", f"${subtotal:,.2f}"],
        ["", "", "Subtotal:", f"${subtotal:,.2f}"],
        ["", "", "Tax (8%):", f"${tax:,.2f}"],
        ["", "", "Total Due:", f"${grand_total:,.2f}"]
    ]

    t = Table(table_data, colWidths=[260, 50, 110, 110])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8fafc')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('LINEBELOW', (0, 0), (-1, 0), 1.5, colors.HexColor('#e2e8f0')),
        ('LINEBELOW', (0, 1), (-1, 1), 1, colors.HexColor('#f1f5f9')),
        ('FONTNAME', (2, 2), (-1, -1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (3, 4), (3, 4), colors.HexColor('#4f46e5')),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 40))

    footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor('#94a3b8'), alignment=1)
    elements.append(Paragraph("Rendered automatically via Python ReportLab + FastAPI Backend Engine.", footer_style))

    doc.build(elements)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={inv.id}.pdf"}
    )

@app.get("/api/expenses", response_model=List[Expense], tags=["Expenses"], dependencies=[Depends(auth.get_current_user)])
def get_expenses(db: Session = Depends(get_db)):
    return active_expenses_query(db).order_by(models.DBExpense.id.desc()).all()

@app.get("/api/expenses/archived", response_model=List[Expense], tags=["Expenses"], dependencies=[Depends(auth.get_current_user)])
def get_archived_expenses(db: Session = Depends(get_db)):
    archived_ids = db.query(models.DBArchivedExpense.expense_id)
    return db.query(models.DBExpense).filter(
        models.DBExpense.id.in_(archived_ids)
    ).order_by(models.DBExpense.id.desc()).all()

@app.patch("/api/expenses/{expense_id}/archive", tags=["Expenses"], dependencies=[Depends(auth.get_current_user)])
def archive_expense(expense_id: int, db: Session = Depends(get_db)):
    expense = db.query(models.DBExpense).filter(models.DBExpense.id == expense_id).first()
    if not expense:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found")

    archived = db.query(models.DBArchivedExpense).filter(
        models.DBArchivedExpense.expense_id == expense_id
    ).first()
    if not archived:
        db.add(models.DBArchivedExpense(expense_id=expense_id))
        db.commit()
    return {"message": "Expense archived"}

@app.patch("/api/expenses/{expense_id}/restore", tags=["Expenses"], dependencies=[Depends(auth.get_current_user)])
def restore_expense(expense_id: int, db: Session = Depends(get_db)):
    expense = db.query(models.DBExpense).filter(models.DBExpense.id == expense_id).first()
    if not expense:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found")

    archived = db.query(models.DBArchivedExpense).filter(
        models.DBArchivedExpense.expense_id == expense_id
    ).first()
    if archived:
        db.delete(archived)
        db.commit()
    return {"message": "Expense restored"}

@app.post("/api/expenses", response_model=Expense, status_code=status.HTTP_201_CREATED, tags=["Expenses"], dependencies=[Depends(auth.get_current_user)])
def log_expense(payload: ExpenseCreate, db: Session = Depends(get_db)):
    is_anomaly = payload.amount > 1000.00
    exp = models.DBExpense(
        date=str(payload.date or date.today()),
        description=payload.description,
        category=payload.category,
        amount=payload.amount,
        vendor=payload.vendor,
        anomaly=is_anomaly
    )
    db.add(exp)
    db.commit()
    db.refresh(exp)
    return exp

@app.put("/api/expenses/{expense_id}", response_model=Expense, tags=["Expenses"], dependencies=[Depends(auth.get_current_user)])
def update_expense(expense_id: int, payload: ExpenseUpdate, db: Session = Depends(get_db)):
    expense = db.query(models.DBExpense).filter(models.DBExpense.id == expense_id).first()
    if not expense:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found")

    expense.description = payload.description
    expense.date = str(payload.date)
    expense.category = payload.category
    expense.amount = payload.amount
    expense.vendor = payload.vendor
    expense.anomaly = payload.amount > 1000.00
    db.commit()
    db.refresh(expense)
    return expense

@app.post("/api/ai/query", response_model=AIQueryResponse, tags=["AI Copilot"], dependencies=[Depends(auth.get_current_user)])
def process_ai_query(req: AIQueryRequest, db: Session = Depends(get_db)):
    q = req.query.lower()

    product_query = any(term in q for term in ("product", "products", "catalog", "catalogue"))
    policy_query = any(term in q for term in ("policy", "refund", "return"))
    if product_query and not policy_query:
        products = db.query(models.DBProduct).order_by(models.DBProduct.name).all()
        if not products:
            return AIQueryResponse(
                text="There are no products in the product catalog yet.",
                meta="Source: live product catalog"
            )

        product_lines = [
            f"{product.name} ({product.category}) - ${product.price:,.2f}; "
            f"{product.stock} in stock."
            for product in products
        ]
        return AIQueryResponse(
            text=(
                "Here is the product information currently in the catalog:\n"
                + "\n".join(product_lines)
                + "\nThe catalog contains names, categories, prices, and stock levels, "
                "but no detailed product descriptions."
            ),
            meta="Source: live product catalog"
        )

    document_query = any(
        term in q
        for term in (
            "policy",
            "refund",
            "return",
            "handbook",
            "runbook",
            "business document",
            "restock",
            "reorder",
        )
    )
    if document_query:
        rag_answer = ask_langchain_rag(req.query)
        if rag_answer:
            return AIQueryResponse(
                text=rag_answer,
                meta="LangChain + ChromaDB RAG answer from SmartBiz business documents"
            )

        fallback_doc_answer = fallback_document_answer(req.query)
        if fallback_doc_answer:
            return AIQueryResponse(
                text=fallback_doc_answer,
                meta="Fallback document retrieval from SmartBiz knowledge base"
            )

    if any(term in q for term in ("owe", "owed", "receivable", "unpaid", "outstanding")):
        unpaid = [
            invoice for invoice in db.query(models.DBInvoice).all()
            if invoice.status not in {"PAID", "VOID"}
        ]
        total = sum(invoice.amount or 0 for invoice in unpaid)
        return AIQueryResponse(
            text=f"Customers currently owe ${total:,.2f} across {len(unpaid)} unpaid invoices.",
            meta="Source: live invoice records"
        )

    if "expense" in q and any(term in q for term in ("categor", "breakdown", "group")):
        expenses = active_expenses_query(db).all()
        totals_by_category: Dict[str, float] = {}
        for expense in expenses:
            category = expense.category or "Uncategorized"
            totals_by_category[category] = totals_by_category.get(category, 0) + (expense.amount or 0)

        if not totals_by_category:
            return AIQueryResponse(
                text="There are no expense records to summarize yet.",
                meta="Source: live expense records"
            )

        breakdown = "\n".join(
            f"{category}: ${amount:,.2f}"
            for category, amount in sorted(
                totals_by_category.items(),
                key=lambda item: item[1],
                reverse=True,
            )
        )
        total = sum(totals_by_category.values())
        return AIQueryResponse(
            text=f"Expenses by category:\n{breakdown}\nTotal expenses: ${total:,.2f}.",
            meta="Source: live expense records"
        )

    if "expense" in q and any(term in q for term in ("unusual", "anomal", "spike")):
        flagged_expenses = active_expenses_query(db).filter(
            models.DBExpense.anomaly.is_(True)
        )
        if "this week" in q:
            today = date.today()
            week_start = today - timedelta(days=today.weekday())
            flagged_expenses = flagged_expenses.filter(
                models.DBExpense.date >= week_start.isoformat(),
                models.DBExpense.date <= today.isoformat(),
            )
            period = f"for this week ({week_start.isoformat()} through {today.isoformat()})"
        else:
            period = "in the recorded expense history"

        flagged_expenses = flagged_expenses.order_by(models.DBExpense.date.desc()).all()
        if not flagged_expenses:
            return AIQueryResponse(
                text=f"No expenses are flagged as unusual {period}.",
                meta="Source: live expense anomaly flags"
            )

        expense_lines = [
            f"{expense.date}: {expense.description} ({expense.vendor or 'vendor not recorded'}) "
            f"- ${(expense.amount or 0):,.2f}"
            for expense in flagged_expenses
        ]
        return AIQueryResponse(
            text=f"Expenses flagged as unusual {period}:\n" + "\n".join(expense_lines),
            meta="Source: live expense anomaly flags"
        )

    business_context = build_business_context(db)
    llm_answer = ask_llm_business_question(req.query, business_context)
    if llm_answer:
        return AIQueryResponse(
            text=llm_answer,
            meta=f"LLM answer generated from live business data (model: {os.getenv('LLM_MODEL', os.getenv('OPENAI_MODEL', 'gpt-4o-mini'))})"
        )

    if any(term in q for term in ("summarize", "summary", "overview", "performance")):
        summary = business_context["summary"]
        return AIQueryResponse(
            text=(
                f"Business overview: {summary['customer_count']} customers, "
                f"{summary['invoice_count']} invoices, "
                f"${summary['total_revenue']:,.2f} in paid revenue, "
                f"${summary['pending_receivables']:,.2f} in unpaid receivables, and "
                f"${summary['total_expense']:,.2f} in recorded expenses. "
                f"There are {len(business_context['inventory_alerts'])} products at or below "
                "their minimum stock level."
            ),
            meta="Source: live business records (Gemini unavailable)"
        )

    if "profit" in q or "highest" in q:
        return AIQueryResponse(
            text="I can’t calculate product profit from the available records because product cost data is not stored.",
            meta="Required data missing: product cost"
        )
    elif "unpaid" in q or "invoice" in q:
        unpaid = db.query(models.DBInvoice).filter(
            models.DBInvoice.status.notin_(["PAID", "VOID"])
        ).all()
        total = sum(i.amount for i in unpaid)
        return AIQueryResponse(
            text=f"You have {len(unpaid)} unpaid invoices totaling ${total:,.2f}.",
            meta="Source: live invoice records"
        )
    return AIQueryResponse(
        text=(
            "I couldn’t generate an AI answer right now. The Gemini service or document search may be "
            "unavailable. Please try again later or ask about information in the business documents "
            "or product, invoice, and inventory records."
        ),
        meta="No live Gemini or RAG answer was generated"
    )
