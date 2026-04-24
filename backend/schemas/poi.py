"""
Pydantic schemas for Points of Interest and overnight options.
"""

from typing import Any, Literal, Optional
from pydantic import BaseModel


POIType = Literal[
    "campsite",
    "hotel",
    "motel",
    "hostel",
    "grocery",
    "convenience_store",
    "water",
    "bike_shop",
    "train_station",
    "ferry",
    "pharmacy",
]

OvernightType = Literal["campsite", "hotel", "motel", "hostel", "dispersed"]

LegalityType = Literal["permitted", "inferred_legal", "unknown"]


class POI(BaseModel):
    """A point of interest extracted from OSM or other sources."""
    id: int
    type: POIType
    lat: float
    lon: float
    name: Optional[str] = None
    source: str = "osm"
    metadata: dict[str, Any] = {}
    confidence_score: float = 1.0
    subregion: str


class OvernightOption(BaseModel):
    """
    An overnight stop candidate, linked to a POI.
    Tier 1 = official campgrounds / structured lodging.
    Tier 2 = community-reported.
    Tier 3 = inferred dispersed-legal areas.
    """
    id: int
    poi_id: int
    overnight_type: OvernightType
    tier: Literal[1, 2, 3]
    legality_type: LegalityType
    reservation_known: bool = False
    seasonality_known: bool = False
    exact_site_known: bool = False
    confidence_score: float


class OvernightStop(BaseModel):
    """One overnight stop within a trip plan — used in planning output."""
    night_number: int
    overnight_option: OvernightOption
    poi: POI
    distance_from_start_km: float
    nearby_grocery_km: Optional[float] = None
    nearby_water_km: Optional[float] = None
    nearby_hotel_fallback_km: Optional[float] = None
    nearby_bailout_km: Optional[float] = None
