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
  { id: "parse",     label: "Reading your brief",                     detail: "Extracting region, distance, gravel target, and constraints",            icon: <Sparkles className="w-4 h-4" />, weight: 0.06 },
  { id: "region",    label: "Loading regional trail data",             detail: "Fetching fire roads, gravel networks, and bike-legal segments",          icon: <Map className="w-4 h-4" />,      weight: 0.14 },
  { id: "candidate", label: "Generating candidate loops",              detail: "Building 12 candidate routes around your distance window",               icon: <Search className="w-4 h-4" />,   weight: 0.22 },
  { id: "terrain",   label: "Scoring terrain & climbing",              detail: "Estimating elevation, surface mix, and exposure for each candidate",     icon: <Mountain className="w-4 h-4" />, weight: 0.18 },
  { id: "overnight", label: "Finding overnight areas",                 detail: "Locating campsites, hotels, and dispersed options near day-end points",  icon: <Tent className="w-4 h-4" />,     weight: 0.16 },
  { id: "tradeoffs", label: "Weighing tradeoffs against your profile", detail: "Comparing scenery, safety, and logistics versus your rider fit",         icon: <Scale className="w-4 h-4" />,    weight: 0.16 },
  { id: "finalize",  label: "Packaging your trip plans",               detail: "Generating itineraries, GPX files, and confidence assessments",          icon: <Check className="w-4 h-4" />,    weight: 0.08 },
];

interface PlanningProgressProps {
  /** Total expected duration in ms. Real backend ~35s. */
  estimatedDurationMs?: number;
}

export default function PlanningProgress({ estimatedDurationMs = 35000 }: PlanningProgressProps) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const start = performance.now();
    const interval = setInterval(() => {
      setElapsed(performance.now() - start);
    }, 80);
    return () => clearInterval(interval);
  }, []);

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
    <div className="max-w-xl mx-auto pt-12">
      <div className="text-center mb-8">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-primary/10 text-primary text-xs font-medium mb-4">
          <Loader2 className="w-3.5 h-3.5 animate-spin" /> Planning in progress
        </div>
        <h2 className="text-2xl sm:text-3xl font-serif text-foreground">
          Designing your trip…
        </h2>
        <p className="text-sm text-muted-foreground mt-2">
          We're working through {STEPS.length} planning steps. This usually takes 20–40 seconds.
        </p>
      </div>

      {/* Overall progress bar */}
      <div className="mb-8">
        <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden">
          <motion.div
            className="h-full bg-gradient-to-r from-primary to-primary/70"
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
              className={`flex items-start gap-3 rounded-lg border px-3.5 py-3 transition-colors ${
                status === "active"
                  ? "border-primary/30 bg-primary/5"
                  : status === "done"
                  ? "border-border bg-card"
                  : "border-border/60 bg-card/50"
              }`}
            >
              <div
                className={`flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center ${
                  status === "done"
                    ? "bg-trail/15 text-trail"
                    : status === "active"
                    ? "bg-primary/15 text-primary"
                    : "bg-muted text-muted-foreground"
                }`}
              >
                {status === "done" ? (
                  <Check className="w-3.5 h-3.5" />
                ) : status === "active" ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  step.icon
                )}
              </div>
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
                      <p className="text-xs text-muted-foreground mt-1 leading-relaxed">{step.detail}</p>
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
        Tip: more specific prompts (region, distance, gravel %) yield better-fit routes.
      </p>
    </div>
  );
}
