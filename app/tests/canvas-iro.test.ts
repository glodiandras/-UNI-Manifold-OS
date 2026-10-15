// A canvas pozíció-tudatos elemzője és bájthű írója (C14). A minták a vault négy írásmódját utánozzák
// (Obsidian-natív tömör elemek; `json.dumps(indent=1|2|'\t')`), szintetikus tartalommal.

import { describe, expect, it } from 'vitest';
import { IroHiba, foltoz } from '../src/canvas/iro';
import { egyenlo, elemez, ertekbol, JsonHiba } from '../src/canvas/json';
import { beolvas, type Vaszon } from '../src/canvas/modell';

const csoport = { id: 'aaaaaaaaaaaaaaaa', x: -40, y: 0, width: 900, height: 400, color: '4', type: 'group', label: 'Ókor' };
const fajl = { id: 'bbbbbbbbbbbbbbbb', type: 'file', file: 'T01 - Történelem/Görög.md', x: 0, y: 20, width: 400, height: 300 };
const fajl2 = { id: 'cccccccccccccccc', type: 'file', file: 'T01 - Történelem/Róma.md', x: 460, y: 20, width: 400, height: 300, color: '1' };
const el = { id: 'dddddddddddddddd', fromNode: 'bbbbbbbbbbbbbbbb', fromSide: 'right', toNode: 'cccccccccccccccc', toSide: 'left', color: '1' };
const ALAP = { nodes: [csoport, fajl, fajl2], edges: [el] };

/** Az Obsidian írásmódja: a gyökér tabbal behúzva, az elemek egy sorban, szóköz nélkül, záró sorvég nélkül. */
function obsidian(v: { nodes: unknown[]; edges: unknown[] }): string {
  const t = (a: unknown[]) => (a.length ? `[\n${a.map((x) => '\t\t' + JSON.stringify(x)).join(',\n')}\n\t]` : '[]');
  return `{\n\t"nodes":${t(v.nodes)},\n\t"edges":${t(v.edges)}\n}`;
}

const MINTAK: [string, string][] = [
  ['obsidian', obsidian(ALAP)],
  ['indent=1', JSON.stringify(ALAP, null, 1)],
  ['indent=2 + sorvég', JSON.stringify(ALAP, null, 2) + '\n'],
  ['indent=tab', JSON.stringify(ALAP, null, '\t')],
];

const klon = <T>(x: T): T => JSON.parse(JSON.stringify(x)) as T;
const modell = (s: string) => beolvas(s).vaszon as Vaszon;

/** A két szöveg közti egyetlen eltérő szakasz (az elejétől és a végétől azonos rész nélkül). */
function kulonbseg(a: string, b: string): { regi: string; uj: string } {
  let k = 0;
  while (k < a.length && k < b.length && a[k] === b[k]) k++;
  let v = 0;
  while (v < a.length - k && v < b.length - k && a[a.length - 1 - v] === b[b.length - 1 - v]) v++;
  return { regi: a.slice(k, a.length - v), uj: b.slice(k, b.length - v) };
}

describe('json: pozíció-tudatos elemzés', () => {
  it('az érték azonos a JSON.parse-szal, a helyek a forrásra mutatnak', () => {
    const s = '{ "a" : [1, -2.5e3, true, null, "x\\"y"], "b": {} }';
    const j = elemez(s);
    expect(ertekbol(j)).toEqual(JSON.parse(s));
    if (j.t !== 'obj') throw new Error();
    expect(s.slice(j.tagok[0].kulcsKezd, j.tagok[0].kulcsVeg)).toBe('"a"');
    const tomb = j.tagok[0].ertek;
    if (tomb.t !== 'tomb') throw new Error();
    expect(tomb.elemek.map((e) => s.slice(e.kezd, e.veg))).toEqual(['1', '-2.5e3', 'true', 'null', '"x\\"y"']);
  });

  it('hibás JSON: hely és magyar üzenet', () => {
    for (const rossz of ['{"a":1,}', '{"a" 1}', '[1 2]', '{"a":"x', '{"a":tru}', '01', '{} x', '"\u0001"']) {
      expect(() => elemez(rossz), rossz).toThrow(JsonHiba);
    }
    try {
      elemez('{\n\t"nodes":[\n\t\t{"id":}\n\t]\n}');
    } catch (e) {
      expect(e).toBeInstanceOf(JsonHiba);
      expect((e as JsonHiba).sor).toBe(3);
    }
  });

  it('egyenlőség: a kulcssorrend nem számít, a tömb sorrendje igen', () => {
    expect(egyenlo({ a: 1, b: [1, 2] }, { b: [1, 2], a: 1 })).toBe(true);
    expect(egyenlo({ a: [1, 2] }, { a: [2, 1] })).toBe(false);
    expect(egyenlo({ a: 1 }, { a: 1, b: undefined })).toBe(false);
  });
});

