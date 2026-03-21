"""Procedures screen - view and manage procedures."""

from typing import Any

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import DataTable, Input, Label, Select, Static, TextArea

from opal.tui.api_client import get_client
from opal.tui.widgets.form import ConfirmModal, FormGroup, FormModal


class ProcedureFormModal(FormModal):
    """Modal form for creating a procedure."""

    form_title = "New Procedure"

    def build_form(self) -> ComposeResult:
        yield FormGroup(
            "Name",
            Input(id="field-name", placeholder="Procedure name"),
            required=True,
        )
        type_options = [
            ("Operation", "op"),
            ("Inspection", "inspection"),
            ("Test", "test"),
            ("Build", "build"),
        ]
        yield FormGroup(
            "Type",
            Select(type_options, id="field-type", value="op"),
        )
        yield FormGroup(
            "Description",
            TextArea(id="field-description"),
        )

    def get_form_data(self) -> dict[str, Any] | None:
        name = self.query_one("#field-name", Input).value.strip()
        if not name:
            self.show_error("Name is required")
            return None
        proc_type = self.query_one("#field-type", Select).value
        description = self.query_one("#field-description", TextArea).text.strip()
        return {
            "name": name,
            "procedure_type": proc_type if proc_type != Select.BLANK else "op",
            "description": description,
        }


class StepFormModal(FormModal):
    """Modal form for adding/editing a procedure step."""

    def __init__(self, step: dict[str, Any] | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.step = step

    @property
    def form_title(self) -> str:
        return "Edit Step" if self.step else "Add Step"

    def build_form(self) -> ComposeResult:
        title_val = self.step.get("title", "") if self.step else ""
        desc_val = self.step.get("description", "") if self.step else ""
        is_contingency = self.step.get("is_contingency", False) if self.step else False

        yield FormGroup(
            "Title",
            Input(value=title_val, id="field-title", placeholder="Step title"),
            required=True,
        )
        yield FormGroup(
            "Description",
            TextArea(text=desc_val, id="field-description"),
        )
        contingency_options = [("No", "false"), ("Yes", "true")]
        yield FormGroup(
            "Contingency Step?",
            Select(
                contingency_options,
                id="field-contingency",
                value="true" if is_contingency else "false",
            ),
        )

    def get_form_data(self) -> dict[str, Any] | None:
        title = self.query_one("#field-title", Input).value.strip()
        if not title:
            self.show_error("Title is required")
            return None
        description = self.query_one("#field-description", TextArea).text.strip()
        contingency = self.query_one("#field-contingency", Select).value
        return {
            "title": title,
            "description": description,
            "is_contingency": contingency == "true",
        }


class StepsList(Static):
    """List of procedure steps."""

    def compose(self) -> ComposeResult:
        yield Label("Steps", classes="section-title")
        yield VerticalScroll(id="steps-list")

    def show_steps(self, steps: list[dict[str, Any]]) -> None:
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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.procedure_data: dict[str, Any] | None = None

    def compose(self) -> ComposeResult:
        yield Label("Procedure Details", classes="section-title")
        yield Container(id="procedure-detail-content")
        yield StepsList(id="steps-panel")

    def show_procedure(self, procedure: dict[str, Any]) -> None:
        """Display procedure details."""
        self.procedure_data = procedure
        content = self.query_one("#procedure-detail-content", Container)
        content.remove_children()

        content.mount(Label(f"ID: {procedure.get('id', '-')}", classes="detail-row"))
        content.mount(Label(f"Name: {procedure.get('name', '-')}", classes="detail-row"))
        content.mount(Label(f"Code: {procedure.get('code', '-')}", classes="detail-row"))
        content.mount(Label(f"Category: {procedure.get('category', '-')}", classes="detail-row"))
        content.mount(
            Label(f"Type: {procedure.get('procedure_type', 'op')}", classes="detail-row")
        )

        current_version = procedure.get("current_version_id")
        if current_version:
            content.mount(
                Label(f"Published: Yes (v{current_version})", classes="detail-row published")
            )
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
        ("a", "add_step", "Add Step"),
        ("s", "start_execution", "Start"),
        ("ctrl+p", "publish", "Publish"),
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
        self.app.push_screen(ProcedureFormModal(), callback=self._on_procedure_created)

    def _on_procedure_created(self, data: dict[str, Any] | None) -> None:
        """Handle procedure creation result."""
        if data is None:
            return
        client = get_client(self.app.api_url)
        try:
            proc = client.create_procedure(data)
            self.notify(f"Created procedure: {proc.get('name', '')}")
            self.run_worker(self.load_procedures())
        except Exception as e:
            self.notify(f"Error creating procedure: {e}", severity="error")

    async def action_add_step(self) -> None:
        """Add a step to the selected procedure."""
        detail = self.query_one("#procedure-detail", ProcedureDetail)
        if not detail.procedure_data:
            self.notify("Select a procedure first", severity="warning")
            return
        if detail.procedure_data.get("current_version_id"):
            self.notify("Cannot edit published procedure (edit master)", severity="warning")
        self.app.push_screen(StepFormModal(), callback=self._on_step_added)

    def _on_step_added(self, data: dict[str, Any] | None) -> None:
        """Handle step creation result."""
        if data is None:
            return
        detail = self.query_one("#procedure-detail", ProcedureDetail)
        if not detail.procedure_data:
            return
        client = get_client(self.app.api_url)
        try:
            client.create_step(detail.procedure_data["id"], data)
            self.notify("Step added")
            # Reload procedure detail
            proc = client.get_procedure(detail.procedure_data["id"])
            detail.show_procedure(proc)
        except Exception as e:
            self.notify(f"Error adding step: {e}", severity="error")

    async def action_publish(self) -> None:
        """Publish the selected procedure."""
        detail = self.query_one("#procedure-detail", ProcedureDetail)
        if not detail.procedure_data:
            self.notify("Select a procedure first", severity="warning")
            return

        self.app.push_screen(
            ConfirmModal(
                title="Publish Procedure",
                message=f"Publish '{detail.procedure_data.get('name', '')}'? This creates an immutable snapshot.",
                confirm_label="Publish",
            ),
            callback=self._on_publish_confirmed,
        )

    def _on_publish_confirmed(self, confirmed: bool) -> None:
        """Handle publish confirmation."""
        if not confirmed:
            return
        detail = self.query_one("#procedure-detail", ProcedureDetail)
        if not detail.procedure_data:
            return
        client = get_client(self.app.api_url)
        try:
            client.publish_procedure(detail.procedure_data["id"])
            self.notify("Procedure published")
            self.run_worker(self.load_procedures())
        except Exception as e:
            self.notify(f"Error publishing: {e}", severity="error")

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
                    p
                    for p in procedures
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
