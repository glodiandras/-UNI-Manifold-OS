// F7 Health: a jelentés sorai, Diagnose / Fix / Learn more, a biztonságos gépi javítás folyama és a hibaágak.
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Egeszseg from '../src/egeszseg/Egeszseg.svelte';
import { beallitasok } from '../src/lib/beallitasok/allapot.svelte';
import { alapBeallitasok } from '../src/lib/beallitasok/tipusok';
import { ApiHiba } from '../src/lib/core/api';
import { egeszsegApi } from '../src/lib/egeszseg/api';
import { EgeszsegTar, egeszsegMegnyit, egeszsegAblak } from '../src/lib/egeszseg/allapot.svelte';
import { CIM, JAVITAS_KEZI, JAVITAS_LEIRAS, TUDJ_MEG } from '../src/lib/egeszseg/szoveg';
import type { EgeszsegJelentes, EgeszsegSor } from '../src/lib/egeszseg/tipusok';
import { szotarFajlok, nyelv } from '../src/lib/i18n';

const sor = (kod: string, allapot: EgeszsegSor['allapot'], uzenet: string, extra: Partial<EgeszsegSor> = {}): EgeszsegSor =>
  ({ kod, cim: kod, allapot, uzenet_kod: `${kod}.x`, param: {}, uzenet, javitas: null, reszletek: [], ...extra });
const jelentes = (sorok: EgeszsegSor[]): EgeszsegJelentes => {
  const osszesen = { ok: 0, info: 0, figyelem: 0, hiba: 0 };
  sorok.forEach((s) => (osszesen[s.allapot] += 1));
  return { verzio: 1, zold: !osszesen.hiba && !osszesen.figyelem, osszesen, ellenorzesek: sorok };
};
const ALAP = () => [
  sor('index', 'figyelem', 'The search index cannot be read.', { javitas: 'index_ujraepit', reszletek: [{ kulcs: 'fajl', ertek: 'vault.sqlite' }, { kulcs: 'titkos_kulcs', ertek: 'x' }] }),
  sor('lemezhely', 'ok', 'There is enough free disk space.', { reszletek: [{ kulcs: 'workspace_szabad_gb', ertek: 71.1 }] }),
  sor('modellek', 'info', 'No AI models are installed.'),
  sor('munkater', 'hiba', 'The workspace settings file is missing or damaged.', { nyers: 'RAW doctor text' }),
];
let tar: EgeszsegTar;

function fejlesztoMod(be: boolean) {
  const ertek = alapBeallitasok();
  ertek.fejleszto.mod = be;
  beallitasok.fogad({ verzio: 1, rev: 'r', ertek, munkater: { id: 'x', nev: 'X', vault: '/v' }, setup_szukseges: false, ujrainditas: [] });
}
async function megnyit(sorok = ALAP(), props: Record<string, unknown> = {}) {
  vi.spyOn(egeszsegApi, 'betolt').mockResolvedValue(jelentes(sorok));
  tar = new EgeszsegTar();
  render(Egeszseg, { props: { tar, onbezar: vi.fn(), ...props } });
  await waitFor(() => expect(tar.adat).not.toBeNull());
}
const sorElem = (kod: string) => document.querySelector<HTMLElement>(`[data-ellenorzes="${kod}"]`)!;

beforeEach(() => { nyelv.beallit('en'); fejlesztoMod(false); });
afterEach(() => { cleanup(); beallitasok.adat = null; vi.restoreAllMocks(); egeszsegAblak.nyitva = false; nyelv.beallit('hu'); });

