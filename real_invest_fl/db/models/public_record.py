"""PublicRecordSignal model — Phase 2 slot. Schema v0.2."""
from sqlalchemy.orm import Mapped, mapped_column
from real_invest_fl.db.base import Base


class PublicRecordSignal(Base):
    __tablename__ = "public_records_signals"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
