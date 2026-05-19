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

### Conectar Mercado Libre

1. Regenera el Client Secret si fue compartido fuera del panel de Mercado Libre.
2. Copia `.env.example` a `.env`.
3. Completa:

```text
MELI_CLIENT_ID=tu_app_id
MELI_CLIENT_SECRET=tu_client_secret_regenerado
MELI_REDIRECT_URI=http://127.0.0.1:8787/auth/meli/callback
```

4. En Mercado Libre Developers, configura exactamente la misma Redirect URI.
5. Abre el panel, entra a Integraciones y presiona Conectar.

Los tokens se guardan localmente en `data/meli_tokens.json`, que esta ignorado por Git.

## Pruebas

```powershell
.\test.ps1
```

## Deploy en Render

El repo incluye `render.yaml` para crear un Web Service Python con disco persistente en `data/`.

Variables que debes configurar en Render:

```text
MELI_CLIENT_ID=785180156949955
MELI_CLIENT_SECRET=tu_secret_regenerado
MELI_REDIRECT_URI=https://tu-servicio.onrender.com/auth/meli/callback
```

En Mercado Libre Developers, registra exactamente el mismo `MELI_REDIRECT_URI`.
