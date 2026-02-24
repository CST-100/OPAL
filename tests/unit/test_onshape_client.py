"""Tests for Onshape API client with mocked HTTP."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from opal.integrations.onshape.client import OnshapeApiError, OnshapeClient


@pytest.fixture
def client() -> OnshapeClient:
    """Create an Onshape client with test credentials."""
    return OnshapeClient(
        access_key="test-access-key",
        secret_key="test-secret-key",
        base_url="https://cad.onshape.com",
    )


class TestAuthHeaders:
    """Test HMAC-SHA256 auth header generation."""

    def test_builds_valid_headers(self, client: OnshapeClient) -> None:
        headers = client._build_auth_headers("GET", "/api/v6/documents/abc123")
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("On test-access-key:HmacSHA256:")
        assert "Date" in headers
        assert "On-Nonce" in headers
        assert headers["Content-Type"] == "application/json"

    def test_nonce_is_unique(self, client: OnshapeClient) -> None:
        h1 = client._build_auth_headers("GET", "/api/test")
        h2 = client._build_auth_headers("GET", "/api/test")
        assert h1["On-Nonce"] != h2["On-Nonce"]


class TestGetDocument:
    """Test get_document method."""

    def test_parses_document_response(self, client: OnshapeClient) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "doc123",
            "name": "Test Assembly",
            "owner": {"name": "Engineer"},
            "defaultWorkspace": {"id": "ws456"},
        }

        with patch.object(client._client, "request", return_value=mock_response):
            doc = client.get_document("doc123")

        assert doc.id == "doc123"
        assert doc.name == "Test Assembly"
        assert doc.owner == "Engineer"
        assert doc.default_workspace_id == "ws456"


class TestGetParts:
    """Test get_parts method."""

    def test_parses_parts_list(self, client: OnshapeClient) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "partId": "p1",
                "name": "Bracket",
                "partNumber": "BRK-001",
                "description": "Mounting bracket",
                "material": {"displayName": "Aluminum 6061"},
            },
            {
                "partId": "p2",
                "name": "Bolt",
                "partNumber": None,
            },
        ]

        with patch.object(client._client, "request", return_value=mock_response):
            parts = client.get_parts("doc1", "ws1", "elem1")

        assert len(parts) == 2
        assert parts[0].part_id == "p1"
        assert parts[0].name == "Bracket"
        assert parts[0].material == "Aluminum 6061"
        assert parts[1].part_number is None


class TestGetBOM:
    """Test get_bom method."""

    def test_parses_flat_bom(self, client: OnshapeClient) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "bomTable": {
                "items": [
                    {
                        "itemSource": {"partId": "p1"},
                        "name": "Assembly",
                        "quantity": "1",
                        "children": [
                            {
                                "itemSource": {"partId": "p2"},
                                "name": "Bracket",
                                "quantity": "2",
                                "children": [],
                            },
                        ],
                    },
                ],
            },
        }

        with patch.object(client._client, "request", return_value=mock_response):
            bom = client.get_bom("doc1", "ws1", "elem1")

        assert bom.document_id == "doc1"
        assert len(bom.items) == 1
        assert bom.items[0].part_name == "Assembly"
        assert len(bom.items[0].children) == 1
        assert bom.items[0].children[0].part_name == "Bracket"
        assert bom.items[0].children[0].quantity == 2


class TestRetryBehavior:
    """Test retry and error handling."""

    def test_raises_on_4xx_error(self, client: OnshapeClient) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not found"

        with patch.object(client._client, "request", return_value=mock_response):
            with pytest.raises(OnshapeApiError) as exc_info:
                client.get_document("nonexistent")
            assert exc_info.value.status_code == 404

    def test_retries_on_429(self, client: OnshapeClient) -> None:
        rate_limited = MagicMock()
        rate_limited.status_code = 429
        rate_limited.headers = {"Retry-After": "0"}

        success = MagicMock()
        success.status_code = 200
        success.json.return_value = {
            "id": "doc1",
            "name": "Doc",
            "owner": {},
            "defaultWorkspace": {},
        }

        with patch.object(client._client, "request", side_effect=[rate_limited, success]):
            doc = client.get_document("doc1")

        assert doc.id == "doc1"

    def test_retries_on_timeout(self, client: OnshapeClient) -> None:
        success = MagicMock()
        success.status_code = 200
        success.json.return_value = {
            "id": "doc1",
            "name": "Doc",
            "owner": {},
            "defaultWorkspace": {},
        }

        with patch.object(
            client._client,
            "request",
            side_effect=[httpx.TimeoutException("timeout"), success],
        ):
            doc = client.get_document("doc1")

        assert doc.id == "doc1"

    def test_exhausts_retries(self, client: OnshapeClient) -> None:
        with patch.object(
            client._client,
            "request",
            side_effect=httpx.TimeoutException("timeout"),
        ):
            with pytest.raises(OnshapeApiError) as exc_info:
                client._request("GET", "/api/test", _retries=2)
            assert "retries" in exc_info.value.detail
