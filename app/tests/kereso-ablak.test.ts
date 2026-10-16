// A nagy keresőablak (E3, ⌘⇧F): késleltetett lekérdezés és elavult válasz eldobása, fájlkártyák kiemelt kivágásokkal,
// a sorra ugrás (kódpont → UTF-16), billentyűzet (↑↓ ↵ ⌘↵ ⌥⌘↵ ⌥↵ Tab ⌘G Esc), a core magyar hibaüzenete (hibás
// lekérdezés, regex-időtúllépés), az index-építés, a ⌘⇧F parancs és a kijelölésből kezdő szöveg.

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { alapParancsok } from '../src/alapParancsok';
import Kereses from '../src/atfedes/KeresoAblak.svelte';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { keresoMegnyit, keresoSzavak, szoKiemeles } from '../src/lib/kereses/kereso';
import { darabok, sorokraEgyesit, utf16Oszlop, vaultKereses } from '../src/lib/kereses/vaultKereses.svelte';
import { Regiszter } from '../src/lib/parancsok/regiszter';
import { VaultFajlok, type FajlInfo } from '../src/lib/vault/fajlok.svelte';
import { szerkesztok } from '../src/szerkeszto/szerkesztok.svelte';

const FAJLOK: FajlInfo[] = [
  { ut: 'Matek/Sorozatok/04 - Mértani sorozat.md', tipus: 'md', meret: 1, mtime: 1 },
  { ut: 'Fizika/Newton.md', tipus: 'md', meret: 1, mtime: 1 },
];

const VALASZ = {
  q: 'sorozat',
  osszes: 2,
  talalatok: [
    {
      ut: 'Matek/Sorozatok/04 - Mértani sorozat.md',
      pont: 3,
      talalatok: [
        { sor: 5, oszlop: 10, hossz: 7, szoveg: 'A mértani sorozat képlete', elotte: ['# Mértani'], utana: ['$a_n = a_1 q^{n-1}$'] },
        { sor: 9, oszlop: 5, hossz: 7, szoveg: '😀 a sorozat', elotte: [], utana: [] },
      ],
    },
    { ut: 'Fizika/Newton.md', pont: 1, talalatok: [{ sor: 2, oszlop: 0, hossz: 7, szoveg: 'sorozat a fizikában' }] },
  ],
};

let kerelmek: string[];
let valaszol: (q: string) => Promise<Response> | Response;

function valasz(adat: unknown, kod = 200) {
  return new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });
}

function kornyezet() {
  const felulet = new Felulet({});
  const fajlok = new VaultFajlok();
  fajlok.beallit(FAJLOK);
  const kapcsolat = new CoreKapcsolat('ws://x');
  const context = new Map<unknown, unknown>([[KORNYEZET_KULCS, { felulet, fajlok, kapcsolat }]]);
  return { felulet, kapcsolat, context };
}

const mezo = () => screen.getByRole('combobox', { name: 'Keresés' });
const opciok = () => screen.getAllByRole('option');

beforeEach(() => {
  kerelmek = [];
  valaszol = () => valasz(VALASZ);
  vi.stubGlobal('fetch', async (url: string) => {
    const u = new URL(url, 'http://127.0.0.1/');
    kerelmek.push(u.pathname + u.search);
    return valaszol(u.searchParams.get('q') ?? '');
  });
  vaultKereses.beallit('', true);
  vaultKereses.indexEpul = false;
  vaultKereses.fokuszKer = 0;
});

afterEach(() => {
  cleanup();
  document.body.textContent = '';
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vaultKereses.beallit('', true);
});

