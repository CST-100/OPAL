"""OPAL TUI Application.

A Textual-based terminal user interface for OPAL.
"""

import sys
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header

from opal.tui.api_client import get_client
from opal.tui.commands import OpalCommands
from opal.tui.screens.audit import AuditScreen
from opal.tui.screens.dashboard import DashboardScreen
from opal.tui.screens.executions import ExecutionsScreen
from opal.tui.screens.inventory import InventoryScreen
from opal.tui.screens.issues import IssuesScreen
from opal.tui.screens.parts import PartsScreen
from opal.tui.screens.procedures import ProceduresScreen
from opal.tui.screens.purchases import PurchasesScreen
from opal.tui.screens.risks import RisksScreen
from opal.tui.screens.search import SearchScreen
from opal.tui.screens.settings import SettingsScreen
from opal.tui.screens.suppliers import SuppliersScreen
from opal.tui.screens.workcenters import WorkcentersScreen
from opal.tui.widgets.form import UserPickerModal


class OpalApp(App):
    """The OPAL Terminal User Interface."""

    TITLE = "OPAL"
    SUB_TITLE = "Operations, Procedures, Assets, Logistics"
    CSS_PATH = (
        Path(getattr(sys, "_MEIPASS", ""), "opal", "tui", "styles.tcss")
        if getattr(sys, "frozen", False)
        else "styles.tcss"
    )

    COMMANDS = {OpalCommands}

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("d", "switch_screen('dashboard')", "Dashboard"),
        Binding("p", "switch_screen('parts')", "Parts"),
        Binding("r", "switch_screen('procedures')", "Procedures"),
        Binding("e", "switch_screen('executions')", "Executions"),
        Binding("v", "switch_screen('inventory')", "Inventory"),
        Binding("i", "switch_screen('issues')", "Issues"),
        Binding("k", "switch_screen('risks')", "Risks"),
        Binding("o", "switch_screen('purchases')", "POs"),
        Binding("u", "switch_screen('suppliers')", "Suppliers"),
        Binding("w", "switch_screen('workcenters')", "Workctrs"),
        Binding("a", "switch_screen('audit')", "Audit"),
        Binding("s", "switch_screen('settings')", "Settings"),
        Binding("/", "switch_screen('search')", "Search"),
        Binding("?", "toggle_help", "Help"),
    ]

    SCREENS = {
        "dashboard": DashboardScreen,
        "parts": PartsScreen,
        "procedures": ProceduresScreen,
        "executions": ExecutionsScreen,
        "inventory": InventoryScreen,
        "issues": IssuesScreen,
        "risks": RisksScreen,
        "purchases": PurchasesScreen,
        "suppliers": SuppliersScreen,
        "workcenters": WorkcentersScreen,
        "audit": AuditScreen,
        "settings": SettingsScreen,
        "search": SearchScreen,
    }

    def __init__(self, api_url: str = "http://127.0.0.1:8000"):
        super().__init__()
        self.api_url = api_url

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        yield Footer()

    async def on_mount(self) -> None:
        """Called when app is mounted. Show user picker then dashboard."""
        client = get_client(self.api_url)
        try:
            result = client.list_users()
            users = result.get("items", result) if isinstance(result, dict) else result
            if isinstance(users, list) and len(users) > 1:
                self.push_screen(UserPickerModal(users), callback=self._on_user_selected)
                return
            elif isinstance(users, list) and len(users) == 1:
                client.user_id = users[0]["id"]
        except Exception:
            pass
        self.push_screen("dashboard")

    def _on_user_selected(self, user_id: int | None) -> None:
        """Handle user selection from picker."""
        if user_id is not None:
            client = get_client(self.api_url)
            client.user_id = user_id
        self.push_screen("dashboard")

    def action_switch_screen(self, screen_name: str) -> None:
        """Switch to a named screen."""
        self.switch_screen(screen_name)

    def action_toggle_help(self) -> None:
        """Toggle help overlay."""
        self.notify(
            "Ctrl+\\ = Command palette | d=Dashboard p=Parts r=Procs e=Exec "
            "v=Inv i=Issues k=Risks o=POs u=Suppliers w=WC a=Audit s=Settings /=Search"
        )


def run_tui(api_url: str = "http://127.0.0.1:8000") -> None:
    """Run the OPAL TUI application."""
    app = OpalApp(api_url=api_url)
    app.run()


if __name__ == "__main__":
    run_tui()
