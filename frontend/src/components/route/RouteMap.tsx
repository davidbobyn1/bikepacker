import React, { useEffect, useRef, useCallback, useMemo, useState } from "react";
import maplibregl from "maplibre-gl";

import type { RouteOption } from "../../types/route";
import { api, type PoiItem } from "../../services/api";

/**
 * RouteMap.tsx — MapLibre GL powered route map
 *
 * Basemap: CARTO Voyager raster tiles (muted, no auth required)
 * Elevation: OpenTopoData SRTM90m API (free, no key, ≤100 pts/batch)
 * Cursor sync: hover on elevation strip → dot marker moves on map
 */

// ─── Worker fix (must run before any Map is created) ─────────────────────────
(maplibregl as any).workerUrl =
  "https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl-csp-worker.js";

// ─── Inline style (CARTO Voyager — muted colours, no auth) ───────────────────
const CARTO_STYLE: any = {
  version: 8,
  sources: {
    "carto-voyager": {
      type: "raster",
      tiles: [
        "https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
        "https://b.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
        "https://c.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
        "https://d.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
      ],
      tileSize: 256,
      attribution:
        '© <a href="https://carto.com/">CARTO</a> © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxzoom: 19,
    },
  },
  layers: [
    {
      id: "carto-voyager",
      type: "raster",
      source: "carto-voyager",
      minzoom: 0,
      maxzoom: 22,
    },
  ],
};

// ─── Additional basemap styles ────────────────────────────────────────────────
const ESRI_SATELLITE_STYLE: any = {
  version: 8,
  sources: {
    "esri-satellite": {
      type: "raster",
      // ESRI tile order is {z}/{y}/{x} — intentionally different from CARTO
      tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
      tileSize: 256,
      attribution: "© Esri, Maxar, Earthstar Geographics, USDA FSA, USGS, Aerogrid, IGN, IGP, and the GIS User Community",
      maxzoom: 19,
    },
  },
  layers: [{ id: "esri-satellite", type: "raster", source: "esri-satellite", minzoom: 0, maxzoom: 22 }],
};

const OPENTOPOMAP_STYLE: any = {
  version: 8,
  sources: {
    "opentopomap": {
      type: "raster",
      tiles: ["https://tile.opentopomap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: '© <a href="https://opentopomap.org">OpenTopoMap</a> (CC-BY-SA)',
      maxzoom: 17,
    },
  },
  layers: [{ id: "opentopomap", type: "raster", source: "opentopomap", minzoom: 0, maxzoom: 22 }],
};

const BASEMAP_OPTIONS = [
  { key: "voyager",   emoji: "🗺️",  label: "Map",       style: CARTO_STYLE },
  { key: "satellite", emoji: "🛰️",  label: "Satellite", style: ESRI_SATELLITE_STYLE },
  { key: "topo",      emoji: "⛰️",  label: "Topo",      style: OPENTOPOMAP_STYLE },
] as const;
type BasemapKey = typeof BASEMAP_OPTIONS[number]["key"];

// ─── Component types ─────────────────────────────────────────────────────────
interface RouteMapProps {
  route?: RouteOption;
  routes?: RouteOption[];
  activeRouteId?: string | null;
  compareMode?: boolean;
  onRouteClick?: (routeId: string) => void;
  className?: string;
}

const ARCHETYPE_COLORS: Record<string, { line: string; glow: string }> = {
  scenic:      { line: "#f59e0b", glow: "#fcd34d" },
  easier:      { line: "#3b82f6", glow: "#93c5fd" },
  adventurous: { line: "#10b981", glow: "#6ee7b7" },
};
const INACTIVE_COLOR = "#94a3b8";

// ─── POI toggle config ────────────────────────────────────────────────────────
const POI_TOGGLES: { type: PoiItem["type"]; emoji: string; label: string; color: string }[] = [
  { type: "water",     emoji: "💧", label: "Water",     color: "#3b82f6" },
  { type: "campsite",  emoji: "⛺", label: "Campsites", color: "#10b981" },
  { type: "bike_shop", emoji: "🚲", label: "Bike shops", color: "#f59e0b" },
];

//// ─── Elevation fetch (proxied via backend → OpenTopoData SRTM90m) ────────────
// Direct browser calls to opentopodata.org are blocked by CORS; the backend
// proxy at /api/elevation forwards the request server-side.
const ELEV_API = `${process.env.REACT_APP_API_BASE || "http://localhost:8000/api"}/elevation`;

async function fetchElevation(geometry: [number, number][]): Promise<number[]> {
  // Sample to ≤100 pts for the API batch limit, then interpolate back
  const n = geometry.length;
  const step = Math.max(1, Math.floor(n / 100));
  const sampled = geometry.filter((_, i) => i % step === 0);
  const res = await fetch(ELEV_API, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      locations: sampled.map(([lat, lon]) => [lat, lon]),
    }),
  });
  if (!res.ok) throw new Error(`elevation proxy error: ${res.status}`);
  const data = await res.json();
  const sampledElevs: number[] = data.elevations;

  // Linear interpolation back to full-length array
  const full: number[] = [];
  for (let i = 0; i < sampledElevs.length; i++) {
    const eA = sampledElevs[i];
    const eB = sampledElevs[i + 1] ?? eA;
    const count = i === sampledElevs.length - 1 ? n - full.length : step;
    for (let j = 0; j < count; j++) {
      full.push(eA + (eB - eA) * (j / step));
    }
  }
  return full.slice(0, n);
}

