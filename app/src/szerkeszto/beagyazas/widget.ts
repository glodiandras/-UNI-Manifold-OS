// A beágyazás a Live Preview-ban (C10): CodeMirror-widget a `beagyazas/rajzol.ts` renderelőjével. Egyedül álló
// `![[…]]` sor blokk-widget, sor közepén álló inline (a jegyzet ott csak link-chip). A kattintás a forrásba
// visz (a sor aktív lesz, a jelölés látszik), kivéve a saját vezérlőket (lejátszó, link, gomb). A `linkVerzio`
// a widget azonosságában van: ha a fájlszerkezet változik (új fájl), a függő beágyazás újrafeloldódik.

import { StateEffect } from '@codemirror/state';
import { type EditorView, WidgetType } from '@codemirror/view';
import { domCel } from '../linkek/elonezet';
import { linkMegnyit, nyitasMod } from '../linkek/navigacio';
import type { LinkAdat } from '../linkek/adat';
import { beagyazasElem } from './rajzol';
import { beallitasok } from '../../lib/beallitasok/allapot.svelte';

/** A fájlszerkezet változott: a Live Preview blokkdíszítései újraszámolódnak. */
export const linkVerzioValt = StateEffect.define<number>();

const SAJAT_VEZERLO = 'a, button, video, audio, iframe, input, select, textarea, img.beagyazas-kep, .wikilink[data-cel], .bazis, .kviz, .beagyazas-canvas-kep, .beagyazas-pdf-nezo';

export class BeagyazasWidget extends WidgetType {
  private megszakito: AbortController | null = null;
  private readonly modulok = JSON.stringify(beallitasok.ertek.modulok);

  constructor(
    readonly link: LinkAdat,
    readonly forras: string,
    readonly verzio: number,
    readonly blokk: boolean,
  ) {
    super();
  }

  eq(m: BeagyazasWidget) {
    return (
      m.blokk === this.blokk &&
      m.forras === this.forras &&
      m.verzio === this.verzio &&
      m.modulok === this.modulok &&
      m.link.cel === this.link.cel &&
      m.link.alcel === this.link.alcel &&
      m.link.alias === this.link.alias
    );
  }

  toDOM(view: EditorView) {
    const kont: HTMLElement = document.createElement(this.blokk ? 'div' : 'span');
    kont.className = this.blokk ? 'cm-beagyazas' : 'cm-beagyazas cm-beagyazas-sorban';
    this.megszakito = new AbortController();
    kont.appendChild(
      beagyazasElem(this.link, {
        forras: this.forras,
        sorban: !this.blokk,
        jel: this.megszakito.signal,
        kesz: () => view.requestMeasure(),
      }),
    );
    kont.addEventListener('mousedown', (ev: MouseEvent) => {
      if (ev.button !== 0) return;
      const t = ev.target as HTMLElement;
      const wl = domCel(t);
      if (wl && (ev.metaKey || ev.ctrlKey || !view.state.readOnly)) {
        ev.preventDefault();
        void linkMegnyit({ forras: wl.forras, cel: wl.link.cel, alcel: wl.link.alcel }, nyitasMod(ev));
        return;
      }
      if (t.closest(SAJAT_VEZERLO)) return;
      ev.preventDefault();
      const kezd = view.posAtDOM(kont);
      view.dispatch({ selection: { anchor: Math.min(kezd, view.state.doc.length) }, scrollIntoView: false });
      view.focus();
    });
    return kont;
  }

  destroy() {
    this.megszakito?.abort();
  }

  get estimatedHeight() {
    return this.blokk ? 96 : -1;
  }

  ignoreEvent() {
    return true;
  }
}
