// A tulajdonságsor Kivágás / Másolás / Beillesztés műveleteinek szövege (03-properties-06): a vágólap egy tulajdonság
// YAML-szerű szövege (`kulcs: érték`, a lista `[a, b]` vagy az Obsidian-féle `- elem` sorok). Tiszta függvények; az érték
// ellenőrzése és a beírás a megszokott `modosit` úton megy (a core adja a hibát), ez csak a szöveg ↔ érték átalakítás.

import { rogzitettTipus, type Tulajdonsag, type TulajdonsagTipus } from './tipusok';

/** Egy szöveg-elem YAML-szerű alakja: idézőjel kell, ha a szerkezetet törné (vessző, szögletes zárójel, kettőspont+szóköz, sortörés). */
function elemSzoveg(s: string): string {
  return /[,[\]"\n\r]|:\s|^\s|\s$|^#/.test(s) ? JSON.stringify(s) : s;
}

/** Az érték YAML-szerű alakja a vágólaphoz (a skalár szövege, a lista `[a, b]`, a null üres). */
export function ertekVagolapSzoveg(ertek: unknown): string {
  if (ertek === null || ertek === undefined) return '';
  if (Array.isArray(ertek)) return `[${ertek.filter((x) => x !== null && x !== undefined).map((x) => elemSzoveg(String(x))).join(', ')}]`;
  if (typeof ertek === 'object') return JSON.stringify(ertek);
  if (typeof ertek === 'string') return elemSzoveg(ertek);
  return String(ertek);
}

/** A tulajdonság a vágólapon: `kulcs: érték`. */
export function tulajdonsagVagolapSzoveg(t: Pick<Tulajdonsag, 'kulcs' | 'ertek'>): string {
  const e = ertekVagolapSzoveg(t.ertek);
  return e === '' ? `${t.kulcs}:` : `${t.kulcs}: ${e}`;
}

export interface VagolapTulajdonsag {
  /** a vágólapon álló kulcs; hiányzik, ha a szöveg csak érték */
  kulcs: string | null;
  ertek: unknown;
  tipus: TulajdonsagTipus;
}

const KULCS_SOR = /^([^\W\d][\w .-]*?)\s*:(?:\s+(.*)|\s*)$/;
const ELEM_SOR = /^\s*-\s+(.*)$/;

function idezettLevesz(s: string): string {
  const t = s.trim();
  if (t.length >= 2 && t[0] === '"' && t[t.length - 1] === '"') {
    try { return JSON.parse(t) as string; } catch { return t.slice(1, -1); }
  }
  if (t.length >= 2 && t[0] === "'" && t[t.length - 1] === "'") return t.slice(1, -1).replace(/''/g, "'");
  return t;
}

/** `[a, "b, c", d]` elemei (az idézett elem vesszőt is tartalmazhat). */
function inlineLista(belso: string): string[] {
  const ki: string[] = [];
  let akt = '', idezo = '';
  for (const c of belso) {
    if (idezo) {
      akt += c;
      if (c === idezo) idezo = '';
    } else if (c === '"' || c === "'") { idezo = c; akt += c; }
    else if (c === ',') { ki.push(akt); akt = ''; }
    else akt += c;
  }
  ki.push(akt);
  return ki.map(idezettLevesz).filter((x) => x !== '');
}

function skalar(s: string): { ertek: unknown; tipus: TulajdonsagTipus } {
  const nyers = s.trim();
  if (nyers === '') return { ertek: null, tipus: 'text' };
  if (nyers.startsWith('[') && nyers.endsWith(']')) return { ertek: inlineLista(nyers.slice(1, -1)), tipus: 'multitext' };
  const t = idezettLevesz(nyers);
  if (nyers === t) {
    if (/^(true|false)$/i.test(t)) return { ertek: t.toLowerCase() === 'true', tipus: 'checkbox' };
    if (/^[-+]?\d+([.,]\d+)?$/.test(t)) return { ertek: Number(t.replace(',', '.')), tipus: 'number' };
    if (/^\d{4}-\d{2}-\d{2}$/.test(t)) return { ertek: t, tipus: 'date' };
    if (/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?$/.test(t)) return { ertek: t.replace(' ', 'T'), tipus: 'datetime' };
  }
  return { ertek: t, tipus: 'text' };
}

/** A vágólap szövege tulajdonságként. `null`, ha üres vagy túl hosszú (a vágólap tetszőleges szöveg lehet).
 *  Formák: `kulcs: érték` · `kulcs: [a, b]` · `kulcs:` + `- elem` sorok · puszta érték (kulcs nélkül). */
export function vagolapTulajdonsag(szoveg: string): VagolapTulajdonsag | null {
  const sorok = szoveg.replace(/\r\n?/g, '\n').split('\n').filter((s) => s.trim() !== '');
  if (!sorok.length || szoveg.length > 20000) return null;
  const m = KULCS_SOR.exec(sorok[0]);
  if (m) {
    const kulcs = m[1].trim();
    const rendkivul = rogzitettTipus(kulcs);
    const elemek = sorok.slice(1).map((s) => ELEM_SOR.exec(s));
    if (!m[2] && elemek.length && elemek.every(Boolean)) {
      return { kulcs, ertek: elemek.map((e) => idezettLevesz(e![1])).filter((x) => x !== ''), tipus: rendkivul ?? 'multitext' };
    }
    if (sorok.length === 1) {
      const s = skalar(m[2] ?? '');
      return { kulcs, ertek: s.ertek, tipus: rendkivul ?? s.tipus };
    }
    return null;
  }
  if (sorok.length > 1) {
    const elemek = sorok.map((s) => ELEM_SOR.exec(s));
    if (elemek.every(Boolean)) return { kulcs: null, ertek: elemek.map((e) => idezettLevesz(e![1])).filter((x) => x !== ''), tipus: 'multitext' };
    return null;
  }
  const s = skalar(sorok[0]);
  return { kulcs: null, ertek: s.ertek, tipus: s.tipus };
}
