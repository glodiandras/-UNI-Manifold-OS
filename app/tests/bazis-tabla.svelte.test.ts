// A Bases táblázata és kerete (C12 6. lépés) jsdom-ban ál-core-ral: ablakozás, link-cellák, csoport, összesítő,
// a sorszámozott kérések, a frissítés eseményre, a `.base` fül.

import { cleanup, fireEvent, render, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { BazisApi } from '../src/bazis/api';
import BazisFul from '../src/bazis/BazisFul.svelte';
import BazisNezet from '../src/bazis/BazisNezet.svelte';
import { rogzitettForras } from '../src/bazis/forras';
import Tabla from '../src/bazis/Tabla.svelte';
import type { LekerdezOpciok, Oszlop, Sor, Valasz } from '../src/bazis/tipusok';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import { navigacioBeallit } from '../src/szerkeszto/linkek/navigacio';
import { szerkesztok } from '../src/szerkeszto/szerkesztok.svelte';

const OSZLOPOK: Oszlop[] = [
  { id: 'file.name', nev: 'Fájlnév', ter: 'file', tipus: 'text', szerkesztheto: false, szelesseg: 250 },
  { id: 'Status', nev: 'Status', ter: 'note', tipus: 'text', szerkesztheto: true, szelesseg: null },
  { id: 'Rating', nev: 'Értékelés', ter: 'note', tipus: 'number', szerkesztheto: true, szelesseg: 90 },
  { id: 'Done', nev: 'Kész', ter: 'note', tipus: 'checkbox', szerkesztheto: true, szelesseg: null },
  { id: 'Tags', nev: 'Címkék', ter: 'note', tipus: 'tags', szerkesztheto: true, szelesseg: null },
];

function sor(i: number, ut = `Mappa/Jegyzet ${i}.md`): Sor {
  return {
    ut,
    nev: `Jegyzet ${i}`,
    md: true,
    cellak: [
      { t: 'link', cel: ut, ut, nev: `Jegyzet ${i}` },
      i % 2 ? 'Done' : 'Reading',
      i / 10,
      i % 3 === 0,
      { t: 'lista', e: ['Book', 'x'] },
    ],
  };
}

function valasz(db: number, kieg: Partial<Valasz> = {}): Valasz {
  return {
    ok: true,
    nezetek: [{ nev: 'Táblázat', tipus: 'table', ismert: true }],
    nezet: { index: 0, nev: 'Táblázat', tipus: 'table', eredeti_tipus: 'table', beallitas: {} },
    oszlopok: OSZLOPOK,
    sorok: Array.from({ length: db }, (_, i) => sor(i)),
    csoportok: null,
    osszesitok: {},
    osszes: db,
    levagva: false,
    hibak: [],
    figyelmeztetesek: [],
    ido_ms: 12.5,
    generacio: 1,
    ...kieg,
  };
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  navigacioBeallit(null);
});

