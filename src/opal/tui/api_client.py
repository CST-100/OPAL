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

    # ── Parts ──────────────────────────────────────────────────────────

    def list_parts(
        self, page: int = 1, page_size: int = 50, search: str | None = None
    ) -> dict[str, Any]:
        """List parts with pagination."""
        params: dict[str, Any] = {"page": page, "page_size": page_size}
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

    def list_categories(self) -> list[str]:
        """List part categories."""
        resp = self.client.get(self._url("/parts/categories"))
        resp.raise_for_status()
        return resp.json()

    # ── BOM ────────────────────────────────────────────────────────────

    def get_bom(self, assembly_id: int) -> list[dict[str, Any]]:
        """Get BOM lines for an assembly."""
        resp = self.client.get(self._url(f"/bom/assemblies/{assembly_id}"))
        resp.raise_for_status()
        return resp.json()

    # ── Inventory ──────────────────────────────────────────────────────

    def list_inventory(
        self,
        part_id: int | None = None,
        location: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """List inventory records."""
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if part_id:
            params["part_id"] = part_id
        if location:
            params["location"] = location
        resp = self.client.get(self._url("/inventory"), params=params)
        resp.raise_for_status()
        return resp.json()

    def get_inventory(self, inventory_id: int) -> dict[str, Any]:
        """Get a single inventory record."""
        resp = self.client.get(self._url(f"/inventory/{inventory_id}"))
        resp.raise_for_status()
        return resp.json()

    def add_inventory(self, data: dict[str, Any]) -> dict[str, Any]:
        """Add inventory."""
        resp = self.client.post(
            self._url("/inventory"), json=data, headers=self._headers()
        )
        resp.raise_for_status()
        return resp.json()

    def adjust_inventory(self, inventory_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """Adjust inventory quantity."""
        resp = self.client.post(
            self._url(f"/inventory/{inventory_id}/adjust"),
            json=data,
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    def transfer_stock(self, data: dict[str, Any]) -> dict[str, Any]:
        """Transfer inventory between locations."""
        resp = self.client.post(
            self._url("/inventory/transfer"), json=data, headers=self._headers()
        )
        resp.raise_for_status()
        return resp.json()

    def calibrate_inventory(self, inventory_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """Record calibration for an inventory item."""
        resp = self.client.post(
            self._url(f"/inventory/{inventory_id}/calibrate"),
            json=data,
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    def get_opal_by_number(self, opal_number: str) -> dict[str, Any]:
        """Lookup inventory by OPAL number."""
        resp = self.client.get(self._url(f"/inventory/opal/{opal_number}"))
        resp.raise_for_status()
        return resp.json()

    def get_opal_history(self, opal_number: str) -> dict[str, Any]:
        """Get history for an OPAL number."""
        resp = self.client.get(self._url(f"/inventory/opal/{opal_number}/history"))
        resp.raise_for_status()
        return resp.json()

    def list_locations(self) -> list[dict[str, Any]]:
        """List inventory locations."""
        resp = self.client.get(self._url("/inventory/locations"))
        resp.raise_for_status()
        return resp.json()

    def get_inventory_test_status(self, inventory_id: int) -> dict[str, Any]:
        """Get test/calibration status for inventory item."""
        resp = self.client.get(self._url(f"/inventory/{inventory_id}/test-status"))
        resp.raise_for_status()
        return resp.json()

    # ── Procedures ─────────────────────────────────────────────────────

    def list_procedures(self, page: int = 1, page_size: int = 50) -> dict[str, Any]:
        """List procedures."""
        params: dict[str, Any] = {"page": page, "page_size": page_size}
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

    def update_procedure(self, procedure_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """Update a procedure."""
        resp = self.client.patch(
            self._url(f"/procedures/{procedure_id}"), json=data, headers=self._headers()
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

    # ── Procedure Steps ────────────────────────────────────────────────

    def create_step(self, procedure_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """Create a procedure step."""
        resp = self.client.post(
            self._url(f"/procedures/{procedure_id}/steps"),
            json=data,
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    def update_step(
        self, procedure_id: int, step_id: int, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Update a procedure step."""
        resp = self.client.patch(
            self._url(f"/procedures/{procedure_id}/steps/{step_id}"),
            json=data,
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    def delete_step(self, procedure_id: int, step_id: int) -> None:
        """Delete a procedure step."""
        resp = self.client.delete(
            self._url(f"/procedures/{procedure_id}/steps/{step_id}"),
            headers=self._headers(),
        )
        resp.raise_for_status()

    def reorder_steps(self, procedure_id: int, order: list[int]) -> dict[str, Any]:
        """Reorder procedure steps."""
        resp = self.client.post(
            self._url(f"/procedures/{procedure_id}/steps/reorder"),
            json={"order": order},
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    # ── Executions ─────────────────────────────────────────────────────

    def list_instances(
        self,
        procedure_id: int | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """List procedure instances."""
        params: dict[str, Any] = {"page": page, "page_size": page_size}
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

    def skip_step(self, instance_id: int, step_number: int) -> dict[str, Any]:
        """Skip a step."""
        resp = self.client.post(
            self._url(f"/procedure-instances/{instance_id}/steps/{step_number}/skip"),
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    def signoff_step(
        self, instance_id: int, step_number: int, data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Sign off on a step."""
        resp = self.client.post(
            self._url(f"/procedure-instances/{instance_id}/steps/{step_number}/signoff"),
            json=data or {},
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    def update_step_notes(
        self, instance_id: int, step_number: int, notes: str
    ) -> dict[str, Any]:
        """Update step notes."""
        resp = self.client.patch(
            self._url(f"/procedure-instances/{instance_id}/steps/{step_number}/notes"),
            json={"notes": notes},
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    def log_nc(
        self, instance_id: int, step_number: int, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Log non-conformance during step execution."""
        resp = self.client.post(
            self._url(f"/procedure-instances/{instance_id}/steps/{step_number}/nc"),
            json=data,
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

    # ── Kit & Consumption ──────────────────────────────────────────────

    def get_kit_availability(self, instance_id: int) -> dict[str, Any]:
        """Get kit availability for an execution."""
        resp = self.client.get(
            self._url(f"/procedure-instances/{instance_id}/kit-availability")
        )
        resp.raise_for_status()
        return resp.json()

    def consume_kit(self, instance_id: int, data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Consume kit items at instance level."""
        resp = self.client.post(
            self._url(f"/procedure-instances/{instance_id}/consume"),
            json=data or {},
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    def consume_step_kit(
        self, instance_id: int, step_number: int, data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Consume kit items for a specific step."""
        resp = self.client.post(
            self._url(f"/procedure-instances/{instance_id}/steps/{step_number}/consume"),
            json=data or {},
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    def get_consumptions(self, instance_id: int) -> list[dict[str, Any]]:
        """Get all consumptions for an instance."""
        resp = self.client.get(
            self._url(f"/procedure-instances/{instance_id}/consumptions")
        )
        resp.raise_for_status()
        return resp.json()

    # ── Production & Finalization ──────────────────────────────────────

    def get_outputs(self, instance_id: int) -> list[dict[str, Any]]:
        """Get output items for an execution."""
        resp = self.client.get(
            self._url(f"/procedure-instances/{instance_id}/outputs")
        )
        resp.raise_for_status()
        return resp.json()

    def produce(self, instance_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """Record production output."""
        resp = self.client.post(
            self._url(f"/procedure-instances/{instance_id}/produce"),
            json=data,
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    def get_productions(self, instance_id: int) -> list[dict[str, Any]]:
        """Get production records for an instance."""
        resp = self.client.get(
            self._url(f"/procedure-instances/{instance_id}/productions")
        )
        resp.raise_for_status()
        return resp.json()

    def get_bom_reconciliation(self, instance_id: int) -> dict[str, Any]:
        """Get BOM reconciliation for an execution."""
        resp = self.client.get(
            self._url(f"/procedure-instances/{instance_id}/bom-reconciliation")
        )
        resp.raise_for_status()
        return resp.json()

    def finalize(self, instance_id: int) -> dict[str, Any]:
        """Finalize an execution."""
        resp = self.client.post(
            self._url(f"/procedure-instances/{instance_id}/finalize"),
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    # ── Issues ─────────────────────────────────────────────────────────

    def list_issues(
        self,
        issue_type: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """List issues."""
        params: dict[str, Any] = {"page": page, "page_size": page_size}
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

    def list_comments(self, issue_id: int) -> list[dict[str, Any]]:
        """List comments on an issue."""
        resp = self.client.get(self._url(f"/issues/{issue_id}/comments"))
        resp.raise_for_status()
        return resp.json()

    def create_comment(self, issue_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """Add a comment to an issue."""
        resp = self.client.post(
            self._url(f"/issues/{issue_id}/comments"),
            json=data,
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    # ── Risks ──────────────────────────────────────────────────────────

    def list_risks(
        self, status: str | None = None, page: int = 1, page_size: int = 50
    ) -> dict[str, Any]:
        """List risks."""
        params: dict[str, Any] = {"page": page, "page_size": page_size}
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

    def update_risk(self, risk_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """Update a risk."""
        resp = self.client.patch(
            self._url(f"/risks/{risk_id}"), json=data, headers=self._headers()
        )
        resp.raise_for_status()
        return resp.json()

    def get_risk_matrix(self) -> dict[str, Any]:
        """Get risk matrix data."""
        resp = self.client.get(self._url("/risks/matrix"))
        resp.raise_for_status()
        return resp.json()

    # ── Purchases ──────────────────────────────────────────────────────

    def list_purchases(
        self,
        status: str | None = None,
        supplier_id: int | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """List purchase orders."""
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if status:
            params["status"] = status
        if supplier_id:
            params["supplier_id"] = supplier_id
        resp = self.client.get(self._url("/purchases"), params=params)
        resp.raise_for_status()
        return resp.json()

    def get_purchase(self, purchase_id: int) -> dict[str, Any]:
        """Get a purchase order."""
        resp = self.client.get(self._url(f"/purchases/{purchase_id}"))
        resp.raise_for_status()
        return resp.json()

    def create_purchase(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a purchase order."""
        resp = self.client.post(
            self._url("/purchases"), json=data, headers=self._headers()
        )
        resp.raise_for_status()
        return resp.json()

    def update_purchase(self, purchase_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """Update a purchase order."""
        resp = self.client.patch(
            self._url(f"/purchases/{purchase_id}"), json=data, headers=self._headers()
        )
        resp.raise_for_status()
        return resp.json()

    def add_purchase_line(self, purchase_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """Add a line item to a purchase order."""
        resp = self.client.post(
            self._url(f"/purchases/{purchase_id}/lines"),
            json=data,
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    def receive_purchase(self, purchase_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """Receive items against a purchase order."""
        resp = self.client.post(
            self._url(f"/purchases/{purchase_id}/receive"),
            json=data,
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    # ── Suppliers ──────────────────────────────────────────────────────

    def list_suppliers(self, page: int = 1, page_size: int = 50) -> dict[str, Any]:
        """List suppliers."""
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        resp = self.client.get(self._url("/suppliers"), params=params)
        resp.raise_for_status()
        return resp.json()

    def get_supplier(self, supplier_id: int) -> dict[str, Any]:
        """Get a supplier."""
        resp = self.client.get(self._url(f"/suppliers/{supplier_id}"))
        resp.raise_for_status()
        return resp.json()

    def create_supplier(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a supplier."""
        resp = self.client.post(
            self._url("/suppliers"), json=data, headers=self._headers()
        )
        resp.raise_for_status()
        return resp.json()

    def update_supplier(self, supplier_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """Update a supplier."""
        resp = self.client.patch(
            self._url(f"/suppliers/{supplier_id}"), json=data, headers=self._headers()
        )
        resp.raise_for_status()
        return resp.json()

    # ── Workcenters ────────────────────────────────────────────────────

    def list_workcenters(self) -> dict[str, Any]:
        """List workcenters."""
        resp = self.client.get(self._url("/workcenters"))
        resp.raise_for_status()
        return resp.json()

    def get_workcenter(self, workcenter_id: int) -> dict[str, Any]:
        """Get a workcenter."""
        resp = self.client.get(self._url(f"/workcenters/{workcenter_id}"))
        resp.raise_for_status()
        return resp.json()

    def create_workcenter(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a workcenter."""
        resp = self.client.post(
            self._url("/workcenters"), json=data, headers=self._headers()
        )
        resp.raise_for_status()
        return resp.json()

    def update_workcenter(self, workcenter_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """Update a workcenter."""
        resp = self.client.patch(
            self._url(f"/workcenters/{workcenter_id}"), json=data, headers=self._headers()
        )
        resp.raise_for_status()
        return resp.json()

    # ── Users ──────────────────────────────────────────────────────────

    def list_users(self) -> dict[str, Any]:
        """List users."""
        resp = self.client.get(self._url("/users"), headers=self._headers())
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

    # ── Search ─────────────────────────────────────────────────────────

    def global_search(self, query: str) -> dict[str, Any]:
        """Search across all entities."""
        resp = self.client.get(self._url("/search"), params={"q": query})
        resp.raise_for_status()
        return resp.json()

    # ── Project Config ─────────────────────────────────────────────────

    def get_project_config(self) -> dict[str, Any]:
        """Get project configuration."""
        resp = self.client.get(self._url("/project/config"))
        resp.raise_for_status()
        return resp.json()

    # ── Health ─────────────────────────────────────────────────────────

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
