// A Bases cellaszerkesztése (C12b 9. lépés): a `cellaIr` a nyitott dokumentumon át ír (hash-alapú mentés, pillanatkép,
// séma-megerősítés), a Tabla cellája dupla kattintásra / ↩-re szerkeszthető, a jelölőnégyzet egy kattintásra vált,
// a mentés után „Visszavonás” értesítés. Ál-core-ral (fetch-csonk: fájl, tulajdonság-számoló, séma, visszavonás).

import { ChangeSet } from '@codemirror/state';
import { cleanup, fireEvent, render, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cellaErtesites, cellaIr, cellaOlvas } from '../src/bazis/cellaIr';
import Tabla from '../src/bazis/Tabla.svelte';
import type { Oszlop, Sor, Valasz } from '../src/bazis/tipusok';
import { ApiHiba } from '../src/lib/core/api';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import type { FajlIras, FajlIrasKeres, FajlOlvasas, VaultApi } from '../src/szerkeszto/dokumentum/api';
import { Dokumentumok } from '../src/szerkeszto/dokumentum/dokumentum.svelte';
import type { ModositEredmeny, Muvelet, Sema, TulajdonsagApi } from '../src/szerkeszto/tulajdonsagok/tipusok';

function hash(s: string): string {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
  return (h >>> 0).toString(16) + ':' + s.length;
}

const UT = 'K/Jegyzet 1.md';
const ALAP_SZOVEG = '---\nStatus: Review\nRating: 1\nDone: true\nTags:\n  - a\n  - b\n---\nTörzs\n';

// ---------------------------------------------------------------------- az ál-core közös része

type Fm = Array<{ kulcs: string; sorok: string[] }>;

function fmBontas(fm: string | null): Fm {
  if (!fm) return [];
  const sorok = fm.split('\n').slice(1);
  const ki: Fm = [];
  for (const s of sorok) {
    if (s === '---' || s === '') continue;
    if (/^\s+- /.test(s) && ki.length) ki[ki.length - 1].sorok.push(s);
    else ki.push({ kulcs: s.split(':')[0], sorok: [s] });
  }
  return ki;
}

function ertekBol(b: { kulcs: string; sorok: string[] }): unknown {
  const ertek = b.sorok[0].slice(b.kulcs.length + 1).trim();
  if (b.sorok.length > 1) return b.sorok.slice(1).map((x) => x.replace(/^\s+- /, ''));
  if (ertek === 'true' || ertek === 'false') return ertek === 'true';
  if (ertek !== '' && !Number.isNaN(Number(ertek))) return Number(ertek);
  return ertek === '' ? null : ertek;
}

const TIPUSOK: Record<string, string> = { Rating: 'number', Done: 'checkbox', Tags: 'tags' };

function sorokKulcsErtek(kulcs: string, ertek: unknown): string[] {
  if (Array.isArray(ertek)) return [`${kulcs}:`, ...ertek.map((x) => `  - ${x}`)];
  return [`${kulcs}: ${ertek === '' || ertek === null ? '' : String(ertek)}`.trimEnd()];
}

function modositFm(fm: string | null, m: { muvelet: string; kulcs: string; ertek?: unknown }): string {
  const b = fmBontas(fm);
  const i = b.findIndex((x) => x.kulcs === m.kulcs);
  if (m.muvelet === 'torol') {
    if (i >= 0) b.splice(i, 1);
  } else if (i >= 0) b[i].sorok = sorokKulcsErtek(m.kulcs, m.ertek);
  else b.push({ kulcs: m.kulcs, sorok: sorokKulcsErtek(m.kulcs, m.ertek) });
  return `---\n${b.flatMap((x) => x.sorok).join('\n')}\n---\n`;
}

