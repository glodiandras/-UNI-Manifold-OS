// F11 / 11-graph-02, 11-graph-03: a gráf virtuális csúcsai — a címke és a még nem létező link-cél. Az adat a core graf-meta
// válaszából jön (a felület nem old fel linket és nem talál ki élt); a fájl-csúcsok foka, az árva-fogalom és az alap nézet
// változatlan, a kapcsolók a láthatóságot vezérlik (a fizikai maszkon át), a rejtett virtuális csúcs sem találat, sem színezett.
import { describe, expect, it } from 'vitest';
import {
  CIMKE_ELOTAG,
  FELOLDATLAN_ELOTAG,
  GrafAdat,
  kereses,
  lathatoElDb,
  lathatosag,
  szinCsoportok,
  virtualisUt,
  type FajlTipus,
  type GrafMeta,
  type GrafValasz,
} from '../src/lib/graf/modell';

const VALASZ: GrafValasz = {
  csucsok: ['A.md', 'B.md', 'C.md', 'Magányos.md', 'Csakcímke.md', 'kep.png'],
  elek: [
    ['A.md', 'B.md'],
    ['B.md', 'C.md'],
  ],
  feloldatlan: { 'Még nincs': 2, 'Másik hiány': 1 },
};

const TIPUS: Record<string, FajlTipus> = { 'kep.png': 'kep' };
const tipus = (u: string): FajlTipus | undefined => TIPUS[u] ?? 'md';

const META: GrafMeta = {
  cimkek: { 'A.md': ['Matek', 'Fizika/Optika'], 'B.md': ['matek'], 'Csakcímke.md': ['#Matek'], 'kep.png': [] },
  tulajdonsagok: {},
  cimke_csucsok: {
    matek: { nev: 'Matek', db: 3 },
    'fizika/optika': { nev: 'Fizika/Optika', db: 1 },
  },
  // A és B hivatkozik a „Még nincs”-re, a Magányos.md csak a „Másik hiány”-ra
  feloldatlan_elek: [
    ['A.md', 'Még nincs'],
    ['B.md', 'Még nincs'],
    ['Magányos.md', 'Másik hiány'],
    ['Nem létező forrás.md', 'Szellem'],
  ],
};

const alap = { lekerdezes: '', mellekletek: true, arvak: true };
const g = (meta: GrafMeta | null = META) => new GrafAdat(VALASZ, tipus, meta);
const nevek = (gr: GrafAdat, m: Uint8Array) => gr.nev.filter((_, i) => m[i]);

