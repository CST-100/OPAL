"""Inventory screen - view and manage inventory records."""

from typing import Any

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, DataTable, Input, Label, Select, Static, TextArea

from opal.tui.api_client import get_client
from opal.tui.widgets.form import FormGroup, FormModal


class InventoryFormModal(FormModal):
    """Modal form for creating an inventory record."""

    form_title = "Add Inventory"

    def build_form(self) -> ComposeResult:
        yield FormGroup(
            "Part ID",
            Input(id="field-part-id", placeholder="Part ID"),
            required=True,
        )
        yield FormGroup(
            "Quantity",
            Input(id="field-quantity", placeholder="1", value="1"),
            required=True,
        )
        yield FormGroup(
            "Location",
            Input(id="field-location", placeholder="e.g., Shelf A-1"),
        )
        yield FormGroup(
            "Lot Number",
            Input(id="field-lot", placeholder="Optional"),
        )

    def get_form_data(self) -> dict[str, Any] | None:
        part_id_str = self.query_one("#field-part-id", Input).value.strip()
        if not part_id_str:
            self.show_error("Part ID is required")
            return None
        try:
            part_id = int(part_id_str)
        except ValueError:
            self.show_error("Part ID must be a number")
            return None

        qty_str = self.query_one("#field-quantity", Input).value.strip()
        try:
            quantity = float(qty_str) if qty_str else 1
        except ValueError:
            self.show_error("Quantity must be a number")
            return None

        location = self.query_one("#field-location", Input).value.strip()
        lot = self.query_one("#field-lot", Input).value.strip()

        data: dict[str, Any] = {
            "part_id": part_id,
            "quantity": quantity,
        }
        if location:
            data["location"] = location
        if lot:
            data["lot_number"] = lot
        return data


