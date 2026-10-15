// A Notion-réteg blokkmodellje és szerkesztő-műveletei (C09), tiszta függvényekként: a kimenet pontos szövege,
// a blokkok bájthűsége, a hibátlan elemzés és a visszavonhatóság.

import type { EditorState } from '@codemirror/state';
import { describe, expect, it } from 'vitest';
import { type Blokk, blokkSorban, blokkok, testverek } from '../src/szerkeszto/notion/blokkmodell';
import {
  atalakit,
  type AtalakitCel,
  blokkLink,
  type Cel,
  duplikal,
  idBeir,
  mozgat,
  type Szerkesztes,
  torol,
  ujBlokkId,
} from '../src/szerkeszto/notion/muveletek';
import { allapot, hibatlan, szerkezet, szerkezetEgyezik } from './notion-segedek';

function alkalmaz(s: EditorState, sz: { changes: unknown; selection?: { anchor: number } } | null): string {
  if (!sz) throw new Error('nincs változás');
  const uj = s.update({ changes: sz.changes as never, selection: sz.selection }).state;
  return uj.doc.sliceString(0, uj.doc.length, uj.lineBreak);
}

function sor(s: EditorState, szoveg: string): Blokk {
  const bl = blokkok(s);
  // `=…`: a blokk első sora pontosan ez; egyébként tartalmazza
  const b = bl.find((x) => (szoveg.startsWith('=') ? s.doc.line(x.elsoSor).text === szoveg.slice(1) : s.doc.line(x.elsoSor).text.includes(szoveg)));
  if (!b) throw new Error(`nincs blokk: ${szoveg}`);
  return b;
}

function mozgatas(doc: string, mit: string, hova: string, hely: Cel['hely'], crlf = false): string | null {
  const s = allapot(doc, crlf);
  const sz = mozgat(s, blokkok(s), sor(s, mit), { blokk: sor(s, hova), hely });
  return sz ? alkalmaz(s, sz) : null;
}

describe('blokkmodell', () => {
  it('a fogható blokkok: legfelső szint, listaelemek a gyerekeikkel, frontmatter nélkül', () => {
    const s = allapot('---\nTags: x\n---\n# Cím\n\nBekezdés ^abc\n\n- a\n\t- b\n- c\n\n> [!tip] T\n> x\n\n```py\n1\n```\n');
    const bl = blokkok(s);
    expect(bl.map((b) => b.tipus)).toEqual(['fejezet', 'bekezdes', 'listaelem', 'listaelem', 'listaelem', 'callout', 'kod']);
    expect(bl[1].id).toBe('abc');
    expect(bl[2].gyerekek).toEqual([3]);
    expect(bl[3].szulo).toBe(2);
    expect([bl[2].elsoSor, bl[2].utolsoSor]).toEqual([8, 9]);
    expect(bl[5].calloutTipus).toBe('tip');
    expect(bl[6].nyelv).toBe('py');
    expect(testverek(bl, bl[2]).map((b) => b.index)).toEqual([2, 4]);
  });

  it('az önálló ^id sor a nem szöveges blokk része; a listaelem sorvégi azonosítója a saját szövegéé', () => {
    const s = allapot('| a |\n|---|\n| 1 |\n\n^tabla1\n\nPara\n\n- elem ^e1\n\t- gyerek\n');
    const bl = blokkok(s);
    expect(bl[0].tipus).toBe('tablazat');
    expect(bl[0].id).toBe('tabla1');
    expect(bl[0].utolsoSor).toBe(5);
    expect(bl.map((b) => b.tipus)).toEqual(['tablazat', 'bekezdes', 'listaelem', 'listaelem']);
    expect(bl[2].id).toBe('e1');
    expect(blokkSorban(bl, 10)!.index).toBe(3);
    expect(blokkSorban(bl, 6)).toBeNull();
  });

  it('az idézetben álló lista nem külön blokk', () => {
    const bl = blokkok(allapot('> - a\n> - b\n\nvége'));
    expect(bl.map((b) => b.tipus)).toEqual(['idezet', 'bekezdes']);
  });
});

describe('mozgatás: legfelső szint', () => {
  it('blokk lefelé és felfelé, az üres sorok megmaradnak', () => {
    expect(mozgatas('A\n\nB\n\nC\n', 'A', 'C', 'utan')).toBe('B\n\nC\n\nA\n');
    expect(mozgatas('A\n\nB\n\nC\n', 'C', 'A', 'elott')).toBe('C\n\nA\n\nB\n');
    expect(mozgatas('A\n\nB\n\nC\n', 'B', 'C', 'utan')).toBe('A\n\nC\n\nB\n');
  });

  it('záró sortörés nélküli dokumentum és CRLF', () => {
    expect(mozgatas('A\n\nB\n\nC', 'A', 'C', 'utan')).toBe('B\n\nC\n\nA');
    expect(mozgatas('A\n\nB\n\nC', 'C', 'A', 'elott')).toBe('C\n\nA\n\nB');
    expect(mozgatas('A\r\n\r\nB\r\n\r\nC\r\n', 'A', 'C', 'utan', true)).toBe('B\r\n\r\nC\r\n\r\nA\r\n');
  });

  it('a szoros szomszéd (fejezet és bekezdés üres sor nélkül) nem olvad össze', () => {
    expect(mozgatas('# H\nPara\n\nX\n', 'X', 'Para', 'elott')).toBe('# H\n\nX\n\nPara\n');
    expect(mozgatas('# H\nPara\n\nX\n', 'Para', 'X', 'utan')).toBe('# H\n\nX\n\nPara\n');
  });

  it('a helyben maradó mozgatás nem változtat', () => {
    expect(mozgatas('A\n\nB\n\nC\n', 'A', 'B', 'elott')).toBeNull();
    expect(mozgatas('A\n\nB\n\nC\n', 'B', 'A', 'utan')).toBeNull();
  });

  it('táblázat, callout, kód és képlet egységként mozog', () => {
    const doc = '# H\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n> [!note] N\n> törzs\n\n```js\nx\n```\n\n$$\ny\n$$\n\nVége\n';
    expect(mozgatas(doc, 'a | b', 'Vége', 'utan')).toBe(
      '# H\n\n> [!note] N\n> törzs\n\n```js\nx\n```\n\n$$\ny\n$$\n\nVége\n\n| a | b |\n|---|---|\n| 1 | 2 |\n',
    );
    expect(mozgatas(doc, 'N', '# H', 'elott')).toBe(
      '> [!note] N\n> törzs\n\n# H\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n```js\nx\n```\n\n$$\ny\n$$\n\nVége\n',
    );
  });

  it('az önálló ^id sor a blokkal együtt mozog', () => {
    expect(mozgatas('| a |\n|---|\n| 1 |\n\n^t1\n\nP\n', 'a |', 'P', 'utan')).toBe('P\n\n| a |\n|---|\n| 1 |\n\n^t1\n');
  });

  it('a lista egészének határára: szöveg a lista mögé és elé', () => {
    expect(mozgatas('P\n\n- a\n- b\n\nQ\n', 'P', 'b', 'utan')).toBe('- a\n- b\n\nP\n\nQ\n');
    expect(mozgatas('Q\n\n- a\n\t- a1\n- b\n', 'Q', 'a1', 'utan')).toBeNull(); // belső elem nem legfelső cél
    expect(mozgatas('P\n\nQ\n\n- a\n- b\n', 'Q', 'a', 'elott')).toBeNull(); // már ott van
    expect(mozgatas('P\n\n- a\n- b\n\nQ\n', 'Q', 'a', 'elott')).toBe('P\n\nQ\n\n- a\n- b\n');
  });

  it('véletlen mozgatások: a blokkok szövege és sorrendje a vártnak megfelelő, a kimenet hibátlan', () => {
    const doc =
      '# Egy\n\nPara egy\nmásodik sor\n\n> [!tip] Tipp\n> törzs\n\n| a |\n|---|\n| 1 |\n\n```js\nkód\n```\n\n---\n\n$$\nx\n$$\n\nVége\n';
    let veletlen = 12345;
    const rnd = (n: number) => {
      veletlen = (veletlen * 1103515245 + 12345) & 0x7fffffff;
      return veletlen % n;
    };
    for (let k = 0; k < 60; k++) {
      const s = allapot(doc);
      const bl = blokkok(s);
      const i = rnd(bl.length);
      let j = rnd(bl.length);
      if (j === i) j = (j + 1) % bl.length;
      const hely = rnd(2) ? 'elott' : 'utan';
      const sz = mozgat(s, bl, bl[i], { blokk: bl[j], hely });
      const elvart = bl.map((b) => s.doc.sliceString(b.from, b.to));
      const [mozgott] = elvart.splice(i, 1);
      const celIdx = elvart.indexOf(s.doc.sliceString(bl[j].from, bl[j].to));
      elvart.splice(hely === 'elott' ? celIdx : celIdx + 1, 0, mozgott);
      if (!sz) {
        // csak akkor maradhat helyben, ha a sorrend sem változna
        expect(elvart).toEqual(bl.map((b) => s.doc.sliceString(b.from, b.to)));
        continue;
      }
      const ki = alkalmaz(s, sz);
      expect(hibatlan(ki)).toBe(true);
      const uj = allapot(ki);
      expect(blokkok(uj).map((b) => uj.doc.sliceString(b.from, b.to))).toEqual(elvart);
    }
  });
});