class AlTulajdonsagok implements TulajdonsagApi {
  hivasok: Array<{ m: Muvelet; megerosit: boolean }> = [];
  mod: 'ok' | 'sertes' | 'hiba' = 'ok';
  elozetes?: () => void;
  async elemez(_ut: string, fm: string | null) {
    const b = fmBontas(fm);
    return {
      van: fm !== null,
      tulajdonsagok: b.map((x) => ({ kulcs: x.kulcs, tipus: (TIPUSOK[x.kulcs] ?? 'text') as 'text', ertek: ertekBol(x), ervenyes: true })),
      hiba: null,
      kulcsok: b.map((x) => x.kulcs),
      problemak: [],
      osztaly: 'x',
    };
  }
  async modosit(_ut: string, fm: string | null, m: Muvelet, megerosit: boolean): Promise<ModositEredmeny> {
    this.hivasok.push({ m, megerosit });
    this.elozetes?.();
    if (this.mod === 'hiba')
      return { ok: false, fm_uj: null, megerositheto: false, valtozas: false, problemak: [{ kod: 'ertek_tipus', szint: 'hiba', kulcs: m.kulcs, ertek: null, uzenet: 'a szám nem szám' }] };
    if (this.mod === 'sertes' && !megerosit)
      return { ok: false, fm_uj: null, megerositheto: true, valtozas: true, problemak: [{ kod: 'status_ertek', szint: 'sertes', kulcs: m.kulcs, ertek: 'X', uzenet: 'A Status értéke nem illik a sémába.' }] };
    return { ok: true, fm_uj: modositFm(fm, m as never), megerositheto: false, valtozas: true, problemak: [] };
  }
  async sema(): Promise<Sema> {
    return { mezosorrend: [], extra_kulcsok: [], tags_ertekkeszlet: [], status_ertekkeszlet: ['Completed', 'In progress', 'Review'], status_gazdai: true, osztaly: null };
  }
}

// ---------------------------------------------------------------------- cellaIr / cellaOlvas közvetlenül

class AlVault implements VaultApi {
  lemez = new Map<string, string>([[UT, ALAP_SZOVEG]]);
  irasok: FajlIrasKeres[] = [];
  async olvas(ut: string): Promise<FajlOlvasas> {
    const t = this.lemez.get(ut);
    if (t === undefined) throw new ApiHiba(404, 'nincs');
    return { ut, tartalom: t, hash: hash(t), jel: '', mtime: 0 };
  }
  async ir(k: FajlIrasKeres): Promise<FajlIras> {
    const t = this.lemez.get(k.ut)!;
    if (hash(t) !== k.alap) throw new ApiHiba(409, 'ütközés', { utkozes: true, hash: hash(t) });
    this.irasok.push(k);
    this.lemez.set(k.ut, k.tartalom);
    return { ok: true, ut: k.ut, hash: hash(k.tartalom), jel: '', uzenet: 'mentve', pillanat: k.pillanat ? 'c0ffee1' : null, elotte: null, git: true };
  }
}

