// A core HTTP-API-ja (ARCHITECTURE 2.): ugyanaz az origin, minden kérésben `X-Manifold: <API-titok>` (35. döntés: a core induláskor
// sorsolja, a héj injektálja a lapba — `titok.ts`).

import { apiTitok } from './titok';

export class ApiHiba extends Error {
  constructor(
    readonly statusz: number,
    uzenet: string,
    readonly adat: Record<string, unknown> = {},
  ) {
    super(uzenet);
    this.name = 'ApiHiba';
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
export const KAPCSOLAT_HIBA = 'A core nem érhető el (megszakadt a kapcsolat).';

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
  400: 'A core elutasította a kérést (400).',
  403: 'A core megtagadta a kérést (403).',
  404: 'Nem található (404).',
  408: 'A core nem válaszolt időben (408).',
  413: 'A kérés túl nagy (413).',
  423: 'Az erőforrás foglalt (423).',
  500: 'A core belső hibája (500).',
  502: 'A core nem érhető el (502).',
  503: 'A core most nem tudja kiszolgálni a kérést (503).',
  504: 'A core nem válaszolt időben (504).',
  507: 'Nincs elég hely a lemezen (507).',
};

/** A HTTP-státusz magyar üzenete, ha a válasz nem hozott saját (`hiba`) üzenetet. */
export function statuszUzenet(statusz: number): string {
  return STATUSZ_UZENET[statusz] ?? `A core hibát adott (${statusz}).`;
}

/**
 * Bármely hiba felhasználónak mutatható, magyar szövege: az ApiHiba üzenete, a nyers hálózati hiba helyett a
 * `KAPCSOLAT_HIBA`, egyébként az üzenet (az „ApiHiba: …” / „Error: …” előtag nélkül).
 */
export function hibaSzoveg(e: unknown): string {
  const uzenet = e instanceof Error ? e.message : typeof e === 'string' ? e : String(e);
  return NYERS_HALOZATI.some((m) => m.test(uzenet.trim())) ? KAPCSOLAT_HIBA : uzenet;
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

/** A nem sikeres válasz hibája: a core magyar `hiba` üzenete, vagy a státusz magyar üzenete; a státusz mindig megmarad. */
function valaszHiba(statusz: number, adat: Record<string, unknown> | null): ApiHiba {
  const sajat = adat && typeof adat === 'object' && adat.hiba != null && adat.hiba !== '' ? String(adat.hiba) : null;
  return new ApiHiba(statusz, sajat ?? statuszUzenet(statusz), adat && typeof adat === 'object' ? adat : {});
}

/** A fetch (vagy az elemzés) hibája ApiHiba-ként: megszakítás = időtúllépés, a nyers hálózati hiba magyarul. */
function kivetelHiba(e: unknown): ApiHiba {
  if (e instanceof ApiHiba) return e;
  if (e instanceof DOMException && e.name === 'AbortError') return new ApiHiba(0, 'időtúllépés');
  return new ApiHiba(0, hibaSzoveg(e));
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
    if (adat === null) throw new ApiHiba(v.status, 'A core válasza nem értelmezhető.');
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
    if (adat === null) throw new ApiHiba(v.status, 'A core válasza nem értelmezhető.');
    return { adat: adat as T, etag: v.headers.get('ETag') };
  } catch (e) {
    throw kivetelHiba(e);
  } finally {
    if (ido) clearTimeout(ido);
  }
}
