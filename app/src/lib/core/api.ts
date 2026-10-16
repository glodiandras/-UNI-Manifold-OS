// A core HTTP-API-ja (ARCHITECTURE 2.): ugyanaz az origin, minden kérésben `X-Manifold: <API-titok>` (35. döntés: a core induláskor
// sorsolja, a héj injektálja a lapba — `titok.ts`).

import { helyettesit, t, tHaVan, tk, type Param } from '../i18n';
import { apiTitok } from './titok';

/** A core `param` mezőjéből a fordításba szánt (szöveg, szám, logikai) értékek. */
function paramSzures(p: unknown): Param {
  const ki: Param = {};
  if (p && typeof p === 'object')
    for (const [k, v] of Object.entries(p)) if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') ki[k] = v;
  return ki;
}

/** A kliens oldali hiba fajtája (a core válaszából nem jön): időtúllépés / megszakadt kapcsolat. */
export type HibaFajta = 'idotullepes' | 'kapcsolat';

export class ApiHiba extends Error {
  constructor(
    readonly statusz: number,
    uzenet: string,
    readonly adat: Record<string, unknown> = {},
    readonly fajta?: HibaFajta,
  ) {
    super(uzenet);
    this.name = 'ApiHiba';
  }

  /** A core hibakódja (a hibatörzs `kod` mezője, pl. `vault.nem_elerheto`); a fordítás kulcsa `hiba.<kod>`. Hiányzik, ha a core nem adott. */
  get kod(): string | undefined {
    const k = this.adat.kod;
    return typeof k === 'string' && k !== '' ? k : undefined;
  }

  /** A hibakód paraméterei (a hibatörzs `param` mezője): a fordítás `{nev}` helyettesítései. */
  get param(): Param {
    return paramSzures(this.adat.param);
  }

  /** A kérés lejárt (a 0-s státuszú, kliens oldali időtúllépés): nem az üzenet szövegét kell összehasonlítani, mert az nyelvfüggő. */
  get idotullepes(): boolean {
    return this.fajta === 'idotullepes';
  }
}

export interface KeresOpciok {
  metodus?: 'GET' | 'POST' | 'PUT';
  torzs?: unknown;
  /** Ezredmásodperc; lejárta után ApiHiba(0). Hiányzik: `ALAP_IDOKORLAT`; 0: nincs korlát (csak kifejezetten hosszú hívásnál). */
  idokorlat?: number;
  /** A lap elhagyásakor is elküldi (a felület-állapot utolsó mentése). */
  keepalive?: boolean;
  /** Külső megszakítás (pl. az elavult keresés): ApiHiba(0)-t ad, mint az időtúllépés. */
  jel?: AbortSignal;
}

/** Az alap időkorlát: egy sosem válaszoló kérés se akassza meg a háttérfrissítéseket (a frissítő sor egyesével futtat). */
export const ALAP_IDOKORLAT = 30_000;

/** A megszakadt kapcsolat magyar üzenete (a böngésző nyers hibája helyett: „Load failed”, „Failed to fetch”…). */
export const KAPCSOLAT_HIBA = tk('A core nem érhető el (megszakadt a kapcsolat).');

/** A böngészőmotorok nyers hálózati hibaüzenetei (WebKit, Chromium, Firefox). */
const NYERS_HALOZATI = [
  /^load failed$/i,
  /^failed to fetch$/i,
  /^networkerror/i,
  /network connection was lost/i,
  /could not connect to the server/i,
  /internet connection appears to be offline/i,
  /^network error$/i,
  /^cancelled$/i,
];

const STATUSZ_UZENET: Record<number, string> = {
  400: tk('A core elutasította a kérést (400).'),
  403: tk('A core megtagadta a kérést (403).'),
  404: tk('Nem található (404).'),
  408: tk('A core nem válaszolt időben (408).'),
  413: tk('A kérés túl nagy (413).'),
  423: tk('Az erőforrás foglalt (423).'),
  500: tk('A core belső hibája (500).'),
  502: tk('A core nem érhető el (502).'),
  503: tk('A core most nem tudja kiszolgálni a kérést (503).'),
  504: tk('A core nem válaszolt időben (504).'),
  507: tk('Nincs elég hely a lemezen (507).'),
};

