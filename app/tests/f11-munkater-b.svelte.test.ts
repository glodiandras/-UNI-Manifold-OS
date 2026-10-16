// F11 workspace, second batch (06-workspace-02/08/12/17/24/26/28): tab-to-edge split, linked tab groups, ribbon
// configuration, backlinks count, navigation history list, named layouts and UI zoom. Synthetic data only.
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { flushSync } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { alapParancsok } from '../src/alapParancsok';
import Elrendezesek from '../src/atfedes/Elrendezesek.svelte';
import Allapotsor from '../src/hej/Allapotsor.svelte';
import Fulsor from '../src/hej/Fulsor.svelte';
import Hej from '../src/hej/Hej.svelte';
import Ikonsav from '../src/hej/Ikonsav.svelte';
import Panel from '../src/hej/Panel.svelte';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet, MAX_ELRENDEZES, NAGYITAS } from '../src/lib/elrendezes/felulet.svelte';
import { fulHuzas, HUZAS_TIPUS, huzasZona } from '../src/lib/elrendezes/fulHuzas.svelte';
import { IKONSAV_ALAP, ikonAthelyez, ikonMozgat, ikonsavElemek, ikonsavErvenyes } from '../src/lib/elrendezes/ikonsav';
import { Munkaterulet } from '../src/lib/elrendezes/munkaterulet.svelte';
import { nagyitasAlkalmaz } from '../src/lib/elrendezes/nagyitas';
import { nyelv } from '../src/lib/i18n';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { kezel } from '../src/lib/parancsok/kezelo';
import { Regiszter, regiszter } from '../src/lib/parancsok/regiszter';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';

const leiratkozok: (() => void)[] = [];
beforeEach(() => { nyelv.beallit('hu'); });
afterEach(() => {
  cleanup();
  leiratkozok.splice(0).forEach((le) => le());
  fulHuzas.fulId = null;
  document.body.textContent = '';
  document.documentElement.style.removeProperty('zoom');
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  nyelv.beallit('hu');
});

function kornyezet(mentett: unknown = { csend: { be: false } }) {
  const felulet = new Felulet(mentett);
  const fajlok = new VaultFajlok();
  fajlok.beallit([{ ut: 'a.md', tipus: 'md', meret: 1, mtime: 1 }, { ut: 'b.md', tipus: 'md', meret: 1, mtime: 2 }]);
  const kapcsolat = new CoreKapcsolat('ws://x');
  return { felulet, fajlok, kapcsolat, context: new Map<unknown, unknown>([[KORNYEZET_KULCS, { felulet, fajlok, kapcsolat }]]) };
}
const utak = (m: Munkaterulet, panelIndex = 0) => m.panelek()[panelIndex].fulek.map((f) => f.ut);

