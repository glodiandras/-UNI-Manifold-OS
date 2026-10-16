// A soron belüli HTML a Live Preview-ban (C32, 01-rendering-11): az engedélylistás címke (`<sub>`, `<sup>`, `<br>`,
// `<span style>` …) szanitizált attribútumokkal formázva jelenik meg, a címke rejtve, mint az Olvasóban; az aktív sorban a
// forrás látszik; a nem engedett és a pár nélküli címke szöveg marad.

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

  it('a <br> sortörés; az attribútumos címke szanitizálva; a nem engedett és a pár nélküli címke szöveg marad', () => {
    const doc = 'egy<br>kettő <span style="color: red; position: fixed">x</span> <sub>nyitva <b class="a" onclick="z()">y</b> <script>s</script>\n\nVége';
    const v = nezet(doc, doc.length);
    const sor = v.contentDOM.querySelector('.cm-line')!;
    expect(sor.querySelector('br')).not.toBeNull();
    expect(sor.textContent).toBe('egykettő x <sub>nyitva y <script>s</script>');
    const span = [...sor.querySelectorAll<HTMLElement>('span')].find((e) => e.style.color === 'red')!;
    expect(span.textContent).toBe('x');
    expect(span.style.position).toBe('');
    const b = sor.querySelector('b')!;
    expect(b.textContent).toBe('y');
    expect(b.getAttribute('class')).toBeNull();
    expect(b.getAttribute('onclick')).toBeNull();
    expect(sor.querySelector('sub, script')).toBeNull();
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
