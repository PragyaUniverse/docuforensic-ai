import { useSyncExternalStore } from "react";

export type Theme = "light" | "dark";
const KEY = "docuforensic.theme";
const listeners = new Set<() => void>();

function current(): Theme {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

export function setTheme(theme: Theme) {
  const root = document.documentElement;
  root.classList.add("theme-changing");
  window.setTimeout(() => root.classList.remove("theme-changing"), 260);
  root.dataset.theme = theme;
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    // Without storage, the choice simply lasts until the page reloads.
  }
  listeners.forEach((l) => l());
}

export function useTheme(): Theme {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    current,
    () => "light",
  );
}
