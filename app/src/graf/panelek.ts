// A gráf és a jegyzet-panelek viszonya (11-graph-01): a jegyzet mellett nyitott helyi gráf a belőle megnyitott jegyzetet a
// jegyzet saját csoportjában nyitja (nem a gráf paneljében, amely így nem tűnne el a jegyzet alatt), és az ottani aktív
// jegyzetet követi. Tiszta függvények a `Munkaterulet` modellen; DOM és Svelte nélkül.

import type { MegnyitasMod, Munkaterulet } from '../lib/elrendezes/munkaterulet.svelte';

/** A panel, amelyben a gráfról megnyitott fájl nyílik, vagy `null` (a gráf saját paneljében: a jelenlegi viselkedés). Csak
 *  a helyi gráf, és csak ha a rögzített `celPanel` még létezik és nem a gráf saját panelje. */
export function celPanelAzon(mt: Munkaterulet, fulId: string, nezet: Record<string, unknown> | undefined): string | null {
  if (nezet?.mod !== 'helyi') return null;
  const kivant = typeof nezet.celPanel === 'string' ? nezet.celPanel : null;
  if (!kivant) return null;
  const sajat = mt.panelek().find((p) => p.fulek.some((f) => f.id === fulId));
  return kivant !== sajat?.id && mt.panel(kivant) ? kivant : null;
}

/** A fájl megnyitása a gráf nézetéhez illő panelben. */
export function fajlMegnyitPanelben(mt: Munkaterulet, celPanel: string | null, ut: string, mod: MegnyitasMod): void {
  if (celPanel) mt.aktivPanelId = celPanel;
  mt.megnyit(ut, mod);
}
