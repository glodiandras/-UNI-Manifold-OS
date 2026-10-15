// A tracker felületi gyűjtői (C27): az aktív idő, a vödrös késleltetés, a kötegelt kliens, a parancs-megfigyelő
// (forrással), a karakterszámlálás, a gépelés-mérő bővítmény és a megjelenítési segédek.

import { ChangeSet, EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Regiszter } from '../src/lib/parancsok/regiszter';
import { aktivUtKulcs, GRAF_KULCS } from '../src/lib/tracker/aktivFul';
import { AktivIdo, BEVITEL_ABLAK_MS, UGRAS_PLAFON_MS, type AktivIdoFuggosegek } from '../src/lib/tracker/bevitel';
import { gepelesMero } from '../src/lib/tracker/gepelesMero';
import { valtozasMeret } from '../src/lib/tracker/karakter';
import { Hisztogram, VEDOR_DB, VEDROK_MS, vedorIndex } from '../src/lib/tracker/kesleltetes';
import { TrackerKliens, trackerKliens } from '../src/lib/tracker/kliens.svelte';
import { idoSzoveg, maiNap, msSzoveg, napCimke, napEltol, napSzoveg, szazalekSzoveg } from '../src/lib/tracker/megjelenites';

describe('késleltetés-hisztogram', () => {
  it('vödörhatárok: a határérték az alsó vödörbe esik, a túlcsordulás az utolsóba', () => {
    expect(VEDROK_MS).toEqual([1, 2, 4, 8, 16, 32, 50, 75, 100, 150, 200, 300, 500, 1000, 2000, 5000]); // = core/tracker.py VEDROK_MS
    expect(VEDOR_DB).toBe(17);
    expect(vedorIndex(0.2)).toBe(0);
    expect(vedorIndex(1)).toBe(0);
    expect(vedorIndex(1.01)).toBe(1);
    expect(vedorIndex(5000)).toBe(15);
    expect(vedorIndex(5000.1)).toBe(16);
  });

  it('számol, maximumot tart vödrönként, ürít és visszatesz', () => {
    const h = new Hisztogram();
    expect(h.ures).toBe(true);
    expect(h.kiurit()).toBeNull();
    for (const ms of [3, 3.5, 12, 90, 9000]) h.add(ms);
    h.add(-1);
    h.add(NaN);
    const k = h.kiurit()!;
    expect(k).toEqual({ '2': [2, 3.5], '4': [1, 12], '8': [1, 90], '16': [1, 9000] });
    expect(h.ures).toBe(true);
    h.vissza(k);
    h.add(2.5);
    expect(h.kiurit()).toEqual({ '2': [3, 3.5], '4': [1, 12], '8': [1, 90], '16': [1, 9000] });
  });
});

