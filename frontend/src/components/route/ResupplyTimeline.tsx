import { useMemo, useState } from "react";
import type { RouteOption } from "../../types/route";
import { Droplets, ShoppingCart, Tent, Hotel, AlertTriangle, MapPin } from "lucide-react";

interface ResupplyTimelineProps {
  route: RouteOption;
}

type WaypointKind = "water" | "grocery" | "camp" | "hotel" | "start" | "end";

interface Waypoint {
  km: number;
  day: number;
  label: string;
  kind: WaypointKind;
  detail?: string;
}

const KIND_META: Record<WaypointKind, { color: string; bg: string; ring: string; icon: React.ReactNode; track: string }> = {
  start:   { color: "text-foreground",  bg: "bg-foreground",  ring: "ring-foreground/20",  icon: <MapPin className="w-3 h-3" />,         track: "row-start-1" },
  end:     { color: "text-foreground",  bg: "bg-foreground",  ring: "ring-foreground/20",  icon: <MapPin className="w-3 h-3" />,         track: "row-start-1" },
  water:   { color: "text-hotel",       bg: "bg-hotel",       ring: "ring-hotel/30",       icon: <Droplets className="w-3 h-3" />,       track: "row-start-2" },
  grocery: { color: "text-grocery",     bg: "bg-grocery",     ring: "ring-grocery/30",     icon: <ShoppingCart className="w-3 h-3" />,   track: "row-start-3" },
  camp:    { color: "text-trail",       bg: "bg-trail",       ring: "ring-trail/30",       icon: <Tent className="w-3 h-3" />,           track: "row-start-4" },
  hotel:   { color: "text-camp",        bg: "bg-camp",        ring: "ring-camp/30",        icon: <Hotel className="w-3 h-3" />,          track: "row-start-4" },
};

export default function ResupplyTimeline({ route }: ResupplyTimelineProps) {
  const [hovered, setHovered] = useState<Waypoint | null>(null);

  const { waypoints, gaps, total } = useMemo(() => buildWaypoints(route), [route]);

  const dayBoundaries = useMemo(() => {
    let acc = 0;
    return route.day_segments.map((d) => {
      acc += d.distance_km;
      return { day: d.day, km: acc };
    });
  }, [route]);

  return (
    <div className="bg-card border border-border rounded-2xl p-5 space-y-4">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h3 className="text-base font-serif text-foreground">Resupply &amp; logistics timeline</h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            Water, food and lodging across the full {total}km — spot the gaps before you ride into them.
          </p>
        </div>
        <Legend />
      </div>

      {/* Timeline */}
      <div className="relative pt-2">
        {/* Day labels above */}
        <div className="relative h-5 mb-1">
          {dayBoundaries.slice(0, -1).map((b) => (
            <div
              key={b.day}
              className="absolute -translate-x-1/2 text-[10px] text-muted-foreground"
              style={{ left: `${(b.km / total) * 100}%` }}
            >
              end of day {b.day}
            </div>
          ))}
        </div>

        {/* Tracks */}
        <div className="relative grid grid-rows-4 gap-2 py-2 pl-12 pr-2">
          {/* Track labels */}
          <TrackLabel icon={<MapPin className="w-3 h-3" />} label="Route" row={1} />
          <TrackLabel icon={<Droplets className="w-3 h-3 text-hotel" />} label="Water" row={2} />
          <TrackLabel icon={<ShoppingCart className="w-3 h-3 text-grocery" />} label="Food" row={3} />
          <TrackLabel icon={<Tent className="w-3 h-3 text-trail" />} label="Sleep" row={4} />

          {/* Track lines */}
          {[1, 2, 3, 4].map((row) => (
            <div
              key={row}
              className="absolute left-12 right-2 h-px bg-border"
              style={{ top: `calc(${(row - 1) * 1.75}rem + ${row * 0.5}rem + 0.875rem)` }}
            />
          ))}

          {/* Day boundary verticals */}
          {dayBoundaries.slice(0, -1).map((b) => (
            <div
              key={`dl-${b.day}`}
              className="absolute top-0 bottom-0 w-px bg-border/60 border-l border-dashed border-border"
              style={{ left: `calc(3rem + ((100% - 3.5rem) * ${b.km / total}))` }}
            />
          ))}

          {/* Gap warnings on water track */}
          {gaps.map((g, i) => (
            <div
              key={`gap-${i}`}
              className="absolute h-1.5 rounded-full bg-destructive/20 border border-destructive/40"
              style={{
                top: `calc(1.75rem + 1rem + 0.625rem)`,
                left: `calc(3rem + ((100% - 3.5rem) * ${g.startKm / total}))`,
                width: `calc((100% - 3.5rem) * ${(g.endKm - g.startKm) / total})`,
              }}
              title={`${Math.round(g.endKm - g.startKm)}km without water`}
            />
          ))}

          {/* Waypoints */}
          {waypoints.map((wp, i) => {
            const meta = KIND_META[wp.kind];
            return (
              <button
                key={`wp-${i}`}
                onMouseEnter={() => setHovered(wp)}
                onMouseLeave={() => setHovered(null)}
                onFocus={() => setHovered(wp)}
                onBlur={() => setHovered(null)}
                className={`absolute -translate-x-1/2 w-5 h-5 rounded-full ${meta.bg} ${meta.ring} ring-2 ring-offset-1 ring-offset-card text-primary-foreground flex items-center justify-center hover:scale-125 transition-transform`}
                style={{
                  top: `calc(${(rowFor(wp.kind) - 1) * 1.75}rem + ${rowFor(wp.kind) * 0.5}rem + 0.375rem)`,
                  left: `calc(3rem + ((100% - 3.5rem) * ${wp.km / total}))`,
                }}
                aria-label={`${wp.label} at km ${wp.km}`}
              >
                {meta.icon}
              </button>
            );
          })}
        </div>

        {/* km axis */}
        <div className="relative h-5 mt-1 pl-12 pr-2">
          {[0, 0.25, 0.5, 0.75, 1].map((pct) => (
            <div
              key={pct}
              className="absolute -translate-x-1/2 text-[10px] text-muted-foreground"
              style={{ left: `calc(3rem + ((100% - 3.5rem) * ${pct}))` }}
            >
              {Math.round(total * pct)}km
            </div>
          ))}
        </div>
      </div>

      {/* Hover detail / gap callout */}
      <div className="min-h-[3rem] bg-secondary/40 border border-border rounded-xl px-4 py-2.5 text-sm">
        {hovered ? (
          <div className="flex items-start gap-2">
            <span className={KIND_META[hovered.kind].color}>{KIND_META[hovered.kind].icon}</span>
            <div>
              <div className="text-foreground font-medium">
                {hovered.label}{" "}
                <span className="text-xs text-muted-foreground font-normal">
                  · km {hovered.km} · day {hovered.day}
                </span>
              </div>
              {hovered.detail && (
                <div className="text-xs text-muted-foreground mt-0.5">{hovered.detail}</div>
              )}
            </div>
          </div>
        ) : gaps.length > 0 ? (
          <div className="flex items-start gap-2 text-muted-foreground">
            <AlertTriangle className="w-4 h-4 text-destructive flex-shrink-0 mt-0.5" />
            <div className="text-xs">
              <span className="text-foreground font-medium">
                {gaps.length} resupply gap{gaps.length > 1 ? "s" : ""} flagged
              </span>{" "}
              — the longest is{" "}
              <span className="text-foreground font-medium">
                {Math.round(Math.max(...gaps.map((g) => g.endKm - g.startKm)))}km
              </span>{" "}
              without a water source. Carry capacity accordingly.
            </div>
          </div>
        ) : (
          <div className="text-xs text-muted-foreground">
            Hover any marker for detail. No major resupply gaps detected on this route.
          </div>
        )}
      </div>
    </div>
  );
}

