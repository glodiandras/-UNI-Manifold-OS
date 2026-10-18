// A Bases-oszlopok és nézettípusok megjelenített neve (10-bases-01): a core az oszlop azonosítóját és angol tartalék-nevet
// ad (`alap_nev: true`, ha nem a felhasználó `displayName`-je); a felület az azonosítóból fordít, sosem a core szövegéből.

import { t, tk } from '../lib/i18n';
import type { NezetTipus, Oszlop } from './tipusok';

/** A `file.*` oszlopok fordítandó felirata (a kulcs a `file.` utáni név). */
export const FAJL_FELIRAT: Readonly<Record<string, string>> = {
  name: tk('Fájlnév'),
  basename: tk('Név'),
  path: tk('Útvonal'),
  folder: tk('Mappa'),
  ext: tk('Kiterjesztés'),
  size: tk('Méret'),
  ctime: tk('Létrehozva'),
  mtime: tk('Módosítva'),
  tags: tk('Címkék'),
  links: tk('Linkek'),
  embeds: tk('Beágyazások'),
  backlinks: tk('Visszahivatkozások'),
};

/** A nézettípusok felirata (tk: a megjelenítéskor `t()`). */
export const TIPUS_FELIRAT: Readonly<Record<NezetTipus, string>> = {
  table: tk('Táblázat'),
  cards: tk('Kártyák'),
  list: tk('Lista'),
  kanban: tk('Kanban'),
};

export const NEZET_TIPUSOK: readonly NezetTipus[] = ['table', 'cards', 'list', 'kanban'];

/** Az oszlop fejlécén látszó név: a felhasználó `displayName`-je változatlanul; az alapnév (`file.*`) az aktív nyelven. */
export function oszlopNev(o: Pick<Oszlop, 'id' | 'nev' | 'ter'> & { alap_nev?: boolean }): string {
  if (o.ter === 'file' && o.alap_nev === true) {
    const felirat = FAJL_FELIRAT[o.id.replace(/^file\./, '')];
    if (felirat) return t(felirat);
  }
  return o.nev;
}

/** Egy elérhető tulajdonság (a választókhoz) neve: a `file.*` alapnév fordítva, egyébként a core neve. */
export function elerhetoNev(e: { id: string; nev: string; ter: string }): string {
  if (e.ter === 'file') {
    const felirat = FAJL_FELIRAT[e.id.replace(/^file\./, '')];
    if (felirat) return t(felirat);
  }
  return e.nev;
}