// A kivétel varrata (T035): a blokk üres sor nélkül álló szomszédai a kivétel után nem olvadhatnak össze.
describe('szoros szomszédok: a kivétel varratánál üres sor áll', () => {
  const torolva = (doc: string, mit: string): string => {
    const s = allapot(doc);
    return alkalmaz(s, torol(s, blokkok(s), sor(s, mit)));
  };

  it('törlés: két bekezdés közül a fejezet kiesik, a bekezdések külön maradnak', () => {
    expect(torolva('Alfa\n# Cím\nBéta\n', '# Cím')).toBe('Alfa\n\nBéta\n');
    expect(torolva('Alfa\n***\nBéta\n', '=***')).toBe('Alfa\n\nBéta\n');
  });

  it('törlés: a táblázat és az idézet utáni bekezdés nem lesz sor / lusta folytatás', () => {
    expect(torolva('| a |\n|---|\n| 1 |\n# H\nPara\n', '# H')).toBe('| a |\n|---|\n| 1 |\n\nPara\n');
    expect(torolva('> q\n# H\nPara\n', '# H')).toBe('> q\n\nPara\n');
  });

  it('törlés: a két lista nem olvad szorosan eggyé; az egyetlen elemű lista is varrat', () => {
    expect(torolva('- a\n# H\n- b\n', '# H')).toBe('- a\n\n- b\n');
    expect(torolva('# H\n- a\n# G\n', '- a')).toBe('# H\n\n# G\n');
  });

  it('a már üres sorral elválasztott szomszéd, a dokumentum széle és a laza elemek változatlanul viselkednek', () => {
    expect(torolva('Alfa\n\n# Cím\nBéta\n', '# Cím')).toBe('Alfa\n\nBéta\n');
    expect(torolva('Alfa\n# Cím\n\nBéta\n', '# Cím')).toBe('Alfa\n\nBéta\n');
    expect(torolva('# Cím\nBéta\n', '# Cím')).toBe('Béta\n');
    expect(torolva('Alfa\n# Cím', '# Cím')).toBe('Alfa');
  });

  it('mozgatás: a kiemelt blokk helyén sem olvad össze a két szomszéd; a célnál is üres sor áll', () => {
    expect(mozgatas('Alfa\n# Cím\nBéta\n\nGamma\n', '# Cím', 'Gamma', 'utan')).toBe('Alfa\n\nBéta\n\nGamma\n\n# Cím\n');
    expect(mozgatas('Alfa\n# Cím\nBéta\n\nGamma\n', 'Gamma', 'Alfa', 'elott')).toBe('Gamma\n\nAlfa\n# Cím\nBéta\n');
    expect(mozgatas('Alfa\n***\nBéta\n', '=***', 'Béta', 'utan')).toBe('Alfa\n\nBéta\n\n***\n');
    expect(mozgatas('- a\n# H\n- b\n', '# H', '=- b', 'utan')).toBe('- a\n\n- b\n\n# H\n');
  });

  it('a lista egyetlen elemének mozgatása a varraton: a szomszédok külön maradnak, a céllista számozása rendben', () => {
    expect(mozgatas('# H\n- a\n# G\n\n- z\n', '- a', '- z', 'utan')).toBe('# H\n\n# G\n\n- z\n- a\n');
    expect(mozgatas('# H\n1. a\n# G\n\n1. x\n2. y\n', 'a', 'x', 'elott')).toBe('# H\n\n# G\n\n1. a\n2. x\n3. y\n');
    expect(mozgatas('# H\n1. a\n# G\n\n1. x\n2. y\n', 'a', 'y', 'utan')).toBe('# H\n\n# G\n\n1. x\n2. y\n3. a\n');
  });

  it('a kurzor törlés után a következő blokk első sorára áll (a varratba tett üres sor mögé)', () => {
    const s = allapot('Alfa\n# Cím\nBéta\n');
    const sz = torol(s, blokkok(s), sor(s, '# Cím'))!;
    const uj = s.update({ changes: sz.changes as never, selection: sz.selection }).state;
    expect(uj.doc.lineAt(uj.selection.main.head).text).toBe('Béta');
  });
});

