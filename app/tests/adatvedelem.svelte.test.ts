// F7 Privacy Center a Settingsben: a szakaszok a core valós állapotából épülnek (hálózat, tárolt adat, modellek, AI-memória, tracker,
// integrációk, engedélyek), a hiba HibaPanel-en jön, a kapcsolók a Settings piszkozatát szerkesztik, a Developer-csoport pedig csak
// Developer módban létezik.
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import BeallitasokAblak from '../src/beallitasok/Beallitasok.svelte';
import { beallitasokTelepit } from '../src/beallitasok';
import { beallitasAblak, SZAKASZOK, szakaszLathato } from '../src/beallitasok/allapot.svelte';
import { adatvedelem } from '../src/lib/adatvedelem/allapot.svelte';
import { meretSzoveg } from '../src/lib/adatvedelem/megjelenites';
import type { AdatvedelemAllapot } from '../src/lib/adatvedelem/tipusok';
import { BeallitasokTar, beallitasok } from '../src/lib/beallitasok/allapot.svelte';
import { alapBeallitasok, type BeallitasokValasz } from '../src/lib/beallitasok/tipusok';
import { egeszsegAblak } from '../src/lib/egeszseg/allapot.svelte';
import { nyelv } from '../src/lib/i18n';
import { Regiszter } from '../src/lib/parancsok/regiszter';

const allapot = (extra: Partial<AdatvedelemAllapot> = {}): AdatvedelemAllapot => ({
  verzio: 1, mikor: '2026-10-16T10:00:00',
  halozat: {
    offline: true,
    engedett: [{ kod: 'models', elerheto: true }, { kod: 'runtime_tools', elerheto: true }, { kod: 'video_links', elerheto: false }],
    tiltott: ['telemetry', 'background_sync', 'cloud_ai', 'update_ping'],
    utolso_letoltesek: [{ fajta: 'models', nev: 'qwen35_4b', mikor: '2026-10-15T09:30:00', eredmeny: 'ok' }, { fajta: 'video_links', nev: 'www.example.org', mikor: '2026-10-14T08:00:00', eredmeny: 'kesz' }],
  },
  modellek: { telepitve: [{ nev: 'qwen35_4b', repo: 'org/q', feladat: ['szoveg'], allapot: 'kesz', bajt: 2_500_000_000 }], ut: '/data/models', bajt: 2_500_000_000, hiba: null },
  adat: [
    { kod: 'workspace', ut: '/notes', bajt: 123_456, van: true, torolheto: false },
    { kod: 'snapshots', ut: '/data/vault.git', bajt: 9_000_000, van: true, torolheto: false },
    { kod: 'index', ut: '/data/index', bajt: null, van: false, torolheto: true },
    { kod: 'personal', ut: '/data/personal', bajt: 4000, van: true, torolheto: false },
    { kod: 'models', ut: '/data/models', bajt: 2_500_000_000, van: true, torolheto: false },
    { kod: 'backup', ut: '/data/backup', bajt: 1000, van: true, torolheto: false },
    { kod: 'caches', ut: '/data/cache', bajt: 0, van: true, torolheto: true },
    { kod: 'logs', ut: '/data/runs', bajt: 500, van: true, torolheto: false },
  ],
  memoria: { kapcsolo: true, tetelek: { mintak: 2, muveletek: 1, elutasitott: 0, hangolas: 0 }, osszes: 3 },
  tracker: { be: true, ut: '/data/personal/szemelyes.sqlite', bajt: 4096, van: true, tarol: ['active_time', 'command_usage'], nem_tarol: ['note_text'] },
  integraciok: [{ kod: 'calendar', be: true, elerheto: false, utolso: null }, { kod: 'notifications', be: true, elerheto: true, utolso: null }, { kod: 'assistant', be: true, elerheto: true, utolso: null }, { kod: 'tracker', be: true, elerheto: true, utolso: null }],
  engedelyek: { naptar: { kapcsolo: true, esemeny: 'engedelyezve', emlekezteto: 'megtagadva' }, ertesitesek: { kapcsolo: true } },
  ...extra,
});
const valasz = (fejleszto = false): BeallitasokValasz => {
  const ertek = alapBeallitasok();
  ertek.fejleszto.mod = fejleszto;
  return { verzio: 1, rev: 'r1', ertek, munkater: { id: 'synthetic', nev: 'Synthetic workspace', vault: '/synthetic/vault' }, setup_szukseges: false, ujrainditas: [] };
};
let kerelmek: string[];
let adatvedelemValasz: () => Response;
const json = (d: unknown, kod = 200) => new Response(JSON.stringify(d), { status: kod, headers: { 'Content-Type': 'application/json' } });

