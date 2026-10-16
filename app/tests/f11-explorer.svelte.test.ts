import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { flushSync } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Fa from '../src/hej/Fa.svelte';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet, MAX_NYITOTT_MAPPA } from '../src/lib/elrendezes/felulet.svelte';
import { nyelv } from '../src/lib/i18n';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { faEpit, faIdoMezo, faRendezes, mappakatKinyit, type FaRendezes } from '../src/lib/vault/fa';
import { VaultFajlok, type FajlInfo } from '../src/lib/vault/fajlok.svelte';

const f = (ut: string, mtime: number | null = 1): FajlInfo => ({ ut, mtime, tipus: 'md', meret: 1 });
const utak = () => screen.getAllByRole('treeitem').map(e => e.getAttribute('data-fa-ut'));
const le: (() => void)[] = [];
beforeEach(() => { nyelv.beallit('en'); });
afterEach(() => { cleanup(); while (le.length) le.pop()!(); document.body.textContent = ''; vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); nyelv.beallit('hu'); });
function kornyezet(mentett: unknown = {}) {
  const felulet = new Felulet(mentett), fajlok = new VaultFajlok(), kapcsolat = new CoreKapcsolat('ws://synthetic');
  fajlok.mappak = ['Zeta', 'Zeta/Child', 'Alpha', 'Alpha/Empty'];
  fajlok.beallit([f('B.md', 9), f('A.md', 1), f('Zeta/B.md', 9), f('Zeta/A.md', 1), f('Zeta/Child/Leaf.md', 0)]);
  vi.spyOn(fajlok, 'frissit').mockResolvedValue();
  const context = new Map([[KORNYEZET_KULCS, { felulet, fajlok, kapcsolat }]]);
  return { felulet, fajlok, kapcsolat, context };
}

