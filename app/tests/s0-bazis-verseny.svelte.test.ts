// A tiszta módosítószámoló válasza csak arra a forrásra alkalmazható, amelyből készült.
// A késleltetett API és a memóriabeli forrás valódi modellmetódusokat vizsgál; nincs vault- vagy lemezírás.
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { BazisApi } from '../src/bazis/api';
import type { BazisForras } from '../src/bazis/forras';
import { BazisModell } from '../src/bazis/modell.svelte';
import type { ModositValasz, Muvelet } from '../src/bazis/tipusok';

const ALAP = 'views:\n  - type: table\n    name: Original\n  - type: cards\n    name: Secondary\n';
const KULSO = ALAP.replace('Original', 'External edit');
const LISTA = { fajta: 'nezet_beallit', nezet: 0, kulcs: 'type', ertek: 'list' } satisfies Muvelet;
const VALTOZOTT = 'A szöveg közben változott; próbáld újra.';
const modellek: BazisModell[] = [];

function fuggoben<T>() {
  let kesz!: (v: T) => void;
  const igeret = new Promise<T>((resolve) => { kesz = resolve; });
  return { igeret, kesz };
}

const eredmeny = (szoveg_uj: string): ModositValasz => ({ ok: true, szoveg_uj, valtozas: '', hibak: [] });

function keret() {
  let szoveg = ALAP;
  let tiltas: string | null = null;
  const api: BazisApi = {
    lekerdez: vi.fn<BazisApi['lekerdez']>(),
    modosit: vi.fn(async (s) => eredmeny(s.replace('type: table', 'type: list'))),
  };
  const forras: BazisForras = {
    ez: 'Views/Synthetic.base',
    szoveg: () => szoveg,
    csakOlvashato: () => tiltas,
    ir: vi.fn(async (s) => { szoveg = s; return true; }),
    figyel: () => () => {},
    lezar: async () => {},
  };
  const modell = new BazisModell(forras, { api, nezet: 0 });
  modellek.push(modell);
  return { api, forras, modell, kulso: (s: string) => { szoveg = s; }, tilt: (s: string | null) => { tiltas = s; } };
}

afterEach(() => {
  for (const modell of modellek.splice(0)) modell.lebont();
});

