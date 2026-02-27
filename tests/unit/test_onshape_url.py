"""Tests for Onshape URL parsing."""

from opal.integrations.onshape.client import parse_onshape_url


class TestParseOnshapeUrl:
    """Test parse_onshape_url() with various URL formats."""

    def test_standard_workspace_url(self) -> None:
        result = parse_onshape_url(
            "https://cad.onshape.com/documents/abc123def456/w/aaa111bbb222/e/eee999fff000"
        )
        assert result == ("abc123def456", "w", "aaa111bbb222", "eee999fff000")

    def test_version_url(self) -> None:
        result = parse_onshape_url(
            "https://cad.onshape.com/documents/abc123/v/ver456/e/elem789"
        )
        assert result == ("abc123", "v", "ver456", "elem789")

    def test_microversion_url(self) -> None:
        result = parse_onshape_url(
            "https://cad.onshape.com/documents/abc123/m/micro456/e/elem789"
        )
        assert result == ("abc123", "m", "micro456", "elem789")

    def test_enterprise_domain(self) -> None:
        result = parse_onshape_url(
            "https://mycompany.onshape.com/documents/abc123/w/ws456/e/elem789"
        )
        assert result == ("abc123", "w", "ws456", "elem789")

    def test_url_with_query_params(self) -> None:
        result = parse_onshape_url(
            "https://cad.onshape.com/documents/abc123/w/ws456/e/elem789?renderMode=0"
        )
        assert result == ("abc123", "w", "ws456", "elem789")

    def test_url_with_fragment(self) -> None:
        result = parse_onshape_url(
            "https://cad.onshape.com/documents/abc123/w/ws456/e/elem789#something"
        )
        assert result == ("abc123", "w", "ws456", "elem789")

    def test_http_url(self) -> None:
        result = parse_onshape_url(
            "http://cad.onshape.com/documents/abc123/w/ws456/e/elem789"
        )
        assert result == ("abc123", "w", "ws456", "elem789")

    def test_invalid_url_no_documents(self) -> None:
        assert parse_onshape_url("https://cad.onshape.com/some/other/path") is None

    def test_invalid_url_empty(self) -> None:
        assert parse_onshape_url("") is None

    def test_invalid_url_not_url(self) -> None:
        assert parse_onshape_url("not-a-url") is None

    def test_invalid_url_missing_element(self) -> None:
        assert parse_onshape_url(
            "https://cad.onshape.com/documents/abc123/w/ws456"
        ) is None

    def test_invalid_url_wrong_wvm_letter(self) -> None:
        """Only w, v, m are valid workspace/version/microversion types."""
        assert parse_onshape_url(
            "https://cad.onshape.com/documents/abc123/x/ws456/e/elem789"
        ) is None

    def test_url_with_trailing_slash(self) -> None:
        result = parse_onshape_url(
            "https://cad.onshape.com/documents/abc123/w/ws456/e/elem789/"
        )
        assert result is not None
        assert result[0] == "abc123"
