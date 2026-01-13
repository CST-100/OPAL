"""Parts screen - view and manage parts."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Input, Label, Static

from opal.tui.api_client import get_client


class PartDetail(Static):
    """Part detail panel."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.part_data: dict | None = None

    def compose(self) -> ComposeResult:
        yield Label("Part Details", classes="section-title")
        yield Container(id="part-detail-content")

    def show_part(self, part: dict) -> None:
        """Display part details."""
        self.part_data = part
        content = self.query_one("#part-detail-content", Container)
        content.remove_children()

        content.mount(Label(f"ID: {part.get('id', '-')}", classes="detail-row"))
        content.mount(Label(f"Name: {part.get('name', '-')}", classes="detail-row"))
        content.mount(Label(f"Number: {part.get('part_number', '-')}", classes="detail-row"))
        content.mount(Label(f"Category: {part.get('category', '-')}", classes="detail-row"))
        content.mount(Label(f"Description: {part.get('description', '-')}", classes="detail-row"))
        content.mount(Label(f"Unit: {part.get('unit_of_measure', '-')}", classes="detail-row"))
        content.mount(Label(f"Min Stock: {part.get('minimum_stock', 0)}", classes="detail-row"))

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
        table.add_columns("ID", "Part Number", "Name", "Category", "Unit")
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
        self.notify("Part creation not yet implemented in TUI")

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
