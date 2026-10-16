// Az Olvasó: a szintaxisfából DOM (a szerkesztővel azonos elemzőből). A Markdown soha nem kerül
// `innerHTML`-be; kivétel a KaTeX kimenete (`trust: false`) és a Mermaid SVG-je (`securityLevel: 'strict'`).
// Obsidian-szemantika: a sima sortörés `<br>` (a „szigorú sortörés” alapból ki), a lábjegyzetek a lap
// alján, a callout összecsukható, a jelölőnégyzet kattintható (a dokumentumot írja). HTML csak az
// engedélyezett soron belüli címkékkel; a többi szövegként látszik. A wikilink `data-cel`/`data-alcel`/`data-forras`
// attribútumot kap (a navigációt és a lebegő előnézetet az Olvasó és a szerkesztő kezeli, C10); a beágyazás
// (`![[…]]`) a `beagyazas/rajzol.ts`-ben készül. A Live Preview táblázat-widgetje is ezt a renderelőt használja.

import { t } from '../../lib/i18n';
import type { SyntaxNode, Tree } from '@lezer/common';
import { ikonElem } from '../../lib/ikon/ikonElem';
import { Check, ChevronRight, Copy } from '../../lib/ikon/ikonok';
import { beagyazasElem } from '../beagyazas/rajzol';
import type { LancElem } from '../beagyazas/regiszter';
import { kepAdat, linkFelirat, wikilinkAdat } from '../linkek/adat';
import { markdownCel } from '../linkek/markdown';
import { kulsoCim } from '../linkek/kulso';
import { calloutAdat } from '../markdown/callout';
import { kepletForras, type Olvaso } from '../markdown/fa';
import { engedettCimke } from '../markdown/html';
import { feladatAllapot } from '../markdown/feladat';
import { sorCellai } from '../markdown/tablazat';
import { calloutTipusok } from '../renderelok/callout';
import { katexHtml } from '../renderelok/katex';
import { kodSzinez } from '../renderelok/kodszin';
import { kodRenderelok, renderel } from '../renderelok/regiszter';
import { sotetTema } from '../renderelok/tema';
import { vagolapra } from '../vagolap';
import type { LustaRajzolo } from './lusta';

export interface RenderOpciok {
  olvas: Olvaso;
  ut: string | null;
  lusta: LustaRajzolo;
  /** a nézet egyedi előtagja (a lábjegyzetek azonosítóihoz) */
  elotag?: string;
  /** a lábjegyzet-hivatkozások sorszáma, az első előfordulás sorrendjében (a renderelés tölti) */
  labjegyzetSzam?: Map<string, number>;
  /** a dokumentumban talált lábjegyzet-definíciók (a renderelés tölti) */
  labjegyzetek?: Map<string, SyntaxNode>;
  /** beágyazott tartalomban: a beágyazás-lánc és a mélység (a körkörös beágyazás védelme) */
  beagyazas?: { lanc: LancElem[]; melyseg: number; kesz?: () => void };
  csakOlvashato?: boolean;
}

const JELOLOK = new Set([
  'EmphasisMark',
  'CodeMark',
  'LinkMark',
  'StrikethroughMark',
  'HighlightMark',
  'QuoteMark',
  'HeaderMark',
  'ListMark',
  'TaskMarker',
  'FootnoteMark',
  'FootnoteLabel',
  'MathMark',
  'TableDelimiter',
  'Comment',
  'ProcessingInstruction',
  'LinkReference',
  'WikilinkMark',
]);

function el<K extends keyof HTMLElementTagNameMap>(tag: K, osztaly?: string): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  if (osztaly) e.className = osztaly;
  return e;
}

// ---------------------------------------------------------------------- soron belüli tartalom

/** Soron belüli író: a sortörés `<br>` (a folytatósor behúzása elmarad), az engedélyezett HTML-címkék
 *  egymásba ágyazódnak. */
class SorIro {
  private readonly verem: Element[] = [];
  sorKezdet: boolean;

  constructor(
    readonly cel: Element,
    sorKezdet = true,
  ) {
    this.sorKezdet = sorKezdet;
  }

