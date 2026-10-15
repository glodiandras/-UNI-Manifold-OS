import { describe, expect, it } from 'vitest';
import { kezdoAllas, pozicioFrissites } from '../src/lib/graf/kezdoallas';
import { lekerdezesFordit, egyszerusit } from '../src/lib/graf/lekerdezes';
import {
  GrafAdat,
  kereses,
  lathatoElDb,
  lathatosag,
  szinCsoportok,
  type FajlTipus,
  type GrafMeta,
  type GrafValasz,
} from '../src/lib/graf/modell';

const VALASZ: GrafValasz = {
  csucsok: ['Cél.md', 'A/Jegyzet.md', 'A/Forrás.md', 'B/Jegyzet.md', 'kep.png', 'Vászon.canvas', 'Árva.md', 'Önhurok.md', 'doc.pdf'],
  elek: [
    ['A/Forrás.md', 'A/Jegyzet.md'],
    ['A/Forrás.md', 'B/Jegyzet.md'],
    ['A/Jegyzet.md', 'A/Forrás.md'], // a másik irány: egy irányítatlan él, kétirányú
    ['Cél.md', 'kep.png'],
    ['Vászon.canvas', 'Cél.md'],
    ['Önhurok.md', 'Önhurok.md'],
    ['B/Jegyzet.md', 'Cél.md'],
  ],
  feloldatlan: { 'nincs ilyen': 2 },
};

const TIPUS: Record<string, FajlTipus> = { 'kep.png': 'kep', 'Vászon.canvas': 'canvas', 'doc.pdf': 'pdf' };
const tipus = (u: string): FajlTipus | undefined => TIPUS[u] ?? 'md';

const META: GrafMeta = {
  cimkek: { 'Cél.md': ['Math/Algebra', 'Fontos'], 'A/Jegyzet.md': ['Fizika'], 'B/Jegyzet.md': ['Math'] },
  tulajdonsagok: {
    'Cél.md': { Status: ['Kész'], Tags: ['Math/Algebra'] },
    'A/Jegyzet.md': { Status: ['Folyamatban'] },
  },
};

const g = () => new GrafAdat(VALASZ, tipus, META);
const SZURO = { lekerdezes: '', mellekletek: true, arvak: true };
const nevek = (gr: GrafAdat, m: Uint8Array) => gr.ut.filter((_, i) => m[i]);

