// A Notion-réteg a CodeMirror-nézetben (C09), jsdom-ban: a `/` menü állapota és billentyűi, a lebegő
// eszköztár feltételei és a link, a blokkparancsok (Alt+↑/↓, link másolása), a táblázat vizuális szerkesztője
// (cellaszerkesztés, Tab/Enter, sor- és oszlopmenü, visszavonás), a közös menü billentyűi. A húzás és a
// pozíciók geometriáját a böngészős kör méri (jsdom-ban nincs elrendezés).

import { undo } from '@codemirror/commands';
import { EditorSelection } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { korbefog, korbefogva } from '../src/szerkeszto/formazas';
import { blokkLep, blokkLinkMasol, blokkTorol, szomszedCel, celErvenyes } from '../src/szerkeszto/notion/blokkfogo';
import { blokkok } from '../src/szerkeszto/notion/blokkmodell';
import { eszkoztarEngedett, linkAdat, urlKodol } from '../src/szerkeszto/notion/eszkoztar';
import { Menu, type MenuElem } from '../src/szerkeszto/notion/menu';
import { perjelNyit, perjelNyitva } from '../src/szerkeszto/notion/perjel';
import { tablaFokusz } from '../src/szerkeszto/notion/tablazat/szerkeszto';
import { billentyu, gepel, nezet, teljesFa, tisztit } from './notion-segedek';

afterEach(() => {
  tisztit();
  vi.restoreAllMocks();
});

const elemek = (v: EditorView) => [...v.dom.querySelectorAll('.nt-perjel .nt-menu-elem')].map((e) => e.querySelector('.nt-menu-nev')!.textContent);

describe('a / menü', () => {
  it('a ⌘P „Beszúrás-menü (/)” parancsa ott, ahol a menü nem nyílhat, nem ír / jelet (T169)', () => {
    const kod = nezet('```\nx\n```', 5);
    expect(perjelNyit(kod)).toBe(false);
    expect(kod.state.doc.toString()).toBe('```\nx\n```');
    const szo = nezet('alma', 2);
    expect(perjelNyit(szo)).toBe(false);
    expect(szo.state.doc.toString()).toBe('alma');
    const ures = nezet('Elöl\n\n');
    expect(perjelNyit(ures)).toBe(true);
    expect(perjelNyitva(ures.state)).toBe(true);
    expect(ures.state.doc.toString()).toBe('Elöl\n\n/');
  });

  it('üres sorban a / megnyitja, a szűrő gépelésre szűkít, ↩ beírja a sablont', () => {
    const v = nezet('Elöl\n\n');
    gepel(v, '/');
    expect(perjelNyitva(v.state)).toBe(true);
    expect(elemek(v).length).toBeGreaterThan(20);
    gepel(v, 'h2');
    expect(elemek(v)[0]).toBe('Fejezet 2');
    const e = billentyu(v, 'Enter');
    expect(e.defaultPrevented).toBe(true);
    expect(v.state.doc.toString()).toBe('Elöl\n\n## ');
    expect(perjelNyitva(v.state)).toBe(false);
    expect(v.state.selection.main.head).toBe(v.state.doc.length);
  });

  it('↑↓ léptet, esc zár és a szöveg megmarad; a ⇥ is választ', () => {
    const v = nezet('');
    gepel(v, '/');
    const elso = v.dom.querySelector('.nt-menu-elem.aktiv .nt-menu-nev')!.textContent;
    billentyu(v, 'ArrowDown');
    expect(v.dom.querySelector('.nt-menu-elem.aktiv .nt-menu-nev')!.textContent).not.toBe(elso);
    billentyu(v, 'ArrowUp');
    expect(v.dom.querySelector('.nt-menu-elem.aktiv .nt-menu-nev')!.textContent).toBe(elso);
    const e = billentyu(v, 'Escape');
    expect(e.defaultPrevented).toBe(true);
    expect(perjelNyitva(v.state)).toBe(false);
    expect(v.state.doc.toString()).toBe('/');
    const w = nezet('');
    gepel(w, '/kod');
    billentyu(w, 'Tab');
    expect(w.state.doc.toString()).toBe('```\n\n```');
  });

  it('nem nyit kódban, szó közepén, képletben; szóköz után igen; elhagyva vagy törölve zár', () => {
    const kod = nezet('```\nx\n```', 5);
    gepel(kod, '/');
    expect(perjelNyitva(kod.state)).toBe(false);
    const szo = nezet('a');
    gepel(szo, '/');
    expect(perjelNyitva(szo.state)).toBe(false);
    const kep = nezet('$$\n\n$$', 3);
    gepel(kep, '/');
    expect(perjelNyitva(kep.state)).toBe(false);
    const szokoz = nezet('Szöveg ');
    gepel(szokoz, '/');
    expect(perjelNyitva(szokoz.state)).toBe(true);
    szokoz.dispatch({ selection: { anchor: 0 } });
    expect(perjelNyitva(szokoz.state)).toBe(false);
    const torol = nezet('');
    gepel(torol, '/');
    expect(perjelNyitva(torol.state)).toBe(true);
    torol.dispatch({ changes: { from: 0, to: 1 }, userEvent: 'delete.backward' });
    expect(perjelNyitva(torol.state)).toBe(false);
  });

  it('nincs találat: a menü ezt írja, az ↩ nem nyel el semmit; szóköz + találat nélkül zár', () => {
    const v = nezet('');
    gepel(v, '/qqqq');
    expect(perjelNyitva(v.state)).toBe(true);
    expect(v.dom.querySelector('.nt-menu-ures')!.textContent).toBe('Nincs találat');
    billentyu(v, 'Enter');
    expect(perjelNyitva(v.state)).toBe(false);
    expect(v.state.doc.toString()).toBe('/qqqq\n'); // a szerkesztő saját Entere futott
    const w = nezet('');
    gepel(w, '/qqqq ');
    expect(perjelNyitva(w.state)).toBe(false);
  });

  it('csak olvasható állapotban nem nyílik; az ARIA-állapot a szerkesztőn', () => {
    const o = nezet('', 0, true);
    o.dispatch({ changes: { from: 0, insert: '/' }, selection: { anchor: 1 }, userEvent: 'input.type' });
    expect(perjelNyitva(o.state)).toBe(false);
    const v = nezet('');
    gepel(v, '/');
    expect(v.contentDOM.getAttribute('aria-expanded')).toBe('true');
    expect(v.contentDOM.getAttribute('aria-activedescendant')).toMatch(/^nm-\d+-o0$/);
    billentyu(v, 'Escape');
    expect(v.contentDOM.getAttribute('aria-expanded')).toBeNull();
  });

  it('a callout-elem a regiszterből: a választás után a törzsben áll a kurzor', () => {
    const v = nezet('');
    gepel(v, '/warn');
    billentyu(v, 'Enter');
    expect(v.state.doc.toString()).toBe('> [!warning]\n> ');
  });
});

