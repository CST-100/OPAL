"""Onshape REST API client with HMAC-SHA256 authentication."""

import base64
import hashlib
import hmac
import logging
import random
import re
import string
from datetime import UTC, datetime
from urllib.parse import urlencode, urlparse

import httpx

from opal.integrations.onshape.models import (
    BOMParseWarning,
    OnshapeBOM,
    OnshapeBOMItem,
    OnshapeDocument,
    OnshapeElement,
    OnshapeMetadataProperty,
    OnshapePart,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://cad.onshape.com"

# Regex for Onshape document URLs:
# https://cad.onshape.com/documents/{did}/(w|v|m)/{wvm_id}/e/{eid}
_ONSHAPE_URL_RE = re.compile(
    r"https?://[^/]+/documents/([a-zA-Z0-9]+)/(w|v|m)/([a-zA-Z0-9]+)/e/([a-zA-Z0-9]+)"
)


def _build_hierarchy(flat_rows: list[dict]) -> list[dict]:
    """Reconstruct nested children arrays from flat rows with indentLevel.

    The Onshape v6 BOM API returns a flat list of rows where hierarchy is
    indicated by an 'indentLevel' field (0 = top-level, 1 = child, etc.)
    rather than nested 'children' arrays. This function rebuilds the tree.

    If rows already have 'children' arrays, they are returned as-is.
    """
    if not flat_rows:
        return flat_rows

    # If the first row already has children, assume the data is already nested
    if flat_rows[0].get("children"):
        return flat_rows

    # Check if any row has indentLevel — if not, return as-is
    if not any("indentLevel" in row for row in flat_rows):
        return flat_rows

    root_items: list[dict] = []
    stack: list[tuple[int, dict]] = []  # (indentLevel, row_dict) ancestors

    for row in flat_rows:
        level = row.get("indentLevel", 0)
        row.setdefault("children", [])

        # Pop stack back to parent level
        while stack and stack[-1][0] >= level:
            stack.pop()

        if stack:
            # Append as child of the current parent
            stack[-1][1]["children"].append(row)
        else:
            # Top-level item
            root_items.append(row)

        stack.append((level, row))

    return root_items


def resolve_header_value(
    raw: dict, header_map: dict[str, str], prop_name: str,
) -> str:
    """Extract a property value from headerIdToValue using the header map.

    Handles both plain string values and dict-wrapped {"value": "X"} entries.
    Returns "" if the property is not found or has no value.
    """
    h2v = raw.get("headerIdToValue", {})
    for hdr_id, mapped_name in header_map.items():
        if mapped_name == prop_name:
            val = h2v.get(hdr_id)
            if val is None:
                continue
            if isinstance(val, dict):
                val = val.get("value", "")
            if isinstance(val, str):
                return val
            return str(val)
    return ""


def parse_bom_item(
    raw: dict,
    header_map: dict[str, str],
    warnings: list[BOMParseWarning],
    item_index: int,
    depth: int = 0,
) -> OnshapeBOMItem:
    """Parse a raw BOM item dict into an OnshapeBOMItem.

    Recursively parses children. Appends BOMParseWarning entries for
    missing part_id or part_name on non-standard-content items.
    """
    children = [
        parse_bom_item(child, header_map, warnings, item_index=item_index, depth=depth + 1)
        for child in raw.get("children", [])
    ]
    item_source = raw.get("itemSource", {})
    source_element_id = item_source.get("elementId", "")
    is_std = bool(raw.get("isStandardContent", False)) or bool(
        item_source.get("isStandardContent", False)
    )
    # part_id: itemSource.partId → itemSource.elementId (sub-assemblies) → raw.partId
    part_id = (
        item_source.get("partId", "")
        or item_source.get("elementId", "")
        or raw.get("partId", "")
    )
    # name: header-based → direct field → capitalized variant
    part_name = (
        resolve_header_value(raw, header_map, "name")
        or raw.get("name", "")
        or raw.get("Name", "")
    )
    # part_number: header-based (try both "partnumber" and "part number") → direct field variants
    part_number = (
        resolve_header_value(raw, header_map, "partnumber")
        or resolve_header_value(raw, header_map, "part number")
        or raw.get("partNumber")
        or raw.get("Part Number")
    ) or None
    # quantity: header-based → direct field, then parse string/float
    raw_qty = (
        resolve_header_value(raw, header_map, "quantity")
        or raw.get("quantity", 1)
    )
    try:
        quantity = int(raw_qty)
    except (ValueError, TypeError):
        try:
            quantity = int(float(raw_qty))
        except (ValueError, TypeError):
            logger.warning(
                "Unparseable quantity %r for part %r, defaulting to 1",
                raw_qty, part_name,
            )
            quantity = 1
    # description: header-based → direct field
    description = (
        resolve_header_value(raw, header_map, "description")
        or raw.get("description", "")
    ) or None

    # Diagnostic warnings
    if not part_id:
        warnings.append(BOMParseWarning(
            item_index=item_index, field="part_id",
            message="Empty part_id — item will be skipped during sync",
        ))
    if not part_name and not is_std:
        warnings.append(BOMParseWarning(
            item_index=item_index, field="part_name",
            message=f"Empty part_name for non-standard-content item (part_id={part_id!r})",
            raw_value=raw.get("headerIdToValue", {}),
        ))
        logger.warning(
            "BOM item[%d] has empty name. raw keys=%r, headerIdToValue=%r, "
            "direct name=%r, Name=%r",
            item_index, sorted(raw.keys()),
            raw.get("headerIdToValue"),
            raw.get("name"), raw.get("Name"),
        )

    source = "header" if raw.get("headerIdToValue") else "direct"
    logger.debug(
        "BOM item[%d] depth=%d: part_id=%r name=%r pn=%r qty=%d source=%s",
        item_index, depth, part_id, part_name, part_number, quantity, source,
    )

    return OnshapeBOMItem(
        item_source=item_source,
        source_element_id=source_element_id,
        part_id=part_id,
        part_name=part_name,
        part_number=part_number,
        description=description,
        quantity=quantity,
        is_standard_content=is_std,
        children=children,
    )


def parse_onshape_url(url: str) -> tuple[str, str, str, str] | None:
    """Parse an Onshape URL into (document_id, wvm_type, wvm_id, element_id).

    Supports workspace (/w/), version (/v/), and microversion (/m/) URLs.
    Returns None if the URL doesn't match the expected Onshape format.
    """
    match = _ONSHAPE_URL_RE.search(url)
    if not match:
        return None
    return (match.group(1), match.group(2), match.group(3), match.group(4))


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

        # Build the signature string — Onshape requires the entire string
        # to be lowercased before HMAC computation
        raw_str = (
            "\n".join([method, nonce, date, content_type, path, query]) + "\n"
        ).lower()

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

    def get_elements(
        self,
        document_id: str,
        workspace_id: str,
    ) -> list[OnshapeElement]:
        """Get all elements (tabs) in a document workspace."""
        path = f"/api/v6/documents/d/{document_id}/w/{workspace_id}/elements"
        data = self._request("GET", path)
        return [
            OnshapeElement(
                id=item["id"],
                name=item.get("name", ""),
                element_type=item.get("elementType", item.get("type", "")),
            )
            for item in data
        ]

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
        params = {
            "indented": str(indented).lower(),
            "multiLevel": str(indented).lower(),
            "generateIfAbsent": "true",
        }
        data = self._request("GET", path, params=params)

        # Log response structure for debugging
        bom_table = data.get("bomTable", {})
        logger.debug(
            "BOM response keys: top=%r, bomTable=%r",
            sorted(data.keys()),
            sorted(bom_table.keys()) if isinstance(bom_table, dict) else type(bom_table).__name__,
        )

        # Build header-id → property-name map from headers.
        # Try bomTable.headers first, then top-level headers (v6 API format).
        headers = bom_table.get("headers", []) if isinstance(bom_table, dict) else []
        if not headers:
            headers = data.get("headers", [])
        header_map: dict[str, str] = {}
        for hdr in headers:
            prop = hdr.get("propertyName") or hdr.get("name", "")
            header_map[hdr["id"]] = prop.lower()

        if header_map:
            logger.info("BOM header map (%d entries): %r", len(header_map),
                        {k: v for k, v in header_map.items()
                         if v in ("name", "quantity", "partnumber", "part number",
                                  "description", "item")})
        else:
            logger.warning(
                "No BOM headers found — will fall back to direct field access"
            )

        # Resilient item extraction — try multiple response structures
        if isinstance(bom_table, dict):
            raw_items = bom_table.get("items", []) or bom_table.get("rows", [])
        else:
            raw_items = []
        # Fallback: items/rows at top level (v6 API format)
        if not raw_items:
            raw_items = data.get("items", []) or data.get("rows", [])

        # Reconstruct hierarchy from flat indentLevel rows (v6 API format)
        raw_items = _build_hierarchy(raw_items)

        if raw_items:
            first = raw_items[0]
            logger.info(
                "First BOM item keys: %r, itemSource: %r",
                sorted(first.keys()) if isinstance(first, dict) else type(first).__name__,
                first.get("itemSource") if isinstance(first, dict) else None,
            )

        logger.info("Assembly BOM returned %d raw items", len(raw_items))

        bom_warnings: list[BOMParseWarning] = []
        items = [
            parse_bom_item(row, header_map, bom_warnings, item_index=i)
            for i, row in enumerate(raw_items)
        ]

        for w in bom_warnings:
            logger.warning("BOM parse warning [item %d, %s]: %s", w.item_index, w.field, w.message)

        return OnshapeBOM(
            document_id=document_id,
            element_id=element_id,
            items=items,
            warnings=bom_warnings,
            header_map=header_map,
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
