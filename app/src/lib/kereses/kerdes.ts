// A ⌘⇧F keresés kérésének és találatainak tiszta segédei (08-search-03/04/11): a lekérdezés csomagolása a kapcsolókkal és a
// találati fájlok rendezése. Külön modul, hogy az állapot (`vaultKereses`) és a segédek (`kereso`) között ne legyen körkörös import.

import { locale } from '../i18n';
import type { KeresesRendezes } from '../elrendezes/felulet.svelte';

/** A kérés lekérdezés-szövege a felület kapcsolóival (08-search-03/11): a „Kis-nagybetű” az egészet `match-case:( … )`-be, a
 *  „Szón belül” `substring:( … )`-be csomagolja (a core operátorai; a felhasználó szövege érintetlen marad). */
export function kerdesAlak(q: string, mod: { kisnagy?: boolean; reszszo?: boolean }): string {
  let k = q.trim();
  if (mod.reszszo) k = `substring:(${k})`;
  if (mod.kisnagy) k = `match-case:(${k})`;
  return k;
}

/** A találati fájlok sorrendje (08-search-04): `relevancia` a core sorrendje (a hibrid/lexikai rangsor), a többi név vagy módosítási idő
 *  szerint; az egyenlők a core sorrendjében maradnak (stabil). */
export function rendezTalalatok<T extends { ut: string }>(
  lista: readonly T[],
  mod: KeresesRendezes,
  nev: (ut: string) => string,
  mtime: (ut: string) => number | null | undefined,
): T[] {
  if (mod === 'relevancia') return [...lista];
  const idx = new Map(lista.map((f, i) => [f, i]));
  const cmp = (a: T, b: T): number => {
    if (mod === 'nev' || mod === 'nev-forditott') {
      const d = nev(a.ut).localeCompare(nev(b.ut), locale(), { numeric: true, sensitivity: 'base' });
      return mod === 'nev' ? d : -d;
    }
    const x = mtime(a.ut) ?? 0, y = mtime(b.ut) ?? 0;
    return mod === 'modositva' ? y - x : x - y;
  };
  return [...lista].sort((a, b) => cmp(a, b) || idx.get(a)! - idx.get(b)!);
}