describe('GrafAdat: a csúcs- és élhalmaz a core gráfja', () => {
  it('minden csúcs és minden irányított él megmarad, és semmi nem kerül hozzá', () => {
    const gr = g();
    expect(gr.n).toBe(VALASZ.csucsok.length);
    expect(gr.ut).toEqual(VALASZ.csucsok);
    expect(gr.hianyzoElek).toBe(0);
    expect(new Set(gr.iranyitottElek().map((e) => e.join('→')))).toEqual(new Set(VALASZ.elek.map((e) => e.join('→'))));
    expect(gr.iranyitott.length / 2).toBe(VALASZ.elek.length);
  });

  it('az alap nézet (minden kapcsoló be, nincs szűrő) a teljes csúcshalmaz', () => {
    const gr = g();
    const r = lathatosag(gr, SZURO);
    expect(r.csucsDb).toBe(gr.n);
    expect(nevek(gr, r.lathato)).toEqual(VALASZ.csucsok);
  });

  it('az irányítatlan élek egyediek, az irány-bitek jók, az önhurok külön él nélkül', () => {
    const gr = g();
    const el = new Map<string, number>();
    for (let e = 0; e < gr.elek.length / 2; e++) el.set(`${gr.ut[gr.elek[2 * e]]}|${gr.ut[gr.elek[2 * e + 1]]}`, gr.irany[e]);
    expect(gr.elek.length / 2).toBe(5); // 7 irányított − önhurok − a kétirányú pár egyik fele
    const fj = gr.csucsIndex('A/Forrás.md');
    const jg = gr.csucsIndex('A/Jegyzet.md');
    const [a, b] = fj < jg ? [fj, jg] : [jg, fj];
    const e = [...Array(gr.elek.length / 2).keys()].find((k) => gr.elek[2 * k] === a && gr.elek[2 * k + 1] === b)!;
    expect(gr.irany[e]).toBe(3);
    expect(gr.onhurok[gr.csucsIndex('Önhurok.md')]).toBe(1);
    expect(gr.fok[gr.csucsIndex('Önhurok.md')]).toBe(0);
    expect(el.size).toBe(5);
  });

  it('a CSR-szomszédság szimmetrikus és fokonként egyezik', () => {
    const gr = g();
    for (let i = 0; i < gr.n; i++) {
      expect(gr.szomszedok(i).length).toBe(gr.fok[i]);
      for (const j of gr.szomszedok(i)) expect([...gr.szomszedok(j)]).toContain(i);
    }
  });

  it('a nem csúcs végpontú élt kihagyja és számolja (a core gráfjában ilyen nincs)', () => {
    const gr = new GrafAdat({ csucsok: ['a.md'], elek: [['a.md', 'nincs.md']] }, tipus);
    expect(gr.hianyzoElek).toBe(1);
    expect(gr.iranyitott.length).toBe(0);
  });

  it('az aláírás a szerkezettől függ, a metaadattól nem', () => {
    const a = g().alairas;
    expect(new GrafAdat(VALASZ, tipus, null).alairas).toBe(a);
    expect(new GrafAdat({ ...VALASZ, elek: VALASZ.elek.filter((e) => e[0] !== 'Cél.md') }, tipus, META).alairas).not.toBe(a);
    // egy él másik iránya nem szerkezeti változás (a fizika ugyanaz): csak az aláírás nem változik, a nyíl igen
    expect(new GrafAdat({ ...VALASZ, elek: VALASZ.elek.slice(1) }, tipus, META).alairas).toBe(a);
    expect(new GrafAdat({ ...VALASZ, csucsok: [...VALASZ.csucsok, 'Új.md'] }, tipus, META).alairas).not.toBe(a);
  });

  it('a név a jegyzetnél kiterjesztés nélkül, máshol teljes', () => {
    const gr = g();
    expect(gr.nev[gr.csucsIndex('A/Forrás.md')]).toBe('Forrás');
    expect(gr.nev[gr.csucsIndex('kep.png')]).toBe('kep.png');
  });
});

