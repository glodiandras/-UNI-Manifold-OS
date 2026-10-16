// A HTML-blokk a Live Preview-ban (01-rendering-11): a nem aktív blokk helyén a szanitizált másolat (ugyanaz a bejáró, mint
// az Olvasóé), a kép a beágyazás-motoron át. Kattintásra a forrás nyílik meg (a sor aktív lesz), kivéve a saját vezérlőket
// (`<summary>`, link). A betöltések élettartama a widget DOM-jához kötött (mint a `BeagyazasWidget`-nél).

import { type EditorView, WidgetType } from '@codemirror/view';
import { beagyazasElem } from '../beagyazas/rajzol';
import { htmlBlokk, nyersHtmlDoboz, vanTartalom } from '../olvaso/htmlSzures';

const megszakitok = new WeakMap<HTMLElement, AbortController>();

export class HtmlBlokkWidget extends WidgetType {
  constructor(
    readonly forras: string,
    readonly ut: string | null,
    readonly verzio: number,
  ) {
    super();
  }

  eq(m: HtmlBlokkWidget) {
    return m.forras === this.forras && m.ut === this.ut && m.verzio === this.verzio;
  }

  toDOM(view: EditorView) {
    const d = document.createElement('div');
    d.className = 'cm-html-blokk html-blokk-render';
    const ac = new AbortController();
    megszakitok.set(d, ac);
    const ut = this.ut;
    const f = htmlBlokk(this.forras, {
      ut,
      kep: ut ? (adat) => beagyazasElem(adat, { forras: ut, sorban: true, jel: ac.signal, kesz: () => view.requestMeasure(), csakOlvashato: view.state.readOnly }) : undefined,
    });
    d.appendChild(f && vanTartalom(f) ? f : nyersHtmlDoboz(this.forras));
    d.addEventListener('mousedown', (ev) => {
      if (ev.button !== 0 || (ev.target as HTMLElement).closest('summary, a, button, .beagyazas')) return;
      ev.preventDefault();
      view.dispatch({ selection: { anchor: Math.min(view.posAtDOM(d), view.state.doc.length) }, scrollIntoView: false });
      view.focus();
    });
    return d;
  }

  destroy(dom: HTMLElement) {
    megszakitok.get(dom)?.abort();
    megszakitok.delete(dom);
  }

  get estimatedHeight() {
    return 48;
  }

  ignoreEvent() {
    return true;
  }
}
