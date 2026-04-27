import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Check, Loader2, Search, Map, Mountain, Tent, Sparkles, Scale } from "lucide-react";

interface Step {
  id: string;
  label: string;
  detail: string;
  icon: React.ReactNode;
  /** approximate share of total time, summed = 1 */
  weight: number;
}

const STEPS: Step[] = [
  {
    id: "parse",
    label: "Reading your brief",
    detail: "Extracting region, distance, gravel target, and riding constraints",
    icon: <Sparkles className="w-4 h-4" />,
    weight: 0.06,
  },
  {
    id: "region",
    label: "Loading trail network",
    detail: "Fetching fire roads, gravel tracks, and bike-legal routes in your region",
    icon: <Map className="w-4 h-4" />,
    weight: 0.14,
  },
  {
    id: "candidate",
    label: "Sketching candidate loops",
    detail: "Laying out corridor shapes across your distance window",
    icon: <Search className="w-4 h-4" />,
    weight: 0.22,
  },
  {
    id: "terrain",
    label: "Scoring terrain & climbing",
    detail: "Pulling real elevation data and surface mix for each candidate",
    icon: <Mountain className="w-4 h-4" />,
    weight: 0.18,
  },
  {
    id: "overnight",
    label: "Finding overnight spots",
    detail: "Locating campsites, huts, and hotel fallbacks near natural day-end points",
    icon: <Tent className="w-4 h-4" />,
    weight: 0.16,
  },
  {
    id: "tradeoffs",
    label: "Weighing the tradeoffs",
    detail: "Comparing scenery, remoteness, and logistics against your rider profile",
    icon: <Scale className="w-4 h-4" />,
    weight: 0.16,
  },
  {
    id: "finalize",
    label: "Packaging your plans",
    detail: "Generating itineraries, GPX files, and confidence assessments",
    icon: <Check className="w-4 h-4" />,
    weight: 0.08,
  },
];

interface PlanningProgressProps {
  /** Total expected duration in ms. Real backend ~40s. */
  estimatedDurationMs?: number;
}

export default function PlanningProgress({ estimatedDurationMs = 40000 }: PlanningProgressProps) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const start = performance.now();
    const interval = setInterval(() => {
      setElapsed(performance.now() - start);
    }, 80);
    return () => clearInterval(interval);
  }, []);

  // Compute active step from weighted timeline, cap at 98.5% so it never "finishes" before the backend
  const progress = Math.min(elapsed / estimatedDurationMs, 0.985);
  let acc = 0;
  let activeIndex = 0;
  for (let i = 0; i < STEPS.length; i++) {
    if (progress < acc + STEPS[i].weight) {
      activeIndex = i;
      break;
    }
    acc += STEPS[i].weight;
    activeIndex = i;
  }

  return (
    <div className="max-w-lg mx-auto pt-10 pb-8">
      {/* Header */}
      <div className="text-center mb-8">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium mb-4"
          style={{ background: "rgba(22,163,74,0.12)", color: "#16a34a" }}>
          <Loader2 className="w-3.5 h-3.5 animate-spin" /> Planning in progress
        </div>
        <h2 className="text-2xl sm:text-3xl font-serif text-foreground">
          Designing your route…
        </h2>
        <p className="text-sm text-muted-foreground mt-2 max-w-sm mx-auto">
          Working through {STEPS.length} planning steps. Usually takes 20–45 seconds.
        </p>
      </div>

      {/* Overall progress bar — trail green */}
      <div className="mb-8">
        <div className="h-1.5 w-full rounded-full overflow-hidden" style={{ background: "#e2e8f0" }}>
          <motion.div
            className="h-full rounded-full"
            style={{ background: "linear-gradient(90deg, #16a34a, #22c55e)" }}
            initial={{ width: 0 }}
            animate={{ width: `${progress * 100}%` }}
            transition={{ ease: "linear", duration: 0.1 }}
          />
        </div>
        <div className="flex justify-between text-[11px] text-muted-foreground mt-1.5 font-mono">
          <span>{Math.round(progress * 100)}%</span>
          <span>{(elapsed / 1000).toFixed(1)}s</span>
        </div>
      </div>

      {/* Step list */}
      <ol className="space-y-2">
        {STEPS.map((step, i) => {
          const status: "done" | "active" | "pending" =
            i < activeIndex ? "done" : i === activeIndex ? "active" : "pending";

          return (
            <motion.li
              key={step.id}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.04 }}
              className="flex items-start gap-3 rounded-lg border px-3.5 py-3 transition-colors"
              style={{
                borderColor: status === "active" ? "rgba(22,163,74,0.3)" : "#e2e8f0",
                background: status === "active" ? "rgba(22,163,74,0.05)" : status === "done" ? "#ffffff" : "rgba(248,250,252,0.6)",
              }}
            >
              {/* Step icon / status indicator */}
              <div
                className="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center"
                style={{
                  background: status === "done"
                    ? "rgba(22,163,74,0.15)"
                    : status === "active"
                    ? "rgba(22,163,74,0.15)"
                    : "#f1f5f9",
                  color: status === "pending" ? "#94a3b8" : "#16a34a",
                }}
              >
                {status === "done" ? (
                  <Check className="w-3.5 h-3.5" />
                ) : status === "active" ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  step.icon
                )}
              </div>

              {/* Label + expanding detail */}
              <div className="flex-1 min-w-0">
                <div className={`text-sm font-medium leading-tight ${status === "pending" ? "text-muted-foreground" : "text-foreground"}`}>
                  {step.label}
                </div>
                <AnimatePresence>
                  {status === "active" && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      className="overflow-hidden"
                    >
                      <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                        {step.detail}
                      </p>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              {status === "done" && (
                <span className="text-[10px] font-mono text-muted-foreground self-center">done</span>
              )}
            </motion.li>
          );
        })}
      </ol>

      <p className="text-center text-xs text-muted-foreground mt-6">
        Tip: include region, days, distance, and gravel % for the best-fit results.
      </p>
    </div>
  );
}
