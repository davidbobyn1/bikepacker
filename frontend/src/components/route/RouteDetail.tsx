import React, { useState } from "react";
import { motion } from "framer-motion";
import {
  ArrowLeft, Download, Loader2, Mountain, Ruler, Percent, Clock,
  ShoppingCart, Droplets, Building, AlertTriangle, Info, MapPin,
  Tent, Hotel, CheckCircle2, Eye, Shield, Flame, ChevronRight,
  Moon, ArrowUpDown, Zap, ExternalLink, Bookmark, BookmarkCheck,
  Share2, Check,
} from "lucide-react";
import RouteMap from "./RouteMap";
import ConfidenceBadge from "./ConfidenceBadge";
import type { RouteOption, TerrainNote } from "../../types/route";
import { api } from "../../services/api";

const API_BASE = process.env.REACT_APP_API_BASE || "http://localhost:8000/api";
const getFullGpxUrl = (gpxUrl: string) => {
  if (!gpxUrl) return "#";
  if (gpxUrl.startsWith("http")) return gpxUrl;
  // Strip /api prefix from gpxUrl if API_BASE already includes it
  const path = gpxUrl.startsWith("/api/") ? gpxUrl.slice(4) : gpxUrl;
  return `${API_BASE}${path}`;
};

interface RouteDetailProps {
  route: RouteOption;
  onBack: () => void;
  onSave?: () => void;
  isSaved?: boolean;
  onShare?: () => Promise<void>;
}

const archetypeIcons: Record<string, React.ReactNode> = {
  scenic: <Eye className="w-5 h-5" />,
  easier: <Shield className="w-5 h-5" />,
  adventurous: <Flame className="w-5 h-5" />,
};

const archetypeAccent: Record<string, string> = {
  scenic: "bg-trail/10 text-trail",
  easier: "bg-hotel/10 text-hotel",
  adventurous: "bg-camp/10 text-camp",
};

// Extract route_id from gpx_url like "/api/gpx/{route_id}"
const getRouteId = (gpxUrl: string): string => {
  if (!gpxUrl) return "";
  const parts = gpxUrl.split("/");
  return parts[parts.length - 1] || "";
};

