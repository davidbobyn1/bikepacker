import React from "react";
import { motion } from "framer-motion";
import { X, ArrowRight, Mountain, Ruler, Percent, Clock, Moon } from "lucide-react";
import type { RouteOption } from "../../types/route";

interface RouteCompareTableProps {
  routes: RouteOption[];
  onClose: () => void;
  onOpen: (route: RouteOption) => void;
}

const archetypeColors: Record<string, string> = {
  scenic: "text-trail",
  easier: "text-hotel",
  adventurous: "text-camp",
};

function MetricRow({
  label,
  icon,
  values,
  format,
  bestIndex,
}: {
  label: string;
  icon: React.ReactNode;
  values: (number | string)[];
  format?: (v: number | string) => string;
  bestIndex?: number;
}) {
  const fmt = format || ((v) => String(v));
  return (
    <tr className="border-b border-border">
      <td className="py-3 pr-4 text-sm text-muted-foreground whitespace-nowrap">
        <span className="inline-flex items-center gap-1.5">
          {icon} {label}
        </span>
      </td>
      {values.map((v, i) => (
        <td
          key={i}
          className={`py-3 px-3 text-sm font-medium text-center ${
            bestIndex === i ? "text-primary" : ""
          }`}
        >
          {fmt(v)}
          {bestIndex === i && (
            <span className="ml-1 text-xs text-primary opacity-70">✓</span>
          )}
        </td>
      ))}
    </tr>
  );
}

export default function RouteCompareTable({ routes, onClose, onOpen }: RouteCompareTableProps) {
  if (routes.length < 2) return null;

  // Find best (lowest) index for each metric
  const bestDistance = routes.reduce(
    (bi, r, i) => (r.total_distance_km < routes[bi].total_distance_km ? i : bi),
    0
  );
  const bestClimbing = routes.reduce(
    (bi, r, i) => (r.total_climbing_m < routes[bi].total_climbing_m ? i : bi),
    0
  );
  const bestGravel = routes.reduce(
    (bi, r, i) =>
      Math.abs(r.gravel_ratio - 0.5) < Math.abs(routes[bi].gravel_ratio - 0.5) ? i : bi,
    0
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 20 }}
      className="fixed inset-0 bg-background/80 backdrop-blur-sm z-50 flex items-center justify-center p-4"
    >
      <div className="bg-background border border-border rounded-2xl shadow-2xl w-full max-w-3xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border sticky top-0 bg-background z-10">
          <h2 className="font-semibold text-lg">Route Comparison</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="px-6 py-5">
          {/* Route name headers */}
          <table className="w-full">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left py-3 pr-4 text-sm text-muted-foreground font-normal w-32">Metric</th>
                {routes.map((r) => (
                  <th key={r.id} className="py-3 px-3 text-center">
                    <div className={`text-sm font-semibold ${archetypeColors[r.archetype] || ""}`}>
                      {r.trip_title || r.archetype_label}
                    </div>
                    <div className="text-xs text-muted-foreground mt-0.5">{r.tagline || r.archetype_tagline}</div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <MetricRow
                label="Distance"
                icon={<Ruler className="w-3.5 h-3.5" />}
                values={routes.map((r) => r.total_distance_km)}
                format={(v) => `${(v as number).toFixed(0)} km`}
                bestIndex={bestDistance}
              />
              <MetricRow
                label="Climbing"
                icon={<Mountain className="w-3.5 h-3.5" />}
                values={routes.map((r) => r.total_climbing_m)}
                format={(v) => `${(v as number).toFixed(0)} m`}
                bestIndex={bestClimbing}
              />
              <MetricRow
                label="Gravel ratio"
                icon={<Percent className="w-3.5 h-3.5" />}
                values={routes.map((r) => r.gravel_ratio)}
                format={(v) => `${Math.round((v as number) * 100)}%`}
                bestIndex={bestGravel}
              />
              <MetricRow
                label="Est. ride time"
                icon={<Clock className="w-3.5 h-3.5" />}
                values={routes.map((r) => {
                  const hours = r.total_distance_km / 15;
                  return hours < 1 ? `${Math.round(hours * 60)}m` : `${hours.toFixed(1)}h`;
                })}
              />
              <MetricRow
                label="Days"
                icon={<Moon className="w-3.5 h-3.5" />}
                values={routes.map((r) => `${r.estimated_days} day${r.estimated_days !== 1 ? "s" : ""}`)}
              />
              <MetricRow
                label="Confidence"
                icon={<span className="w-3.5 h-3.5 inline-block" />}
                values={routes.map((r) => r.confidence_level)}
                format={(v) => String(v).charAt(0).toUpperCase() + String(v).slice(1)}
              />
            </tbody>
          </table>

          {/* Open buttons */}
          <div className="flex gap-3 mt-6">
            {routes.map((r) => (
              <button
                key={r.id}
                onClick={() => { onOpen(r); onClose(); }}
                className="flex-1 inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl border border-border hover:bg-muted transition-colors text-sm font-medium"
              >
                View route <ArrowRight className="w-4 h-4" />
              </button>
            ))}
          </div>
        </div>
      </div>
    </motion.div>
  );
}
