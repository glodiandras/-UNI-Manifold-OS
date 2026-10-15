// Tulajdonság-értékek átalakítása a panel mezőihez (C11b): wikilink-alakok, listák, dátum- és számbevitel.
// Tiszta függvények; a YAML-szerializálás és a séma a core dolga (core/tulajdonsagok.py), itt csak a bevitel.

const WIKI = /^\s*!?\[\[([^\]]*)\]\]\s*$/;

export interface WikiReszek {
  cel: string;
  alcel: string | null;
  alias: string | null;
  /** a chipen látszó szöveg: az alias, különben a cél (a horgony előtt ` › `) */
  felirat: string;
}

/** A `[[cél#alcím|alias]]` részei; `null`, ha az érték nem wikilink. */
export function wikiReszek(s: unknown): WikiReszek | null {
  if (typeof s !== 'string') return null;
  const m = WIKI.exec(s);
  if (!m) return null;
  const [bal, ...aliasReszek] = m[1].split('|');
  const alias = aliasReszek.length ? aliasReszek.join('|').trim() || null : null;
  const i = bal.indexOf('#');
  const cel = (i < 0 ? bal : bal.slice(0, i)).trim();
  const alcel = i < 0 ? null : bal.slice(i + 1).trim() || null;
  return { cel, alcel, alias, felirat: alias ?? (alcel ? `${cel} › ${alcel}` : cel) };
}

/** Egy lista-értékű mező elemei szövegként (a `null`/üres: nincs elem; a skalár egyelemű lista). */
export function listaElemek(ertek: unknown): string[] {
  if (ertek === null || ertek === undefined || ertek === '') return [];
  const tomb = Array.isArray(ertek) ? ertek : [ertek];
  return tomb.filter((x) => x !== null && x !== undefined && String(x).trim() !== '').map((x) => String(x));
}

/** Minden elem wikilink-e (és van elem): ekkor a mező link-mezőként jelenik meg. */
export function csupaLink(ertek: unknown): boolean {
  const e = listaElemek(ertek);
  return e.length > 0 && e.every((x) => wikiReszek(x) !== null);
}

/** A beírt név wikilinkké alakítása (a link-mezőkben: `NN`, `Source`, `Canvas`); a már `[[…]]` alakú érintetlen. */
export function linkke(szoveg: string): string {
  const s = szoveg.trim();
  return s === '' || WIKI.test(s) ? s : `[[${s}]]`;
}

/** Az érték a szöveges mezőben (a skalár; a lista vesszővel, a null üres). */
export function ertekSzoveg(ertek: unknown): string {
  if (ertek === null || ertek === undefined) return '';
  if (Array.isArray(ertek)) return ertek.map(String).join(', ');
  if (typeof ertek === 'object') return JSON.stringify(ertek);
  return String(ertek);
}

/** A `date` / `datetime-local` mező értéke a tárolt szövegből; a nem illeszkedő érték üres (a mező nem mutat hibásat). */
export function datumBevitel(tipus: 'date' | 'datetime', ertek: unknown): string {
  const s = typeof ertek === 'string' ? ertek.trim() : '';
  if (tipus === 'date') return /^\d{4}-\d{2}-\d{2}/.test(s) ? s.slice(0, 10) : '';
  const m = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})/.exec(s);
  return m ? `${m[1]}T${m[2]}` : /^\d{4}-\d{2}-\d{2}$/.test(s) ? `${s}T00:00` : '';
}

/** A szám-mező szövege számmá (a magyar tizedesvessző is jó); `undefined`: nem szám; `null`: üres. */
export function szamBevitel(szoveg: string): number | null | undefined {
  const s = szoveg.trim().replace(',', '.');
  if (s === '') return null;
  if (!/^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$/.test(s)) return undefined;
  const n = Number(s);
  return Number.isFinite(n) ? n : undefined;
}

/** A vesszővel tagolt lista-bevitel elemei (az új tulajdonság űrlapjához). */
export function listaBevitel(szoveg: string): string[] {
  return szoveg
    .split(',')
    .map((x) => x.trim())
    .filter(Boolean);
}

/** Az alapból listaként kezelt séma-kulcsok (üres értéknél is lista-mező jelenik meg). */
export const LISTA_KULCSOK = ['Tags', 'Source', 'NN'] as const;
/** A séma link-mezői: a beírt név automatikusan `[[…]]` lesz. */
export const LINK_KULCSOK = ['Source', 'NN', 'Canvas'] as const;