// Synthetic fallback — keeps the strip visible while fetch is in progress
function syntheticElevation(geometry: [number, number][], totalClimbM: number): number[] {
  const n = geometry.length;
  return geometry.map((_, i) => {
    const t = i / n;
    return (
      Math.sin(t * Math.PI * 2.5) * (totalClimbM / 5) +
      Math.sin(t * Math.PI * 0.8) * (totalClimbM / 3) +
      200
    );
  });
}

// ─── Elevation profile strip ─────────────────────────────────────────────────
function ElevationProfile({
  route,
  elevationData,
  onPositionClick,
  onHover,
  mapHoverIdx,
}: {
  route: RouteOption | null;
  elevationData: number[] | null;
  onPositionClick: (coord: [number, number]) => void;
  onHover: (coord: [number, number] | null) => void;
  mapHoverIdx: number | null;
}) {
  if (!route || !route.geometry || route.geometry.length < 2) return null;

  const points = route.geometry;
  const n = points.length;
  const heights =
    elevationData ??
    syntheticElevation(points, route.total_climbing_m || 500);

  const maxH = Math.max(...heights);
  const minH = Math.min(...heights);
  const range = maxH - minH || 1;
  const W = 1000;
  const H = 56;

  const pathD = heights
    .map((h, i) => {
      const x = (i / (n - 1)) * W;
      const y = H - ((h - minH) / range) * H;
      return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");

  const areaD = `${pathD} L ${W} ${H} L 0 ${H} Z`;
  const colors = ARCHETYPE_COLORS[route.archetype] ?? ARCHETYPE_COLORS.scenic;

  const getCoordAtEvent = (e: React.MouseEvent<SVGSVGElement>): [number, number] => {
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const idx = Math.min(Math.floor(ratio * (n - 1)), n - 1);
    return points[idx];
  };

  const elevGainLabel = elevationData
    ? `${Math.round(maxH - minH)} m ↑`
    : `~${route.total_climbing_m.toFixed(0)} m ↑`;

  return (
    <div
      className="absolute bottom-0 left-0 right-0 bg-gray-950/90 backdrop-blur-sm border-t border-gray-800 z-10"
      style={{ height: 80 }}
    >
      <div className="flex items-center px-3 pt-1 gap-3">
        <span className="text-xs text-gray-400 font-medium">Elevation</span>
        <span className="text-xs text-gray-600">
          {route.total_distance_km.toFixed(0)} km · {elevGainLabel}
        </span>
        {!elevationData && (
          <span className="text-xs text-gray-700 italic">loading real data…</span>
        )}
        <span className="text-xs text-gray-700 ml-auto hidden sm:block">
          Click or hover to explore
        </span>
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full cursor-crosshair"
        style={{ height: 56 }}
        onClick={(e) => onPositionClick(getCoordAtEvent(e))}
        onMouseMove={(e) => onHover(getCoordAtEvent(e))}
        onMouseLeave={() => onHover(null)}
        preserveAspectRatio="none"
      >
        <path d={areaD} fill={`${colors.line}22`} />
        <path d={pathD} fill="none" stroke={colors.line} strokeWidth="2" />
        {mapHoverIdx !== null && (() => {
          const x = (mapHoverIdx / (n - 1)) * W;
          const h = heights[mapHoverIdx];
          const y = H - ((h - minH) / range) * H;
          return (
            <>
              <line x1={x} y1={0} x2={x} y2={H} stroke="#fff" strokeWidth="1" strokeOpacity={0.6} strokeDasharray="3 2" />
              <circle cx={x} cy={y} r={3} fill={colors.line} stroke="#fff" strokeWidth="1.5" />
            </>
          );
        })()}
      </svg>
    </div>
  );
}

// ─── Main component ──────────────────────────────────────────────────────────
export default function RouteMap({
  route: singleRoute,
  routes: multiRoutes,
  activeRouteId,
  compareMode = false,
  onRouteClick,
  className = "",
}: RouteMapProps) {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);
  const poiMarkersRef = useRef<maplibregl.Marker[]>([]);
  const hoverMarkerRef = useRef<maplibregl.Marker | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const [elevationData, setElevationData] = useState<number[] | null>(null);
  const [elevHoverIdx, setElevHoverIdx] = useState<number | null>(null);
  const elevHoverIdxRef = useRef<number | null>(null);
  const [pois, setPois] = useState<PoiItem[]>([]);
  const [visibleTypes, setVisibleTypes] = useState<Set<PoiItem["type"]>>(
    new Set(["water", "campsite", "bike_shop"] as PoiItem["type"][])
  );
  const [basemap, setBasemap] = useState<BasemapKey>("voyager");

  const routes: RouteOption[] = useMemo(
    () => multiRoutes ?? (singleRoute ? [singleRoute] : []),
    [multiRoutes, singleRoute]
  );
  const effectiveActiveId = activeRouteId ?? routes[0]?.id ?? null;
  const activeRoute = routes.find((r) => r.id === effectiveActiveId) ?? routes[0] ?? null;

  // ── Fetch real elevation whenever active route changes ─────────────────────
  useEffect(() => {
    if (!activeRoute?.geometry?.length) return;
    setElevationData(null); // clear stale data while fetching

    let cancelled = false;
    fetchElevation(activeRoute.geometry)
      .then((data) => { if (!cancelled) setElevationData(data); })
      .catch(() => { /* fall back to synthetic — no-op */ });

    return () => { cancelled = true; };
  }, [activeRoute?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Fetch POIs when active route changes ──────────────────────────────────
  useEffect(() => {
    if (!activeRoute?.geometry?.length) return;

    const lats = activeRoute.geometry.map(([lat]) => lat);
    const lons = activeRoute.geometry.map(([, lon]) => lon);
    const pad = 0.04; // ~4 km padding around route bounds
    const south = Math.min(...lats) - pad;
    const north = Math.max(...lats) + pad;
    const west  = Math.min(...lons) - pad;
    const east  = Math.max(...lons) + pad;

    let cancelled = false;
    api.getPois(south, west, north, east, "water,campsite,bike_shop", activeRoute.geometry)
      .then((data) => {
        if (!cancelled) {
          console.debug(`[POI] Loaded ${data.pois.length} POIs for route ${activeRoute.id}`);
          setPois(data.pois);
        }
      })
      .catch((err) => {
        // Log so we can diagnose Overpass/backend failures
        console.error("[POI] Failed to fetch POIs:", err);
      });

    return () => { cancelled = true; };
  }, [activeRoute?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Draw / remove POI markers whenever pois or visibility toggles change ──
  useEffect(() => {
    if (!mapReady || !mapRef.current) return;
    const map = mapRef.current;

    // Remove all existing POI markers
    poiMarkersRef.current.forEach((m) => m.remove());
    poiMarkersRef.current = [];

    pois.forEach((poi) => {
      if (!visibleTypes.has(poi.type)) return;

      const cfg = POI_TOGGLES.find((t) => t.type === poi.type);
      if (!cfg) return;

      const el = document.createElement("div");
      el.style.cssText = [
        `background:#1e293b;`,
        `border:2px solid ${cfg.color};`,
        `border-radius:50%;`,
        `width:26px;height:26px;`,
        `display:flex;align-items:center;justify-content:center;`,
        `font-size:13px;`,
        `box-shadow:0 2px 6px rgba(0,0,0,.4);`,
        `cursor:pointer;`,
      ].join("");
      el.textContent = cfg.emoji;

      const popupHtml = `
        <div style="font-size:12px;padding:3px 2px;min-width:80px">
          <strong>${poi.name ?? cfg.label}</strong>
          ${poi.name ? `<br/><span style="color:#94a3b8">${cfg.label}</span>` : ""}
        </div>`;

      const popup = new maplibregl.Popup({ offset: 14, closeButton: false }).setHTML(popupHtml);

      poiMarkersRef.current.push(
        new maplibregl.Marker({ element: el })
          .setLngLat([poi.lon, poi.lat])
          .setPopup(popup)
          .addTo(map)
      );
    });
  }, [mapReady, pois, visibleTypes]);

  // ── Initialise map (synchronous — no async, no fetch) ──────────────────────
  useEffect(() => {
    if (!mapContainer.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: mapContainer.current,
      style: CARTO_STYLE,
      center: [-122.59, 37.99],
      zoom: 10,
      attributionControl: false,
    });

    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.addControl(
      new maplibregl.AttributionControl({ compact: true }),
      "bottom-right"
    );

    map.on("load", () => {
      map.resize();
      setMapReady(true);
    });

    const ro = new ResizeObserver(() => map.resize());
    ro.observe(mapContainer.current);

    let resizeFrames = 0;
    const resizeLoop = () => {
      if (!mapRef.current || resizeFrames > 60) return;
      map.resize();
      resizeFrames++;
      requestAnimationFrame(resizeLoop);
    };
    requestAnimationFrame(resizeLoop);

    const t1 = setTimeout(() => map.resize(), 100);
    const t2 = setTimeout(() => map.resize(), 500);
    const t3 = setTimeout(() => map.resize(), 1500);

    const onResize = () => map.resize();
    window.addEventListener("resize", onResize);

    mapRef.current = map;

    return () => {
      ro.disconnect();
      clearTimeout(t1);
      clearTimeout(t2);
      clearTimeout(t3);
      window.removeEventListener("resize", onResize);
      poiMarkersRef.current.forEach((m) => m.remove());
      poiMarkersRef.current = [];
      map.remove();
      mapRef.current = null;
      setMapReady(false);
    };
  }, []);

  // ── Hover marker (created once map is ready) ───────────────────────────────
  useEffect(() => {
    if (!mapReady || !mapRef.current) return;

    const el = document.createElement("div");
    el.style.cssText =
      "width:12px;height:12px;border-radius:50%;background:#fff;border:2.5px solid #2563eb;box-shadow:0 2px 6px rgba(0,0,0,.5);pointer-events:none;display:none;";

    const marker = new maplibregl.Marker({ element: el })
      .setLngLat([0, 0])
      .addTo(mapRef.current);

    hoverMarkerRef.current = marker;

    return () => {
      marker.remove();
      hoverMarkerRef.current = null;
    };
  }, [mapReady]);

  // ── Swap basemap style ────────────────────────────────────────────────────
  useEffect(() => {
    if (!mapReady || !mapRef.current) return;
    const selected = BASEMAP_OPTIONS.find((b) => b.key === basemap);
    if (selected) mapRef.current.setStyle(selected.style);
  }, [mapReady, basemap]);

  // ── Draw / redraw routes ───────────────────────────────────────────────────
  useEffect(() => {
    if (!mapReady || !mapRef.current) return;
    const map = mapRef.current;

    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];

    const style = map.getStyle();
    (style?.layers ?? []).forEach((layer) => {
      if (layer.id.startsWith("bp-route-")) map.removeLayer(layer.id);
    });
    Object.keys(style?.sources ?? {}).forEach((id) => {
      if (id.startsWith("bp-route-")) map.removeSource(id);
    });

    const toDraw = compareMode
      ? routes
      : routes.filter((r) => r.id === effectiveActiveId);

    toDraw.forEach((route) => {
      if (!route.geometry?.length) return;
      const isActive = route.id === effectiveActiveId;
      const colors = ARCHETYPE_COLORS[route.archetype] ?? ARCHETYPE_COLORS.scenic;
      const lineColor = compareMode && !isActive ? INACTIVE_COLOR : colors.line;
      const lineWidth = isActive ? 4 : 2;
      const opacity = compareMode && !isActive ? 0.45 : 1;

      const coordinates = route.geometry.map(([lat, lon]) => [lon, lat]);
      const sourceId = `bp-route-${route.id}`;

      map.addSource(sourceId, {
        type: "geojson",
        data: {
          type: "Feature",
          properties: { routeId: route.id },
          geometry: { type: "LineString", coordinates },
        },
      });

      map.addLayer({
        id: `bp-route-glow-${route.id}`,
        type: "line",
        source: sourceId,
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": colors.glow,
          "line-width": lineWidth + 8,
          "line-opacity": opacity * 0.25,
          "line-blur": 6,
        },
      });

      map.addLayer({
        id: `bp-route-line-${route.id}`,
        type: "line",
        source: sourceId,
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": lineColor,
          "line-width": lineWidth,
          "line-opacity": opacity,
        },
      });

      map.on("click", `bp-route-line-${route.id}`, () =>
        onRouteClick?.(route.id)
      );
      map.on("mouseenter", `bp-route-line-${route.id}`, () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", `bp-route-line-${route.id}`, () => {
        map.getCanvas().style.cursor = "";
      });

      if (isActive && coordinates.length >= 2) {
        const makeEndEl = (label: string, bg: string) => {
          const el = document.createElement("div");
          el.style.cssText = `background:${bg};color:#fff;font-weight:700;font-size:11px;width:26px;height:26px;border-radius:50%;border:2px solid #fff;display:flex;align-items:center;justify-content:center;box-shadow:0 2px 6px rgba(0,0,0,.5);`;
          el.textContent = label;
          return el;
        };
        const [sLon, sLat] = coordinates[0];
        const [fLon, fLat] = coordinates[coordinates.length - 1];
        markersRef.current.push(
          new maplibregl.Marker({ element: makeEndEl("S", "#16a34a") })
            .setLngLat([sLon, sLat])
            .addTo(map),
          new maplibregl.Marker({ element: makeEndEl("F", "#dc2626") })
            .setLngLat([fLon, fLat])
            .addTo(map)
        );
      }

      if (isActive || !compareMode) {
        route.overnight_areas?.forEach((area, i) => {
          const [lat, lon] = area.coordinates;
          if (!lat || !lon) return;

          // Pick icon based on overnight type from matching day segment
          const seg = route.day_segments?.[i];
          const firstOption = seg?.overnight_area?.options?.[0];
          const oType = firstOption?.type ?? "campsite";
          const isHotel = oType === "hotel" || oType === "motel";
          const icon = isHotel ? "🏨" : "⛺";

          // Pill marker: [N1 ⛺]
          const el = document.createElement("div");
          el.style.cssText = [
            "display:flex",
            "align-items:center",
            "gap:3px",
            `background:${colors.line}`,
            "color:#fff",
            "font-size:11px",
            "font-weight:700",
            "font-family:system-ui,sans-serif",
            "padding:3px 8px 3px 7px",
            "border-radius:99px",
            "border:2px solid #fff",
            "box-shadow:0 2px 8px rgba(0,0,0,.55)",
            "cursor:pointer",
            "white-space:nowrap",
            "user-select:none",
          ].join(";");
          el.innerHTML = `<span>N${i + 1}</span><span style="font-size:13px;line-height:1;margin-left:2px">${icon}</span>`;

          // Rich popup
          const optCount = area.options?.length ?? (seg?.overnight_area?.options?.length ?? 0);
          const optLabel = optCount > 1
            ? `${optCount} options · tap card for details`
            : isHotel ? "Hotel / lodging" : oType === "dispersed" ? "Dispersed camping" : "Campsite";
          const popup = new maplibregl.Popup({ offset: 18, closeButton: false, maxWidth: "220px" }).setHTML(
            `<div style="font-family:system-ui,sans-serif;font-size:12px;padding:2px 0">`
            + `<div style="font-weight:700;font-size:13px;margin-bottom:3px">Night ${i + 1} — ${area.name}</div>`
            + `<div style="color:#64748b;font-size:11px">${optLabel}</div>`
            + `</div>`
          );
          markersRef.current.push(
            new maplibregl.Marker({ element: el })
              .setLngLat([lon, lat])
              .setPopup(popup)
              .addTo(map)
          );
        });
      }
    });

    if (activeRoute?.geometry?.length) {
      const lons = activeRoute.geometry.map(([, lon]) => lon);
      const lats = activeRoute.geometry.map(([lat]) => lat);
      map.fitBounds(
        [
          [Math.min(...lons), Math.min(...lats)],
          [Math.max(...lons), Math.max(...lats)],
        ],
        { padding: { top: 50, bottom: 90, left: 40, right: 40 }, duration: 700 }
      );
    }
  // basemap included: setStyle() wipes custom layers, so we must redraw routes after a swap
  }, [mapReady, routes, effectiveActiveId, compareMode, onRouteClick, activeRoute, basemap]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Map mousemove → highlight position on elevation strip ─────────────────
  useEffect(() => {
    if (!mapReady || !mapRef.current || !activeRoute?.geometry?.length) return;
    const map = mapRef.current;
    const geom = activeRoute.geometry; // [lat, lon][]
    const n = geom.length;

    const onMove = (e: maplibregl.MapMouseEvent) => {
      const { lng, lat } = e.lngLat;
      // Find nearest geometry index using haversine approximation
      let bestIdx = 0;
      let bestDist = Infinity;
      const step = Math.max(1, Math.floor(n / 300)); // sample for perf
      for (let i = 0; i < n; i += step) {
        const [glat, glon] = geom[i];
        const d = (glat - lat) ** 2 + (glon - lng) ** 2;
        if (d < bestDist) { bestDist = d; bestIdx = i; }
      }
      if (elevHoverIdxRef.current !== bestIdx) {
        elevHoverIdxRef.current = bestIdx;
        setElevHoverIdx(bestIdx);
      }
    };
    const onLeave = () => {
      elevHoverIdxRef.current = null;
      setElevHoverIdx(null);
    };

    map.on("mousemove", onMove);
    map.on("mouseleave", onLeave);
    return () => {
      map.off("mousemove", onMove);
      map.off("mouseleave", onLeave);
    };
  }, [mapReady, activeRoute?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Elevation click → fly to ───────────────────────────────────────────────
  const flyTo = useCallback(([lat, lon]: [number, number]) => {
    mapRef.current?.flyTo({ center: [lon, lat], zoom: 13, duration: 600 });
  }, []);

  // ── Elevation hover → move dot marker ─────────────────────────────────────
  const handleElevHover = useCallback((coord: [number, number] | null) => {
    const marker = hoverMarkerRef.current;
    if (!marker) return;
    if (!coord) {
      marker.getElement().style.display = "none";
    } else {
      const [lat, lon] = coord;
      marker.setLngLat([lon, lat]);
      marker.getElement().style.display = "";
    }
  }, []);

  return (
    <div
      className={`relative rounded-xl overflow-hidden ${className}`}
      style={{ height: 520, minHeight: 400, width: "100%" }}
    >
      <div
        ref={mapContainer}
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          width: "100%",
          height: "100%",
        }}
      />
      <style>{`
        .maplibregl-map { width: 100% !important; height: 100% !important; position: absolute !important; inset: 0 !important; }
        .maplibregl-canvas-container { width: 100% !important; height: 100% !important; }
        .maplibregl-canvas { width: 100% !important; height: 100% !important; }
      `}</style>
      {/* Map controls — top-left, stays out of nav controls (top-right) */}
      {mapReady && (
        <div className="absolute top-3 left-3 z-10 flex flex-col gap-1.5">
          {/* POI layer toggles */}
          <div className="flex gap-1.5 flex-wrap">
            {POI_TOGGLES.map(({ type, emoji, label }) => {
              const active = visibleTypes.has(type);
              return (
                <button
                  key={type}
                  onClick={() =>
                    setVisibleTypes((prev) => {
                      const next = new Set(prev) as Set<PoiItem["type"]>;
                      if (next.has(type)) next.delete(type);
                      else next.add(type);
                      return next;
                    })
                  }
                  style={{
                    background: active ? "rgba(15,23,42,0.88)" : "rgba(15,23,42,0.50)",
                    border: `1px solid ${active ? "rgba(148,163,184,0.5)" : "rgba(71,85,105,0.4)"}`,
                    backdropFilter: "blur(6px)",
                  }}
                  className={`flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium transition-all ${
                    active ? "text-white" : "text-slate-500"
                  }`}
                >
                  <span>{emoji}</span>
                  <span className="hidden sm:inline">{label}</span>
                </button>
              );
            })}
          </div>

          {/* Basemap style toggle */}
          <div className="flex gap-1.5 flex-wrap">
            {BASEMAP_OPTIONS.map(({ key, emoji, label }) => (
              <button
                key={key}
                onClick={() => setBasemap(key)}
                style={{
                  background: basemap === key ? "rgba(15,23,42,0.92)" : "rgba(15,23,42,0.50)",
                  border: `1px solid ${basemap === key ? "rgba(99,102,241,0.7)" : "rgba(71,85,105,0.4)"}`,
                  backdropFilter: "blur(6px)",
                }}
                className={`flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium transition-all ${
                  basemap === key ? "text-white" : "text-slate-500"
                }`}
              >
                <span>{emoji}</span>
                <span className="hidden sm:inline">{label}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {mapReady && (
        <ElevationProfile
          route={activeRoute}
          elevationData={elevationData}
          onPositionClick={flyTo}
          onHover={handleElevHover}
          mapHoverIdx={elevHoverIdx}
        />
      )}
    </div>
  );
}
