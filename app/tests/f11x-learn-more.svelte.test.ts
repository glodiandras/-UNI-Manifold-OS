// F11 (4. tétel): a Health „Learn more” az útmutató megfelelő oldalát és szakaszát hozza (core `GET /api/doku/learn`), a munkatér
// másolata fülben nyílik; elérhetetlen útmutatónál a beépített magyarázat marad. A szakasz-megjelenítő a valódi útmutató minden
// oldalán maradék Markdown-jelölés nélkül rajzol.
import { cleanup, fireEvent, render, waitFor, within } from '@testing-library/svelte';
import { readdirSync, readFileSync } from 'node:fs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Egeszseg from '../src/egeszseg/Egeszseg.svelte';
import { ApiHiba } from '../src/lib/core/api';
import { egeszsegApi } from '../src/lib/egeszseg/api';
import { EgeszsegTar } from '../src/lib/egeszseg/allapot.svelte';
import { blokkok, sorElemez } from '../src/lib/egeszseg/dokuSzakasz';
import type { DokuCel, EgeszsegSor } from '../src/lib/egeszseg/tipusok';
import { nyelv } from '../src/lib/i18n';

const sor = (kod: string, allapot: EgeszsegSor['allapot'], uzenet: string): EgeszsegSor =>
  ({ kod, cim: kod, allapot, uzenet_kod: `${kod}.x`, param: {}, uzenet, javitas: null, reszletek: [] });
const cel = (extra: Partial<DokuCel> = {}): DokuCel => ({
  tema: 'health.index', oldal: { azonosito: 'health', fajl: 'HEALTH-AND-TROUBLESHOOTING.md', cim: 'Health & troubleshooting' }, horgony: 'search-index',
  fejlec: 'Search index', szakasz: 'The search index is a fast lookup.\n\n- **Fix automatically** sets it aside\n- rebuilds it\n\n| Status | Meaning |\n|---|---|\n| **Healthy** | Nothing to do |\n',
  munkater_ut: null, ...extra,
});
let tar: EgeszsegTar;
async function megnyit(props: Record<string, unknown> = {}) {
  vi.spyOn(egeszsegApi, 'betolt').mockResolvedValue({ verzio: 1, zold: true, osszesen: { ok: 2, info: 0, figyelem: 0, hiba: 0 }, ellenorzesek: [sor('index', 'ok', 'Fine.'), sor('lemezhely', 'ok', 'Enough space.')] });
  tar = new EgeszsegTar();
  render(Egeszseg, { props: { tar, onbezar: vi.fn(), ...props } });
  await waitFor(() => expect(tar.adat).not.toBeNull());
}
const sorElem = (kod: string) => document.querySelector<HTMLElement>(`[data-ellenorzes="${kod}"]`)!;

beforeEach(() => nyelv.beallit('en'));
afterEach(() => { cleanup(); vi.restoreAllMocks(); nyelv.beallit('hu'); });

describe('Health: Learn more az útmutatóra', () => {
  it('a Learn more az ellenőrzés útmutató-szakaszát kéri, megmutatja az oldal és a szakasz nevét, a szakasz kinyitható', async () => {
    const ker = vi.spyOn(egeszsegApi, 'tudjMeg').mockResolvedValue(cel());
    await megnyit();
    await fireEvent.click(within(sorElem('index')).getByRole('button', { name: 'Learn more' }));
    await waitFor(() => expect(sorElem('index').querySelector('[data-utmutato]')).not.toBeNull());
    expect(ker).toHaveBeenCalledWith('index');
    expect(sorElem('index').querySelector('[data-utmutato]')!.textContent).toBe('Guide: Health & troubleshooting › Search index');
    expect(sorElem('index').querySelector('[data-doku-szakasz]')).toBeNull();               // kinyitás előtt nincs szakasz
    await fireEvent.click(sorElem('index').querySelector('[data-utmutato-mutat]')!);
    const sz = sorElem('index').querySelector<HTMLElement>('[data-doku-szakasz]')!;
    expect(sz.querySelector('strong')!.textContent).toBe('Fix automatically');
    expect(sz.querySelectorAll('li')).toHaveLength(2);
    expect(sz.querySelector('table th')!.textContent).toBe('Status');
    expect(sz.textContent).not.toContain('**');
    await fireEvent.click(sorElem('index').querySelector('[data-utmutato-mutat]')!);
    expect(sorElem('index').querySelector('[data-doku-szakasz]')).toBeNull();                // újra kattintva elrejti
  });

  it('ha a munkatér tartalmazza az útmutatót, a gomb a jegyzetét nyitja (és nem rajzol szakaszt)', async () => {
    vi.spyOn(egeszsegApi, 'tudjMeg').mockResolvedValue(cel({ munkater_ut: 'Manifold Guide/Health and troubleshooting.md' }));
    const onjegyzet = vi.fn();
    await megnyit({ onjegyzet });
    await fireEvent.click(within(sorElem('index')).getByRole('button', { name: 'Learn more' }));
    const gomb = await waitFor(() => { const g = sorElem('index').querySelector<HTMLElement>('[data-utmutato-megnyit]'); expect(g).not.toBeNull(); return g!; });
    expect(gomb.textContent).toBe('Open the guide page');
    await fireEvent.click(gomb);
    expect(onjegyzet).toHaveBeenCalledWith('Manifold Guide/Health and troubleshooting.md');
    expect(sorElem('index').querySelector('[data-utmutato-mutat]')).toBeNull();
  });

  it('elérhetetlen útmutatónál a beépített magyarázat marad, hibajelzés és útmutató-gomb nélkül; a következő megnyitás újrapróbál', async () => {
    const ker = vi.spyOn(egeszsegApi, 'tudjMeg').mockRejectedValueOnce(new ApiHiba(404, 'The guide page is not installed.', { kod: 'doku.nincs_oldal' })).mockResolvedValue(cel({ tema: 'health.lemezhely' }));
    await megnyit();
    const gomb = within(sorElem('lemezhely')).getByRole('button', { name: 'Learn more' });
    await fireEvent.click(gomb);
    await waitFor(() => expect(ker).toHaveBeenCalledTimes(1));
    expect(sorElem('lemezhely').querySelector('[data-panel="tudj"]')!.textContent).toMatch(/disk/i);
    expect(sorElem('lemezhely').querySelector('[data-utmutato]')).toBeNull();
    await fireEvent.click(gomb);                                                             // becsuk
    await fireEvent.click(gomb);                                                             // újra nyit: újrapróbál
    await waitFor(() => expect(sorElem('lemezhely').querySelector('[data-utmutato]')).not.toBeNull());
    expect(ker).toHaveBeenCalledTimes(2);
  });
});

