import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { flushSync } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { alapParancsok } from '../src/alapParancsok';
import Valto from '../src/atfedes/Valto.svelte';
import Allapotsor from '../src/hej/Allapotsor.svelte';
import Fulsor from '../src/hej/Fulsor.svelte';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { Munkaterulet } from '../src/lib/elrendezes/munkaterulet.svelte';
import { SzovegStatisztika, statisztika, szovegetSzamol } from '../src/lib/elrendezes/szovegStatisztika.svelte';
import { ujJegyzetCel } from '../src/lib/elrendezes/ujJegyzet';
import { nyelv } from '../src/lib/i18n';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { Regiszter } from '../src/lib/parancsok/regiszter';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import { linkek } from '../src/lib/vault/linkek.svelte';

const utak = (m: Munkaterulet) => m.aktivPanel.fulek.map(f => f.ut);
const leiratkozok: (() => void)[] = [];
afterEach(() => {
  cleanup();
  leiratkozok.splice(0).forEach(le => le());
  document.body.textContent = '';
  vi.restoreAllMocks();
  nyelv.beallit('hu');
});
function kornyezet() {
  const felulet = new Felulet({ csend: { be: false } });
  const fajlok = new VaultFajlok();
  fajlok.beallit([{ ut: 'Folder/First.md', tipus: 'md', meret: 1, mtime: 1 }, { ut: 'Second.md', tipus: 'md', meret: 1, mtime: 2 }]);
  const kapcsolat = new CoreKapcsolat('ws://x');
  return { felulet, fajlok, kapcsolat, context: new Map([[KORNYEZET_KULCS, { felulet, fajlok, kapcsolat }]]) };
}