// ---------------------------------------------------------------------- generátor (T125)

function mulberry32(mag: number): () => number {
  let a = mag >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

interface Darab {
  szoveg: (n: number) => string;
  /** a darab legfelső szintű csomópontja a Lezer-fában */
  csomopont: string;
  lista?: true;
}

const DARABOK: Darab[] = [
  { szoveg: (n) => `Bekezdés ${n}`, csomopont: 'Paragraph' },
  { szoveg: (n) => `Első ${n}\nmásodik ${n}`, csomopont: 'Paragraph' },
  { szoveg: (n) => `# Cím ${n}`, csomopont: 'ATXHeading1' },
  { szoveg: (n) => `Cím ${n}\n===`, csomopont: 'SetextHeading1' },
  { szoveg: (n) => `> idézet ${n}`, csomopont: 'Blockquote' },
  { szoveg: (n) => `> [!note] ${n}\n> törzs`, csomopont: 'Blockquote' },
  { szoveg: (n) => `- a ${n}\n- b`, csomopont: 'BulletList', lista: true },
  { szoveg: (n) => `1. x ${n}\n2. y`, csomopont: 'OrderedList', lista: true },
  { szoveg: (n) => '```\nkód ' + n + '\n```', csomopont: 'FencedCode' },
  { szoveg: (n) => `| a | b |\n|---|---|\n| ${n} | 2 |`, csomopont: 'Table' },
  { szoveg: () => '***', csomopont: 'HorizontalRule' },
  { szoveg: (n) => `$$\nx ${n}\n$$`, csomopont: 'MathBlock' },
];

interface Generalt {
  darabok: Darab[];
  szovegek: string[];
  doc: string;
  /** a darabok első sora (1-alapú) */
  elsoSorok: number[];
}

/** Véletlen dokumentumok a darabokból, `\n` (üres sor nélkül) vagy `\n\n` kötéssel; csak azok maradnak, amelyek
 *  legfelső szintű csomópontjai pontosan a darabok vártnevei (a „szorosan állhat” mátrixot a Lezer adja). */
function generalt(mag: number, db: number): Generalt[] {
  const rnd = mulberry32(mag);
  const ki: Generalt[] = [];
  for (let k = 0; k < 2000 && ki.length < db; k++) {
    const darabok = Array.from({ length: 3 + Math.floor(rnd() * 3) }, () => DARABOK[Math.floor(rnd() * DARABOK.length)]);
    const szovegek = darabok.map((d, i) => d.szoveg(i + 1));
    let doc = '';
    const elsoSorok: number[] = [];
    szovegek.forEach((sz, i) => {
      if (i) doc += rnd() < 0.5 ? '\n' : '\n\n';
      elsoSorok.push(doc.split('\n').length);
      doc += sz;
    });
    if (rnd() < 0.6) doc += '\n';
    const felso = szerkezet(doc).felso;
    if (felso.length === darabok.length && felso.every((n, i) => n === darabok[i].csomopont)) ki.push({ darabok, szovegek, doc, elsoSorok });
  }
  return ki;
}

const kanonikus = (szovegek: string[]): string => szovegek.join('\n\n') + '\n';
const nemUresSorok = (s: string): string[] => s.split('\n').filter((x) => x.trim() !== '').sort();

describe('generátor: a legfelső szintű blokkok műveletei után a szerkezet a kanonikus (T125)', () => {
  it('a mag rögzített: ugyanazok a dokumentumok, és van elég, többféle', () => {
    const a = generalt(0x5eed, 150);
    expect(a.map((g) => g.doc)).toEqual(generalt(0x5eed, 150).map((g) => g.doc));
    expect(a.length).toBe(150);
    expect(new Set(a.flatMap((g) => g.darabok.map((d) => d.csomopont))).size).toBe(10);
    // a darabokban nincs üres sor: a `\n\n` hiánya valamelyik kötésnél szoros szomszédot jelent
    expect(a.some((g) => g.doc.split('\n\n').length < g.darabok.length)).toBe(true);
    expect(a.some((g) => g.doc.split('\n\n').length === g.darabok.length)).toBe(true);
  });

  it('törlés, mozgatás (elé / mögé) és duplikálás: a kimenet szerkezete a darabok \\n\\n-nel fűzött alakja', () => {
    const rnd = mulberry32(0xbeef);
    const hibak: string[] = [];
    let muveletek = 0;
    for (const g of generalt(0x5eed, 150)) {
      const s = allapot(g.doc);
      const bl = blokkok(s);
      const blokk = (i: number): Blokk => {
        const b = bl.find((x) => x.elsoSor === g.elsoSorok[i]);
        if (!b) throw new Error(`nincs blokk a ${g.elsoSorok[i]}. sorban: ${JSON.stringify(g.doc)}`);
        return b;
      };
      const sorrend = g.szovegek.map((_, k) => k);
      /** `rend`: a darabok várt sorrendje (indexekkel; a `***` darabok szövege azonos lehet, azok cseréje nem változás) */
      const ellenoriz = (nev: string, szz: Szerkesztes | null, rend: number[]) => {
        muveletek++;
        const ki = szz ? alkalmaz(s, szz) : g.doc;
        const elvart = kanonikus(rend.map((k) => g.szovegek[k]));
        try {
          if (!szz) expect(rend.map((k) => g.szovegek[k]), 'a helyben maradónak a sorrend sem változhat').toEqual(g.szovegek);
          else {
            szerkezetEgyezik(ki, elvart);
            expect(nemUresSorok(ki), 'a nem üres sorok halmaza').toEqual(nemUresSorok(elvart));
          }
        } catch (e) {
          hibak.push(`${nev} ${JSON.stringify(g.doc)} → ${JSON.stringify(ki)}: ${(e as Error).message.split('\n')[0]}`);
        }
      };
      for (let i = 0; i < g.darabok.length; i++) {
        if (g.darabok[i].lista) continue; // listaelem: a testvér-műveletek nem „legfelső szintű blokk”
        ellenoriz(`torol(${i})`, torol(s, bl, blokk(i)), sorrend.filter((k) => k !== i));
        ellenoriz(`duplikal(${i})`, duplikal(s, bl, blokk(i)), [...sorrend.slice(0, i + 1), ...sorrend.slice(i)]);
        let j = Math.floor(rnd() * (g.darabok.length - 1));
        if (j >= i) j++;
        for (const hely of ['elott', 'utan'] as const) {
          const maradt = sorrend.filter((k) => k !== i);
          maradt.splice(maradt.indexOf(j) + (hely === 'utan' ? 1 : 0), 0, i);
          ellenoriz(`mozgat(${i} ${hely} ${j})`, mozgat(s, bl, blokk(i), { blokk: blokk(j), hely }), maradt);
        }
      }
    }
    expect(muveletek).toBeGreaterThan(300);
    expect({ db: hibak.length, elso: hibak.slice(0, 6) }).toEqual({ db: 0, elso: [] });
  }, 30_000);
});

// ---------------------------------------------------------------------- PDF-kiemelés blokk (T036)

// A `core/pdfkiemeles.py` `elemez` függvényének tükre (a vitestből Python nem hívható; a formátum egyetlen helye a
// core): a jelölősor + a közvetlenül alatta álló `>` sorok; a záró sort (`> — [[…]] ^k-…`) kihagyja, a szöveg a
// többi sor `>` utáni, kerekített része szóközzel fűzve. Az oldalszám itt nem számít, csak az (azonosító, szöveg).
const KIEMELES_JELOLO = /^%%manifold-kiemeles (k-[0-9a-f]{4,16}) ([0-9.,;]*)%%[ \t]*$/;
const KIEMELES_ZARO = /^> — (\[\[[^\]]*\]\])(?: \^(k-[0-9a-f]{4,16}))?[ \t]*$/;

