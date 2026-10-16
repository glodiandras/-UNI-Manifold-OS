// A vezérlő adatrétege (C17): a feladatsor élő listája a WS-eseményekből, a feladat végének értesítése, a kapcsolók,
// a rendszerállapot időzítése, a megjelenítési segédek, a tartós szakasz-állapot és a telepített parancsok.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { Regiszter } from '../src/lib/parancsok/regiszter';
import { Feladatsor } from '../src/lib/vezerlo/feladatsor.svelte';
import { VezerloKapcsolok } from '../src/lib/vezerlo/kapcsolok.svelte';
import { allapotCimke, feladatHiba, feladatSzoveg, gb, haladasSzoveg, idoRovid, idotartam, mb, utReszei } from '../src/lib/vezerlo/megjelenites';
import { nyelv } from '../src/lib/i18n';
import { FRISSITES_MS, RendszerAllapot } from '../src/lib/vezerlo/rendszer.svelte';
import type { Feladat } from '../src/lib/vezerlo/tipusok';
import { feladatVege, vezerloTelepit } from '../src/vezerlo';
import { HELYORZOK } from '../src/vezerlo/helyorzok';

function feladat(id: string, mezok: Partial<Feladat> = {}): Feladat {
  return {
    id,
    tipus: 'proba',
    cim: `Feladat ${id}`,
    osszegzes: '',
    figyelmeztetes: [],
    lepesek: [{ cim: 'a' }, { cim: 'b' }],
    kulturalt_stop: false,
    allapot: 'sorban',
    letrehozva: '2026-10-02T10:00:00',
    indult: null,
    vegzett: null,
    szazalek: 0,
    lepes_i: 0,
    kilepes: null,
    hiba: null,
    leallitas_kerve: false,
    forras: '2.0',
    vault_ir: true,
    modell: false,
    ...mezok,
  };
}

const valasz = (adat: unknown, kod = 200) =>
  new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });

let kerelmek: { url: string; metodus: string; body?: unknown }[];
let valaszok: Record<string, (init?: RequestInit) => Response>;

beforeEach(() => {
  kerelmek = [];
  valaszok = {};
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://127.0.0.1/');
    kerelmek.push({ url: u.pathname, metodus: init?.method ?? 'GET', body: init?.body ? JSON.parse(String(init.body)) : undefined });
    const f = valaszok[`${init?.method ?? 'GET'} ${u.pathname}`];
    return f ? f(init) : valasz({ hiba: 'nincs' }, 404);
  });
  ertesitesek.lista = [];
  ertesitesek.elozmeny = [];
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  nyelv.beallit('hu');
});

describe('a feladatsor élő listája', () => {
  it('a WS-esemény helyben frissít, az új feladat legelöl áll, a pont a futó feladatot jelzi', () => {
    const k = new CoreKapcsolat('ws://x');
    const s = new Feladatsor();
    s.figyel(k);
    expect(s.aktiv).toBe(false);
    k.szetoszt({ tipus: 'feladat', feladat: feladat('F-1') });
    k.szetoszt({ tipus: 'feladat', feladat: feladat('F-2', { allapot: 'fut', szazalek: 10 }) });
    expect(s.lista.map((f) => f.id)).toEqual(['F-2', 'F-1']);
    expect(s.aktiv).toBe(true);
    expect(s.sorban.map((f) => f.id)).toEqual(['F-1']);
    k.szetoszt({ tipus: 'feladat', feladat: feladat('F-2', { allapot: 'fut', szazalek: 60 }) });
    expect(s.lista).toHaveLength(2);
    expect(s.kap('F-2')!.szazalek).toBe(60);
    k.szetoszt({ tipus: 'feladat', feladat: feladat('F-2', { allapot: 'kesz', szazalek: 100 }) });
    expect(s.aktiv).toBe(false);
    expect(s.legutobbi.map((f) => f.id)).toEqual(['F-2']);
  });

  it('a lista a 40 legutóbbi feladatra korlátozott', () => {
    const s = new Feladatsor();
    for (let i = 0; i < 45; i++) s.upsert(feladat(`F-${i}`));
    expect(s.lista).toHaveLength(40);
    expect(s.lista[0].id).toBe('F-44');
  });

  it('a végállapot egyszer jelez; a törölt, a betöltött előzmény és az ismételt esemény nem', () => {
    const k = new CoreKapcsolat('ws://x');
    const s = new Feladatsor();
    const vege = vi.fn();
    s.figyel(k, vege);
    k.szetoszt({ tipus: 'feladat', feladat: feladat('F-1', { allapot: 'fut' }) });
    expect(vege).not.toHaveBeenCalled();
    k.szetoszt({ tipus: 'feladat', feladat: feladat('F-1', { allapot: 'kesz' }) });
    k.szetoszt({ tipus: 'feladat', feladat: feladat('F-1', { allapot: 'kesz' }) });
    expect(vege).toHaveBeenCalledTimes(1);
    k.szetoszt({ tipus: 'feladat', feladat: feladat('F-2', { allapot: 'sorban' }) });
    k.szetoszt({ tipus: 'feladat', feladat: feladat('F-2', { allapot: 'torolve' }) });
    expect(vege).toHaveBeenCalledTimes(1);
    k.szetoszt({ tipus: 'feladat', feladat: feladat('F-3', { allapot: 'hiba', hiba: 'x' }) });
    expect(vege).toHaveBeenCalledTimes(2);
    k.szetoszt({ tipus: 'feladat' });                      // hibás esemény: nem dob
    k.szetoszt({ tipus: 'feladat', feladat: { cim: 'id nélkül' } });
  });

  it('betöltés a core-ból (és a `hello` újratölt); hiba esetén a hiba látszik', async () => {
    valaszok['GET /api/feladatok'] = () => valasz({ feladatok: [feladat('F-9', { allapot: 'kesz' })] });
    const s = new Feladatsor();
    await s.betolt();
    expect(s.betoltve && s.lista.map((f) => f.id)).toEqual(['F-9']);
    valaszok['GET /api/feladatok'] = () => valasz({ hiba: 'leáll' }, 503);
    await s.betolt();
    expect(s.hiba).toBe('leáll');
  });
});

