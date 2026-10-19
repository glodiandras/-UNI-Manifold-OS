// A már létező gráf napi must fogyasztói: parancs → panel → valódi Svelte vezérlő → modell/rajzoló bemenet.
// A pixel/hit-test és a fizika/perf külön f11-graf-rajzolo / teljesitmeny tesztjeit nem ismételjük meg.
import { cleanup, fireEvent, render, waitFor } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Esemenyek } from '../src/lib/graf/rajzolo';
import type { Be, Ki } from '../src/lib/graf/fizikaMotor';

const rajz = vi.hoisted(() => ({ esemenyek: null as Esemenyek | null }));
vi.mock('../src/lib/graf/rajzolo', async (orig) => {
  const m = await orig<typeof import('../src/lib/graf/rajzolo')>();
  return { ...m, GrafRajzolo: class extends m.GrafRajzolo {
    constructor(v: HTMLCanvasElement, e: Esemenyek) { super(v, e); rajz.esemenyek = e; }
  } };
});
// A komponens tesztben a számolás kész pozíciót ad; a valódi renderer és modell megmarad.
vi.mock('../src/lib/graf/fizikaGazda', () => ({ FizikaGazda: class {
  workerben = false;
  constructor(private fogad: (m: Ki) => void) {}
  kuld(m: Be) { if (m.tipus === 'init') this.fogad({ tipus: 'poz', poz: new Float32Array(m.poz), alpha: 0, fut: false }); }
  leallit() {}
} }));

import Graf from '../src/graf/Graf.svelte';
import { grafTelepit } from '../src/graf';
import { beallitasok } from '../src/lib/beallitasok/allapot.svelte';
import { alapBeallitasok } from '../src/lib/beallitasok/tipusok';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { GrafAdat, FELOLDATLAN_ELOTAG } from '../src/lib/graf/modell';
import { GrafRajzolo } from '../src/lib/graf/rajzolo';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { Regiszter } from '../src/lib/parancsok/regiszter';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import { grafAdat } from '../src/lib/vault/graf.svelte';
import { felvevoKontextus } from './graf-vaszon-segedek';

const UTAK = ['Notes/A.md', 'Notes/B.md', 'Notes/C.md'];
const le: (() => void)[] = [];
let letrehozas: { kod: number; adat: unknown };
let postok: { url: string; body: unknown }[];

beforeEach(() => {
  rajz.esemenyek = null; postok = [];
  letrehozas = { kod: 200, adat: { ut: 'Core-selected/Ghost.md' } };
  const ertek = alapBeallitasok();
  beallitasok.fogad({ verzio: 1, rev: 'synthetic', ertek, munkater: { id: 'synthetic', nev: 'Synthetic', vault: '/synthetic' }, setup_szukseges: false, ujrainditas: [] });
  grafAdat.adat = new GrafAdat({ csucsok: UTAK, elek: [[UTAK[0], UTAK[1]], [UTAK[1], UTAK[2]]] }, () => 'md', {
    cimkek: { [UTAK[0]]: ['work'] }, tulajdonsagok: {}, feloldatlan_elek: [[UTAK[0], 'Ghost']], cimke_csucsok: { work: { nev: 'work', db: 1 } },
  });
  grafAdat.json = { van: false, szincsoportok: [] }; grafAdat.betoltve = true; grafAdat.hiba = null;
  vi.spyOn(grafAdat, 'megjelenik').mockReturnValue(() => {});
  vi.spyOn(grafAdat, 'tipusokFrissit').mockImplementation(() => {});
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(felvevoKontextus().ctx as never);
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} unobserve() {} });
  vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    postok.push({ url, body: JSON.parse(String(init?.body)) });
    expect(url).toBe('/api/vault/uj');
    return new Response(JSON.stringify(letrehozas.adat), { status: letrehozas.kod, headers: { 'Content-Type': 'application/json' } });
  });
});
afterEach(async () => {
  await fireEvent.keyDown(document, { key: 'Escape' });
  cleanup(); le.splice(0).forEach(f => f());
  grafAdat.adat = null; beallitasok.adat = null; ertesitesek.lista.length = 0;
  vi.unstubAllGlobals();
});

