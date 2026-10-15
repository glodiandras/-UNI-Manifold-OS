// A címkefa (az oldalsáv harmadik füle) és a jegyzet-előzmények (C11b): a fa és a szűrt lista, a billentyűzet, a tartós
// nézet; az előzmények listája, a diff-párbeszéd és a visszaállítás menete (a nyitott dokumentum mentése, core-hívás,
// értesítés „Visszavonás” művelettel).

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { cimkek } from '../src/lib/vault/cimkek.svelte';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import Oldalsav from '../src/hej/Oldalsav.svelte';
import Elozmenyek from '../src/hej/kapcsolatok/Elozmenyek.svelte';
import { szerkesztok } from '../src/szerkeszto/szerkesztok.svelte';

function valasz(adat: unknown, kod = 200) {
  return new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });
}

const CIMKEK = [
  { cimke: 'AI', kis: 'ai', db: 2, ossz: 2 },
  { cimke: 'Fizika', kis: 'fizika', db: 0, ossz: 3 },
  { cimke: 'Fizika/Mechanika', kis: 'fizika/mechanika', db: 2, ossz: 3 },
  { cimke: 'Fizika/Mechanika/Newton', kis: 'fizika/mechanika/newton', db: 1, ossz: 1 },
];

let kerelmek: { url: string; metodus: string; body?: Record<string, unknown> }[];
let kapcsolat: CoreKapcsolat;

function kornyezet(allapot: unknown = {}) {
  const felulet = new Felulet(allapot);
  const fajlok = new VaultFajlok();
  kapcsolat = new CoreKapcsolat('ws://x');
  return { felulet, fajlok, context: new Map<unknown, unknown>([[KORNYEZET_KULCS, { felulet, fajlok, kapcsolat }]]) };
}

beforeEach(() => {
  kerelmek = [];
  cimkek.lista = [];
  cimkek.betoltve = false;
  cimkek.latszik = false;
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://127.0.0.1/');
    kerelmek.push({ url: u.pathname + u.search, metodus: init?.method ?? 'GET', body: init?.body ? JSON.parse(String(init.body)) : undefined });
    if (u.pathname === '/api/vault/cimkek') return valasz({ cimkek: CIMKEK });
    if (u.pathname === '/api/vault/kereses') {
      return valasz({ osszes: 2, talalatok: [{ ut: 'Mappa/Béta.md', talalatok: [] }, { ut: 'Alfa.md', talalatok: [] }] });
    }
    if (u.pathname === '/api/vault/elozmeny') {
      return valasz({
        ut: 'J.md',
        bejegyzesek: [
          { sha: 'b'.repeat(40), datum: '2026-10-02T10:05:00+02:00', targy: 'x', tipus: 'szerk', cimke: 'Szerkesztés a Manifoldban', kor: 'SZERK-20261002-100500', forras: 'pult-szerkeszto', statusz: 'M', ut_akkor: 'J.md', regi_ut: null, elozo: { sha: 'a'.repeat(40), ut: 'J.md' }, visszaallithato: false },
          { sha: 'a'.repeat(40), datum: '2026-10-02T09:00:00+02:00', targy: 'y', tipus: 'kezi', cimke: 'Kézi változás (Obsidian, Finder, …)', kor: null, forras: 'kezi', statusz: 'A', ut_akkor: 'J.md', regi_ut: null, elozo: null, visszaallithato: true },
        ],
      });
    }
    return valasz({ hiba: 'nincs' }, 404);
  });
});

afterEach(() => {
  cleanup();
  document.body.textContent = '';
  vi.unstubAllGlobals();
  ertesitesek.lista = [];
});

describe('az oldalsáv második füle (Címkék)', () => {
  it('a fülek közt a nyilak körbe lépnek, a nézet tartós', async () => {
    const { felulet, context } = kornyezet();
    render(Oldalsav, { context });
    const fulek = screen.getAllByRole('tab').map((t) => t.textContent?.trim());
    expect(fulek).toEqual(['Fájlok', 'Címkék']);
    await fireEvent.keyDown(screen.getByRole('tablist'), { key: 'ArrowLeft' });
    expect(felulet.oldalsav.nezet).toBe('cimkek');
    await fireEvent.keyDown(screen.getByRole('tablist'), { key: 'ArrowRight' });
    expect(felulet.oldalsav.nezet).toBe('fajlok');
    felulet.oldalsav.nezet = 'cimkek';
    expect(new Felulet(JSON.parse(JSON.stringify(felulet.sorosit()))).oldalsav.nezet).toBe('cimkek');
    expect(new Felulet({ oldalsav: { nezet: 'ismeretlen' } }).oldalsav.nezet).toBe('fajlok');
  });
});