describe('a feladat végének értesítése', () => {
  it('a feladathiba kódja angolul jelenik meg; a dinamikus cím suffixe érintetlen', () => {
    nyelv.beallit('en');
    const f = feladat('F-en', {
      allapot: 'hiba', cim: 'note|draft', hiba: 'magyar tartalék', kod: 'feladat.idotullepes', param: { mp: 30 },
    });
    expect(feladatHiba(f)).toBe('The task exceeded its maximum run time (30 s) and was stopped.');
    feladatVege(f, new Felulet());
    expect(ertesitesek.elozmeny[0].cim).toBe('Error: note|draft');
    expect(ertesitesek.elozmeny[0].szoveg).toBe('The task exceeded its maximum run time (30 s) and was stopped.');
  });

  it('állapotonként más szint; a „Részletek” a lapot a feladatra nyitja', () => {
    const felulet = new Felulet();
    feladatVege(feladat('F-1', { allapot: 'kesz', cim: 'Mentés' }), felulet);
    feladatVege(feladat('F-2', { allapot: 'hiba', cim: 'Lánc', hiba: 'elromlott' }), felulet);
    feladatVege(feladat('F-3', { allapot: 'megallitva', cim: 'Próba' }), felulet);
    feladatVege(feladat('F-4', { allapot: 'megszakadt', cim: 'Régi', hiba: 'a core leállt' }), felulet);
    const e = ertesitesek.elozmeny;
    expect(e.map((x) => [x.szint, x.cim])).toEqual([
      ['figyelmeztetes', 'Megszakadt: Régi'],
      ['info', 'Megállítva: Próba'],
      ['hiba', 'Hiba: Lánc'],
      ['siker', 'Kész: Mentés'],
    ]);
    expect(e[2].szoveg).toBe('elromlott');
    const reszletek = e[3].muvelet!;
    expect(reszletek.nev).toBe('Részletek');
    reszletek.futtat();
    expect(felulet.manifoldLap).toBe(true);
    expect(felulet.manifoldFeladat).toBe('F-1');
  });
});

describe('a kapcsolók', () => {
  it('alapból mindkettő be; a váltás azonnali és a core válaszára igazodik', async () => {
    const k = new VezerloKapcsolok();
    expect(k.ertek).toEqual({ asszisztens: true, tracker: true });
    valaszok['PUT /api/vezerlo/kapcsolok'] = (init) => {
      const b = JSON.parse(String(init!.body));
      return valasz({ ok: true, kapcsolok: { asszisztens: b.asszisztens ?? true, tracker: true } });
    };
    const p = k.allit('asszisztens', false);
    expect(k.ertek.asszisztens).toBe(false);          // még a válasz előtt
    await p;
    expect(k.ertek).toEqual({ asszisztens: false, tracker: true });
    expect(kerelmek.at(-1)!.body).toEqual({ asszisztens: false });
  });

  it('hiba esetén visszaáll, és a hiba megjelenik', async () => {
    const k = new VezerloKapcsolok();
    valaszok['PUT /api/vezerlo/kapcsolok'] = () => valasz({ hiba: 'nem írható' }, 400);
    await k.allit('tracker', false);
    expect(k.ertek.tracker).toBe(true);
    expect(k.hiba).toBe('nem írható');
  });

  it('a WS `kapcsolok` esemény átírja; hibás alakot figyelmen kívül hagy', async () => {
    valaszok['GET /api/vezerlo/kapcsolok'] = () => valasz({ kapcsolok: { asszisztens: true, tracker: true } });
    const ws = new CoreKapcsolat('ws://x');
    const k = new VezerloKapcsolok();
    k.figyel(ws);
    ws.szetoszt({ tipus: 'kapcsolok', kapcsolok: { asszisztens: false, tracker: true } });
    expect(k.ertek).toEqual({ asszisztens: false, tracker: true });
    ws.szetoszt({ tipus: 'kapcsolok', kapcsolok: { asszisztens: 'x' } });
    ws.szetoszt({ tipus: 'kapcsolok' });
    expect(k.ertek).toEqual({ asszisztens: false, tracker: true });
  });
});

