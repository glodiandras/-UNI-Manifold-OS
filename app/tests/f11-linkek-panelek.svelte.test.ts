// F11 / 02-links-08…11: a jobb panel szűrőmezői, a kimenő linkeletlen említések („Linkelés”), a ⌘-hover előnézet a szerkesztőn kívül
// és a középső gombos megnyitás az Olvasóban, a beágyazott tartalomban és a panelben.

import { EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { cleanup, fireEvent, render, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Fa from '../src/hej/Fa.svelte';
import Oldalsav from '../src/hej/Oldalsav.svelte';
import JobbPanel from '../src/hej/JobbPanel.svelte';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { VaultFajlok, type FajlInfo } from '../src/lib/vault/fajlok.svelte';
import { BeagyazasWidget } from '../src/szerkeszto/beagyazas/widget';
import { chip } from '../src/szerkeszto/beagyazas/rajzol';
import Olvaso from '../src/szerkeszto/Olvaso.svelte';
import { Dokumentum } from '../src/szerkeszto/dokumentum/dokumentum.svelte';
import { elonezet, elonezetUtakra } from '../src/szerkeszto/linkek/elonezet';
import { navigacioBeallit } from '../src/szerkeszto/linkek/navigacio';
import { szerkesztok } from '../src/szerkeszto/szerkesztok.svelte';

const AKTIV = 'Matek/Mértani sorozat.md';
const SZOVEG = '# Mértani sorozat\n\nA Számtani sorozat is fontos.\n';
let lemez: Map<string, string>;
let kerelmek: string[];
let alak: 'wiki' | 'md';
const hash = (s: string) => `h${s.length}`;
const valasz = (adat: unknown, kod = 200) => new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });

beforeEach(() => {
  kerelmek = [];
  alak = 'wiki';
  lemez = new Map([[AKTIV, SZOVEG]]);
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://127.0.0.1/');
    kerelmek.push(u.pathname + u.search);
    switch (u.pathname) {
      case '/api/vault/visszahivatkozasok':
        return valasz({
          forrasok: [
            { ut: 'Matek/Számtani.md', linkek: [{ fajta: 'wiki', sor: 3, oszlop: 5, hossz: 19, alcel: null, alias: null, beagyazas: false, tulajdonsag: null, csomopont: null, kornyezet: 'Lásd [[Mértani sorozat]] is.' }] },
            { ut: 'X03 - Könyvek/Könyv.md', linkek: [{ fajta: 'wiki', sor: 2, oszlop: 9, hossz: 21, alcel: null, alias: null, beagyazas: false, tulajdonsag: null, csomopont: null, kornyezet: 'Sorozat: [[Mértani sorozat]]' }] },
          ],
        });
      case '/api/vault/emlitesek':
        return valasz({ forrasok: [{ ut: 'Történelem/Ókor.md', talalatok: [{ sor: 3, oszlop: 2, hossz: 15, szoveg: 'A mértani sorozat fontos.' }] }, { ut: 'Fizika/Hullám.md', talalatok: [{ sor: 1, oszlop: 0, hossz: 15, szoveg: 'mértani sorozat a hullámban' }] }] });
      case '/api/vault/jegyzet':
        return valasz({ linkek: [] });
      case '/api/vault/kimeno-emlitesek':
        return valasz({ forrasok: [{ ut: 'Matek/Számtani sorozat.md', talalatok: [{ sor: 3, oszlop: 2, hossz: 16, szoveg: 'A Számtani sorozat is fontos.', emlitett: 'Számtani sorozat' }] }] });
      case '/api/vault/linkcel':
        return valasz({ ut: 'x', cel: 'Számtani sorozat', alak, md: 'Sz%C3%A1mtani%20sorozat.md' });
      case '/api/vault/beagyazas':
        return valasz({ tipus: 'jegyzet', ut: u.searchParams.get('cel'), szoveg: '# Előnézet\n\nTartalom', kezd: 1, veg: 3 });
      case '/api/vault/fajl':
        if (init?.method === 'PUT') {
          const k = JSON.parse(String(init.body));
          lemez.set(k.ut, k.tartalom);
          return valasz({ ok: true, ut: k.ut, hash: hash(k.tartalom), jel: '', uzenet: 'mentve', pillanat: null, elotte: null, git: true });
        } else {
          const t = lemez.get(u.searchParams.get('ut')!);
          return t === undefined ? valasz({ hiba: 'nincs' }, 404) : valasz({ ut: u.searchParams.get('ut'), tartalom: t, hash: hash(t), jel: '', mtime: 0, kodolas_hiba: false });
        }
    }
    return valasz({ hiba: 'nincs' }, 404);
  });
});

