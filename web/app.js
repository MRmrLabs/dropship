const state = {
  suppliers: [],
  products: [],
  opportunities: [],
  drafts: [],
  orders: [],
  meli: null,
};

const api = async (path, options = {}) => {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Error API");
  return payload;
};

const money = (value) =>
  Number(value).toLocaleString("es-MX", { style: "currency", currency: "MXN" });

const pct = (value) => `${Math.round(Number(value) * 1000) / 10}%`;

const signalLabel = {
  green: "Verde",
  yellow: "Revision",
  red: "Descartado",
};

const statusLabel = {
  draft: "Borrador",
  needs_review: "Requiere revision",
  approved: "Aprobado",
  published: "Publicado",
  paused: "Pausado",
  rejected: "Rechazado",
};

async function refresh() {
  const [suppliers, products, opportunities, drafts, orders, meli] = await Promise.all([
    api("/api/suppliers"),
    api("/api/products"),
    api("/api/opportunities"),
    api("/api/listing-drafts"),
    api("/api/purchase-orders"),
    api("/api/integrations/meli/status"),
  ]);
  Object.assign(state, { suppliers, products, opportunities, drafts, orders, meli });
  render();
}

function render() {
  renderMetrics();
  renderOpportunities();
  renderDrafts();
  renderOrders();
  renderSuppliers();
  renderIntegrations();
}

function renderMetrics() {
  const greens = state.opportunities.filter((item) => item.signal === "green").length;
  const drafts = state.drafts.filter((item) => item.status === "draft").length;
  const approved = state.drafts.filter((item) => item.status === "approved").length;
  document.querySelector("#metrics").innerHTML = [
    ["Proveedores", state.suppliers.length],
    ["Oportunidades verdes", greens],
    ["Borradores", drafts],
    ["Aprobados", approved],
  ]
    .map(([label, value]) => `<article class="metric"><strong>${value}</strong><p>${label}</p></article>`)
    .join("");
}

function renderOpportunities() {
  const target = document.querySelector("#opportunityList");
  if (!state.opportunities.length) {
    target.innerHTML = `<article class="card"><h3>Sin analisis todavia</h3><p>Presiona Analizar oportunidades para evaluar los productos demo.</p></article>`;
    return;
  }
  target.innerHTML = state.opportunities
    .map(
      (item) => `
      <article class="card">
        <img src="${item.image_url}" alt="${item.title}">
        <h3>${item.title}</h3>
        <div class="meta">
          <span class="pill ${item.signal}">${signalLabel[item.signal]}</span>
          <span class="pill">Score ${item.score}</span>
          <span class="pill">${item.supplier_name}</span>
        </div>
        <p class="money">${money(item.suggested_price)}</p>
        <p>Margen neto ${pct(item.net_margin_rate)} · utilidad ${money(item.net_profit)}</p>
        <p class="muted">Costo ${money(item.cost)} + envio proveedor ${money(item.supplier_shipping)} · stock ${item.stock}</p>
        ${renderRisks(item.risks)}
        <div class="actions">
          <button class="primary" onclick="createDraft(${item.product_id})" ${item.signal === "red" ? "disabled" : ""}>Crear borrador</button>
          <button onclick="createOrder(${item.product_id})">Orden simulada</button>
        </div>
      </article>
    `
    )
    .join("");
}

function renderRisks(risks) {
  if (!risks.length) return `<p class="green pill">Sin riesgos bloqueantes</p>`;
  return `<ul class="risk-list">${risks.map((risk) => `<li>${risk}</li>`).join("")}</ul>`;
}

function renderDrafts() {
  const target = document.querySelector("#draftList");
  if (!state.drafts.length) {
    target.innerHTML = `<article class="row"><div><h3>No hay borradores</h3><p>Genera uno desde una oportunidad verde o amarilla.</p></div></article>`;
    return;
  }
  target.innerHTML = state.drafts
    .map(
      (item) => `
      <article class="row">
        <div>
          <h3>${item.title}</h3>
          <div class="meta">
            <span class="pill">${statusLabel[item.status]}</span>
            <span class="pill">${money(item.price)}</span>
            <span class="pill">Stock publicado ${item.stock}</span>
          </div>
          <p>${item.description.replace(/\n/g, "<br>")}</p>
        </div>
        <div class="actions">
          <button class="primary" onclick="setDraftStatus(${item.id}, 'approved')">Aprobar</button>
          <button onclick="setDraftStatus(${item.id}, 'rejected')">Rechazar</button>
          <button onclick="createOrder(${item.product_id}, ${item.id})">Orden</button>
        </div>
      </article>
    `
    )
    .join("");
}