describe('lebegő eszköztár: feltételek, formázás, link', () => {
  it('egy blokkon belüli szövegkijelölésre engedett; több blokkra, kódra, képletre nem', () => {
    const v = nezet('Egy bekezdés szöveg.\n\nMásik.\n\n```js\nkód\n```\n\n$$\nx\n$$\n');
    const jelol = (a: number, b: number) => v.dispatch({ selection: EditorSelection.single(a, b) });
    jelol(3, 9);
    expect(eszkoztarEngedett(v.state)).toBe(true);
    jelol(3, 24);
    expect(eszkoztarEngedett(v.state)).toBe(false);
    const k = v.state.doc.toString().indexOf('kód');
    jelol(k, k + 3);
    expect(eszkoztarEngedett(v.state)).toBe(false);
    jelol(5, 5);
    expect(eszkoztarEngedett(v.state)).toBe(false);
    const w = nezet('Szöveg', 0, true);
    w.dispatch({ selection: EditorSelection.single(0, 3) });
    expect(eszkoztarEngedett(w.state)).toBe(false);
  });

  it('a gomb állapota a körbefogásból jön: a ** és a * külön, a ***x*** mindkettő', () => {
    const v = nezet('**félkövér** *dőlt* ***mindkettő*** sima ==kiemelt==');
    const szo = (s: string) => {
      const a = v.state.doc.toString().indexOf(s);
      v.dispatch({ selection: EditorSelection.single(a, a + s.length) });
    };
    szo('félkövér');
    expect([korbefogva(v.state, '**'), korbefogva(v.state, '*')]).toEqual([true, false]);
    szo('dőlt');
    expect([korbefogva(v.state, '**'), korbefogva(v.state, '*')]).toEqual([false, true]);
    szo('mindkettő');
    expect([korbefogva(v.state, '**'), korbefogva(v.state, '*')]).toEqual([true, true]);
    szo('sima');
    expect([korbefogva(v.state, '**'), korbefogva(v.state, '*'), korbefogva(v.state, '==')]).toEqual([false, false, false]);
    szo('kiemelt');
    expect(korbefogva(v.state, '==')).toBe(true);
  });

  it('a dőlt a félkövéren ***-ra bővül, és onnan egy lépéssel vissza', () => {
    const v = nezet('**x**');
    v.dispatch({ selection: EditorSelection.single(2, 3) });
    korbefog(v, '*');
    expect(v.state.doc.toString()).toBe('***x***');
    korbefog(v, '*');
    expect(v.state.doc.toString()).toBe('**x**');
    korbefog(v, '**');
    expect(v.state.doc.toString()).toBe('x');
  });

  it('link: az URL kódolása, a meglévő link felismerése', () => {
    expect(urlKodol(' https://pelda.hu/a b(c) ')).toBe('https://pelda.hu/a%20b%28c%29');
    const v = nezet('Lásd [a lap](https://pelda.hu) most.');
    const a = v.state.doc.toString().indexOf('a lap');
    v.dispatch({ selection: EditorSelection.single(a, a + 5) });
    const l = linkAdat(v.state)!;
    expect(l.szoveg).toBe('a lap');
    expect(l.url).toBe('https://pelda.hu');
    expect(v.state.sliceDoc(l.from, l.to)).toBe('[a lap](https://pelda.hu)');
    v.dispatch({ selection: EditorSelection.single(0, 4) });
    expect(linkAdat(v.state)).toBeNull();
  });
});

