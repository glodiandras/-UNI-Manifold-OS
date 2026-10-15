// A `vault_valtozas` WS-esemény kezelője a szerkesztőben (C29.7a, T115): az „eltűnt” dokumentum visszatér, ha a fájl
// újra olvasható — akkor is, ha a core az újra megjelent fájlt nem `kulso`-nak, csak `utak`-nak jelöli (a hash a core
// saját utolsó írásáé). A globális `szerkesztok.dokumentumok`-on át, stubolt `fetch`-csel.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { Regiszter } from '../src/lib/parancsok/regiszter';
import { szerkesztoTelepit } from '../src/szerkeszto';
import { szerkesztok } from '../src/szerkeszto/szerkesztok.svelte';

const UT = 'Visszatero.md';
const hash = (s: string) => `h${s.length}:${[...s].reduce((h, c) => (h * 31 + c.charCodeAt(0)) | 0, 7)}`;
let lemez: Map<string, string>;
let le: () => void;
let k: CoreKapcsolat;

const valasz = (kod: number, adat: unknown) =>
  new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });

beforeEach(() => {
  lemez = new Map([[UT, '# Cím\n']]);
  vi.stubGlobal('fetch', async (url: string) => {
    const u = new URL(url, 'http://127.0.0.1/');
    const t = lemez.get(u.searchParams.get('ut') ?? '');
    if (u.pathname !== '/api/vault/fajl') return valasz(404, { hiba: 'nincs' });
    if (t === undefined) return valasz(404, { hiba: 'nincs ilyen fájl' });
    return valasz(200, { ut: UT, tartalom: t, hash: hash(t), jel: '', mtime: 0, kodolas_hiba: false });
  });
  k = new CoreKapcsolat('ws://127.0.0.1:1/ws');
  le = szerkesztoTelepit(new Regiszter(), k);
});

afterEach(() => {
  le();
  szerkesztok.dokumentumok.eldob(UT);
  for (const e of [...ertesitesek.lista]) ertesitesek.elvet(e.id);
  vi.unstubAllGlobals();
});

describe('az „eltűnt” dokumentum visszatérése a WS-eseményre (T115)', () => {
  it('a visszatért fájl `kulso`-ban: a dokumentum tiszta lesz', async () => {
    const d = await szerkesztok.dokumentumok.megnyit(UT);
    lemez.delete(UT);
    k.szetoszt({ tipus: 'vault_valtozas', utak: [], torolt: [UT], kulso: [] });
    expect(d.allapot).toBe('eltunt');
    lemez.set(UT, '# Cím\n');
    k.szetoszt({ tipus: 'vault_valtozas', utak: [UT], torolt: [], kulso: [UT] });
    await vi.waitFor(() => expect(d.allapot).toBe('tiszta'));
  });

  it('a visszatért fájl csak az `utak`-ban áll (a hash a core saját utolsó írásáé): a dokumentum akkor is visszatér', async () => {
    const d = await szerkesztok.dokumentumok.megnyit(UT);
    lemez.delete(UT);
    k.szetoszt({ tipus: 'vault_valtozas', utak: [], torolt: [UT], kulso: [] });
    expect(d.allapot).toBe('eltunt');
    lemez.set(UT, '# Cím\n');
    k.szetoszt({ tipus: 'vault_valtozas', utak: [UT], torolt: [], kulso: [] });
    await vi.waitFor(() => expect(d.allapot).toBe('tiszta'));
  });

  it('eltérő tartalommal visszatérve a tiszta dokumentum betölti a lemezen lévőt', async () => {
    const d = await szerkesztok.dokumentumok.megnyit(UT);
    lemez.delete(UT);
    k.szetoszt({ tipus: 'vault_valtozas', utak: [], torolt: [UT], kulso: [] });
    lemez.set(UT, '# Más\n');
    k.szetoszt({ tipus: 'vault_valtozas', utak: [UT], torolt: [], kulso: [UT] });
    await vi.waitFor(() => expect(d.allapot).toBe('tiszta'));
    expect(d.szoveg.toString()).toBe('# Más\n');
  });

  it('a nem „eltűnt” dokumentumot az `utak` önmagában nem érinti (a saját írás nem tölt újra)', async () => {
    const d = await szerkesztok.dokumentumok.megnyit(UT);
    const olvasasok = vi.fn();
    vi.stubGlobal('fetch', async () => {
      olvasasok();
      return valasz(200, { ut: UT, tartalom: '# Cím\n', hash: hash('# Cím\n'), jel: '', mtime: 0 });
    });
    k.szetoszt({ tipus: 'vault_valtozas', utak: [UT], torolt: [], kulso: [] });
    await new Promise((r) => setTimeout(r, 30));
    expect(olvasasok).not.toHaveBeenCalled();
    expect(d.allapot).toBe('tiszta');
  });
});

describe('WS-kiesés utáni szinkron (C29.7b, T107)', () => {
  const olvasasok = () => vi.fn();

  it('az első `hello` nem olvas; a második (újracsatlakozás) minden nyitott dokumentumot újraellenőriz', async () => {
    const d = await szerkesztok.dokumentumok.megnyit(UT);
    k.szetoszt({ tipus: 'hello', figyelmeztetesek: [] });
    await new Promise((r) => setTimeout(r, 20));
    expect(d.szoveg.toString()).toBe('# Cím\n');
    lemez.set(UT, '# Kiesés alatt írták\n'); // a WS-kiesés alatt kívülről módosult — esemény nem érkezett
    k.szetoszt({ tipus: 'hello', figyelmeztetesek: [] }); // újracsatlakozás
    await vi.waitFor(() => expect(d.szoveg.toString()).toBe('# Kiesés alatt írták\n'));
    expect(d.allapot).toBe('tiszta');
  });

  it('a mentetlen dokumentum az újracsatlakozáskor ütközést kap (a felhasználó dönt), nem íródik felül', async () => {
    const d = await szerkesztok.dokumentumok.megnyit(UT);
    const { ChangeSet } = await import('@codemirror/state');
    const v = ChangeSet.of([{ from: 0, insert: 'enyém ' }], d.szoveg.length);
    d.valtozott(v, v.apply(d.szoveg), null);
    k.szetoszt({ tipus: 'hello' });
    lemez.set(UT, '# Kívülről\n');
    k.szetoszt({ tipus: 'hello' });
    await vi.waitFor(() => expect(d.allapot).toBe('utkozes'));
    expect(d.szoveg.toString()).toBe('enyém # Cím\n');
  });

  it('`kimaradt` (a core eldobott eseményeket): minden nyitott dokumentum újraellenőrződik', async () => {
    const d = await szerkesztok.dokumentumok.megnyit(UT);
    lemez.set(UT, '# Elveszett esemény\n');
    k.szetoszt({ tipus: 'kimaradt', db: 7 });
    await vi.waitFor(() => expect(d.szoveg.toString()).toBe('# Elveszett esemény\n'));
    void olvasasok;
  });
});
