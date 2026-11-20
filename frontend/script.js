
// ----------------------------------------------------------------
// SmartBiz AI Frontend
// ----------------------------------------------------------------
const API_BASE = window.SMARTBIZ_API_BASE
  || `${window.location.protocol === 'file:' ? 'http:' : window.location.protocol}//${window.location.hostname || '127.0.0.1'}:8000/api`;

const DB = {
  customers: [],
  products: [],
  invoices: [],
  expenses: [],
  archivedExpenses: []
};

const EDITING = {
  customerId: null,
  productId: null,
  invoiceId: null,
  expenseId: null
};

const AUTH_KEYS = {
  token: 'smartbiz_token',
  username: 'smartbiz_username',
  role: 'smartbiz_user_role'
};

const APP_SETTINGS = {
  layoutDensity: 'comfortable',
  reduceMotion: false
};

const APP_SETTINGS_KEYS = {
  layoutDensity: 'smartbiz_layout_density',
  reduceMotion: 'smartbiz_reduce_motion'
};

const CHARTS = {
  revenue: null,
  expense: null
};

function applyAppSettings() {
  document.body.classList.toggle('compact-layout', APP_SETTINGS.layoutDensity === 'compact');
  document.body.classList.toggle('reduce-motion', APP_SETTINGS.reduceMotion);

  const densitySetting = document.getElementById('layoutDensitySetting');
  const motionSetting = document.getElementById('reduceMotionSetting');
  if (densitySetting) densitySetting.value = APP_SETTINGS.layoutDensity;
  if (motionSetting) motionSetting.checked = APP_SETTINGS.reduceMotion;
}

function loadAppSettings() {
  const density = localStorage.getItem(APP_SETTINGS_KEYS.layoutDensity);
  const reduceMotion = localStorage.getItem(APP_SETTINGS_KEYS.reduceMotion);

  if (density === 'comfortable' || density === 'compact') {
    APP_SETTINGS.layoutDensity = density;
  } else if (density !== null) {
    console.warn('Ignoring invalid saved layout density setting.');
  }

  if (reduceMotion === 'true' || reduceMotion === 'false') {
    APP_SETTINGS.reduceMotion = reduceMotion === 'true';
  } else if (reduceMotion !== null) {
    console.warn('Ignoring invalid saved reduced-motion setting.');
  }

  applyAppSettings();
}

function updateAppSetting(setting, value) {
  if (setting === 'layoutDensity') {
    if (value !== 'comfortable' && value !== 'compact') {
      throw new Error('Unsupported layout density setting.');
    }
    localStorage.setItem(APP_SETTINGS_KEYS.layoutDensity, value);
    APP_SETTINGS.layoutDensity = value;
  } else if (setting === 'reduceMotion') {
    if (typeof value !== 'boolean') {
      throw new Error('Reduced-motion setting must be a boolean.');
    }
    localStorage.setItem(APP_SETTINGS_KEYS.reduceMotion, String(value));
    APP_SETTINGS.reduceMotion = value;
  } else {
    throw new Error('Unsupported SmartBiz setting.');
  }

  applyAppSettings();
  const status = document.getElementById('settingsStatus');
  if (status) status.textContent = 'Preferences saved in this browser.';
}

function openSettingsModal() {
  openModal('settingsModal');
  applyAppSettings();
  document.getElementById('layoutDensitySetting')?.focus();
}

function closeSettingsModal() {
  closeModal('settingsModal');
  document.getElementById('brandSettingsButton')?.focus();
}

function formatCurrency(value) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(Number(value || 0));
}

function getAuthToken() {
  return localStorage.getItem(AUTH_KEYS.token);
}

function getAuthHeaders() {
  const token = getAuthToken();
  const headers = { 'Content-Type': 'application/json' };

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  return headers;
}

function apiFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = getAuthToken();
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  return fetch(url, { ...options, headers }).then((response) => {
    if (response.status === 401) {
      clearAuthState();
      checkAuthState();
      clearPrivateData();
      openModal('loginModal');
    }
    return response;
  });
}

function clearAuthState() {
  localStorage.removeItem(AUTH_KEYS.token);
  localStorage.removeItem(AUTH_KEYS.username);
  localStorage.removeItem(AUTH_KEYS.role);
}

function checkAuthState() {
  const token = getAuthToken();
  const badge = document.getElementById('authStatusBadge');
  const authText = document.getElementById('authStatusText');
  const workspaceStatus = document.getElementById('workspaceAccessStatus');
  const workspaceTag = document.getElementById('workspaceAccessTag');
  const workspaceDot = document.getElementById('workspaceStatusDot');

  if (token) {
    if (badge) {
      badge.textContent = 'SIGNED IN';
      badge.className = 'badge badge-paid';
    }

    if (authText) {
      const user = localStorage.getItem(AUTH_KEYS.username) || 'Admin';
      authText.textContent = user;
    }
    if (workspaceStatus) workspaceStatus.textContent = 'Secure session active';
    if (workspaceTag) {
      workspaceTag.textContent = 'ACTIVE';
      workspaceTag.className = 'role-tag is-authenticated';
    }
    if (workspaceDot) workspaceDot.className = 'status-dot is-authenticated';
  } else {
    if (badge) {
      badge.textContent = 'SIGN IN';
      badge.className = 'badge badge-standard';
    }

    if (authText) {
      authText.textContent = 'Guest Access';
    }
    if (workspaceStatus) workspaceStatus.textContent = 'Sign in to unlock';
    if (workspaceTag) {
      workspaceTag.textContent = 'LOCKED';
      workspaceTag.className = 'role-tag is-guest';
    }
    if (workspaceDot) workspaceDot.className = 'status-dot is-guest';
  }
}

function clearPrivateData() {
  DB.customers = [];
  DB.products = [];
  DB.invoices = [];
  DB.expenses = [];
  DB.archivedExpenses = [];

  ['kpi-gross-revenue', 'kpi-total-expenses', 'kpi-net-profit', 'kpi-receivables'].forEach((id) => {
    const node = document.getElementById(id);
    if (node) node.textContent = formatCurrency(0);
  });
  const stockNode = document.getElementById('kpi-lowstock-alert');
  if (stockNode) stockNode.textContent = '0 Items Critical Stock';

  renderCustomers();
  renderInventory();
  renderInvoices();
  renderExpenses();
  renderDashboardSummary();
  renderDashboardAlerts(false);
  populateDropdowns();
  drawCharts();
}

