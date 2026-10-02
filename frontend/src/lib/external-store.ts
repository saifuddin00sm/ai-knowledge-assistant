/**
 * Minimal store for browser-only state that lives outside React (localStorage).
 *
 * Reading `localStorage` in an effect and calling `setState` causes a cascading
 * render, which the React Compiler rules correctly flag. `useSyncExternalStore`
 * is the sanctioned way to read an external source: React uses the server
 * snapshot while rendering on the server and during hydration, then switches to
 * the live one. Snapshots are cached because `getSnapshot` must be referentially
 * stable between changes or React re-renders forever.
 */

export interface BrowserStore<T> {
  subscribe: (onChange: () => void) => () => void;
  getSnapshot: () => T;
  getServerSnapshot: () => T;
  /** Call after writing, so every subscriber re-reads. */
  notify: () => void;
}

export function createBrowserStore<T>(
  read: () => T,
  serverSnapshot: T,
): BrowserStore<T> {
  const listeners = new Set<() => void>();
  let snapshot: T = serverSnapshot;
  let fresh = false;

  function invalidate(): void {
    fresh = false;
    for (const listener of listeners) listener();
  }

  return {
    subscribe(onChange) {
      listeners.add(onChange);
      // Keep other tabs in step.
      window.addEventListener("storage", invalidate);
      return () => {
        listeners.delete(onChange);
        if (listeners.size === 0) {
          window.removeEventListener("storage", invalidate);
        }
      };
    },
    getSnapshot() {
      if (!fresh) {
        snapshot = read();
        fresh = true;
      }
      return snapshot;
    },
    getServerSnapshot: () => serverSnapshot,
    notify: invalidate,
  };
}
