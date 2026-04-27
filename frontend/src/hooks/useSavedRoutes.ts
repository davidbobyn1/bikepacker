/**
 * useSavedRoutes — localStorage-based route saving and comparison.
 * Saves full RouteOption objects keyed by their id.
 * Max 20 saved routes to avoid localStorage size limits.
 */
import { useState, useEffect, useCallback } from "react";
import type { RouteOption } from "../types/route";

const STORAGE_KEY = "bikepacker_saved_routes";
const MAX_SAVED = 20;

export interface SavedRoute {
  route: RouteOption;
  savedAt: string; // ISO date string
  customName?: string;
}

function loadFromStorage(): SavedRoute[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    return JSON.parse(raw) as SavedRoute[];
  } catch {
    return [];
  }
}

function saveToStorage(routes: SavedRoute[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(routes));
  } catch {
    // localStorage full or unavailable — silently ignore
  }
}

export function useSavedRoutes() {
  const [savedRoutes, setSavedRoutes] = useState<SavedRoute[]>(() => loadFromStorage());

  // Keep storage in sync whenever state changes
  useEffect(() => {
    saveToStorage(savedRoutes);
  }, [savedRoutes]);

  const saveRoute = useCallback((route: RouteOption, customName?: string) => {
    setSavedRoutes((prev) => {
      // Don't duplicate
      if (prev.some((s) => s.route.id === route.id)) return prev;
      const updated = [
        { route, savedAt: new Date().toISOString(), customName },
        ...prev,
      ].slice(0, MAX_SAVED);
      return updated;
    });
  }, []);

  const removeRoute = useCallback((routeId: string) => {
    setSavedRoutes((prev) => prev.filter((s) => s.route.id !== routeId));
  }, []);

  const isRouteSaved = useCallback(
    (routeId: string) => savedRoutes.some((s) => s.route.id === routeId),
    [savedRoutes]
  );

  const renameRoute = useCallback((routeId: string, newName: string) => {
    setSavedRoutes((prev) =>
      prev.map((s) =>
        s.route.id === routeId ? { ...s, customName: newName } : s
      )
    );
  }, []);

  return { savedRoutes, saveRoute, removeRoute, isRouteSaved, renameRoute };
}
