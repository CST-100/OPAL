"""OPAL TUI Application.

A Textual-based terminal user interface for OPAL.
"""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header

from opal.tui.screens.dashboard import DashboardScreen
from opal.tui.screens.executions import ExecutionsScreen
from opal.tui.screens.issues import IssuesScreen
from opal.tui.screens.parts import PartsScreen
from opal.tui.screens.procedures import ProceduresScreen
from opal.tui.screens.risks import RisksScreen


class OpalApp(App):
    """The OPAL Terminal User Interface."""

    TITLE = "OPAL"
    SUB_TITLE = "Operations, Procedures, Assets, Logistics"
    CSS_PATH = "styles.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("d", "switch_screen('dashboard')", "Dashboard"),
        Binding("p", "switch_screen('parts')", "Parts"),
        Binding("r", "switch_screen('procedures')", "Procedures"),
        Binding("e", "switch_screen('executions')", "Executions"),
        Binding("i", "switch_screen('issues')", "Issues"),
        Binding("k", "switch_screen('risks')", "Risks"),
        Binding("?", "toggle_help", "Help"),
    ]

    SCREENS = {
        "dashboard": DashboardScreen,
        "parts": PartsScreen,
        "procedures": ProceduresScreen,
        "executions": ExecutionsScreen,
        "issues": IssuesScreen,
        "risks": RisksScreen,
    }

    def __init__(self, api_url: str = "http://127.0.0.1:8000"):
        super().__init__()
        self.api_url = api_url

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        yield Footer()

    def on_mount(self) -> None:
        """Called when app is mounted."""
        self.push_screen("dashboard")

    def action_switch_screen(self, screen_name: str) -> None:
        """Switch to a named screen."""
        self.switch_screen(screen_name)

    def action_toggle_help(self) -> None:
        """Toggle help overlay."""
        self.notify("Press keys shown in footer to navigate. q to quit.")


def run_tui(api_url: str = "http://127.0.0.1:8000") -> None:
    """Run the OPAL TUI application."""
    app = OpalApp(api_url=api_url)
    app.run()


if __name__ == "__main__":
    run_tui()