describe('S0 Bases: számolás és írás közti verseny', () => {
  it('nem írja felül a számolás alatt érkező külső szerkesztést; az újrapróba a friss szövegből számol', async () => {
    const k = keret();
    const valasz = fuggoben<ModositValasz>();
    vi.mocked(k.api.modosit).mockImplementationOnce(() => valasz.igeret);
    const iras = k.modell.alkalmaz(LISTA, 1);
    await Promise.resolve();
    expect(k.api.modosit).toHaveBeenCalledWith(ALAP, LISTA);
    k.kulso(KULSO);
    valasz.kesz(eredmeny(ALAP.replace('type: table', 'type: list')));

    expect(await iras).toMatchObject({ ok: false, irva: false });
    expect(k.forras.ir).not.toHaveBeenCalled();
    expect(k.forras.szoveg()).toBe(KULSO);
    expect(k.modell.irasHiba).toBe(VALTOZOTT);
    expect(k.modell.nezet).toBe(0);

    expect(await k.modell.alkalmaz(LISTA, 1)).toMatchObject({ ok: true, irva: true });
    expect(k.api.modosit).toHaveBeenLastCalledWith(KULSO, LISTA);
    expect(k.forras.szoveg()).toBe(KULSO.replace('type: table', 'type: list'));
    expect(k.modell.irasHiba).toBeNull();
    expect(k.modell.nezet).toBe(1);
  });

  it.each(['Synthetic read-only', 'Synthetic conflict'])('a számolás alatt életbe lépő %s kaput az írás előtt újra ellenőrzi', async (tiltas) => {
    const k = keret();
    const valasz = fuggoben<ModositValasz>();
    vi.mocked(k.api.modosit).mockImplementationOnce(() => valasz.igeret);
    const iras = k.modell.alkalmaz(LISTA, 1);
    await Promise.resolve();
    k.tilt(tiltas);
    valasz.kesz(eredmeny(ALAP.replace('type: table', 'type: list')));

    expect(await iras).toMatchObject({ ok: false, irva: false });
    expect(k.forras.ir).not.toHaveBeenCalled();
    expect(k.forras.szoveg()).toBe(ALAP);
    expect(k.modell.irasHiba).toBe(tiltas);
    expect(k.modell.nezet).toBe(0);
  });

  it('a régi eredménnyel azonos külső szöveg sem számít sikeres saját műveletnek', async () => {
    const k = keret();
    const valasz = fuggoben<ModositValasz>();
    vi.mocked(k.api.modosit).mockImplementationOnce(() => valasz.igeret);
    const iras = k.modell.alkalmaz(LISTA, 1);
    await Promise.resolve();
    const uj = ALAP.replace('type: table', 'type: list');
    k.kulso(uj);
    valasz.kesz(eredmeny(uj));

    expect(await iras).toMatchObject({ ok: false, irva: false });
    expect(k.forras.ir).not.toHaveBeenCalled();
    expect(k.forras.szoveg()).toBe(uj);
    expect(k.modell.irasHiba).toBe(VALTOZOTT);
    expect(k.modell.nezet).toBe(0);
  });

  it('a változatlan eredmény sem kerülheti meg a közben életbe lépő írási tiltást', async () => {
    const k = keret();
    const valasz = fuggoben<ModositValasz>();
    vi.mocked(k.api.modosit).mockImplementationOnce(() => valasz.igeret);
    const iras = k.modell.alkalmaz(LISTA, 1);
    await Promise.resolve();
    k.tilt('Synthetic conflict');
    valasz.kesz(eredmeny(ALAP));

    expect(await iras).toMatchObject({ ok: false, irva: false });
    expect(k.forras.ir).not.toHaveBeenCalled();
    expect(k.modell.irasHiba).toBe('Synthetic conflict');
    expect(k.modell.nezet).toBe(0);
  });

  it('a sorban következő művelet egy elavult számítás elutasítása után is a legfrissebb forrást kapja', async () => {
    const k = keret();
    const valasz = fuggoben<ModositValasz>();
    vi.mocked(k.api.modosit).mockImplementationOnce(() => valasz.igeret);
    const elso = k.modell.alkalmaz(LISTA, 1);
    const masodik = k.modell.alkalmaz(LISTA, 1);
    await Promise.resolve();
    expect(k.api.modosit).toHaveBeenCalledTimes(1);
    k.kulso(KULSO);
    valasz.kesz(eredmeny(ALAP.replace('type: table', 'type: list')));

    expect(await elso).toMatchObject({ ok: false, irva: false });
    expect(await masodik).toMatchObject({ ok: true, irva: true });
    expect(vi.mocked(k.api.modosit).mock.calls.map(([s]) => s)).toEqual([ALAP, KULSO]);
    expect(k.forras.ir).toHaveBeenCalledExactlyOnceWith(KULSO.replace('type: table', 'type: list'));
    expect(k.modell.nezet).toBe(1);
  });

  it('kezdeti tiltásnál számolás sincs, és sikertelen mentés nem vált nézetet', async () => {
    const k = keret();
    k.tilt('Synthetic read-only');
    expect(await k.modell.alkalmaz(LISTA, 1)).toMatchObject({ ok: false, irva: false });
    expect(k.api.modosit).not.toHaveBeenCalled();
    expect(k.forras.ir).not.toHaveBeenCalled();
    k.tilt(null);
    vi.mocked(k.forras.ir).mockResolvedValueOnce(false);
    expect(await k.modell.alkalmaz(LISTA, 1)).toMatchObject({ irva: false });
    expect(k.forras.szoveg()).toBe(ALAP);
    expect(k.modell.nezet).toBe(0);
  });

  it('a valóban változatlan siker törli a korábbi hibát, lemezírás nélkül', async () => {
    const k = keret();
    k.modell.irasHiba = 'Previous write failed';
    vi.mocked(k.api.modosit).mockResolvedValueOnce(eredmeny(ALAP));
    expect(await k.modell.alkalmaz(LISTA, 1)).toMatchObject({ ok: true, irva: true });
    expect(k.forras.ir).not.toHaveBeenCalled();
    expect(k.modell.irasHiba).toBeNull();
    expect(k.modell.nezet).toBe(1);
  });
});
