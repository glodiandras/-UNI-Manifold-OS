import { describe, expect, it } from 'vitest';
import { FuzzyIndex, darabol, normalizal, tavolsag } from '../src/lib/kereses/fuzzy';

const NEVEK = [
  'Mértani sorozat',
  'Számtani sorozat',
  'Mátrixok',
  'Matematika érettségi 2026',
  'Őszi szünet terve',
  'Fizika — mozgások',
  'Merev test forgása',
  'Sorozatok határértéke',
];

function index(nevek = NEVEK) {
  return new FuzzyIndex(nevek.map((n) => ({ ertek: n, nev: n, ut: `Matek/${n}.md` })));
}

const elso = (q: string, ix = index()) => ix.keres(q)[0]?.ertek;

describe('normalizálás', () => {
  it('ékezetfüggetlen és kisbetűs', () => {
    expect(normalizal('Mértani ŐSZ űrhajó')).toBe('mertani osz urhajo');
  });
});

describe('távolság', () => {
  it('Damerau–Levenshtein felcseréléssel', () => {
    expect(tavolsag('metrani', 'mertani', 2)).toBe(1);
    expect(tavolsag('mrtani', 'mertani', 2)).toBe(1);
    expect(tavolsag('abc', 'xyz', 1)).toBe(2); // korlát + 1
  });
});

describe('keresés', () => {
  it('ékezet nélkül: „mertani” → Mértani sorozat', () => {
    expect(elso('mertani')).toBe('Mértani sorozat');
  });

  it('elírástűrő: kihagyott, felcserélt és elütött betű', () => {
    expect(elso('mrtani')).toBe('Mértani sorozat');
    expect(elso('metrani')).toBe('Mértani sorozat');
    expect(elso('mertsni')).toBe('Mértani sorozat');
  });

  it('a szókezdet erősebb a részszövegnél és a részsorozatnál', () => {
    const r = index().keres('sor').map((t) => t.ertek);
    expect(r[0]).toBe('Sorozatok határértéke'); // első szó eleje
    expect(r).toContain('Mértani sorozat');
  });

  it('több szó, bármely sorrendben, a sorrend bónuszt kap', () => {
    expect(elso('mert sor')).toBe('Mértani sorozat');
    expect(elso('sor mert')).toBe('Mértani sorozat');
  });

  it('részsorozat szóközök nélkül', () => {
    expect(elso('mertanisor')).toBe('Mértani sorozat');
  });

  it('a szétszórt részsorozat nem találat', () => {
    const ix = index(['Geometriai transzformációk', 'Megtorlás az 1956-os forradalom után', 'Mértani sorozat']);
    expect(ix.keres('mertani').map((t) => t.ertek)).toEqual(['Mértani sorozat']);
    expect(index().keres('msor').map((t) => t.ertek)).toContain('Mértani sorozat'); // szókezdő betűkből
  });

  it('a nem illeszkedő elem kiesik; üres lekérdezés üres', () => {
    expect(index().keres('xyzq')).toEqual([]);
    expect(index().keres('   ')).toEqual([]);
  });

  it('az út kisebb súllyal számít', () => {
    const ix = new FuzzyIndex([
      { ertek: 'a', nev: 'Jegyzet', ut: 'Matek/Analízis' },
      { ertek: 'b', nev: 'Analízis alapjai', ut: 'Matek' },
    ]);
    expect(ix.keres('analizis').map((t) => t.ertek)).toEqual(['b', 'a']);
  });

  it('a bónusz (legutóbbiak) előrébb hoz', () => {
    const ix = index();
    const r = ix.keres('sorozat', { bonusz: (n) => (n === 'Számtani sorozat' ? 40 : 0) });
    expect(r[0].ertek).toBe('Számtani sorozat');
  });

  it('a kiemelés az eredeti név indexeiben van (ékezettel is)', () => {
    const t = index().keres('ertani')[0];
    expect(t.ertek).toBe('Mértani sorozat');
    expect(t.kiemeles).toEqual([[1, 7]]);
    expect(darabol('Mértani sorozat', t.kiemeles)).toEqual([
      { szoveg: 'M', kiemelt: false },
      { szoveg: 'értani', kiemelt: true },
      { szoveg: ' sorozat', kiemelt: false },
    ]);
  });

  it('NFD-ben érkező név is ugyanúgy illeszkedik', () => {
    const nfd = 'Mértani sorozat'.normalize('NFD');
    const ix = new FuzzyIndex([{ ertek: 1, nev: nfd }]);
    const t = ix.keres('mert')[0];
    expect(t.ertek).toBe(1);
    expect(nfd.slice(t.kiemeles[0][0], t.kiemeles[0][1]).normalize('NFC')).toBe('Mért');
  });

  it('a lekérdezés költsége az elemek számával közel lineárisan nő (arány, nem falióra)', () => {
    // T008 (2. audit): az abszolút kapu (4000 elemen < 15 ms / lekérdezés) a perf-készletben van (tests/perf/fuzzy.perf.ts,
    // `bin/mos perf`: terhelés alatt 17–21 ms-ot mértünk a 15 ms-os kapuhoz). Itt a skálázás: a lineáris költség a 4×-es méretre
    // ≈ 4×, egy négyzetes bejárás ≈ 16×. Egymás után, ugyanabban a folyamatban, mediánnal mérünk: a gép terhelése kiesik.
    const szavak = ['sorozat', 'mértani', 'függvény', 'határérték', 'derivált', 'integrál', 'vektor', 'mátrix', 'gráf'];
    const mer = (n: number) => {
      const ix = index(Array.from({ length: n }, (_, i) => `${szavak[i % 9]} ${szavak[(i * 7) % 9]} ${i}`));
      ix.keres('fugveny'); // bemelegítés
      const korok = [0, 1, 2, 3, 4].map(() => {
        const t0 = performance.now();
        for (let r = 0; r < 4; r++) for (const q of ['mertani', 'fugveny hatar', 'drivalt', 'xyz', 'm']) ix.keres(q);
        return performance.now() - t0;
      });
      return korok.sort((a, b) => a - b)[2];
    };
    const kicsi = mer(1000);
    const nagy = mer(4000);
    expect(nagy / kicsi).toBeLessThan(10); // lineáris ≈ 4, négyzetes ≈ 16
    // Terhelés alatt (a teljes, 150 fájlos vitest-futás) a két mérés 9 s volt, és az alap 5 s-os időkorlát lejárt; az arány
    // nem függ a falióra hosszától, ezért az időkorlát bővebb
  }, 30_000);
});
