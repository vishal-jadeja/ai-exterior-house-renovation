"""SQLAlchemy ORM models.

Mirrors the schema created by `alembic/versions/*_initial_schema.py` and
`*_material_quantity_unit.py` exactly — table/column names, nullability, FKs and indexes here
must match those migrations (tests build the schema straight from these models via
`Base.metadata.create_all`, while Postgres is provisioned through the migrations, so the two
must never drift).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def _id() -> str:
    return str(uuid.uuid4())


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (Index("ix_users_email", "email", unique=True),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    refresh_token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Material(TimestampMixin, Base):
    __tablename__ = "materials"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity_unit: Mapped[str] = mapped_column(
        String(16), nullable=False, default="sqft", server_default="sqft"
    )
    coverage: Mapped[float | None] = mapped_column(Float, nullable=True)
    coats: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    piece_area_sqft: Mapped[float | None] = mapped_column(Float, nullable=True)
    pieces_per_box: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wastage_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    default_material_rate: Mapped[float] = mapped_column(Float, nullable=False)
    default_labor_rate: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")
    texture_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    color_hex: Mapped[str | None] = mapped_column(String(9), nullable=True)
    prompt_hint: Mapped[str] = mapped_column(Text, nullable=False)
    applicable_labels: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    durability_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    maintenance: Mapped[str] = mapped_column(String(32), nullable=False, default="low")


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        Index("ix_projects_owner_created", "owner_id", "created_at"),
        Index("ix_projects_owner_id", "owner_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")
    unit_system: Mapped[str] = mapped_column(String(16), nullable=False, default="imperial")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="created")
    scale_ft_per_px: Mapped[float | None] = mapped_column(Float, nullable=True)
    scale_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scale_confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    facade_width_ft: Mapped[float | None] = mapped_column(Float, nullable=True)
    facade_height_ft: Mapped[float | None] = mapped_column(Float, nullable=True)
    floors: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Design(TimestampMixin, Base):
    __tablename__ = "designs"
    __table_args__ = (Index("ix_designs_project_id", "project_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=False)

    assignments: Mapped[list[DesignAssignment]] = relationship(
        back_populates="design", cascade="all, delete-orphan", passive_deletes=True
    )


class Image(TimestampMixin, Base):
    __tablename__ = "images"
    __table_args__ = (Index("ix_images_project_id", "project_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class RateCard(TimestampMixin, Base):
    __tablename__ = "rate_cards"
    __table_args__ = (
        Index("ix_rate_cards_project_id", "project_id"),
        UniqueConstraint("project_id", "material_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    material_id: Mapped[str] = mapped_column(String(64), ForeignKey("materials.id"), nullable=False)
    material_rate: Mapped[float] = mapped_column(Float, nullable=False)
    labor_rate: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")


class Estimate(TimestampMixin, Base):
    __tablename__ = "estimates"
    __table_args__ = (
        Index("ix_estimates_design_id", "design_id"),
        UniqueConstraint("design_id", "version", name="uq_estimates_design_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    design_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("designs.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")
    grand_total: Mapped[float] = mapped_column(Float, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class Region(TimestampMixin, Base):
    __tablename__ = "regions"
    __table_args__ = (
        Index("ix_regions_image_id", "image_id"),
        Index("ix_regions_project_id", "project_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    image_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("images.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    polygon: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    pixel_area: Mapped[float] = mapped_column(Float, nullable=False)
    bbox: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)


class Render(TimestampMixin, Base):
    __tablename__ = "renders"
    __table_args__ = (Index("ix_renders_design_id", "design_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    design_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("designs.id", ondelete="CASCADE"), nullable=False
    )
    image_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("images.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    provider_used: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider_log: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Report(TimestampMixin, Base):
    __tablename__ = "reports"
    __table_args__ = (Index("ix_reports_design_id", "design_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    design_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("designs.id", ondelete="CASCADE"), nullable=False
    )
    image_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("images.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class DesignAssignment(TimestampMixin, Base):
    __tablename__ = "design_assignments"
    __table_args__ = (
        Index("ix_design_assignments_design_id", "design_id"),
        Index("ix_design_assignments_region_id", "region_id"),
        UniqueConstraint("design_id", "region_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    design_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("designs.id", ondelete="CASCADE"), nullable=False
    )
    region_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("regions.id", ondelete="CASCADE"), nullable=False
    )
    material_id: Mapped[str] = mapped_column(String(64), ForeignKey("materials.id"), nullable=False)
    color_hex: Mapped[str | None] = mapped_column(String(9), nullable=True)

    design: Mapped[Design] = relationship(back_populates="assignments")


class Job(TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_owner_id", "owner_id"),
        Index("ix_jobs_status_created", "status", "created_at"),
        UniqueConstraint("idempotency_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    owner_id: Mapped[str] = mapped_column(String(36), nullable=False)
