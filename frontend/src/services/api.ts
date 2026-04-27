import type { TripRequest, GenerateResponse, RouteOption } from "../types/route";

export interface PoiItem {
  type: "water" | "campsite" | "bike_shop";
  lat: number;
  lon: number;
  name: string | null;
}

const API_BASE = process.env.REACT_APP_API_BASE || "http://localhost:8000/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

// Map frontend RiderProfile/TripPreferences to the backend's expected shape
function buildRequestBody(tripRequest: TripRequest) {
  const { prompt, riderProfile, preferences, origin, days } = tripRequest;

  const fitnessMap: Record<string, string> = {
    beginner: "beginner",
    intermediate: "intermediate",
    advanced: "strong",
    expert: "elite",
  };

  const skillMap: Record<string, string> = {
    novice: "low",
    intermediate: "medium",
    advanced: "high",
  };

  return {
    prompt,
    origin: origin || undefined,
    days: days || undefined,
    rider_profile: riderProfile
      ? {
          fitness_level: fitnessMap[riderProfile.fitness] ?? "intermediate",
          technical_skill: skillMap[riderProfile.technicalSkill] ?? "medium",
          overnight_experience: riderProfile.overnightExperience,
          comfort_daily_km: riderProfile.fitness === "beginner" ? 50 :
                            riderProfile.fitness === "intermediate" ? 75 :
                            riderProfile.fitness === "advanced" ? 100 : 130,
          comfort_daily_climbing_m: riderProfile.fitness === "beginner" ? 800 :
                                    riderProfile.fitness === "intermediate" ? 1200 :
                                    riderProfile.fitness === "advanced" ? 1800 : 2500,
          remote_tolerance: preferences?.lowTraffic ? "high" : "medium",
          bailout_preference: "medium",
        }
      : undefined,
    trip_preferences: preferences
      ? {
          scenic: false,
          minimize_traffic: preferences.lowTraffic,
          prefer_remote: false,
          hotel_allowed: preferences.overnightPreference === "hotel" || preferences.overnightPreference === "flexible",
          camping_required: preferences.overnightPreference === "camping",
          gravel_ratio: 0.5,
        }
      : undefined,
  };
}

export const api = {
  parse: (prompt: string) =>
    request("/parse", { method: "POST", body: JSON.stringify({ prompt }) }),

  generate: (tripRequest: TripRequest): Promise<GenerateResponse> =>
    request("/generate", { method: "POST", body: JSON.stringify(tripRequest) }),

  generateFull: (tripRequest: TripRequest | string): Promise<GenerateResponse> => {
    // Accept either a plain string (legacy) or a full TripRequest object
    const body = typeof tripRequest === "string"
      ? { prompt: tripRequest }
      : buildRequestBody(tripRequest);
    return request("/generate-full", { method: "POST", body: JSON.stringify(body) });
  },

  finalize: (routeId: string) =>
    request("/finalize", { method: "POST", body: JSON.stringify({ route_id: routeId }) }),

  getRoute: (id: string): Promise<RouteOption> =>
    request(`/route/${id}`),

  getGpxUrl: (id: string) => `${API_BASE}/route/${id}/gpx`,

  getMapboxUsage: () =>
    request<{ date: string; count: number; limit: number; remaining: number }>("/mapbox-usage"),

  getPois: (
    south: number,
    west: number,
    north: number,
    east: number,
    types = "water,campsite,bike_shop",
    routeCoords?: [number, number][]
  ): Promise<{ pois: PoiItem[] }> => {
    const p = new URLSearchParams({
      south: south.toString(),
      west: west.toString(),
      north: north.toString(),
      east: east.toString(),
      types,
    });
    if (routeCoords && routeCoords.length > 0) {
      // Sample to max 300 points to keep URL size reasonable
      const step = Math.max(1, Math.floor(routeCoords.length / 300));
      const sampled = routeCoords.filter((_, i) => i % step === 0);
      p.set("route", sampled.map(([lat, lon]) => `${lat},${lon}`).join("|"));
    }
    return request(`/pois?${p}`);
  },
};
