"""
Pydantic schemas for trip specification.

TripSpec is the structured output of the intent parser — the source of truth
for what the user wants. All downstream planning reads from TripSpec.
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field


class TripDays(BaseModel):
    min: int = 2
    max: int = 3
    flexibility: Literal["hard", "soft"] = "soft"


class RelaxTo(BaseModel):
    min: float
    max: float


class TotalDistanceKm(BaseModel):
    min: float
    max: float
    flexibility: Literal["hard", "soft"] = "soft"
    relax_to: Optional[RelaxTo] = None


class RouteShape(BaseModel):
    preferred: Literal["loop", "out_and_back", "point_to_point"] = "loop"
    flexibility: Literal["hard", "soft"] = "soft"


class SurfaceTarget(BaseModel):
    gravel_ratio: float = Field(default=0.5, ge=0.0, le=1.0)
    tolerance: float = 0.15
    flexibility: Literal["soft"] = "soft"


class OvernightSpec(BaseModel):
    camping_required: bool = True
    hotel_allowed: bool = False
    overnight_flexibility: Literal["hard", "soft"] = "soft"


class RiderProfile(BaseModel):
    fitness_level: Literal["beginner", "intermediate", "strong", "elite"] = "intermediate"
    technical_skill: Literal["low", "medium", "high"] = "medium"
    overnight_experience: Literal["none", "some", "experienced"] = "some"
    comfort_daily_km: float = Field(default=75.0, gt=0)
    comfort_daily_climbing_m: float = Field(default=1200.0, gt=0)
    remote_tolerance: Literal["low", "medium", "high"] = "medium"
    bailout_preference: Literal["high", "medium", "low"] = "medium"


class LogisticsPreferences(BaseModel):
    grocery_access_required: bool = False
    water_access_required: bool = True
    bailout_access_preferred: bool = True


class TripPreferences(BaseModel):
    scenic: bool = False
    minimize_traffic: bool = True
    prefer_remote: bool = False


class RelaxationPolicy(BaseModel):
    allow_distance_widen: bool = True
    allow_surface_widen: bool = True
    allow_lower_overnight_tier: bool = True
    allow_hotel_fallback: bool = False
    allow_out_and_back: bool = True


class TripSpec(BaseModel):
    """
    Structured trip specification output by the intent parser.
    All fields are validated and defaults applied before passing downstream.
    """
    region: str = "north_bay"
    origin_preference: Optional[str] = None
    trip_days: TripDays = Field(default_factory=TripDays)
    total_distance_km: TotalDistanceKm
    route_shape: RouteShape = Field(default_factory=RouteShape)
    surface_target: SurfaceTarget = Field(default_factory=SurfaceTarget)
    overnight: OvernightSpec = Field(default_factory=OvernightSpec)
    rider_profile: RiderProfile = Field(default_factory=RiderProfile)
    logistics_preferences: LogisticsPreferences = Field(default_factory=LogisticsPreferences)
    preferences: TripPreferences = Field(default_factory=TripPreferences)
    hard_constraints: list[str] = Field(default_factory=list)
    soft_constraints: list[str] = Field(default_factory=list)
    relaxation_policy: RelaxationPolicy = Field(default_factory=RelaxationPolicy)
    parser_notes: str = ""


class ParseRequest(BaseModel):
    """Request body for POST /api/parse."""
    prompt: str = Field(..., min_length=10, max_length=2000)


class ParseResponse(BaseModel):
    """Response from POST /api/parse."""
    request_id: str
    trip_spec: TripSpec
    validation_warnings: list[str] = Field(default_factory=list)
