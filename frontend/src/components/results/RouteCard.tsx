import React from "react";
import { motion } from "framer-motion";
import { Ruler, Mountain, Percent, Clock, ArrowRight, Eye, Shield, Flame } from "lucide-react";
import type { RouteOption } from "../../types/route";

interface Props {
  route: RouteOption;
  index: number;
  onViewDetails: (route: RouteOption) => void;
}

const archetypeConfig: Record<string, { icon: React.ReactNode; color: string; bg: string }> = {
  scenic:      { icon: <Eye className="w-4 h-4" />,    color: "#f59e0b", bg: "rgba(245,158,11,0.1)" },
  easier:      { icon: <Shield className="w-4 h-4" />, color: "#3b82f6", bg: "rgba(59,130,246,0.1)" },
  adventurous: { icon: <Flame className="w-4 h-4" />,  color: "#10b981", bg: "rgba(16,185,129,0.1)" },
};

export default function RouteCard({ route, index, onViewDetails }: Props) {
  const cfg = archetypeConfig[route.archetype] ?? archetypeConfig.scenic;

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.08 }}
      className="bg-card border border-border rounded-xl overflow-hidden flex flex-col hover:shadow-md transition-shadow"
    >
      {/* Archetype badge */}
      <div className="px-4 pt-4 pb-3 flex items-center gap-2">
        <span className="p-1.5 rounded-lg" style={{ background: cfg.bg, color: cfg.color }}>
          {cfg.icon}
        </span>
        <div>
          <div className="text-xs font-semibold uppercase tracking-wider" style={{ color: cfg.color }}>
            {route.archetype_label}
          </div>
          <div className="text-xs text-muted-foreground">{route.tagline || route.archetype_tagline}</div>
        </div>
      </div>

      {/* Trip title */}
      <div className="px-4 pb-3">
        <h3 className="text-base font-serif text-foreground leading-snug">
          {route.trip_title || route.archetype_label}
        </h3>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 gap-2 px-4 pb-4">
        <StatItem icon={<Ruler className="w-3.5 h-3.5" />} label="Distance" value={`${route.total_distance_km} km`} />
        <StatItem icon={<Mountain className="w-3.5 h-3.5" />} label="Climbing" value={`${route.total_climbing_m} m`} />
        <StatItem icon={<Percent className="w-3.5 h-3.5" />} label="Gravel" value={`${Math.round(route.gravel_ratio * 100)}%`} />
        <StatItem icon={<Clock className="w-3.5 h-3.5" />} label="Days" value={`${route.estimated_days} days`} />
      </div>

      {/* Why this fits */}
      {route.why_this_route && (
        <div className="px-4 pb-3">
          <p className="text-xs text-muted-foreground leading-relaxed line-clamp-3">{route.why_this_route}</p>
        </div>
      )}

      <div className="mt-auto px-4 pb-4">
        <button
          onClick={() => onViewDetails(route)}
          className="w-full flex items-center justify-center gap-1.5 py-2.5 rounded-lg text-sm font-medium transition-colors"
          style={{ background: cfg.bg, color: cfg.color }}
        >
          View Full Plan <ArrowRight className="w-4 h-4" />
        </button>
      </div>
    </motion.div>
  );
}

function StatItem({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex items-center gap-1.5 text-xs">
      <span className="text-muted-foreground">{icon}</span>
      <span className="text-muted-foreground">{label}:</span>
      <span className="font-semibold text-foreground">{value}</span>
    </div>
  );
}
