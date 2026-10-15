// A nyers frontmatter kiegészítése a szerkesztőben: ha a kurzor a `---` blokkon belül áll, a CodeMirror kiegészítője
// ugyanazt kínálja, mint a tulajdonság-panel (`javaslat.ts`):
//   kulcs-hely  `Ta|`              → a séma- és a vault-kulcsok; a beírás `Kulcs: `;
//   érték       `Tags: Ma|`, `  - Ma|`  → a kulcs értékei (Tags: a vault címkéi és a séma értékkészlete, Status: az engedett
//                                    értékek, más kulcs: a vaultban használt értékei); a beírás YAML-hű (szükség esetén idézve);
//   link        `Source:`/`NN:`/`Canvas:` alatt, vagy `"[[` kezdetű érték → a vault fájljai; a beírás `"[[cél#horgony]]"`,
//                                    a cél a core `linkcel`-éből (L42), a gépelt `#page=12` horgony megmarad.
// A billentyűk: a lista magától nem jelöl ki sort (`selectOnOpen: false`), így az ↩ a megszokott új sor marad; a ↑↓ jelöl,
// az ↩ a kijelöltet, a Tab a kijelöltet vagy az elsőt veszi; Esc bezár; ⌃Space üres helyen is nyit. Gépeléskor a lista
// a kiegészítő saját késleltetésével (`activateOnTypingDelay`) számolódik, a gyorsítótárazott listából: a gépelés útvonala
// nem vár a core-ra. A `[[` saját menüje elsőbbséget kap (amíg nyitva van, ez a forrás hallgat). Csak olvasható
// dokumentumban nincs kiegészítés.

import {
  acceptCompletion,
  autocompletion,
  completionStatus,
  selectedCompletionIndex,
  setSelectedCompletion,
  type Completion,
  type CompletionContext,
  type CompletionResult,
} from '@codemirror/autocomplete';
import { syntaxTree } from '@codemirror/language';
import { type EditorState, type Extension, Prec } from '@codemirror/state';
import { EditorView, keymap } from '@codemirror/view';
import { linkek } from '../../lib/vault/linkek.svelte';
import { jegyzetUtja } from '../elo/jegyzet';
import { kiegeszitesForras, kiegeszitesNyitva } from '../linkek/kiegeszites';
import { tulajdonsagApi } from './api';
import { ertekLista, javaslatFajta, kulcsLista, linkLista, type JavaslatElem, type JavaslatLista, JavaslatTar } from './javaslat';

// ---------------------------------------------------------------------- a kurzor helye a frontmatterben

export type FmHely =
  | { fajta: 'kulcs'; from: number; to: number; q: string; kulcsok: string[] }
  | { fajta: 'ertek'; kulcs: string; from: number; to: number; q: string; lista: boolean; tarsak: string[] };

