// A nézet-beállítások, a cellaszerkesztés és a Kanban tiszta függvényei (C12b 8–10. lépés).

import { describe, expect, it } from 'vitest';
import { bevitelbol, fajta, iroTipus, kezdoSzoveg, valtozatlan } from '../src/bazis/cellaErtek';
import { csoportKulcs, ejtesErtek, irhatoErtek, oszlopok } from '../src/bazis/kanban';
import {
  csoport,
  csoportBeallit,
  egeszBevitel,
  oszlopKapcsol,
  oszlopMozgat,
  osszesitoBeallit,
  rendezesBeallit,
  rendezesek,
  rendezesValt,
  szelessegBeallit,
  szelessegKorlat,
} from '../src/bazis/muveletek';
import type { Csoport, Sor, Valasz } from '../src/bazis/tipusok';

function valasz(beallitas: Record<string, unknown>, kieg: Partial<Valasz> = {}): Valasz {
  return {
    ok: true,
    nezetek: [{ nev: 'N', tipus: 'table', ismert: true }],
    nezet: { index: 0, nev: 'N', tipus: 'table', eredeti_tipus: 'table', beallitas },
    oszlopok: [],
    sorok: [],
    csoportok: null,
    osszesitok: {},
    osszes: 0,
    levagva: false,
    hibak: [],
    figyelmeztetesek: [],
    ido_ms: 1,
    generacio: 1,
    ...kieg,
  };
}

describe('rendezés', () => {
  it('a kattintás körbejár: nincs → növekvő → csökkenő → nincs', () => {
    let r = rendezesValt([], 'Rating', false);
    expect(r).toEqual([{ property: 'Rating', direction: 'ASC' }]);
    r = rendezesValt(r, 'Rating', false);
    expect(r).toEqual([{ property: 'Rating', direction: 'DESC' }]);
    expect(rendezesValt(r, 'Rating', false)).toEqual([]);
  });

  it('kattintás egy másik oszlopra az egyetlen rendezést cseréli; ⇧ hozzáad, a helyén vált, és töröl', () => {
    const elso = [{ property: 'A', direction: 'ASC' as const }];
    expect(rendezesValt(elso, 'B', false)).toEqual([{ property: 'B', direction: 'ASC' }]);
    const ketto = rendezesValt(elso, 'B', true);
    expect(ketto.map((x) => x.property)).toEqual(['A', 'B']);
    const valtott = rendezesValt(ketto, 'A', true);
    expect(valtott).toEqual([
      { property: 'A', direction: 'DESC' },
      { property: 'B', direction: 'ASC' },
    ]);
    expect(rendezesValt(valtott, 'A', true)).toEqual([{ property: 'B', direction: 'ASC' }]);
  });

  it('a nyers `sort` kulcsból olvassa a sorrendet, az érvénytelen bejegyzést kihagyja', () => {
    const v = valasz({ sort: [{ property: 'A', direction: 'desc' }, { x: 1 }, 'szoveg', { property: 'B' }] });
    expect(rendezesek(v)).toEqual([
      { property: 'A', direction: 'DESC' },
      { property: 'B', direction: 'ASC' },
    ]);
    expect(rendezesek(valasz({}))).toEqual([]);
  });

  it('az üres rendezés törli a kulcsot (null)', () => {
    expect(rendezesBeallit(2, [])).toEqual({ fajta: 'nezet_beallit', nezet: 2, kulcs: 'sort', ertek: null });
  });
});

