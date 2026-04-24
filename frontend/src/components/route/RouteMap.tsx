import React, { useState, useEffect, useRef, useCallback, useMemo } from "react";
/**
 * RouteMap.tsx — MapLibre GL powered route map
 *
 * Uses Mapbox's outdoor tiles (via MapLibre GL JS) for beautiful terrain rendering.
 * Features:
 *  - Full-bleed map with color-coded route polylines per archetype
 *  - Overnight stop markers with popups
 *  - "Compare Routes" mode: all options overlaid simultaneously
 *  - Interactive elevation profile pinned to the bottom — click to fly to location
 *  - Glow effect on active route for visual clarity
 *
 * Props:
 *  - routes: all route options to potentially draw
 *  - activeRouteId: which route is currently selected
 *  - compareMode: if true, draw all routes simultaneously
 *  - onRouteClick: called when user clicks a route line
 *  - mapboxToken: Mapbox public token (from VITE_MAPBOX_TOKEN)
 *  - className: optional CSS class for the container div
 */

import type { RouteOption } from "../../types/route";

// We load MapLibre dynamically to avoid SSR issues

interface RouteMapProps {
  route?: RouteOption;           // single-route mode (legacy compat)
  routes?: RouteOption[];        // multi-route mode
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

// ---------------------------------------------------------------------------
// Elevation Profile Strip
// ---------------------------------------------------------------------------

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

  // Simulate elevation profile shape from climbing data
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
    <div className="absolute bottom-0 left-0 right-0 bg-gray-950/90 backdrop-blur-sm border-t border-gray-800 z-10" style={{ height: 80 }}>
      <div className="flex items-center px-3 pt-1 gap-3">
        <span className="text-xs text-gray-400 font-medium">Elevation</span>
        <span className="text-xs text-gray-600">
          {route.total_distance_km.toFixed(0)} km · {route.total_climbing_m.toFixed(0)} m ↑
        </span>
        <span className="text-xs text-gray-700 ml-auto hidden sm:block">Click to fly to location</span>
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

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function RouteMap({
  route: singleRoute,
  routes: multiRoutes,
  activeRouteId,
  compareMode = false,
  onRouteClick,
  className = "",
}: RouteMapProps) {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<InstanceType<typeof import("maplibre-gl").Map> | null>(null);
  const markersRef = useRef<Array<InstanceType<typeof import("maplibre-gl").Marker>>>([]);
  const [mapReady, setMapReady] = useState(false);
  const [mlgl, setMlgl] = useState<typeof import("maplibre-gl") | null>(null);

  // Normalise: support both single-route (legacy) and multi-route modes
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const routes: RouteOption[] = useMemo(() => multiRoutes ?? (singleRoute ? [singleRoute] : []), [multiRoutes, singleRoute]);
  const effectiveActiveId = activeRouteId ?? routes[0]?.id ?? null;
  const activeRoute = routes.find((r) => r.id === effectiveActiveId) ?? routes[0] ?? null;

  // Load MapLibre dynamically
  useEffect(() => {
    import("maplibre-gl").then((mod) => {
      setMlgl(mod);
    });
  }, []);

  // Initialise map once MapLibre is loaded
  useEffect(() => {
    if (!mlgl || !mapContainer.current || mapRef.current) return;

    let cancelled = false;

    fetch("https://tiles.openfreemap.org/styles/bright")
      .then((r) => r.json())
      .then((style) => {
        if (cancelled || !mapContainer.current) return;
        const map = new mlgl.Map({
          container: mapContainer.current,
          style,
          center: [-122.59, 37.99],
          zoom: 10,
          attributionControl: false,
        });
        map.addControl(new mlgl.NavigationControl(), "top-right");
        map.addControl(new mlgl.AttributionControl({ compact: true }), "bottom-right");
        map.on("load", () => setMapReady(true));
        mapRef.current = map;
      });

    return () => {
      cancelled = true;
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
        setMapReady(false);
      }
    };
  }, [mlgl]);

  // Draw routes whenever data or mode changes
  useEffect(() => {
    if (!mapReady || !mapRef.current || !mlgl) return;
    const map = mapRef.current;

    // Clear old markers
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];

    // Remove old route layers/sources
    const style = map.getStyle();
    (style?.layers ?? []).forEach((layer) => {
      if (layer.id.startsWith("bp-route-")) map.removeLayer(layer.id);
    });
    Object.keys(style?.sources ?? {}).forEach((id) => {
      if (id.startsWith("bp-route-")) map.removeSource(id);
    });

    const toDraw = compareMode ? routes : routes.filter((r) => r.id === effectiveActiveId);

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

      // Glow
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

      map.on("click", `bp-route-line-${route.id}`, () => onRouteClick?.(route.id));
      map.on("mouseenter", `bp-route-line-${route.id}`, () => { map.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", `bp-route-line-${route.id}`, () => { map.getCanvas().style.cursor = ""; });

      // Start / Finish markers for active route
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
          new mlgl!.Marker({ element: makeEndEl("S", "#16a34a") }).setLngLat([sLon, sLat]).addTo(map),
          new mlgl!.Marker({ element: makeEndEl("F", "#dc2626") }).setLngLat([fLon, fLat]).addTo(map),
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
          const popup = new mlgl!.Popup({ offset: 16, closeButton: false })
            .setHTML(`<div style="font-size:12px;padding:4px 2px"><strong>Night ${i + 1}</strong><br/>${area.name}</div>`);
          markersRef.current.push(
            new mlgl!.Marker({ element: el }).setLngLat([lon, lat]).setPopup(popup).addTo(map),
          );
        });
      }
    });

    // Fit bounds to active route
    if (activeRoute?.geometry?.length) {
      const lons = activeRoute.geometry.map(([, lon]) => lon);
      const lats = activeRoute.geometry.map(([lat]) => lat);
      map.fitBounds(
        [[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]],
        { padding: { top: 50, bottom: 90, left: 40, right: 40 }, duration: 700 },
      );
    }
  }, [mapReady, mlgl, routes, effectiveActiveId, compareMode, onRouteClick, activeRoute]);

  const flyTo = useCallback(([lat, lon]: [number, number]) => {
    mapRef.current?.flyTo({ center: [lon, lat], zoom: 13, duration: 600 });
  }, []);

  return (
    <div className={`relative overflow-hidden rounded-xl ${className}`} style={{ minHeight: 400 }}>
      <div ref={mapContainer} className="absolute inset-0" />
      {mapReady && <ElevationProfile route={activeRoute} onPositionClick={flyTo} />}
    </div>
  );
}
