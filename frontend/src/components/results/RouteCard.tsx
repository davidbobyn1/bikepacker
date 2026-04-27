import type { RouteOption } from "../../types/route";
import { motion } from "framer-motion";
import {
  ArrowRight, Download, Mountain, Ruler, Percent, Clock,
  Eye, Shield, Flame, ShoppingCart, Droplets, Building,
  CheckCircle2, AlertTriangle, Info, Trees, Compass,
} from "lucide-react";
import ConfidenceBadge from "../route/ConfidenceBadge";

type Archetype = "scenic" | "easier" | "adventurous";

interface ArchetypeStyle {
  icon: React.ReactNode;
  terrainBadge: { label: string; icon: React.ReactNode };
  bandClass: string;
  borderClass: string;
  iconBgClass: string;
  ringClass: string;
  terrainBadgeClass: string;
}

const ARCHETYPE_STYLES: Record<Archetype, ArchetypeStyle> = {
  scenic: {
    icon: <Eye className="w-5 h-5" />,
    terrainBadge: { label: "Coastal & Forest", icon: <Trees className="w-3 h-3" /> },
    bandClass: "bg-gradient-to-r from-trail/15 via-trail/5 to-transparent",
    borderClass: "border-l-trail",
    iconBgClass: "bg-trail/15 text-trail ring-1 ring-trail/20",
    ringClass: "hover:ring-trail/30",
    terrainBadgeClass: "bg-trail/15 text-trail",
  },
  easier: {
    icon: <Shield className="w-5 h-5" />,
    terrainBadge: { label: "Town-to-Town", icon: <Building className="w-3 h-3" /> },
    bandClass: "bg-gradient-to-r from-hotel/15 via-hotel/5 to-transparent",
    borderClass: "border-l-hotel",
    iconBgClass: "bg-hotel/15 text-hotel ring-1 ring-hotel/20",
    ringClass: "hover:ring-hotel/30",
    terrainBadgeClass: "bg-hotel/15 text-hotel",
  },
  adventurous: {
    icon: <Flame className="w-5 h-5" />,
    terrainBadge: { label: "Backcountry & Ridges", icon: <Mountain className="w-3 h-3" /> },
    bandClass: "bg-gradient-to-r from-camp/15 via-camp/5 to-transparent",
    borderClass: "border-l-camp",
    iconBgClass: "bg-camp/15 text-camp ring-1 ring-camp/20",
    ringClass: "hover:ring-camp/30",
    terrainBadgeClass: "bg-camp/15 text-camp",
  },
};

const API_BASE = process.env.REACT_APP_API_BASE || "http://localhost:8000/api";
function getFullGpxUrl(gpxUrl: string) {
  if (!gpxUrl) return "#";
  if (gpxUrl.startsWith("http")) return gpxUrl;
  const path = gpxUrl.startsWith("/api/") ? gpxUrl.slice(4) : gpxUrl;
  return `${API_BASE}${path}`;
}

interface RouteCardProps {
  route: RouteOption;
  index: number;
  onViewDetails: (route: RouteOption) => void;
  isBestFit?: boolean;
}

