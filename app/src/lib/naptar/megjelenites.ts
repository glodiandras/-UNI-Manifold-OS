// A naptár és az emlékeztetők (C29) megjelenítési logikája: tiszta függvények, magyar szöveggel. A komponensek, az
// értesítések és a tesztek közös helye; a core állapot-alakjából emberi mondatot csinál, és nem hív semmit.

import type { EngedelyAllapot, NaptarAllapotValasz, NaptarValtozas, Utkozes } from './tipusok';

const RENDSZERBEALLITAS = 'Rendszerbeállítások › Adatvédelem és biztonság';

/** Az engedély-állapot egy rövid, emberi szövege (a vezérlő két sora). */
export function engedelySzoveg(s: EngedelyAllapot | null | undefined): string {
  switch (s) {
    case 'engedelyezve':
      return 'engedélyezve';
    case 'nincs_dontes':
      return 'még nincs döntés (kérhető)';
    case 'megtagadva':
      return 'megtagadva';
    case 'korlatozott':
      return 'korlátozott (a teljes hozzáférés kell)';
    case 'csak_iras':
      return 'csak írás (az olvasáshoz teljes hozzáférés kell)';
    case 'ismeretlen':
      return 'ismeretlen';
    default:
      return 'még nem ismert';
  }
}

export interface NaptarJelzes {
  szoveg: string;
  /** látszik-e az „engedély kérése” gomb (csak `nincs_dontes` esetén) */
  kerheto: boolean;
}

/**
 * A Ma oldal naptár-szakaszának jelzése: miért nincs (friss) naptáradat. `null`, ha nincs mit mondani (minden
 * rendben, vagy a szolgáltatás még nem próbálkozott). A `megtagadva` esetén csak szöveg: nem tudunk beállítást nyitni.
 */
export function naptarJelzes(
  s: { seged?: boolean | null; esemeny_engedely?: EngedelyAllapot | null; hiba?: string | null } | { hiba: string } | null | undefined,
): NaptarJelzes | null {
  if (!s) return null;
  const e = 'esemeny_engedely' in s ? s.esemeny_engedely : undefined;
  const seged = 'seged' in s ? s.seged : undefined;
  const hiba = s.hiba ?? null;
  if (seged === false) {
    return { szoveg: hiba ? `A naptár-szinkron nem működik: ${hiba}` : 'A naptár-szinkron nem működik: nincs naptár-segéd.', kerheto: false };
  }
  switch (e) {
    case 'nincs_dontes':
      return { szoveg: 'A Manifold még nem kapott hozzáférést a naptárhoz, ezért nincs friss naptáradat.', kerheto: true };
    case 'megtagadva':
      return {
        szoveg: `A naptár-hozzáférés meg van tagadva. Engedélyezd a Manifoldnak: ${RENDSZERBEALLITAS} › Naptárak (és Emlékeztetők).`,
        kerheto: false,
      };
    case 'korlatozott':
      return {
        szoveg: `A Manifold csak korlátozott naptár-hozzáférést kapott; az olvasáshoz teljes kell: ${RENDSZERBEALLITAS} › Naptárak.`,
        kerheto: false,
      };
    case 'csak_iras':
      return {
        szoveg: `A Manifold csak írási naptár-hozzáférést kapott; az olvasáshoz teljes kell: ${RENDSZERBEALLITAS} › Naptárak.`,
        kerheto: false,
      };
    case 'ismeretlen':
      return { szoveg: 'A naptár-hozzáférés állapota nem állapítható meg.', kerheto: false };
    default:
      return hiba ? { szoveg: `A naptár-szinkron hibát jelzett: ${hiba}`, kerheto: false } : null;
  }
}

/** `2026-10-03T14:05:12+02:00` → „ma 14:05” / „okt. 2. 14:05” (a core ISO-jának saját óráját mutatja). */
export function mikorSzoveg(iso: string | null | undefined, maKulcs: string): string {
  if (!iso || iso.length < 16) return 'még nem';
  const nap = iso.slice(0, 10);
  const ora = iso.slice(11, 16);
  if (nap === maKulcs) return `ma ${ora}`;
  const [, h, n] = nap.split('-').map(Number);
  const HONAPOK = ['jan.', 'febr.', 'márc.', 'ápr.', 'máj.', 'jún.', 'júl.', 'aug.', 'szept.', 'okt.', 'nov.', 'dec.'];
  return `${HONAPOK[h - 1] ?? nap} ${n}. ${ora}`;
}

