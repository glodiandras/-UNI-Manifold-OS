// Szanitizált HTML (01-rendering-11): a jegyzetben álló HTML-blokk és soron belüli HTML-címke engedélylistás másolata.
// A „nincs innerHTML” szabály marad: a forrás egy inert `DOMParser`-dokumentumba kerül (ott nem fut szkript, nem tölt be
// kép vagy stíluslap), és onnan egy engedélylistás bejáró másolja az elemeket ÚJ, a lap dokumentumában létrehozott
// csomópontokba. Esemény-attribútum, `class`, `id`, `href`/`src` közvetlenül soha nem kerül át; a link az Olvasó saját
// jelölését kapja (`data-url` a héj megnyitójához, vagy a vault-link `data-cel`-je), a kép a beágyazás-motoron át
// töltődik (vault-fájl a core-on át; külső kép automatikus hálózati kérés nélkül, D3). A stílusból csak biztonságos
// tulajdonság marad (nincs `url()`, `position`, negatív margó). Méret- és mélységkorlát felett a hívó a nyers forrást mutatja.

import { t } from '../../lib/i18n';
import type { LinkAdat } from '../linkek/adat';
import { kulsoCim } from '../linkek/kulso';
import { markdownCel } from '../linkek/markdown';

export const MAX_HTML_HOSSZ = 64 * 1024;
export const MAX_HTML_ELEM = 1500;
export const MAX_HTML_MELYSEG = 24;

/** Soron belül megjelenő címkék (bekezdésen belül értelmesek). */
export const SORON_BELULI_CIMKEK = new Set([
  'span', 'a', 'img', 'font', 'sub', 'sup', 'u', 'mark', 'kbd', 'b', 'i', 's', 'em', 'strong', 'small', 'del', 'ins', 'abbr',
  'cite', 'q', 'code', 'var', 'samp', 'dfn', 'time', 'big', 'br', 'wbr', 'ruby', 'rt', 'rp', 'bdi', 'bdo', 'strike', 'tt',
]);

/** Blokkszintű engedélylista (a soron belüliek mellett). */
const BLOKK_CIMKEK = new Set([
  'div', 'p', 'center', 'details', 'summary', 'section', 'article', 'aside', 'header', 'footer', 'nav', 'main', 'figure',
  'figcaption', 'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td', 'caption', 'colgroup', 'col', 'ul', 'ol', 'li', 'dl',
  'dt', 'dd', 'blockquote', 'pre', 'hr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'address',
]);

/** Ezek a tartalmukkal együtt eltűnnek (szkript, beágyazott dokumentum, űrlap, aktív média, idegen névtér). */
const ELDOBANDO = new Set([
  'script', 'style', 'template', 'iframe', 'frame', 'frameset', 'object', 'embed', 'applet', 'noscript', 'noembed', 'noframes',
  'svg', 'math', 'head', 'title', 'meta', 'link', 'base', 'form', 'input', 'button', 'textarea', 'select', 'option', 'optgroup',
  'datalist', 'output', 'dialog', 'canvas', 'video', 'audio', 'source', 'track', 'picture', 'portal', 'slot', 'param', 'xmp',
  'plaintext', 'marquee', 'map', 'area',
]);

const URES_CIMKEK = new Set(['br', 'wbr', 'hr', 'img', 'col']);

