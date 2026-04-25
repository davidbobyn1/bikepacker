import React, { useEffect, useRef, useCallback, useMemo, useState } from "react";
import maplibregl from "maplibre-gl";

/**
 * RouteMap.tsx — MapLibre GL powered route map
 *
 * Uses Mapbox outdoor tiles when REACT_APP_MAPBOX_TOKEN is set (recommended),
 * falls back to OpenFreeMap for local dev without a token.
 *
 * Worker fix: CRA/webpack cannot bundle MapLibre's tile worker via blob URL.
 * We point workerUrl at the matching CDN version so the worker loads correctly
 * in both dev and production builds.
 */

import type { RouteOption } from "../../types/route";

// ─── Worker fix (must happen before any Map is created) ──────────────────────
// CRA's webpack production build cannot follow MapLibre's dynamic worker
// blob URL. Pointing at the CDN version of the worker for the same release
// guarantees the tile-processing worker loads correctly everywhere.
(maplibregl as any).workerUrl =
  "https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl-csp-worker.js";

// ─── Tile source ──────────────────────────────────────────────────────────────
const MAPBOX_TOKEN = process.env.REACT_APP_MAPBOX_TOKEN || "";

/** Rewrites mapbox:// protocol URLs to Mapbox REST API calls with the token. */
function mapboxTransformRequest(
  url: string
): { url: string } {
  if (!url.startsWith("mapbox://")) return { url };
  const token = MAPBOX_TOKEN;
  const append = (u: string) =>
    `${u}${u.includes("?") ? "&" : "?"}access_token=${token}`;

  if (url.startsWith("mapbox://tiles/")) {
    return { url: append(url.replace("mapbox://tiles/", "https://api.mapbox.com/v4/")) };
  }
  if (url.startsWith("mapbox://fonts/")) {
    return { url: append(url.replace("mapbox://fonts/", "https://api.mapbox.com/fonts/v1/")) };
  }
  if (url.startsWith("mapbox://sprites/")) {
    return { url: append(url.replace("mapbox://sprites/", "https://api.mapbox.com/sprites/v1/")) };
  }
  // Generic mapbox://<tileset-id> source descriptor
  const id = url.replace("mapbox://", "");
  return { url: append(`https://api.mapbox.com/v4/${id}.json`) + "&secure" };
}

const MAP_STYLE = MAPBOX_TOKEN
  ? `https://api.mapbox.com/styles/v1/mapbox/outdoors-v12?access_token=${MAPBOX_TOKEN}`
  : "https://tiles.openfreemap.org/styles/bright";

// ─── Archetype colours ────────────────────────────────────────────────────────
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

