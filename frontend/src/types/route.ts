export type Archetype = "scenic" | "easier" | "adventurous";

export type ConfidenceLevel = "high" | "medium" | "low";

export type RiderFitness = "beginner" | "intermediate" | "advanced" | "expert";
export type TechnicalSkill = "novice" | "intermediate" | "advanced";
export type OvernightExperience = "new" | "some" | "experienced";
export type OvernightPreference = "camping" | "hotel" | "flexible";
export type RouteShape = "loop" | "out-and-back" | "point-to-point" | "any";

export interface RiderProfile {
  fitness: RiderFitness;
  technicalSkill: TechnicalSkill;
  overnightExperience: OvernightExperience;
}

export interface TripPreferences {
  overnightPreference: OvernightPreference;
  routeShape: RouteShape;
  groceryAccess: boolean;
  waterAccess: boolean;
  lowTraffic: boolean;
}

export interface TripRequest {
  prompt: string;
  riderProfile?: RiderProfile;
  preferences?: TripPreferences;
  origin?: string;
  days?: number;
}

export interface OvernightOption {
  id: string;
  name: string;
  type: "campsite" | "hotel" | "motel" | "dispersed";
  distance_from_route_km: number;
  description: string;
  amenities: string[];
  cost_estimate?: string;
  coordinates: [number, number];
  reservation_note?: string;
}

export interface OvernightArea {
  name: string;
  description: string;
  coordinates: [number, number];
  options: OvernightOption[];
  framing_note: string;
}

export interface TerrainNote {
  label: string;
  description: string;
  severity: "info" | "caution" | "warning";
}

export interface DaySegment {
  day: number;
  title: string;
  distance_km: number;
  climbing_m: number;
  gravel_ratio: number;
  estimated_hours: number;
  description: string;
  key_advice?: string;
  highlights: string[];
  terrain_notes: TerrainNote[];
  overnight_area?: OvernightArea;
  water_points: string[];
  grocery_points: string[];
}

export interface ScoreBreakdown {
  scenery: number;
  gravel_quality: number;
  safety: number;
  logistics: number;
  overall: number;
}

export interface Tradeoff {
  label: string;
  pro: string;
  con: string;
}

export interface RiderFitReason {
  icon_type: "check" | "warning" | "info";
  text: string;
}

export interface ConfidenceDetail {
  aspect: string;
  level: ConfidenceLevel;
  note: string;
}

export interface StravaHighlight {
  id: number;
  name: string;
  climb_category: string;
  avg_grade_pct: number;
  distance_km: number;
  elev_difference_m: number;
  strava_url: string;
}

export interface MapboxUsage {
  date: string;
  count: number;
  limit: number;
  remaining: number;
}

export interface RouteOption {
  id: string;
  archetype: Archetype;
  archetype_label: string;
  archetype_tagline: string;

  // AI-generated narrative fields (new)
  trip_title?: string;
  tagline?: string;
  summary: string;
  why_this_route: string;
  tradeoff_statement?: string;
  logistics_note?: string;
  confidence_framing?: string;

  // Metrics
  total_distance_km: number;
  total_climbing_m: number;
  gravel_ratio: number;
  estimated_days: number;

  score_breakdown: ScoreBreakdown;
  day_segments: DaySegment[];
  overnight_areas: OvernightArea[];

  // Strava integration (new)
  strava_highlights?: StravaHighlight[];

  grocery_distance_km: number;
  water_distance_km: number;
  hotel_fallback_distance_km: number;
  bailout_notes: string[];
  confidence_notes: string[];
  confidence_level: ConfidenceLevel;
  confidence_details: ConfidenceDetail[];
  tradeoffs: Tradeoff[];
  rider_fit_reasons: RiderFitReason[];
  gpx_url: string;
  geometry: [number, number][];
  mapbox_profile?: string;
}

export interface TripContext {
  parsed_region: string;
  parsed_duration: string;
  parsed_distance: string;
  parsed_gravel_target: string;
  key_constraints: string[];
  mapbox_usage?: MapboxUsage;
}

export interface GenerateResponse {
  request_id: string;
  trip_context: TripContext;
  routes: RouteOption[];
  no_results_reason?: string;
}
