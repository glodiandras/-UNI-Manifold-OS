// F6 Model Manager (Settings › AI › Models és Calibration): lista és telepítettség, letöltés folyamatjelzővel és megszakítással
// (csak kattintásra), törlés megerősítéssel, „Test this model” (előpróba → mérés → jel), a riport, a saját aranyhalmaz-varázsló,
// az ajánlott modellek telepítése és az AI-hibák megjelenítése. Mockolt API: valós modell vagy hálózat nélkül.
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import BeallitasokAblak from '../src/beallitasok/Beallitasok.svelte';
import { beallitasAblak } from '../src/beallitasok/allapot.svelte';
import { BeallitasokTar, beallitasok } from '../src/lib/beallitasok/allapot.svelte';
import { alapBeallitasok, type BeallitasokValasz } from '../src/lib/beallitasok/tipusok';
import { egeszsegAblak } from '../src/lib/egeszseg/allapot.svelte';
import AiHiba from '../src/modellek/AiHiba.svelte';
import Kalibracio from '../src/modellek/Kalibracio.svelte';
import ModellKezelo from '../src/modellek/ModellKezelo.svelte';
import { ApiHiba, hibaUzenet, kerdez, kodUzenet } from '../src/lib/core/api';
import { nyelv } from '../src/lib/i18n';
import { aiHibaAdat, aiHibaEgysor } from '../src/lib/modellek/aiHiba';
import { modellApi } from '../src/lib/modellek/api';
import { ModellTar, modellek } from '../src/lib/modellek/allapot.svelte';
import type { Halmazok, Modell } from '../src/lib/modellek/tipusok';
import { vezerloApi } from '../src/lib/vezerlo/api';
import { Feladatsor } from '../src/lib/vezerlo/feladatsor.svelte';
import { feladat, halmazok, kal, lista, modell, riport, sajatOsszegzes } from './modellek-fixture';

let lemez: Record<string, Modell>;
let halm: Halmazok;
let fs: Feladatsor;
let tar: ModellTar;
const sorrend = () => Object.values(lemez);

beforeEach(() => {
  nyelv.beallit('en');
  lemez = {};
  halm = halmazok();
  fs = new Feladatsor();
  tar = new ModellTar(fs);
  vi.spyOn(modellApi, 'lista').mockImplementation(async () => lista(sorrend()));
  vi.spyOn(modellApi, 'egy').mockImplementation(async (id) => structuredClone(lemez[id]));
  vi.spyOn(modellApi, 'halmazok').mockImplementation(async () => structuredClone(halm));
  vi.spyOn(modellApi, 'riport').mockRejectedValue(new ApiHiba(404, 'none', { kod: 'modell.nincs_teszt', param: {} }));
  vi.spyOn(vezerloApi, 'feladatok').mockResolvedValue({ feladatok: [] });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); nyelv.beallit('hu'); });

function felvesz(...ms: Modell[]) { for (const m of ms) lemez[m.id] = m; }
async function megnyit(...ms: Modell[]) {
  felvesz(...ms);
  const r = render(ModellKezelo, { props: { tar, oneszeg: vi.fn(), onkalibracio: vi.fn() } });
  await waitFor(() => expect(tar.lista).not.toBeNull());
  await waitFor(() => expect(tar.halmazok).not.toBeNull());
  return r;
}
const sor = (id: string) => document.querySelector<HTMLElement>(`[data-modell="${id}"]`)!;

describe('Model Manager: lista és telepítettség', () => {
  it('shows every install state from the disk, with role, language, licence and sizes', async () => {
    await megnyit(
      modell('uj', { allapot: 'nincs' }),
      modell('felbe', { allapot: 'reszleges', lemez_bajt: 1_000_000_000 }),
      modell('kesz', { allapot: 'kesz', lemez_bajt: 2_500_000_000, ellenorizve: '2026-10-10T10:00:00' }),
      modell('regi', { allapot: 'elter_revizio', lemez_bajt: 3_000_000_000 }),
      modell('ellenorizetlen', { allapot: 'ellenorizetlen', lemez_bajt: 500_000_000 }),
      modell('konv', { allapot: 'konvertalasra_var', konvertalas: true, lemez_bajt: 700_000_000 }),
    );
    expect(within(sor('uj')).getByText('Not installed')).toBeTruthy();
    expect(within(sor('felbe')).getByText('Partly downloaded')).toBeTruthy();
    expect(within(sor('kesz')).getByText('Installed and verified')).toBeTruthy();
    expect(within(sor('kesz')).getByText('2.5 GB on disk')).toBeTruthy();
    expect(within(sor('regi')).getByText('Different version installed')).toBeTruthy();
    expect(within(sor('ellenorizetlen')).getByText('Installed, not verified')).toBeTruthy();
    expect(within(sor('konv')).getByText('Needs conversion')).toBeTruthy();
    expect(within(sor('uj')).getByText('Licence: Apache-2.0')).toBeTruthy();
    expect(within(sor('uj')).getByText('Download size: 2.50 GB')).toBeTruthy();
    expect(within(sor('uj')).getByText('Peak memory: 3.10 GB')).toBeTruthy();
    expect(within(sor('uj')).getByText('Source: org/uj')).toBeTruthy();
  });

  it('groups by role and filters by role and by language (multilingual models match every language)', async () => {
    await megnyit(
      modell('szoveges', { szerep: 'szoveg', nyelvek: ['*'] }),
      modell('magyar', { szerep: 'szoveg', nyelvek: ['hu'] }),
      modell('hangos', { szerep: 'hang', nyelvek: ['en', 'hu'] }),
    );
    expect(within(sor('magyar')).getByText('Hungarian')).toBeTruthy();
    expect(within(sor('szoveges')).getByText('All languages')).toBeTruthy();
    expect(within(sor('hangos')).getByText('English, Hungarian')).toBeTruthy();
    await fireEvent.change(screen.getByLabelText('Role'), { target: { value: 'hang' } });
    expect(document.querySelectorAll('[data-modell]')).toHaveLength(1);
    await fireEvent.change(screen.getByLabelText('Role'), { target: { value: '' } });
    await fireEvent.change(screen.getByLabelText('Language'), { target: { value: 'en' } });
    expect([...document.querySelectorAll('[data-modell]')].map((e) => e.getAttribute('data-modell')).sort()).toEqual(['hangos', 'szoveges']);
    await fireEvent.change(screen.getByLabelText('Language'), { target: { value: 'hu' } });
    expect(document.querySelectorAll('[data-modell]')).toHaveLength(3);
  });

  it('marks each task of a model Calibrated or Trial, with the word and an icon, never by colour alone', async () => {
    await megnyit(modell('vegyes', { feladat: ['szoveg', 'kiegeszites'], allapot: 'kesz', kalibracio: [kal('szoveg', true, { mero: 'sajat' }), kal('kiegeszites', false)] }));
    const jelek = within(sor('vegyes')).getByLabelText('Calibration status by task');
    expect(within(jelek).getByText('Text understanding:').parentElement!.textContent).toContain('Calibrated');
    expect(within(jelek).getByText('Text understanding:').parentElement!.textContent).toContain('own examples');
    expect(within(jelek).getByText('Text completion:').parentElement!.textContent).toContain('Trial');
    expect(jelek.querySelectorAll('svg')).toHaveLength(2);
  });

  it('shows a load failure in the shared error panel with a reload action, and an empty list as an empty state', async () => {
    (modellApi.lista as ReturnType<typeof vi.spyOn>).mockRejectedValueOnce(new ApiHiba(503, 'Synthetic list failure'));
    const r = render(ModellKezelo, { props: { tar } });
    await waitFor(() => expect(r.getByRole('alert').textContent).toContain('Synthetic list failure'));
    expect(r.getByText('What happened')).toBeTruthy();
    await fireEvent.click(r.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(r.getByText('No models are listed')).toBeTruthy());
  });
});

