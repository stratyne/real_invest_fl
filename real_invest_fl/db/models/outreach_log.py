"""OutreachLog model — append-only. Schema v0.2."""
from sqlalchemy.orm import Mapped, mapped_column
from real_invest_fl.db.base import Base


class OutreachLog(Base):
    __tablename__ = "outreach_log"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
