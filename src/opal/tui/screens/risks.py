"""Risks screen - view and manage risks."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Label, Static

from opal.tui.api_client import get_client


RISK_COLORS = {
    "low": "green",
    "medium": "yellow",
    "high": "orange",
    "critical": "red",
}


class RiskDetail(Static):
    """Risk detail panel."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.risk_data: dict | None = None

    def compose(self) -> ComposeResult:
        yield Label("Risk Details", classes="section-title")
        yield Container(id="risk-detail-content")

    def show_risk(self, risk: dict) -> None:
        """Display risk details."""
        self.risk_data = risk
        content = self.query_one("#risk-detail-content", Container)
        content.remove_children()

        content.mount(Label(f"ID: {risk.get('id', '-')}", classes="detail-row"))
        content.mount(Label(f"Title: {risk.get('title', '-')}", classes="detail-row"))

        status = risk.get("status", "-")
        content.mount(Label(f"Status: {status}", classes=f"detail-row status-{status}"))

        # Risk scoring
        probability = risk.get("probability", 0)
        impact = risk.get("impact", 0)
        score = risk.get("risk_score", 0)
        level = risk.get("risk_level", "unknown")

        content.mount(Label(f"Probability: {probability}/5", classes="detail-row"))
        content.mount(Label(f"Impact: {impact}/5", classes="detail-row"))
        content.mount(Label(f"Score: {score} ({level.upper()})", classes=f"detail-row risk-{level}"))

        # Description
        description = risk.get("description", "")
        if description:
            content.mount(Label("Description:", classes="detail-label"))
            content.mount(Label(description[:200], classes="detail-text"))

        # Mitigation
        mitigation = risk.get("mitigation_plan", "")
        if mitigation:
            content.mount(Label("Mitigation Plan:", classes="detail-label"))
            content.mount(Label(mitigation[:200], classes="detail-text"))

        # Owner
        if risk.get("owner_id"):
            content.mount(Label(f"Owner: User #{risk['owner_id']}", classes="detail-row"))

        # Timestamps
        created = risk.get("created_at", "")[:16] if risk.get("created_at") else "-"
        content.mount(Label(f"Created: {created}", classes="detail-row"))

    def clear(self) -> None:
        """Clear the detail panel."""
        self.risk_data = None
        content = self.query_one("#risk-detail-content", Container)
        content.remove_children()
        content.mount(Label("Select a risk to view details", classes="hint"))


class RiskMatrix(Static):
    """Risk matrix visualization."""

    def compose(self) -> ComposeResult:
        yield Label("Risk Matrix", classes="section-title")
        yield Container(id="matrix-content")

    def show_matrix(self, matrix_data: dict) -> None:
        """Display risk matrix."""
        content = self.query_one("#matrix-content", Container)
        content.remove_children()

        matrix = matrix_data.get("matrix", [])

        # Header row (impact levels)
        header = "     1   2   3   4   5  <- Impact"
        content.mount(Label(header, classes="matrix-header"))

        # Matrix rows (probability levels, from 5 to 1)
        for prob in range(5, 0, -1):
            row_data = matrix[prob - 1] if prob <= len(matrix) else [0] * 5
            cells = " ".join(f"[{c:2d}]" if c > 0 else " .  " for c in row_data)
            content.mount(Label(f"P{prob}: {cells}", classes="matrix-row"))

        content.mount(Label("^ Probability", classes="matrix-footer"))

        # Legend
        summary = matrix_data.get("summary", {})
        legend = f"Low:{summary.get('low', 0)} Med:{summary.get('medium', 0)} High:{summary.get('high', 0)} Crit:{summary.get('critical', 0)}"
        content.mount(Label(legend, classes="matrix-legend"))


class RisksScreen(Screen):
    """Risks list screen."""

    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("n", "new_risk", "New Risk"),
        ("m", "toggle_matrix", "Matrix"),
        ("escape", "go_back", "Back"),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.show_matrix = False

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Risks", classes="screen-title"),
            Horizontal(
                Button("All", id="filter-all", variant="primary"),
                Button("Identified", id="filter-identified"),
                Button("Mitigating", id="filter-mitigating"),
                Button("Accepted", id="filter-accepted"),
                Button("Closed", id="filter-closed"),
                classes="filter-bar",
            ),
            Horizontal(
                Vertical(
                    DataTable(id="risks-table"),
                    classes="table-container",
                ),
                Vertical(
                    RiskDetail(id="risk-detail"),
                    RiskMatrix(id="risk-matrix"),
                    classes="detail-panel",
                ),
                classes="main-content",
            ),
            classes="screen-container",
        )

    async def on_mount(self) -> None:
        """Initialize the risks table."""
        table = self.query_one("#risks-table", DataTable)
        table.add_columns("ID", "Title", "P", "I", "Score", "Level", "Status")
        table.cursor_type = "row"
        await self.load_risks()
        await self.load_matrix()

    async def action_refresh(self) -> None:
        """Refresh risks list."""
        await self.load_risks()
        await self.load_matrix()
        self.notify("Risks refreshed")

    def action_go_back(self) -> None:
        """Go back to dashboard."""
        self.app.switch_screen("dashboard")

    async def action_new_risk(self) -> None:
        """Show new risk dialog."""
        self.notify("Risk creation not yet implemented in TUI")

    def action_toggle_matrix(self) -> None:
        """Toggle risk matrix visibility."""
        matrix = self.query_one("#risk-matrix", RiskMatrix)
        matrix.display = not matrix.display
        self.notify("Matrix " + ("shown" if matrix.display else "hidden"))

    async def load_risks(self, status: str | None = None) -> None:
        """Load risks from API."""
        client = get_client(self.app.api_url)
        table = self.query_one("#risks-table", DataTable)
        detail = self.query_one("#risk-detail", RiskDetail)

        try:
            result = client.list_risks(status=status, page_size=100)
            risks = result.get("items", [])

            table.clear()
            for risk in risks:
                table.add_row(
                    str(risk.get("id", "")),
                    risk.get("title", "")[:30],
                    str(risk.get("probability", 0)),
                    str(risk.get("impact", 0)),
                    str(risk.get("risk_score", 0)),
                    risk.get("risk_level", "")[:4].upper(),
                    risk.get("status", ""),
                    key=str(risk.get("id")),
                )

            detail.clear()

        except Exception as e:
            self.notify(f"Error loading risks: {e}", severity="error")

    async def load_matrix(self) -> None:
        """Load risk matrix data."""
        client = get_client(self.app.api_url)
        matrix_widget = self.query_one("#risk-matrix", RiskMatrix)

        try:
            matrix_data = client.get_risk_matrix()
            matrix_widget.show_matrix(matrix_data)
        except Exception as e:
            self.notify(f"Error loading matrix: {e}", severity="error")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle filter button clicks."""
        button_id = event.button.id or ""

        if button_id.startswith("filter-"):
            status = button_id.replace("filter-", "")
            if status == "all":
                status = None
            await self.load_risks(status=status)

    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection."""
        client = get_client(self.app.api_url)
        detail = self.query_one("#risk-detail", RiskDetail)

        try:
            risk_id = int(event.row_key.value)
            risk = client.get_risk(risk_id)
            detail.show_risk(risk)
        except Exception as e:
            self.notify(f"Error loading risk: {e}", severity="error")
