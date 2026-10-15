// A rendszerértesítések (E10): mi megy a macOS Értesítési központjába (szint, kézi/automatikus feladat, előtér/háttér, beállítás),
// a híd üzenetének alakja és korlátai, a kattintás visszahatása, a beállítás tartóssága, a feladat végének jelölése.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { Ertesitesek, ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { MAX_CIM, MAX_SZOVEG, RendszerErtesites, ertesitesUzenet, nativbaMegy } from '../src/lib/ertesites/rendszer';
import type { Feladat } from '../src/lib/vezerlo/tipusok';
import { feladatVege } from '../src/vezerlo/index';

const HATTER = { hejben: true, elotter: false, bekapcsolva: true };

describe('a natívba küldés szabálya', () => {
  it('hiba mindig megy, ha az app háttérben van', () => {
    expect(nativbaMegy({ szint: 'hiba' }, HATTER)).toBe(true);
  });

  it('info, siker, figyelmeztetés csak a `rendszer` jelzéssel megy', () => {
    for (const szint of ['info', 'siker', 'figyelmeztetes']) {
      expect(nativbaMegy({ szint }, HATTER)).toBe(false);
      expect(nativbaMegy({ szint, rendszer: true }, HATTER)).toBe(true);
    }
  });

  it('előtérben soha (a belső buborék marad)', () => {
    const elol = { ...HATTER, elotter: true };
    expect(nativbaMegy({ szint: 'hiba' }, elol)).toBe(false);
    expect(nativbaMegy({ szint: 'siker', rendszer: true }, elol)).toBe(false);
  });

  it('kikapcsolt beállításnál és héj nélkül (böngésző) soha', () => {
    expect(nativbaMegy({ szint: 'hiba' }, { ...HATTER, bekapcsolva: false })).toBe(false);
    expect(nativbaMegy({ szint: 'hiba' }, { ...HATTER, hejben: false })).toBe(false);
  });
});

describe('a híd üzenete', () => {
  it('a cím és a szöveg sortörés nélküli és korlátos', () => {
    const u = ertesitesUzenet({ cim: 'A\nB', szoveg: 'x'.repeat(1000), szint: 'hiba' }, 'e7');
    expect(u).toMatchObject({ tipus: 'ertesites', cim: 'A B', azon: 'e7', kategoria: 'hiba' });
    expect(u.szoveg.length).toBeLessThanOrEqual(MAX_SZOVEG);
    expect(u.szoveg.endsWith('…')).toBe(true);
    expect(ertesitesUzenet({ cim: 'c'.repeat(500), szoveg: '', szint: 'siker' }, 'e1').cim.length).toBeLessThanOrEqual(MAX_CIM);
  });

  it('a kategória a szintből jön', () => {
    expect(ertesitesUzenet({ cim: 'a', szoveg: '', szint: 'siker' }, 'e1').kategoria).toBe('kesz');
    expect(ertesitesUzenet({ cim: 'a', szoveg: '', szint: 'figyelmeztetes' }, 'e1').kategoria).toBe('jelzes');
  });
});

