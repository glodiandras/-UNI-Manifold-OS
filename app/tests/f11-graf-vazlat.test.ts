// F11 / 11-graph-06, 11-graph-07, 11-graph-08 (a Vázlat tiszta logikája): a fa és az összecsukás, a szűrő, a szakaszok és az
// áthelyezés terve. Az áthelyezés adatbiztonsági tulajdonságai minden fejezet-párra és minden irányra: a szöveg nem vész el és
// nem duplázódik, a többi szakasz sorrendje és a sorvég-stílus (CRLF) érintetlen, a fájl végi sortörés megmarad, a kódblokkban
// álló `#` sor nem fejezet. A tranzakció alkalmazása ugyanaz, amit a szerkesztő elküld (ChangeSet) — itt DOM nélkül.
import { history, redo, undo, undoDepth } from '@codemirror/commands';
import { ChangeSet, EditorState, type Transaction } from '@codemirror/state';
import { describe, expect, it } from 'vitest';
import { markdownNyelv } from '../src/szerkeszto/beallitas';
import { eloFejezetek } from '../src/szerkeszto/linkek/kiegeszites';
import {
  athelyezTerv,
  athelyezTilt,
  egyszerusit,
  elemIndex,
  latszoSorok,
  osszecsukhatok,
  szakaszTartomany,
  testverIndex,
  vazlatSorok,
  type Hova,
} from '../src/szerkeszto/vazlat';

function allapot(szoveg: string, crlf = false): EditorState {
  return EditorState.create({ doc: szoveg, extensions: [markdownNyelv(), ...(crlf ? [EditorState.lineSeparator.of('\r\n')] : [])] });
}

function mozgat(szoveg: string, forras: string, cel: string, hova: Hova, crlf = false): string | { hiba: string } {
  const st = allapot(szoveg, crlf);
  const elemek = eloFejezetek(st);
  const f = elemek.findIndex((e) => e.szoveg === forras);
  const c = elemek.findIndex((e) => e.szoveg === cel);
  expect(f, `forrás: ${forras}`).toBeGreaterThanOrEqual(0);
  expect(c, `cél: ${cel}`).toBeGreaterThanOrEqual(0);
  const r = athelyezTerv(st, elemek, f, c, hova);
  if ('hiba' in r) return r;
  return ChangeSet.of(r.terv.changes, st.doc.length).apply(st.doc).sliceString(0, undefined, st.lineBreak);
}