describe('Tabla', () => {
  it('fejléc, cellák és típus szerinti megjelenítés', () => {
    const { container } = render(Tabla, { props: { valasz: valasz(3) } });
    const fejlec = [...container.querySelectorAll('[role=columnheader]')].map((e) => e.textContent?.trim());
    expect(fejlec).toEqual(['Fájlnév', 'Status', 'Értékelés', 'Kész', 'Címkék']);
    const sorok = container.querySelectorAll('.sor');
    expect(sorok).toHaveLength(3);
    const c = [...sorok[1].querySelectorAll('[role=cell]')];
    expect(c[0].textContent?.trim()).toBe('Jegyzet 1');
    expect(c[1].textContent?.trim()).toBe('Done');
    expect(c[2].textContent?.trim()).toBe('0,1');
    expect(c[3].querySelector('.jelolo')).not.toBeNull();
    expect(c[3].querySelector('.jelolo.be')).toBeNull();
    expect([...c[4].querySelectorAll('.elem')].map((e) => e.textContent?.trim())).toEqual(['Book', 'x']);
    expect(sorok[0].querySelector('.jelolo.be')).not.toBeNull();
  });

  it('az oszlopszélesség a core adata (px), az alap a típustól függ', () => {
    const { container } = render(Tabla, { props: { valasz: valasz(1) } });
    const sablon = (container.querySelector('.fejlec') as HTMLElement).style.gridTemplateColumns;
    expect(sablon.startsWith('250px 180px 90px 110px 220px')).toBe(true);
  });

  it('2000 sornál csak a látható sorok kerülnek a DOM-ba, és görgetésre a tartomány követi', async () => {
    const { container } = render(Tabla, { props: { valasz: valasz(2000) } });
    const elso = container.querySelectorAll('.sor');
    expect(elso.length).toBeGreaterThan(5);
    expect(elso.length).toBeLessThan(80);
    expect(elso[0].textContent).toContain('Jegyzet 0');
    const g = container.querySelector('.gorgeto') as HTMLElement;
    g.scrollTop = 30 * 1000;
    await fireEvent.scroll(g);
    const kozep = [...container.querySelectorAll('.sor')].map((e) => e.querySelector('.link')?.textContent);
    expect(kozep).toContain('Jegyzet 1000');
    expect(kozep).not.toContain('Jegyzet 0');
    expect(container.querySelectorAll('.sor').length).toBeLessThan(80);
    // a kirajzolatlan sorok helye megmarad: a görgetősáv hossza a teljes lista
    const fent = (container.querySelector('.torzs > div') as HTMLElement).style.height;
    expect(parseInt(fent)).toBeGreaterThan(25_000);
  });

  it('a sormagasság a rowHeight beállításból jön', () => {
    const v = valasz(2);
    v.nezet!.beallitas = { rowHeight: 'tall' };
    const { container } = render(Tabla, { props: { valasz: v } });
    expect((container.querySelector('.sor') as HTMLElement).style.height).toBe('62px');
  });

  it('csoportfejléc a csoport összesítőjével, lábléc az egész nézet összesítőjével', () => {
    const v = valasz(4, {
      csoportok: [
        { kulcs: 'Done', cimke: 'Done', tol: 0, db: 2, huzhato: true, osszesitok: { Rating: { nev: 'Average', ertek: 0.05 } } },
        { kulcs: null, cimke: '', tol: 2, db: 2, huzhato: true, osszesitok: {} },
      ],
      osszesitok: { Rating: { nev: 'Sum', ertek: 0.6 } },
    });
    const { container } = render(Tabla, { props: { valasz: v } });
    const cs = container.querySelectorAll('.csoport');
    expect(cs).toHaveLength(2);
    expect(cs[0].textContent).toContain('Done');
    expect(cs[0].querySelector('.csoport-db')?.textContent).toBe('2');
    expect(cs[0].querySelector('.osszesito')?.textContent).toContain('Average');
    expect(cs[0].querySelector('.osszesito')?.textContent).toContain('0,05');
    expect(cs[1].querySelector('.csoport-cim')?.textContent).toBe('Nincs érték');
    expect(container.querySelectorAll('.sor')).toHaveLength(4);
    const sorrend = [...container.querySelectorAll('.csoport, .sor')].map((e) => e.className.split(' ')[0]);
    expect(sorrend).toEqual(['csoport', 'sor', 'sor', 'csoport', 'sor', 'sor']);
    const lablec = container.querySelector('.lablec')!;
    expect(lablec.textContent).toContain('Sum');
    expect(lablec.textContent).toContain('0,6');
  });

  it('üres találati halmaznál üzenet', () => {
    const { container } = render(Tabla, { props: { valasz: valasz(0) } });
    expect(container.querySelector('.ures')?.textContent).toContain('Nincs a feltételeknek');
    expect(container.querySelectorAll('.sor')).toHaveLength(0);
  });

  it('a hiba-cella és az üres cella', () => {
    const v = valasz(1);
    v.sorok[0].cellak = [{ t: 'hiba', u: 'rossz' }, null, null, null, null];
    const { container } = render(Tabla, { props: { valasz: v } });
    const h = container.querySelector('.hiba')!;
    expect(h.textContent).toBe('Hiba');
    expect(h.getAttribute('title')).toBe('rossz');
    expect(container.querySelectorAll('.cella .ures')).toHaveLength(4);
  });

  it('a link-cella a core feloldott útját nyitja (⌘ új fül); feloldatlan linknél a cél szövegét adja át', async () => {
    const nyitasok: unknown[] = [];
    navigacioBeallit({ megnyit: (ut, mod) => nyitasok.push([ut, mod]), mappak: () => [] });
    vi.stubGlobal('fetch', async (url: string) => {
      const u = new URL(url, 'http://127.0.0.1/');
      const cel = u.searchParams.get('cel')!;
      const kimenet = cel === 'Nincs' ? { tipus: 'nincs', cel } : { tipus: 'jegyzet', ut: cel };
      return new Response(JSON.stringify(kimenet), { status: 200, headers: { 'Content-Type': 'application/json' } });
    });
    const v = valasz(1);
    v.sorok[0].cellak[1] = { t: 'link', cel: 'Cél', ut: 'People/Cél.md', nev: 'Cél' };
    const { container } = render(Tabla, { props: { valasz: v, ez: 'Host.base' } });
    const linkek = container.querySelectorAll<HTMLAnchorElement>('a.link');
    await fireEvent.click(linkek[0]);
    await waitFor(() => expect(nyitasok).toEqual([['Mappa/Jegyzet 0.md', 'aktiv']]));
    await fireEvent.click(linkek[1], { metaKey: true });
    await waitFor(() => expect(nyitasok).toHaveLength(2));
    expect(nyitasok[1]).toEqual(['People/Cél.md', 'ujful']);
  });
});

