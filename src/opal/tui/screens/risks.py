"""Risks screen - view and manage risks."""

from typing import Any

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Input, Label, Select, Static, TextArea

from opal.tui.api_client import get_client
from opal.tui.widgets.form import FormGroup, FormModal


class RiskFormModal(FormModal):
    """Modal form for creating/editing a risk."""

    def __init__(self, risk: dict[str, Any] | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.risk = risk

    @property
    def form_title(self) -> str:
        return "Edit Risk" if self.risk else "New Risk"

    def build_form(self) -> ComposeResult:
        title_val = self.risk.get("title", "") if self.risk else ""
        desc_val = self.risk.get("description", "") if self.risk else ""
        mitigation_val = self.risk.get("mitigation_plan", "") if self.risk else ""

        yield FormGroup(
            "Title",
            Input(value=title_val, id="field-title", placeholder="Risk title"),
            required=True,
        )

        prob_options = [(str(i), str(i)) for i in range(1, 6)]
        current_prob = str(self.risk.get("probability", 3)) if self.risk else "3"
        yield FormGroup(
            "Probability (1-5)",
            Select(prob_options, id="field-probability", value=current_prob),
            required=True,
        )

        impact_options = [(str(i), str(i)) for i in range(1, 6)]
        current_impact = str(self.risk.get("impact", 3)) if self.risk else "3"
        yield FormGroup(
            "Impact (1-5)",
            Select(impact_options, id="field-impact", value=current_impact),
            required=True,
        )

        if self.risk:
            status_options = [
                ("Identified", "identified"),
                ("Analyzing", "analyzing"),
                ("Mitigating", "mitigating"),
                ("Monitoring", "monitoring"),
                ("Accepted", "accepted"),
                ("Closed", "closed"),
            ]
            yield FormGroup(
                "Status",
                Select(
                    status_options,
                    id="field-status",
                    value=self.risk.get("status", "identified"),
                ),
            )

        yield FormGroup(
            "Description",
            TextArea(text=desc_val, id="field-description"),
        )

        yield FormGroup(
            "Mitigation Plan",
            TextArea(text=mitigation_val, id="field-mitigation"),
        )

    def get_form_data(self) -> dict[str, Any] | None:
        title = self.query_one("#field-title", Input).value.strip()
        if not title:
            self.show_error("Title is required")
            return None

        probability = self.query_one("#field-probability", Select).value
        impact = self.query_one("#field-impact", Select).value
        description = self.query_one("#field-description", TextArea).text.strip()
        mitigation = self.query_one("#field-mitigation", TextArea).text.strip()

        data: dict[str, Any] = {
            "title": title,
            "probability": int(probability) if probability != Select.BLANK else 3,
            "impact": int(impact) if impact != Select.BLANK else 3,
            "description": description,
            "mitigation_plan": mitigation,
        }

        if self.risk:
            try:
                status = self.query_one("#field-status", Select).value
                if status != Select.BLANK:
                    data["status"] = status
            except Exception:
                pass

        return data


class RiskDetail(Static):
    """Risk detail panel."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.risk_data: dict[str, Any] | None = None

    def compose(self) -> ComposeResult:
        yield Label("Risk Details", classes="section-title")
        yield Container(id="risk-detail-content")

    def show_risk(self, risk: dict[str, Any]) -> None:
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
        content.mount(
            Label(f"Score: {score} ({level.upper()})", classes=f"detail-row risk-{level}")
        )

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

        # Linked issue
        if risk.get("linked_issue_id"):
            content.mount(
                Label(f"Linked Issue: #{risk['linked_issue_id']}", classes="detail-row")
            )

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

    def show_matrix(self, matrix_data: dict[str, Any]) -> None:
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
        legend_parts = [
            f"Low:{summary.get('low', 0)}",
            f"Med:{summary.get('medium', 0)}",
            f"High:{summary.get('high', 0)}",
            f"Crit:{summary.get('critical', 0)}",
        ]
        content.mount(Label(" ".join(legend_parts), classes="matrix-legend"))


class RisksScreen(Screen):
    """Risks list screen."""

    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("n", "new_risk", "New Risk"),
        ("ctrl+e", "edit_risk", "Edit"),
        ("m", "toggle_matrix", "Matrix"),
        ("escape", "go_back", "Back"),
    ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.show_matrix = False

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Risks", classes="screen-title"),
            Horizontal(
                Button("All", id="filter-all", variant="primary"),
                Button("Identified", id="filter-identified"),
                Button("Analyzing", id="filter-analyzing"),
                Button("Mitigating", id="filter-mitigating"),
                Button("Monitoring", id="filter-monitoring"),
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
        self.app.push_screen(RiskFormModal(), callback=self._on_risk_created)

    def _on_risk_created(self, data: dict[str, Any] | None) -> None:
        """Handle risk creation result."""
        if data is None:
            return
        client = get_client(self.app.api_url)
        try:
            risk = client.create_risk(data)
            self.notify(f"Created risk: {risk.get('title', '')}")
            self.run_worker(self.load_risks())
            self.run_worker(self.load_matrix())
        except Exception as e:
            self.notify(f"Error creating risk: {e}", severity="error")

    async def action_edit_risk(self) -> None:
        """Edit the selected risk."""
        detail = self.query_one("#risk-detail", RiskDetail)
        if not detail.risk_data:
            self.notify("Select a risk first", severity="warning")
            return
        self.app.push_screen(
            RiskFormModal(risk=detail.risk_data),
            callback=self._on_risk_edited,
        )

    def _on_risk_edited(self, data: dict[str, Any] | None) -> None:
        """Handle risk edit result."""
        if data is None:
            return
        detail = self.query_one("#risk-detail", RiskDetail)
        if not detail.risk_data:
            return
        client = get_client(self.app.api_url)
        try:
            client.update_risk(detail.risk_data["id"], data)
            self.notify("Risk updated")
            self.run_worker(self.load_risks())
            self.run_worker(self.load_matrix())
        except Exception as e:
            self.notify(f"Error updating risk: {e}", severity="error")

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