describe('oszlopok és méret', () => {
  it('mozgatás: a cél a többi elem eltávolítása utáni index', () => {
    expect(oszlopMozgat(['a', 'b', 'c', 'd'], 'a', 2)).toEqual(['b', 'c', 'a', 'd']);
    expect(oszlopMozgat(['a', 'b', 'c', 'd'], 'd', 0)).toEqual(['d', 'a', 'b', 'c']);
    expect(oszlopMozgat(['a', 'b'], 'x', 0)).toEqual(['a', 'b']);
    expect(oszlopMozgat(['a', 'b'], 'a', 99)).toEqual(['b', 'a']);
  });

  it('kijelölés és elrejtés a sorrend megtartásával', () => {
    expect(oszlopKapcsol(['a', 'b'], 'c', true)).toEqual(['a', 'b', 'c']);
    expect(oszlopKapcsol(['a', 'b'], 'a', true)).toEqual(['a', 'b']);
    expect(oszlopKapcsol(['a', 'b', 'c'], 'b', false)).toEqual(['a', 'c']);
  });

  it('a szélesség 60 és 900 px közé szorul, egészre kerekítve', () => {
    expect(szelessegKorlat(10)).toBe(60);
    expect(szelessegKorlat(2000)).toBe(900);
    expect(szelessegKorlat(200.6)).toBe(201);
    expect(szelessegBeallit(1, 'Rating', 5)).toEqual({ fajta: 'nezet_beallit', nezet: 1, kulcs: 'columnSize', alkulcs: 'Rating', ertek: 60 });
  });

  it('összesítő és csoport műveletei', () => {
    expect(osszesitoBeallit(0, 'Rating', 'Average')).toEqual({ fajta: 'nezet_beallit', nezet: 0, kulcs: 'summaries', alkulcs: 'Rating', ertek: 'Average' });
    expect((csoportBeallit(0, 'Status', 'DESC') as { ertek: unknown }).ertek).toEqual({ property: 'Status', direction: 'DESC' });
    expect((csoportBeallit(0, null) as { ertek: unknown }).ertek).toBeNull();
    expect(csoport(valasz({ groupBy: { property: 'Status' } }))).toEqual({ property: 'Status', direction: 'ASC' });
    expect(csoport(valasz({}))).toBeNull();
  });

  it('pozitív egész bevitel', () => {
    expect(egeszBevitel('')).toBeNull();
    expect(egeszBevitel(' 420 ')).toBe(420);
    expect(egeszBevitel('0')).toBeUndefined();
    expect(egeszBevitel('-3')).toBeUndefined();
    expect(egeszBevitel('1,5')).toBeUndefined();
    expect(egeszBevitel('x')).toBeUndefined();
  });
});

describe('cella-értékek', () => {
  it('a szerkesztő fajtája az oszlop típusából; a Status mindig választó', () => {
    expect(fajta('number', 'Rating')).toBe('szam');
    expect(fajta('checkbox', 'Done')).toBe('jelolo');
    expect(fajta('date', 'D')).toBe('datum');
    expect(fajta('datetime', 'D')).toBe('datumido');
    expect(fajta('tags', 'Tags')).toBe('lista');
    expect(fajta('text', 'Status')).toBe('valaszto');
    expect(fajta('text', 'X', ['a'])).toBe('lista');
    expect(fajta('text', 'X', 'a')).toBe('szoveg');
    expect(iroTipus('formula')).toBeUndefined();
    expect(iroTipus('tags')).toBe('tags');
  });

  it('kezdőszöveg a nyers értékből: lista vesszővel, dátum a mező alakjában', () => {
    expect(kezdoSzoveg('lista', ['a', 'b'])).toBe('a, b');
    expect(kezdoSzoveg('lista', null)).toBe('');
    expect(kezdoSzoveg('datum', '2024-05-01')).toBe('2024-05-01');
    expect(kezdoSzoveg('datumido', '2024-05-01 10:30')).toBe('2024-05-01T10:30');
    expect(kezdoSzoveg('szoveg', 5)).toBe('5');
  });

  it('a bevitel értékké: szám (magyar tizedesvesszővel), lista, link-kulcsok wikilinkké, üres = üres érték', () => {
    expect(bevitelbol('szam', '3,5', 'Rating')).toEqual({ ertek: 3.5 });
    expect(bevitelbol('szam', '', 'Rating')).toEqual({ ertek: '' });
    expect(bevitelbol('szam', 'x', 'Rating')).toEqual({ hiba: 'Ez nem szám.' });
    expect(bevitelbol('lista', 'a, b ,, c', 'Tags')).toEqual({ ertek: ['a', 'b', 'c'] });
    expect(bevitelbol('lista', 'Alap, [[Más]]', 'NN')).toEqual({ ertek: ['[[Alap]]', '[[Más]]'] });
    expect(bevitelbol('szoveg', ' Cél ', 'Source')).toEqual({ ertek: '[[Cél]]' });
    expect(bevitelbol('szoveg', '  ', 'Cím')).toEqual({ ertek: '' });
  });

  it('változatlan szerkesztés: a lista sorrendje és szóköze számít, a szóközök nem', () => {
    expect(valtozatlan('szoveg', 'a ', 'a')).toBe(true);
    expect(valtozatlan('lista', 'a, b', 'a,b')).toBe(true);
    expect(valtozatlan('lista', 'a, b', 'b, a')).toBe(false);
  });
});

