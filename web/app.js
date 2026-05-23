const state = {
  suppliers: [],
  products: [],
  opportunities: [],
  drafts: [],
  orders: [],
  storeOrders: [],
  meli: null,
  openai: null,
  stripe: null,
  auth: null,
  aiRuns: [],
  rejected: [],
  currentPlanProductId: null,
};

const api = async (path, options = {}) => {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (response.status === 401) {
    showLogin();
    throw new Error(payload.error || "Login requerido");
  }
  if (!response.ok) throw new Error(payload.error || "Error API");
  return payload;
};

const secondsToMinutes = (value) => `${Math.ceil(Number(value || 0) / 60)} min`;
const money = (value) => Number(value || 0).toLocaleString("es-MX", { style: "currency", currency: "MXN" });
const pct = (value) => `${Math.round(Number(value || 0) * 1000) / 10}%`;

const signalLabel = { green: "Recomendada", yellow: "Riesgosa", red: "Saturada" };
const statusLabel = {
  draft: "Borrador",
  needs_review: "Requiere revision",
  approved: "Aprobado",
  published: "Publicado",
  paused: "Pausado",
  rejected: "Rechazado",
};

const defaultDiscoveryQuery =
  "productos ganadores Mercado Libre Mexico accesorios tech margen alto baja saturacion proveedor factura";

let busy = false;

async function refresh() {
  const [auth, suppliers, products, opportunities, drafts, orders, storeOrders, meli, openai, stripe, aiRuns, rejected] = await Promise.all([
    api("/api/auth/status"),
    api("/api/suppliers"),
    api("/api/products"),
    api("/api/opportunity-list"),
    api("/api/listing-drafts"),
    api("/api/purchase-orders"),
    api("/api/storefront/orders"),
    api("/api/integrations/meli/status"),
    api("/api/integrations/openai/status"),
    api("/api/integrations/stripe/status"),
    api("/api/ai/research-runs"),
    api("/api/rejected-candidates"),
  ]);
  Object.assign(state, { auth, suppliers, products, opportunities, drafts, orders, storeOrders, meli, openai, stripe, aiRuns, rejected });
  hideLogin();
  render();
}

function render() {
  renderMetrics();
  renderOpportunities();
  renderDrafts();
  renderStoreOrders();
  renderOrders();
  renderSuppliers();
  renderAiResearch();
  renderRejected();
  renderIntegrations();
}

function renderMetrics() {
  const recommended = state.opportunities.filter((item) => item.intelligence?.verdict_signal === "green").length;
  const avgPotential = state.opportunities.length
    ? Math.round(
        state.opportunities.reduce((sum, item) => sum + Number(item.intelligence?.potential_score || item.score || 0), 0) /
          state.opportunities.length
      )
    : 0;
  const avgMargin = state.opportunities.length
    ? state.opportunities.reduce((sum, item) => sum + Number(item.net_margin_rate || 0), 0) / state.opportunities.length
    : 0;
  const webSales = state.storeOrders.length;
  document.querySelector("#metrics").innerHTML = [
    ["Recomendadas", recommended],
    ["Potencial medio", `${avgPotential}/100`],
    ["Margen real medio", pct(avgMargin)],
    ["Ventas web", webSales],
  ]
    .map(([label, value]) => `<article class="metric"><strong>${value}</strong><p>${label}</p></article>`)
    .join("");
}

function renderOpportunities() {
  const target = document.querySelector("#opportunityList");
  if (!state.opportunities.length) {
    target.innerHTML = `<article class="empty-state"><h3>Sin oportunidades reales</h3><p>Ejecuta una busqueda para llenar tu radar con productos concretos, margen y competencia.</p></article>`;
    return;
  }
  target.innerHTML = state.opportunities.map(renderOpportunityCard).join("");
}