describe('cellaIr', () => {
  let vault: AlVault;
  let dk: Dokumentumok;
  let api: AlTulajdonsagok;

  beforeEach(() => {
    vault = new AlVault();
    dk = new Dokumentumok(vault);
    api = new AlTulajdonsagok();
  });
  afterEach(() => ertesitesek.lista.splice(0));

  it('a nyers érték olvasása: kulcs kis-nagybetűtől függetlenül, lista, hiányzó kulcs', async () => {
    expect(await cellaOlvas(UT, 'rating', { api, dk })).toEqual({ kulcs: 'Rating', van: true, tipus: 'number', ertek: 1 });
    expect((await cellaOlvas(UT, 'Tags', { api, dk })).ertek).toEqual(['a', 'b']);
    expect(await cellaOlvas(UT, 'Nincs', { api, dk })).toEqual({ kulcs: 'Nincs', van: false, tipus: null, ertek: null });
    expect(vault.irasok).toEqual([]); // az olvasás nem ír
  });

  it('beírja az értéket a frontmatterbe, a törzs érintetlen; pillanatképet készít és visszaadja', async () => {
    const r = await cellaIr(UT, 'Rating', 4, 'number', false, { api, dk });
    expect(r).toEqual({ ok: true, pillanat: 'c0ffee1' });
    expect(vault.lemez.get(UT)).toBe('---\nStatus: Review\nRating: 4\nDone: true\nTags:\n  - a\n  - b\n---\nTörzs\n');
    expect(vault.irasok).toHaveLength(1);
    expect(vault.irasok[0]).toMatchObject({ elso: true, pillanat: true });
    expect(dk.kap(UT)).toBeUndefined(); // a dokumentum kikerült
  });

  it('lista és üres érték: a kulcs megmarad', async () => {
    await cellaIr(UT, 'Tags', ['x', 'y', 'z'], 'tags', false, { api, dk });
    expect(vault.lemez.get(UT)).toContain('Tags:\n  - x\n  - y\n  - z\n---');
    await cellaIr(UT, 'Status', '', 'text', false, { api, dk });
    expect(vault.lemez.get(UT)).toContain('\nStatus:\nRating');
  });

  it('változatlan érték: nincs írás', async () => {
    const r = await cellaIr(UT, 'Rating', 1, 'number', false, { api, dk });
    expect(r.ok).toBe(true);
    expect(vault.irasok).toEqual([]);
  });

  it('séma-sértés: megerősítés nélkül nem ír, a „Mégis beírom” megerősítéssel igen', async () => {
    api.mod = 'sertes';
    const r = await cellaIr(UT, 'Status', 'X', 'text', false, { api, dk });
    expect(r.ok).toBe(false);
    expect(r.fuggo?.[0].uzenet).toContain('nem illik a sémába');
    expect(vault.lemez.get(UT)).toBe(ALAP_SZOVEG);
    const r2 = await cellaIr(UT, 'Status', 'X', 'text', true, { api, dk });
    expect(r2.ok).toBe(true);
    expect(api.hivasok.map((h) => h.megerosit)).toEqual([false, true]);
    expect(vault.lemez.get(UT)).toContain('Status: X');
  });

  it('a hiba szintű érték megerősítéssel sem íródik; az ok látszik', async () => {
    api.mod = 'hiba';
    const r = await cellaIr(UT, 'Rating', 'x', 'number', true, { api, dk });
    expect(r).toEqual({ ok: false, elutasitva: 'a szám nem szám' });
    expect(vault.lemez.get(UT)).toBe(ALAP_SZOVEG);
  });

  it('ha közben a frontmatter megváltozik, a válasz elavult: nem ír', async () => {
    api.elozetes = () => {
      const dok = dk.kap(UT)!;
      const cs = ChangeSet.of([{ from: 4, to: 4, insert: 'Uj: 1\n' }], dok.szoveg.length);
      dok.valtozott(cs, cs.apply(dok.szoveg), null);
    };
    const r = await cellaIr(UT, 'Rating', 4, 'number', false, { api, dk });
    expect(r.ok).toBe(false);
    expect(r.elutasitva).toContain('megváltozott');
    expect(vault.lemez.get(UT)).not.toContain('Rating: 4'); // csak a közbeszúrt (más által végzett) szerkesztés mentődik
  });

  it('a már nyitott szerkesztőben nincs pillanatkép (a szerkesztés része, ⌘Z), a szöveg mégis mentődik', async () => {
    const dok = await dk.megnyit(UT);
    const le = dok.csatol({ alkalmaz() {} });
    const r = await cellaIr(UT, 'Rating', 7, 'number', false, { api, dk });
    expect(r).toEqual({ ok: true, pillanat: null });
    expect(vault.irasok[0].pillanat).toBe(false);
    expect(vault.lemez.get(UT)).toContain('Rating: 7');
    le();
  });

  it('eltűnt vagy csak olvasható jegyzet: érthető elutasítás', async () => {
    const r = await cellaIr('K/Nincs.md', 'Rating', 1, 'number', false, { api, dk });
    expect(r.ok).toBe(false);
    expect(r.elutasitva).toBeTruthy();
  });
});

