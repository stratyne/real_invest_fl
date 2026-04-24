"""FilterProfile model — schema v0.2."""
from sqlalchemy.orm import Mapped, mapped_column
from real_invest_fl.db.base import Base


class FilterProfile(Base):
    __tablename__ = "filter_profiles"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