export default function RouteCard({ route, index, onViewDetails, isBestFit }: RouteCardProps) {
  const style = ARCHETYPE_STYLES[route.archetype as Archetype] ?? ARCHETYPE_STYLES.scenic;
  const topFitReasons = route.rider_fit_reasons.slice(0, 2);
  const topTradeoff = route.tradeoffs[0];
  const gpxHref = getFullGpxUrl(route.gpx_url);

  return (
    <motion.div
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.12, duration: 0.45 }}
      className={`relative bg-card rounded-xl border border-border border-l-4 ${style.borderClass} shadow-sm hover:shadow-lg transition-all ring-1 ring-transparent ${style.ringClass} flex flex-col overflow-hidden`}
    >
      {isBestFit && (
        <div className="absolute top-3 right-3 z-10">
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-primary text-primary-foreground text-[10px] font-semibold uppercase tracking-wider shadow-sm">
            <Compass className="w-3 h-3" /> Best fit
          </span>
        </div>
      )}

      {/* Archetype header band */}
      <div className={`${style.bandClass} px-5 sm:px-6 pt-5 pb-4`}>
        <div className="flex items-start gap-3 mb-3">
          <div className={`p-2.5 rounded-lg ${style.iconBgClass} flex-shrink-0`}>
            {style.icon}
          </div>
          <div className="flex-1 min-w-0 pr-16">
            <div className="flex items-center gap-1.5 mb-1">
              <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider ${style.terrainBadgeClass}`}>
                {style.terrainBadge.icon}
                {style.terrainBadge.label}
              </span>
            </div>
            <h3 className="text-lg font-serif text-foreground leading-tight">{route.archetype_label}</h3>
            <p className="text-xs text-muted-foreground mt-0.5 leading-snug">{route.archetype_tagline}</p>
          </div>
        </div>

        {/* Metrics strip */}
        <div className="grid grid-cols-4 gap-2 pt-1">
          <Metric icon={<Ruler className="w-3 h-3" />}   label="km"    value={route.total_distance_km.toLocaleString()} />
          <Metric icon={<Mountain className="w-3 h-3" />} label="climb" value={`${Math.round(route.total_climbing_m).toLocaleString()}m`} />
          <Metric icon={<Percent className="w-3 h-3" />}  label="gravel" value={`${Math.round(route.gravel_ratio * 100)}%`} />
          <Metric icon={<Clock className="w-3 h-3" />}    label="days"  value={route.estimated_days} />
        </div>
      </div>

      {/* Body */}
      <div className="px-5 sm:px-6 pt-4 flex-1 flex flex-col">
        <p className="text-sm text-muted-foreground leading-relaxed line-clamp-2">{route.summary}</p>

        {/* Logistics badges */}
        <div className="flex flex-wrap gap-1.5 pt-3">
          <LogisticsBadge icon={<ShoppingCart className="w-3 h-3" />} label="Grocery" value={`${route.grocery_distance_km} km`} good={route.grocery_distance_km <= 1} />
          <LogisticsBadge icon={<Droplets className="w-3 h-3" />}     label="Water"   value={`${route.water_distance_km} km`}   good={route.water_distance_km <= 2} />
          <LogisticsBadge icon={<Building className="w-3 h-3" />}     label="Hotel"   value={`${route.hotel_fallback_distance_km} km`} good={route.hotel_fallback_distance_km <= 2} />
        </div>

        {/* Rider fit preview — one line only to keep cards compact */}
        <div className="space-y-1.5 pt-3">
          {topFitReasons.slice(0, 1).map((reason, i) => (
            <div key={i} className="flex items-start gap-1.5 text-xs">
              {reason.icon_type === "check"   && <CheckCircle2 className="w-3.5 h-3.5 text-trail flex-shrink-0 mt-0.5" />}
              {reason.icon_type === "warning" && <AlertTriangle className="w-3.5 h-3.5 text-camp flex-shrink-0 mt-0.5" />}
              {reason.icon_type === "info"    && <Info className="w-3.5 h-3.5 text-hotel flex-shrink-0 mt-0.5" />}
              <span className="text-muted-foreground">{reason.text}</span>
            </div>
          ))}
        </div>

        {/* Overnight preview */}
        <div className="pt-3 text-xs">
          <span className="font-medium text-foreground">Overnight area: </span>
          <span className="text-muted-foreground">{route.overnight_areas.map((a) => a.name).join(", ")}</span>
        </div>

        {/* Confidence + Actions */}
        <div className="pt-4 pb-5 mt-auto">
          <div className="flex items-center gap-2 mb-3">
            <ConfidenceBadge level={route.confidence_level} />
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => onViewDetails(route)}
              className="flex-1 inline-flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity"
            >
              Full Trip Plan <ArrowRight className="w-4 h-4" />
            </button>
            <a
              href={gpxHref}
              download
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center gap-1.5 px-3 py-2.5 rounded-lg bg-secondary text-secondary-foreground text-sm font-medium hover:bg-muted transition-colors"
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

function Metric({ icon, label, value }: { icon: React.ReactNode; label: string; value: string | number }) {
  return (
    <div className="flex flex-col items-start gap-0.5 px-2 py-1.5 rounded-md bg-card/70 backdrop-blur-sm border border-border/50">
      <div className="flex items-center gap-1 text-[10px] text-muted-foreground uppercase tracking-wider">
        {icon} {label}
      </div>
      <div className="text-sm font-semibold text-foreground tabular-nums leading-none">{value}</div>
    </div>
  );
}

function LogisticsBadge({ icon, label, value, good }: { icon: React.ReactNode; label: string; value: string; good: boolean }) {
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium ${good ? "bg-trail/10 text-trail" : "bg-muted text-muted-foreground"}`}>
      {icon} {label} {value}
    </span>
  );
}

function truncate(s: string, n: number) {
  return s.length > n ? s.slice(0, n) + "…" : s;
}
