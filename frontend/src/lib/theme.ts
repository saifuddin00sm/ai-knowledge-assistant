import { createBrowserStore } from "@/lib/external-store";

export const THEME_STORAGE_KEY = "aka.theme";

export type Theme = "system" | "light" | "dark";

function read(): Theme {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return stored === "light" || stored === "dark" ? stored : "system";
  } catch {
    return "system";
  }
}

export const themeStore = createBrowserStore<Theme>(read, "system");

/** Reflect the choice on <html> so the `dark:` variant picks it up. */
export function applyTheme(theme: Theme): void {
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const dark = theme === "dark" || (theme === "system" && prefersDark);
  document.documentElement.classList.toggle("dark", dark);
}

export function setTheme(theme: Theme): void {
  try {
    if (theme === "system") window.localStorage.removeItem(THEME_STORAGE_KEY);
    else window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Storage blocked; the class below still applies for this session.
  }
  applyTheme(theme);
  themeStore.notify();
}
