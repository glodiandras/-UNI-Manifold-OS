// A valódi KaTeX-képlethiba jelzése (C30b-mag; CHATKALAUZ C30b 3. pont). A core `higienia.py` próbája (`kepletproba`)
// csak szerkezeti (zárójelpár, `\begin`/`\end`); a szerkesztő renderelője a valódi hibát tudja. Itt a nyitott
// dokumentum képleteit a **valódi renderelővel** (`katexEllenoriz`, ugyanaz az előkészítés és beállítás, mint a
// rajzolásnál) ellenőrizzük, és a hibásakat a jobb panel Higiénia-szakaszába kliens-tételként adjuk. Az index sémája és a
// core riportja változatlan: ezek a tételek a riportba, a statisztikába nem kerülnek.
//
// Nem a gépelés útvonalán fut: a hívó (a panel) csendes idő után, a szerkesztő már kiszámolt szintaxisfájából dolgozik, a
// képleteket időkeretben, a főszál-megosztással ellenőrzi, és a képlet-szövegekre gyorsítótára van.

import type { Text } from '@codemirror/state';
import type { Tree } from '@lezer/common';
import { katexEllenoriz } from '../renderelok/katex';

export interface Kepletforras {
  tex: string;
  display: boolean;
  /** 1-től */
  sor: number;
}

/** A szintaxisfa képletei (`$…$`, `$$…$$` soron belül és blokkban). */
export function kepletekKiszed(fa: Tree, doc: Text): Kepletforras[] {
  const ki: Kepletforras[] = [];
  fa.iterate({
    enter(n) {
      if (n.name === 'InlineMath' || n.name === 'DisplayMath') {
        const jelek: { from: number; to: number }[] = [];
        for (let c = n.node.firstChild; c; c = c.nextSibling) if (c.name === 'MathMark') jelek.push({ from: c.from, to: c.to });
        if (jelek.length < 2) return false;
        const tex = doc.sliceString(jelek[0].to, jelek[jelek.length - 1].from);
        if (tex.trim()) ki.push({ tex, display: n.name === 'DisplayMath', sor: doc.lineAt(n.from).number });
        return false;
      }
      if (n.name === 'MathBlock') {
        const reszek: string[] = [];
        for (let c = n.node.firstChild; c; c = c.nextSibling) if (c.name === 'MathText') reszek.push(doc.sliceString(c.from, c.to));
        const tex = reszek.join('\n');
        if (tex.trim()) ki.push({ tex, display: true, sor: doc.lineAt(n.from).number });
        return false;
      }
      return undefined;
    },
  });
  return ki;
}

const TAR_MERET = 4000;
const tar = new Map<string, string | null>();

/** A képlet valódi KaTeX-hibája (a `ParseError` üzenete), vagy `null`, ha rendben van. Gyorsítótárazva. */
export function kepletHiba(tex: string, display: boolean): string | null {
  const kulcs = (display ? 'D' : 'I') + tex;
  if (tar.has(kulcs)) {
    const mar = tar.get(kulcs)!;
    tar.delete(kulcs);
    tar.set(kulcs, mar);
    return mar;
  }
  let hiba: string | null = null;
  try {
    katexEllenoriz(tex, display);
  } catch (e) {
    hiba = (e instanceof Error ? e.message : String(e)).replace(/^KaTeX parse error:\s*/, '').replace(/\s+/g, ' ').slice(0, 160);
  }
  tar.set(kulcs, hiba);
  if (tar.size > TAR_MERET) tar.delete(tar.keys().next().value as string);
  return hiba;
}

export interface KepletHiba {
  sor: number;
  uzenet: string;
}

export interface EllenorzesOpciok {
  /** egy szelet legfeljebb ennyi ideig (ms) tart, utána a hívó átadja a vezérlést */
  szeletMs?: number;
  /** a szelet végén hívva: igaz → megszakítva, nincs eredmény */
  megszakit?: () => boolean;
  /** a szelet végén hívva (a főszál visszaadása); alapból egy `setTimeout(0)` */
  atad?: () => Promise<void>;
}

/** Az összes képlet ellenőrzése időkeretes szeletekben; a hibásak sor szerint. Megszakítva `null`. */
export async function kepletekEllenoriz(lista: readonly Kepletforras[], o: EllenorzesOpciok = {}): Promise<KepletHiba[] | null> {
  const szeletMs = o.szeletMs ?? 12;
  const atad = o.atad ?? (() => new Promise<void>((ok) => setTimeout(ok, 0)));
  const ki: KepletHiba[] = [];
  let szeletKezd = performance.now();
  for (const k of lista) {
    const hiba = kepletHiba(k.tex, k.display);
    if (hiba) ki.push({ sor: k.sor, uzenet: hiba });
    if (performance.now() - szeletKezd >= szeletMs) {
      await atad();
      if (o.megszakit?.()) return null;
      szeletKezd = performance.now();
    }
  }
  return ki;
}

/** A gyorsítótár ürítése (teszt). */
export function kepletTarUrit(): void {
  tar.clear();
}
