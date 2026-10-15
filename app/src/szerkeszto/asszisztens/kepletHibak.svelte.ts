// A nyitott jegyzet valódi KaTeX-hibái a jobb panel Higiénia-szakaszának (C30b-mag). A számítás csendes idő után fut
// (a hívó időzíti), a szerkesztő meglévő szintaxisfájából, időkeretes szeletekben: a gépelés útvonalán nincs dolga.

import { syntaxTree } from '@codemirror/language';
import type { Text } from '@codemirror/state';
import type { Tree } from '@lezer/common';
import type { HigieniaTetel } from '../../lib/asszisztens/tipusok';
import { obsidianElemzo } from '../markdown/elemzo';
import { szerkesztok } from '../szerkesztok.svelte';
import { kepletekEllenoriz, kepletekKiszed } from './keplet';

/** A kliens-tételek azonosító-előtagja: a core riportjában és a statisztikában nincs ilyen. */
export const KLIENS_ELOTAG = 'kliens-keplet:';

/** A core tételei a kliens KaTeX-tételeivel: azonos sorú, core-beli `hibas_keplet` helyére a valódi KaTeX-üzenet kerül. */
export function osszevon(core: readonly HigieniaTetel[], kliens: readonly HigieniaTetel[]): HigieniaTetel[] {
  if (!kliens.length) return [...core];
  const sorok = new Set(kliens.map((t) => t.sor));
  return [...core.filter((t) => !(t.fajta === 'hibas_keplet' && t.sor !== null && sorok.has(t.sor))), ...kliens].sort(
    (a, b) => (a.sor ?? Infinity) - (b.sor ?? Infinity),
  );
}

export class KatexHibak {
  tetelek = $state.raw<HigieniaTetel[]>([]);
  private sorszam = 0;

  /** A `ut` jegyzet képletei a nyitott dokumentumból (mentetlen szövegből is). */
  async frissit(ut: string | null): Promise<void> {
    const en = ++this.sorszam;
    if (!ut || !ut.toLowerCase().endsWith('.md')) {
      this.tetelek = [];
      return;
    }
    const forras = this.forras(ut);
    if (!forras) {
      this.tetelek = [];
      return;
    }
    const lista = kepletekKiszed(forras.fa, forras.doc);
    const hibak = await kepletekEllenoriz(lista, { megszakit: () => en !== this.sorszam });
    if (!hibak || en !== this.sorszam) return;
    this.tetelek = hibak.map((h, i) => ({
      azonosito: `${KLIENS_ELOTAG}${ut}:${h.sor}:${i}`,
      fajta: 'hibas_keplet',
      szint: 'hiba',
      ut,
      sor: h.sor,
      uzenet: `A KaTeX nem tudja megjeleníteni: ${h.uzenet}`,
    }));
  }

  private forras(ut: string): { fa: Tree; doc: Text } | null {
    const p = szerkesztok.aktiv;
    const v = p && p.ut === ut ? p.nezet() : null;
    if (v) return { fa: syntaxTree(v.state), doc: v.state.doc }; // a szerkesztő már elemzett fája (nincs újraelemzés)
    const d = szerkesztok.dokumentumok.kap(ut);
    if (!d) return null;
    const doc = d.szoveg;
    return { fa: obsidianElemzo.parse(doc.toString()), doc };
  }

  torol(): void {
    this.sorszam++;
    this.tetelek = [];
  }
}
