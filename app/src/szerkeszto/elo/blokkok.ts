// A Live Preview blokkszintű díszítései (StateField: a sortörést is cserélő és a blokk-widget csak innen
// adható). A teljes elemzett dokumentumra épül, hogy a görgetés közben ne ugráljon a tartalom; a DOM-ot a
// CodeMirror úgyis csak a látható részre rajzolja, a widgetek `eq`-ja a forrásszöveg szerint újrahasznosít.
//
//   táblázat → a renderelt táblázat; `$$` blokk → a képlet (szerkesztés közben alatta élő előnézet);
//   soron belüli `$$` → a képlet; elválasztó → vonal; regiszteres kódblokk (Mermaid…) → a rajz;
//   `![[…]]` beágyazás → a tartalma (C10; egyedül álló sor: blokk, sor közepén: inline);
//   a kódblokk záró kerítése és a setext-cím aláhúzása → rejtve; összecsukott callout → a törzse rejtve.

import { syntaxTree } from '@codemirror/language';
import { type EditorState, type Range, StateField } from '@codemirror/state';
import { Decoration, type DecorationSet, EditorView } from '@codemirror/view';
import type { SyntaxNode } from '@lezer/common';
import { linkek } from '../../lib/vault/linkek.svelte';
import { BeagyazasWidget, linkVerzioValt } from '../beagyazas/widget';
import { wikilinkAdat } from '../linkek/adat';
import { calloutAdat } from '../markdown/callout';
import { kepletForras } from '../markdown/fa';
import { kodRenderelok } from '../renderelok/regiszter';
import { aktiv, aktivBlokkok, type Tartomany } from './aktivBlokk';
import { calloutHajtas, calloutHajtasValt } from './hajtas';
import { jegyzetUtja } from './jegyzet';
import { TablaSzerkesztoWidget } from '../notion/tablazat/szerkeszto';
import { ElvalasztoWidget, KepletElonezetWidget, KepletWidget, RendereloWidget, TablaWidget } from './widgetek';

const TAROLO = new Set(['Document', 'Blockquote', 'BulletList', 'OrderedList', 'ListItem', 'FootnoteDefinition']);
const elrejt = Decoration.replace({ block: true });
const elvalaszto = new ElvalasztoWidget();

function gyermek(n: SyntaxNode, nev: string): SyntaxNode | null {
  for (let c = n.firstChild; c; c = c.nextSibling) if (c.name === nev) return c;
  return null;
}

/** A kódblokk záró kerítésének sora, ha a blokk lezárt (a nyitó után, külön sorban áll). */
export function zaroKerites(state: EditorState, n: SyntaxNode): { from: number; to: number } | null {
  const utolso = n.lastChild;
  const elso = n.firstChild;
  if (!utolso || !elso || utolso === elso || utolso.name !== 'CodeMark') return null;
  const sor = state.doc.lineAt(utolso.from);
  return sor.from > state.doc.lineAt(elso.from).to ? { from: sor.from, to: sor.to } : null;
}

