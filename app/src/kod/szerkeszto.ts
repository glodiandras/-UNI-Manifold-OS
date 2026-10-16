// A kód-fül szerkesztő CodeMirror-bővítményei (C36a-UI, F10: minden nyelvre): sorszám, aktív sor, zárójel-párosítás és -zárás,
// behúzás beíráskor, összecsukás, history, keresés (⌘F), kódrészletek (C++), a nyelv színezése (lustán betöltve, a betöltés után
// Compartmentbe kerül), és a fordító / futási hiba diagnosztikája a hozzá kötött soron aláhúzásként (`@codemirror/lint`: ez a ⌘R
// eredménye, nem LSP — a clangd a C36a3). A Markdown-szerkesztő bővítményei (⌘B, linkek, Live Preview) itt nincsenek.

import { autocompletion, closeBrackets, closeBracketsKeymap, completionKeymap } from '@codemirror/autocomplete';
import { defaultKeymap, history, historyKeymap, indentWithTab } from '@codemirror/commands';
import { bracketMatching, foldGutter, foldKeymap, indentOnInput, indentUnit, LanguageDescription, syntaxHighlighting } from '@codemirror/language';
import { lintGutter, setDiagnostics, type Diagnostic } from '@codemirror/lint';
import { search, searchKeymap } from '@codemirror/search';
import { Compartment, EditorState, type Extension, type Text } from '@codemirror/state';
import {
  drawSelection,
  EditorView,
  highlightActiveLine,
  highlightActiveLineGutter,
  highlightSpecialChars,
  keymap,
  lineNumbers,
} from '@codemirror/view';
import { classHighlighter } from '@lezer/highlight';
import { gepelesMero } from '../lib/tracker/gepelesMero';
import { lustaImportHiba } from '../lib/vezerlo/epites.svelte';
import { MAGYAR_FELIRATOK, szinkronJel } from '../szerkeszto/beallitas';
import type { Diagnosztika, Futas } from './futas.svelte';
import { reszletForras } from './reszletek';

export const nyelvKapcsolo = new Compartment();
export const kodIrhatosag = new Compartment();

/** A C++-nyelv lusta betöltése (egyszer); hibánál színezés nélkül marad a szerkesztő. */
let nyelvIgeret: Promise<Extension | null> | null = null;
export function cppNyelv(): Promise<Extension | null> {
  nyelvIgeret ??= import('@codemirror/lang-cpp').then(
    (m) => m.cpp(),
    () => {
      nyelvIgeret = null; // a következő fül újrapróbál; ha a dist közben újrafordult, újratöltés kell
      lustaImportHiba();
      return null;
    },
  );
  return nyelvIgeret;
}

/** A core nyelv-azonosítója → a `@codemirror/language-data` neve (a többi nyelv lustán, nyelvenként tölt). */
export const SZINEZO_NEV: Record<string, string> = {
  c: 'C',
  python: 'Python',
  javascript: 'JavaScript',
  typescript: 'TypeScript',
  java: 'Java',
  go: 'Go',
  rust: 'Rust',
  swift: 'Swift',
};

const tobbiNyelv = new Map<string, Promise<Extension | null>>();

/** A nyelv színezője (azonosító szerint): a C++ a saját csomagjával, a többi a nyelv-adatból, nyelvenként egyszer és lustán. Ismeretlen
 *  nyelv vagy betöltési hiba: `null` (a szerkesztő színezés nélkül is használható). */
export function kodNyelv(azonosito: string | null | undefined): Promise<Extension | null> {
  if (!azonosito) return Promise.resolve(null);
  if (azonosito === 'cpp') return cppNyelv();
  const nev = SZINEZO_NEV[azonosito];
  if (!nev) return Promise.resolve(null);
  let igeret = tobbiNyelv.get(azonosito);
  if (!igeret) {
    igeret = import('@codemirror/language-data').then(
      (m) => m.languages.find((l: LanguageDescription) => l.name === nev)?.load().then((tamogatas) => tamogatas as Extension) ?? null,
      () => {
        tobbiNyelv.delete(azonosito);
        lustaImportHiba();
        return null;
      },
    );
    tobbiNyelv.set(azonosito, igeret);
  }
  return igeret.catch(() => null);
}

export interface KodOpciok {
  csakOlvashato: boolean;
  cimke: string;
  /** a nyelv azonosítója: a kódrészletek (C++) csak a `cpp` nyelvnél ajánlódnak */
  nyelv?: string;
}

