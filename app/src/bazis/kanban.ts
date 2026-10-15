// A Kanban-nézet oszlopai és az áthelyezés értéke (C12b): tiszta függvények, DOM nélkül. Az oszlop a `groupBy`
// tulajdonság egy értéke; a „Nincs érték” oszlop az üres értékeké. `Status`-nál az oszlopok a séma értékkészletének
// sorrendjében állnak (üres oszloppal is, hogy oda lehessen húzni). A kártya áthúzása a jegyzet frontmatterét írja:
// csak `.md` sor és csak note-tulajdonság húzható, és csak skalár értékű (nem lista / dátum / link) oszlopba.

import type { Ertek, Sor, Valasz } from './tipusok';

export interface KanbanOszlop {
  /** a csoport nyers értéke (a core `Ertek`-je); a „Nincs érték” oszlopé `null` */
  kulcs: Ertek;
  /** a fejlécen látszó szöveg */
  cimke: string;
  sorok: Sor[];
  /** ide húzható kártya (az érték skalár és a tulajdonság szerkeszthető) */
  fogad: boolean;
}

export const NINCS_ERTEK = 'Nincs érték';

/** A csoportosító tulajdonság kulcsa a `.base`-ből (`note.Status` → `Status`); `null`, ha nem frontmatter-tulajdonság. */
export function csoportKulcs(valasz: Valasz): string | null {
  const g = valasz.nezet?.beallitas?.groupBy as { property?: unknown } | undefined;
  const p = typeof g?.property === 'string' ? g.property : null;
  if (!p) return null;
  if (p.startsWith('file.') || p.startsWith('formula.')) return null;
  return p.replace(/^note\./, '');
}

/** A csoport értéke a frontmatterbe írható alakban: skalár vagy `''` (üres); egyébként `undefined` (nem írható). */
export function irhatoErtek(e: Ertek): string | number | boolean | undefined {
  if (e === null || e === '') return '';
  if (typeof e === 'string' || typeof e === 'number' || typeof e === 'boolean') return e;
  return undefined;
}

function szoveg(e: Ertek): string {
  return e === null ? '' : typeof e === 'string' ? e : String(typeof e === 'object' ? JSON.stringify(e) : e);
}

/** Az oszlopok: a core csoportjai; a `statusSorrend` (a séma értékkészlete) megadva a `Status`-oszlopok e szerint
 *  rendeződnek, a hiányzó értékek üres oszlopként is megjelennek. */
export function oszlopok(valasz: Valasz, statusSorrend?: string[]): KanbanOszlop[] {
  const kulcs = csoportKulcs(valasz);
  const cs = valasz.csoportok ?? [];
  const ki: KanbanOszlop[] = cs.map((c) => ({
    kulcs: c.kulcs,
    cimke: c.cimke || NINCS_ERTEK,
    sorok: valasz.sorok.slice(c.tol, c.tol + c.db),
    fogad: kulcs !== null && c.huzhato && irhatoErtek(c.kulcs) !== undefined,
  }));
  if (kulcs === 'Status' && statusSorrend?.length) {
    const rend = new Map(statusSorrend.map((s, i) => [s, i]));
    const jelenlevo = new Set(ki.map((o) => szoveg(o.kulcs)));
    const huzhato = cs.length ? cs[0].huzhato : true;
    for (const s of statusSorrend) if (!jelenlevo.has(s)) ki.push({ kulcs: s, cimke: s, sorok: [], fogad: huzhato });
    const hely = (o: KanbanOszlop) => (o.kulcs === null ? -1 : (rend.get(szoveg(o.kulcs)) ?? statusSorrend.length));
    ki.sort((a, b) => hely(a) - hely(b));
  }
  return ki;
}

/** Az áthúzott kártya új értéke az oszlopban: `undefined`, ha oda nem írható. */
export function ejtesErtek(o: KanbanOszlop): string | number | boolean | undefined {
  return o.fogad ? irhatoErtek(o.kulcs) : undefined;
}
