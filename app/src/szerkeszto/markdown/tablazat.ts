// GFM-táblázat, egy eltéréssel: a soron belüli képletben álló `|` nem cellahatár. A vault 28 jegyzetének
// táblázataiban 64 képlet áll abszolút értékkel (`| $|A| = 0$ | … |`); a szigorú GFM ezeket `$`, `A`,
// `= 0$` cellákra vágná, és a sor szétesne. A képlet felismerése a `matek.ts` szabálya (az indexé).
//
// A @lezer/markdown Table-bővítésének másolata (MIT, © Marijn Haverbeke), a sorbontás képlet-tudatos;
// a csomópontnevek ugyanazok (Table, TableHeader, TableRow, TableCell, TableDelimiter).

import type { SyntaxNode } from '@lezer/common';
import type { BlockContext, Element, LeafBlock, LeafBlockParser, Line, MarkdownConfig } from '@lezer/markdown';
import { tags as t } from '@lezer/highlight';
import { kepletVege } from './matek';

const CSO = 124;
const VISSZAPER = 92;
const DOLLAR = 36;

/** Egy sor celláinak száma; ha `elemek` adott, a cellák és a határolók csomópontjai is. */
function sorBont(cx: BlockContext, sor: string, kezd = 0, elemek?: Element[], eltolas = 0): number {
  let db = 0;
  let elso = true;
  let cellaKezd = -1;
  let cellaVeg = -1;
  let esc = false;
  const cella = () => {
    elemek!.push(
      cx.elt(
        'TableCell',
        eltolas + cellaKezd,
        eltolas + cellaVeg,
        cx.parser.parseInline(sor.slice(cellaKezd, cellaVeg), eltolas + cellaKezd),
      ),
    );
  };
  for (let i = kezd; i < sor.length; i++) {
    const c = sor.charCodeAt(i);
    if (c === DOLLAR && !esc) {
      const k = kepletVege(sor, i);
      if (k) {
        if (cellaKezd < 0) cellaKezd = i;
        cellaVeg = k.veg;
        i = k.veg - 1;
        esc = false;
        continue;
      }
    }
    if (c === CSO && !esc) {
      if (!elso || cellaKezd > -1) db++;
      elso = false;
      if (elemek) {
        if (cellaKezd > -1) cella();
        elemek.push(cx.elt('TableDelimiter', i + eltolas, i + eltolas + 1));
      }
      cellaKezd = cellaVeg = -1;
    } else if (esc || (c !== 32 && c !== 9)) {
      if (cellaKezd < 0) cellaKezd = i;
      cellaVeg = i + 1;
    }
    esc = !esc && c === VISSZAPER;
  }
  if (cellaKezd > -1) {
    db++;
    if (elemek) cella();
  }
  return db;
}

function vanCso(s: string, kezd: number): boolean {
  for (let i = kezd; i < s.length; i++) {
    const c = s.charCodeAt(i);
    if (c === CSO) return true;
    if (c === VISSZAPER) i++;
  }
  return false;
}

const HATAROLO_SOR = /^[>\s]*\|?(\s*:?-+:?\s*\|)+(\s*:?-+:?\s*)?$/;

class TablazatElemzo implements LeafBlockParser {
  // null: a második sor még nem jött; false: nem táblázat; tömb: a táblázat eddigi sorai
  private sorok: Element[] | false | null = null;

  nextLine(cx: BlockContext, line: Line, leaf: LeafBlock): boolean {
    if (this.sorok === null) {
      this.sorok = false;
      let szoveg: string;
      if (
        (line.next === 45 || line.next === 58 || line.next === CSO) &&
        HATAROLO_SOR.test((szoveg = line.text.slice(line.pos)))
      ) {
        const elsoSor: Element[] = [];
        const elsoDb = sorBont(cx, leaf.content, 0, elsoSor, leaf.start);
        if (elsoDb === sorBont(cx, szoveg, 0))
          this.sorok = [
            cx.elt('TableHeader', leaf.start, leaf.start + leaf.content.length, elsoSor),
            cx.elt('TableDelimiter', cx.lineStart + line.pos, cx.lineStart + line.text.length),
          ];
      }
    } else if (this.sorok) {
      const tartalom: Element[] = [];
      sorBont(cx, line.text, line.pos, tartalom, cx.lineStart);
      this.sorok.push(cx.elt('TableRow', cx.lineStart + line.pos, cx.lineStart + line.text.length, tartalom));
    }
    return false;
  }

  finish(cx: BlockContext, leaf: LeafBlock): boolean {
    if (!this.sorok) return false;
    cx.addLeafElement(leaf, cx.elt('Table', leaf.start, leaf.start + leaf.content.length, this.sorok));
    return true;
  }
}

export const Tablazat: MarkdownConfig = {
  defineNodes: [
    { name: 'Table', block: true },
    { name: 'TableHeader', style: { 'TableHeader/...': t.heading } },
    'TableRow',
    { name: 'TableCell', style: t.content },
    { name: 'TableDelimiter', style: t.processingInstruction },
  ],
  parseBlock: [
    {
      name: 'Table',
      leaf: (_cx: BlockContext, leaf: LeafBlock) => (vanCso(leaf.content, 0) ? new TablazatElemzo() : null),
      endLeaf(cx: BlockContext, line: Line, leaf: LeafBlock) {
        if (leaf.parsers.some((p) => p instanceof TablazatElemzo) || !vanCso(line.text, line.basePos)) return false;
        const kov = cx.peekLine();
        return HATAROLO_SOR.test(kov) && sorBont(cx, line.text, line.basePos) === sorBont(cx, kov, line.basePos);
      },
      before: 'SetextHeading',
    },
  ],
};

export interface CellaTartomany {
  from: number;
  to: number;
  /** a `TableCell` csomópont; az üres cellának nincs */
  node: SyntaxNode | null;
}

/** Egy sor (`TableHeader` vagy `TableRow`) cellái sorrendben. Az üres cellának nincs `TableCell` csomópontja
 *  (a Lezer nem hoz létre), ezért két elválasztó közti hézag is cella; az első `|` a sor eleji határoló. */
export function sorCellai(sor: SyntaxNode): CellaTartomany[] {
  const ki: CellaTartomany[] = [];
  let nyitott: SyntaxNode | null = null;
  let elso = true;
  let elozoVeg = sor.from;
  for (let x = sor.firstChild; x; x = x.nextSibling) {
    if (x.name === 'TableCell') nyitott = x;
    else if (x.name === 'TableDelimiter') {
      if (nyitott) ki.push({ from: nyitott.from, to: nyitott.to, node: nyitott });
      else if (!elso) ki.push({ from: elozoVeg, to: elozoVeg, node: null });
      elso = false;
      nyitott = null;
      elozoVeg = x.to;
    }
  }
  if (nyitott) ki.push({ from: nyitott.from, to: nyitott.to, node: nyitott });
  return ki;
}