export function kodBovitmenyek(o: KodOpciok): Extension[] {
  return [
    lineNumbers(),
    highlightActiveLineGutter(),
    foldGutter({ openText: '▾', closedText: '▸' }),
    lintGutter(),
    highlightSpecialChars(),
    history(),
    drawSelection(),
    indentOnInput(),
    bracketMatching(),
    closeBrackets(),
    highlightActiveLine(),
    indentUnit.of('    '),
    EditorState.tabSize.of(4),
    EditorState.allowMultipleSelections.of(true),
    EditorState.phrases.of(MAGYAR_FELIRATOK),
    search({ top: true }),
    autocompletion({ override: o.nyelv === undefined || o.nyelv === 'cpp' ? [reszletForras] : [], icons: false }),
    keymap.of([...closeBracketsKeymap, ...completionKeymap, indentWithTab, ...searchKeymap, ...historyKeymap, ...foldKeymap, ...defaultKeymap]),
    syntaxHighlighting(classHighlighter),
    nyelvKapcsolo.of([]),
    kodIrhatosag.of(EditorState.readOnly.of(o.csakOlvashato)),
    EditorState.changeFilter.of((tr) => !tr.startState.readOnly || !!tr.annotation(szinkronJel)),
    gepelesMero(),
    EditorView.editorAttributes.of({ class: 'cm-kodszerkeszto' }),
    EditorView.contentAttributes.of({
      spellcheck: 'false',
      autocorrect: 'off',
      autocapitalize: 'off',
      translate: 'no',
      'aria-label': o.cimke,
      'data-fokusz-cel': '',
    }),
  ];
}

/** A fordító diagnosztikája (a saját forrás sorai) → CodeMirror-diagnosztika. A sor/oszlop 1-től számol; a dokumentumon
 *  kívül eső hely a dokumentum végére szorul (a forrás a futás óta változhatott). `forras`: a diagnosztika neve a listában. */
export function lintDiagnosztika(doc: Text, lista: Diagnosztika[], forras = 'clang'): Diagnostic[] {
  const ki: Diagnostic[] = [];
  for (const d of lista) {
    if (!d.sajat || !d.sor || d.szint === 'note' || d.szint === 'remark') continue;
    ki.push(sorDiagnosztika(doc, d.sor, d.oszlop, d.szint === 'warning' ? 'warning' : 'error', d.uzenet + (d.kapcsolo ? ` [${d.kapcsolo}]` : ''), forras));
  }
  return ki;
}

function sorDiagnosztika(doc: Text, sorSzam: number, oszlop: number | null | undefined, severity: Diagnostic['severity'], message: string, source: string): Diagnostic {
  const sor = doc.line(Math.min(Math.max(1, sorSzam), doc.lines));
  const from = Math.min(sor.from + Math.max(0, (oszlop ?? 1) - 1), sor.to);
  // az aláhúzás a hely szavát fedi (legalább egy karakter, ha a sor nem üres)
  const szo = /^[\w$]+/.exec(sor.text.slice(from - sor.from))?.[0].length ?? 1;
  const to = Math.min(sor.to, from + Math.max(1, szo));
  return { from, to: Math.max(from, to), severity, message, source };
}

/**
 * Egy futás sorhoz kötött üzenetei az editorban: a fordító / szintaxis-vizsgálat saját soros üzenetei, és a tesztek futási hibáinak
 * jelentése (a saját forrás sora: Python traceback, Node, Java, Go, Rust, Swift, sanitizer). Ugyanaz a hely + üzenet egyszer szerepel.
 */
export function futasDiagnosztika(doc: Text, futas: Futas | null, forras: string): Diagnostic[] {
  if (!futas) return [];
  const ki = lintDiagnosztika(doc, futas.fordit?.diagnosztika ?? [], forras);
  const latott = new Set(ki.map((d) => `${d.from}:${d.message}`));
  for (const te of futas.tesztek) {
    const j = te.jelentes;
    if (!j?.sajat || !j.sor || !j.leiras) continue;
    const d = sorDiagnosztika(doc, j.sor, j.oszlop, 'error', j.leiras, forras);
    const kulcs = `${d.from}:${d.message}`;
    if (latott.has(kulcs)) continue;
    latott.add(kulcs);
    ki.push(d);
  }
  return ki;
}

/** A diagnosztika beállítása (üres listával törli). */
export function diagnosztikaBeallit(view: EditorView, lista: Diagnostic[]): void {
  view.dispatch(setDiagnostics(view.state, lista));
}