  get aktualis(): Element {
    return this.verem[this.verem.length - 1] ?? this.cel;
  }

  szoveg(s: string): void {
    const reszek = s.split('\n');
    for (let i = 0; i < reszek.length; i++) {
      let r = reszek[i];
      if (i > 0) {
        this.aktualis.appendChild(el('br'));
        this.sorKezdet = true;
      }
      if (i < reszek.length - 1) r = r.replace(/[ \t]+$/, '');
      if (this.sorKezdet) {
        r = r.replace(/^[ \t]+/, '');
        if (r) this.sorKezdet = false;
      }
      if (r) this.aktualis.appendChild(document.createTextNode(r));
    }
  }

  elem(e: Node): void {
    this.aktualis.appendChild(e);
    this.sorKezdet = false;
  }

  belep(e: Element): void {
    this.elem(e);
    this.verem.push(e);
  }

  kilep(e: Element): void {
    const i = this.verem.lastIndexOf(e);
    if (i >= 0) this.verem.length = i;
  }

  html(cimke: string): void {
    const c = engedettCimke(cimke);
    if (!c) {
      this.szoveg(cimke);
      return;
    }
    const nev = c.nev;
    if (nev === 'br') {
      this.elem(el('br'));
      this.sorKezdet = true;
      return;
    }
    if (c.zaro) {
      for (let i = this.verem.length - 1; i >= 0; i--)
        if (this.verem[i].tagName.toLowerCase() === nev) {
          this.verem.length = i;
          return;
        }
      return;
    }
    if (!c.onzaro) this.belep(document.createElement(nev));
  }

  /** A blokk végi szóközök levágása. */
  zar(): void {
    const u = this.cel.lastChild;
    if (u?.nodeType === Node.TEXT_NODE) {
      u.textContent = (u.textContent ?? '').replace(/[ \t]+$/, '');
      if (!u.textContent) u.remove();
    }
  }
}

function gyermek(n: SyntaxNode, nev: string): SyntaxNode | null {
  for (let c = n.firstChild; c; c = c.nextSibling) if (c.name === nev) return c;
  return null;
}

function sorban(n: SyntaxNode, from: number, to: number, o: RenderOpciok, w: SorIro): void {
  let pos = from;
  for (let c = n.firstChild; c; c = c.nextSibling) {
    if (c.to <= from) continue;
    if (c.from >= to) break;
    if (c.from > pos) w.szoveg(o.olvas(pos, c.from));
    sorbanElem(c, o, w);
    pos = Math.max(pos, c.to);
  }
  if (pos < to) w.szoveg(o.olvas(pos, to));
}

function burkol(e: HTMLElement, c: SyntaxNode, o: RenderOpciok, w: SorIro, from = c.from, to = c.to): void {
  w.belep(e);
  sorban(c, from, to, o, w);
  w.kilep(e);
}

function kepletElem(c: SyntaxNode, o: RenderOpciok, display: boolean, blokkos = false): HTMLElement {
  const tex = kepletForras(c, o.olvas);
  const e = el(blokkos ? 'div' : 'span', blokkos ? 'keplet-blokk' : display ? 'keplet keplet-display' : 'keplet');
  e.textContent = tex;
  o.lusta.ker(e, () => {
    e.innerHTML = katexHtml(tex, display);
  });
  return e;
}

/** A megnyitható külső link jelölése: `data-url` (az Olvasó kattintáskezelője ezt keresi), `role` és fókusz. `href` nincs:
 *  a WebView-ban egy `<a href>` kattintása navigálna. A nem megnyitható (relatív, tiltott séma) link csak szöveg marad. */
function kulsoJeloles(a: HTMLElement, url: string): void {
  const cim = kulsoCim(url);
  if (!cim) return;
  a.dataset.url = cim;
  a.setAttribute('role', 'link');
  a.tabIndex = 0;
}

