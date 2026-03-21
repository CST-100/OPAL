"""Workcenters screen - view and manage workcenters."""

from typing import Any

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Input, Label, Static, TextArea

from opal.tui.api_client import get_client
from opal.tui.widgets.form import FormGroup, FormModal


class WorkcenterFormModal(FormModal):
    """Modal form for creating/editing a workcenter."""

    def __init__(self, wc: dict[str, Any] | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.wc = wc

    @property
    def form_title(self) -> str:
        return "Edit Workcenter" if self.wc else "New Workcenter"

    def build_form(self) -> ComposeResult:
        name = self.wc.get("name", "") if self.wc else ""
        desc = self.wc.get("description", "") if self.wc else ""
        location = self.wc.get("location", "") if self.wc else ""

        yield FormGroup(
            "Name",
            Input(value=name, id="field-name", placeholder="Workcenter name"),
            required=True,
        )
        yield FormGroup(
            "Location",
            Input(value=location, id="field-location", placeholder="Physical location"),
        )
        yield FormGroup(
            "Description",
            TextArea(text=desc, id="field-description"),
        )

    def get_form_data(self) -> dict[str, Any] | None:
        name = self.query_one("#field-name", Input).value.strip()
        if not name:
            self.show_error("Name is required")
            return None
        data: dict[str, Any] = {"name": name}
        location = self.query_one("#field-location", Input).value.strip()
        if location:
            data["location"] = location
        desc = self.query_one("#field-description", TextArea).text.strip()
        if desc:
            data["description"] = desc
        return data


class WorkcenterDetail(Static):
    """Workcenter detail panel."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.wc_data: dict[str, Any] | None = None

    def compose(self) -> ComposeResult:
        yield Label("Workcenter Details", classes="section-title")
        yield Container(id="wc-detail-content")

    def show_workcenter(self, wc: dict[str, Any]) -> None:
        self.wc_data = wc
        content = self.query_one("#wc-detail-content", Container)
        content.remove_children()

        content.mount(Label(f"ID: {wc.get('id', '-')}", classes="detail-row"))
        content.mount(Label(f"Name: {wc.get('name', '-')}", classes="detail-row"))
        if wc.get("location"):
            content.mount(Label(f"Location: {wc['location']}", classes="detail-row"))
        active = "Yes" if wc.get("is_active", True) else "No"
        content.mount(Label(f"Active: {active}", classes="detail-row"))
        if wc.get("description"):
            content.mount(Label("Description:", classes="detail-label"))
            content.mount(Label(wc["description"][:200], classes="detail-text"))

    def clear(self) -> None:
        self.wc_data = None
        content = self.query_one("#wc-detail-content", Container)
        content.remove_children()
        content.mount(Label("Select a workcenter to view details", classes="hint"))


class WorkcentersScreen(Screen):
    """Workcenters list screen."""

    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("n", "new_wc", "New"),
        ("ctrl+e", "edit_wc", "Edit"),
        ("escape", "go_back", "Back"),
    ]

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Workcenters", classes="screen-title"),
            Horizontal(
                Vertical(
                    DataTable(id="wc-table"),
                    classes="table-container",
                ),
                WorkcenterDetail(id="wc-detail"),
                classes="main-content",
            ),
            classes="screen-container",
        )

    async def on_mount(self) -> None:
        table = self.query_one("#wc-table", DataTable)
        table.add_columns("ID", "Name", "Location", "Active")
        table.cursor_type = "row"
        await self.load_workcenters()

    async def action_refresh(self) -> None:
        await self.load_workcenters()
        self.notify("Workcenters refreshed")

    def action_go_back(self) -> None:
        self.app.switch_screen("dashboard")

    async def action_new_wc(self) -> None:
        self.app.push_screen(WorkcenterFormModal(), callback=self._on_created)

    def _on_created(self, data: dict[str, Any] | None) -> None:
        if data is None:
            return
        client = get_client(self.app.api_url)
        try:
            wc = client.create_workcenter(data)
            self.notify(f"Created workcenter: {wc.get('name', '')}")
            self.run_worker(self.load_workcenters())
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    async def action_edit_wc(self) -> None:
        detail = self.query_one("#wc-detail", WorkcenterDetail)
        if not detail.wc_data:
            self.notify("Select a workcenter first", severity="warning")
            return
        self.app.push_screen(
            WorkcenterFormModal(wc=detail.wc_data), callback=self._on_edited
        )

    def _on_edited(self, data: dict[str, Any] | None) -> None:
        if data is None:
            return
        detail = self.query_one("#wc-detail", WorkcenterDetail)
        if not detail.wc_data:
            return
        client = get_client(self.app.api_url)
        try:
            client.update_workcenter(detail.wc_data["id"], data)
            self.notify("Workcenter updated")
            self.run_worker(self.load_workcenters())
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    async def load_workcenters(self) -> None:
        client = get_client(self.app.api_url)
        table = self.query_one("#wc-table", DataTable)
        detail = self.query_one("#wc-detail", WorkcenterDetail)

        try:
            result = client.list_workcenters()
            items = result.get("items", result) if isinstance(result, dict) else result

            table.clear()
            for wc in items:
                active = "Yes" if wc.get("is_active", True) else "No"
                table.add_row(
                    str(wc.get("id", "")),
                    wc.get("name", "")[:25],
                    wc.get("location", "-")[:20],
                    active,
                    key=str(wc.get("id")),
                )
            detail.clear()
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        client = get_client(self.app.api_url)
        detail = self.query_one("#wc-detail", WorkcenterDetail)
        try:
            wc_id = int(event.row_key.value)
            wc = client.get_workcenter(wc_id)
            detail.show_workcenter(wc)
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")
