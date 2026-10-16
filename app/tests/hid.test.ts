// A héj ↔ felület híd (`window.manifold`) szerződése (C29.7b, 2. audit T033, T121, T114): a héj ezekre a függvényekre épít,
// és ha a `mentes` hiányzik vagy hibás, a mentetlen szöveg mentés nélkül vész el — ezért a híd pontos felülete, a `mentes()`
// jelentésének alakja és a lépések sorrendje (leáll → mentés → tracker-ürítés) gépi teszt alatt áll.

import { ChangeSet } from '@codemirror/state';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiHiba } from '../src/lib/core/api';
import { hidTelepit, type HidFuggosegek } from '../src/lib/core/hid';
import { leall } from '../src/lib/core/leall.svelte';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { rendszerErtesites } from '../src/lib/ertesites/rendszer';
import { kilepesMentes, mentetlenSzovegek } from '../src/szerkeszto';
import type { FajlIras, FajlIrasKeres, FajlOlvasas, VaultApi } from '../src/szerkeszto/dokumentum/api';
import { Dokumentumok } from '../src/szerkeszto/dokumentum/dokumentum.svelte';

class AlCore implements VaultApi {
  lemez = '# A\n';
  hiba: ApiHiba | null = null;
  async olvas(ut: string): Promise<FajlOlvasas> {
    return { ut, tartalom: this.lemez, hash: 'h:' + this.lemez, jel: '', mtime: 0 };
  }
  async ir(k: FajlIrasKeres): Promise<FajlIras> {
    if (this.hiba) throw this.hiba;
    this.lemez = k.tartalom;
    return { ok: true, ut: k.ut, hash: 'h:' + k.tartalom, jel: '', uzenet: 'mentve', pillanat: null, elotte: null, git: true };
  }
}

type Ablak = { manifold?: Record<string, (...a: unknown[]) => unknown> };
const hid = () => (window as unknown as Ablak).manifold!;

function fuggosegek(tobb: Partial<HidFuggosegek> = {}): HidFuggosegek & { sorrend: string[] } {
  const sorrend: string[] = [];
  return {
    sorrend,
    parancsFuttat: vi.fn(),
    fokuszVisszaallit: vi.fn(),
    naptarFogad: vi.fn(),
    mentesElokeszit: () => void sorrend.push('elokeszit'),
    mentesKi: async () => void sorrend.push('felulet-allapot'),
    kilepesMentes: async () => {
      sorrend.push(`dokumentumok(leall=${leall.aktiv})`);
      return { ok: true, mentetlen: [] };
    },
    trackerKi: async () => void sorrend.push('tracker'),
    mentetlenSzovegek: () => [],
    ...tobb,
  };
}

let le: (() => void) | null = null;
beforeEach(() => {
  vi.useFakeTimers();
  leall.ki();
  for (const e of [...ertesitesek.lista]) ertesitesek.elvet(e.id);
});
afterEach(() => {
  le?.();
  le = null;
  leall.ki();
  vi.useRealTimers();
});

describe('a híd felülete (a héj ezekre épít)', () => {
  it('az `ertesitesKattintas` a rendszerértesítés kattintás-kezelőjét hívja (E10)', () => {
    le = hidTelepit(fuggosegek());
    const alap = vi.fn();
    const regi = rendszerErtesites.alapMuvelet;
    rendszerErtesites.alapMuvelet = alap;
    try {
      hid().ertesitesKattintas('ismeretlen');
      expect(alap).toHaveBeenCalledOnce();
    } finally {
      rendszerErtesites.alapMuvelet = regi;
    }
  });


  it('pontosan a héj által hívott függvények vannak meg, a leszedő eltünteti', () => {
    le = hidTelepit(fuggosegek());
    // `mappaValasztas` (F8) az egyetlen kulcs, amelyet a FELÜLET hív a héjnak (nem a héj a felületnek): a natív mappaválasztó
    // útvonal-szöveget ad vissza (tartalmat soha), felhasználói aktiváció nélkül nem nyílik — a fix lista ezért bővült, nem lazult.
    expect(Object.keys(hid()).sort()).toEqual(['ertesitesKattintas', 'fokusz', 'hejUzenet', 'leallAllapot', 'mappaValasztas', 'mentes', 'mentetlen', 'naptarEngedely', 'parancs']);
    for (const k of Object.keys(hid())) expect(typeof hid()[k]).toBe('function');
    le();
    le = null;
    expect((window as unknown as Ablak).manifold).toBeUndefined();
  });

  it('a parancs, a fókusz és a naptár-válasz a megfelelő függőségre megy', () => {
    const f = fuggosegek();
    le = hidTelepit(f);
    hid().parancs('hej.paletta');
    hid().fokusz();
    hid().naptarEngedely({ esemeny: 'engedelyezve' });
    expect(f.parancsFuttat).toHaveBeenCalledWith('hej.paletta');
    expect(f.fokuszVisszaallit).toHaveBeenCalledOnce();
    expect(f.naptarFogad).toHaveBeenCalledWith({ esemeny: 'engedelyezve' });
  });

  it('hejUzenet: a héj értesítése a felületen jelenik meg', () => {
    le = hidTelepit(fuggosegek());
    hid().hejUzenet({ szint: 'figyelmeztetes', cim: 'A felület újratöltődött', szoveg: 'a mentetlen szöveg elveszhetett' });
    const e = ertesitesek.lista.find((x) => x.cim === 'A felület újratöltődött');
    expect(e?.szint).toBe('figyelmeztetes');
    expect(e?.szoveg).toContain('mentetlen');
    hid().hejUzenet({ nem: 'jó alak' }); // a hibás üzenet nem dob
    hid().hejUzenet(null);
  });
});

