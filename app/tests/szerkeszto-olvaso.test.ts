// Az Olvasó (C08, jsdom): a szintaxisfából épített DOM. Obsidian-szemantika (sima sortörés → `<br>`,
// lábjegyzetek a lap alján, összecsukható callout), engedélyezett HTML-címkék, és hogy a Markdownból
// soha nem lesz futó HTML.

import { afterEach, describe, expect, it, vi } from 'vitest';
import { obsidianElemzo } from '../src/szerkeszto/markdown/elemzo';
import { dokumentumRenderel } from '../src/szerkeszto/olvaso/html';
import { LustaRajzolo } from '../src/szerkeszto/olvaso/lusta';
import { kodRenderelok } from '../src/szerkeszto/renderelok/regiszter';

function render(s: string): HTMLElement {
  const lusta = LustaRajzolo.azonnali();
  const d = document.createElement('article');
  d.appendChild(dokumentumRenderel(obsidianElemzo.parse(s), { olvas: (a, b) => s.slice(a, b), ut: 'proba.md', lusta, elotag: 'p' }));
  return d;
}

afterEach(() => vi.restoreAllMocks());

describe('olvasó: szöveg és soron belüli elemek', () => {
  it('fejezet, bekezdés, kiemelések, kód; a sima sortörés `<br>`', () => {
    const d = render('# Cím\n\n*dőlt* **félkövér** ~~áthúzott~~ ==kiemelt== `kód`\nkövetkező sor');
    expect(d.querySelector('h1')!.textContent).toBe('Cím');
    const p = d.querySelector('p')!;
    expect(p.querySelector('em')!.textContent).toBe('dőlt');
    expect(p.querySelector('strong')!.textContent).toBe('félkövér');
    expect(p.querySelector('del')!.textContent).toBe('áthúzott');
    expect(p.querySelector('mark.jeloles')!.textContent).toBe('kiemelt');
    expect(p.querySelector('code')!.textContent).toBe('kód');
    expect(p.querySelector('br')).not.toBeNull();
    expect(p.textContent).toBe('dőlt félkövér áthúzott kiemelt kódkövetkező sor');
  });

  it('a képlet KaTeX-szel; a soron belüli és a blokk', () => {
    const d = render('Sorban $a^2$, blokk:\n\n$$\n\\frac12\n$$');
    expect(d.querySelector('span.keplet .katex')).not.toBeNull();
    expect(d.querySelector('div.keplet-blokk .katex-display')).not.toBeNull();
  });

  it('a link formázva, de nem navigál; a wikilink az aliasát mutatja; a kép a közös beágyazóba kerül', () => {
    const d = render('[szöveg](https://pelda.hu) és [[Cél#Fejezet|alias]] és [[Cél#Fejezet]] és ![kép](a.png)');
    const a = d.querySelector<HTMLAnchorElement>('a.link')!;
    expect(a.getAttribute('href')).toBeNull();
    expect(a.title).toBe('https://pelda.hu');
    const w = [...d.querySelectorAll('.wikilink')].map((x) => x.textContent);
    expect(w).toEqual(['alias', 'Cél › Fejezet']);
    expect(d.querySelector<HTMLElement>('.beagyazas')!.dataset.cel).toBe('a.png');
  });

  it('HTML: a `sub`/`sup` elem lesz, minden más szöveg marad (nincs futó HTML)', () => {
    const d = render('H<sub>2</sub>O és x<sup>2</sup>; <script>alert(1)</script> <img src=x onerror=alert(1)> <b onclick="x">b</b>\n\n<div onclick="alert(1)">blokk</div>');
    expect(d.querySelector('sub')!.textContent).toBe('2');
    expect(d.querySelector('sup')!.textContent).toBe('2');
    expect(d.querySelector('script')).toBeNull();
    expect(d.querySelector('img')).toBeNull();
    expect(d.querySelector('[onclick]')).toBeNull();
    expect(d.querySelector('div[onclick]')).toBeNull();
    expect(d.textContent).toContain('<script>alert(1)</script>');
    expect(d.textContent).toContain('<div onclick="alert(1)">blokk</div>');
  });
});

