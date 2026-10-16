// F7 közös minták: az üres állapot (ikon, cím, magyarázat, művelet) és a hiba-minta („What happened / Fix / [Fix automatically]
// [Open diagnostics]”), valamint bevezetésük a fő nézetekbe és a fő hibahelyekre.
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Info } from '../src/lib/ikon/ikonok';
import { ApiHiba } from '../src/lib/core/api';
import { egeszsegAblak } from '../src/lib/egeszseg/allapot.svelte';
import { nyelv } from '../src/lib/i18n';
import HibaPanel from '../src/lib/ui/HibaPanel.svelte';
import UresAllapot from '../src/lib/ui/UresAllapot.svelte';
import { IsmetlesMenet } from '../src/kartya/menet.svelte';
import Pakli from '../src/kartya/Pakli.svelte';
import { regiszter } from '../src/lib/parancsok/regiszter';
import Most from '../src/hej/vezerlo/Most.svelte';
import { feladatsor } from '../src/lib/vezerlo/feladatsor.svelte';
import JobbPanel from '../src/hej/JobbPanel.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import UjFul from '../src/hej/nezetek/UjFul.svelte';
import Allapotsor from '../src/hej/Allapotsor.svelte';

beforeEach(() => nyelv.beallit('en'));
afterEach(() => {
  cleanup();
  egeszsegAblak.nyitva = false;
  egeszsegAblak.kod = null;
  vi.restoreAllMocks();
  nyelv.beallit('hu');
});

describe('UresAllapot', () => {
  it('ikon, cím, magyarázat és két művelet; a művelet a hívót futtatja', async () => {
    const elso = vi.fn(), masodik = vi.fn();
    const { container } = render(UresAllapot, { props: { ikon: Info, cim: 'Nothing here', leiras: 'Why and what to do.', muvelet: { cimke: 'Do it', onclick: elso }, masodlagos: { cimke: 'Later', onclick: masodik } } });
    expect(container.querySelector('svg')).toBeTruthy();
    expect(screen.getByText('Nothing here')).toBeTruthy();
    expect(screen.getByText('Why and what to do.')).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: 'Do it' }));
    expect(elso).toHaveBeenCalledOnce();
    expect(masodik).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Do it' }).classList.contains('semleges')).toBe(false);
    expect(screen.getByRole('button', { name: 'Later' }).classList.contains('semleges')).toBe(true);
  });

  it('művelet nélkül nincs gomb, ikon nélkül nincs ikon', () => {
    const { container } = render(UresAllapot, { props: { cim: 'Empty' } });
    expect(container.querySelectorAll('button')).toHaveLength(0);
    expect(container.querySelector('svg')).toBeNull();
  });
});

describe('HibaPanel', () => {
  it('a három rész: mi történt, javítás, gombok; a hiba role="alert" és szóval jön', () => {
    render(HibaPanel, { props: { mi: 'The index is damaged.', javitas: 'Rebuild it.', automatikus: async () => 'ok', diagnosztika: vi.fn() } });
    expect(screen.getByText('What happened')).toBeTruthy();
    expect(screen.getByRole('alert').textContent).toBe('The index is damaged.');
    expect(screen.getByText('Fix')).toBeTruthy();
    expect(screen.getByText('Rebuild it.')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Fix automatically' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Open diagnostics' })).toBeTruthy();
  });

  it('gépi javítás nélkül nincs „Fix automatically”; semmi nincs a gombok nélkül', () => {
    const { container } = render(HibaPanel, { props: { mi: 'Broken.', javitas: 'Restart.' } });
    expect(screen.queryByRole('button', { name: 'Fix automatically' })).toBeNull();
    expect(container.querySelectorAll('button')).toHaveLength(0);
  });

  it('a javítás futása alatt tiltott (nem fut kétszer), utána az eredmény státusz', async () => {
    let kesz!: (v: string) => void;
    const automatikus = vi.fn(() => new Promise<string>((r) => (kesz = r)));
    render(HibaPanel, { props: { mi: 'Broken.', automatikus } });
    const gomb = screen.getByRole('button', { name: 'Fix automatically' }) as HTMLButtonElement;
    await fireEvent.click(gomb);
    await fireEvent.click(gomb);
    expect(automatikus).toHaveBeenCalledOnce();
    expect(gomb.disabled).toBe(true);
    expect(screen.getByRole('status').textContent).toBe('Fixing…');
    kesz('Fixed it.');
    await waitFor(() => expect(screen.getByText('Fixed it.')).toBeTruthy());
    expect(gomb.disabled).toBe(false);
  });

  it('a javítás hibája a panelben marad, ikonnal és szóval (role="alert")', async () => {
    render(HibaPanel, { props: { mi: 'Broken.', automatikus: async () => { throw new ApiHiba(409, 'There is nothing to fix right now.'); } } });
    await fireEvent.click(screen.getByRole('button', { name: 'Fix automatically' }));
    await waitFor(() => expect(screen.getAllByRole('alert')).toHaveLength(2));
    expect(screen.getAllByRole('alert')[1].textContent).toBe('There is nothing to fix right now.');
    expect(screen.getAllByRole('alert').every((e) => e.classList.contains('hiba'))).toBe(true);   // az alap.css ezekre rajzolja az ikont
  });

  it('a Try again és az Open diagnostics a hívót futtatja', async () => {
    const ujra = vi.fn(), diag = vi.fn();
    render(HibaPanel, { props: { mi: 'x', ujra, diagnosztika: diag } });
    await fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await fireEvent.click(screen.getByRole('button', { name: 'Open diagnostics' }));
    expect([ujra.mock.calls.length, diag.mock.calls.length]).toEqual([1, 1]);
  });
});

