// 01-rendering-11: szanitizált HTML — blokkok, attribútumok, `<img>`, `<details>`, `<span style>` az Olvasóban és a
// Live Preview-ban; a `innerHTML`-tilalom marad (inert elemzés + engedélylistás másolás), nincs futó kód, nincs hálózat.
import { ensureSyntaxTree } from '@codemirror/language';
import { EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { LinkAdat } from '../src/szerkeszto/linkek/adat';
import { bovitmenyek } from '../src/szerkeszto/beallitas';
import { obsidianElemzo } from '../src/szerkeszto/markdown/elemzo';
import { dokumentumRenderel } from '../src/szerkeszto/olvaso/html';
import { htmlBlokk, MAX_HTML_ELEM, MAX_HTML_HOSSZ, MAX_HTML_MELYSEG, soronBeluliCimke } from '../src/szerkeszto/olvaso/htmlSzures';
import { LustaRajzolo } from '../src/szerkeszto/olvaso/lusta';

const nezetek: EditorView[] = [];
let keresek: string[] = [];
beforeEach(() => {
  keresek = [];
  vi.stubGlobal('fetch', vi.fn(async (u: string) => { keresek.push(String(u)); return new Response('{}', { status: 404 }); }));
});
afterEach(() => { for (const v of nezetek.splice(0)) v.destroy(); document.body.textContent = ''; vi.unstubAllGlobals(); });

function blokk(html: string, kepek: LinkAdat[] = []) {
  const f = htmlBlokk(html, { ut: 'Mappa/Host.md', kep: (a) => { kepek.push(a); const s = document.createElement('span'); s.className = 'kep-helye'; return s; } });
  const d = document.createElement('div');
  if (f) d.append(f);
  return { d, f };
}

describe('a szanitizáló bejáró', () => {
  it('szkript, stílus, iframe, űrlap és SVG a tartalmával együtt eltűnik; eseménykezelő, class, id nem kerül át', () => {
    const { d } = blokk('<div id="x" class="atfedes" onclick="a()" onmouseover="b()">ok<script>alert(1)</script><style>*{}</style><iframe src="https://e.x"></iframe><form><input value="v"></form><svg><script>1</script></svg></div>');
    expect(d.innerHTML).toBe('<div>ok</div>');
  });

  it('a stílusból csak biztonságos tulajdonság marad', () => {
    const { d } = blokk('<span style="color: red; position: fixed; top: 0; background-image: url(https://e.x/a.png); margin-left: -500px; font-weight: bold; z-index: 99">x</span>');
    const s = d.querySelector('span')!;
    expect(s.style.color).toBe('red');
    expect(s.style.fontWeight).toBe('bold');
    expect(s.style.position).toBe('');
    expect(s.style.backgroundImage).toBe('');
    expect(s.style.marginLeft).toBe('');
    expect(s.style.zIndex).toBe('');
  });

  it('link: külső cím a héj megnyitójának, vault-cél wikilinkként, tiltott séma csak szöveg; href sosem', () => {
    const { d } = blokk('<a href="https://example.com/x">k</a><a href="Mappa/Cél%20jegyzet.md#Rész">b</a><a href="javascript:alert(1)">j</a>');
    const [k, b, j] = [...d.querySelectorAll<HTMLElement>('a')];
    expect(k.dataset.url).toBe('https://example.com/x');
    expect(b.classList.contains('wikilink')).toBe(true);
    expect(b.dataset).toMatchObject({ cel: 'Mappa/Cél jegyzet.md', alcel: 'Rész', forras: 'Mappa/Host.md' });
    expect(j.dataset.url).toBeUndefined();
    expect(j.getAttribute('role')).toBeNull();
    expect(d.querySelector('[href]')).toBeNull();
  });

  it('kép: a beágyazás-motoron át (méret aliasként, a külső kép jelölve), alt nélküli forrás nélkül eltűnik', () => {
    const kepek: LinkAdat[] = [];
    const { d } = blokk('<img src="attachments/a%20b.png" width="120" height="80" alt="Ábra" onerror="x()"><img src="https://e.x/k.png"><img alt="csak alt">', kepek);
    expect(kepek.map((k) => [k.cel, k.alias, k.alt, k.kulso])).toEqual([
      ['attachments/a b.png', '120x80', 'Ábra', false],
      ['https://e.x/k.png', null, '', true],
    ]);
    expect(d.querySelectorAll('.kep-helye').length).toBe(2);
    expect(d.querySelector('img')).toBeNull();
    expect(d.textContent).toBe('csak alt');
  });

  it('details/summary, táblázat colspan, center, font color, ismeretlen címke kibontva', () => {
    const { d } = blokk('<details open><summary>Össze</summary>Tartalom</details><table><tr><td colspan="2" width="50%">c</td></tr></table><center>k</center><font color="#c00" face="x">f</font><foo-bar>belső</foo-bar>');
    expect((d.querySelector('details') as HTMLDetailsElement).open).toBe(true);
    expect(d.querySelector('summary')!.textContent).toBe('Össze');
    const td = d.querySelector('td') as HTMLTableCellElement;
    expect(td.colSpan).toBe(2);
    expect(td.style.width).toBe('50%');
    expect((d.querySelector('div') as HTMLElement).style.textAlign).toBe('center');
    expect(d.querySelector('span')!.style.color).toBe('rgb(204, 0, 0)');
    expect(d.querySelector('foo-bar')).toBeNull();
    expect(d.textContent).toContain('belső');
  });

  it('korlátok: túl hosszú, túl sok elem vagy túl mély forrás → null (a hívó a forrást mutatja)', () => {
    expect(blokk('x'.repeat(MAX_HTML_HOSSZ + 1)).f).toBeNull();
    expect(blokk('<b>x</b>'.repeat(MAX_HTML_ELEM + 1)).f).toBeNull();
    expect(blokk('<div>'.repeat(MAX_HTML_MELYSEG + 3) + 'x').f).toBeNull();
  });

  it('soron belüli címke: csak a soron belüli engedélylista, szanitizált elemmel', () => {
    expect(soronBeluliCimke('<span style="color:blue" onclick="x">', { ut: null })?.elem?.outerHTML).toBe('<span style="color: blue;"></span>');
    expect(soronBeluliCimke('</span>', { ut: null })).toMatchObject({ nev: 'span', zaro: true });
    expect(soronBeluliCimke('<div>', { ut: null })).toBeNull();
    expect(soronBeluliCimke('<script>', { ut: null })).toBeNull();
    expect(soronBeluliCimke('<br/>', { ut: null })).toMatchObject({ nev: 'br', onzaro: true });
  });
});

describe('Olvasó', () => {
  const olvaso = (doc: string) => {
    const d = document.createElement('div');
    d.append(dokumentumRenderel(obsidianElemzo.parse(doc), { olvas: (a, b) => doc.slice(a, b), ut: 'Host.md', lusta: LustaRajzolo.azonnali() }));
    return d;
  };

  it('HTML-blokk és soron belüli HTML renderelve; a kép vault-beágyazás, külső kép hálózati kérés nélkül', () => {
    const d = olvaso('<div align="center">\n<b>Cím</b> <img src="pic.png" width="64">\n</div>\n\nSzín: <span style="color: green">zöld</span>, <a href="https://example.com">link</a>, <img src="https://e.x/a.png">');
    const blokkElem = d.querySelector('.html-blokk-render > div') as HTMLElement;
    expect(blokkElem.style.textAlign).toBe('center');
    expect(blokkElem.querySelector('b')!.textContent).toBe('Cím');
    expect(blokkElem.querySelector<HTMLElement>('.beagyazas')!.dataset.cel).toBe('pic.png');
    const p = d.querySelector('p')!;
    expect(p.querySelector('span')!.style.color).toBe('green');
    expect(p.querySelector<HTMLElement>('a.link')!.dataset.url).toBe('https://example.com/');
    expect(p.querySelectorAll('.beagyazas').length).toBe(1);
    expect(keresek.some((u) => u.includes('e.x'))).toBe(false);
  });

  it('üres eredmény (csak szkript) helyén a forrás látszik, halványan', () => {
    const d = olvaso('<script>\nalert(1)\n</script>');
    expect(d.querySelector('script')).toBeNull();
    expect(d.querySelector('.html-blokk')!.textContent).toContain('alert(1)');
  });
});

describe('Live Preview', () => {
  function nezet(doc: string, kurzor: number) {
    const parent = document.createElement('div'); document.body.append(parent);
    const v = new EditorView({ parent, state: EditorState.create({ doc, selection: { anchor: kurzor }, extensions: bovitmenyek({ mod: 'elo', ut: 'Host.md', cimke: 'Note', csakOlvashato: false }) }) });
    ensureSyntaxTree(v.state, doc.length, 5000); nezetek.push(v); return v;
  }

  it('a nem aktív HTML-blokk renderelve, az aktív forrásként; a soron belüli kép beágyazás-widget', () => {
    const doc = '<details>\n<summary>Nyitható</summary>\nRejtett <b>rész</b>\n</details>\n\nKép: <img src="a.png" width="40">\n\nVége';
    const v = nezet(doc, doc.length);
    const w = v.dom.querySelector('.cm-html-blokk')!;
    expect(w.querySelector('summary')!.textContent).toBe('Nyitható');
    expect(w.querySelector('b')!.textContent).toBe('rész');
    expect(v.dom.querySelector<HTMLElement>('.cm-beagyazas-sorban .beagyazas')!.dataset.cel).toBe('a.png');
    v.dispatch({ selection: { anchor: 3 } });
    expect(v.dom.querySelector('.cm-html-blokk')).toBeNull();
    expect(v.dom.textContent).toContain('<summary>Nyitható</summary>');
    expect(v.state.doc.toString()).toBe(doc);
  });

  it('listajel mellett álló HTML nem cserélődik blokkra (a jel nem tűnik el)', () => {
    const doc = '- <div>elem</div>\n\nVége';
    const v = nezet(doc, doc.length);
    expect(v.dom.querySelector('.cm-html-blokk')).toBeNull();
  });
});