function setApiOfflineState(isOffline) {
  const existing = document.getElementById('apiOfflineBanner');

  if (isOffline) {
    if (!existing) {
      const banner = document.createElement('div');
      banner.id = 'apiOfflineBanner';
      banner.style.cssText = [
        'margin: 12px 18px 0 18px',
        'padding: 12px 16px',
        'border: 1px solid rgba(239, 68, 68, 0.45)',
        'background: rgba(127, 29, 29, 0.22)',
        'color: #fecaca',
        'border-radius: 12px',
        'font-size: 0.92rem',
        'font-weight: 600',
        'display: flex',
        'align-items: center',
        'gap: 8px'
      ].join(';');
      banner.innerHTML = '<span>⚠️</span><span>API offline: SmartBiz backend is not reachable. Start the FastAPI server or check the localhost connection.</span>';

      const container = document.querySelector('.view-container');
      if (container) {
        container.prepend(banner);
      }
    }
    return;
  }

  if (existing) {
    existing.remove();
  }
}

async function checkBackendHealth() {
  try {
    const response = await fetch(`${API_BASE}/health`, {
      method: 'GET',
      cache: 'no-store'
    });

    if (!response.ok) {
      throw new Error(`API status ${response.status}`);
    }

    setApiOfflineState(false);
    return true;
  } catch (error) {
    console.error('Backend health check failed:', error);
    setApiOfflineState(true);
    return false;
  }
}

function toggleAuthModal() {
  const token = getAuthToken();

  if (token) {
    const shouldLogout = confirm('You are currently signed in. Do you want to sign out?');
    if (!shouldLogout) return;

    clearAuthState();
    checkAuthState();
    clearPrivateData();
    if (typeof showToast === 'function') {
      showToast('Signed out successfully.');
    } else {
      alert('Signed out successfully.');
    }
    return;
  }

  if (typeof openModal === 'function') {
    openModal('loginModal');
  }
}