describe('bevezetés a fő nézetekbe', () => {
  it('Pakli: ha egyáltalán nincs kártya, az üres állapot a „Kártyák ebből” műveletet kínálja', async () => {
    const m = new IsmetlesMenet({ tipus: 'mai' }, {} as never);
    m.fazis = 'ures';
    const futtat = vi.spyOn(regiszter, 'futtat').mockImplementation(() => undefined as never);
    const { container } = render(Pakli, { props: { menet: m } });
    expect(container.querySelector('[data-ures]')).toBeTruthy();
    expect(container.textContent).toContain('No cards due today');
    await fireEvent.click(screen.getByRole('button', { name: 'Make cards from this note' }));
    expect(futtat).toHaveBeenCalledWith('kartya.ebbol', 'gomb');
  });

  it('Pakli: ha vannak kártyák, de ma nincs esedékes, marad a rövid sor', () => {
    const m = new IsmetlesMenet({ tipus: 'mai' }, {} as never);
    m.fazis = 'ures';
    m.osszes = 12;
    const { container } = render(Pakli, { props: { menet: m } });
    expect(container.querySelector('[data-ures]')).toBeNull();
    expect(container.textContent).toContain('12');
  });

  it('Most: üres feladatsor — cím, magyarázat és a videó-hozzáadás művelete', async () => {
    feladatsor.betoltve = true;
    feladatsor.hiba = null;
    feladatsor.lista = [];
    const futtat = vi.spyOn(regiszter, 'futtat').mockImplementation(() => undefined as never);
    const { container } = render(Most, { props: { onnyit: () => {} } });
    expect(container.querySelector('[data-ures]')).toBeTruthy();
    expect(screen.getByText('Nothing is running')).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: 'Add a video from a link' }));
    expect(futtat).toHaveBeenCalledWith('video.link', 'gomb');
  });
});

describe('bevezetés: jobb panel, új fül, hibahelyek', () => {
  it('jobb panel megnyitott fájl nélkül: üres állapot, a gyorsváltó megnyitásával', async () => {
    const felulet = new Felulet({ csend: { be: false } });
    const context = new Map<unknown, unknown>([[KORNYEZET_KULCS, { felulet, fajlok: new VaultFajlok(), kapcsolat: new CoreKapcsolat('ws://127.0.0.1:1/ws') }]]);
    const futtat = vi.spyOn(regiszter, 'futtat').mockImplementation(() => undefined as never);
    const { container } = render(JobbPanel, { context });
    expect(container.querySelector('[data-ures]')).toBeTruthy();
    expect(container.textContent).toContain('No file is open');
    await fireEvent.click(screen.getByRole('button', { name: 'Open a note' }));
    expect(futtat).toHaveBeenCalledWith('hej.valto', 'gomb');
  });

  it('új fül: minden lehetőség művelet (gomb), nincs zsákutca', () => {
    render(UjFul, { props: {} as never });
    expect(screen.getAllByRole('button').length).toBeGreaterThanOrEqual(4);
  });

  it('Most: a feladatsor hibája HibaPanel, az „Open diagnostics” a Health oldalt nyitja a háttérszolgáltatás ellenőrzésével', async () => {
    feladatsor.betoltve = true;
    feladatsor.lista = [];
    feladatsor.hiba = 'connection refused';
    render(Most, { props: { onnyit: () => {} } });
    expect(screen.getByText('What happened')).toBeTruthy();
    expect(screen.getByRole('alert').textContent).toContain('connection refused');
    await fireEvent.click(screen.getByRole('button', { name: 'Open diagnostics' }));
    expect([egeszsegAblak.nyitva, egeszsegAblak.kod]).toEqual([true, 'folyamatok']);
    feladatsor.hiba = null;
  });

  it('állapotsor: az index hibája gombként az index diagnosztikáját nyitja (a jelző csendes módban sem rejtett)', async () => {
    const fajlok = new VaultFajlok();
    fajlok.index = { kesz: false, hiba: 'database disk image is malformed' } as never;
    const felulet = new Felulet({ csend: { be: true } });
    const context = new Map<unknown, unknown>([[KORNYEZET_KULCS, { felulet, fajlok, kapcsolat: new CoreKapcsolat('ws://127.0.0.1:1/ws') }]]);
    const { container } = render(Allapotsor, { context });
    const gomb = container.querySelector<HTMLButtonElement>('[data-index-hiba]')!;
    expect(gomb).toBeTruthy();
    expect(container.querySelector('footer')!.hasAttribute('data-regio-rejtett')).toBe(false);
    await fireEvent.click(gomb);
    expect([egeszsegAblak.nyitva, egeszsegAblak.kod]).toEqual([true, 'index']);
  });
});
