# Bot Dropshipping Tech MX

MVP local para evaluar accesorios tecnologicos reales en Mexico, detectar oportunidades con margen neto minimo de 15%, crear publicaciones para Mercado Libre, generar planes de inversion y preparar ventas directas con Stripe.

## Ejecutar

```powershell
.\run.ps1
```

Abre el panel en:

```text
http://127.0.0.1:8787
```

El servidor usa solo Python estandar y SQLite. La base se crea en `data/dropshipping.db`.

## Flujo MVP

1. Buscar proveedores y productos reales con IA web o capturarlos manualmente.
2. Importar automaticamente candidatos con fuentes verificables.
3. Analizar oportunidades con reglas de margen, stock, marca, imagenes y competencia.
4. Generar borradores de Mercado Libre para oportunidades verdes o amarillas revisables.
5. Crear la publicacion real en Mercado Libre al presionar Crear borrador, si OAuth y datos del producto son validos.
6. Ver el plan de inversion: costo proveedor, precio ML, ROI, pasos y PDF.
7. Cobrar pedidos directos con Stripe si las variables estan configuradas.
8. Rechazar oportunidades para sacarlas del tablero.

## Integraciones

Mercado Libre usa OAuth/API para crear publicaciones reales desde el boton Crear borrador.
Amazon queda como placeholder de fase 2 para SP-API.

La busqueda real de proveedores usa OpenAI Responses API con la herramienta `web_search` y salida estructurada JSON Schema. Requiere `OPENAI_API_KEY`; la app guarda cada investigacion y muestra fuentes para validacion manual.

Por seguridad de costos, la busqueda IA tiene limites configurables:

```text
AI_DAILY_SEARCH_LIMIT=3
AI_MIN_SECONDS_BETWEEN_SEARCHES=300
AI_MAX_CANDIDATES=4
AI_REQUIRED_CANDIDATES=4
AI_RESEARCH_MAX_ATTEMPTS=5
AI_CANDIDATE_POOL_SIZE=24
DEEP_SEARCH_MAX_MINUTES=20
ML_TRENDS_ENABLED=true
ML_MARKET_VERIFY_ENABLED=true
REJECT_MEMORY_DAYS=30
ML_COMMISSION_RATE=0.145
MX_IVA_RATE=0.16
ESTIMATED_ADS_RATE=0.06
RETURN_BUFFER_RATE=0.03
STORE_BRAND=NEOBOT Store
STORE_WHATSAPP=5215512345678
ADMIN_PASSWORD=cambia_esto
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PLATFORM_COMMISSION_RATE=0.10
```

### Conectar Mercado Libre

1. Regenera el Client Secret si fue compartido fuera del panel de Mercado Libre.
2. Copia `.env.example` a `.env`.
3. Completa:

```text
MELI_CLIENT_ID=tu_app_id
MELI_CLIENT_SECRET=tu_client_secret_regenerado
MELI_REDIRECT_URI=http://127.0.0.1:8787/auth/meli/callback
OPENAI_API_KEY=tu_openai_api_key
OPENAI_WEB_MODEL=gpt-4.1-mini
OPENAI_REQUEST_TIMEOUT_SECONDS=240
OPENAI_MAX_OUTPUT_TOKENS=2600
AI_DAILY_SEARCH_LIMIT=3
AI_MIN_SECONDS_BETWEEN_SEARCHES=300
AI_MAX_CANDIDATES=4
AI_REQUIRED_CANDIDATES=4
AI_RESEARCH_MAX_ATTEMPTS=5
AI_CANDIDATE_POOL_SIZE=24
DEEP_SEARCH_MAX_MINUTES=20
ML_TRENDS_ENABLED=true
ML_MARKET_VERIFY_ENABLED=true
REJECT_MEMORY_DAYS=30
ADMIN_PASSWORD=cambia_esto
ADMIN_SESSION_SECRET=cambia_esto_tambien
```

4. En Mercado Libre Developers, configura exactamente la misma Redirect URI.
5. Abre el panel, entra a Integraciones y presiona Conectar.

Los tokens se guardan localmente en `data/meli_tokens.json`, que esta ignorado por Git.

### Publicar en Mercado Libre

