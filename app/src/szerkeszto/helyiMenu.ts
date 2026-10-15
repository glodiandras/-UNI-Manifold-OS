// A jegyzet helyi menüje (C17): jobb klikk (vagy ⇧F10 / a Menü billentyű) a Markdown-jegyzet szerkesztőjében. A natív
// menü helyett saját, hogy a modulok parancsai („Kártyák ebből”, „Kvíz ebből”, „Megoldás”, …) is elérhetők legyenek:
// felül Kivágás / Másolás / Beillesztés, alatta a Manifold-parancsok. A parancsok a regiszterből futnak (ugyanazok,
// mint a ⌘P-ben), így ha egy modul a helyőrzőt a saját azonosítóján valódi parancsra cseréli, a menü követi.
//
// C32b: a valódi appban (a héj hirdeti a `helyiMenu` képességet) a natív menü nyílik (Szó keresése, helyesírás-javaslat,
// Kivágás/Másolás/Beillesztés), a Manifold-parancsok a végére kerülnek: a lap a `contextmenu` közben elküldi a parancslistát
// (`menuElemek` Manifold-csoportja — EGY lista, a saját menüé is), a héj a `willOpenMenu`-ban fűzi hozzá, a választás a
// `window.manifold.parancs(id)` hídon fut. Héj nélkül (böngésző, teszt, régi héj) és a billentyűs megnyitásnál (⇧F10, Menü) a saját menü marad.

import type { Extension } from '@codemirror/state';
import { EditorView, keymap } from '@codemirror/view';
import { hejKepesseg, hejnek } from '../lib/core/hej';
import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
import { regiszter } from '../lib/parancsok/regiszter';
import { JEGYZET_MENU_PARANCSOK } from '../vezerlo/helyorzok';
import { irhato } from './beallitas';
import { jegyzetUtja } from './elo/jegyzet';
import { lebegoMenu, type MenuElem } from './notion/menu';
import { vagolapra } from './vagolap';

/** A menü nyitható-e ebben a szerkesztőben: csak Markdown-jegyzetben (a canvas-kártya és más szerkesztők natív menüt kapnak). */
export function menuNyithato(view: EditorView): boolean {
  return (view.state.facet(jegyzetUtja) ?? '').toLowerCase().endsWith('.md');
}

export function menuElemek(view: EditorView): { elemek: MenuElem[]; akciok: Map<string, () => void> } {
  const elemek: MenuElem[] = [];
  const akciok = new Map<string, () => void>();
  const sel = view.state.selection.main;
  const van = !sel.empty;
  const ir = irhato(view); // csak olvasható jegyzetben a Kivágás és a Beillesztés tiltott (T117)
  const hozzaad = (e: MenuElem, fn: () => void) => {
    elemek.push(e);
    akciok.set(e.id, fn);
  };
  hozzaad({ id: 'kivag', nev: 'Kivágás', jelzo: '⌘X', letiltva: !van || !ir, csoport: 'Szerkesztés' }, () => {
    const s = view.state.selection.main;
    void vagolapra(view.state.sliceDoc(s.from, s.to));
    if (irhato(view)) view.dispatch({ changes: { from: s.from, to: s.to }, userEvent: 'delete.cut' });
  });
  hozzaad({ id: 'masol', nev: 'Másolás', jelzo: '⌘C', letiltva: !van, csoport: 'Szerkesztés' }, () => {
    const s = view.state.selection.main;
    void vagolapra(view.state.sliceDoc(s.from, s.to));
  });
  hozzaad({ id: 'beillesztes', nev: 'Beillesztés', jelzo: '⌘V', letiltva: !ir, csoport: 'Szerkesztés' }, () => {
    navigator.clipboard.readText().then(
      (t) => irhato(view) && view.dispatch(view.state.replaceSelection(t), { userEvent: 'input.paste', scrollIntoView: true }),
      () => ertesitesek.ertesit({ szint: 'info', cim: 'A beillesztéshez használd a ⌘V-t', szoveg: 'A böngészőmotor itt nem engedi a vágólap olvasását.' }),
    );
  });
  for (const id of JEGYZET_MENU_PARANCSOK) {
    const p = regiszter.kap(id);
    if (!p) continue;
    hozzaad({ id: `parancs:${id}`, nev: p.nev, csoport: 'Manifold', letiltva: !regiszter.elerheto(p) }, () => void regiszter.futtat(id, 'menu'));
  }
  return { elemek, akciok };
}

/** A natív menühöz küldendő Manifold-parancsok: ugyanaz a lista, mint a saját menüben (csoport: Manifold), a regiszter-azonosítóval. */
export function nativMenuElemek(view: EditorView): { id: string; nev: string; letiltva: boolean }[] {
  return menuElemek(view)
    .elemek.filter((e) => e.csoport === 'Manifold')
    .map((e) => ({ id: e.id.replace(/^parancs:/, ''), nev: e.nev, letiltva: !!e.letiltva }));
}

function nyit(view: EditorView, x: number, y: number): void {
  const { elemek, akciok } = menuElemek(view);
  lebegoMenu(view, x, y, elemek, akciok, 'Jegyzet menü');
}

export function helyiMenuBovitmeny(): Extension {
  return [
    EditorView.domEventHandlers({
      contextmenu(e, view) {
        if (!menuNyithato(view)) return false;
        if (hejKepesseg('helyiMenu')) {
          hejnek({ tipus: 'helyi-menu', elemek: nativMenuElemek(view) });
          return false; // nincs preventDefault: a WebKit a natív menüt nyitja, a héj a végére fűzi a parancsokat
        }
        e.preventDefault();
        // a kijelölésen kívüli jobb klikk a kurzort oda teszi (mint a natív menünél)
        const pos = view.posAtCoords({ x: e.clientX, y: e.clientY });
        const s = view.state.selection.main;
        if (pos !== null && (pos < s.from || pos > s.to)) view.dispatch({ selection: { anchor: pos } });
        nyit(view, e.clientX, e.clientY);
        return true;
      },
    }),
    keymap.of(
      ['Shift-F10', 'ContextMenu'].map((key) => ({
        key,
        run(view: EditorView) {
          if (!menuNyithato(view)) return false;
          const c = view.coordsAtPos(view.state.selection.main.head);
          const r = view.dom.getBoundingClientRect();
          nyit(view, c ? c.left : r.left + 24, c ? c.bottom + 4 : r.top + 24);
          return true;
        },
      })),
    ),
  ];
}
