// A link adatai a szintaxisfából és a média-horgonyok értelmezése (C10). Csak szövegfeldolgozás: a feloldás a
// core-é (L42).

import type { SyntaxNode } from '@lezer/common';
import type { Olvaso } from '../markdown/fa';

export interface LinkAdat {
  /** a nyers cél (a `[[` utáni szöveg a `#`/`|` előtt); üres: az aktuális jegyzet (`[[#Fejezet]]`) */
  cel: string;
  /** a `#` utáni rész (fejezet, `^blokk`, `page=3`, `t=12`) a `#` nélkül */
  alcel: string | null;
  alias: string | null;
  beagyazas: boolean;
  from: number;
  to: number;
}

function gyermek(n: SyntaxNode, nev: string): SyntaxNode | null {
  for (let c = n.firstChild; c; c = c.nextSibling) if (c.name === nev) return c;
  return null;
}

/** Egy `Wikilink` vagy `Embed` csomópont adatai. */
export function wikilinkAdat(n: SyntaxNode, olvas: Olvaso): LinkAdat | null {
  if (n.name !== 'Wikilink' && n.name !== 'Embed') return null;
  const cel = gyermek(n, 'WikilinkTarget');
  const al = gyermek(n, 'WikilinkSubpath');
  const alias = gyermek(n, 'WikilinkAlias');
  const alcel = al ? olvas(al.from + 1, al.to).trim() : '';
  return {
    cel: cel ? olvas(cel.from, cel.to).trim() : '',
    alcel: alcel || null,
    alias: alias ? olvas(alias.from, alias.to) : null,
    beagyazas: n.name === 'Embed',
    from: n.from,
    to: n.to,
  };
}

/** A link szöveges alakja, ahogy a felületen látszik: az alias, különben a cél (és ` › alcél`). */
export function linkFelirat(a: LinkAdat): string {
  if (a.alias) return a.alias;
  return (a.cel || '') + (a.alcel ? (a.cel ? ' › ' : '') + a.alcel : '');
}

export interface Meret {
  szelesseg?: number;
  magassag?: number;
}

/** A beágyazás aliasa méretként: `300` vagy `300x200` (egyébként alt-szöveg). */
export function meretAliasbol(alias: string | null): Meret | null {
  const m = alias ? /^\s*(\d+)(?:\s*x\s*(\d+))?\s*$/i.exec(alias) : null;
  if (!m) return null;
  return { szelesseg: Number(m[1]), magassag: m[2] ? Number(m[2]) : undefined };
}

/** A média-horgony: `t=243`, `t=12:40`, `t=1:02:03` másodpercben; `page=N`. Máskülönben `{}`. */
export function mediaHorgony(alcel: string | null | undefined): { t?: number; page?: number } {
  if (!alcel) return {};
  const t = /^t=(\d+(?::\d+){0,2})(?:[,-].*)?$/i.exec(alcel.trim());
  if (t) {
    const resz = t[1].split(':').map(Number);
    return { t: resz.reduce((a, x) => a * 60 + x, 0) };
  }
  const p = /^page=(\d+)/i.exec(alcel.trim());
  if (p && Number(p[1]) >= 1) return { page: Number(p[1]) };
  return {};
}