async function loginUser(username, password) {
  const formData = new URLSearchParams();
  formData.append('username', username);
  formData.append('password', password);

  try {
    const response = await fetch(`${API_BASE}/auth/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: formData
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(errData.detail || 'Authentication failed');
    }

    const data = await response.json();
    localStorage.setItem(AUTH_KEYS.token, data.access_token);
    localStorage.setItem(AUTH_KEYS.username, data.username || username);
    localStorage.setItem(AUTH_KEYS.role, data.role || 'Admin');

    checkAuthState();

    if (typeof showToast === 'function') {
      showToast(`Logged in successfully as ${data.username || username}`);
    }

    return true;
  } catch (error) {
    alert(error.message || String(error));
    return false;
  }
}

async function handleLoginSubmit(event) {
  if (event) event.preventDefault();

  const username = document.getElementById('loginUsername')?.value.trim() || '';
  const password = document.getElementById('loginPassword')?.value.trim() || '';

  if (!username || !password) {
    alert('Please enter both username and password.');
    return;
  }

  const success = await loginUser(username, password);
  if (!success) return;

  if (typeof closeModal === 'function') {
    closeModal('loginModal');
  }
  await renderAllViews();
}

function logoutUser() {
  clearAuthState();
  checkAuthState();
  clearPrivateData();

  if (typeof showToast === 'function') {
    showToast('Logged out successfully');
  }
}

function navigateTab(tabKey, clickedButton = null) {
  const viewContainer = document.querySelector('.view-container');
  if (viewContainer) {
    viewContainer.scrollTop = 0;
  }

  const tabViews = document.querySelectorAll('.tab-view');
  tabViews.forEach((tab) => tab.classList.remove('active-tab'));

  const buttons = document.querySelectorAll('.sidebar-menu .nav-btn');
  buttons.forEach((button) => button.classList.remove('active'));

  const target = document.getElementById(`view-${tabKey}`);
  if (target) {
    target.classList.add('active-tab');
  }

  if (clickedButton) {
    clickedButton.classList.add('active');
  }

  const titles = {
    dashboard: 'Dashboard Overview',
    customers: 'Customer CRM Directory',
    inventory: 'Inventory & Stock Control',
    invoices: 'Invoices & ReportLab PDF Engine',
    expenses: 'Sales & Outflow Ledger',
    'ai-copilot': 'SmartBiz Copilot'
  };

  const titleNode = document.getElementById('currentViewTitle');
  if (titleNode) {
    titleNode.textContent = titles[tabKey] || 'Dashboard';
  }

  if (tabKey === 'dashboard') {
    setTimeout(drawCharts, 50);
  }

  const sidebar = document.getElementById('main-sidebar');
  if (sidebar && window.innerWidth <= 900) {
    setSidebarOpen(false);
  }
}

function toggleSidebar() {
  const sidebar = document.getElementById('main-sidebar');
  const app = document.getElementById('app-container');
  if (!sidebar || !app) return;

  const isMobile = window.innerWidth <= 900;
  const isOpen = isMobile
    ? sidebar.classList.contains('mobile-open')
    : !app.classList.contains('sidebar-collapsed');
  setSidebarOpen(!isOpen);
}

function setSidebarOpen(isOpen) {
  const app = document.getElementById('app-container');
  const sidebar = document.getElementById('main-sidebar');
  const backdrop = document.querySelector('.sidebar-backdrop');
  const toggle = document.querySelector('.menu-toggle');
  const isMobile = window.innerWidth <= 900;

  if (app) app.classList.toggle('sidebar-collapsed', !isOpen && !isMobile);
  if (sidebar) sidebar.classList.toggle('mobile-open', isOpen && isMobile);
  if (backdrop) backdrop.classList.toggle('visible', isOpen && isMobile);
  if (toggle) {
    toggle.setAttribute('aria-expanded', String(isOpen));
    toggle.setAttribute('aria-label', isOpen ? 'Hide navigation menu' : 'Show navigation menu');
  }
}

function openModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.add('open');
  }
  if (modalId === 'logExpenseModal' && !EDITING.expenseId) {
    const dateInput = document.getElementById('expDateInput');
    if (dateInput && !dateInput.value) {
      const now = new Date();
      dateInput.value = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().split('T')[0];
    }
  }
}

function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.remove('open');
  }

  const editorModes = {
    addCustomerModal: {
      key: 'customerId',
      title: 'Add New Customer Account',
      submit: 'Save Customer',
      form: 'form'
    },
    addProductModal: {
      key: 'productId',
      title: 'Add SKU / Inventory Item',
      submit: 'Save to Inventory',
      form: 'form'
    },
    createInvoiceModal: {
      key: 'invoiceId',
      title: 'Create Tax Invoice',
      submit: 'Generate Invoice',
      form: 'form'
    },
    logExpenseModal: {
      key: 'expenseId',
      title: 'Log Business Outflow / Expense',
      submit: 'Record Expense',
      form: 'form'
    }
  };
  const editorMode = editorModes[modalId];
  if (editorMode) {
    EDITING[editorMode.key] = null;
    const title = modal?.querySelector('.modal-title');
    const submit = modal?.querySelector('button[type="submit"]');
    if (title) title.textContent = editorMode.title;
    if (submit) submit.textContent = editorMode.submit;
    modal?.querySelector(editorMode.form)?.reset();
  }
}

function showToast(message) {
  const toast = document.getElementById('toastNotification');
  const text = document.getElementById('toastText');

  if (!toast || !text) return;

  text.textContent = message;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 3000);
}

function handleGlobalSearch(value) {
  const query = (value || '').trim().toLowerCase();
  renderCustomers(query);
  renderInventory(query);
  renderInvoices(query);
}

function getBadgeClass(status) {
  const normalized = String(status || '').toUpperCase();
  if (normalized === 'PAID') return 'badge-paid';
  if (normalized === 'PENDING') return 'badge-pending';
  if (normalized === 'VOID') return 'badge-void';
  return 'badge-overdue';
}

async function renderAllViews() {
  await Promise.all([
    loadKPIs(),
    loadCustomers(),
    loadInventory(),
    loadInvoices(),
    loadExpenses()
  ]);

  populateDropdowns();
  renderDashboardAlerts();
  drawCharts();
}

async function loadKPIs() {
  try {
    const response = await apiFetch(`${API_BASE}/dashboard/kpis`);
    if (!response.ok) return;

    const data = await response.json();
    const revenueNode = document.getElementById('kpi-gross-revenue');
    const expenseNode = document.getElementById('kpi-total-expenses');
    const profitNode = document.getElementById('kpi-net-profit');
    const receivablesNode = document.getElementById('kpi-receivables');
    const stockNode = document.getElementById('kpi-lowstock-alert');

    if (revenueNode) {
      revenueNode.textContent = formatCurrency(data.gross_revenue || 0);
    }

    if (expenseNode) {
      expenseNode.textContent = formatCurrency(data.total_expenses || 0);
    }

    if (profitNode) {
      profitNode.textContent = formatCurrency(data.net_profit || 0);
    }

    if (receivablesNode) {
      receivablesNode.textContent = formatCurrency(data.receivables || 0);
    }

    if (stockNode) {
      stockNode.textContent = `${data.low_stock_critical_count || 0} Items Critical Stock`;
    }
  } catch (error) {
    console.error('Failed to load KPIs:', error);
  }
}

async function loadCustomers() {
  try {
    const response = await apiFetch(`${API_BASE}/customers`);
    if (!response.ok) return;
    DB.customers = await response.json();
    renderCustomers();
  } catch (error) {
    console.error('Failed to fetch customers:', error);
  }
}

async function loadInventory() {
  try {
    const response = await apiFetch(`${API_BASE}/inventory`);
    if (!response.ok) return;
    DB.products = await response.json();
    renderInventory();
  } catch (error) {
    console.error('Failed to fetch inventory:', error);
  }
}

async function loadInvoices() {
  try {
    const response = await apiFetch(`${API_BASE}/invoices`);
    if (!response.ok) return;
    DB.invoices = await response.json();
    renderInvoices();
    renderDashboardSummary();
  } catch (error) {
    console.error('Failed to fetch invoices:', error);
  }
}

async function loadExpenses() {
  try {
    const response = await apiFetch(`${API_BASE}/expenses`);
    if (!response.ok) return;
    DB.expenses = await response.json();
    renderExpenses();
  } catch (error) {
    console.error('Failed to fetch expenses:', error);
  }
}

async function loadArchivedExpenses() {
  try {
    const response = await apiFetch(`${API_BASE}/expenses/archived`);
    if (!response.ok) {
      throw new Error('Could not load archived expenses.');
    }
    DB.archivedExpenses = await response.json();
    renderExpenses();
  } catch (error) {
    alert(error.message || String(error));
  }
}

function toggleArchivedExpenses(showArchived) {
  if (showArchived) {
    loadArchivedExpenses();
  } else {
    renderExpenses();
  }
}

function renderDashboardSummary() {
  const tbody = document.getElementById('dash-recent-invoices-body');
  if (!tbody) return;

  tbody.innerHTML = DB.invoices.slice(0, 4).map((invoice) => `
    <tr>
      <td><strong>${invoice.id}</strong></td>
      <td>${invoice.customer_name || invoice.customerName || 'N/A'}</td>
      <td><strong>${formatCurrency(invoice.amount)}</strong></td>
      <td><span class="badge ${getBadgeClass(invoice.status)}">${invoice.status}</span></td>
      <td style="text-align: right;">
        <button class="btn btn-secondary btn-sm" onclick="openPdfPreview('${invoice.id}')">View PDF</button>
      </td>
    </tr>
  `).join('');
}

function renderDashboardAlerts(dataReady = true) {
  const status = document.getElementById('dashboard-alert-status');
  const summary = document.getElementById('dashboard-alert-summary');
  const lowStockCount = document.getElementById('dashboard-low-stock-count');
  const flaggedExpenseCount = document.getElementById('dashboard-flagged-expense-count');
  if (!status || !summary || !lowStockCount || !flaggedExpenseCount) return;

  if (!getAuthToken()) {
    status.textContent = 'Sign-in required';
    status.className = 'watchlist-status is-unavailable';
    summary.textContent = 'Sign in to load your current inventory and expense alerts.';
    lowStockCount.textContent = '—';
    flaggedExpenseCount.textContent = '—';
    return;
  }

  if (!dataReady) {
    status.textContent = 'Unavailable';
    status.className = 'watchlist-status is-unavailable';
    summary.textContent = 'Live alerts are unavailable. Check your workspace connection and try again.';
    lowStockCount.textContent = '—';
    flaggedExpenseCount.textContent = '—';
    return;
  }

  const lowStockProducts = DB.products.filter((product) => {
    const stock = Number(product.stock);
    const minimumStock = Number(product.min_stock ?? product.minStock ?? 5);
    return Number.isFinite(stock) && Number.isFinite(minimumStock) && stock <= minimumStock;
  });
  const flaggedExpenses = DB.expenses.filter((expense) => expense.anomaly === true);
  const lowStockTotal = lowStockProducts.length;
  const flaggedExpenseTotal = flaggedExpenses.length;
  const alertTotal = lowStockTotal + flaggedExpenseTotal;

  lowStockCount.textContent = String(lowStockTotal);
  flaggedExpenseCount.textContent = String(flaggedExpenseTotal);

  if (alertTotal === 0) {
    status.textContent = 'All clear';
    status.className = 'watchlist-status is-clear';
    summary.textContent = 'No inventory or expense items currently need review.';
    return;
  }

  status.textContent = `${alertTotal} ${alertTotal === 1 ? 'item' : 'items'} to review`;
  status.className = 'watchlist-status is-warning';
  const alertMessages = [];
  if (lowStockTotal > 0) {
    alertMessages.push(
      `${lowStockTotal} product${lowStockTotal === 1 ? '' : 's'} at or below minimum stock`
    );
  }
  if (flaggedExpenseTotal > 0) {
    alertMessages.push(
      `${flaggedExpenseTotal} expense${flaggedExpenseTotal === 1 ? '' : 's'} flagged for review`
    );
  }
  summary.textContent = `${alertMessages.join(' · ')}.`;
}

function renderCustomers(filter = '') {
  const tbody = document.getElementById('customers-table-body');
  if (!tbody) return;

  const query = filter.toLowerCase();
  const filtered = DB.customers.filter((customer) => {
    if (!query) return true;
    return (
      (customer.name || '').toLowerCase().includes(query) ||
      (customer.email || '').toLowerCase().includes(query)
    );
  });

  tbody.innerHTML = filtered.map((customer) => `
    <tr>
      <td class="customer-identity">
        <strong>${customer.name}</strong><br>
        <span class="customer-id">${customer.id}</span>
      </td>
      <td>${customer.email}</td>
      <td>${customer.phone}</td>
      <td><span class="badge badge-enterprise">${customer.tier}</span></td>
      <td class="customer-spend"><strong>${formatCurrency(customer.spend || 0)}</strong></td>
      <td class="customer-actions">
        <button class="btn btn-secondary btn-sm" onclick="openCustomerAuditLog('${customer.id}')">Audit Log</button>
        <button class="btn btn-secondary btn-sm" onclick="editCustomer('${customer.id}')">Edit</button>
        <button class="btn btn-danger btn-sm" onclick="deleteCustomer('${customer.id}')">Delete</button>
      </td>
    </tr>
  `).join('');
}

async function openCustomerAuditLog(customerId) {
  const customer = DB.customers.find((item) => item.id === customerId);
  const customerName = document.getElementById('customerAuditCustomerName');
  const status = document.getElementById('customerAuditStatus');
  const tbody = document.getElementById('customerAuditTableBody');
  if (!customerName || !status || !tbody) return;

  customerName.textContent = customer ? `${customer.name} (${customer.id})` : customerId;
  status.textContent = 'Loading customer history…';
  tbody.replaceChildren();
  openModal('customerAuditModal');

  try {
    const response = await apiFetch(
      `${API_BASE}/customers/${encodeURIComponent(customerId)}/audit-log`
    );
    if (!response.ok) {
      throw new Error(await apiErrorMessage(response, 'Could not load customer history.'));
    }

    const entries = await response.json();
    if (!entries.length) {
      status.textContent = 'No earlier activity is available. Changes are recorded from now on.';
      return;
    }

    status.textContent = '';
    entries.forEach((entry) => {
      const row = document.createElement('tr');
      const timestamp = new Date(entry.created_at);
      const timestampCell = document.createElement('td');
      const actionCell = document.createElement('td');
      const actorCell = document.createElement('td');
      const fieldsCell = document.createElement('td');
      const fieldNames = (entry.changed_fields || []).map((field) => field.replace(/_/g, ' '));

      timestampCell.textContent = Number.isNaN(timestamp.getTime())
        ? entry.created_at
        : timestamp.toLocaleString();
      actionCell.textContent = entry.action;
      actorCell.textContent = entry.actor;
      fieldsCell.textContent = fieldNames.length
        ? fieldNames.join(', ')
        : entry.action === 'created'
          ? 'Customer record created'
          : 'Customer record deleted';
      row.append(timestampCell, actionCell, actorCell, fieldsCell);
      tbody.appendChild(row);
    });
  } catch (error) {
    status.textContent = error.message || 'Could not load customer history.';
  }
}

function renderInventory(filter = '') {
  const tbody = document.getElementById('inventory-table-body');
  if (!tbody) return;

  const query = filter.toLowerCase();
  const filtered = DB.products.filter((product) => {
    if (!query) return true;
    return (
      (product.name || '').toLowerCase().includes(query) ||
      (product.sku || '').toLowerCase().includes(query)
    );
  });

  tbody.innerHTML = filtered.map((product) => {
    const minThreshold = product.min_stock ?? product.minStock ?? 5;
    const isCritical = product.stock <= minThreshold;

    return `
      <tr>
        <td class="inventory-sku"><code>${product.sku}</code></td>
        <td class="inventory-item"><strong>${product.name}</strong></td>
        <td class="inventory-category">${product.category}</td>
        <td class="inventory-price">${formatCurrency(product.price)}</td>
        <td class="inventory-stock"><strong>${product.stock} units</strong></td>
        <td>
          <span class="badge ${isCritical ? 'badge-overdue' : 'badge-paid'}">
            ${isCritical ? 'Low Stock' : 'Optimal'}
          </span>
        </td>
        <td class="inventory-actions">
          <button class="btn btn-secondary btn-sm" onclick="restockItem('${product.id}')">+ Restock (10)</button>
          <button class="btn btn-secondary btn-sm" onclick="editProduct('${product.id}')">Edit</button>
          <button class="btn btn-danger btn-sm" onclick="deleteProduct('${product.id}')">Delete</button>
        </td>
      </tr>
    `;
  }).join('');
}

function renderInvoices(filter = '') {
  const tbody = document.getElementById('invoices-table-body');
  if (!tbody) return;

  const query = filter.toLowerCase();
  const filtered = DB.invoices.filter((invoice) => {
    if (!query) return true;
    const customerName = invoice.customer_name || invoice.customerName || '';
    return (
      invoice.id.toLowerCase().includes(query) ||
      customerName.toLowerCase().includes(query)
    );
  });

  tbody.innerHTML = filtered.map((invoice) => `
    <tr>
      <td class="invoice-reference"><strong>${invoice.id}</strong></td>
      <td class="invoice-customer">${invoice.customer_name || invoice.customerName || 'N/A'}</td>
      <td class="invoice-date">${invoice.date}</td>
      <td class="invoice-amount"><strong>${formatCurrency(invoice.amount)}</strong></td>
      <td><span class="badge ${getBadgeClass(invoice.status)}">${invoice.status}</span></td>
      <td class="invoice-actions">
        <button class="btn btn-secondary btn-sm" onclick="openPdfPreview('${invoice.id}')">View PDF</button>
        ${['PENDING', 'OVERDUE'].includes(String(invoice.status).toUpperCase())
    ? `<button class="btn btn-secondary btn-sm" onclick="editInvoice('${invoice.id}')">Edit</button><button class="btn btn-danger btn-sm" onclick="voidInvoice('${invoice.id}')">Void</button>`
    : ''}
      </td>
    </tr>
  `).join('');
}

function renderExpenses() {
  const tbody = document.getElementById('expenses-table-body');
  if (!tbody) return;

  const showArchived = document.getElementById('showArchivedExpenses')?.checked;
  const expenses = showArchived ? DB.archivedExpenses : DB.expenses;

  tbody.innerHTML = expenses.map((expense) => `
    <tr>
      <td class="expense-date">${expense.date}</td>
      <td class="expense-description"><strong>${expense.description}</strong></td>
      <td class="expense-category">${expense.category}</td>
      <td class="expense-amount"><strong>${formatCurrency(expense.amount)}</strong></td>
      <td class="expense-vendor">${expense.vendor}</td>
      <td>
        <span class="badge ${expense.anomaly ? 'badge-overdue' : 'badge-paid'}">
          ${expense.anomaly ? 'Anomaly' : 'Normal'}
        </span>
      </td>
      <td class="expense-actions">
        <button class="btn btn-secondary btn-sm" onclick="editExpense(${expense.id})">Edit</button>
        ${showArchived
    ? `<button class="btn btn-secondary btn-sm" onclick="restoreExpense(${expense.id})">Restore</button>`
    : `<button class="btn btn-danger btn-sm" onclick="archiveExpense(${expense.id})">Archive</button>`}
      </td>
    </tr>
  `).join('');
}

async function apiErrorMessage(response, fallback) {
  const payload = await response.json().catch(() => null);
  return typeof payload?.detail === 'string' ? payload.detail : fallback;
}

async function deleteCustomer(id) {
  if (!confirm('Delete this customer? Customers with invoice history cannot be deleted.')) return;

  try {
    const response = await apiFetch(`${API_BASE}/customers/${encodeURIComponent(id)}`, { method: 'DELETE' });
    if (!response.ok) throw new Error(await apiErrorMessage(response, 'Could not delete customer.'));
    showToast('Customer deleted');
    await renderAllViews();
  } catch (error) {
    alert(error.message || String(error));
  }
}

function editCustomer(id) {
  const customer = DB.customers.find((item) => item.id === id);
  if (!customer) return;

  EDITING.customerId = id;
  document.getElementById('custNameInput').value = customer.name || '';
  document.getElementById('custEmailInput').value = customer.email || '';
  document.getElementById('custPhoneInput').value = customer.phone || '';
  document.getElementById('custTierInput').value = customer.tier || 'Standard';
  document.querySelector('#addCustomerModal .modal-title').textContent = 'Edit Customer Account';
  document.querySelector('#addCustomerModal button[type="submit"]').textContent = 'Save Changes';
  clearCustomerFieldError('custNameInput');
  clearCustomerFieldError('custEmailInput');
  clearCustomerFieldError('custPhoneInput');
  clearCustomerFieldError('custTierInput');
  openModal('addCustomerModal');
}

async function deleteProduct(id) {
  if (!confirm('Permanently delete this product from inventory?')) return;

  try {
    const response = await apiFetch(`${API_BASE}/inventory/${encodeURIComponent(id)}`, { method: 'DELETE' });
    if (!response.ok) throw new Error(await apiErrorMessage(response, 'Could not delete product.'));
    showToast('Product deleted');
    await renderAllViews();
  } catch (error) {
    alert(error.message || String(error));
  }
}

function editProduct(id) {
  const product = DB.products.find((item) => item.id === id);
  if (!product) return;

  EDITING.productId = id;
  document.getElementById('prodNameInput').value = product.name || '';
  document.getElementById('prodCategoryInput').value = product.category || '';
  document.getElementById('prodStockInput').value = product.stock ?? 0;
  document.getElementById('prodMinStockInput').value = product.min_stock ?? product.minStock ?? 5;
  document.getElementById('prodPriceInput').value = product.price ?? 0;
  document.querySelector('#addProductModal .modal-title').textContent = 'Edit Inventory Item';
  document.querySelector('#addProductModal button[type="submit"]').textContent = 'Save Changes';
  openModal('addProductModal');
}

function editInvoice(id) {
  const invoice = DB.invoices.find((item) => item.id === id);
  if (!invoice || !['PENDING', 'OVERDUE'].includes(String(invoice.status).toUpperCase())) return;

  const product = DB.products.find((item) => item.name === invoice.item);
  if (!product) {
    alert('The original product is no longer available. Void and reissue this invoice instead.');
    return;
  }

  EDITING.invoiceId = id;
  document.getElementById('modalInvCustomer').value = invoice.customer_id || invoice.customerId || '';
  document.getElementById('modalInvDate').value = invoice.date || '';
  document.getElementById('modalInvProduct').value = product.id;
  document.getElementById('modalInvQty').value = invoice.qty || 1;
  recalculateInvoiceFormTotal();
  document.querySelector('#createInvoiceModal .modal-title').textContent = 'Edit Unpaid Invoice';
  document.querySelector('#createInvoiceModal button[type="submit"]').textContent = 'Save Changes';
  openModal('createInvoiceModal');
}

function editExpense(id) {
  const expense = [...DB.expenses, ...DB.archivedExpenses].find((item) => item.id === id);
  if (!expense) return;

  EDITING.expenseId = id;
  document.getElementById('expDateInput').value = expense.date || '';
  document.getElementById('expDescInput').value = expense.description || '';
  document.getElementById('expCategoryInput').value = expense.category || '';
  document.getElementById('expAmountInput').value = expense.amount ?? 0;
  document.getElementById('expVendorInput').value = expense.vendor || '';
  document.querySelector('#logExpenseModal .modal-title').textContent = 'Edit Business Expense';
  document.querySelector('#logExpenseModal button[type="submit"]').textContent = 'Save Changes';
  openModal('logExpenseModal');
}

async function voidInvoice(id) {
  if (!confirm('Void this unpaid invoice? It will remain in the invoice history.')) return;

  try {
    const response = await apiFetch(`${API_BASE}/invoices/${encodeURIComponent(id)}/void`, { method: 'PATCH' });
    if (!response.ok) throw new Error(await apiErrorMessage(response, 'Could not void invoice.'));
    showToast('Invoice voided');
    await renderAllViews();
  } catch (error) {
    alert(error.message || String(error));
  }
}

async function archiveExpense(id) {
  if (!confirm('Archive this expense? It will be excluded from totals and can be restored.')) return;

  try {
    const response = await apiFetch(`${API_BASE}/expenses/${id}/archive`, { method: 'PATCH' });
    if (!response.ok) throw new Error(await apiErrorMessage(response, 'Could not archive expense.'));
    showToast('Expense archived');
    await renderAllViews();
    if (document.getElementById('showArchivedExpenses')?.checked) await loadArchivedExpenses();
  } catch (error) {
    alert(error.message || String(error));
  }
}

async function restoreExpense(id) {
  try {
    const response = await apiFetch(`${API_BASE}/expenses/${id}/restore`, { method: 'PATCH' });
    if (!response.ok) throw new Error(await apiErrorMessage(response, 'Could not restore expense.'));
    showToast('Expense restored');
    await renderAllViews();
    if (document.getElementById('showArchivedExpenses')?.checked) await loadArchivedExpenses();
  } catch (error) {
    alert(error.message || String(error));
  }
}

async function restockItem(id) {
  try {
    const response = await apiFetch(`${API_BASE}/inventory/${id}/restock?units=10`, {
      method: 'POST',
      headers: getAuthHeaders()
    });

    if (!response.ok) {
      throw new Error('Restock failed');
    }

    const updated = await response.json();
    showToast(`Restocked ${updated.name} (+10 units)`);
    await renderAllViews();
  } catch (error) {
    alert(error.message || String(error));
  }
}

function populateDropdowns() {
  const customerSelect = document.getElementById('modalInvCustomer');
  const productSelect = document.getElementById('modalInvProduct');

  if (customerSelect) {
    customerSelect.innerHTML = DB.customers.length ? DB.customers
      .map((customer) => `<option value="${customer.id}">${customer.name}</option>`)
      .join('') : '<option value="">No customers available</option>';
  }

  if (productSelect) {
    productSelect.innerHTML = DB.products.length ? DB.products
      .map((product) => `<option value="${product.id}" data-price="${product.price}">${product.name} (${formatCurrency(product.price)})</option>`)
      .join('') : '<option value="">No products available</option>';

    recalculateInvoiceFormTotal();
  }
}

function recalculateInvoiceFormTotal() {
  const productSelect = document.getElementById('modalInvProduct');
  const qtyInput = document.getElementById('modalInvQty');
  const unitPriceInput = document.getElementById('modalInvUnitPrice');
  const totalInput = document.getElementById('modalInvCalculatedTotal');

  if (!productSelect || !productSelect.selectedOptions[0]) return;

  const unitPrice = Number(productSelect.selectedOptions[0].dataset.price || 0);
  const quantity = Number(qtyInput?.value || 1);
  const subtotal = unitPrice * quantity;
  const total = subtotal * 1.08;

  if (unitPriceInput) {
    unitPriceInput.value = unitPrice.toFixed(2);
  }

  if (totalInput) {
    totalInput.value = `$${total.toFixed(2)}`;
  }
}

const CUSTOMER_FIELD_ERRORS = {
  custNameInput: 'custNameError',
  custEmailInput: 'custEmailError',
  custPhoneInput: 'custPhoneError',
  custTierInput: 'custTierError'
};

function showCustomerFormMessage(message) {
  const messageBox = document.getElementById('customerFormMessage');
  if (!messageBox) return;
  messageBox.textContent = message;
  messageBox.hidden = !message;
}

function setCustomerFieldError(fieldId, message) {
  const input = document.getElementById(fieldId);
  const error = document.getElementById(CUSTOMER_FIELD_ERRORS[fieldId]);
  if (input) {
    input.setAttribute('aria-invalid', message ? 'true' : 'false');
  }
  if (error) {
    error.textContent = message;
    error.hidden = !message;
  }
}

function clearCustomerFieldError(fieldId) {
  setCustomerFieldError(fieldId, '');
  showCustomerFormMessage('');
}

function validateCustomerForm(payload) {
  const errors = {};
  const nameLooksLikePhone = /^[+0-9().\-\s]+$/.test(payload.name)
    && (payload.name.match(/\d/g) || []).length >= 7;

  if (payload.name.length < 2 || payload.name.length > 100 || payload.name.includes('@') || nameLooksLikePhone) {
    errors.custNameInput = 'Enter a company/client name (2-100 characters), not an email address or phone number.';
  }
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(payload.email)) {
    errors.custEmailInput = 'Enter an email address like name@company.com.';
  }
  const phoneDigits = payload.phone.replace(/\D/g, '').length;
  if (!/^[+0-9().\-\s]+$/.test(payload.phone) || phoneDigits < 7 || phoneDigits > 15) {
    errors.custPhoneInput = 'Enter a phone number with 7-15 digits. Do not enter an email or company name here.';
  }
  if (!['Enterprise', 'Growth', 'Standard'].includes(payload.tier)) {
    errors.custTierInput = 'Choose Enterprise, Growth, or Standard.';
  }
  return errors;
}

async function handleAddCustomerSubmit(event) {
  event.preventDefault();
  Object.keys(CUSTOMER_FIELD_ERRORS).forEach(clearCustomerFieldError);

  const payload = {
    name: document.getElementById('custNameInput')?.value.trim() || '',
    email: document.getElementById('custEmailInput')?.value.trim() || '',
    phone: document.getElementById('custPhoneInput')?.value.trim() || '',
    tier: document.getElementById('custTierInput')?.value || 'Standard'
  };
  const validationErrors = validateCustomerForm(payload);
  const invalidFields = Object.entries(validationErrors);
  if (invalidFields.length) {
    invalidFields.forEach(([fieldId, message]) => setCustomerFieldError(fieldId, message));
    showCustomerFormMessage('Please correct the highlighted customer fields.');
    document.getElementById(invalidFields[0][0])?.focus();
    return;
  }

  const editingId = EDITING.customerId;
  try {
    const url = editingId
      ? `${API_BASE}/customers/${encodeURIComponent(editingId)}`
      : `${API_BASE}/customers`;
    const response = await apiFetch(url, {
      method: editingId ? 'PUT' : 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      if (Array.isArray(errData.detail)) {
        const backendFieldNames = {
          name: 'custNameInput',
          email: 'custEmailInput',
          phone: 'custPhoneInput',
          tier: 'custTierInput'
        };
        let hasFieldErrors = false;
        errData.detail.forEach((item) => {
          const fieldId = backendFieldNames[item.loc?.[item.loc.length - 1]];
          if (fieldId) {
            setCustomerFieldError(fieldId, item.msg || 'Check this value and try again.');
            hasFieldErrors = true;
          }
        });
        if (hasFieldErrors) {
          showCustomerFormMessage('Please correct the highlighted customer fields.');
          return;
        }
      }

      const message = typeof errData.detail === 'string'
        ? errData.detail
        : 'Failed to add customer. Check the information and try again.';
      if (response.status === 409) {
        setCustomerFieldError('custEmailInput', message);
        showCustomerFormMessage('The email address needs attention.');
        document.getElementById('custEmailInput')?.focus();
        return;
      }
      showCustomerFormMessage(message);
      return;
    }

    closeModal('addCustomerModal');
    await renderAllViews();
    showToast(`${editingId ? 'Updated' : 'Added'} ${payload.name} in the customer directory.`);

    const form = event.target;
    if (form) form.reset();
  } catch (error) {
    showCustomerFormMessage('Could not reach the server. Your customer information was not saved; check the API connection and try again.');
    console.error('Failed to add customer:', error);
  }
}

async function handleCreateInvoiceSubmit(event) {
  event.preventDefault();
  event.stopPropagation();

  const payload = {
    customer_id: document.getElementById('modalInvCustomer')?.value || '',
    product_id: document.getElementById('modalInvProduct')?.value || '',
    issue_date: document.getElementById('modalInvDate')?.value || new Date().toISOString().split('T')[0],
    quantity: Number(document.getElementById('modalInvQty')?.value || 1)
  };

  if (!payload.customer_id || !payload.product_id) {
    alert('Please select both a valid customer and a product.');
    return;
  }

  if (!Number.isFinite(payload.quantity) || payload.quantity <= 0) {
    alert('Quantity must be greater than 0.');
    return;
  }

  const editingId = EDITING.invoiceId;
  try {
    const url = editingId
      ? `${API_BASE}/invoices/${encodeURIComponent(editingId)}`
      : `${API_BASE}/invoices`;
    const response = await apiFetch(url, {
      method: editingId ? 'PUT' : 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(errData.detail || 'Failed to create invoice');
    }

    const result = await response.json();
    closeModal('createInvoiceModal');
    await renderAllViews();
    showToast(`${editingId ? 'Updated' : 'Generated'} invoice ${result.id || ''}.`);

    if (event.target) event.target.reset();
  } catch (error) {
    alert(error.message || String(error));
  }
}

async function handleAddProductSubmit(event) {
  event.preventDefault();

  const editingId = EDITING.productId;
  const payload = {
    name: document.getElementById('prodNameInput')?.value.trim() || '',
    category: document.getElementById('prodCategoryInput')?.value.trim() || '',
    price: Number(document.getElementById('prodPriceInput')?.value || 0),
    stock: Number(document.getElementById('prodStockInput')?.value || 0),
    min_stock: Number(document.getElementById('prodMinStockInput')?.value || 0)
  };

  try {
    const url = editingId
      ? `${API_BASE}/inventory/${encodeURIComponent(editingId)}`
      : `${API_BASE}/inventory`;
    const response = await apiFetch(url, {
      method: editingId ? 'PUT' : 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(errData.detail || 'Failed to add product to catalog');
    }

    closeModal('addProductModal');
    await renderAllViews();
    showToast(`${editingId ? 'Updated' : 'Added'} ${payload.name} in the stock catalog.`);

    if (event.target) event.target.reset();
  } catch (error) {
    showToast(error.message || String(error));
  }
}

async function handleLogExpenseSubmit(event) {
  event.preventDefault();

  const payload = {
    date: document.getElementById('expDateInput')?.value || new Date().toISOString().split('T')[0],
    description: document.getElementById('expDescInput')?.value.trim() || '',
    category: document.getElementById('expCategoryInput')?.value || '',
    amount: Number(document.getElementById('expAmountInput')?.value || 0),
    vendor: document.getElementById('expVendorInput')?.value.trim() || ''
  };

  const editingId = EDITING.expenseId;
  try {
    const url = editingId
      ? `${API_BASE}/expenses/${editingId}`
      : `${API_BASE}/expenses`;
    const response = await apiFetch(url, {
      method: editingId ? 'PUT' : 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(errData.detail || 'Failed to record expense');
    }

    closeModal('logExpenseModal');
    await renderAllViews();
    if (document.getElementById('showArchivedExpenses')?.checked) await loadArchivedExpenses();
    showToast(`${editingId ? 'Updated' : 'Logged'} expense of ${formatCurrency(payload.amount)}.`);

    if (event.target) event.target.reset();
  } catch (error) {
    showToast(error.message || String(error));
  }
}

function openPdfPreview(invoiceId) {
  if (!invoiceId) return;

  const pdfUrl = `${API_BASE}/invoices/${encodeURIComponent(invoiceId)}/pdf`;

  const invoice = DB.invoices.find((item) => item.id === invoiceId);
  if (invoice) {
    const customer = DB.customers.find((item) => item.id === (invoice.customer_id || invoice.customerId)) || {
      email: 'billing@client.org'
    };

    const previewNumber = document.getElementById('pdfPreviewNumber');
    const previewDate = document.getElementById('pdfPreviewDate');
    const previewClientName = document.getElementById('pdfPreviewClientName');
    const previewClientEmail = document.getElementById('pdfPreviewClientEmail');
    const previewStatus = document.getElementById('pdfPreviewStatusBadge');
    const previewAmount = document.getElementById('pdfPreviewAmount');
    const previewTax = document.getElementById('pdfPreviewTax');
    const previewTotal = document.getElementById('pdfPreviewTotal');

    if (previewNumber) previewNumber.textContent = invoice.id;
    if (previewDate) previewDate.textContent = `Date: ${invoice.date}`;
    if (previewClientName) previewClientName.textContent = invoice.customer_name || invoice.customerName || 'N/A';
    if (previewClientEmail) previewClientEmail.textContent = customer.email;
    if (previewAmount) previewAmount.textContent = formatCurrency(invoice.amount);

    const subtotal = Number(invoice.amount || 0) / 1.08;
    const taxAmount = Number(invoice.amount || 0) - subtotal;

    if (previewTax) previewTax.textContent = formatCurrency(taxAmount);
    if (previewTotal) previewTotal.textContent = formatCurrency(invoice.amount || 0);

    if (previewStatus) {
      previewStatus.innerHTML = `<span class="badge ${getBadgeClass(invoice.status)}">${invoice.status}</span>`;
    }
  }

  const token = getAuthToken();
  const fetchOptions = {
    method: 'GET',
    headers: getAuthHeaders()
  };

  apiFetch(pdfUrl, fetchOptions)
    .then(async (response) => {
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to generate invoice PDF');
      }

      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = objectUrl;
      link.download = `${invoiceId}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);

      if (token) {
        showToast('Invoice PDF downloaded successfully.');
      } else {
        showToast('Invoice PDF opened successfully.');
      }
    })
    .catch((error) => {
      console.error('PDF generation failed:', error);
      showToast(error.message || 'Unable to open invoice PDF.');
      if (document.getElementById('pdfPreviewModal')) {
        openModal('pdfPreviewModal');
      }
    });
}

