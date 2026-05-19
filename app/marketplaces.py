from __future__ import annotations

from dataclasses import dataclass

from app.meli_auth import get_access_token


@dataclass
class MarketplaceResult:
    ok: bool
    message: str
    external_id: str | None = None


class MercadoLibreSync:
    """Adapter boundary for Mercado Libre OAuth/API.

    The MVP intentionally keeps real publishing disabled until credentials are
    configured and a listing has been explicitly approved by the seller.
    """

    def __init__(self, access_token: str | None = None) -> None:
        self.access_token = access_token

    def publish_listing(self, listing: dict) -> MarketplaceResult:
        if listing.get("status") != "approved":
            return MarketplaceResult(False, "La publicacion debe estar aprobada antes de publicar")
        access_token = self.access_token
        if not access_token:
            try:
                access_token = get_access_token()
            except ValueError:
                access_token = None
        if not access_token:
            return MarketplaceResult(False, "Falta configurar OAuth de Mercado Libre")
        return MarketplaceResult(False, "Publicacion real pendiente de activar en fase de credenciales")


class AmazonSpApiSync:
    def publish_listing(self, listing: dict) -> MarketplaceResult:
        return MarketplaceResult(False, "Amazon SP-API queda reservado para fase 2")
