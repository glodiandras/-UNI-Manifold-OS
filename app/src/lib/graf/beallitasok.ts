// A gráfnézet beállításai (C13): a felhasználó tartós felülírásai (a `Felulet.graf` mezőben él) és az Obsidian
// `.obsidian/graph.json` értékeiből számolt kiindulás. A tényleges érték = a felülírás, ennek hiányában a graph.json,
// annak hiányában az alap. A graph.json csak olvasható (az `.obsidian` a vault része; ide a 2.0 nem ír vissza).

import { t } from '../i18n';

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
  /** `showTags`: a címkék csúcsként (az Obsidian alapja: nem). */
  mutat_cimkek?: boolean;
  /** `hideUnresolved`: csak a létező fájlok (a feloldatlan link-célok nem csúcsok). */
  csak_letezo?: boolean;
  erok?: { kozep?: number; taszitas?: number; rugo?: number; tavolsag?: number };
  szincsoportok?: { lekerdezes: string; szin: string; alfa?: number }[];
}

export type ErokKulcs = 'taszitas' | 'rugo' | 'rugohossz' | 'kozep';

/** A csúszkák tartománya (szorzó az alapértékre; 1 = alap). */
export const EROK_TARTOMANY: Record<ErokKulcs, { min: number; max: number; lepes: number; nev: string }> = {
  taszitas: { min: 0.2, max: 4, lepes: 0.05, get nev() { return t('Taszítás'); } },
  rugo: { min: 0.1, max: 3, lepes: 0.05, get nev() { return t('Rugóerő'); } },
  rugohossz: { min: 0.3, max: 4, lepes: 0.05, get nev() { return t('Rugóhossz'); } },
  kozep: { min: 0, max: 4, lepes: 0.05, get nev() { return t('Középre húzás'); } },
};

export const EROK_KULCSOK = Object.keys(EROK_TARTOMANY) as ErokKulcs[];

/** A megjelenítés csúszkái (11-graph-04): a csúcsméret és a vonalvastagság szorzó (1 = alap), a szöveg-halványítás az Obsidian
 *  „Text fade threshold” tartománya (−3 … 3; a nagyobb érték csak a nagyobb / közelebbi csúcsra ír feliratot). */
export type MegjelenesKulcs = 'meretSzorzo' | 'vonalSzorzo' | 'szovegHalvany';
export const MEGJELENES_TARTOMANY: Record<MegjelenesKulcs, { min: number; max: number; lepes: number; alap: number }> = {
  meretSzorzo: { min: 0.5, max: 2, lepes: 0.05, alap: 1 },
  vonalSzorzo: { min: 0.3, max: 3, lepes: 0.05, alap: 1 },
  szovegHalvany: { min: -3, max: 3, lepes: 0.1, alap: 0 },
};

export const MAX_LEKERDEZES = 500;
export const MAX_SZINCSOPORT = 30;

/** A felhasználó felülírásai; a hiányzó mező a graph.json-ból (vagy az alapból) jön. */
export interface GrafFeluliras {
  lekerdezes?: string;
  mellekletek?: boolean;
  arvak?: boolean;
  nyilak?: boolean;
  /** A címkék csúcsként (11-graph-03). */
  cimkek?: boolean;
  /** Csak létező fájlok: a feloldatlan link-célok nem csúcsok (11-graph-02). */
  letezoCsak?: boolean;
  meretSzorzo?: number;
  vonalSzorzo?: number;
  szovegHalvany?: number;
  erok?: Partial<Record<ErokKulcs, number>>;
  szincsoportok?: SzinCsoport[];
}

export interface GrafEffektiv {
  lekerdezes: string;
  mellekletek: boolean;
  arvak: boolean;
  nyilak: boolean;
  cimkek: boolean;
  letezoCsak: boolean;
  erok: Record<ErokKulcs, number>;
  szincsoportok: SzinCsoport[];
  /** A graph.json-ból jött színcsoport (nem a felhasználó felülírása). */
  szincsoportForras: 'sajat' | 'graph.json' | 'nincs';
  meretSzorzo: number;
  vonalSzorzo: number;
  /** A feliratok halványítási küszöbe (−3 … 3, 0 = alap). */
  szovegHalvany: number;
}

const korlat = (x: number, a: number, b: number) => Math.min(b, Math.max(a, x));
const veges = (x: unknown): x is number => typeof x === 'number' && Number.isFinite(x);

/** Az Obsidian erői a csúszkák szorzóira (a legacy leképezése: az Obsidian alapjaihoz mérve). */
export function erokGraphJsonbol(j: GrafJson | null | undefined): Record<ErokKulcs, number> {
  const e = j?.van ? (j.erok ?? {}) : {};
  const korlatoz = (k: ErokKulcs, v: number) => korlat(v, EROK_TARTOMANY[k].min, EROK_TARTOMANY[k].max);
  return {
    taszitas: korlatoz('taszitas', e.taszitas ? e.taszitas / 10 : 1),
    rugo: korlatoz('rugo', veges(e.rugo) ? e.rugo : 1),
    rugohossz: korlatoz('rugohossz', e.tavolsag ? e.tavolsag / 250 : 1),
    kozep: korlatoz('kozep', e.kozep ? e.kozep / 0.518713248970312 : 1),
  };
}

/** A csúszka tényleges értéke: a felülírás (a tartományon belül), ennek hiányában a graph.json értéke (változatlanul: a
 *  rajzoló a saját tartományára szorítja, a csúszka a szélén áll), annak hiányában az alap. */
function megjelenes(kulcs: MegjelenesKulcs, felulir: number | undefined, json: number | undefined): number {
  const t = MEGJELENES_TARTOMANY[kulcs];
  if (veges(felulir)) return korlat(felulir, t.min, t.max);
  return veges(json) ? json : t.alap;
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
    cimkek: f.cimkek ?? (van ? (j!.mutat_cimkek ?? false) : false),
    letezoCsak: f.letezoCsak ?? (van ? (j!.csak_letezo ?? true) : true),
    erok,
    szincsoportok: sajat ?? jsonCsoportok,
    szincsoportForras: sajat ? 'sajat' : jsonCsoportok.length ? 'graph.json' : 'nincs',
    meretSzorzo: megjelenes('meretSzorzo', f.meretSzorzo, van ? j!.meret_szorzo : undefined),
    vonalSzorzo: megjelenes('vonalSzorzo', f.vonalSzorzo, van ? j!.vonal_szorzo : undefined),
    szovegHalvany: megjelenes('szovegHalvany', f.szovegHalvany, van ? j!.szoveg_halvanyitas : undefined),
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
  if (typeof o.cimkek === 'boolean') ki.cimkek = o.cimkek;
  if (typeof o.letezoCsak === 'boolean') ki.letezoCsak = o.letezoCsak;
  for (const k of ['meretSzorzo', 'vonalSzorzo', 'szovegHalvany'] as const) {
    const v = o[k];
    if (veges(v)) ki[k] = korlat(v, MEGJELENES_TARTOMANY[k].min, MEGJELENES_TARTOMANY[k].max);
  }
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