describe('aktív idő', () => {
  function minta(mezok: Partial<AktivIdoFuggosegek> = {}) {
    const allapot = { most: 0, ut: 'M01/a.md' as string | null, lathato: true, fokusz: true, jatszik: false };
    const jelentesek: [string, number, string][] = [];
    const ido = new AktivIdo({
      most: () => allapot.most,
      aktivUt: () => allapot.ut,
      lathato: () => allapot.lathato,
      fokuszban: () => allapot.fokusz,
      jatszik: () => allapot.jatszik,
      jelent: (ut, mp, nap) => jelentesek.push([ut, mp, nap]),
      nap: () => '2026-10-03',
      ...mezok,
    });
    const utem = (ms = 1000) => {
      allapot.most += ms;
      ido.utem();
    };
    return { allapot, jelentesek, ido, utem };
  }
  const osszeg = (j: [string, number, string][]) => j.reduce((s, x) => s + x[1], 0);

  it('bevitel nélkül nem számol; bevitel után másodpercenként', () => {
    const { ido, utem, jelentesek } = minta();
    utem(); // az első ütem csak az alap
    for (let i = 0; i < 5; i++) utem();
    expect(jelentesek).toEqual([]);
    ido.bevitel();
    for (let i = 0; i < 5; i++) utem();
    expect(osszeg(jelentesek)).toBe(5);
    expect(jelentesek[0]).toEqual(['M01/a.md', 1, '2026-10-03']);
  });

  it('a 60 mp-es bevitel-ablak után megáll', () => {
    const { ido, utem, jelentesek } = minta();
    utem();
    ido.bevitel();
    for (let i = 0; i < BEVITEL_ABLAK_MS / 1000 + 30; i++) utem();
    expect(osszeg(jelentesek)).toBe(BEVITEL_ABLAK_MS / 1000); // legfeljebb 60 mp a bevitel után
  });

  it('nem számol, ha az ablak nem látszik, nincs fókuszban, vagy nincs jegyzet-fül', () => {
    const { allapot, ido, utem, jelentesek } = minta();
    utem();
    ido.bevitel();
    allapot.lathato = false;
    for (let i = 0; i < 4; i++) utem();
    allapot.lathato = true;
    allapot.fokusz = false;
    for (let i = 0; i < 4; i++) utem();
    allapot.fokusz = true;
    allapot.ut = null;
    for (let i = 0; i < 4; i++) utem();
    expect(jelentesek).toEqual([]);
    allapot.ut = 'F01/b.md';
    for (let i = 0; i < 3; i++) utem();
    expect(osszeg(jelentesek)).toBe(3);
  });

  it('a lejátszás bevitelnek számít (38. döntés, T074): a bevitel nélküli videónézés 60 mp után sem szakad meg', () => {
    const { allapot, ido, utem, jelentesek } = minta();
    utem();
    ido.bevitel();
    allapot.jatszik = true;
    for (let i = 0; i < 300; i++) utem(); // 5 perc nézés egyetlen bevitel nélkül
    expect(osszeg(jelentesek)).toBe(300);
    allapot.jatszik = false; // megáll a lejátszás: a legutóbbi „bevitel” (a lejátszás utolsó másodperce) után még 60 mp számít
    for (let i = 0; i < 100; i++) utem();
    expect(osszeg(jelentesek)).toBe(300 + BEVITEL_ABLAK_MS / 1000);
  });

  it('a játszó lejátszó sem számol, ha az ablak nem látszik vagy nincs fókuszban, és fülváltáskor nem vándorol át', () => {
    const { allapot, ido, utem, jelentesek } = minta();
    utem();
    ido.bevitel();
    allapot.jatszik = true;
    allapot.lathato = false;
    for (let i = 0; i < 5; i++) utem();
    allapot.lathato = true;
    allapot.fokusz = false;
    for (let i = 0; i < 5; i++) utem();
    expect(jelentesek).toEqual([]);
    allapot.fokusz = true;
    for (let i = 0; i < 3; i++) utem();
    expect(osszeg(jelentesek)).toBe(3);
  });

  it('az alvó gép ideje nem számít: az ütemenkénti ugrás plafonos', () => {
    const { ido, utem, jelentesek } = minta();
    utem();
    ido.bevitel();
    utem(50_000); // az ütem 50 s-ot késett (alvás): a bevitel-ablakon belül is csak a plafon számít
    expect(osszeg(jelentesek)).toBe(UGRAS_PLAFON_MS / 1000);
  });

  it('fülváltáskor a törtrész nem vándorol át másik jegyzetre', () => {
    const { allapot, ido, utem, jelentesek } = minta();
    utem();
    ido.bevitel();
    utem(600);
    utem(600); // 1,2 s a régi fülön: 1 mp könyvelve, 0,2 s tört
    expect(jelentesek).toEqual([['M01/a.md', 1, '2026-10-03']]);
    allapot.ut = 'F01/b.md';
    utem(600);
    expect(jelentesek).toHaveLength(1);
    utem(600);
    expect(jelentesek[1]).toEqual(['F01/b.md', 1, '2026-10-03']);
  });
});

