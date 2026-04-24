"""ZestimateCache model — schema v0.2."""
from sqlalchemy.orm import Mapped, mapped_column
from real_invest_fl.db.base import Base


class ZestimateCache(Base):
    __tablename__ = "zestimate_cache"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
