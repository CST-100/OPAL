"""Issues screen - view and manage issues."""

from typing import Any

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, DataTable, Input, Label, Select, Static, TextArea

from opal.tui.api_client import get_client
from opal.tui.widgets.form import FormGroup, FormModal


class IssueFormModal(FormModal):
    """Modal form for creating/editing an issue."""

    def __init__(self, issue: dict[str, Any] | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.issue = issue

    @property
    def form_title(self) -> str:
        return "Edit Issue" if self.issue else "New Issue"

    def build_form(self) -> ComposeResult:
        title_val = self.issue.get("title", "") if self.issue else ""
        desc_val = self.issue.get("description", "") if self.issue else ""

        yield FormGroup(
            "Title",
            Input(value=title_val, id="field-title", placeholder="Issue title"),
            required=True,
        )

        type_options = [
            ("Non-Conformance", "non_conformance"),
            ("Bug", "bug"),
            ("Task", "task"),
            ("Improvement", "improvement"),
        ]
        current_type = self.issue.get("issue_type", "task") if self.issue else "task"
        yield FormGroup(
            "Type",
            Select(type_options, id="field-type", value=current_type),
            required=True,
        )

        priority_options = [
            ("Low", "low"),
            ("Medium", "medium"),
            ("High", "high"),
            ("Critical", "critical"),
        ]
        current_priority = self.issue.get("priority", "medium") if self.issue else "medium"
        yield FormGroup(
            "Priority",
            Select(priority_options, id="field-priority", value=current_priority),
        )

        if self.issue:
            status_options = [
                ("Open", "open"),
                ("Investigating", "investigating"),
                ("Disposition Pending", "disposition_pending"),
                ("Disposition Approved", "disposition_approved"),
                ("Closed", "closed"),
            ]
            yield FormGroup(
                "Status",
                Select(
                    status_options, id="field-status", value=self.issue.get("status", "open")
                ),
            )

        yield FormGroup(
            "Description",
            TextArea(text=desc_val, id="field-description"),
        )

        # Link fields
        part_id = (
            str(self.issue.get("part_id", ""))
            if self.issue and self.issue.get("part_id")
            else ""
        )
        yield FormGroup(
            "Linked Part ID",
            Input(value=part_id, id="field-part-id", placeholder="Optional"),
            hint="Enter part ID to link",
        )

    def get_form_data(self) -> dict[str, Any] | None:
        title = self.query_one("#field-title", Input).value.strip()
        if not title:
            self.show_error("Title is required")
            return None

        issue_type = self.query_one("#field-type", Select).value
        priority = self.query_one("#field-priority", Select).value
        description = self.query_one("#field-description", TextArea).text.strip()
        part_id_str = self.query_one("#field-part-id", Input).value.strip()

        data: dict[str, Any] = {
            "title": title,
            "issue_type": issue_type if issue_type != Select.BLANK else "task",
            "priority": priority if priority != Select.BLANK else "medium",
            "description": description,
        }

        if part_id_str:
            try:
                data["part_id"] = int(part_id_str)
            except ValueError:
                self.show_error("Part ID must be a number")
                return None

        if self.issue:
            try:
                status = self.query_one("#field-status", Select).value
                if status != Select.BLANK:
                    data["status"] = status
            except Exception:
                pass

        return data


class DispositionModal(FormModal):
    """Modal for issue disposition."""

    form_title = "Record Disposition"

    def __init__(self, issue: dict[str, Any], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.issue = issue

    def build_form(self) -> ComposeResult:
        disp_options = [
            ("Use As Is", "use_as_is"),
            ("Rework", "rework"),
            ("Repair", "repair"),
            ("Scrap", "scrap"),
            ("Return to Supplier", "return_to_supplier"),
        ]
        yield FormGroup(
            "Disposition Type",
            Select(disp_options, id="field-disposition", prompt="Select..."),
            required=True,
        )
        yield FormGroup(
            "Root Cause",
            TextArea(id="field-root-cause"),
        )
        yield FormGroup(
            "Corrective Action",
            TextArea(id="field-corrective-action"),
        )

    def get_form_data(self) -> dict[str, Any] | None:
        disposition = self.query_one("#field-disposition", Select).value
        if disposition == Select.BLANK:
            self.show_error("Disposition type is required")
            return None

        root_cause = self.query_one("#field-root-cause", TextArea).text.strip()
        corrective_action = self.query_one("#field-corrective-action", TextArea).text.strip()

        data: dict[str, Any] = {
            "status": "disposition_approved",
            "disposition_type": disposition,
        }
        if root_cause:
            data["root_cause"] = root_cause
        if corrective_action:
            data["corrective_action"] = corrective_action
        return data


class CommentInput(Static):
    """Comment input widget at bottom of detail panel."""

    def compose(self) -> ComposeResult:
        yield Label("Add Comment:", classes="detail-label")
        yield Input(placeholder="Type comment and press Enter", id="comment-input")


class IssueDetail(Static):
    """Issue detail panel."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.issue_data: dict[str, Any] | None = None

    def compose(self) -> ComposeResult:
        yield Label("Issue Details", classes="section-title")
        yield Container(id="issue-detail-content")
        yield Label("Comments", classes="section-title")
        yield VerticalScroll(id="comments-list")
        yield CommentInput(id="comment-input-widget")

    def show_issue(self, issue: dict[str, Any]) -> None:
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
        content.mount(
            Label(f"Priority: {priority}", classes=f"detail-row priority-{priority}")
        )

        # Disposition info
        if issue.get("disposition_type"):
            content.mount(
                Label(f"Disposition: {issue['disposition_type']}", classes="detail-row")
            )
        if issue.get("root_cause"):
            content.mount(Label("Root Cause:", classes="detail-label"))
            content.mount(Label(issue["root_cause"][:200], classes="detail-text"))
        if issue.get("corrective_action"):
            content.mount(Label("Corrective Action:", classes="detail-label"))
            content.mount(Label(issue["corrective_action"][:200], classes="detail-text"))

        # Description
        description = issue.get("description", "")
        if description:
            content.mount(Label("Description:", classes="detail-label"))
            content.mount(Label(description[:200], classes="detail-text"))

        # Links
        if issue.get("part_id"):
            content.mount(
                Label(f"Linked Part: #{issue['part_id']}", classes="detail-row")
            )
        if issue.get("procedure_id"):
            content.mount(
                Label(f"Linked Procedure: #{issue['procedure_id']}", classes="detail-row")
            )
        if issue.get("procedure_instance_id"):
            content.mount(
                Label(
                    f"Linked Execution: #{issue['procedure_instance_id']}",
                    classes="detail-row",
                )
            )

        # Timestamps
        created = issue.get("created_at", "")[:16] if issue.get("created_at") else "-"
        content.mount(Label(f"Created: {created}", classes="detail-row"))

    def show_comments(self, comments: list[dict[str, Any]]) -> None:
        """Display comments list."""
        container = self.query_one("#comments-list", VerticalScroll)
        container.remove_children()

        if not comments:
            container.mount(Label("No comments", classes="hint"))
            return

        for comment in comments:
            user = comment.get("user_name", f"User #{comment.get('user_id', '?')}")
            text = comment.get("body", comment.get("text", ""))
            ts = comment.get("created_at", "")[:16] if comment.get("created_at") else ""
            container.mount(Label(f"[{ts}] {user}: {text}", classes="detail-row"))

    def clear(self) -> None:
        """Clear the detail panel."""
        self.issue_data = None
        content = self.query_one("#issue-detail-content", Container)
        content.remove_children()
        content.mount(Label("Select an issue to view details", classes="hint"))

        comments = self.query_one("#comments-list", VerticalScroll)
        comments.remove_children()


class IssuesScreen(Screen):
    """Issues list screen."""

    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("n", "new_issue", "New Issue"),
        ("ctrl+e", "edit_issue", "Edit"),
        ("c", "close_issue", "Close"),
        ("o", "disposition", "Disposition"),
        ("escape", "go_back", "Back"),
    ]

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Issues", classes="screen-title"),
            Horizontal(
                Button("All", id="filter-all", variant="primary"),
                Button("Open", id="filter-open"),
                Button("Investigating", id="filter-investigating"),
                Button("Disp Pending", id="filter-disposition_pending"),
                Button("Disp Approved", id="filter-disposition_approved"),
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

    def action_go_back(self) -> None:
        """Go back to dashboard."""
        self.app.switch_screen("dashboard")

    async def action_new_issue(self) -> None:
        """Show new issue dialog."""
        self.app.push_screen(IssueFormModal(), callback=self._on_issue_created)

    def _on_issue_created(self, data: dict[str, Any] | None) -> None:
        """Handle issue creation result."""
        if data is None:
            return
        client = get_client(self.app.api_url)
        try:
            issue = client.create_issue(data)
            self.notify(f"Created issue #{issue.get('id', '')}: {issue.get('title', '')}")
            self.run_worker(self.load_issues())
        except Exception as e:
            self.notify(f"Error creating issue: {e}", severity="error")

    async def action_edit_issue(self) -> None:
        """Edit the selected issue."""
        detail = self.query_one("#issue-detail", IssueDetail)
        if not detail.issue_data:
            self.notify("Select an issue first", severity="warning")
            return
        self.app.push_screen(
            IssueFormModal(issue=detail.issue_data),
            callback=self._on_issue_edited,
        )

    def _on_issue_edited(self, data: dict[str, Any] | None) -> None:
        """Handle issue edit result."""
        if data is None:
            return
        detail = self.query_one("#issue-detail", IssueDetail)
        if not detail.issue_data:
            return
        client = get_client(self.app.api_url)
        try:
            client.update_issue(detail.issue_data["id"], data)
            self.notify("Issue updated")
            self.run_worker(self.load_issues())
        except Exception as e:
            self.notify(f"Error updating issue: {e}", severity="error")

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

    async def action_disposition(self) -> None:
        """Open disposition dialog for selected issue."""
        detail = self.query_one("#issue-detail", IssueDetail)
        if not detail.issue_data:
            self.notify("Select an issue first", severity="warning")
            return
        self.app.push_screen(
            DispositionModal(issue=detail.issue_data),
            callback=self._on_disposition,
        )

    def _on_disposition(self, data: dict[str, Any] | None) -> None:
        """Handle disposition result."""
        if data is None:
            return
        detail = self.query_one("#issue-detail", IssueDetail)
        if not detail.issue_data:
            return
        client = get_client(self.app.api_url)
        try:
            client.update_issue(detail.issue_data["id"], data)
            self.notify("Disposition recorded")
            self.run_worker(self.load_issues())
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    async def load_issues(
        self, status: str | None = None, issue_type: str | None = None
    ) -> None:
        """Load issues from API."""
        client = get_client(self.app.api_url)
        table = self.query_one("#issues-table", DataTable)
        detail = self.query_one("#issue-detail", IssueDetail)

        try:
            result = client.list_issues(
                status=status, issue_type=issue_type, page_size=100
            )
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

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle comment submission."""
        if event.input.id == "comment-input":
            detail = self.query_one("#issue-detail", IssueDetail)
            if not detail.issue_data:
                return
            text = event.value.strip()
            if not text:
                return

            client = get_client(self.app.api_url)
            try:
                client.create_comment(detail.issue_data["id"], {"body": text})
                event.input.value = ""
                # Reload comments
                comments = client.list_comments(detail.issue_data["id"])
                detail.show_comments(comments)
                self.notify("Comment added")
            except Exception as e:
                self.notify(f"Error adding comment: {e}", severity="error")

    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection."""
        client = get_client(self.app.api_url)
        detail = self.query_one("#issue-detail", IssueDetail)

        try:
            issue_id = int(event.row_key.value)
            issue = client.get_issue(issue_id)
            detail.show_issue(issue)
            # Load comments
            try:
                comments = client.list_comments(issue_id)
                detail.show_comments(comments)
            except Exception:
                pass
        except Exception as e:
            self.notify(f"Error loading issue: {e}", severity="error")
