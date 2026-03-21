"""Settings screen - read-only project info and configuration."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Label

from opal.tui.api_client import get_client


class SettingsScreen(Screen):
    """Settings and project info — read-only."""

    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("escape", "go_back", "Back"),
    ]

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Settings & Project Info", classes="screen-title"),
            Horizontal(
                Vertical(
                    Label("Project Configuration", classes="section-title"),
                    Container(id="project-config"),
                    classes="quick-actions",
                ),
                Vertical(
                    Label("System Info", classes="section-title"),
                    Container(id="system-info"),
                    classes="system-status",
                ),
                classes="dashboard-content",
            ),
            classes="dashboard-container",
        )

    async def on_mount(self) -> None:
        await self.load_settings()

    async def action_refresh(self) -> None:
        await self.load_settings()
        self.notify("Settings refreshed")

    def action_go_back(self) -> None:
        self.app.switch_screen("dashboard")

    async def load_settings(self) -> None:
        client = get_client(self.app.api_url)

        # System info
        sys_container = self.query_one("#system-info", Container)
        sys_container.remove_children()

        try:
            health = client.health_check()
            sys_container.mount(
                Label(f"API Status: {health.get('status', '?')}", classes="detail-row")
            )
            sys_container.mount(
                Label(f"Version: {health.get('version', '?')}", classes="detail-row")
            )
        except Exception:
            sys_container.mount(Label("API: offline", classes="status-error"))

        try:
            user = client.get_current_user()
            if user:
                sys_container.mount(
                    Label(f"Current User: {user.get('name', '?')}", classes="detail-row")
                )
                sys_container.mount(
                    Label(f"User ID: {client.user_id}", classes="detail-row")
                )
        except Exception:
            pass

        sys_container.mount(Label(f"API URL: {client.base_url}", classes="detail-row"))

        # Project config
        config_container = self.query_one("#project-config", Container)
        config_container.remove_children()

        try:
            config = client.get_project_config()
            proj_name = config.get("name", config.get("project_name", "?"))
            config_container.mount(
                Label(f"Project: {proj_name}", classes="detail-row")
            )

            # Tiers
            tiers = config.get("tiers", [])
            if tiers:
                config_container.mount(Label("Tiers:", classes="detail-label"))
                for tier in tiers:
                    if isinstance(tier, dict):
                        config_container.mount(
                            Label(
                                f"  {tier.get('number', '?')}: {tier.get('name', '?')}",
                                classes="detail-row",
                            )
                        )
                    else:
                        config_container.mount(Label(f"  {tier}", classes="detail-row"))

            # Categories
            categories = config.get("categories", [])
            if categories:
                config_container.mount(Label("Categories:", classes="detail-label"))
                for cat in categories:
                    if isinstance(cat, dict):
                        config_container.mount(
                            Label(f"  {cat.get('name', '?')}", classes="detail-row")
                        )
                    else:
                        config_container.mount(Label(f"  {cat}", classes="detail-row"))

            # Part numbering
            numbering = config.get("part_numbering", {})
            if numbering:
                config_container.mount(Label("Part Numbering:", classes="detail-label"))
                prefix = numbering.get("prefix", "?")
                config_container.mount(
                    Label(f"  Prefix: {prefix}", classes="detail-row")
                )

        except Exception as e:
            config_container.mount(
                Label(f"Could not load config: {e}", classes="status-error")
            )