describe('F11 a fájlfa rendezése', () => {
  it.each([
    ['nev', ['Alpha', 'Zeta', 'A.md', 'B.md'], ['Zeta/Child', 'Zeta/A.md', 'Zeta/B.md']],
    ['nev-forditva', ['Zeta', 'Alpha', 'B.md', 'A.md'], ['Zeta/Child', 'Zeta/B.md', 'Zeta/A.md']],
    ['modositva', ['Alpha', 'Zeta', 'B.md', 'A.md'], ['Zeta/Child', 'Zeta/B.md', 'Zeta/A.md']],
    ['modositva-regi', ['Alpha', 'Zeta', 'A.md', 'B.md'], ['Zeta/Child', 'Zeta/A.md', 'Zeta/B.md']],
  ] as [FaRendezes, string[], string[]][])('%s minden szinten rendez, a mappák elöl maradnak', (mod, felso, belso) => {
    const lista = Object.freeze([Object.freeze(f('B.md', 9)), Object.freeze(f('A.md', 1)), Object.freeze(f('Zeta/B.md', 9)), Object.freeze(f('Zeta/A.md', 1)), Object.freeze(f('Zeta/Child/Leaf.md'))]);
    const fa = faEpit(lista, ['Alpha/Empty'], mod);
    expect(fa.gyerekek.map(g => g.ut)).toEqual(felso);
    expect(fa.gyerekek.find(g => g.ut === 'Zeta')!.gyerekek.map(g => g.ut)).toEqual(belso);
    expect(fa.gyerekek.find(g => g.ut === 'Alpha')!.gyerekek[0].ut).toBe('Alpha/Empty');
    expect(lista.map(e => e.ut)).toEqual(['B.md', 'A.md', 'Zeta/B.md', 'Zeta/A.md', 'Zeta/Child/Leaf.md']);
  });

  it('azonos időnél a név és út dönt, hiányzó vagy hibás idő mindkét dátumrend végén áll; epoch 0 valós idő', () => {
    const lista = [f('Unknown.md', null), f('B.md', 10), f('A.md', 10), f('Epoch.md', 0), f('Invalid.md', NaN)];
    expect(faEpit(lista, [], 'modositva').gyerekek.map(g => g.ut)).toEqual(['A.md', 'B.md', 'Epoch.md', 'Invalid.md', 'Unknown.md']);
    expect(faEpit([...lista].reverse(), [], 'modositva-regi').gyerekek.map(g => g.ut)).toEqual(['Epoch.md', 'A.md', 'B.md', 'Invalid.md', 'Unknown.md']);
    expect(faEpit([f('Same.MD'), f('Same.md')], [], 'modositva').gyerekek.map(g => g.ut)).toEqual(['Same.md', 'Same.MD']);
  });

  it.each([
    ['letrehozva', ['Alpha', 'Zeta', 'B.md', 'A.md', 'Unknown.md']],
    ['letrehozva-regi', ['Alpha', 'Zeta', 'A.md', 'B.md', 'Unknown.md']],
  ] as [FaRendezes, string[]][])('%s a valódi születési időt használja; az mtime nem helyettesít, az ismeretlen a végén áll', (mod, varhato) => {
    // Az mtime szándékosan az ctime-mal ellentétes sorrendű: ha bárhol átszivárogna, a sorrend megfordulna.
    const lista = [
      { ...f('A.md', 99), ctime: 1 }, { ...f('B.md', 1), ctime: 9 },
      { ...f('Unknown.md', 50), ctime: null }, f('Zeta/X.md', 5),
    ];
    const fa = faEpit(lista, ['Alpha/Empty'], mod);
    expect(fa.gyerekek.map(g => g.ut)).toEqual(varhato);
    expect(faEpit(lista.slice(0, 3), [], mod).gyerekek.at(-1)!.ctime).toBeNull();
  });

  it('a faIdoMezo a rendezési módhoz a megfelelő időmezőt adja', () => {
    expect(faIdoMezo('modositva')).toBe('mtime'); expect(faIdoMezo('modositva-regi')).toBe('mtime');
    expect(faIdoMezo('letrehozva')).toBe('ctime'); expect(faIdoMezo('letrehozva-regi')).toBe('ctime');
    expect(faIdoMezo('nev')).toBeNull(); expect(faIdoMezo('nev-forditva')).toBeNull();
    expect(faRendezes('letrehozva-regi')).toBe('letrehozva-regi');
  });

  it('a létrehozás szerinti módot a menü kínálja, és a mód mentése túléli az újratöltést', async () => {
    const k = kornyezet();
    render(Fa, { context: k.context });
    await fireEvent.click(screen.getByRole('button', { name: 'Sort order: File name (A–Z)' }));
    expect(screen.getByText('Created: newest first')).toBeTruthy();
    expect(screen.getByText('Created: oldest first')).toBeTruthy();
    await fireEvent.click(screen.getByText('Created: oldest first'));
    expect(k.felulet.oldalsav.rendezes).toBe('letrehozva-regi');
    expect(new Felulet(JSON.parse(JSON.stringify(k.felulet.sorosit()))).oldalsav.rendezes).toBe('letrehozva-regi');
  });

  it('a rendezés mentése megőrzi a korábbi nyitásokat; régi vagy hibás érték névrendre áll vissza', () => {
    const felulet = new Felulet({ oldalsav: { nyitott: ['Zeta', 'Zeta/Child'], rendezes: 'modositva-regi' } });
    const ujra = new Felulet(JSON.parse(JSON.stringify(felulet.sorosit())));
    expect(ujra.oldalsav.rendezes).toBe('modositva-regi');
    expect(ujra.oldalsav.nyitott).toEqual(['Zeta', 'Zeta/Child']);
    for (const hibas of [undefined, null, 'letrejott', 'bogus', {}, []]) {
      expect(faRendezes(hibas)).toBe('nev');
      expect(new Felulet({ oldalsav: { rendezes: hibas, nyitott: ['Zeta'] } }).oldalsav).toMatchObject({ rendezes: 'nev', nyitott: ['Zeta'] });
    }
  });

  it('a kompakt menü billentyűzetről választható, a fókusz visszatér, és a nyitások nem változnak', async () => {
    const k = kornyezet({ oldalsav: { nyitott: ['Zeta', 'Zeta/Child'] } });
    render(Fa, { context: k.context });
    const gomb = screen.getByRole('button', { name: 'Sort order: File name (A–Z)' });
    await fireEvent.click(gomb);
    expect(screen.getByRole('listbox', { name: 'File sort order' })).toBeTruthy();
    const menu = screen.getByRole('listbox').closest<HTMLElement>('.nt-lebego')!;
    await fireEvent.keyDown(menu, { key: 'ArrowDown' }); await fireEvent.keyDown(menu, { key: 'Enter' });
    expect(k.felulet.oldalsav.rendezes).toBe('nev-forditva');
    expect(k.felulet.oldalsav.nyitott).toEqual(['Zeta', 'Zeta/Child']);
    expect(document.activeElement).toBe(gomb);
    expect(utak()).toEqual(['Zeta', 'Zeta/Child', 'Zeta/Child/Leaf.md', 'Zeta/B.md', 'Zeta/A.md', 'Alpha', 'B.md', 'A.md']);
  });

  it('a módosítás idejének frissülése helyben rendezi a sorokat; a kijelölt jegyzet és a fa fókusza megmarad', async () => {
    const k = kornyezet({ oldalsav: { rendezes: 'modositva' } });
    k.felulet.munkaterulet.megnyit('A.md');
    render(Fa, { context: k.context });
    const sor = screen.getAllByRole('treeitem').find(e => e.getAttribute('data-fa-ut') === 'A.md')!;
    sor.focus();
    k.fajlok.beallit(k.fajlok.lista.map(f => f.ut === 'A.md' ? { ...f, mtime: 20 } : f)); flushSync();
    expect(utak()).toEqual(['Alpha', 'Zeta', 'A.md', 'B.md']);
    expect(k.felulet.munkaterulet.aktivFul?.ut).toBe('A.md');
    expect(document.activeElement).toBe(sor);
  });
});