describe('06-workspace-02: fül húzása panel-szélre = osztás', () => {
  it('a zóna a pointer helyéből: négy szél és a közép, sarokban a közelebbi szél', () => {
    expect(huzasZona(5, 100, 400, 300)).toBe('bal');
    expect(huzasZona(395, 100, 400, 300)).toBe('jobb');
    expect(huzasZona(200, 4, 400, 300)).toBe('fel');
    expect(huzasZona(200, 296, 400, 300)).toBe('le');
    expect(huzasZona(200, 150, 400, 300)).toBe('kozep');
    expect(huzasZona(2, 40, 400, 300)).toBe('bal');
    expect(huzasZona(0, 0, 0, 0)).toBe('kozep');
  });

  it.each([
    ['bal', 'sor', true], ['jobb', 'sor', false], ['fel', 'oszlop', true], ['le', 'oszlop', false],
  ] as const)('a %s szélre ejtett fül új panelbe kerül (%s osztás), a forrás füleit nem viszi', (irany, tengely, elol) => {
    const m = new Munkaterulet();
    m.megnyit('a.md'); m.megnyit('b.md', 'ujful'); m.rogzit();
    const b = m.aktivFul!, aPanel = m.aktivPanelId;
    expect(m.athelyezOsztasba(b.id, aPanel, irany)).toBe(true);
    const gyoker = m.gyoker;
    expect(gyoker.tipus).toBe('osztas');
    if (gyoker.tipus !== 'osztas') return;
    expect(gyoker.irany).toBe(tengely);
    const uj = (elol ? gyoker.a : gyoker.b), regi = (elol ? gyoker.b : gyoker.a);
    expect(uj.tipus === 'panel' && uj.fulek.map((f) => f.ut)).toEqual(['b.md']);
    expect(regi.tipus === 'panel' && regi.fulek.map((f) => f.ut)).toEqual(['a.md']);
    expect(m.aktivPanelId).toBe(uj.id);
    expect(m.aktivFul).toMatchObject({ id: b.id, rogzitett: true }); // a fül saját állapota megmarad
  });

  it('másik panelből húzva az üressé váló forráspanel összehúzódik; az egyetlen fül a saját szélére nem oszt', () => {
    const m = new Munkaterulet();
    m.megnyit('a.md'); m.oszt('sor', false); m.megnyit('b.md');
    const [bal, jobb] = m.panelek();
    expect(m.athelyezOsztasba(jobb.fulek[0].id, bal.id, 'le')).toBe(true);
    expect(m.panelek().map((p) => p.fulek.map((f) => f.ut))).toEqual([['a.md'], ['b.md']]);
    expect(m.gyoker.tipus === 'osztas' && m.gyoker.irany).toBe('oszlop'); // a vízszintes osztás eltűnt
    const egyedul = new Munkaterulet();
    egyedul.megnyit('x.md');
    expect(egyedul.athelyezOsztasba(egyedul.aktivFul!.id, egyedul.aktivPanelId, 'jobb')).toBe(false);
    expect(egyedul.panelek().length).toBe(1);
    expect(egyedul.athelyezOsztasba('nincs', egyedul.aktivPanelId, 'jobb')).toBe(false);
  });

  it('a Panel szélzónái csak fülhúzás közben látszanak; a drop a kiválasztott irányba oszt, a közép fülcsoportba ejt', async () => {
    const k = kornyezet(), m = k.felulet.munkaterulet;
    m.megnyit('a.md'); m.megnyit('b.md', 'ujful');
    const panel = m.aktivPanel;
    render(Panel, { context: k.context, props: { panel } });
    expect(document.querySelector('[data-huzas-reteg]')).toBeNull();
    const b = m.aktivFul!.id;
    fulHuzas.fulId = b; flushSync();
    const reteg = document.querySelector<HTMLElement>('[data-huzas-reteg]')!;
    reteg.getBoundingClientRect = () => ({ left: 0, top: 0, width: 400, height: 300, right: 400, bottom: 300, x: 0, y: 0, toJSON() {} });
    const dataTransfer = { types: [HUZAS_TIPUS], getData: () => b, dropEffect: '' };
    const esemeny = (tipus: string, clientX: number, clientY: number) => Object.assign(new Event(tipus, { bubbles: true, cancelable: true }), { dataTransfer, clientX, clientY });
    await fireEvent(reteg, esemeny('dragover', 395, 100));
    expect(reteg.querySelector('[data-zona]')?.getAttribute('data-zona')).toBe('jobb');
    await fireEvent(reteg, esemeny('drop', 395, 100));
    expect(m.panelek().length).toBe(2);
    expect(utak(m, 0)).toEqual(['a.md']);
    expect(utak(m, 1)).toEqual(['b.md']);
    expect(fulHuzas.fulId).toBeNull();
  });

  it('a Fulsor fülmenüje billentyűzetről is új csoportba helyezi a fület', async () => {
    const k = kornyezet(), m = k.felulet.munkaterulet;
    m.megnyit('a.md'); m.megnyit('b.md', 'ujful');
    render(Fulsor, { context: k.context, props: { panel: m.aktivPanel, aktivPanel: true, nezetId: 'n' } });
    await fireEvent.keyDown(screen.getAllByRole('tab')[1], { key: 'F10', shiftKey: true });
    await fireEvent.click(screen.getByRole('option', { name: 'Fül áthelyezése új csoportba jobbra' }));
    expect(m.panelek().map((p) => p.fulek.map((f) => f.ut))).toEqual([['a.md'], ['b.md']]);
  });
});

