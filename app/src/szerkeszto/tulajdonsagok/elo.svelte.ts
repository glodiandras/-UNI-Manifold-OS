// CX-006: a tulajdonságok a YAML helyén, a dokumentum görgetésének részeként élnek (Élő nézet; a Forrás módban a nyers
// YAML marad, 80(d)). A formai hibás frontmatter nem rejtőzik el: a core elemzése (`Elemzes.hiba`) után a blokk nyersen,
// szerkeszthetően látszik, fölötte a hibaüzenettel; a javítás után a widget visszaáll.
//
// A kurzor nem parkolhat a widget mögötti, láthatatlan helyeken (a `---` előtt vagy a záró `---` sor végén): ott a
// gépelés a frontmattert rontaná el, és a WebKit a blokk-widget szélén rajzolja a caretet. Az ilyen kijelölés a törzs
// elejére kerül (`kurzorOr`).
import { EditorSelection, EditorState, Facet, StateEffect, StateField, type Extension, type Text } from '@codemirror/state';
import { Decoration, EditorView, WidgetType, type DecorationSet } from '@codemirror/view';
import { mount, unmount } from 'svelte';
import EloTulajdonsagok from './EloTulajdonsagok.svelte';
import { fmBlokk } from './fm';
import type { LinkForras } from './javaslat';

interface Beallitas { ut: string; nyitottsag: { nyitva: boolean }; kiegeszites?: LinkForras }
export const eloTulajdonsagForras = Facet.define<Beallitas, Beallitas | null>({
  combine: (v) => v[0] ?? null,
});

/** A core a frontmattert formai hibásnak találta (`string`: az ok) vagy rendben van (`null`). */
export const eloFmHiba = StateEffect.define<string | null>();

interface Props { view: EditorView; valtozat: number; hiba: string | null }
const peldanyok = new WeakMap<HTMLElement, { props: Props; peldany: object }>();

class TulajdonsagWidget extends WidgetType {
  constructor(readonly b: Beallitas, readonly szoveg: string, readonly csakOlvashato: boolean, readonly hiba: string | null) { super(); }
  eq(m: TulajdonsagWidget) {
    return this.b === m.b && this.szoveg === m.szoveg && this.csakOlvashato === m.csakOlvashato && this.hiba === m.hiba;
  }
  toDOM(view: EditorView) {
    const dom = document.createElement('div');
    dom.className = 'cm-tulajdonsagok';
    const props = $state<Props>({ view, valtozat: 0, hiba: this.hiba });
    const peldany = mount(EloTulajdonsagok, { target: dom, props: {
      ...this.b,
      get view() { return props.view; },
      get valtozat() { return props.valtozat; },
      get hiba() { return props.hiba; },
      jelez: (hiba: string | null) => hibaJelez(props.view, hiba),
    } });
    peldanyok.set(dom, { props, peldany });
    return dom;
  }
  updateDOM(dom: HTMLElement, view: EditorView) {
    const p = peldanyok.get(dom);
    if (!p) return false;
    p.props.view = view;
    p.props.hiba = this.hiba;
    p.props.valtozat++;
    return true;
  }
  destroy(dom: HTMLElement) {
    const p = peldanyok.get(dom);
    if (p) void unmount(p.peldany);
    peldanyok.delete(dom);
  }
  ignoreEvent() { return true; }
}

/** Az elemzés eredménye a szerkesztő állapotába (a CM frissítésén kívül, egy mikrotaszk után). */
function hibaJelez(view: EditorView, hiba: string | null) {
  queueMicrotask(() => {
    const f = view.state.field(eloTulajdonsagMezo, false);
    if (!f || f.hiba === hiba || !view.dom.isConnected) return;
    view.dispatch({ effects: eloFmHiba.of(hiba) });
  });
}

interface Allapot { hiba: string | null; deco: DecorationSet }

function diszites(state: EditorState, hiba: string | null): DecorationSet {
  const b = state.facet(eloTulajdonsagForras);
  if (!b) return Decoration.none;
  const fm = fmBlokk(state.doc);
  const nyers = !fm || hiba !== null;
  const widget = new TulajdonsagWidget(b, fm?.szoveg ?? '', state.readOnly, fm ? hiba : null);
  return Decoration.set([nyers
    ? Decoration.widget({ widget, block: true, side: -1 }).range(0)
    : Decoration.replace({ widget, block: true }).range(0, fmVege(state.doc, fm.ig))]);
}

const fmVege = (doc: Text, ig: number) => doc.lineAt(Math.max(0, ig - 1)).to;

export const eloTulajdonsagMezo = StateField.define<Allapot>({
  create: (s) => ({ hiba: null, deco: diszites(s, null) }),
  update(regi, tr) {
    let hiba = regi.hiba;
    for (const e of tr.effects) if (e.is(eloFmHiba)) hiba = e.value;
    if (hiba === regi.hiba && !tr.docChanged && !tr.reconfigured) return regi;
    return { hiba, deco: diszites(tr.state, hiba) };
  },
  provide: (f) => [
    EditorView.decorations.from(f, (a) => a.deco),
    EditorView.atomicRanges.of((v) => v.state.field(f).deco),
  ],
});

/** A törzs első pozíciója, ha a frontmatter a widget mögött rejtőzik (és van utána sor); különben `null`. */
export function torzsEleje(state: EditorState): number | null {
  const f = state.field(eloTulajdonsagMezo, false);
  if (!f || f.hiba !== null || !state.facet(eloTulajdonsagForras)) return null;
  const fm = fmBlokk(state.doc);
  if (!fm) return null;
  const vege = fmVege(state.doc, fm.ig);
  return vege < state.doc.length ? vege + 1 : null;
}

const KORLAT = 20_000; // a `fmBlokk` első szelete: ennél hátrébb álló kurzornál a szűrő nem számol

const kurzorOr = EditorState.transactionFilter.of((tr) => {
  if (!tr.selection && !tr.reconfigured && !tr.effects.some((e) => e.is(eloFmHiba))) return tr;
  const sel = tr.newSelection;
  if (!sel.ranges.some((r) => r.empty && r.head < KORLAT)) return tr;
  const hatar = torzsEleje(tr.state);
  if (hatar === null || !sel.ranges.some((r) => r.empty && r.head < hatar)) return tr;
  const uj = EditorSelection.create(sel.ranges.map((r) => (r.empty && r.head < hatar ? EditorSelection.cursor(hatar) : r)), sel.mainIndex);
  return [tr, { selection: uj, sequential: true }];
});

/** A frissen létrehozott (vagy visszaállított) nézet kezdő kurzora: a szűrő csak tranzakcióra fut. */
export function eloKurzorIgazit(view: EditorView): void {
  const hatar = torzsEleje(view.state);
  if (hatar !== null && view.state.selection.ranges.some((r) => r.empty && r.head < hatar)) view.dispatch({ selection: view.state.selection });
}

export const eloTulajdonsagok: Extension = [eloTulajdonsagMezo, kurzorOr];