describe('a kapcsolók újracsatlakozáskor', () => {
  it('a WS `hello`-n újratöltődnek (a core közben váltott állapota); a leiratkozás után nem', async () => {
    let allapot = { asszisztens: true, tracker: true };
    valaszok['GET /api/vezerlo/kapcsolok'] = () => valasz({ kapcsolok: allapot });
    const ws = new CoreKapcsolat('ws://x');
    const k = new VezerloKapcsolok();
    const le = k.figyel(ws);
    await vi.waitFor(() => expect(kerelmek.filter((x) => x.url === '/api/vezerlo/kapcsolok')).toHaveLength(1));
    allapot = { asszisztens: false, tracker: false };
    ws.szetoszt({ tipus: 'hello' });
    await vi.waitFor(() => expect(k.ertek).toEqual({ asszisztens: false, tracker: false }));
    le();
    ws.szetoszt({ tipus: 'hello' });
    await new Promise((r) => setTimeout(r, 0));
    expect(kerelmek.filter((x) => x.url === '/api/vezerlo/kapcsolok')).toHaveLength(2);
  });
});

describe('a rendszerállapot időzítése', () => {
  it('azonnal kér, utána csak látszó ablakban; a leiratkozás megállítja', async () => {
    vi.useFakeTimers();
    valaszok['GET /api/vezerlo/rendszer'] = () => valasz({ memoria: { szabad_szazalek: 40 } });
    const r = new RendszerAllapot();
    const le = r.indit();
    await vi.advanceTimersByTimeAsync(0);
    expect(kerelmek).toHaveLength(1);
    expect((r.adat as unknown as { memoria: { szabad_szazalek: number } }).memoria.szabad_szazalek).toBe(40);
    await vi.advanceTimersByTimeAsync(FRISSITES_MS);
    expect(kerelmek).toHaveLength(2);
    const vis = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
    await vi.advanceTimersByTimeAsync(FRISSITES_MS * 3);
    expect(kerelmek).toHaveLength(2);                  // rejtett ablakban nem kérdez
    vis.mockReturnValue('visible');
    await vi.advanceTimersByTimeAsync(FRISSITES_MS);
    expect(kerelmek).toHaveLength(3);
    le();
    await vi.advanceTimersByTimeAsync(FRISSITES_MS * 3);
    expect(kerelmek).toHaveLength(3);                  // leiratkozás után semmi
  });

  it('hiba esetén a hiba látszik, a régi adat megmarad', async () => {
    valaszok['GET /api/vezerlo/rendszer'] = () => valasz({ memoria: {} });
    const r = new RendszerAllapot();
    await r.frissit();
    valaszok['GET /api/vezerlo/rendszer'] = () => valasz({ hiba: 'nincs core' }, 500);
    await r.frissit();
    expect(r.hiba).toBe('nincs core');
    expect(r.adat).not.toBeNull();
  });
});

describe('megjelenítési segédek', () => {
  it('a core állandó feladatszövege fordítódik, az ismeretlen dinamikus szöveg érintetlen', () => {
    nyelv.beallit('en');
    expect(feladatSzoveg('Füzetfotók bekötése')).toBe('Link notebook photos');
    expect(feladatSzoveg('Videók letöltése')).toBe('Download videos');
    expect(feladatSzoveg('note|draft')).toBe('note|draft');
  });

  it('feliratok, haladás, idő, méret, út', () => {
    expect(allapotCimke('megszakadt')).toBe('Megszakadt');
    expect(haladasSzoveg(feladat('a', { allapot: 'fut', szazalek: 40.4, lepes_i: 1 }))).toBe('2/2. lépés · 40 %');
    expect(haladasSzoveg(feladat('a', { allapot: 'fut', szazalek: 5, lepesek: [{ cim: 'x' }] }))).toBe('5 %');
    expect(haladasSzoveg(feladat('a'))).toBe('');
    const d = (mp: number) => idotartam(feladat('a', { indult: '2026-10-02T10:00:00', vegzett: new Date(Date.parse('2026-10-02T10:00:00') + mp * 1000).toISOString() }));
    expect([d(3), d(134), d(3900)]).toEqual(['3 mp', '2 p 14 mp', '1 ó 05 p']);
    expect(idotartam(feladat('a'))).toBe('');
    expect(idoRovid(null)).toBe('');
    const most = new Date('2026-10-02T15:00:00');
    expect(idoRovid('2026-10-02T14:03:00', most)).toMatch(/14:03/);
    expect(idoRovid('2026-09-30T14:03:00', most)).toMatch(/14:03/);
    expect(idoRovid('2026-09-30T14:03:00', most).length).toBeGreaterThan(5);
    expect(gb(8.25)).toMatch(/8,3|8,2/);
    expect(mb(512)).toMatch(/512 MB/);
    expect(mb(2048)).toMatch(/2 GB/);
    expect(utReszei('A/B/c.md')).toEqual({ nev: 'c.md', mappa: 'A/B' });
    expect(utReszei('c.md')).toEqual({ nev: 'c.md', mappa: '' });
  });
});

