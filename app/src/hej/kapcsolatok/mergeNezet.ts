// A kétoldalas, csak olvasható összevetés (`@codemirror/merge`) közös beállítása: a jegyzet előzményeinek diffje (C11b)
// és a vezérlő „Mit változtatott” nézete (C17) ugyanezt rajzolja.

import { MergeView } from '@codemirror/merge';
import { syntaxHighlighting } from '@codemirror/language';
import { EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { classHighlighter } from '@lezer/highlight';
import { MAGYAR_FELIRATOK, markdownNyelv } from '../../szerkeszto/beallitas';

export const lf = (s: string | null | undefined) => (s ?? '').replace(/\r\n?/g, '\n');

export function mergeNezet(parent: HTMLElement, a: string, b: string): MergeView {
  const kozos = [
    markdownNyelv(),
    EditorView.lineWrapping,
    syntaxHighlighting(classHighlighter),
    EditorState.phrases.of(MAGYAR_FELIRATOK),
    EditorState.readOnly.of(true),
    EditorView.editable.of(false),
  ];
  return new MergeView({
    parent,
    a: { doc: a, extensions: kozos },
    b: { doc: b, extensions: kozos },
    highlightChanges: true,
    gutter: true,
    collapseUnchanged: { margin: 3, minSize: 8 },
  });
}
