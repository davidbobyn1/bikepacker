import React, { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import type { RiderProfile, TripPreferences } from "../../types/route";

interface Props {
  riderProfile: RiderProfile;
  preferences: TripPreferences;
  onRiderProfileChange: (p: RiderProfile) => void;
  onPreferencesChange: (p: TripPreferences) => void;
}

export default function TripPreferencesPanel({ riderProfile, preferences, onRiderProfileChange, onPreferencesChange }: Props) {
  const [open, setOpen] = useState(false);

  return (
    <div className="border border-border rounded-xl overflow-hidden bg-card">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-foreground hover:bg-secondary/50 transition-colors"
      >
        <span>Rider Profile & Preferences</span>
        {open ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-4 border-t border-border pt-4">
          {/* Fitness */}
          <div>
            <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider block mb-2">Fitness Level</label>
            <div className="flex gap-2">
              {(["beginner", "intermediate", "advanced", "expert"] as const).map((level) => (
                <button
                  key={level}
                  onClick={() => onRiderProfileChange({ ...riderProfile, fitness: level })}
                  className={`flex-1 py-1.5 rounded-lg text-xs font-medium capitalize transition-colors ${
                    riderProfile.fitness === level ? "bg-primary text-white" : "bg-secondary text-foreground hover:opacity-80"
                  }`}
                >
                  {level}
                </button>
              ))}
            </div>
          </div>

          {/* Technical Skill */}
          <div>
            <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider block mb-2">Technical Skill</label>
            <div className="flex gap-2">
              {(["novice", "intermediate", "advanced"] as const).map((level) => (
                <button
                  key={level}
                  onClick={() => onRiderProfileChange({ ...riderProfile, technicalSkill: level })}
                  className={`flex-1 py-1.5 rounded-lg text-xs font-medium capitalize transition-colors ${
                    riderProfile.technicalSkill === level ? "bg-primary text-white" : "bg-secondary text-foreground hover:opacity-80"
                  }`}
                >
                  {level}
                </button>
              ))}
            </div>
          </div>

          {/* Route Shape */}
          <div>
            <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider block mb-2">Route Shape</label>
            <div className="flex gap-2">
              {(["loop", "point-to-point", "out-and-back"] as const).map((shape) => (
                <button
                  key={shape}
                  onClick={() => onPreferencesChange({ ...preferences, routeShape: shape })}
                  className={`flex-1 py-1.5 rounded-lg text-xs font-medium capitalize transition-colors ${
                    preferences.routeShape === shape ? "bg-primary text-white" : "bg-secondary text-foreground hover:opacity-80"
                  }`}
                >
                  {shape.replace(/_/g, " ")}
                </button>
              ))}
            </div>
          </div>

          {/* Overnight Preference */}
          <div>
            <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider block mb-2">Overnight Preference</label>
            <div className="flex gap-2">
              {(["camping", "hotel", "flexible"] as const).map((pref) => (
                <button
                  key={pref}
                  onClick={() => onPreferencesChange({ ...preferences, overnightPreference: pref })}
                  className={`flex-1 py-1.5 rounded-lg text-xs font-medium capitalize transition-colors ${
                    preferences.overnightPreference === pref ? "bg-primary text-white" : "bg-secondary text-foreground hover:opacity-80"
                  }`}
                >
                  {pref}
                </button>
              ))}
            </div>
          </div>

          {/* Toggles */}
          <div className="flex flex-wrap gap-2">
            {([
              { key: "groceryAccess", label: "Grocery Access" },
              { key: "waterAccess", label: "Water Access" },
              { key: "lowTraffic", label: "Low Traffic" },
            ] as const).map(({ key, label }) => (
              <button
                key={key}
                onClick={() => onPreferencesChange({ ...preferences, [key]: !preferences[key] })}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  preferences[key] ? "bg-trail text-white" : "bg-secondary text-muted-foreground"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