describe('06-workspace-08: összekapcsolt fülcsoportok', () => {
  function ketPanel() {
    const m = new Munkaterulet();
    m.megnyit('a.md'); m.oszt('sor', false);
    const [bal, jobb] = m.panelek();
    return { m, bal, jobb };
  }

  it('az összekapcsolt csoportok közös fájlnyitást kapnak, a nem kapcsoltak nem', () => {
    const { m, bal, jobb } = ketPanel();
    m.osszekapcsol(bal.id, jobb.id);
    m.aktival(bal.id); m.megnyit('b.md');
    expect(m.panel(jobb.id)!.fulek.map((f) => f.ut)).toContain('b.md');
    expect(m.panel(jobb.id)!.fulek.find((f) => f.id === m.panel(jobb.id)!.aktiv)!.ut).toBe('b.md');
    m.aktival(jobb.id); m.megnyit('c.md');
    expect(m.panel(bal.id)!.fulek.find((f) => f.id === m.panel(bal.id)!.aktiv)!.ut).toBe('c.md');
    m.lekapcsol(jobb.id);
    expect(m.kapcsoltTarsak(bal.id)).toEqual([]);
    m.aktival(bal.id); m.megnyit('d.md');
    expect(m.panel(jobb.id)!.fulek.some((f) => f.ut === 'd.md')).toBe(false);
  });

  it('a tükrözés nem visszhangzik, megnyitási előzményt és a legutóbbiak listáját egyszer frissíti', () => {
    const k = kornyezet(), m = k.felulet.munkaterulet;
    m.megnyit('a.md'); m.oszt('sor', false);
    const [bal, jobb] = m.panelek();
    m.osszekapcsol(bal.id, jobb.id);
    m.aktival(bal.id); m.megnyit('b.md');
    expect(k.felulet.legutobbiFajlok[0]).toBe('b.md');
    expect(m.panel(bal.id)!.fulek.length + m.panel(jobb.id)!.fulek.length).toBeLessThanOrEqual(3);
  });

  it('a kapcsolat mentődik és újratöltődik; hibás azonosítót az ellenőrzés eldob', () => {
    const { m, bal, jobb } = ketPanel();
    m.osszekapcsol(bal.id, jobb.id);
    const mentett = JSON.parse(JSON.stringify(m.sorosit()));
    const uj = new Munkaterulet(mentett);
    expect(uj.kapcsoltTarsak(bal.id).map((p) => p.id)).toEqual([jobb.id]);
    mentett.gyoker.a.kapcsolt = '<script>';
    expect(new Munkaterulet(mentett).panel(bal.id)!.kapcsolt).toBeUndefined();
  });

  it('a kapcsolt panel fülsorán ikon jelzi a kapcsolatot, a fülmenüből leválasztható', async () => {
    const k = kornyezet(), m = k.felulet.munkaterulet;
    m.megnyit('a.md'); m.oszt('sor', false);
    const [bal, jobb] = m.panelek();
    render(Fulsor, { context: k.context, props: { panel: bal, aktivPanel: true, nezetId: 'n' } });
    expect(screen.queryByRole('img', { name: 'Összekapcsolt fülcsoport' })).toBeNull();
    await fireEvent.keyDown(screen.getAllByRole('tab')[0], { key: 'F10', shiftKey: true });
    await fireEvent.click(screen.getByRole('option', { name: 'Fülcsoport összekapcsolása…' })); // egyetlen társ: azonnal összekapcsol
    expect(m.kapcsoltTarsak(bal.id).map((p) => p.id)).toEqual([jobb.id]);
    expect(await screen.findByRole('img', { name: 'Összekapcsolt fülcsoport' })).toBeTruthy();
    await fireEvent.keyDown(screen.getAllByRole('tab')[0], { key: 'F10', shiftKey: true });
    await fireEvent.click(screen.getByRole('option', { name: 'Fülcsoport leválasztása' }));
    expect(m.kapcsoltTarsak(bal.id)).toEqual([]);
  });

  it('a görgetés aránya követi a társcsoportot, de nem pattog vissza; kapcsolat nélkül nem szinkronizál', async () => {
    const k = kornyezet(), m = k.felulet.munkaterulet;
    m.megnyit('a.md'); m.oszt('sor', false);
    const [bal, jobb] = m.panelek();
    render(Panel, { context: k.context, props: { panel: bal } });
    render(Panel, { context: k.context, props: { panel: jobb } });
    const [elso, masodik] = [...document.querySelectorAll<HTMLElement>('.nezet')];
    for (const e of [elso, masodik]) {
      Object.defineProperty(e, 'scrollHeight', { value: 1100, configurable: true });
      Object.defineProperty(e, 'clientHeight', { value: 100, configurable: true });
    }
    elso.scrollTop = 500;
    await fireEvent.scroll(elso);
    expect(masodik.scrollTop).toBe(0); // nincs kapcsolat: nincs szinkron
    m.osszekapcsol(bal.id, jobb.id); flushSync();
    elso.scrollTop = 250; // az arány 25 %
    await fireEvent.scroll(elso);
    expect(masodik.scrollTop).toBe(250);
    elso.scrollTop = 0;
    await fireEvent.scroll(masodik); // a visszhang ideje alatt a társ görgetése nem indít újat
    expect(elso.scrollTop).toBe(0);
  });

  it('a ⌘P-parancsok: összekapcsolás csak több csoportnál, leválasztás csak kapcsolt csoportnál', () => {
    const f = new Felulet({ csend: { be: false } }), reg = new Regiszter();
    leiratkozok.push(alapParancsok(reg, f));
    const m = f.munkaterulet;
    expect(reg.elerheto(reg.kap('panel.osszekapcsol')!)).toBe(false);
    expect(reg.elerheto(reg.kap('panel.lekapcsol')!)).toBe(false);
    m.oszt('sor', false);
    expect(reg.elerheto(reg.kap('panel.osszekapcsol')!)).toBe(true);
    reg.futtat('panel.osszekapcsol'); // két csoport: azonnali kapcsolat
    expect(reg.elerheto(reg.kap('panel.lekapcsol')!)).toBe(true);
    reg.futtat('panel.lekapcsol');
    expect(m.kapcsoltTarsak(m.aktivPanelId)).toEqual([]);
  });
});

