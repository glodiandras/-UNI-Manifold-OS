// F11 / 11-graph (teljesítmény): nagy gráfon (≥ 5000 fájl-csúcs, plusz címke- és feloldatlan csúcsok) az interakció nem blokkolja a
// felületet. A fő szálon futó lépések mérve, bőkezű (lassú CI-n is tartó) korlátokkal — a korlát a szándék: a fizika Workerben
// számol, a kép egy képkockában (nem folyamatosan), a virtuális csúcsok száma korlátos, és a korlát elérése jelzett (nem csendes).
// A mért idők a jelentésbe kerülnek (konzol). A pontos ms-kapu a perf-készlet dolga (tests/perf).
import { describe, expect, it, vi } from 'vitest';
import { Fizika } from '../src/lib/graf/fizika';
import { GrafAdat, kereses, lathatoElDb, lathatosag, szinCsoportok, MAX_VIRTUALIS, type FajlTipus, type GrafMeta, type GrafValasz } from '../src/lib/graf/modell';
import { GrafRajzolo } from '../src/lib/graf/rajzolo';
import { SZINEK } from './graf-vaszon-segedek';
import { szintetikus } from './graf-segedek';

const N = 6000;
const TAG_DB = 300;
const FELOLDATLAN_DB = 2500;

function nagy(n = N, feloldatlan = FELOLDATLAN_DB) {
  const sz = szintetikus(n, n * 3);
  const csucsok = Array.from({ length: n }, (_, i) => `Mappa${i % 40}/J${i}.md`);
  const elek: [string, string][] = [];
  for (let e = 0; e < sz.elek.length; e += 2) elek.push([csucsok[sz.elek[e]], csucsok[sz.elek[e + 1]]]);
  const cimkek: Record<string, string[]> = {};
  const cimke_csucsok: GrafMeta['cimke_csucsok'] = {};
  for (let t = 0; t < TAG_DB; t++) cimke_csucsok![`cimke${t}`] = { nev: `cimke${t}`, db: 0 };
  for (let i = 0; i < n; i += 2) cimkek[csucsok[i]] = [`cimke${(i / 2) % TAG_DB}`, `Cimke${((i / 2) * 7) % TAG_DB}`]; // mind a 300 címkének van jegyzete
  const feloldatlan_elek: [string, string][] = [];
  for (let k = 0; k < feloldatlan; k++) feloldatlan_elek.push([csucsok[(k * 3) % n], `Hiány ${k}`]);
  const valasz: GrafValasz = { csucsok, elek };
  const meta: GrafMeta = { cimkek, tulajdonsagok: {}, cimke_csucsok, feloldatlan_elek };
  return { valasz, meta, poz: sz.poz };
}

const tipus = (): FajlTipus => 'md';
const ms = (f: () => void): number => {
  const t0 = performance.now();
  f();
  return performance.now() - t0;
};
const jelent = (nev: string, t: number) => console.info(`graf-teljesitmeny: ${nev}: ${t.toFixed(1)} ms`);

