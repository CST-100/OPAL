"""Suppliers screen - view and manage suppliers."""

from typing import Any

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Input, Label, Static, TextArea

from opal.tui.api_client import get_client
from opal.tui.widgets.form import FormGroup, FormModal


class SupplierFormModal(FormModal):
    """Modal form for creating/editing a supplier."""

    def __init__(self, supplier: dict[str, Any] | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.supplier = supplier

    @property
    def form_title(self) -> str:
        return "Edit Supplier" if self.supplier else "New Supplier"

    def build_form(self) -> ComposeResult:
        name = self.supplier.get("name", "") if self.supplier else ""
        contact = self.supplier.get("contact_name", "") if self.supplier else ""
        email = self.supplier.get("email", "") if self.supplier else ""
        phone = self.supplier.get("phone", "") if self.supplier else ""
        notes = self.supplier.get("notes", "") if self.supplier else ""

        yield FormGroup(
            "Name",
            Input(value=name, id="field-name", placeholder="Supplier name"),
            required=True,
        )
        yield FormGroup(
            "Contact Name",
            Input(value=contact, id="field-contact", placeholder="Contact person"),
        )
        yield FormGroup(
            "Email",
            Input(value=email, id="field-email", placeholder="email@example.com"),
        )
        yield FormGroup(
            "Phone",
            Input(value=phone, id="field-phone", placeholder="Phone number"),
        )
        yield FormGroup(
            "Notes",
            TextArea(text=notes, id="field-notes"),
        )

    def get_form_data(self) -> dict[str, Any] | None:
        name = self.query_one("#field-name", Input).value.strip()
        if not name:
            self.show_error("Name is required")
            return None

        data: dict[str, Any] = {"name": name}
        contact = self.query_one("#field-contact", Input).value.strip()
        if contact:
            data["contact_name"] = contact
        email = self.query_one("#field-email", Input).value.strip()
        if email:
            data["email"] = email
        phone = self.query_one("#field-phone", Input).value.strip()
        if phone:
            data["phone"] = phone
        notes = self.query_one("#field-notes", TextArea).text.strip()
        if notes:
            data["notes"] = notes
        return data


class SupplierDetail(Static):
    """Supplier detail panel."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.supplier_data: dict[str, Any] | None = None

    def compose(self) -> ComposeResult:
        yield Label("Supplier Details", classes="section-title")
        yield Container(id="supplier-detail-content")

    def show_supplier(self, supplier: dict[str, Any]) -> None:
        self.supplier_data = supplier
        content = self.query_one("#supplier-detail-content", Container)
        content.remove_children()

        content.mount(Label(f"ID: {supplier.get('id', '-')}", classes="detail-row"))
        content.mount(Label(f"Name: {supplier.get('name', '-')}", classes="detail-row"))
        if supplier.get("contact_name"):
            content.mount(
                Label(f"Contact: {supplier['contact_name']}", classes="detail-row")
            )
        if supplier.get("email"):
            content.mount(Label(f"Email: {supplier['email']}", classes="detail-row"))
        if supplier.get("phone"):
            content.mount(Label(f"Phone: {supplier['phone']}", classes="detail-row"))

        active = "Yes" if supplier.get("is_active", True) else "No"
        content.mount(Label(f"Active: {active}", classes="detail-row"))

        if supplier.get("notes"):
            content.mount(Label("Notes:", classes="detail-label"))
            content.mount(Label(supplier["notes"][:200], classes="detail-text"))

    def clear(self) -> None:
        self.supplier_data = None
        content = self.query_one("#supplier-detail-content", Container)
        content.remove_children()
        content.mount(Label("Select a supplier to view details", classes="hint"))


class SuppliersScreen(Screen):
    """Suppliers list screen."""

    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("n", "new_supplier", "New"),
        ("ctrl+e", "edit_supplier", "Edit"),
        ("escape", "go_back", "Back"),
    ]

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Suppliers", classes="screen-title"),
            Horizontal(
                Vertical(
                    DataTable(id="suppliers-table"),
                    classes="table-container",
                ),
                SupplierDetail(id="supplier-detail"),
                classes="main-content",
            ),
            classes="screen-container",
        )

    async def on_mount(self) -> None:
        table = self.query_one("#suppliers-table", DataTable)
        table.add_columns("ID", "Name", "Contact", "Email", "Active")
        table.cursor_type = "row"
        await self.load_suppliers()

    async def action_refresh(self) -> None:
        await self.load_suppliers()
        self.notify("Suppliers refreshed")

    def action_go_back(self) -> None:
        self.app.switch_screen("dashboard")

    async def action_new_supplier(self) -> None:
        self.app.push_screen(SupplierFormModal(), callback=self._on_created)

    def _on_created(self, data: dict[str, Any] | None) -> None:
        if data is None:
            return
        client = get_client(self.app.api_url)
        try:
            s = client.create_supplier(data)
            self.notify(f"Created supplier: {s.get('name', '')}")
            self.run_worker(self.load_suppliers())
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    async def action_edit_supplier(self) -> None:
        detail = self.query_one("#supplier-detail", SupplierDetail)
        if not detail.supplier_data:
            self.notify("Select a supplier first", severity="warning")
            return
        self.app.push_screen(
            SupplierFormModal(supplier=detail.supplier_data),
            callback=self._on_edited,
        )

    def _on_edited(self, data: dict[str, Any] | None) -> None:
        if data is None:
            return
        detail = self.query_one("#supplier-detail", SupplierDetail)
        if not detail.supplier_data:
            return
        client = get_client(self.app.api_url)
        try:
            client.update_supplier(detail.supplier_data["id"], data)
            self.notify("Supplier updated")
            self.run_worker(self.load_suppliers())
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    async def load_suppliers(self) -> None:
        client = get_client(self.app.api_url)
        table = self.query_one("#suppliers-table", DataTable)
        detail = self.query_one("#supplier-detail", SupplierDetail)

        try:
            result = client.list_suppliers(page_size=100)
            items = result.get("items", [])

            table.clear()
            for s in items:
                active = "Yes" if s.get("is_active", True) else "No"
                table.add_row(
                    str(s.get("id", "")),
                    s.get("name", "")[:25],
                    s.get("contact_name", "-")[:20],
                    s.get("email", "-")[:25],
                    active,
                    key=str(s.get("id")),
                )
            detail.clear()
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        client = get_client(self.app.api_url)
        detail = self.query_one("#supplier-detail", SupplierDetail)
        try:
            sid = int(event.row_key.value)
            supplier = client.get_supplier(sid)
            detail.show_supplier(supplier)
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")
