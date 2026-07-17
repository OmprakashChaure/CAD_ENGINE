"""Pydantic schema for the final frozen entity-centric output."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class Relationship(BaseModel):
    """Engineering-meaningful relationship between entities."""
    rel_type: str
    target_id: int


class StructuredThread(BaseModel):
    """Structured thread engineering parameters parsed from annotation notes."""
    thread_standard: Optional[str] = Field(None, description="Thread standard (e.g. ISO Metric, UNC, UNF, BSPP, NPT)")
    nominal_diameter: Optional[float] = Field(None, description="Nominal major diameter in mm")
    thread_pitch: Optional[float] = Field(None, description="Thread pitch distance in mm")
    thread_gender: Optional[str] = Field(None, description="Thread gender: internal (female) or external (male)")
    tolerance_class: Optional[str] = Field(None, description="Tolerance fit class (e.g. 6H, 6g)")
    nominal_pipe_size: Optional[str] = Field(None, description="Pipe nominal thread size code (e.g. 1/4, 1/2)")
    major_diameter: Optional[float] = Field(None, description="Physical major diameter in mm")
    pitch_tpi: Optional[float] = Field(None, description="Threads per inch (TPI)")
    taper: Optional[float] = Field(None, description="Pipe thread taper ratio (e.g. 0.0625 for NPT)")
    validation_status: str = Field("unvalidated", description="Status of standard lookups: validated, fallback, or unvalidated")
    source_annotation: str = Field(..., description="Original raw annotation text")


class StructuredFit(BaseModel):
    """Structured limit fit class parameters based on ISO 286."""
    fit_class: str = Field(..., description="Fit class designation (e.g. H7, G6)")
    nominal_diameter: float = Field(..., description="Target bore or shaft diameter in mm")
    lower_deviation: Optional[float] = Field(None, description="Lower deviation limit in mm")
    upper_deviation: Optional[float] = Field(None, description="Upper deviation limit in mm")
    validation_status: str = Field("unvalidated", description="Status of fit standard lookups")
    source_annotation: str = Field(..., description="Original raw annotation text")


class SemanticEntity(BaseModel):
    """
    Final frozen entity schema.
    
    Every entity in the output MUST conform to this structure.
    No exceptions. No alternate formats.
    """

    id: int
    geometry: dict[str, Any] = Field(description="Type-specific geometry payload")
    semantic: dict[str, Any] = Field(default_factory=dict, description="Engineering meaning")
    manufacturing: dict[str, Any] = Field(default_factory=dict, description="Manufacturing interpretation")
    dimensions: list[dict[str, Any]] = Field(default_factory=list, description="Attached dimensions")
    relationships: list[Relationship] = Field(default_factory=list, description="Engineering relationships")