function renderOpportunityCard(item) {
  const intel = item.intelligence || {};
  const financials = intel.financials || {};
  const decision = intel.verdict_signal || item.signal;
  return `
    <article class="opportunity-card ${decision}">
      <div class="product-media">
        ${item.image_url ? `<img src="${item.image_url}" alt="${item.title}">` : `<div class="media-placeholder">${initials(item.title)}</div>`}
      </div>
      <div class="card-body">
        <div class="card-topline">
          <span class="decision ${decision}">${intel.verdict || signalLabel[item.signal]}</span>
          <span class="score">${intel.potential_score || item.score}/100</span>
        </div>
        <h3>${item.title}</h3>
        <div class="metric-row">
          <div><span>Ganancia</span><strong>${money(item.net_profit)}</strong></div>
          <div><span>Margen real</span><strong>${pct(item.net_margin_rate)}</strong></div>
          <div><span>Precio sugerido</span><strong>${money(item.suggested_price)}</strong></div>
        </div>
        <div class="supplier-focus">
          <strong>Comprar proveedor: ${money(item.cost)}</strong>
          <span>${item.supplier_name} · llega en ${item.lead_time_days} dia(s)</span>
        </div>
        <div class="signal-grid">
          ${renderScoreDetails(item)}
          <span>Saturacion <b>${intel.saturation || "Media"}</b></span>
          <span>Competencia ML <b>${intel.competition || "Media"}</b></span>
          <span>Devolucion <b>${intel.return_risk || "Medio"}</b></span>
          <span>TikTok visual <b>${intel.visual_potential || "Medio"}</b></span>
        </div>
        <div class="cost-breakdown">
          <span>Proveedor ${money(item.cost)}</span>
          <span>Envio ${money(item.supplier_shipping)}</span>
          <span>Comision ${money(financials.marketplace_fee || financials.fees)}</span>
          <span>IVA ${money(financials.iva)}</span>
          <span>Ads ${money(financials.ads)}</span>
          <span>Stripe ${money(financials.stripe_fee)}</span>
          <span>Comision PrimeLoot ${money(financials.platform_commission)}</span>
        </div>
        ${renderAlerts(item)}
        ${item.duplicate_count > 1 ? `<p class="dupes">${item.duplicate_count - 1} variante(s) agrupada(s). Mostrando el mejor match.</p>` : ""}
        <p class="supplier-line">${item.supplier_name} · Stock ${item.stock} · Auto: ${intel.auto_action || "revision"}</p>
        ${renderOpportunityActions(item)}
      </div>
    </article>
  `;
}

function renderScoreDetails(item) {
  const details = item.evidence?.score_details || item.score_details;
  if (!details?.subscores) return "";
  const subs = details.subscores;
  return `
    <span>Demanda <b>${subs.demanda || 0}/100</b></span>
    <span>Proveedor <b>${subs.proveedor || 0}/100</b></span>
  `;
}

function renderOpportunityActions(item) {
  if (item.signal === "red") {
    return `<div class="actions"><button onclick="rejectOpportunity(${item.product_id})">Sacar descartado</button></div>`;
  }
  return `
    <div class="actions">
      <button class="primary" onclick="openInvestmentPlan(${item.product_id})">Ver plan</button>
      <button class="primary" onclick="createDraft(${item.product_id})">Crear publicacion</button>
      <button onclick="compareMarket(${item.product_id})">Comparar ML</button>
      <button onclick="createOrder(${item.product_id})">Crear orden</button>
      <button onclick="openSupplierRoute(${item.product_id})">Comprar proveedor</button>
      <button onclick="rejectOpportunity(${item.product_id})">Rechazar</button>
    </div>
  `;
}

function renderAlerts(item) {
  const alerts = item.intelligence?.alerts?.length ? item.intelligence.alerts : item.risks || [];
  if (!alerts.length) return `<p class="positive-note">Sin alertas bloqueantes</p>`;
  return `<div class="alert-strip">${alerts.slice(0, 3).map((risk) => `<span>${risk}</span>`).join("")}</div>`;
}