function nyit(szakasz: string, fejleszto = false) {
  const tar = new BeallitasokTar();
  tar.fogad(valasz(fejleszto));
  beallitasok.fogad(valasz(fejleszto));
  beallitasAblak.szakasz = szakasz as typeof beallitasAblak.szakasz;
  const onbezar = vi.fn(), onrendszer = vi.fn();
  render(BeallitasokAblak, { props: { tar, onbezar, onsetup: vi.fn(), onrendszer } });
  return { tar, onbezar, onrendszer };
}

beforeEach(() => {
  nyelv.beallit('en');
  kerelmek = [];
  adatvedelem.adat = null;
  adatvedelem.hiba = null;
  adatvedelemValasz = () => json(allapot());
  vi.stubGlobal('fetch', async (url: string) => {
    const u = new URL(url, 'http://127.0.0.1/');
    kerelmek.push(u.pathname);
    if (u.pathname === '/api/adatvedelem') return adatvedelemValasz();
    if (u.pathname === '/api/asszisztens/tanult') return json({ kapcsolo: true, mintak: [{ elotte: 'abcdefgh', szoveg: 'ij' }], muveletek: [], hangolas: [], elutasitott: [] });
    if (u.pathname === '/api/rendszer/epites') return json({ ok: true, mag: 'm', reszek: [{ resz: 'felulet', azonosito: 'abc', friss: true }] });
    if (u.pathname === '/api/egeszseg') return json({ verzio: 1, zold: true, osszesen: { ok: 1, info: 0, figyelem: 0, hiba: 0 }, ellenorzesek: [] });
    return json({ hiba: 'nincs' }, 404);
  });
});
afterEach(() => { cleanup(); beallitasok.adat = null; egeszsegAblak.nyitva = false; beallitasAblak.szakasz = 'altalanos'; vi.unstubAllGlobals(); nyelv.beallit('hu'); });

describe('Privacy › Network', () => {
  it('az offline mód a tényleges állapotból, az engedett és a tiltott lista, az utolsó letöltések', async () => {
    nyit('halozat');
    await screen.findByText(/Offline mode is on/);
    const lista = within(document.querySelector('[data-adatvedelem="halozat"]') as HTMLElement);
    expect(lista.getByText('Download AI models')).toBeTruthy();
    expect(lista.getByText(/Download videos from links you give/).textContent).toContain('Turned off');     // a kikapcsolt modul nem „Available”
    expect(lista.getByText('Telemetry and analytics')).toBeTruthy();
    expect(lista.getByText(/Model: qwen35_4b/)).toBeTruthy();
    expect(lista.getByText(/Video: www\.example\.org/)).toBeTruthy();
    expect(kerelmek.filter((k) => k === '/api/adatvedelem')).toHaveLength(1);
  });

  it('nem offline munkamenet: figyelmeztető sor szóval (nem csak szín)', async () => {
    adatvedelemValasz = () => json(allapot({ halozat: { ...allapot().halozat, offline: false } }));
    nyit('halozat');
    const sor = await screen.findByText(/Offline mode is off for this session/);
    expect(sor.closest('[role="status"]')!.querySelector('svg')).toBeTruthy();
  });

  it('nincs letöltés: üres állapot, a Models megnyitása művelettel', async () => {
    adatvedelemValasz = () => json(allapot({ halozat: { ...allapot().halozat, utolso_letoltesek: [] } }));
    const { onrendszer, onbezar } = nyit('halozat');
    await screen.findByText('No downloads yet');
    await fireEvent.click(screen.getByRole('button', { name: 'Open Models' }));
    expect(onbezar).toHaveBeenCalled();
    expect(onrendszer).toHaveBeenCalledWith('modellek');
  });

  it('a core hibája HibaPanel: mi történt, javítás, újrapróbálás; az újrapróbálás betölt', async () => {
    adatvedelemValasz = () => json({ hiba: 'The core is not available.' }, 503);
    nyit('halozat');
    await screen.findByText('What happened');
    expect(screen.getByRole('button', { name: 'Open diagnostics' })).toBeTruthy();
    adatvedelemValasz = () => json(allapot());
    await fireEvent.click(screen.getAllByRole('button', { name: 'Try again' })[0]);
    await screen.findByText(/Offline mode is on/);
  });
});