class AdjustModal(FormModal):
    """Modal for adjusting inventory quantity."""

    form_title = "Adjust Inventory"

    def __init__(self, inventory: dict[str, Any], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.inventory = inventory

    def build_form(self) -> ComposeResult:
        current_qty = self.inventory.get("quantity", 0)
        yield FormGroup(
            "Current Quantity",
            Input(value=str(current_qty), id="field-current", disabled=True),
        )
        yield FormGroup(
            "New Quantity",
            Input(id="field-new-qty", placeholder="New quantity"),
            required=True,
        )
        reason_options = [
            ("Cycle Count", "cycle_count"),
            ("Damage", "damage"),
            ("Scrap", "scrap"),
            ("Found", "found"),
            ("Correction", "correction"),
        ]
        yield FormGroup(
            "Reason",
            Select(reason_options, id="field-reason", prompt="Select reason..."),
            required=True,
        )
        yield FormGroup(
            "Notes",
            TextArea(id="field-notes"),
        )

    def get_form_data(self) -> dict[str, Any] | None:
        qty_str = self.query_one("#field-new-qty", Input).value.strip()
        if not qty_str:
            self.show_error("New quantity is required")
            return None
        try:
            new_qty = float(qty_str)
        except ValueError:
            self.show_error("Quantity must be a number")
            return None

        reason = self.query_one("#field-reason", Select).value
        if reason == Select.BLANK:
            self.show_error("Reason is required")
            return None

        notes = self.query_one("#field-notes", TextArea).text.strip()

        return {
            "new_quantity": new_qty,
            "reason": reason,
            "notes": notes,
        }


class TransferModal(FormModal):
    """Modal for transferring inventory to a new location."""

    form_title = "Transfer Inventory"

    def __init__(self, inventory: dict[str, Any], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.inventory = inventory

    def build_form(self) -> ComposeResult:
        current_loc = self.inventory.get("location", "Unassigned")
        yield FormGroup(
            "From Location",
            Input(value=current_loc, id="field-from", disabled=True),
        )
        yield FormGroup(
            "To Location",
            Input(id="field-to", placeholder="New location"),
            required=True,
        )
        yield FormGroup(
            "Quantity",
            Input(
                id="field-qty",
                placeholder="Leave blank for all",
                value=str(self.inventory.get("quantity", 0)),
            ),
        )

    def get_form_data(self) -> dict[str, Any] | None:
        to_location = self.query_one("#field-to", Input).value.strip()
        if not to_location:
            self.show_error("Destination location is required")
            return None

        qty_str = self.query_one("#field-qty", Input).value.strip()
        quantity = None
        if qty_str:
            try:
                quantity = float(qty_str)
            except ValueError:
                self.show_error("Quantity must be a number")
                return None

        data: dict[str, Any] = {
            "inventory_id": self.inventory["id"],
            "to_location": to_location,
        }
        if quantity is not None:
            data["quantity"] = quantity
        return data


class OpalLookupModal(FormModal):
    """Modal for looking up inventory by OPAL number."""

    form_title = "OPAL Lookup"

    def build_form(self) -> ComposeResult:
        yield FormGroup(
            "OPAL Number",
            Input(id="field-opal", placeholder="e.g., OPAL-0001"),
            required=True,
        )

    def get_form_data(self) -> dict[str, Any] | None:
        opal = self.query_one("#field-opal", Input).value.strip()
        if not opal:
            self.show_error("OPAL number is required")
            return None
        return {"opal_number": opal}


class InventoryDetail(Static):
    """Inventory detail panel."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.inventory_data: dict[str, Any] | None = None

    def compose(self) -> ComposeResult:
        yield Label("Inventory Details", classes="section-title")
        yield Container(id="inv-detail-content")
        yield Label("History", classes="section-title")
        yield VerticalScroll(id="inv-history")

    def show_inventory(self, inv: dict[str, Any]) -> None:
        """Display inventory details."""
        self.inventory_data = inv
        content = self.query_one("#inv-detail-content", Container)
        content.remove_children()

        content.mount(Label(f"ID: {inv.get('id', '-')}", classes="detail-row"))

        opal_num = inv.get("opal_number", "-")
        content.mount(Label(f"OPAL#: {opal_num}", classes="detail-row"))

        part_name = inv.get("part_name", inv.get("part_number", f"Part #{inv.get('part_id', '?')}"))
        content.mount(Label(f"Part: {part_name}", classes="detail-row"))

        content.mount(Label(f"Quantity: {inv.get('quantity', 0)}", classes="detail-row"))

        location = inv.get("location", "Unassigned")
        content.mount(Label(f"Location: {location}", classes="detail-row"))

        status = inv.get("status", "available")
        content.mount(
            Label(f"Status: {status}", classes=f"detail-row status-{status}")
        )

        if inv.get("lot_number"):
            content.mount(Label(f"Lot#: {inv['lot_number']}", classes="detail-row"))

        if inv.get("serial_number"):
            content.mount(Label(f"Serial#: {inv['serial_number']}", classes="detail-row"))

        if inv.get("expiration_date"):
            content.mount(
                Label(f"Expires: {inv['expiration_date'][:10]}", classes="detail-row")
            )

        # Calibration info
        if inv.get("calibration_due_date"):
            content.mount(
                Label(
                    f"Cal Due: {inv['calibration_due_date'][:10]}", classes="detail-row"
                )
            )

        created = inv.get("created_at", "")[:16] if inv.get("created_at") else "-"
        content.mount(Label(f"Created: {created}", classes="detail-row"))

    def show_history(self, history: list[dict[str, Any]]) -> None:
        """Display OPAL history."""
        container = self.query_one("#inv-history", VerticalScroll)
        container.remove_children()

        if not history:
            container.mount(Label("No history available", classes="hint"))
            return

        for entry in history[:20]:
            action = entry.get("action", entry.get("event_type", "?"))
            ts = entry.get("created_at", entry.get("timestamp", ""))[:16]
            details = entry.get("details", entry.get("description", ""))
            container.mount(
                Label(f"[{ts}] {action}: {details}", classes="detail-row")
            )

    def clear(self) -> None:
        """Clear the detail panel."""
        self.inventory_data = None
        content = self.query_one("#inv-detail-content", Container)
        content.remove_children()
        content.mount(Label("Select an item to view details", classes="hint"))

        history = self.query_one("#inv-history", VerticalScroll)
        history.remove_children()


class InventoryScreen(Screen):
    """Inventory list screen."""

    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("n", "new_inventory", "New"),
        ("a", "adjust", "Adjust"),
        ("t", "transfer", "Transfer"),
        ("l", "lookup", "Lookup"),
        ("escape", "go_back", "Back"),
        ("/", "focus_search", "Search"),
    ]

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Inventory", classes="screen-title"),
            Horizontal(
                Input(placeholder="Search by OPAL# or part...", id="search-input"),
                classes="search-bar",
            ),
            Horizontal(
                Button("All", id="filter-all", variant="primary"),
                Button("Available", id="filter-available"),
                Button("Consumed", id="filter-consumed"),
                Button("Quarantined", id="filter-quarantined"),
                classes="filter-bar",
            ),
            Horizontal(
                Vertical(
                    DataTable(id="inventory-table"),
                    classes="table-container",
                ),
                InventoryDetail(id="inventory-detail"),
                classes="main-content",
            ),
            classes="screen-container",
        )

    async def on_mount(self) -> None:
        """Initialize the inventory table."""
        table = self.query_one("#inventory-table", DataTable)
        table.add_columns("ID", "OPAL#", "Part", "Qty", "Location", "Status")
        table.cursor_type = "row"
        await self.load_inventory()

    async def action_refresh(self) -> None:
        """Refresh inventory list."""
        await self.load_inventory()
        self.notify("Inventory refreshed")

    async def action_focus_search(self) -> None:
        """Focus the search input."""
        self.query_one("#search-input", Input).focus()

    def action_go_back(self) -> None:
        """Go back to dashboard."""
        self.app.switch_screen("dashboard")

    async def action_new_inventory(self) -> None:
        """Show new inventory dialog."""
        self.app.push_screen(InventoryFormModal(), callback=self._on_inventory_created)

    def _on_inventory_created(self, data: dict[str, Any] | None) -> None:
        """Handle inventory creation result."""
        if data is None:
            return
        client = get_client(self.app.api_url)
        try:
            inv = client.add_inventory(data)
            self.notify(f"Created inventory #{inv.get('id', '')}")
            self.run_worker(self.load_inventory())
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    async def action_adjust(self) -> None:
        """Adjust selected inventory."""
        detail = self.query_one("#inventory-detail", InventoryDetail)
        if not detail.inventory_data:
            self.notify("Select an item first", severity="warning")
            return
        self.app.push_screen(
            AdjustModal(inventory=detail.inventory_data),
            callback=self._on_adjusted,
        )

    def _on_adjusted(self, data: dict[str, Any] | None) -> None:
        """Handle adjustment result."""
        if data is None:
            return
        detail = self.query_one("#inventory-detail", InventoryDetail)
        if not detail.inventory_data:
            return
        client = get_client(self.app.api_url)
        try:
            client.adjust_inventory(detail.inventory_data["id"], data)
            self.notify("Inventory adjusted")
            self.run_worker(self.load_inventory())
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    async def action_transfer(self) -> None:
        """Transfer selected inventory."""
        detail = self.query_one("#inventory-detail", InventoryDetail)
        if not detail.inventory_data:
            self.notify("Select an item first", severity="warning")
            return
        self.app.push_screen(
            TransferModal(inventory=detail.inventory_data),
            callback=self._on_transferred,
        )

    def _on_transferred(self, data: dict[str, Any] | None) -> None:
        """Handle transfer result."""
        if data is None:
            return
        client = get_client(self.app.api_url)
        try:
            client.transfer_stock(data)
            self.notify("Transfer complete")
            self.run_worker(self.load_inventory())
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    async def action_lookup(self) -> None:
        """OPAL number lookup."""
        self.app.push_screen(OpalLookupModal(), callback=self._on_lookup)

    def _on_lookup(self, data: dict[str, Any] | None) -> None:
        """Handle OPAL lookup result."""
        if data is None:
            return
        client = get_client(self.app.api_url)
        detail = self.query_one("#inventory-detail", InventoryDetail)
        try:
            inv = client.get_opal_by_number(data["opal_number"])
            detail.show_inventory(inv)
            # Try to load history
            try:
                history = client.get_opal_history(data["opal_number"])
                items = history if isinstance(history, list) else history.get("events", [])
                detail.show_history(items)
            except Exception:
                pass
            self.notify(f"Found {data['opal_number']}")
        except Exception as e:
            self.notify(f"Not found: {e}", severity="error")

    async def load_inventory(
        self,
        location: str | None = None,
        status: str | None = None,
    ) -> None:
        """Load inventory from API."""
        client = get_client(self.app.api_url)
        table = self.query_one("#inventory-table", DataTable)
        detail = self.query_one("#inventory-detail", InventoryDetail)

        try:
            result = client.list_inventory(location=location, page_size=100)
            items = result.get("items", [])

            table.clear()
            for inv in items:
                part_name = inv.get(
                    "part_name", inv.get("part_number", f"#{inv.get('part_id', '?')}")
                )
                table.add_row(
                    str(inv.get("id", "")),
                    inv.get("opal_number", "-"),
                    str(part_name)[:20],
                    str(inv.get("quantity", 0)),
                    inv.get("location", "-")[:15],
                    inv.get("status", "available"),
                    key=str(inv.get("id")),
                )

            detail.clear()

        except Exception as e:
            self.notify(f"Error loading inventory: {e}", severity="error")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle filter button clicks."""
        button_id = event.button.id or ""

        if button_id.startswith("filter-"):
            status = button_id.replace("filter-", "")
            if status == "all":
                await self.load_inventory()
            else:
                await self.load_inventory(status=status)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle search."""
        if event.input.id == "search-input":
            query = event.value.strip()
            if not query:
                await self.load_inventory()
                return
            # Try OPAL lookup first
            client = get_client(self.app.api_url)
            detail = self.query_one("#inventory-detail", InventoryDetail)
            try:
                inv = client.get_opal_by_number(query)
                detail.show_inventory(inv)
                self.notify(f"Found {query}")
            except Exception:
                # Fall back to regular listing
                await self.load_inventory()

    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection."""
        client = get_client(self.app.api_url)
        detail = self.query_one("#inventory-detail", InventoryDetail)

        try:
            inv_id = int(event.row_key.value)
            inv = client.get_inventory(inv_id)
            detail.show_inventory(inv)
        except Exception as e:
            self.notify(f"Error loading inventory: {e}", severity="error")