describe('a szakaszok tartós állapota', () => {
  it('körbejár a mentésen; a hibás kulcs és érték kiesik', () => {
    const f = new Felulet();
    f.vezerlo.nyitott.rendszer = true;
    f.vezerlo.nyitott.most = false;
    const mentett = JSON.parse(JSON.stringify(f.sorosit()));
    expect(mentett.vezerlo).toEqual({ nyitott: { rendszer: true, most: false } });
    expect(new Felulet(mentett).vezerlo.nyitott).toEqual({ rendszer: true, most: false });
    const rossz = new Felulet({ vezerlo: { nyitott: { rendszer: 'igen', 'Rossz kulcs!': true, bevitel: true } } });
    expect(rossz.vezerlo.nyitott).toEqual({ bevitel: true });
    expect(new Felulet({}).vezerlo.nyitott).toEqual({});
  });

  it('az átmeneti feladat-kiválasztás nem mentődik', () => {
    const f = new Felulet();
    f.manifoldFeladat = 'F-1';
    expect(JSON.stringify(f.sorosit())).not.toContain('F-1');
  });
});

describe('a telepített parancsok', () => {
  function telep(aktivUt: string | null) {
    const reg = new Regiszter();
    const felulet = new Felulet();
    if (aktivUt) felulet.munkaterulet.megnyit(aktivUt, 'aktiv');
    const le = vezerloTelepit(reg, felulet, new CoreKapcsolat('ws://x'));
    return { reg, felulet, le };
  }

  it('a C17 jegyzet-parancsainak már mind valódi tulajdonosa van: a vezérlő nem telepít helyőrzőt helyettük', () => {
    expect(HELYORZOK).toEqual([]);                       // C23b kártya, C26b összefoglalás, C22b kvíz (a saját moduljukban)
    const { reg, le } = telep('Jegyzet.md');
    for (const id of ['kartya.ebbol', 'kviz.ebbol', 'osszefoglalas.keszit']) expect(reg.kap(id)).toBeUndefined();
    le();
  });

  it('a tulajdonos chat ugyanazon az azonosítón cserélheti a helyőrzőt', () => {
    const { reg, le } = telep('Jegyzet.md');
    le();                                                // a helyőrzők leiratkoznak (a modul telepítése előtt)
    const valodi = vi.fn();
    reg.regisztral({ id: 'kartya.ebbol', nev: 'Kártyák ebből', futtat: valodi });
    reg.futtat('kartya.ebbol');
    expect(valodi).toHaveBeenCalledTimes(1);
  });

  it('a vezérlő parancsai: lap megnyitása, mentés, kapcsolók elérhetősége', async () => {
    const { reg, felulet, le } = telep(null);
    felulet.manifoldFeladat = 'F-1';
    reg.futtat('manifold.most');
    expect(felulet.manifoldLap).toBe(true);
    expect(felulet.manifoldRendszer).toBe(true); // CX-007: a vezérlő szakaszai a Rendszer alatt
    expect(felulet.manifoldFeladat).toBeNull();
    expect(felulet.vezerlo.nyitott.most).toBe(true);
    valaszok['POST /api/feladatok'] = () => valasz(feladat('F-9', { tipus: 'mentes' }), 201);
    reg.futtat('manifold.mentes');
    await vi.waitFor(() => expect(kerelmek.some((k) => k.metodus === 'POST' && (k.body as { tipus: string }).tipus === 'mentes')).toBe(true));
    expect(reg.elerheto(reg.kap('manifold.asszisztens-be')!)).toBe(false);     // alapból be van kapcsolva
    expect(reg.elerheto(reg.kap('manifold.asszisztens-ki')!)).toBe(true);
    le();
  });
});