function linkSzoveg(c: SyntaxNode, o: RenderOpciok): { from: number; to: number; cim: string } {
  let nyito: SyntaxNode | null = null;
  let zaro: SyntaxNode | null = null;
  for (let m = c.firstChild; m; m = m.nextSibling) {
    if (m.name !== 'LinkMark') continue;
    const t = o.olvas(m.from, m.to);
    if (!nyito && (t === '[' || t === '![')) nyito = m;
    else if (nyito && !zaro && t === ']') zaro = m;
  }
  const url = gyermek(c, 'URL');
  return {
    from: nyito ? nyito.to : c.from,
    to: zaro ? zaro.from : c.to,
    cim: url ? o.olvas(url.from, url.to) : '',
  };
}

function sorbanElem(c: SyntaxNode, o: RenderOpciok, w: SorIro): void {
  switch (c.name) {
    case 'ObsidianComment':
    case 'ObsidianCommentBlock':
      return;
    case 'Emphasis':
      return burkol(el('em'), c, o, w);
    case 'StrongEmphasis':
      return burkol(el('strong'), c, o, w);
    case 'Strikethrough':
      return burkol(el('del'), c, o, w);
    case 'Highlight':
      return burkol(el('mark', 'jeloles'), c, o, w);
    case 'InlineCode': {
      const elso = c.firstChild;
      const utolso = c.lastChild;
      const kod = el('code');
      kod.textContent = o.olvas(elso ? elso.to : c.from, utolso && utolso !== elso ? utolso.from : c.to).replace(/\n/g, ' ');
      return w.elem(kod);
    }
    case 'InlineMath':
      return w.elem(kepletElem(c, o, false));
    case 'DisplayMath':
      return w.elem(kepletElem(c, o, true));
    case 'Link': {
      const l = linkSzoveg(c, o);
      const a = el('a', 'link');
      if (l.cim) {
        a.title = l.cim;
        const helyi = markdownCel(l.cim);
        if (helyi && o.ut) {
          a.classList.add('wikilink');
          a.dataset.cel = helyi.cel;
          if (helyi.alcel) a.dataset.alcel = helyi.alcel;
          a.dataset.forras = o.ut;
          a.setAttribute('role', 'link');
          a.tabIndex = 0;
        } else kulsoJeloles(a, l.cim);
      }
      return burkol(a, c, o, w, l.from, l.to);
    }
    case 'Image': {
      return beagyazas(c, o, w);
    }
    case 'Autolink': {
      const url = gyermek(c, 'URL');
      const a = el('a', 'link');
      a.textContent = url ? o.olvas(url.from, url.to) : o.olvas(c.from, c.to);
      a.title = a.textContent;
      kulsoJeloles(a, a.textContent);
      return w.elem(a);
    }
    case 'URL': {
      const a = el('a', 'link');
      a.textContent = o.olvas(c.from, c.to);
      a.title = a.textContent;
      kulsoJeloles(a, a.textContent);
      return w.elem(a);
    }
    case 'Wikilink': {
      const a = wikilinkAdat(c, o.olvas);
      const s = el('span', 'wikilink');
      s.textContent = a ? linkFelirat(a) : o.olvas(c.from, c.to);
      s.title = o.olvas(c.from, c.to);
      if (a && o.ut) {
        s.dataset.cel = a.cel;
        if (a.alcel) s.dataset.alcel = a.alcel;
        s.dataset.forras = o.ut;
        s.setAttribute('role', 'link');
        s.tabIndex = 0;
      }
      return w.elem(s);
    }
    case 'Embed':
      return beagyazas(c, o, w);
    case 'FootnoteReference': {
      const cimke = gyermek(c, 'FootnoteLabel');
      const nev = cimke ? o.olvas(cimke.from, cimke.to) : '';
      const szamok = (o.labjegyzetSzam ??= new Map());
      let n = szamok.get(nev);
      if (n === undefined) szamok.set(nev, (n = szamok.size + 1));
      const sup = el('sup', 'labjegyzet-hiv');
      const a = el('a');
      a.dataset.labjegyzet = nev;
      a.id = `${o.elotag ?? 'lj'}-hiv-${nev}`;
      a.textContent = String(n);
      a.setAttribute('role', 'link');
      a.tabIndex = 0;
      a.setAttribute('aria-label', t('{n}. lábjegyzet', { n }));
      sup.appendChild(a);
      return w.elem(sup);
    }
    case 'Escape':
      return w.szoveg(o.olvas(c.from + 1, c.to));
    case 'Entity':
      return w.szoveg(entitas(o.olvas(c.from, c.to)));
    case 'HTMLTag':
      return w.html(o.olvas(c.from, c.to));
    case 'HardBreak':
      w.elem(el('br'));
      w.sorKezdet = true;
      return;
    default:
      if (JELOLOK.has(c.name)) return;
      w.szoveg(o.olvas(c.from, c.to));
  }
}

