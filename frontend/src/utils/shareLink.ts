/**
 * Share-link encoding/decoding for RouteOption objects.
 *
 * Encodes the route as URL-safe base64 JSON. Modern browsers support URLs up
 * to 64 KB+; a typical RouteOption stringifies to 8–14 KB, well within limits.
 * No compression library needed — keeps the bundle lean.
 */
import type { RouteOption } from "../types/route";

export function encodeRouteForUrl(route: RouteOption): string {
  const json = JSON.stringify(route);
  // btoa requires a binary string; handle Unicode by escaping first
  const encoded = btoa(encodeURIComponent(json).replace(/%([0-9A-F]{2})/g, (_, p1) =>
    String.fromCharCode(parseInt(p1, 16))
  ));
  // URL-safe base64: replace + → - and / → _ so the param needs no percent-encoding
  return encoded.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function decodeRouteFromUrl(encoded: string): RouteOption {
  const b64 = encoded.replace(/-/g, "+").replace(/_/g, "/");
  const json = decodeURIComponent(
    Array.from(atob(b64), (c) => "%" + c.charCodeAt(0).toString(16).padStart(2, "0")).join("")
  );
  return JSON.parse(json) as RouteOption;
}

export function buildShareUrl(route: RouteOption, encoded: string): string {
  const base = `${window.location.origin}${window.location.pathname}`;
  return `${base}?route=${encoded}`;
}