describe('modell: beolvasás és ellenőrzés', () => {
  it('az üres szöveg és a {} üres canvas', () => {
    expect(beolvas('').vaszon).toEqual({});
    expect(beolvas('{}').vaszon).toEqual({});
  });

  it('végzetes hibák: csak olvasható', () => {
    for (const [s, minta] of [
      ['[]', /gyökere/],
      ['{"nodes":{}}', /nem tömb/],
      ['{"nodes":[{"type":"text","x":0,"y":0,"width":1,"height":1}]}', /azonosító/],
      ['{"nodes":[{"id":"a","type":"text","x":"0","y":0,"width":1,"height":1}]}', /„x”/],
      [`{"nodes":[${JSON.stringify(fajl)},${JSON.stringify(fajl)}]}`, /azonos/],
      ['{"nodes":[', /nem érvényes JSON/],
    ] as const) {
      const b = beolvas(s);
      expect(b.vaszon, s).toBeNull();
      expect(b.hiba, s).toMatch(minta);
    }
    expect(beolvas('{"nodes":[').hely?.sor).toBe(1);
  });

  it('figyelmeztetés: ismeretlen típus, nem egész szám, lógó él', () => {
    const b = beolvas(
      JSON.stringify({
        nodes: [{ id: 'a', type: 'kep3d', x: 0.5, y: 0, width: 1, height: 1 }],
        edges: [{ id: 'e', fromNode: 'a', toNode: 'nincs' }],
      }),
    );
    expect(b.hiba).toBeNull();
    expect(b.figyelmeztetesek.join(' ')).toMatch(/kep3d.*nem egész.*nem létező/s);
  });
});

