# Bot Dropshipping Tech MX

MVP local para evaluar accesorios tecnologicos en Mexico, detectar oportunidades con margen neto minimo de 15%, crear borradores de publicaciones para Mercado Libre y generar ordenes de compra manuales.

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

1. Registrar proveedores mexicanos.
2. Cargar productos de proveedor.
3. Analizar oportunidades con reglas de margen, stock, marca, imagenes y competencia.
4. Generar borradores de Mercado Libre para oportunidades verdes.
5. Aprobar borradores antes de publicar.
6. Simular ventas y generar ordenes de compra para armar pedidos manualmente.

## Integraciones

Mercado Libre queda preparado como adaptador OAuth/API, pero el MVP no publica automaticamente sin credenciales ni aprobacion.
Amazon queda como placeholder de fase 2 para SP-API.

La busqueda real de proveedores usa OpenAI Responses API con la herramienta `web_search`. Requiere `OPENAI_API_KEY`; la app guarda cada investigacion y muestra fuentes para validacion manual.

Por seguridad de costos, la busqueda IA tiene limites configurables:

```text
AI_DAILY_SEARCH_LIMIT=3
AI_MIN_SECONDS_BETWEEN_SEARCHES=300
AI_MAX_CANDIDATES=4
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
