"""Purchases screen - view and manage purchase orders."""

from typing import Any

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, DataTable, Input, Label, Select, Static, TextArea

from opal.tui.api_client import get_client
from opal.tui.widgets.form import FormGroup, FormModal


class PurchaseFormModal(FormModal):
    """Modal form for creating a purchase order."""

    form_title = "New Purchase Order"

    def __init__(self, suppliers: list[dict[str, Any]] | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.suppliers = suppliers or []

    def build_form(self) -> ComposeResult:
        if self.suppliers:
            supplier_options = [
                (s.get("name", f"#{s['id']}"), s["id"]) for s in self.suppliers
            ]
            yield FormGroup(
                "Supplier",
                Select(supplier_options, id="field-supplier", prompt="Select supplier..."),
                required=True,
            )
        else:
            yield FormGroup(
                "Supplier ID",
                Input(id="field-supplier-id", placeholder="Supplier ID"),
                required=True,
            )
        yield FormGroup(
            "Reference",
            Input(id="field-reference", placeholder="PO reference number"),
        )
        yield FormGroup(
            "Notes",
            TextArea(id="field-notes"),
        )

    def get_form_data(self) -> dict[str, Any] | None:
        if self.suppliers:
            supplier = self.query_one("#field-supplier", Select).value
            if supplier == Select.BLANK:
                self.show_error("Supplier is required")
                return None
            supplier_id = supplier
        else:
            sid = self.query_one("#field-supplier-id", Input).value.strip()
            if not sid:
                self.show_error("Supplier ID is required")
                return None
            try:
                supplier_id = int(sid)
            except ValueError:
                self.show_error("Supplier ID must be a number")
                return None

        reference = self.query_one("#field-reference", Input).value.strip()
        notes = self.query_one("#field-notes", TextArea).text.strip()

        data: dict[str, Any] = {"supplier_id": supplier_id}
        if reference:
            data["reference"] = reference
        if notes:
            data["notes"] = notes
        return data


class AddLineModal(FormModal):
    """Modal for adding a line item to a PO."""

    form_title = "Add PO Line"

    def build_form(self) -> ComposeResult:
        yield FormGroup(
            "Part ID",
            Input(id="field-part-id", placeholder="Part ID"),
            required=True,
        )
        yield FormGroup(
            "Quantity",
            Input(id="field-quantity", placeholder="Quantity", value="1"),
            required=True,
        )
        yield FormGroup(
            "Unit Cost",
            Input(id="field-cost", placeholder="0.00"),
        )

    def get_form_data(self) -> dict[str, Any] | None:
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

        cost_str = self.query_one("#field-cost", Input).value.strip()
        data: dict[str, Any] = {"part_id": part_id, "quantity": quantity}
        if cost_str:
            try:
                data["unit_cost"] = float(cost_str)
            except ValueError:
                self.show_error("Cost must be a number")
                return None
        return data


class PurchaseDetail(Static):
    """Purchase order detail panel."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.purchase_data: dict[str, Any] | None = None

    def compose(self) -> ComposeResult:
        yield Label("PO Details", classes="section-title")
        yield Container(id="po-detail-content")
        yield Label("Line Items", classes="section-title")
        yield VerticalScroll(id="po-lines")

    def show_purchase(self, po: dict[str, Any]) -> None:
        """Display PO details."""
        self.purchase_data = po
        content = self.query_one("#po-detail-content", Container)
        content.remove_children()

        content.mount(Label(f"ID: {po.get('id', '-')}", classes="detail-row"))
        if "supplier_name" in po:
            supplier_label = f"Supplier: {po.get('supplier_name', '?')}"
        else:
            sid = po.get("supplier_id", "-")
            supplier_label = f"Supplier ID: {sid}"
        content.mount(Label(supplier_label, classes="detail-row"))

        status = po.get("status", "-")
        content.mount(Label(f"Status: {status}", classes=f"detail-row status-{status}"))

        if po.get("reference"):
            content.mount(Label(f"Ref: {po['reference']}", classes="detail-row"))

        created = po.get("created_at", "")[:16] if po.get("created_at") else "-"
        content.mount(Label(f"Created: {created}", classes="detail-row"))

        # Line items
        lines = po.get("lines", po.get("line_items", []))
        lines_container = self.query_one("#po-lines", VerticalScroll)
        lines_container.remove_children()

        if not lines:
            lines_container.mount(Label("No line items", classes="hint"))
        else:
            for line in lines:
                pid = line.get("part_id", "?")
                part = line.get("part_name", f"Part #{pid}")
                qty = line.get("quantity", 0)
                cost = line.get("unit_cost", "")
                cost_str = f" @ ${cost}" if cost else ""
                lines_container.mount(
                    Label(f"  {part} x{qty}{cost_str}", classes="detail-row")
                )

    def clear(self) -> None:
        """Clear the detail panel."""
        self.purchase_data = None
        content = self.query_one("#po-detail-content", Container)
        content.remove_children()
        content.mount(Label("Select a PO to view details", classes="hint"))

        lines = self.query_one("#po-lines", VerticalScroll)
        lines.remove_children()


class PurchasesScreen(Screen):
    """Purchase orders list screen."""

    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("n", "new_purchase", "New PO"),
        ("a", "add_line", "Add Line"),
        ("ctrl+r", "receive", "Receive"),
        ("escape", "go_back", "Back"),
    ]

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Purchase Orders", classes="screen-title"),
            Horizontal(
                Button("All", id="filter-all", variant="primary"),
                Button("Draft", id="filter-draft"),
                Button("Ordered", id="filter-ordered"),
                Button("Partial", id="filter-partial"),
                Button("Received", id="filter-received"),
                classes="filter-bar",
            ),
            Horizontal(
                Vertical(
                    DataTable(id="purchases-table"),
                    classes="table-container",
                ),
                PurchaseDetail(id="purchase-detail"),
                classes="main-content",
            ),
            classes="screen-container",
        )

    async def on_mount(self) -> None:
        """Initialize the purchases table."""
        table = self.query_one("#purchases-table", DataTable)
        table.add_columns("ID", "Supplier", "Status", "Ref", "Created")
        table.cursor_type = "row"
        await self.load_purchases()

    async def action_refresh(self) -> None:
        await self.load_purchases()
        self.notify("Purchases refreshed")

    def action_go_back(self) -> None:
        self.app.switch_screen("dashboard")

    async def action_new_purchase(self) -> None:
        client = get_client(self.app.api_url)
        try:
            result = client.list_suppliers(page_size=100)
            suppliers = result.get("items", [])
        except Exception:
            suppliers = []
        self.app.push_screen(
            PurchaseFormModal(suppliers=suppliers), callback=self._on_po_created
        )

    def _on_po_created(self, data: dict[str, Any] | None) -> None:
        if data is None:
            return
        client = get_client(self.app.api_url)
        try:
            po = client.create_purchase(data)
            self.notify(f"Created PO #{po.get('id', '')}")
            self.run_worker(self.load_purchases())
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    async def action_add_line(self) -> None:
        detail = self.query_one("#purchase-detail", PurchaseDetail)
        if not detail.purchase_data:
            self.notify("Select a PO first", severity="warning")
            return
        self.app.push_screen(AddLineModal(), callback=self._on_line_added)

    def _on_line_added(self, data: dict[str, Any] | None) -> None:
        if data is None:
            return
        detail = self.query_one("#purchase-detail", PurchaseDetail)
        if not detail.purchase_data:
            return
        client = get_client(self.app.api_url)
        try:
            client.add_purchase_line(detail.purchase_data["id"], data)
            self.notify("Line added")
            po = client.get_purchase(detail.purchase_data["id"])
            detail.show_purchase(po)
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    async def action_receive(self) -> None:
        detail = self.query_one("#purchase-detail", PurchaseDetail)
        if not detail.purchase_data:
            self.notify("Select a PO first", severity="warning")
            return
        client = get_client(self.app.api_url)
        try:
            client.receive_purchase(detail.purchase_data["id"], {})
            self.notify("PO received — inventory created")
            self.run_worker(self.load_purchases())
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    async def load_purchases(self, status: str | None = None) -> None:
        client = get_client(self.app.api_url)
        table = self.query_one("#purchases-table", DataTable)
        detail = self.query_one("#purchase-detail", PurchaseDetail)

        try:
            result = client.list_purchases(status=status, page_size=100)
            items = result.get("items", [])

            table.clear()
            for po in items:
                sid = po.get("supplier_id", "?")
                supplier = po.get("supplier_name", f"#{sid}")
                created = po.get("created_at", "")[:10] if po.get("created_at") else "-"
                table.add_row(
                    str(po.get("id", "")),
                    str(supplier)[:20],
                    po.get("status", ""),
                    po.get("reference", "-")[:15],
                    created,
                    key=str(po.get("id")),
                )
            detail.clear()
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id.startswith("filter-"):
            status = button_id.replace("filter-", "")
            if status == "all":
                status = None
            await self.load_purchases(status=status)

    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        client = get_client(self.app.api_url)
        detail = self.query_one("#purchase-detail", PurchaseDetail)
        try:
            po_id = int(event.row_key.value)
            po = client.get_purchase(po_id)
            detail.show_purchase(po)
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")