function TrackLabel({ icon, label, row }: { icon: React.ReactNode; label: string; row: number }) {
  return (
    <div
      className="absolute left-0 flex items-center gap-1 text-[10px] uppercase tracking-wider text-muted-foreground"
      style={{ top: `calc(${(row - 1) * 1.75}rem + ${row * 0.5}rem + 0.375rem)` }}
    >
      {icon}
      <span>{label}</span>
    </div>
  );
}

function Legend() {
  const items: { kind: WaypointKind; label: string }[] = [
    { kind: "water", label: "Water" },
    { kind: "grocery", label: "Food" },
    { kind: "camp", label: "Camp" },
    { kind: "hotel", label: "Hotel" },
  ];
  return (
    <div className="flex flex-wrap gap-2.5">
      {items.map((i) => (
        <span key={i.kind} className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
          <span className={`w-2.5 h-2.5 rounded-full ${KIND_META[i.kind].bg}`} />
          {i.label}
        </span>
      ))}
    </div>
  );
}

function rowFor(kind: WaypointKind): number {
  if (kind === "start" || kind === "end") return 1;
  if (kind === "water") return 2;
  if (kind === "grocery") return 3;
  return 4;
}

// ─── Build waypoints from RouteOption ───────────────────────────────────────
function buildWaypoints(route: RouteOption): {
  waypoints: Waypoint[];
  gaps: { startKm: number; endKm: number }[];
  total: number;
} {
  const waypoints: Waypoint[] = [];
  let cumulativeKm = 0;

  waypoints.push({ km: 0, day: 1, label: "Start", kind: "start" });

  route.day_segments.forEach((seg) => {
    const dayStartKm = cumulativeKm;

    // Distribute water points evenly across the day
    seg.water_points.forEach((wp, i) => {
      const pct = (i + 1) / (seg.water_points.length + 1);
      waypoints.push({
        km: Math.round(dayStartKm + seg.distance_km * pct),
        day: seg.day,
        label: wp,
        kind: "water",
        detail: `Water source on day ${seg.day}`,
      });
    });

    // Distribute grocery points
    seg.grocery_points.forEach((gp, i) => {
      const pct = (i + 1) / (seg.grocery_points.length + 1);
      waypoints.push({
        km: Math.round(dayStartKm + seg.distance_km * pct),
        day: seg.day,
        label: gp,
        kind: "grocery",
        detail: `Resupply / food on day ${seg.day}`,
      });
    });

    // Overnight options at end of day
    if (seg.overnight_area) {
      seg.overnight_area.options.forEach((opt) => {
        waypoints.push({
          km: Math.round(cumulativeKm + seg.distance_km),
          day: seg.day,
          label: opt.name,
          kind: opt.type === "hotel" || opt.type === "motel" ? "hotel" : "camp",
          detail: `${opt.description} · ${opt.distance_from_route_km}km from route`,
        });
      });
    }

    cumulativeKm += seg.distance_km;
  });

  waypoints.push({ km: Math.round(cumulativeKm), day: route.estimated_days, label: "Finish", kind: "end" });

  // Detect water gaps > 40km
  const waterKms = [0, ...waypoints.filter((w) => w.kind === "water").map((w) => w.km), Math.round(cumulativeKm)];
  waterKms.sort((a, b) => a - b);
  const gaps: { startKm: number; endKm: number }[] = [];
  for (let i = 0; i < waterKms.length - 1; i++) {
    if (waterKms[i + 1] - waterKms[i] > 40) {
      gaps.push({ startKm: waterKms[i], endKm: waterKms[i + 1] });
    }
  }

  return { waypoints, gaps, total: Math.round(cumulativeKm) };
}