describe('az aktív idő útja minden fájl-fülön (38. döntés, T074)', () => {
  const ful = (ut: string | null, nezet?: Record<string, unknown>) => ({ id: 'f1', ut, ...(nezet ? { nezet } : {}) });

  it('a jegyzet, PDF, videó, hang, canvas és base útja számít', () => {
    for (const ut of ['M01/a.md', 'Tx/11 - Történelem.pdf', 'ATTCHMNTS/Videos/A Nyugat.mp4', 'Xn/2026-09-22 - Irodalom.m4a', 'M03/térkép.canvas', 'K/Books.base']) {
      expect(aktivUtKulcs(ful(ut)), ut).toBe(ut);
    }
  });

  it('a gráf nézet-fül (nincs útja) saját kulcsot kap; a többi út nélküli fül nem számít', () => {
    expect(aktivUtKulcs(ful(null, { tipus: 'graf' }))).toBe(GRAF_KULCS);
    expect(GRAF_KULCS).toBe('(gráf)');
    for (const tipus of ['ma', 'statisztika', 'hasznalat']) expect(aktivUtKulcs(ful(null, { tipus })), tipus).toBeNull();
    expect(aktivUtKulcs(ful(null))).toBeNull(); // az „Új fül”
    expect(aktivUtKulcs(null)).toBeNull();
  });
});

