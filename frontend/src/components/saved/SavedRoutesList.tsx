import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Bookmark, Trash2, ArrowRight, X, BarChart2, Pencil, Check } from "lucide-react";
import type { SavedRoute } from "../../hooks/useSavedRoutes";
import type { RouteOption } from "../../types/route";

interface SavedRoutesListProps {
  savedRoutes: SavedRoute[];
  onOpen: (route: RouteOption) => void;
  onRemove: (routeId: string) => void;
  onRename: (routeId: string, name: string) => void;
  onClose: () => void;
  onCompare: (routes: RouteOption[]) => void;
}

export default function SavedRoutesList({
  savedRoutes,
  onOpen,
  onRemove,
  onRename,
  onClose,
  onCompare,
}: SavedRoutesListProps) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else if (next.size < 3) next.add(id);
      return next;
    });
  };

  const startEdit = (saved: SavedRoute) => {
    setEditingId(saved.route.id);
    setEditValue(saved.customName || saved.route.trip_title || saved.route.archetype_label);
  };

  const commitEdit = (routeId: string) => {
    if (editValue.trim()) onRename(routeId, editValue.trim());
    setEditingId(null);
  };

  const formatDate = (iso: string) => {
    const d = new Date(iso);
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  };

  return (
    <motion.div
      initial={{ opacity: 0, x: 40 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 40 }}
      className="fixed inset-y-0 right-0 w-full max-w-sm bg-background border-l border-border shadow-2xl z-50 flex flex-col"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-border">
        <div className="flex items-center gap-2">
          <Bookmark className="w-5 h-5 text-primary" />
          <h2 className="font-semibold text-base">Saved Routes</h2>
          <span className="text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded-full">
            {savedRoutes.length}
          </span>
        </div>
        <button onClick={onClose} className="text-muted-foreground hover:text-foreground transition-colors">
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Compare bar */}
      <AnimatePresence>
        {selectedIds.size >= 2 && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="px-5 py-3 bg-primary/10 border-b border-primary/20 flex items-center justify-between">
              <span className="text-sm font-medium text-primary">
                {selectedIds.size} routes selected
              </span>
              <button
                onClick={() => {
                  const selected = savedRoutes
                    .filter((s) => selectedIds.has(s.route.id))
                    .map((s) => s.route);
                  onCompare(selected);
                }}
                className="inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:opacity-80 transition-opacity"
              >
                <BarChart2 className="w-4 h-4" /> Compare
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* List */}
      <div className="flex-1 overflow-y-auto">
        {savedRoutes.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-muted-foreground px-8 text-center">
            <Bookmark className="w-10 h-10 opacity-30" />
            <p className="text-sm">No saved routes yet. Generate a route and click the bookmark icon to save it.</p>
          </div>
        ) : (
          <ul className="divide-y divide-border">
            {savedRoutes.map((saved) => {
              const name = saved.customName || saved.route.trip_title || saved.route.archetype_label;
              const isSelected = selectedIds.has(saved.route.id);
              return (
                <li
                  key={saved.route.id}
                  className={`px-5 py-4 hover:bg-muted/50 transition-colors ${isSelected ? "bg-primary/5" : ""}`}
                >
                  <div className="flex items-start gap-3">
                    {/* Select checkbox */}
                    <button
                      onClick={() => toggleSelect(saved.route.id)}
                      className={`mt-0.5 w-5 h-5 rounded border-2 flex-shrink-0 flex items-center justify-center transition-colors ${
                        isSelected
                          ? "bg-primary border-primary text-primary-foreground"
                          : "border-border hover:border-primary"
                      }`}
                    >
                      {isSelected && <Check className="w-3 h-3" />}
                    </button>

                    <div className="flex-1 min-w-0">
                      {/* Name / edit */}
                      {editingId === saved.route.id ? (
                        <div className="flex items-center gap-1 mb-1">
                          <input
                            autoFocus
                            value={editValue}
                            onChange={(e) => setEditValue(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") commitEdit(saved.route.id);
                              if (e.key === "Escape") setEditingId(null);
                            }}
                            className="flex-1 text-sm font-medium bg-muted rounded px-2 py-0.5 outline-none border border-primary"
                          />
                          <button onClick={() => commitEdit(saved.route.id)} className="text-primary">
                            <Check className="w-4 h-4" />
                          </button>
                        </div>
                      ) : (
                        <div className="flex items-center gap-1 mb-1">
                          <span className="text-sm font-medium truncate">{name}</span>
                          <button
                            onClick={() => startEdit(saved)}
                            className="text-muted-foreground hover:text-foreground transition-colors flex-shrink-0"
                          >
                            <Pencil className="w-3 h-3" />
                          </button>
                        </div>
                      )}

                      {/* Metrics */}
                      <div className="flex items-center gap-3 text-xs text-muted-foreground">
                        <span>{saved.route.total_distance_km.toFixed(0)} km</span>
                        <span>{saved.route.total_climbing_m.toFixed(0)} m ↑</span>
                        <span>{Math.round(saved.route.gravel_ratio * 100)}% gravel</span>
                        <span className="ml-auto">{formatDate(saved.savedAt)}</span>
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-1 flex-shrink-0">
                      <button
                        onClick={() => { onOpen(saved.route); onClose(); }}
                        className="text-muted-foreground hover:text-primary transition-colors"
                        title="Open route"
                      >
                        <ArrowRight className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => onRemove(saved.route.id)}
                        className="text-muted-foreground hover:text-red-500 transition-colors"
                        title="Remove"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* Footer hint */}
      {savedRoutes.length >= 2 && (
        <div className="px-5 py-3 border-t border-border text-xs text-muted-foreground text-center">
          Select 2–3 routes to compare them side-by-side
        </div>
      )}
    </motion.div>
  );
}
