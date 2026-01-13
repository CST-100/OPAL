"""Dashboard screen - overview of OPAL status."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Label, Static

from opal.tui.api_client import get_client


class StatCard(Static):
    """A card displaying a statistic."""

    def __init__(self, title: str, value: str = "-", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title = title
        self._value = value

    def compose(self) -> ComposeResult:
        yield Label(self.title, classes="stat-title")
        yield Label(self._value, classes="stat-value", id=f"stat-{self.title.lower().replace(' ', '-')}")

    def update_value(self, value: str) -> None:
        """Update the displayed value."""
        self._value = value
        label = self.query_one(f"#stat-{self.title.lower().replace(' ', '-')}", Label)
        label.update(value)


class RecentActivity(Static):
    """Recent activity widget."""

    def compose(self) -> ComposeResult:
        yield Label("Recent Activity", classes="section-title")
        yield Container(id="activity-list")


class DashboardScreen(Screen):
    """Main dashboard screen."""

    BINDINGS = [
        ("r", "refresh", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("OPAL Dashboard", classes="screen-title"),
            Horizontal(
                StatCard("Parts", id="parts-stat"),
                StatCard("Active Executions", id="exec-stat"),
                StatCard("Open Issues", id="issues-stat"),
                StatCard("Active Risks", id="risks-stat"),
                classes="stats-row",
            ),
            Horizontal(
                Vertical(
                    Label("Quick Actions", classes="section-title"),
                    Label("[p] View Parts", classes="action-hint"),
                    Label("[r] View Procedures", classes="action-hint"),
                    Label("[e] View Executions", classes="action-hint"),
                    Label("[i] View Issues", classes="action-hint"),
                    Label("[k] View Risks", classes="action-hint"),
                    classes="quick-actions",
                ),
                Vertical(
                    Label("System Status", classes="section-title"),
                    Container(id="status-container"),
                    classes="system-status",
                ),
                classes="dashboard-content",
            ),
            classes="dashboard-container",
        )

    async def on_mount(self) -> None:
        """Load data when screen is mounted."""
        await self.load_stats()

    async def action_refresh(self) -> None:
        """Refresh dashboard data."""
        await self.load_stats()
        self.notify("Dashboard refreshed")

    async def load_stats(self) -> None:
        """Load statistics from API."""
        client = get_client(self.app.api_url)

        try:
            # Health check
            health = client.health_check()
            status_container = self.query_one("#status-container", Container)
            status_container.remove_children()
            status_container.mount(Label(f"API: {health.get('status', 'unknown')}", classes="status-ok"))
            status_container.mount(Label(f"Database: OK", classes="status-ok"))

            # Parts count
            parts = client.list_parts(page_size=1)
            parts_stat = self.query_one("#parts-stat", StatCard)
            parts_stat.update_value(str(parts.get("total", 0)))

            # Active executions
            executions = client.list_instances(status="in_progress", page_size=1)
            exec_stat = self.query_one("#exec-stat", StatCard)
            exec_stat.update_value(str(executions.get("total", 0)))

            # Open issues
            issues = client.list_issues(status="open", page_size=1)
            issues_stat = self.query_one("#issues-stat", StatCard)
            issues_stat.update_value(str(issues.get("total", 0)))

            # Active risks
            risks = client.list_risks(status="identified", page_size=1)
            risks_stat = self.query_one("#risks-stat", StatCard)
            risks_stat.update_value(str(risks.get("total", 0)))

        except Exception as e:
            self.notify(f"Error loading stats: {e}", severity="error")
            status_container = self.query_one("#status-container", Container)
            status_container.remove_children()
            status_container.mount(Label(f"API: offline", classes="status-error"))