afterEach(() => {
  cleanup();
  elonezet.zar();
  navigacioBeallit(null);
  ertesitesek.lista.length = 0;
  for (const ut of [AKTIV, 'Matek/Számtani sorozat.md']) szerkesztok.dokumentumok.eldob(ut);
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  document.body.textContent = '';
});

function panel() {
  const felulet = new Felulet({ csend: { be: false } });
  felulet.munkaterulet.megnyit(AKTIV);
  const kapcsolat = new CoreKapcsolat('ws://127.0.0.1:1/ws');
  const context = new Map<unknown, unknown>([[KORNYEZET_KULCS, { felulet, fajlok: new VaultFajlok(), kapcsolat }]]);
  return { ...render(JobbPanel, { context }), felulet };
}

const kimenoSzakasz = (c: HTMLElement) => c.querySelectorAll('section')[2];
const csoportok = (c: HTMLElement, szakasz: number) => [...c.querySelectorAll('section')[szakasz].querySelectorAll('li.forras .nev')].map((e) => e.textContent);

describe('02-links-11: szűrőmező a panelben', () => {
  it('visszahivatkozások: ékezet- és kisbetű-független, a találó jegyzet minden linkje marad; a számláló a láthatókat mutatja', async () => {
    const { container, getByLabelText } = panel();
    await waitFor(() => expect(csoportok(container, 0)).toHaveLength(2));
    const mezo = getByLabelText('Visszahivatkozások szűrése') as HTMLInputElement;
    await fireEvent.input(mezo, { target: { value: 'KONYV' } });
    expect(csoportok(container, 0)).toEqual(['Könyv']);
    expect(container.querySelectorAll('section')[0].textContent).toContain('1 link, 1 jegyzetből');
    await fireEvent.input(mezo, { target: { value: 'Lásd mértani' } }); // a link sora szerint is szűr
    expect(csoportok(container, 0)).toEqual(['Számtani']);
    await fireEvent.input(mezo, { target: { value: 'zzzz' } });
    expect(container.querySelectorAll('section')[0].textContent).toContain('Nincs találat.');
    await fireEvent.input(mezo, { target: { value: '' } });
    expect(csoportok(container, 0)).toHaveLength(2);
  });

  it('linkeletlen említések: a jegyzet neve vagy a sor szövege szerint', async () => {
    const { container, getByLabelText } = panel();
    await waitFor(() => expect(csoportok(container, 1)).toHaveLength(2));
    const mezo = getByLabelText('Említések szűrése') as HTMLInputElement;
    await fireEvent.input(mezo, { target: { value: 'hullam' } });
    expect(csoportok(container, 1)).toEqual(['Hullám']);
    await fireEvent.input(mezo, { target: { value: 'fontos' } });
    expect(csoportok(container, 1)).toEqual(['Ókor']);
  });
});