describe('Model Manager: letöltés', () => {
  it('downloads nothing on open; starts only on click, shows progress and finishes with a verified model', async () => {
    const m = modell('alap', { allapot: 'nincs' });
    const letolt = vi.spyOn(modellApi, 'letoltes').mockImplementation(async () => {
      lemez.alap = { ...m, letoltes: { feladat_id: 'f1', allapot: 'fut', szazalek: 0 } };
      return { feladat: feladat('f1', 'modell_letoltes', { szazalek: 0 }) };
    });
    await megnyit(m);
    expect(letolt).not.toHaveBeenCalled();
    await fireEvent.click(within(sor('alap')).getByRole('button', { name: 'Download (2.50 GB)' }));
    await waitFor(() => expect(within(sor('alap')).getByRole('progressbar')).toBeTruthy());
    expect(letolt).toHaveBeenCalledWith('alap');
    fs.upsert(feladat('f1', 'modell_letoltes', { szazalek: 42 }));
    await waitFor(() => expect(within(sor('alap')).getByText('Downloading… 42 %')).toBeTruthy());
    expect((within(sor('alap')).getByRole('progressbar') as HTMLProgressElement).value).toBe(42);
    lemez.alap = { ...m, allapot: 'kesz', lemez_bajt: 2_500_000_000 };
    fs.upsert(feladat('f1', 'modell_letoltes', { allapot: 'kesz', szazalek: 100, vegzett: '2026-10-16T12:00:00' }));
    await waitFor(() => expect(within(sor('alap')).getByText('Installed and verified')).toBeTruthy());
    expect(within(sor('alap')).getByText('Download finished and verified.')).toBeTruthy();
    expect(within(sor('alap')).queryByRole('progressbar')).toBeNull();
  });

  it('cancels a running download and offers to resume it', async () => {
    const m = modell('alap', { allapot: 'reszleges', lemez_bajt: 1_000_000_000, letoltes: { feladat_id: 'f1', allapot: 'fut', szazalek: 30 } });
    const megszakit = vi.spyOn(modellApi, 'megszakit').mockImplementation(async () => {
      lemez.alap = { ...m, letoltes: null };
      return { feladat: feladat('f1', 'modell_letoltes', { allapot: 'megallitva', szazalek: 31 }) };
    });
    fs.upsert(feladat('f1', 'modell_letoltes', { szazalek: 30 }));
    await megnyit(m);
    expect(within(sor('alap')).getByText('Downloading… 30 %')).toBeTruthy();
    expect(within(sor('alap')).queryByRole('button', { name: /^Download|Resume/ })).toBeNull();
    await fireEvent.click(within(sor('alap')).getByRole('button', { name: 'Cancel download' }));
    await waitFor(() => expect(within(sor('alap')).getByText(/Download cancelled/)).toBeTruthy());
    expect(megszakit).toHaveBeenCalledWith('alap');
    expect(within(sor('alap')).getByRole('button', { name: 'Resume download (2.50 GB)' })).toBeTruthy();
    expect(within(sor('alap')).queryByRole('progressbar')).toBeNull();
  });

  it('shows a failed download with an alert (words and icon) and the reason from the error code', async () => {
    const m = modell('alap', { allapot: 'reszleges', letoltes: { feladat_id: 'f2', allapot: 'fut', szazalek: 5 } });
    fs.upsert(feladat('f2', 'modell_letoltes', { szazalek: 5 }));
    await megnyit(m);
    lemez.alap = { ...m, letoltes: null };
    fs.upsert(feladat('f2', 'modell_letoltes', { allapot: 'hiba', hiba: 'x', kod: 'modell.nincs_hely', param: { szukseges_gb: 6.5 } }));
    await waitFor(() => expect(within(sor('alap')).getByRole('alert').textContent).toContain('Not enough disk space: 6.5 GB is needed.'));
    expect(within(sor('alap')).getByRole('alert').textContent).toContain('Download failed');
    expect(within(sor('alap')).getByRole('alert').closest('.uzenet-hiba')!.querySelector('p.hiba')).toBeTruthy();
  });

  it('shows a refused download start (already running / blocked host) as an alert instead of failing silently', async () => {
    vi.spyOn(modellApi, 'letoltes').mockRejectedValue(new ApiHiba(400, 'x', { kod: 'modell.host_tiltott', param: { host: 'evil.example' } }));
    await megnyit(modell('alap'));
    await fireEvent.click(within(sor('alap')).getByRole('button', { name: /^Download/ }));
    await waitFor(() => expect(within(sor('alap')).getByRole('alert').textContent).toBe('Downloads from evil.example are not allowed.'));
  });

  it('treats "already downloading" (409) as success and shows the running download', async () => {
    const m = modell('alap');
    vi.spyOn(modellApi, 'letoltes').mockRejectedValue(new ApiHiba(409, 'x', { kod: 'modell.letoltes_fut', param: {} }));
    await megnyit(m);
    lemez.alap = { ...m, letoltes: { feladat_id: 'f9', allapot: 'fut', szazalek: 12 } };
    fs.upsert(feladat('f9', 'modell_letoltes', { szazalek: 12 }));
    await fireEvent.click(within(sor('alap')).getByRole('button', { name: /^Download/ }));
    await waitFor(() => expect(within(sor('alap')).getByRole('progressbar')).toBeTruthy());
    expect(within(sor('alap')).queryByRole('alert')).toBeNull();
  });
});

