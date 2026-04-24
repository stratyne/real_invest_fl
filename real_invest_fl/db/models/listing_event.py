"""ListingEvent model — schema v0.2. Includes deal_score, deal_score_version."""
from sqlalchemy.orm import Mapped, mapped_column
from real_invest_fl.db.base import Base


class ListingEvent(Base):
    __tablename__ = "listing_events"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