describe('Kanban', () => {
  const sorok: Sor[] = ['A', 'B', 'C'].map((n) => ({ ut: `${n}.md`, nev: n, md: true, cellak: [] }));
  const cs = (kulcs: Csoport['kulcs'], tol: number, db: number, huzhato = true): Csoport => ({
    kulcs,
    cimke: typeof kulcs === 'string' ? kulcs : '',
    tol,
    db,
    osszesitok: {},
    huzhato,
  });

  it('a csoportosító tulajdonság kulcsa; a file.* és a képlet nem írható', () => {
    expect(csoportKulcs(valasz({ groupBy: { property: 'note.Status' } }))).toBe('Status');
    expect(csoportKulcs(valasz({ groupBy: { property: 'Status' } }))).toBe('Status');
    expect(csoportKulcs(valasz({ groupBy: { property: 'file.folder' } }))).toBeNull();
    expect(csoportKulcs(valasz({ groupBy: { property: 'formula.x' } }))).toBeNull();
    expect(csoportKulcs(valasz({}))).toBeNull();
  });

  it('az oszlopok a csoportokból; a „Nincs érték” üres értékű, és üres értéket ír', () => {
    const v = valasz({ groupBy: { property: 'Status' } }, { sorok, csoportok: [cs(null, 0, 1), cs('Kész', 1, 2)] });
    const o = oszlopok(v);
    expect(o.map((x) => [x.cimke, x.sorok.length, x.fogad])).toEqual([
      ['Nincs érték', 1, true],
      ['Kész', 2, true],
    ]);
    expect(ejtesErtek(o[0])).toBe('');
    expect(ejtesErtek(o[1])).toBe('Kész');
  });

  it('Status: a séma sorrendje, a hiányzó értékek üres oszlopként is', () => {
    const v = valasz({ groupBy: { property: 'Status' } }, { sorok, csoportok: [cs(null, 0, 1), cs('Review', 1, 2)] });
    const o = oszlopok(v, ['Completed', 'In progress', 'Review']);
    expect(o.map((x) => [x.cimke, x.sorok.length])).toEqual([
      ['Nincs érték', 1],
      ['Completed', 0],
      ['In progress', 0],
      ['Review', 2],
    ]);
    expect(o.every((x) => x.fogad)).toBe(true);
  });

  it('a nem skalár érték és a nem szerkeszthető tulajdonság oszlopába nem lehet ejteni', () => {
    expect(irhatoErtek({ t: 'lista', e: [] })).toBeUndefined();
    expect(irhatoErtek({ t: 'link', cel: 'x', ut: null, nev: 'x' })).toBeUndefined();
    expect(irhatoErtek(true)).toBe(true);
    const v = valasz({ groupBy: { property: 'Tags' } }, { sorok, csoportok: [cs({ t: 'lista', e: ['a'] }, 0, 3)] });
    expect(oszlopok(v)[0].fogad).toBe(false);
    const f = valasz({ groupBy: { property: 'file.folder' } }, { sorok, csoportok: [cs('X', 0, 3, false)] });
    expect(oszlopok(f)[0].fogad).toBe(false);
  });
});