describe('06-workspace-24: navigációs előzménylista', () => {
  it('a lista a legközelebbi lépéstől, az n-edik elem n lépést ugrik; az új ág megszünteti az előre ágat', () => {
    const m = new Munkaterulet();
    ['a.md', 'b.md', 'c.md', 'd.md'].forEach((u) => m.megnyit(u));
    expect(m.elozmenyLista().map((l) => l.ut)).toEqual(['c.md', 'b.md', 'a.md']);
    m.navigalLepes(-1, 3);
    expect(m.aktivFul!.ut).toBe('a.md');
    expect(m.elozmenyLista(undefined, 1).map((l) => l.ut)).toEqual(['b.md', 'c.md', 'd.md']);
    m.navigalLepes(1, 2);
    expect(m.aktivFul!.ut).toBe('c.md');
    m.navigalLepes(1, 99); // a lista végén megáll
    expect(m.aktivFul!.ut).toBe('d.md');
    m.megnyit('e.md');
    expect(m.elozmenyLista(undefined, 1)).toEqual([]);
  });

  it('a vissza nyíl helyi menüje felsorolja az előzményt, a választott elem több lépést ugrik', async () => {
    const k = kornyezet(), m = k.felulet.munkaterulet;
    ['a.md', 'b.md', 'c.md'].forEach((u) => m.megnyit(u));
    render(Fulsor, { context: k.context, props: { panel: m.aktivPanel, aktivPanel: true, nezetId: 'n' } });
    await fireEvent.contextMenu(screen.getByRole('button', { name: 'Vissza az előző jegyzethez' }), { clientX: 10, clientY: 10 });
    const opciok = screen.getAllByRole('option').map((o) => o.textContent?.trim());
    expect(opciok).toEqual(['b', 'a']);
    await fireEvent.click(screen.getByRole('option', { name: 'a' }));
    expect(m.aktivFul!.ut).toBe('a.md');
    await fireEvent.contextMenu(screen.getByRole('button', { name: 'Előre a következő jegyzethez' }), { clientX: 10, clientY: 10 });
    expect(screen.getAllByRole('option').map((o) => o.textContent?.trim())).toEqual(['b', 'c']);
  });

  it('üres előzménynél a menü nem nyílik', async () => {
    const k = kornyezet(), m = k.felulet.munkaterulet;
    m.megnyit('a.md');
    render(Fulsor, { context: k.context, props: { panel: m.aktivPanel, aktivPanel: true, nezetId: 'n' } });
    await fireEvent.contextMenu(screen.getByRole('button', { name: 'Vissza az előző jegyzethez' }));
    expect(screen.queryAllByRole('option')).toEqual([]);
  });
});