function renderOrders() {
  const target = document.querySelector("#orderList");
  if (!state.orders.length) {
    target.innerHTML = `<article class="row"><div><h3>No hay ordenes</h3><p>Simula una venta desde una oportunidad o borrador.</p></div></article>`;
    return;
  }
  target.innerHTML = state.orders
    .map(
      (item) => `
      <article class="row">
        <div>
          <h3>${item.product_title}</h3>
          <div class="meta">
            <span class="pill yellow">${item.status}</span>
            <span class="pill">SKU ${item.supplier_sku}</span>
            <span class="pill">Margen ${pct(item.expected_margin_rate)}</span>
          </div>
          <p>Proveedor: <a href="${item.supplier_url}" target="_blank" rel="noreferrer">${item.supplier_url}</a></p>
          <p>Costo: ${money(item.supplier_cost)} · envio proveedor: ${money(item.supplier_shipping)}</p>
          <ul class="checklist">${item.checklist.map((entry) => `<li>${entry}</li>`).join("")}</ul>
        </div>
      </article>
    `
    )
    .join("");
}

function renderSuppliers() {
  const target = document.querySelector("#supplierList");
  target.innerHTML = state.suppliers
    .map(
      (item) => `
      <article class="row">
        <div>
          <h3>${item.name}</h3>
          <div class="meta">
            <span class="pill">Confiabilidad ${item.reliability}</span>
            <span class="pill ${item.invoices ? "green" : "yellow"}">${item.invoices ? "Factura" : "Factura no confirmada"}</span>
            <span class="pill ${item.authorized_assets ? "green" : "yellow"}">${item.authorized_assets ? "Recursos autorizados" : "Recursos pendientes"}</span>
          </div>
          <p>${item.terms}</p>
          <p class="muted">${item.contact} · ${item.shipping_type}</p>
        </div>
      </article>
    `
    )
    .join("");
}

function renderIntegrations() {
  const target = document.querySelector("#integrationList");
  const meli = state.meli || {};
  target.innerHTML = `
    <article class="row">
      <div>
        <h3>Mercado Libre Mexico</h3>
        <div class="meta">
          <span class="pill ${meli.configured ? "green" : "yellow"}">${meli.configured ? "Credenciales configuradas" : "Falta .env"}</span>
          <span class="pill ${meli.connected ? "green" : "yellow"}">${meli.connected ? "Cuenta conectada" : "Sin OAuth"}</span>
          ${meli.user_id ? `<span class="pill">Usuario ${meli.user_id}</span>` : ""}
        </div>
        <p>Redirect URI: ${meli.redirect_uri || "No configurado"}</p>
      </div>
      <div class="actions">
        <button class="primary" onclick="connectMeli()" ${!meli.configured ? "disabled" : ""}>Conectar</button>
        <button onclick="checkMeliMe()" ${!meli.connected ? "disabled" : ""}>Verificar cuenta</button>
      </div>
    </article>
  `;
}

async function createDraft(productId) {
  await api("/api/listing-drafts", {
    method: "POST",
    body: JSON.stringify({ product_id: productId }),
  });
  await refresh();
}

async function setDraftStatus(id, status) {
  await api(`/api/listing-drafts/${id}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
  await refresh();
}

async function createOrder(productId, listingDraftId = null) {
  await api("/api/purchase-orders", {
    method: "POST",
    body: JSON.stringify({
      product_id: productId,
      listing_draft_id: listingDraftId,
      sale_reference: `VENTA-SIM-${Date.now()}`,
    }),
  });
  await refresh();
}

async function connectMeli() {
  const payload = await api("/api/integrations/meli/auth-url");
  window.location.href = payload.url;
}

async function checkMeliMe() {
  const payload = await api("/api/integrations/meli/me");
  alert(`Mercado Libre conectado: ${payload.nickname || payload.id}`);
}

document.querySelector("#analyzeBtn").addEventListener("click", async () => {
  await api("/api/analyze", { method: "POST" });
  await refresh();
});

document.querySelectorAll(".tab").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    document.querySelector(`#${button.dataset.tab}`).classList.add("active");
  });
});

refresh();
