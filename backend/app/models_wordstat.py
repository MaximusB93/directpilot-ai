from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import Date, DateTime, Float, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _uuid() -> str:
    return str(uuid4())


class WordstatQueryBatch(Base):
    __tablename__ = "wordstat_query_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    client_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    period: Mapped[str] = mapped_column(String(32), nullable=False)
    from_date: Mapped[date] = mapped_column(Date, nullable=False)
    to_date: Mapped[date] = mapped_column(Date, nullable=False)
    regions_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    devices_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    regions_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    devices_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="created")
    total_phrases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_phrases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_phrases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class WordstatQueryItem(Base):
    __tablename__ = "wordstat_query_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    batch_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    phrase: Mapped[str] = mapped_column(Text, nullable=False)
    phrase_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="created")
    points_loaded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class WordstatDynamicsPoint(Base):
    __tablename__ = "wordstat_dynamics"
    __table_args__ = (
        UniqueConstraint(
            "phrase_normalized",
            "period",
            "stat_date",
            "regions_hash",
            "devices_hash",
            name="uq_wordstat_dynamics_cache_key",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    phrase_original: Mapped[str] = mapped_column(Text, nullable=False)
    phrase_normalized: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    period: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    stat_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    share: Mapped[float | None] = mapped_column(Float, nullable=True)
    regions_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    devices_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    regions_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    devices_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class WordstatRequestLog(Base):
    __tablename__ = "wordstat_request_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="yandex_search_api")
    method: Mapped[str] = mapped_column(String(64), nullable=False, default="dynamics")
    phrase: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="started")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