const KULCS_SOR = /^([^\s#:\-][^:]*?)\s*:(?=\s|$)/;
const LISTA_ELEM = /^(\s*)-\s+(.*)$/;

/** A frontmatter-tartalom tartománya, ha a `pos` benne áll (a szintaxisfa `FrontmatterContent` csomópontja, L39). */
function tartalom(state: EditorState, pos: number): { from: number; to: number } | null {
  for (let n: ReturnType<ReturnType<typeof syntaxTree>['resolveInner']> | null = syntaxTree(state).resolveInner(pos, -1); n; n = n.parent)
    if (n.name === 'FrontmatterContent') return { from: n.from, to: n.to };
  return null;
}

/** A tartalom kulcsai a sorrendjükben (a kulcs-javaslat ezeket kihagyja). */
function blokkKulcsok(state: EditorState, t: { from: number; to: number }): string[] {
  const ki: string[] = [];
  for (const s of state.sliceDoc(t.from, t.to).split('\n')) {
    const m = KULCS_SOR.exec(s);
    if (m) ki.push(m[1].trim());
  }
  return ki;
}

/** Egy lista-kulcs elemei (a `- x` sorok a kulcs alatt): az érték-javaslat ezeket kihagyja. */
function listaTarsak(state: EditorState, kulcsSor: number, t: { from: number; to: number }, kiveve: number): string[] {
  const ki: string[] = [];
  const utolso = state.doc.lineAt(t.to).number;
  for (let i = kulcsSor + 1; i <= utolso; i++) {
    if (i === kiveve) continue;
    const s = state.doc.line(i).text;
    const m = LISTA_ELEM.exec(s);
    if (!m) {
      if (KULCS_SOR.test(s)) break;
      continue;
    }
    ki.push(m[2].trim().replace(/^"(.*)"$/, '$1').replace(/^'(.*)'$/, '$1'));
  }
  return ki;
}

/** Hol áll a kurzor a frontmatterben: kulcs-helyen, egy kulcs értékén (a sorában vagy a lista egy elemén), vagy sehol. */
export function fmHely(state: EditorState, pos: number): FmHely | null {
  const t = tartalom(state, pos);
  if (!t) return null;
  const sor = state.doc.lineAt(pos);
  if (sor.from < t.from || /^---/.test(sor.text)) return null;
  const elotte = sor.text.slice(0, pos - sor.from);
  const utana = sor.text.slice(pos - sor.from);
  const zaro = /^(?:\]\])?["']?\s*$/.exec(utana) ? utana.replace(/\s*$/, '').length : 0; // a `[[` párja és az idézőjel
  const lista = LISTA_ELEM.exec(elotte);
  if (lista) {
    // a lista-elem gazdája: a fölötte álló első kulcs-sor
    for (let i = sor.number - 1; i >= state.doc.lineAt(t.from).number; i--) {
      const m = KULCS_SOR.exec(state.doc.line(i).text);
      if (!m) continue;
      const q = lista[2];
      return { fajta: 'ertek', kulcs: m[1].trim(), from: pos - q.length, to: pos + zaro, q, lista: true, tarsak: listaTarsak(state, i, t, sor.number) };
    }
    return null;
  }
  const kulcs = KULCS_SOR.exec(elotte);
  if (kulcs) {
    const utan = elotte.slice(kulcs[0].length);
    const ures = /^\s*/.exec(utan)![0].length;
    const q = utan.slice(ures);
    if (q.startsWith('[') && !q.startsWith('[[')) return null; // YAML flow-lista: nem kínálunk bele
    if (q.startsWith('{') || q.startsWith('|') || q.startsWith('>')) return null;
    return { fajta: 'ertek', kulcs: kulcs[1].trim(), from: pos - q.length, to: pos + zaro, q, lista: false, tarsak: [] };
  }
  // kulcs-hely: a sor eleje a kettőspontig (a meglévő kulcs átírásakor a kurzor utáni rész is cserélődik, a `:` marad)
  const kulcsVeg = /^[^:]*(?=:)/.exec(utana)?.[0].replace(/\s+$/, '').length ?? 0;
  if (/^[^\s#:\-]/.test(elotte) && !elotte.includes(':'))
    return { fajta: 'kulcs', from: sor.from, to: pos + kulcsVeg, q: elotte, kulcsok: blokkKulcsok(state, t) };
  if (elotte === '' && sor.text === '') return { fajta: 'kulcs', from: sor.from, to: pos, q: '', kulcsok: blokkKulcsok(state, t) };
  return null;
}

// ---------------------------------------------------------------------- YAML-hű beírás

const IDEZENDO = /^[\s[\]{}&*!|>'"%@`#,?:-]|: | #|\s$|^(?:true|false|yes|no|on|off|null|~|[-+]?\d[\d_.]*(?:e[-+]?\d+)?)$/i;

/** A skalár értéke YAML-ban: ami másként olvasódna (szám, logikai, jelölő-kezdet, `: `, ` #`), idézőjelbe kerül. */
export function yamlSkalar(v: string): string {
  return IDEZENDO.test(v) ? JSON.stringify(v) : v;
}

// ---------------------------------------------------------------------- a forrás

export interface FmKiegeszitesOpciok {
  /** a kulcs- és érték-listák (alapból a core végpontjai, gyorsítótárazva) */
  tar?: Pick<JavaslatTar, 'kulcsok' | 'ertekek'>;
  linkCel?: (ut: string, forras: string) => Promise<string>;
}

function opcio(e: JavaslatElem, i: number, apply: Completion['apply'], tipus: string): Completion {
  const reszlet = [e.megjegyzes, e.jelzo].filter(Boolean).join(' · ');
  return { label: e.nev, detail: reszlet || undefined, info: e.leiras, apply, type: tipus, boost: 99 - Math.min(i, 198) };
}

/** A kiemelés a CodeMirror alakjában (`[from, to, from, to…]` a címkén). */
function egyezes(elemek: JavaslatElem[]): (c: Completion) => readonly number[] {
  const t = new Map(elemek.map((e) => [e.nev, e.kiemeles ?? []]));
  return (c) => (t.get(c.label) ?? []).flat();
}

/** a szerkesztők közös gyorsítótára (a core-listák fülenként nem kérődnek újra) */
let alapTar: JavaslatTar | null = null;

export function fmForras(o: FmKiegeszitesOpciok = {}) {
  const tar = o.tar ?? (alapTar ??= new JavaslatTar(tulajdonsagApi()));
  const linkCel = o.linkCel ?? ((u: string, f: string) => linkek.linkCel(u, f));
  return async (cx: CompletionContext): Promise<CompletionResult | null> => {
    const s = cx.state;
    if (s.readOnly || kiegeszitesNyitva(s)) return null;
    const h = fmHely(s, cx.pos);
    if (!h) return null;
    // magától csak gépelt szövegre nyílik (különben az üres értékhely ↩-je is a listába futna); ⌃Space mindig
    if (!cx.explicit && !h.q.trim()) return null;
    const ut = s.facet(jegyzetUtja) ?? '';
    let lista: JavaslatLista;
    let apply: (e: JavaslatElem) => Completion['apply'];
    let tipus: string;
    if (h.fajta === 'kulcs') {
      lista = kulcsLista(await tar.kulcsok(ut).catch(() => []), h.q, h.kulcsok);
      apply = (e) => (view, _c, from, to) => {
        const veg = view.state.sliceDoc(to, view.state.doc.lineAt(to).to);
        const ins = /^\s*:/.test(veg) ? e.ertek : `${e.ertek}: `;
        view.dispatch({ changes: { from, to, insert: ins }, selection: { anchor: from + ins.length }, userEvent: 'input.complete' });
      };
      tipus = 'property';
    } else if (javaslatFajta(h.kulcs) === 'link' || /^["']?!?\[\[/.test(h.q)) {
      const f = s.facet(kiegeszitesForras);
      if (!f) return null;
      lista = linkLista(f, h.q, h.kulcs, ut, linkCel, h.tarsak);
      apply = (e) => (view, _c, from, to) => {
        const eredeti = view.state.doc;
        void (async () => {
          const link = e.feloldas ? await e.feloldas() : e.ertek;
          if (view.state.doc !== eredeti) return; // közben gépelt: a javaslat elavult
          const ins = JSON.stringify(link);
          view.dispatch({ changes: { from, to, insert: ins }, selection: { anchor: from + ins.length }, userEvent: 'input.complete' });
        })();
      };
      tipus = 'link';
    } else {
      lista = ertekLista(await tar.ertekek(ut, h.kulcs).catch(() => []), h.q.replace(/^["']/, ''), h.tarsak);
      apply = (e) => (view, _c, from, to) => {
        const ins = yamlSkalar(e.ertek);
        view.dispatch({ changes: { from, to, insert: ins }, selection: { anchor: from + ins.length }, userEvent: 'input.complete' });
      };
      tipus = 'enum';
    }
    if (!lista.elemek.length) return null;
    return {
      from: h.from,
      // az értéknél a kurzor utáni `]]` és záró idézőjel, a kulcsnál a kettőspont előtti rész is a cserélt tartományba tartozik
      to: h.to,
      options: lista.elemek.map((e, i) => opcio(e, i, apply(e), tipus)),
      filter: false,
      getMatch: egyezes(lista.elemek),
    };
  };
}

/** Tab: a kijelölt javaslat, vagy (kijelölés nélkül) az első; nyitott lista nélkül a Tab a megszokott. */
function tabElfogad(view: EditorView): boolean {
  if (completionStatus(view.state) !== 'active') return false;
  if (selectedCompletionIndex(view.state) === null) view.dispatch({ effects: setSelectedCompletion(0) });
  return acceptCompletion(view);
}

/** A frontmatter kiegészítése a szerkesztőben (a `[[` kiegészítés forrásával együtt kerül be). */
export function fmKiegeszites(o: FmKiegeszitesOpciok = {}): Extension {
  return [
    autocompletion({
      override: [fmForras(o)],
      icons: false,
      selectOnOpen: false,
      activateOnTypingDelay: 120,
      tooltipClass: () => 'fm-kiegeszites',
    }),
    Prec.highest(keymap.of([{ key: 'Tab', run: tabElfogad }])),
  ];
}