function kiemelesek(szoveg: string): [string, string][] {
  const sorok = szoveg.replace(/\r\n/g, '\n').split('\n');
  const ki: [string, string][] = [];
  for (let i = 0; i < sorok.length; i++) {
    const j = KIEMELES_JELOLO.exec(sorok[i]);
    if (!j) continue;
    const szov: string[] = [];
    let n = i + 1;
    for (; n < sorok.length && sorok[n].startsWith('>'); n++) if (!KIEMELES_ZARO.test(sorok[n])) szov.push(sorok[n].slice(1).trim());
    ki.push([j[1], szov.filter(Boolean).join(' ')]);
    i = n - 1;
  }
  return ki;
}

const rendezve = (k: [string, string][]): [string, string][] => [...k].sort((x, y) => (x[0] < y[0] ? -1 : x[0] > y[0] ? 1 : 0));

// A `tests/test_pdfkiemeles.py` kiemelés-fájljának mintájára: frontmatter, H1, oldalanként `## N. oldal`, kiemelésenként
// jelölősor + idézet + záró sor; közöttük a felhasználó saját szövege.
const KIEMELES_FAJL = [
  '---',
  'Tags:',
  '  - Mathematics',
  'Source:',
  '  - "[[10 - Matematika.pdf#page=12]]"',
  '  - "[[10 - Matematika.pdf#page=35]]"',
  'Status:',
  'NN:',
  'Canvas:',
  '---',
  '',
  '# Matematika – kiemelések',
  '',
  '## 12. oldal',
  '',
  '%%manifold-kiemeles k-cccccc 0.1,0.9,0.3,0.02%%',
  '> Korábbi lap',
  '> — [[10 - Matematika.pdf#page=12]] ^k-cccccc',
  '',
  '## 35. oldal',
  '',
  '%%manifold-kiemeles k-bbbbbb 0.1,0.2,0.3,0.02%%',
  '> Fent',
  '> — [[10 - Matematika.pdf#page=35]] ^k-bbbbbb',
  '',
  '%%manifold-kiemeles k-aaaaaa 0.1,0.5,0.3,0.02;0.1,0.52,0.3,0.02%%',
  '> Több soros',
  '> kijelölés',
  '> — [[10 - Matematika.pdf#page=35]] ^k-aaaaaa',
  '',
  'Saját megjegyzés **itt**.',
  '',
  '%%manifold-kiemeles k-eeeeee 0.1,0.9,0.3,0.02%%',
  '> Lent',
  '> — [[10 - Matematika.pdf#page=35]] ^k-eeeeee',
  '',
].join('\n');