describe('11-graph-06: a fejezetek fája és az összecsukás', () => {
  const E = (szint: number, szoveg: string, sor: number) => ({ szint, szoveg, sor });
  const elemek = [E(1, 'A', 1), E(2, 'A1', 3), E(3, 'A1a', 5), E(2, 'A2', 7), E(1, 'B', 9), E(2, 'B1', 11)];

  it('szülő, gyerek-jelzés és behúzás szint szerint; a mélység ugrása (H1 → H3) is szülő-gyerek', () => {
    const s = vazlatSorok(elemek);
    expect(s.map((x) => x.szulo)).toEqual([-1, 0, 1, 0, -1, 4]);
    expect(s.map((x) => x.gyerek)).toEqual([true, true, false, false, true, false]);
    expect(s.map((x) => x.mely)).toEqual([0, 1, 2, 1, 0, 1]);
    const ugras = vazlatSorok([E(1, 'X', 1), E(3, 'Y', 2), E(2, 'Z', 3)]);
    expect(ugras.map((x) => x.szulo)).toEqual([-1, 0, 0]);
  });

  it('az összecsukás kulcsa szint + szöveg + előfordulás: duplikált szövegnél is egyedi, szerkesztés közben stabil', () => {
    const dup = vazlatSorok([E(2, 'Összegzés', 3), E(2, 'Összegzés', 9), E(3, 'Összegzés', 12)]);
    expect(new Set(dup.map((x) => x.kulcs)).size).toBe(3);
    // más sorszámok (a fölötte lévő szöveg átírása), ugyanaz a kulcs
    const eltolt = vazlatSorok([E(2, 'Összegzés', 30), E(2, 'Összegzés', 90), E(3, 'Összegzés', 120)]);
    expect(eltolt.map((x) => x.kulcs)).toEqual(dup.map((x) => x.kulcs));
    // szintváltás = új kulcs: az összecsukott állapot magától elavul
    expect(vazlatSorok([E(3, 'Összegzés', 3)])[0].kulcs).not.toBe(dup[0].kulcs);
  });

  it('az összecsukott fejezet minden leszármazottját elrejti (több szinten), a testvéreket nem', () => {
    const s = vazlatSorok(elemek);
    const lat = (ossz: string[], szuro = '') => latszoSorok(s, new Set(ossz), szuro).map((x) => x.sor.elem.szoveg);
    expect(lat([])).toEqual(['A', 'A1', 'A1a', 'A2', 'B', 'B1']);
    expect(lat([s[0].kulcs])).toEqual(['A', 'B', 'B1']);
    expect(lat([s[1].kulcs])).toEqual(['A', 'A1', 'A2', 'B', 'B1']);
    expect(lat([s[0].kulcs, s[1].kulcs])).toEqual(['A', 'B', 'B1']); // a belső összecsukás a külsőt nem oldja
    expect(lat([s[4].kulcs])).toEqual(['A', 'A1', 'A1a', 'A2', 'B']);
  });

  it('összes összecsukása = a gyerekes fejezetek; a levél nem összecsukható', () => {
    const s = vazlatSorok(elemek);
    expect(osszecsukhatok(s)).toEqual([s[0].kulcs, s[1].kulcs, s[4].kulcs]);
    const kevesebb = latszoSorok(s, new Set(osszecsukhatok(s)), '');
    expect(kevesebb.map((x) => x.sor.elem.szoveg)).toEqual(['A', 'B']);
  });
});

describe('11-graph-07: a Vázlat szűrője', () => {
  const E = (szint: number, szoveg: string, sor: number) => ({ szint, szoveg, sor });
  const s = vazlatSorok([E(1, 'Bevezetés', 1), E(2, 'Háttér és előzmények', 3), E(2, 'Módszer', 5), E(3, 'Árvíz-modell', 7), E(1, 'Eredmények', 9)]);

  it('ékezet- és kisbetű-független részszó; a találat őse látszik (halványan), az összecsukás nem rejti a találatot', () => {
    expect(egyszerusit('Árvíz')).toBe('arviz');
    const r = latszoSorok(s, new Set(osszecsukhatok(s)), 'ARVIZ');
    expect(r.map((x) => [x.sor.elem.szoveg, x.talalat])).toEqual([
      ['Bevezetés', false],
      ['Módszer', false],
      ['Árvíz-modell', true],
    ]);
  });

  it('több találat, üres és csak szóköz szűrő; nincs találat → üres lista', () => {
    // Az ékezetfüggetlen „mod” a Módszer és a modell szavakra is illeszkedik; a közös ős egyszer látszik.
    expect(latszoSorok(s, new Set(), 'mód').map((x) => [x.sor.elem.szoveg, x.talalat])).toEqual([
      ['Bevezetés', false],
      ['Módszer', true],
      ['Árvíz-modell', true],
    ]);
    expect(latszoSorok(s, new Set(), '   ').length).toBe(5);
    expect(latszoSorok(s, new Set(), 'nincs ilyen')).toEqual([]);
    expect(latszoSorok(s, new Set(), 'e').map((x) => x.sor.elem.szoveg)).toEqual(['Bevezetés', 'Háttér és előzmények', 'Módszer', 'Árvíz-modell', 'Eredmények']);
  });
});