describe('06-workspace-26: névvel mentett elrendezések', () => {
  it('mentés, betöltés, törlés; azonos név felülír; a fájlfülek nézet-állapota nem kerül bele', () => {
    const f = new Felulet({ csend: { be: false } }), m = f.munkaterulet;
    m.megnyit('a.md'); m.aktivFul!.nezet = { gorgetes: 99 }; m.oszt('sor'); m.megnyit('b.md', 'ujful'); m.megnyitNezet('graf', { mod: 'globalis' });
    f.oldalsav.nyitva = false; f.jobbPanel.nyitva = true;
    expect(f.elrendezesMent('  Munka  ')).toBe('ok');
    expect(f.elrendezesek.map((e) => e.nev)).toEqual(['Munka']);
    expect(JSON.stringify(f.elrendezesek[0].munkaterulet)).not.toContain('gorgetes');
    expect(JSON.stringify(f.elrendezesek[0].munkaterulet)).toContain('"graf"'); // a nézet-fül megőrzi a típusát
    m.betolt(); f.oldalsav.nyitva = true; f.jobbPanel.nyitva = false; // más elrendezés
    expect(m.panelek().length).toBe(1);
    expect(f.elrendezesBetolt('Munka')).toBe(true);
    expect(m.panelek().length).toBe(2);
    expect(m.panelek().flatMap((p) => p.fulek.map((x) => x.ut))).toContain('b.md');
    expect([f.oldalsav.nyitva, f.jobbPanel.nyitva]).toEqual([false, true]);
    f.elrendezesMent('Munka'); expect(f.elrendezesek.length).toBe(1);
    expect(f.elrendezesBetolt('nincs')).toBe(false);
    expect(f.elrendezesTorol('Munka')).toBe(true);
    expect(f.elrendezesTorol('Munka')).toBe(false);
    expect(f.elrendezesek).toEqual([]);
  });

  it('üres név, darabszám- és méretkorlát; a felület-állapottal együtt újratöltődik', () => {
    const f = new Felulet({ csend: { be: false } });
    expect(f.elrendezesMent('   ')).toBe('ures');
    for (let i = 0; i < MAX_ELRENDEZES; i++) expect(f.elrendezesMent(`L${i}`)).toBe('ok');
    expect(f.elrendezesMent('túl sok')).toBe('tul-sok');
    expect(f.elrendezesMent('L0')).toBe('ok'); // felülírás a telt listán is lehet
    const ujra = new Felulet(JSON.parse(JSON.stringify(f.sorosit())));
    expect(ujra.elrendezesek.map((e) => e.nev)).toEqual(f.elrendezesek.map((e) => e.nev));
    const nagy = new Felulet({ csend: { be: false } });
    for (let i = 0; i < 80; i++) nagy.munkaterulet.megnyitNezet('graf', { mod: 'globalis', i, kozeppont: 'x'.repeat(60) + i, vesz: i });
    for (let i = 0; i < 80; i++) nagy.munkaterulet.megnyit(`${'hosszú'.repeat(10)}-${i}.md`, 'ujful');
    expect(nagy.elrendezesMent('nagy')).toBe('tul-nagy');
    expect(nagy.elrendezesek).toEqual([]);
  });

  it('a hibás vagy túlméretes mentett bejegyzést betöltéskor eldobja', () => {
    const f = new Felulet({ csend: { be: false }, elrendezesek: [
      { nev: '', munkaterulet: {} }, { nev: 'jó', munkaterulet: { gyoker: { tipus: 'panel', id: 'p', fulek: [{ id: 'f', ut: 'a.md' }], aktiv: 'f' }, aktivPanelId: 'p' } },
      { nev: 'jó', munkaterulet: {} }, { nev: 'x', munkaterulet: 7 }, 'szemét', { nev: 'óriás', munkaterulet: { x: 'y'.repeat(20000) } },
    ] });
    expect(f.elrendezesek.map((e) => e.nev)).toEqual(['jó']);
  });

  it('az átfedés: mentés névvel (Enter), betöltés és törlés gombbal, hibaüzenet ikonnal', async () => {
    const k = kornyezet(), m = k.felulet.munkaterulet;
    m.megnyit('a.md'); m.oszt('sor');
    k.felulet.atfedes = 'elrendezesek';
    render(Elrendezesek, { context: k.context });
    expect(screen.getByText('Még nincs mentett elrendezés.')).toBeTruthy();
    const mezo = screen.getByPlaceholderText('Az elrendezés neve') as HTMLInputElement;
    await fireEvent.input(mezo, { target: { value: 'Olvasás' } });
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    expect(k.felulet.elrendezesek.map((e) => e.nev)).toEqual(['Olvasás']);
    expect(await screen.findByText('Olvasás')).toBeTruthy();
    m.betolt();
    await fireEvent.click(screen.getByRole('button', { name: 'Olvasás betöltése' }));
    expect(m.panelek().length).toBe(2);
    expect(k.felulet.atfedes).toBeNull();
  });

  it('az átfedés törlés gombja és a telt lista hibája látszik', async () => {
    const k = kornyezet();
    for (let i = 0; i < MAX_ELRENDEZES; i++) k.felulet.elrendezesMent(`L${i}`);
    k.felulet.atfedes = 'elrendezesek';
    render(Elrendezesek, { context: k.context });
    const mezo = screen.getByPlaceholderText('Az elrendezés neve');
    await fireEvent.input(mezo, { target: { value: 'új' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Mentés' }));
    expect((await screen.findByRole('alert')).textContent).toContain(`Legfeljebb ${MAX_ELRENDEZES}`);
    await fireEvent.click(screen.getByRole('button', { name: 'L3 törlése' }));
    expect(k.felulet.elrendezesek.some((e) => e.nev === 'L3')).toBe(false);
  });

  it('a ⌘P-parancsok az elrendezés-átfedést nyitják', () => {
    const f = new Felulet({ csend: { be: false } }), reg = new Regiszter();
    leiratkozok.push(alapParancsok(reg, f));
    reg.futtat('elrendezes.kezel'); expect(f.atfedes).toBe('elrendezesek');
    f.atfedes = null; reg.futtat('elrendezes.ment'); expect(f.atfedes).toBe('elrendezesek');
  });
});

describe('06-workspace-28: UI-nagyítás', () => {
  it('a szorzó 0,8–1,6 között marad, 0,1-es lépésekkel; visszaállítás 1-re; mentődik', () => {
    const f = new Felulet({ csend: { be: false } });
    f.nagyit(NAGYITAS.lepes); expect(f.nagyitas).toBeCloseTo(1.1);
    for (let i = 0; i < 20; i++) f.nagyit(NAGYITAS.lepes);
    expect(f.nagyitas).toBe(NAGYITAS.max);
    for (let i = 0; i < 30; i++) f.nagyit(-NAGYITAS.lepes);
    expect(f.nagyitas).toBe(NAGYITAS.min);
    f.nagyit(0.3);
    expect(new Felulet(JSON.parse(JSON.stringify(f.sorosit()))).nagyitas).toBeCloseTo(1.1);
    f.nagyitasAlap(); expect(f.nagyitas).toBe(1);
    expect(new Felulet({ nagyitas: 9 }).nagyitas).toBe(NAGYITAS.max);
    expect(new Felulet({ nagyitas: 'sok' }).nagyitas).toBe(1);
    expect(new Felulet({ nagyitas: NaN }).nagyitas).toBe(1);
  });

  it('⌘= ⌘- ⌘0 a billentyűkezelőn át nagyít, kicsinyít, visszaállít', () => {
    const f = new Felulet({ csend: { be: false } }), reg = new Regiszter();
    leiratkozok.push(alapParancsok(reg, f));
    const gomb = (key: string, code = '') => kezel(new KeyboardEvent('keydown', { key, code, metaKey: true, cancelable: true }), reg);
    expect(gomb('0', 'Digit0')).toBe(false); // alapértéken a visszaállítás nem elérhető
    expect(gomb('=', 'Equal')).toBe(true); expect(f.nagyitas).toBeCloseTo(1.1);
    expect(gomb('-', 'Minus')).toBe(true); expect(gomb('-', 'Minus')).toBe(true); expect(f.nagyitas).toBeCloseTo(0.9);
    expect(gomb('0', 'Digit0')).toBe(true); expect(f.nagyitas).toBe(1);
  });

  it('a PDF-fül saját nagyítását nem veszi el a globális parancs', () => {
    const f = new Felulet({ csend: { be: false } }), reg = new Regiszter();
    leiratkozok.push(alapParancsok(reg, f));
    f.munkaterulet.megnyit('doc.pdf');
    const e = new KeyboardEvent('keydown', { key: '=', code: 'Equal', metaKey: true, cancelable: true });
    expect(kezel(e, reg)).toBe(false);
    expect(e.defaultPrevented).toBe(false);
    expect(f.nagyitas).toBe(1);
  });

  it('a gyökérelem zoom tulajdonsága a szorzót követi; 1-nél törlődik', () => {
    nagyitasAlkalmaz(1.2);
    expect(document.documentElement.style.getPropertyValue('zoom')).toBe('1.2');
    nagyitasAlkalmaz(1);
    expect(document.documentElement.style.getPropertyValue('zoom')).toBe('');
  });

  it('a Hej a mentett szorzót a gyökérelemre teszi, és követi a változást', async () => {
    const k = kornyezet({ csend: { be: false }, nagyitas: 1.3 });
    render(Hej, { context: k.context });
    expect(document.documentElement.style.getPropertyValue('zoom')).toBe('1.3');
    k.felulet.nagyit(NAGYITAS.lepes); flushSync();
    expect(document.documentElement.style.getPropertyValue('zoom')).toBe('1.4');
  });
});

describe('06-workspace-12: ikonsáv-beállítás', () => {
  it('az alap sorrend a mai négy + az új ikonok; ismeretlen azonosító eldobva; a rejtett kimarad', () => {
    const b = ikonsavErvenyes(undefined);
    expect(ikonsavElemek(b).felso.map((d) => d.id)).toEqual(['hej.oldalsav', 'kereses.panel', 'hej.valto', 'fa.uj-jegyzet', 'sablon.uj-jegyzet', 'graf.megnyit', 'naplo.napi', 'hej.paletta']);
    expect(ikonsavElemek(b).also.map((d) => d.id)).toEqual(['munkater.valto', 'manifold.vezerlo', 'beallitasok.megnyit']);
    const mentett = ikonsavErvenyes({ lathato: false, rejtett: ['naplo.napi', 'ismeretlen', 'naplo.napi', 7], sorrend: ['hej.paletta', 'x'] });
    expect(mentett).toEqual({ lathato: false, rejtett: ['naplo.napi'], sorrend: ['hej.paletta'] });
    expect(ikonsavElemek(mentett).felso[0].id).toBe('hej.paletta');
    expect(ikonsavElemek(mentett).felso.map((d) => d.id)).not.toContain('naplo.napi');
    expect(ikonsavElemek(mentett, true).felso.map((d) => d.id)).toContain('naplo.napi');
    expect(IKONSAV_ALAP.length).toBe(11);
  });

  it('mozgatás és húzás csak a csoporton belül; a szélen a mozgatás nem tesz semmit', () => {
    let b = ikonsavErvenyes({});
    b = ikonMozgat(b, 'kereses.panel', 1);
    expect(ikonsavElemek(b).felso.map((d) => d.id).slice(0, 3)).toEqual(['hej.oldalsav', 'hej.valto', 'kereses.panel']);
    expect(ikonMozgat(b, 'hej.oldalsav', -1)).toBe(b);
    expect(ikonAthelyez(b, 'manifold.vezerlo', 'hej.oldalsav')).toBe(b); // másik csoportba nem
    const c = ikonAthelyez(b, 'hej.paletta', 'hej.oldalsav');
    expect(ikonsavElemek(c).felso[0].id).toBe('hej.paletta');
    const d = ikonAthelyez(c, 'hej.paletta', 'naplo.napi');
    expect(ikonsavElemek(d).felso.slice(-2).map((x) => x.id)).toEqual(['naplo.napi', 'hej.paletta']);
  });

  it('az ikonsáv a beállítás szerint rajzol: új ikonok, rejtés jobb klikkre, visszahozás, sáv elrejtése', async () => {
    const k = kornyezet();
    render(Ikonsav, { context: k.context });
    const nav = screen.getByRole('navigation', { name: 'Gyorsműveletek' });
    const id = () => [...nav.querySelectorAll('[data-ikonsav]')].map((e) => e.getAttribute('data-ikonsav'));
    expect(id()).toContain('graf.megnyit');
    expect(id()).toContain('hej.paletta');
    await fireEvent.contextMenu(nav.querySelector('[data-ikonsav="graf.megnyit"]')!, { clientX: 5, clientY: 5 });
    await fireEvent.click(screen.getByRole('option', { name: 'Ikon elrejtése' }));
    expect(k.felulet.ikonsav.rejtett).toEqual(['graf.megnyit']);
    await waitFor(() => expect(id()).not.toContain('graf.megnyit'));
    await fireEvent.contextMenu(nav.querySelector('[data-ikonsav="hej.paletta"]')!, { clientX: 5, clientY: 5 });
    const visszahoz = screen.getAllByRole('option').map((o) => o.textContent?.trim()).find((x) => x?.startsWith('Ikon megjelenítése:'));
    expect(visszahoz).toBeTruthy();
    await fireEvent.click(screen.getByRole('option', { name: visszahoz! }));
    expect(k.felulet.ikonsav.rejtett).toEqual([]);
    await fireEvent.contextMenu(nav.querySelector('[data-ikonsav="hej.paletta"]')!, { clientX: 5, clientY: 5 });
    await fireEvent.click(screen.getByRole('option', { name: 'Ikonsáv elrejtése' }));
    expect(k.felulet.ikonsav.lathato).toBe(false);
    expect(nav.classList.contains('rejtett')).toBe(true);
  });

  it('a menüből lefelé mozgatott ikon és a húzás is átrendez; a beállítás mentődik', async () => {
    const k = kornyezet();
    render(Ikonsav, { context: k.context });
    const nav = screen.getByRole('navigation', { name: 'Gyorsműveletek' });
    const sorrend = () => [...nav.querySelectorAll('[data-ikonsav]')].map((e) => e.getAttribute('data-ikonsav'));
    await fireEvent.contextMenu(nav.querySelector('[data-ikonsav="hej.oldalsav"]')!, { clientX: 5, clientY: 5 });
    await fireEvent.click(screen.getByRole('option', { name: 'Mozgatás lefelé' }));
    await waitFor(() => expect(sorrend().slice(0, 2)).toEqual(['kereses.panel', 'hej.oldalsav']));
    const adat = new Map<string, string>();
    const dataTransfer = { setData: (a: string, v: string) => adat.set(a, v), getData: (a: string) => adat.get(a) ?? '', types: ['application/x-manifold-ikon'], effectAllowed: '', dropEffect: '' };
    await fireEvent.dragStart(nav.querySelector('[data-ikonsav="hej.paletta"]')!, { dataTransfer });
    await fireEvent.dragOver(nav.querySelector('[data-ikonsav="kereses.panel"]')!, { dataTransfer });
    await fireEvent.drop(nav.querySelector('[data-ikonsav="kereses.panel"]')!, { dataTransfer });
    await waitFor(() => expect(sorrend()[0]).toBe('hej.paletta'));
    const ujra = new Felulet(JSON.parse(JSON.stringify(k.felulet.sorosit())));
    expect(ikonsavElemek(ujra.ikonsav).felso[0].id).toBe('hej.paletta');
  });

  it('a munkaterület-váltó ikon csak a héjban látszik (a parancs elérhetősége dönt)', async () => {
    const k = kornyezet(), reg = regiszter;
    leiratkozok.push(alapParancsok(reg, k.felulet));
    const { unmount } = render(Ikonsav, { context: k.context });
    expect(document.querySelector('[data-ikonsav="munkater.valto"]')).toBeNull(); // böngésző / teszt: nincs héj
    unmount();
    const uzenetek: unknown[] = [];
    vi.stubGlobal('webkit', { messageHandlers: { manifold: { postMessage: (u: unknown) => uzenetek.push(u) } } });
    render(Ikonsav, { context: k.context });
    await fireEvent.click(document.querySelector('[data-ikonsav="munkater.valto"]')!);
    expect(uzenetek).toEqual([{ tipus: 'munkater-valaszto' }]);
  });

  it('az ikon a regiszter parancsát futtatja, a tooltip a regiszter gyorsbillentyűjét mutatja', async () => {
    const k = kornyezet();
    const futott: string[] = [];
    leiratkozok.push(regiszter.regisztral({ id: 'graf.megnyit', nev: 'Gráfnézet megnyitása', billentyu: 'Mod+Alt+G', futtat: () => void futott.push('graf') }));
    render(Ikonsav, { context: k.context });
    const gomb = screen.getByRole('button', { name: 'Gráfnézet megnyitása' });
    expect(gomb.getAttribute('title')).toContain('⌥⌘G');
    await fireEvent.click(gomb);
    expect(futott).toEqual(['graf']);
  });

  it('az ikonsáv oszlopa a Hej rácsában 0 széles, ha a sáv rejtett; a parancs visszahozza', async () => {
    const k = kornyezet({ csend: { be: false }, ikonsav: { lathato: false } });
    const { container } = render(Hej, { context: k.context });
    const rac = container.querySelector<HTMLElement>('.hej')!;
    expect(rac.style.getPropertyValue('--ikonsav-sz')).toBe('0px');
    const reg = new Regiszter();
    leiratkozok.push(alapParancsok(reg, k.felulet));
    reg.futtat('ikonsav.kapcsol'); flushSync();
    expect(rac.style.getPropertyValue('--ikonsav-sz')).toBe('var(--szelesseg-ikonsav)');
  });
});

describe('06-workspace-17: visszahivatkozások száma az állapotsorban', () => {
  const valasz = (adat: unknown, kod = 200) => new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });

  it('az aktív jegyzet linkjeinek számát mutatja, kattintásra a jobb panel szakasza nyílik', async () => {
    const hivasok: string[] = [];
    vi.stubGlobal('fetch', async (url: string) => {
      hivasok.push(String(url));
      return valasz({ forrasok: [{ ut: 'x.md', linkek: [{}, {}] }, { ut: 'y.md', linkek: [{}] }] });
    });
    const k = kornyezet({ csend: { be: false } }), f = k.felulet;
    leiratkozok.push(alapParancsok(regiszter, f));
    f.jobbPanel.nyitva = false; f.jobbPanel.visszahivatkozasok = false;
    f.munkaterulet.megnyit('a.md');
    render(Allapotsor, { context: k.context });
    const gomb = await screen.findByText('3 visszahivatkozás');
    expect(hivasok.some((u) => u.includes('/api/vault/visszahivatkozasok?ut=a.md'))).toBe(true);
    await fireEvent.click(gomb);
    expect(f.jobbPanel.nyitva).toBe(true);
    expect(f.jobbPanel.visszahivatkozasok).toBe(true);
  });

  it('fülváltásra újratölt, nem jegyzet-fülön és hibánál eltűnik; a késői válasz nem írja felül az újat', async () => {
    let feloldA: (r: Response) => void = () => {};
    vi.stubGlobal('fetch', (url: string) => {
      const u = String(url);
      if (u.includes('ut=a.md')) return new Promise<Response>((res) => (feloldA = res));
      if (u.includes('ut=b.md')) return Promise.resolve(valasz({ forrasok: [{ ut: 'x.md', linkek: [{}] }] }));
      return Promise.resolve(valasz({ hiba: 'nincs' }, 503));
    });
    const k = kornyezet({ csend: { be: false } }), m = k.felulet.munkaterulet;
    m.megnyit('a.md');
    render(Allapotsor, { context: k.context });
    m.megnyit('b.md'); flushSync();
    expect(await screen.findByText('1 visszahivatkozás')).toBeTruthy();
    feloldA(valasz({ forrasok: [{ ut: 'q.md', linkek: [{}, {}, {}, {}] }] })); // a lassú, régi válasz
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByText('4 visszahivatkozás')).toBeNull();
    m.megnyitNezet('graf'); flushSync();
    await waitFor(() => expect(screen.queryByText('1 visszahivatkozás')).toBeNull());
    m.megnyit('c.md'); flushSync();
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByText(/visszahivatkozás/)).toBeNull(); // a hiba nem hamis 0
  });

  it('angolul egyes és többes szám', async () => {
    nyelv.beallit('en');
    vi.stubGlobal('fetch', async () => valasz({ forrasok: [{ ut: 'x.md', linkek: [{}] }] }));
    const k = kornyezet({ csend: { be: false } });
    k.felulet.munkaterulet.megnyit('a.md');
    render(Allapotsor, { context: k.context });
    expect(await screen.findByText('1 backlink')).toBeTruthy();
  });
});
