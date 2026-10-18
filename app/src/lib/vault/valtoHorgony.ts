// Gyorsváltó-horgonyok (13-palette-03): `Jegyzet#fejezet` és `Jegyzet^blokk` a ⌘O listában. Tiszta függvények: a lekérdezés
// elemzése, a jegyzetrész kiválasztása a fájlok közül, és a fejezetek/blokkok szűrése. A core adatai: `/api/vault/jegyzet`
// (`fejezetek`, `blokkok`) és `/api/vault/fejezetek` (vault-szintű fejezetkeresés).
//
// Az Obsidian core váltójának heading/block keresése NEM megerősített (a súgó hallgat; ismert a közösségi Quick Switcher++-ból), ezért
// ez kiegészítő szintaxis: a `#`/`^` korábban érvénytelen jegyzetnév volt, így semmi meglévő viselkedést nem vált le. Kis- és
// nagybetűre érzéketlen, ékezetfüggetlen (a FuzzyIndex), Tab kiegészíti a jegyzetnevet.

import { FuzzyIndex, normalizal, type Talalat } from '../kereses/fuzzy';
import { fajlNev, mappa, type FajlInfo } from './fajlok.svelte';

export type HorgonyJel = '#' | '^';

export interface HorgonyLekerdezes {
  /** `#`: fejezetek, `^`: blokkok. */
  jel: HorgonyJel;
  /** A jegyzetnév rész (üres: vault-szintű fejezetek, illetve az aktív jegyzet blokkjai). */
  jegyzet: string;
  /** A fejezet-/blokkszűrő. */
  szuro: string;
}

export interface FejezetSor {
  szint: number;
  szoveg: string;
  sor: number;
}

export interface BlokkSor {
  azon: string;
  sor: number;
  kezdo_sor?: number;
}

export interface HorgonyElem {
  jel: HorgonyJel;
  /** A jegyzet útja. */
  ut: string;
  /** Ahová ugrunk (1-alapú sor). */
  sor: number;
  /** Fejezet szövege vagy blokkazonosító. */
  szoveg: string;
  szint?: number;
}

/** `Jegyzet#szűrő`, `Jegyzet^szűrő`, `#szűrő`, `Jegyzet#^szűrő` (Obsidian-alak: blokk) → a lekérdezés; különben null (sima fájlkeresés). */
export function horgonyElemez(lekerdezes: string): HorgonyLekerdezes | null {
  const m = /^([^#^]*)(#\^|#|\^)(.*)$/s.exec(lekerdezes);
  if (!m) return null;
  return { jel: m[2] === '#' ? '#' : '^', jegyzet: m[1].trim(), szuro: m[3].trim() };
}

const nevKulcs = (s: string): string => normalizal(s.replace(/\.md$/i, '')).trim();

/** A lekérdezés jegyzetrészéhez tartozó jegyzet: a pontos (kis/nagybetű- és ékezetfüggetlen) névegyezés előbb, különben a legjobb
 *  fuzzy találat; csak `.md` fájlok. Üres részre null. */
export function jegyzetKivalaszt(fajlok: readonly FajlInfo[], jegyzet: string, legutobbi: readonly string[] = []): FajlInfo | null {
  const kulcs = nevKulcs(jegyzet);
  if (!kulcs) return null;
  const md = fajlok.filter((f) => f.ut.toLowerCase().endsWith('.md'));
  const pontos = md.filter((f) => nevKulcs(fajlNev(f.ut)) === kulcs || nevKulcs(f.ut) === kulcs);
  if (pontos.length) return [...pontos].sort((a, b) => legutobbi.indexOf(a.ut) - legutobbi.indexOf(b.ut) || a.ut.length - b.ut.length)[0];
  const rang = new Map(legutobbi.map((u, i) => [u, i]));
  const t = new FuzzyIndex(md.map((f) => ({ ertek: f, nev: fajlNev(f.ut), ut: mappa(f.ut) }))).keres(jegyzet, {
    limit: 1,
    bonusz: (f) => (rang.has(f.ut) ? Math.max(5, 30 - (rang.get(f.ut) as number)) : 0),
  });
  return t[0]?.ertek ?? null;
}

export function fejezetSzures(ut: string, fejezetek: readonly FejezetSor[], szuro: string, limit = 50): Talalat<HorgonyElem>[] {
  const elemek = fejezetek
    .filter((f) => f.szoveg && f.szoveg.trim())
    .map((f) => ({ ertek: { jel: '#', ut, sor: f.sor, szoveg: f.szoveg, szint: f.szint } as HorgonyElem, nev: f.szoveg }));
  return szures(elemek, szuro, limit);
}

export function blokkSzures(ut: string, blokkok: readonly BlokkSor[], szuro: string, limit = 50): Talalat<HorgonyElem>[] {
  const elemek = blokkok
    .filter((b) => b.azon)
    .map((b) => ({ ertek: { jel: '^', ut, sor: b.kezdo_sor ?? b.sor, szoveg: b.azon } as HorgonyElem, nev: b.azon }));
  return szures(elemek, szuro, limit);
}

function szures(elemek: { ertek: HorgonyElem; nev: string }[], szuro: string, limit: number): Talalat<HorgonyElem>[] {
  if (!szuro.trim()) return elemek.slice(0, limit).map((e) => ({ ertek: e.ertek, pont: 0, kiemeles: [] }));
  return new FuzzyIndex(elemek).keres(szuro, { limit });
}

/** A Tab-kiegészített lekérdezés: a jegyzetrész a jegyzet teljes nevére (`Pla#Ov` → `Plan#Ov`); ha nincs mit cserélni, null. */
export function jegyzetKiegeszit(l: HorgonyLekerdezes, jegyzet: FajlInfo | null): string | null {
  if (!jegyzet) return null;
  const nev = fajlNev(jegyzet.ut);
  if (l.jegyzet === nev) return null;
  return `${nev}${l.jel}${l.szuro}`;
}
