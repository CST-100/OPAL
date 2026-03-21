"""Command palette provider for OPAL TUI navigation and actions."""

from functools import partial

from textual.command import Hit, Hits, Provider


class OpalCommands(Provider):
    """Provides screen navigation and common actions for the command palette."""

    SCREEN_COMMANDS: list[tuple[str, str, str]] = [
        ("Dashboard", "dashboard", "View dashboard with stats and recent activity"),
        ("Parts", "parts", "Browse and manage parts catalog"),
        ("Procedures", "procedures", "Browse and manage procedure templates"),
        ("Executions", "executions", "View and run procedure executions"),
        ("Inventory", "inventory", "Manage inventory, stock, and OPAL numbers"),
        ("Issues", "issues", "Track issues, NCRs, and dispositions"),
        ("Risks", "risks", "Risk register and mitigation tracking"),
        ("Purchase Orders", "purchases", "Manage purchase orders and receiving"),
        ("Suppliers", "suppliers", "Manage supplier directory"),
        ("Workcenters", "workcenters", "Manage workcenter definitions"),
        ("Audit Log", "audit", "View recent entity activity log"),
        ("Settings", "settings", "View project config and system info"),
        ("Search", "search", "Search across all entities"),
    ]

    async def search(self, query: str) -> Hits:
        """Search for matching commands."""
        matcher = self.matcher(query)
        for label, screen_name, help_text in self.SCREEN_COMMANDS:
            cmd = f"Go to {label}"
            score = matcher.match(cmd)
            if score > 0:
                yield Hit(
                    score,
                    matcher.highlight(cmd),
                    partial(self._switch_screen, screen_name),
                    help=help_text,
                )

    def _switch_screen(self, screen_name: str) -> None:
        """Switch to the named screen."""
        self.app.switch_screen(screen_name)