describe('olvasó: blokkok', () => {
  it('listák, feladatok (kattintható jelölő), számozás kezdete', () => {
    const d = render('- a\n- b\n\n3. c\n4. d\n\n- [ ] nyitott\n- [x] kész\n- [/] folyamatban');
    expect(d.querySelectorAll('ul li').length).toBeGreaterThanOrEqual(2);
    expect((d.querySelector('ol') as HTMLOListElement).start).toBe(3);
    const dobozok = [...d.querySelectorAll<HTMLInputElement>('input.feladat-jelolo')];
    expect(dobozok.map((x) => x.checked)).toEqual([false, true, true]);
    expect(dobozok.every((x) => x.dataset.jelolo !== undefined)).toBe(true);
  });

  it('idézet és callout: ikon, cím vagy magyar alapcím, összecsukható `details`', () => {
    const d = render('> sima\n\n> [!note] Saját cím\n> törzs\n\n> [!warning]- \n> rejtett\n\n> [!tip]+\n> nyitott\n\n> [!ismeretlen]\n> x');
    expect(d.querySelector('blockquote')!.textContent).toBe('sima');
    const c = [...d.querySelectorAll<HTMLElement>('.callout')];
    expect(c.map((x) => x.dataset.callout)).toEqual(['note', 'warning', 'tip', 'ismeretlen']);
    expect(c[0].querySelector('.callout-cim-szoveg')!.textContent).toBe('Saját cím');
    expect(c[0].tagName).toBe('DIV');
    expect(c[1].tagName).toBe('DETAILS');
    expect((c[1] as HTMLDetailsElement).open).toBe(false);
    expect(c[1].querySelector('.callout-cim-szoveg')!.textContent).toBe('Figyelmeztetés');
    expect((c[2] as HTMLDetailsElement).open).toBe(true);
    expect(c[2].querySelector('.callout-cim-szoveg')!.textContent).toBe('Tipp');
    expect(c[3].classList.contains('callout-kek')).toBe(true);
    expect(c[3].querySelector('.callout-cim-szoveg')!.textContent).toBe('Ismeretlen');
    expect(c[0].querySelector('.callout-torzs')!.textContent).toBe('törzs');
  });

  it('kódblokk: nyelvcímke, másolás gomb, a kód szövege; a regiszteres nyelv a renderelőhöz kerül', async () => {
    const render1 = vi.fn((forras: string, cel: HTMLElement) => {
      cel.textContent = `rajz: ${forras}`;
    });
    const le = kodRenderelok.regisztral({ nyelv: 'probarajz', render: render1 });
    try {
      const d = render('```python\nprint(1)\n```\n\n```probarajz\nA -> B\n```');
      expect(d.querySelector('.kodblokk-nyelv')!.textContent).toBe('python');
      expect(d.querySelector('.kod-masol')!.getAttribute('aria-label')).toBe('Kód másolása');
      expect(d.querySelector('pre code')!.textContent).toBe('print(1)');
      await Promise.resolve();
      expect(render1).toHaveBeenCalledWith('A -> B', expect.any(HTMLElement), expect.objectContaining({ ut: 'proba.md' }));
      expect(d.querySelector('.kodblokk-renderelo')!.textContent).toBe('rajz: A -> B');
    } finally {
      le();
    }
  });

  it('a renderelő hibája a blokkban látszik', async () => {
    const le = kodRenderelok.regisztral({
      nyelv: 'hibasrajz',
      render: () => {
        throw new Error('rossz szintaxis');
      },
    });
    try {
      const d = render('```hibasrajz\nx\n```');
      await new Promise((r) => setTimeout(r, 0));
      expect(d.querySelector('.renderelo-hiba')!.textContent).toContain('rossz szintaxis');
    } finally {
      le();
    }
  });

  it('táblázat: fejléc, igazítás, a cellák forráshelye; elválasztó', () => {
    const s = '| a | b |\n|:-:|--:|\n| 1 | $|x|$ |\n\n---';
    const d = render(s);
    const th = [...d.querySelectorAll('th')];
    expect(th.map((x) => x.textContent)).toEqual(['a', 'b']);
    expect(th.map((x) => x.style.textAlign)).toEqual(['center', 'right']);
    const td = [...d.querySelectorAll('td')];
    expect(td[0].dataset.from).toBe(String(s.indexOf('1 |')));
    expect(td[1].querySelector('.katex')).not.toBeNull();
    expect(d.querySelector('hr')).not.toBeNull();
  });

  it('lábjegyzetek a lap alján, a hivatkozás sorrendjében számozva, visszamutatóval', () => {
    const d = render('Első[^b] és második[^a].\n\n[^a]: Az A.\n[^b]: A B.');
    expect([...d.querySelectorAll('sup.labjegyzet-hiv a')].map((x) => x.textContent)).toEqual(['1', '2']);
    const lj = [...d.querySelectorAll('section.labjegyzetek li')];
    expect(lj.map((x) => x.textContent!.replace('↩', '').trim())).toEqual(['A B.', 'Az A.']);
    expect(lj[0].id).toBe('p-def-b');
    expect(d.querySelector('[data-labjegyzet-vissza="b"]')).not.toBeNull();
  });

  it('frontmatter: összecsukott tulajdonságok; a felső szintű blokkok forráshelye', () => {
    const s = '---\nTags: a\nSource: b\n---\n# Cím';
    const d = render(s);
    expect(d.querySelector('details.tulajdonsagok summary')!.textContent).toBe('Tulajdonságok (2)');
    const h1 = d.querySelector('h1')!;
    expect(h1.dataset.from).toBe(String(s.indexOf('# Cím')));
  });
});

describe('olvasó: blokkazonosító (C09)', () => {
  it('a bekezdés, listaelem, feladat végén álló ^id és az önálló ^id sor rejtve marad (mint az Obsidianban)', () => {
    const d = render('Bekezdés ^abc123\n\n- elem ^e1\n- [ ] feladat ^f1\n\n| a |\n|---|\n| 1 |\n\n^tabla\n\nSzöveg ^2 nem végén ^ x\n');
    const szoveg = d.textContent!;
    expect(szoveg).not.toContain('^abc123');
    expect(szoveg).not.toContain('^e1');
    expect(szoveg).not.toContain('^f1');
    expect(szoveg).not.toContain('^tabla');
    expect(d.querySelectorAll('p').length).toBe(4); // a bekezdés, a két lista-elem, az utolsó; az ^id sor nem bekezdés
    expect(szoveg).toContain('Szöveg ^2 nem végén ^ x');
    expect(d.querySelector('p')!.textContent).toBe('Bekezdés');
  });
});