describe('a Health oldal', () => {
  it('minden sor ikonnal ÉS szóval jelzi az állapotát, az összegzés a legrosszabbat mondja', async () => {
    await megnyit();
    expect(screen.getByText('A problem needs your attention.')).toBeTruthy();
    const szavak = { index: 'Needs attention', lemezhely: 'Healthy', modellek: 'Note', munkater: 'Problem' };
    for (const [kod, szo] of Object.entries(szavak)) {
      const s = sorElem(kod);
      expect(within(s).getByText(szo)).toBeTruthy();
      expect(s.querySelector('svg')).toBeTruthy();
    }
    expect(within(sorElem('index')).getByText('Search index')).toBeTruthy();          // a cím a szótárból
    expect(within(sorElem('index')).getByText('The search index cannot be read.')).toBeTruthy();
  });

  it('csupa zöldnél „Everything looks healthy.”', async () => {
    await megnyit([sor('index', 'ok', 'Fine.'), sor('zarak', 'ok', 'No locks.')]);
    expect(screen.getByText('Everything looks healthy.')).toBeTruthy();
  });

  it('Diagnose: újrafuttatja az egy ellenőrzést; csak az ismert kulcsok címkéi látszanak, az ismeretlen kulcs nem', async () => {
    await megnyit();
    const diag = vi.spyOn(egeszsegApi, 'diagnosztika').mockResolvedValue({ verzio: 1, ellenorzesek: [sor('index', 'figyelem', 'The search index cannot be read.', { javitas: 'index_ujraepit', reszletek: [{ kulcs: 'fajl', ertek: 'vault.sqlite' }, { kulcs: 'sema', ertek: 3 }, { kulcs: 'titkos_kulcs', ertek: 'x' }] })] });
    await fireEvent.click(within(sorElem('index')).getByRole('button', { name: 'Diagnose' }));
    await waitFor(() => expect(within(sorElem('index')).getByText('Index version')).toBeTruthy());
    expect(diag).toHaveBeenCalledWith('index');
    const panel = sorElem('index').querySelector('[data-panel="diagnosztika"]')!;
    expect(panel.textContent).toContain('File');
    expect(panel.textContent).toContain('vault.sqlite');
    expect(panel.textContent).not.toContain('titkos_kulcs');                 // normál módban nincs nyers azonosító
    expect(panel.querySelector('[data-nyers]')).toBeNull();                  // és nincs nyers JSON
    await fireEvent.click(within(sorElem('index')).getByRole('button', { name: 'Diagnose' }));
    expect(sorElem('index').querySelector('[data-panel]')).toBeNull();       // újra kattintva becsukódik
  });

  it('Diagnose Developer módban a nyers JSON-t és a doctor szövegét is mutatja', async () => {
    fejlesztoMod(true);
    await megnyit();
    vi.spyOn(egeszsegApi, 'diagnosztika').mockResolvedValue({ verzio: 1, ellenorzesek: [ALAP()[3]] });
    await fireEvent.click(within(sorElem('munkater')).getByRole('button', { name: 'Diagnose' }));
    const nyers = await waitFor(() => { const e = sorElem('munkater').querySelector('[data-nyers]'); expect(e).toBeTruthy(); return e!; });
    expect(nyers.textContent).toContain('RAW doctor text');
    expect(nyers.textContent).toContain('"uzenet_kod": "munkater.x"');
  });

  it('Fix: a gépi javítás leírja, mit tesz, és csak a gombra fut; a siker után a friss sor kerül a helyére', async () => {
    await megnyit();
    const javit = vi.spyOn(egeszsegApi, 'javit').mockResolvedValue({
      ok: true, javitas: 'index_ujraepit', param: {}, uzenet: 'The search index is being rebuilt. The damaged file was kept aside.',
      ellenorzesek: [sor('index', 'ok', 'The search index is healthy (3 files).')],
    });
    await fireEvent.click(within(sorElem('index')).getByRole('button', { name: 'Fix' }));
    const panel = sorElem('index').querySelector('[data-panel="javitas"]')!;
    expect(within(panel as HTMLElement).getByText('What happened')).toBeTruthy();
    expect(panel.textContent).toContain('kept as a copy');                       // a javítás leírása: mit tesz, mi marad meg
    expect(javit).not.toHaveBeenCalled();                                         // megnyitás nem javít
    await fireEvent.click(within(panel as HTMLElement).getByRole('button', { name: 'Fix automatically' }));
    await waitFor(() => expect(javit).toHaveBeenCalledWith('index_ujraepit'));
    await waitFor(() => expect(sorElem('index').dataset.allapot).toBe('ok'));
    expect(screen.getAllByText('The search index is being rebuilt. The damaged file was kept aside.').length).toBeGreaterThan(0);
    expect(tar.adat!.osszesen).toEqual({ ok: 2, info: 1, figyelem: 0, hiba: 1 });
  });

  it('gépi javítás nélküli problémánál kézi lépés van, „Fix automatically” nincs', async () => {
    await megnyit();
    await fireEvent.click(within(sorElem('munkater')).getByRole('button', { name: 'Fix' }));
    const panel = sorElem('munkater').querySelector('[data-panel="javitas"]') as HTMLElement;
    expect(within(panel).queryByRole('button', { name: 'Fix automatically' })).toBeNull();
    expect(panel.textContent).toContain('Reconnect the drive');
    expect(within(panel).getByRole('button', { name: 'Open diagnostics' })).toBeTruthy();
  });

  it('rendben lévő sornál nincs Fix gomb', async () => {
    await megnyit();
    expect(within(sorElem('lemezhely')).queryByRole('button', { name: 'Fix' })).toBeNull();
    expect(within(sorElem('lemezhely')).getByRole('button', { name: 'Learn more' })).toBeTruthy();
  });

  it('a javítás hibája (409) a panelben marad, a sor nem változik', async () => {
    await megnyit();
    vi.spyOn(egeszsegApi, 'javit').mockRejectedValue(new ApiHiba(409, 'There is nothing to fix right now.', { kod: 'egeszseg.nincs_mit_javitani' }));
    await fireEvent.click(within(sorElem('index')).getByRole('button', { name: 'Fix' }));
    await fireEvent.click(within(sorElem('index')).getByRole('button', { name: 'Fix automatically' }));
    await waitFor(() => expect(screen.getAllByRole('alert').some((e) => /nothing to fix/.test(e.textContent ?? ''))).toBe(true));
    expect(sorElem('index').dataset.allapot).toBe('figyelem');
  });

  it('Learn more: mindegyik ellenőrzéshez van magyarázat', async () => {
    await megnyit();
    await fireEvent.click(within(sorElem('lemezhely')).getByRole('button', { name: 'Learn more' }));
    expect(sorElem('lemezhely').querySelector('[data-panel="tudj"]')!.textContent).toMatch(/disk/i);
  });

  it('a core hibája HibaPanel-en jelenik meg újrapróbálással; újrapróbálva betölt', async () => {
    const betolt = vi.spyOn(egeszsegApi, 'betolt').mockRejectedValueOnce(new ApiHiba(503, 'The core is not available.')).mockResolvedValue(jelentes(ALAP()));
    tar = new EgeszsegTar();
    render(Egeszseg, { props: { tar, onbezar: vi.fn() } });
    await waitFor(() => expect(screen.getByText('What happened')).toBeTruthy());
    expect(screen.getByRole('alert').textContent).toBe('The core is not available.');
    await fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(tar.adat).not.toBeNull());
    expect(betolt).toHaveBeenCalledTimes(2);
  });

  it('a megnyitáskor kért ellenőrzés (Open diagnostics) azonnal kinyílik', async () => {
    vi.spyOn(egeszsegApi, 'diagnosztika').mockResolvedValue({ verzio: 1, ellenorzesek: [ALAP()[0]] });
    await megnyit(ALAP(), { kod: 'index' });
    await waitFor(() => expect(sorElem('index').querySelector('[data-panel="diagnosztika"]')).toBeTruthy());
  });

  it('a megnyitó függvény beállítja az ablakot és a kért ellenőrzést', () => {
    egeszsegMegnyit('index');
    expect([egeszsegAblak.nyitva, egeszsegAblak.kod]).toEqual([true, 'index']);
  });
});

describe('a Health szövegei', () => {
  it('minden core-ellenőrzés kódjához van cím, magyarázat és kézi lépés, és minden gépi javításhoz leírás — mind az angol szótárban', () => {
    const en = Object.assign({}, ...Object.entries(szotarFajlok()).filter(([ut]) => ut.startsWith('./en/')).map(([, v]) => v));
    const kodok = ['index', 'pillanatkep', 'zarak', 'lemezhely', 'modellek', 'munkater', 'folyamatok', 'telepites'];
    for (const k of kodok) for (const tabla of [CIM, TUDJ_MEG, JAVITAS_KEZI]) expect(en[tabla[k]], `${k}: ${tabla[k]}`).toBeTruthy();
    for (const j of ['zar_takarit', 'git_zar_takarit', 'regiszter_takarit', 'index_ujraepit', 'gyorsitotar_torles']) expect(en[JAVITAS_LEIRAS[j]], j).toBeTruthy();
  });
});
