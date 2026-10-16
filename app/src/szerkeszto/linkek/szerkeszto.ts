// A link a szerkesztőben (C10): megnyitás (⌘-kattintás mindkét módban; Live Preview-ban a kirajzolt link sima
// kattintásra is), lebegő előnézet (⌘ + rámutatás) és a parancsok célpontja (a kurzornál álló link).
// A feloldás nem itt történik (L42): a navigáció és az előnézet a core-tól kérdez.

import { syntaxTree } from '@codemirror/language';
import type { EditorState, Extension } from '@codemirror/state';
import { EditorView, ViewPlugin } from '@codemirror/view';
import type { SyntaxNode } from '@lezer/common';
import { aktiv, aktivBlokkok } from '../elo/aktivBlokk';
import { jegyzetUtja } from '../elo/jegyzet';
import { wikilinkAdat, type LinkAdat } from './adat';
import { domCel, elonezetKapcsol, type ElonezetCel } from './elonezet';
import { kulsoCim, kulsoLink } from './kulso';
import { cimkeKeres, linkMegnyit, nyitasMod } from './navigacio';
import { cimkeAt } from './cimkek';
import { markdownCel } from './markdown';

const LINK_NEVEK = new Set(['Wikilink', 'Embed', 'Link']);

/** A `pos`-nál álló wikilink/beágyazás csomópontja (a határokon is). */
export function linkCsomopont(state: EditorState, pos: number): SyntaxNode | null {
  const fa = syntaxTree(state);
  for (const oldal of [1, -1] as const)
    for (let n: SyntaxNode | null = fa.resolveInner(pos, oldal); n; n = n.parent) {
      if (n.name === 'Image') break;
      if (LINK_NEVEK.has(n.name)) return n;
    }
  return null;
}

/** A `pos`-nál álló link adatai, vagy `null`. */
export function linkAt(state: EditorState, pos: number): LinkAdat | null {
  const n = linkCsomopont(state, pos);
  if (!n) return null;
  if (n.name !== 'Link') return wikilinkAdat(n, (a, b) => state.doc.sliceString(a, b));
  const url = n.getChild('URL');
  if (!url) return null;
  const cel = markdownCel(state.doc.sliceString(url.from, url.to));
  if (!cel) return null;
  const nyito = n.firstChild;
  let zaro = nyito?.nextSibling;
  while (zaro && !(zaro.name === 'LinkMark' && state.doc.sliceString(zaro.from, zaro.to) === ']')) zaro = zaro.nextSibling;
  return { ...cel, alias: nyito && zaro ? state.doc.sliceString(nyito.to, zaro.from) : null, beagyazas: false, from: n.from, to: n.to };
}

function egerLink(view: EditorView, e: MouseEvent): LinkAdat | null {
  const cel = e.target as HTMLElement | null;
  if (!cel?.closest('.cm-line')) return null;
  const pos = view.posAtCoords({ x: e.clientX, y: e.clientY });
  return pos === null ? null : linkAt(view.state, pos);
}

/** A `pos`-nál álló külső link (Markdown-link, autolink, csupasz URL) címe és tartománya, vagy `null` (a kép nem link). */
export function kulsoLinkAt(state: EditorState, pos: number): { url: string; from: number; to: number } | null {
  const fa = syntaxTree(state);
  for (const oldal of [1, -1] as const) {
    for (let n: SyntaxNode | null = fa.resolveInner(pos, oldal); n; n = n.parent) {
      if (n.name === 'Image' || n.name === 'Wikilink' || n.name === 'Embed' || n.parent?.name === 'Image') break;
      const tartalmazo = n.name === 'Link' || n.name === 'Autolink';
      if (!tartalmazo && !(n.name === 'URL' && n.parent?.name !== 'Link' && n.parent?.name !== 'Autolink')) continue;
      const u = n.name === 'URL' ? n : n.getChild('URL');
      if (!u) break;
      const url = kulsoCim(state.doc.sliceString(u.from, u.to));
      return url ? { url, from: n.from, to: n.to } : null;
    }
  }
  return null;
}

function elonezetiCel(view: EditorView, l: LinkAdat): ElonezetCel | null {
  const forras = view.state.facet(jegyzetUtja);
  if (!forras) return null;
  return {
    link: l,
    forras,
    rect: () => {
      const a = view.coordsAtPos(l.from);
      const b = view.coordsAtPos(l.to, -1);
      const bal = a?.left ?? 0;
      return new DOMRect(bal, a?.top ?? 0, Math.max(0, (b?.right ?? bal) - bal), (a?.bottom ?? 0) - (a?.top ?? 0));
    },
  };
}