describe('blokkparancsok', () => {
  it('Alt+↓ / Alt+↑: a blokk a szomszédja mögé / elé kerül', () => {
    const v = nezet('A\n\nB\n\nC\n', 0);
    const e = billentyu(v, 'ArrowDown', { altKey: true });
    expect(e.defaultPrevented).toBe(true);
    expect(v.state.doc.toString()).toBe('B\n\nA\n\nC\n');
    billentyu(v, 'ArrowUp', { altKey: true });
    expect(v.state.doc.toString()).toBe('A\n\nB\n\nC\n');
    const l = nezet('- a\n- b\n', 0);
    blokkLep(l, 1);
    expect(l.state.doc.toString()).toBe('- b\n- a\n');
    const hatar = nezet('A\n\nB\n', 0);
    expect(blokkLep(hatar, -1)).toBe(true);
    expect(hatar.state.doc.toString()).toBe('A\n\nB\n');
  });

  it('a szomszéd-cél: a lista egy egység, a testvér a listán belül; érvényes célok', () => {
    const v = nezet('P\n\n- a\n\t- a1\n- b\n\nQ\n');
    const bl = blokkok(v.state);
    const P = bl[0];
    const Q = bl[bl.length - 1];
    expect(szomszedCel(bl, P, 1)!.hely).toBe('utan');
    expect(szomszedCel(bl, P, 1)!.blokk.index).toBe(3); // a lista utolsó legfelső eleme
    expect(szomszedCel(bl, Q, -1)!.blokk.index).toBe(1); // a lista első eleme
    expect(szomszedCel(bl, bl[1], -1)).toBeNull(); // a lista első eleme: nincs testvér fölötte
    expect(celErvenyes(bl, bl[1], { blokk: bl[2], hely: 'utan' })).toBe(false); // a saját gyereke
    expect(celErvenyes(bl, P, { blokk: bl[2], hely: 'elott' })).toBe(false); // szöveg nem lista belsejébe
    expect(celErvenyes(bl, bl[3], { blokk: bl[1], hely: 'gyerek' })).toBe(true);
  });

  it('link másolása: ^id a sorvégre, [[Név#^id]] a vágólapra; a meglévő azonosító marad', async () => {
    const irt: string[] = [];
    vi.stubGlobal('navigator', { clipboard: { writeText: async (s: string) => void irt.push(s) } });
    const v = nezet('Bekezdés\n\nMásik ^van\n', 2);
    expect(await blokkLinkMasol(v)).toBe(true);
    const id = /Bekezdés \^([a-z0-9]{6})/.exec(v.state.doc.toString())![1];
    expect(irt[0]).toBe(`[[Jegyzet#^${id}]]`);
    v.dispatch({ selection: { anchor: v.state.doc.toString().indexOf('Másik') } });
    expect(await blokkLinkMasol(v)).toBe(true);
    expect(irt[1]).toBe('[[Jegyzet#^van]]');
    expect(v.state.doc.toString().match(/\^van/g)).toHaveLength(1);
    // visszavonás: az azonosító is el kell tűnjön, egy lépésben
    undo(v);
    expect(v.state.doc.toString()).toBe('Bekezdés\n\nMásik ^van\n');
    vi.unstubAllGlobals();
  });
});