function renderDrafts() {
  const target = document.querySelector("#draftList");
  if (!state.drafts.length) {
    target.innerHTML = `<article class="empty-state"><h3>No hay publicaciones</h3><p>Crea una publicacion desde una oportunidad recomendada o riesgosa revisable.</p></article>`;
    return;
  }
  target.innerHTML = state.drafts.map(renderDraftPreview).join("");
}

function renderDraftPreview(item) {
  return `
    <article class="listing-preview">
      <div class="listing-main">
        <div class="listing-image">
          ${item.image_url ? `<img src="${item.image_url}" alt="${item.title}">` : `<div class="media-placeholder">${initials(item.title)}</div>`}
        </div>
        <div>
          <h3>${item.title}</h3>
          <div class="meta">
            <span class="pill">${statusLabel[item.status]}</span>
            <span class="pill">${money(item.price)}</span>
            <span class="pill">Stock ${item.stock}</span>
            ${item.marketplace_item_id ? `<span class="pill green">ML ${item.marketplace_item_id}</span>` : ""}
          </div>
          ${item.marketplace_error ? `<p class="ml-error">Mercado Libre: ${item.marketplace_error}</p>` : ""}
          <p class="listing-copy">${String(item.description || "").replace(/\n/g, "<br>")}</p>
          <p class="preview-tag">Preview Mercado Libre · ${money(item.price)}</p>
        </div>
      </div>
      <div class="actions">
        ${
          item.marketplace_permalink
            ? `<button class="primary" onclick="openUrl('${item.marketplace_permalink}')">Ver en Mercado Libre</button>`
            : `<button class="primary" onclick="setDraftStatus(${item.id}, 'approved')">Aprobar</button>`
        }
        <button onclick="setDraftStatus(${item.id}, 'rejected')">Rechazar</button>
        <button onclick="createOrder(${item.product_id}, ${item.id})">Orden</button>
      </div>
    </article>
  `;
}