/** A megengedett stílus-tulajdonságok. */
const STILUS = new Set([
  'color', 'background-color', 'font-weight', 'font-style', 'font-variant', 'font-size', 'font-family', 'text-decoration',
  'text-decoration-line', 'text-decoration-color', 'text-decoration-style', 'text-align', 'text-transform', 'vertical-align',
  'white-space', 'letter-spacing', 'line-height', 'width', 'max-width', 'min-width', 'height', 'max-height', 'min-height',
  'margin', 'margin-top', 'margin-right', 'margin-bottom', 'margin-left', 'padding', 'padding-top', 'padding-right',
  'padding-bottom', 'padding-left', 'border', 'border-top', 'border-right', 'border-bottom', 'border-left', 'border-color',
  'border-style', 'border-width', 'border-radius', 'border-collapse', 'list-style-type', 'float', 'clear',
]);
const TILTOTT_ERTEK = /url\s*\(|expression\s*\(|javascript:|@import|\\|attr\s*\(|image-set|element\s*\(|-moz-binding|behavior/i;

export interface HtmlKornyezet {
  /** a jegyzet útja (a vault-linkek forrása); nélküle a helyi link szöveg marad */
  ut: string | null;
  /** a kép a beágyazás-motoron át (vault-fájl vagy külső kép kattintásos letöltése); nélküle az alt-szöveg látszik */
  kep?: (adat: LinkAdat) => HTMLElement;
}

interface Szamlalo {
  elem: number;
}

function stilusMasol(forras: HTMLElement, cel: HTMLElement): void {
  const st = forras.style;
  for (let i = 0; i < st.length; i++) {
    const tul = st[i];
    if (!STILUS.has(tul)) continue;
    const ertek = st.getPropertyValue(tul).trim();
    if (!ertek || ertek.length > 200 || TILTOTT_ERTEK.test(ertek)) continue;
    if (/^(margin|padding)/.test(tul) && /(^|\s)-\d|(^|\s)-\./.test(ertek)) continue; // nem lóghat a tartalmon kívülre
    cel.style.setProperty(tul, ertek);
  }
}

const egesz = (x: string | null, min: number, max: number): number | null => {
  if (x === null || !/^\s*\d{1,6}\s*$/.test(x)) return null;
  const n = Number(x);
  return n >= min && n <= max ? n : null;
};

/** A link jelölése: vault-cél (`data-cel`, mint az Olvasó Markdown-linkje) vagy külső cím (`data-url`); `href` sosem. */
function linkJelol(a: HTMLElement, href: string, k: HtmlKornyezet): void {
  a.classList.add('link');
  a.title = href;
  const helyi = markdownCel(href);
  if (helyi && k.ut) {
    a.classList.add('wikilink');
    a.dataset.cel = helyi.cel;
    if (helyi.alcel) a.dataset.alcel = helyi.alcel;
    a.dataset.forras = k.ut;
  } else {
    const cim = kulsoCim(href);
    if (!cim) return;
    a.dataset.url = cim;
  }
  a.setAttribute('role', 'link');
  a.tabIndex = 0;
}

function kepElem(forras: HTMLElement, k: HtmlKornyezet): HTMLElement | null {
  const src = (forras.getAttribute('src') ?? '').trim();
  const alt = forras.getAttribute('alt') ?? '';
  const w = egesz(forras.getAttribute('width'), 1, 10000);
  const h = egesz(forras.getAttribute('height'), 1, 10000);
  if (!src || !k.kep) {
    if (!alt) return null;
    const s = document.createElement('span');
    s.className = 'html-kep-alt';
    s.textContent = alt;
    return s;
  }
  const helyi = markdownCel(src);
  const adat: LinkAdat = {
    cel: helyi?.cel ?? src,
    alcel: helyi?.alcel ?? null,
    alias: w ? (h ? `${w}x${h}` : String(w)) : null,
    alt,
    kulso: !helyi,
    beagyazas: true,
    from: 0,
    to: 0,
  };
  return k.kep(adat);
}

/** Egy engedélyezett forrás-elem üres (gyermek nélküli) másolata a lap dokumentumában; `null`: nem engedett. */
function elemMasol(forras: Element, k: HtmlKornyezet, soronBelul: boolean): HTMLElement | null {
  const nev = forras.localName;
  if (forras.namespaceURI !== 'http://www.w3.org/1999/xhtml') return null;
  if (!SORON_BELULI_CIMKEK.has(nev) && (soronBelul || !BLOKK_CIMKEK.has(nev))) return null;
  const f = forras as HTMLElement; // az inert dokumentum eleme: csak olvassuk
  if (nev === 'img') return kepElem(f, k);
  let cel: HTMLElement;
  switch (nev) {
    case 'center':
      cel = document.createElement('div');
      cel.style.textAlign = 'center';
      break;
    case 'font':
    case 'big':
      cel = document.createElement('span');
      if (nev === 'big') cel.style.fontSize = 'larger';
      break;
    case 'strike':
      cel = document.createElement('s');
      break;
    case 'tt':
      cel = document.createElement('code');
      break;
    case 'a':
      cel = document.createElement('a');
      break;
    default:
      cel = document.createElement(nev);
  }
  stilusMasol(f, cel);
  for (const attr of ['title', 'lang']) {
    const v = f.getAttribute(attr);
    if (v !== null && v.length <= 500) cel.setAttribute(attr, v);
  }
  const dir = f.getAttribute('dir');
  if (dir && /^(ltr|rtl|auto)$/i.test(dir)) cel.dir = dir.toLowerCase();
  const align = f.getAttribute('align');
  if (align && /^(left|right|center|justify)$/i.test(align)) cel.style.textAlign = align.toLowerCase();
  if (nev === 'font') {
    const szin = f.getAttribute('color');
    if (szin && /^#?[a-zA-Z0-9]{1,20}$/.test(szin)) cel.style.color = szin;
  }
  if (nev === 'td' || nev === 'th') {
    const cs = egesz(f.getAttribute('colspan'), 1, 100);
    const rs = egesz(f.getAttribute('rowspan'), 1, 1000);
    if (cs) (cel as HTMLTableCellElement).colSpan = cs;
    if (rs) (cel as HTMLTableCellElement).rowSpan = rs;
  }
  if (nev === 'td' || nev === 'th' || nev === 'table' || nev === 'col') {
    const w = f.getAttribute('width');
    if (w && /^\d{1,5}%?$/.test(w)) cel.style.width = /%$/.test(w) ? w : `${w}px`;
  }
  if (nev === 'details' && f.hasAttribute('open')) (cel as HTMLDetailsElement).open = true;
  if (nev === 'ol') {
    const s = egesz(f.getAttribute('start'), 0, 1e6);
    if (s !== null) (cel as HTMLOListElement).start = s;
    if (f.hasAttribute('reversed')) (cel as HTMLOListElement).reversed = true;
    const tipus = f.getAttribute('type');
    if (tipus && /^[1aAiI]$/.test(tipus)) (cel as HTMLOListElement).type = tipus;
  }
  if (nev === 'time') {
    const d = f.getAttribute('datetime');
    if (d && d.length <= 64) cel.setAttribute('datetime', d);
  }
  if (nev === 'a') {
    const href = (f.getAttribute('href') ?? '').trim();
    if (href) linkJelol(cel, href, k);
  }
  return cel;
}

function masol(forras: Node, cel: Node, k: HtmlKornyezet, sz: Szamlalo, melyseg: number): boolean {
  if (melyseg > MAX_HTML_MELYSEG) return false;
  for (let c = forras.firstChild; c; c = c.nextSibling) {
    if (c.nodeType === Node.TEXT_NODE) {
      cel.appendChild(document.createTextNode(c.textContent ?? ''));
      continue;
    }
    if (c.nodeType !== Node.ELEMENT_NODE) continue; // megjegyzés, feldolgozási utasítás
    const e = c as Element;
    const nev = e.localName;
    if (ELDOBANDO.has(nev) || e.namespaceURI !== 'http://www.w3.org/1999/xhtml') continue;
    if (++sz.elem > MAX_HTML_ELEM) return false;
    const uj = elemMasol(e, k, false);
    if (!uj) {
      // ismeretlen címke: a tartalma megmarad, maga a címke nem
      if (!masol(e, cel, k, sz, melyseg + 1)) return false;
      continue;
    }
    cel.appendChild(uj);
    if (!URES_CIMKEK.has(nev) && nev !== 'img' && !masol(e, uj, k, sz, melyseg + 1)) return false;
  }
  return true;
}

function inert(html: string): Document {
  return new DOMParser().parseFromString(`<!doctype html><html><body>${html}</body></html>`, 'text/html');
}

/** Egy HTML-blokk szanitizált másolata; `null`, ha a forrás a korlátokon túl van (a hívó a nyers szöveget mutatja). */
export function htmlBlokk(html: string, k: HtmlKornyezet): DocumentFragment | null {
  if (html.length > MAX_HTML_HOSSZ) return null;
  const f = document.createDocumentFragment();
  return masol(inert(html).body, f, k, { elem: 0 }, 0) ? f : null;
}

/** Látható-e bármi a szanitizált eredményben (szöveg vagy kép); az üres eredmény helyén a hívó a forrást mutatja. */
export function vanTartalom(f: DocumentFragment): boolean {
  return !!(f.textContent ?? '').trim() || !!(f as unknown as ParentNode).querySelector?.('img, .beagyazas, hr, br, table');
}

export interface SoronBeluliCimke {
  nev: string;
  zaro: boolean;
  onzaro: boolean;
  /** nyitó címkénél a szanitizált, gyermek nélküli elem (kép esetén a beágyazás) */
  elem: HTMLElement | null;
}

/** Egy soron belüli HTML-címke (`<x …>`, `</x>`, `<x/>`) az engedélylistáról, szanitizált attribútumokkal; különben `null`. */
export function soronBeluliCimke(cimke: string, k: HtmlKornyezet): SoronBeluliCimke | null {
  const s = cimke.trim();
  const m = /^<(\/?)([a-zA-Z][a-zA-Z0-9]*)\b([^<>]*?)(\/?)>$/s.exec(s);
  if (!m || s.length > 4096) return null;
  const nev = m[2].toLowerCase();
  if (!SORON_BELULI_CIMKEK.has(nev)) return null;
  if (m[1]) return /^\s*$/.test(m[3]) ? { nev, zaro: true, onzaro: false, elem: null } : null;
  const forras = inert(s).body.firstElementChild;
  if (!forras || forras.localName !== nev) return null;
  const elem = elemMasol(forras, k, true);
  if (!elem && nev !== 'img') return null;
  return { nev, zaro: false, onzaro: !!m[4] || URES_CIMKEK.has(nev), elem };
}

/** A szanitizált elem attribútumai a Live Preview jelöléséhez (`style`, `title`, `lang`, `dir`, link-adatok). */
export function attributumok(e: HTMLElement): Record<string, string> {
  const ki: Record<string, string> = {};
  for (const a of e.attributes) ki[a.name] = a.value;
  return ki;
}

/** A nyers forrás doboza (a korlátokon túli vagy üres eredményű blokk): a meglévő `html-blokk` megjelenés. */
export function nyersHtmlDoboz(forras: string): HTMLElement {
  const p = document.createElement('p');
  p.className = 'html-blokk';
  p.textContent = forras;
  p.title = t('A HTML nem jeleníthető meg biztonságosan; a forrás látszik.');
  return p;
}