describe('iro: bájthű foltozás mind a négy írásmódban', () => {
  for (const [nev, s] of MINTAK) {
    describe(nev, () => {
      it('változás nélkül ugyanaz a szöveg', () => {
        expect(foltoz(s, modell(s))).toBe(s);
      });

      it('egy node mozgatása: csak az x/y literál változik, és visszamozgatva bájtra az eredeti', () => {
        const v = modell(s);
        const uj = klon(v);
        uj.nodes![1] = { ...uj.nodes![1], x: 120, y: -60 };
        const ki = foltoz(s, uj);
        expect(JSON.parse(ki)).toEqual(uj);
        const d = kulonbseg(s, ki);
        expect(d.regi).not.toMatch(/id|file|width/); // csak a két szám (és ami köztük áll) változott
        expect(d.regi.length).toBeLessThan(20);
        expect(ki.length - s.length).toBe(3); // 0→120 (+2), 20→-60 (+1)
        expect(foltoz(ki, v)).toBe(s);
      });

      it('szín ki és be, címke új kulcsként a tagok végére, a saját elválasztóval', () => {
        const uj = klon(modell(s));
        delete uj.nodes![2].color;
        uj.edges![0] = { ...uj.edges![0], label: 'hatás' };
        const ki = foltoz(s, uj);
        expect(JSON.parse(ki)).toEqual(uj);
        expect(ki).not.toContain('"height":300,"color":"1"');
        expect(ki).toMatch(nev === 'obsidian' ? /"color":"1","label":"hatás"\}/ : /"color": "1",\n\s+"label": "hatás"\n/);
        expect(foltoz(ki, modell(s))).toBe(s);
      });

      it('új szövegkártya a tömb végére, új csoport az első nem-csoport elé, a fájl stílusában', () => {
        const uj = klon(modell(s));
        const szoveg = { id: 'eeeeeeeeeeeeeeee', type: 'text', text: 'Első sor\n„idézet”', x: 0, y: 400, width: 250, height: 60 };
        const csop = { id: 'ffffffffffffffff', type: 'group', x: 0, y: 0, width: 10, height: 10, label: 'Új' };
        uj.nodes!.push(szoveg);
        uj.nodes!.splice(1, 0, csop);
        const ki = foltoz(s, uj);
        expect(JSON.parse(ki)).toEqual(uj);
        expect(ki).toContain('„idézet”'); // nem-ASCII nyersen
        if (nev === 'obsidian') {
          expect(ki).toContain(`\n\t\t${JSON.stringify(szoveg)}\n\t]`);
          expect(ki).toContain(`${JSON.stringify(csoport)},\n\t\t${JSON.stringify(csop)},\n\t\t{"id":"bbbb`);
        } else {
          const be = nev === 'indent=1' ? ' ' : nev === 'indent=tab' ? '\t' : '  ';
          expect(ki).toContain(`\n${be.repeat(3)}"text": "Első sor\\n„idézet”",`);
        }
        // a régi elemek bájtra érintetlenek
        for (const e of [csoport, fajl, fajl2]) expect(ki).toContain(nev === 'obsidian' ? JSON.stringify(e) : `"id": "${e.id}"`);
      });

      it('törlés: az első, a középső és az utolsó elem a vesszőjével', () => {
        for (const k of [0, 1, 2]) {
          const uj = klon(modell(s));
          uj.nodes!.splice(k, 1);
          const ki = foltoz(s, uj);
          expect(JSON.parse(ki), `${k}`).toEqual(uj);
          expect(ki).not.toMatch(/,\s*[\]}]/); // nincs lógó vessző
          expect(ki).not.toMatch(/\[\s*,/);
        }
        const uj = klon(modell(s));
        uj.edges = [];
        const ki = foltoz(s, uj);
        expect(ki).toMatch(/"edges": ?\[\]/);
        // és vissza: az él az üres tömbbe a fájl stílusában
        const vissza = foltoz(ki, modell(s));
        expect(JSON.parse(vissza)).toEqual(modell(s));
        if (nev === 'obsidian') expect(vissza).toBe(s);
      });

      it('az ismeretlen kulcs és a gyökér többi kulcsa megmarad', () => {
        const alap = klon(modell(s)) as Vaszon & { metadata?: unknown };
        alap.nodes![1] = { ...alap.nodes![1], styleAttributes: { border: 'dashed' } };
        alap.metadata = { verzio: 1 };
        const s2 = foltoz(s, alap);
        const uj = klon(alap);
        uj.nodes![1].x = 999;
        const ki = foltoz(s2, uj);
        expect(JSON.parse(ki)).toEqual(uj);
        expect(kulonbseg(s2, ki)).toEqual({ regi: '0', uj: '999' });
      });
    });
  }

  it('a nem érintett string escape-alakja marad (\\u, \\/)', () => {
    const s = '{"nodes":[{"id":"a","type":"text","text":"\\u00e9\\/x","x":0,"y":0,"width":10,"height":10}],"edges":[]}';
    const uj = klon(modell(s));
    uj.nodes![0].x = 20;
    const ki = foltoz(s, uj);
    expect(ki).toBe(s.replace('"x":0', '"x":20'));
  });

  it('a {} és az üres fájl: az Obsidian-natív alak, mindkét tömbbel', () => {
    for (const s of ['{}', '', '{ }\n']) {
      const uj: Vaszon = { nodes: [{ id: '0123456789abcdef', type: 'text', text: 'x', x: 0, y: 0, width: 250, height: 60 }] };
      const ki = foltoz(s, uj);
      expect(ki).toBe('{\n\t"nodes":[\n\t\t{"id":"0123456789abcdef","type":"text","text":"x","x":0,"y":0,"width":250,"height":60}\n\t],\n\t"edges":[]\n}');
      expect(foltoz(s, {})).toBe(s);
    }
  });

  it('a fájlban álló edges kulcs a modellből hiányozva sem törlődik ({} → kártya → szövegcsere)', () => {
    const c = { id: '0123456789abcdef', type: 'text', text: 'x', x: 0, y: 0, width: 250, height: 60 };
    const s1 = foltoz('{}', { nodes: [c] });
    expect(s1).toContain('"edges":[]');
    const s2 = foltoz(s1, { nodes: [{ ...c, text: 'y' }] });
    expect(s2).toBe(s1.replace('"text":"x"', '"text":"y"'));
    expect(foltoz(s1, { nodes: [c] })).toBe(s1);
  });

  it('a hiányzó edges kulcs csak akkor íródik be, ha él kerül bele', () => {
    const s = '{"nodes":[{"id":"a","type":"text","text":"x","x":0,"y":0,"width":1,"height":1},{"id":"b","type":"text","text":"y","x":0,"y":0,"width":1,"height":1}]}';
    const v = modell(s);
    expect(foltoz(s, { ...v, edges: [] })).toBe(s);
    const ki = foltoz(s, { ...v, edges: [{ id: 'e', fromNode: 'a', toNode: 'b' }] });
    expect(ki).toBe(s.slice(0, -1) + ',"edges":[{"id":"e","fromNode":"a","toNode":"b"}]}');
  });

  it('megváltozott sorrend: a tömb újra összeáll, az elemek a saját szövegükkel', () => {
    const s = MINTAK[0][1];
    const uj = klon(modell(s));
    uj.nodes = [uj.nodes![2], uj.nodes![0], { ...uj.nodes![1], x: 5 }];
    const ki = foltoz(s, uj);
    expect(JSON.parse(ki)).toEqual(uj);
    expect(ki).toContain(`${JSON.stringify(fajl2)},\n\t\t${JSON.stringify(csoport)},\n\t\t`);
  });

  it('a nem véges szám elutasítva (nem írunk hibás JSON-t)', () => {
    const s = MINTAK[0][1];
    const uj = klon(modell(s));
    uj.nodes![0].x = Number.NaN;
    expect(() => foltoz(s, uj)).toThrow(IroHiba);
  });
});
