// Markdown-jelölők gépelés közbeni párosítása. Saját mező tartja számon a ténylegesen általunk írt
// zárójeleket: meglévő szövegen nem ugrunk át, kódban/YAML-ben pedig nem értelmezzük át a gépelést.

import { isolateHistory } from '@codemirror/commands';
import { ensureSyntaxTree } from '@codemirror/language';
import { EditorSelection, type EditorState, type Extension, Facet, Prec, StateEffect, StateField } from '@codemirror/state';
import { EditorView, keymap } from '@codemirror/view';
import type { SyntaxNode } from '@lezer/common';

export const autoParEngedelyezett = Facet.define<boolean, boolean>({ combine: (v) => v[0] ?? true });

/** A másik két csoport kapcsolója (Beállítások › Szerkesztő, 14-appearance-05): a Markdown-jelek (`* _ ~ = $`) az `autoParEngedelyezett`-et
 *  követik; a zárójelek `( {` és a `[[` záró `]]`-je, illetve az idézőjelek `' " \`` külön-külön kapcsolhatók. */
export interface ParKapcsolok { zarojel: boolean; idezojel: boolean }
export const autoParKapcsolok = Facet.define<ParKapcsolok, ParKapcsolok>({ combine: (v) => v[0] ?? { zarojel: true, idezojel: true } });

/** A CodeMirror `closeBrackets` párjai a kapcsolók szerint (a `[` szándékosan kimarad: a `[[`-t a wikilink-bővítmény kezeli). */
export function parosithatoJelek(state: EditorState): string[] {
  const k = state.facet(autoParKapcsolok);
  return [...(k.zarojel ? ['(', '{'] : []), ...(k.idezojel ? ["'", '"', '`'] : [])];
}

interface Par { from: number; to: number; jel: string; hossz: number }
const parokBeallit = StateEffect.define<readonly Par[]>();
const JELEK = new Set(['*', '_', '~', '=', '$']);
const KETTOS = new Set(['*', '_', '~', '=']);
const VEDETT = new Set(['FencedCode', 'CodeBlock', 'Frontmatter', 'MathBlock', 'InlineMath', 'InlineCode', 'HTMLBlock', 'CommentBlock', 'Comment', 'ObsidianCommentBlock', 'ObsidianComment', 'Link', 'URL', 'Wikilink', 'Embed', 'LinkReference']);

const parok = StateField.define<readonly Par[]>({
  create: () => [],
  update(ertek, tr) {
    for (const e of tr.effects) if (e.is(parokBeallit)) return e.value;
    if (!tr.docChanged) return ertek;
    return ertek.map((p) => ({ ...p, from: tr.changes.mapPos(p.from, 1), to: tr.changes.mapPos(p.to, 1) })).filter((p) =>
      p.to >= p.from + p.hossz && tr.state.sliceDoc(p.from, p.from + p.hossz) === p.jel.repeat(p.hossz) && tr.state.sliceDoc(p.to, p.to + p.hossz) === p.jel.repeat(p.hossz));
  },
});

function vedett(state: EditorState, from: number, to: number): boolean {
  const fa = ensureSyntaxTree(state, to, 100);
  if (!fa) return true;
  // A lezáró jel előtti pozíció még a képlet/kód része; a csomópont vége mögött már gépelhető próza.
  for (const pos of [from, to]) {
    for (let n: SyntaxNode | null = fa.resolveInner(pos, pos === to && from !== to ? -1 : 1); n; n = n.parent) {
      if (VEDETT.has(n.name) && n.from < to + (from === to ? 1 : 0) && n.to > from) return true;
    }
  }
  let talal = false;
  if (to > from) fa.iterate({ from, to, enter(n) { if (VEDETT.has(n.name) && n.from < to && n.to > from) talal = true; return !talal; } });
  return talal;
}