describe('PDF-kiemelés: a jelölősor és az idézet egy blokk (T036)', () => {
  it('a tükör az arany mintán a kiemeléseket adja', () => {
    expect(rendezve(kiemelesek(KIEMELES_FAJL))).toEqual([
      ['k-aaaaaa', 'Több soros kijelölés'],
      ['k-bbbbbb', 'Fent'],
      ['k-cccccc', 'Korábbi lap'],
      ['k-eeeeee', 'Lent'],
    ]);
  });

  it('a blokkmodell: a jelölősor a blokk része (jelolo), az első sor az idézeté; a jelölősor nem fogható', () => {
    const s = allapot(KIEMELES_FAJL);
    const bl = blokkok(s);
    const kiemelt = bl.filter((b) => typeof b.jelolo === 'number');
    expect(kiemelt.map((b) => s.doc.line(b.elsoSor).text)).toEqual(['> Korábbi lap', '> Fent', '> Több soros', '> Lent']);
    for (const b of kiemelt) {
      expect(b.jelolo).toBe(b.elsoSor - 1);
      expect(s.doc.line(b.jelolo!).text).toMatch(/^%%manifold-kiemeles /);
      expect(b.tipus).toBe('idezet');
      expect(b.id).toMatch(/^k-/);
      expect(blokkSorban(bl, b.jelolo!)).toBeNull();
    }
    expect(bl.some((b) => s.doc.line(b.elsoSor).text.startsWith('%%manifold-kiemeles'))).toBe(false);
    expect(bl.filter((b) => b.jelolo === null).map((b) => b.tipus)).toEqual(['fejezet', 'fejezet', 'fejezet', 'bekezdes']);
  });

  it('jelölősor idézet nélkül, vagy üres sorral elválasztott idézettel: közönséges bekezdés, nincs jelolo', () => {
    const s = allapot('%%manifold-kiemeles k-aaaaaa 0,0,1,1%%\n\n> Egy\n\n%%manifold-kiemeles k-bbbbbb 0,0,1,1%%\n\nVége\n');
    expect(blokkok(s).map((b) => [b.tipus, b.jelolo])).toEqual([['bekezdes', null], ['idezet', null], ['bekezdes', null], ['bekezdes', null]]);
  });

  const ketto = [
    '## 3. oldal',
    '',
    '%%manifold-kiemeles k-aaaaaa 0.1,0.2,0.4,0.02%%',
    '> Egy',
    '> — [[X.pdf#page=3]] ^k-aaaaaa',
    '',
    '%%manifold-kiemeles k-bbbbbb 0.1,0.5,0.4,0.02%%',
    '> Kettő',
    '> — [[X.pdf#page=3]] ^k-bbbbbb',
    '',
  ].join('\n');

  it('mozgatás: a jelölősor az idézettel együtt mozog; mögé és elé is', () => {
    const csere = [
      '## 3. oldal',
      '',
      '%%manifold-kiemeles k-bbbbbb 0.1,0.5,0.4,0.02%%',
      '> Kettő',
      '> — [[X.pdf#page=3]] ^k-bbbbbb',
      '',
      '%%manifold-kiemeles k-aaaaaa 0.1,0.2,0.4,0.02%%',
      '> Egy',
      '> — [[X.pdf#page=3]] ^k-aaaaaa',
      '',
    ].join('\n');
    expect(mozgatas(ketto, '> Kettő', '> Egy', 'elott')).toBe(csere);
    expect(mozgatas(ketto, '> Egy', '> Kettő', 'utan')).toBe(csere);
    expect(mozgatas(ketto, '> Kettő', '## 3.', 'elott')).toBe(
      [
        '%%manifold-kiemeles k-bbbbbb 0.1,0.5,0.4,0.02%%',
        '> Kettő',
        '> — [[X.pdf#page=3]] ^k-bbbbbb',
        '',
        '## 3. oldal',
        '',
        '%%manifold-kiemeles k-aaaaaa 0.1,0.2,0.4,0.02%%',
        '> Egy',
        '> — [[X.pdf#page=3]] ^k-aaaaaa',
        '',
      ].join('\n'),
    );
  });

  it('a más blokk a kiemelés elé kerül, nem a jelölősor és az idézet közé', () => {
    expect(mozgatas(`${ketto}\nSaját.\n`, 'Saját.', '> Kettő', 'elott')).toBe(
      ketto.replace('%%manifold-kiemeles k-bbbbbb', 'Saját.\n\n%%manifold-kiemeles k-bbbbbb'),
    );
  });

  it('törlés: a jelölősor és az idézet együtt tűnik el; a másik kiemelés érintetlen', () => {
    const s = allapot(ketto);
    expect(alkalmaz(s, torol(s, blokkok(s), sor(s, '> Egy')))).toBe(
      ['## 3. oldal', '', '%%manifold-kiemeles k-bbbbbb 0.1,0.5,0.4,0.02%%', '> Kettő', '> — [[X.pdf#page=3]] ^k-bbbbbb', ''].join('\n'),
    );
  });

  it('duplikálás: a másolat sima idézet, a jelölősor és az azonosító nem másolódik', () => {
    const s = allapot(ketto);
    expect(alkalmaz(s, duplikal(s, blokkok(s), sor(s, '> Egy')))).toBe(
      ketto.replace('^k-aaaaaa\n\n', '^k-aaaaaa\n\n> Egy\n> — [[X.pdf#page=3]]\n\n'),
    );
  });

  it('a jelolo-s blokk nem alakítható át', () => {
    const s = allapot(ketto);
    const b = sor(s, '> Egy');
    expect(b.jelolo).toBe(3);
    for (const cel of [{ tipus: 'szoveg' }, { tipus: 'lista' }, { tipus: 'callout', callout: 'note' }, { tipus: 'kod' }] as AtalakitCel[]) {
      expect(atalakit(s, b, cel), cel.tipus).toBeNull();
    }
  });

  it('az azonosító nélküli kiemelés záró sorára kerül a ^id, nem a jelölősorra', () => {
    const s = allapot('%%manifold-kiemeles k-abcdef 0,0,1,1%%\n> Szöveg\n> — [[X.pdf#page=3]]\n');
    const r = idBeir(s, blokkok(s)[0], 'k-123abc')!;
    expect(alkalmaz(s, r.szerkesztes)).toBe('%%manifold-kiemeles k-abcdef 0,0,1,1%%\n> Szöveg\n> — [[X.pdf#page=3]] ^k-123abc\n');
  });

  it('minden blokkon minden művelet után az (azonosító, szöveg) halmaz a vártnak megfelelő, azonos azonosító nem duplázódik', () => {
    const s = allapot(KIEMELES_FAJL);
    const bl = blokkok(s);
    const eredeti = rendezve(kiemelesek(KIEMELES_FAJL));
    const hibak: string[] = [];
    const ellenoriz = (nev: string, szz: Szerkesztes | null, vart: [string, string][]) => {
      if (!szz) return;
      const ki = rendezve(kiemelesek(alkalmaz(s, szz)));
      if (JSON.stringify(ki) !== JSON.stringify(vart)) hibak.push(`${nev}: ${JSON.stringify(ki)}`);
    };
    for (const b of bl) {
      const nev = `${b.tipus}@${b.elsoSor}`;
      // a törlés a saját kiemelést viszi (a jelolo-s blokknál), egyébként a halmaz változatlan
      const sajat = typeof b.jelolo === 'number' ? KIEMELES_JELOLO.exec(s.doc.line(b.jelolo).text)![1] : null;
      ellenoriz(`torol ${nev}`, torol(s, bl, b), eredeti.filter((k) => k[0] !== sajat));
      ellenoriz(`duplikal ${nev}`, duplikal(s, bl, b), eredeti);
      ellenoriz(`idBeir ${nev}`, idBeir(s, b, 'uj123x')?.szerkesztes ?? null, eredeti);
      for (const cel of [{ tipus: 'szoveg' }, { tipus: 'fejezet', szint: 2 }, { tipus: 'lista' }, { tipus: 'idezet' }, { tipus: 'kod' }] as AtalakitCel[])
        ellenoriz(`atalakit ${cel.tipus} ${nev}`, atalakit(s, b, cel), sajat ? [] : eredeti);
      for (const c of bl) {
        for (const hely of ['elott', 'utan'] as const) ellenoriz(`mozgat ${nev} ${hely} ${c.tipus}@${c.elsoSor}`, mozgat(s, bl, b, { blokk: c, hely }), eredeti);
      }
    }
    expect({ db: hibak.length, elso: hibak.slice(0, 6) }).toEqual({ db: 0, elso: [] });
  }, 30_000);
});

