import React from "react";
import { motion } from "framer-motion";
import {
  Ruler, Mountain, Percent, Clock, ArrowRight,
  Eye, Shield, Flame, Compass, Trees, Building,
  CheckCircle2, AlertTriangle, Info, Download,
} from "lucide-react";
import type { RouteOption } from "../../types/route";
import ConfidenceBadge from "../route/ConfidenceBadge";

// ---------------------------------------------------------------------------
// Per-archetype visual identity
// ---------------------------------------------------------------------------
interface ArchetypeStyle {
  icon: React.ReactNode;
  terrainLabel: string;
  terrainIcon: React.ReactNode;
  accentColor: string;
  accentBg: string;
  borderLeft: string;
  gradientBand: string;
}

const ARCHETYPE_STYLES: Record<string, ArchetypeStyle> = {
  scenic: {
    icon: <Eye className="w-5 h-5" />,
    terrainLabel: "Coastal & Forest",
    terrainIcon: <Trees className="w-3 h-3" />,
    accentColor: "#16a34a",
    accentBg: "rgba(22,163,74,0.15)",
    borderLeft: "4px solid #16a34a",
    gradientBand: "linear-gradient(135deg, rgba(22,163,74,0.10) 0%, rgba(22,163,74,0.03) 100%)",
  },
  easier: {
    icon: <Shield className="w-5 h-5" />,
    terrainLabel: "Town-to-Town",
    terrainIcon: <Building className="w-3 h-3" />,
    accentColor: "#3b82f6",
    accentBg: "rgba(59,130,246,0.15)",
    borderLeft: "4px solid #3b82f6",
    gradientBand: "linear-gradient(135deg, rgba(59,130,246,0.10) 0%, rgba(59,130,246,0.03) 100%)",
  },
  adventurous: {
    icon: <Flame className="w-5 h-5" />,
    terrainLabel: "Backcountry & Ridges",
    terrainIcon: <Mountain className="w-3 h-3" />,
    accentColor: "#f59e0b",
    accentBg: "rgba(245,158,11,0.15)",
    borderLeft: "4px solid #f59e0b",
    gradientBand: "linear-gradient(135deg, rgba(245,158,11,0.10) 0%, rgba(245,158,11,0.03) 100%)",
  },
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
interface Props {
  route: RouteOption;
  index: number;
  onViewDetails: (route: RouteOption) => void;
  isBestFit?: boolean;
}

export default function RouteCard({ route, index, onViewDetails, isBestFit }: Props) {
  const style = ARCHETYPE_STYLES[route.archetype] ?? ARCHETYPE_STYLES.scenic;
  const topFitReasons = route.rider_fit_reasons?.slice(0, 2) ?? [];
  const topTradeoff = route.tradeoffs?.[0];

  // Build full GPX URL
  const apiBase = (import.meta as any).env?.VITE_API_BASE ?? "";
  const gpxHref = route.gpx_url
    ? route.gpx_url.startsWith("http") ? route.gpx_url : `${apiBase}${route.gpx_url}`
    : "#";

  return (
    <motion.div
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.12, duration: 0.45 }}
      className="relative bg-card rounded-xl border border-border overflow-hidden flex flex-col hover:shadow-lg transition-shadow"
      style={{ borderLeft: style.borderLeft }}
    >
      {/* Best fit pill */}
      {isBestFit && (
        <div className="absolute top-3 right-3 z-10">
          <span
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider shadow-sm"
            style={{ background: style.accentColor, color: "#fff" }}
          >
            <Compass className="w-3 h-3" /> Best fit
          </span>
        </div>
      )}

      {/* Gradient header band */}
      <div style={{ background: style.gradientBand }} className="px-5 pt-5 pb-4">
        <div className="flex items-start gap-3 mb-3">
          <div
            className="p-2.5 rounded-lg flex-shrink-0"
            style={{ background: style.accentBg, color: style.accentColor }}
          >
            {style.icon}
          </div>
          <div className="flex-1 min-w-0 pr-16">
            <span
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider mb-1"
              style={{ background: style.accentBg, color: style.accentColor }}
            >
              {style.terrainIcon}
              {style.terrainLabel}
            </span>
            <h3 className="text-base font-serif text-foreground leading-tight">
              {route.trip_title || route.archetype_label}
            </h3>
            <p className="text-xs text-muted-foreground mt-0.5 leading-snug">
              {route.tagline || route.archetype_tagline}
            </p>
          </div>
        </div>

        {/* 4-up metric tiles */}
        <div className="grid grid-cols-4 gap-1.5">
          <MetricTile icon={<Ruler className="w-3 h-3" />}    label="km"    value={`${route.total_distance_km}`} />
          <MetricTile icon={<Mountain className="w-3 h-3" />} label="climb" value={`${route.total_climbing_m}m`} />
          <MetricTile icon={<Percent className="w-3 h-3" />}  label="gravel" value={`${Math.round(route.gravel_ratio * 100)}%`} />
          <MetricTile icon={<Clock className="w-3 h-3" />}    label="days"  value={`${route.estimated_days}`} />
        </div>
      </div>

      {/* Body */}
      <div className="px-5 pt-4 flex-1 flex flex-col">
        <p className="text-sm text-muted-foreground leading-relaxed line-clamp-3">
          {route.summary || route.why_this_route}
        </p>

        {/* Rider fit reasons */}
        {topFitReasons.length > 0 && (
          <div className="space-y-1.5 pt-3">
            {topFitReasons.map((reason, i) => (
              <div key={i} className="flex items-start gap-1.5 text-xs">
                {reason.icon_type === "check"   && <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" style={{ color: "#16a34a" }} />}
                {reason.icon_type === "warning" && <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" style={{ color: "#f59e0b" }} />}
                {reason.icon_type === "info"    && <Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" style={{ color: "#3b82f6" }} />}
                <span className="text-muted-foreground">{reason.text}</span>
              </div>
            ))}
          </div>
        )}

        {/* Key tradeoff */}
        {topTradeoff && (
          <div className="pt-3">
            <div className="rounded-lg px-3 py-2 bg-muted/50">
              <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
                {topTradeoff.label}
              </span>
              <p className="text-xs mt-0.5" style={{ color: "#16a34a" }}>
                + {truncate(topTradeoff.pro, 60)}
              </p>
              <p className="text-xs mt-0.5 text-muted-foreground">
                − {truncate(topTradeoff.con, 60)}
              </p>
            </div>
          </div>
        )}

        {/* Overnight areas */}
        {route.overnight_areas?.length > 0 && (
          <div className="pt-3 text-xs">
            <span className="font-medium text-foreground">Overnight: </span>
            <span className="text-muted-foreground">
              {route.overnight_areas.map((a) => a.name).join(" → ")}
            </span>
          </div>
        )}

        {/* Confidence + Actions */}
        <div className="pt-4 pb-5 mt-auto">
          <div className="mb-3">
            <ConfidenceBadge level={route.confidence_level} />
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => onViewDetails(route)}
              className="flex-1 inline-flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-lg text-sm font-medium text-white transition-opacity hover:opacity-90"
              style={{ background: style.accentColor }}
            >
              Full Trip Plan <ArrowRight className="w-4 h-4" />
            </button>
            <a
              href={gpxHref}
              download
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center gap-1.5 px-3 py-2.5 rounded-lg border border-border bg-card text-muted-foreground hover:bg-muted transition-colors text-sm"
              title="Download GPX"
            >
              <Download className="w-4 h-4" />
            </a>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

function MetricTile({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex flex-col items-start gap-0.5 px-2 py-1.5 rounded-md bg-card/70 border border-border/50">
      <div className="flex items-center gap-1 text-[10px] text-muted-foreground uppercase tracking-wider">
        {icon} {label}
      </div>
      <div className="text-sm font-semibold text-foreground tabular-nums leading-none">{value}</div>
    </div>
  );
}

function truncate(s: string, n: number) {
  return s && s.length > n ? s.slice(0, n) + "…" : s ?? "";
}
