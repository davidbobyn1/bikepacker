import React from "react";
import type { ConfidenceLevel } from "../../types/route";
import { Shield, AlertTriangle, AlertCircle } from "lucide-react";

const config: Record<ConfidenceLevel, { label: string; icon: React.ReactNode; className: string }> = {
  high: { label: "High confidence", icon: <Shield className="w-3.5 h-3.5" />, className: "bg-trail/15 text-trail" },
  medium: { label: "Medium confidence", icon: <AlertTriangle className="w-3.5 h-3.5" />, className: "bg-accent/15 text-accent" },
  low: { label: "Low confidence", icon: <AlertCircle className="w-3.5 h-3.5" />, className: "bg-destructive/15 text-destructive" },
};

export default function ConfidenceBadge({ level }: { level: ConfidenceLevel }) {
  const c = config[level];
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold ${c.className}`}>
      {c.icon}
      {c.label}
    </span>
  );
}