describe('02-links-10: kimenő linkeletlen említések', () => {
  it('a Kimenő linkek szakaszban jelennek meg, a Linkelés gomb a [[Cél]] linket írja az aktív jegyzetbe', async () => {
    const { container } = panel();
    await waitFor(() => expect(container.textContent).toContain('Említett, még nem linkelt jegyzetek'));
    const kimeno = container.querySelectorAll('section')[2];
    expect(kimeno.querySelector('.fej .nev')!.textContent).toBe('Számtani sorozat');
    const gomb = kimeno.querySelector<HTMLButtonElement>('button.linkel')!;
    await fireEvent.click(gomb);
    await waitFor(() => expect(lemez.get(AKTIV)).toBe('# Mértani sorozat\n\nA [[Számtani sorozat]] is fontos.\n'));
    expect(kerelmek.some((k) => k.startsWith('/api/vault/linkcel'))).toBe(true);
  });

  it('„Use [[Wikilinks]]” kikapcsolva a Linkelés markdown-linket ír', async () => {
    alak = 'md';
    const { container } = panel();
    await waitFor(() => expect(kimenoSzakasz(container).querySelector('button.linkel')).not.toBeNull());
    await fireEvent.click(kimenoSzakasz(container).querySelector<HTMLButtonElement>('button.linkel')!);
    await waitFor(() => expect(lemez.get(AKTIV)).toBe('# Mértani sorozat\n\nA [Számtani sorozat](Sz%C3%A1mtani%20sorozat.md) is fontos.\n'));
  });

  it('elavult sor (közben megváltozott a jegyzet) esetén nem ír', async () => {
    const { container } = panel();
    await waitFor(() => expect(kimenoSzakasz(container).querySelector('button.linkel')).not.toBeNull());
    lemez.set(AKTIV, '# Mértani sorozat\n\nMás szöveg.\n');
    await fireEvent.click(kimenoSzakasz(container).querySelector<HTMLButtonElement>('button.linkel')!);
    await waitFor(() => expect(ertesitesek.lista.at(-1)?.cim).toContain('megváltozott'));
    expect(lemez.get(AKTIV)).toBe('# Mértani sorozat\n\nMás szöveg.\n');
  });
});