/** A HTTP-státusz üzenete az aktív nyelven, ha a válasz nem hozott saját (`hiba`) üzenetet. */
export function statuszUzenet(statusz: number): string {
  const uzenet = STATUSZ_UZENET[statusz];
  return uzenet ? t(uzenet) : t('A core hibát adott ({statusz}).', { statusz });
}

const nyersHalozati = (uzenet: string) => NYERS_HALOZATI.some((m) => m.test(uzenet.trim()));

/**
 * Bármely hiba felhasználónak mutatható szövege: az ApiHiba üzenete, a nyers hálózati hiba helyett a
 * `KAPCSOLAT_HIBA` (az aktív nyelven), egyébként az üzenet (az „ApiHiba: …” / „Error: …” előtag nélkül).
 */
export function hibaSzoveg(e: unknown): string {
  const uzenet = e instanceof Error ? e.message : typeof e === 'string' ? e : String(e);
  return nyersHalozati(uzenet) ? t(KAPCSOLAT_HIBA) : uzenet;
}

/** A core `kod` + `param` hibájának fordítása az aktív nyelven (`hiba.<kod>` kulcs); `undefined`, ha nincs kód vagy nincs fordítás. */
function kodSzoveg(hiba: ApiHiba): string | undefined {
  return kodFordit(hiba.kod, hiba.param);
}

function kodFordit(kod: unknown, adat: unknown): string | undefined {
  if (typeof kod !== 'string' || kod === '') return undefined;
  const sablon = tHaVan(`hiba.${kod}`);
  if (sablon === undefined) return undefined;
  const param = paramSzures(adat);
  // Hiányos vagy régebbi core-válasz esetén a kész tartalék-mondat marad;
  // a felhasználó ne kapjon kitöltetlen {ut} helyettesítőt.
  if ([...sablon.matchAll(/\{([A-Za-z_][A-Za-z0-9_]*)\}/g)].some((m) => !Object.hasOwn(param, m[1]))) return undefined;
  return helyettesit(sablon, param);
}

/**
 * Egy core-törzs (`{hiba, kod, param}`; nem ApiHiba: feladat-hiba, WS-esemény, `/api/ma` szakasz-hiba, …) szövege az aktív nyelven:
 * a `hiba.<kod>` fordítás a `param`-mal, ha van; különben a core magyar `hiba` mondata; végül a `tartalek`.
 */
export function kodUzenet(torzs: { hiba?: unknown; kod?: unknown; param?: unknown } | null | undefined, tartalek = ''): string {
  const fordito = kodFordit(torzs?.kod, torzs?.param);
  return fordito ?? (typeof torzs?.hiba === 'string' && torzs.hiba !== '' ? torzs.hiba : tartalek);
}

/**
 * A core hibájának felhasználónak mutatható szövege az aktív nyelven: ha az ApiHiba hordoz `kod`-ot és van `hiba.<kod>`
 * fordítás (`{nev}` helyettesítésekkel a `param`-ból), az; különben a core magyar `hiba` szövege (az ApiHiba üzenete) — vagyis a
 * `hibaSzoveg`. A `hu` nyelvnek nincs szótára, ott mindig a core szövege jön. Új kód: `hiba.<kod>` kulcs az `en/core.json`-ban.
 */
export function hibaUzenet(e: unknown): string {
  return (e instanceof ApiHiba ? kodSzoveg(e) : undefined) ?? hibaSzoveg(e);
}

/** A válasz törzse: JSON, ha az; különben (pl. a Python `send_error` HTML-je 413/500-nál) `null`. */
function torzsElemez(szoveg: string): Record<string, unknown> | null {
  if (!szoveg) return {};
  try {
    return JSON.parse(szoveg);
  } catch {
    return null;
  }
}

/**
 * A nem sikeres válasz hibája: a core `kod` + `param` fordítása az aktív nyelven, ha van; különben a core magyar `hiba` üzenete
 * (a tartalék, az `adat.hiba` is megmarad), vagy a státusz üzenete; a státusz mindig megmarad.
 */
