import React, { useMemo } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { ElevationPoint } from "../../types/route";

interface Props {
  elevationPoints?: ElevationPoint[];
  distanceKm: number;
  climbingM: number;
}

/**
 * Synthesise a plausible elevation profile from total distance and climbing.
 * Uses a combination of sine waves to create a realistic-looking hilly profile.
 * TODO: replace with real per-day elevation data from the backend elevation proxy.
 */
function synthesiseElevation(distanceKm: number, climbingM: number): ElevationPoint[] {
  const POINTS = 40;
  const baseElevation = 50; // arbitrary start
  const amplitude = Math.max(climbingM * 0.6, 30);
  const points: ElevationPoint[] = [];

  for (let i = 0; i <= POINTS; i++) {
    const km = parseFloat(((i / POINTS) * distanceKm).toFixed(1));
    const t = (i / POINTS) * Math.PI * 2;
    // Mix two sine waves for a more natural profile
    const elevation = Math.round(
      baseElevation +
        amplitude * 0.6 * Math.sin(t * 1.5 + 0.3) +
        amplitude * 0.3 * Math.sin(t * 3.2 + 1.1) +
        amplitude * 0.1 * Math.sin(t * 5.7 + 0.7)
    );
    points.push({ km, elevation_m: Math.max(0, elevation) });
  }
  return points;
}

interface TooltipPayload {
  payload?: { km: number; elevation_m: number };
}

function CustomTooltip({ active, payload }: { active?: boolean; payload?: TooltipPayload[] }) {
  if (!active || !payload?.length || !payload[0].payload) return null;
  const d = payload[0].payload;
  return (
    <div className="bg-card border border-border rounded-md px-2.5 py-1.5 text-xs shadow-sm">
      <span className="font-medium text-foreground">{d.elevation_m} m</span>
      <span className="text-muted-foreground ml-1.5">at {d.km} km</span>
    </div>
  );
}

export default function ElevationProfile({ elevationPoints, distanceKm, climbingM }: Props) {
  const data = useMemo(
    () => elevationPoints ?? synthesiseElevation(distanceKm, climbingM),
    [elevationPoints, distanceKm, climbingM]
  );

  const minEl = Math.min(...data.map((p) => p.elevation_m));
  const maxEl = Math.max(...data.map((p) => p.elevation_m));
  const domain: [number, number] = [Math.max(0, minEl - 20), maxEl + 20];

  return (
    <div className="w-full" style={{ height: 80 }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 4, right: 4, left: -28, bottom: 0 }}>
          <defs>
            <linearGradient id="elevGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#16a34a" stopOpacity={0.25} />
              <stop offset="95%" stopColor="#16a34a" stopOpacity={0.03} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="km"
            tick={{ fontSize: 9, fill: "#94a3b8" }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v: number) => `${v}km`}
            interval="preserveStartEnd"
          />
          <YAxis
            domain={domain}
            tick={{ fontSize: 9, fill: "#94a3b8" }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v: number) => `${v}m`}
            width={36}
          />
          <Tooltip content={<CustomTooltip />} />
          <Area
            type="monotone"
            dataKey="elevation_m"
            stroke="#16a34a"
            strokeWidth={1.5}
            fill="url(#elevGrad)"
            dot={false}
            activeDot={{ r: 3, fill: "#16a34a" }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
