// A médiafájl átirata (C16): a core `GET /api/media/atirat` válasza (a melléklet-keresés és a VTT-elemzés a
// core-é, `core/atirat.py`) és a lejátszó számításai: az aktív mondat és a szűrés.

import { kerdez } from '../lib/core/api';

export interface Cue {
  k: number;
  v: number;
  szoveg: string;
}

export interface Atirat {
  ut: string;
  vtt: string | null;
  nyelv: string | null;
  gepi: boolean | null;
  leiro: string | null;
  cuek: Cue[];
  figyelmeztetes: string | null;
}

export const atiratApi = (ut: string) => kerdez<Atirat>(`/api/media/atirat?ut=${encodeURIComponent(ut)}`, { idokorlat: 10000 });

/** Az aktív mondat indexe a `t` időpontban: az utolsó, amely már elkezdődött és még tart; ha a `t` két mondat
 *  közti szünetben áll, az előző (a gépi átiratban a cue vége a következő kezdete). Kezdés előtt −1. */
export function aktivCue(cuek: Cue[], t: number): number {
  let lo = 0;
  let hi = cuek.length - 1;
  let ki = -1;
  while (lo <= hi) {
    const m = (lo + hi) >> 1;
    if (cuek[m].k <= t) {
      ki = m;
      lo = m + 1;
    } else hi = m - 1;
  }
  return ki;
}

export function normal(s: string): string {
  return s.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();
}

/** A szűrőnek megfelelő mondatok indexei (ékezet- és kisbetű-független; a szavak mind szerepeljenek). */
export function szur(cuek: Cue[], q: string): number[] {
  const szavak = normal(q).split(/\s+/).filter(Boolean);
  if (!szavak.length) return cuek.map((_, i) => i);
  const ki: number[] = [];
  cuek.forEach((c, i) => {
    const n = normal(c.szoveg);
    if (szavak.every((s) => n.includes(s))) ki.push(i);
  });
  return ki;
}
