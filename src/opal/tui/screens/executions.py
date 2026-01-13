"""Executions screen - view and manage procedure executions."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, DataTable, Label, ProgressBar, Static

from opal.tui.api_client import get_client


class StepExecution(Static):
    """Individual step execution widget."""

    def __init__(self, step_data: dict, step_exec: dict | None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.step_data = step_data
        self.step_exec = step_exec

    def compose(self) -> ComposeResult:
        order = self.step_data.get("order", 0)
        title = self.step_data.get("title", "Untitled")
        is_contingency = self.step_data.get("is_contingency", False)

        status = "pending"
        if self.step_exec:
            status = self.step_exec.get("status", "pending")

        status_icon = {
            "pending": "[ ]",
            "in_progress": "[>]",
            "completed": "[x]",
            "skipped": "[-]",
        }.get(status, "[ ]")

        prefix = "[C] " if is_contingency else ""
        yield Label(f"{status_icon} {order}. {prefix}{title}", classes=f"step-line {status}")


class ExecutionDetail(Static):
    """Execution detail panel with step controls."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance_data: dict | None = None
        self.version_content: dict | None = None

    def compose(self) -> ComposeResult:
        yield Label("Execution Details", classes="section-title")
        yield Container(id="exec-detail-content")
        yield Label("Steps", classes="section-title")
        yield VerticalScroll(id="steps-execution")
        yield Horizontal(
            Button("Start Step", id="btn-start", variant="primary"),
            Button("Complete Step", id="btn-complete", variant="success"),
            classes="step-controls",
        )

    def show_execution(self, instance: dict, version_content: dict) -> None:
        """Display execution details."""
        self.instance_data = instance
        self.version_content = version_content

        content = self.query_one("#exec-detail-content", Container)
        content.remove_children()

        content.mount(Label(f"ID: {instance.get('id', '-')}", classes="detail-row"))
        content.mount(Label(f"Procedure: {instance.get('procedure_name', '-')}", classes="detail-row"))
        content.mount(Label(f"Work Order: {instance.get('work_order_number', '-') or 'N/A'}", classes="detail-row"))
        content.mount(Label(f"Status: {instance.get('status', '-')}", classes=f"detail-row status-{instance.get('status', 'unknown')}"))

        # Progress
        step_executions = instance.get("step_executions", [])
        completed = sum(1 for s in step_executions if s.get("status") in ["completed", "skipped"])
        total = len(step_executions)
        progress = (completed / total * 100) if total > 0 else 0
        content.mount(Label(f"Progress: {completed}/{total} ({progress:.0f}%)", classes="detail-row"))

        # Scheduling info
        if instance.get("scheduled_start_at"):
            content.mount(Label(f"Scheduled: {instance['scheduled_start_at'][:16]}", classes="detail-row"))
        if instance.get("target_completion_at"):
            content.mount(Label(f"Due: {instance['target_completion_at'][:16]}", classes="detail-row"))
        if instance.get("priority", 0) > 0:
            priority_text = {1: "High", 2: "Urgent"}.get(instance["priority"], str(instance["priority"]))
            content.mount(Label(f"Priority: {priority_text}", classes="detail-row priority"))

        # Show steps
        self._render_steps(instance, version_content)

    def _render_steps(self, instance: dict, version_content: dict) -> None:
        """Render step execution list."""
        steps_container = self.query_one("#steps-execution", VerticalScroll)
        steps_container.remove_children()

        steps = version_content.get("steps", [])
        step_executions = {s["step_number"]: s for s in instance.get("step_executions", [])}

        for step in sorted(steps, key=lambda s: s.get("order", 0)):
            step_exec = step_executions.get(step["order"])
            widget = StepExecution(step, step_exec)
            steps_container.mount(widget)

    def get_current_step(self) -> int | None:
        """Get the current step number to work on."""
        if not self.instance_data:
            return None

        step_executions = self.instance_data.get("step_executions", [])
        for step in sorted(step_executions, key=lambda s: s.get("step_number", 0)):
            if step.get("status") in ["pending", "in_progress"]:
                return step["step_number"]
        return None

    def clear(self) -> None:
        """Clear the detail panel."""
        self.instance_data = None
        self.version_content = None

        content = self.query_one("#exec-detail-content", Container)
        content.remove_children()
        content.mount(Label("Select an execution to view details", classes="hint"))

        steps_container = self.query_one("#steps-execution", VerticalScroll)
        steps_container.remove_children()


