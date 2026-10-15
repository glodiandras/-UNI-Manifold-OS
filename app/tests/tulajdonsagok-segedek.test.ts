// A tulajdonság-szerkesztő tiszta segédei (C11b): a frontmatter-blokk a dokumentumban (L39), a legkisebb csere, az
// értékek átalakítása a mezőkhöz, a címkefa sorai, az oldalikon megjelenítési módja, a visszaállítás tilalmának oka.

import { Text } from '@codemirror/state';
import { describe, expect, it } from 'vitest';
import { cimkeFa, type CimkeCsucs } from '../src/lib/vault/cimkek.svelte';
import { visszaallitasOka, type ElozmenyBejegyzes } from '../src/lib/vault/elozmeny';
import { ikonFajta } from '../src/lib/vault/ikonok.svelte';
import {
  csupaLink,
  datumBevitel,
  ertekSzoveg,
  linkke,
  listaBevitel,
  listaElemek,
  szamBevitel,
  wikiReszek,
} from '../src/szerkeszto/tulajdonsagok/ertek';
import { blokkCsere, fmBlokk } from '../src/szerkeszto/tulajdonsagok/fm';

describe('fmBlokk (L39)', () => {
  it('a legelső sortól a záró --- soráig, a sortöréssel együtt', () => {
    const b = fmBlokk('---\nTags:\n  - AI\n---\n\n# Cím\n');
    expect(b?.szoveg).toBe('---\nTags:\n  - AI\n---\n');
    expect(b?.ig).toBe(b!.szoveg.length);
  });

  it('nincs frontmatter: nem az első sorban áll, vagy nincs lezárva', () => {
    expect(fmBlokk('# Cím\n---\na: 1\n---\n')).toBeNull();
    expect(fmBlokk('---\na: 1\nnincs zárás\n')).toBeNull();
    expect(fmBlokk('')).toBeNull();
    expect(fmBlokk(' ---\na: 1\n---\n')).toBeNull();
  });

  it('CodeMirror-szövegből is, és a nagy frontmattert is megtalálja', () => {
    const nagy = '---\n' + Array.from({ length: 3000 }, (_, i) => `k${i}: ${i}`).join('\n') + '\n---\ntörzs';
    expect(nagy.length).toBeGreaterThan(20_000);
    expect(fmBlokk(Text.of(nagy.split('\n')))?.szoveg).toBe(nagy.slice(0, nagy.indexOf('\ntörzs') + 1));
  });

  it('a záró --- után nincs sortörés a blokkban, ha a dokumentum ott ér véget', () => {
    expect(fmBlokk('---\na: 1\n---')?.szoveg).toBe('---\na: 1\n---');
  });

  it('az üres és a BOM-os blokk is frontmatter (C29.8, T130): az „Új tulajdonság” nem szúr második blokkot', () => {
    const ures = fmBlokk('---\n---\n# Cím');
    expect(ures?.szoveg).toBe('---\n---\n');
    expect(ures?.ig).toBe(8);
    expect(fmBlokk('---\n---\ntörzs\n---\n')?.szoveg).toBe('---\n---\n');          // az üres blokk, nem a későbbi `---` sorig
    const bom = fmBlokk('\ufeff---\nTags:\n  - AI\n---\n# Cím');
    expect(bom?.szoveg).toBe('\ufeff---\nTags:\n  - AI\n---\n');
    expect(fmBlokk(Text.of('\ufeff---\n---\nx'.split('\n')))?.szoveg).toBe('\ufeff---\n---\n');
    expect(fmBlokk('--- \na: 1\n---\n')).toBeNull();                                  // a szóközös nyitó nem (K79)
  });

  it('a BOM-os blokk cseréje a BOM-ot nem érinti', () => {
    const regi = fmBlokk('\ufeff---\nTags:\n  - AI\n---\n# C')!;
    const c = blokkCsere(regi, '\ufeff---\nTags:\n  - AI\nStatus: Review\n---\n')!;
    expect(c.from).toBeGreaterThan(0);                                                 // a BOM (0. karakter) érintetlen
    expect(regi.szoveg.slice(0, c.from) + c.insert + regi.szoveg.slice(c.to)).toBe('\ufeff---\nTags:\n  - AI\nStatus: Review\n---\n');
  });
});