describe('F11 minden mappa kinyitása', () => {
  it('az üres és beágyazott mappák is kinyílnak, összecsukhatók, a rendezési mód közben változatlan', async () => {
    const k = kornyezet({ oldalsav: { rendezes: 'nev-forditva' } });
    render(Fa, { context: k.context });
    await fireEvent.click(screen.getByRole('button', { name: 'Expand all folders' }));
    expect(new Set(k.felulet.oldalsav.nyitott)).toEqual(new Set(['Zeta', 'Zeta/Child', 'Alpha', 'Alpha/Empty']));
    expect(utak()).toContain('Zeta/Child/Leaf.md'); expect(utak()).toContain('Alpha/Empty');
    await fireEvent.click(screen.getByRole('button', { name: 'Collapse all folders' }));
    expect(k.felulet.oldalsav.nyitott).toEqual([]);
    expect(k.felulet.oldalsav.rendezes).toBe('nev-forditva');
    expect(utak()).toEqual(['Zeta', 'Alpha', 'B.md', 'A.md']);
    expect(screen.getByRole('button', { name: 'Expand all folders' })).toBeTruthy();
  });

  it('a 2000-es korlát mellett megmaradnak az emlékezett nyitások és a szülők előbb nyílnak ki', () => {
    const mappak = Array.from({ length: MAX_NYITOTT_MAPPA + 2 }, (_, i) => `Folder ${i}`);
    mappak.push('Folder 0/Child');
    const fa = faEpit([], mappak), emlekezett = ['Detached remembered', 'Folder 2001'];
    const kinyitott = mappakatKinyit(fa, emlekezett, MAX_NYITOTT_MAPPA);
    expect(kinyitott.utak).toHaveLength(MAX_NYITOTT_MAPPA);
    expect(kinyitott.utak.slice(0, 2)).toEqual(emlekezett);
    expect(kinyitott.utak).toContain('Folder 0');
    expect(kinyitott.utak).not.toContain('Folder 0/Child');
    expect(kinyitott.kimaradt).toBe(4);
    expect(emlekezett).toEqual(['Detached remembered', 'Folder 2001']);
    expect(mappakatKinyit(faEpit([], ['A/B/C', 'D']), ['A/B'], 4).utak).toEqual(['A/B', 'A', 'D', 'A/B/C']);
  });
});

