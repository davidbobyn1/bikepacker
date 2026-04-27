import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, Send, Loader2, RotateCcw, Check } from "lucide-react";
import type { RouteOption } from "../../types/route";

interface RefineRoutePanelProps {
  route: RouteOption;
  onApplyRefinement?: (instruction: string) => void;
}

interface RefinementMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  proposedChanges?: string[];
  status?: "pending" | "applied" | "dismissed";
}

const SUGGESTION_CHIPS = [
  "Make day 2 shorter",
  "Swap the hotel for camping",
  "Avoid the gravel section on day 1",
  "Add a rest day",
  "More climbing, fewer kilometres",
];

export default function RefineRoutePanel({ route, onApplyRefinement }: RefineRoutePanelProps) {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<RefinementMessage[]>([]);
  const [isThinking, setIsThinking] = useState(false);

  const send = (text: string) => {
    if (!text.trim() || isThinking) return;
    const userMsg: RefinementMessage = {
      id: `u-${Date.now()}`,
      role: "user",
      text: text.trim(),
    };
    setMessages((m) => [...m, userMsg]);
    setInput("");
    setIsThinking(true);

    // TODO: replace with POST /api/refine when backend endpoint is ready
    // Body: { route_id, instruction, conversation_history: {role, content}[] }
    // Returns: { reasoning: string, proposed_changes: string[], updated_route?: RouteOption }
    setTimeout(() => {
      const reply = mockReply(text, route);
      setMessages((m) => [...m, reply]);
      setIsThinking(false);
    }, 1100);
  };

  const apply = (id: string) => {
    setMessages((m) => m.map((msg) => (msg.id === id ? { ...msg, status: "applied" } : msg)));
    const applied = messages.find((m) => m.id === id);
    if (applied) onApplyRefinement?.(applied.text);
  };

  const dismiss = (id: string) => {
    setMessages((m) => m.map((msg) => (msg.id === id ? { ...msg, status: "dismissed" } : msg)));
  };

  return (
    <div className="bg-card border border-border rounded-2xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 px-5 py-4 border-b border-border bg-secondary/30">
        <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
          <Sparkles className="w-4 h-4 text-primary" />
        </div>
        <div>
          <h3 className="text-base font-serif text-foreground">Refine this route</h3>
          <p className="text-xs text-muted-foreground">Ask for changes in plain language</p>
        </div>
      </div>

      {/* Conversation */}
      <div className="px-5 py-4 space-y-3 max-h-80 overflow-y-auto">
        {messages.length === 0 && (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground italic">
              Try one of these, or write your own:
            </p>
            <div className="flex flex-wrap gap-1.5">
              {SUGGESTION_CHIPS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="px-3 py-1.5 rounded-full bg-secondary/60 hover:bg-secondary text-xs text-foreground border border-border transition-colors"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        <AnimatePresence initial={false}>
          {messages.map((msg) => (
            <motion.div
              key={msg.id}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              className={msg.role === "user" ? "flex justify-end" : "flex justify-start"}
            >
              {msg.role === "user" ? (
                <div className="max-w-[85%] px-3.5 py-2 rounded-2xl rounded-tr-sm bg-primary text-primary-foreground text-sm">
                  {msg.text}
                </div>
              ) : (
                <div className="max-w-[90%] space-y-2">
                  <div className="px-3.5 py-2.5 rounded-2xl rounded-tl-sm bg-secondary/60 border border-border text-sm text-foreground">
                    {msg.text}
                  </div>
                  {msg.proposedChanges && msg.status !== "dismissed" && (
                    <div className="bg-background border border-border rounded-xl p-3 space-y-2">
                      <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                        Proposed changes
                      </div>
                      <ul className="space-y-1">
                        {msg.proposedChanges.map((c, i) => (
                          <li key={i} className="text-xs text-foreground flex items-start gap-1.5">
                            <span className="mt-1.5 w-1 h-1 rounded-full bg-primary flex-shrink-0" />
                            {c}
                          </li>
                        ))}
                      </ul>
                      {msg.status === "applied" ? (
                        <div className="flex items-center gap-1.5 text-xs text-trail font-medium pt-1">
                          <Check className="w-3.5 h-3.5" /> Applied — regenerating route…
                        </div>
                      ) : (
                        <div className="flex items-center gap-2 pt-1">
                          <button
                            onClick={() => apply(msg.id)}
                            className="px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:opacity-90 transition-opacity inline-flex items-center gap-1.5"
                          >
                            <RotateCcw className="w-3 h-3" /> Apply &amp; regenerate
                          </button>
                          <button
                            onClick={() => dismiss(msg.id)}
                            className="px-3 py-1.5 rounded-lg text-xs text-muted-foreground hover:text-foreground transition-colors"
                          >
                            Dismiss
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </motion.div>
          ))}
        </AnimatePresence>

        {isThinking && (
          <div className="flex justify-start">
            <div className="px-3.5 py-2.5 rounded-2xl rounded-tl-sm bg-secondary/60 border border-border text-sm text-muted-foreground inline-flex items-center gap-2">
              <Loader2 className="w-3.5 h-3.5 animate-spin" /> Reworking the route…
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        className="flex items-center gap-2 px-3 py-3 border-t border-border bg-background"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="e.g. shorten day 3, add a coffee stop, less gravel…"
          className="flex-1 px-3 py-2 bg-transparent text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
        />
        <button
          type="submit"
          disabled={!input.trim() || isThinking}
          className="w-9 h-9 rounded-lg bg-primary text-primary-foreground flex items-center justify-center disabled:opacity-40 disabled:cursor-not-allowed hover:opacity-90 transition-opacity"
        >
          <Send className="w-4 h-4" />
        </button>
      </form>
    </div>
  );
}

// ─── Mock AI reasoning — replace with FastAPI /api/refine call ───────────────
function mockReply(instruction: string, route: RouteOption): RefinementMessage {
  const lower = instruction.toLowerCase();
  let text = "Here's how I'd adjust the route:";
  const changes: string[] = [];

  if (lower.includes("shorter") || lower.includes("shorten")) {
    const target = lower.match(/day (\d)/)?.[1] || "2";
    changes.push(`Trim Day ${target} from ~${route.day_segments[0]?.distance_km ?? 80}km to ~${(route.day_segments[0]?.distance_km ?? 80) - 20}km`);
    changes.push(`Move overnight area ~15km earlier to a quieter valley`);
    changes.push(`Day ${parseInt(target) + 1} gets +20km to compensate`);
    text = `Got it — shortening day ${target} means redistributing distance and shifting one overnight area.`;
  } else if (lower.includes("hotel") && lower.includes("camp")) {
    changes.push(`Replace hotel option on night 1 with a dispersed camping spot 2km off-route`);
    changes.push(`Add water-source note (creek, treat before drinking)`);
    changes.push(`Drop estimated cost by ~$120`);
    text = "Swapping the hotel for camping changes logistics — here's what shifts:";
  } else if (lower.includes("gravel")) {
    changes.push(`Re-route around the rough gravel section (saves ~8km of chunky surface)`);
    changes.push(`Adds 4km of paved shoulder — slightly more traffic`);
    changes.push(`Total gravel ratio drops from ${Math.round(route.gravel_ratio * 100)}% to ~${Math.max(20, Math.round(route.gravel_ratio * 100) - 15)}%`);
    text = "Avoiding that section trades surface quality for a bit more pavement:";
  } else if (lower.includes("rest day")) {
    changes.push(`Insert rest day between days 2 and 3 in the same overnight area`);
    changes.push(`Trip extends from ${route.estimated_days} to ${route.estimated_days + 1} days`);
    changes.push(`Adds optional short loop (~25km) for the rest-day curious`);
    text = "Adding a rest day — here's what changes:";
  } else if (lower.includes("climb")) {
    changes.push(`Re-route via the ridge alternate: +400m climbing, -15km distance`);
    changes.push(`Two extra viewpoints on the new ridgeline section`);
    changes.push(`Skips the flat valley road on day 2`);
    text = "More climbing, fewer kilometres — here's the alternate:";
  } else {
    changes.push(`Adjust route to match: "${instruction}"`);
    changes.push(`Recompute logistics (water, grocery, lodging)`);
    changes.push(`Update confidence and tradeoffs`);
    text = "I can work with that. Here's what I'd change:";
  }

  return {
    id: `a-${Date.now()}`,
    role: "assistant",
    text,
    proposedChanges: changes,
    status: "pending",
  };
}