describe('Privacy › Data és Memory', () => {
  it('a tárolt adat helyei és mérete a core-tól; a modellek mérettel; az AI-memória darabszáma', async () => {
    nyit('adatok');
    await screen.findByText('Where your data lives');
    const hely = (kod: string) => document.querySelector<HTMLElement>(`[data-hely="${kod}"]`)!;
    expect(hely('workspace').textContent).toContain('123.5 KB');
    expect(hely('workspace').textContent).toContain('/notes');
    expect(hely('index').textContent).toContain('Not created yet');
    expect(hely('models').textContent).toContain('2.5 GB');
    expect(screen.getByText('qwen35_4b')).toBeTruthy();
    expect(screen.getByText(/3 learned items stored on this Mac/)).toBeTruthy();
  });

  it('modell nélkül üres állapot CTA-val', async () => {
    adatvedelemValasz = () => json(allapot({ modellek: { telepitve: [], ut: '/m', bajt: 0, hiba: null } }));
    nyit('adatok');
    await screen.findByText('No models installed');
    expect(screen.getByRole('button', { name: 'Open Models' })).toBeTruthy();
  });

  it('a „Manage AI memory” az AI › Memory szakaszra visz, ahol a tanult tételek törölhetők', async () => {
    nyit('adatok');
    await fireEvent.click(await screen.findByRole('button', { name: 'Manage AI memory' }));
    await screen.findByText(/The assistant is learning on this Mac/);
    expect(screen.getByRole('heading', { name: 'Memory' })).toBeTruthy();
    await screen.findByText('Accepted text continuations');                      // a meglévő tanult-lista (törlés tételenként)
    expect(screen.getByRole('button', { name: /Delete the text pattern: abcdefgh/ })).toBeTruthy();
  });
});

describe('Privacy › Telemetry, Integrations, Permissions', () => {
  it('a tracker: mit tárol és mit soha, hol van és mekkora; törlés/export a meglévő kezelővel', async () => {
    nyit('telemetria');
    await screen.findByText(/no remote telemetry/);
    const adat = within(document.querySelector('[data-adatvedelem="telemetria"]') as HTMLElement);
    expect(adat.getByText(/Active time, Command usage/)).toBeTruthy();
    expect(adat.getByText('Note text')).toBeTruthy();                              // a „soha nem tárolt” listában
    expect(adat.getByText(/szemelyes\.sqlite \(4\.1 KB\)/)).toBeTruthy();
    expect(adat.getByRole('button', { name: 'Delete…' })).toBeTruthy();
  });

  it('a kapcsolók a Settings piszkozatát szerkesztik, a mentés nyomon követi', async () => {
    nyit('integraciok');
    const naptar = await screen.findByLabelText('Calendar & Reminders integration') as HTMLInputElement;
    expect(naptar.checked).toBe(false);
    await fireEvent.click(naptar);
    expect(screen.getByText('Unsaved settings changes')).toBeTruthy();
    expect((screen.getByRole('button', { name: 'Save changes' }) as HTMLButtonElement).disabled).toBe(false);
  });

  it('bekapcsolt, de nem elérhető naptár-segéd: hibapanel javítással', async () => {
    nyit('integraciok');
    await screen.findByText(/calendar helper is not available/);
    expect(screen.getByText('What happened')).toBeTruthy();
  });

  it('az engedélyek a core/OS állapotából, szóval', async () => {
    nyit('engedelyek');
    await screen.findByText('Permissions are granted by macOS. Manifold asks only when you use a feature that needs one.');
    expect(document.querySelector('[data-engedely="naptar"]')!.textContent).toBe('Allowed');
  });
});