describe('értesítés és visszavonás', () => {
  afterEach(() => {
    ertesitesek.lista.splice(0);
    vi.unstubAllGlobals();
  });

  it('pillanatkép nélkül nincs értesítés', () => {
    cellaErtesites('Jegyzet', 'Rating', null);
    expect(ertesitesek.lista).toHaveLength(0);
  });

  it('a „Visszavonás” a pillanatkép visszavonását kéri a core-tól, és sikerről értesít', async () => {
    const kerelmek: Array<[string, unknown]> = [];
    vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
      kerelmek.push([url, JSON.parse(String(init?.body))]);
      return new Response(JSON.stringify({ ok: true, sha: 'f00' }), { status: 200 });
    });
    cellaErtesites('Jegyzet', 'Rating', 'c0ffee1');
    const e = ertesitesek.lista.at(-1)!;
    expect(e.cim).toBe('Rating módosítva');
    expect(e.muvelet?.nev).toBe('Visszavonás');
    e.muvelet!.futtat();
    await vi.waitFor(() => expect(ertesitesek.lista.some((x) => x.cim === 'Visszavonva')).toBe(true));
    expect(kerelmek).toEqual([['/api/pillanat/vault/visszavonas', { sha: 'c0ffee1' }]]);
  });
});

// ---------------------------------------------------------------------- a Tabla cellája

const OSZLOPOK: Oszlop[] = [
  { id: 'file.name', nev: 'Fájlnév', ter: 'file', tipus: 'text', szerkesztheto: false, szelesseg: null },
  { id: 'Status', nev: 'Status', ter: 'note', tipus: 'text', szerkesztheto: true, szelesseg: null },
  { id: 'Rating', nev: 'Értékelés', ter: 'note', tipus: 'number', szerkesztheto: true, szelesseg: null },
  { id: 'Done', nev: 'Kész', ter: 'note', tipus: 'checkbox', szerkesztheto: true, szelesseg: null },
  { id: 'Tags', nev: 'Címkék', ter: 'note', tipus: 'tags', szerkesztheto: true, szelesseg: null },
];

function tablaValasz(md = true): Valasz {
  const sor: Sor = {
    ut: UT,
    nev: 'Jegyzet 1',
    md,
    cellak: [{ t: 'link', cel: UT, ut: UT, nev: 'Jegyzet 1' }, 'Review', 1, true, { t: 'lista', e: ['a', 'b'] }],
  };
  return {
    ok: true,
    nezetek: [{ nev: 'T', tipus: 'table', ismert: true }],
    nezet: { index: 0, nev: 'T', tipus: 'table', eredeti_tipus: 'table', beallitas: {} },
    oszlopok: OSZLOPOK,
    sorok: [sor],
    csoportok: null,
    osszesitok: {},
    osszes: 1,
    levagva: false,
    hibak: [],
    figyelmeztetesek: [],
    ido_ms: 1,
    generacio: 1,
  };
}

