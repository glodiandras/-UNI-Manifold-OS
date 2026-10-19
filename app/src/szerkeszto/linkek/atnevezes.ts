// Jegyzet átnevezése és áthelyezése a felületen (C10): a core terve és végrehajtása (`/api/vault/atnevezes[/terv]`),
// a ⌘P-parancsok, és a `vault_atnevezes` WS-esemény kezelője (a nyitott fülek átcímzése, az „eltűnt” értesítés
// elnyomása). A link-átírás és a referencia-próba a core dolga (L42, a legacy I30 szabálya); itt csak kérés van.

import { t, tp, tk } from '../../lib/i18n';
import { ApiHiba, kerdez } from '../../lib/core/api';
import type { CoreKapcsolat } from '../../lib/core/ws.svelte';
import type { Felulet } from '../../lib/elrendezes/felulet.svelte';
import { ertesitesek } from '../../lib/ertesites/ertesites.svelte';
import type { Parancs } from '../../lib/parancsok/regiszter';
import { linkek } from '../../lib/vault/linkek.svelte';
import { szerkesztok } from '../szerkesztok.svelte';
import { vagolapra } from '../vagolap';

export interface TervLink {
  sor: number;
  regi: string;
  uj: string;
}

export interface TervFajl {
  ut: string;
  alap: string;
  darab: number;
  linkek: TervLink[];
}

/** Egy kifejezés (`.base` szűrő, képlet, összesítő), amelyet az átnevezés nem ír át (C12b): a név- vagy útrészlet-alapú
 *  összehasonlítás (`file.name ==`, `startsWith`, regex) az új névvel esetleg másként dönt — a felhasználó nézze át. */
export interface TervFigyelmeztetes {
  ut: string;
  hely: string;
  kifejezes: string;
  uzenet: string;
}

export interface Terv {
  ok: boolean;
  regi: string;
  uj: string;
  /** mappa-átnevezés/-áthelyezés (C11a, 21. döntés): a `regi`/`uj` mappaút, a `mozgo_fajlok` a mozgó jegyzetek száma */
  mappa?: boolean;
  mozgo_fajlok?: number;
  blokkolok: string[];
  /** a nem átírt, de érintett `.base`-kifejezések (a régi core-válaszban nincs) */
  figyelmeztetesek?: TervFigyelmeztetes[];
  fajlok: TervFajl[];
  modositott_linkek: number;
  osszes_link: number;
  uj_feloldott: number;
  terv_hash: string;
}

export interface Eredmeny {
  visszavonhato?: boolean;
  ok: true;
  regi: string;
  uj: string;
  mappa?: boolean;
  mozgo_fajlok?: number;
  modositott: string[];
  pillanat: string | null;
  ms: number;
}

export const SZOVEGES = /\.(md|canvas|base)$/i;

export function atnevezesTerv(ut: string, uj: string): Promise<Terv> {
  return kerdez<Terv>('/api/vault/atnevezes/terv', { metodus: 'POST', torzs: { ut, uj }, idokorlat: 60000 });
}

/** A régi úton (mappánál: a mappa alatt) álló dokumentumok kikerülése az átnevezés vagy a visszavonás után. A MENTETLEN
 *  dokumentumot (amelybe a felhasználó közben gépelt) nem dobjuk el (C29.6, T015): `eltunt` állapotban megmarad, a core
 *  többé nem tekinti mentetlennek, és az értesítés „Másolás” művelete a vágólapra viszi a szövegét — ugyanúgy, mint az
 *  eltűnt jegyzetnél. A tiszta dokumentum egyszerűen kikerül (a fül az új útról újra betölt). */
export function regiDokumentumokKikerulnek(regi: string, mappa: boolean): void {
  const dk = szerkesztok.dokumentumok;
  for (const d of dk.lista().filter((x) => x.ut === regi || (mappa && x.ut.startsWith(regi + '/')))) {
    if (!d.mentetlen) {
      dk.eldob(d.ut);
      continue;
    }
    d.eltunt();
    const szoveg = d.fajlSzoveg();
    ertesitesek.ertesit({
      szint: 'figyelmeztetes',
      cim: t('Mentetlen szöveg az átnevezéskor'),
      szoveg: t('{ut} — az átnevezés közben gépelt, még nem mentett szöveg nem került a fájlba. A vágólapra másolható.', { ut: d.ut }),
      muvelet: { nev: t('Másolás'), futtat: () => void vagolapra(szoveg) },
      idotartam: 0,
    });
  }
}

/** Végrehajtás: előtte minden nyitott dokumentum lezárul (mentés), hogy a core ne ütközzön a függő szerkesztéssel. Ha a core
 *  mégis mentetlennek látja a forrást (409 `nyitott`: a WS-jelentés egy pillanattal lemaradhat a mentés mögött), egyszer újrapróbál. */
export async function atnevezesVegrehajt(ut: string, uj: string, tervHash: string, mehet: () => boolean = () => true): Promise<Eredmeny> {
  await szerkesztok.dokumentumok.mindLezar();
  if (!mehet()) throw new Error(t('s1.cim.rename_cancelled'));
  const keres = () => kerdez<Eredmeny>('/api/vault/atnevezes', { metodus: 'POST', torzs: { ut, uj, terv_hash: tervHash }, idokorlat: 300000 });
  try {
    return await keres();
  } catch (e) {
    if (!(e instanceof ApiHiba && e.statusz === 409 && e.adat.nyitott === true)) throw e;
    await new Promise((r) => setTimeout(r, 400));
    await szerkesztok.dokumentumok.mindLezar();
    if (!mehet()) throw new Error(t('s1.cim.rename_cancelled'));
    return keres();
  }
}

