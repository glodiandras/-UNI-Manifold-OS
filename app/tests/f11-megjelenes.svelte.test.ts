// F11 Settings pages (14-appearance-01, -02, -05, -06): font fields with preview and reset, auto-pair switches, the Excluded
// files list, its explorer / quick-switcher effects and the PLAN §11 promise. Synthetic data; the core calls are mocked.
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import Valto from '../src/atfedes/Valto.svelte';
import BeallitasokAblak from '../src/beallitasok/Beallitasok.svelte';
import { beallitasAblak } from '../src/beallitasok/allapot.svelte';
import Fa from '../src/hej/Fa.svelte';
import { BeallitasokTar, beallitasok } from '../src/lib/beallitasok/allapot.svelte';
import { beallitasokApi } from '../src/lib/beallitasok/api';
import { alapBeallitasok, type BeallitasokValasz } from '../src/lib/beallitasok/tipusok';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { nyelv } from '../src/lib/i18n';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { VaultFajlok, type FajlInfo } from '../src/lib/vault/fajlok.svelte';
import { linkek } from '../src/lib/vault/linkek.svelte';

const valasz = (rev = 'r1'): BeallitasokValasz => ({ verzio: 1, rev, ertek: alapBeallitasok(), munkater: { id: 'synthetic', nev: 'Synthetic workspace', vault: '/synthetic/vault' }, setup_szukseges: false, ujrainditas: [] });
beforeEach(() => { nyelv.beallit('en'); beallitasAblak.szakasz = 'altalanos'; vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null); vi.spyOn(beallitasokApi, 'kizartElonezet').mockRejectedValue(new Error('index not ready')); });
afterEach(() => { cleanup(); beallitasok.adat = null; vi.restoreAllMocks(); vi.unstubAllGlobals(); document.body.textContent = ''; nyelv.beallit('hu'); });

function nyit() {
  const tar = new BeallitasokTar(); tar.fogad(valasz());
  render(BeallitasokAblak, { props: { tar, onbezar: vi.fn(), onsetup: vi.fn(), onrendszer: vi.fn() } });
  return tar;
}
const szakasz = (nev: string) => fireEvent.click(screen.getByRole('button', { name: nev }));
const ment = () => fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));

/** A vászon-próba álvászna: a megadott családok szélessége eltér az általános családokétól (azaz "telepítettek"). */
function telepitettBetuk(nevek: string[]) {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(function () {
    let font = '';
    return {
      set font(v: string) { font = v; }, get font() { return font; },
      measureText: (s: string) => {
        const m = /^72px (?:"([^"]+)", )?(monospace|serif|sans-serif)$/.exec(font);
        return { width: s.length * ((m?.[2] === 'monospace' ? 10 : m?.[2] === 'serif' ? 11 : 12) + (m?.[1] && nevek.includes(m[1]) ? 3 : 0)) };
      },
    } as unknown as CanvasRenderingContext2D;
  } as never);
}

