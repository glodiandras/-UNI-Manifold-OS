// A címmező életciklus-kapuja a valódi, meglévő átnevező szolgáltatásban is érvényesül.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, waitFor } from '@testing-library/svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { atnevezesErtesites, atnevezesVegrehajt } from '../src/szerkeszto/linkek/atnevezes';
import { szerkesztok } from '../src/szerkeszto/szerkesztok.svelte';
import FajlCim from '../src/szerkeszto/FajlCim.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { belep } from '../src/lib/fokusz/hatokor';

const eredmeny = { ok: true as const, regi: 'Title.md', uj: 'New.md', modositott: [], pillanat: 'snapshot', ms: 1 };
const valasz = (r: unknown, status = 200) => new Response(JSON.stringify(r), { status, headers: { 'Content-Type': 'application/json' } });
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); ertesitesek.lista.length = 0; szerkesztok.atnevezesAlatt.clear(); });

describe('U01: a rename szolgáltatás életciklus-kapuja', () => {
  it('a belső mentés/lezárás közben megszűnt kérőből nem lesz POST', async () => {
    let felold!: () => void;
    vi.spyOn(szerkesztok.dokumentumok, 'mindLezar').mockReturnValue(new Promise<void>(r => (felold = r)));
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
    let aktiv = true;
    const r = atnevezesVegrehajt('Title.md', 'New.md', 'plan', () => aktiv).catch(e => e);
    aktiv = false; felold();
    expect(await r).toBeInstanceOf(Error);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('409 nyitott után a késleltetés alatt megszűnt kérő nem küld második POST-ot', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    const lezar = vi.spyOn(szerkesztok.dokumentumok, 'mindLezar').mockResolvedValue(undefined);
    const fetch = vi.fn().mockResolvedValue(valasz({ hiba: 'Pending document', nyitott: true }, 409)); vi.stubGlobal('fetch', fetch);
    let aktiv = true;
    const r = atnevezesVegrehajt('Title.md', 'New.md', 'plan', () => aktiv).catch(e => e);
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    aktiv = false;
    await vi.advanceTimersByTimeAsync(400);
    expect(await r).toBeInstanceOf(Error);
    expect(lezar).toHaveBeenCalledTimes(2);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('siker után a meglévő snapshot-Undo mentés után fut, eredeti tervhashsel, H1-írás nélkül', async () => {
    const lezar = vi.spyOn(szerkesztok.dokumentumok, 'mindLezar').mockResolvedValue(undefined);
    const keresek: { url: string; body: unknown }[] = [];
    vi.stubGlobal('fetch', async (input: string, init?: RequestInit) => {
      keresek.push({ url: input, body: JSON.parse(String(init?.body)) });
      return valasz(input === '/api/vault/atnevezes' ? eredmeny : { ok: true });
    });
    const f = new Felulet({}); f.munkaterulet.megnyit('New.md');
    const r = await atnevezesVegrehajt('Title.md', 'New.md', 'plan', () => true);
    atnevezesErtesites(r, f);
    ertesitesek.lista.at(-1)!.muvelet!.futtat();
    await vi.waitFor(() => expect(keresek).toHaveLength(2));
    expect(keresek).toEqual([
      { url: '/api/vault/atnevezes', body: { ut: 'Title.md', uj: 'New.md', terv_hash: 'plan' } },
      { url: '/api/pillanat/vault/visszavonas', body: { sha: 'snapshot' } },
    ]);
    expect(lezar).toHaveBeenCalledTimes(2);
    await vi.waitFor(() => expect(f.munkaterulet.aktivFul!.ut).toBe('Title.md'));
  });

  it('valódi title/helper: a belső lezárás alatt megnyitott Setup megállítja a POST-ot, hibás globális rename-jelzés nélkül', async () => {
    let felold!: () => void;
    const lezar = vi.spyOn(szerkesztok.dokumentumok, 'mindLezar').mockResolvedValueOnce(undefined)
      .mockReturnValueOnce(new Promise<void>(r => (felold = r)));
    const kertek: string[] = [];
    vi.stubGlobal('fetch', async (url: string) => {
      kertek.push(url);
      return valasz({ ok: true, blokkolok: [], fajlok: [], terv_hash: 'plan' });
    });
    const f = new Felulet({}); const kesz = vi.fn();
    const c = render(FajlCim, { props: { ut: 'Title.md', onkesz: kesz }, context: new Map([[KORNYEZET_KULCS, { felulet: f }]]) });
    const mezo = c.getByRole('textbox') as HTMLInputElement;
    await fireEvent.input(mezo, { target: { value: 'New' } });
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    await waitFor(() => expect(lezar).toHaveBeenCalledTimes(2));
    const kilep = belep('setup');
    const masik = document.createElement('input'); document.body.appendChild(masik); masik.focus();
    try {
      felold();
      await waitFor(() => expect(mezo.disabled).toBe(false));
      expect(kertek).toEqual(['/api/vault/atnevezes/terv']);
      expect(ertesitesek.lista).toHaveLength(0);
      expect(mezo.value).toBe('New');
      expect(kesz).not.toHaveBeenCalled();
      expect(document.activeElement).toBe(masik);
    } finally { kilep(); masik.remove(); }
  });

  it('valódi title/helper: már elküldött írás sikere Setup alatt is tényleges Undo-értesítést ad, fókuszváltás nélkül', async () => {
    vi.spyOn(szerkesztok.dokumentumok, 'mindLezar').mockResolvedValue(undefined);
    let felold!: (r: Response) => void;
    const kertek: string[] = [];
    vi.stubGlobal('fetch', (url: string) => {
      kertek.push(url);
      return url === '/api/vault/atnevezes/terv'
        ? Promise.resolve(valasz({ ok: true, blokkolok: [], fajlok: [], terv_hash: 'plan' }))
        : new Promise<Response>(r => (felold = r));
    });
    const f = new Felulet({}); const kesz = vi.fn();
    const c = render(FajlCim, { props: { ut: 'Title.md', onkesz: kesz }, context: new Map([[KORNYEZET_KULCS, { felulet: f }]]) });
    const mezo = c.getByRole('textbox');
    await fireEvent.input(mezo, { target: { value: 'New' } });
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    await waitFor(() => expect(kertek).toContain('/api/vault/atnevezes'));
    const kilep = belep('setup');
    const masik = document.createElement('input'); document.body.appendChild(masik); masik.focus();
    try {
      felold(valasz(eredmeny));
      await waitFor(() => expect(ertesitesek.lista.at(-1)?.muvelet?.nev).toBe('Visszavonás'));
      expect(ertesitesek.lista.at(-1)).toMatchObject({ szint: 'siker', szoveg: 'Title.md → New.md' });
      expect(kesz).not.toHaveBeenCalled();
      expect(document.activeElement).toBe(masik);
    } finally { kilep(); masik.remove(); }
  });
});