export default function RouteDetail({ route, onBack, onSave, isSaved, onShare }: RouteDetailProps) {
  const [expandedDay, setExpandedDay] = useState<number | null>(1);
  const [rwgpsLoading, setRwgpsLoading] = useState(false);
  const [rwgpsError, setRwgpsError] = useState<string | null>(null);
  const [shareCopied, setShareCopied] = useState(false);

  const handleShare = async () => {
    if (!onShare) return;
    await onShare();
    setShareCopied(true);
    setTimeout(() => setShareCopied(false), 2500);
  };

  const handleExportToRwgps = async () => {
    const routeId = getRouteId(route.gpx_url);
    if (!routeId) {
      setRwgpsError("Route ID not found. Please regenerate the route and try again.");
      return;
    }
    setRwgpsLoading(true);
    setRwgpsError(null);
    try {
      const data = await api.exportToRwgps(routeId);
      if (data.url) {
        window.open(data.url, "_blank");
      }
    } catch (err: any) {
      // Parse the error message from the API response if possible
      let msg = "Export failed. Please try again.";
      if (err?.message?.includes("503")) {
        msg = "RideWithGPS export is not configured. Download the GPX file and import it manually at ridewithgps.com/routes/new.";
      } else if (err?.message?.includes("404")) {
        msg = "Route has expired — please regenerate your trip and try again.";
      } else if (err?.message?.includes("502")) {
        msg = "RideWithGPS API error. Try downloading the GPX and importing manually.";
      }
      setRwgpsError(msg);
    } finally {
      setRwgpsLoading(false);
    }
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-8">
      {/* Back nav + Save + Share */}
      <div className="flex items-center justify-between">
        <button onClick={onBack} className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors">
          <ArrowLeft className="w-4 h-4" /> Back to route options
        </button>
        <div className="flex items-center gap-2">
          {onShare && (
            <button
              onClick={handleShare}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-secondary text-foreground hover:opacity-80 transition-opacity"
            >
              {shareCopied ? <Check className="w-3.5 h-3.5 text-trail" /> : <Share2 className="w-3.5 h-3.5" />}
              {shareCopied ? "Copied!" : "Share"}
            </button>
          )}
          {onSave && (
            <button
              onClick={onSave}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-secondary text-foreground hover:opacity-80 transition-opacity"
            >
              {isSaved ? <BookmarkCheck className="w-3.5 h-3.5 text-primary" /> : <Bookmark className="w-3.5 h-3.5" />}
              {isSaved ? "Saved" : "Save route"}
            </button>
          )}
        </div>
      </div>

      {/* Hero header */}
      <div className="flex items-start gap-4">
        <div className={`p-3 rounded-xl ${archetypeAccent[route.archetype]}`}>
          {archetypeIcons[route.archetype]}
        </div>
        <div>
          {/* AI-generated trip title (new) */}
          <h1 className="text-2xl sm:text-3xl font-serif text-foreground">
            {route.trip_title || route.archetype_label}
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            {route.tagline || route.archetype_tagline}
          </p>
          <div className="mt-2 flex items-center gap-2">
            <ConfidenceBadge level={route.confidence_level} />
            <span className="text-xs text-muted-foreground">·</span>
            <span className="text-xs text-muted-foreground">{route.estimated_days}-day trip</span>
          </div>
        </div>
      </div>

      {/* Map + Summary sidebar */}
      <div className="flex flex-col lg:flex-row gap-6">
        <div className="lg:w-3/5">
          <RouteMap route={route} className="h-[420px] lg:h-[520px]" />
          <div className="flex items-center gap-4 mt-3 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1"><span className="w-3 h-3 rounded-full bg-camp inline-block" /> Overnight area</span>
            <span className="inline-flex items-center gap-1"><span className="w-3 h-3 rounded-full bg-trail inline-block" /> Campsite</span>
            <span className="inline-flex items-center gap-1"><span className="w-3 h-3 rounded-full bg-hotel inline-block" /> Hotel/Motel</span>
          </div>
        </div>

        <div className="lg:w-2/5 space-y-4">
          {/* Quick stats */}
          <div className="grid grid-cols-2 gap-2">
            <StatBox icon={<Ruler className="w-4 h-4" />} label="Total Distance" value={`${route.total_distance_km} km`} />
            <StatBox icon={<Mountain className="w-4 h-4" />} label="Total Climbing" value={`${route.total_climbing_m} m`} />
            <StatBox icon={<Percent className="w-4 h-4" />} label="Gravel Ratio" value={`${Math.round(route.gravel_ratio * 100)}%`} />
            <StatBox icon={<Clock className="w-4 h-4" />} label="Est. Ride Time" value={`${route.day_segments.reduce((s, d) => s + d.estimated_hours, 0).toFixed(0)}h`} />
          </div>

          {/* Logistics strip */}
          <div className="bg-card border border-border rounded-xl p-4">
            <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">Logistics at a Glance</h4>
            <div className="space-y-2">
              <LogisticsRow icon={<ShoppingCart className="w-4 h-4" />} label="Nearest grocery" value={`${route.grocery_distance_km} km from route`} good={route.grocery_distance_km <= 1} />
              <LogisticsRow icon={<Droplets className="w-4 h-4" />} label="Nearest water" value={`${route.water_distance_km} km from route`} good={route.water_distance_km <= 2} />
              <LogisticsRow icon={<Building className="w-4 h-4" />} label="Hotel fallback" value={`${route.hotel_fallback_distance_km} km from route`} good={route.hotel_fallback_distance_km <= 2} />
            </div>
            {/* AI logistics note (new) */}
            {route.logistics_note && (
              <p className="mt-3 text-xs text-muted-foreground leading-relaxed border-t border-border pt-3 italic">
                {route.logistics_note}
              </p>
            )}
          </div>

          {/* GPX download + RideWithGPS export */}
          <div className="flex flex-col gap-2">
            <a
              href={getFullGpxUrl(route.gpx_url)}
              download
              target="_blank"
              rel="noopener noreferrer"
              className="w-full inline-flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-primary text-primary-foreground font-medium hover:opacity-90 transition-opacity"
            >
              <Download className="w-4 h-4" /> Download GPX File
            </a>
            <button
              onClick={handleExportToRwgps}
              disabled={rwgpsLoading}
              className="w-full inline-flex items-center justify-center gap-2 px-4 py-3 rounded-xl border border-border bg-background text-foreground font-medium hover:bg-muted transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {rwgpsLoading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <svg width="18" height="18" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <circle cx="32" cy="32" r="32" fill="#FF6B00"/>
                  <path d="M20 44 L32 20 L44 44" stroke="white" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
                  <circle cx="32" cy="20" r="4" fill="white"/>
                </svg>
              )}
              {rwgpsLoading ? "Exporting…" : "Export to RideWithGPS"}
            </button>
            {rwgpsError && (
              <p className="text-xs text-destructive leading-snug px-1">{rwgpsError}</p>
            )}
          </div>
        </div>
      </div>

      {/* ── STRAVA COMMUNITY HIGHLIGHTS (new) ── */}
      {route.strava_highlights && route.strava_highlights.length > 0 && (
        <Section title="Community Highlights" icon={<Zap className="w-5 h-5 text-orange-400" />}>
          <p className="text-sm text-muted-foreground mb-3">
            This route passes through {route.strava_highlights.length} popular Strava segment{route.strava_highlights.length > 1 ? "s" : ""} — roads real cyclists love.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {route.strava_highlights.map((seg) => (
              <a
                key={seg.id}
                href={seg.strava_url}
                target="_blank"
                rel="noopener noreferrer"
                className="bg-card border border-border rounded-xl p-3 space-y-1 hover:border-orange-400/50 transition-colors group"
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-foreground group-hover:text-orange-400 transition-colors">{seg.name}</span>
                  <ExternalLink className="w-3.5 h-3.5 text-muted-foreground group-hover:text-orange-400" />
                </div>
                <div className="flex items-center gap-3 text-xs text-muted-foreground">
                  <span>{seg.distance_km} km</span>
                  <span>·</span>
                  <span>{seg.avg_grade_pct}% avg grade</span>
                  <span>·</span>
                  <span className="text-orange-400/80">{seg.climb_category}</span>
                </div>
              </a>
            ))}
          </div>
        </Section>
      )}

      {/* ── WHY THIS FITS YOU ── */}
      <Section title="Why This Fits You" icon={<CheckCircle2 className="w-5 h-5 text-trail" />}>
        <p className="text-sm text-muted-foreground leading-relaxed mb-4">{route.why_this_route}</p>
        <div className="space-y-2">
          {route.rider_fit_reasons.map((reason, i) => (
            <div key={i} className="flex items-start gap-2">
              {reason.icon_type === "check" && <CheckCircle2 className="w-4 h-4 text-trail flex-shrink-0 mt-0.5" />}
              {reason.icon_type === "warning" && <AlertTriangle className="w-4 h-4 text-camp flex-shrink-0 mt-0.5" />}
              {reason.icon_type === "info" && <Info className="w-4 h-4 text-hotel flex-shrink-0 mt-0.5" />}
              <span className="text-sm text-foreground">{reason.text}</span>
            </div>
          ))}
        </div>
        {/* Confidence framing (new) */}
        {route.confidence_framing && (
          <p className="mt-3 text-xs text-muted-foreground/70 italic border-t border-border pt-3">
            {route.confidence_framing}
          </p>
        )}
      </Section>

      {/* ── TRADEOFFS ── */}
      <Section title="Tradeoffs" icon={<ArrowUpDown className="w-5 h-5 text-accent" />}>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {route.tradeoffs.map((t, i) => (
            <div key={i} className="bg-card border border-border rounded-xl p-4 space-y-2">
              <h4 className="text-sm font-semibold text-foreground">{t.label}</h4>
              <div className="flex items-start gap-1.5 text-xs">
                <span className="text-trail font-medium mt-0.5">+</span>
                <span className="text-muted-foreground">{t.pro}</span>
              </div>
              <div className="flex items-start gap-1.5 text-xs">
                <span className="text-camp font-medium mt-0.5">−</span>
                <span className="text-muted-foreground">{t.con}</span>
              </div>
            </div>
          ))}
        </div>
        {route.tradeoff_statement && (
          <p className="text-xs text-muted-foreground/70 italic mt-2">{route.tradeoff_statement}</p>
        )}
      </Section>

      {/* ── CONFIDENCE ── */}
      <Section title="Confidence Assessment" icon={<Shield className="w-5 h-5 text-primary" />}>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {route.confidence_details.map((d, i) => (
            <div key={i} className="bg-card border border-border rounded-xl p-4">
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-sm font-medium text-foreground">{d.aspect}</span>
                <ConfidenceBadge level={d.level} />
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed">{d.note}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* ── DAY-BY-DAY ITINERARY ── */}
      <Section title="Day-by-Day Itinerary" icon={<MapPin className="w-5 h-5 text-primary" />}>
        <div className="space-y-3">
          {route.day_segments.map((seg) => {
            const isExpanded = expandedDay === seg.day;
            return (
              <div key={seg.day} className="bg-card border border-border rounded-xl overflow-hidden">
                <button
                  onClick={() => setExpandedDay(isExpanded ? null : seg.day)}
                  className="w-full flex items-center justify-between p-5 text-left hover:bg-muted/30 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                      <span className="text-sm font-bold text-primary">{seg.day}</span>
                    </div>
                    <div>
                      <h3 className="text-base font-serif text-foreground">{seg.title}</h3>
                      <div className="flex items-center gap-2 mt-0.5 text-xs text-muted-foreground">
                        <span>{seg.distance_km} km</span>
                        <span>·</span>
                        <span>{seg.climbing_m} m↑</span>
                        <span>·</span>
                        <span>{Math.round(seg.gravel_ratio * 100)}% gravel</span>
                        <span>·</span>
                        <span>~{seg.estimated_hours}h ride</span>
                      </div>
                    </div>
                  </div>
                  <ChevronRight className={`w-5 h-5 text-muted-foreground transition-transform ${isExpanded ? "rotate-90" : ""}`} />
                </button>

                {isExpanded && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="px-5 pb-5 space-y-4 border-t border-border pt-4"
                  >
                    {/* AI day narrative */}
                    <p className="text-sm text-muted-foreground leading-relaxed">{seg.description}</p>

                    {/* Key advice callout (new) */}
                    {seg.key_advice && (
                      <div className="flex items-start gap-2 p-3 rounded-lg bg-primary/5 border border-primary/20">
                        <Zap className="w-4 h-4 text-primary flex-shrink-0 mt-0.5" />
                        <p className="text-xs text-foreground">{seg.key_advice}</p>
                      </div>
                    )}

                    {/* Highlights */}
                    {seg.highlights.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {seg.highlights.map((h) => (
                          <span key={h} className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-primary/10 text-primary text-xs font-medium">
                            <MapPin className="w-3 h-3" /> {h}
                          </span>
                        ))}
                      </div>
                    )}

                    {/* Terrain notes */}
                    {seg.terrain_notes.length > 0 && (
                      <div className="space-y-1.5">
                        <h5 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Terrain Notes</h5>
                        {seg.terrain_notes.map((tn, i) => (
                          <TerrainNoteRow key={i} note={tn} />
                        ))}
                      </div>
                    )}

                    {/* Water & Grocery */}
                    <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
                      {seg.water_points.length > 0 && (
                        <span className="flex items-center gap-1.5">
                          <Droplets className="w-3.5 h-3.5 text-hotel" />
                          <span className="font-medium text-foreground">Water:</span> {seg.water_points.join(" → ")}
                        </span>
                      )}
                      {seg.grocery_points.length > 0 && (
                        <span className="flex items-center gap-1.5">
                          <ShoppingCart className="w-3.5 h-3.5" />
                          <span className="font-medium text-foreground">Grocery:</span> {seg.grocery_points.join(" → ")}
                        </span>
                      )}
                    </div>

                    {/* Overnight area */}
                    {seg.overnight_area && (
                      <div className="bg-secondary/40 rounded-xl p-4 space-y-3 border border-border/50">
                        <div>
                          <h4 className="text-sm font-semibold text-foreground flex items-center gap-1.5">
                            <Moon className="w-4 h-4 text-camp" /> Overnight Options Near Day-End
                          </h4>
                          {seg.overnight_area.framing_note && (
                            <p className="text-xs text-muted-foreground mt-0.5 italic">{seg.overnight_area.framing_note}</p>
                          )}
                        </div>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                          {seg.overnight_area.options.map((opt) => (
                            <div key={opt.id} className="bg-card rounded-lg border border-border p-3 space-y-1.5">
                              <div className="flex items-center gap-1.5">
                                {opt.type === "campsite" || opt.type === "dispersed" ? (
                                  <Tent className="w-4 h-4 text-trail" />
                                ) : (
                                  <Hotel className="w-4 h-4 text-hotel" />
                                )}
                                <span className="text-sm font-medium text-foreground">{opt.name}</span>
                                <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground capitalize">{opt.type}</span>
                              </div>
                              <p className="text-xs text-muted-foreground leading-snug">{opt.description}</p>
                              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                                <span>{opt.distance_from_route_km} km from route</span>
                                {opt.cost_estimate && <span className="font-medium text-foreground">· {opt.cost_estimate}</span>}
                              </div>
                              {opt.reservation_note && (
                                <p className="text-[11px] text-camp italic">{opt.reservation_note}</p>
                              )}
                              {opt.amenities.length > 0 && (
                                <div className="flex flex-wrap gap-1 pt-0.5">
                                  {opt.amenities.map((a) => (
                                    <span key={a} className="px-1.5 py-0.5 rounded bg-muted text-muted-foreground text-[10px]">{a}</span>
                                  ))}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </motion.div>
                )}
              </div>
            );
          })}
        </div>
      </Section>

      {/* ── BAILOUT OPTIONS ── */}
      {route.bailout_notes.length > 0 && (
        <Section title="Bailout Options" icon={<AlertTriangle className="w-5 h-5 text-accent" />}>
          <ul className="space-y-2">
            {route.bailout_notes.map((note, i) => (
              <li key={i} className="text-sm text-muted-foreground flex items-start gap-2.5">
                <span className="mt-1.5 w-2 h-2 rounded-full bg-accent flex-shrink-0" />
                {note}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {/* Bottom GPX CTA */}
      <div className="flex justify-center pb-4">
        <a
          href={getFullGpxUrl(route.gpx_url)}
          download
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 px-8 py-3 rounded-xl bg-primary text-primary-foreground font-medium hover:opacity-90 transition-opacity"
        >
          <Download className="w-4 h-4" /> Download GPX & Start Planning
        </a>
      </div>
    </motion.div>
  );
}

function Section({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="space-y-4">
      <h2 className="text-xl font-serif text-foreground flex items-center gap-2">
        {icon} {title}
      </h2>
      {children}
    </div>
  );
}

function StatBox({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="bg-card border border-border rounded-xl p-3 text-center">
      <div className="flex justify-center text-primary mb-1">{icon}</div>
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="text-sm font-bold text-foreground">{value}</div>
    </div>
  );
}

function LogisticsRow({ icon, label, value, good }: { icon: React.ReactNode; label: string; value: string; good: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <span className={good ? "text-trail" : "text-muted-foreground"}>{icon}</span>
      <span className="text-sm text-foreground font-medium flex-1">{label}</span>
      <span className={`text-sm ${good ? "text-trail font-medium" : "text-muted-foreground"}`}>{value}</span>
    </div>
  );
}

function TerrainNoteRow({ note }: { note: TerrainNote }) {
  const styles: Record<string, { icon: React.ReactNode; color: string }> = {
    info: { icon: <Info className="w-3.5 h-3.5" />, color: "text-hotel" },
    caution: { icon: <AlertTriangle className="w-3.5 h-3.5" />, color: "text-accent" },
    warning: { icon: <AlertTriangle className="w-3.5 h-3.5" />, color: "text-destructive" },
  };
  const s = styles[note.severity] || styles.info;
  return (
    <div className={`flex items-start gap-2 text-xs ${s.color}`}>
      <span className="flex-shrink-0 mt-0.5">{s.icon}</span>
      <div>
        <span className="font-medium">{note.label}: </span>
        <span className="text-muted-foreground">{note.description}</span>
      </div>
    </div>
  );
}