describe('Developer mód a Settingsben', () => {
  it('normál módban nincs Developer csoport, nincs parancs; a kapcsoló az Advanced information alatt van', async () => {
    nyit('nevjegy');
    expect(screen.queryByText('Developer')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Diagnostics' })).toBeNull();
    expect(SZAKASZOK.filter((s) => !szakaszLathato(s.id, false)).map((s) => s.id)).toEqual(
      ['fejleszto_naplok', 'fejleszto_diagnosztika', 'fejleszto_homokozo', 'fejleszto_modell', 'fejleszto_teszt', 'fejleszto_git', 'fejleszto_import']);
    const reg = new Regiszter();
    beallitasokTelepit(reg);
    expect(reg.mind().filter((p) => p.id.startsWith('beallitasok.fejleszto')).every((p) => !reg.elerheto(p))).toBe(true);
    expect(reg.mind().some((p) => p.id.startsWith('beallitasok.fejleszto'))).toBe(true);
    const kapcsolo = screen.getByLabelText('Developer mode') as HTMLInputElement;     // a <details> zárva is a DOM-ban van
    expect(kapcsolo.checked).toBe(false);
  });

  it('a kapcsoló bekapcsolása piszkozat; mentve (Developer mód) megjelenik a csoport, a diagnosztikában a nyers jelentés', async () => {
    nyit('nevjegy', true);
    expect((screen.getByLabelText('Developer mode') as HTMLInputElement).checked).toBe(true);
    expect(screen.getByText('Developer')).toBeTruthy();                                // a csoportcím
    const reg = new Regiszter();
    beallitasokTelepit(reg);
    expect(reg.mind().filter((p) => p.id.startsWith('beallitasok.fejleszto')).every((p) => reg.elerheto(p))).toBe(true);
    await fireEvent.click(screen.getByRole('button', { name: 'Diagnostics' }));
    await waitFor(() => expect(document.querySelector('[data-fejleszto="fejleszto_diagnosztika"]')).toBeTruthy());
    await waitFor(() => expect(document.querySelector('[data-nyers]')).toBeTruthy());
    expect(document.querySelector('[data-nyers]')!.textContent).toContain('"verzio": 1');
  });

  it('az indító kényszere: a kapcsoló kész, magyarázza, hogy a mentett érték nem változott', async () => {
    const tar = new BeallitasokTar();
    tar.fogad({ ...valasz(true), fejleszto_kenyszer: true });
    beallitasok.fogad({ ...valasz(true), fejleszto_kenyszer: true });
    render(BeallitasokAblak, { props: { tar, onbezar: vi.fn(), onsetup: vi.fn(), onrendszer: vi.fn() } });
    await fireEvent.click(screen.getByRole('button', { name: 'About Manifold' }));
    expect(screen.getByText(/Turned on for this session from the launcher/)).toBeTruthy();
  });

  it('a Developer-szakasz nem nyitható normál módban: a nyitott szakasz a névjegyre esik vissza', () => {
    beallitasAblak.szakasz = 'fejleszto_git';
    nyit('fejleszto_git', false);
    expect(screen.getByRole('heading', { name: 'About Manifold' })).toBeTruthy();
  });
});

describe('Settings › General és a betöltési hiba', () => {
  it('a „Check app health” bezárja a Settingst és megnyitja a Health oldalt', async () => {
    const { onbezar } = nyit('altalanos');
    await fireEvent.click(screen.getByRole('button', { name: 'Check app health' }));
    expect(onbezar).toHaveBeenCalled();
    expect(egeszsegAblak.nyitva).toBe(true);
  });

  it('a Settings nem tölthető be: HibaPanel újrapróbálással és diagnosztikával', async () => {
    const tar = new BeallitasokTar();
    tar.hiba = 'Settings are not available right now. Reconnect or reopen the workspace.';
    vi.spyOn(tar, 'betolt').mockResolvedValue();
    render(BeallitasokAblak, { props: { tar, onbezar: vi.fn(), onsetup: vi.fn(), onrendszer: vi.fn() } });
    expect(screen.getByText('What happened')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Reload settings' })).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: 'Open diagnostics' }));
    expect(egeszsegAblak.nyitva).toBe(true);
    expect(egeszsegAblak.kod).toBe('folyamatok');
  });
});

describe('méret-formázás', () => {
  it('bájt → olvasható', () => {
    expect([meretSzoveg(null), meretSzoveg(0), meretSzoveg(999), meretSzoveg(1500), meretSzoveg(2_500_000), meretSzoveg(3_200_000_000)])
      .toEqual(['–', '0 B', '999 B', '1.5 KB', '2.5 MB', '3.2 GB']);
  });
});
