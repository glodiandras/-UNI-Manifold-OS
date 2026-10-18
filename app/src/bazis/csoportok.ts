// A csoportok kezelése (10-bases-05, -06, -14): a `groupOrder` lista (melyik csoport látszik és milyen sorrendben), az összecsukás
// állapota (csak a nézetben, nem íródik a `.base`-be: az Obsidian erre vonatkozó formátuma nem ismert, audit Q3) és a Kanban-oszlopok
// közös műveletei. DOM nélküli, tiszta függvények; az írás a meglévő `nezet_beallit` művelettel megy (`nezetKulcs`).
//
// A `groupOrder` szemantikája (a core `lekerdezes._csoport_sorrend` tükre): hiányzó kulcs = minden csoport a `groupBy` sorrendjében;
// lista = csak a felsoroltak, a megadott sorrendben (a sor nélküli felsorolt csoport üres csoportként látszik); az üres lista
// minden csoportot elrejt; a `null` az „üres érték” csoportja.

import type { Ertek, Muvelet, Valasz } from './tipusok';

export type CsoportKulcs = string | number | boolean | null;

export interface CsoportSor {
  kulcs: CsoportKulcs;
  cimke: string;
  db: number;
  lathato: boolean;
}

/** A csoport értéke a `groupOrder`-be írható alakban: skalár önmaga, minden más (dátum, link…) a megjelenített szöveg. */
export function csoportKulcsIrhato(kulcs: Ertek, cimke: string): CsoportKulcs {
  if (kulcs === null || typeof kulcs === 'string' || typeof kulcs === 'number' || typeof kulcs === 'boolean') return kulcs;
  return cimke;
}

/** A nézetben beállított `groupOrder`, vagy `null` (automatikus sorrend). */
export function kezdiSorrend(v: Valasz): CsoportKulcs[] | null {
  const g = v.nezet?.beallitas?.groupOrder;
  return Array.isArray(g) ? (g as CsoportKulcs[]) : null;
}

/** Minden csoport: előbb a látszók a megjelenő sorrendben, utána az elrejtettek. */
export function csoportSorok(v: Valasz): CsoportSor[] {
  const lathato = (v.csoportok ?? []).map((c) => ({ kulcs: csoportKulcsIrhato(c.kulcs, c.cimke), cimke: c.cimke, db: c.db, lathato: true }));
  const rejtett = (v.rejtett_csoportok ?? []).map((c) => ({ kulcs: csoportKulcsIrhato(c.kulcs, c.cimke), cimke: c.cimke, db: c.db, lathato: false }));
  return [...lathato, ...rejtett];
}

const lathatoLista = (sorok: CsoportSor[]): CsoportKulcs[] => sorok.filter((s) => s.lathato).map((s) => s.kulcs);

/** A `groupOrder` írása: `null` törli a kulcsot (automatikus sorrend), a lista (akár üres) kézi sorrendet ír. */
export function csoportSorrendMuvelet(nezet: number, lista: CsoportKulcs[] | null): Muvelet {
  return { fajta: 'nezet_beallit', nezet, kulcs: 'groupOrder', ertek: lista };
}

/** A csoport egy hellyel feljebb (`-1`) vagy lejjebb (`1`) a látszók között; a többi változatlan. `null`: nincs mozgás. */
export function csoportMozgat(sorok: CsoportSor[], i: number, d: -1 | 1): CsoportKulcs[] | null {
  const lat = sorok.filter((s) => s.lathato);
  const s = sorok[i];
  if (!s?.lathato) return null;
  const hely = lat.indexOf(s);
  const j = hely + d;
  if (j < 0 || j >= lat.length) return null;
  const ki = lat.map((x) => x.kulcs);
  [ki[hely], ki[j]] = [ki[j], ki[hely]];
  return ki;
}

/** A csoport megjelenítése / elrejtése: elrejtéskor kikerül a listából, megjelenítéskor a látszók végére kerül. */
export function csoportLathatoValt(sorok: CsoportSor[], i: number, lathato: boolean): CsoportKulcs[] {
  const s = sorok[i];
  if (!s) return lathatoLista(sorok);
  const lat = sorok.filter((x) => x.lathato && x !== s).map((x) => x.kulcs);
  return lathato ? [...lat, s.kulcs] : lat;
}

/** Új, üres csoport felvétele a látszók végére (a Kanban „oszlop hozzáadása”). `null`: a csoport már van, vagy üres a név. */
export function csoportHozzaad(sorok: CsoportSor[], ertek: string): CsoportKulcs[] | null {
  const nev = ertek.trim();
  if (!nev) return null;
  if (sorok.some((s) => s.lathato && String(s.kulcs ?? '') === nev)) return null;
  const rejtett = sorok.findIndex((s) => !s.lathato && String(s.kulcs ?? '') === nev);
  return rejtett >= 0 ? csoportLathatoValt(sorok, rejtett, true) : [...lathatoLista(sorok), nev];
}

// ------------------------------------------------------------------ összecsukás (10-bases-06)

/** A csoport összecsukás-kulcsa: nézetenként és csoportonként stabil. */
export function zartKulcs(nezet: number, kulcs: Ertek): string {
  return `${nezet}\u0000${JSON.stringify(kulcs)}`;
}

/** A halmaz új példánya a csoport összecsukott állapotának megfordításával (a reaktív állapot nem módosul helyben). */
export function zartKapcsol(zart: ReadonlySet<string>, kulcs: string): Set<string> {
  const uj = new Set(zart);
  if (!uj.delete(kulcs)) uj.add(kulcs);
  return uj;
}
