"""Runtime-mutable application settings stored in the database.

Provides a key/value escape hatch for config that needs to be edited from
the UI without touching .env. The Settings class still loads env defaults;
values present in this table override them.
"""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from opal.db.base import Base, TimestampMixin


class AppSetting(Base, TimestampMixin):
    """A single runtime-mutable application setting.

    `key` is the canonical name (e.g. ``onshape_access_key``). `value` is
    stored as text; consumers cast as needed.
    """

    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<AppSetting(key={self.key!r})>"