describe('tracker kliens', () => {
  let k: TrackerKliens;
  let kerelmek: { url: string; body: Record<string, unknown>; keepalive?: boolean }[];
  let siker: boolean;
  let valasz: Record<string, unknown>;
  let valaszKod: number;
  let kapu: Promise<void> | null;

  beforeEach(() => {
    k = new TrackerKliens();
    k.kapcsoloFelulir = true;
    kerelmek = [];
    siker = true;
    valasz = { fogadva: true };
    valaszKod = 200;
    kapu = null;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init: RequestInit) => {
        kerelmek.push({ url, body: JSON.parse(String(init.body)), keepalive: init.keepalive });
        if (kapu) await kapu;
        if (!siker) throw new TypeError('hálózati hiba');
        return new Response(JSON.stringify(valasz), { status: valaszKod, headers: { 'Content-Type': 'application/json' } });
      }),
    );
  });

  it('a core „fogadva: false” válasza látszik (T007): nemFogad a hibával, a következő sikeres köteg törli', async () => {
    expect(k.nemFogad).toBeNull();
    valasz = { fogadva: false, hiba: 'a tracker adatbázisa nem írható' };
    k.aktivMp('M01/a.md', 5, '2026-10-03');
    await k.kuld();
    expect(k.nemFogad).toBe('a tracker adatbázisa nem írható');
    valasz = { fogadva: true };
    k.aktivMp('M01/a.md', 5, '2026-10-03');
    await k.kuld();
    expect(k.nemFogad).toBeNull();
  });

  it('a hiba nélküli „fogadva: false” (a core szerint a Tracker ki van kapcsolva) is jelzés', async () => {
    valasz = { fogadva: false };
    k.aktivMp('M01/a.md', 5, '2026-10-03');
    await k.kuld();
    expect(k.nemFogad).toMatch(/ki van kapcsolva/);
  });

  it('hálózati hibánál nincs hamis jelzés: a köteg visszakerül a pufferbe, a korábbi állapot marad', async () => {
    valasz = { fogadva: false, hiba: 'x' };
    k.aktivMp('M01/a.md', 5, '2026-10-03');
    await k.kuld();
    siker = false;
    k.aktivMp('M01/a.md', 5, '2026-10-03');
    await k.kuld();
    expect(k.nemFogad).toBe('x');
    expect(k.uresPuffer).toBe(false);
  });
  afterEach(() => vi.unstubAllGlobals());

  it('összevon és egy kötegben küld, a puffer kiürül', async () => {
    k.aktivMp('M01/a.md', 5, '2026-10-03');
    k.aktivMp('M01/a.md', 7, '2026-10-03');
    k.aktivMp('F01/b.md', 2, '2026-10-03');
    k.szerkesztes('M01/a.md', 10, 2, '2026-10-03');
    k.szerkesztes('M01/a.md', 5, 0, '2026-10-03');
    k.parancs('manifold.most', 'paletta');
    k.parancs('manifold.most', 'paletta');
    k.parancs('manifold.most', 'billentyu');
    k.gepelesMs(5);
    k.mentesMs(70);
    k.esemeny('kviz_eredmeny', 'M01/a.md', { jo: 3 });
    expect(k.uresPuffer).toBe(false);
    await k.kuld();
    expect(kerelmek).toHaveLength(1);
    expect(kerelmek[0].url).toBe('/api/tracker/esemenyek');
    const b = kerelmek[0].body as Record<string, any>;
    expect(b.aktiv).toEqual([
      { nap: '2026-10-03', ut: 'M01/a.md', mp: 12 },
      { nap: '2026-10-03', ut: 'F01/b.md', mp: 2 },
    ]);
    expect(b.karakter).toEqual([{ nap: '2026-10-03', ut: 'M01/a.md', beszurt: 15, torolt: 2 }]);
    expect(b.parancsok).toEqual([
      { id: 'manifold.most', forras: 'paletta', db: 2 },
      { id: 'manifold.most', forras: 'billentyu', db: 1 },
    ]);
    expect(b.kesleltetes).toEqual({ gepeles: { '3': [1, 5] }, mentes: { '7': [1, 70] } });
    expect(b.esemenyek[0]).toMatchObject({ tipus: 'kviz_eredmeny', ut: 'M01/a.md', adat: { jo: 3 } });
    expect(k.uresPuffer).toBe(true);
    await k.kuld();
    expect(kerelmek).toHaveLength(1); // üres puffer: nincs kérés
  });

  it('kuldKi (T114, kilépés): megvárja az úton lévő köteget, utána elküldi a puffert is', async () => {
    let enged!: () => void;
    kapu = new Promise<void>((r) => (enged = r));
    k.aktivMp('M01/a.md', 5, '2026-10-03');
    const uton = k.kuld(); // a 30 s-os ütem küldése még válaszra vár
    k.aktivMp('M01/a.md', 7, '2026-10-03'); // közben újabb adat gyűlt
    const ki = k.kuldKi();
    await Promise.resolve();
    expect(kerelmek).toHaveLength(1);
    kapu = null;
    enged();
    await Promise.all([uton, ki]);
    expect(kerelmek).toHaveLength(2);
    expect(kerelmek[1].body.aktiv).toEqual([{ nap: '2026-10-03', ut: 'M01/a.md', mp: 7 }]);
    expect(k.uresPuffer).toBe(true);
  });

  it('kuldKi soha nem dob, és nem hagyja el a puffert hiba esetén sem (a hívó időkorlátja dönt)', async () => {
    siker = false;
    k.aktivMp('M01/a.md', 5, '2026-10-03');
    await expect(k.kuldKi()).resolves.toBeUndefined();
    expect(k.uresPuffer).toBe(false); // a köteg visszakerült: nincs elvesztve, ha a core közben visszajön
  });

  it('kikapcsolt kapcsolónál nem gyűjt és nem küld', async () => {
    k.kapcsoloFelulir = false;
    k.aktivMp('M01/a.md', 5);
    k.parancs('a.b', 'gomb');
    k.gepelesMs(3);
    expect(k.uresPuffer).toBe(true);
    await k.kuld();
    expect(kerelmek).toEqual([]);
  });

  it('a kapcsoló kikapcsolása a már összegyűlt puffert is eldobja', async () => {
    k.aktivMp('M01/a.md', 5);
    k.kapcsoloFelulir = false;
    await k.kuld();
    expect(kerelmek).toEqual([]);
    k.kapcsoloFelulir = true;
    expect(k.uresPuffer).toBe(true);
  });

  it('hálózati hibánál a köteg visszakerül és a következő küldéssel megy', async () => {
    k.aktivMp('M01/a.md', 5, '2026-10-03');
    k.parancs('a.b', 'gomb');
    k.mentesMs(40);
    siker = false;
    await k.kuld(); // nem dob
    expect(k.uresPuffer).toBe(false);
    k.aktivMp('M01/a.md', 3, '2026-10-03');
    siker = true;
    await k.kuld();
    const b = kerelmek.at(-1)!.body as Record<string, any>;
    expect(b.aktiv).toEqual([{ nap: '2026-10-03', ut: 'M01/a.md', mp: 8 }]);
    expect(b.parancsok).toEqual([{ id: 'a.b', forras: 'gomb', db: 1 }]);
    expect(b.kesleltetes.mentes).toEqual({ '6': [1, 40] });
  });

  it('a 4xx válasz tartós hiba (T029): a köteg eldobódik és naplózódik, nem küldi újra örökké; a következő köteg csak az újat viszi', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    for (const kod of [400, 403, 404, 413]) {
      warn.mockClear();
      valaszKod = kod;
      valasz = { hiba: 'a köteg elutasítva' };
      k.aktivMp('M01/a.md', 5, '2026-10-03');
      k.parancs('a.b', 'gomb');
      await k.kuld();
      expect(k.uresPuffer, `${kod}: a köteg nem kerülhet vissza`).toBe(true);
      expect(warn, `${kod}: naplózni kell`).toHaveBeenCalledTimes(1);
      expect(String(warn.mock.calls[0][0])).toContain(String(kod));
      expect(k.nemFogad).toBeNull(); // az új adat tovább gyűlik: nincs „nem tud írni” szalag
      valaszKod = 200;
      valasz = { fogadva: true };
      k.aktivMp('F01/b.md', 3, '2026-10-03');
      await k.kuld();
      const b = kerelmek.at(-1)!.body as Record<string, any>;
      expect(b.aktiv, `${kod}: csak az új adat`).toEqual([{ nap: '2026-10-03', ut: 'F01/b.md', mp: 3 }]);
      expect(b.parancsok).toEqual([]);
    }
    warn.mockRestore();
  });

  it('az 5xx válasz átmeneti: a köteg visszakerül és a következő küldéssel megy', async () => {
    valaszKod = 503;
    valasz = { hiba: 'nem elérhető' };
    k.aktivMp('M01/a.md', 5, '2026-10-03');
    await k.kuld();
    expect(k.uresPuffer).toBe(false);
    valaszKod = 200;
    valasz = { fogadva: true };
    k.aktivMp('M01/a.md', 3, '2026-10-03');
    await k.kuld();
    expect((kerelmek.at(-1)!.body as Record<string, any>).aktiv).toEqual([{ nap: '2026-10-03', ut: 'M01/a.md', mp: 8 }]);
    expect(k.uresPuffer).toBe(true);
  });

  it('a részben elfogadott köteg (elvetve) sikeres: nem megy vissza, a kimaradás naplózódik', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    valasz = { fogadva: true, elvetve: 2, okok: ['parancsok.id: érvénytelen parancsazonosító'] };
    k.aktivMp('M01/a.md', 5, '2026-10-03');
    await k.kuld();
    expect(k.uresPuffer).toBe(true);
    expect(k.nemFogad).toBeNull();
    expect(warn).toHaveBeenCalledTimes(1);
    expect(String(warn.mock.calls[0][0])).toContain('2');
    warn.mockRestore();
  });

  describe('törlés előtti puffer (T110)', () => {
    const tolt = () => {
      k.aktivMp('M01/titkos.md', 5, '2026-10-03');
      k.szerkesztes('M01/titkos.md', 10, 2, '2026-10-03');
      k.esemeny('kviz_eredmeny', 'M01/titkos.md', { jo: 3 });
      k.parancs('a.b', 'gomb');
      k.gepelesMs(5);
      k.mentesMs(70);
    };

    it('a „tevekenyseg” törlése az aktív idő, karakter és események pufferét dobja el, a használatét nem', async () => {
      tolt();
      await k.torlesElott('tevekenyseg');
      k.torlesUtan();
      await k.kuld();
      const b = kerelmek[0].body as Record<string, any>;
      expect(b.aktiv).toEqual([]);
      expect(b.karakter).toEqual([]);
      expect(b.esemenyek).toEqual([]);
      expect(b.parancsok).toEqual([{ id: 'a.b', forras: 'gomb', db: 1 }]);
      expect(b.kesleltetes).toEqual({ gepeles: { '3': [1, 5] }, mentes: { '7': [1, 70] } });
    });

    it('a „hasznalat” törlése a parancs- és késleltetés-puffert dobja el, a tevékenységét nem', async () => {
      tolt();
      await k.torlesElott('hasznalat');
      k.torlesUtan();
      await k.kuld();
      const b = kerelmek[0].body as Record<string, any>;
      expect(b.aktiv).toEqual([{ nap: '2026-10-03', ut: 'M01/titkos.md', mp: 5 }]);
      expect(b.karakter).toHaveLength(1);
      expect(b.esemenyek).toHaveLength(1);
      expect(b.parancsok).toEqual([]);
      expect(b.kesleltetes).toEqual({});
    });

    it('a „minden” mindent eldob; a törlés alatt a küldés áll, utána újra megy', async () => {
      tolt();
      await k.torlesElott('minden');
      expect(k.uresPuffer).toBe(true);
      k.aktivMp('F01/b.md', 3, '2026-10-03'); // a törlés közben keletkezett adat nem vész el, de nem is megy el
      await k.kuld();
      expect(kerelmek).toEqual([]);
      expect(k.uresPuffer).toBe(false);
      k.torlesUtan();
      await k.kuld();
      expect((kerelmek[0].body as Record<string, any>).aktiv).toEqual([{ nap: '2026-10-03', ut: 'F01/b.md', mp: 3 }]);
    });

    it('a folyamatban lévő köteget megvárja: a törlés kérése csak a küldés befejezése után mehet', async () => {
      let nyit!: () => void;
      kapu = new Promise<void>((r) => (nyit = r));
      k.aktivMp('M01/titkos.md', 5, '2026-10-03');
      const kuldes = k.kuld(); // a kérés elindult, a válasz még nincs
      expect(kerelmek).toHaveLength(1);
      let kesz = false;
      const elott = k.torlesElott('minden').then(() => (kesz = true));
      await Promise.resolve();
      await Promise.resolve();
      expect(kesz).toBe(false);
      nyit();
      await kuldes;
      await elott;
      expect(kesz).toBe(true);
      k.torlesUtan();
    });

    it('a sikertelen küldés visszatett kötege sem éli túl a törlést', async () => {
      let nyit!: () => void;
      kapu = new Promise<void>((r) => (nyit = r));
      siker = false;
      k.aktivMp('M01/titkos.md', 5, '2026-10-03');
      const kuldes = k.kuld();
      const elott = k.torlesElott('minden');
      nyit();
      await kuldes;
      await elott;
      expect(k.uresPuffer).toBe(true);
      k.torlesUtan();
    });

    it('a felfüggesztések számlálnak: két egymást átfedő törlés után is csak az utolsó engedi vissza a küldést', async () => {
      await k.torlesElott('minden');
      await k.torlesElott('minden');
      k.torlesUtan();
      k.aktivMp('F01/b.md', 3, '2026-10-03');
      await k.kuld();
      expect(kerelmek).toEqual([]);
      k.torlesUtan();
      await k.kuld();
      expect(kerelmek).toHaveLength(1);
    });
  });

  it('elrejtéskor és elhagyáskor azonnal, keepalive-val küld', async () => {
    const le = k.indit();
    k.parancs('a.b', 'gomb');
    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });
    document.dispatchEvent(new Event('visibilitychange'));
    await vi.waitFor(() => expect(kerelmek).toHaveLength(1));
    expect(kerelmek[0].keepalive).toBe(true);
    k.parancs('a.c', 'gomb');
    window.dispatchEvent(new Event('pagehide'));
    await vi.waitFor(() => expect(kerelmek).toHaveLength(2));
    Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true });
    le();
  });
});