describe('lekérdezés-nyelv', () => {
  const gr = g();
  const t = (q: string) => nevek(gr, lathatosag(gr, { ...SZURO, lekerdezes: q }).lathato);

  it('üres lekérdezés mindent mutat', () => {
    expect(t('').length).toBe(gr.n);
    expect(t('   ').length).toBe(gr.n);
  });

  it('path: és file: ékezetfüggetlen résszel', () => {
    expect(t('path:forras')).toEqual(['A/Forrás.md']);
    expect(t('path:"A/"')).toEqual(['A/Jegyzet.md', 'A/Forrás.md']);
    expect(t('file:.canvas')).toEqual(['Vászon.canvas']);
    expect(t('file:/\\.(png|pdf)$/')).toEqual(['kep.png', 'doc.pdf']);
  });

  it('tag: a címkét és az alatta állókat találja, kis-nagybetűtől függetlenül', () => {
    expect(t('tag:#math')).toEqual(['Cél.md', 'B/Jegyzet.md']);
    expect(t('tag:#Math/Algebra')).toEqual(['Cél.md']);
    expect(t('tag:#mat')).toEqual([]); // nem szegmenshatáron
  });

  it('[tulajdonság] és [kulcs:érték]', () => {
    expect(t('[status]')).toEqual(['Cél.md', 'A/Jegyzet.md']);
    expect(t('[Status:kesz]')).toEqual(['Cél.md']);
    expect(t('[status:folyamat]')).toEqual(['A/Jegyzet.md']);
  });

  it('ÉS, OR, tagadás, zárójel', () => {
    expect(t('tag:#math path:B/')).toEqual(['B/Jegyzet.md']);
    expect(t('path:B/ OR path:A/')).toEqual(['A/Jegyzet.md', 'A/Forrás.md', 'B/Jegyzet.md']);
    expect(t('-path:A/ file:.md')).toEqual(['Cél.md', 'B/Jegyzet.md', 'Árva.md', 'Önhurok.md']);
    expect(t('(path:A/ OR path:B/) -tag:#fizika')).toEqual(['A/Forrás.md', 'B/Jegyzet.md']);
  });

  it('sima szó a névben vagy az útban', () => {
    expect(t('jegyzet')).toEqual(['A/Jegyzet.md', 'B/Jegyzet.md']);
    expect(t('"a/jegy"')).toEqual(['A/Jegyzet.md']);
  });

  it('a nem támogatott elem jelölt, és a szűrő nem hat', () => {
    expect(lekerdezesFordit('line:(a b)').tamogatott).toBe(false);
    expect(lekerdezesFordit('/tartalom/').tamogatott).toBe(false);
    expect(lekerdezesFordit('path:/(/').tamogatott).toBe(false); // hibás regex
    const r = lathatosag(gr, { ...SZURO, lekerdezes: 'tag:#math section:x' });
    expect(r.nemTamogatott).toBe('section:');
    expect(r.csucsDb).toBe(gr.n);
  });

  it('a hibás zárójel és az árva `)` nem dob', () => {
    expect(() => t('(path:A/')).not.toThrow();
    expect(t('(path:A/')).toEqual(['A/Jegyzet.md', 'A/Forrás.md']);
    expect(() => t('path:A/)')).not.toThrow();
  });

  it('egyszerusit: ékezet és nagybetű', () => {
    expect(egyszerusit('Ütőér ŐŰ')).toBe('utoer ou');
  });
});

describe('szűrők és helyi gráf', () => {
  const gr = g();

  it('a mellékletek kapcsolója a nem jegyzet-szerű fájlokat rejti', () => {
    const r = lathatosag(gr, { ...SZURO, mellekletek: false });
    expect(nevek(gr, r.lathato)).not.toContain('kep.png');
    expect(nevek(gr, r.lathato)).not.toContain('doc.pdf');
    expect(nevek(gr, r.lathato)).toContain('Vászon.canvas'); // a canvas jegyzet-szerű
  });

  it('az árvák kapcsolója a fok nélküli csúcsokat rejti', () => {
    const r = lathatosag(gr, { ...SZURO, arvak: false });
    expect(nevek(gr, r.lathato)).not.toContain('Árva.md');
    expect(nevek(gr, r.lathato)).not.toContain('Önhurok.md');
    expect(nevek(gr, r.lathato)).toContain('Cél.md');
  });

  it('helyi gráf: 1, 2, 3 lépés a középpontból, irányítatlanul', () => {
    const k = gr.csucsIndex('Cél.md');
    const lep = (melyseg: number) => nevek(gr, lathatosag(gr, SZURO, { kozeppont: k, melyseg }).lathato).sort();
    expect(lep(0)).toEqual(['Cél.md']);
    expect(lep(1)).toEqual(['B/Jegyzet.md', 'Cél.md', 'Vászon.canvas', 'kep.png']);
    expect(lep(2)).toEqual(['A/Forrás.md', 'B/Jegyzet.md', 'Cél.md', 'Vászon.canvas', 'kep.png']);
    expect(lep(3)).toEqual(['A/Forrás.md', 'A/Jegyzet.md', 'B/Jegyzet.md', 'Cél.md', 'Vászon.canvas', 'kep.png']);
    expect(lep(9)).toEqual(lep(3)); // a mélység legfeljebb 3
  });

  it('helyi gráfban a szűrő a bejárást is korlátozza, a középpont mindig látszik', () => {
    const k = gr.csucsIndex('Cél.md');
    const r = lathatosag(gr, { ...SZURO, lekerdezes: 'path:A/' }, { kozeppont: k, melyseg: 3 });
    expect(nevek(gr, r.lathato)).toEqual(['Cél.md']); // az A/ csúcsai csak a szűrőn kívüli B/Jegyzet.md-n át érhetők el
  });

  it('a látható élek száma a látható csúcsokon számol', () => {
    const r = lathatosag(gr, SZURO);
    expect(lathatoElDb(gr, r.lathato)).toBe(gr.elek.length / 2);
    const k = lathatosag(gr, SZURO, { kozeppont: gr.csucsIndex('Cél.md'), melyseg: 1 });
    expect(lathatoElDb(gr, k.lathato)).toBe(3);
  });
});

