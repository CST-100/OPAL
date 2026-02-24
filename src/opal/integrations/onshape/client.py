"""Onshape REST API client with HMAC-SHA256 authentication."""

import base64
import hashlib
import hmac
import logging
import random
import string
from datetime import UTC, datetime
from urllib.parse import urlencode, urlparse

import httpx

from opal.integrations.onshape.models import (
    OnshapeBOM,
    OnshapeBOMItem,
    OnshapeDocument,
    OnshapeMetadataProperty,
    OnshapePart,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://cad.onshape.com"


class OnshapeApiError(Exception):
    """Raised when an Onshape API call fails."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Onshape API error {status_code}: {detail}")


class OnshapeClient:
    """Synchronous Onshape REST API client.

    Uses HMAC-SHA256 request signing per Onshape's API key auth scheme.
    Designed to run in a thread pool via asyncio.to_thread() since
    SQLAlchemy sessions are synchronous.
    """

    def __init__(
        self,
        access_key: str,
        secret_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
    ) -> None:
        self.access_key = access_key
        self.secret_key = secret_key
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> "OnshapeClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # ── Auth ──────────────────────────────────────────────────────────

    def _build_auth_headers(
        self,
        method: str,
        path: str,
        query: str = "",
        content_type: str = "application/json",
    ) -> dict[str, str]:
        """Build HMAC-SHA256 signed headers for Onshape API auth."""
        date = datetime.now(UTC).strftime("%a, %d %b %Y %H:%M:%S GMT")
        nonce = "".join(random.choices(string.ascii_lowercase + string.digits, k=25))

        # Build the signature string
        raw_str = "\n".join([
            method.lower(),
            nonce,
            date,
            content_type,
            path,
            query,
        ]) + "\n"

        # HMAC-SHA256 signature
        signature = base64.b64encode(
            hmac.new(
                self.secret_key.encode("utf-8"),
                raw_str.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        ).decode("utf-8")

        return {
            "Content-Type": content_type,
            "Date": date,
            "On-Nonce": nonce,
            "Authorization": f"On {self.access_key}:HmacSHA256:{signature}",
            "Accept": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json_body: dict | None = None,
        _retries: int = 3,
    ) -> dict:
        """Make an authenticated request to the Onshape API.

        Automatically retries on 429 (rate limit) with exponential backoff,
        and on transient network errors (timeouts, connection resets).
        """
        import time

        query_string = urlencode(params) if params else ""
        url = f"{self.base_url}{path}"
        if query_string:
            url = f"{url}?{query_string}"

        last_error: Exception | None = None

        for attempt in range(_retries):
            parsed = urlparse(url)
            headers = self._build_auth_headers(
                method=method,
                path=parsed.path,
                query=parsed.query,
            )

            try:
                response = self._client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=json_body,
                )
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_error = e
                wait = 2 ** attempt
                logger.warning(
                    "Onshape request failed (attempt %d/%d): %s — retrying in %ds",
                    attempt + 1, _retries, e, wait,
                )
                time.sleep(wait)
                continue

            if response.status_code == 429:
                # Rate limited — use Retry-After header or exponential backoff
                retry_after = int(response.headers.get("Retry-After", 2 ** attempt))
                logger.warning(
                    "Onshape rate limited (429), retrying in %ds", retry_after,
                )
                time.sleep(retry_after)
                continue

            if response.status_code >= 500 and attempt < _retries - 1:
                wait = 2 ** attempt
                logger.warning(
                    "Onshape server error %d, retrying in %ds",
                    response.status_code, wait,
                )
                time.sleep(wait)
                continue

            if response.status_code >= 400:
                raise OnshapeApiError(
                    status_code=response.status_code,
                    detail=response.text[:500],
                )

            return response.json()

        # Exhausted retries
        if last_error:
            raise OnshapeApiError(
                status_code=0,
                detail=f"Request failed after {_retries} retries: {last_error}",
            ) from last_error
        raise OnshapeApiError(
            status_code=429,
            detail=f"Rate limited after {_retries} retries",
        )

    # ── API Methods ───────────────────────────────────────────────────

    def get_document(self, document_id: str) -> OnshapeDocument:
        """Get document metadata."""
        data = self._request("GET", f"/api/v6/documents/{document_id}")
        return OnshapeDocument(
            id=data["id"],
            name=data["name"],
            owner=data.get("owner", {}).get("name"),
            default_workspace_id=data.get("defaultWorkspace", {}).get("id"),
        )

    def get_parts(
        self,
        document_id: str,
        workspace_id: str,
        element_id: str,
    ) -> list[OnshapePart]:
        """Get all parts in a part studio element."""
        path = (
            f"/api/v6/parts/d/{document_id}/w/{workspace_id}/e/{element_id}"
        )
        data = self._request("GET", path)

        parts = []
        for item in data:
            parts.append(OnshapePart(
                part_id=item.get("partId", ""),
                name=item.get("name", ""),
                part_number=item.get("partNumber"),
                description=item.get("description"),
                revision=item.get("revision"),
                material=item.get("material", {}).get("displayName") if item.get("material") else None,
                state=item.get("state"),
                appearance=item.get("appearance"),
            ))
        return parts

    def get_bom(
        self,
        document_id: str,
        workspace_id: str,
        element_id: str,
        indented: bool = True,
    ) -> OnshapeBOM:
        """Get BOM for an assembly element.

        Args:
            document_id: Onshape document ID.
            workspace_id: Workspace ID.
            element_id: Assembly element ID.
            indented: If True, return indented (hierarchical) BOM.
        """
        path = (
            f"/api/v6/assemblies/d/{document_id}/w/{workspace_id}/e/{element_id}/bom"
        )
        params = {"indented": str(indented).lower()}
        data = self._request("GET", path, params=params)

        def _parse_bom_item(raw: dict) -> OnshapeBOMItem:
            children = [
                _parse_bom_item(child)
                for child in raw.get("children", [])
            ]
            item_source = raw.get("itemSource", {})
            return OnshapeBOMItem(
                item_source=item_source,
                part_id=item_source.get("partId", ""),
                part_name=raw.get("name", ""),
                part_number=raw.get("partNumber"),
                quantity=int(raw.get("quantity", 1)),
                children=children,
            )

        items = [_parse_bom_item(row) for row in data.get("bomTable", {}).get("items", [])]

        return OnshapeBOM(
            document_id=document_id,
            element_id=element_id,
            items=items,
        )

    def get_metadata(
        self,
        document_id: str,
        workspace_id: str,
        element_id: str,
        part_id: str,
    ) -> list[OnshapeMetadataProperty]:
        """Get metadata properties for a specific part."""
        path = (
            f"/api/v6/metadata/d/{document_id}/w/{workspace_id}"
            f"/e/{element_id}/p/{part_id}"
        )
        data = self._request("GET", path)

        properties = []
        for prop in data.get("properties", []):
            properties.append(OnshapeMetadataProperty(
                name=prop.get("name", ""),
                value=str(prop.get("value", "")) if prop.get("value") is not None else None,
                property_id=prop.get("propertyId"),
            ))
        return properties

    def set_metadata(
        self,
        document_id: str,
        workspace_id: str,
        element_id: str,
        part_id: str,
        properties: list[dict[str, str]],
    ) -> dict:
        """Set metadata properties on a specific part.

        Args:
            document_id: Onshape document ID.
            workspace_id: Workspace ID.
            element_id: Element ID.
            part_id: Part ID within the element.
            properties: List of {"propertyId": ..., "value": ...} dicts.
        """
        path = (
            f"/api/v6/metadata/d/{document_id}/w/{workspace_id}"
            f"/e/{element_id}/p/{part_id}"
        )
        body = {"properties": properties}
        return self._request("POST", path, json_body=body)

    def register_webhook(
        self,
        document_id: str,
        webhook_url: str,
        events: list[str] | None = None,
    ) -> str:
        """Register a webhook for document change events.

        Returns the webhook ID.
        """
        if events is None:
            events = ["onshape.model.lifecycle.changed"]

        body = {
            "url": webhook_url,
            "events": events,
            "filter": f'{{"documentId": "{document_id}"}}',
        }
        data = self._request("POST", "/api/v6/webhooks", json_body=body)
        return data["id"]

    def delete_webhook(self, webhook_id: str) -> None:
        """Delete a registered webhook."""
        self._request("DELETE", f"/api/v6/webhooks/{webhook_id}")