/** Az átnevezés visszavonása a meglévő pillanatkép-végponton (a commit a régi és az új utat is tartalmazza). */
export async function atnevezesVisszavon(r: Eredmeny, felulet: Felulet): Promise<boolean> {
  if (!r.pillanat) return false;
  await szerkesztok.dokumentumok.mindLezar();
  szerkesztok.atnevezesAlatt.add(r.uj);
  try {
    await kerdez('/api/pillanat/vault/visszavonas', { metodus: 'POST', torzs: { sha: r.pillanat }, idokorlat: 120000 });
    felulet.utatNevez(r.uj, r.regi);
    regiDokumentumokKikerulnek(r.uj, !!r.mappa);
    ertesitesek.ertesit({ szint: 'siker', cim: t('Átnevezés visszavonva'), szoveg: `${r.uj} → ${r.regi}`, idotartam: 4000 });
    return true;
  } catch (e) {
    ertesitesek.ertesit({
      szint: 'hiba',
      cim: t('A visszavonás nem sikerült'),
      szoveg: e instanceof ApiHiba ? e.message : String(e),
      idotartam: 0,
    });
    return false;
  } finally {
    setTimeout(() => szerkesztok.atnevezesAlatt.delete(r.uj), 3000);
  }
}

/** Siker utáni értesítés „Visszavonás” művelettel. */
export function atnevezesErtesites(r: Eredmeny, felulet: Felulet): void {
  const db = r.mappa ? r.modositott.filter((m) => !m.startsWith(r.uj + '/')).length : r.modositott.filter((m) => m !== r.uj).length;
  const mozgott = r.mappa ? ' · ' + tp('{n} jegyzet', r.mozgo_fajlok ?? 0) : '';
  ertesitesek.ertesit({
    szint: 'siker',
    cim: r.mappa ? t('Mappa átnevezve') : t('Átnevezve'),
    szoveg: `${r.regi} → ${r.uj}${mozgott}${db ? ' · ' + tp('{n} jegyzet linkjei átírva', db) : ''}`,
    muvelet: r.pillanat && r.visszavonhato !== false ? { nev: t('Visszavonás'), futtat: () => void atnevezesVisszavon(r, felulet) } : undefined,
    idotartam: 15000,
  });
}

/** A `vault_atnevezes` WS-esemény: `kezd` (az „eltűnt” elnyomása), `kesz` (fülek átcímzése), `vissza` (semmi nem változott). */
export function atnevezesFigyel(kapcsolat: CoreKapcsolat, felulet: Felulet): () => void {
  return kapcsolat.figyel('vault_atnevezes', (e) => {
    const regi = String(e.regi ?? '');
    const uj = String(e.uj ?? '');
    if (!regi) return;
    if (e.allapot === 'kezd') {
      szerkesztok.atnevezesAlatt.add(regi);
    } else if (e.allapot === 'kesz') {
      felulet.utatNevez(regi, uj);
      regiDokumentumokKikerulnek(regi, e.mappa === true);
      linkek.ervenytelenit();
      setTimeout(() => szerkesztok.atnevezesAlatt.delete(regi), 3000);
    } else if (e.allapot === 'vissza') {
      szerkesztok.atnevezesAlatt.delete(regi);
    }
  });
}

/** A ⌘P-parancsok: átnevezés és áthelyezés — a fájlfában fókuszált sorra (fájl vagy mappa; ilyenkor az F2 is ezt
 *  futtatja), különben az aktív fájlra. */
export function atnevezesParancsok(felulet: Felulet): Parancs[] {
  const aktivUt = () => {
    const u = felulet.munkaterulet.aktivFul?.ut;
    return u && SZOVEGES.test(u) ? u : null;
  };
  const faSor = (): { ut: string; mappa: boolean } | null => {
    const e = typeof document !== 'undefined' ? document.activeElement : null;
    const sor = e instanceof Element ? e.closest<HTMLElement>('[data-fa-ut]') : null;
    return sor?.dataset.faUt ? { ut: sor.dataset.faUt, mappa: sor.dataset.faMappa === 'true' } : null;
  };
  const cel = (): { ut: string; mappa: boolean } | null => {
    const sor = faSor();
    if (sor) return sor;
    const ut = aktivUt();
    return ut ? { ut, mappa: false } : null;
  };
  const nyit = (mod: 'nev' | 'hely') => {
    const c = cel();
    if (!c) return;
    const sor = faSor();
    if (mod === 'nev' && sor) {
      // a fa során az F2 helyben, szerkeszthető névvel indul (07-explorer-03); a terv-átfedés csak link-változásnál nyílik
      felulet.faAtnevezKer = { ut: sor.ut, n: (felulet.faAtnevezKer?.n ?? 0) + 1 };
      return;
    }
    felulet.atnevezes = { ut: c.ut, mod, ...(c.mappa ? { mappa: true } : {}) };
    felulet.atfedes = 'atnevezes';
  };
  return [
    { id: 'vault.atnevezes', nev: t('Jegyzet átnevezése…'), kategoria: tk('Fájl'), billentyu: 'F2', elerheto: () => !!cel(), futtat: () => nyit('nev') },
    { id: 'vault.athelyezes', nev: t('Jegyzet áthelyezése…'), kategoria: tk('Fájl'), elerheto: () => !!cel(), futtat: () => nyit('hely') },
  ];
}
