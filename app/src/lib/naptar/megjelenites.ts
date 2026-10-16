// A naptár és az emlékeztetők (C29) megjelenítési logikája: tiszta függvények, magyar szöveggel. A komponensek, az
// értesítések és a tesztek közös helye; a core állapot-alakjából emberi mondatot csinál, és nem hív semmit.

import { t, tk, locale } from '../i18n';

import type { EngedelyAllapot, NaptarAllapotValasz, NaptarValtozas, Utkozes } from './tipusok';

const RENDSZERBEALLITAS = tk('Rendszerbeállítások › Adatvédelem és biztonság');

/** Az engedély-állapot egy rövid, emberi szövege (a vezérlő két sora). */
export function engedelySzoveg(s: EngedelyAllapot | null | undefined): string {
  switch (s) {
    case 'engedelyezve':
      return t('engedélyezve');
    case 'nincs_dontes':
      return t('még nincs döntés (kérhető)');
    case 'megtagadva':
      return t('megtagadva');
    case 'korlatozott':
      return t('korlátozott (a teljes hozzáférés kell)');
    case 'csak_iras':
      return t('csak írás (az olvasáshoz teljes hozzáférés kell)');
    case 'ismeretlen':
      return t('ismeretlen');
    default:
      return t('még nem ismert');
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
    return { szoveg: hiba ? t('A naptár-szinkron nem működik: {hiba}', { hiba }) : t('A naptár-szinkron nem működik: nincs naptár-segéd.'), kerheto: false };
  }
  switch (e) {
    case 'nincs_dontes':
      return { szoveg: t('A Manifold még nem kapott hozzáférést a naptárhoz, ezért nincs friss naptáradat.'), kerheto: true };
    case 'megtagadva':
      return {
        szoveg: t('A naptár-hozzáférés meg van tagadva. Engedélyezd a Manifoldnak: {ut} › Naptárak (és Emlékeztetők).', { ut: t(RENDSZERBEALLITAS) }),
        kerheto: false,
      };
    case 'korlatozott':
      return {
        szoveg: t('A Manifold csak korlátozott naptár-hozzáférést kapott; az olvasáshoz teljes kell: {ut} › Naptárak.', { ut: t(RENDSZERBEALLITAS) }),
        kerheto: false,
      };
    case 'csak_iras':
      return {
        szoveg: t('A Manifold csak írási naptár-hozzáférést kapott; az olvasáshoz teljes kell: {ut} › Naptárak.', { ut: t(RENDSZERBEALLITAS) }),
        kerheto: false,
      };
    case 'ismeretlen':
      return { szoveg: t('A naptár-hozzáférés állapota nem állapítható meg.'), kerheto: false };
    default:
      return hiba ? { szoveg: t('A naptár-szinkron hibát jelzett: {hiba}', { hiba }), kerheto: false } : null;
  }
}

/** `2026-10-03T14:05:12+02:00` → „ma 14:05” / „okt. 2. 14:05” (a core ISO-jának saját óráját mutatja). */
export function mikorSzoveg(iso: string | null | undefined, maKulcs: string): string {
  if (!iso || iso.length < 16) return t('még nem');
  const nap = iso.slice(0, 10);
  const ora = iso.slice(11, 16);
  if (nap === maKulcs) return t('ma {ora}', { ora });
  const [, h, n] = nap.split('-').map(Number);
  const honap = Number.isFinite(h) ? new Intl.DateTimeFormat(locale(), { month: 'short', timeZone: 'UTC' }).format(new Date(Date.UTC(2000, h - 1, 1))) : nap;
  return locale() === 'hu-HU' ? `${honap} ${n}. ${ora}` : `${n} ${honap} ${ora}`;
}

