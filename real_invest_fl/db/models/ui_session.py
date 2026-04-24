"""UISession model — single-operator session tracking. Schema v0.2."""
from sqlalchemy.orm import Mapped, mapped_column
from real_invest_fl.db.base import Base


class UISession(Base):
    __tablename__ = "ui_sessions"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