describe('a közös menü', () => {
  const elemek: MenuElem[] = [
    { id: 'a', nev: 'Első' },
    { id: 'b', nev: 'Tiltott', letiltva: true },
    { id: 'c', nev: 'Almenü', almenu: () => [{ id: 'c1', nev: 'Belső egy' }, { id: 'c2', nev: 'Belső kettő', kijelolt: true }] },
    { id: 'd', nev: 'Utolsó' },
  ];

  it('a léptetés körbefordul és átugorja a letiltottat; Enter választ; az almenübe → lép, ← vagy esc vissza', () => {
    const valasztott: string[] = [];
    const m = new Menu({ cimke: 'próba', onValaszt: (e) => valasztott.push(e.id) });
    m.beallit(elemek);
    const k = (key: string, o: KeyboardEventInit = {}) => m.billentyu(new KeyboardEvent('keydown', { key, ...o }));
    expect(m.aktivElem!.id).toBe('a');
    k('ArrowDown');
    expect(m.aktivElem!.id).toBe('c');
    k('ArrowDown');
    k('ArrowDown');
    expect(m.aktivElem!.id).toBe('a');
    k('ArrowUp');
    expect(m.aktivElem!.id).toBe('d');
    k('ArrowUp');
    k('ArrowRight');
    expect(m.szint).toBe(1);
    expect(m.aktivElem!.id).toBe('c2'); // a jelenlegi (kijelölt) elemen áll
    expect(m.elem.querySelector('.nt-menu-vissza')!.textContent).toBe('Almenü');
    k('ArrowLeft');
    expect(m.szint).toBe(0);
    k('ArrowRight');
    expect(k('Escape')).toBe(true);
    expect(m.szint).toBe(0);
    expect(k('Escape')).toBe(false); // a gyökérben a hívó zár
    k('ArrowDown');
    k('Enter');
    expect(valasztott).toEqual(['d']);
    expect(k('F5')).toBe(false);
    expect(k('Enter', { metaKey: true })).toBe(false);
  });

  it('ARIA: listbox, option, aria-selected, aria-disabled; a kiemelés <mark>', () => {
    const m = new Menu({ cimke: 'próba', onValaszt: () => {} });
    m.beallit([{ id: 'a', nev: 'Fejezet', kiemeles: [[0, 3]] }, { id: 'b', nev: 'Tilt', letiltva: true }]);
    expect(m.elem.querySelector('[role="listbox"]')!.getAttribute('aria-label')).toBe('próba');
    const o = m.elem.querySelectorAll('[role="option"]');
    expect(o[0].getAttribute('aria-selected')).toBe('true');
    expect(o[1].getAttribute('aria-disabled')).toBe('true');
    expect(o[0].querySelector('mark')!.textContent).toBe('Fej');
    expect(m.aktivId).toBe(o[0].id);
  });
});

// ---------------------------------------------------------------------- táblázat

const TABLA = '| a | b |\n|---|:-:|\n| 1 | 2 |\n';

function tabla(v: EditorView): HTMLElement {
  return v.dom.querySelector<HTMLElement>('.nt-tabla')!;
}

function cella(v: EditorView, sor: number, oszlop: number): HTMLElement {
  return tabla(v).querySelector<HTMLElement>(`[data-sor="${sor}"][data-oszlop="${oszlop}"]`)!;
}

function irCellaba(v: EditorView, sor: number, oszlop: number, szoveg: string, gomb: 'Enter' | 'Tab' | 'Escape' = 'Enter', opciok: KeyboardEventInit = {}) {
  cella(v, sor, oszlop).click();
  const i = tabla(v).querySelector<HTMLInputElement>('input.nt-cella-mezo')!;
  i.value = szoveg;
  i.dispatchEvent(new KeyboardEvent('keydown', { key: gomb, bubbles: true, cancelable: true, ...opciok }));
}