/** Az utolsó szinkron eredménye egy mondatban. */
export function szinkronEredmeny(a: Pick<NaptarAllapotValasz, 'hiba' | 'naptar' | 'utolso_szinkron' | 'seged'>): string {
  if (a.hiba) return `hiba: ${a.hiba}`;
  if (a.seged === false) return 'nincs naptár-segéd';
  const n = a.naptar;
  if (n) {
    if (n.allapot !== 'engedelyezve') return `nem olvasható (${engedelySzoveg(n.allapot as EngedelyAllapot)})`;
    const reszek: string[] = [];
    if (n.uj) reszek.push(`${n.uj} új`);
    if (n.valtozott) reszek.push(`${n.valtozott} változott`);
    if (n.torolt) reszek.push(`${n.torolt} törölt`);
    return `${n.osszes} esemény${reszek.length ? ` (${reszek.join(', ')})` : ', nincs változás'}`;
  }
  const u = a.utolso_szinkron;
  if (u?.allapot) return u.allapot === 'engedelyezve' ? 'rendben' : (u.uzenet ?? u.allapot);
  return 'még nem futott';
}

export function utkozesFajtaSzoveg(fajta: string): string {
  switch (fajta) {
    case 'kesz':
      return 'Ellentétes pipálás: a jegyzet nyert';
    case 'szerkesztve':
      return 'Az emlékeztetőt átírták: a jegyzet nyert';
    case 'sor_nincs':
      return 'A feladat sora nem azonosítható: a jegyzet nyert';
    case 'torles_visszatartva':
      return 'Egy körben túl sok törlés: visszatartva';
    default:
      return fajta;
  }
}

function utkozesRovid(fajta: string): string {
  switch (fajta) {
    case 'kesz':
      return 'ellentétes pipálás';
    case 'szerkesztve':
      return 'az emlékeztetőt átírták';
    case 'sor_nincs':
      return 'a sor nem azonosítható';
    case 'torles_visszatartva':
      return 'a törlés visszatartva';
    default:
      return fajta;
  }
}

export function rovidit(s: string, max: number): string {
  const t = s.replace(/\s+/g, ' ').trim();
  return t.length > max ? `${t.slice(0, max - 1).trimEnd()}…` : t;
}

/** Az `emlekezteto_utkozes` WS-esemény értesítése: „A jegyzet nyert: <szöveg>” + a fajta szerint rövidített részlet. */
export function utkozesErtesites(e: Pick<Utkozes, 'fajta' | 'szoveg' | 'reszlet'>): { cim: string; szoveg: string } {
  const tartalom = e.szoveg ? rovidit(e.szoveg, 70) : '';
  const cim = e.fajta === 'torles_visszatartva' ? 'Emlékeztető-törlés visszatartva' : tartalom ? `A jegyzet nyert: ${tartalom}` : 'A jegyzet nyert';
  const reszlet = e.reszlet ? rovidit(e.reszlet, 140) : '';
  const rovid = utkozesRovid(e.fajta);
  return { cim, szoveg: reszlet && reszlet !== rovid ? `${rovid} — ${reszlet}` : rovid };
}

/** Egy naptár-változás értesítése (`atnevezve` / `eltunt`); más fajtánál `null`. */
export function valtozasErtesites(v: Pick<NaptarValtozas, 'fajta' | 'regi' | 'uj'>): { cim: string; szoveg: string } | null {
  if (v.fajta === 'atnevezve') return { cim: `A(z) „${v.uj ?? '?'}” naptár átnevezve`, szoveg: v.regi ? `Régi neve: „${v.regi}”.` : '' };
  if (v.fajta === 'eltunt') return { cim: `A(z) „${v.regi ?? '?'}” naptár eltűnt`, szoveg: '' };
  return null;
}

/** A változás-lista egy sora a vezérlőben. */
export function valtozasSor(v: NaptarValtozas, nev?: string): string {
  switch (v.fajta) {
    case 'atnevezve':
      return `átnevezve: „${v.regi ?? '?'}” → „${v.uj ?? '?'}”`;
    case 'eltunt':
      return `eltűnt: „${v.regi ?? '?'}”`;
    case 'visszajott':
      return `visszajött: „${v.uj ?? '?'}”`;
    case 'osszekotve':
      return `újra összekötve: „${v.uj ?? '?'}”`;
    case 'szin':
      return nev ? `„${nev}” színe megváltozott` : 'egy naptár színe megváltozott';
    default:
      return v.fajta;
  }
}
