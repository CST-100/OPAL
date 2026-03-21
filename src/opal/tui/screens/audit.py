"""Audit log screen - read-only log viewer."""

from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Label

from opal.tui.api_client import get_client


class AuditScreen(Screen):
    """Audit log viewer — read-only."""

    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("escape", "go_back", "Back"),
    ]

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Audit Log", classes="screen-title"),
            Horizontal(
                Button("All", id="filter-all", variant="primary"),
                Button("Create", id="filter-create"),
                Button("Update", id="filter-update"),
                Button("Delete", id="filter-delete"),
                classes="filter-bar",
            ),
            DataTable(id="audit-table"),
            classes="screen-container",
        )

    async def on_mount(self) -> None:
        table = self.query_one("#audit-table", DataTable)
        table.add_columns("Timestamp", "User", "Action", "Entity", "ID", "Details")
        table.cursor_type = "row"
        await self.load_log()

    async def action_refresh(self) -> None:
        await self.load_log()
        self.notify("Audit log refreshed")

    def action_go_back(self) -> None:
        self.app.switch_screen("dashboard")

    async def load_log(self, action_filter: str | None = None) -> None:
        """Load recent audit entries via parts/issues/executions list endpoints.

        Since there's no dedicated audit log API, we show recent entity activity
        by sampling recent items from each domain.
        """
        table = self.query_one("#audit-table", DataTable)
        table.clear()

        client = get_client(self.app.api_url)
        entries: list[dict[str, Any]] = []

        # Gather recent items from various domains as pseudo-audit entries
        try:
            parts = client.list_parts(page_size=10)
            for p in parts.get("items", []):
                entries.append({
                    "timestamp": p.get("created_at", "")[:16],
                    "user": "-",
                    "action": "create",
                    "entity": "part",
                    "entity_id": str(p.get("id", "")),
                    "details": p.get("name", ""),
                })
        except Exception:
            pass

        try:
            issues = client.list_issues(page_size=10)
            for i in issues.get("items", []):
                entries.append({
                    "timestamp": i.get("created_at", "")[:16],
                    "user": "-",
                    "action": "create",
                    "entity": "issue",
                    "entity_id": str(i.get("id", "")),
                    "details": i.get("title", ""),
                })
        except Exception:
            pass

        try:
            execs = client.list_instances(page_size=10)
            for e in execs.get("items", []):
                entries.append({
                    "timestamp": e.get("created_at", "")[:16],
                    "user": "-",
                    "action": "create",
                    "entity": "execution",
                    "entity_id": str(e.get("id", "")),
                    "details": e.get("procedure_name", ""),
                })
        except Exception:
            pass

        # Sort by timestamp descending
        entries.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        # Filter
        if action_filter:
            entries = [e for e in entries if e["action"] == action_filter]

        for entry in entries[:50]:
            table.add_row(
                entry.get("timestamp", ""),
                entry.get("user", "-"),
                entry.get("action", ""),
                entry.get("entity", ""),
                entry.get("entity_id", ""),
                entry.get("details", "")[:30],
            )

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id.startswith("filter-"):
            action = button_id.replace("filter-", "")
            if action == "all":
                action = None
            await self.load_log(action_filter=action)
