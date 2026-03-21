"""Parts screen - view and manage parts."""

from typing import Any

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Input, Label, Select, Static, TextArea

from opal.tui.api_client import get_client
from opal.tui.widgets.form import ConfirmModal, FormGroup, FormModal


class PartFormModal(FormModal):
    """Modal form for creating/editing a part."""

    def __init__(
        self,
        part: dict[str, Any] | None = None,
        categories: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.part = part
        self.categories = categories or []

    @property
    def form_title(self) -> str:
        return "Edit Part" if self.part else "New Part"

    def build_form(self) -> ComposeResult:
        name_val = self.part.get("name", "") if self.part else ""
        desc_val = self.part.get("description", "") if self.part else ""
        min_stock = str(self.part.get("minimum_stock", 0)) if self.part else "0"

        yield FormGroup(
            "Name",
            Input(value=name_val, id="field-name", placeholder="Part name"),
            required=True,
        )

        cat_options = [(c, c) for c in self.categories] if self.categories else []
        current_cat = self.part.get("category") if self.part else None
        yield FormGroup(
            "Category",
            Select(
                cat_options,
                id="field-category",
                prompt="Select category...",
                value=current_cat if current_cat in [c[1] for c in cat_options] else Select.BLANK,
            ),
            required=True,
        )

        unit_options = [
            ("Each", "each"),
            ("Meters", "m"),
            ("Kilograms", "kg"),
            ("Liters", "L"),
            ("Feet", "ft"),
            ("Inches", "in"),
        ]
        current_unit = self.part.get("unit_of_measure", "each") if self.part else "each"
        yield FormGroup(
            "Unit of Measure",
            Select(unit_options, id="field-unit", value=current_unit),
        )

        tier_options = [
            ("Tier 1 - Flight/Critical", "1"),
            ("Tier 2 - Prototype", "2"),
            ("Tier 3 - Development", "3"),
            ("Tier 4 - COTS/Consumable", "4"),
        ]
        current_tier = str(self.part.get("tier", "3")) if self.part else "3"
        yield FormGroup(
            "Tier",
            Select(tier_options, id="field-tier", value=current_tier),
        )

        tracking_options = [
            ("None", "none"),
            ("Lot", "lot"),
            ("Serial", "serial"),
        ]
        current_tracking = self.part.get("tracking_type", "none") if self.part else "none"
        yield FormGroup(
            "Tracking",
            Select(tracking_options, id="field-tracking", value=current_tracking),
        )

        yield FormGroup(
            "Minimum Stock",
            Input(value=min_stock, id="field-min-stock", placeholder="0"),
        )

        yield FormGroup(
            "Description",
            TextArea(text=desc_val, id="field-description"),
        )

    def get_form_data(self) -> dict[str, Any] | None:
        name = self.query_one("#field-name", Input).value.strip()
        if not name:
            self.show_error("Name is required")
            return None

        category = self.query_one("#field-category", Select).value
        if category == Select.BLANK:
            self.show_error("Category is required")
            return None

        unit = self.query_one("#field-unit", Select).value
        tier = self.query_one("#field-tier", Select).value
        tracking = self.query_one("#field-tracking", Select).value
        description = self.query_one("#field-description", TextArea).text.strip()
        min_stock_str = self.query_one("#field-min-stock", Input).value.strip()

        try:
            min_stock = int(min_stock_str) if min_stock_str else 0
        except ValueError:
            self.show_error("Minimum stock must be a number")
            return None

        data: dict[str, Any] = {
            "name": name,
            "category": category,
            "unit_of_measure": unit if unit != Select.BLANK else "each",
            "tier": int(tier) if tier != Select.BLANK else 3,
            "tracking_type": tracking if tracking != Select.BLANK else "none",
            "description": description,
            "minimum_stock": min_stock,
        }
        return data


class PartDetail(Static):
    """Part detail panel."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.part_data: dict[str, Any] | None = None

    def compose(self) -> ComposeResult:
        yield Label("Part Details", classes="section-title")
        yield Container(id="part-detail-content")

    def show_part(self, part: dict[str, Any]) -> None:
        """Display part details."""
        self.part_data = part
        content = self.query_one("#part-detail-content", Container)
        content.remove_children()

        content.mount(Label(f"ID: {part.get('id', '-')}", classes="detail-row"))
        content.mount(Label(f"Name: {part.get('name', '-')}", classes="detail-row"))
        content.mount(Label(f"Number: {part.get('part_number', '-')}", classes="detail-row"))
        content.mount(Label(f"Category: {part.get('category', '-')}", classes="detail-row"))
        content.mount(Label(f"Tier: {part.get('tier', '-')}", classes="detail-row"))
        content.mount(Label(f"Tracking: {part.get('tracking_type', 'none')}", classes="detail-row"))
        content.mount(Label(f"Description: {part.get('description', '-')}", classes="detail-row"))
        content.mount(Label(f"Unit: {part.get('unit_of_measure', '-')}", classes="detail-row"))
        content.mount(Label(f"Min Stock: {part.get('minimum_stock', 0)}", classes="detail-row"))

        # BOM section for assemblies
        bom_lines = part.get("bom_lines", [])
        if bom_lines:
            content.mount(Label("BOM:", classes="detail-label"))
            for line in bom_lines:
                comp_name = line.get("component_name", line.get("component_part_number", "?"))
                qty = line.get("quantity", 0)
                content.mount(Label(f"  {comp_name} x{qty}", classes="detail-row"))

    def clear(self) -> None:
        """Clear the detail panel."""
        self.part_data = None
        content = self.query_one("#part-detail-content", Container)
        content.remove_children()
        content.mount(Label("Select a part to view details", classes="hint"))


class PartsScreen(Screen):
    """Parts list screen."""

    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("n", "new_part", "New Part"),
        ("ctrl+e", "edit_part", "Edit"),
        ("ctrl+d", "delete_part", "Delete"),
        ("escape", "go_back", "Back"),
        ("/", "focus_search", "Search"),
    ]

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Parts", classes="screen-title"),
            Horizontal(
                Input(placeholder="Search parts...", id="search-input"),
                classes="search-bar",
            ),
            Horizontal(
                Vertical(
                    DataTable(id="parts-table"),
                    classes="table-container",
                ),
                PartDetail(id="part-detail"),
                classes="main-content",
            ),
            classes="screen-container",
        )

    async def on_mount(self) -> None:
        """Initialize the parts table."""
        table = self.query_one("#parts-table", DataTable)
        table.add_columns("ID", "Part Number", "Name", "Category", "Tier", "Unit")
        table.cursor_type = "row"
        await self.load_parts()

    async def action_refresh(self) -> None:
        """Refresh parts list."""
        await self.load_parts()
        self.notify("Parts refreshed")

    async def action_focus_search(self) -> None:
        """Focus the search input."""
        search = self.query_one("#search-input", Input)
        search.focus()

    def action_go_back(self) -> None:
        """Go back to dashboard."""
        self.app.switch_screen("dashboard")

    async def action_new_part(self) -> None:
        """Show new part dialog."""
        client = get_client(self.app.api_url)
        try:
            categories = client.list_categories()
        except Exception:
            categories = []
        self.app.push_screen(PartFormModal(categories=categories), callback=self._on_part_created)

    def _on_part_created(self, data: dict[str, Any] | None) -> None:
        """Handle part creation result."""
        if data is None:
            return
        client = get_client(self.app.api_url)
        try:
            part = client.create_part(data)
            self.notify(f"Created part: {part.get('name', '')}")
            self.run_worker(self.load_parts())
        except Exception as e:
            self.notify(f"Error creating part: {e}", severity="error")

    async def action_edit_part(self) -> None:
        """Edit the selected part."""
        detail = self.query_one("#part-detail", PartDetail)
        if not detail.part_data:
            self.notify("Select a part first", severity="warning")
            return

        client = get_client(self.app.api_url)
        try:
            categories = client.list_categories()
        except Exception:
            categories = []

        self.app.push_screen(
            PartFormModal(part=detail.part_data, categories=categories),
            callback=self._on_part_edited,
        )

    def _on_part_edited(self, data: dict[str, Any] | None) -> None:
        """Handle part edit result."""
        if data is None:
            return
        detail = self.query_one("#part-detail", PartDetail)
        if not detail.part_data:
            return
        client = get_client(self.app.api_url)
        try:
            client.update_part(detail.part_data["id"], data)
            self.notify("Part updated")
            self.run_worker(self.load_parts())
        except Exception as e:
            self.notify(f"Error updating part: {e}", severity="error")

    async def action_delete_part(self) -> None:
        """Delete the selected part."""
        detail = self.query_one("#part-detail", PartDetail)
        if not detail.part_data:
            self.notify("Select a part first", severity="warning")
            return

        name = detail.part_data.get("name", "")
        self.app.push_screen(
            ConfirmModal(title="Delete Part", message=f"Delete '{name}'?"),
            callback=self._on_delete_confirmed,
        )

    def _on_delete_confirmed(self, confirmed: bool) -> None:
        """Handle delete confirmation."""
        if not confirmed:
            return
        detail = self.query_one("#part-detail", PartDetail)
        if not detail.part_data:
            return
        client = get_client(self.app.api_url)
        try:
            client.delete_part(detail.part_data["id"])
            self.notify("Part deleted")
            detail.clear()
            self.run_worker(self.load_parts())
        except Exception as e:
            self.notify(f"Error deleting part: {e}", severity="error")

    async def load_parts(self, search: str | None = None) -> None:
        """Load parts from API."""
        client = get_client(self.app.api_url)
        table = self.query_one("#parts-table", DataTable)
        detail = self.query_one("#part-detail", PartDetail)

        try:
            result = client.list_parts(search=search, page_size=100)
            parts = result.get("items", [])

            table.clear()
            for part in parts:
                table.add_row(
                    str(part.get("id", "")),
                    part.get("part_number", ""),
                    part.get("name", ""),
                    part.get("category", ""),
                    str(part.get("tier", "")),
                    part.get("unit_of_measure", ""),
                    key=str(part.get("id")),
                )

            detail.clear()

        except Exception as e:
            self.notify(f"Error loading parts: {e}", severity="error")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle search submission."""
        if event.input.id == "search-input":
            search = event.value.strip() or None
            await self.load_parts(search=search)

    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection."""
        client = get_client(self.app.api_url)
        detail = self.query_one("#part-detail", PartDetail)

        try:
            part_id = int(event.row_key.value)
            part = client.get_part(part_id)
            detail.show_part(part)
        except Exception as e:
            self.notify(f"Error loading part: {e}", severity="error")
