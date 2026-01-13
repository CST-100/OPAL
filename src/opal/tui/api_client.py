"""API client for TUI to communicate with OPAL backend."""

from typing import Any

import httpx


class OpalAPIClient:
    """HTTP client for OPAL API."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=30.0)
        self.user_id = 1  # Default user for TUI operations

    def _url(self, path: str) -> str:
        """Build full URL for API path."""
        return f"{self.base_url}/api{path}"

    def _headers(self) -> dict[str, str]:
        """Get request headers."""
        return {"X-User-ID": str(self.user_id)}

    # Parts
    def list_parts(
        self, page: int = 1, page_size: int = 50, search: str | None = None
    ) -> dict[str, Any]:
        """List parts with pagination."""
        params = {"page": page, "page_size": page_size}
        if search:
            params["search"] = search
        resp = self.client.get(self._url("/parts"), params=params)
        resp.raise_for_status()
        return resp.json()

    def get_part(self, part_id: int) -> dict[str, Any]:
        """Get a single part."""
        resp = self.client.get(self._url(f"/parts/{part_id}"))
        resp.raise_for_status()
        return resp.json()

    def create_part(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new part."""
        resp = self.client.post(
            self._url("/parts"), json=data, headers=self._headers()
        )
        resp.raise_for_status()
        return resp.json()

    def update_part(self, part_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """Update a part."""
        resp = self.client.patch(
            self._url(f"/parts/{part_id}"), json=data, headers=self._headers()
        )
        resp.raise_for_status()
        return resp.json()

    def delete_part(self, part_id: int) -> None:
        """Delete a part."""
        resp = self.client.delete(
            self._url(f"/parts/{part_id}"), headers=self._headers()
        )
        resp.raise_for_status()

    # Inventory
    def list_inventory(
        self, part_id: int | None = None, page: int = 1, page_size: int = 50
    ) -> dict[str, Any]:
        """List inventory records."""
        params = {"page": page, "page_size": page_size}
        if part_id:
            params["part_id"] = part_id
        resp = self.client.get(self._url("/inventory"), params=params)
        resp.raise_for_status()
        return resp.json()

    def add_inventory(self, data: dict[str, Any]) -> dict[str, Any]:
        """Add inventory."""
        resp = self.client.post(
            self._url("/inventory"), json=data, headers=self._headers()
        )
        resp.raise_for_status()
        return resp.json()

    # Procedures
    def list_procedures(self, page: int = 1, page_size: int = 50) -> dict[str, Any]:
        """List procedures."""
        params = {"page": page, "page_size": page_size}
        resp = self.client.get(self._url("/procedures"), params=params)
        resp.raise_for_status()
        return resp.json()

    def get_procedure(self, procedure_id: int) -> dict[str, Any]:
        """Get a procedure with steps."""
        resp = self.client.get(self._url(f"/procedures/{procedure_id}"))
        resp.raise_for_status()
        return resp.json()

    def create_procedure(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a procedure."""
        resp = self.client.post(
            self._url("/procedures"), json=data, headers=self._headers()
        )
        resp.raise_for_status()
        return resp.json()

    def publish_procedure(self, procedure_id: int) -> dict[str, Any]:
        """Publish a procedure version."""
        resp = self.client.post(
            self._url(f"/procedures/{procedure_id}/publish"), headers=self._headers()
        )
        resp.raise_for_status()
        return resp.json()

    # Executions
    def list_instances(
        self,
        procedure_id: int | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """List procedure instances."""
        params = {"page": page, "page_size": page_size}
        if procedure_id:
            params["procedure_id"] = procedure_id
        if status:
            params["status"] = status
        resp = self.client.get(self._url("/procedure-instances"), params=params)
        resp.raise_for_status()
        return resp.json()

    def get_instance(self, instance_id: int) -> dict[str, Any]:
        """Get an instance."""
        resp = self.client.get(self._url(f"/procedure-instances/{instance_id}"))
        resp.raise_for_status()
        return resp.json()

    def create_instance(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a procedure instance."""
        resp = self.client.post(
            self._url("/procedure-instances"), json=data, headers=self._headers()
        )
        resp.raise_for_status()
        return resp.json()

    def start_step(self, instance_id: int, step_number: int) -> dict[str, Any]:
        """Start a step."""
        resp = self.client.post(
            self._url(f"/procedure-instances/{instance_id}/steps/{step_number}/start"),
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    def complete_step(
        self, instance_id: int, step_number: int, data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Complete a step."""
        resp = self.client.post(
            self._url(f"/procedure-instances/{instance_id}/steps/{step_number}/complete"),
            json=data or {},
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    def get_version_content(self, instance_id: int) -> dict[str, Any]:
        """Get version content for an instance."""
        resp = self.client.get(
            self._url(f"/procedure-instances/{instance_id}/version-content")
        )
        resp.raise_for_status()
        return resp.json()

    # Issues
    def list_issues(
        self,
        issue_type: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """List issues."""
        params = {"page": page, "page_size": page_size}
        if issue_type:
            params["issue_type"] = issue_type
        if status:
            params["status"] = status
        resp = self.client.get(self._url("/issues"), params=params)
        resp.raise_for_status()
        return resp.json()

    def get_issue(self, issue_id: int) -> dict[str, Any]:
        """Get an issue."""
        resp = self.client.get(self._url(f"/issues/{issue_id}"))
        resp.raise_for_status()
        return resp.json()

    def create_issue(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create an issue."""
        resp = self.client.post(
            self._url("/issues"), json=data, headers=self._headers()
        )
        resp.raise_for_status()
        return resp.json()

    def update_issue(self, issue_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """Update an issue."""
        resp = self.client.patch(
            self._url(f"/issues/{issue_id}"), json=data, headers=self._headers()
        )
        resp.raise_for_status()
        return resp.json()

    # Risks
    def list_risks(
        self, status: str | None = None, page: int = 1, page_size: int = 50
    ) -> dict[str, Any]:
        """List risks."""
        params = {"page": page, "page_size": page_size}
        if status:
            params["status"] = status
        resp = self.client.get(self._url("/risks"), params=params)
        resp.raise_for_status()
        return resp.json()

    def get_risk(self, risk_id: int) -> dict[str, Any]:
        """Get a risk."""
        resp = self.client.get(self._url(f"/risks/{risk_id}"))
        resp.raise_for_status()
        return resp.json()

    def create_risk(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a risk."""
        resp = self.client.post(
            self._url("/risks"), json=data, headers=self._headers()
        )
        resp.raise_for_status()
        return resp.json()

    def get_risk_matrix(self) -> dict[str, Any]:
        """Get risk matrix data."""
        resp = self.client.get(self._url("/risks/matrix"))
        resp.raise_for_status()
        return resp.json()

    # Users
    def list_users(self) -> dict[str, Any]:
        """List users."""
        resp = self.client.get(self._url("/users"))
        resp.raise_for_status()
        return resp.json()

    def get_current_user(self) -> dict[str, Any] | None:
        """Get current user info."""
        try:
            resp = self.client.get(self._url(f"/users/{self.user_id}"))
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError:
            return None

    # Health
    def health_check(self) -> dict[str, Any]:
        """Check API health."""
        resp = self.client.get(self._url("/health"))
        resp.raise_for_status()
        return resp.json()

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()


# Global client instance
_client: OpalAPIClient | None = None


def get_client(base_url: str = "http://127.0.0.1:8000") -> OpalAPIClient:
    """Get or create the API client."""
    global _client
    if _client is None:
        _client = OpalAPIClient(base_url)
    return _client