describe('02-links-09: ⌘-hover előnézet a szerkesztőn kívül', () => {
  it('a panel sorain ⌘ nyomva a célt mutatja (a teljes vault-út a cél, a forrás egy képzeletbeli út)', async () => {
    const { container } = panel();
    await waitFor(() => expect(container.querySelector('li.forras[data-elonezet-ut]')).not.toBeNull());
    const sor = container.querySelector<HTMLElement>('li.forras[data-elonezet-ut="Matek/Számtani.md"]')!;
    await fireEvent.mouseMove(sor.querySelector('.fej')!, { metaKey: true });
    await waitFor(() => expect(document.querySelector('.link-elonezet')).not.toBeNull(), { timeout: 2000 });
    await waitFor(() => expect(document.querySelector('.link-elonezet')!.textContent).toContain('Előnézet'));
    expect(kerelmek.some((k) => k.startsWith('/api/vault/beagyazas?') && k.includes('forras=.preview') && k.includes('cel=Matek%2FSz%C3%A1mtani.md'))).toBe(true);
  });

  it('⌘ nélkül nincs előnézet', async () => {
    const { container } = panel();
    await waitFor(() => expect(container.querySelector('li.forras[data-elonezet-ut]')).not.toBeNull());
    await fireEvent.mouseMove(container.querySelector('li.forras .fej')!, {});
    await new Promise((r) => setTimeout(r, 450));
    expect(document.querySelector('.link-elonezet')).toBeNull();
  });

  it('a fájlfa fájl-során ⌘-hoverre előnézet, a mappa-soron nincs', async () => {
    const felulet = new Felulet({}), fajlok = new VaultFajlok();
    fajlok.mappak = ['Matek'];
    const fi = (ut: string): FajlInfo => ({ ut, mtime: 1, tipus: 'md', meret: 1 });
    fajlok.beallit([fi('Matek/Számtani.md'), fi('Jegyzet.md')]);
    vi.spyOn(fajlok, 'frissit').mockResolvedValue();
    const context = new Map([[KORNYEZET_KULCS, { felulet, fajlok, kapcsolat: new CoreKapcsolat('ws://synthetic') }]]);
    const { container } = render(Fa, { context });
    const fajl = await waitFor(() => {
      const e = container.querySelector<HTMLElement>('[data-fa-ut="Jegyzet.md"]');
      expect(e).not.toBeNull();
      return e!;
    });
    const mappa = container.querySelector<HTMLElement>('[data-fa-ut="Matek"]')!;
    await fireEvent.mouseMove(mappa, { metaKey: true });
    await new Promise((r) => setTimeout(r, 450));
    expect(document.querySelector('.link-elonezet')).toBeNull();
    await fireEvent.mouseMove(fajl, { metaKey: true });
    await waitFor(() => expect(document.querySelector('.link-elonezet')).not.toBeNull(), { timeout: 2000 });
    expect(kerelmek.some((k) => k.startsWith('/api/vault/beagyazas?') && k.includes('cel=Jegyzet.md'))).toBe(true);
  });

  it('a keresési találat fejlécén ⌘-hoverre előnézet', async () => {
    const felulet = new Felulet({ kenyelmiVerzio: 1, csend: { be: false }, oldalsav: { nyitva: true, nezet: 'kereses' } });
    const fajlok = new VaultFajlok();
    fajlok.beallit([{ ut: 'Alpha.md', tipus: 'md', meret: 1, mtime: 1 }]);
    const eredeti = fetch;
    vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
      const u = new URL(url, 'http://127.0.0.1/');
      if (u.pathname.includes('kereses')) return valasz({ q: 'alpha', osszes: 1, talalatok: [{ ut: 'Alpha.md', pont: 1, talalatok: [{ sor: 1, oszlop: 0, hossz: 5, szoveg: 'alpha example' }] }] });
      if (u.pathname === '/api/vault/cimkek') return valasz({ cimkek: [] });
      return eredeti(url, init);
    });
    const { container } = render(Oldalsav, { context: new Map([[KORNYEZET_KULCS, { felulet, fajlok, kapcsolat: new CoreKapcsolat('ws://synthetic') }]]) });
    await fireEvent.input(container.querySelector('[role="combobox"]')!, { target: { value: 'alpha' } });
    const fejlec = await waitFor(() => {
      const e = container.querySelector<HTMLElement>('.fejlec[data-elonezet-ut="Alpha.md"]');
      expect(e).not.toBeNull();
      return e!;
    });
    await fireEvent.mouseMove(fejlec, { metaKey: true });
    await waitFor(() => expect(document.querySelector('.link-elonezet')).not.toBeNull(), { timeout: 2000 });
    expect(kerelmek.some((k) => k.startsWith('/api/vault/beagyazas?') && k.includes('cel=Alpha.md'))).toBe(true);
  });

  it('elonezetUtakra: egyedi szelektor és út-függvény (a fa mappa-sora kimarad)', async () => {
    const gyoker = document.createElement('div');
    gyoker.innerHTML = '<div class="s" data-fa-ut="Mappa" data-fa-mappa="true"><b>m</b></div><div class="s" data-fa-ut="Mappa/Jegyzet.md" data-fa-mappa="false"><b>f</b></div>';
    document.body.append(gyoker);
    const le = elonezetUtakra(gyoker, { valaszto: '[data-fa-ut]', ut: (e) => (e.dataset.faMappa === 'true' ? null : (e.dataset.faUt ?? null)) });
    gyoker.querySelectorAll('b')[0].dispatchEvent(new MouseEvent('mousemove', { bubbles: true, metaKey: true }));
    await new Promise((r) => setTimeout(r, 450));
    expect(document.querySelector('.link-elonezet')).toBeNull();
    gyoker.querySelectorAll('b')[1].dispatchEvent(new MouseEvent('mousemove', { bubbles: true, metaKey: true }));
    await waitFor(() => expect(document.querySelector('.link-elonezet')).not.toBeNull(), { timeout: 2000 });
    le();
    expect(document.querySelector('.link-elonezet')).toBeNull(); // a leiratkozás bezárja
  });
});