describe('11-graph-02: feloldatlan link-célok csúcsként', () => {
  it('a core graf-meta adatából virtuális csúcsok lesznek, a fájl-csúcsok után; nem vault-utak', () => {
    const gr = g();
    expect(gr.nValos).toBe(VALASZ.csucsok.length);
    const felold = gr.ut.map((u, i) => [u, i] as const).filter(([, i]) => gr.tipus[i] === 'feloldatlan');
    expect(felold.map(([u]) => u).sort()).toEqual([FELOLDATLAN_ELOTAG + 'Másik hiány', FELOLDATLAN_ELOTAG + 'Még nincs']);
    for (const [u, i] of felold) {
      expect(i).toBeGreaterThanOrEqual(gr.nValos);
      expect(virtualisUt(u)).toBe(true);
      expect(gr.virtualis(i)).toBe(true);
      expect(gr.csucsIndex(u)).toBe(-1); // nem vault-út: megnyitni nem lehet, fájllal nem ütközhet
    }
    expect(VALASZ.csucsok.some(virtualisUt)).toBe(false);
  });

  it('a nem létező forrás éle kimarad (a felület nem talál ki csúcsot), a cél egyszer jön, két forrás két éllel', () => {
    const gr = g();
    expect(gr.ut.some((u) => u.endsWith('Szellem'))).toBe(false);
    const nincs = gr.ut.indexOf(FELOLDATLAN_ELOTAG + 'Még nincs');
    expect([...gr.szomszedok(nincs)].map((j) => gr.ut[j]).sort()).toEqual(['A.md', 'B.md']);
    expect(gr.fok[nincs]).toBe(2);
    expect(gr.irany[[...Array(gr.elek.length / 2).keys()].find((e) => gr.elek[2 * e + 1] === nincs)!]).toBe(1); // forrás → cél
  });

  it('a fájl-csúcsok foka, az irányított élek és a core-éllista változatlan (a virtuális él nem számít bele)', () => {
    const tiszta = g(null);
    const gr = g();
    for (let i = 0; i < gr.nValos; i++) expect(gr.fok[i]).toBe(tiszta.fok[i]);
    expect(gr.iranyitottElek()).toEqual(tiszta.iranyitottElek());
    expect(gr.hianyzoElek).toBe(0);
    expect(gr.iranyitott.length / 2).toBe(VALASZ.elek.length);
  });

  it('alapértelmezés = csak létező fájlok: a nézet és az élek az eddigivel azonosak', () => {
    const tiszta = g(null);
    const gr = g();
    const r = lathatosag(gr, alap); // a `letezoCsak` hiánya = igaz
    expect(r.csucsDb).toBe(gr.nValos);
    expect(nevek(gr, r.lathato)).toEqual(tiszta.nev);
    expect(lathatoElDb(gr, r.lathato)).toBe(lathatoElDb(tiszta, lathatosag(tiszta, alap).lathato));
  });

  it('„Csak létező fájlok” kikapcsolva a feloldatlan célok halvány csúcsként megjelennek, az éleikkel együtt', () => {
    const gr = g();
    const r = lathatosag(gr, { ...alap, letezoCsak: false });
    expect(nevek(gr, r.lathato)).toEqual(expect.arrayContaining(['Még nincs', 'Másik hiány']));
    expect(r.csucsDb).toBe(gr.nValos + 2);
    const tiszta = lathatoElDb(gr, lathatosag(gr, alap).lathato);
    expect(lathatoElDb(gr, r.lathato)).toBe(tiszta + 3); // A→Még nincs, B→Még nincs, Magányos→Másik hiány
  });

  it('a rejtett forrásnál a cél sem marad látható (nincs szellem-csúcs)', () => {
    const gr = g();
    const r = lathatosag(gr, { lekerdezes: 'path:Magányos', mellekletek: true, arvak: true, letezoCsak: false });
    expect(nevek(gr, r.lathato).sort()).toEqual(['Magányos', 'Másik hiány'].sort());
  });

  it('árva-szűrő: a csak feloldatlan linket tartalmazó jegyzet nem árva, amíg a cél látszik', () => {
    const gr = g();
    const van = lathatosag(gr, { ...alap, arvak: false, letezoCsak: false });
    expect(nevek(gr, van.lathato)).toContain('Magányos');
    const nincs = lathatosag(gr, { ...alap, arvak: false, letezoCsak: true });
    expect(nevek(gr, nincs.lathato)).not.toContain('Magányos'); // az eddigi árva-fogalom
    expect(nevek(gr, nincs.lathato)).not.toContain('Másik hiány');
  });

  it('a helyi gráf a feloldatlan célon át is eléri a szomszédot (2 lépés), csak ha a cél látszik', () => {
    const gr = g();
    const kozep = gr.csucsIndex('A.md');
    const lathato = (letezoCsak: boolean) =>
      nevek(gr, lathatosag(gr, { ...alap, letezoCsak }, { kozeppont: kozep, melyseg: 2 }).lathato);
    expect(lathato(false)).toEqual(expect.arrayContaining(['A', 'B', 'C', 'Még nincs']));
    expect(lathato(true)).not.toContain('Még nincs');
  });

  it('a kereses() a rejtett feloldatlan célt nem találja meg, a látszót igen', () => {
    const gr = g();
    const rejtett = lathatosag(gr, alap).lathato;
    expect(kereses(gr, 'még nincs', rejtett)).toEqual([]);
    const lathato = lathatosag(gr, { ...alap, letezoCsak: false }).lathato;
    expect(kereses(gr, 'meg nincs', lathato).map((i) => gr.nev[i])).toEqual(['Még nincs']);
  });

  it('a régi graf-meta (új mezők nélkül) és a meta nélküli adat ugyanúgy működik', () => {
    const regi = g({ cimkek: META.cimkek, tulajdonsagok: {} });
    expect(regi.n).toBe(VALASZ.csucsok.length);
    expect(g(null).n).toBe(VALASZ.csucsok.length);
  });

  it('a core csonkolásának jelzése továbbmegy a nézetnek (nem csendes)', () => {
    expect(g({ ...META, feloldatlan_csonkolt: true }).csonkolt).toBe(true);
    expect(g().csonkolt).toBe(false);
  });
});

