// A link adatai a szintaxisfából és a média-horgonyok értelmezése (C10). Csak szövegfeldolgozás: a feloldás a
// core-é (L42).

import type { SyntaxNode } from '@lezer/common';
import type { Olvaso } from '../markdown/fa';
import { markdownCel } from './markdown';

export interface LinkAdat {
  /** a nyers cél (a `[[` utáni szöveg a `#`/`|` előtt); üres: az aktuális jegyzet (`[[#Fejezet]]`) */
  cel: string;
  /** a `#` utáni rész (fejezet, `^blokk`, `page=3`, `t=12`) a `#` nélkül */
  alcel: string | null;
  alias: string | null;
  beagyazas: boolean;
  from: number;
  to: number;
  /** Markdown-képnél külön alt-szöveg: a méretalias ettől független. */
  alt?: string;
  /** Külső kép: sosem indul automatikus hálózati kérés. */
  kulso?: boolean;
}

/** Markdown-kép: a szöveg és méret helyi értelmezés, a fájl feloldása továbbra is a core-é. */
export function kepAdat(n: SyntaxNode, olvas: Olvaso): LinkAdat | null {
  if (n.name !== 'Image') return null;
  const url = gyermek(n, 'URL');
  if (!url) return null;
  let nyito: SyntaxNode | null = null;
  let zaro: SyntaxNode | null = null;
  for (let c = n.firstChild; c; c = c.nextSibling) {
    if (c.name !== 'LinkMark') continue;
    const jel = olvas(c.from, c.to);
    if (jel === '![') nyito = c;
    else if (nyito && jel === ']') { zaro = c; break; }
  }
  const felirat = nyito && zaro ? olvas(nyito.to, zaro.from) : '';
  const meret = /\|\s*(\d+(?:\s*x\s*\d+)?)\s*$/i.exec(felirat);
  const nyers = olvas(url.from, url.to);
  const cim = markdownCel(nyers);
  return {
    cel: cim?.cel ?? nyers.replace(/^<|>$/g, ''),
    alcel: cim?.alcel ?? null,
    alias: meret ? meret[1] : null,
    alt: meret ? felirat.slice(0, meret.index) : felirat,
    kulso: !cim,
    beagyazas: true,
    from: n.from,
    to: n.to,
  };
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
export function mediaHorgony(alcel: string | null | undefined): { t?: number; page?: number; height?: number } {
  if (!alcel) return {};
  const ki: { t?: number; page?: number; height?: number } = {};
  for (const resz of alcel.trim().split('&')) {
    const t = /^t=(\d+(?::\d+){0,2})(?:[,-].*)?$/i.exec(resz);
    if (t) {
      const szamok = t[1].split(':').map(Number);
      const mp = szamok.reduce((a, x) => a * 60 + x, 0);
      if (Number.isSafeInteger(mp)) ki.t = mp;
    }
    const p = /^(page|height)=(\d+)$/i.exec(resz);
    if (p && Number.isSafeInteger(Number(p[2])) && Number(p[2]) >= 1)
      ki[p[1].toLowerCase() as 'page' | 'height'] = Number(p[2]);
  }
  return ki;
}

export interface LinkSzovegOpciok {
  /** a megjelenítendő szöveg (`[[cel|alias]]`, `[alias](…)`) */
  alias?: string | null;
  /** a horgony a `#` nélkül (`Fejezet`, `^id`) */
  alcel?: string | null;
  beagyazas?: boolean;
  /** a cél neve (jegyzetnél kiterjesztés nélkül): az md-link alapértelmezett felirata */
  nev: string;
}

/** A beírandó link szövege a beállítások szerint (02-links-12/13): `[[cél#alcél|alias]]`, vagy a „Use [[Wikilinks]]” kikapcsolva
 *  `[felirat](kódolt-cél.md#alcél)` — a cél és a kódolás a core `linkcel`-éből jön (`forma`), a felület csak összeilleszt. */
export function linkSzoveg(forma: { cel: string; alak: 'wiki' | 'md'; md: string }, o: LinkSzovegOpciok): string {
  const elo = o.beagyazas ? '!' : '';
  const alcel = o.alcel?.trim() || '';
  if (forma.alak !== 'md' || !forma.md) return `${elo}[[${forma.cel}${alcel ? `#${alcel}` : ''}${o.alias ? `|${o.alias}` : ''}]]`;
  const felirat = (o.alias || `${o.nev}${alcel ? `#${alcel}` : ''}`).replace(/[[\]]/g, ' ').replace(/\s+/g, ' ').trim();
  return `${elo}[${felirat}](${forma.md})`;
}
