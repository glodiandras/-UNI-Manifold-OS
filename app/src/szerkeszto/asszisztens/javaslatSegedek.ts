// A linkjavaslat tiszta segédei (C30b-mag): a core kódpont-pozícióinak UTF-16-ra váltása, a javaslatok szűrése (kód,
// frontmatter, link, képlet és minden más, ahová a link nem való), a kurzorhoz tartozó „aktív” javaslat és a küszöb-
// szabály. Nincs benne CodeMirror-nézet, hálózat és Svelte-állapot, ezért önállóan tesztelhető.

import { ensureSyntaxTree } from '@codemirror/language';
import type { EditorState, Text } from '@codemirror/state';
import type { EmlitesValasz, JavaslatKuszob } from '../../lib/asszisztens/tipusok';

export interface Javaslat {
  /** a nézet élete alatt egyedi */
  id: number;
  from: number;
  to: number;
  /** a megjelölt szöveg (az érvényesség ellenőrzéséhez) */
  szoveg: string;
  celUt: string;
  /** az elvetés kulcsa: ugyanaz a cél ugyanazzal az írásmóddal nem tér vissza */
  kulcs: string;
}

/** Ennyi csend (ms) után kérdez a core-tól, alapküszöbnél. */
export const VART_ALAP_MS = 1200;
/** Egyszerre ennyi javaslat látszik (alapküszöbnél), a kurzorhoz legközelebbiek. */
export const MAX_ALAP = 5;
/** A kérés szövegének felső határa (karakter): ennél nagyobb jegyzetnél nincs javaslat. */
export const MAX_KARAKTER = 600_000;
/** A kurzor ennyi kódegységgel a javaslat vége után még „a javaslaton” van (a Tab/Esc ilyenkor hat rá). */
export const AKTIV_TAVOLSAG = 24;

export interface KuszobSzabaly {
  /** a fajta némítva (nincs kérés, nincs aláhúzás) */
  tilt: boolean;
  vartMs: number;
  max: number;
  /** a jegyzet–cél hasonlóság alsó határa (C25c; a core a szorzóval együtt adja); hiányzik: nincs szűrés */
  hasonlosag?: number;
}

/** A `Statisztika.kuszob("emlites")` szorzója a javaslat gyakoriságára: a csend hosszát szorozza, szigorúnál egyszerre
 *  csak egy javaslat látszik; `nema`: nincs. A hasonlósági küszöböt (C30b) a core számolja a szorzóval (`hasonlosag_kuszob`):
 *  a szerkesztő csak alkalmazza. */
export function kuszobSzabaly(k: JavaslatKuszob | null | undefined): KuszobSzabaly {
  if (k?.szint === 'nema') return { tilt: true, vartMs: VART_ALAP_MS, max: 0 };
  const szorzo = k?.szorzo && k.szorzo > 0 ? k.szorzo : 1;
  const szabaly: KuszobSzabaly = { tilt: false, vartMs: Math.round(VART_ALAP_MS * szorzo), max: k?.szint === 'szigoru' ? 1 : MAX_ALAP };
  if (typeof k?.hasonlosag === 'number' && k.hasonlosag > 0) szabaly.hasonlosag = k.hasonlosag;
  return szabaly;
}

/** A hasonlósági szűrő (C30b, K205 (b)): a cél javaslat marad, ha a pontja legalább a küszöb, **vagy ha nincs pontja** (a cél
 *  nincs az indexben / nincs vektora: a lexikai javaslat változatlan, nem ítélünk). Nincs küszöb vagy nincs pont-térkép: nincs
 *  szűrő. */
export function hasonlosagSzuro(
  pontok: ReadonlyMap<string, number | null> | null,
  kuszob: number | undefined,
): ((celUt: string) => boolean) | undefined {
  if (!pontok || kuszob === undefined) return undefined;
  return (celUt) => {
    const pont = pontok.get(celUt);
    return pont === undefined || pont === null || pont >= kuszob;
  };
}

/** Kódpont → UTF-16 eltolás a `szoveg`-ben. Növekvő hívássorrendre lineáris (az emlitesek `kezd` szerint rendezettek). */
export function utf16Konvertalo(szoveg: string): (kodpont: number) => number {
  let i = 0;
  let c = 0;
  return (kodpont) => {
    if (kodpont < c) {
      i = 0;
      c = 0;
    }
    while (c < kodpont && i < szoveg.length) {
      const k = szoveg.charCodeAt(i);
      i += k >= 0xd800 && k <= 0xdbff && i + 1 < szoveg.length ? 2 : 1;
      c++;
    }
    return i;
  };
}

/** Ahová a link nem való: a core ezeket a szöveg maszkolásával eleve kihagyja, a felület a saját szintaxisfájával még
 *  egyszer ellenőrzi (a szöveg közben szerkesztődött, és a két elemző nem azonos). A ```` ```plot ```` és a
 *  ```` ```teszt ```` blokk is `FencedCode`. */