function beagyazas(c: SyntaxNode, o: RenderOpciok, w: SorIro): void {
  const a = c.name === 'Image' ? kepAdat(c, o.olvas) : wikilinkAdat(c, o.olvas);
  if (!a || !o.ut) {
    const s = el('span', 'beagyazas-nyers');
    s.textContent = o.olvas(c.from, c.to);
    return w.elem(s);
  }
  w.elem(beagyazasElem(a, {
    forras: o.ut,
    lanc: o.beagyazas?.lanc ?? [{ ut: o.ut, alcel: null }],
    melyseg: o.beagyazas?.melyseg ?? 0,
    jel: o.lusta.jel,
    kesz: o.beagyazas?.kesz,
    csakOlvashato: o.csakOlvashato,
  }));
}

function entitas(s: string): string {
  const d = new DOMParser().parseFromString(`<!doctype html><body>${s}`, 'text/html');
  return d.body.textContent ?? s;
}

// ---------------------------------------------------------------------- blokkok

const BLOKK_ID_VEGE = /(?:^|[ \t\n])\^[A-Za-z0-9-]+[ \t]*$/;

/** A blokkazonosító (`^id`) a bekezdés végén: az Olvasó nem mutatja (az Obsidian sem), a forrásban marad.
 *  Visszaadja a tartalom új végét; `null`, ha a bekezdés csak az azonosító (önálló sor a blokk után). */
function azonositoNelkul(o: RenderOpciok, from: number, to: number): number | null {
  const m = BLOKK_ID_VEGE.exec(o.olvas(from, to));
  if (!m) return to;
  const veg = from + m.index;
  return o.olvas(from, veg).trim() === '' ? null : veg;
}

function bekezdes(n: SyntaxNode, o: RenderOpciok, cel: Node, from = n.from, to = n.to): void {
  const veg = azonositoNelkul(o, from, to);
  if (veg === null) return;
  const p = el('p');
  const w = new SorIro(p);
  sorban(n, from, veg, o, w);
  w.zar();
  cel.appendChild(p);
}

function cimsor(n: SyntaxNode, szint: number, o: RenderOpciok, cel: Node): void {
  const h = el(`h${szint}` as 'h1');
  const w = new SorIro(h);
  // a setext-cím aláhúzása (az utolsó HeaderMark) nem tartalom
  const alahuzas = n.name.startsWith('SetextHeading') ? n.lastChild : null;
  let veg = alahuzas?.name === 'HeaderMark' ? alahuzas.from : n.to;
  while (veg > n.from && /\s/.test(o.olvas(veg - 1, veg))) veg--; // az aláhúzás előtti sortörés nem tartalom
  sorban(n, n.from, veg, o, w);
  w.zar();
  cel.appendChild(h);
}

