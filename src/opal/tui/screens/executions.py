"""Executions screen - view and manage procedure executions."""

from typing import Any

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, DataTable, Input, Label, Select, Static, TextArea

from opal.tui.api_client import get_client
from opal.tui.widgets.form import ConfirmModal, FormGroup, FormModal


class StepNotesModal(FormModal):
    """Modal for editing step notes."""

    form_title = "Step Notes"

    def __init__(self, current_notes: str = "", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.current_notes = current_notes

    def build_form(self) -> ComposeResult:
        yield FormGroup(
            "Notes",
            TextArea(text=self.current_notes, id="field-notes"),
        )

    def get_form_data(self) -> dict[str, Any] | None:
        notes = self.query_one("#field-notes", TextArea).text.strip()
        return {"notes": notes}


class NCLogModal(FormModal):
    """Modal for logging a non-conformance during execution."""

    form_title = "Log Non-Conformance"

    def build_form(self) -> ComposeResult:
        yield FormGroup(
            "Title",
            Input(id="field-title", placeholder="NC description"),
            required=True,
        )
        priority_options = [
            ("Low", "low"),
            ("Medium", "medium"),
            ("High", "high"),
            ("Critical", "critical"),
        ]
        yield FormGroup(
            "Priority",
            Select(priority_options, id="field-priority", value="medium"),
        )
        yield FormGroup(
            "Description",
            TextArea(id="field-description"),
        )

    def get_form_data(self) -> dict[str, Any] | None:
        title = self.query_one("#field-title", Input).value.strip()
        if not title:
            self.show_error("Title is required")
            return None
        priority = self.query_one("#field-priority", Select).value
        description = self.query_one("#field-description", TextArea).text.strip()
        return {
            "title": title,
            "priority": priority if priority != Select.BLANK else "medium",
            "description": description,
        }


class ProduceModal(FormModal):
    """Modal for recording production output."""

    form_title = "Record Production"

    def __init__(self, outputs: list[dict[str, Any]], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.outputs = outputs

    def build_form(self) -> ComposeResult:
        if self.outputs:
            output_options = []
            for o in self.outputs:
                part_id = o.get("part_id", "?")
                name = o.get("part_name", f"Part #{part_id}")
                output_options.append((name, str(o.get("part_id", ""))))
            yield FormGroup(
                "Output Part",
                Select(output_options, id="field-part", prompt="Select output..."),
                required=True,
            )
        else:
            yield FormGroup(
                "Part ID",
                Input(id="field-part-id", placeholder="Part ID to produce"),
                required=True,
            )
        yield FormGroup(
            "Quantity",
            Input(id="field-quantity", placeholder="1", value="1"),
            required=True,
        )
        yield FormGroup(
            "Location",
            Input(id="field-location", placeholder="Storage location"),
        )

    def get_form_data(self) -> dict[str, Any] | None:
        if self.outputs:
            part_sel = self.query_one("#field-part", Select).value
            if part_sel == Select.BLANK:
                self.show_error("Select an output part")
                return None
            part_id = int(part_sel)
        else:
            pid = self.query_one("#field-part-id", Input).value.strip()
            if not pid:
                self.show_error("Part ID is required")
                return None
            try:
                part_id = int(pid)
            except ValueError:
                self.show_error("Part ID must be a number")
                return None

        qty_str = self.query_one("#field-quantity", Input).value.strip()
        try:
            quantity = int(qty_str) if qty_str else 1
        except ValueError:
            self.show_error("Quantity must be a number")
            return None

        location = self.query_one("#field-location", Input).value.strip()

        data: dict[str, Any] = {"part_id": part_id, "quantity": quantity}
        if location:
            data["location"] = location
        return data


class StepExecution(Static):
    """Individual step execution widget."""

    def __init__(
        self,
        step_data: dict[str, Any],
        step_exec: dict[str, Any] | None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
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
        line = f"{status_icon} {order}. {prefix}{title}"

        # Show notes indicator
        if self.step_exec and self.step_exec.get("notes"):
            line += " [N]"

        # Show signoff indicator
        if self.step_exec and self.step_exec.get("signed_off_by"):
            line += " [S]"

        yield Label(line, classes=f"step-line {status}")


class ExecutionDetail(Static):
    """Execution detail panel with step controls."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.instance_data: dict[str, Any] | None = None
        self.version_content: dict[str, Any] | None = None

    def compose(self) -> ComposeResult:
        yield Label("Execution Details", classes="section-title")
        yield Container(id="exec-detail-content")
        yield Label("Steps", classes="section-title")
        yield VerticalScroll(id="steps-execution")
        yield Horizontal(
            Button("Start Step", id="btn-start", variant="primary"),
            Button("Complete Step", id="btn-complete", variant="success"),
            Button("Skip Step", id="btn-skip", variant="default"),
            Button("Sign Off", id="btn-signoff", variant="warning"),
            Button("Notes", id="btn-notes", variant="default"),
            Button("Log NC", id="btn-nc", variant="error"),
            classes="step-controls",
        )
        yield Label("Kit & Production", classes="section-title")
        yield Horizontal(
            Button("Kit Status", id="btn-kit", variant="default"),
            Button("Consume Kit", id="btn-consume", variant="warning"),
            Button("Produce", id="btn-produce", variant="success"),
            Button("Finalize", id="btn-finalize", variant="primary"),
            classes="step-controls",
        )
        yield VerticalScroll(id="kit-production-panel")

    def show_execution(
        self, instance: dict[str, Any], version_content: dict[str, Any]
    ) -> None:
        """Display execution details."""
        self.instance_data = instance
        self.version_content = version_content

        content = self.query_one("#exec-detail-content", Container)
        content.remove_children()

        content.mount(Label(f"ID: {instance.get('id', '-')}", classes="detail-row"))
        content.mount(
            Label(f"Procedure: {instance.get('procedure_name', '-')}", classes="detail-row")
        )
        content.mount(
            Label(
                f"Work Order: {instance.get('work_order_number', '-') or 'N/A'}",
                classes="detail-row",
            )
        )
        content.mount(
            Label(
                f"Status: {instance.get('status', '-')}",
                classes=f"detail-row status-{instance.get('status', 'unknown')}",
            )
        )

        # Progress
        step_executions = instance.get("step_executions", [])
        completed = sum(
            1 for s in step_executions if s.get("status") in ["completed", "skipped"]
        )
        total = len(step_executions)
        progress = (completed / total * 100) if total > 0 else 0
        content.mount(
            Label(f"Progress: {completed}/{total} ({progress:.0f}%)", classes="detail-row")
        )

        # Scheduling info
        if instance.get("scheduled_start_at"):
            content.mount(
                Label(
                    f"Scheduled: {instance['scheduled_start_at'][:16]}", classes="detail-row"
                )
            )
        if instance.get("target_completion_at"):
            content.mount(
                Label(f"Due: {instance['target_completion_at'][:16]}", classes="detail-row")
            )
        if instance.get("priority", 0) > 0:
            priority_text = {1: "High", 2: "Urgent"}.get(
                instance["priority"], str(instance["priority"])
            )
            content.mount(Label(f"Priority: {priority_text}", classes="detail-row priority"))

        # Show steps
        self._render_steps(instance, version_content)

    def _render_steps(
        self, instance: dict[str, Any], version_content: dict[str, Any]
    ) -> None:
        """Render step execution list."""
        steps_container = self.query_one("#steps-execution", VerticalScroll)
        steps_container.remove_children()

        steps = version_content.get("steps", [])
        step_executions = {
            s["step_number"]: s for s in instance.get("step_executions", [])
        }

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

    def get_in_progress_step(self) -> dict[str, Any] | None:
        """Get the in-progress step execution data."""
        if not self.instance_data:
            return None
        step_executions = self.instance_data.get("step_executions", [])
        for step in step_executions:
            if step.get("status") == "in_progress":
                return step
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

        kit_panel = self.query_one("#kit-production-panel", VerticalScroll)
        kit_panel.remove_children()

    def show_kit_availability(self, kit_data: dict[str, Any] | list[dict[str, Any]]) -> None:
        """Display kit availability in the panel."""
        panel = self.query_one("#kit-production-panel", VerticalScroll)
        panel.remove_children()
        panel.mount(Label("Kit Availability:", classes="detail-label"))

        items = kit_data if isinstance(kit_data, list) else kit_data.get("items", [])
        if not items:
            panel.mount(Label("  No kit items required", classes="hint"))
            return

        for item in items:
            pid = item.get("part_id", "?")
            part = item.get("part_name", item.get("part_number", f"#{pid}"))
            required = item.get("required_quantity", item.get("quantity", 0))
            available = item.get("available_quantity", item.get("available", "?"))
            if isinstance(available, (int, float)):
                ready = item.get("is_available", available >= required)
            else:
                ready = item.get("is_available", False)
            icon = "[OK]" if ready else "[!!]"
            panel.mount(
                Label(f"  {icon} {part}: need {required}, have {available}", classes="detail-row")
            )

    def show_productions(self, productions: list[dict[str, Any]]) -> None:
        """Display production records in the panel."""
        panel = self.query_one("#kit-production-panel", VerticalScroll)
        panel.remove_children()
        panel.mount(Label("Production Records:", classes="detail-label"))

        if not productions:
            panel.mount(Label("  No production yet", classes="hint"))
            return

        for prod in productions:
            pid = prod.get("part_id", "?")
            part = prod.get("part_name", f"Part #{pid}")
            qty = prod.get("quantity", 0)
            panel.mount(Label(f"  {part} x{qty}", classes="detail-row"))

    def show_consumptions(self, consumptions: list[dict[str, Any]]) -> None:
        """Display consumption records in the panel."""
        panel = self.query_one("#kit-production-panel", VerticalScroll)
        panel.remove_children()
        panel.mount(Label("Consumptions:", classes="detail-label"))

        if not consumptions:
            panel.mount(Label("  No consumptions yet", classes="hint"))
            return

        for cons in consumptions:
            cid = cons.get("part_id", "?")
            part = cons.get("part_name", f"Part #{cid}")
            qty = cons.get("quantity", 0)
            panel.mount(Label(f"  {part} x{qty}", classes="detail-row"))


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

    async def _skip_step(self) -> None:
        """Skip the current step."""
        detail = self.query_one("#execution-detail", ExecutionDetail)
        if not detail.instance_data:
            self.notify("Select an execution first", severity="warning")
            return

        step_number = detail.get_current_step()
        if step_number is None:
            self.notify("No step to skip", severity="warning")
            return

        client = get_client(self.app.api_url)
        try:
            client.skip_step(detail.instance_data["id"], step_number)
            self.notify(f"Skipped step {step_number}")
            await self._reload_selected()
            await self.load_executions()
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    async def _signoff_step(self) -> None:
        """Sign off on the in-progress step."""
        detail = self.query_one("#execution-detail", ExecutionDetail)
        if not detail.instance_data:
            self.notify("Select an execution first", severity="warning")
            return

        step = detail.get_in_progress_step()
        if not step:
            self.notify("No step in progress to sign off", severity="warning")
            return

        client = get_client(self.app.api_url)
        try:
            client.signoff_step(detail.instance_data["id"], step["step_number"])
            self.notify(f"Signed off step {step['step_number']}")
            await self._reload_selected()
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    async def _edit_notes(self) -> None:
        """Edit notes for the in-progress step."""
        detail = self.query_one("#execution-detail", ExecutionDetail)
        if not detail.instance_data:
            self.notify("Select an execution first", severity="warning")
            return

        step = detail.get_in_progress_step()
        if not step:
            self.notify("No step in progress", severity="warning")
            return

        current_notes = step.get("notes", "")
        self.app.push_screen(
            StepNotesModal(current_notes=current_notes),
            callback=self._on_notes_saved,
        )

    def _on_notes_saved(self, data: dict[str, Any] | None) -> None:
        """Handle notes save result."""
        if data is None:
            return
        detail = self.query_one("#execution-detail", ExecutionDetail)
        if not detail.instance_data:
            return
        step = detail.get_in_progress_step()
        if not step:
            return
        client = get_client(self.app.api_url)
        try:
            client.update_step_notes(
                detail.instance_data["id"], step["step_number"], data["notes"]
            )
            self.notify("Notes updated")
            self.run_worker(self._reload_selected())
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    async def _log_nc(self) -> None:
        """Log a non-conformance for the current step."""
        detail = self.query_one("#execution-detail", ExecutionDetail)
        if not detail.instance_data:
            self.notify("Select an execution first", severity="warning")
            return

        step = detail.get_in_progress_step()
        if not step:
            self.notify("No step in progress", severity="warning")
            return

        self.app.push_screen(NCLogModal(), callback=self._on_nc_logged)

    def _on_nc_logged(self, data: dict[str, Any] | None) -> None:
        """Handle NC log result."""
        if data is None:
            return
        detail = self.query_one("#execution-detail", ExecutionDetail)
        if not detail.instance_data:
            return
        step = detail.get_in_progress_step()
        if not step:
            return
        client = get_client(self.app.api_url)
        try:
            result = client.log_nc(detail.instance_data["id"], step["step_number"], data)
            issue_id = result.get("id", result.get("issue_id", "?"))
            self.notify(f"NC logged as issue #{issue_id}")
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
                completed = sum(
                    1
                    for s in step_execs
                    if s.get("status") in ["completed", "skipped"]
                )
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
        """Handle filter and control button clicks."""
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
        elif button_id == "btn-skip":
            await self._skip_step()
        elif button_id == "btn-signoff":
            await self._signoff_step()
        elif button_id == "btn-notes":
            await self._edit_notes()
        elif button_id == "btn-nc":
            await self._log_nc()
        elif button_id == "btn-kit":
            await self._show_kit()
        elif button_id == "btn-consume":
            await self._consume_kit()
        elif button_id == "btn-produce":
            await self._produce()
        elif button_id == "btn-finalize":
            await self._finalize()

    async def _show_kit(self) -> None:
        """Show kit availability for selected execution."""
        detail = self.query_one("#execution-detail", ExecutionDetail)
        if not detail.instance_data:
            self.notify("Select an execution first", severity="warning")
            return
        client = get_client(self.app.api_url)
        try:
            kit = client.get_kit_availability(detail.instance_data["id"])
            detail.show_kit_availability(kit)
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    async def _consume_kit(self) -> None:
        """Consume kit items for selected execution."""
        detail = self.query_one("#execution-detail", ExecutionDetail)
        if not detail.instance_data:
            self.notify("Select an execution first", severity="warning")
            return
        client = get_client(self.app.api_url)
        try:
            client.consume_kit(detail.instance_data["id"])
            self.notify("Kit consumed")
            # Show consumptions
            consumptions = client.get_consumptions(detail.instance_data["id"])
            detail.show_consumptions(consumptions)
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    async def _produce(self) -> None:
        """Record production output."""
        detail = self.query_one("#execution-detail", ExecutionDetail)
        if not detail.instance_data:
            self.notify("Select an execution first", severity="warning")
            return
        client = get_client(self.app.api_url)
        try:
            outputs = client.get_outputs(detail.instance_data["id"])
        except Exception:
            outputs = []
        self.app.push_screen(
            ProduceModal(outputs=outputs),
            callback=self._on_produced,
        )

    def _on_produced(self, data: dict[str, Any] | None) -> None:
        """Handle production result."""
        if data is None:
            return
        detail = self.query_one("#execution-detail", ExecutionDetail)
        if not detail.instance_data:
            return
        client = get_client(self.app.api_url)
        try:
            client.produce(detail.instance_data["id"], data)
            self.notify("Production recorded")
            # Show productions
            productions = client.get_productions(detail.instance_data["id"])
            detail.show_productions(productions)
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    async def _finalize(self) -> None:
        """Finalize the selected execution."""
        detail = self.query_one("#execution-detail", ExecutionDetail)
        if not detail.instance_data:
            self.notify("Select an execution first", severity="warning")
            return

        self.app.push_screen(
            ConfirmModal(
                title="Finalize Execution",
                message=f"Finalize execution #{detail.instance_data['id']}? This locks all records.",
                confirm_label="Finalize",
            ),
            callback=self._on_finalize_confirmed,
        )

    def _on_finalize_confirmed(self, confirmed: bool) -> None:
        """Handle finalize confirmation."""
        if not confirmed:
            return
        detail = self.query_one("#execution-detail", ExecutionDetail)
        if not detail.instance_data:
            return
        client = get_client(self.app.api_url)
        try:
            client.finalize(detail.instance_data["id"])
            self.notify("Execution finalized")
            self.run_worker(self.load_executions())
            self.run_worker(self._reload_selected())
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

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
