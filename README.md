# SmartBiz AI

SmartBiz AI is a small-business operations dashboard for managing customers, inventory,
invoices, expenses, and business-document questions. It has:

- A static HTML/CSS/JavaScript frontend
- A FastAPI REST API
- SQLAlchemy models backed by MySQL
- JWT authentication
- ReportLab-generated invoice PDFs
- Chart.js dashboard visualizations
- Optional Gemini/LangChain RAG for local business documents

The project is currently intended as a self-hosted internal application, not a
multi-tenant SaaS service.

## Table of contents

- [Feature overview](#feature-overview)
- [Technology stack](#technology-stack)
- [Project structure](#project-structure)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Local setup](#local-setup)
- [Configuration reference](#configuration-reference)
- [Using the application](#using-the-application)
- [API reference](#api-reference)
- [Data model](#data-model)
- [Business rules](#business-rules)
- [AI and document knowledge base](#ai-and-document-knowledge-base)
- [Frontend behavior](#frontend-behavior)
- [Testing](#testing)
- [Deployment notes](#deployment-notes)
- [Troubleshooting](#troubleshooting)
- [Repository hygiene](#repository-hygiene)

## Feature overview

### Dashboard

- Paid invoice revenue
- Active expense totals
- Net profit (paid revenue minus active expenses)
- Unpaid receivable balances
- Low-stock item count
- Low-stock and unusual-expense watchlist
- Monthly sales/expense chart
- Expense category chart
- Recent invoices

Archived expenses are excluded from dashboard totals and reports.

### Customer CRM

- Add, edit, and list customers
- Store name, email, phone, and account tier
- Validate customer contact information
- Generate sequential customer IDs such as `CUST-101`
- Prevent duplicate customer email addresses
- View customer audit history
- Protect customers with existing invoice history from deletion

Customer audit entries record the action, actor, timestamp, and changed field names.
They do not record old or new contact values.

### Inventory

- Add and edit products
- Track SKU, category, price, stock, and minimum stock
- Restock an existing product
- Identify products at or below their minimum stock threshold
- Prevent deletion or renaming of products that appear on invoices

The inventory routes do not expose a general stock-adjustment reason or audit log.

### Invoices

- Create an invoice from a customer and product
- Reserve inventory when an invoice is created
- Calculate 8% tax
- Edit pending or overdue invoices
- Recalculate the inventory allocation after invoice changes
- Mark unpaid invoices as paid
- Void pending or overdue invoices
- Return inventory when a pending or overdue invoice is voided
- Generate and preview a PDF invoice

Paid and void invoices are protected from status changes that would invalidate
their billing history.

### Expenses

- Add an expense with date, description, category, amount, and vendor
- Edit an expense
- Automatically flag an expense as anomalous when it exceeds `$1000`
- Archive an expense without deleting it
- Restore an archived expense
- Keep archived expenses out of active totals

An expense is only flagged at $1000.01 or more; this threshold is recalculated
whenever an expense is edited.

### SmartBiz Copilot

The copilot answers questions through a priority of sources:

1. Live product catalog queries
2. ChromaDB/LangChain business-document RAG
3. Fallback answers for a few common policy questions
4. Live invoice, expense, inventory, and customer calculations
5. Optional Gemini or OpenAI-compatible LLM context

If no provider or source can answer, the API returns a useful fallback rather than
inventing a result.

## Technology stack

| Area | Technology |
|---|---|
| Frontend | HTML5, CSS3, vanilla JavaScript |
| Charts | Chart.js loaded from jsDelivr |
| Backend | Python, FastAPI, Uvicorn |
| Database | SQLAlchemy with MySQL through PyMySQL |
| Authentication | JWT, python-jose, Passlib/bcrypt |
| PDF generation | ReportLab |
| Documents | LangChain, ChromaDB, Google Gemini embeddings/chat |
| PDF document extraction | pypdf |
| Tests | Python `unittest` |

The frontend has no npm build step. It can be served by any static-file server.

## Project structure

```text
Smartbitz AI/
|-- backend/
|   |-- auth.py             # Password hashing and JWT authentication
|   |-- config.py           # Loads the local .env file
|   |-- create_admin.py     # Interactive initial-admin setup
|   |-- database.py         # SQLAlchemy engine and sessions
|   |-- main.py             # FastAPI app, schemas, routes, AI, and PDF logic
|   |-- models.py           # SQLAlchemy database tables
|   `-- requirements-rag.txt
|-- frontend/
|   |-- index.html          # Views, modals, and static markup
|   |-- script.js           # API calls, state, rendering, and interactions
|   `-- style.css           # Layout, components, responsive styles
|-- business_docs/
|   `-- README.md           # Instructions for the private knowledge base
|-- tests/
|   `-- test_record_removal.py
|-- .env.example
`-- README.md
```

Generated, private, or environment-specific paths may also include `.env`,
`.venv`/`venv`, `.chromadb`, and files inside `business_docs/`.

## Architecture

```text
Browser
  |
  | HTTP/JSON or PDF request
  v
Static Frontend (index.html + script.js)
  |
  | Bearer JWT
  v
FastAPI API (backend/main.py)
  |-- SQLAlchemy ORM
  |     |
  |     v
  |   MySQL
  |
  |-- ReportLab PDF output
  |
  `-- Optional AI providers
        |-- Live SQL context
        |-- Gemini/OpenAI-compatible HTTP API
        `-- ChromaDB local document index
```

The frontend keeps its fetched records in the `DB` JavaScript object. Authentication
credentials are stored in browser `localStorage`:

- `smartbiz_token`
- `smartbiz_username`
- `smartbiz_user_role`

Every protected API route requires a valid bearer token. A `401` response clears the
browser authentication state and private in-memory data.

## Requirements

### Required

- Python 3.10 or newer
- MySQL 8 or a compatible database URL supported by SQLAlchemy/PyMySQL
- A modern web browser
- Internet access for Chart.js if it is not replaced or cached locally

### Optional

- Gemini API access for document RAG or live-data LLM answers
- An OpenAI-compatible API endpoint
- PowerShell for the Windows setup commands below

## Local setup

### 1. Clone and open the project

```powershell
git clone <repository-url>
cd "Smartbitz AI"
```

Run commands from the repository root. Commands assume Windows PowerShell.

### 2. Create a MySQL database

Create a database and a dedicated application account, for example:

```sql
CREATE DATABASE smartbiz_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'smartbiz_user'@'localhost' IDENTIFIED BY 'replace_with_a_strong_password';
GRANT ALL PRIVILEGES ON smartbiz_db.* TO 'smartbiz_user'@'localhost';
FLUSH PRIVILEGES;
```

Do not use the MySQL root account for normal application operation.

### 3. Create a Python environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend\requirements-rag.txt
```

The requirements file installs both core dependencies and optional RAG dependencies.
The application can start without RAG packages or an API key, but RAG features will
be unavailable.

### 4. Configure environment variables

Copy the template:

```powershell
Copy-Item .env.example .env
```

Generate a JWT secret:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Set at least:

```dotenv
SMARTBIZ_DATABASE_URL=mysql+pymysql://smartbiz_user:replace_with_a_strong_password@127.0.0.1:3306/smartbiz_db
SMARTBIZ_JWT_SECRET=<generated-random-secret>
SMARTBIZ_CORS_ORIGINS=http://127.0.0.1:5501,http://localhost:5501
SMARTBIZ_SEED_DEMO_DATA=false
```

The backend rejects startup if `SMARTBIZ_DATABASE_URL` or a sufficiently long
`SMARTBIZ_JWT_SECRET` is missing.

### 5. Create the first administrator

```powershell
python -m backend.create_admin
```

The command prompts for:

- Username
- Email
- Password
- Password confirmation

The initial user is assigned the `Admin` role. The command refuses to run if any
users already exist. After initialization, an administrator creates additional users
through `POST /api/auth/register`.

### 6. Start the API

```powershell
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

API documentation:

- Swagger UI: `http://127.0.0.1:8000/docs`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`
- Health check: `http://127.0.0.1:8000/api/health`

### 7. Start the frontend

Use a separate terminal:

```powershell
python -m http.server 5501 --directory frontend
```

Open `http://127.0.0.1:5501`.

Do not open `frontend/index.html` directly through `file://` when a fixed API origin
is required. The frontend can derive the API origin from the current host, but a
static HTTP server is the safer setup.

## Configuration reference

| Variable | Required | Purpose |
|---|---:|---|
| `SMARTBIZ_DATABASE_URL` | Yes | SQLAlchemy MySQL connection URL |
| `SMARTBIZ_JWT_SECRET` | Yes | Secret used to sign/verify JWTs; at least 32 characters |
| `SMARTBIZ_CORS_ORIGINS` | No | Comma-separated exact frontend origins |
| `SMARTBIZ_SEED_DEMO_DATA` | No | Seeds demo records when set to `true`, `1`, or `yes` |
| `LLM_API_KEY` | No | Gemini key or generic LLM key |
| `LLM_API_URL` | No | Custom LLM API URL |
| `LLM_MODEL` | No | Chat model name |
| `GEMINI_EMBEDDING_MODEL` | No | Gemini embedding model name |
| `OPENAI_API_KEY` | No | Alternative API key |
| `OPENAI_API_URL` | No | Alternative OpenAI-compatible endpoint |
| `OPENAI_MODEL` | No | Alternative chat model name |

`SMARTBIZ_CORS_ORIGINS` defaults to ports 5500 and 5501 on localhost and 127.0.0.1.
For production, list exact HTTPS frontend origins and never use a wildcard with
cookies or bearer-authenticated requests.

When the frontend and API are hosted on different origins, set this before
`script.js` loads:

```html
<script>
  window.SMARTBIZ_API_BASE = "https://api.example.com/api";
</script>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script src="script.js"></script>
```

This setting must match the API origin configured in `SMARTBIZ_CORS_ORIGINS`.

## Using the application

1. Start MySQL.
2. Start the FastAPI process.
3. Start the frontend server.
4. Open the frontend and sign in.
5. Create customers and products.
6. Create invoices.
7. Mark invoices paid or void unpaid invoices.
8. Record expenses.
9. Archive unusual expenses instead of deleting them.
10. Use SmartBiz Copilot for live-record summaries or policy questions.

### Common invoice workflow

```text
Create invoice
  -> PENDING
  -> stock is reduced
  -> invoice total includes 8% tax
  -> edit while PENDING/OVERDUE (stock recalculated)
  -> PAID (locked)
  or VOID (PENDING/OVERDUE only; stock returned)
```

Invoices cannot be deleted. They are kept as ledger history.

### Expense workflow

```text
Create or edit expense
  -> amount > 1000 = anomaly
  -> archive = hidden from active totals
  -> restore = included again
```

## API reference

All routes are prefixed with `/api` unless otherwise noted.

### Authentication

| Method | Route | Purpose |
|---|---|---|
| `POST` | `/api/auth/token` | Sign in with form fields `username` and `password` |
| `GET` | `/api/auth/me` | Return the signed-in user |
| `POST` | `/api/auth/register` | Create a user; caller must be an Admin |

JWT tokens expire after 12 hours.

### Core data

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/api/health` | Public health check |
| `GET` | `/api/dashboard/kpis` | Dashboard totals |
| `GET/POST` | `/api/customers` | List/create customers |
| `PUT/DELETE` | `/api/customers/{customer_id}` | Edit/delete a customer |
| `GET` | `/api/customers/{customer_id}/audit-log` | Customer change history |
| `GET/POST` | `/api/inventory` | List/create products |
| `PUT/DELETE` | `/api/inventory/{product_id}` | Edit/delete a product |
| `POST` | `/api/inventory/{product_id}/restock?units=N` | Increase stock |
| `GET/POST` | `/api/invoices` | List/create invoices |
| `PUT` | `/api/invoices/{invoice_id}` | Edit an unpaid invoice |
| `PATCH` | `/api/invoices/{invoice_id}/pay` | Mark paid |
| `PATCH` | `/api/invoices/{invoice_id}/void` | Void and restock |
| `GET` | `/api/invoices/{invoice_id}/pdf` | Return an inline PDF |
| `GET/POST` | `/api/expenses` | List/create active expenses |
| `GET` | `/api/expenses/archived` | List archived expenses |
| `PUT` | `/api/expenses/{expense_id}` | Edit an expense |
| `PATCH` | `/api/expenses/{expense_id}/archive` | Archive an expense |
| `PATCH` | `/api/expenses/{expense_id}/restore` | Restore an expense |
| `POST` | `/api/ai/query` | Ask SmartBiz Copilot |

Core routes except `/api/health` and user authentication generally require
authorization. `POST /api/auth/register` additionally requires the Admin role.

FastAPI uses Pydantic request validation and returns `400`, `404`, `409`, or `401`
responses for validation, missing resources, conflicting business operations, or
authentication failures.

## Data model

| Table | Key fields |
|---|---|
| `users` | username, email, hashed password, role, active flag |
| `customers` | ID, name, email, phone, tier, lifetime spend |
| `customer_audit_logs` | customer ID, action, actor, changed fields, timestamp |
| `products` | ID, SKU, name, category, price, stock, minimum stock |
| `invoices` | ID, customer, date, amount, status, item, quantity, unit price |
| `expenses` | date, description, category, amount, vendor, anomaly |
| `archived_expenses` | links an expense ID to an archive timestamp |

The API creates missing tables automatically with
`Base.metadata.create_all(bind=engine)`. It does not perform schema migrations or
alter existing business rows. For schema changes, back up MySQL and use a migration
tool or a controlled SQL migration before deployment.

## Business rules

- Customer and product email/name identity rules prevent ambiguous records.
- Invoice creation reduces product stock and records an 8% tax.
- Editing a PENDING or OVERDUE invoice adjusts old/new product stock.
- Marking an invoice paid makes it locked.
- Voiding returns stock only once and only for PENDING or OVERDUE invoices.
- Paid invoices cannot be voided.
- A void invoice cannot be marked paid.
- Customers cannot be deleted if they have invoice history.
- Products cannot be deleted or renamed if invoice history references their name.
- Archived expenses remain in the database and can be restored.
- Expense anomaly is recalculated from the current amount.
- Gross revenue counts PAID invoices only.
- Receivables count every status except PAID and VOID.

## AI and document knowledge base

Place authorized knowledge-base files in `business_docs/`:

- `.txt`
- `.md`
- `.markdown`
- `.pdf`

Startup attempts to rebuild a local ChromaDB index only when `LLM_API_KEY` is set
and supported RAG dependencies are installed.

The generated vector index is stored in `.chromadb/`. It is not business data in
MySQL and should be excluded from Git.

The backend supports both Gemini and OpenAI-compatible requests:

- `LLM_API_KEY` or `OPENAI_API_KEY`
- `LLM_API_URL` or `OPENAI_API_URL`
- `LLM_MODEL` or `OPENAI_MODEL`

For Gemini RAG, set `GEMINI_EMBEDDING_MODEL` and optionally `LLM_MODEL`.

Live LLM answers receive a compact JSON summary containing:

- Customer/product/invoice/expense counts
- Paid revenue
- Pending receivables
- Total active expenses
- Top customers
- Product catalog and stock alerts
- Recent invoices and expenses

Never add documents containing secrets or sensitive customer data unless they are
authorized for use with the configured LLM provider.

## Frontend behavior

The frontend is organized as six views:

- Dashboard
- Customer CRM
- Inventory
- Invoices
- Expenses
- SmartBiz Copilot

It also includes login, settings, customer audit, invoice PDF preview, and create/edit
modals.

Browser preferences for layout density and reduced motion are stored locally:

- `smartbiz_layout_density`
- `smartbiz_reduce_motion`

The app polls `/api/health` every 15 seconds and displays an offline banner if the
backend cannot be reached. On logout or `401`, private fetched data is cleared from
the in-memory `DB` object.

Chart.js is loaded through a CDN. The rest of the UI does not require a package
manager or bundler.

## Testing

Run the focused record-removal and business-rule tests:

```powershell
python -m unittest discover -s tests
```

The tests use an isolated in-memory SQLite database and set temporary environment
variables. They do not connect to your configured MySQL database.

Tests cover:

- Customer audit history
- Customer deletion protection
- Customer editing
- Invoice stock adjustment
- Invoice void and paid protections
- Product deletion/rename protection
- Expense archive/restore
- Expense anomaly recalculation

Before committing backend changes, also check the Swagger routes and run a login,
create, edit, PDF, and AI smoke test against a disposable database.

## Deployment notes

This repository is not a production deployment package. Before internet-facing use:

- Use HTTPS for both frontend and API
- Store secrets outside source control and rotate exposed credentials
- Restrict CORS to exact origins
- Use a non-root MySQL account with minimum required privileges
- Back up MySQL and `.chromadb/`
- Set demo seeding to false
- Put the static frontend behind a CDN or web server
- Run Uvicorn behind a reverse proxy and process supervisor
- Configure log retention and monitoring
- Review privacy requirements before sending ledger or document data to an LLM
- Add database migrations if schema evolves
- Add rate limiting and stronger account controls before public exposure

The JWT is a bearer token stored in browser `localStorage`. Use HTTPS and consider
the XSS implications of any third-party scripts or unsafe HTML rendering.

## Troubleshooting

### `Set SMARTBIZ_DATABASE_URL...`

Create `.env`, copy `.env.example`, and set a valid SQLAlchemy URL. The URL must be
accessible from the backend process.

### `Set SMARTBIZ_JWT_SECRET...`

Set a random secret with at least 32 characters.

### `Access to fetch at ... has been blocked by CORS`

The frontend origin must exactly match an entry in `SMARTBIZ_CORS_ORIGINS`.
Restart Uvicorn after changing `.env`.

### Login succeeds but data is cleared

The browser token may be expired or invalid. JWTs expire after 12 hours. Sign in
again and verify `/api/auth/me`.

### API refuses to connect to MySQL

Check the host, port, database name, account, and PyMySQL driver. Confirm MySQL is
running and the application account can connect.

### RAG answers are unavailable

Confirm:

- `LLM_API_KEY` is set
- RAG dependencies are installed
- Authorized documents exist in `business_docs/`
- `.chromadb/` is writable
- The selected API/model supports the configured endpoint

Restart the API after adding or changing business documents so startup rebuilds the
index.

### PDF preview or Chart.js is unavailable

PDFs require ReportLab and a live API response. Chart.js requires internet access
from the browser unless the library is downloaded locally.

## Repository hygiene

The repository intentionally excludes:

- `.env`
- Python virtual environments
- `.chromadb/`
- Files inside `business_docs/`
- Local PDFs or private documents marked for exclusion

Before committing:

```powershell
git status --short
git diff --stat
```

Do not commit database credentials, JWT secrets, LLM keys, generated vector indexes,
customer exports, private documents, or local invoice PDFs.

No license is currently included. Add a license only after deciding the terms under
which the project may be reused.