/** A beviteli kezelő külön is exportált, hogy ugyanazon az úton tesztelhető legyen, mint a beforeinput. */
export function markdownParBeir(view: EditorView, from: number, to: number, jel: string): boolean {
  const state = view.state;
  if (!JELEK.has(jel) || state.readOnly || !state.facet(autoParEngedelyezett) || view.composing || view.compositionStarted || from !== state.selection.main.from || to !== state.selection.main.to) return false;
  const regiek = state.field(parok);
  const torolt = new Set<Par>();
  const ujParok: { tipus: 'uj' | 'bovit' | 'atlep'; from: number; to: number; hossz: number }[] = [];
  let kezelt = false;
  const tr = state.changeByRange((r) => {
    const par = r.empty ? regiek.find((p) => p.to === r.head && p.jel === jel) : undefined;
    // A saját üres páron belüli második * → **|**. A dupla jelölők bezárásakor már egyenként
    // átugrunk; a szöveget nem kell újra kijelölni a félkövér/áthúzott/kiemelt beíráshoz.
    if (par) {
      torolt.add(par);
      kezelt = true;
      if (r.head === par.from + par.hossz && par.hossz === 1 && KETTOS.has(jel)) {
        ujParok.push({ tipus: 'bovit', from: par.from, to: par.to, hossz: 2 });
        return { changes: { from: r.head, insert: jel + jel }, range: EditorSelection.cursor(r.head + 1) };
      }
      if (par.hossz > 1) ujParok.push({ tipus: 'atlep', from: par.from, to: par.to, hossz: par.hossz - 1 });
      return { range: EditorSelection.cursor(r.head + 1) };
    }
    const elotte = state.sliceDoc(Math.max(0, r.from - 1), r.from);
    const utana = state.sliceDoc(r.to, Math.min(state.doc.length, r.to + 1));
    const sor = state.doc.lineAt(r.from);
    const torzs = sor.text.replace(/^[ \t]*(?:>[ \t]*)*(?:(?:[-+*]|\d{1,9}[.)])[ \t]+(?:\[[^\n]\][ \t]+)?)?/, '').trim();
    // A ~ párja kerítést, a $ párja több soros képletet nyithatna az üres tárolósoron, és ezzel
    // a következő bekezdéseket is átértelmezné. Itt a kézzel gépelt kerítés/$$ pontosan megmarad;
    // kijelölt szöveg körbefogása és soron belüli párosítás továbbra is működik.
    const uresBlokk = r.empty && (jel === '~' || jel === '$') && /^[~$]*$/.test(torzs);
    const jogos = !vedett(state, r.from, r.to) && !/\\$/.test(state.sliceDoc(state.doc.lineAt(r.from).from, r.from).replace(/\\\\/g, '')) &&
      !uresBlokk && (!r.empty || (!/[\p{L}\p{N}_]/u.test(elotte) && (!utana || /[\s)\]}.,;:!?]/.test(utana))));
    if (!jogos) return { changes: { from: r.from, to: r.to, insert: jel }, range: EditorSelection.cursor(r.from + 1) };
    kezelt = true;
    ujParok.push({ tipus: 'uj', from: r.from, to: r.to, hossz: 1 });
    if (r.empty) return { changes: { from: r.from, insert: jel + jel }, range: EditorSelection.cursor(r.from + 1) };
    return { changes: [{ from: r.from, insert: jel }, { from: r.to, insert: jel }], range: EditorSelection.range(r.anchor + 1, r.head + 1) };
  });
  if (!kezelt) return false;
  const valtozas = tr.changes;
  const uj = regiek.filter((p) => !torolt.has(p)).map((p) => ({ ...p, from: valtozas.mapPos(p.from, 1), to: valtozas.mapPos(p.to, 1) }));
  for (const p of ujParok) uj.push({
    jel, hossz: p.hossz,
    from: valtozas.mapPos(p.from, -1),
    to: p.tipus === 'uj' ? valtozas.mapPos(p.to, 1) - 1 : p.tipus === 'bovit' ? valtozas.mapPos(p.to, 1) - 1 : valtozas.mapPos(p.to, 1) + 1,
  });
  const doc = valtozas.apply(state.doc);
  const ervenyes = uj.filter((p) => p.to >= p.from + p.hossz && doc.sliceString(p.from, p.from + p.hossz) === p.jel.repeat(p.hossz) && doc.sliceString(p.to, p.to + p.hossz) === p.jel.repeat(p.hossz));
  view.dispatch(state.update(tr, { effects: parokBeallit.of(ervenyes), userEvent: 'input.type', scrollIntoView: true }));
  return true;
}

/** Backspace az általunk beszúrt üres párt egyszerre veszi ki. */
export function markdownParTorol(view: EditorView): boolean {
  const state = view.state;
  if (state.readOnly || !state.facet(autoParEngedelyezett) || view.composing || view.compositionStarted) return false;
  const regiek = state.field(parok);
  const celok = state.selection.ranges.map((r) => r.empty ? regiek.find((p) => p.to === r.head && p.from + p.hossz === r.head) : undefined);
  if (celok.some((p) => !p)) return false;
  const tr = state.changeByRange((r) => {
    const p = regiek.find((p) => p.to === r.head && p.from + p.hossz === r.head)!;
    return { changes: { from: p.from, to: p.to + p.hossz }, range: EditorSelection.cursor(p.from) };
  });
  view.dispatch(state.update(tr, { userEvent: 'delete.backward', annotations: isolateHistory.of('full'), scrollIntoView: true }));
  return true;
}

/** A normál zárójel/wikilink párosítást változatlanul hagyja; % sosem párosul (PDF-jelölők). */
export function autoParokBovitmeny(): Extension {
  return [parok, Prec.highest(EditorView.inputHandler.of(markdownParBeir)), Prec.high(keymap.of([{ key: 'Backspace', run: markdownParTorol }]))];
}
