// A gráfnézet beállításai (C13): a felhasználó tartós felülírásai (a `Felulet.graf` mezőben él) és az Obsidian
// `.obsidian/graph.json` értékeiből számolt kiindulás. A tényleges érték = a felülírás, ennek hiányában a graph.json,
// annak hiányában az alap. A graph.json csak olvasható (az `.obsidian` a vault része; ide a 2.0 nem ír vissza).

import type { ErokBeallitas } from './fizika';
import type { SzinCsoport } from './modell';

/** A `GET /api/vault/graf-beallitasok` válasza. */
export interface GrafJson {
  van: boolean;
  kereses?: string;
  mutat_mellekletek?: boolean;
  mutat_arvak?: boolean;
  nyil?: boolean;
  meret_szorzo?: number;
  vonal_szorzo?: number;
  szoveg_halvanyitas?: number;
  erok?: { kozep?: number; taszitas?: number; rugo?: number; tavolsag?: number };
  szincsoportok?: { lekerdezes: string; szin: string; alfa?: number }[];
}

export type ErokKulcs = 'taszitas' | 'rugo' | 'rugohossz' | 'kozep';

/** A csúszkák tartománya (szorzó az alapértékre; 1 = alap). */
export const EROK_TARTOMANY: Record<ErokKulcs, { min: number; max: number; lepes: number; nev: string }> = {
  taszitas: { min: 0.2, max: 4, lepes: 0.05, nev: 'Taszítás' },
  rugo: { min: 0.1, max: 3, lepes: 0.05, nev: 'Rugóerő' },
  rugohossz: { min: 0.3, max: 4, lepes: 0.05, nev: 'Rugóhossz' },
  kozep: { min: 0, max: 4, lepes: 0.05, nev: 'Középre húzás' },
};

export const EROK_KULCSOK = Object.keys(EROK_TARTOMANY) as ErokKulcs[];

export const MAX_LEKERDEZES = 500;
export const MAX_SZINCSOPORT = 30;

/** A felhasználó felülírásai; a hiányzó mező a graph.json-ból (vagy az alapból) jön. */
export interface GrafFeluliras {
  lekerdezes?: string;
  mellekletek?: boolean;
  arvak?: boolean;
  nyilak?: boolean;
  erok?: Partial<Record<ErokKulcs, number>>;
  szincsoportok?: SzinCsoport[];
}

export interface GrafEffektiv {
  lekerdezes: string;
  mellekletek: boolean;
  arvak: boolean;
  nyilak: boolean;
  erok: Record<ErokKulcs, number>;
  szincsoportok: SzinCsoport[];
  /** A graph.json-ból jött színcsoport (nem a felhasználó felülírása). */
  szincsoportForras: 'sajat' | 'graph.json' | 'nincs';
  meretSzorzo: number;
  vonalSzorzo: number;
}

const korlat = (x: number, a: number, b: number) => Math.min(b, Math.max(a, x));
const veges = (x: unknown): x is number => typeof x === 'number' && Number.isFinite(x);

/** Az Obsidian erői a csúszkák szorzóira (a legacy leképezése: az Obsidian alapjaihoz mérve). */
export function erokGraphJsonbol(j: GrafJson | null | undefined): Record<ErokKulcs, number> {
  const e = j?.van ? (j.erok ?? {}) : {};
  const t = (k: ErokKulcs, v: number) => korlat(v, EROK_TARTOMANY[k].min, EROK_TARTOMANY[k].max);
  return {
    taszitas: t('taszitas', e.taszitas ? e.taszitas / 10 : 1),
    rugo: t('rugo', veges(e.rugo) ? e.rugo : 1),
    rugohossz: t('rugohossz', e.tavolsag ? e.tavolsag / 250 : 1),
    kozep: t('kozep', e.kozep ? e.kozep / 0.518713248970312 : 1),
  };
}

export function effektiv(j: GrafJson | null | undefined, f: GrafFeluliras): GrafEffektiv {
  const van = !!j?.van;
  const alapErok = erokGraphJsonbol(j);
  const erok = { ...alapErok };
  for (const k of EROK_KULCSOK) {
    const v = f.erok?.[k];
    if (veges(v)) erok[k] = korlat(v, EROK_TARTOMANY[k].min, EROK_TARTOMANY[k].max);
  }
  const jsonCsoportok: SzinCsoport[] = van ? (j!.szincsoportok ?? []).map((c) => ({ lekerdezes: c.lekerdezes, szin: c.szin })) : [];
  const sajat = f.szincsoportok;
  return {
    lekerdezes: f.lekerdezes ?? (van ? (j!.kereses ?? '') : ''),
    mellekletek: f.mellekletek ?? (van ? (j!.mutat_mellekletek ?? true) : true),
    arvak: f.arvak ?? (van ? (j!.mutat_arvak ?? true) : true),
    nyilak: f.nyilak ?? (van ? (j!.nyil ?? false) : false),
    erok,
    szincsoportok: sajat ?? jsonCsoportok,
    szincsoportForras: sajat ? 'sajat' : jsonCsoportok.length ? 'graph.json' : 'nincs',
    meretSzorzo: van ? (j!.meret_szorzo ?? 1) : 1,
    vonalSzorzo: van ? (j!.vonal_szorzo ?? 1) : 1,
  };
}

/** A mentett felülírás ellenőrzése (a `felulet.json` bármi lehet); hibás mezőt eldob. */
export function feluliras(x: unknown): GrafFeluliras {
  if (!x || typeof x !== 'object' || Array.isArray(x)) return {};
  const o = x as Record<string, unknown>;
  const ki: GrafFeluliras = {};
  if (typeof o.lekerdezes === 'string') ki.lekerdezes = o.lekerdezes.slice(0, MAX_LEKERDEZES);
  if (typeof o.mellekletek === 'boolean') ki.mellekletek = o.mellekletek;
  if (typeof o.arvak === 'boolean') ki.arvak = o.arvak;
  if (typeof o.nyilak === 'boolean') ki.nyilak = o.nyilak;
  if (o.erok && typeof o.erok === 'object') {
    const e: Partial<Record<ErokKulcs, number>> = {};
    for (const k of EROK_KULCSOK) {
      const v = (o.erok as Record<string, unknown>)[k];
      if (veges(v)) e[k] = korlat(v, EROK_TARTOMANY[k].min, EROK_TARTOMANY[k].max);
    }
    if (Object.keys(e).length) ki.erok = e;
  }
  if (Array.isArray(o.szincsoportok)) {
    ki.szincsoportok = o.szincsoportok
      .filter(
        (c): c is SzinCsoport =>
          !!c && typeof c === 'object' && typeof (c as SzinCsoport).lekerdezes === 'string' && /^#[0-9a-f]{6}$/i.test((c as SzinCsoport).szin),
      )
      .slice(0, MAX_SZINCSOPORT)
      .map((c) => ({ lekerdezes: c.lekerdezes.slice(0, 200), szin: c.szin.toLowerCase() }));
  }
  return ki;
}

/** A fizika beállítása az effektív erőkből. */
export function fizikaBeallitas(e: GrafEffektiv): Partial<ErokBeallitas> {
  return { taszitas: e.erok.taszitas, rugo: e.erok.rugo, rugohossz: e.erok.rugohossz, kozep: e.erok.kozep };
}