describe('14-appearance-01/02: Text font and Monospace font', () => {
  it('shows both fields with a preview that follows the draft, and the default preview uses the system tokens', async () => {
    telepitettBetuk(['Georgia', 'Menlo']);
    nyit(); await szakasz('Appearance');
    const szoveg = screen.getByLabelText('Text font') as HTMLInputElement, mono = screen.getByLabelText('Monospace font') as HTMLInputElement;
    expect([szoveg.value, mono.value]).toEqual(['', '']);
    const elonezet = (fajta: string) => document.querySelector<HTMLElement>(`[data-elonezet="${fajta}"]`)!;
    expect(elonezet('szoveg').style.getPropertyValue('--betu-jegyzet')).toBe('var(--betu-rendszer)');
    await fireEvent.input(szoveg, { target: { value: 'Georgia' } });
    await fireEvent.input(mono, { target: { value: 'Menlo' } });
    expect(elonezet('szoveg').style.getPropertyValue('--betu-jegyzet')).toBe('"Georgia", var(--betu-rendszer)');
    expect(elonezet('mono').style.getPropertyValue('--betu-mono')).toBe('"Menlo", var(--betu-mono-alap)');
    expect(screen.queryByText(/is not installed on this Mac/)).toBeNull();
  });

  it('says so, without blocking, when the family is not installed; reset restores the default', async () => {
    telepitettBetuk(['Georgia']);
    nyit(); await szakasz('Appearance');
    const szoveg = screen.getByLabelText('Text font') as HTMLInputElement;
    await fireEvent.input(szoveg, { target: { value: 'Imaginary Serif' } });
    expect(screen.getByRole('status').textContent).toContain('"Imaginary Serif" is not installed on this Mac, so the default font is used.');
    expect((screen.getByRole('button', { name: 'Save changes' }) as HTMLButtonElement).disabled).toBe(false);
    const reset = within(szoveg.closest('.betu') as HTMLElement).getByRole('button', { name: 'Reset to default' });
    await fireEvent.click(reset);
    expect(szoveg.value).toBe('');
    expect(screen.queryByText(/is not installed/)).toBeNull();
  });

  it('saves only valid names: CSS-like input is flagged with an icon and words and never sent', async () => {
    telepitettBetuk([]);
    nyit(); await szakasz('Appearance');
    const put = vi.spyOn(beallitasokApi, 'ment');
    await fireEvent.input(screen.getByLabelText('Text font'), { target: { value: 'x";}body{display:none' } });
    const alert = screen.getAllByRole('alert').find(e => e.textContent?.includes('Use a font family name only'))!;
    expect(alert.querySelector('svg')).not.toBeNull();
    await ment();
    expect(screen.getAllByRole('alert').some(e => e.textContent?.includes('Fix the font name before saving.'))).toBe(true);
    expect(put).not.toHaveBeenCalled();
    await fireEvent.input(screen.getByLabelText('Text font'), { target: { value: 'url(https://example.invalid/f.woff)' } });
    await ment();
    expect(put).not.toHaveBeenCalled();
  });

  it('sends valid names in the one atomic settings call; the other appearance values stay', async () => {
    telepitettBetuk(['Georgia', 'Menlo']);
    nyit(); await szakasz('Appearance');
    const mentett = valasz('r2'); mentett.ertek.megjelenes.betu_szoveg = 'Georgia'; mentett.ertek.megjelenes.betu_mono = 'Menlo';
    const put = vi.spyOn(beallitasokApi, 'ment').mockResolvedValue(mentett);
    await fireEvent.input(screen.getByLabelText('Text font'), { target: { value: 'Georgia' } });
    await fireEvent.input(screen.getByLabelText('Monospace font'), { target: { value: 'Menlo' } });
    await ment();
    await waitFor(() => expect(screen.getByRole('status').textContent).toBe('Settings saved'));
    expect(put.mock.calls[0][1]).toEqual({ megjelenes: { tema: 'rendszer', betumeret: 16, csend: false, betu_szoveg: 'Georgia', betu_mono: 'Menlo' } });
  });

  it('an older settings response without the new keys still opens the page with defaults', async () => {
    const tar = new BeallitasokTar(); const v = valasz();
    delete (v.ertek.megjelenes as Partial<typeof v.ertek.megjelenes>).betu_szoveg; delete (v.ertek.fajlok as Partial<typeof v.ertek.fajlok>).kizart;
    tar.fogad(v);
    render(BeallitasokAblak, { props: { tar, onbezar: vi.fn(), onsetup: vi.fn(), onrendszer: vi.fn() } });
    await szakasz('Appearance');
    expect((screen.getByLabelText('Text font') as HTMLInputElement).value).toBe('');
    await szakasz('Files & links');
    expect(screen.getByText('No files are excluded.')).toBeTruthy();
  });
});

describe('14-appearance-05: auto-pair switches in the Editor page', () => {
  it('shows three independent switches (default on) and saves each one separately', async () => {
    nyit(); await szakasz('Editor');
    const nevek = ['Auto pair brackets', 'Auto pair quotes', 'Auto pair Markdown syntax'];
    for (const n of nevek) expect(screen.getByRole('switch', { name: n }).getAttribute('aria-checked')).toBe('true');
    const mentett = valasz('r2'); mentett.ertek.szerkeszto.auto_par_idezojel = false;
    const put = vi.spyOn(beallitasokApi, 'ment').mockResolvedValue(mentett);
    await fireEvent.click(screen.getByRole('switch', { name: 'Auto pair quotes' }));
    expect(screen.getByRole('switch', { name: 'Auto pair quotes' }).getAttribute('aria-checked')).toBe('false');
    expect(screen.getByRole('switch', { name: 'Auto pair brackets' }).getAttribute('aria-checked')).toBe('true');
    await ment();
    await waitFor(() => expect(put).toHaveBeenCalled());
    expect(put.mock.calls[0][1].szerkeszto).toMatchObject({ auto_par_zarojel: true, auto_par_idezojel: false, auto_par_jeloles: true });
  });
});

