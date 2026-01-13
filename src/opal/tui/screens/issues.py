"""Issues screen - view and manage issues."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Input, Label, Static

from opal.tui.api_client import get_client


class IssueDetail(Static):
    """Issue detail panel."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.issue_data: dict | None = None

    def compose(self) -> ComposeResult:
        yield Label("Issue Details", classes="section-title")
        yield Container(id="issue-detail-content")

    def show_issue(self, issue: dict) -> None:
        """Display issue details."""
        self.issue_data = issue
        content = self.query_one("#issue-detail-content", Container)
        content.remove_children()

        content.mount(Label(f"ID: {issue.get('id', '-')}", classes="detail-row"))
        content.mount(Label(f"Title: {issue.get('title', '-')}", classes="detail-row"))

        issue_type = issue.get("issue_type", "-")
        content.mount(Label(f"Type: {issue_type}", classes=f"detail-row type-{issue_type}"))

        status = issue.get("status", "-")
        content.mount(Label(f"Status: {status}", classes=f"detail-row status-{status}"))

        priority = issue.get("priority", "-")
        content.mount(Label(f"Priority: {priority}", classes=f"detail-row priority-{priority}"))

        # Description
        description = issue.get("description", "")
        if description:
            content.mount(Label("Description:", classes="detail-label"))
            content.mount(Label(description[:200], classes="detail-text"))

        # Links
        if issue.get("part_id"):
            content.mount(Label(f"Linked Part: #{issue['part_id']}", classes="detail-row"))
        if issue.get("procedure_id"):
            content.mount(Label(f"Linked Procedure: #{issue['procedure_id']}", classes="detail-row"))
        if issue.get("procedure_instance_id"):
            content.mount(Label(f"Linked Execution: #{issue['procedure_instance_id']}", classes="detail-row"))

        # Timestamps
        created = issue.get("created_at", "")[:16] if issue.get("created_at") else "-"
        content.mount(Label(f"Created: {created}", classes="detail-row"))

    def clear(self) -> None:
        """Clear the detail panel."""
        self.issue_data = None
        content = self.query_one("#issue-detail-content", Container)
        content.remove_children()
        content.mount(Label("Select an issue to view details", classes="hint"))


class IssuesScreen(Screen):
    """Issues list screen."""

    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("n", "new_issue", "New Issue"),
        ("c", "close_issue", "Close"),
        ("escape", "go_back", "Back"),
        ("/", "focus_search", "Search"),
    ]

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Issues", classes="screen-title"),
            Horizontal(
                Button("All", id="filter-all", variant="primary"),
                Button("Open", id="filter-open"),
                Button("In Progress", id="filter-in_progress"),
                Button("Resolved", id="filter-resolved"),
                Button("Closed", id="filter-closed"),
                classes="filter-bar",
            ),
            Horizontal(
                Button("All Types", id="type-all"),
                Button("NC", id="type-non_conformance"),
                Button("Bug", id="type-bug"),
                Button("Task", id="type-task"),
                Button("Improvement", id="type-improvement"),
                classes="filter-bar type-filter",
            ),
            Horizontal(
                Vertical(
                    DataTable(id="issues-table"),
                    classes="table-container",
                ),
                IssueDetail(id="issue-detail"),
                classes="main-content",
            ),
            classes="screen-container",
        )

    async def on_mount(self) -> None:
        """Initialize the issues table."""
        table = self.query_one("#issues-table", DataTable)
        table.add_columns("ID", "Type", "Priority", "Title", "Status")
        table.cursor_type = "row"
        await self.load_issues()

    async def action_refresh(self) -> None:
        """Refresh issues list."""
        await self.load_issues()
        self.notify("Issues refreshed")

    async def action_focus_search(self) -> None:
        """Focus the search input."""
        self.notify("Search not yet implemented")

    def action_go_back(self) -> None:
        """Go back to dashboard."""
        self.app.switch_screen("dashboard")

    async def action_new_issue(self) -> None:
        """Show new issue dialog."""
        self.notify("Issue creation not yet implemented in TUI")

    async def action_close_issue(self) -> None:
        """Close the selected issue."""
        detail = self.query_one("#issue-detail", IssueDetail)
        if not detail.issue_data:
            self.notify("Select an issue first", severity="warning")
            return

        client = get_client(self.app.api_url)
        try:
            client.update_issue(detail.issue_data["id"], {"status": "closed"})
            self.notify(f"Closed issue #{detail.issue_data['id']}")
            await self.load_issues()
        except Exception as e:
            self.notify(f"Error closing issue: {e}", severity="error")

    async def load_issues(
        self, status: str | None = None, issue_type: str | None = None
    ) -> None:
        """Load issues from API."""
        client = get_client(self.app.api_url)
        table = self.query_one("#issues-table", DataTable)
        detail = self.query_one("#issue-detail", IssueDetail)

        try:
            result = client.list_issues(status=status, issue_type=issue_type, page_size=100)
            issues = result.get("items", [])

            table.clear()
            for issue in issues:
                table.add_row(
                    str(issue.get("id", "")),
                    issue.get("issue_type", ""),
                    issue.get("priority", ""),
                    issue.get("title", "")[:40],
                    issue.get("status", ""),
                    key=str(issue.get("id")),
                )

            detail.clear()

        except Exception as e:
            self.notify(f"Error loading issues: {e}", severity="error")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle filter button clicks."""
        button_id = event.button.id or ""

        if button_id.startswith("filter-"):
            status = button_id.replace("filter-", "")
            if status == "all":
                status = None
            await self.load_issues(status=status)

        elif button_id.startswith("type-"):
            issue_type = button_id.replace("type-", "")
            if issue_type == "all":
                issue_type = None
            await self.load_issues(issue_type=issue_type)

    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection."""
        client = get_client(self.app.api_url)
        detail = self.query_one("#issue-detail", IssueDetail)

        try:
            issue_id = int(event.row_key.value)
            issue = client.get_issue(issue_id)
            detail.show_issue(issue)
        except Exception as e:
            self.notify(f"Error loading issue: {e}", severity="error")