describe('F11 munkaterület', () => {
  it('a rögzített fül megmarad fájl- és önálló nézetnyitáskor, újraindításkor és visszanyitáskor', () => {
    const m = new Munkaterulet();
    m.megnyit('a.md'); m.rogzit();
    const id = m.aktivFul!.id;
    m.megnyit('b.md');
    expect(utak(m)).toEqual(['a.md', 'b.md']);
    expect(m.aktivFul!.id).not.toBe(id);
    m.aktival(m.aktivPanelId, id); m.megnyitNezet('graf');
    expect(utak(m)).toEqual(['a.md', null, 'b.md']);
    const uj = new Munkaterulet(m.sorosit());
    expect(uj.aktivPanel.fulek.find(f => f.id === id)?.rogzitett).toBe(true);
    uj.bezar(uj.aktivPanelId, id); uj.ujranyit();
    expect(uj.aktivFul).toMatchObject({ id, ut: 'a.md', rogzitett: true });
  });

  it('a csoportos zárás megőrzi a rögzített füleket és a bezártak visszanyithatók', () => {
    const m = new Munkaterulet();
    m.megnyit('a.md'); m.rogzit(); m.megnyit('b.md', 'ujful'); m.megnyit('c.md', 'ujful');
    const b = m.aktivPanel.fulek[1].id;
    m.aktival(m.aktivPanelId, b); m.bezarTobbit('jobb');
    expect(utak(m)).toEqual(['a.md', 'b.md']);
    m.ujranyit(); expect(m.aktivFul?.ut).toBe('c.md');
    m.aktival(m.aktivPanelId, b); m.bezarTobbit('tobbi');
    expect(utak(m)).toEqual(['a.md', 'b.md']);
    m.bezarTobbit('mind'); expect(utak(m)).toEqual(['a.md']);
    m.bezarPanel(); expect(utak(m)).toEqual([null]);
    m.ujranyit(); expect(m.aktivFul).toMatchObject({ ut: 'a.md', rogzitett: true });
  });

  it('a csoportzárás másik csoportot és a nézet saját állapotát megőrzi', () => {
    const m = new Munkaterulet(); m.megnyitNezet('graf', { mod: 'helyi', kozeppont: 'a.md' });
    m.oszt('sor'); expect(m.aktivFul?.nezet).toMatchObject({ tipus: 'graf', kozeppont: 'a.md' });
    expect(m.panelek()).toHaveLength(2);
    m.bezarPanel(); expect(m.panelek()).toHaveLength(1);
    expect(m.aktivFul?.nezet?.tipus).toBe('graf');
  });

  it('a panelirányok a beágyazott osztásokat követik, a szélen nem fordulnak körbe', () => {
    const m = new Munkaterulet(); const bal = m.aktivPanelId;
    m.oszt('sor'); const jobbFel = m.aktivPanelId;
    m.oszt('oszlop'); const jobbLe = m.aktivPanelId;
    m.panelIrany('fel'); expect(m.aktivPanelId).toBe(jobbFel);
    m.panelIrany('fel'); expect(m.aktivPanelId).toBe(jobbFel);
    m.panelIrany('le'); expect(m.aktivPanelId).toBe(jobbLe);
    m.panelIrany('bal'); expect(m.aktivPanelId).toBe(bal);
    m.panelIrany('bal'); expect(m.aktivPanelId).toBe(bal);
    m.panelIrany('jobb'); expect([jobbFel, jobbLe]).toContain(m.aktivPanelId);
  });

  it('a navigációs nyilak élő előzményt mutatnak, az új ág megszünteti az előrét', async () => {
    const k = kornyezet(), m = k.felulet.munkaterulet;
    render(Fulsor, { context: k.context, props: { panel: m.aktivPanel, aktivPanel: true, nezetId: 'n' } });
    expect((screen.getByRole('button', { name: 'Vissza az előző jegyzethez' }) as HTMLButtonElement).disabled).toBe(true);
    m.megnyit('a.md'); m.megnyit('b.md'); flushSync();
    const vissza = screen.getByRole('button', { name: 'Vissza az előző jegyzethez' });
    expect((vissza as HTMLButtonElement).disabled).toBe(false);
    await fireEvent.click(vissza); expect(m.aktivFul?.ut).toBe('a.md');
    expect((screen.getByRole('button', { name: 'Előre a következő jegyzethez' }) as HTMLButtonElement).disabled).toBe(false);
    m.megnyit('c.md'); flushSync();
    expect((screen.getByRole('button', { name: 'Előre a következő jegyzethez' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('a fülmenü billentyűzetről is elérhető és a rögzítés látható', async () => {
    const k = kornyezet(), m = k.felulet.munkaterulet;
    m.megnyit('a.md');
    render(Fulsor, { context: k.context, props: { panel: m.aktivPanel, aktivPanel: true, nezetId: 'n' } });
    await fireEvent.keyDown(screen.getByRole('tab'), { key: 'F10', shiftKey: true });
    await fireEvent.click(screen.getByRole('option', { name: 'Fül rögzítése' }));
    expect(m.aktivFul?.rogzitett).toBe(true);
    expect(screen.getByTitle('Rögzített fül')).toBeTruthy();
    await fireEvent.contextMenu(screen.getByRole('tab'), { clientX: 20, clientY: 30 });
    await fireEvent.click(screen.getByRole('option', { name: 'Fül rögzítésének feloldása' }));
    expect(m.aktivFul?.rogzitett).toBe(false);
  });

  it('Cmd+N valódi új jegyzetmezőt kér, nem új üres fület', async () => {
    const f = new Felulet(), reg = new Regiszter();
    leiratkozok.push(alapParancsok(reg, f));
    expect(reg.kap('fa.uj-jegyzet')?.billentyu).toBe('Mod+n');
    await reg.futtat('fa.uj-jegyzet', 'billentyu');
    expect(f.faUjJegyzet).toBe(true);
    expect(f.munkaterulet.aktivPanel.fulek).toHaveLength(1);
  });
});

describe('F11 gyorsváltó', () => {
  it('az alias külön találat, a valódi fájlt nyitja', async () => {
    vi.spyOn(linkek, 'aliasokKap').mockResolvedValue({ 'Folder/First.md': ['First alias'] });
    const k = kornyezet(); render(Valto, { context: k.context });
    const input = screen.getByRole('combobox');
    await fireEvent.input(input, { target: { value: 'alias' } });
    await vi.waitFor(() => expect(screen.getByRole('option').textContent).toContain('First alias'));
    await fireEvent.keyDown(input, { key: 'Enter', metaKey: true });
    expect(k.felulet.munkaterulet.aktivFul?.ut).toBe('Folder/First.md');
    expect(k.felulet.faUjJegyzet).toBe(false);
  });

  it('az ismert fájl tartalmi eseménye frissíti az aliasokat nyitott váltónál is, szerkezeti újraindex nélkül', async () => {
    const aliasok = vi.spyOn(linkek, 'aliasokKap').mockResolvedValue({ 'Folder/First.md': ['Mercury'] });
    const k = kornyezet();
    leiratkozok.push(linkek.figyel(k.kapcsolat, ut => !!k.fajlok.info(ut)));
    render(Valto, { context: k.context });
    const input = screen.getByRole('combobox');
    await fireEvent.input(input, { target: { value: 'Mercury' } });
    await vi.waitFor(() => expect(screen.getByRole('option').textContent).toContain('Mercury'));
    const verzio = linkek.verzio;
    aliasok.mockResolvedValue({ 'Folder/First.md': ['Jupiter'] });
    k.kapcsolat.szetoszt({ tipus: 'vault_valtozas', utak: ['Folder/First.md'] });
    await vi.waitFor(() => expect(aliasok).toHaveBeenCalledTimes(2));
    expect(linkek.verzio).toBe(verzio);
    await fireEvent.input(input, { target: { value: 'Jupiter' } });
    await vi.waitFor(() => expect(screen.getByRole('option').textContent).toContain('Jupiter'));
    await fireEvent.input(input, { target: { value: 'Mercury' } });
    expect(screen.queryAllByRole('option')).toHaveLength(0);
  });

  it('nincs találat → Enter, találat → ShiftEnter ugyanazt a névvel kitöltött kérést adja', async () => {
    vi.spyOn(linkek, 'aliasokKap').mockResolvedValue({});
    const k = kornyezet(); render(Valto, { context: k.context });
    const input = screen.getByRole('combobox');
    await fireEvent.input(input, { target: { value: 'New folder/New note.md' } });
    expect(screen.queryAllByRole('option')).toHaveLength(0);
    await fireEvent.keyDown(input, { key: 'Enter', metaKey: true, altKey: true });
    expect(k.felulet.faUjNev).toEqual({ nev: 'New note', mappa: 'New folder', mod: 'osztas' });
    expect(k.felulet.faUjJegyzet).toBe(true);
    k.felulet.faUjJegyzet = false; k.felulet.faUjNev = null;
    await fireEvent.input(input, { target: { value: 'First' } });
    expect(screen.getAllByRole('option')).not.toHaveLength(0);
    await fireEvent.keyDown(input, { key: 'Enter', shiftKey: true });
    expect(k.felulet.faUjNev).toEqual({ nev: 'First', mod: 'aktiv' });
  });

  it('az alias-API hibája nem blokkolja a fájlnév szerinti nyitást; tiltott név nem hoz létre', async () => {
    vi.spyOn(linkek, 'aliasokKap').mockRejectedValue(new Error('offline'));
    const k = kornyezet(); render(Valto, { context: k.context });
    const input = screen.getByRole('combobox');
    await fireEvent.input(input, { target: { value: '../escape' } });
    await fireEvent.keyDown(input, { key: 'Enter' });
    expect(k.felulet.faUjNev).toBe(null);
    expect(screen.getByRole('alert').textContent).toContain('érvényes');
    await fireEvent.input(input, { target: { value: 'Second' } });
    await fireEvent.keyDown(input, { key: 'Enter' });
    expect(k.felulet.munkaterulet.aktivFul?.ut).toBe('Second.md');
  });

  it('a név előkészítése megtartja az explicit mappát és kizárja a törött utakat', () => {
    expect(ujJegyzetCel(' Árvíz/Új jegyzet.MD ')).toEqual({ mappa: 'Árvíz', nev: 'Új jegyzet' });
    expect(ujJegyzetCel('Untitled')).toEqual({ nev: 'Untitled' });
    for (const q of ['', '/tmp/note', '../note', 'a//b', '.hidden/note', 'a/../b', 'name#fragment', 'a\\b', 'a/[link]', 'a/ b', 'a/']) expect(ujJegyzetCel(q), q).toBe(null);
  });
});

describe('F11 szavak és karakterek', () => {
  it('Unicode-szavak és látható karakterek; több kijelölésnél az átfedés egyszer számít', () => {
    expect(szovegetSzamol('Árvíz tűrő 👨‍👩‍👧‍👦 e\u0301')).toEqual({ szavak: 3, karakterek: 14 });
    const s = new SzovegStatisztika();
    s.frissit('f', 'a.md', 'one two three', [{ from: 0, to: 3 }, { from: 0, to: 7 }, { from: 8, to: 13 }]);
    expect(s.olvas('f', 'a.md')).toMatchObject({ szavak: 3, karakterek: 12, osszesKarakterek: 13, kijelolt: true });
    s.frissit('f', 'a.md', 'one two three', [{ from: 2, to: 2 }]);
    expect(s.olvas('f', 'a.md')).toMatchObject({ szavak: 3, karakterek: 13, kijelolt: false });
    expect(s.olvas('f', 'b.md')).toBeUndefined();
    s.torol('f'); expect(s.olvas('f', 'a.md')).toBeUndefined();
  });

  it('az állapotsor az aktív fül kijelölését követi; más nézetben nem mutat régi adatot', async () => {
    nyelv.beallit('en');
    const k = kornyezet(), m = k.felulet.munkaterulet;
    m.megnyit('a.md'); const id = m.aktivFul!.id;
    statisztika.frissit(id, 'a.md', 'one two', [{ from: 0, to: 3 }]);
    render(Allapotsor, { context: k.context });
    expect(screen.getByText('1 word')).toBeTruthy(); expect(screen.getByText('3 characters')).toBeTruthy();
    expect(screen.getByText('Selection:')).toBeTruthy();
    statisztika.frissit(id, 'a.md', 'one two'); flushSync();
    expect(screen.getByText('2 words')).toBeTruthy(); expect(screen.getByText('7 characters')).toBeTruthy();
    m.megnyitNezet('graf'); flushSync(); expect(screen.queryByText('2 words')).toBeNull();
    statisztika.torol(id);
  });
});