describe('a címkefa', () => {
  async function megnyit() {
    const k = kornyezet({ oldalsav: { szelesseg: 264, nyitva: true, nezet: 'cimkek' } });
    render(Oldalsav, { context: k.context });
    await screen.findByRole('tree', { name: 'Címkék' });
    await waitFor(() => expect(screen.getAllByRole('treeitem').length).toBeGreaterThan(0));
    return k;
  }
  const nevek = () => screen.getAllByRole('treeitem').map((e) => e.querySelector('.nev')?.textContent);

  it('zárt fában a gyökerek számlálóval; a szülő kinyitása a gyerekeket mutatja', async () => {
    await megnyit();
    expect(nevek()).toEqual(['AI', 'Fizika']);
    const fizika = screen.getAllByRole('treeitem')[1];
    expect(fizika.getAttribute('aria-expanded')).toBe('false');
    expect(fizika.querySelector('.db')!.textContent).toBe('3');
    await fireEvent.click(screen.getAllByRole('button', { name: 'Kinyitás' })[0]);
    expect(nevek()).toEqual(['AI', 'Fizika', 'Mechanika']);
    expect(screen.getAllByRole('treeitem')[2].getAttribute('aria-level')).toBe('2');
  });

  it('a címke kijelölése a keresés `tag:` operátorával tölti a listát; újra kattintva megszűnik a szűrés', async () => {
    await megnyit();
    await fireEvent.click(screen.getAllByRole('treeitem')[1]);
    await screen.findByRole('list', { name: 'A címkéhez tartozó jegyzetek' });
    await waitFor(() => expect(screen.getAllByRole('button', { name: /Alfa|Béta/ }).length).toBe(2));
    const k = kerelmek.find((r) => r.url.startsWith('/api/vault/kereses'))!;
    expect(decodeURIComponent(k.url)).toContain('q=tag:#fizika');
    expect(screen.getAllByRole('button', { name: /Alfa|Béta/ }).map((b) => b.querySelector('.nev')?.textContent)).toEqual(['Alfa', 'Béta']);
    await fireEvent.click(screen.getAllByRole('treeitem')[1]);
    expect(screen.queryByRole('list', { name: 'A címkéhez tartozó jegyzetek' })).toBeNull();
  });

  it('billentyűzet: → kinyit, ↓ lép, ↩ kijelöl, ← becsuk', async () => {
    await megnyit();
    const fizika = screen.getAllByRole('treeitem')[1];
    fizika.focus();
    await fireEvent.keyDown(fizika, { key: 'ArrowRight' });
    expect(nevek()).toEqual(['AI', 'Fizika', 'Mechanika']);
    await fireEvent.keyDown(fizika, { key: 'ArrowDown' });
    await waitFor(() => expect(document.activeElement?.getAttribute('data-cimke')).toBe('fizika/mechanika'));
    await fireEvent.keyDown(document.activeElement!, { key: 'Enter' });
    await waitFor(() => expect(screen.getAllByRole('treeitem')[2].getAttribute('aria-selected')).toBe('true'));
    await fireEvent.keyDown(document.activeElement!, { key: 'ArrowLeft' }); // a gyerektelen... Mechanika-nak van gyereke (zárt): a szülőre lép
    await waitFor(() => expect(document.activeElement?.getAttribute('data-cimke')).toBe('fizika'));
    await fireEvent.keyDown(document.activeElement!, { key: 'ArrowLeft' });
    expect(nevek()).toEqual(['AI', 'Fizika']);
  });

  it('üres vault: magyar üzenet', async () => {
    vi.stubGlobal('fetch', async () => valasz({ cimkek: [] }));
    const k = kornyezet({ oldalsav: { szelesseg: 264, nyitva: true, nezet: 'cimkek' } });
    render(Oldalsav, { context: k.context });
    expect(await screen.findByText('A vaultban nincs címke.')).toBeTruthy();
  });
});