describe('11-graph-03: címkék csúcsként', () => {
  it('a címke kis-nagybetűtől függetlenül egy csúcs; a # előtag nem számít; nincs külön csúcs a kimaradó címkének', () => {
    const gr = g();
    const cimkek = gr.ut.map((u, i) => [u, i] as const).filter(([, i]) => gr.tipus[i] === 'cimke');
    expect(cimkek.map(([u]) => u).sort()).toEqual([CIMKE_ELOTAG + 'fizika/optika', CIMKE_ELOTAG + 'matek']);
    const matek = gr.ut.indexOf(CIMKE_ELOTAG + 'matek');
    expect(gr.nev[matek]).toBe('#Matek'); // az első írásmód
    // A (Matek), B (matek) és Csakcímke (#Matek) is odakötődik
    expect([...gr.szomszedok(matek)].map((j) => gr.ut[j]).sort()).toEqual(['A.md', 'B.md', 'Csakcímke.md']);
    expect(gr.fok[matek]).toBe(3);
  });

  it('a címke-él nem irányított (nincs nyíl), és a fájl-csúcsok foka nem változik', () => {
    const gr = g();
    const matek = gr.ut.indexOf(CIMKE_ELOTAG + 'matek');
    const e = [...Array(gr.elek.length / 2).keys()].find((k) => gr.elek[2 * k + 1] === matek)!;
    expect(gr.irany[e]).toBe(0);
    expect(gr.fok[gr.csucsIndex('Csakcímke.md')]).toBe(0); // árva marad a link-fogalom szerint
  });

  it('alapból rejtve; bekapcsolva megjelenik, és a csak címkés jegyzet már nem árva', () => {
    const gr = g();
    expect(nevek(gr, lathatosag(gr, alap).lathato).some((n) => n.startsWith('#'))).toBe(false);
    const be = lathatosag(gr, { ...alap, cimkek: true });
    expect(nevek(gr, be.lathato)).toEqual(expect.arrayContaining(['#Matek', '#Fizika/Optika']));
    const arvaNelkul = lathatosag(gr, { ...alap, cimkek: true, arvak: false });
    expect(nevek(gr, arvaNelkul.lathato)).toContain('Csakcímke');
    expect(nevek(gr, lathatosag(gr, { ...alap, cimkek: false, arvak: false }).lathato)).not.toContain('Csakcímke');
  });

  it('a szöveges szűrő a jegyzeteket szűri; a címke csak akkor marad, ha van látható jegyzete', () => {
    const gr = g();
    const r = lathatosag(gr, { lekerdezes: 'path:C.md', mellekletek: true, arvak: true, cimkek: true });
    expect(nevek(gr, r.lathato)).toEqual(['C']);
    const csak = lathatosag(gr, { lekerdezes: 'path:Csakcímke', mellekletek: true, arvak: true, cimkek: true });
    expect(nevek(gr, csak.lathato).sort()).toEqual(['#Matek', 'Csakcímke'].sort());
  });

  it('a színcsoport és a mellékletszűrő nem érinti a virtuális csúcsot', () => {
    const gr = g();
    const cs = szinCsoportok(gr, [{ lekerdezes: 'matek', szin: '#ff0000' }]);
    for (let i = gr.nValos; i < gr.n; i++) expect(cs.csoport[i]).toBe(-1);
    expect(gr.melleklet(gr.ut.indexOf(CIMKE_ELOTAG + 'matek'))).toBe(false);
    const r = lathatosag(gr, { ...alap, mellekletek: false, cimkek: true, letezoCsak: false });
    expect(nevek(gr, r.lathato)).toEqual(expect.arrayContaining(['#Matek', 'Még nincs']));
    expect(nevek(gr, r.lathato)).not.toContain('kep.png');
  });

  it('a címke-csúcs kereshető (látható esetben), a rejtett nem', () => {
    const gr = g();
    expect(kereses(gr, 'fizika', lathatosag(gr, alap).lathato)).toEqual([]);
    const lathato = lathatosag(gr, { ...alap, cimkek: true }).lathato;
    expect(kereses(gr, 'optika', lathato).map((i) => gr.nev[i])).toEqual(['#Fizika/Optika']);
  });

  it('a szerkezet-aláírás a virtuális csúcsot és élt is tartalmazza (változásra a fizika újraindul)', () => {
    expect(g().alairas).not.toBe(g(null).alairas);
    expect(g().alairas).toBe(g().alairas);
  });
});
