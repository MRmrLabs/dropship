# Bot Dropshipping Tech MX

MVP local para evaluar accesorios tecnologicos reales en Mexico, detectar oportunidades con margen neto minimo de 15%, crear borradores de publicaciones para Mercado Libre y generar ordenes de compra manuales.

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
6. Rechazar oportunidades para sacarlas del tablero.

## Integraciones

Mercado Libre usa OAuth/API para crear publicaciones reales desde el boton Crear borrador.
Amazon queda como placeholder de fase 2 para SP-API.

La busqueda real de proveedores usa OpenAI Responses API con la herramienta `web_search` y salida estructurada JSON Schema. Requiere `OPENAI_API_KEY`; la app guarda cada investigacion y muestra fuentes para validacion manual.

Por seguridad de costos, la busqueda IA tiene limites configurables:

```text
AI_DAILY_SEARCH_LIMIT=3
AI_MIN_SECONDS_BETWEEN_SEARCHES=300
AI_MAX_CANDIDATES=4
ML_COMMISSION_RATE=0.145
MX_IVA_RATE=0.16
ESTIMATED_ADS_RATE=0.06
RETURN_BUFFER_RATE=0.03
STORE_BRAND=NEOBOT Store
STORE_WHATSAPP=5215512345678
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
OPENAI_REQUEST_TIMEOUT_SECONDS=60
OPENAI_MAX_OUTPUT_TOKENS=1600
AI_DAILY_SEARCH_LIMIT=3
AI_MIN_SECONDS_BETWEEN_SEARCHES=300
AI_MAX_CANDIDATES=4
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

Muestra productos activos del radar, permite agregar al carrito y crea pedidos web en estado `pending_payment`. Si configuras `STORE_WHATSAPP` con tu numero en formato internacional, el checkout genera un link para confirmar el pedido por WhatsApp.

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
OPENAI_REQUEST_TIMEOUT_SECONDS=60
OPENAI_MAX_OUTPUT_TOKENS=1600
AI_DAILY_SEARCH_LIMIT=3
AI_MIN_SECONDS_BETWEEN_SEARCHES=300
AI_MAX_CANDIDATES=4
```

En Mercado Libre Developers, registra exactamente el mismo `MELI_REDIRECT_URI`.

Si el servicio se reinicia y Mercado Libre aparece desconectado, vuelve a entrar a Integraciones y completa OAuth otra vez.