describe('14-appearance-06: Excluded files in Files & links', () => {
  const elonezet = (mintak: string[]) => ({ osszes: 5, kizart: mintak.includes('Archive/') ? 2 : 0, mintak: mintak.map(m => ({ minta: m, db: m === 'Archive/' ? 2 : 0, hiba: m === '/(a+)+$/' ? 'regex_veszelyes' : null })) });

  it('no longer claims rules are "preserved" and says what exclusion does and does not do', async () => {
    nyit(); await szakasz('Files & links');
    expect(document.body.textContent).not.toMatch(/preserved/i);
    expect(screen.getByText(/Matching files are hidden from search, the graph, the quick switcher, and unlinked mentions\. They are not deleted or moved/)).toBeTruthy();
    expect(screen.getByText('Deleted files go to the system Trash.')).toBeTruthy();
  });

  it('adds and removes entries, shows live per-entry and total counts from the core, and saves the list', async () => {
    const pre = vi.spyOn(beallitasokApi, 'kizartElonezet').mockImplementation(async (m) => elonezet(m));
    nyit(); await szakasz('Files & links');
    const mezo = screen.getByLabelText('New excluded path or pattern');
    await fireEvent.input(mezo, { target: { value: 'Archive/' } });
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    expect(screen.getByText('Archive/')).toBeTruthy();
    await waitFor(() => expect(screen.getByText('2 matching')).toBeTruthy());
    expect(screen.getByRole('status').textContent).toBe('2 of 5 files are currently excluded.');
    expect(pre).toHaveBeenLastCalledWith(['Archive/']);
    await fireEvent.input(mezo, { target: { value: '/\\.tmp$/' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    expect(screen.getAllByRole('listitem').map(e => e.querySelector('code')?.textContent)).toEqual(['Archive/', '/\\.tmp$/']);
    const mentett = valasz('r2'); mentett.ertek.fajlok.kizart = ['Archive/', '/\\.tmp$/'];
    const put = vi.spyOn(beallitasokApi, 'ment').mockResolvedValue(mentett);
    await ment();
    await waitFor(() => expect(put).toHaveBeenCalled());
    expect(put.mock.calls[0][1].fajlok?.kizart).toEqual(['Archive/', '/\\.tmp$/']);
    await fireEvent.click(screen.getByRole('button', { name: 'Remove Archive/' }));
    expect(screen.getAllByRole('listitem').map(e => e.querySelector('code')?.textContent)).toEqual(['/\\.tmp$/']);
  });

  it('flags an invalid entry with an icon and words and blocks saving until it is fixed', async () => {
    vi.spyOn(beallitasokApi, 'kizartElonezet').mockImplementation(async (m) => elonezet(m));
    nyit(); await szakasz('Files & links');
    const mezo = screen.getByLabelText('New excluded path or pattern');
    await fireEvent.input(mezo, { target: { value: '/(a+)+$/' } });
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    const hiba = await screen.findByText('Pattern could run too long');
    expect(hiba.closest('[role="alert"]')!.querySelector('svg')).not.toBeNull();
    const put = vi.spyOn(beallitasokApi, 'ment');
    await ment();
    expect(screen.getAllByRole('alert').some(e => e.textContent?.includes('Fix or remove the excluded-files entries'))).toBe(true);
    expect(put).not.toHaveBeenCalled();
    await fireEvent.click(screen.getByRole('button', { name: 'Remove /(a+)+$/' }));
    await waitFor(() => expect(screen.queryByText('Pattern could run too long')).toBeNull());
  });

  it('keeps working when the match count is unavailable (index still building)', async () => {
    nyit(); await szakasz('Files & links');
    await fireEvent.input(screen.getByLabelText('New excluded path or pattern'), { target: { value: 'Archive/' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    await waitFor(() => expect(screen.getByText(/The match count is not available yet/)).toBeTruthy());
    expect(screen.getByText('Archive/')).toBeTruthy();
  });
});

describe('14-appearance-06: explorer dims and the quick switcher hides excluded files; links to them are not affected', () => {
  const f = (ut: string, kizart = false): FajlInfo => ({ ut, tipus: 'md', meret: 1, mtime: 1, ...(kizart ? { kizart: true } : {}) });
  function kornyezet() {
    const felulet = new Felulet({ legutobbiFajlok: ['Archive/Old.md', 'Public.md'] }), fajlok = new VaultFajlok();
    fajlok.beallit([f('Public.md'), f('Notes/Open.md'), f('Archive/Old.md', true), f('Secret.md', true)]);
    vi.spyOn(fajlok, 'frissit').mockResolvedValue();
    const context = new Map<unknown, unknown>([[KORNYEZET_KULCS, { felulet, fajlok, kapcsolat: new CoreKapcsolat('ws://synthetic') }]]);
    return { felulet, fajlok, context };
  }

  it('the tree still lists every file; excluded rows are marked (dimmed) and explain why in the title', async () => {
    const k = kornyezet();
    k.felulet.oldalsav.nyitott = ['Archive', 'Notes'];
    render(Fa, { context: k.context });
    const sorok = screen.getAllByRole('treeitem');
    const ut = (e: Element) => e.getAttribute('data-fa-ut');
    expect(sorok.map(ut).sort()).toEqual(['Archive', 'Archive/Old.md', 'Notes', 'Notes/Open.md', 'Public.md', 'Secret.md']);
    expect(sorok.filter(e => e.classList.contains('kizart')).map(ut).sort()).toEqual(['Archive/Old.md', 'Secret.md']);
    expect(sorok.find(e => ut(e) === 'Secret.md')!.getAttribute('title')).toContain('Excluded from search, graph and quick switcher');
    expect(sorok.find(e => ut(e) === 'Public.md')!.getAttribute('title')).not.toContain('Excluded');
  });

  it('the quick switcher lists neither recents nor search hits for excluded files, but still finds the rest', async () => {
    vi.spyOn(linkek, 'aliasokKap').mockResolvedValue({ 'Secret.md': ['Hidden alias'], 'Public.md': ['Open alias'] });
    const k = kornyezet();
    render(Valto, { context: k.context });
    const nevek = () => screen.getAllByRole('option').map(o => o.textContent?.replace(/\s+/g, ' ').trim());
    expect(nevek().join('|')).toContain('Public');
    expect(nevek().join('|')).not.toMatch(/Old|Secret/);
    const mezo = screen.getByRole('combobox');
    await fireEvent.input(mezo, { target: { value: 'secret' } });
    expect(screen.queryAllByRole('option').some(o => /Secret/.test(o.textContent ?? ''))).toBe(false);
    await fireEvent.input(mezo, { target: { value: 'hidden alias' } });
    expect(screen.queryAllByRole('option').some(o => /Hidden alias|Secret/.test(o.textContent ?? ''))).toBe(false);
    await fireEvent.input(mezo, { target: { value: 'open alias' } });
    expect(nevek().join('|')).toContain('Open alias');
  });
});

describe('PLAN §11 "Files & links → excluded files": the promise is kept end to end', () => {
  it('the plan item has its setting (core ALAP + os.toml + TS defaults), UI, enforcement module and tests', () => {
    const olvas = (ut: string) => readFileSync(decodeURIComponent(new URL(ut, import.meta.url).pathname), 'utf8');
    expect(olvas('../../docs/PLAN.md')).toMatch(/Files & links \(new note location, attachment folder, trash, link format, excluded files/);
    expect(olvas('../../core/termek_beallitasok.py')).toMatch(/"kizart": \[\]/);
    expect(olvas('../../config/os.toml')).toMatch(/^kizart = \[\]/m);
    expect(alapBeallitasok().fajlok.kizart).toEqual([]);
    expect(olvas('../src/beallitasok/Beallitasok.svelte')).toContain('<KizartSzerkeszto');
    expect(olvas('../../tests/test_f11_kizaras.py')).toContain('test_kereses_kihagyja_es_a_lista_torlese_visszahozza');
  });
});