describe('táblázat: vizuális szerkesztő', () => {
  it('a táblázat helyén a szerkesztő áll, minden cellának helye és fogója van', () => {
    const v = nezet('Elöl\n\n' + TABLA, 0);
    expect(tabla(v)).not.toBeNull();
    expect(v.dom.querySelectorAll('.nt-tabla td, .nt-tabla th').length).toBe(4);
    expect(tabla(v).querySelectorAll('.nt-oszlop-fogo').length).toBe(2);
    expect(tabla(v).querySelectorAll('.nt-sor-fogo').length).toBe(1);
    expect(tabla(v).querySelectorAll('.nt-plusz').length).toBe(2);
    expect(cella(v, 1, 1).style.textAlign).toBe('center');
  });

  it('a cella szerkesztése Enterrel ment: egy tranzakció, az újraigazított táblázat; ⌘Z visszaadja', () => {
    const v = nezet('Elöl\n\n' + TABLA, 0);
    irCellaba(v, 1, 0, 'hosszú|érték', 'Tab');
    const h = 'hosszú\\|érték';
    expect(v.state.doc.toString()).toBe(`Elöl\n\n| ${'a'.padEnd(h.length)} |  b  |\n| ${'-'.repeat(h.length)} | :-: |\n| ${h} |  2  |\n`);
    undo(v);
    expect(v.state.doc.toString()).toBe('Elöl\n\n' + TABLA);
  });

  it('Esc elveti, a változatlan érték nem ír', () => {
    const v = nezet(TABLA, 0);
    irCellaba(v, 1, 0, 'eldobott', 'Escape');
    expect(v.state.doc.toString()).toBe(TABLA);
    irCellaba(v, 1, 0, '1', 'Tab'); // változatlan érték: a Tab csak lép, nem ír
    expect(v.state.doc.toString()).toBe(TABLA);
  });

  it('Tab a következő cellára lép; az utolsó után új sor jön; a képlet | jele megmarad', () => {
    const v = nezet(TABLA, 0);
    irCellaba(v, 1, 1, '$|x|$', 'Tab');
    expect(v.state.doc.toString()).toBe('| a   |   b   |\n| --- | :---: |\n| 1   | $|x|$ |\n|     |       |\n');
  });

  it('az utolsó sorban az Enter új sort ad (a cella értékével együtt, egy lépésben)', () => {
    const v = nezet(TABLA, 0);
    irCellaba(v, 1, 0, 'x', 'Enter');
    expect(v.state.doc.toString()).toBe('| a   |  b  |\n| --- | :-: |\n| x   |  2  |\n|     |     |\n');
    undo(v);
    expect(v.state.doc.toString()).toBe(TABLA);
  });

  it('a sor- és oszlopmenü műveletei: beszúrás, igazítás, törlés', () => {
    const v = nezet(TABLA, 0);
    // az oszlop menüje: a fogó kattintására a body-n lebegő menü nyílik
    tabla(v).querySelector<HTMLElement>('.nt-oszlop-fogo')!.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, button: 0 }));
    tabla(v).querySelector<HTMLElement>('.nt-oszlop-fogo')!.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, button: 0 }));
    const menu = document.body.querySelector('.nt-lebego')!;
    expect(menu).not.toBeNull();
    const nevek = [...menu.querySelectorAll('.nt-menu-nev')].map((e) => e.textContent);
    expect(nevek).toEqual(['Beszúrás balra', 'Beszúrás jobbra', 'Igazítás', 'Duplikálás', 'Mozgatás balra', 'Mozgatás jobbra', 'Oszlop törlése']);
    // Mozgatás jobbra
    [...menu.querySelectorAll<HTMLElement>('.nt-menu-elem')].find((e) => e.textContent!.includes('Mozgatás jobbra'))!.click();
    expect(v.state.doc.toString()).toBe('|  b  | a   |\n| :-: | --- |\n|  2  | 1   |\n');
  });

  it('a + gomb új sort és új oszlopot ad', () => {
    const v = nezet(TABLA, 0);
    tabla(v).querySelector<HTMLElement>('.nt-plusz-sor')!.click();
    expect(v.state.doc.toString()).toBe('| a   |  b  |\n| --- | :-: |\n| 1   |  2  |\n|     |     |\n');
    tabla(v).querySelector<HTMLElement>('.nt-plusz-oszlop')!.click();
    expect(v.state.doc.toString().split('\n')[0]).toBe('| a   |  b  | Oszlop 3 |');
  });

  it('idézetben álló táblázat: az előtag megmarad', () => {
    const v = nezet('> [!note]\n> | a | b |\n> |---|---|\n> | 1 | 2 |\n', 0);
    irCellaba(v, 1, 0, 'x', 'Tab');
    expect(v.state.doc.toString()).toBe('> [!note]\n> | a   | b   |\n> | --- | --- |\n> | x   | 2   |\n');
  });

  it('listába ágyazott táblázat: a cella átírása a környező sorokat és a többi cellát bájtra őrzi; ⌘Z visszaadja', () => {
    const elo = 'Elöl\n\n- | a | b |\n  |---|---|\n  | 1 | 2 |\n\nUtána\n';
    const v = nezet(elo, 0);
    expect(tabla(v)).not.toBeNull();
    irCellaba(v, 1, 0, 'x', 'Tab');
    expect(v.state.doc.toString()).toBe('Elöl\n\n- | a   | b   |\n  | --- | --- |\n  | x   | 2   |\n\nUtána\n');
    undo(v);
    expect(v.state.doc.toString()).toBe(elo);
  });

  it('listajelölős, számozott és idézetbe ágyazott listás táblázat: a jelölő csak az első sor előtt áll', () => {
    for (const [elso, tobbi] of [['* ', '  '], ['+ ', '  '], ['1. ', '   '], ['1) ', '   '], ['> - ', '>   ']] as const) {
      const elo = `Elöl\n\n${elso}| a | b |\n${tobbi}|---|---|\n${tobbi}| 1 | 2 |\n\nUtána\n`;
      const v = nezet(elo, 0);
      irCellaba(v, 1, 0, 'xy', 'Tab');
      expect(v.state.doc.toString(), elso).toBe(`Elöl\n\n${elso}| a   | b   |\n${tobbi}| --- | --- |\n${tobbi}| xy  | 2   |\n\nUtána\n`);
      tisztit();
    }
  });

  it('a fejlécnél hosszabb sor extra cellája a szomszéd cella átírása után is megmarad', () => {
    const elo = 'Elöl\n\n| a | b |\n|---|---|\n| 1 | 2 | 3 |\n| 4 | 5 |\n\nUtána\n';
    const v = nezet(elo, 0);
    irCellaba(v, 2, 0, 'x', 'Tab');
    expect(v.state.doc.toString()).toBe('Elöl\n\n| a   | b   |\n| --- | --- |\n| 1   | 2   | 3 |\n| x   | 5   |\n\nUtána\n');
  });

  it('csak olvasható: nincs szerkesztés, nincs fogó', () => {
    const v = nezet(TABLA, 0, true);
    expect(tabla(v).querySelector('.nt-fogo-sav, .nt-plusz')).toBeNull();
    cella(v, 1, 0).click();
    expect(tabla(v).querySelector('input')).toBeNull();
  });

  it('a nyilak az üres sorból a táblázatra lépnek; a táblázat után álló blokk Backspace-e nem fűzi bele a szöveget', () => {
    const v = nezet('Elöl\n\n' + TABLA, 5);
    const e = billentyu(v, 'ArrowDown');
    expect(e.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(cella(v, 0, 0));
    const w = nezet(TABLA + '# Cím\n', 0);
    const cim = w.state.doc.toString().indexOf('# Cím');
    w.dispatch({ selection: { anchor: cim } });
    const be = billentyu(w, 'Backspace');
    expect(be.defaultPrevented).toBe(true);
    expect(w.state.doc.toString()).toBe(TABLA + '# Cím\n');
    expect(document.activeElement).toBe(cella(w, 1, 0));
    expect(tablaFokusz(w, 0, 0, 1)).toBe(true);
    expect(document.activeElement).toBe(cella(w, 0, 1));
  });
});

