// A gépi írás a felületen (C16.5): a `gepi_iras` esemény → csendes újratöltés vagy ütközés, körönként egy
// értesítés „Visszavonás” gombbal ({sha} egy tételnél, {kor} többnél), a próba néma, a mentetlen-jelzés a WS-en.

import { ChangeSet, Text } from '@codemirror/state';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiHiba } from '../src/lib/core/api';
import { CoreKapcsolat, type CoreEsemeny } from '../src/lib/core/ws.svelte';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import type { FajlIras, FajlIrasKeres, FajlOlvasas, VaultApi } from '../src/szerkeszto/dokumentum/api';
import { Dokumentumok, type Dokumentum } from '../src/szerkeszto/dokumentum/dokumentum.svelte';
import { gepiIrasFigyel } from '../src/szerkeszto/gepiIras';

class AlCore implements VaultApi {
  lemez = new Map<string, string>();
  async olvas(ut: string): Promise<FajlOlvasas> {
    const t = this.lemez.get(ut);
    if (t === undefined) throw new ApiHiba(404, 'nincs ilyen fájl');
    return { ut, tartalom: t, hash: 'h:' + t, jel: '', mtime: 0, kodolas_hiba: false };
  }
  async ir(k: FajlIrasKeres): Promise<FajlIras> {
    this.lemez.set(k.ut, k.tartalom);
    return { ok: true, ut: k.ut, hash: 'h:' + k.tartalom, jel: '', uzenet: 'mentve', pillanat: null, elotte: null, git: true, figyelmeztetes: null };
  }
}

function gepel(d: Dokumentum, szoveg: string) {
  d.valtozott(ChangeSet.of([{ from: 0, to: d.szoveg.length, insert: szoveg }], d.szoveg.length), Text.of(szoveg.split('\n')), null);
}

const tick = () => new Promise((r) => setTimeout(r, 0));
const esemeny = (e: Partial<CoreEsemeny>): CoreEsemeny => ({ tipus: 'gepi_iras', kor: 'KARTYA-1', tetel: 't1', utak: ['A.md'], sha: 'a1', forras: 'mos-kartya', uzenet: 'kártyák', proba: false, ...e });

describe('gépi írás a felületen (C16.5)', () => {
  let core: AlCore;
  let dk: Dokumentumok;
  let kapcsolat: CoreKapcsolat;
  let kuldott: CoreEsemeny[];
  let keresek: { url: string; torzs: unknown }[];
  let le: () => void;

  beforeEach(() => {
    core = new AlCore();
    core.lemez.set('A.md', '# A');
    core.lemez.set('B.md', '# B');
    dk = new Dokumentumok(core);
    kapcsolat = new CoreKapcsolat('ws://x');
    kuldott = [];
    vi.spyOn(kapcsolat, 'kuld').mockImplementation((u) => (kuldott.push(u), true));
    keresek = [];
    vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
      keresek.push({ url: new URL(url, 'http://x/').pathname, torzs: init?.body ? JSON.parse(String(init.body)) : null });
      return new Response(JSON.stringify({ ok: true, sha: 'v1' }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    });
    ertesitesek.mindElvet();
    le = gepiIrasFigyel(kapcsolat, dk);
  });

  afterEach(() => {
    le();
    ertesitesek.mindElvet();
    vi.unstubAllGlobals();
  });

  it('a tiszta dokumentum csendben újratölt, a mentetlen ütközik', async () => {
    const a = await dk.megnyit('A.md');
    const b = await dk.megnyit('B.md');
    gepel(b, '# B gépelve');
    core.lemez.set('A.md', '# A\ngépi');
    core.lemez.set('B.md', '# B\ngépi');
    kapcsolat.szetoszt(esemeny({ utak: ['A.md', 'B.md', 'C.md'] }));
    await tick();
    expect(a.szoveg.toString()).toBe('# A\ngépi');
    expect(a.allapot).toBe('tiszta');
    expect(b.allapot).toBe('utkozes');
    expect(b.szoveg.toString()).toBe('# B gépelve');
  });

  it('körönként egy értesítés; a Visszavonás egy tételnél {sha}, többnél {kor}', async () => {
    const a = await dk.megnyit('A.md');
    kapcsolat.szetoszt(esemeny({}));
    const gepi = () => ertesitesek.lista.filter((e) => e.cim === 'Gépi írás');
    expect(gepi()).toHaveLength(1);
    expect(gepi()[0].szoveg).toBe('kártyák · 1 fájl');
    kapcsolat.szetoszt(esemeny({ kor: 'KARTYA-2', sha: 'c3' }));
    kapcsolat.szetoszt(esemeny({ tetel: 't2', sha: 'b2', utak: ['A.md', 'B.md'], uzenet: 'kártyák 2' }));
    expect(gepi()).toHaveLength(2);
    expect(gepi()[0].szoveg).toBe('2 tétel · 2 fájl · kártyák 2');

    gepi()[1].muvelet!.futtat(); // a KARTYA-2 kör: egy tétel
    await tick();
    expect(keresek.at(-1)).toEqual({ url: '/api/pillanat/vault/visszavonas', torzs: { sha: 'c3' } });

    core.lemez.set('A.md', '# A visszavonva');
    gepi()[0].muvelet!.futtat(); // a KARTYA-1 kör: két tétel
    await tick();
    await tick();
    expect(keresek.at(-1)).toEqual({ url: '/api/pillanat/vault/visszavonas', torzs: { kor: 'KARTYA-1' } });
    expect(a.szoveg.toString()).toBe('# A visszavonva'); // a nyitott dokumentum a visszavonás után is friss
    expect(ertesitesek.lista.some((e) => e.cim === 'Gépi írás visszavonva')).toBe(true);
  });

  it('a visszavonás hibája (ütközés) az érintett fájlokkal szól', async () => {
    vi.stubGlobal('fetch', async () =>
      new Response(JSON.stringify({ hiba: 'a visszavonás ütközik', utkozes: true, fajlok: ['A.md'] }), { status: 409, headers: { 'Content-Type': 'application/json' } }),
    );
    kapcsolat.szetoszt(esemeny({}));
    ertesitesek.lista.find((e) => e.cim === 'Gépi írás')!.muvelet!.futtat();
    await tick();
    const h = ertesitesek.lista.find((e) => e.szint === 'hiba')!;
    expect(h.szoveg).toContain('ütközik');
    expect(h.szoveg).toContain('A.md');
  });

  it('a próba-kör néma: nincs újratöltés, nincs értesítés', async () => {
    const a = await dk.megnyit('A.md');
    core.lemez.set('A.md', '# más');
    kapcsolat.szetoszt(esemeny({ proba: true, kor: 'KARTYA-1-proba' }));
    await tick();
    expect(a.szoveg.toString()).toBe('# A');
    expect(ertesitesek.lista).toHaveLength(0);
  });

  it('a mentetlen dokumentumok jelzése: változáskor, mentés után és újracsatlakozáskor', async () => {
    const a = await dk.megnyit('A.md');
    await tick();
    gepel(a, '# A gépelve');
    await tick();
    expect(kuldott.at(-1)).toEqual({ tipus: 'mentetlen', utak: ['A.md'] });
    await a.ment();
    await tick();
    expect(kuldott.at(-1)).toEqual({ tipus: 'mentetlen', utak: [] });
    const n = kuldott.length;
    kapcsolat.szetoszt({ tipus: 'hello' }); // új kapcsolat: a teljes halmaz megy újra
    expect(kuldott).toHaveLength(n + 1);
    expect(kuldott.at(-1)).toEqual({ tipus: 'mentetlen', utak: [] });
  });
});