function renderOrders() {
  const target = document.querySelector("#orderList");
  if (!state.orders.length) {
    target.innerHTML = `<article class="empty-state"><h3>No hay ordenes</h3><p>Genera ordenes solo cuando el margen y la competencia sigan sanos.</p></article>`;
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
        <div class="actions">
          <button class="primary" onclick="openUrl('${item.supplier_url}')">Comprar proveedor</button>
        </div>
      </article>
    `
    )
    .join("");
}

function renderStoreOrders() {
  const target = document.querySelector("#webSalesList");
  if (!target) return;
  if (!state.storeOrders.length) {
    target.innerHTML = `<article class="empty-state"><h3>Aun no hay ventas web</h3><p>Comparte /tienda para empezar a capturar pedidos directos.</p></article>`;
    return;
  }
  target.innerHTML = state.storeOrders
    .map(
      (order) => `
      <article class="row">
        <div>
          <h3>Pedido web #${order.id} · ${money(order.subtotal)}</h3>
          <div class="meta">
            <span class="pill yellow">${order.status}</span>
            ${order.stripe_payment_status ? `<span class="pill green">Stripe ${order.stripe_payment_status}</span>` : ""}
            <span class="pill">${order.customer_name}</span>
            <span class="pill">${order.customer_phone}</span>
          </div>
          <p>${order.delivery_city || "Ciudad pendiente"} · ${order.customer_email || "Sin email"}</p>
          <ul class="checklist">${order.items.map((item) => `<li>${item.quantity} x ${item.title} · ${money(item.line_total)}</li>`).join("")}</ul>
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
  const openai = state.openai || {};
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
        <button onclick="openMeliListings()" ${!meli.user_id ? "disabled" : ""}>Ver mis publicaciones</button>
      </div>
    </article>
    <article class="row">
      <div>
        <h3>Stripe Connect</h3>
        <div class="meta">
          <span class="pill ${state.stripe?.configured ? "green" : "yellow"}">${state.stripe?.configured ? "Listo para cobrar" : "Falta STRIPE_SECRET_KEY"}</span>
          <span class="pill">${Math.round(Number(state.stripe?.commission_rate || 0) * 100)}% comision</span>
          <span class="pill">${state.stripe?.mode || "checkout"}</span>
        </div>
        <p>Base para cobrar ventas reales y comision configurable con Stripe Connect.</p>
      </div>
    </article>
    <article class="row">
      <div>
        <h3>OpenAI Web Search</h3>
        <div class="meta">
          <span class="pill ${openai.configured ? "green" : "yellow"}">${openai.configured ? "API key configurada" : "Falta OPENAI_API_KEY"}</span>
          <span class="pill">${openai.model || "gpt-4.1-mini"}</span>
          <span class="pill">${openai.tool || "web_search"}</span>
        </div>
        <p>Busqueda real con limites de costo y fuentes verificables.</p>
      </div>
    </article>
  `;
}

function renderAiResearch() {
  const target = document.querySelector("#aiResearchList");
  const status = document.querySelector("#aiStatus");
  const openai = state.openai || {};
  status.textContent = openai.configured
    ? `OpenAI listo con ${openai.model || "gpt-4.1-mini"}. Objetivo: ${openai.required_candidates || 4} productos perfectos, hasta ${openai.max_attempts || 5} intento(s), timeout ${secondsToMinutes(openai.request_timeout_seconds || 240)} por intento.`
    : "Falta configurar OPENAI_API_KEY en Render o en tu .env local.";
  if (!state.aiRuns.length) {
    target.innerHTML = `<article class="empty-state"><h3>Sin busquedas reales todavia</h3><p>Ejecuta una busqueda para encontrar proveedores y productos con fuentes.</p></article>`;
    return;
  }
  target.innerHTML = state.aiRuns.map((run) => renderAiRun(run)).join("");
}

function renderAiRun(run) {
  const result = run.result || {};
  const candidates = result.candidates || [];
  const stages = result.stages || result.attempts || [];
  return `
    <article class="row">
      <div>
        <h3>${result.summary || run.query}</h3>
        <div class="meta">
          <span class="pill">${run.status}</span>
          <span class="pill">${candidates.length} candidatos</span>
          <span class="pill">${run.created_at}</span>
          ${result.engine ? `<span class="pill green">${result.engine}</span>` : ""}
        </div>
        ${stages.length ? `<div class="stage-strip">${stages.map(renderStage).join("")}</div>` : ""}
        ${candidates.map((candidate, index) => renderCandidate(run.id, candidate, index)).join("")}
      </div>
    </article>
  `;
}

function renderStage(stage) {
  return `<span>${stage.stage || `Intento ${stage.attempt || ""}`}: ${stage.accepted ?? stage.pool ?? stage.items ?? stage.returned ?? 0}</span>`;
}

function renderCandidate(runId, candidate, index) {
  const urls = Array.isArray(candidate.source_urls) ? candidate.source_urls : [];
  const risks = Array.isArray(candidate.risk_flags) ? candidate.risk_flags : [];
  return `
    <div class="card">
      <h3>${candidate.product_title || "Producto candidato"}</h3>
      <div class="meta">
        <span class="pill">${candidate.supplier_name || "Proveedor"}</span>
        <span class="pill">${candidate.category || "categoria"}</span>
        <span class="pill">Confianza ${Math.round(Number(candidate.confidence || 0) * 100)}%</span>
        ${candidate.score_details ? `<span class="pill green">Deep ${candidate.score_details.total}/100</span>` : ""}
      </div>
      <p class="money">${money(candidate.estimated_market_price_mxn || 0)}</p>
      <p>Costo estimado ${money(candidate.estimated_cost_mxn || 0)} · envio ${money(candidate.estimated_shipping_mxn || 0)}</p>
      <p class="muted">${candidate.notes || "Validar condiciones con proveedor."}</p>
      ${risks.length ? `<ul class="risk-list">${risks.map((risk) => `<li>${risk}</li>`).join("")}</ul>` : ""}
      ${candidate.evidence?.survived_because ? `<ul class="risk-list good">${candidate.evidence.survived_because.map((reason) => `<li>${reason}</li>`).join("")}</ul>` : ""}
      <p>${urls.map((url) => `<a href="${url}" target="_blank" rel="noreferrer">Fuente</a>`).join(" · ")}</p>
      <div class="actions"><button onclick="importCandidate(${runId}, ${index})">Reimportar</button></div>
    </div>
  `;
}

function renderRejected() {
  const target = document.querySelector("#rejectedList");
  if (!target) return;
  if (!state.rejected.length) {
    target.innerHTML = `<article class="empty-state"><h3>Sin descartados todavia</h3><p>PrimeLoot guardara aqui productos agotados, saturados o con mala evidencia.</p></article>`;
    return;
  }
  target.innerHTML = state.rejected
    .map(
      (item) => `
      <article class="row">
        <div>
          <h3>${item.title || "Candidato rechazado"}</h3>
          <div class="meta">
            <span class="pill red">${item.reason}</span>
            <span class="pill">${item.supplier_name || "Proveedor"}</span>
            <span class="pill">${item.created_at}</span>
          </div>
          <p>${item.product_url ? `<a href="${item.product_url}" target="_blank" rel="noreferrer">${item.product_url}</a>` : "Sin URL"}</p>
        </div>
        <div class="actions">
          <button onclick="restoreRejected(${item.id})">Restaurar</button>
        </div>
      </article>`
    )
    .join("");
}

async function createDraft(productId) {
  const payload = await api("/api/listing-drafts", {
    method: "POST",
    body: JSON.stringify({ product_id: productId }),
  });
  await refresh();
  if (payload.permalink) {
    window.open(payload.permalink, "_blank", "noopener");
  } else if (payload.error) {
    alert(`Borrador local creado, pero Mercado Libre pidio revision: ${payload.error}`);
  }
}

async function setDraftStatus(id, status) {
  await api(`/api/listing-drafts/${id}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
  await refresh();
}

async function createOrder(productId, listingDraftId = null) {
  const payload = await api("/api/purchase-orders", {
    method: "POST",
    body: JSON.stringify({
      product_id: productId,
      listing_draft_id: listingDraftId,
      sale_reference: `VENTA-SIM-${Date.now()}`,
    }),
  });
  await refresh();
  alert(`Orden ${payload.id} creada con comparacion de Mercado Libre actualizada.`);
}

async function openInvestmentPlan(productId) {
  state.currentPlanProductId = productId;
  const payload = await api(`/api/investment-plans/${productId}`);
  const plan = payload.plan || {};
  document.querySelector("#planTitle").textContent = `Plan: ${plan.title || "producto"}`;
  document.querySelector("#planContent").innerHTML = renderInvestmentPlan(plan);
  document.querySelector("#planModal").classList.remove("hidden");
}

function renderInvestmentPlan(plan) {
  const rows = [
    ["Proveedor", plan.supplier_name],
    ["URL oficial", plan.supplier_url ? `<a href="${plan.supplier_url}" target="_blank" rel="noreferrer">${plan.supplier_url}</a>` : "Pendiente"],
    ["Cantidad sugerida", `${plan.quantity} unidad(es)`],
    ["Inversion", money(plan.total_investment)],
    ["Precio venta ML", money(plan.suggested_sale_price)],
    ["Ganancia esperada", money(plan.expected_profit)],
    ["Margen", pct(plan.net_margin_rate)],
    ["ROI", pct(plan.roi)],
    ["Llegada", `${plan.lead_time_days} dia(s)`],
  ];
  return `
    <div class="plan-score">
      <span class="decision green">${plan.verdict || "Revisar"} · ${plan.score || 0}/100</span>
      <span>Saturacion ${plan.saturation || "Media"} · Devolucion ${plan.return_risk || "Medio"} · Visual ${plan.visual_potential || "Medio"}</span>
    </div>
    <table class="plan-table">${rows.map(([key, value]) => `<tr><th>${key}</th><td>${value}</td></tr>`).join("")}</table>
    <h3>Pasos exactos</h3>
    <ol class="checklist">${(plan.steps || []).map((step) => `<li>${step}</li>`).join("")}</ol>
    <h3>Riesgos y validaciones</h3>
    <ul class="checklist">${(plan.risks || ["Sin alertas bloqueantes"]).map((risk) => `<li>${risk}</li>`).join("")}</ul>
  `;
}

async function openSupplierRoute(productId) {
  const route = await api(`/api/supplier-order-route/${productId}`);
  openProgress("Compra con proveedor");
  logProgress(`Ruta: ${route.type}. Confirmacion final requerida.`, "done");
  (route.steps || []).forEach((step) => logProgress(step));
  if (route.url) window.open(route.url, "_blank", "noopener");
}

async function connectMeli() {
  const payload = await api("/api/integrations/meli/auth-url");
  window.location.href = payload.url;
}

async function checkMeliMe() {
  const payload = await api("/api/integrations/meli/me");
  alert(`Mercado Libre conectado: ${payload.nickname || payload.id}`);
}

function openMeliListings() {
  const userId = state.meli?.user_id;
  if (!userId) return;
  window.open(`https://listado.mercadolibre.com.mx/_CustId_${userId}`, "_blank", "noopener");
}

function openUrl(url) {
  window.open(url, "_blank", "noopener");
}

async function compareMarket(productId) {
  const payload = await api("/api/products/compare-market", {
    method: "POST",
    body: JSON.stringify({ product_id: productId }),
  });
  await refresh();
  const market = payload.market || {};
  alert(`Mercado comparado: referencia ${money(market.reference_price)}, minimo ${money(market.min_price)}, resultados ${market.count || 0}.`);
}

async function runAiSearch(query) {
  const status = document.querySelector("#aiStatus");
  status.textContent = "Buscando en internet con IA...";
  try {
    openProgress("Busqueda IA en internet");
    logProgress("Preparando busqueda con limite de costo activo.");
    logProgress(`Consulta: ${query || defaultDiscoveryQuery}`);
    await api("/api/ai/deep-search", {
      method: "POST",
      body: JSON.stringify({ query: query || defaultDiscoveryQuery }),
    });
    logProgress("PrimeLoot Local Search guardado; productos top importados automaticamente a Oportunidades.", "done");
    await refresh();
  } catch (error) {
    status.textContent = error.message;
    logProgress(error.message, "error");
  }
}

async function restoreRejected(id) {
  await api(`/api/rejected-candidates/${id}/restore`, { method: "POST" });
  await refresh();
}

async function importCandidate(runId, candidateIndex, options = {}) {
  const payload = await api("/api/ai/import-candidate", {
    method: "POST",
    body: JSON.stringify({ run_id: runId, candidate_index: candidateIndex }),
  });
  await api("/api/analyze", { method: "POST" });
  await refresh();
  if (!options.silent) {
    alert(`Candidato importado como producto ${payload.product_id}. Ya puedes verlo en Oportunidades.`);
  }
  return payload;
}

async function rejectOpportunity(productId) {
  await api("/api/opportunities/reject", {
    method: "POST",
    body: JSON.stringify({ product_id: productId }),
  });
  await refresh();
}

async function discoverAndAnalyze() {
  if (busy) return;
  busy = true;
  document.querySelector("#analyzeBtn").disabled = true;
  openProgress("Buscando oportunidades reales");
  try {
    await refresh();
    if (!state.openai?.configured) throw new Error("Falta configurar OPENAI_API_KEY en Render.");
    if ((state.openai.searches_today || 0) >= (state.openai.daily_limit || 3)) {
      throw new Error("Limite diario de busquedas IA alcanzado.");
    }
    const query = document.querySelector("#aiQuery")?.value || defaultDiscoveryQuery;
    logProgress("Buscando tendencias Mercado Libre.", "done");
    logProgress(`Generando pool de hasta ${state.openai.candidate_pool_size || 24} candidatos con IA web.`);
    logProgress("Verificando proveedor, stock, factura, ML y memoria de descartados.");
    const started = await api("/api/local-search/start", {
      method: "POST",
      body: JSON.stringify({ query }),
    });
    const research = await waitLocalSearch(started.id);
    const candidates = research.result?.candidates || [];
    const imported = research.result?.imported || [];
    logProgress(`PrimeLoot eligio ${candidates.length} candidato(s) top.`, "done");
    logProgress(`Importacion automatica: ${imported.length} resultado(s).`, "done");
    for (let index = 0; index < candidates.length; index += 1) {
      const candidate = candidates[index];
      const result = imported[index];
      const title = candidate.product_title || `candidato ${index + 1}`;
      logProgress(
        result?.product_id ? `${title}: agregado al radar (${result.status}).` : `${title}: ${result?.status || "no importado"}.`,
        result?.product_id ? "done" : "error"
      );
    }
    await refresh();
    logProgress("Radar actualizado. Revisa recomendaciones y alertas.", "done");
  } catch (error) {
    logProgress(error.message, "error");
  } finally {
    busy = false;
    document.querySelector("#analyzeBtn").disabled = false;
    await refresh();
  }
}

async function waitLocalSearch(jobId) {
  let lastProgress = 0;
  for (;;) {
    const job = await api(`/api/local-search/status/${jobId}`);
    const progress = job.progress || [];
    progress.slice(lastProgress).forEach((entry) => logProgress(`${entry.stage}: ${entry.message}`, entry.ok === false ? "error" : ""));
    lastProgress = progress.length;
    if (job.status === "completed") {
      return api(`/api/local-search/results/${jobId}`);
    }
    if (job.status === "failed") throw new Error(job.error || "Local Search fallo");
    if (job.status === "stopped") throw new Error("Local Search detenido");
    await new Promise((resolve) => setTimeout(resolve, 2500));
  }
}

function openProgress(title) {
  document.querySelector("#progressTitle").textContent = title;
  document.querySelector("#progressLog").innerHTML = "";
  document.querySelector("#progressModal").classList.remove("hidden");
}

function logProgress(message, type = "") {
  const item = document.createElement("li");
  item.textContent = message;
  if (type) item.classList.add(type);
  document.querySelector("#progressLog").appendChild(item);
  item.scrollIntoView({ block: "nearest" });
}

function closeProgress() {
  document.querySelector("#progressModal").classList.add("hidden");
}

function closePlan() {
  document.querySelector("#planModal").classList.add("hidden");
}

function downloadPlanPdf() {
  if (!state.currentPlanProductId) return;
  window.open(`/api/investment-plans/${state.currentPlanProductId}.pdf`, "_blank", "noopener");
}

function showLogin() {
  document.querySelector("#loginGate")?.classList.remove("hidden");
}

function hideLogin() {
  if (!state.auth?.enabled || state.auth?.authenticated) {
    document.querySelector("#loginGate")?.classList.add("hidden");
  }
}

async function loginAdmin(event) {
  event.preventDefault();
  const password = document.querySelector("#adminPassword").value;
  try {
    await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ password }),
    });
    document.querySelector("#loginError").textContent = "";
    await refresh();
  } catch (error) {
    document.querySelector("#loginError").textContent = error.message;
  }
}

function initials(value) {
  return String(value || "ML")
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

document.querySelector("#analyzeBtn").addEventListener("click", async () => {
  await discoverAndAnalyze();
});
document.querySelector("#progressClose").addEventListener("click", closeProgress);
document.querySelector("#planClose").addEventListener("click", closePlan);
document.querySelector("#planPdfBtn").addEventListener("click", downloadPlanPdf);
document.querySelector("#loginForm").addEventListener("submit", loginAdmin);
document.querySelector("#aiSearchForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  await runAiSearch(document.querySelector("#aiQuery").value);
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