describe('11-graph-08: szakaszok és testvérek', () => {
  const doc = '# A\n## A1\nx\n## A2\ny\n# B\nz\n';
  it('a szakasz a következő azonos vagy magasabb szintű fejezet előtt ér véget; a záró sortörés nem része', () => {
    const st = allapot(doc);
    const e = eloFejezetek(st);
    expect(e.map((x) => x.szoveg)).toEqual(['A', 'A1', 'A2', 'B']);
    expect(szakaszTartomany(st.doc, e, 0)).toEqual({ s0: 1, s1: 5 });
    expect(szakaszTartomany(st.doc, e, 1)).toEqual({ s0: 2, s1: 3 });
    expect(szakaszTartomany(st.doc, e, 3)).toEqual({ s0: 6, s1: 7 }); // a 8. „sor” a fájl végi sortörés
    expect(szakaszTartomany(allapot('# A\nx').doc, eloFejezetek(allapot('# A\nx')), 0)).toEqual({ s0: 1, s1: 2 });
  });

  it('testvér: azonos szülő alatt az előző / következő azonos szintű; a szülőn át nem lép', () => {
    const s = vazlatSorok(eloFejezetek(allapot(doc)));
    expect(testverIndex(s, 1, 1)).toBe(2); // A1 → A2
    expect(testverIndex(s, 2, -1)).toBe(1);
    expect(testverIndex(s, 1, -1)).toBe(-1); // az A első gyereke: feljebb nincs testvér
    expect(testverIndex(s, 2, 1)).toBe(-1); // A2 alatt a B már másik szülő
    expect(testverIndex(s, 0, 1)).toBe(3); // A → B
    expect(testverIndex(s, 3, 1)).toBe(-1);
    expect(testverIndex(s, 99, 1)).toBe(-1);
  });
});

