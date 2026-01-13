"""Procedures screen - view and manage procedures."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import DataTable, Input, Label, Static

from opal.tui.api_client import get_client


class StepsList(Static):
    """List of procedure steps."""

    def compose(self) -> ComposeResult:
        yield Label("Steps", classes="section-title")
        yield VerticalScroll(id="steps-list")

    def show_steps(self, steps: list[dict]) -> None:
        """Display procedure steps."""
        container = self.query_one("#steps-list", VerticalScroll)
        container.remove_children()

        if not steps:
            container.mount(Label("No steps defined", classes="hint"))
            return

        for step in sorted(steps, key=lambda s: s.get("order", 0)):
            order = step.get("order", 0)
            title = step.get("title", "Untitled")
            is_contingency = step.get("is_contingency", False)

            step_class = "step-item contingency" if is_contingency else "step-item"
            prefix = "[C] " if is_contingency else ""
            container.mount(Label(f"{order}. {prefix}{title}", classes=step_class))

    def clear(self) -> None:
        """Clear the steps list."""
        container = self.query_one("#steps-list", VerticalScroll)
        container.remove_children()


class ProcedureDetail(Static):
    """Procedure detail panel."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.procedure_data: dict | None = None

    def compose(self) -> ComposeResult:
        yield Label("Procedure Details", classes="section-title")
        yield Container(id="procedure-detail-content")
        yield StepsList(id="steps-panel")

    def show_procedure(self, procedure: dict) -> None:
        """Display procedure details."""
        self.procedure_data = procedure
        content = self.query_one("#procedure-detail-content", Container)
        content.remove_children()

        content.mount(Label(f"ID: {procedure.get('id', '-')}", classes="detail-row"))
        content.mount(Label(f"Name: {procedure.get('name', '-')}", classes="detail-row"))
        content.mount(Label(f"Code: {procedure.get('code', '-')}", classes="detail-row"))
        content.mount(Label(f"Category: {procedure.get('category', '-')}", classes="detail-row"))
        content.mount(Label(f"Type: {procedure.get('procedure_type', 'op')}", classes="detail-row"))

        current_version = procedure.get("current_version_id")
        if current_version:
            content.mount(Label(f"Published: Yes (v{current_version})", classes="detail-row published"))
        else:
            content.mount(Label("Published: No (draft)", classes="detail-row draft"))

        # Show steps
        steps_panel = self.query_one("#steps-panel", StepsList)
        steps_panel.show_steps(procedure.get("steps", []))

    def clear(self) -> None:
        """Clear the detail panel."""
        self.procedure_data = None
        content = self.query_one("#procedure-detail-content", Container)
        content.remove_children()
        content.mount(Label("Select a procedure to view details", classes="hint"))

        steps_panel = self.query_one("#steps-panel", StepsList)
        steps_panel.clear()


class ProceduresScreen(Screen):
    """Procedures list screen."""

    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("n", "new_procedure", "New"),
        ("s", "start_execution", "Start"),
        ("escape", "go_back", "Back"),
        ("/", "focus_search", "Search"),
    ]

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Procedures", classes="screen-title"),
            Horizontal(
                Input(placeholder="Search procedures...", id="search-input"),
                classes="search-bar",
            ),
            Horizontal(
                Vertical(
                    DataTable(id="procedures-table"),
                    classes="table-container",
                ),
                ProcedureDetail(id="procedure-detail"),
                classes="main-content",
            ),
            classes="screen-container",
        )

    async def on_mount(self) -> None:
        """Initialize the procedures table."""
        table = self.query_one("#procedures-table", DataTable)
        table.add_columns("ID", "Code", "Name", "Category", "Type", "Published")
        table.cursor_type = "row"
        await self.load_procedures()

    async def action_refresh(self) -> None:
        """Refresh procedures list."""
        await self.load_procedures()
        self.notify("Procedures refreshed")

    async def action_focus_search(self) -> None:
        """Focus the search input."""
        search = self.query_one("#search-input", Input)
        search.focus()

    def action_go_back(self) -> None:
        """Go back to dashboard."""
        self.app.switch_screen("dashboard")

    async def action_new_procedure(self) -> None:
        """Show new procedure dialog."""
        self.notify("Procedure creation not yet implemented in TUI")

    async def action_start_execution(self) -> None:
        """Start execution of selected procedure."""
        detail = self.query_one("#procedure-detail", ProcedureDetail)
        if not detail.procedure_data:
            self.notify("Select a procedure first", severity="warning")
            return

        procedure = detail.procedure_data
        if not procedure.get("current_version_id"):
            self.notify("Procedure must be published first", severity="warning")
            return

        client = get_client(self.app.api_url)
        try:
            instance = client.create_instance({"procedure_id": procedure["id"]})
            self.notify(f"Started execution #{instance['id']}")
            self.app.switch_screen("executions")
        except Exception as e:
            self.notify(f"Error starting execution: {e}", severity="error")

    async def load_procedures(self, search: str | None = None) -> None:
        """Load procedures from API."""
        client = get_client(self.app.api_url)
        table = self.query_one("#procedures-table", DataTable)
        detail = self.query_one("#procedure-detail", ProcedureDetail)

        try:
            result = client.list_procedures(page_size=100)
            procedures = result.get("items", [])

            # Filter by search if provided
            if search:
                search_lower = search.lower()
                procedures = [
                    p for p in procedures
                    if search_lower in p.get("name", "").lower()
                    or search_lower in p.get("code", "").lower()
                ]

            table.clear()
            for proc in procedures:
                published = "Yes" if proc.get("current_version_id") else "No"
                table.add_row(
                    str(proc.get("id", "")),
                    proc.get("code", ""),
                    proc.get("name", ""),
                    proc.get("category", ""),
                    proc.get("procedure_type", "op"),
                    published,
                    key=str(proc.get("id")),
                )

            detail.clear()

        except Exception as e:
            self.notify(f"Error loading procedures: {e}", severity="error")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle search submission."""
        if event.input.id == "search-input":
            search = event.value.strip() or None
            await self.load_procedures(search=search)

    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection."""
        client = get_client(self.app.api_url)
        detail = self.query_one("#procedure-detail", ProcedureDetail)

        try:
            procedure_id = int(event.row_key.value)
            procedure = client.get_procedure(procedure_id)
            detail.show_procedure(procedure)
        except Exception as e:
            self.notify(f"Error loading procedure: {e}", severity="error")