describe('F11 módosítási idő figyelése', () => {
  it('ismert fájl tartalmi eseménye csak dátumrendezésnél frissít; gyors események összeolvadnak, leállítás után nincs figyelés', () => {
    vi.useFakeTimers();
    const fajlok = new VaultFajlok(), kapcsolat = new CoreKapcsolat('ws://synthetic');
    fajlok.beallit([f('A.md')]);
    const frissit = vi.spyOn(fajlok, 'frissit').mockResolvedValue();
    le.push(fajlok.figyel(kapcsolat));
    kapcsolat.szetoszt({ tipus: 'vault_valtozas', utak: ['A.md'] }); vi.advanceTimersByTime(500);
    expect(frissit).not.toHaveBeenCalled();
    const befejez = fajlok.idobelyegeketFigyel(); vi.advanceTimersByTime(0); frissit.mockClear();
    kapcsolat.szetoszt({ tipus: 'vault_valtozas', utak: ['A.md'] });
    kapcsolat.szetoszt({ tipus: 'vault_valtozas', utak: ['A.md'] });
    vi.advanceTimersByTime(299); expect(frissit).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1); expect(frissit).toHaveBeenCalledTimes(1);
    befejez(); befejez();
    kapcsolat.szetoszt({ tipus: 'vault_valtozas', utak: ['A.md'] }); vi.advanceTimersByTime(500);
    expect(frissit).toHaveBeenCalledTimes(1);
  });

  it('az utolsó dátumfigyelő elengedése csak a saját várakozó frissítését törli, a szerkezeti eseményét megőrzi', () => {
    vi.useFakeTimers();
    const fajlok = new VaultFajlok(), kapcsolat = new CoreKapcsolat('ws://synthetic');
    fajlok.beallit([f('A.md')]);
    const frissit = vi.spyOn(fajlok, 'frissit').mockResolvedValue();
    le.push(fajlok.figyel(kapcsolat));
    const elso = fajlok.idobelyegeketFigyel(); elso(); vi.advanceTimersByTime(1000);
    expect(frissit).not.toHaveBeenCalled();
    const masodik = fajlok.idobelyegeketFigyel();
    kapcsolat.szetoszt({ tipus: 'vault_valtozas', utak: ['New.md'] });
    // Az utána érkező metaadatkérés sem változtathatja vissza a szerkezeti frissítést megszakíthatóvá.
    kapcsolat.szetoszt({ tipus: 'vault_valtozas', utak: ['A.md'] });
    masodik(); vi.advanceTimersByTime(300);
    expect(frissit).toHaveBeenCalledTimes(1);
  });

  it('egy későn visszatérő régi fájllista és hiba sem írja felül az újabb sikeres választ', async () => {
    const fajlok = new VaultFajlok();
    const valaszok: ((valasz: Response) => void)[] = [];
    const json = (d: unknown, status = 200) => new Response(JSON.stringify(d), { status, headers: { 'Content-Type': 'application/json' } });
    vi.stubGlobal('fetch', async (url: string) => url === '/api/vault/index'
      ? json({ kesz: true }) : new Promise<Response>(r => { valaszok.push(r); }));
    const regi = fajlok.frissit(); await waitFor(() => expect(valaszok).toHaveLength(1));
    const uj = fajlok.frissit(); await waitFor(() => expect(valaszok).toHaveLength(2));
    valaszok[1](json({ fajlok: [f('New.md', 20)], mappak: ['New folder'] })); await uj;
    valaszok[0](json({ fajlok: [f('Old.md', 1)], mappak: ['Old folder'] })); await regi;
    expect(fajlok.lista.map(f => f.ut)).toEqual(['New.md']);
    expect(fajlok.mappak).toEqual(['New folder']); expect(fajlok.info('Old.md')).toBeUndefined();
    const hibas = fajlok.frissit(); await waitFor(() => expect(valaszok).toHaveLength(3));
    const legujabb = fajlok.frissit(); await waitFor(() => expect(valaszok).toHaveLength(4));
    valaszok[3](json({ fajlok: [f('Newest.md', 30)], mappak: [] })); await legujabb;
    valaszok[2](json({ hiba: 'Old error' }, 500)); await hibas;
    expect(fajlok.lista.map(f => f.ut)).toEqual(['Newest.md']); expect(fajlok.hiba).toBeNull();
  });

});