describe('11-graph-08: az áthelyezés pontos eredménye', () => {
  it('felfelé és lefelé, a fájl végi sortöréssel', () => {
    const d = '# A\na\n# B\nb\n# C\nc\n';
    expect(mozgat(d, 'C', 'A', 'elott')).toBe('# C\nc\n# A\na\n# B\nb\n');
    expect(mozgat(d, 'A', 'C', 'utan')).toBe('# B\nb\n# C\nc\n# A\na\n');
    expect(mozgat(d, 'B', 'A', 'elott')).toBe('# B\nb\n# A\na\n# C\nc\n');
    expect(mozgat(d, 'B', 'C', 'utan')).toBe('# A\na\n# C\nc\n# B\nb\n');
  });

  it('záró sortörés nélküli fájl: marad záró sortörés nélkül, nincs eltűnő vagy üres sor', () => {
    const d = '# A\na\n# B\nb';
    expect(mozgat(d, 'A', 'B', 'utan')).toBe('# B\nb\n# A\na');
    expect(mozgat(d, 'B', 'A', 'elott')).toBe('# B\nb\n# A\na');
    const h = '# A\na\n# B\nb\n# C\nc';
    expect(mozgat(h, 'B', 'C', 'utan')).toBe('# A\na\n# C\nc\n# B\nb');
    expect(mozgat(h, 'C', 'B', 'elott')).toBe('# A\na\n# C\nc\n# B\nb');
  });

  it('beágyazott szakaszok együtt mozognak; testvér-csere; kimozgatás a szülőből', () => {
    const d = '# A\n## A1\nx\n## A2\ny\n# B\nz\n';
    expect(mozgat(d, 'A2', 'A1', 'elott')).toBe('# A\n## A2\ny\n## A1\nx\n# B\nz\n');
    expect(mozgat(d, 'A', 'B', 'utan')).toBe('# B\nz\n# A\n## A1\nx\n## A2\ny\n');
    expect(mozgat(d, 'A1', 'A', 'elott')).toBe('## A1\nx\n# A\n## A2\ny\n# B\nz\n'); // csak a blokk mozog, a szint nem változik
    expect(mozgat(d, 'B', 'A1', 'elott')).toBe('# A\n# B\nz\n## A1\nx\n## A2\ny\n');
  });

  it('a bevezető szöveg, a front matter és a kódblokkba zárt `#` sor érintetlen', () => {
    const d = '---\ntags: [x]\n---\nbevezető\n\n# A\n```\n# nem fejezet\n```\n# B\nb\n';
    expect(eloFejezetek(allapot(d)).map((e) => e.szoveg)).toEqual(['A', 'B']);
    expect(mozgat(d, 'B', 'A', 'elott')).toBe('---\ntags: [x]\n---\nbevezető\n\n# B\nb\n# A\n```\n# nem fejezet\n```\n');
  });

  it('Setext fejezet: a szöveg- és az aláhúzás-sor együtt mozog', () => {
    const d = 'Első\n=====\nszöveg\n\nMásodik\n=======\nmás\n';
    expect(eloFejezetek(allapot(d)).map((e) => e.szoveg)).toEqual(['Első', 'Második']);
    expect(mozgat(d, 'Második', 'Első', 'elott')).toBe('Második\n=======\nmás\nElső\n=====\nszöveg\n\n');
  });

  it('CRLF-es jegyzet: a sortörés végig CRLF marad (nincs magányos LF)', () => {
    const d = '# A\r\na\r\n# B\r\nb\r\n';
    const k = mozgat(d, 'B', 'A', 'elott', true) as string;
    expect(k).toBe('# B\r\nb\r\n# A\r\na\r\n');
    expect(k.replace(/\r\n/g, '')).not.toMatch(/[\r\n]/);
    const v = mozgat('# A\r\na\r\n# B\r\nb', 'A', 'B', 'utan', true) as string;
    expect(v).toBe('# B\r\nb\r\n# A\r\na');
  });

  it('tiltott vagy értelmetlen kérés: nincs változtatás (önmagába, szomszédos helyre, érvénytelen index)', () => {
    const d = '# A\n## A1\nx\n# B\nb\n';
    expect(mozgat(d, 'A', 'A1', 'elott')).toEqual({ hiba: 'sajatReszben' });
    // Az utolsó gyerek UTÁNI pozíció a forrásszakasz vége: nincs változás, nincs tranzakció.
    expect(mozgat(d, 'A', 'A1', 'utan')).toEqual({ hiba: 'nincsValtozas' });
    expect(mozgat('# A\n## A1\nx\n## A2\ny\n# B\nb\n', 'A', 'A1', 'utan')).toEqual({ hiba: 'sajatReszben' });
    expect(mozgat(d, 'A', 'B', 'elott')).toEqual({ hiba: 'nincsValtozas' }); // már ott áll
    expect(mozgat(d, 'B', 'A', 'utan')).toEqual({ hiba: 'nincsValtozas' });
    expect(mozgat(d, 'A', 'A', 'elott')).toEqual({ hiba: 'nincsValtozas' });
    const st = allapot(d);
    const e = eloFejezetek(st);
    expect(athelyezTerv(st, e, -1, 0, 'elott')).toEqual({ hiba: 'ervenytelen' });
    expect(athelyezTerv(st, e, 0, 99, 'utan')).toEqual({ hiba: 'ervenytelen' });
    expect(athelyezTerv(st, e, 0.5, 1, 'utan')).toEqual({ hiba: 'ervenytelen' });
    // az egész jegyzet egyetlen szakasz
    expect(mozgat('# Csak\nszöveg', 'Csak', 'Csak', 'utan')).toEqual({ hiba: 'nincsValtozas' });
  });

  it('a kurzor az áthelyezett fejezet új kezdetére mutat', () => {
    const st = allapot('# A\na\n# B\nb\n# C\nc\n');
    const e = eloFejezetek(st);
    const r = athelyezTerv(st, e, 2, 0, 'elott');
    if ('hiba' in r) throw new Error(r.hiba);
    const uj = ChangeSet.of(r.terv.changes, st.doc.length).apply(st.doc);
    expect(uj.sliceString(r.terv.fejezetPoz, r.terv.fejezetPoz + 3)).toBe('# C');
    const veg = athelyezTerv(st, e, 0, 2, 'utan');
    if ('hiba' in veg) throw new Error(veg.hiba);
    const ujVeg = ChangeSet.of(veg.terv.changes, st.doc.length).apply(st.doc);
    expect(ujVeg.sliceString(veg.terv.fejezetPoz, veg.terv.fejezetPoz + 3)).toBe('# A');
    const vegNL = allapot('# A\na\n# B\nb');
    const e2 = eloFejezetek(vegNL);
    const v2 = athelyezTerv(vegNL, e2, 0, 1, 'utan');
    if ('hiba' in v2) throw new Error(v2.hiba);
    const ujVeg2 = ChangeSet.of(v2.terv.changes, vegNL.doc.length).apply(vegNL.doc);
    expect(ujVeg2.sliceString(v2.terv.fejezetPoz, v2.terv.fejezetPoz + 3)).toBe('# A'); // a fájl végére mozgatva is
  });

  it('a szakasz mozgatása egy CodeMirror undo-lépés, redo után is bájthű (CRLF, teljes alfejezet és ismeretlen tartalom)', () => {
    const eredeti = '---\r\nk: "keep"\r\n---\r\n# A\r\n## A1\r\n```\r\n# code\r\n```\r\n# B\r\nb\r\n';
    let state = EditorState.create({ doc: eredeti, extensions: [markdownNyelv(), EditorState.lineSeparator.of('\r\n'), history()] });
    const elemek = eloFejezetek(state);
    const r = athelyezTerv(state, elemek, 0, 2, 'utan');
    if ('hiba' in r) throw new Error(r.hiba);
    state = state.update({ changes: r.terv.changes, selection: { anchor: r.terv.fejezetPoz }, userEvent: 'move.section' }).state;
    const mozgatott = '---\r\nk: "keep"\r\n---\r\n# B\r\nb\r\n# A\r\n## A1\r\n```\r\n# code\r\n```\r\n';
    const szoveg = () => state.sliceDoc(0, state.doc.length);
    const cel = { get state() { return state; }, dispatch(tr: Transaction) { state = tr.state; } };
    expect(szoveg()).toBe(mozgatott);
    expect(undoDepth(state)).toBe(1);
    expect(undo(cel)).toBe(true);
    expect(szoveg()).toBe(eredeti);
    expect(undo(cel)).toBe(false);
    expect(redo(cel)).toBe(true);
    expect(szoveg()).toBe(mozgatott);
  });
});

