// Fülcsoportok összekapcsolása (06-workspace-08): a cél csoport kiválasztása a többi közül. Egyetlen másik csoportnál
// azonnal összekapcsol; többnél helyi menü a csoportok címével (az aktív fül neve).

import { t } from '../lib/i18n';
import type { Felulet } from '../lib/elrendezes/felulet.svelte';
import { nezetFul, type PanelCs } from '../lib/elrendezes/munkaterulet.svelte';
import { fajlNev } from '../lib/vault/fajlok.svelte';
import { lebegoMenu, type MenuElem } from '../szerkeszto/notion/menu';

/** A csoport címe a választóban: az aktív fül fájlneve. */
export function panelCim(p: PanelCs): string {
  const ful = p.fulek.find((f) => f.id === p.aktiv) ?? p.fulek[0];
  return ful?.ut ? fajlNev(ful.ut) : ful && nezetFul(ful) ? String(ful.nezet?.tipus ?? '') || t('Új fül') : t('Új fül');
}

export function panelKapcsolatMenu(felulet: Felulet, panelId: string, x?: number, y?: number): void {
  const m = felulet.munkaterulet;
  const masok = m.panelek().filter((p) => p.id !== panelId);
  if (!masok.length) return;
  if (masok.length === 1) { m.osszekapcsol(panelId, masok[0].id); return; }
  const doboz = typeof document !== 'undefined' ? document.querySelector<HTMLElement>(`[data-panel-id="${panelId}"]`)?.getBoundingClientRect() : undefined;
  const elemek: MenuElem[] = [], akciok = new Map<string, () => void>();
  masok.forEach((p) => {
    const id = `kapcsol-${p.id}`;
    elemek.push({ id, nev: t('Fülcsoport {n}: {cim}', { n: m.panelek().findIndex((q) => q.id === p.id) + 1, cim: panelCim(p) }) });
    akciok.set(id, () => m.osszekapcsol(panelId, p.id));
  });
  lebegoMenu({ focus: () => undefined }, x ?? doboz?.left ?? 0, y ?? doboz?.top ?? 0, elemek, akciok, t('Összekapcsolás ezzel'));
}
