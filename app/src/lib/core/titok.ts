// A core API-titka a felületen (C29.7b, 35. döntés / T071). A core induláskor sorsolja, a kézfogás-sor a héjnak adja, a héj a
// lap betöltése ELŐTT injektálja (`window.__MOS_TITOK__`, `WKUserScript` a főkeretben). Fejlesztői tartalék (Browser pane, kézi
// próba): a címben `#titok=<t>` — a töredéket a szerver nem látja, az app egyszer olvassa és törli a címből (a history-ba sem
// marad). Titok nélkül minden API-kérés 403: a felület csak a héjon át (vagy a kézi próba URL-jével) működik, és erre nincs
// kerülőút: a lap letöltése (`GET /`) titok nélkül megy, de nem hordozza.

const MINTA = /^[A-Za-z0-9_.-]{16,128}$/;

let aktualis: string | null = null;

/** A titok beolvasása (az injektált érték, különben a cím töredéke; böngésző nélkül — a kézi Node-próbák — a `MOS_API_TITOK`
 *  környezeti változó); érvénytelen alak vagy hiány: üres szöveg. */
export function titokBetolt(ablakParam?: Window | null): string {
  const ablak = ablakParam === undefined ? (typeof window === 'undefined' ? null : window) : ablakParam; // null: nincs böngésző
  if (!ablak) {
    const env = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env;
    const t = env?.MOS_API_TITOK ?? '';
    aktualis = MINTA.test(t) ? t : '';
    return aktualis;
  }
  const w = ablak as Window & { __MOS_TITOK__?: unknown };
  let t = typeof w.__MOS_TITOK__ === 'string' ? w.__MOS_TITOK__ : '';
  if ('__MOS_TITOK__' in w) delete w.__MOS_TITOK__; // ne maradjon a globális névtérben
  if (!t) {
    const m = /(?:^|[#&])titok=([^&]+)/.exec(ablak.location.hash);
    if (m) {
      try {
        t = decodeURIComponent(m[1]);
      } catch {
        t = '';
      }
      try {
        ablak.history.replaceState(null, '', ablak.location.pathname + ablak.location.search);
      } catch {
        // a cím nem írható: a titok így is a memóriában van
      }
    }
  }
  aktualis = MINTA.test(t) ? t : '';
  return aktualis;
}

/** A titok (az első híváskor lustán beolvasva). */
export function apiTitok(): string {
  return aktualis ?? titokBetolt();
}

/** Teszt: a titok kézi beállítása (`null`: a következő hívás újra beolvassa). */
export function titokBeallit(t: string | null): void {
  aktualis = t;
}