/** Az utolsó szinkron eredménye egy mondatban. */
export function szinkronEredmeny(a: Pick<NaptarAllapotValasz, 'hiba' | 'naptar' | 'utolso_szinkron' | 'seged'>): string {
  if (a.hiba) return t('hiba: {hiba}', { hiba: a.hiba });
  if (a.seged === false) return t('nincs naptár-segéd');
  const n = a.naptar;
  if (n) {
    if (n.allapot !== 'engedelyezve') return t('nem olvasható ({ok})', { ok: engedelySzoveg(n.allapot as EngedelyAllapot) });
    const reszek: string[] = [];
    if (n.uj) reszek.push(t('{n} új', { n: n.uj }));
    if (n.valtozott) reszek.push(t('{n} változott', { n: n.valtozott }));
    if (n.torolt) reszek.push(t('{n} törölt', { n: n.torolt }));
    return reszek.length ? t('{n} esemény ({reszek})', { n: n.osszes, reszek: reszek.join(', ') }) : t('{n} esemény, nincs változás', { n: n.osszes });
  }
  const u = a.utolso_szinkron;
  if (u?.allapot) return u.allapot === 'engedelyezve' ? t('rendben|naptar') : (u.uzenet ?? u.allapot);
  return t('még nem futott');
}

export function utkozesFajtaSzoveg(fajta: string): string {
  switch (fajta) {
    case 'kesz':
      return t('Ellentétes pipálás: a jegyzet nyert');
    case 'szerkesztve':
      return t('Az emlékeztetőt átírták: a jegyzet nyert');
    case 'sor_nincs':
      return t('A feladat sora nem azonosítható: a jegyzet nyert');
    case 'torles_visszatartva':
      return t('Egy körben túl sok törlés: visszatartva');
    default:
      return fajta;
  }
}

function utkozesRovid(fajta: string): string {
  switch (fajta) {
    case 'kesz':
      return t('ellentétes pipálás');
    case 'szerkesztve':
      return t('az emlékeztetőt átírták');
    case 'sor_nincs':
      return t('a sor nem azonosítható');
    case 'torles_visszatartva':
      return t('a törlés visszatartva');
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
  const cim = e.fajta === 'torles_visszatartva' ? t('Emlékeztető-törlés visszatartva') : tartalom ? t('A jegyzet nyert: {tartalom}', { tartalom }) : t('A jegyzet nyert');
  const reszlet = e.reszlet ? rovidit(e.reszlet, 140) : '';
  const rovid = utkozesRovid(e.fajta);
  return { cim, szoveg: reszlet && reszlet !== rovid ? `${rovid} — ${reszlet}` : rovid };
}

/** Egy naptár-változás értesítése (`atnevezve` / `eltunt`); más fajtánál `null`. */
export function valtozasErtesites(v: Pick<NaptarValtozas, 'fajta' | 'regi' | 'uj'>): { cim: string; szoveg: string } | null {
  if (v.fajta === 'atnevezve') return { cim: t('A(z) „{nev}” naptár átnevezve', { nev: v.uj ?? '?' }), szoveg: v.regi ? t('Régi neve: „{nev}”.', { nev: v.regi }) : '' };
  if (v.fajta === 'eltunt') return { cim: t('A(z) „{nev}” naptár eltűnt', { nev: v.regi ?? '?' }), szoveg: '' };
  return null;
}

/** A változás-lista egy sora a vezérlőben. */
export function valtozasSor(v: NaptarValtozas, nev?: string): string {
  switch (v.fajta) {
    case 'atnevezve':
      return t('átnevezve: „{regi}” → „{uj}”', { regi: v.regi ?? '?', uj: v.uj ?? '?' });
    case 'eltunt':
      return t('eltűnt: „{nev}”', { nev: v.regi ?? '?' });
    case 'visszajott':
      return t('visszajött: „{nev}”', { nev: v.uj ?? '?' });
    case 'osszekotve':
      return t('újra összekötve: „{nev}”', { nev: v.uj ?? '?' });
    case 'szin':
      return nev ? t('„{nev}” színe megváltozott', { nev }) : t('egy naptár színe megváltozott');
    default:
      return v.fajta;
  }
}
