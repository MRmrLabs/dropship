const state = { products: [], cart: loadCart() };

const money = (value) => Number(value || 0).toLocaleString("es-MX", { style: "currency", currency: "MXN" });

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Error API");
  return payload;
}

function loadCart() {
  try {
    return JSON.parse(localStorage.getItem("primeloot_cart") || "[]");
  } catch {
    return [];
  }
}

function saveCart() {
  localStorage.setItem("primeloot_cart", JSON.stringify(state.cart));
}

async function loadStore() {
  const payload = await api("/api/storefront/products");
  document.querySelector("#brandName").textContent = payload.brand || "PrimeLoot Store";
  state.products = payload.products || [];
  renderProducts();
  renderCart();
}

function renderProducts() {
  const target = document.querySelector("#productGrid");
  if (!state.products.length) {
    target.innerHTML = `<article class="product-card"><div class="product-body"><h3>Catalogo en preparacion</h3><p>Publica oportunidades desde el radar interno para llenar tu tienda.</p></div></article>`;
    return;
  }
  target.innerHTML = state.products
    .map(
      (item) => `
      <article class="product-card">
        ${item.image_url ? `<img src="${item.image_url}" alt="${item.title}">` : `<div class="media-placeholder">${initials(item.title)}</div>`}
        <div class="product-body">
          <span class="badge">${item.verdict} · ${item.score}/100</span>
          <h3>${item.title}</h3>
          <p>${item.description}</p>
          <p class="price">${money(item.price)}</p>
          <button onclick="addToCart(${item.product_id})">Agregar al carrito</button>
        </div>
      </article>
    `
    )
    .join("");
}

function renderCart() {
  const target = document.querySelector("#cartItems");
  if (!state.cart.length) {
    target.innerHTML = `<p>Tu carrito esta vacio.</p>`;
  } else {
    target.innerHTML = state.cart
      .map((item) => {
        const product = state.products.find((entry) => entry.product_id === item.product_id);
        return `
          <div class="cart-line">
            <div><strong>${product?.title || "Producto"}</strong><p>${item.quantity} x ${money(product?.price || 0)}</p></div>
            <button onclick="removeFromCart(${item.product_id})">Quitar</button>
          </div>
        `;
      })
      .join("");
  }
  document.querySelector("#cartTotal").textContent = money(cartTotal());
}

function addToCart(productId) {
  const existing = state.cart.find((item) => item.product_id === productId);
  if (existing) existing.quantity += 1;
  else state.cart.push({ product_id: productId, quantity: 1 });
  saveCart();
  renderCart();
}

function removeFromCart(productId) {
  state.cart = state.cart.filter((item) => item.product_id !== productId);
  saveCart();
  renderCart();
}

function cartTotal() {
  return state.cart.reduce((sum, item) => {
    const product = state.products.find((entry) => entry.product_id === item.product_id);
    return sum + Number(product?.price || 0) * item.quantity;
  }, 0);
}

document.querySelector("#checkoutForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const payload = Object.fromEntries(form.entries());
  payload.items = state.cart;
  const result = await api("/api/storefront/orders", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  state.cart = [];
  saveCart();
  renderCart();
  if (result.checkout_url) {
    document.querySelector("#checkoutResult").innerHTML = `Pedido #${result.id} creado. Redirigiendo a pago seguro...`;
    window.location.href = result.checkout_url;
    return;
  }
  if (result.stripe_error) {
    console.warn("Stripe checkout fallback:", result.stripe_error);
  }
  document.querySelector("#checkoutResult").innerHTML = result.whatsapp_url
    ? `Pedido #${result.id} creado. <a href="${result.whatsapp_url}" target="_blank" rel="noreferrer">Confirmar por WhatsApp</a>`
    : `Pedido #${result.id} creado. Te contactaremos para confirmar stock y pago.`;
});

function initials(value) {
  return String(value || "NS")
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

loadStore();
