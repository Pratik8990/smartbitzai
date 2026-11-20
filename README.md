# SmartBiz AI

A small business operations dashboard with a static HTML/CSS/JavaScript frontend and a FastAPI/MySQL backend. It includes customer, inventory, invoice, expense, JWT authentication, PDF invoice, and optional business-document question-answering features.

## Requirements

- Python 3.10 or newer
- MySQL 8 or newer
- A modern browser

## Local setup

1. Create a MySQL database and a dedicated application user with access only to that database. Do not use the MySQL root account.
2. Create and activate a virtual environment, then install the backend dependencies:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r backend\requirements-rag.txt
   ```

3. Copy `.env.example` to `.env`. Set `SMARTBIZ_DATABASE_URL` to your MySQL URL and generate a strong JWT secret:

   ```powershell
   Copy-Item .env.example .env
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

   Put the generated value in `SMARTBIZ_JWT_SECRET` in `.env`. Never commit `.env` or share its contents.

4. Create the first administrator interactively:

   ```powershell
   python -m backend.create_admin
   ```

   The command refuses to create another initial admin if users already exist. Administrators can create regular users through `POST /api/auth/register`; registration is not open to anonymous visitors.

5. Start the API and frontend in separate terminals:

   ```powershell
   python -m uvicorn backend.main:app --reload
   ```

   ```powershell
   python -m http.server 5501 --directory frontend
   ```

   Open `http://127.0.0.1:5501`. The API documentation is at `http://127.0.0.1:8000/docs`.

## Configuration

- `SMARTBIZ_DATABASE_URL` and `SMARTBIZ_JWT_SECRET` are required. The JWT secret must be at least 32 characters.
- `SMARTBIZ_CORS_ORIGINS` is a comma-separated allowlist. Add the exact frontend origin when deploying; do not use `*`.
- `SMARTBIZ_SEED_DEMO_DATA` defaults to `false`. Set it to `true` only for a disposable demo database.
- `LLM_API_KEY` is optional. RAG uses local files in `business_docs/`; that directory is ignored by Git to avoid publishing private business documents. Add only documents you are authorized to send to your configured LLM provider.
- To host the frontend and API on different domains or ports, set `window.SMARTBIZ_API_BASE` before `script.js` loads and configure the API's CORS allowlist accordingly.

The project creates tables on startup, including a small archive index for expenses and customer audit history; existing business rows are not altered. The customer audit log records create, update, and delete actions with the authenticated username, timestamp, and changed field names (not old/new contact values). It begins tracking from the time this feature is enabled; earlier activity cannot be reconstructed. Customers, products, and expenses can be edited; customer records with invoice history and products referenced by invoices are protected from deletion or renaming. Paid or void invoices cannot be edited; pending invoices can be edited with stock adjusted, and voiding a pending invoice returns its units to inventory. Archived expenses are excluded from totals and can be restored. Back up the database before maintaining real business data. Demo seed data and local development settings are not a production deployment configuration. Use HTTPS and review operational, privacy, and security requirements before deploying.

Run focused record-removal tests with `python -m unittest discover -s tests`. They use an isolated in-memory SQLite database and do not connect to your configured MySQL database.

## Public repository hygiene

The repository ignores `.env`, virtual environments, generated ChromaDB data, the explicitly marked private document, the local invoice-check PDF, and files inside `business_docs/`. Verify the staged file list with `git status --short` before every commit.

No license is included. Add a license only after choosing the terms under which you want others to reuse this project.