describe('mozgatás: listaelemek', () => {
  it('az elem a gyerekeivel együtt mozog', () => {
    expect(mozgatas('- a\n\t- a1\n\t- a2\n- b\n- c\n', 'a', 'b', 'utan')).toBe('- b\n- a\n\t- a1\n\t- a2\n- c\n');
    expect(mozgatas('- a\n- b\n- c\n', 'c', 'a', 'elott')).toBe('- c\n- a\n- b\n');
  });

  it('szintet vált: gyerekként és kilépve, a behúzás a célhoz igazodik', () => {
    expect(mozgatas('- a\n- b\n- c\n', 'c', 'b', 'gyerek')).toBe('- a\n- b\n\t- c\n');
    expect(mozgatas('- a\n\t- a1\n- b\n', 'a1', 'b', 'utan')).toBe('- a\n- b\n- a1\n');
    expect(mozgatas('- a\n\t- a1\n\t\t- a11\n- b\n', 'a1', 'b', 'gyerek')).toBe('- a\n- b\n\t- a1\n\t\t- a11\n');
    // gyerekes elem első gyereknek
    expect(mozgatas('- a\n- b\n\t- b1\n', 'a', 'b', 'gyerek')).toBe('- b\n\t- a\n\t- b1\n');
  });

  it('a szóközzel behúzott gyerek a másik jelölőszélességhez igazodik', () => {
    expect(mozgatas('- a\n  - a1\n1. x\n', 'a', 'x', 'utan')).toBe('1. x\n2. a\n   - a1\n');
  });

  it('a számozott lista újraszámozódik, ha folyamatos volt; az „1., 1., 1.” nem', () => {
    expect(mozgatas('1. a\n2. b\n3. c\n', 'c', 'a', 'elott')).toBe('1. c\n2. a\n3. b\n');
    expect(mozgatas('1. a\n2. b\n3. c\n', 'a', 'c', 'utan')).toBe('1. b\n2. c\n3. a\n');
    expect(mozgatas('1. a\n1. b\n1. c\n', 'c', 'a', 'elott')).toBe('1. c\n1. a\n1. b\n');
    expect(mozgatas('3. a\n4. b\n5. c\n', 'a', 'c', 'utan')).toBe('3. b\n4. c\n5. a\n');
  });

  it('listák között: a jelölő a cél listájáé, mindkét számozás rendben marad', () => {
    expect(mozgatas('- a\n- b\n\nP\n\n1. x\n2. y\n', 'a', 'x', 'utan')).toBe('- b\n\nP\n\n1. x\n2. a\n3. y\n');
    expect(mozgatas('1. x\n2. y\n3. z\n\nP\n\n- a\n', 'y', 'a', 'utan')).toBe('1. x\n2. z\n\nP\n\n- a\n- y\n');
  });

  it('a feladatjelölő és a laza lista megmarad', () => {
    expect(mozgatas('- [x] a\n- [ ] b\n- [/] c\n', 'a', 'c', 'utan')).toBe('- [ ] b\n- [/] c\n- [x] a\n');
    expect(mozgatas('- a\n\n- b\n\n- c\n', 'a', 'c', 'utan')).toBe('- b\n\n- c\n\n- a\n');
    expect(mozgatas('- a\n\n- b\n\n- c\n', 'c', 'a', 'elott')).toBe('- c\n\n- a\n\n- b\n');
  });

  it('a saját leszármazottjába nem mozgatható; a helyben maradó nem változtat', () => {
    expect(mozgatas('- a\n\t- a1\n- b\n', 'a', 'a1', 'utan')).toBeNull();
    expect(mozgatas('- a\n- b\n', 'a', 'b', 'elott')).toBeNull();
    expect(mozgatas('- a\n- b\n', 'b', 'a', 'utan')).toBeNull();
  });

  it('a lista egyetlen elemének kivétele nem hagy dupla üres sort', () => {
    expect(mozgatas('P\n\n- a\n\nQ\n\n- z\n', 'a', 'z', 'utan')).toBe('P\n\nQ\n\n- z\n- a\n');
  });

  it('CRLF: a sorvég megmarad', () => {
    expect(mozgatas('- a\r\n\t- a1\r\n- b\r\n', 'a', 'b', 'utan', true)).toBe('- b\r\n- a\r\n\t- a1\r\n');
  });
});

describe('duplikálás és törlés', () => {
  it('a listaelem a gyerekeivel megkettőződik; a másolat nem viszi az azonosítót', () => {
    const s = allapot('- a ^k1\n\t- a1\n- b\n');
    expect(alkalmaz(s, duplikal(s, blokkok(s), sor(s, 'a ^k1')))).toBe('- a ^k1\n\t- a1\n- a\n\t- a1\n- b\n');
  });

  it('a számozott lista duplikálás után újraszámozódik', () => {
    const s = allapot('1. a\n2. b\n');
    expect(alkalmaz(s, duplikal(s, blokkok(s), sor(s, 'a')))).toBe('1. a\n2. a\n3. b\n');
  });

  it('legfelső szintű blokk duplikálása; az önálló ^id sor nem másolódik', () => {
    const s = allapot('P\n\nQ\n');
    expect(alkalmaz(s, duplikal(s, blokkok(s), sor(s, 'P')))).toBe('P\n\nP\n\nQ\n');
    const t = allapot('| a |\n|---|\n| 1 |\n\n^t1\n');
    expect(alkalmaz(t, duplikal(t, blokkok(t), blokkok(t)[0]))).toBe('| a |\n|---|\n| 1 |\n\n^t1\n\n| a |\n|---|\n| 1 |\n');
  });

  it('törlés: üres sor nélkül marad a szöveg, a lista számozása rendben', () => {
    const s = allapot('A\n\nB\n\nC\n');
    expect(alkalmaz(s, torol(s, blokkok(s), sor(s, 'B')))).toBe('A\n\nC\n');
    expect(alkalmaz(s, torol(s, blokkok(s), sor(s, 'C')))).toBe('A\n\nB\n');
    expect(alkalmaz(s, torol(s, blokkok(s), sor(s, 'A')))).toBe('B\n\nC\n');
    const l = allapot('1. a\n2. b\n3. c\n');
    expect(alkalmaz(l, torol(l, blokkok(l), sor(l, 'a')))).toBe('1. b\n2. c\n');
    const k = allapot('- a\n\t- a1\n- b\n');
    expect(alkalmaz(k, torol(k, blokkok(k), sor(k, 'a')))).toBe('- b\n');
  });
});

function atalakitva(doc: string, mit: string, cel: AtalakitCel): string | null {
  const s = allapot(doc);
  const sz = atalakit(s, sor(s, mit), cel);
  return sz ? alkalmaz(s, sz) : null;
}

describe('átalakítás: az üres sor nélküli szomszédok nem olvadnak össze (C29.7b, a T035 rokona)', () => {
  it('fejezet → szöveg: a szomszédos szöveges sorok közé üres sor kerül (különben egy bekezdés lenne)', () => {
    expect(atalakitva('## H\ntext\n', 'H', { tipus: 'szoveg' })).toBe('H\n\ntext\n');
    expect(atalakitva('előtte\n## H\n', 'H', { tipus: 'szoveg' })).toBe('előtte\n\nH\n');
    expect(atalakitva('a\n## H\nb\n', 'H', { tipus: 'szoveg' })).toBe('a\n\nH\n\nb\n');
  });

  it('kód és idézet → szöveg ugyanígy; a már üres sorral elválasztott szomszéd nem kap újat', () => {
    expect(atalakitva('a\n```\nx\n```\nb\n', '```', { tipus: 'szoveg' })).toBe('a\n\nx\n\nb\n');
    expect(atalakitva('a\n> q\n\nb\n', 'q', { tipus: 'szoveg' })).toBe('a\n\nq\n\nb\n');
    expect(atalakitva('a\n\n## H\n\nb\n', 'H', { tipus: 'szoveg' })).toBe('a\n\nH\n\nb\n');
  });

  it('idézet/lista/callout cél: az utána álló sort az idézet/listaelem lustán „folytatná” — üres sor kell; az előző bekezdést megszakítja', () => {
    expect(atalakitva('## H\ntext\n', 'H', { tipus: 'idezet' })).toBe('> H\n\ntext\n');
    expect(atalakitva('előtte\n## H\n', 'H', { tipus: 'idezet' })).toBe('előtte\n> H\n');
    expect(atalakitva('előtte\n## H\ntext\n', 'H', { tipus: 'lista' })).toBe('előtte\n- H\n\ntext\n');
    expect(atalakitva('## H\ntext\n', 'H', { tipus: 'callout', callout: 'tip' })).toBe('> [!tip]\n> H\n\ntext\n');
  });

  it('a szerkezet: az átalakított blokk és a szomszédai külön blokkok maradnak', () => {
    const doc = 'a\n## H\nb\n';
    const s = allapot(doc);
    const sz = atalakit(s, sor(s, 'H'), { tipus: 'szoveg' })!;
    const uj = s.update({ changes: sz.changes as never }).state;
    expect(blokkok(uj).map((b) => uj.doc.line(b.elsoSor).text)).toEqual(['a', 'H', 'b']);
  });
});

