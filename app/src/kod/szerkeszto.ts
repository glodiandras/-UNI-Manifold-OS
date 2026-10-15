// A `.cpp` szerkesztő CodeMirror-bővítményei (C36a-UI): sorszám, aktív sor, zárójel-párosítás és -zárás, behúzás beíráskor,
// összecsukás, history, keresés (⌘F), kódrészletek, C++-színezés (a `@codemirror/lang-cpp` lusta importtal, a nyelv a
// betöltés után Compartmentbe kerül), és a fordító diagnosztikája aláhúzásként (`@codemirror/lint`: ez a ⌘R eredménye, nem
// LSP — a clangd a C36a3). A Markdown-szerkesztő bővítményei (⌘B, linkek, Live Preview) itt nincsenek.

import { autocompletion, closeBrackets, closeBracketsKeymap, completionKeymap } from '@codemirror/autocomplete';
import { defaultKeymap, history, historyKeymap, indentWithTab } from '@codemirror/commands';
import { bracketMatching, foldGutter, foldKeymap, indentOnInput, indentUnit, syntaxHighlighting } from '@codemirror/language';
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
import type { Diagnosztika } from './futas.svelte';
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

export interface KodOpciok {
  csakOlvashato: boolean;
  cimke: string;
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
    autocompletion({ override: [reszletForras], icons: false }),
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
 *  kívül eső hely a dokumentum végére szorul (a forrás a futás óta változhatott). */
export function lintDiagnosztika(doc: Text, lista: Diagnosztika[]): Diagnostic[] {
  const ki: Diagnostic[] = [];
  for (const d of lista) {
    if (!d.sajat || !d.sor || d.szint === 'note' || d.szint === 'remark') continue;
    const sor = doc.line(Math.min(Math.max(1, d.sor), doc.lines));
    const from = Math.min(sor.from + Math.max(0, (d.oszlop ?? 1) - 1), sor.to);
    // az aláhúzás a hely szavát fedi (legalább egy karakter, ha a sor nem üres)
    const szo = /^[\w$]+/.exec(sor.text.slice(from - sor.from))?.[0].length ?? 1;
    const to = Math.min(sor.to, from + Math.max(1, szo));
    ki.push({
      from,
      to: Math.max(from, to),
      severity: d.szint === 'warning' ? 'warning' : 'error',
      message: d.uzenet + (d.kapcsolo ? ` [${d.kapcsolo}]` : ''),
      source: 'clang',
    });
  }
  return ki;
}

/** A diagnosztika beállítása (üres listával törli). */
export function diagnosztikaBeallit(view: EditorView, lista: Diagnosztika[]): void {
  view.dispatch(setDiagnostics(view.state, lintDiagnosztika(view.state.doc, lista)));
}