describe('parancs-megfigyelő', () => {
  it('az azonosítót és a forrást kapja, csak sikeres futásnál; a hibája nem akasztja a parancsot', () => {
    const reg = new Regiszter();
    const futott = vi.fn();
    reg.regisztral({ id: 'proba.egy', nev: 'Egy', futtat: futott });
    reg.regisztral({ id: 'proba.nem', nev: 'Nem', elerheto: () => false, futtat: vi.fn() });
    const lat: [string, string][] = [];
    const le = reg.megfigyel((id, f) => lat.push([id, f]));
    reg.megfigyel(() => {
      throw new Error('rossz megfigyelő');
    });
    const hiba = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(reg.futtat('proba.egy')).toBe(true);
    expect(reg.futtat('proba.egy', 'billentyu')).toBe(true);
    expect(reg.futtat('proba.nem', 'paletta')).toBe(false);
    expect(reg.futtat('nincs.ilyen', 'gomb')).toBe(false);
    expect(futott).toHaveBeenCalledTimes(2);
    expect(lat).toEqual([['proba.egy', 'egyeb'], ['proba.egy', 'billentyu']]);
    le();
    reg.futtat('proba.egy', 'menu');
    expect(lat).toHaveLength(2);
    hiba.mockRestore();
  });
});

describe('szerkesztett karakter és gépelés-mérő', () => {
  it('a változáshalmaz beszúrt és törölt karakterei', () => {
    const doc = 'Hello világ';
    const cs = ChangeSet.of([{ from: 0, to: 5, insert: 'Szia' }, { from: 11, insert: '!!!' }], doc.length);
    expect(valtozasMeret(cs)).toEqual({ beszurt: 7, torolt: 5 });
    expect(valtozasMeret(ChangeSet.empty(5))).toEqual({ beszurt: 0, torolt: 0 });
  });

  it('a leütés → frissítés késleltetése a kliens hisztogramjába kerül; leütés nélküli változás nem', () => {
    const mintak: number[] = [];
    const eredeti = trackerKliens.gepelesMs.bind(trackerKliens);
    trackerKliens.gepelesMs = (ms: number) => mintak.push(ms);
    const szulo = document.createElement('div');
    document.body.append(szulo);
    const view = new EditorView({ state: EditorState.create({ doc: '', extensions: [gepelesMero()] }), parent: szulo });
    // a jsdom `timeStamp`-je nem a `performance.now()` időskáláján van: a böngészőt utánozzuk
    const leutes = (init: KeyboardEventInit) => {
      const e = new KeyboardEvent('keydown', { bubbles: true, ...init });
      Object.defineProperty(e, 'timeStamp', { value: performance.now() });
      view.contentDOM.dispatchEvent(e);
    };
    try {
      view.dispatch({ changes: { from: 0, insert: 'x' } }); // nincs leütés
      expect(mintak).toEqual([]);
      leutes({ key: 'a' });
      view.dispatch({ changes: { from: 1, insert: 'a' } });
      expect(mintak).toHaveLength(1);
      expect(mintak[0]).toBeGreaterThanOrEqual(0);
      view.dispatch({ changes: { from: 2, insert: 'b' } }); // egy leütés egy mintát ad
      expect(mintak).toHaveLength(1);
      leutes({ key: 'c', metaKey: true }); // parancs, nem gépelés
      view.dispatch({ changes: { from: 3, insert: 'c' } });
      expect(mintak).toHaveLength(1);
    } finally {
      trackerKliens.gepelesMs = eredeti;
      view.destroy();
      szulo.remove();
    }
  });
});