describe('lekérdezés', () => {
  it('üresen a keresőnyelv súgója; gépelésre késleltetve, egyetlen kérés megy (kornyezet=1, limit)', async () => {
    const { context } = kornyezet();
    render(Kereses, { context });
    expect(screen.getByText('Keresőnyelv')).toBeTruthy();
    expect(screen.getByText('"pontos kifejezés"')).toBeTruthy();
    for (const q of ['s', 'so', 'sor', 'sorozat']) await fireEvent.input(mezo(), { target: { value: q } });
    expect(kerelmek.length).toBe(0);
    await waitFor(() => expect(kerelmek.length).toBe(1), { timeout: 2000 });
    expect(kerelmek[0]).toBe('/api/vault/kereses?q=sorozat&limit=200&kornyezet=1');
    expect(await screen.findByText('2 találó fájl')).toBeTruthy();
  });

  it('az elavult válasz nem írja felül az újabbat', async () => {
    const { context } = kornyezet();
    let kiad: (r: Response) => void = () => {};
    valaszol = (q) => (q === 'lassu' ? new Promise<Response>((r) => (kiad = r)) : valasz({ ...VALASZ, q, osszes: 1, talalatok: [VALASZ.talalatok[1]] }));
    render(Kereses, { context });
    vaultKereses.beallit('lassu', true);
    await waitFor(() => expect(kerelmek.length).toBe(1));
    vaultKereses.beallit('gyors', true);
    expect(await screen.findByText('1 találó fájl')).toBeTruthy();
    kiad(valasz({ ...VALASZ, q: 'lassu', osszes: 2 }));
    await new Promise((r) => setTimeout(r, 30));
    expect(screen.getByText('1 találó fájl')).toBeTruthy();
    expect(screen.queryByText('2 találó fájl')).toBeNull();
  });

  it('egy karakternél nincs kérés, csak tipp; a hosszabb lekérdezés megy', async () => {
    const { context } = kornyezet();
    render(Kereses, { context });
    vaultKereses.beallit('a', true);
    await new Promise((r) => setTimeout(r, 40));
    expect(kerelmek.length).toBe(0);
    expect(screen.getByText(/Legalább 2 karakter/)).toBeTruthy();
    vaultKereses.beallit('ab', true);
    await waitFor(() => expect(kerelmek.length).toBe(1));
    expect(screen.queryByText(/Legalább 2 karakter/)).toBeNull();
  });

  it('az elavult kérés megszakad (signal.aborted), a válasza nem látszik', async () => {
    const { context } = kornyezet();
    const jelek: AbortSignal[] = [];
    vi.stubGlobal('fetch', (url: string, o: RequestInit) => {
      jelek.push(o.signal as AbortSignal);
      const q = new URL(url, 'http://127.0.0.1/').searchParams.get('q') ?? '';
      if (q === 'lassu') return new Promise<Response>((_, rej) => o.signal?.addEventListener('abort', () => rej(new DOMException('x', 'AbortError'))));
      return Promise.resolve(valasz({ ...VALASZ, q, osszes: 1, talalatok: [VALASZ.talalatok[1]] }));
    });
    render(Kereses, { context });
    vaultKereses.beallit('lassu', true);
    await waitFor(() => expect(jelek.length).toBe(1));
    vaultKereses.beallit('gyors', true);
    expect(await screen.findByText('1 találó fájl')).toBeTruthy();
    expect(jelek[0].aborted).toBe(true);
    expect(vaultKereses.hiba).toBeNull();
  });

  it('a részeredmény „legalább N” jelzést kap', async () => {
    const { context } = kornyezet();
    valaszol = (q) => valasz({ q, osszes: 2, legalabb: true, talalatok: VALASZ.talalatok });
    render(Kereses, { context });
    vaultKereses.beallit('gyakori', true);
    expect(await screen.findByText('legalább 2 találó fájl')).toBeTruthy();
  });

  it('nincs találat: érthető állapotfelirat', async () => {
    const { context } = kornyezet();
    valaszol = (q) => valasz({ q, osszes: 0, talalatok: [] });
    render(Kereses, { context });
    vaultKereses.beallit('semmi', true);
    expect(await screen.findByText('Nincs találat: „semmi”.')).toBeTruthy();
  });

  it('a túl sok találat jelzi, hogy csak az első látszik', async () => {
    const { context } = kornyezet();
    valaszol = (q) => valasz({ q, osszes: 350, talalatok: VALASZ.talalatok });
    render(Kereses, { context });
    vaultKereses.beallit('gyakori', true);
    expect(await screen.findByText(/350 találó fájl \(az első 200 látszik/)).toBeTruthy();
  });
});

describe('hibák: a core magyar üzenete szó szerint', () => {
  it('hibás lekérdezés (400)', async () => {
    const { context } = kornyezet();
    valaszol = () => valasz({ hiba: 'hiányzó záró zárójel' }, 400);
    render(Kereses, { context });
    vaultKereses.beallit('(a OR b', true);
    expect((await screen.findByRole('alert')).textContent).toBe('hiányzó záró zárójel');
    expect(opciok).toThrow(); // nincs találatlista
  });

  it('regex-időtúllépés (400): az egyszerűsítést kérő üzenet', async () => {
    const { context } = kornyezet();
    const uzenet = 'A regex túl sokáig futott (2 s alatt nem végzett) — egyszerűsítsd a mintát (pl. az egymásba ágyazott ismétlést, mint az „(a|aa)+”).';
    valaszol = () => valasz({ hiba: uzenet }, 400);
    render(Kereses, { context });
    vaultKereses.beallit('/(a|aa)+$/', true);
    expect((await screen.findByRole('alert')).textContent).toBe(uzenet);
  });

  it('a hiba a következő sikeres keresésre eltűnik', async () => {
    const { context } = kornyezet();
    valaszol = (q) => (q === 'rossz(' ? valasz({ hiba: 'fölösleges záró zárójel' }, 400) : valasz(VALASZ));
    render(Kereses, { context });
    vaultKereses.beallit('rossz(', true);
    await screen.findByRole('alert');
    vaultKereses.beallit('jo', true);
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
    expect(await screen.findByText('2 találó fájl')).toBeTruthy();
  });

  it('az index még épül (503): felirat; az `index` esemény után újrafut', async () => {
    const { context, kapcsolat } = kornyezet();
    let kesz = false;
    valaszol = () => (kesz ? valasz(VALASZ) : valasz({ hiba: 'az index még épül' }, 503));
    render(Kereses, { context });
    vaultKereses.beallit('sorozat', true);
    expect(await screen.findByText(/Az index még épül/)).toBeTruthy();
    kesz = true;
    kapcsolat.szetoszt({ tipus: 'index', kesz: true });
    expect(await screen.findByText('2 találó fájl')).toBeTruthy();
  });

  it('a core nem válaszol (hálózati hiba)', async () => {
    const { context } = kornyezet();
    vi.stubGlobal('fetch', async () => {
      throw new TypeError('Load failed');
    });
    render(Kereses, { context });
    vaultKereses.beallit('xx', true);
    expect((await screen.findByRole('alert')).textContent).toContain('A core nem válaszol');
  });
});

describe('találatok', () => {
  async function talalatokkal() {
    const k = kornyezet();
    k.felulet.atfedes = 'kereso';
    render(Kereses, { context: k.context });
    vaultKereses.beallit('sorozat', true);
    await screen.findByText('2 találó fájl');
    return k;
  }

  it('fájlonként kártya: név kiemeléssel, egyezésszám, mappa-út, kivágás sorok kiemeléssel és sorszámmal', async () => {
    await talalatokkal();
    const o = opciok();
    expect(o).toHaveLength(5); // 2 kártyafejléc + 3 kivágás
    expect(o[0].textContent).toContain('04 - Mértani sorozat');
    expect(o[0].querySelector('mark')!.textContent).toBe('sorozat'); // a név kiemelése
    expect(o[0].querySelector('.db')!.textContent).toBe('2 egyezés');
    expect(screen.getAllByRole('group')[0].querySelector('.mappa')!.textContent).toBe('Matek/Sorozatok');
    expect(o[1].querySelector('mark')!.textContent).toBe('sorozat');
    expect(o[1].querySelector('.sorszam')!.textContent).toBe('5');
    expect(o[3].textContent).toContain('Newton');
  });

  it('egy kártyán legfeljebb négy kivágás, a többit „+N további sor” jelzi', async () => {
    const { context } = kornyezet();
    const sok = Array.from({ length: 7 }, (_, i) => ({ sor: i + 1, oszlop: 0, hossz: 2, szoveg: `ab sor ${i}` }));
    valaszol = (q) => valasz({ q, osszes: 1, talalatok: [{ ut: 'A.md', pont: 1, talalatok: sok }] });
    render(Kereses, { context });
    vaultKereses.beallit('ab', true);
    await screen.findByText('1 találó fájl');
    expect(opciok()).toHaveLength(5); // fejléc + 4 kivágás
    expect(screen.getByText('+3 további sor')).toBeTruthy();
    expect(screen.getByText('7 egyezés')).toBeTruthy();
  });

  it('a kattintás megnyitja a fájlt és a sorra ugrik; az oszlop kódpontból UTF-16 lesz; bezár', async () => {
    const { felulet } = await talalatokkal();
    const ugras = vi.spyOn(szerkesztok, 'ugras').mockImplementation(() => {});
    await fireEvent.click(opciok()[1]);
    expect(felulet.atfedes).toBeNull();
    expect(felulet.munkaterulet.aktivFul?.ut).toBe('Matek/Sorozatok/04 - Mértani sorozat.md');
    expect(ugras).toHaveBeenLastCalledWith('Matek/Sorozatok/04 - Mértani sorozat.md', 5, 10);
    await fireEvent.click(opciok()[2]);
    expect(ugras).toHaveBeenLastCalledWith('Matek/Sorozatok/04 - Mértani sorozat.md', 9, 6); // a 😀 két UTF-16 egység
    expect(utf16Oszlop('😀 a', 3)).toBe(4);
  });

  it('billentyűzet: a fókusz a mezőben marad; ↑↓ kártya és kivágás közt lép (körbe), ↵ az adott találatra ugrik', async () => {
    await talalatokkal();
    const ugras = vi.spyOn(szerkesztok, 'ugras').mockImplementation(() => {});
    const m = mezo();
    expect(m.getAttribute('aria-controls')).toBe(screen.getByRole('listbox').id);
    expect(m.getAttribute('aria-activedescendant')).toBe(opciok()[0].id);
    await fireEvent.keyDown(m, { key: 'ArrowDown' });
    expect(opciok()[1].getAttribute('aria-selected')).toBe('true');
    expect(m.getAttribute('aria-activedescendant')).toBe(opciok()[1].id);
    await fireEvent.keyDown(m, { key: 'ArrowUp' });
    await fireEvent.keyDown(m, { key: 'ArrowUp' });
    expect(opciok()[4].getAttribute('aria-selected')).toBe('true'); // körbe
    await fireEvent.keyDown(m, { key: 'ArrowDown' });
    expect(opciok()[0].getAttribute('aria-selected')).toBe('true');
    await fireEvent.keyDown(m, { key: 'ArrowDown' });
    await fireEvent.keyDown(m, { key: 'ArrowDown' });
    await fireEvent.keyDown(m, { key: 'Enter' });
    expect(ugras).toHaveBeenLastCalledWith('Matek/Sorozatok/04 - Mértani sorozat.md', 9, 6);
  });

  it('a kártya fejlécén a ↵ az első egyezésre ugrik; ⌘↵ új fülben, ⌥⌘↵ osztásban', async () => {
    const { felulet } = await talalatokkal();
    const ugras = vi.spyOn(szerkesztok, 'ugras').mockImplementation(() => {});
    const megnyit = vi.spyOn(felulet.munkaterulet, 'megnyit');
    const m = mezo();
    const UT = 'Matek/Sorozatok/04 - Mértani sorozat.md';
    await fireEvent.keyDown(m, { key: 'Enter' });
    expect(ugras).toHaveBeenLastCalledWith(UT, 5, 10);
    expect(megnyit).toHaveBeenLastCalledWith(UT, 'aktiv');
    for (const [mod, jel] of [[{ metaKey: true }, 'ujful'], [{ metaKey: true, altKey: true }, 'osztas']] as const) {
      felulet.atfedes = 'kereso';
      await fireEvent.keyDown(m, { key: 'Enter', ...mod });
      expect(megnyit).toHaveBeenLastCalledWith(UT, jel);
    }
  });

  it('⌘G a kivágásokat ki-be kapcsolja; az állapot tartós (a felület mentésében)', async () => {
    const { felulet } = await talalatokkal();
    expect(opciok()).toHaveLength(5);
    await fireEvent.keyDown(mezo(), { key: 'g', metaKey: true });
    expect(felulet.kereso.kivagasok).toBe(false);
    expect(opciok()).toHaveLength(2);
    expect(felulet.sorosit().kereso).toEqual({ kivagasok: false });
    expect(new Felulet(JSON.parse(JSON.stringify(felulet.sorosit()))).kereso.kivagasok).toBe(false);
    await fireEvent.keyDown(mezo(), { key: 'g', metaKey: true });
    expect(opciok()).toHaveLength(5);
  });

  it('Esc bezár, és a fókusz a megnyitóra tér vissza', async () => {
    const gomb = document.createElement('button');
    document.body.append(gomb);
    gomb.focus();
    const k = kornyezet();
    k.felulet.atfedes = 'kereso';
    const r = render(Kereses, { context: k.context });
    expect(document.activeElement).toBe(mezo());
    await fireEvent.keyDown(mezo(), { key: 'Escape' });
    expect(k.felulet.atfedes).toBeNull();
    r.unmount();
    await waitFor(() => expect(document.activeElement).toBe(gomb));
    gomb.remove();
  });

  it('⌥↵: a találatra mutató link az aktív szerkesztő kurzorához kerül (a cél a core linkcel-jéből)', async () => {
    const { felulet } = await talalatokkal();
    let doc = 'x ';
    const dispatch = vi.fn((tr: unknown) => tr);
    const nezet = {
      dispatch,
      focus: vi.fn(),
      state: { replaceSelection: (t: string) => ({ changes: { from: doc.length, insert: t } }), update: (...a: unknown[]) => ({ a }) },
    };
    const peldany = { ut: 'Fizika/Newton.md', nezet: () => nezet, mod: () => 'elo' } as never;
    szerkesztok.beallit(peldany);
    valaszol = (q) => (q === 'sorozat' ? valasz(VALASZ) : valasz({}));
    vi.stubGlobal('fetch', async (url: string) => {
      const u = new URL(url, 'http://127.0.0.1/');
      kerelmek.push(u.pathname + u.search);
      if (u.pathname === '/api/vault/linkcel') return valasz({ cel: '04 - Mértani sorozat' });
      return valaszol(u.searchParams.get('q') ?? '');
    });
    await fireEvent.keyDown(mezo(), { key: 'Enter', altKey: true });
    await waitFor(() => expect(dispatch).toHaveBeenCalled());
    expect(kerelmek.some((k) => k.startsWith('/api/vault/linkcel?ut=Matek%2FSorozatok%2F04'))).toBe(true);
    expect(JSON.stringify(dispatch.mock.calls[0][0])).toContain('[[04 - Mértani sorozat]]');
    expect(felulet.atfedes).toBeNull();
    szerkesztok.megszunt(peldany);
    doc = '';
  });

  it('nyitott szerkesztő nélkül a ⌥↵ figyelmeztet, az ablak nyitva marad', async () => {
    const { felulet } = await talalatokkal();
    await fireEvent.keyDown(mezo(), { key: 'Enter', altKey: true });
    expect(felulet.atfedes).toBe('kereso');
  });

  it('a Tab bezár és a jegyzeten belüli keresésre vált (a kártya jegyzetét megnyitja)', async () => {
    const { felulet } = await talalatokkal();
    await fireEvent.keyDown(mezo(), { key: 'Tab' });
    expect(felulet.atfedes).toBeNull();
    expect(felulet.munkaterulet.aktivFul?.ut).toBe('Matek/Sorozatok/04 - Mértani sorozat.md');
  });

  it('a 200 találat is fokozatosan rajzolódik (30 kártya elsőre), és a lépkedés többet rajzol', async () => {
    const { context } = kornyezet();
    const sok = Array.from({ length: 200 }, (_, i) => ({ ut: `M/J${i}.md`, pont: 1, talalatok: [{ sor: 1, oszlop: 0, hossz: 2, szoveg: 'ab' }] }));
    valaszol = (q) => valasz({ q, osszes: 200, talalatok: sok });
    render(Kereses, { context });
    vaultKereses.beallit('ab', true);
    await screen.findByText(/200 találó fájl/);
    expect(screen.getAllByRole('group')).toHaveLength(30);
    for (let i = 0; i < 61; i++) await fireEvent.keyDown(mezo(), { key: 'ArrowDown' });
    expect(screen.getAllByRole('group').length).toBeGreaterThan(30);
    expect(screen.getAllByRole('group').length).toBeLessThan(200);
  });
});

describe('a lekérdezés szavai (kiemelés)', () => {
  it('a kiemelendő szavak: az operátorok, a tagadás, a tag:, a line:, a regex kimarad; a path:/file: értéke marad', () => {
    expect(keresoSzavak('romantika "angol költők" -ne OR (a b) tag:#x path:Irodalom /re.x/ file:Byron line:(a b)')).toEqual(['romantika', 'angol költők', 'a', 'b', 'Irodalom', 'Byron']);
  });

  it('ékezet- és kis-nagybetű-független kiemelés, a hossz megmarad', () => {
    expect(szoKiemeles('Az ÉSZ és a esz', ['esz']).map((d) => (d.jelolt ? `[${d.t}]` : d.t)).join('')).toBe('Az [ÉSZ] és a [esz]');
    expect(szoKiemeles('semmi', ['x'])).toEqual([{ t: 'semmi', jelolt: false }]);
  });
});

describe('⌘⇧F', () => {
  it('a parancs megnyitja az ablakot, a mezőre fókuszál; újra leütve zár; nincs billentyű-ütközés', async () => {
    const { felulet, context } = kornyezet();
    const reg = new Regiszter();
    alapParancsok(reg, felulet);
    const p = reg.lista().find((x) => x.id === 'kereses.panel')!;
    expect(p.billentyu).toBe('Mod+Shift+f');
    expect(reg.lista().filter((x) => x.billentyu === 'Mod+Shift+f')).toHaveLength(1);
    p.futtat();
    expect(felulet.atfedes).toBe('kereso');
    render(Kereses, { context });
    await waitFor(() => expect(document.activeElement).toBe(mezo()));
    p.futtat();
    expect(felulet.atfedes).toBeNull();
  });

  it('az aktív szerkesztő kijelölése a kezdő keresőszöveg (egysoros); többsoros kijelölés nem', async () => {
    const { felulet } = kornyezet();
    let kijeloles = 'mértani';
    const nezet = { state: { selection: { main: { empty: false, from: 0, to: 1 } }, sliceDoc: () => kijeloles } };
    const peldany = { ut: 'A.md', nezet: () => nezet, mod: () => 'elo' } as never;
    szerkesztok.beallit(peldany);
    const reg = new Regiszter();
    alapParancsok(reg, felulet);
    vaultKereses.beallit('regi', true);
    reg.lista().find((x) => x.id === 'kereses.panel')!.futtat();
    expect(vaultKereses.q).toBe('mértani');
    felulet.atfedes = null;
    kijeloles = 'két\nsor';
    reg.lista().find((x) => x.id === 'kereses.panel')!.futtat();
    expect(vaultKereses.q).toBe('mértani'); // az előző lekérdezés marad
    szerkesztok.megszunt(peldany);
  });

  it('a „Keresés ebben a mappában” előtöltött lekérdezése azonnal fut', async () => {
    const { felulet, context } = kornyezet();
    render(Kereses, { context });
    keresoMegnyit(felulet, 'path:"Matek/" ');
    expect(felulet.atfedes).toBe('kereso');
    await waitFor(() => expect(kerelmek.length).toBe(1));
    expect(decodeURIComponent(kerelmek[0])).toContain('q=path:"Matek/"');
    expect((mezo() as HTMLInputElement).value).toBe('path:"Matek/" ');
  });

  it('a „kereses” oldalsáv-nézet tartósan visszatérhet', () => {
    expect(new Felulet({ oldalsav: { szelesseg: 264, nyitva: true, nezet: 'kereses' } }).oldalsav.nezet).toBe('kereses');
  });
});

describe('az egyezések sorokra egyesítve', () => {
  const fajl = {
    ut: 'A.md',
    pont: 1,
    talalatok: [
      { sor: 3, oszlop: 23, hossz: 3, szoveg: 'Az erő és a gyorsulás: erő', elotte: ['x'], utana: ['y'] },
      { sor: 3, oszlop: 3, hossz: 3, szoveg: 'Az erő és a gyorsulás: erő' },
      { sor: 7, oszlop: 0, hossz: 2, szoveg: 'ab' },
    ],
  };

  it('az azonos sor egyezései egy sor, oszlop szerint rendezett kiemelésekkel; az ugrás az elsőre megy', () => {
    const sorok = sorokraEgyesit(fajl);
    expect(sorok.map((s) => [s.sor, s.oszlop, s.jelek.length])).toEqual([[3, 3, 2], [7, 0, 1]]);
    expect(sorok[0].elotte).toEqual(['x']);
  });

  it('a kiemelés darabjai: a találat körüli ablak, több kiemelés, a kezdő „…” ha vágtunk', () => {
    const [s] = sorokraEgyesit({ ut: 'B.md', pont: 0, talalatok: [{ sor: 1, oszlop: 7, hossz: 3, szoveg: 'előtte erő után erő vége' }, { sor: 1, oszlop: 16, hossz: 3, szoveg: 'előtte erő után erő vége' }] });
    expect(darabok(s).map((d) => (d.jelolt ? `[${d.t}]` : d.t)).join('')).toBe('előtte [erő] után [erő] vége');
    const hosszu = 'x'.repeat(60) + ' találat ' + 'y'.repeat(200);
    const [h] = sorokraEgyesit({ ut: 'C.md', pont: 0, talalatok: [{ sor: 1, oszlop: 61, hossz: 7, szoveg: hosszu }] });
    const d = darabok(h);
    expect(d[0].t.startsWith('… ')).toBe(true);
    expect(d.find((x) => x.jelolt)!.t).toBe('találat');
    expect(Array.from(d.map((x) => x.t).join('')).length).toBeLessThan(150);
  });

  it('a kártyán egy sor egy kivágás, két kiemeléssel', async () => {
    const { context } = kornyezet();
    valaszol = (q) => valasz({ q, osszes: 1, talalatok: [fajl] });
    render(Kereses, { context });
    vaultKereses.beallit('erő', true);
    await screen.findByText('1 találó fájl');
    const o = opciok();
    expect(o).toHaveLength(3); // fejléc + 2 sor (a 3. sor két egyezése egyben)
    expect([...o[1].querySelectorAll('mark')].map((m) => m.textContent)).toEqual(['erő', 'erő']);
  });
});