/** A kurzornál álló link előnézeti célja (a parancsnak). */
export function kurzorLinkCel(view: EditorView): ElonezetCel | null {
  const l = linkAt(view.state, view.state.selection.main.head);
  return l ? elonezetiCel(view, l) : null;
}

/** A kurzornál álló link megnyitása (a parancsnak). */
export function kurzorLinkMegnyit(view: EditorView, mod: 'aktiv' | 'ujful' | 'osztas' = 'aktiv'): boolean {
  const l = linkAt(view.state, view.state.selection.main.head);
  const forras = view.state.facet(jegyzetUtja);
  if (!l || !forras) return false;
  void linkMegnyit({ forras, cel: l.cel, alcel: l.alcel }, mod);
  return true;
}

/** Egy sor "kirajzolt-e" a Live Preview-ban (nem az aktív egység): ott a link sima kattintásra is megnyílik. */
function kirajzolt(view: EditorView, l: LinkAdat): boolean {
  if (!view.dom.classList.contains('cm-elonezet')) return false;
  const a = view.state.field(aktivBlokkok, false);
  if (!a) return false;
  const d = view.state.doc;
  return !aktiv(a, d.lineAt(l.from).from, d.lineAt(l.to).to);
}

const elonezetPlugin = ViewPlugin.fromClass(
  class {
    private readonly le: () => void;
    constructor(view: EditorView) {
      this.le = elonezetKapcsol(view.dom, (t, e) => {
        const l = egerLink(view, e);
        return l ? elonezetiCel(view, l) : domCel(t); // a beágyazott tartalomban álló link a DOM-ból
      });
    }
    destroy() {
      this.le();
    }
  },
);

/** Egy tartomány "kirajzolt-e" a Live Preview-ban (egyik sora sem az aktív egység). */
function kirajzoltTartomany(view: EditorView, from: number, to: number): boolean {
  if (!view.dom.classList.contains('cm-elonezet')) return false;
  const a = view.state.field(aktivBlokkok, false);
  if (!a) return false;
  const d = view.state.doc;
  return !aktiv(a, d.lineAt(from).from, d.lineAt(to).to);
}

const kattintas = EditorView.domEventHandlers({
  mousedown(e, view) {
    if (e.button !== 0 && e.button !== 1) return false;
    if (e.button === 0 && e.target instanceof HTMLElement && e.target.closest('.cm-line')) {
      const pos = view.posAtCoords({ x: e.clientX, y: e.clientY });
      const cimke = pos === null ? null : cimkeAt(view.state, pos);
      if (cimke && (e.metaKey || e.ctrlKey || kirajzoltTartomany(view, cimke.from, cimke.to)) && cimkeKeres(cimke.cimke)) {
        e.preventDefault();
        return true;
      }
    }
    const l = egerLink(view, e);
    const forras = view.state.facet(jegyzetUtja);
    if (!l) {
      // külső link: ⌘-kattintás mindig nyit; Live Preview-ban a kirajzolt (nem aktív) soron a sima kattintás is
      const cel = e.target instanceof HTMLElement && e.target.closest('.cm-line') ? view.posAtCoords({ x: e.clientX, y: e.clientY }) : null;
      const k = cel === null ? null : kulsoLinkAt(view.state, cel);
      if (!k || !(e.button === 1 || e.metaKey || e.ctrlKey || kirajzoltTartomany(view, k.from, k.to))) return false;
      e.preventDefault();
      kulsoLink(k.url);
      return true;
    }
    if (!forras) return false;
    const meta = e.metaKey || e.ctrlKey;
    // a beágyazás widget a saját kattintását kezeli; a ⌘-kattintás a forrásmódban és az aktív sorban is nyit
    if (e.button !== 1 && !meta && (l.beagyazas || !kirajzolt(view, l))) return false;
    e.preventDefault();
    void linkMegnyit({ forras, cel: l.cel, alcel: l.alcel }, e.button === 1 ? 'ujful' : nyitasMod(e));
    return true;
  },
});

export function linkBovitmeny(): Extension {
  return [elonezetPlugin, kattintas];
}
