import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Compass, Loader2, Sparkles, MapPin, Clock, Ruler, Target, Layers, AlertCircle } from "lucide-react";
import type { RouteOption, RiderProfile, TripPreferences, TripContext } from "../types/route";
import { api } from "../services/api";
import TripPreferencesPanel from "../components/planner/TripPreferencesPanel";
import RouteCard from "../components/results/RouteCard";
import RouteDetail from "../components/route/RouteDetail";
import RouteMap from "../components/route/RouteMap";

type View = "planner" | "results" | "detail";

export default function Index() {
  const [view, setView] = useState<View>("planner");
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [routes, setRoutes] = useState<RouteOption[]>([]);
  const [selectedRoute, setSelectedRoute] = useState<RouteOption | null>(null);
  const [activeRouteId, setActiveRouteId] = useState<string | null>(null);
  const [compareMode, setCompareMode] = useState(false);
  const [tripContext, setTripContext] = useState<TripContext | null>(null);

  const [riderProfile, setRiderProfile] = useState<RiderProfile>({
    fitness: "intermediate",
    technicalSkill: "intermediate",
    overnightExperience: "some",
  });

  const [preferences, setPreferences] = useState<TripPreferences>({
    overnightPreference: "flexible",
    routeShape: "loop",
    groceryAccess: true,
    waterAccess: true,
    lowTraffic: true,
  });

  const handleGenerate = async () => {
    if (!prompt.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const response = await api.generateFull({ prompt, riderProfile, preferences });
      if (response.routes.length === 0 && response.no_results_reason) {
        setError(response.no_results_reason);
      } else {
        setRoutes(response.routes);
        setTripContext(response.trip_context);
        setActiveRouteId(response.routes[0]?.id ?? null);
        setView("results");
      }
    } catch (err) {
      console.error("generateFull failed:", err);
      setError("Something went wrong generating your routes. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleViewDetails = (route: RouteOption) => {
    setSelectedRoute(route);
    setActiveRouteId(route.id);
    setView("detail");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleSelectRoute = (routeId: string) => {
    setActiveRouteId(routeId);
    if (!compareMode) {
      const r = routes.find((r) => r.id === routeId);
      if (r) setSelectedRoute(r);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border bg-card sticky top-0 z-50" style={{ backdropFilter: "blur(8px)" }}>
        <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
          <button
            onClick={() => { setView("planner"); setSelectedRoute(null); setError(null); }}
            className="flex items-center gap-2 text-foreground font-serif text-lg hover:opacity-80 transition-opacity"
          >
            <Compass className="w-5 h-5 text-primary" />
            Bikepacker
          </button>
          {view !== "planner" && (
            <div className="flex items-center gap-3">
              {view === "results" && routes.length > 1 && (
                <button
                  onClick={() => setCompareMode((v) => !v)}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                    compareMode ? "bg-primary text-white" : "bg-secondary text-foreground hover:opacity-80"
                  }`}
                >
                  <Layers className="w-3.5 h-3.5" />
                  {compareMode ? "Comparing" : "Compare Routes"}
                </button>
              )}
              <button
                onClick={() => { setView("planner"); setSelectedRoute(null); setError(null); }}
                className="text-sm text-muted-foreground hover:text-foreground transition-colors"
              >
                New trip
              </button>
            </div>
          )}
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-8">
        <AnimatePresence mode="wait">
          {/* PLANNER */}
          {view === "planner" && (
            <motion.div key="planner" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="max-w-2xl mx-auto space-y-6">
              <div className="text-center space-y-3 pt-8 pb-4">
                <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium mb-2" style={{ background: "rgba(37,99,235,0.1)", color: "#2563eb" }}>
                  <Sparkles className="w-3.5 h-3.5" /> AI Trip Planner
                </div>
                <h1 className="text-3xl font-serif text-foreground">Plan your next bikepacking trip</h1>
                <p className="text-muted-foreground max-w-lg mx-auto text-sm">
                  Describe your ideal ride in plain language. We'll generate complete trip plans with overnight options, logistics, and downloadable GPX files.
                </p>
              </div>

              <div className="space-y-4">
                <textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleGenerate(); }}
                  placeholder="Plan me a 2–3 day bikepacking loop north of San Francisco for an intermediate rider, 150–200 km, around 50% gravel, with legal overnight options, low traffic, grocery access, and a GPX."
                  rows={4}
                  className="w-full rounded-xl border border-border bg-card px-4 py-3 text-sm text-foreground placeholder-muted-foreground focus:outline-none focus:ring-2 resize-none"
                />

                <TripPreferencesPanel
                  riderProfile={riderProfile}
                  preferences={preferences}
                  onRiderProfileChange={setRiderProfile}
                  onPreferencesChange={setPreferences}
                />

                {error && (
                  <div className="flex items-start gap-2 p-3 rounded-xl text-sm" style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.2)", color: "#ef4444" }}>
                    <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                    {error}
                  </div>
                )}

                <button
                  onClick={handleGenerate}
                  disabled={loading || !prompt.trim()}
                  className="w-full flex items-center justify-center gap-2 px-6 py-3.5 rounded-xl bg-primary text-white font-medium text-sm hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loading ? (
                    <><Loader2 className="w-4 h-4 animate-spin" /> Planning your trip…</>
                  ) : (
                    <><Compass className="w-4 h-4" /> Generate Trip Plans</>
                  )}
                </button>
              </div>
            </motion.div>
          )}

          {/* RESULTS */}
          {view === "results" && (
            <motion.div key="results" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="space-y-6">
              {tripContext && (
                <div className="bg-card border border-border rounded-xl p-5">
                  <div className="flex items-center gap-2 mb-3">
                    <Sparkles className="w-4 h-4 text-primary" />
                    <h2 className="text-lg font-serif text-foreground">Your Trip Brief</h2>
                  </div>
                  <div className="flex flex-wrap gap-3 mb-3">
                    <ContextChip icon={<MapPin className="w-3.5 h-3.5" />} value={tripContext.parsed_region} />
                    <ContextChip icon={<Clock className="w-3.5 h-3.5" />} value={tripContext.parsed_duration} />
                    <ContextChip icon={<Ruler className="w-3.5 h-3.5" />} value={tripContext.parsed_distance} />
                    <ContextChip icon={<Target className="w-3.5 h-3.5" />} value={tripContext.parsed_gravel_target} />
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {tripContext.key_constraints.map((c) => (
                      <span key={c} className="px-2 py-0.5 rounded-full text-xs font-medium" style={{ background: "rgba(37,99,235,0.1)", color: "#2563eb" }}>{c}</span>
                    ))}
                  </div>
                </div>
              )}

              {compareMode && routes.length > 0 && (
                <div className="rounded-xl overflow-hidden border border-border">
                  <RouteMap routes={routes} activeRouteId={activeRouteId} compareMode={true} onRouteClick={handleSelectRoute} className="h-96" />
                  <div className="bg-card px-4 py-2 flex items-center gap-4 text-xs text-muted-foreground border-t border-border">
                    {routes.map((r) => {
                      const colors: Record<string, string> = { scenic: "#f59e0b", easier: "#3b82f6", adventurous: "#10b981" };
                      return (
                        <button key={r.id} onClick={() => handleSelectRoute(r.id)} className={`flex items-center gap-1.5 transition-opacity ${r.id === activeRouteId ? "opacity-100 font-medium" : "opacity-50 hover:opacity-75"}`}>
                          <span className="w-3 h-3 rounded-full inline-block" style={{ background: colors[r.archetype] }} />
                          {r.archetype_label}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              <div>
                <h2 className="text-2xl font-serif text-foreground">We found {routes.length} route options</h2>
                <p className="text-sm text-muted-foreground mt-1">Each represents a different approach to your trip.</p>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                {routes.map((route, i) => (
                  <RouteCard key={route.id} route={route} index={i} onViewDetails={handleViewDetails} />
                ))}
              </div>
            </motion.div>
          )}

          {/* DETAIL */}
          {view === "detail" && selectedRoute && (
            <motion.div
              key="detail"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onAnimationComplete={() => {
                // Force MapLibre to recalculate canvas size after fade-in animation
                window.dispatchEvent(new Event("resize"));
              }}
            >
              <RouteDetail route={selectedRoute} onBack={() => { setView("results"); setSelectedRoute(null); }} />
            </motion.div>
          )}
        </AnimatePresence>
      </main>
    </div>
  );
}

function ContextChip({ icon, value }: { icon: React.ReactNode; value: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-secondary text-foreground text-sm font-medium">
      {icon} {value}
    </span>
  );
}