describe('az előzmények', () => {
  function elozmenyek(nyitva = true) {
    const k = kornyezet();
    render(Elozmenyek, { props: { ut: 'J.md', nyitva }, context: k.context });
  }

  it('a lista a legújabbal kezdődik, felirattal, idővel és körrel; a legújabb „jelenlegi”', async () => {
    elozmenyek();
    const lista = await screen.findByRole('list', { name: 'A jegyzet pillanatképei' });
    const elemek = [...lista.querySelectorAll('.elem')];
    expect(elemek.length).toBe(2);
    expect(elemek[0].querySelector('.cimke')!.textContent).toContain('Szerkesztés a Manifoldban');
    expect(elemek[0].querySelector('.jelenlegi')).not.toBeNull();
    expect(elemek[0].querySelector('.ido')!.textContent).toContain('SZERK-20261002-100500');
    expect(elemek[1].querySelector('.cimke')!.textContent).toContain('Kézi változás');
  });

  it('csak md-jegyzethez és csak nyitott szakaszban kérdez', async () => {
    elozmenyek(false);
    await Promise.resolve();
    expect(kerelmek.some((r) => r.url.startsWith('/api/vault/elozmeny'))).toBe(false);
    cleanup();
    const k = kornyezet();
    render(Elozmenyek, { props: { ut: 'Kep.png', nyitva: true }, context: k.context });
    expect(await screen.findByText(/Markdown-jegyzetekhez/)).toBeTruthy();
    expect(kerelmek.some((r) => r.url.startsWith('/api/vault/elozmeny'))).toBe(false);
  });

  it('hiba: a core 404-e magyar jelzés', async () => {
    vi.stubGlobal('fetch', async () => valasz({ hiba: 'x' }, 404));
    elozmenyek();
    expect((await screen.findByRole('alert')).textContent).toContain('nem érhetők el');
  });

  it('egy elemre kattintva megnyílik a diff-párbeszéd; a legújabb nem állítható vissza, a régebbi igen', async () => {
    vi.stubGlobal('fetch', async (url: string) => {
      const u = new URL(url, 'http://127.0.0.1/');
      if (u.pathname === '/api/vault/elozmeny/valtozat') return valasz({ sha: 'x', ut_akkor: 'J.md', szoveg: 'új\n', szoveg_ok: null, elozo: 'régi\n', elozo_ok: null });
      if (u.pathname === '/api/vault/fajl') return valasz({ ut: 'J.md', tartalom: 'jelenlegi\n', hash: 'h' });
      return valasz({
        ut: 'J.md',
        bejegyzesek: [
          { sha: 'b'.repeat(40), datum: '2026-10-02T10:05:00+02:00', targy: '', tipus: 'szerk', cimke: 'Szerkesztés a Manifoldban', kor: null, forras: null, statusz: 'M', ut_akkor: 'J.md', regi_ut: null, elozo: null, visszaallithato: false },
          { sha: 'a'.repeat(40), datum: '2026-10-02T09:00:00+02:00', targy: '', tipus: 'kezi', cimke: 'Kézi változás', kor: null, forras: 'kezi', statusz: 'A', ut_akkor: 'J.md', regi_ut: null, elozo: null, visszaallithato: true },
        ],
      });
    });
    elozmenyek();
    const elemek = await screen.findAllByRole('button', { name: /Szerkesztés a Manifoldban|Kézi változás/ });
    await fireEvent.click(elemek[0]);
    const gomb = (await screen.findByRole('button', { name: /Visszaállítás erre a verzióra/ })) as HTMLButtonElement;
    await waitFor(() => expect(gomb.title).toMatch(/jelenlegi változat/));
    expect(gomb.disabled).toBe(true);
    await fireEvent.click(screen.getByRole('button', { name: 'Bezárás' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    await fireEvent.click((await screen.findAllByRole('button', { name: /Kézi változás/ }))[0]);
    const gomb2 = (await screen.findByRole('button', { name: /Visszaállítás erre a verzióra/ })) as HTMLButtonElement;
    await waitFor(() => expect(gomb2.disabled).toBe(false));
  });

  it('visszaállítás: nyitott dokumentum mentése, core-hívás, újratöltés, értesítés „Visszavonás” művelettel', async () => {
    const hivasok: string[] = [];
    const dok = {
      allapot: 'tiszta', csakOlvashato: null,
      ment: vi.fn(async () => (hivasok.push('ment'), { ok: true })),
      kulsoValtozas: vi.fn(async () => void hivasok.push('ujratolt')),
      fajlSzoveg: () => 'x',
    };
    vi.spyOn(szerkesztok.dokumentumok, 'kap').mockReturnValue(dok as never);
    vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
      const u = new URL(url, 'http://127.0.0.1/');
      if (u.pathname === '/api/vault/elozmeny/valtozat') return valasz({ sha: 'x', ut_akkor: 'J.md', szoveg: 'új\n', szoveg_ok: null, elozo: 'régi\n', elozo_ok: null });
      if (u.pathname === '/api/vault/elozmeny/visszaallit') {
        hivasok.push('visszaallit:' + JSON.parse(String(init!.body)).sha.slice(0, 3));
        return valasz({ ok: true, ut: 'J.md', sha: 'c'.repeat(40), visszaallitott: 'a'.repeat(40) });
      }
      if (u.pathname === '/api/pillanat/vault/visszavonas') {
        hivasok.push('visszavonas:' + JSON.parse(String(init!.body)).sha.slice(0, 3));
        return valasz({ ok: true, sha: 'd'.repeat(40) });
      }
      return valasz({
        ut: 'J.md',
        bejegyzesek: [
          { sha: 'b'.repeat(40), datum: '2026-10-02T10:05:00+02:00', targy: '', tipus: 'szerk', cimke: 'Szerkesztés', kor: null, forras: null, statusz: 'M', ut_akkor: 'J.md', regi_ut: null, elozo: null, visszaallithato: false },
          { sha: 'a'.repeat(40), datum: '2026-10-02T09:00:00+02:00', targy: '', tipus: 'kezi', cimke: 'Kézi változás', kor: null, forras: 'kezi', statusz: 'A', ut_akkor: 'J.md', regi_ut: null, elozo: null, visszaallithato: true },
        ],
      });
    });
    elozmenyek();
    await fireEvent.click((await screen.findAllByRole('button', { name: /Kézi változás/ }))[0]);
    const gomb = (await screen.findByRole('button', { name: /Visszaállítás erre a verzióra/ })) as HTMLButtonElement;
    await waitFor(() => expect(gomb.disabled).toBe(false));
    await fireEvent.click(gomb);
    await fireEvent.click(await screen.findByRole('button', { name: 'Visszaállítás' }));
    await waitFor(() => expect(hivasok).toContain('ujratolt'));
    expect(hivasok.slice(0, 3)).toEqual(['ment', 'visszaallit:aaa', 'ujratolt']);
    const e = ertesitesek.lista.find((x) => x.cim === 'Visszaállítva')!;
    expect(e.muvelet?.nev).toBe('Visszavonás');
    e.muvelet!.futtat();
    await waitFor(() => expect(hivasok).toContain('visszavonas:ccc'));
  });

  it('ütköző dokumentumnál a visszaállítás előbb döntést kér, és nem ír', async () => {
    const dok = { allapot: 'utkozes', csakOlvashato: null, ment: vi.fn(), kulsoValtozas: vi.fn(), fajlSzoveg: () => '' };
    vi.spyOn(szerkesztok.dokumentumok, 'kap').mockReturnValue(dok as never);
    const hivasok: string[] = [];
    vi.stubGlobal('fetch', async (url: string) => {
      const u = new URL(url, 'http://127.0.0.1/');
      hivasok.push(u.pathname);
      if (u.pathname === '/api/vault/elozmeny/valtozat') return valasz({ sha: 'x', ut_akkor: 'J.md', szoveg: 'új\n', szoveg_ok: null, elozo: null, elozo_ok: 'nincs' });
      return valasz({
        ut: 'J.md',
        bejegyzesek: [
          { sha: 'b'.repeat(40), datum: '2026-10-02T10:05:00+02:00', targy: '', tipus: 'szerk', cimke: 'Szerkesztés', kor: null, forras: null, statusz: 'M', ut_akkor: 'J.md', regi_ut: null, elozo: null, visszaallithato: false },
          { sha: 'a'.repeat(40), datum: '2026-10-02T09:00:00+02:00', targy: '', tipus: 'kezi', cimke: 'Kézi változás', kor: null, forras: 'kezi', statusz: 'A', ut_akkor: 'J.md', regi_ut: null, elozo: null, visszaallithato: true },
        ],
      });
    });
    elozmenyek();
    await fireEvent.click((await screen.findAllByRole('button', { name: /Kézi változás/ }))[0]);
    const gomb = (await screen.findByRole('button', { name: /Visszaállítás erre a verzióra/ })) as HTMLButtonElement;
    await waitFor(() => expect(gomb.disabled).toBe(false));
    await fireEvent.click(gomb);
    await fireEvent.click(await screen.findByRole('button', { name: 'Visszaállítás' }));
    await waitFor(() => expect(ertesitesek.lista.some((x) => x.cim === 'A visszaállítás előbb döntést kér')).toBe(true));
    expect(hivasok).not.toContain('/api/vault/elozmeny/visszaallit');
    expect(dok.ment).not.toHaveBeenCalled();
  });
});
