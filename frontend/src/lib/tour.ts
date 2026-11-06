import { useSyncExternalStore } from "react";

export type TourId = "home" | "case" | "findings";

const KEY = "docuforensic.tours";
let active: TourId | null = null;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((l) => l());
}

function readDone(): Partial<Record<TourId, boolean>> {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "{}");
  } catch {
    return {};
  }
}

export function tourSeen(id: TourId): boolean {
  return !!readDone()[id];
}

export function markTourSeen(id: TourId) {
  try {
    localStorage.setItem(KEY, JSON.stringify({ ...readDone(), [id]: true }));
  } catch {
    // Without storage, the tour may simply show again next time.
  }
}

export function startTour(id: TourId) {
  active = id;
  emit();
}

export function endTour() {
  if (active) markTourSeen(active);
  active = null;
  emit();
}

export function useActiveTour(): TourId | null {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => active,
    () => null,
  );
}

/** Which tour fits the page you're on. */
export function tourForPath(pathname: string): TourId {
  if (/^\/cases\/[^/]+\/viewer/.test(pathname)) return "findings";
  if (/^\/cases\/[^/]+/.test(pathname)) return "case";
  return "home";
}

/** "Give me a tour", "show me around" and similar, typed to Doc. */
export const TOUR_REQUEST = /\b(tour|show me around|walk ?me through|guide me|introduc\w*|how does (this|the) (site|website|app|page) work|onboard\w*)\b/i;
