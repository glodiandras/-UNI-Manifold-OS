// A core fájl-API-ja a szerkesztőnek (ARCHITECTURE 2.: `GET/PUT /api/vault/fajl`). Az alap URL a kézi
// próbáknak állítható (Node-ból a core-hoz abszolút címmel); a felületen üres (ugyanaz az origin).

import { kerdez } from '../../lib/core/api';

export interface FajlOlvasas {
  ut: string;
  tartalom: string;
  /** a lemezen álló bájtok sha1-e: a mentés alapja */
  hash: string;
  jel: string;
  mtime: number;
  /** a fájl nem érvényes UTF-8 (C08): csak olvasható */
  kodolas_hiba?: boolean;
}

export interface FajlIrasKeres {
  ut: string;
  tartalom: string;
  alap: string;
  /** a szerkesztés első mentése: előtte kézi commit */
  elso: boolean;
  /** a szerkesztés lezárása: saját gépi commit */
  pillanat: boolean;
  /** ütközés-feloldás („Az enyém”): a lemezen álló, a szerkesztőben nem szereplő változatot írjuk felül — foglalt kör-zárnál
   *  a core 423-at ad, nem ír pillanatkép nélkül (C29.7b, T116) */
  felulir?: boolean;
}

export interface FajlIras {
  ok: boolean;
  ut: string;
  hash: string;
  jel: string;
  uzenet: string;
  pillanat: string | null;
  elotte: string | null;
  git: boolean;
  /** a git hibázott (K1): a jegyzet pillanatkép nélkül mentődött */
  figyelmeztetes?: string | null;
}

export interface VaultApi {
  olvas(ut: string): Promise<FajlOlvasas>;
  ir(k: FajlIrasKeres): Promise<FajlIras>;
}

export function vaultApi(alap = ''): VaultApi {
  return {
    olvas: (ut) => kerdez<FajlOlvasas>(`${alap}/api/vault/fajl?ut=${encodeURIComponent(ut)}`, { idokorlat: 15000 }),
    ir: (k) => kerdez<FajlIras>(`${alap}/api/vault/fajl`, { metodus: 'PUT', torzs: k, idokorlat: 30000 }),
  };
}