describe('11-graph-08: adatbiztonsági tulajdonságok (minden fejezet-pár, minden irány)', () => {
  const DOKUMENTUMOK: Record<string, [string, boolean]> = {
    'záró sortöréssel': ['bevezető\n\n# A\na1\na2\n## A1\nx\n\n## A2\ny\n# B\n\nb\n# C\nc\n### C1\nd\n', false],
    'záró sortörés nélkül': ['# A\n## A1\nx\n# B\nb\n## B1\nutolsó', false],
    CRLF: ['# A\r\na\r\n## A1\r\nx\r\n# B\r\nb\r\n', true],
    'kódblokk és front matter': ['---\nk: v\n---\n# A\n```\n# kód\n```\n## A1\nx\n# B\n> # idézet\nb\n', false],
    'több üres sor a végén': ['# A\na\n# B\nb\n\n\n', false],
  };

  for (const [nev, [szoveg, crlf]] of Object.entries(DOKUMENTUMOK))
    it(`${nev}: semmi nem vész el, nem duplázódik; a többi szakasz sorrendje, a sorvég és a végi sortörés megmarad`, () => {
      const st = allapot(szoveg, crlf);
      const lb = st.lineBreak;
      const elemek = eloFejezetek(st);
      expect(elemek.length).toBeGreaterThanOrEqual(2);
      let kombinaciok = 0;
      for (let f = 0; f < elemek.length; f++)
        for (let c = 0; c < elemek.length; c++)
          for (const hova of ['elott', 'utan'] as Hova[]) {
            const r = athelyezTerv(st, elemek, f, c, hova);
            if ('hiba' in r) continue;
            kombinaciok++;
            const uj = ChangeSet.of(r.terv.changes, st.doc.length).apply(st.doc).sliceString(0, undefined, lb);
            const cimke = `${elemek[f].szoveg} ${hova} ${elemek[c].szoveg}`;
            // 1. minden sor megvan, egyszer (a sorok multihalmaza azonos)
            const eredetiSorok = szoveg.split(lb);
            const ujSorok = uj.split(lb);
            expect(ujSorok.length, cimke).toBe(eredetiSorok.length);
            expect([...ujSorok].sort(), cimke).toEqual([...eredetiSorok].sort());
            // 2. a fájl végi sortörés megléte és a sorvég-stílus változatlan
            expect(uj.endsWith(lb), cimke).toBe(szoveg.endsWith(lb));
            if (crlf) expect(uj.replace(/\r\n/g, ''), cimke).not.toMatch(/[\r\n]/);
            // 3. a szakasz egybefüggő blokk, és a maradék sorrendje az eredeti
            const sz = r.terv.szakasz;
            const blokk = eredetiSorok.slice(sz.s0 - 1, sz.s1);
            const maradek = [...eredetiSorok.slice(0, sz.s0 - 1), ...eredetiSorok.slice(sz.s1)];
            let ok = false;
            for (let i = 0; i + blokk.length <= ujSorok.length && !ok; i++) {
              if (blokk.every((s, k) => ujSorok[i + k] === s)) {
                const mar = [...ujSorok.slice(0, i), ...ujSorok.slice(i + blokk.length)];
                ok = mar.length === maradek.length && mar.every((s, k) => s === maradek[k]);
              }
            }
            expect(ok, `${cimke}: a szakasz egybefüggő, a többi sorrendje változatlan`).toBe(true);
            // 4. a tervben nincs átfedő változtatás (két tartomány, az eredeti dokumentumban)
            expect(r.terv.changes.length).toBe(2);
          }
      // Két fejezetnél pontosan két valódi áthelyezés van: B A elé és A B után; a másik hat kérés no-op.
      if (elemek.length === 2) expect(kombinaciok).toBe(2);
      else expect(kombinaciok).toBeGreaterThan(elemek.length); // nem üresen futott
    });
});

