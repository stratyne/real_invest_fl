"""PermitRecord model — Phase 2 slot. Schema v0.2."""
from sqlalchemy.orm import Mapped, mapped_column
from real_invest_fl.db.base import Base


class PermitRecord(Base):
    __tablename__ = "permit_records"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