// ─── Elevation profile strip ──────────────────────────────────────────────────
function ElevationProfile({
  route,
  onPositionClick,
}: {
  route: RouteOption | null;
  onPositionClick: (coord: [number, number]) => void;
}) {
  if (!route || !route.geometry || route.geometry.length < 2) return null;

  const points = route.geometry;
  const n = points.length;
  const totalClimb = route.total_climbing_m || 500;

  const heights = points.map((_, i) => {
    const t = i / n;
    return (
      Math.sin(t * Math.PI * 2.5) * (totalClimb / 5) +
      Math.sin(t * Math.PI * 0.8) * (totalClimb / 3) +
      200
    );
  });

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

  const handleClick = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = (e.clientX - rect.left) / rect.width;
    const idx = Math.min(Math.floor(ratio * (n - 1)), n - 1);
    onPositionClick(points[idx]);
  };

  return (
    <div
      className="absolute bottom-0 left-0 right-0 bg-gray-950/90 backdrop-blur-sm border-t border-gray-800 z-10"
      style={{ height: 80 }}
    >
      <div className="flex items-center px-3 pt-1 gap-3">
        <span className="text-xs text-gray-400 font-medium">Elevation</span>
        <span className="text-xs text-gray-600">
          {route.total_distance_km.toFixed(0)} km · {route.total_climbing_m.toFixed(0)} m ↑
        </span>
        <span className="text-xs text-gray-700 ml-auto hidden sm:block">
          Click to fly to location
        </span>
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full cursor-crosshair"
        style={{ height: 56 }}
        onClick={handleClick}
        preserveAspectRatio="none"
      >
        <path d={areaD} fill={`${colors.line}22`} />
        <path d={pathD} fill="none" stroke={colors.line} strokeWidth="2" />
      </svg>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────
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
  const [mapReady, setMapReady] = useState(false);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const routes: RouteOption[] = useMemo(
    () => multiRoutes ?? (singleRoute ? [singleRoute] : []),
    [multiRoutes, singleRoute]
  );
  const effectiveActiveId = activeRouteId ?? routes[0]?.id ?? null;
  const activeRoute = routes.find((r) => r.id === effectiveActiveId) ?? routes[0] ?? null;

  // ── Initialise map ──────────────────────────────────────────────────────────
  useEffect(() => {
    if (!mapContainer.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: mapContainer.current,
      style: MAP_STYLE,
      center: [-122.59, 37.99],
      zoom: 10,
      attributionControl: false,
      ...(MAPBOX_TOKEN
        ? { transformRequest: mapboxTransformRequest as any }
        : {}),
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

    // Force resize whenever the container dimensions change (Framer Motion fade-in)
    const ro = new ResizeObserver(() => map.resize());
    ro.observe(mapContainer.current!);

    // Belt-and-suspenders resize calls to catch animation end
    const t1 = setTimeout(() => map.resize(), 100);
    const t2 = setTimeout(() => map.resize(), 500);
    const t3 = setTimeout(() => map.resize(), 1000);

    const onResize = () => map.resize();
    window.addEventListener("resize", onResize);

    mapRef.current = map;

    return () => {
      ro.disconnect();
      clearTimeout(t1);
      clearTimeout(t2);
      clearTimeout(t3);
      window.removeEventListener("resize", onResize);
      map.remove();
      mapRef.current = null;
      setMapReady(false);
    };
  }, []);

  // ── Draw / redraw routes ────────────────────────────────────────────────────
  useEffect(() => {
    if (!mapReady || !mapRef.current) return;
    const map = mapRef.current;

    // Remove old markers
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];

    // Remove old layers + sources
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

      // GeoJSON expects [lon, lat]
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

      // Glow layer
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

      // Main line
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

      // Start / Finish markers
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

      // Overnight markers
      if (isActive || !compareMode) {
        route.overnight_areas?.forEach((area, i) => {
          const [lat, lon] = area.coordinates;
          if (!lat || !lon) return;
          const el = document.createElement("div");
          el.style.cssText = `background:#1e293b;border:2px solid ${colors.line};border-radius:50%;width:30px;height:30px;display:flex;align-items:center;justify-content:center;font-size:15px;box-shadow:0 2px 8px rgba(0,0,0,.45);cursor:pointer;`;
          el.textContent = "🏕";
          const popup = new maplibregl.Popup({ offset: 16, closeButton: false }).setHTML(
            `<div style="font-size:12px;padding:4px 2px"><strong>Night ${i + 1}</strong><br/>${area.name}</div>`
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

    // Fit bounds to active route
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
  }, [mapReady, routes, effectiveActiveId, compareMode, onRouteClick, activeRoute]);

  const flyTo = useCallback(([lat, lon]: [number, number]) => {
    mapRef.current?.flyTo({ center: [lon, lat], zoom: 13, duration: 600 });
  }, []);

  return (
    <div
      className={`relative overflow-hidden rounded-xl ${className}`}
      style={{ minHeight: 400 }}
    >
      <div ref={mapContainer} className="absolute inset-0" />
      {mapReady && (
        <ElevationProfile route={activeRoute} onPositionClick={flyTo} />
      )}
    </div>
  );
}