describe('blokkCsere', () => {
  const regi = fmBlokk('---\nTags:\n  - AI\nStatus:\n---\n\ntörzs')!;

  it('csak a változó sorokat cseréli (közös eleje és vége nélkül)', () => {
    const uj = '---\nTags:\n  - AI\nStatus: Review\n---\n';
    const c = blokkCsere(regi, uj)!;
    expect(c.insert).toBe(' Review');
    expect(regi.szoveg.slice(0, c.from) + c.insert + regi.szoveg.slice(c.to)).toBe(uj);
  });

  it('változatlan blokk: nincs csere', () => {
    expect(blokkCsere(regi, regi.szoveg)).toBeNull();
  });

  it('új blokk a dokumentum elejére kerül', () => {
    expect(blokkCsere(null, '---\nTags:\n---\n\n')).toEqual({ from: 0, to: 0, insert: '---\nTags:\n---\n\n' });
  });

  it('törlés: a sorok eltűnnek', () => {
    const c = blokkCsere(regi, '---\nTags:\n  - AI\n---\n')!;
    expect(regi.szoveg.slice(0, c.from) + c.insert + regi.szoveg.slice(c.to)).toBe('---\nTags:\n  - AI\n---\n');
  });
});

describe('értékek', () => {
  it('wikilink részei: alias, horgony, felirat', () => {
    expect(wikiReszek('[[A]]')).toEqual({ cel: 'A', alcel: null, alias: null, felirat: 'A' });
    expect(wikiReszek('[[A#Fej|másik]]')).toEqual({ cel: 'A', alcel: 'Fej', alias: 'másik', felirat: 'másik' });
    expect(wikiReszek('[[09 - Matematika.pdf#page=125]]')?.felirat).toBe('09 - Matematika.pdf › page=125');
    expect(wikiReszek('![[kep.png]]')?.cel).toBe('kep.png');
    expect(wikiReszek('szöveg')).toBeNull();
    expect(wikiReszek(3)).toBeNull();
  });

  it('listaElemek és csupaLink', () => {
    expect(listaElemek(null)).toEqual([]);
    expect(listaElemek('')).toEqual([]);
    expect(listaElemek('egy')).toEqual(['egy']);
    expect(listaElemek(['a', '', null, 3])).toEqual(['a', '3']);
    expect(csupaLink(['[[A]]', '[[B]]'])).toBe(true);
    expect(csupaLink(['[[A]]', 'b'])).toBe(false);
    expect(csupaLink([])).toBe(false);
  });

  it('linkke: a csupasz név [[…]] lesz, a link érintetlen', () => {
    expect(linkke('Alma')).toBe('[[Alma]]');
    expect(linkke(' [[Alma]] ')).toBe('[[Alma]]');
    expect(linkke('')).toBe('');
  });

  it('ertekSzoveg', () => {
    expect(ertekSzoveg(null)).toBe('');
    expect(ertekSzoveg(['a', 'b'])).toBe('a, b');
    expect(ertekSzoveg(3.5)).toBe('3.5');
    expect(ertekSzoveg({ a: 1 })).toBe('{"a":1}');
  });

  it('dátum- és számbevitel', () => {
    expect(datumBevitel('date', '2026-10-02')).toBe('2026-10-02');
    expect(datumBevitel('date', 'tegnap')).toBe('');
    expect(datumBevitel('datetime', '2026-10-02T09:30:15')).toBe('2026-10-02T09:30');
    expect(datumBevitel('datetime', '2026-10-02')).toBe('2026-10-02T00:00');
    expect(szamBevitel('3,5')).toBe(3.5);
    expect(szamBevitel('-2')).toBe(-2);
    expect(szamBevitel('')).toBeNull();
    expect(szamBevitel('sok')).toBeUndefined();
    expect(szamBevitel('1e3')).toBe(1000);
  });

  it('listaBevitel: vesszővel tagolt, üres elemek nélkül', () => {
    expect(listaBevitel(' a, b ,, c ')).toEqual(['a', 'b', 'c']);
  });
});

