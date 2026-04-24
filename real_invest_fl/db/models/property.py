"""Property (MQI) model — schema v0.2."""
from sqlalchemy.orm import Mapped, mapped_column
from real_invest_fl.db.base import Base


class Property(Base):
    __tablename__ = "properties"
    county_fips: Mapped[str] = mapped_column(primary_key=True)
    parcel_id: Mapped[str] = mapped_column(primary_key=True)
