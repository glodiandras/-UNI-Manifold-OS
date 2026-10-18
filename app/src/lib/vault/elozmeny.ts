// Jegyzetenkénti előzmények (C11b): a core `/api/vault/elozmeny*` hívásai. A napló a jegyzet pillanatképeiből áll
// (melyik kör, milyen forrás); a diffet a felület a két változat szövegéből rajzolja; a visszaállítás a core-é
// (revert-commit, a kör-zár alatt) — a nyitott dokumentumot a hívó előbb menti, utána újratölti.

import { t, locale } from '../i18n';

import { kerdez } from '../core/api';

export interface ElozmenyBejegyzes {
  sha: string;
  datum: string;
  targy: string;
  /** a pillanatkép fajtája: szerk, atnev, visszaallitas, visszavonas, kezi, lepes, fuzet, kviz, kor, egyeb */
  tipus: string;
  /** magyar felirat */
  cimke: string;
  kor: string | null;
  forras: string | null;
  /** A hozzáadva, M módosítva, D törölve, R átnevezve */
  statusz: 'A' | 'M' | 'D' | 'R';
  ut_akkor: string;
  regi_ut: string | null;
  elozo: { sha: string; ut: string } | null;
  visszaallithato: boolean;
}

export interface ElozmenyValtozat {
  sha: string;
  ut_akkor: string;
  szoveg: string | null;
  szoveg_ok: string | null;
  elozo: string | null;
  elozo_ok: string | null;
}

/** Egy lap a jegyzet napjából (13-palette-05): a lapméretet a core konfigurációja adja (`[elozmeny] lap`, plafon: `lap_max`). */
export interface ElozmenyLap {
  ut: string;
  bejegyzesek: ElozmenyBejegyzes[];
  lap: number;
  /** van régebbi bejegyzés */
  tovabb: boolean;
  /** a következő lap kurzora (`elotte`), ha van */
  kovetkezo: string | null;
}

/** Egy törölt jegyzet (13-palette-04): a törlő commit és az, hogy az eredeti helyen áll-e most valami. */
export interface ToroltBejegyzes {
  ut: string;
  sha: string;
  datum: string;
  targy: string;
  tipus: string;
  cimke: string;
  ut_van: boolean;
}

export interface VisszahozasEredmeny {
  ok: boolean;
  ut: string;
  eredeti_ut: string;
  sha: string | null;
  visszaallitott: string;
  uj_nev: boolean;
}

const q = encodeURIComponent;

/** Az előzmény a "írható szöveges" típusoknak van (a core `vaultio.IRHATO` jegyzet-/nézettípusai): `.md`, `.base`, `.canvas`
 *  (13-palette-06). A napló és a revert útvonal-független; a szerkesztők a visszaállítás után a `Dokumentum.kulsoValtozas()`-szal töltenek újra. */
export const ELOZMENY_KITERJESZTESEK = ['.md', '.base', '.canvas'] as const;

export function elozmenyesUt(ut: string | null | undefined): boolean {
  const kis = (ut ?? '').toLowerCase();
  return ELOZMENY_KITERJESZTESEK.some((k) => kis.endsWith(k));
}

export const elozmenyApi = {
  naplo: (ut: string, elotte?: string | null) =>
    kerdez<ElozmenyLap>(`/api/vault/elozmeny?ut=${q(ut)}${elotte ? `&elotte=${q(elotte)}` : ''}`, { idokorlat: 15000 }),
  valtozat: (ut: string, sha: string) =>
    kerdez<ElozmenyValtozat>(`/api/vault/elozmeny/valtozat?ut=${q(ut)}&sha=${q(sha)}`, { idokorlat: 15000 }),
  visszaallit: (ut: string, sha: string) =>
    kerdez<{ ok: boolean; ut: string; sha: string; visszaallitott: string }>('/api/vault/elozmeny/visszaallit', {
      metodus: 'POST',
      torzs: { ut, sha },
      idokorlat: 60000,
    }),
  torolt: (kerdes: string, jel?: AbortSignal) =>
    kerdez<{ torolt: ToroltBejegyzes[]; lap: number; lap_max: number }>(`/api/vault/elozmeny/torolt?q=${q(kerdes)}`, { idokorlat: 20000, jel }),
  toroltValtozat: (ut: string, sha: string) =>
    kerdez<ElozmenyValtozat>(`/api/vault/elozmeny/torolt/valtozat?ut=${q(ut)}&sha=${q(sha)}`, { idokorlat: 15000 }),
  visszahoz: (ut: string, sha: string, mod: 'eredeti' | 'uj', nev?: string) =>
    kerdez<VisszahozasEredmeny>('/api/vault/elozmeny/visszahoz', {
      metodus: 'POST',
      torzs: { ut, sha, mod, ...(nev ? { nev } : {}) },
      idokorlat: 60000,
    }),
};

/** A commit ideje magyarul, rövid alakban (`2026. okt. 2. 14:03`). */
export function elozmenyIdo(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat(locale(), { dateStyle: 'medium', timeStyle: 'short' }).format(d);
}

/** Miért nem állítható vissza egy bejegyzés (a gomb tooltipje), vagy `null`, ha igen. */
export function visszaallitasOka(b: ElozmenyBejegyzes, legujabb: boolean): string | null {
  if (b.visszaallithato) return null;
  if (legujabb) return t('Ez a jelenlegi változat.');
  if (b.statusz === 'D') return t('Ebben a pillanatképben a jegyzet törölve lett.');
  // 39. döntés: a korábbi néven álló változat is visszaállítható (új tartalom-írásként) — a core adja a `visszaallithato` jelzőt
  return t('Ez a változat nem állítható vissza.');
}
