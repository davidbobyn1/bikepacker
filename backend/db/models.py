"""
SQLAlchemy ORM models.

These mirror the Pydantic schemas in backend/schemas/ but are the DB representation.
All geometry columns use PostGIS via GeoAlchemy2, stored in WGS84 (EPSG:4326).
"""

import datetime
from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Float, Index, Integer,
    JSON, String, Text, ForeignKey
)
from sqlalchemy.orm import DeclarativeBase, relationship
from geoalchemy2 import Geometry


class Base(DeclarativeBase):
    pass


class TripRequest(Base):
    """Stores raw prompts and their parsed trip specs."""
    __tablename__ = "trip_requests"

    id = Column(String, primary_key=True)  # UUID string
    raw_prompt = Column(Text, nullable=False)
    parsed_constraints_json = Column(JSON, nullable=True)
    rider_profile_json = Column(JSON, nullable=True)
    region = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    candidate_routes = relationship("CandidateRoute", back_populates="trip_request")
    final_routes = relationship("FinalRoute", back_populates="trip_request")


class Subregion(Base):
    """Supported geographic subregions with bounding polygons."""
    __tablename__ = "subregions"

    id = Column(Integer, primary_key=True)
    name = Column(String(64), unique=True, nullable=False)
    geom = Column(Geometry("POLYGON", srid=4326), nullable=False)

    __table_args__ = (
        Index("ix_subregions_geom", "geom", postgresql_using="gist"),
    )


class OriginHub(Base):
    """Named origin hubs cyclists can start from."""
    __tablename__ = "origin_hubs"

    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    geom = Column(Geometry("POINT", srid=4326), nullable=False)
    subregion = Column(String(64), nullable=False)

    __table_args__ = (
        Index("ix_origin_hubs_geom", "geom", postgresql_using="gist"),
    )


class Node(Base):
    """Graph node — an OSM intersection or endpoint."""
    __tablename__ = "graph_nodes"

    id = Column(BigInteger, primary_key=True)  # OSM node ID — requires BigInteger (64-bit)
    geom = Column(Geometry("POINT", srid=4326), nullable=False)
    elevation_m = Column(Float, nullable=True)
    subregion = Column(String(64), nullable=False, index=True)

    __table_args__ = (
        Index("ix_graph_nodes_geom", "geom", postgresql_using="gist"),
    )


class Edge(Base):
    """
    Graph edge — an OSM way segment between two nodes.
    All enrichment scores are precomputed and stored here.
    See docs/enrichment_rules.md for how each score is derived.
    """
    __tablename__ = "graph_edges"

    id = Column(Integer, primary_key=True)
    source_node = Column(BigInteger, ForeignKey("graph_nodes.id"), nullable=False, index=True)
    target_node = Column(BigInteger, ForeignKey("graph_nodes.id"), nullable=False, index=True)
    geom = Column(Geometry("LINESTRING", srid=4326), nullable=False)
    distance_m = Column(Float, nullable=False)
    climb_up_m = Column(Float, nullable=False, default=0.0)
    climb_down_m = Column(Float, nullable=False, default=0.0)

    # Normalized classifications
    road_class = Column(String(64), nullable=True)
    bike_access = Column(Boolean, nullable=True)
    is_oneway = Column(Boolean, nullable=False, default=False)

    # Enriched surface attributes
    surface_class = Column(String(32), nullable=True)       # paved / gravel / dirt / unknown
    surface_confidence = Column(Float, nullable=True)        # 0.0–1.0

    # Enriched scores (0.0–1.0 unless noted)
    rideability_score = Column(Float, nullable=True)
    technicality_score = Column(Float, nullable=True)
    traffic_score = Column(Float, nullable=True)
    scenic_score = Column(Float, nullable=True)
    hike_a_bike_risk = Column(Float, nullable=True)          # 0.0–1.0
    data_quality_score = Column(Float, nullable=True)

    subregion = Column(String(64), nullable=False, index=True)

    # RideWithGPS confidence boost (populated if cross-referenced)
    rwgps_confidence_boost = Column(Float, nullable=True)

    __table_args__ = (
        Index("ix_graph_edges_geom", "geom", postgresql_using="gist"),
    )


class POI(Base):
    """A point of interest — campsite, hotel, water, grocery, etc."""
    __tablename__ = "poi"

    id = Column(Integer, primary_key=True)
    type = Column(String(32), nullable=False, index=True)
    geom = Column(Geometry("POINT", srid=4326), nullable=False)
    name = Column(String(256), nullable=True)
    source = Column(String(32), nullable=False, default="osm")
    metadata_json = Column(JSON, nullable=True)
    confidence_score = Column(Float, nullable=False, default=1.0)
    subregion = Column(String(64), nullable=False, index=True)

    overnight_option = relationship("OvernightOption", back_populates="poi", uselist=False)

    __table_args__ = (
        Index("ix_poi_geom", "geom", postgresql_using="gist"),
    )


class OvernightOption(Base):
    """
    An overnight stop candidate.
    Tier 1 = official / high-confidence.
    Tier 2 = community-reported.
    Tier 3 = inferred dispersed-legal.
    """
    __tablename__ = "overnight_options"

    id = Column(Integer, primary_key=True)
    poi_id = Column(Integer, ForeignKey("poi.id"), nullable=False, unique=True)
    overnight_type = Column(String(32), nullable=False)
    tier = Column(Integer, nullable=False)
    legality_type = Column(String(32), nullable=False)
    reservation_known = Column(Boolean, nullable=False, default=False)
    seasonality_known = Column(Boolean, nullable=False, default=False)
    exact_site_known = Column(Boolean, nullable=False, default=False)
    confidence_score = Column(Float, nullable=False)

    poi = relationship("POI", back_populates="overnight_option")


class CandidateRoute(Base):
    """A fully assembled candidate route with metrics and scores."""
    __tablename__ = "candidate_routes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String, ForeignKey("trip_requests.id"), nullable=False, index=True)
    geometry = Column(Geometry("LINESTRING", srid=4326), nullable=True)
    total_distance_km = Column(Float, nullable=True)
    total_climbing_m = Column(Float, nullable=True)
    gravel_ratio = Column(Float, nullable=True)
    paved_ratio = Column(Float, nullable=True)
    uncertainty_km = Column(Float, nullable=True)
    overnight_plan_json = Column(JSON, nullable=True)
    route_metrics_json = Column(JSON, nullable=True)
    score_breakdown_json = Column(JSON, nullable=True)
    passed_filters = Column(Boolean, nullable=True)
    status = Column(String(32), nullable=False, default="pending")

    trip_request = relationship("TripRequest", back_populates="candidate_routes")
    final_route = relationship("FinalRoute", back_populates="candidate_route", uselist=False)

    __table_args__ = (
        Index("ix_candidate_routes_geom", "geometry", postgresql_using="gist"),
    )


class FinalRoute(Base):
    """A finalized route selected by the user, with GPX stored."""
    __tablename__ = "final_routes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String, ForeignKey("trip_requests.id"), nullable=False, index=True)
    candidate_route_id = Column(Integer, ForeignKey("candidate_routes.id"), nullable=False)
    gpx_blob_path = Column(String(512), nullable=True)
    final_summary_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    trip_request = relationship("TripRequest", back_populates="final_routes")
    candidate_route = relationship("CandidateRoute", back_populates="final_route")