/** A táblázat (a Live Preview widgetje is ezt használja). A cellák `data-from`-ja a forrásbeli helyük. */
export function tablaRenderel(n: SyntaxNode, o: RenderOpciok): HTMLTableElement {
  const t = el('table');
  let igazitas: string[] = [];
  for (let c = n.firstChild; c; c = c.nextSibling)
    if (c.name === 'TableDelimiter') {
      igazitas = o
        .olvas(c.from, c.to)
        .replace(/^[\s>]*\|?|\|?\s*$/g, '')
        .split('|')
        .map((x) => {
          const s = x.trim();
          return s.startsWith(':') && s.endsWith(':') ? 'center' : s.endsWith(':') ? 'right' : s.startsWith(':') ? 'left' : '';
        });
      break;
    }
  const sor = (r: SyntaxNode, fej: boolean, szulo: HTMLElement, oszlopok: number) => {
    const tr = el('tr');
    tr.dataset.from = String(r.from);
    let i = 0;
    for (const c of sorCellai(r)) {
      if (oszlopok && i >= oszlopok) break;
      const cella = el(fej ? 'th' : 'td');
      cella.dataset.from = String(c.from);
      if (igazitas[i]) cella.style.textAlign = igazitas[i];
      if (c.node) {
        const w = new SorIro(cella);
        sorban(c.node, c.from, c.to, o, w);
        w.zar();
      }
      tr.appendChild(cella);
      i++;
    }
    for (; oszlopok && i < oszlopok; i++) {
      const ures = el(fej ? 'th' : 'td');
      ures.dataset.from = String(r.to);
      tr.appendChild(ures);
    }
    szulo.appendChild(tr);
    return i;
  };
  let oszlopok = 0;
  const fej = gyermek(n, 'TableHeader');
  if (fej) {
    const thead = el('thead');
    oszlopok = sor(fej, true, thead, 0);
    t.appendChild(thead);
  }
  const tbody = el('tbody');
  for (let c = n.firstChild; c; c = c.nextSibling) if (c.name === 'TableRow') sor(c, false, tbody, oszlopok);
  if (tbody.childNodes.length) t.appendChild(tbody);
  return t;
}

function lista(n: SyntaxNode, o: RenderOpciok, cel: Node): void {
  const rendezett = n.name === 'OrderedList';
  const l = el(rendezett ? 'ol' : 'ul');
  if (rendezett) {
    const jel = n.firstChild && gyermek(n.firstChild, 'ListMark');
    const kezd = jel ? parseInt(o.olvas(jel.from, jel.to), 10) : 1;
    if (Number.isFinite(kezd) && kezd !== 1) (l as HTMLOListElement).start = kezd;
  }
  for (let c = n.firstChild; c; c = c.nextSibling) {
    if (c.name !== 'ListItem') continue;
    const li = el('li');
    for (let b = c.firstChild; b; b = b.nextSibling) {
      if (b.name === 'ListMark') continue;
      if (b.name === 'Task') feladat(b, o, li);
      else blokk(b, o, li);
    }
    l.appendChild(li);
  }
  cel.appendChild(l);
}

function feladat(n: SyntaxNode, o: RenderOpciok, li: HTMLElement): void {
  const jel = gyermek(n, 'TaskMarker');
  const allapot = jel ? feladatAllapot(o.olvas(jel.from, jel.to)) : ' ';
  li.classList.add('feladat');
  li.dataset.allapot = allapot;
  const doboz = el('input', 'feladat-jelolo');
  doboz.type = 'checkbox';
  doboz.checked = allapot !== ' ';
  doboz.setAttribute('aria-label', allapot === ' ' ? t('Feladat: kész') : t('Feladat: nincs kész'));
  if (jel) doboz.dataset.jelolo = String(jel.from);
  if (o.ut) doboz.dataset.jeloloUt = o.ut;
  if (o.beagyazas) doboz.dataset.beagyazas = 'true';
  doboz.disabled = o.csakOlvashato === true;
  const p = el('p');
  p.appendChild(doboz);
  const w = new SorIro(p);
  sorban(n, jel ? jel.to : n.from, azonositoNelkul(o, jel ? jel.to : n.from, n.to) ?? n.to, o, w);
  w.zar();
  li.appendChild(p);
}

function kodSzovege(n: SyntaxNode, o: RenderOpciok): string {
  let s = '';
  for (let c = n.firstChild; c; c = c.nextSibling) if (c.name === 'CodeText') s += o.olvas(c.from, c.to);
  return s;
}

export function masolasGomb(kod: () => string): HTMLButtonElement {
  const b = el('button', 'kod-masol');
  b.type = 'button';
  b.setAttribute('aria-label', t('Kód másolása'));
  b.title = t('Kód másolása');
  b.appendChild(ikonElem(Copy, 14));
  b.addEventListener('click', async (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (await vagolapra(kod())) {
      b.replaceChildren(ikonElem(Check, 14));
      b.setAttribute('aria-label', t('Másolva'));
      setTimeout(() => {
        b.replaceChildren(ikonElem(Copy, 14));
        b.setAttribute('aria-label', t('Kód másolása'));
      }, 1500);
    }
  });
  return b;
}


