import React, { useEffect, useRef, useCallback, useMemo, useState } from "react";
import maplibregl from "maplibre-gl";

import type { RouteOption } from "../../types/route";

/**
 * RouteMap.tsx — MapLibre GL powered route map
 *
 * Uses an inline raster-tile style backed by OpenStreetMap tiles.
 * This is intentionally the simplest possible setup:
 *   - No external style.json (no Mapbox / Stadia validation issues)
 *   - No mapbox:// protocol (no transformRequest gymnastics)
 *   - No async fetches in useEffect (no TS build failures)
 *
 * The CDN workerUrl assignment below fixes CRA/webpack's broken handling
 * of MapLibre's tile worker — without it, tiles never decode in production.
 */

// ─── Worker fix (must run before any Map is created) ─────────────────────────
(maplibregl as any).workerUrl =
  "https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl-csp-worker.js";

// ─── Inline style (raster OSM tiles, no auth required) ───────────────────────
const RASTER_STYLE: any = {
  version: 8,
  sources: {
    "osm-tiles": {
      type: "raster",
      tiles: [
        "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png",
        "https://b.tile.openstreetmap.org/{z}/{x}/{y}.png",
        "https://c.tile.openstreetmap.org/{z}/{x}/{y}.png",
      ],
      tileSize: 256,
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxzoom: 19,
    },
  },
  layers: [
    {
      id: "osm-tiles",
      type: "raster",
      source: "osm-tiles",
      minzoom: 0,
      maxzoom: 22,
    },
  ],
};

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

// ─── Elevation profile strip ─────────────────────────────────────────────────
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
  const [mapReady, setMapReady] = useState(false);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const routes: RouteOption[] = useMemo(
    () => multiRoutes ?? (singleRoute ? [singleRoute] : []),
    [multiRoutes, singleRoute]
  );
  const effectiveActiveId = activeRouteId ?? routes[0]?.id ?? null;
  const activeRoute = routes.find((r) => r.id === effectiveActiveId) ?? routes[0] ?? null;

  // ── Initialise map (synchronous — no async, no fetch) ──────────────────────
  useEffect(() => {
    if (!mapContainer.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: mapContainer.current,
      style: RASTER_STYLE,
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

    // Aggressive resize loop for the first second — catches Framer Motion
    // fade-in completion, lazy layout, and any other late dimension changes.
    let resizeFrames = 0;
    const resizeLoop = () => {
      if (!mapRef.current || resizeFrames > 60) return; // ~1 second @ 60fps
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
      map.remove();
      mapRef.current = null;
      setMapReady(false);
    };
  }, []);

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
      className={`relative rounded-xl overflow-hidden ${className}`}
      style={{ height: 520, minHeight: 400, width: "100%" }}
    >
      {/* Inline style guarantees the map container has explicit, non-zero
          dimensions BEFORE MapLibre measures it at mount. The previous
          `absolute inset-0` approach left dimensions dependent on Tailwind
          arbitrary classes resolving correctly, which they didn't. */}
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
      {/* Force MapLibre's internal canvas to fill its container regardless
          of any Tailwind preflight / specificity surprises. */}
      <style>{`
        .maplibregl-map { width: 100% !important; height: 100% !important; position: absolute !important; inset: 0 !important; }
        .maplibregl-canvas-container { width: 100% !important; height: 100% !important; }
        .maplibregl-canvas { width: 100% !important; height: 100% !important; }
      `}</style>
      {mapReady && (
        <ElevationProfile route={activeRoute} onPositionClick={flyTo} />
      )}
    </div>
  );
}
