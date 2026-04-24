"""County and CountyZip models — schema v0.2."""
# STUB: full column definitions added in migration session.
from sqlalchemy.orm import Mapped, mapped_column
from real_invest_fl.db.base import Base


class County(Base):
    __tablename__ = "counties"
    county_fips: Mapped[str] = mapped_column(primary_key=True)


class CountyZip(Base):
    __tablename__ = "county_zips"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