describe('az útmutató-szakasz modellje', () => {
  it('a soron belüli jelölések és a link szövege', () => {
    expect(sorElemez('a `b` **c** *d* [e](F.md#x)')).toEqual([
      { t: 'szoveg', s: 'a ' }, { t: 'kod', s: 'b' }, { t: 'szoveg', s: ' ' }, { t: 'felkover', s: 'c' }, { t: 'szoveg', s: ' ' },
      { t: 'dolt', s: 'd' }, { t: 'szoveg', s: ' ' }, { t: 'szoveg', s: 'e' },
    ]);
  });

  it('blokkok: cím, bekezdés (összefűzve), lista, táblázat, callout, kódblokk — HTML-nek semmi nem megy át', () => {
    const b = blokkok('### Cím\n\nelső\nsor\n\n1. egy\n2. kettő\n\n| A | B |\n|---|---|\n| x | `y` |\n\n> [!note] Figyelem\n> szöveg\n\n```\n<b>nem html</b>\n```\n');
    expect(b.map((x) => x.t)).toEqual(['cim', 'bekezdes', 'lista', 'tabla', 'idezet', 'kod']);
    expect(b[1]).toEqual({ t: 'bekezdes', sor: [{ t: 'szoveg', s: 'első sor' }] });
    expect(b[2]).toMatchObject({ t: 'lista', rendezett: true });
    expect(b[3]).toMatchObject({ t: 'tabla' });
    expect(b[4]).toEqual({ t: 'idezet', sorok: [[{ t: 'felkover', s: 'Figyelem' }], [{ t: 'szoveg', s: 'szöveg' }]] });
    expect(b[5]).toEqual({ t: 'kod', szoveg: '<b>nem html</b>' });
  });

  it('a valódi útmutató mind a 16 oldala maradék jelölés (táblázatsor, **, fejléc-#) nélkül bontható', () => {
    const mappa = `${(import.meta as unknown as { dirname: string }).dirname}/../../docs/user`;
    const fajlok = readdirSync(mappa).filter((f) => f.endsWith('.md'));
    expect(fajlok).toHaveLength(16);
    for (const f of fajlok) {
      const szoveg = readFileSync(`${mappa}/${f}`, 'utf8').replace(/<!--[\s\S]*?-->/g, '');
      const sz = (s: { t: string; s: string }[]) => s.map((r) => r.s).join('');
      for (const b of blokkok(szoveg)) {
        const mind: string[] = b.t === 'bekezdes' || b.t === 'cim' ? [sz(b.sor)]
          : b.t === 'lista' ? b.elemek.map(sz) : b.t === 'tabla' ? [...b.fejlec.map(sz), ...b.sorok.flat().map(sz)]
          : b.t === 'idezet' ? b.sorok.map(sz) : [];
        for (const s of mind) {
          expect(s, `${f}: ${s.slice(0, 40)}`).not.toMatch(/\*\*|^\|\s|^#{1,6}\s|^```/);
        }
      }
    }
  });
});