describe('Model Manager: törlés', () => {
  it('asks first, shows the size it frees, keeps the model on "Keep it", and deletes only on confirmation', async () => {
    const m = modell('alap', { allapot: 'kesz', lemez_bajt: 2_500_000_000, feladat: ['szoveg'], kalibracio: [kal('szoveg', true)] });
    const torol = vi.spyOn(modellApi, 'torol').mockImplementation(async () => {
      lemez.alap = { ...m, allapot: 'nincs', lemez_bajt: 0, kalibracio: [] };
      return { id: 'alap', felszabadult_bajt: 2_500_000_000, kalibracio_levett: ['szoveg'] };
    });
    await megnyit(m);
    await fireEvent.click(within(sor('alap')).getByRole('button', { name: 'Delete…' }));
    const csoport = within(sor('alap')).getByRole('group', { name: 'Confirm deletion of alap' });
    expect(csoport.textContent).toContain('Delete alap? This frees 2.5 GB on disk.');
    expect(csoport.textContent).toContain('calibration marks are removed');
    expect(torol).not.toHaveBeenCalled();
    await waitFor(() => expect(document.activeElement).toBe(within(csoport).getByRole('button', { name: 'Keep it' })));
    await fireEvent.click(within(csoport).getByRole('button', { name: 'Keep it' }));
    expect(within(sor('alap')).queryByRole('group')).toBeNull();
    expect(torol).not.toHaveBeenCalled();
    await fireEvent.click(within(sor('alap')).getByRole('button', { name: 'Delete…' }));
    await fireEvent.click(within(sor('alap')).getByRole('button', { name: 'Delete and free 2.5 GB' }));
    await waitFor(() => expect(within(sor('alap')).getByText('Model deleted.')).toBeTruthy());
    expect(torol).toHaveBeenCalledWith('alap');
    expect(within(sor('alap')).getByText('Calibrated status removed for: Text understanding.')).toBeTruthy();
    expect(within(sor('alap')).getByText('Not installed')).toBeTruthy();
    expect(within(sor('alap')).queryByRole('button', { name: 'Delete…' })).toBeNull();
  });

  it('shows a refused deletion (model in use) with an alert and keeps the confirmation open', async () => {
    vi.spyOn(modellApi, 'torol').mockRejectedValue(new ApiHiba(409, 'x', { kod: 'modell.foglalt', param: {} }));
    await megnyit(modell('alap', { allapot: 'kesz', lemez_bajt: 1_000_000_000 }));
    await fireEvent.click(within(sor('alap')).getByRole('button', { name: 'Delete…' }));
    await fireEvent.click(within(sor('alap')).getByRole('button', { name: /^Delete and free/ }));
    await waitFor(() => expect(within(sor('alap')).getByRole('alert').textContent).toContain('in use by a download or a test'));
    expect(within(sor('alap')).getByRole('group', { name: /Confirm deletion/ })).toBeTruthy();
  });

  it('does not allow deleting while a download runs', async () => {
    fs.upsert(feladat('f1', 'modell_letoltes', { szazalek: 10 }));
    await megnyit(modell('alap', { allapot: 'reszleges', lemez_bajt: 5, letoltes: { feladat_id: 'f1', allapot: 'fut', szazalek: 10 } }));
    expect((within(sor('alap')).getByRole('button', { name: 'Delete…' }) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe('Model Manager: ajánlott modellek', () => {
  it('Install recommended models starts one download per missing recommended model, only on click', async () => {
    const letolt = vi.spyOn(modellApi, 'letoltes').mockImplementation(async (id) => {
      lemez[id] = { ...lemez[id], letoltes: { feladat_id: `f-${id}`, allapot: 'fut', szazalek: 0 } };
      return { feladat: feladat(`f-${id}`, 'modell_letoltes') };
    });
    await megnyit(
      modell('a', { ajanlott: true, meret_gb: 5 }), modell('b', { ajanlott: true, meret_gb: 1.5, allapot: 'reszleges' }),
      modell('c', { ajanlott: true, allapot: 'kesz' }), modell('d', { ajanlott: false }),
    );
    expect(letolt).not.toHaveBeenCalled();
    expect(screen.getByText('1 of 3 recommended models are installed.')).toBeTruthy();
    expect(screen.getByText('2 models · 6.50 GB')).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: 'Install recommended models' }));
    await waitFor(() => expect(letolt.mock.calls.map((c) => c[0])).toEqual(['a', 'b']));
    await waitFor(() => expect(screen.getByText('Recommended downloads in progress: 2.')).toBeTruthy());
    expect(screen.queryByRole('button', { name: 'Install recommended models' })).toBeNull();
  });

  it('reports when every recommended model is installed', async () => {
    await megnyit(modell('a', { ajanlott: true, allapot: 'kesz' }));
    expect(screen.getByText('All 1 recommended models are installed.')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Install recommended models' })).toBeNull();
  });
});

describe('Model Manager: Test this model', () => {
  const kesz = (extra: Partial<Modell> = {}) => modell('alap', { allapot: 'kesz', lemez_bajt: 2_500_000_000, feladat: ['szoveg'], ...extra });

  it('runs trial run → measurement → Calibrated and opens the report', async () => {
    const m = kesz();
    const teszt = vi.spyOn(modellApi, 'teszt').mockImplementation(async () => {
      lemez.alap = { ...m, teszt: { feladat_id: 't1', allapot: 'fut', szazalek: 0, feladat: 'szoveg' } };
      return { feladat: feladat('t1', 'modell_teszt'), elofeltetel: [] };
    });
    await megnyit(m);
    await fireEvent.click(within(sor('alap')).getByRole('button', { name: 'Test this model' }));
    expect((screen.getByLabelText('Task') as HTMLSelectElement).value).toBe('szoveg');
    expect(teszt).not.toHaveBeenCalled();
    await fireEvent.click(screen.getByRole('button', { name: 'Start test' }));
    await waitFor(() => expect(teszt).toHaveBeenCalledWith('alap', 'szoveg', 'szallitott'));
    await waitFor(() => expect(document.querySelector('[data-lepes="folyamatban"]')!.textContent).toContain('Trial run (3 items)'));
    fs.upsert(feladat('t1', 'modell_teszt', { szazalek: 55 }));
    await waitFor(() => expect(document.querySelector('[data-lepes="folyamatban"]')!.textContent).toContain('Measurement'));
    expect(document.querySelector('[data-lepes="kesz"]')!.textContent).toContain('Trial run');
    expect((screen.getByRole('progressbar', { name: 'Test progress for Text understanding' }) as HTMLProgressElement).value).toBe(55);
    // a mérés vége: a core rögzítette a jelet, a riport letölthető
    lemez.alap = { ...m, teszt: null, kalibracio: [kal('szoveg', true)] };
    vi.spyOn(modellApi, 'riport').mockResolvedValue(riport());
    fs.upsert(feladat('t1', 'modell_teszt', { allapot: 'kesz', szazalek: 100 }));
    const eredmeny = await waitFor(() => { const e = document.querySelector<HTMLElement>('.eredmeny[data-jel="kalibralt"]'); expect(e).toBeTruthy(); return e!; });
    expect(eredmeny.textContent).toContain('Calibrated');
    expect(eredmeny.textContent).toContain('Score: 0.820 (threshold: 0.4)');
    expect(within(sor('alap')).getByLabelText('Calibration status by task').textContent).toContain('Calibrated');
    expect(document.querySelector('[data-riport]')).toBeNull();
    await fireEvent.click(within(eredmeny).getByRole('button', { name: 'Open report' }));
    const dl = document.querySelector('[data-riport]')!;
    expect(dl.textContent).toContain('24 of 24');
    expect(dl.textContent).toContain('shipped examples');
    expect(dl.textContent).toContain('Recorded in the calibration table');
    await fireEvent.click(within(eredmeny).getByRole('button', { name: 'Close report' }));
    expect(document.querySelector('[data-riport]')).toBeNull();
  });

  it('a measurement below the threshold ends as Trial, with each reason in words and an icon', async () => {
    const m = kesz();
    vi.spyOn(modellApi, 'teszt').mockImplementation(async () => {
      lemez.alap = { ...m, teszt: { feladat_id: 't1', allapot: 'fut', szazalek: 0, feladat: 'szoveg' } };
      return { feladat: feladat('t1', 'modell_teszt'), elofeltetel: [] };
    });
    await megnyit(m);
    await fireEvent.click(within(sor('alap')).getByRole('button', { name: 'Test this model' }));
    await fireEvent.click(screen.getByRole('button', { name: 'Start test' }));
    await waitFor(() => expect(tar.aktiv(lemez.alap, 'teszt')).not.toBeNull());
    lemez.alap = { ...m, teszt: null };
    vi.spyOn(modellApi, 'riport').mockResolvedValue(riport({
      jel: 'proba', rogzitve: true,
      okok: [{ kod: 'modell.kuszob_alatt', param: { feladat: 'szoveg', pontszam: 0.31, kuszob: 0.4 } }, { kod: 'modell.nem_teljes', param: { n: 10, tetelszam: 24 } }],
      ertekeles: { pontszam: 0.31, n: 10, tetelszam: 24, teljes: false, ervenyes: true, ervenyesseg: { levagott: 1, hurok: 0, ures: 0, hiba: 0, hianyzo: 14 } },
    }));
    fs.upsert(feladat('t1', 'modell_teszt', { allapot: 'kesz', szazalek: 100 }));
    const eredmeny = await waitFor(() => { const e = document.querySelector<HTMLElement>('.eredmeny[data-jel="proba"]'); expect(e).toBeTruthy(); return e!; });
    expect(eredmeny.textContent).toContain('Trial');
    expect(eredmeny.textContent).toContain('output stays marked Trial');
    const okok = [...eredmeny.querySelectorAll('.ok-sor')];
    expect(okok.map((o) => o.textContent)).toEqual(['The score 0.31 is below the threshold 0.4.', 'The measurement did not cover the whole example set.']);
    for (const o of okok) expect(o.querySelector('svg')).toBeTruthy();
    expect(within(sor('alap')).getByLabelText('Calibration status by task').textContent).toContain('Trial');
  });

  it('shows the missing preconditions (400) as a list with icons and starts nothing', async () => {
    vi.spyOn(modellApi, 'teszt').mockRejectedValue(new ApiHiba(400, 'x', {
      kod: 'modell.halmaz_vazlat', param: { feladat: 'szoveg' },
      okok: [{ kod: 'modell.halmaz_vazlat', param: { feladat: 'szoveg' } }, { kod: 'modell.tul_nagy', param: { modell: 'alap', csucs_gb: 12, keret_gb: 9 } }],
    }));
    await megnyit(kesz());
    await fireEvent.click(within(sor('alap')).getByRole('button', { name: 'Test this model' }));
    await fireEvent.click(screen.getByRole('button', { name: 'Start test' }));
    await waitFor(() => expect(within(sor('alap')).getByRole('alert').textContent).toBe('The test cannot start yet:'));
    const sorok = [...sor('alap').querySelectorAll('.hiba-reszlet')];
    expect(sorok.map((s) => s.textContent)).toEqual(['The example set is not approved yet.', 'The model needs 12 GB of memory; at most 9 GB is available for AI.']);
    for (const s of sorok) expect(s.querySelector('svg')).toBeTruthy();
    expect(document.querySelector('[data-lepes]')).toBeNull();
  });

  it('explains why a model that is not installed cannot be tested, and a task without a threshold cannot be calibrated', async () => {
    await megnyit(modell('alap', { allapot: 'nincs' }), modell('hang', { allapot: 'kesz', lemez_bajt: 1, feladat: ['atirat'] }));
    expect(within(sor('alap')).queryByRole('button', { name: 'Test this model' })).toBeNull();
    await fireEvent.click(within(sor('hang')).getByRole('button', { name: 'Test this model' }));
    expect(within(sor('hang')).getByText(/Speech to text \(cannot be calibrated yet\)/)).toBeTruthy();
    expect(within(sor('hang')).getByText(/no calibration threshold yet/)).toBeTruthy();
  });

  it('offers your own examples only when an approved set exists, and measures on them when chosen', async () => {
    halm = halmazok({ sajat: { kiegeszites: sajatOsszegzes({ van: true, allapot: 'jovahagyott', tetelszam: 12, nyelv: 'en' }) } });
    const m = kesz({ feladat: ['kiegeszites'] });
    const teszt = vi.spyOn(modellApi, 'teszt').mockImplementation(async () => {
      lemez.alap = { ...m, teszt: { feladat_id: 't1', allapot: 'fut', szazalek: 0, feladat: 'kiegeszites' } };
      return { feladat: feladat('t1', 'modell_teszt'), elofeltetel: [] };
    });
    await megnyit(m);
    await fireEvent.click(within(sor('alap')).getByRole('button', { name: 'Test this model' }));
    const halmaz = screen.getByLabelText('Examples to measure on') as HTMLSelectElement;
    expect([...halmaz.options].map((o) => [o.value, o.disabled])).toEqual([['szallitott', false], ['sajat', false]]);
    expect(screen.getByRole('option', { name: 'My own examples (12 items)' })).toBeTruthy();
    await fireEvent.change(halmaz, { target: { value: 'sajat' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Start test' }));
    await waitFor(() => expect(teszt).toHaveBeenCalledWith('alap', 'kiegeszites', 'sajat'));
  });

  it('keeps the own-example option disabled while the set is only a draft', async () => {
    halm = halmazok({ sajat: { kiegeszites: sajatOsszegzes({ van: true, allapot: 'vazlat', tetelszam: 12 }) } });
    await megnyit(kesz({ feladat: ['kiegeszites'] }));
    await fireEvent.click(within(sor('alap')).getByRole('button', { name: 'Test this model' }));
    expect((screen.getByRole('option', { name: /My own examples/ }) as HTMLOptionElement).disabled).toBe(true);
  });

  it('stops a running test gracefully and reports it as stopped, resumable', async () => {
    const m = kesz({ teszt: { feladat_id: 't1', allapot: 'fut', szazalek: 50, feladat: 'szoveg' } });
    fs.upsert(feladat('t1', 'modell_teszt', { szazalek: 50 }));
    const leallit = vi.spyOn(vezerloApi, 'leallit').mockResolvedValue({ allapot: 'megallitva' });
    await megnyit(m);
    expect(screen.getByRole('button', { name: 'Stop test' })).toBeTruthy();
    expect((within(sor('alap')).getByRole('button', { name: 'Delete…' }) as HTMLButtonElement).disabled).toBe(true);
    await fireEvent.click(screen.getByRole('button', { name: 'Stop test' }));
    expect(leallit).toHaveBeenCalledWith('t1', false);
    lemez.alap = { ...m, teszt: null };
    vi.spyOn(modellApi, 'riport').mockResolvedValue(riport({ allapot: 'megallitva', jel: 'proba', okok: [] }));
    fs.upsert(feladat('t1', 'modell_teszt', { allapot: 'megallitva', szazalek: 52 }));
    await waitFor(() => expect(within(sor('alap')).getByText(/Test stopped\. Start it again/)).toBeTruthy());
    await waitFor(() => expect(document.querySelector('.eredmeny')!.textContent).toContain('stopped before it finished'));
    expect(screen.getByRole('button', { name: 'Start test' })).toBeTruthy();
  });

  it('disables starting while another model test runs', async () => {
    fs.upsert(feladat('t9', 'modell_teszt', { szazalek: 20 }));
    await megnyit(kesz(), modell('masik', { allapot: 'kesz', lemez_bajt: 1, teszt: { feladat_id: 't9', allapot: 'fut', szazalek: 20, feladat: 'szoveg' } }));
    await fireEvent.click(within(sor('alap')).getByRole('button', { name: 'Test this model' }));
    expect((within(sor('alap')).getByRole('button', { name: 'Start test' }) as HTMLButtonElement).disabled).toBe(true);
    expect(within(sor('alap')).getByText(/Another model test is running/)).toBeTruthy();
  });

  it('a failed test task shows its reason as an alert', async () => {
    const m = kesz({ teszt: { feladat_id: 't1', allapot: 'fut', szazalek: 10, feladat: 'szoveg' } });
    fs.upsert(feladat('t1', 'modell_teszt', { szazalek: 10 }));
    await megnyit(m);
    lemez.alap = { ...m, teszt: null };
    fs.upsert(feladat('t1', 'modell_teszt', { allapot: 'hiba', hiba: 'x', kod: 'modell.teszt_hiba', param: {} }));
    await waitFor(() => expect(within(sor('alap')).getByRole('alert').textContent).toContain('The model test could not run.'));
  });
});

describe('Calibration: saját aranyhalmaz-varázsló', () => {
  const fajl = (tartalom: unknown, nev = 'mine.json') => new File([typeof tartalom === 'string' ? tartalom : JSON.stringify(tartalom)], nev, { type: 'application/json' });
  const tetelek = [
    { id: 's001', elotte: 'Hello', utana: '.', elfogadhato: [' world'] },
    { id: 's002', elotte: 'Good', utana: '.', elfogadhato: [' morning'] },
  ];
  async function megnyitKal() {
    const r = render(Kalibracio, { props: { tar, onmodellek: vi.fn() } });
    await waitFor(() => expect(tar.halmazok).not.toBeNull());
    await waitFor(() => expect(tar.lista).not.toBeNull());
    return r;
  }
  const valaszt = async (f: File) => {
    const mezo = screen.getByLabelText('File with your examples') as HTMLInputElement;
    await fireEvent.change(mezo, { target: { files: [f] } });
  };

  it('shows the task thresholds, who is calibrated, and the shipped example sets with language and licence', async () => {
    felvesz(modell('alap', { allapot: 'kesz', feladat: ['szoveg'], kalibracio: [kal('szoveg', true)] }));
    await megnyitKal();
    const sz = document.querySelector('[data-feladat="szoveg"]')!;
    expect(sz.textContent).toContain('Score of at least 0.4 on 20 or more items');
    expect(sz.textContent).toContain('Calibrated');
    expect(sz.textContent).toContain('alap');
    expect(document.querySelector('[data-feladat="kiegeszites"]')!.textContent).toContain('Trial');
    expect(document.querySelector('[data-feladat="atirat"]')!.textContent).toContain('No threshold yet: cannot be calibrated');
    expect(document.querySelector('[data-szallitott="szoveg"]')!.textContent).toContain('24 items · language: English · licence: CC0-1.0');
    expect(document.querySelector('[data-szallitott="szoveg"]')!.textContent).toContain('Approved');
  });

  it('rejects files that are not a list of examples, with a reason in words and an icon', async () => {
    await megnyitKal();
    await valaszt(fajl('not a list'));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('could not be read as a list of examples'));
    await valaszt(fajl({ valami: 1 }));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('does not contain a list of examples'));
    await valaszt(fajl([{ id: 's1', elotte: 'a', elfogadhato: ['b'] }]));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('Item 1 is missing the field “utana”.'));
    expect((screen.getByRole('button', { name: 'Create draft set' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('walks the whole wizard: choose a file, review and approve, use it, delete it', async () => {
    const letrehoz = vi.spyOn(modellApi, 'halmazLetrehoz').mockImplementation(async () => {
      halm.sajat.kiegeszites = sajatOsszegzes({ van: true, allapot: 'vazlat', tetelszam: 2, nyelv: 'en', tetelek: [{ id: 's001' }, { id: 's002' }] });
      return halm.sajat.kiegeszites;
    });
    const jovahagy = vi.spyOn(modellApi, 'halmazJovahagy').mockImplementation(async () => {
      halm.sajat.kiegeszites = sajatOsszegzes({ van: true, allapot: 'jovahagyott', tetelszam: 2, nyelv: 'en', tetelek: [{ id: 's001' }, { id: 's002' }] });
      return halm.sajat.kiegeszites;
    });
    const valasztas = vi.spyOn(modellApi, 'halmazValaszt').mockImplementation(async (_f, mi) => {
      halm.sajat.kiegeszites = { ...halm.sajat.kiegeszites, valasztva: mi === 'sajat' };
      return halm.sajat.kiegeszites;
    });
    const torol = vi.spyOn(modellApi, 'halmazTorol').mockImplementation(async () => {
      halm.sajat.kiegeszites = sajatOsszegzes();
      return { feladat: 'kiegeszites', torolve: true };
    });
    await megnyitKal();
    expect(screen.getByText('No set of your own yet')).toBeTruthy();
    // 1. fájl + nyelv
    await valaszt(fajl(tetelek));
    await waitFor(() => expect(screen.getByText('mine.json: 2 items found.')).toBeTruthy());
    await fireEvent.change(screen.getByLabelText('Language of the examples'), { target: { value: 'hu' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Create draft set' }));
    await waitFor(() => expect(letrehoz).toHaveBeenCalledWith('kiegeszites', tetelek, 'hu'));
    // 2. átnézés és jóváhagyás: legalább min_tetel (2) tétel kell
    await waitFor(() => expect(screen.getByText('Draft: not approved yet')).toBeTruthy());
    expect(screen.getByText('Keeping 2 of 2 items (at least 2 are needed).')).toBeTruthy();
    await fireEvent.click(screen.getByRole('checkbox', { name: 's002' }));
    expect(screen.getByText('Keeping 1 of 2 items (at least 2 are needed).')).toBeTruthy();
    expect((screen.getByRole('button', { name: 'Approve set' }) as HTMLButtonElement).disabled).toBe(true);
    await fireEvent.click(screen.getByRole('checkbox', { name: 's002' }));
    await fireEvent.click(screen.getByRole('button', { name: 'Approve set' }));
    await waitFor(() => expect(jovahagy).toHaveBeenCalledWith('kiegeszites', ['s001', 's002']));
    const allapot = () => document.querySelector('[data-halmaz-allapot]')!.textContent;
    await waitFor(() => expect(allapot()).toContain('Approved'));
    // 3. választás
    await fireEvent.click(screen.getByRole('button', { name: 'Use my examples for tests' }));
    await waitFor(() => expect(valasztas).toHaveBeenCalledWith('kiegeszites', 'sajat'));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Use the shipped examples instead' })).toBeTruthy());
    expect(screen.getByText('Used for tests of this task')).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: 'Use the shipped examples instead' }));
    await waitFor(() => expect(valasztas).toHaveBeenLastCalledWith('kiegeszites', 'szallitott'));
    // 4. törlés megerősítéssel
    await fireEvent.click(screen.getByRole('button', { name: 'Delete my set…' }));
    const csoport = screen.getByRole('group', { name: 'Confirm deletion of your set' });
    expect(csoport.textContent).toContain('moved aside, not erased for good');
    expect(torol).not.toHaveBeenCalled();
    await fireEvent.click(within(csoport).getByRole('button', { name: 'Delete set' }));
    await waitFor(() => expect(torol).toHaveBeenCalledWith('kiegeszites'));
    await waitFor(() => expect(screen.getByText('No set of your own yet')).toBeTruthy());
    expect(screen.getByText('The set was removed.')).toBeTruthy();
  });

  it('shows the core\'s item error (row and field) when the draft is refused', async () => {
    vi.spyOn(modellApi, 'halmazLetrehoz').mockRejectedValue(new ApiHiba(400, 'x', { kod: 'modell.sajat_hibas_tetel', param: { sor: 2, mezo: 'utana' } }));
    await megnyitKal();
    await valaszt(fajl(tetelek));
    await waitFor(() => expect((screen.getByRole('button', { name: 'Create draft set' }) as HTMLButtonElement).disabled).toBe(false));
    await fireEvent.click(screen.getByRole('button', { name: 'Create draft set' }));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('Item 2 is invalid (utana).'));
  });

  it('shows the core\'s refusal to approve too few items', async () => {
    halm = halmazok({ sajat: { kiegeszites: sajatOsszegzes({ van: true, allapot: 'vazlat', tetelszam: 2, tetelek: [{ id: 's001' }, { id: 's002' }] }) } });
    vi.spyOn(modellApi, 'halmazJovahagy').mockRejectedValue(new ApiHiba(400, 'x', { kod: 'modell.keves_tetel', param: { feladat: 'kiegeszites', n: 1, min_tetel: 12 } }));
    await megnyitKal();
    await fireEvent.click(screen.getByRole('button', { name: 'Approve set' }));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('The set has 1 items; at least 12 are needed.'));
  });
});

describe('AI-hibák a hibaszerződés `ai` mezője szerint', () => {
  const aiTorzs = (kod: string, extra: Record<string, unknown> = {}) => ({ kod: 'nincs_kalibralt', param: {}, ai: { kod, feladat: 'szoveg', funkcio: 'kerdezz', param: {}, ...extra } });

  it('turns "no calibrated model" into what happened, what to do, and a link to the Model Manager', async () => {
    beallitasAblak.nyitva = false;
    render(AiHiba, { props: { hiba: new ApiHiba(503, 'x', aiTorzs('nincs_kalibralt')) } });
    expect(screen.getByRole('alert').textContent).toBe('No calibrated model is available for Text understanding.');
    expect(screen.getByText('What happened')).toBeTruthy();
    expect(screen.getByText(/Install a model for this task in Settings › AI › Models, then run “Test this model”/)).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: 'Open Model Manager' }));
    expect(beallitasAblak.nyitva).toBe(true);
    expect(beallitasAblak.szakasz).toBe('modellek');
    beallitasAblak.nyitva = false;
  });

  it('uses the task title of the loaded manifest and calls the provided opener', async () => {
    tar = new ModellTar(fs);
    const onmodellek = vi.fn();
    render(AiHiba, { props: { hiba: aiTorzs('nincs_telepitve', { feladat: 'kod' }), onmodellek } });
    expect(screen.getByRole('alert').textContent).toBe('No model is installed for Code assistant.');
    await fireEvent.click(screen.getByRole('button', { name: 'Open Model Manager' }));
    expect(onmodellek).toHaveBeenCalledTimes(1);
  });

  it('covers every code: away-only offers the manager; an unavailable engine offers diagnostics instead', async () => {
    const r1 = render(AiHiba, { props: { hiba: aiTorzs('csak_tavol') } });
    expect(r1.getByRole('alert').textContent).toBe('The model for Text understanding runs only while you are away.');
    expect(r1.getByRole('button', { name: 'Open Model Manager' })).toBeTruthy();
    r1.unmount();
    const diag = vi.fn();
    const r2 = render(AiHiba, { props: { hiba: aiTorzs('nincs_ai_runtime'), diagnosztika: diag } });
    expect(r2.getByRole('alert').textContent).toBe('The AI engine is not available.');
    expect(r2.queryByRole('button', { name: 'Open Model Manager' })).toBeNull();
    await fireEvent.click(r2.getByRole('button', { name: 'Open diagnostics' }));
    expect(diag).toHaveBeenCalled();
    r2.unmount();
    const r3 = render(AiHiba, { props: { hiba: aiTorzs('worker_hiba') } });
    expect(r3.getByRole('alert').textContent).toBe('The AI model stopped with an error.');
  });

  it('renders nothing for an error that is not an AI error', () => {
    const r = render(AiHiba, { props: { hiba: new ApiHiba(500, 'x', { kod: 'nincs_kalibralt' }) } });
    expect(r.container.querySelector('[data-hiba-panel]')).toBeNull();
  });

  it('every plain-text error surface gets the same understandable sentence (ApiHiba message, hibaUzenet, kodUzenet)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ hiba: 'Régi szöveg', ...aiTorzs('nincs_kalibralt') }), { status: 503, headers: { 'Content-Type': 'application/json' } })));
    const e = (await kerdez("/api/x").catch((x) => x)) as ApiHiba;
    vi.unstubAllGlobals();
    expect(e).toBeInstanceOf(ApiHiba);
    const vart = aiHibaEgysor(aiHibaAdat(e)!);
    expect(vart).toBe('No calibrated model is available for Text understanding. Install a model for this task in Settings › AI › Models, then run “Test this model”. Only a calibrated model can be used.');
    expect(e.message).toBe(vart);
    expect(hibaUzenet(e)).toBe(vart);
    expect(kodUzenet(aiTorzs('nincs_kalibralt'))).toBe(vart);
    expect(kodUzenet({ hiba: 'Plain', kod: 'valami.mas' })).toBe('Plain');
  });

  it('a body without an `ai` field keeps its own code-based text', () => {
    expect(aiHibaAdat(new ApiHiba(503, 'x', { kod: 'nincs_kalibralt' }))).toBeNull();
    expect(aiHibaAdat({ kod: 'nincs_kalibralt', param: {} })).toBeNull();
    expect(aiHibaAdat({ ai: { kod: 'ismeretlen_kod', feladat: 'szoveg' } })).toBeNull();
    expect(hibaUzenet(new ApiHiba(503, 'x', { kod: 'nincs_kalibralt', param: {} }))).toBe('No calibrated model is available for this task. Use trial mode or calibrate a model.');
  });
});

describe('ModellTar', () => {
  it('stops following a task that vanished from a loaded task list and re-reads the model from disk', async () => {
    const m = modell('alap', { letoltes: { feladat_id: 'f1', allapot: 'fut', szazalek: 10 } });
    felvesz(m);
    await tar.betolt();
    expect(tar.dolgozik).toBe(true);
    lemez.alap = { ...m, letoltes: null, allapot: 'kesz' };
    fs.lista = [];
    fs.betoltve = true;
    await tar.szinkron([]);
    expect(tar.dolgozik).toBe(false);
    expect(tar.modellek[0].allapot).toBe('kesz');
  });

  it('a missing report (404) is not an error', async () => {
    felvesz(modell('alap'));
    await tar.betolt();
    expect(await tar.riportBetolt('alap', 'szoveg')).toBeNull();
    expect(tar.uzenetek.alap).toBeUndefined();
  });
});

describe('Settings › AI integráció', () => {
  const beallitasValasz = (): BeallitasokValasz => ({ verzio: 1, rev: 'r1', ertek: alapBeallitasok(), munkater: { id: 'synthetic', nev: 'Synthetic workspace', vault: '/synthetic/vault' }, setup_szukseges: false, ujrainditas: [] });
  function settings(szakasz: 'modellek' | 'kalibracio') {
    const bt = new BeallitasokTar();
    bt.fogad(beallitasValasz());
    beallitasok.fogad(beallitasValasz());
    beallitasAblak.szakasz = szakasz;
    const onbezar = vi.fn();
    render(BeallitasokAblak, { props: { tar: bt, onbezar, onsetup: vi.fn(), onrendszer: vi.fn() } });
    return { onbezar };
  }
  afterEach(() => { beallitasok.adat = null; egeszsegAblak.nyitva = false; beallitasAblak.szakasz = 'altalanos'; });

  it('Models opens the Model Manager, with the shared nav entry and a jump to Calibration', async () => {
    lemez = { alap: modell('alap', { ajanlott: true }) };
    settings('modellek');
    await waitFor(() => expect(document.querySelector('[data-modell="alap"]')).toBeTruthy());
    expect(screen.getByRole('heading', { name: 'Models' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Install recommended models' })).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: 'Open Calibration' }));
    await waitFor(() => expect(document.querySelector('[data-kalibracio]')).toBeTruthy());
    expect(screen.getByRole('heading', { name: 'Calibration' })).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Your own examples' })).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: 'Open Models' }));
    await waitFor(() => expect(document.querySelector('[data-modellkezelo]')).toBeTruthy());
  });

  it('a model-list failure offers diagnostics, which closes Settings and opens Health', async () => {
    modellek.lista = null; modellek.hiba = null;
    (modellApi.lista as ReturnType<typeof vi.spyOn>).mockRejectedValue(new ApiHiba(503, 'Synthetic list failure'));
    const { onbezar } = settings('modellek');
    await waitFor(() => expect(screen.getAllByRole('alert').some((a) => a.textContent?.includes('Synthetic list failure'))).toBe(true));
    await fireEvent.click(screen.getByRole('button', { name: 'Open diagnostics' }));
    expect(onbezar).toHaveBeenCalled();
    expect(egeszsegAblak.nyitva).toBe(true);
  });
});