// ---------------------------------------------------------------------- BazisNezet

function alApi(valaszok: (szoveg: string, o: unknown) => Valasz | Promise<Valasz>): BazisApi & { hivasok: unknown[][] } {
  const hivasok: unknown[][] = [];
  return {
    hivasok,
    lekerdez: async (szoveg, o) => {
      hivasok.push([szoveg, o]);
      return valaszok(szoveg, o);
    },
    modosit: async (szoveg) => ({ ok: true, szoveg_uj: szoveg, valtozas: '', hibak: [] }),
  };
}

describe('BazisNezet', () => {
  it('lekérdez, kirajzol; a találatszám title-je a core és a rajz idejét mutatja', async () => {
    const api = alApi(() => valasz(3));
    const forras = rogzitettForras('views:\n  - type: table\n', 'X.base');
    const { container } = render(BazisNezet, { props: { forras, api } });
    await waitFor(() => expect(container.querySelectorAll('.sor')).toHaveLength(3));
    expect(api.hivasok[0][0]).toBe('views:\n  - type: table\n');
    expect(api.hivasok[0][1]).toMatchObject({ ez: 'X.base', nezet: null, kerdes: 1 });          // a kérés-azonosító is megy (T040)
    expect((api.hivasok[0][1] as LekerdezOpciok).azon).toMatch(/^bm-/);
    const t = container.querySelector('.talalat') as HTMLElement;
    expect(t.textContent?.trim()).toBe('3 találat');
    await waitFor(() => expect(t.title).toMatch(/^core: 12\.5 ms · rajz: \d+ ms$/));
  });

  it('több nézetnél fülek; a váltás új lekérdezést indít, és jelez a fülnek', async () => {
    const valtott: number[] = [];
    const api = alApi((_, o) => {
      const i = (o as { nezet: number | null }).nezet ?? 0;
      return valasz(2, {
        nezetek: [
          { nev: 'A', tipus: 'table', ismert: true },
          { nev: 'Bé', tipus: 'table', ismert: true },
        ],
        nezet: { index: i, nev: i ? 'Bé' : 'A', tipus: 'table', eredeti_tipus: 'table', beallitas: {} },
      });
    });
    const forras = rogzitettForras('x', 'X.base');
    const { container } = render(BazisNezet, { props: { forras, api, nezetValtott: (i: number) => valtott.push(i) } });
    await waitFor(() => expect(container.querySelectorAll('[role=tab]')).toHaveLength(2));
    expect(container.querySelector('[role=tab][aria-selected=true]')?.textContent).toBe('A');
    await fireEvent.click(container.querySelectorAll('[role=tab]')[1]);
    await waitFor(() => expect(container.querySelector('[role=tab][aria-selected=true]')?.textContent).toBe('Bé'));
    expect(valtott).toEqual([1]);
    expect(api.hivasok.at(-1)![1]).toMatchObject({ ez: 'X.base', nezet: 1 });
    const elso = api.hivasok[0][1] as LekerdezOpciok;
    const utolso = api.hivasok.at(-1)![1] as LekerdezOpciok;
    expect(utolso.kerdes!).toBeGreaterThan(elso.kerdes!);                                 // újabb kérés: nagyobb sorszám, ugyanaz az azonosító
    expect(utolso.azon).toBe(elso.azon);
  });

  it('a kártya-nézet kártyákat rajzol (nem táblázatot)', async () => {
    const api = alApi(() => valasz(2, { nezet: { index: 0, nev: 'K', tipus: 'cards', eredeti_tipus: 'cards', beallitas: {} } }));
    const { container } = render(BazisNezet, { props: { forras: rogzitettForras('x', null), api } });
    await waitFor(() => expect(container.querySelectorAll('.kartya')).toHaveLength(2));
    expect(container.querySelector('[role=table]')).toBeNull();
  });

  it('a hibák és figyelmeztetések a nézet fölött jelennek meg, a YAML-hiba nem rajzol táblázatot', async () => {
    const api = alApi(() =>
      valasz(0, { ok: false, nezet: null, oszlopok: [], hibak: [{ hely: 'yaml', uzenet: 'rossz bemenet' }] }),
    );
    const { container } = render(BazisNezet, { props: { forras: rogzitettForras('x', null), api } });
    await waitFor(() => expect(container.querySelector('[role=alert]')).not.toBeNull());
    expect(container.querySelector('[role=alert]')!.textContent).toContain('A .base fájl nem értelmezhető');
    expect(container.querySelector('[role=table]')).toBeNull();
    const api2 = alApi(() =>
      valasz(1, { hibak: [{ hely: 'filters', uzenet: 'x == 1', db: 2 }], figyelmeztetesek: [{ hely: 'views[0]', uzenet: 'ismeretlen nézettípus' }] }),
    );
    const r2 = render(BazisNezet, { props: { forras: rogzitettForras('x', null), api: api2 } });
    await waitFor(() => expect(r2.container.querySelector('[role=alert]')).not.toBeNull());
    expect(r2.container.querySelector('[role=alert]')!.textContent).toContain('2 sort kihagytam');
    expect(r2.container.querySelector('[role=status]')!.textContent).toContain('ismeretlen nézettípus');
  });

  it('a core hibája (pl. az index nem kész) üzenet, nem dob', async () => {
    const api = alApi(() => {
      throw new Error('az index még nem épült fel');
    });
    const { container } = render(BazisNezet, { props: { forras: rogzitettForras('x', null), api } });
    await waitFor(() => expect(container.querySelector('[role=alert]')?.textContent).toContain('az index még nem épült fel'));
  });

  it('az elavult válasz eldobódik (a sorszámozott kérések)', async () => {
    let feloldok: Array<(v: Valasz) => void> = [];
    const api = alApi(() => new Promise<Valasz>((f) => feloldok.push(f)));
    const forras = rogzitettForras('x', null);
    const { container } = render(BazisNezet, { props: { forras, api } });
    await waitFor(() => expect(feloldok).toHaveLength(1));
    await forras.ir('y'); // a szöveg változik: új kérés
    await waitFor(() => expect(feloldok).toHaveLength(2));
    feloldok[1](valasz(5)); // az újabb előbb megérkezik
    await waitFor(() => expect(container.querySelectorAll('.sor')).toHaveLength(5));
    feloldok[0](valasz(2)); // a régi később: eldobódik
    await new Promise((r) => setTimeout(r, 30));
    expect(container.querySelectorAll('.sor')).toHaveLength(5);
  });

  it('a vault változása után 300 ms-mal újra lekérdez; az index kész-jelére azonnal', async () => {
    const kapcsolat = new CoreKapcsolat('ws://127.0.0.1:1/ws');
    const api = alApi(() => valasz(1));
    render(BazisNezet, { props: { forras: rogzitettForras('x', null), api, kapcsolat } });
    await waitFor(() => expect(api.hivasok).toHaveLength(1));
    kapcsolat.szetoszt({ tipus: 'vault_valtozas', utak: ['A.md'], torolt: [], kulso: [] });
    kapcsolat.szetoszt({ tipus: 'vault_valtozas', utak: ['B.md'], torolt: [], kulso: [] });
    await new Promise((r) => setTimeout(r, 120));
    expect(api.hivasok).toHaveLength(1); // még a késleltetésen belül
    await waitFor(() => expect(api.hivasok).toHaveLength(2)); // a két esemény egy kérésbe olvadt
    await new Promise((r) => setTimeout(r, 400));
    expect(api.hivasok).toHaveLength(2);
    kapcsolat.szetoszt({ tipus: 'index', kesz: true });
    await waitFor(() => expect(api.hivasok).toHaveLength(3));
  });

  it('a bezárás után az úton lévő válasz nem ír és az események nem indítanak kérést', async () => {
    const kapcsolat = new CoreKapcsolat('ws://127.0.0.1:1/ws');
    const api = alApi(() => valasz(1));
    const { unmount } = render(BazisNezet, { props: { forras: rogzitettForras('x', null), api, kapcsolat } });
    await waitFor(() => expect(api.hivasok).toHaveLength(1));
    unmount();
    kapcsolat.szetoszt({ tipus: 'vault_valtozas', utak: [], torolt: [], kulso: [] });
    await new Promise((r) => setTimeout(r, 450));
    expect(api.hivasok).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------- a .base fül

describe('BazisFul', () => {
  const BASE = 'views:\n  - type: table\n    name: Books\n';

  function megjelenit(kieg: Record<string, unknown> = {}) {
    const felulet = new Felulet({});
    const ful = $state({ id: 'f1', ut: 'X03 - Books/Books.base' as string | null, nezet: kieg as Record<string, unknown> | undefined });
    const context = new Map<unknown, unknown>([
      [KORNYEZET_KULCS, { felulet, fajlok: new VaultFajlok(), kapcsolat: new CoreKapcsolat('ws://127.0.0.1:1/ws') }],
    ]);
    const r = render(BazisFul, { props: { ful, info: undefined, aktiv: true }, context });
    return { ...r, ful };
  }

  let lekerdezesek: Array<{ szoveg: string; ez: string; nezet: unknown }>;
  let lemez: Map<string, string>;

  beforeEach(() => {
    lekerdezesek = [];
    lemez = new Map([['X03 - Books/Books.base', BASE]]);
    vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
      const u = new URL(url, 'http://127.0.0.1/');
      const valasz_ = (kod: number, adat: unknown) =>
        new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });
      if (u.pathname === '/api/vault/fajl') {
        const ut = u.searchParams.get('ut')!;
        const t = lemez.get(ut);
        if (t === undefined) return valasz_(404, { hiba: 'nincs ilyen fájl' });
        return valasz_(200, { ut, tartalom: t, hash: 'h', jel: '', mtime: 0, kodolas_hiba: false });
      }
      if (u.pathname === '/api/vault/bazis/lekerdez') {
        const k = JSON.parse(String(init!.body));
        lekerdezesek.push(k);
        return valasz_(200, valasz(2));
      }
      return valasz_(404, { hiba: 'nincs' });
    });
  });

  it('megnyitja a fájlt a Dokumentumon át, a szöveget a core-nak adja, és kirajzolja a sorokat', async () => {
    const { container } = megjelenit();
    await waitFor(() => expect(container.querySelectorAll('.sor')).toHaveLength(2));
    expect(lekerdezesek[0]).toMatchObject({ szoveg: BASE, ez: 'X03 - Books/Books.base' });
    expect(container.querySelector('.morzsa')!.textContent).toContain('Books');
    expect(szerkesztok.dokumentumok.kap('X03 - Books/Books.base')).toBeDefined();
  });

  it('a fül tartós állapotából indul a nézet, és a váltás oda is íródik', async () => {
    const { ful } = megjelenit({ bazisNezet: 1 });
    await waitFor(() => expect(lekerdezesek.length).toBeGreaterThan(0));
    expect(lekerdezesek[0].nezet).toBe(1);
    expect(ful.nezet?.bazisNezet).toBe(1);
  });

  it('a hiányzó fájl hibaüzenetet ad', async () => {
    lemez.clear();
    const { container } = megjelenit();
    await waitFor(() => expect(container.querySelector('.hiba')?.textContent).toContain('nincs meg'));
  });

  it('a nézet lebontása elengedi a dokumentumot', async () => {
    const { container, unmount } = megjelenit();
    await waitFor(() => expect(container.querySelectorAll('.sor')).toHaveLength(2));
    const d = szerkesztok.dokumentumok.kap('X03 - Books/Books.base')!;
    expect(d.nezetSzam).toBe(1);
    unmount();
    await waitFor(() => expect(d.nezetSzam).toBe(0));
  });
});
