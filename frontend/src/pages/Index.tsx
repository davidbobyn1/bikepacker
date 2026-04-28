import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { encodeRouteForUrl, buildShareUrl, decodeRouteFromUrl } from "../utils/shareLink";
import { Compass, Loader2, Sparkles, MapPin, Clock, Ruler, Target, Layers, AlertCircle, Bookmark, ArrowRight } from "lucide-react";
import type { RouteOption, RiderProfile, TripPreferences, TripContext } from "../types/route";
import { api } from "../services/api";
import TripPreferencesPanel from "../components/planner/TripPreferencesPanel";
import PlanningProgress from "../components/planner/PlanningProgress";
import RouteCard from "../components/results/RouteCard";
import RouteDetail from "../components/route/RouteDetail";
import RouteMap from "../components/route/RouteMap";
import SavedRoutesList from "../components/saved/SavedRoutesList";
import RouteCompareTable from "../components/saved/RouteCompareTable";
import { useSavedRoutes } from "../hooks/useSavedRoutes";
import bikeIllustration from "../assets/bike-illustration.png";

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
  const [showSaved, setShowSaved] = useState(false);
  const [compareRoutes, setCompareRoutes] = useState<RouteOption[] | null>(null);
  const { savedRoutes, saveRoute, removeRoute, isRouteSaved, renameRoute } = useSavedRoutes();

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

  // ── On mount: decode ?route= param and pre-load a shared route ───────────
  useEffect(() => {
    const param = new URLSearchParams(window.location.search).get("route");
    if (!param) return;
    try {
      const route = decodeRouteFromUrl(param);
      setRoutes([route]);
      setSelectedRoute(route);
      setActiveRouteId(route.id);
      setView("detail");
    } catch {
      // Malformed or old link — silently ignore and stay on planner
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Share: encode active route and copy URL to clipboard ─────────────────
  const handleShare = async (route: RouteOption) => {
    try {
      const encoded = encodeRouteForUrl(route);
      const url = buildShareUrl(route, encoded);
      await navigator.clipboard.writeText(url);
    } catch {
      // Clipboard blocked (non-HTTPS dev env) — fall back to prompt
      const encoded = encodeRouteForUrl(route);
      const url = buildShareUrl(route, encoded);
      window.prompt("Copy share link:", url);
    }
  };

  const handleGenerate = async () => {
    if (!prompt.trim()) return;
    setLoading(true);
    setError(null);
    setView("results");
    try {
      const response = await api.generateFull({ prompt, riderProfile, preferences });
      if (response.routes.length === 0 && response.no_results_reason) {
        setError(response.no_results_reason);
        setView("planner");
      } else {
        setRoutes(response.routes);
        setTripContext(response.trip_context);
        setActiveRouteId(response.routes[0]?.id ?? null);
      }
    } catch (err) {
      console.error("generateFull failed:", err);
      setError("Something went wrong generating your routes. Please try again.");
      setView("planner");
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

  const handleSaveToggle = (route: RouteOption) => {
    if (isRouteSaved(route.id)) removeRoute(route.id);
    else saveRoute(route);
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Trail-marker top stripe */}
      <div className="h-1 w-full bg-primary" />

      {/* Header */}
      <header className="border-b border-border bg-background/90 backdrop-blur-sm sticky top-1 z-50">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
          <button
            onClick={() => { setView("planner"); setSelectedRoute(null); setError(null); }}
            className="flex items-center gap-2.5 group"
          >
            <span className="inline-flex items-center justify-center w-7 h-7 rounded-sm border-2 border-primary text-primary group-hover:bg-primary group-hover:text-primary-foreground transition-colors">
              <Compass className="w-4 h-4" strokeWidth={2.25} />
            </span>
            <span className="font-serif text-xl text-foreground tracking-tight">Bikepacker</span>
          </button>

          {view !== "planner" && (
            <div className="flex items-center gap-3">
              {view === "results" && routes.length > 1 && (
                <button
                  onClick={() => setCompareMode((v) => !v)}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                    compareMode ? "bg-primary text-primary-foreground" : "bg-secondary text-foreground hover:opacity-80"
                  }`}
                >
                  <Layers className="w-3.5 h-3.5" />
                  {compareMode ? "Comparing" : "Compare Routes"}
                </button>
              )}
              <button
                onClick={() => setShowSaved(true)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-secondary text-foreground hover:opacity-80 transition-colors"
              >
                <Bookmark className="w-3.5 h-3.5" />
                {savedRoutes.length > 0 && <span>{savedRoutes.length}</span>}
              </button>
              <button
                onClick={() => { setView("planner"); setSelectedRoute(null); setError(null); }}
                className="text-sm text-muted-foreground hover:text-foreground transition-colors uppercase tracking-wider"
              >
                New trip
              </button>
            </div>
          )}
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8">
        <AnimatePresence mode="wait">
          {/* ── PLANNER ── */}
          {view === "planner" && (
            <motion.div key="planner" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="max-w-2xl mx-auto space-y-8">
              {/* Hero with bike illustration */}
              <div className="relative text-center pt-10 pb-2">
                <img
                  src={bikeIllustration}
                  alt=""
                  aria-hidden="true"
                  className="mx-auto w-full max-w-md opacity-90 -mb-4 select-none pointer-events-none"
                />
                <div className="space-y-3">
                  <p className="text-xs uppercase tracking-[0.25em] text-accent font-medium">A field guide to your next ride</p>
                  <h1 className="text-5xl sm:text-6xl font-serif text-foreground leading-[1.05] tracking-tight">
                    Where do you want<br />to ride?
                  </h1>
                  <p className="text-muted-foreground max-w-md mx-auto text-[15px] leading-relaxed pt-1">
                    Tell us about the trip in your head. We'll lay out routes, overnights, and resupply — like a guidebook written just for you.
                  </p>
                </div>
              </div>

              <div className="space-y-5">
                {/* Journal-style textarea */}
                <div className="relative rounded-lg border border-border bg-card shadow-[0_1px_0_rgba(0,0,0,0.03)] focus-within:border-primary/60 focus-within:shadow-[0_0_0_3px_hsl(var(--primary)/0.08)] transition-all">
                  <div className="absolute top-3 left-4 text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-medium">
                    Trip notes
                  </div>
                  <textarea
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleGenerate(); }}
                    placeholder="Three days north of San Francisco, mostly gravel, camping where possible. Want big climbs but a lodge or two if the weather turns…"
                    rows={5}
                    className="w-full bg-transparent px-4 pt-9 pb-4 text-[15px] font-serif text-foreground placeholder:text-muted-foreground/70 placeholder:font-serif placeholder:italic focus:outline-none resize-none leading-relaxed"
                  />
                </div>

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
                  className="group w-full flex items-center justify-center gap-2.5 px-6 py-4 rounded-lg bg-primary text-primary-foreground font-medium text-[15px] tracking-wide hover:bg-primary/90 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-[0_2px_0_hsl(var(--primary)/0.4)]"
                >
                  {loading ? (
                    <><Loader2 className="w-4 h-4 animate-spin" /> Charting your route…</>
                  ) : (
                    <>
                      <Compass className="w-4 h-4" strokeWidth={2.25} />
                      Plan my trip
                      <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
                    </>
                  )}
                </button>

                <p className="text-center text-xs text-muted-foreground/80 italic font-serif pt-1">
                  "The bicycle is a curious vehicle. Its passenger is its engine." — John Howard
                </p>
              </div>
            </motion.div>
          )}

          {/* ── RESULTS ── */}
          {view === "results" && (
            <motion.div key="results" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="space-y-6">
              {loading ? (
                <PlanningProgress estimatedDurationMs={35000} />
              ) : (
                <>
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
                          <span key={c} className="px-2 py-0.5 rounded-full bg-primary/10 text-primary text-xs font-medium">{c}</span>
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
                    <p className="text-sm text-muted-foreground mt-1">Each represents a different approach to your trip. Compare the tradeoffs, then dive into the full plan.</p>
                  </div>

                  <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                    {routes.map((route, i) => (
                      <RouteCard
                        key={route.id}
                        route={route}
                        index={i}
                        onViewDetails={handleViewDetails}
                        isBestFit={route.archetype === "scenic"}
                      />
                    ))}
                  </div>
                </>
              )}
            </motion.div>
          )}

          {/* ── DETAIL ── */}
          {view === "detail" && selectedRoute && (
            <motion.div
              key="detail"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onAnimationComplete={() => window.dispatchEvent(new Event("resize"))}
            >
              <RouteDetail
                route={selectedRoute}
                onBack={() => { setView("results"); setSelectedRoute(null); }}
                onSave={() => handleSaveToggle(selectedRoute)}
                isSaved={isRouteSaved(selectedRoute.id)}
                onShare={() => handleShare(selectedRoute)}
              />
            </motion.div>
          )}
        </AnimatePresence>
      </main>

      {/* Saved routes panel */}
      {showSaved && (
        <SavedRoutesList
          savedRoutes={savedRoutes}
          onClose={() => setShowSaved(false)}
          onOpen={(route) => { setShowSaved(false); handleViewDetails(route); }}
          onRemove={removeRoute}
          onRename={renameRoute}
          onCompare={(selected) => { setCompareRoutes(selected); setShowSaved(false); }}
        />
      )}

      {/* Compare table modal */}
      {compareRoutes && compareRoutes.length >= 2 && (
        <RouteCompareTable
          routes={compareRoutes}
          onClose={() => setCompareRoutes(null)}
          onOpen={(route: RouteOption) => { setCompareRoutes(null); handleViewDetails(route); }}
        />
      )}
    </div>
  );
}

function ContextChip({ icon, value }: { icon: React.ReactNode; value: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-secondary text-secondary-foreground text-sm font-medium">
      {icon} {value}
    </span>
  );
}