describe('mappaValasztas(): a natív mappaválasztó (F8, import)', () => {
  const webkit = (postMessage: (u: unknown) => unknown) => vi.stubGlobal('webkit', { messageHandlers: { mappaValaszto: { postMessage } } });
  const aktivacio = (isActive: boolean) => Object.defineProperty(navigator, 'userActivation', { value: { isActive }, configurable: true });
  afterEach(() => {
    vi.unstubAllGlobals();
    delete (navigator as unknown as { userActivation?: unknown }).userActivation;
  });

  it('a választott abszolút útvonalat adja vissza, a kérés fix alakú, a cím vágott', async () => {
    const kuld = vi.fn(async () => '/synthetic/Vault');
    webkit(kuld);
    le = hidTelepit(fuggosegek());
    expect(await hid().mappaValasztas('Choose the Obsidian vault folder')).toBe('/synthetic/Vault');
    expect(kuld).toHaveBeenCalledWith({ tipus: 'mappa-valaszto', cim: 'Choose the Obsidian vault folder' });
    await hid().mappaValasztas('x'.repeat(500));
    expect((kuld.mock.calls[1] as unknown as [{ cim: string }])[0].cim).toHaveLength(200);
    await hid().mappaValasztas();
    expect(kuld.mock.calls[2]).toEqual([{ tipus: 'mappa-valaszto' }]);
    await hid().mappaValasztas({ tipus: 'masik' } as unknown as string);   // nem szöveg: nincs cím a kérésben
    expect(kuld.mock.calls[3]).toEqual([{ tipus: 'mappa-valaszto' }]);
  });

  it('megszakításra (null), hibára, híd nélkül és érvénytelen válaszra null — soha nem dob', async () => {
    le = hidTelepit(fuggosegek());
    expect(await hid().mappaValasztas()).toBeNull();                       // böngésző: nincs csatorna
    for (const v of [null, undefined, '', 'relativ/ut', '~/Vault', 5, {}, '/a\0b', '/' + 'x'.repeat(5000)]) {
      webkit(async () => v);
      expect(await hid().mappaValasztas()).toBeNull();
    }
    webkit(async () => { throw new Error('héj hiba'); });
    expect(await hid().mappaValasztas()).toBeNull();
  });

  it('felhasználói aktiváció nélkül a kérés el sem megy', async () => {
    const kuld = vi.fn(async () => '/synthetic/Vault');
    webkit(kuld);
    le = hidTelepit(fuggosegek());
    aktivacio(false);
    expect(await hid().mappaValasztas()).toBeNull();
    expect(kuld).not.toHaveBeenCalled();
    aktivacio(true);
    expect(await hid().mappaValasztas()).toBe('/synthetic/Vault');
  });

  it('egyszerre egy panel: a második hívás azonnal null, a befejezés után újra nyílik', async () => {
    let kesz!: (u: string | null) => void;
    const kuld = vi.fn(() => new Promise<string | null>((r) => { kesz = r; }));
    webkit(kuld);
    le = hidTelepit(fuggosegek());
    const elso = hid().mappaValasztas() as Promise<string | null>;
    expect(await hid().mappaValasztas()).toBeNull();
    expect(kuld).toHaveBeenCalledOnce();
    kesz('/synthetic/A');
    expect(await elso).toBe('/synthetic/A');
    const masodik = hid().mappaValasztas() as Promise<string | null>;
    kesz('/synthetic/B');
    expect(await masodik).toBe('/synthetic/B');
  });

  it('a függőségként adott választó (teszt) felülírja a héj csatornáját', async () => {
    const mas = vi.fn(async () => '/synthetic/Mas');
    le = hidTelepit(fuggosegek({ mappaValasztas: mas }));
    expect(await hid().mappaValasztas('cim')).toBe('/synthetic/Mas');
    expect(mas).toHaveBeenCalledWith('cim');
  });
});