describe('színcsoportok és keresés', () => {
  const gr = g();

  it('az első illeszkedő csoport nyer, a nem támogatott jelölt', () => {
    const r = szinCsoportok(gr, [
      { lekerdezes: 'tag:#math', szin: '#4caf50' },
      { lekerdezes: 'file:.canvas', szin: '#f00000' },
      { lekerdezes: 'path:A/', szin: '#0000ff' },
      { lekerdezes: 'line:x', szin: '#000000' },
    ]);
    expect(r.csoport[gr.csucsIndex('Cél.md')]).toBe(0);
    expect(r.csoport[gr.csucsIndex('B/Jegyzet.md')]).toBe(0);
    expect(r.csoport[gr.csucsIndex('Vászon.canvas')]).toBe(1);
    expect(r.csoport[gr.csucsIndex('A/Jegyzet.md')]).toBe(2);
    expect(r.csoport[gr.csucsIndex('Árva.md')]).toBe(-1);
    expect(r.tamogatott).toEqual([true, true, true, false]);
  });

  it('a keresés ékezetfüggetlen, névkezdet → névrész → út sorrendben', () => {
    expect(kereses(gr, 'arva', null).map((i) => gr.ut[i])).toEqual(['Árva.md']);
    expect(kereses(gr, 'jegy', null).map((i) => gr.ut[i])).toEqual(['B/Jegyzet.md', 'A/Jegyzet.md']); // döntetlen: nagyobb fok
    expect(kereses(gr, 'a/', null).map((i) => gr.ut[i])).toEqual(['A/Forrás.md', 'A/Jegyzet.md']); // útrész, döntetlen: rövidebb név
    expect(kereses(gr, '  ', null)).toEqual([]);
  });

  it('a rejtett csúcs a találatok végére kerül, de megmarad (a keresés oldja a szűrőt)', () => {
    const lath = lathatosag(gr, { ...SZURO, lekerdezes: 'path:B/' }).lathato;
    const t = kereses(gr, 'jegy', lath).map((i) => gr.ut[i]);
    expect(t).toEqual(['B/Jegyzet.md', 'A/Jegyzet.md']);
  });
});

describe('kezdőállás', () => {
  const gr = g();

  it('determinisztikus és minden csúcsnak van véges helye', () => {
    const a = kezdoAllas(gr);
    const b = kezdoAllas(gr);
    expect([...a]).toEqual([...b]);
    expect(a.every(Number.isFinite)).toBe(true);
    expect(new Set(Array.from({ length: gr.n }, (_, i) => `${a[2 * i]},${a[2 * i + 1]}`)).size).toBe(gr.n);
  });

  it('frissítéskor a régi hely marad, az új csúcs a szomszédai közelébe kerül', () => {
    const regi = new Map<string, [number, number]>([
      ['Cél.md', [100, 100]],
      ['B/Jegyzet.md', [120, 100]],
    ]);
    const { poz, uj } = pozicioFrissites(gr, regi);
    expect(uj).toBe(gr.n - 2);
    expect(poz[2 * gr.csucsIndex('Cél.md')]).toBe(100);
    const k = gr.csucsIndex('Vászon.canvas'); // szomszédja a Cél.md
    expect(Math.abs(poz[2 * k] - 100)).toBeLessThan(10);
    expect(Math.abs(poz[2 * k + 1] - 100)).toBeLessThan(10);
  });
});