function kodBlokk(n: SyntaxNode, o: RenderOpciok, cel: Node): void {
  const infoNode = gyermek(n, 'CodeInfo');
  const info = infoNode ? o.olvas(infoNode.from, infoNode.to) : '';
  const kod = n.name === 'CodeBlock' ? o.olvas(n.from, n.to).replace(/^ {1,4}/gm, '') : kodSzovege(n, o);
  const r = kodRenderelok.keres(info);
  if (r) {
    const d = el('div', 'kodblokk-renderelo');
    d.style.minHeight = `${r.becsultMagassag?.(kod) ?? 120}px`;
    o.lusta.ker(d, () => {
      void renderel(r, kod, d, { ut: o.ut, sotet: sotetTema(), jel: o.lusta.jel }).then((t) => {
        d.style.minHeight = '';
        o.lusta.takarit(t);
      });
    });
    cel.appendChild(d);
    return;
  }
  const f = el('figure', 'kodblokk');
  const fej = el('div', 'kodblokk-fej');
  const nyelv = el('span', 'kodblokk-nyelv');
  nyelv.textContent = /^\S*/.exec(info)?.[0] ?? '';
  fej.append(nyelv, masolasGomb(() => kod));
  const pre = el('pre');
  const code = el('code');
  code.textContent = kod;
  pre.appendChild(code);
  if (info) o.lusta.ker(code, () => void kodSzinez(kod, info, code));
  f.append(fej, pre);
  cel.appendChild(f);
}

function callout(n: SyntaxNode, o: RenderOpciok, cel: Node): boolean {
  const a = calloutAdat(n, o.olvas);
  if (!a) return false;
  const m = calloutTipusok.megjelenes(a.tipus);
  const hajthato = a.hajtas !== '';
  const kont = el(hajthato ? 'details' : 'div', `callout callout-${m.szin}`);
  kont.dataset.callout = m.tipus;
  if (kont instanceof HTMLDetailsElement) kont.open = a.hajtas !== '-';
  const fej = el(hajthato ? 'summary' : 'div', 'callout-cim');
  const ikon = el('span', 'callout-ikon');
  ikon.appendChild(ikonElem(m.ikon, 16));
  const cim = el('span', 'callout-cim-szoveg');
  if (a.cimTo > a.cimFrom) {
    const w = new SorIro(cim);
    sorban(a.bekezdes, a.cimFrom, a.cimTo, o, w);
    w.zar();
  } else cim.textContent = m.cim;
  fej.append(ikon, cim);
  if (hajthato) {
    const h = el('span', 'callout-hajto');
    h.appendChild(ikonElem(ChevronRight, 16));
    fej.appendChild(h);
  }
  const torzs = el('div', 'callout-torzs');
  if (a.fejVeg < a.bekezdes.to) bekezdes(a.bekezdes, o, torzs, a.fejVeg + 1, a.bekezdes.to);
  for (let c = a.bekezdes.nextSibling; c; c = c.nextSibling) if (c.name !== 'QuoteMark') blokk(c, o, torzs);
  kont.append(fej, torzs);
  cel.appendChild(kont);
  return true;
}

