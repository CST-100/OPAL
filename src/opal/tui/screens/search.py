"""Global search screen - search across all entities."""

from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import DataTable, Input, Label

from opal.tui.api_client import get_client


class SearchScreen(Screen):
    """Global search across parts, issues, procedures, inventory."""

    BINDINGS = [
        ("escape", "go_back", "Back"),
    ]

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Search", classes="screen-title"),
            Input(id="search-input", placeholder="Search parts, issues, procedures..."),
            VerticalScroll(id="search-results"),
            classes="screen-container",
        )

    async def on_mount(self) -> None:
        self.query_one("#search-input", Input).focus()

    def action_go_back(self) -> None:
        self.app.switch_screen("dashboard")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        query = event.value.strip()
        if not query:
            return
        await self._do_search(query)

    async def _do_search(self, query: str) -> None:
        results_container = self.query_one("#search-results", VerticalScroll)
        results_container.remove_children()

        client = get_client(self.app.api_url)

        # Try the global search endpoint first
        try:
            result = client.global_search(query)
            await self._show_global_results(results_container, result)
            return
        except Exception:
            pass

        # Fallback: search each domain independently
        total = 0

        # Parts
        try:
            parts = client.list_parts(search=query, page_size=10)
            items = parts.get("items", [])
            if items:
                await results_container.mount(
                    Label(f"Parts ({len(items)})", classes="section-title")
                )
                table = DataTable(id="search-parts")
                await results_container.mount(table)
                table.add_columns("ID", "Name", "Category", "PN")
                for p in items:
                    table.add_row(
                        str(p.get("id", "")),
                        p.get("name", "")[:30],
                        p.get("category", "-"),
                        p.get("part_number", "-"),
                    )
                total += len(items)
        except Exception:
            pass

        # Issues
        try:
            issues = client.list_issues(page_size=20)
            items = [
                i for i in issues.get("items", [])
                if query.lower() in (i.get("title", "") + i.get("description", "")).lower()
            ]
            if items:
                await results_container.mount(
                    Label(f"Issues ({len(items)})", classes="section-title")
                )
                table = DataTable(id="search-issues")
                await results_container.mount(table)
                table.add_columns("ID", "Title", "Type", "Status")
                for i in items[:10]:
                    table.add_row(
                        str(i.get("id", "")),
                        i.get("title", "")[:30],
                        i.get("issue_type", "-"),
                        i.get("status", "-"),
                    )
                total += len(items)
        except Exception:
            pass

        # Procedures
        try:
            procs = client.list_procedures(page_size=20)
            items = [
                p for p in procs.get("items", [])
                if query.lower() in (p.get("name", "") + p.get("description", "")).lower()
            ]
            if items:
                await results_container.mount(
                    Label(f"Procedures ({len(items)})", classes="section-title")
                )
                table = DataTable(id="search-procedures")
                await results_container.mount(table)
                table.add_columns("ID", "Name", "Type", "Published")
                for p in items[:10]:
                    pub = "Yes" if p.get("published_version") else "No"
                    table.add_row(
                        str(p.get("id", "")),
                        p.get("name", "")[:30],
                        p.get("procedure_type", "-"),
                        pub,
                    )
                total += len(items)
        except Exception:
            pass

        if total == 0:
            await results_container.mount(
                Label(f"No results for '{query}'", classes="hint")
            )
        else:
            await results_container.mount(
                Label(f"{total} result(s) found", classes="hint")
            )

    async def _show_global_results(
        self, container: VerticalScroll, result: dict[str, Any]
    ) -> None:
        """Display results from global search API."""
        total = 0
        for entity_type, items in result.items():
            if not isinstance(items, list) or not items:
                continue
            await container.mount(
                Label(f"{entity_type.title()} ({len(items)})", classes="section-title")
            )
            table = DataTable(id=f"search-{entity_type}")
            await container.mount(table)
            table.add_columns("ID", "Name/Title", "Type", "Status")
            for item in items[:15]:
                name = item.get("name", item.get("title", item.get("part_number", "")))
                itype = item.get("category", item.get("issue_type", item.get("procedure_type", "-")))
                status = item.get("status", "-")
                table.add_row(
                    str(item.get("id", "")),
                    str(name)[:30],
                    str(itype),
                    str(status),
                )
                total += 1

        if total == 0:
            await container.mount(Label("No results found", classes="hint"))
