import { THEME_STORAGE_KEY } from "@/lib/theme";

/**
 * Applies the stored theme before first paint so there is no flash of the wrong
 * palette. Inlined deliberately: a deferred script would run after paint.
 */
const SCRIPT = `
(function () {
  try {
    var stored = localStorage.getItem('${THEME_STORAGE_KEY}');
    var prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    var dark = stored === 'dark' || (stored !== 'light' && prefersDark);
    document.documentElement.classList.toggle('dark', dark);
  } catch (error) {
    /* storage blocked: fall through to the light default */
  }
})();
`;

export function ThemeScript() {
  return <script dangerouslySetInnerHTML={{ __html: SCRIPT }} />;
}