function frontmatter(n: SyntaxNode, o: RenderOpciok, cel: Node): void {
  const tartalom = gyermek(n, 'FrontmatterContent');
  const yaml = tartalom ? o.olvas(tartalom.from, tartalom.to) : '';
  const d = el('details', 'tulajdonsagok');
  const s = el('summary');
  const sorok = yaml.split('\n').filter((x) => /^[^\s#-][^:]*:/.test(x)).length;
  s.textContent = sorok ? t('Tulajdonságok ({n})', { n: sorok }) : t('Tulajdonságok');
  const pre = el('pre');
  const code = el('code');
  code.textContent = yaml;
  pre.appendChild(code);
  o.lusta.ker(code, () => void kodSzinez(yaml, 'yaml', code));
  d.append(s, pre);
  cel.appendChild(d);
}

export function blokk(n: SyntaxNode, o: RenderOpciok, cel: Node): void {
  const fejezet = /^(?:ATX|Setext)Heading(\d)$/.exec(n.name);
  if (fejezet) return cimsor(n, Number(fejezet[1]), o, cel);
  switch (n.name) {
    case 'Document':
      for (let c = n.firstChild; c; c = c.nextSibling) blokk(c, o, cel);
      return;
    case 'Paragraph':
      return bekezdes(n, o, cel);
    case 'Blockquote': {
      if (callout(n, o, cel)) return;
      const bq = el('blockquote');
      for (let c = n.firstChild; c; c = c.nextSibling) if (c.name !== 'QuoteMark') blokk(c, o, bq);
      cel.appendChild(bq);
      return;
    }
    case 'BulletList':
    case 'OrderedList':
      return lista(n, o, cel);
    case 'FencedCode':
    case 'CodeBlock':
      return kodBlokk(n, o, cel);
    case 'MathBlock':
      cel.appendChild(kepletElem(n, o, true, true));
      return;
    case 'Table':
      cel.appendChild(tablaRenderel(n, o));
      return;
    case 'HorizontalRule':
      cel.appendChild(el('hr'));
      return;
    case 'Frontmatter':
      return frontmatter(n, o, cel);
    case 'FootnoteDefinition': {
      const cimke = gyermek(n, 'FootnoteLabel');
      if (cimke) (o.labjegyzetek ??= new Map()).set(o.olvas(cimke.from, cimke.to), n);
      return;
    }
    case 'HTMLBlock': {
      const p = el('p', 'html-blokk');
      p.textContent = o.olvas(n.from, n.to);
      cel.appendChild(p);
      return;
    }
    case 'LinkReference':
    case 'ObsidianCommentBlock':
    case 'ObsidianComment':
    case 'CommentBlock':
    case 'ProcessingInstructionBlock':
      return;
    default:
      if (JELOLOK.has(n.name)) return;
      bekezdes(n, o, cel);
  }
}

function labjegyzetSzakasz(o: RenderOpciok): HTMLElement | null {
  const defs = o.labjegyzetek;
  if (!defs?.size) return null;
  const szamok = (o.labjegyzetSzam ??= new Map());
  for (const nev of defs.keys()) if (!szamok.has(nev)) szamok.set(nev, szamok.size + 1);
  const s = el('section', 'labjegyzetek');
  s.setAttribute('aria-label', t('Lábjegyzetek'));
  s.appendChild(el('hr'));
  const ol = el('ol');
  for (const [nev, n] of [...defs].sort((a, b) => szamok.get(a[0])! - szamok.get(b[0])!)) {
    const li = el('li');
    li.id = `${o.elotag ?? 'lj'}-def-${nev}`;
    for (let c = n.firstChild; c; c = c.nextSibling) if (!JELOLOK.has(c.name)) blokk(c, o, li);
    const vissza = el('a', 'labjegyzet-vissza');
    vissza.dataset.labjegyzetVissza = nev;
    vissza.textContent = '↩';
    vissza.setAttribute('role', 'link');
    vissza.tabIndex = 0;
    vissza.setAttribute('aria-label', t('Vissza a szövegbe'));
    (li.lastElementChild ?? li).appendChild(vissza);
    ol.appendChild(li);
  }
  s.appendChild(ol);
  return s;
}

/** A teljes dokumentum (a lábjegyzet-szakasszal együtt). A felső szintű blokkok `data-from`/`data-to`
 *  attribútumot kapnak (a módváltás a görgetési helyet ezzel tartja meg). */
export function dokumentumRenderel(fa: Tree, o: RenderOpciok): DocumentFragment {
  const f = document.createDocumentFragment();
  o.labjegyzetSzam = new Map();
  o.labjegyzetek = new Map();
  for (let c = fa.topNode.firstChild; c; c = c.nextSibling) {
    const elotte = f.lastChild;
    blokk(c, o, f);
    for (let e = elotte ? elotte.nextSibling : f.firstChild; e; e = e.nextSibling)
      if (e instanceof HTMLElement) {
        e.dataset.from = String(c.from);
        e.dataset.to = String(c.to);
      }
  }
  const lj = labjegyzetSzakasz(o);
  if (lj) f.appendChild(lj);
  return f;
}
