// A fájlfa adatmodellje (C11a): magyar ábécérend, mappák elöl, számlálók, üres mappák, a nyitott mappák szerinti lapítás,
// és az áthelyezés szabályai.

import { describe, expect, it } from 'vitest';
import type { FajlInfo, FajlTipus } from '../src/lib/vault/fajlok.svelte';
import { athelyezettUt, athelyezheto, faEpit, lapit, nevHasonlit, osMappak } from '../src/lib/vault/fa';

const f = (ut: string, tipus: FajlTipus = 'md'): FajlInfo => ({ ut, tipus, meret: 1, mtime: 1 });

describe('magyar ábécérend', () => {
  it('az ékezetes betűk a párjuk mellett, a digráfok (cs, gy, ly, sz, zs) külön betűként', () => {
    const nevek = ['Zebra', 'Csoport', 'Cukor', 'Árvíz', 'Alma', 'Dió', 'Gyöngy', 'Gomba', 'Őz', 'Olaj', 'Szél', 'Sör', 'Zsír', 'Zöld'];
    expect([...nevek].sort(nevHasonlit)).toEqual(['Alma', 'Árvíz', 'Cukor', 'Csoport', 'Dió', 'Gomba', 'Gyöngy', 'Olaj', 'Őz', 'Sör', 'Szél', 'Zebra', 'Zöld', 'Zsír']);
  });

  it('a számok értékük szerint: 02 előbb, mint 10', () => {
    expect(['10 - Zárás', '2 - Második', '02 - Első', '1 - Nulla'].sort(nevHasonlit)).toEqual(['1 - Nulla', '02 - Első', '2 - Második', '10 - Zárás']);
  });

  it('kis-nagybetűre nem érzékeny az első szinten', () => {
    expect(['b', 'A', 'a', 'B'].sort(nevHasonlit)).toEqual(['a', 'A', 'b', 'B']);
  });
});

describe('faEpit', () => {
  const lista = [
    f('Zöld.md'),
    f('Árvíz.md'),
    f('F02 - Dinamika/Elmélet/10 - Vége.md'),
    f('F02 - Dinamika/Elmélet/02 - Newton II. törvénye.md'),
    f('F02 - Dinamika/Elmélet/ábra.png', 'kep'),
    f('F02 - Dinamika/Vászon.canvas', 'canvas'),
    f('Alma.md'),
    f('ATTCHMNTS/foto.jpg', 'kep'),
  ];
  const mappak = ['ATTCHMNTS', 'F02 - Dinamika', 'F02 - Dinamika/Elmélet', 'Üres', 'Üres/Alsó'];
  const fa = faEpit(lista, mappak);

  it('a mappák elöl, magyar sorrendben; utánuk a fájlok, a jegyzet kiterjesztés nélkül', () => {
    expect(fa.gyerekek.map((g) => `${g.mappa ? '▸' : ''}${g.nev}`)).toEqual(['▸ATTCHMNTS', '▸F02 - Dinamika', '▸Üres', 'Alma', 'Árvíz', 'Zöld']);
    const elmelet = fa.gyerekek[1].gyerekek[0];
    expect(elmelet.gyerekek.map((g) => g.nev)).toEqual(['02 - Newton II. törvénye', '10 - Vége', 'ábra.png']);
  });

  it('a számláló a teljes részfa fájljait és jegyzeteit adja', () => {
    const dinamika = fa.gyerekek[1];
    expect([dinamika.fajlok, dinamika.jegyzetek]).toEqual([4, 3]);
    expect([fa.fajlok, fa.jegyzetek]).toEqual([8, 6]);
    const foto = fa.gyerekek[0];
    expect([foto.fajlok, foto.jegyzetek]).toEqual([1, 0]);
  });

  it('az üres mappa is látszik, nullával', () => {
    const ures = fa.gyerekek[2];
    expect(ures.nev).toBe('Üres');
    expect(ures.gyerekek.map((g) => g.nev)).toEqual(['Alsó']);
    expect([ures.fajlok, ures.gyerekek[0].fajlok]).toEqual([0, 0]);
  });

  it('a fájl szülőmappája a mappalistából hiányozva is létrejön', () => {
    const t = faEpit([f('Új/Mély/x.md')], []);
    expect(t.gyerekek[0].ut).toBe('Új');
    expect(t.gyerekek[0].gyerekek[0].gyerekek[0].ut).toBe('Új/Mély/x.md');
    expect(t.fajlok).toBe(1);
  });

  it('üres vault', () => {
    const t = faEpit([], []);
    expect([t.gyerekek.length, t.fajlok]).toEqual([0, 0]);
  });
});

describe('lapit', () => {
  const fa = faEpit([f('A/b.md'), f('A/C/d.md'), f('e.md')], ['A', 'A/C']);

  it('zárt mappáknál csak a gyökér gyerekei', () => {
    const sorok = lapit(fa, new Set());
    expect(sorok.map((s) => s.cs.ut)).toEqual(['A', 'e.md']);
  });

  it('a nyitott mappák gyerekei mélységgel és hellyel', () => {
    const sorok = lapit(fa, new Set(['A', 'A/C']));
    expect(sorok.map((s) => [s.cs.ut, s.melyseg])).toEqual([['A', 0], ['A/C', 1], ['A/C/d.md', 2], ['A/b.md', 1], ['e.md', 0]]);
    expect([sorok[1].hely, sorok[1].testverek]).toEqual([1, 2]);
  });

  it('a zárt szülő alatti nyitott mappa nem látszik', () => {
    expect(lapit(fa, new Set(['A/C'])).map((s) => s.cs.ut)).toEqual(['A', 'e.md']);
  });
});

describe('útsegédek és az áthelyezés szabályai', () => {
  it('osMappak', () => {
    expect(osMappak('a/b/c.md')).toEqual(['a', 'a/b']);
    expect(osMappak('c.md')).toEqual([]);
  });

  it('athelyezettUt', () => {
    expect(athelyezettUt('a/b/c.md', 'x')).toBe('x/c.md');
    expect(athelyezettUt('a/b/c.md', '')).toBe('c.md');
  });

  it('athelyezheto: nem önmagába, nem a saját részfájába, nem a mostani szülőbe', () => {
    expect(athelyezheto('a/b', true, 'a/b')).toBe(false);
    expect(athelyezheto('a/b', true, 'a/b/c')).toBe(false);
    expect(athelyezheto('a/b', true, 'a')).toBe(false); // már ott van
    expect(athelyezheto('a/b', true, 'x')).toBe(true);
    expect(athelyezheto('a/b', true, 'a/bb')).toBe(true); // előtag-hasonlóság nem részfa
    expect(athelyezheto('a/b.md', false, 'a')).toBe(false);
    expect(athelyezheto('a/b.md', false, '')).toBe(true);
    expect(athelyezheto('b.md', false, '')).toBe(false);
  });
});