function valaszHiba(statusz: number, adat: Record<string, unknown> | null): ApiHiba {
  const torzs = adat && typeof adat === 'object' ? adat : {};
  const sajat = torzs.hiba != null && torzs.hiba !== '' ? String(torzs.hiba) : null;
  const hiba = new ApiHiba(statusz, sajat ?? statuszUzenet(statusz), torzs);
  const fordito = kodSzoveg(hiba);
  if (fordito !== undefined) hiba.message = fordito;
  return hiba;
}

/** A fetch (vagy az elemzés) hibája ApiHiba-ként: megszakítás = időtúllépés, a nyers hálózati hiba az aktív nyelvű kapcsolat-hiba. */
function kivetelHiba(e: unknown): ApiHiba {
  if (e instanceof ApiHiba) return e;
  if (e instanceof DOMException && e.name === 'AbortError') return new ApiHiba(0, t('időtúllépés'), {}, 'idotullepes');
  const uzenet = e instanceof Error ? e.message : typeof e === 'string' ? e : String(e);
  return new ApiHiba(0, hibaSzoveg(e), {}, nyersHalozati(uzenet) ? 'kapcsolat' : undefined);
}

function idozito(o: { idokorlat?: number; jel?: AbortSignal }, vezerlo: AbortController) {
  const korlat = o.idokorlat ?? ALAP_IDOKORLAT;
  const ido = korlat > 0 ? setTimeout(() => vezerlo.abort(), korlat) : null;
  if (o.jel?.aborted) vezerlo.abort();
  else o.jel?.addEventListener('abort', () => vezerlo.abort(), { once: true });
  return ido;
}

export async function kerdez<T>(ut: string, o: KeresOpciok = {}): Promise<T> {
  const vezerlo = new AbortController();
  const ido = idozito(o, vezerlo);
  try {
    const v = await fetch(ut, {
      method: o.metodus ?? 'GET',
      headers: { 'X-Manifold': apiTitok(), ...(o.torzs !== undefined ? { 'Content-Type': 'application/json' } : {}) },
      body: o.torzs !== undefined ? JSON.stringify(o.torzs) : undefined,
      signal: vezerlo.signal,
      keepalive: o.keepalive,
      cache: 'no-store',
    });
    const adat = torzsElemez(await v.text());
    if (!v.ok) throw valaszHiba(v.status, adat);
    if (adat === null) throw new ApiHiba(v.status, t('A core válasza nem értelmezhető.'));
    return adat as T;
  } catch (e) {
    throw kivetelHiba(e);
  } finally {
    if (ido) clearTimeout(ido);
  }
}

/** Feltételes GET (C33, T070): az előző válasz ETag-jével; 304-nél `{adat: null}` (a hívó a régit tartja meg, nem tölt és
 *  nem épít újra). A gráf és a graf-meta mentésenként ~2,7 MB volt, a `GrafAdat` építése a fő szálon ~30 ms. */
export async function kerdezEtag<T>(
  ut: string,
  etag: string | null,
  o: Omit<KeresOpciok, 'metodus' | 'torzs' | 'keepalive'> = {},
): Promise<{ adat: T | null; etag: string | null }> {
  const vezerlo = new AbortController();
  const ido = idozito(o, vezerlo);
  try {
    const v = await fetch(ut, {
      headers: { 'X-Manifold': apiTitok(), ...(etag ? { 'If-None-Match': etag } : {}) },
      signal: vezerlo.signal,
      cache: 'no-store',
    });
    if (v.status === 304) return { adat: null, etag };
    const adat = torzsElemez(await v.text());
    if (!v.ok) throw valaszHiba(v.status, adat);
    if (adat === null) throw new ApiHiba(v.status, t('A core válasza nem értelmezhető.'));
    return { adat: adat as T, etag: v.headers.get('ETag') };
  } catch (e) {
    throw kivetelHiba(e);
  } finally {
    if (ido) clearTimeout(ido);
  }
}