const TILTOTT = new Set([
  'FencedCode',
  'CodeBlock',
  'InlineCode',
  'Frontmatter',
  'Wikilink',
  'Embed',
  'Link',
  'Image',
  'URL',
  'Autolink',
  'LinkReference',
  'InlineMath',
  'DisplayMath',
  'MathBlock',
  'HTMLBlock',
  'HTMLTag',
  'Comment',
  'CommentBlock',
  'ProcessingInstruction',
]);

/** Tiltott helyen áll-e a `[from, to)` szakasz. Ha a szintaxisfa az időkorlátig nem épül ki, óvatosan igen (nincs javaslat). */
export function tiltottHelyen(state: EditorState, from: number, to: number): boolean {
  const fa = ensureSyntaxTree(state, Math.min(state.doc.length, to + 1), 50);
  if (!fa) return true;
  let talalt = false;
  fa.iterate({
    from,
    to,
    enter(n) {
      if (TILTOTT.has(n.name)) {
        talalt = true;
        return false;
      }
      return undefined;
    },
  });
  return talalt;
}

const SZOKARAKTER = /[\p{L}\p{N}_]/u;

/** A `[from, to)` a dokumentumban még az eredeti szöveg, önálló szóként (a határ két oldalán nem szókarakter). */
export function ervenyesSzo(doc: Text, from: number, to: number, szoveg: string): boolean {
  if (from < 0 || to > doc.length || to - from !== szoveg.length) return false;
  if (doc.sliceString(from, to) !== szoveg) return false;
  if (from > 0 && SZOKARAKTER.test(doc.sliceString(from - 1, from))) return false;
  if (to < doc.length && SZOKARAKTER.test(doc.sliceString(to, to + 1))) return false;
  return true;
}

/** A válasz javaslatai a `doc` szövegére: csak az egyértelmű célú, érvényes, nem tiltott helyen álló találatok. */
export function javaslatokBol(
  v: EmlitesValasz,
  state: EditorState,
  elutasitott: ReadonlySet<string>,
  kovId: () => number,
  celSzuro?: (celUt: string) => boolean,
): Javaslat[] {
  const doc = state.doc;
  const szoveg = doc.toString();
  const ut16 = utf16Konvertalo(szoveg);
  const ki: Javaslat[] = [];
  for (const m of [...v.emlitesek].sort((a, b) => a.kezd - b.kezd)) {
    if (m.tobbertelmu || !m.cel) continue; // rossz linket nem ajánlunk
    if (celSzuro && !celSzuro(m.cel)) continue; // a hasonlóság szűrője (C30b): a jegyzethez nem illő cél nem javaslat
    const from = ut16(m.kezd);
    const to = ut16(m.veg);
    if (!ervenyesSzo(doc, from, to, m.szoveg)) continue;
    const kulcs = `${m.cel}|${m.szoveg.toLowerCase()}`;
    if (elutasitott.has(kulcs)) continue;
    if (tiltottHelyen(state, from, to)) continue;
    ki.push({ id: kovId(), from, to, szoveg: m.szoveg, celUt: m.cel, kulcs });
  }
  return ki;
}

/** A `pos` bekezdése (az üres soroktól határolt sorok), legfeljebb `MAX_SOR` sornyira a két irányban. */
const MAX_SOR = 60;
export function bekezdesHatar(doc: Text, pos: number): [number, number] {
  const sor = doc.lineAt(pos);
  const ures = (n: number) => doc.line(n).text.trim() === '';
  let a = sor.number;
  let b = sor.number;
  for (let i = 0; i < MAX_SOR && a > 1 && !ures(a - 1); i++) a--;
  for (let i = 0; i < MAX_SOR && b < doc.lines && !ures(b + 1); i++) b++;
  return [doc.line(a).from, doc.line(b).to];
}

/** A kurzorhoz tartozó „aktív” javaslat: amelyiken a kurzor áll, különben amelyik vége a kurzor előtt legfeljebb
 *  `AKTIV_TAVOLSAG` kódegységgel, ugyanabban a sorban ér véget. */
export function aktivJavaslat(lista: readonly Javaslat[], doc: Text, fej: number): Javaslat | null {
  const sorEleje = doc.lineAt(fej).from;
  let jo: Javaslat | null = null;
  for (const j of lista) {
    if (j.from <= fej && fej <= j.to) return j;
    if (j.to < fej && fej - j.to <= AKTIV_TAVOLSAG && j.to >= sorEleje && (!jo || j.to > jo.to)) jo = j;
  }
  return jo;
}

/** A link szövege az említéshez: `[[Cél]]`, ha az említés pontosan a név; különben `[[Cél|szöveg]]`. */
export function emlitesLink(cel: string, nev: string, emlitett: string): string {
  return emlitett === nev ? `[[${cel}]]` : `[[${cel}|${emlitett}]]`;
}