describe(`nagy gráf (${N} fájl + ${TAG_DB} címke + ${FELOLDATLAN_DB} feloldatlan cél)`, () => {
  const { valasz, meta } = nagy();
  let g!: GrafAdat;

  it('a csúcstábla felépítése a fő szálon gyors (nem blokkol)', () => {
    const t = ms(() => (g = new GrafAdat(valasz, tipus, meta)));
    jelent('GrafAdat felépítése', t);
    expect(g.nValos).toBe(N);
    expect(g.n).toBeGreaterThanOrEqual(N + TAG_DB + FELOLDATLAN_DB);
    expect(g.csonkolt).toBe(false);
    expect(t).toBeLessThan(3000);
  });

  it('a szűrés (globális és helyi), a keresés és a színezés mind a kapcsolókkal együtt gyors', () => {
    const be = { lekerdezes: '', mellekletek: true, arvak: true, cimkek: true, letezoCsak: false };
    let r!: ReturnType<typeof lathatosag>;
    const tGlobalis = ms(() => (r = lathatosag(g, be)));
    jelent('lathatosag (globális, minden kapcsoló be)', tGlobalis);
    expect(r.csucsDb).toBe(g.n);
    expect(tGlobalis).toBeLessThan(1000);

    const tSzoveges = ms(() => lathatosag(g, { ...be, lekerdezes: 'path:Mappa3/ OR tag:#cimke5' }));
    jelent('lathatosag (szöveges szűrő)', tSzoveges);
    expect(tSzoveges).toBeLessThan(1500);

    const tHelyi = ms(() => (r = lathatosag(g, be, { kozeppont: 10, melyseg: 3 })));
    jelent('lathatosag (helyi, 3 lépés)', tHelyi);
    expect(r.csucsDb).toBeLessThan(g.n);
    expect(tHelyi).toBeLessThan(1000);

    const lathato = lathatosag(g, be).lathato;
    const tKeres = ms(() => expect(kereses(g, 'j12', lathato, 8).length).toBeGreaterThan(0));
    jelent('kereses', tKeres);
    expect(tKeres).toBeLessThan(500);

    const tSzin = ms(() => szinCsoportok(g, Array.from({ length: 10 }, (_, i) => ({ lekerdezes: `path:Mappa${i}/`, szin: '#336699' }))));
    jelent('szinCsoportok (10 csoport)', tSzin);
    expect(tSzin).toBeLessThan(1500);
    expect(lathatoElDb(g, lathato)).toBeGreaterThan(0);
  });

  it('egy teljes kép és az egérkövetés (találat-keresés) a fő szálon belátható költségű', () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] }); // a performance.now valódi marad: a mérés érvényes
    vi.stubGlobal('requestAnimationFrame', (f: FrameRequestCallback) => setTimeout(() => f(performance.now()), 16) as unknown as number);
    vi.stubGlobal('cancelAnimationFrame', (id: number) => clearTimeout(id));
    vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
    try {
      const noop = new Proxy({ measureText: () => ({ width: 10 }) } as Record<string, unknown>, {
        get: (t, k) => (k in t ? t[k as string] : () => undefined),
        set: () => true,
      }) as unknown as CanvasRenderingContext2D;
      const canvas = document.createElement('canvas');
      vi.spyOn(canvas, 'getContext').mockImplementation(() => noop as never);
      canvas.getBoundingClientRect = () => ({ left: 0, top: 0, right: 1200, bottom: 800, width: 1200, height: 800, x: 0, y: 0, toJSON() {} });
      const r = new GrafRajzolo(canvas, { megnyit: vi.fn(), fizika: vi.fn() });
      try {
        r.meretValtozas();
        r.szinBeallit(SZINEK, '11px sans-serif');
        const lathato = lathatosag(g, { lekerdezes: '', mellekletek: true, arvak: true, cimkek: true, letezoCsak: false }).lathato;
        // a csúcsok a vászonra szórva (a teljes nézet: mind látszik, a legrosszabb eset a rajznak)
        const poz = new Float32Array(2 * g.n);
        for (let i = 0; i < g.n; i++) {
          poz[2 * i] = ((i * 7919) % 1200) | 0;
          poz[2 * i + 1] = ((i * 104729) % 800) | 0;
        }
        const tBemenet = ms(() => r.bemenet({ adat: g, lathato, csoport: new Int16Array(g.n).fill(-1), csoportSzinek: [], nyil: true, meretSzorzo: 1, vonalSzorzo: 1, szovegHalvany: -3 }));
        jelent('rajzoló bemenete', tBemenet);
        expect(tBemenet).toBeLessThan(1000);
        r.pozBe(poz, false);
        const tKep = ms(() => vi.advanceTimersByTime(40)); // az első kép
        jelent('egy teljes kép (nyilak, a legtöbb felirat)', tKep);
        expect(r.meres.kepek).toBeGreaterThanOrEqual(1);
        expect(Math.max(...r.meres.rajzMs)).toBeLessThan(1500);
        const tHover = ms(() => {
          for (let k = 0; k < 2000; k++) r.csucsAlatt((k * 37) % 1200, (k * 91) % 800);
        });
        jelent('2000 találat-keresés (egér)', tHover);
        expect(tHover).toBeLessThan(500);
        // nyugalomban nincs ütemezett munka: egy kép után a rajz áll (a folyamatos CPU-használat tilos)
        const ut = r.meres.utemezesek;
        vi.advanceTimersByTime(5000);
        expect(r.meres.utemezesek).toBe(ut);
      } finally {
        r.leallit();
      }
    } finally {
      vi.useRealTimers();
      vi.unstubAllGlobals();
      vi.restoreAllMocks();
    }
  });

  it('a kikapcsolt virtuális csúcsok a fizikából kiesnek: nem mozognak és nem terhelik a számolást', () => {
    const be = lathatosag(g, { lekerdezes: '', mellekletek: true, arvak: true, cimkek: false, letezoCsak: true });
    expect(be.csucsDb).toBe(g.nValos);
    const sz = szintetikus(g.n, 1);
    const f = new Fizika(g.n, g.elek.slice(), sz.poz.slice());
    f.aktival(be.lathato);
    const elotte = Float64Array.from([f.x[g.nValos], f.y[g.nValos], f.x[g.n - 1], f.y[g.n - 1]]);
    const t = ms(() => {
      for (let k = 0; k < 3; k++) f.tick();
    });
    jelent('3 fizika-tick (a Workerben fut; itt a fő szálon mérve)', t);
    expect([f.x[g.nValos], f.y[g.nValos], f.x[g.n - 1], f.y[g.n - 1]]).toEqual([...elotte]);
  });
});

describe('a virtuális csúcsok száma korlátos, a korlát jelzett', () => {
  it(`${MAX_VIRTUALIS} fölött a felesleg kimarad, és a csonkolás jelzése be van állítva`, () => {
    const n = 300;
    const { valasz, meta } = nagy(n, MAX_VIRTUALIS + 500);
    meta.cimke_csucsok = {};
    const g = new GrafAdat(valasz, tipus, meta);
    expect(g.csonkolt).toBe(true);
    expect(g.n - g.nValos).toBeLessThanOrEqual(MAX_VIRTUALIS);
    expect(g.n - g.nValos).toBeGreaterThan(MAX_VIRTUALIS - 1);
    // a levágás után a gráf konzisztens: minden él végpontja csúcs, a fokok és a szomszédság egyezik
    for (let e = 0; e < g.elek.length; e++) expect(g.elek[e]).toBeLessThan(g.n);
    expect(g.kezd[g.n]).toBe(g.lista.length);
  });
});
