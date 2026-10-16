from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Protocol(Base):
    """A protocol document, with the normalised text we extract from."""

    __tablename__ = "protocol"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    filename: Mapped[str] = mapped_column(String(300))
    text_hash: Mapped[str] = mapped_column(String(64))
    normalised: Mapped[str] = mapped_column(Text)
    sections: Mapped[list] = mapped_column(JSON)       # [{number,title,start,end,page}]
    pages: Mapped[int] = mapped_column(Integer)
    tokens_estimate: Mapped[int] = mapped_column(Integer)
    uploaded_by: Mapped[str] = mapped_column(String(100))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class ECRFVersion(Base):
    """Draft and approved eCRFs. APPEND ONLY.

    An approval inserts a new row with version + 1 and never updates in
    place, so this table IS the version history and the audit trail.
    protocol_hash pins each version to the exact document text it came
    from, which is what makes the traceability claim hold after an
    amendment.
    """

    __tablename__ = "ecrf_version"
    __table_args__ = (UniqueConstraint("protocol_id", "version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    protocol_id: Mapped[int] = mapped_column(ForeignKey("protocol.id"))
    protocol_hash: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[dict] = mapped_column(JSON)         # DraftECRF as dict
    created_by: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)


class Observation(Base):
    """Collected readings. Synthetic or approved de-identified data ONLY.

    repeat_num is what makes triplicate measurements storable without
    three near-identical columns, and what the statistics average over.
    """

    __tablename__ = "observation"
    __table_args__ = (UniqueConstraint("protocol_id", "subject_id", "visit",
                                       "field_name", "repeat_num"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    protocol_id: Mapped[int] = mapped_column(ForeignKey("protocol.id"))
    subject_id: Mapped[str] = mapped_column(String(50))
    visit: Mapped[str] = mapped_column(String(100))
    field_name: Mapped[str] = mapped_column(String(200))
    repeat_num: Mapped[int] = mapped_column(Integer, default=1)
    value_num: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    entered_by: Mapped[str] = mapped_column(String(100))
    entered_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