describe('megjelenítési segédek', () => {
  it('idő, ms, százalék', () => {
    expect(idoSzoveg(0)).toBe('0 p');
    expect(idoSzoveg(42)).toBe('42 mp');
    expect(idoSzoveg(60 * 45)).toBe('45 p');
    expect(idoSzoveg(3600 * 2 + 300)).toBe('2 ó 05 p');
    expect(msSzoveg(null)).toBe('–');
    expect(msSzoveg(16)).toBe('16 ms');
    expect(msSzoveg(2500)).toMatch(/^2,5 s$/);
    expect(szazalekSzoveg(0.756)).toBe('76 %');
    expect(szazalekSzoveg(null)).toBe('–');
  });

  it('napok: eltolás, címke, szöveg', () => {
    expect(napEltol('2026-10-03', -7)).toBe('2026-09-26');
    expect(napEltol('2026-03-01', -1)).toBe('2026-02-28');
    expect(maiNap(new Date(2026, 9, 3, 23, 59))).toBe('2026-10-03');
    expect(napCimke('2026-10-03', 'nap')).toBe('Szo');
    expect(napCimke('2026-09-28', 'het')).toBe('28.');
    expect(napSzoveg('2026-10-03')).toBe('okt. 3. (Szo)');
    expect(napSzoveg('2026-09-28', 'het')).toBe('szept. 28.-tól');
  });
});