function drawCharts() {
  drawRevenueChart();
  drawDoughnutChart();
}

function drawRevenueChart() {
  if (typeof Chart === 'undefined') return;
  const canvas = document.getElementById('financialChartCanvas');
  if (!canvas) return;

  if (CHARTS.revenue) {
    CHARTS.revenue.destroy();
  }

  const monthlyPeriods = Array.from({ length: 6 }, (_, index) => {
    const date = new Date();
    date.setDate(1);
    date.setMonth(date.getMonth() - (5 - index));
    const key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
    return {
      key,
      label: date.toLocaleDateString('en-US', { month: 'short' })
    };
  });
  const monthlyTotal = (records) => {
    const totals = new Map(monthlyPeriods.map((period) => [period.key, 0]));
    records.forEach((record) => {
      const month = String(record.date || '').slice(0, 7);
      if (totals.has(month)) {
        totals.set(month, totals.get(month) + Number(record.amount || 0));
      }
    });
    return monthlyPeriods.map((period) => totals.get(period.key));
  };

  const context = canvas.getContext('2d');
  CHARTS.revenue = new Chart(context, {
    type: 'line',
    data: {
      labels: monthlyPeriods.map((period) => period.label),
      datasets: [
        {
          label: 'Invoiced Sales ($)',
          data: monthlyTotal(DB.invoices.filter((invoice) => String(invoice.status).toUpperCase() !== 'VOID')),
          borderColor: '#4f46e5',
          backgroundColor: 'rgba(79, 70, 229, 0.08)',
          fill: true,
          tension: 0.35,
          borderWidth: 2.5,
          pointBackgroundColor: '#4f46e5',
          pointRadius: 4,
          pointHoverRadius: 6
        },
        {
          label: 'Expenses ($)',
          data: monthlyTotal(DB.expenses),
          borderColor: '#ef4444',
          borderDash: [5, 5],
          backgroundColor: 'transparent',
          tension: 0.35,
          borderWidth: 2,
          pointBackgroundColor: '#ef4444',
          pointRadius: 3,
          pointHoverRadius: 5
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: 'index',
        intersect: false
      },
      plugins: {
        legend: {
          position: 'top',
          labels: {
            boxWidth: 12,
            font: { size: 11, family: 'sans-serif' },
            color: '#64748b'
          }
        },
        tooltip: {
          backgroundColor: '#0f172a',
          titleFont: { size: 12, weight: 'bold' },
          bodyFont: { size: 12 },
          padding: 10,
          callbacks: {
            label(context) {
              return ` ${context.dataset.label}: $${context.raw.toLocaleString()}`;
            }
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: {
            color: '#64748b',
            font: { size: 10 }
          }
        },
        y: {
          grid: { color: '#f1f5f9' },
          ticks: {
            color: '#94a3b8',
            font: { size: 10 },
            callback: (value) => `$${value / 1000}k`
          },
          suggestedMax: 60000
        }
      }
    }
  });
}

function drawDoughnutChart() {
  if (typeof Chart === 'undefined') return;
  const canvas = document.getElementById('expenseCategoryCanvas');
  if (!canvas) return;

  if (CHARTS.expense) {
    CHARTS.expense.destroy();
  }

  const categoryTotals = new Map();
  DB.expenses.forEach((expense) => {
    const category = expense.category || 'Uncategorized';
    categoryTotals.set(category, (categoryTotals.get(category) || 0) + Number(expense.amount || 0));
  });

  const context = canvas.getContext('2d');
  CHARTS.expense = new Chart(context, {
    type: 'doughnut',
    data: {
      labels: Array.from(categoryTotals.keys()),
      datasets: [
        {
          data: Array.from(categoryTotals.values()),
          backgroundColor: ['#4f46e5', '#ec4899', '#06b6d4', '#f59e0b'],
          borderWidth: 2,
          borderColor: '#ffffff',
          hoverOffset: 6
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '68%',
      plugins: {
        legend: {
          position: 'bottom',
          labels: {
            boxWidth: 10,
            padding: 12,
            font: { size: 10, family: 'sans-serif' },
            color: '#64748b'
          }
        },
        tooltip: {
          backgroundColor: '#0f172a',
          padding: 8,
          callbacks: {
            label(context) {
              return ` ${context.label}: ${formatCurrency(context.raw)}`;
            }
          }
        }
      }
    }
  });
}

function askAICopilot(promptText) {
  const input = document.getElementById('aiUserInput');
  if (input) {
    input.value = promptText;
  }
  handleAIChatSubmit(new Event('submit'));
}

async function handleAIChatSubmit(event) {
  event.preventDefault();

  const input = document.getElementById('aiUserInput');
  const query = input?.value.trim() || '';
  if (!query) return;

  appendChatMessage('user', query);
  input.value = '';

  try {
    const response = await apiFetch(`${API_BASE}/ai/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query })
    });

    if (!response.ok) {
      throw new Error('AI query failed');
    }

    const data = await response.json();
    appendChatMessage('assistant', data.text, data.meta);
  } catch (error) {
    appendChatMessage('assistant', 'Error communicating with FastAPI AI service.');
    console.error(error);
  }
}

function appendChatMessage(sender, text, meta = null) {
  const container = document.getElementById('aiChatThread');
  if (!container) return;

  container.querySelector('.chat-welcome')?.classList.remove('chat-welcome');

  const bubble = document.createElement('div');
  bubble.className = `chat-bubble ${sender}`;
  bubble.innerHTML = `
    <strong>${sender === 'user' ? 'You' : 'SmartBiz Copilot'}:</strong><br>
    ${text}
    ${meta ? `<div style="margin-top:6px; font-size:0.72rem; opacity:0.85; border-top:1px solid rgba(0,0,0,0.1); padding-top:4px;">${meta}</div>` : ''}
  `;

  container.appendChild(bubble);
  container.scrollTop = container.scrollHeight;
}

async function initializeApp() {
  loadAppSettings();
  checkAuthState();
  renderDashboardAlerts(false);

  let wasMobileViewport = window.innerWidth <= 900;
  setSidebarOpen(!wasMobileViewport);

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      if (document.getElementById('settingsModal')?.classList.contains('open')) {
        closeSettingsModal();
      }
      document.querySelectorAll('.modal-backdrop.open').forEach((modal) => {
        modal.classList.remove('open');
      });
      if (window.innerWidth <= 900) {
        setSidebarOpen(false);
      }
    }
  });

  window.addEventListener('resize', () => {
    const isMobileViewport = window.innerWidth <= 900;
    if (isMobileViewport !== wasMobileViewport) {
      wasMobileViewport = isMobileViewport;
      setSidebarOpen(!isMobileViewport);
    }
  });

  const backendOnline = await checkBackendHealth();
  if (!backendOnline) {
    renderDashboardAlerts(false);
    drawCharts();
    return;
  }

  if (getAuthToken()) {
    const response = await apiFetch(`${API_BASE}/auth/me`);
    if (response.ok) {
      await renderAllViews();
    }
  } else {
    clearPrivateData();
    openModal('loginModal');
  }

  const invoiceDate = document.getElementById('modalInvDate');
  if (invoiceDate && !invoiceDate.value) {
    invoiceDate.value = new Date().toISOString().split('T')[0];
  }

  const quantityInput = document.getElementById('modalInvQty');
  if (quantityInput) {
    quantityInput.addEventListener('input', recalculateInvoiceFormTotal);
  }

  const productSelect = document.getElementById('modalInvProduct');
  if (productSelect) {
    productSelect.addEventListener('change', recalculateInvoiceFormTotal);
  }

  document.querySelectorAll('.modal-backdrop').forEach((backdrop) => {
    backdrop.addEventListener('click', (event) => {
      if (event.target === backdrop) {
        if (backdrop.id === 'settingsModal') {
          closeSettingsModal();
        } else {
          backdrop.classList.remove('open');
        }
      }
    });
  });

  setInterval(() => {
    checkBackendHealth();
  }, 15000);
}

document.addEventListener('DOMContentLoaded', initializeApp);
