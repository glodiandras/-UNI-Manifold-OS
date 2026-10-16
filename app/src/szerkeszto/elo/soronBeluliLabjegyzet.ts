// A soron belüli lábjegyzet (`^[…]`, 01-rendering-10) a Live Preview-ban: a nem aktív sorban felső indexű sorszám (az Olvasó
// számozásával azonos: a `[^címke]` hivatkozások és a soron belüliek közös, első előfordulás szerinti sorrendje); a törzs
// a súgóban és az akadálymentes címkében olvasható. Az aktív sorban a forrás látszik.

import { syntaxTree } from '@codemirror/language';
import type { EditorState } from '@codemirror/state';
import { WidgetType } from '@codemirror/view';
import { t } from '../../lib/i18n';

/** A soron belüli lábjegyzetek sorszáma (kezdőpozíció → szám) a teljes dokumentum hivatkozási sorrendjében. */
export function soronBeluliSzamok(state: EditorState): Map<number, number> {
  const cimkek = new Map<string, number>();
  const ki = new Map<number, number>();
  syntaxTree(state).iterate({
    enter(n) {
      if (n.name === 'FootnoteReference') {
        const c = n.node.getChild('FootnoteLabel');
        const nev = c ? state.sliceDoc(c.from, c.to) : '';
        if (!cimkek.has(nev)) cimkek.set(nev, cimkek.size + ki.size + 1);
        return false;
      }
      if (n.name === 'FootnoteInline') {
        ki.set(n.from, cimkek.size + ki.size + 1);
        return false;
      }
      return n.name !== 'FootnoteDefinition';
    },
  });
  return ki;
}

export class SoronBeluliLabjegyzetWidget extends WidgetType {
  constructor(
    readonly szam: number,
    readonly szoveg: string,
  ) {
    super();
  }

  eq(m: SoronBeluliLabjegyzetWidget) {
    return m.szam === this.szam && m.szoveg === this.szoveg;
  }

  toDOM() {
    const e = document.createElement('sup');
    e.className = 'cm-labjegyzet-widget cm-labjegyzet-soron';
    e.textContent = String(this.szam);
    const rovid = this.szoveg.length > 300 ? `${this.szoveg.slice(0, 300)}…` : this.szoveg;
    e.title = rovid;
    e.setAttribute('aria-label', t('{n}. lábjegyzet: {szoveg}', { n: this.szam, szoveg: rovid }));
    return e;
  }

  ignoreEvent() {
    return false;
  }
}