describe('a küldő a héj hídján', () => {
  let uzenetek: unknown[];
  let fokusz: boolean;
  let lathato: string;

  beforeEach(() => {
    uzenetek = [];
    fokusz = false;
    lathato = 'visible';
    (window as unknown as { webkit: unknown }).webkit = { messageHandlers: { manifold: { postMessage: (u: unknown) => uzenetek.push(u) } } };
    vi.spyOn(document, 'hasFocus').mockImplementation(() => fokusz);
    vi.spyOn(document, 'visibilityState', 'get').mockImplementation(() => lathato as DocumentVisibilityState);
  });
  afterEach(() => {
    delete (window as unknown as { webkit?: unknown }).webkit;
  });

  function kotes() {
    const r = new RendszerErtesites();
    const e = new Ertesitesek();
    e.rendszerKuldo = (x) => void r.kuld(x);
    return { r, e };
  }

  it('háttérben a hiba elmegy, előtérben nem; a rejtett lap háttérnek számít', () => {
    const { e } = kotes();
    e.ertesit({ szint: 'hiba', cim: 'Hiba háttérben' });
    expect(uzenetek).toHaveLength(1);
    fokusz = true;
    e.ertesit({ szint: 'hiba', cim: 'Hiba előtérben' });
    expect(uzenetek).toHaveLength(1);
    lathato = 'hidden';
    e.ertesit({ szint: 'hiba', cim: 'Hiba rejtve' });
    expect(uzenetek).toHaveLength(2);
  });

  it('az ismétlődő (összevont) értesítés nem küld újra; a kulcsos frissítés igen', () => {
    const { e } = kotes();
    e.ertesit({ szint: 'hiba', cim: 'X' });
    e.ertesit({ szint: 'hiba', cim: 'X' });
    expect(uzenetek).toHaveLength(1);
    e.ertesit({ szint: 'hiba', cim: 'K', kulcs: 'k' });
    e.ertesit({ szint: 'hiba', cim: 'K2', kulcs: 'k' });
    expect(uzenetek).toHaveLength(3);
  });

  it('a beállítás kikapcsolása után nem küld', () => {
    const { r, e } = kotes();
    r.bekapcsolva = () => false;
    e.ertesit({ szint: 'hiba', cim: 'X' });
    expect(uzenetek).toHaveLength(0);
  });

  it('héj nélkül csendben kimarad', () => {
    delete (window as unknown as { webkit?: unknown }).webkit;
    const { e } = kotes();
    expect(() => e.ertesit({ szint: 'hiba', cim: 'X' })).not.toThrow();
    expect(uzenetek).toHaveLength(0);
  });

  it('a küldő hibája nem akadályozza a belső értesítést', () => {
    const e = new Ertesitesek();
    e.rendszerKuldo = () => {
      throw new Error('híd');
    };
    e.ertesit({ szint: 'hiba', cim: 'X' });
    expect(e.lista).toHaveLength(1);
  });

  it('a kattintás a belső értesítés műveletét futtatja; ismeretlen azonosítónál az alapművelet', () => {
    const { r, e } = kotes();
    const futott = vi.fn();
    const alap = vi.fn();
    r.alapMuvelet = alap;
    e.ertesit({ szint: 'siker', cim: 'Kész', rendszer: true, muvelet: { nev: 'Részletek', futtat: futott } });
    const azon = (uzenetek[0] as { azon: string }).azon;
    r.kattintas(azon);
    expect(futott).toHaveBeenCalledOnce();
    r.kattintas(azon); // egyszer használatos
    expect(alap).toHaveBeenCalledOnce();
    r.kattintas(42);
    expect(alap).toHaveBeenCalledOnce();
  });
});

describe('a feladat vége', () => {
  const feladat = (tobb: Partial<Feladat>): Feladat =>
    ({ id: 'F-1', tipus: 't', cim: 'Kártyák', osszegzes: '', figyelmeztetes: [], lepesek: [], kulturalt_stop: false, allapot: 'kesz', letrehozva: '', indult: null, vegzett: null, szazalek: 100, lepes_i: 0, kilepes: 0, hiba: null, leallitas_kerve: false, forras: '2.0', vault_ir: false, modell: false, ...tobb }) as Feladat;
  const felulet = new Felulet({});

  beforeEach(() => {
    for (const x of [...ertesitesek.lista]) ertesitesek.elvet(x.id);
  });

  it('a kézi feladat vége rendszerértesítést kér, az automatikus nem (siker)', () => {
    feladatVege(feladat({ automatikus: false }), felulet);
    feladatVege(feladat({ automatikus: true, cim: 'Auto' }), felulet);
    const kez = ertesitesek.lista.find((x) => x.cim === 'Kész: Kártyák');
    const auto = ertesitesek.lista.find((x) => x.cim === 'Kész: Auto');
    expect(kez?.rendszer).toBe(true);
    expect(auto?.rendszer).toBe(false);
  });

  it('a hiba mindkét esetben hiba szintű (a szint maga natívba viszi)', () => {
    feladatVege(feladat({ allapot: 'hiba', hiba: 'baj', automatikus: true }), felulet);
    const e = ertesitesek.lista.find((x) => x.cim === 'Hiba: Kártyák');
    expect(e?.szint).toBe('hiba');
    expect(nativbaMegy(e!, HATTER)).toBe(true);
  });

  it('a régi core (nincs `automatikus` mező) kézinek számít', () => {
    feladatVege(feladat({}), felulet);
    expect(ertesitesek.lista.find((x) => x.cim === 'Kész: Kártyák')?.rendszer).toBe(true);
  });
});

describe('a beállítás tartóssága', () => {
  it('alapból be; a mentett kikapcsolás visszajön; a hibás érték az alapra esik', () => {
    expect(new Felulet({}).rendszerErtesites).toBe(true);
    const f = new Felulet({});
    f.rendszerErtesites = false;
    const vissza = new Felulet(JSON.parse(JSON.stringify(f.sorosit())));
    expect(vissza.rendszerErtesites).toBe(false);
    expect(new Felulet({ rendszerErtesites: 'x' }).rendszerErtesites).toBe(true);
  });
});