describe('02-links-08: középső gomb új fület nyit', () => {
  it('a panel soraiban', async () => {
    const { container, felulet } = panel();
    await waitFor(() => expect(container.querySelectorAll('section')[0].querySelector('li.forras .link')).not.toBeNull());
    const megnyit = vi.spyOn(felulet.munkaterulet, 'megnyit');
    const fej = container.querySelectorAll('section')[0].querySelector('li.forras .fej')!;
    await fireEvent(fej, new MouseEvent('auxclick', { bubbles: true, button: 2 }));
    expect(megnyit).not.toHaveBeenCalled(); // a jobb gomb nem nyit
    await fireEvent(container.querySelectorAll('section')[0].querySelector('li.forras .link')!, new MouseEvent('auxclick', { bubbles: true, button: 1 }));
    expect(megnyit).toHaveBeenCalledWith('Matek/Számtani.md', 'ujful');
  });

  it('az Olvasóban a linken; a bal gomb ⌘ nélkül az aktív fülben', async () => {
    const megnyit = vi.fn();
    navigacioBeallit({ megnyit });
    const szoveg = 'Lásd [[Target]] is.';
    const view = new EditorView({ state: EditorState.create({ doc: szoveg }) });
    const dok = new Dokumentum({ olvas: vi.fn(), ir: vi.fn() }, { ut: 'Host.md', tartalom: szoveg, hash: 'h', jel: '', mtime: 0 });
    const { container } = render(Olvaso, { props: { view, dok, ut: 'Host.md', valtozat: 0 } });
    const wl = container.querySelector<HTMLElement>('.wikilink[data-cel]')!;
    expect(wl).not.toBeNull();
    const le = new MouseEvent('mousedown', { bubbles: true, cancelable: true, button: 1 });
    wl.dispatchEvent(le);
    expect(le.defaultPrevented).toBe(true); // nincs automatikus görgetés
    await fireEvent(wl, new MouseEvent('auxclick', { bubbles: true, button: 1 }));
    await waitFor(() => expect(megnyit).toHaveBeenCalledWith('Target', 'ujful', null));
    view.destroy();
  });

  it('a beágyazott tartalom chipjén és a Live Preview widget linkjén', async () => {
    const megnyit = vi.fn();
    navigacioBeallit({ megnyit });
    const kont = document.createElement('span');
    chip({ tipus: 'canvas', ut: 'Rajz.canvas' }, { cel: 'Rajz', alcel: null, alias: null, beagyazas: true, from: 0, to: 0 }, kont, { forras: 'Host.md' });
    document.body.append(kont);
    await fireEvent(kont.querySelector('a.beagyazas-cim')!, new MouseEvent('auxclick', { bubbles: true, button: 1 }));
    await waitFor(() => expect(megnyit).toHaveBeenCalledWith('Rajz', 'ujful', null));
    megnyit.mockClear();

    const view = new EditorView({ state: EditorState.create({ doc: '![[Target]]' }), parent: document.body });
    const w = new BeagyazasWidget({ cel: 'Target', alcel: null, alias: null, beagyazas: true, from: 0, to: 11 }, 'Host.md', 0, true);
    const dom = w.toDOM(view);
    document.body.append(dom);
    const belso = document.createElement('span');
    belso.className = 'wikilink';
    belso.dataset.cel = 'Masik';
    belso.dataset.forras = 'Host.md';
    dom.append(belso);
    const le = new MouseEvent('mousedown', { bubbles: true, cancelable: true, button: 1 });
    belso.dispatchEvent(le);
    expect(le.defaultPrevented).toBe(true);
    await waitFor(() => expect(megnyit).toHaveBeenCalledWith('Masik', 'ujful', null));
    view.destroy();
  });
});