describe('átalakítás', () => {
  it('bekezdés → fejezet, lista, számozott, feladat, idézet, callout, kód', () => {
    expect(atalakitva('Szöveg\n', 'Szöveg', { tipus: 'fejezet', szint: 2 })).toBe('## Szöveg\n');
    expect(atalakitva('Szöveg\n', 'Szöveg', { tipus: 'lista' })).toBe('- Szöveg\n');
    expect(atalakitva('Szöveg\n', 'Szöveg', { tipus: 'szamozott' })).toBe('1. Szöveg\n');
    expect(atalakitva('Szöveg\n', 'Szöveg', { tipus: 'feladat' })).toBe('- [ ] Szöveg\n');
    expect(atalakitva('Szöveg\n', 'Szöveg', { tipus: 'idezet' })).toBe('> Szöveg\n');
    expect(atalakitva('Szöveg\n', 'Szöveg', { tipus: 'callout', callout: 'tip' })).toBe('> [!tip]\n> Szöveg\n');
    expect(atalakitva('Szöveg\n', 'Szöveg', { tipus: 'kod', nyelv: 'py' })).toBe('```py\nSzöveg\n```\n');
  });

  it('a többsoros bekezdésből nem lesz fejezet (nincs sorösszefűzés), a többi igen', () => {
    expect(atalakitva('egy\nkettő\n', 'egy', { tipus: 'fejezet', szint: 1 })).toBeNull();
    expect(atalakitva('egy\nkettő\n', 'egy', { tipus: 'lista' })).toBe('- egy\n  kettő\n');
    expect(atalakitva('egy\nkettő\n', 'egy', { tipus: 'idezet' })).toBe('> egy\n> kettő\n');
  });

  it('fejezet → szöveg és másik szint; azonos szintre nincs változás', () => {
    expect(atalakitva('## Cím ##\n', 'Cím', { tipus: 'szoveg' })).toBe('Cím\n');
    expect(atalakitva('## Cím\n', 'Cím', { tipus: 'fejezet', szint: 3 })).toBe('### Cím\n');
    expect(atalakitva('## Cím\n', 'Cím', { tipus: 'fejezet', szint: 2 })).toBeNull();
  });

  it('callout típusa csak a típusnevet cseréli, a címet és az összecsukást megtartja', () => {
    expect(atalakitva('> [!note]- Cím\n> törzs\n', 'Cím', { tipus: 'callout', callout: 'warning' })).toBe('> [!warning]- Cím\n> törzs\n');
  });

  it('idézet ↔ callout ↔ szöveg', () => {
    expect(atalakitva('> a\n> b\n', 'a', { tipus: 'callout', callout: 'info' })).toBe('> [!info]\n> a\n> b\n');
    expect(atalakitva('> [!tip] Cím\n> törzs\n', 'Cím', { tipus: 'szoveg' })).toBe('Cím\ntörzs\n');
    expect(atalakitva('> a\n> b\n', 'a', { tipus: 'szoveg' })).toBe('a\nb\n');
  });

  it('kód → szöveg, szöveg → kód a belső kerítéshez igazodó kerítéssel', () => {
    expect(atalakitva('```py\nx = 1\n```\n', '```py', { tipus: 'szoveg' })).toBe('x = 1\n');
    expect(atalakitva('van ``` benne\n', 'van', { tipus: 'kod' })).toBe('````\nvan ``` benne\n````\n');
  });

  it('listaelem: a jelölő cserélődik, a gyerekek érintetlenek; a feladatból sima elem', () => {
    expect(atalakitva('- a\n\t- a1\n', '=- a', { tipus: 'szamozott' })).toBe('1. a\n\t- a1\n');
    expect(atalakitva('- [x] a\n', '[x] a', { tipus: 'lista' })).toBe('- a\n');
    expect(atalakitva('- a\n', '=- a', { tipus: 'feladat' })).toBe('- [ ] a\n');
    expect(atalakitva('1. a\n', '1. a', { tipus: 'lista' })).toBe('- a\n');
  });

  it('gyerekes vagy beágyazott listaelemből nem lesz fejezet; a legfelső szintű listaelemből igen, a lista kettéválik', () => {
    expect(atalakitva('- a\n\t- a1\n', '=- a', { tipus: 'fejezet', szint: 1 })).toBeNull();
    expect(atalakitva('- a\n\t- a1\n', 'a1', { tipus: 'szoveg' })).toBeNull();
    expect(atalakitva('- a\n- b\n- c\n', 'b', { tipus: 'szoveg' })).toBe('- a\n\nb\n\n- c\n');
    expect(atalakitva('- a\n- b\n', 'b', { tipus: 'fejezet', szint: 2 })).toBe('- a\n\n## b\n');
  });

  it('a blokkazonosítós blokk nem lesz fejezet vagy kód, a szöveges átalakítás megtartja az azonosítót', () => {
    expect(atalakitva('Szöveg ^k1\n', 'Szöveg', { tipus: 'fejezet', szint: 1 })).toBeNull();
    expect(atalakitva('Szöveg ^k1\n', 'Szöveg', { tipus: 'kod' })).toBeNull();
    expect(atalakitva('Szöveg ^k1\n', 'Szöveg', { tipus: 'lista' })).toBe('- Szöveg ^k1\n');
  });

  it('táblázat, képlet, elválasztó nem alakítható', () => {
    expect(atalakitva('| a |\n|---|\n| 1 |\n', '| a', { tipus: 'szoveg' })).toBeNull();
    expect(atalakitva('---\n\nx\n', '---', { tipus: 'idezet' })).toBeNull();
  });
});