describe('cimkeFa', () => {
  const c = (kis: string, cimke: string, db: number, ossz: number): CimkeCsucs => ({ kis, cimke, db, ossz });
  const lista = [
    c('fizika', 'Fizika', 0, 3),
    c('fizika/mechanika', 'Fizika/Mechanika', 2, 3),
    c('fizika/mechanika/newton', 'Fizika/Mechanika/Newton', 1, 1),
    c('ai', 'AI', 5, 5),
    c('matek', 'Matek', 1, 1),
  ];

  it('zárt fában csak a gyökerek; a nyitott szülő alatt a gyerekei, sorrendben', () => {
    expect(cimkeFa(lista, new Set()).map((s) => s.kis)).toEqual(['ai', 'fizika', 'matek']);
    const nyitva = cimkeFa(lista, new Set(['fizika']));
    expect(nyitva.map((s) => [s.nev, s.melyseg])).toEqual([['AI', 0], ['Fizika', 0], ['Mechanika', 1], ['Matek', 0]]);
    const mind = cimkeFa(lista, new Set(['fizika', 'fizika/mechanika']));
    expect(mind.map((s) => s.nev)).toEqual(['AI', 'Fizika', 'Mechanika', 'Newton', 'Matek']);
  });

  it('van_gyerek és a számlálók', () => {
    const fa = cimkeFa(lista, new Set(['fizika']));
    expect(fa.find((s) => s.kis === 'fizika')).toMatchObject({ van_gyerek: true, db: 0, ossz: 3 });
    expect(fa.find((s) => s.kis === 'ai')?.van_gyerek).toBe(false);
  });

  it('a szülő nélküli gyerek (a szülő nem létezik) nem látszik, de nem is dob', () => {
    expect(cimkeFa([c('a/b', 'a/b', 1, 1)], new Set(['a'])).map((s) => s.kis)).toEqual([]);
  });
});

describe('ikonFajta', () => {
  it('emoji, kép, külső URL, szöveg', () => {
    expect(ikonFajta({ ertek: '📘', ut: null })).toEqual({ fajta: 'emoji', szoveg: '📘' });
    expect(ikonFajta({ ertek: '[[kep.png]]', ut: 'Média/kep.png' })).toEqual({ fajta: 'kep', szoveg: 'Média/kep.png' });
    expect(ikonFajta({ ertek: 'https://x.hu/i.png', ut: null }).fajta).toBe('nincs');
    expect(ikonFajta({ ertek: 'nagyon hosszú szöveg', ut: null }).fajta).toBe('nincs');
    expect(ikonFajta({ ertek: 'kep.png', ut: null }).fajta).toBe('nincs');
    expect(ikonFajta(undefined).fajta).toBe('nincs');
  });
});

describe('visszaallitasOka', () => {
  const b = (o: Partial<ElozmenyBejegyzes>): ElozmenyBejegyzes => ({
    sha: 'a', datum: '2026-10-02T10:00:00+02:00', targy: '', tipus: 'szerk', cimke: 'x', kor: null, forras: null,
    statusz: 'M', ut_akkor: 'J.md', regi_ut: null, elozo: null, visszaallithato: true, ...o,
  });

  it('a visszaállítható nem kap okot; a többi magyar indokot', () => {
    expect(visszaallitasOka(b({}), false)).toBeNull();
    expect(visszaallitasOka(b({ visszaallithato: false }), true)).toMatch(/jelenlegi/);
    expect(visszaallitasOka(b({ visszaallithato: false, statusz: 'D' }), false)).toMatch(/törölve/);
    // 39. döntés: a régi néven álló változat is visszaállítható (új tartalom-írás) — a „korábbi nevén” indok megszűnt
    expect(visszaallitasOka(b({ ut_akkor: 'Regi.md', regi_ut: 'Regi.md', statusz: 'R' }), false)).toBeNull();
    const maradek = visszaallitasOka(b({ visszaallithato: false, ut_akkor: 'Regi.md' }), false);
    expect(maradek).toMatch(/nem állítható vissza/);
    expect(maradek).not.toMatch(/korábbi nevén/);
  });
});