function kornyezet() {
  const felulet = new Felulet({}), reg = new Regiszter(), fajlok = new VaultFajlok();
  fajlok.lista = UTAK.map(ut => ({ ut, tipus: 'md', meret: 10, mtime: 0 }));
  le.push(grafTelepit(reg, felulet));
  return { felulet, reg, fajlok, kapcsolat: new CoreKapcsolat('ws://127.0.0.1:1/ws') };
}
async function helyiNyit() {
  const k = kornyezet(), m = k.felulet.munkaterulet;
  m.megnyit(UTAK[0]);
  const forrasPanel = m.aktivPanelId;
  expect(k.reg.futtat('graf.helyi', 'paletta')).toBe(true);
  const grafPanel = m.panelek().find(p => p.fulek.some(f => f.nezet?.tipus === 'graf'))!;
  const ful = grafPanel.fulek.find(f => f.nezet?.tipus === 'graf')!;
  const c = render(Graf, { props: { ful, aktiv: false, info: undefined }, context: new Map([[KORNYEZET_KULCS, k]]) });
  await waitFor(() => expect(rajz.esemenyek).not.toBeNull()); await tick();
  return { ...c, ...k, m, ful, grafPanel, forrasPanel };
}

describe('S1 napi graph must: valódi parancs/panel/vezérlő út', () => {
  it('graf.helyi jegyzet mellett nyílik, a jegyzet marad aktív; modul nélkül és aktív jegyzet nélkül nem fut', async () => {
    const c = await helyiNyit();
    expect(c.m.panelek()).toHaveLength(2);
    expect(c.m.aktivPanelId).toBe(c.forrasPanel);
    expect(c.m.aktivFul!.ut).toBe(UTAK[0]);
    expect(c.ful.nezet).toMatchObject({ mod: 'helyi', kozeppont: UTAK[0], kovet: true, celPanel: c.forrasPanel });
    c.reg.futtat('graf.helyi'); await tick();
    expect(c.m.panelek()).toHaveLength(2);
    beallitasok.adat!.ertek.modulok.graf = false;
    expect(c.reg.futtat('graf.helyi')).toBe(false);
    beallitasok.adat!.ertek.modulok.graf = true;
    c.m.aktival(c.grafPanel.id, c.ful.id);
    expect(c.reg.futtat('graf.helyi')).toBe(false);
    expect(c.m.panelek()).toHaveLength(2);
  });

  it('az aktív jegyzetváltás követ, follow off után a centrum stabil; a gráffül aktiválása nem törli a centrumot', async () => {
    const c = await helyiNyit();
    c.m.megnyit(UTAK[1]); await tick();
    expect(c.ful.nezet!.kozeppont).toBe(UTAK[1]);
    expect(c.getByRole('application').getAttribute('aria-label')).toContain('helyi gráf: B');
    const kovet = c.getByRole('button', { name: 'Aktív jegyzet követése' });
    await fireEvent.click(kovet);
    expect(kovet.getAttribute('aria-pressed')).toBe('false');
    c.m.megnyit(UTAK[2]); await tick();
    expect(c.ful.nezet!.kozeppont).toBe(UTAK[1]);
    c.m.aktival(c.grafPanel.id, c.ful.id); await tick();
    expect(c.ful.nezet!.kozeppont).toBe(UTAK[1]);
    await fireEvent.click(kovet); // gráf aktív: nincs note, ezért a régi érvényes centrum marad
    expect(c.ful.nezet!.kozeppont).toBe(UTAK[1]);
    c.m.aktival(c.forrasPanel); await tick();
    expect(c.ful.nezet!.kozeppont).toBe(UTAK[2]);
  });

  it('a gráfból megnyitott valódi csúcs a jegyzet paneljébe kerül; a local graph nem cserélődik le', async () => {
    const c = await helyiNyit();
    c.m.aktival(c.grafPanel.id, c.ful.id); await tick();
    rajz.esemenyek!.megnyit(grafAdat.adat!.csucsIndex(UTAK[2]), 'aktiv'); await tick();
    expect(c.m.aktivPanelId).toBe(c.forrasPanel);
    expect(c.m.aktivFul!.ut).toBe(UTAK[2]);
    expect(c.grafPanel.fulek.find(f => f.id === c.ful.id)?.nezet?.tipus).toBe('graf');
    expect(c.ful.nezet!.kozeppont).toBe(UTAK[2]);
    expect(postok).toEqual([]);
  });

  it('a tényleges Existing files only kapcsoló a renderer bemenetét váltja, és a felület mentett állapotában marad', async () => {
    const bemenet = vi.spyOn(GrafRajzolo.prototype, 'bemenet');
    const c = await helyiNyit();
    await fireEvent.click(c.getByRole('button', { name: 'Szűrők, színek és erők' }));
    const checkbox = c.getByRole('checkbox', { name: 'Csak létező fájlok' }) as HTMLInputElement;
    const i = grafAdat.adat!.ut.indexOf(FELOLDATLAN_ELOTAG + 'Ghost');
    expect(i).toBeGreaterThanOrEqual(0);
    expect(checkbox.checked).toBe(true);
    expect(bemenet.mock.calls.at(-1)![0].lathato[i]).toBe(0);
    await fireEvent.click(checkbox);
    expect(bemenet.mock.calls.at(-1)![0].lathato[i]).toBe(1);
    expect(c.felulet.sorosit().graf).toMatchObject({ letezoCsak: false });
    await fireEvent.click(checkbox);
    expect(bemenet.mock.calls.at(-1)![0].lathato[i]).toBe(0);
    expect(postok).toEqual([]); // a kapcsoló nem hoz létre fájlt
  });

  it.each([200, 409])('a feloldatlan cél explicit Create után a core-ra bízza az útvonalat; %i eredmény helyes panelt/hibát ad', async kod => {
    const c = await helyiNyit();
    await fireEvent.click(c.getByRole('button', { name: 'Szűrők, színek és erők' }));
    await fireEvent.click(c.getByRole('checkbox', { name: 'Csak létező fájlok' }));
    const i = grafAdat.adat!.ut.indexOf(FELOLDATLAN_ELOTAG + 'Ghost');
    rajz.esemenyek!.megnyit(i, 'aktiv', 10, 10);
    expect(postok).toEqual([]);
    const menu = document.querySelector<HTMLElement>('.nt-lebego')!;
    await fireEvent.keyDown(menu, { key: 'Escape' });
    expect(postok).toEqual([]);
    expect(document.activeElement).toBe(c.getByRole('application'));
    rajz.esemenyek!.megnyit(i, 'aktiv', 10, 10);
    if (kod === 409) letrehozas = { kod, adat: { hiba: 'Synthetic collision' } };
    const cel = [...document.querySelectorAll<HTMLElement>('.nt-lebego [role="option"]')].find(e => e.textContent?.includes('Jegyzet létrehozása'))!;
    await fireEvent.click(cel);
    await waitFor(() => expect(postok).toHaveLength(1));
    expect(postok[0]).toEqual({ url: '/api/vault/uj', body: { link: { cel: 'Ghost', forras: UTAK[0] } } });
    if (kod === 200) {
      await waitFor(() => expect(c.m.aktivFul!.ut).toBe('Core-selected/Ghost.md'));
      expect(c.m.aktivPanelId).toBe(c.forrasPanel);
      expect(c.grafPanel.fulek.find(f => f.id === c.ful.id)?.nezet?.tipus).toBe('graf');
    } else {
      await waitFor(() => expect(ertesitesek.lista.at(-1)?.szint).toBe('hiba'));
      expect(c.m.aktivFul!.ut).toBe(UTAK[0]);
      expect(ertesitesek.lista.at(-1)?.szoveg).toContain('Synthetic collision');
    }
  });
});