describe('blokkazonosító és link', () => {
  it('az új azonosító 6 karakteres és egyedi', () => {
    const s = allapot('x ^abcdef\n');
    const lista = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5];
    let i = 0;
    const id = ujBlokkId(s, () => lista[i++ % lista.length]);
    expect(id).toMatch(/^[a-z0-9]{6}$/);
    expect(id).not.toBe('aaaaaa'.slice(0, 6) === 'abcdef' ? 'x' : 'abcdef');
    expect(ujBlokkId(s)).toMatch(/^[a-z0-9]{6}$/);
  });

  it('szöveges blokk: a sorvégre; a listaelemnél a saját szöveg végére (a gyerek lista előtt)', () => {
    const s = allapot('Para\nmásodik sor\n\n- elem\n\t- gyerek\n');
    expect(alkalmaz(s, idBeir(s, sor(s, 'Para'), 'k1')!.szerkesztes)).toBe('Para\nmásodik sor ^k1\n\n- elem\n\t- gyerek\n');
    expect(alkalmaz(s, idBeir(s, sor(s, '=- elem'), 'k2')!.szerkesztes)).toBe('Para\nmásodik sor\n\n- elem ^k2\n\t- gyerek\n');
  });

  it('nem szöveges blokk: önálló sorba, üres sorral; az idézet a sorvégre', () => {
    const s = allapot('| a |\n|---|\n| 1 |\n\nUtána\n');
    expect(alkalmaz(s, idBeir(s, blokkok(s)[0], 'k3')!.szerkesztes)).toBe('| a |\n|---|\n| 1 |\n\n^k3\n\nUtána\n');
    const t = allapot('```js\nx\n```\n');
    expect(alkalmaz(t, idBeir(t, blokkok(t)[0], 'k4')!.szerkesztes)).toBe('```js\nx\n```\n\n^k4\n');
    const q = allapot('> [!tip] T\n> törzs\n');
    expect(alkalmaz(q, idBeir(q, blokkok(q)[0], 'k5')!.szerkesztes)).toBe('> [!tip] T\n> törzs ^k5\n');
  });

  it('a meglévő azonosító marad; a fejezetnek nincs azonosítója', () => {
    const s = allapot('Para ^van\n\n## Fej\n');
    const r = idBeir(s, sor(s, 'Para'), 'uj123x')!;
    expect(r.id).toBe('van');
    expect(r.szerkesztes).toBeNull();
    expect(idBeir(s, sor(s, 'Fej'), 'uj123x')).toBeNull();
  });

  it('a link: blokknál [[Név#^id]], fejezetnél [[Név#Cím]]', () => {
    const s = allapot('Para ^k1\n\n## Fej: #egy | két\n');
    expect(blokkLink('Jegyzet', sor(s, 'Para'), 'k1', 'Para ^k1')).toBe('[[Jegyzet#^k1]]');
    expect(blokkLink('Jegyzet', sor(s, 'Fej'), null, '## Fej: #egy | két')).toBe('[[Jegyzet#Fej: egy két]]');
  });
});

describe('minden művelet után érvényes Markdown', () => {
  it('a mozgatás/átalakítás/duplikálás/törlés kimenete hibátlanul elemződik', () => {
    const doc = '# Cím\n\n- a\n\t- a1\n- b\n\n1. x\n2. y\n\nPara\n\n> [!tip] T\n> törzs\n\n| a |\n|---|\n| 1 |\n';
    const s = allapot(doc);
    const bl = blokkok(s);
    for (const b of bl) {
      for (const sz of [duplikal(s, bl, b), torol(s, bl, b)]) if (sz) expect(hibatlan(alkalmaz(s, sz))).toBe(true);
      for (const cel of bl) for (const hely of ['elott', 'utan', 'gyerek'] as const) {
        const sz = mozgat(s, bl, b, { blokk: cel, hely });
        if (sz) expect(hibatlan(alkalmaz(s, sz))).toBe(true);
      }
    }
  });
});

describe('C31: nem szöveges cél-sor (T160) és egységek (T161)', () => {
  it('a kódkerítéssel záruló callout önálló ^id-t kap, a kerítést nem töri', () => {
    const s = allapot('> [!example] C\n> ```\n> x = 1\n> ```\n\nUtána\n');
    const b = blokkok(s)[0];
    expect(b.idMod).toBe('onallo');
    expect(alkalmaz(s, idBeir(s, b, 'k6')!.szerkesztes)).toBe('> [!example] C\n> ```\n> x = 1\n> ```\n\n^k6\n\nUtána\n');
    const uj = allapot('> [!example] C\n> ```\n> x = 1\n> ```\n\n^k6\n\nUtána\n');
    expect(blokkok(uj)[0].id).toBe('k6');
  });

  it('a kerítéssel kezdődő listaelem nem kap azonosítót (a nyelv nem sérül)', () => {
    const s = allapot('- szöveg\n- ```js\n  x\n  ```\n');
    const b = sor(s, '- ```js');
    expect(b.idMod).toBe('nincs');
    expect(idBeir(s, b, 'k7')).toBeNull();
    expect(sor(s, '- szöveg').idMod).toBe('sorveg');
  });

  it('a több bekezdéses %% megjegyzés egy blokk, a mozgatás egészben viszi', () => {
    const doc = 'Előtte\n\n%%\nElső.\n\nMásodik.\n%%\n\nUtána\n';
    const s = allapot(doc);
    const bl = blokkok(s);
    expect(bl.map((b) => [b.elsoSor, b.utolsoSor, b.mozgathato])).toEqual([[1, 1, true], [3, 7, true], [9, 9, true]]);
    expect(mozgatas(doc, 'Utána', '%%', 'elott')).toBe('Előtte\n\nUtána\n\n%%\nElső.\n\nMásodik.\n%%\n');
  });

  it('a nyitott HTML-konténer egy blokk; közé nem ejthető blokk', () => {
    const doc = '<details>\n<summary>S</summary>\n\nBelső.\n\n</details>\n\nUtána\n';
    const s = allapot(doc);
    const bl = blokkok(s);
    expect(bl.map((b) => [b.tipus, b.elsoSor, b.utolsoSor])).toEqual([['html', 1, 6], ['bekezdes', 8, 8]]);
    expect(blokkSorban(bl, 4)?.elsoSor).toBe(1);
  });

  it('a lezáratlan kerítés nem mozgatható, és utána nem ejthető blokk', () => {
    const doc = 'Első\n\n```\nnyitott kód\n';
    const s = allapot(doc);
    const kod = blokkok(s)[1];
    expect(kod.mozgathato).toBe(false);
    expect(mozgatas(doc, '```', 'Első', 'elott')).toBeNull();
    expect(mozgatas(doc, 'Első', '```', 'utan')).toBeNull();
    const zart = blokkok(allapot('```\nkód\n```\n'))[0];
    expect(zart.mozgathato).toBe(true);
  });
});