// A kézi kör F2-je (C10.7): a szerkesztett cellából másik cellára kattintva az első kattintás csak kilépett, és
// a gépelt szöveg pipe nélküli sorként a táblázat alá került (az üres sor eltűnt).
describe('táblázat: cellaváltás és gépelés a táblázat mellett (F2)', () => {
  const T = '| a | b |\n|---|:-:|\n| 1 | 2 |';

  /** A dokumentum táblázatainak szövege (a Lezer-elemzés szerint). */
  function tablak(v: EditorView): string[] {
    const ki: string[] = [];
    teljesFa(v.state).iterate({
      enter(n) {
        if (n.name === 'Table') ki.push(v.state.sliceDoc(n.from, n.to));
      },
    });
    return ki;
  }

  it('szerkesztett cellából egy kattintás a másik cellára vált; a WebKit fókuszvesztése sem viszi el a célt', async () => {
    const v = nezet('Elöl\n\n' + T + '\n\nUtána\n', 0);
    cella(v, 1, 0).click();
    tabla(v).querySelector<HTMLInputElement>('input.nt-cella-mezo')!.value = 'A1';
    const cel = cella(v, 1, 1);
    const le = new MouseEvent('mousedown', { bubbles: true, cancelable: true, button: 0 });
    cel.dispatchEvent(le);
    // a WebKit a contenteditable-en belüli kattintásnál a fókuszt a szerkesztő gyökerének adja
    if (!le.defaultPrevented) v.contentDOM.focus();
    await new Promise((r) => setTimeout(r, 0));
    cel.click();
    expect(le.defaultPrevented).toBe(true);
    await vi.waitFor(() => {
      const i = tabla(v).querySelector<HTMLInputElement>('input.nt-cella-mezo');
      expect(i).not.toBeNull();
      expect(document.activeElement).toBe(i);
      expect(i!.closest<HTMLElement>('td, th')!.dataset).toMatchObject({ sor: '1', oszlop: '1' });
    });
    expect(v.state.doc.toString()).toBe('Elöl\n\n| a   |  b  |\n| --- | :-: |\n| A1  |  2  |\n\nUtána\n');
    const i = tabla(v).querySelector<HTMLInputElement>('input.nt-cella-mezo')!;
    i.value = 'B1';
    i.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true, cancelable: true }));
    expect(v.state.doc.toString()).toBe('Elöl\n\n| a   |  b  |\n| --- | :-: |\n| A1  | B1  |\n\nUtána\n');
  });

  it('a táblázat utolsó sorának végén és az alatta álló üres sorban gépelve új bekezdés lesz; a táblázat ép', () => {
    const doc = 'Elöl\n\n' + T + '\n\nUtána\n';
    const to = doc.indexOf('\n\nUtána');
    for (const kurzor of [to, to + 1]) {
      const v = nezet(doc, kurzor);
      gepel(v, 'Z3');
      expect(v.state.doc.toString(), String(kurzor)).toBe('Elöl\n\n' + T + '\n\nZ3\n\nUtána\n');
      expect(tablak(v)).toEqual([T]);
      undo(v);
      expect(v.state.doc.toString()).toBe(doc);
    }
  });

  it('a táblázat első sorának elején gépelve a szöveg elé kerül, üres sorral', () => {
    const v = nezet('Elöl\n\n' + T + '\n', 6);
    gepel(v, 'Z3');
    expect(v.state.doc.toString()).toBe('Elöl\n\nZ3\n\n' + T + '\n');
    expect(tablak(v)).toEqual([T]);
    const w = nezet('Elöl\n' + T + '\n', 5);
    gepel(w, 'Z');
    expect(w.state.doc.toString()).toBe('Elöl\n\nZ\n\n' + T + '\n');
  });

  it('a dokumentum végén álló táblázat mögött és közvetlenül alatta álló szöveg előtt is', () => {
    const v = nezet(T, T.length);
    gepel(v, 'Z3');
    expect(v.state.doc.toString()).toBe(T + '\n\nZ3');
    const w = nezet(T + '\n\n', T.length + 1);
    gepel(w, 'Z');
    expect(w.state.doc.toString()).toBe(T + '\n\nZ\n');
    expect(tablak(w)).toEqual([T]);
  });
});

describe('blokktörlés és ⌘Z (T170)', () => {
  it('a blokktörlés saját visszavonási lépés: nem olvad össze az előtte tett Backspace-szel', () => {
    const v = nezet('Első\n\nMásodik bekezdés\n\nHarmadik', 'Első\n\nMásodik bekezdés'.length);
    const r = v.state.selection.main.head;
    v.dispatch({ changes: { from: r - 1, to: r }, selection: { anchor: r - 1 }, userEvent: 'delete.backward' });
    expect(blokkTorol(v)).toBe(true);
    expect(v.state.doc.toString()).not.toContain('Második');
    undo(v);
    expect(v.state.doc.toString()).toBe('Első\n\nMásodik bekezdé\n\nHarmadik');
    undo(v);
    expect(v.state.doc.toString()).toBe('Első\n\nMásodik bekezdés\n\nHarmadik');
  });
});