class ExecutionsScreen(Screen):
    """Executions list screen."""

    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("space", "start_step", "Start"),
        ("enter", "complete_step", "Complete"),
        ("escape", "go_back", "Back"),
    ]

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Executions", classes="screen-title"),
            Horizontal(
                Button("All", id="filter-all", variant="primary"),
                Button("Pending", id="filter-pending"),
                Button("In Progress", id="filter-in_progress"),
                Button("Completed", id="filter-completed"),
                classes="filter-bar",
            ),
            Horizontal(
                Vertical(
                    DataTable(id="executions-table"),
                    classes="table-container",
                ),
                ExecutionDetail(id="execution-detail"),
                classes="main-content",
            ),
            classes="screen-container",
        )

    async def on_mount(self) -> None:
        """Initialize the executions table."""
        table = self.query_one("#executions-table", DataTable)
        table.add_columns("ID", "Procedure", "Status", "Work Order", "Progress")
        table.cursor_type = "row"
        await self.load_executions()

    async def action_refresh(self) -> None:
        """Refresh executions list."""
        await self.load_executions()
        self.notify("Executions refreshed")

    def action_go_back(self) -> None:
        """Go back to dashboard."""
        self.app.switch_screen("dashboard")

    async def action_start_step(self) -> None:
        """Start the current step."""
        detail = self.query_one("#execution-detail", ExecutionDetail)
        if not detail.instance_data:
            self.notify("Select an execution first", severity="warning")
            return

        step_number = detail.get_current_step()
        if step_number is None:
            self.notify("No step to start", severity="warning")
            return

        client = get_client(self.app.api_url)
        try:
            client.start_step(detail.instance_data["id"], step_number)
            self.notify(f"Started step {step_number}")
            await self._reload_selected()
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    async def action_complete_step(self) -> None:
        """Complete the current step."""
        detail = self.query_one("#execution-detail", ExecutionDetail)
        if not detail.instance_data:
            self.notify("Select an execution first", severity="warning")
            return

        # Find in-progress step
        step_executions = detail.instance_data.get("step_executions", [])
        in_progress = [s for s in step_executions if s.get("status") == "in_progress"]

        if not in_progress:
            self.notify("No step in progress", severity="warning")
            return

        step_number = in_progress[0]["step_number"]

        client = get_client(self.app.api_url)
        try:
            client.complete_step(detail.instance_data["id"], step_number)
            self.notify(f"Completed step {step_number}")
            await self._reload_selected()
            await self.load_executions()
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    async def _reload_selected(self) -> None:
        """Reload the currently selected execution."""
        detail = self.query_one("#execution-detail", ExecutionDetail)
        if detail.instance_data:
            client = get_client(self.app.api_url)
            try:
                instance = client.get_instance(detail.instance_data["id"])
                version_content = client.get_version_content(detail.instance_data["id"])
                detail.show_execution(instance, version_content)
            except Exception:
                pass

    async def load_executions(self, status: str | None = None) -> None:
        """Load executions from API."""
        client = get_client(self.app.api_url)
        table = self.query_one("#executions-table", DataTable)
        detail = self.query_one("#execution-detail", ExecutionDetail)

        try:
            result = client.list_instances(status=status, page_size=100)
            instances = result.get("items", [])

            table.clear()
            for inst in instances:
                step_execs = inst.get("step_executions", [])
                completed = sum(1 for s in step_execs if s.get("status") in ["completed", "skipped"])
                total = len(step_execs)
                progress = f"{completed}/{total}"

                table.add_row(
                    str(inst.get("id", "")),
                    inst.get("procedure_name", ""),
                    inst.get("status", ""),
                    inst.get("work_order_number", "") or "-",
                    progress,
                    key=str(inst.get("id")),
                )

            detail.clear()

        except Exception as e:
            self.notify(f"Error loading executions: {e}", severity="error")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle filter button clicks."""
        button_id = event.button.id or ""

        if button_id.startswith("filter-"):
            status = button_id.replace("filter-", "")
            if status == "all":
                status = None
            await self.load_executions(status=status)

        elif button_id == "btn-start":
            await self.action_start_step()
        elif button_id == "btn-complete":
            await self.action_complete_step()

    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection."""
        client = get_client(self.app.api_url)
        detail = self.query_one("#execution-detail", ExecutionDetail)

        try:
            instance_id = int(event.row_key.value)
            instance = client.get_instance(instance_id)
            version_content = client.get_version_content(instance_id)
            detail.show_execution(instance, version_content)
        except Exception as e:
            self.notify(f"Error loading execution: {e}", severity="error")