describe('mentetlen(): a core halálakor a héj ebből kérdez és másol (C29.7b, T031)', () => {
  it('a mentetlen (gépelt, hibás, ütköző) dokumentumok útja, állapota, hibája és szövege — mentés és zárás nélkül', async () => {
    const core = new AlCore();
    const dk = new Dokumentumok(core);
    const a = await dk.megnyit('A.md');
    await dk.megnyit('B.md');
    const v = ChangeSet.of([{ from: 0, insert: 'x' }], a.szoveg.length);
    a.valtozott(v, v.apply(a.szoveg), null);
    le = hidTelepit(fuggosegek({ mentetlenSzovegek: () => mentetlenSzovegek(dk) }));
    const lista = hid().mentetlen() as { ut: string; allapot: string; hiba: string | null; szoveg: string }[];
    expect(lista).toEqual([{ ut: 'A.md', allapot: 'piszkos', hiba: null, szoveg: 'x# A\n' }]);
    expect(leall.aktiv).toBe(false); // nem kapcsolja be a „leáll” réteget: a szerkesztés tovább megy (újraindítás)
    expect(core.lemez).toBe('# A\n'); // és nem ment
  });

  it('a hídon át nem dob, ha a lekérés hibázik', () => {
    le = hidTelepit(fuggosegek({ mentetlenSzovegek: () => { throw new Error('x'); } }));
    expect(hid().mentetlen()).toEqual([]);
  });
});

describe('mentes(): a kilépési jelentés (a héj ebből dönt)', () => {
  it('a jelentés alakja `{ok, mentetlen: [{ut, allapot, hiba}]}` — valódi dokumentumokon', async () => {
    const core = new AlCore();
    const dk = new Dokumentumok(core);
    const a = await dk.megnyit('A.md');
    await dk.megnyit('B.md');
    const v = ChangeSet.of([{ from: 0, insert: 'x' }], a.szoveg.length);
    a.valtozott(v, v.apply(a.szoveg), null);
    core.hiba = new ApiHiba(500, 'a lemez megtelt');
    le = hidTelepit(fuggosegek({ kilepesMentes: () => kilepesMentes(dk) }));
    const j = await hid().mentes();
    expect(j).toEqual({ ok: false, mentetlen: [{ ut: 'A.md', allapot: 'hiba', hiba: 'a lemez megtelt' }] });
    core.hiba = null;
    expect(await hid().mentes()).toEqual({ ok: true, mentetlen: [] });
    expect(core.lemez.startsWith('x')).toBe(true);
  });

  it('sorrend: leáll állapot → felület-állapot és dokumentumok → tracker-ürítés (utoljára)', async () => {
    const f = fuggosegek();
    le = hidTelepit(f);
    expect(leall.aktiv).toBe(false);
    await hid().mentes();
    expect(f.sorrend).toEqual(['elokeszit', 'felulet-allapot', 'dokumentumok(leall=true)', 'tracker']);
    expect(leall.aktiv).toBe(true); // a mentés után is „leáll” marad: a héj vagy leállítja a core-t, vagy visszavonja
  });

  it('leallAllapot(szöveg | null): a héj frissíti a szöveget, null visszavonja (Vissza a szerkesztéshez)', async () => {
    le = hidTelepit(fuggosegek());
    await hid().mentes();
    hid().leallAllapot('Leállítás a futó feladat végén…');
    expect(leall.szoveg).toBe('Leállítás a futó feladat végén…');
    hid().leallAllapot(null);
    expect(leall.aktiv).toBe(false);
  });

  it('a tracker-ürítés időkorlátos: a core nem válaszol → a jelentés ≤ 2,5 s alatt megjön', async () => {
    le = hidTelepit(fuggosegek({ trackerKi: () => new Promise<void>(() => {}) }));
    let kesz = false;
    const p = (hid().mentes() as Promise<unknown>).then((j) => ((kesz = true), j));
    await vi.advanceTimersByTimeAsync(1500);
    expect(kesz).toBe(false);
    await vi.advanceTimersByTimeAsync(1000);
    expect(kesz).toBe(true);
    expect(await p).toEqual({ ok: true, mentetlen: [] });
  });

  it('a tracker hibája nem viszi el a jelentést', async () => {
    le = hidTelepit(fuggosegek({ trackerKi: async () => Promise.reject(new Error('hálózat')) }));
    expect(await hid().mentes()).toEqual({ ok: true, mentetlen: [] });
  });
});