describe('Tabla: cellaszerkesztés', () => {
  let lemez: Map<string, string>;
  let putok: FajlIrasKeres[];
  let kerelmek: Array<[string, unknown]>;
  const tul = new AlTulajdonsagok();

  beforeEach(() => {
    lemez = new Map([[UT, ALAP_SZOVEG]]);
    putok = [];
    kerelmek = [];
    tul.hivasok = [];
    tul.mod = 'ok';
    vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
      const u = new URL(url, 'http://127.0.0.1/');
      const valasz = (s: number, x: unknown) => new Response(JSON.stringify(x), { status: s, headers: { 'Content-Type': 'application/json' } });
      const torzs = init?.body ? JSON.parse(String(init.body)) : null;
      kerelmek.push([`${init?.method ?? 'GET'} ${u.pathname}`, torzs]);
      if (u.pathname === '/api/vault/fajl' && (init?.method ?? 'GET') === 'GET') {
        const t = lemez.get(u.searchParams.get('ut')!)!;
        return valasz(200, { ut: UT, tartalom: t, hash: hash(t), jel: '', mtime: 0 });
      }
      if (u.pathname === '/api/vault/fajl') {
        putok.push(torzs);
        lemez.set(torzs.ut, torzs.tartalom);
        return valasz(200, { ok: true, ut: torzs.ut, hash: hash(torzs.tartalom), jel: '', uzenet: 'mentve', pillanat: torzs.pillanat ? 'abc1234' : null, elotte: null, git: true });
      }
      if (u.pathname === '/api/vault/tulajdonsagok/elemez') return valasz(200, await tul.elemez(torzs.ut, torzs.fm));
      if (u.pathname === '/api/vault/tulajdonsagok/modosit')
        return valasz(200, await tul.modosit(torzs.ut, torzs.fm, { muvelet: torzs.muvelet, kulcs: torzs.kulcs, ertek: torzs.ertek } as never, torzs.megerosit));
      if (u.pathname === '/api/vault/sema') return valasz(200, await tul.sema());
      return valasz(200, { ok: true, sha: 'x' });
    });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    ertesitesek.lista.splice(0);
  });

  const cella = (c: HTMLElement, i: number) => c.querySelectorAll<HTMLElement>('.sor [role=cell]')[i];
  const szerkesztoMezo = (c: HTMLElement) => c.querySelector<HTMLInputElement | HTMLSelectElement>('.szerkeszto input, .szerkeszto select')!;
  /** megvárja a mezőt (a „…” betöltés után jelenik meg) */
  const mezoVar = (c: HTMLElement) =>
    waitFor(() => {
      const m = szerkesztoMezo(c) as HTMLInputElement;
      expect(m).not.toBeNull();
      return m;
    });
  const figyVar = (c: HTMLElement) =>
    waitFor(() => {
      const m = c.querySelector<HTMLElement>('.szerkeszto [role=alert]');
      expect(m).not.toBeNull();
      return m!;
    });

  it('a szám-cella dupla kattintásra szerkeszthető: a nyers értékből indul, ↩ ment, a cella visszaáll', async () => {
    const { container } = render(Tabla, { props: { valasz: tablaValasz(), cellaIras: true } });
    await fireEvent.dblClick(cella(container, 2));
    const mezo = await waitFor(() => {
      const m = szerkesztoMezo(container) as HTMLInputElement;
      expect(m).not.toBeNull();
      expect(m.value).toBe('1');
      return m;
    });
    await fireEvent.input(mezo, { target: { value: '4,5' } });
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    await waitFor(() => expect(putok).toHaveLength(1));
    expect(putok[0].tartalom).toContain('Rating: 4.5');
    expect(putok[0].pillanat).toBe(true);
    await waitFor(() => expect(container.querySelector('.szerkeszto')).toBeNull());
    const ert = ertesitesek.lista.at(-1)!;
    expect(ert.cim).toBe('Rating módosítva');
    expect(ert.muvelet?.nev).toBe('Visszavonás');
  });

  it('az Esc elvet, a változatlan érték nem ír', async () => {
    const { container } = render(Tabla, { props: { valasz: tablaValasz(), cellaIras: true } });
    await fireEvent.dblClick(cella(container, 2));
    let mezo = await mezoVar(container);
    await waitFor(() => expect(mezo.value).toBe('1'));
    await fireEvent.input(mezo, { target: { value: '9' } });
    await fireEvent.keyDown(mezo, { key: 'Escape' });
    await waitFor(() => expect(container.querySelector('.szerkeszto')).toBeNull());
    expect(putok).toHaveLength(0);
    await fireEvent.dblClick(cella(container, 2));
    mezo = await mezoVar(container);
    await waitFor(() => expect(mezo.value).toBe('1'));
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    await waitFor(() => expect(container.querySelector('.szerkeszto')).toBeNull());
    expect(putok).toHaveLength(0);
  });

  it('a lista-cella vesszős szövegként szerkeszthető', async () => {
    const { container } = render(Tabla, { props: { valasz: tablaValasz(), cellaIras: true } });
    await fireEvent.dblClick(cella(container, 4));
    const mezo = await waitFor(() => {
      const m = szerkesztoMezo(container) as HTMLInputElement;
      expect(m.value).toBe('a, b');
      return m;
    });
    await fireEvent.input(mezo, { target: { value: 'a, b, c' } });
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    await waitFor(() => expect(putok).toHaveLength(1));
    expect(putok[0].tartalom).toContain('Tags:\n  - a\n  - b\n  - c\n---');
  });

  it('a Status választó a séma értékkészletével; a választás azonnal ment', async () => {
    const { container } = render(Tabla, { props: { valasz: tablaValasz(), cellaIras: true } });
    await fireEvent.dblClick(cella(container, 1));
    const sel = await waitFor(() => {
      const s = container.querySelector<HTMLSelectElement>('.szerkeszto select')!;
      expect([...s.options].map((o) => o.value)).toEqual(['', 'Completed', 'In progress', 'Review']);
      return s;
    });
    await fireEvent.change(sel, { target: { value: 'Completed' } });
    await waitFor(() => expect(putok).toHaveLength(1));
    expect(putok[0].tartalom).toContain('Status: Completed');
  });

  it('a jelölőnégyzet egy kattintásra vált (nyers értékről: igaz → hamis)', async () => {
    const { container } = render(Tabla, { props: { valasz: tablaValasz(), cellaIras: true } });
    await fireEvent.click(container.querySelector('[aria-label="Kész váltása"]')!);
    await waitFor(() => expect(putok).toHaveLength(1));
    expect(putok[0].tartalom).toContain('Done: false');
  });

  it('séma-sértésnél a mező nyitva marad, „Mégis beírom” megerősítéssel ír', async () => {
    tul.mod = 'sertes';
    const { container } = render(Tabla, { props: { valasz: tablaValasz(), cellaIras: true } });
    await fireEvent.dblClick(cella(container, 2));
    const mezo = await waitFor(() => {
      const m = szerkesztoMezo(container) as HTMLInputElement;
      expect(m.value).toBe('1');
      return m;
    });
    await fireEvent.input(mezo, { target: { value: '5' } });
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    const figy = await figyVar(container);
    expect(figy.textContent).toContain('nem illik a sémába');
    expect(putok).toHaveLength(0);
    const gombok = [...figy.querySelectorAll('button')];
    await fireEvent.click(gombok.find((g) => g.textContent === 'Mégis beírom')!);
    await waitFor(() => expect(putok).toHaveLength(1));
    expect(tul.hivasok.map((h) => h.megerosit)).toEqual([false, true]);
  });

  it('a hiba szintű érték: az ok látszik, a mező nyitva marad, a fájl érintetlen', async () => {
    tul.mod = 'hiba';
    const { container } = render(Tabla, { props: { valasz: tablaValasz(), cellaIras: true } });
    await fireEvent.dblClick(cella(container, 2));
    const mezo = await waitFor(() => {
      const m = szerkesztoMezo(container) as HTMLInputElement;
      expect(m.value).toBe('1');
      return m;
    });
    await fireEvent.input(mezo, { target: { value: '5' } });
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    await waitFor(() => expect(container.querySelector('.szerkeszto [role=alert]')?.textContent).toContain('a szám nem szám'));
    expect(putok).toHaveLength(0);
    expect(container.querySelector('.szerkeszto input')).not.toBeNull();
  });

  it('a nem jegyzet sor, a fájl-oszlop és az Olvasó cellája nem szerkeszthető', async () => {
    const a = render(Tabla, { props: { valasz: tablaValasz(), cellaIras: true } });
    await fireEvent.dblClick(cella(a.container, 0)); // file.name
    expect(a.container.querySelector('.szerkeszto')).toBeNull();
    a.unmount();
    const b = render(Tabla, { props: { valasz: tablaValasz(false), cellaIras: true } });
    await fireEvent.dblClick(cella(b.container, 2));
    expect(b.container.querySelector('.szerkeszto')).toBeNull();
    b.unmount();
    const c = render(Tabla, { props: { valasz: tablaValasz(), cellaIras: false } });
    await fireEvent.dblClick(cella(c.container, 2));
    expect(c.container.querySelector('.szerkeszto')).toBeNull();
    expect(c.container.querySelector('[aria-label="Kész váltása"]')).toBeNull();
    expect(kerelmek).toEqual([]);
  });

  it('billentyűzettel: nyíl a szomszéd cellára, ↩ szerkeszt', async () => {
    const { container } = render(Tabla, { props: { valasz: tablaValasz(), cellaIras: true } });
    const c1 = cella(container, 1);
    c1.focus();
    await fireEvent.keyDown(c1, { key: 'ArrowRight' });
    await waitFor(() => expect(document.activeElement).toBe(cella(container, 2)));
    await fireEvent.keyDown(cella(container, 2), { key: 'Enter' });
    await waitFor(() => expect(container.querySelector('.szerkeszto')).not.toBeNull());
  });
});
