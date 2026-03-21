"""Reusable form widgets for TUI modals and screens."""

from __future__ import annotations

from typing import Any

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static, TextArea


class FormGroup(Static):
    """Container with label + input + optional validation error."""

    DEFAULT_CSS = """
    FormGroup {
        height: auto;
        margin: 0 0 1 0;
    }
    FormGroup .form-label {
        height: 1;
        padding: 0 1;
        color: $text-muted;
        text-style: bold;
    }
    FormGroup .form-error {
        height: 1;
        padding: 0 1;
        color: $error;
        display: none;
    }
    FormGroup .form-hint {
        height: 1;
        padding: 0 1;
        color: $text-muted;
        text-style: italic;
    }
    FormGroup Input {
        margin: 0 1;
    }
    FormGroup Select {
        margin: 0 1;
    }
    FormGroup TextArea {
        margin: 0 1;
        height: 6;
    }
    """

    def __init__(
        self,
        label: str,
        input_widget: Input | Select | TextArea,
        *,
        required: bool = False,
        hint: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.label_text = label
        self.input_widget = input_widget
        self.required = required
        self.hint_text = hint

    def compose(self) -> ComposeResult:
        req = " *" if self.required else ""
        yield Label(f"{self.label_text}{req}", classes="form-label")
        yield self.input_widget
        if self.hint_text:
            yield Label(self.hint_text, classes="form-hint")
        yield Label("", classes="form-error", id=f"error-{self.input_widget.id or 'field'}")

    def set_error(self, message: str) -> None:
        """Show a validation error."""
        error = self.query_one(".form-error", Label)
        error.update(message)
        error.display = True

    def clear_error(self) -> None:
        """Clear the validation error."""
        error = self.query_one(".form-error", Label)
        error.update("")
        error.display = False

    @property
    def value(self) -> Any:
        """Get the current value of the input widget."""
        widget = self.input_widget
        if isinstance(widget, Input):
            return widget.value
        if isinstance(widget, TextArea):
            return widget.text
        if isinstance(widget, Select):
            return widget.value if widget.value != Select.BLANK else None
        return None


class FormModal(ModalScreen[dict[str, Any] | None]):
    """Base modal screen with title, scrollable form body, Save/Cancel buttons.

    Subclasses should override `form_title`, `build_form()`, and `get_form_data()`.
    The modal returns a dict of form data on save, or None on cancel.
    """

    DEFAULT_CSS = """
    FormModal {
        align: center middle;
    }
    FormModal #form-dialog {
        width: 70;
        max-height: 80%;
        border: solid $primary;
        background: $surface;
    }
    FormModal #form-title {
        text-style: bold;
        padding: 1 2;
        background: $primary;
        color: $text;
        width: 100%;
        text-align: center;
    }
    FormModal #form-body {
        padding: 1 2;
        height: auto;
        max-height: 60;
    }
    FormModal #form-actions {
        height: 3;
        padding: 0 2;
        align: right middle;
    }
    FormModal #form-actions Button {
        margin: 0 1;
    }
    """

    form_title: str = "Form"

    def compose(self) -> ComposeResult:
        with Vertical(id="form-dialog"):
            yield Label(self.form_title, id="form-title")
            with VerticalScroll(id="form-body"):
                yield from self.build_form()
            with Horizontal(id="form-actions"):
                yield Button("Save", id="form-save", variant="success")
                yield Button("Cancel", id="form-cancel", variant="default")

    def build_form(self) -> ComposeResult:
        """Override to yield form widgets. Must be implemented by subclasses."""
        yield Label("Override build_form() in subclass")

    def get_form_data(self) -> dict[str, Any] | None:
        """Override to collect and validate form data.

        Return a dict of data on success, or None to prevent dismissal.
        Call self.show_error() or set_error on FormGroups for validation.
        """
        return {}

    def show_error(self, message: str) -> None:
        """Show a notification error message."""
        self.notify(message, severity="error")

    @on(Button.Pressed, "#form-save")
    def _on_save(self, event: Button.Pressed) -> None:
        """Handle save button."""
        event.stop()
        data = self.get_form_data()
        if data is not None:
            self.dismiss(data)

    @on(Button.Pressed, "#form-cancel")
    def _on_cancel(self, event: Button.Pressed) -> None:
        """Handle cancel button."""
        event.stop()
        self.dismiss(None)

    def key_escape(self) -> None:
        """Handle escape key."""
        self.dismiss(None)


class ConfirmModal(ModalScreen[bool]):
    """Simple yes/no confirmation dialog."""

    DEFAULT_CSS = """
    ConfirmModal {
        align: center middle;
    }
    ConfirmModal #confirm-dialog {
        width: 50;
        height: auto;
        border: solid $warning;
        background: $surface;
        padding: 1 2;
    }
    ConfirmModal #confirm-title {
        text-style: bold;
        padding: 0 0 1 0;
        color: $warning;
    }
    ConfirmModal #confirm-message {
        padding: 0 0 1 0;
    }
    ConfirmModal #confirm-actions {
        height: 3;
        align: right middle;
    }
    ConfirmModal #confirm-actions Button {
        margin: 0 1;
    }
    """

    def __init__(
        self,
        title: str = "Confirm",
        message: str = "Are you sure?",
        confirm_label: str = "Yes",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._title = title
        self._message = message
        self._confirm_label = confirm_label

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Label(self._title, id="confirm-title")
            yield Label(self._message, id="confirm-message")
            with Horizontal(id="confirm-actions"):
                yield Button(self._confirm_label, id="confirm-yes", variant="error")
                yield Button("Cancel", id="confirm-no", variant="default")

    @on(Button.Pressed, "#confirm-yes")
    def _on_yes(self, event: Button.Pressed) -> None:
        event.stop()
        self.dismiss(True)

    @on(Button.Pressed, "#confirm-no")
    def _on_no(self, event: Button.Pressed) -> None:
        event.stop()
        self.dismiss(False)

    def key_escape(self) -> None:
        self.dismiss(False)


class UserPickerModal(ModalScreen[int | None]):
    """Modal for selecting the active user on TUI startup."""

    DEFAULT_CSS = """
    UserPickerModal {
        align: center middle;
    }
    UserPickerModal #picker-dialog {
        width: 50;
        height: auto;
        max-height: 80%;
        border: solid $primary;
        background: $surface;
    }
    UserPickerModal #picker-title {
        text-style: bold;
        padding: 1 2;
        background: $primary;
        color: $text;
        width: 100%;
        text-align: center;
    }
    UserPickerModal #picker-body {
        padding: 1 2;
        height: auto;
        max-height: 20;
    }
    UserPickerModal #picker-actions {
        height: 3;
        padding: 0 2;
        align: right middle;
    }
    """

    def __init__(self, users: list[dict[str, Any]], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.users = users

    def compose(self) -> ComposeResult:
        options = [(f"{u['name']} ({u.get('email', '')})", u["id"]) for u in self.users]
        with Vertical(id="picker-dialog"):
            yield Label("Select User", id="picker-title")
            with VerticalScroll(id="picker-body"):
                yield FormGroup(
                    "User",
                    Select(options, id="user-select", prompt="Choose user..."),
                    required=True,
                )
            with Horizontal(id="picker-actions"):
                yield Button("Select", id="picker-select", variant="success")

    @on(Button.Pressed, "#picker-select")
    def _on_select(self, event: Button.Pressed) -> None:
        event.stop()
        select = self.query_one("#user-select", Select)
        if select.value != Select.BLANK:
            self.dismiss(select.value)
        else:
            self.notify("Please select a user", severity="warning")

    def key_escape(self) -> None:
        self.dismiss(None)