describe('11-graph-08: mikor tilos (tiszta szabály)', () => {
  const szabad = { mod: 'forras' as const, nezetVan: true, csakOlvashato: null, allapot: 'tiszta' as const };
  it('Olvasó mód, csak olvasható, ütközés, eltűnt, töltés: tilos; tiszta, piszkos, mentés alatt, hiba: szabad', () => {
    expect(athelyezTilt(szabad)).toBeNull();
    expect(athelyezTilt({ ...szabad, mod: 'elo' })).toBeNull();
    for (const a of ['piszkos', 'mentes', 'hiba'] as const) expect(athelyezTilt({ ...szabad, allapot: a })).toBeNull();
    expect(athelyezTilt({ ...szabad, mod: 'olvaso' })).toBe('olvaso');
    expect(athelyezTilt({ ...szabad, nezetVan: false })).toBe('nincsNezet');
    expect(athelyezTilt({ ...szabad, csakOlvashato: 'hibás UTF-8' })).toBe('csakOlvashato');
    expect(athelyezTilt({ ...szabad, allapot: 'utkozes' })).toBe('utkozes');
    expect(athelyezTilt({ ...szabad, allapot: 'eltunt' })).toBe('eltunt');
    expect(athelyezTilt({ ...szabad, allapot: 'betoltes' })).toBe('betoltes');
    expect(athelyezTilt({ ...szabad, allapot: undefined })).toBe('betoltes');
  });

  it('a fejezet azonosítása sor + szint + szöveg szerint: elcsúszott vagy átírt fejezet nem azonosítható', () => {
    const e = [{ szint: 1, szoveg: 'A', sor: 1 }, { szint: 2, szoveg: 'B', sor: 4 }];
    expect(elemIndex(e, { szint: 2, szoveg: 'B', sor: 4 })).toBe(1);
    expect(elemIndex(e, { szint: 2, szoveg: 'B', sor: 5 })).toBe(-1);
    expect(elemIndex(e, { szint: 3, szoveg: 'B', sor: 4 })).toBe(-1);
    expect(elemIndex(e, { szint: 2, szoveg: 'C', sor: 4 })).toBe(-1);
  });
});
