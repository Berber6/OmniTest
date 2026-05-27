"""SQLAlchemy ORM models for omni_test persistence."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Feature(Base):
    """A feature extracted from crawled web content."""

    __tablename__ = "features"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    source_chunks: Mapped[dict] = mapped_column(JSON, nullable=False, default=list)

    scenarios: Mapped[list["TestScenario"]] = relationship(back_populates="feature")


class TestScenario(Base):
    """A test scenario derived from a feature."""

    __tablename__ = "test_scenarios"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    feature_id: Mapped[str] = mapped_column(String, ForeignKey("features.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    steps_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=list)
    expectations_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=list)

    feature: Mapped["Feature"] = relationship(back_populates="scenarios")
    step_results: Mapped[list["StepResult"]] = relationship(back_populates="scenario")
    executions: Mapped[list["ExecutionRecord"]] = relationship(back_populates="scenario")
    mutations: Mapped[list["MutationResult"]] = relationship(
        back_populates="original_scenario",
        foreign_keys="MutationResult.original_scenario_id",
    )


class StepResult(Base):
    """Result of executing a single step within a scenario."""

    __tablename__ = "step_results"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    scenario_id: Mapped[str] = mapped_column(
        String, ForeignKey("test_scenarios.id"), nullable=False
    )
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    target: Mapped[str] = mapped_column(String, nullable=False)
    result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    screenshot_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    scenario: Mapped["TestScenario"] = relationship(back_populates="step_results")


class ExecutionRecord(Base):
    """Record of a full scenario execution run."""

    __tablename__ = "execution_records"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    scenario_id: Mapped[str] = mapped_column(
        String, ForeignKey("test_scenarios.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    final_result: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    plan_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=list)
    executed_steps_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=list)
    verification_result_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=dict)
    screenshots_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=list)
    reflection: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    scenario: Mapped["TestScenario"] = relationship(back_populates="executions")


class MutationResult(Base):
    """Result of applying a mutation to an original scenario."""

    __tablename__ = "mutation_results"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    original_scenario_id: Mapped[str] = mapped_column(
        String, ForeignKey("test_scenarios.id"), nullable=False
    )
    mutation_type: Mapped[str] = mapped_column(String, nullable=False)
    mutation_description: Mapped[str] = mapped_column(Text, nullable=False)
    execution_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    detected_error_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    detected_error_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mutated_scenario_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    execution_record_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("execution_records.id"), nullable=True
    )

    original_scenario: Mapped["TestScenario"] = relationship(
        back_populates="mutations",
        foreign_keys=[original_scenario_id],
    )
    execution_record: Mapped[Optional["ExecutionRecord"]] = relationship()