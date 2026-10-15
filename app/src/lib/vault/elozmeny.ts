// Jegyzetenkénti előzmények (C11b): a core `/api/vault/elozmeny*` hívásai. A napló a jegyzet pillanatképeiből áll
// (melyik kör, milyen forrás); a diffet a felület a két változat szövegéből rajzolja; a visszaállítás a core-é
// (revert-commit, a kör-zár alatt) — a nyitott dokumentumot a hívó előbb menti, utána újratölti.

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

const q = encodeURIComponent;

export const elozmenyApi = {
  naplo: (ut: string, n = 50) =>
    kerdez<{ ut: string; bejegyzesek: ElozmenyBejegyzes[] }>(`/api/vault/elozmeny?ut=${q(ut)}&n=${n}`, { idokorlat: 15000 }),
  valtozat: (ut: string, sha: string) =>
    kerdez<ElozmenyValtozat>(`/api/vault/elozmeny/valtozat?ut=${q(ut)}&sha=${q(sha)}`, { idokorlat: 15000 }),
  visszaallit: (ut: string, sha: string) =>
    kerdez<{ ok: boolean; ut: string; sha: string; visszaallitott: string }>('/api/vault/elozmeny/visszaallit', {
      metodus: 'POST',
      torzs: { ut, sha },
      idokorlat: 60000,
    }),
};

/** A commit ideje magyarul, rövid alakban (`2026. okt. 2. 14:03`). */
export function elozmenyIdo(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat('hu', { dateStyle: 'medium', timeStyle: 'short' }).format(d);
}

/** Miért nem állítható vissza egy bejegyzés (a gomb tooltipje), vagy `null`, ha igen. */
export function visszaallitasOka(b: ElozmenyBejegyzes, legujabb: boolean): string | null {
  if (b.visszaallithato) return null;
  if (legujabb) return 'Ez a jelenlegi változat.';
  if (b.statusz === 'D') return 'Ebben a pillanatképben a jegyzet törölve lett.';
  // 39. döntés: a korábbi néven álló változat is visszaállítható (új tartalom-írásként) — a core adja a `visszaallithato` jelzőt
  return 'Ez a változat nem állítható vissza.';
}