El boton **Crear borrador** crea el borrador local y despues intenta crear la publicacion real en Mercado Libre. Si Mercado Libre acepta el item, el panel guarda el `item_id` y muestra **Ver en Mercado Libre**. Si Mercado Libre rechaza por categoria, atributos, imagenes o permisos, el borrador queda en revision y muestra el error exacto para corregirlo.

Variable opcional:

```text
MELI_LISTING_TYPE_ID=gold_special
```

Antes de crear borradores u ordenes, el sistema compara el producto contra busqueda publica de Mercado Libre Mexico y recalcula precio de referencia, competencia y margen. El margen real estimado incluye costo proveedor, envio, comision ML, IVA, ads estimados y colchon de devoluciones.

## Tienda directa

La tienda publica vive en:

```text
/tienda
```

Muestra productos activos del radar, permite agregar al carrito y crea pedidos web en estado `pending_payment`. Si configuras `STRIPE_SECRET_KEY`, el checkout crea una sesion real de Stripe y redirige al pago. Si no hay Stripe, usa WhatsApp como fallback cuando `STORE_WHATSAPP` esta configurado.

## Seguridad interna

Configura `ADMIN_PASSWORD` para proteger el panel interno. La tienda publica `/tienda`, el catalogo publico y el checkout quedan accesibles; costos de proveedor, ordenes, planes de inversion, publicaciones ML e integraciones quedan detras del login.

## Stripe Connect

Variables principales:

```text
STRIPE_SECRET_KEY=sk_live_o_sk_test
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_CONNECTED_ACCOUNT_ID=acct_... # opcional para Connect
STRIPE_PLATFORM_COMMISSION_RATE=0.10
PUBLIC_BASE_URL=https://tu-servicio.onrender.com
```

Si `STRIPE_CONNECTED_ACCOUNT_ID` existe, NEOBOT prepara el cobro con transferencia a la cuenta conectada y comision de plataforma. Si no existe, cobra con Checkout normal en tu cuenta.

## Pruebas

```powershell
.\test.ps1
```

## Deploy en Render Free

El repo incluye `render.yaml` para crear un Web Service Python en el plan gratis de Render.

Importante: Render Free no tiene Persistent Disk. La base SQLite y los tokens OAuth guardados en `data/` pueden perderse despues de redeploys, reinicios o limpiezas del servicio. Para produccion real, usa Render Starter con Persistent Disk o migra la app a Render Postgres.

Variables que debes configurar en Render:

```text
MELI_CLIENT_ID=785180156949955
MELI_CLIENT_SECRET=tu_secret_regenerado
MELI_REDIRECT_URI=https://tu-servicio.onrender.com/auth/meli/callback
OPENAI_API_KEY=tu_openai_api_key
OPENAI_WEB_MODEL=gpt-4.1-mini
OPENAI_REQUEST_TIMEOUT_SECONDS=240
OPENAI_MAX_OUTPUT_TOKENS=2600
OPENAI_DEEP_ANALYSIS_MODEL=gpt-4.1-mini
OPENAI_DEEP_MAX_OUTPUT_TOKENS=2600
AI_DAILY_SEARCH_LIMIT=3
AI_MIN_SECONDS_BETWEEN_SEARCHES=300
AI_MAX_CANDIDATES=4
AI_REQUIRED_CANDIDATES=4
AI_RESEARCH_MAX_ATTEMPTS=5
AI_CANDIDATE_POOL_SIZE=24
DEEP_SEARCH_MAX_MINUTES=20
ML_TRENDS_ENABLED=true
ML_MARKET_VERIFY_ENABLED=true
REJECT_MEMORY_DAYS=30
ADMIN_PASSWORD=cambia_esto
ADMIN_SESSION_SECRET=cambia_esto_tambien
PUBLIC_BASE_URL=https://tu-servicio.onrender.com
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_CONNECTED_ACCOUNT_ID=
STRIPE_PLATFORM_COMMISSION_RATE=0.10
```

En Mercado Libre Developers, registra exactamente el mismo `MELI_REDIRECT_URI`.

Si el servicio se reinicia y Mercado Libre aparece desconectado, vuelve a entrar a Integraciones y completa OAuth otra vez.
