// A soron belüli HTML a Live Preview-ban (C32): az engedélylistás címke (`<sub>`, `<sup>`, `<br>` …) formázva jelenik
// meg, a címke rejtve, mint az Olvasóban; az aktív sorban a forrás látszik; a nem engedett címke és az attribútumos
// címke szöveg marad.

import { afterEach, describe, expect, it } from 'vitest';
import { engedettCimke } from '../src/szerkeszto/markdown/html';
import { nezet, tisztit } from './notion-segedek';

afterEach(() => tisztit());

describe('engedettCimke', () => {
  it('csak attribútum nélküli, engedélylistás címke', () => {
    expect(engedettCimke('<sub>')).toEqual({ nev: 'sub', zaro: false, onzaro: false });
    expect(engedettCimke('</SUP>')).toEqual({ nev: 'sup', zaro: true, onzaro: false });
    expect(engedettCimke('<br/>')).toEqual({ nev: 'br', zaro: false, onzaro: true });
    expect(engedettCimke('<img src="x.png">')).toBeNull();
    expect(engedettCimke('<span style="color:red">')).toBeNull();
    expect(engedettCimke('<script>')).toBeNull();
  });
});

describe('Live Preview', () => {
  it('a H<sub>2</sub>O formázva, a címkék rejtve; az aktív sorban forrás', () => {
    const v = nezet('A víz H<sub>2</sub>O, x<sup>2</sup>.\n\nMásik sor', 'A víz H<sub>2</sub>O, x<sup>2</sup>.\n\nMásik sor'.length);
    const sor = v.contentDOM.querySelector('.cm-line')!;
    expect(sor.querySelector('sub')?.textContent).toBe('2');
    expect(sor.querySelector('sup')?.textContent).toBe('2');
    expect(sor.textContent).toBe('A víz H2O, x2.');
    v.dispatch({ selection: { anchor: 3 } });
    expect(v.contentDOM.querySelector('.cm-line')!.textContent).toBe('A víz H<sub>2</sub>O, x<sup>2</sup>.');
  });

  it('a <br> sortörés; a nem engedett, a pár nélküli és az attribútumos címke szöveg marad', () => {
    const doc = 'egy<br>kettő <span>x</span> <sub>nyitva <b class="a">y</b>\n\nVége';
    const v = nezet(doc, doc.length);
    const sor = v.contentDOM.querySelector('.cm-line')!;
    expect(sor.querySelector('br')).not.toBeNull();
    expect(sor.textContent).toContain('<span>x</span>');
    expect(sor.textContent).toContain('<sub>nyitva');
    expect(sor.textContent).toContain('<b class="a">y</b>');
    expect(sor.querySelector('sub, b')).toBeNull();
  });
});

describe('blokkazonosító a Live Preview-ban', () => {
  it('a sor végi ^id halványan jelölve; kódban és szó közepén nem', () => {
    const doc = 'Bekezdés vége ^abc-1\n\n```\nkód ^nem\n```\n\nx^2 és 2^n\n\nVége';
    const v = nezet(doc, doc.length);
    const jelek = [...v.contentDOM.querySelectorAll('.cm-blokk-azon')].map((e) => e.textContent);
    expect(jelek).toEqual(['^abc-1']);
  });
});