export function blokkDiszitesek(state: EditorState): DecorationSet {
  const aktivak = state.field(aktivBlokkok);
  const hajtas = state.field(calloutHajtas);
  const doc = state.doc;
  const olvas = (a: number, b: number) => doc.sliceString(a, b);
  const sorok = (from: number, to: number): Tartomany => ({ from: doc.lineAt(from).from, to: doc.lineAt(to).to });
  const ki: Range<Decoration>[] = [];

  syntaxTree(state).iterate({
    enter(n) {
      if (TAROLO.has(n.name) && n.name !== 'Blockquote') return true;
      switch (n.name) {
        case 'Blockquote': {
          const a = calloutAdat(n.node, olvas);
          if (!a || !a.hajtas || a.fejVeg >= n.to) return true;
          const kulcs = doc.lineAt(n.from).from;
          const csukva = hajtas.get(kulcs) ?? a.hajtas === '-';
          const torzs = sorok(a.fejVeg + 1, n.to);
          if (!csukva || aktiv(aktivak, torzs.from, torzs.to)) return true;
          ki.push(elrejt.range(torzs.from, torzs.to));
          return false;
        }
        case 'Table': {
          // a vizuális szerkesztő (C09) mindig a táblázat helyén áll; ha a sorok önállóan nem elemezhetők
          // (pl. listaelembe ágyazott táblázat), marad az olvasható widget és az aktív egység forrása
          const s = sorok(n.from, n.to);
          const sz = TablaSzerkesztoWidget.keszit(olvas(s.from, s.to), state.readOnly);
          if (sz) ki.push(Decoration.replace({ widget: sz, block: true }).range(s.from, s.to));
          else if (!aktiv(aktivak, s.from, s.to))
            ki.push(
              Decoration.replace({
                widget: new TablaWidget(olvas(n.from, n.to), n.node, n.from, n.from - s.from),
                block: true,
              }).range(s.from, s.to),
            );
          return false;
        }
        case 'MathBlock': {
          const s = sorok(n.from, n.to);
          const tex = kepletForras(n.node, olvas);
          if (!aktiv(aktivak, s.from, s.to))
            ki.push(Decoration.replace({ widget: new KepletWidget(tex, true, true), block: true }).range(s.from, s.to));
          else if (tex.trim())
            ki.push(Decoration.widget({ widget: new KepletElonezetWidget(tex), block: true, side: 1 }).range(s.to));
          return false;
        }
        case 'DisplayMath': {
          const s = sorok(n.from, n.to);
          if (!aktiv(aktivak, s.from, s.to))
            ki.push(Decoration.replace({ widget: new KepletWidget(kepletForras(n.node, olvas), true) }).range(n.from, n.to));
          return false;
        }
        case 'HorizontalRule': {
          const s = sorok(n.from, n.to);
          if (!aktiv(aktivak, s.from, s.to)) ki.push(Decoration.replace({ widget: elvalaszto, block: true }).range(s.from, s.to));
          return false;
        }
        case 'FencedCode': {
          const s = sorok(n.from, n.to);
          if (aktiv(aktivak, s.from, s.to)) return false;
          const info = gyermek(n.node, 'CodeInfo');
          const r = info ? kodRenderelok.keres(olvas(info.from, info.to)) : undefined;
          if (r) {
            let kod = '';
            for (let c = n.node.firstChild; c; c = c.nextSibling) if (c.name === 'CodeText') kod += olvas(c.from, c.to);
            ki.push(
              Decoration.replace({ widget: new RendereloWidget(r, kod, state.facet(jegyzetUtja)), block: true }).range(s.from, s.to),
            );
            return false;
          }
          const z = zaroKerites(state, n.node);
          if (z) ki.push(elrejt.range(z.from, z.to));
          return false;
        }
        case 'SetextHeading1':
        case 'SetextHeading2': {
          const s = sorok(n.from, n.to);
          const alahuzas = n.node.lastChild;
          if (alahuzas?.name === 'HeaderMark' && !aktiv(aktivak, s.from, s.to)) {
            const sor = doc.lineAt(alahuzas.from);
            if (sor.from > s.from) ki.push(elrejt.range(sor.from, sor.to));
          }
          return false;
        }
        case 'Embed': {
          const forras = state.facet(jegyzetUtja);
          const adat = forras ? wikilinkAdat(n.node, olvas) : null;
          if (!forras || !adat) return false;
          const sor = doc.lineAt(n.from);
          if (aktiv(aktivak, sor.from, doc.lineAt(n.to).to)) return false;
          if (sor.text.trim() === olvas(n.from, n.to))
            ki.push(Decoration.replace({ widget: new BeagyazasWidget(adat, forras, linkek.verzio, true), block: true }).range(sor.from, sor.to));
          else ki.push(Decoration.replace({ widget: new BeagyazasWidget(adat, forras, linkek.verzio, false) }).range(n.from, n.to));
          return false;
        }
        case 'Paragraph':
        case 'Task':
          return true; // a soron belüli `$$` és a beágyazás miatt
        default:
          return false;
      }
    },
  });
  return Decoration.set(ki, true);
}

export const blokkMezo = StateField.define<DecorationSet>({
  create: (s) => blokkDiszitesek(s),
  update(ertek, tr) {
    if (
      tr.docChanged ||
      syntaxTree(tr.startState) !== syntaxTree(tr.state) ||
      // a módváltáskor (Forrás → Live Preview) az előző állapotban még nincs meg a mező
      tr.startState.field(aktivBlokkok, false) !== tr.state.field(aktivBlokkok) ||
      tr.effects.some((e) => e.is(calloutHajtasValt) || e.is(linkVerzioValt))
    )
      return blokkDiszitesek(tr.state);
    return ertek;
  },
  provide: (f) => [
    EditorView.decorations.from(f),
    // a táblázat és az interaktív renderelt blokk (Bases) egyetlen egység: a kurzor nem léphet a rejtett sorai közé
    EditorView.atomicRanges.of((view) =>
      view.state.field(f).update({
        filter: (_a, _b, d) => {
          const w = (d.spec as { widget?: unknown }).widget;
          return w instanceof TablaSzerkesztoWidget || (w instanceof RendereloWidget && w.r.interaktiv === true);
        },
      }),
    ),
  ],
});
