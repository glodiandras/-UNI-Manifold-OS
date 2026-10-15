// A Bases Kanban-nézete (C12b 10. lépés): oszlopok a groupBy szerint (Status: a séma sorrendje, üres oszloppal is),
// kártya áthúzása / áthelyezése menüből a jegyzet frontmatterébe, „Mégis beírom”, csak `.md` és note-tulajdonság húzható.

import { cleanup, fireEvent, render, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Kanban from '../src/bazis/Kanban.svelte';
import type { Csoport, Oszlop, Sor, Valasz } from '../src/bazis/tipusok';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';

const hash = (s: string) => `${s.length}:${[...s].reduce((h, c) => (h * 31 + c.charCodeAt(0)) | 0, 7)}`;

const OSZLOPOK: Oszlop[] = [
  { id: 'file.name', nev: 'Fájlnév', ter: 'file', tipus: 'text', szerkesztheto: false, szelesseg: null },
  { id: 'Status', nev: 'Status', ter: 'note', tipus: 'text', szerkesztheto: true, szelesseg: null },
];

const ut = (n: string) => `P/${n}.md`;
function sor(n: string, status: string | null, md = true): Sor {
  return { ut: ut(n), nev: n, md, cellak: [{ t: 'link', cel: ut(n), ut: ut(n), nev: n }, status] };
}

function csoport(kulcs: string | null, tol: number, db: number, huzhato = true): Csoport {
  return { kulcs, cimke: kulcs ?? '', tol, db, osszesitok: {}, huzhato };
}

function valasz(kieg: Partial<Valasz> = {}, csoportProp = 'Status'): Valasz {
  const sorok = [sor('A', null), sor('B', 'Review'), sor('C', 'Review')];
  return {
    ok: true,
    nezetek: [{ nev: 'Tábla', tipus: 'kanban', ismert: true }],
    nezet: { index: 0, nev: 'Tábla', tipus: 'kanban', eredeti_tipus: 'kanban', beallitas: { groupBy: { property: csoportProp } } },
    oszlopok: OSZLOPOK,
    sorok,
    csoportok: [csoport(null, 0, 1), csoport('Review', 1, 2)],
    osszesitok: {},
    fajl: { szuro: '', szuro_nezet: '', kepletek: {}, osszesitok: [], elerheto: [{ id: 'Status', nev: 'Status', ter: 'note', tipus: 'text' }] },
    osszes: 3,
    levagva: false,
    hibak: [],
    figyelmeztetesek: [],
    ido_ms: 1,
    generacio: 1,
    ...kieg,
  };
}

let lemez: Map<string, string>;
let putok: Array<{ ut: string; tartalom: string; pillanat: boolean }>;
let mod: 'ok' | 'sertes' = 'ok';
let modositasok: Array<{ ertek: unknown; megerosit: boolean; kulcs?: string }>;

beforeEach(() => {
  mod = 'ok';
  putok = [];
  modositasok = [];
  lemez = new Map([A, B, C].map((n) => [ut(n), `---\nStatus: ${n === A ? '' : 'Review'}\n---\n`] as const).map(([k, v]) => [k, v.replace('Status: \n', 'Status:\n')] as const));
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://127.0.0.1/');
    const j = (s: number, x: unknown) => new Response(JSON.stringify(x), { status: s, headers: { 'Content-Type': 'application/json' } });
    const t = init?.body ? JSON.parse(String(init.body)) : null;
    if (u.pathname === '/api/vault/fajl' && (init?.method ?? 'GET') === 'GET') {
      const tartalom = lemez.get(u.searchParams.get('ut')!)!;
      return j(200, { ut: u.searchParams.get('ut'), tartalom, hash: hash(tartalom), jel: '', mtime: 0 });
    }
    if (u.pathname === '/api/vault/fajl') {
      putok.push(t);
      lemez.set(t.ut, t.tartalom);
      return j(200, { ok: true, ut: t.ut, hash: hash(t.tartalom), jel: '', uzenet: 'mentve', pillanat: t.pillanat ? 'abc1234' : null, elotte: null, git: true });
    }
    if (u.pathname === '/api/vault/tulajdonsagok/elemez') {
      const m = /Status:[ ]?(.*)\n/.exec(t.fm ?? '');
      return j(200, { van: true, tulajdonsagok: [{ kulcs: 'Status', tipus: 'text', ertek: m?.[1] || null, ervenyes: true }], hiba: null, kulcsok: ['Status'], problemak: [], osztaly: 'x' });
    }
    if (u.pathname === '/api/vault/tulajdonsagok/modosit') {
      modositasok.push({ ertek: t.ertek, megerosit: t.megerosit, kulcs: t.kulcs });
      if (mod === 'sertes' && !t.megerosit)
        return j(200, { ok: false, fm_uj: null, megerositheto: true, valtozas: true, problemak: [{ kod: 'status_ertek', szint: 'sertes', kulcs: 'Status', ertek: t.ertek, uzenet: 'A Status értéke nem illik a sémába.' }] });
      return j(200, { ok: true, fm_uj: `---\nStatus:${t.ertek === '' ? '' : ' ' + t.ertek}\n---\n`, megerositheto: false, valtozas: true, problemak: [] });
    }
    if (u.pathname === '/api/vault/sema')
      return j(200, { mezosorrend: [], extra_kulcsok: [], tags_ertekkeszlet: [], status_ertekkeszlet: ['Completed', 'In progress', 'Review'], status_gazdai: true, osztaly: null });
    return j(200, { ok: true });
  });
});

const A = 'A';
const B = 'B';
const C = 'C';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  ertesitesek.lista.splice(0);
  document.querySelectorAll('.nt-lebego').forEach((e) => e.remove());
});

const oszlopok = (c: HTMLElement) => [...c.querySelectorAll('.oszlop')].map((o) => [o.querySelector('.cim')?.textContent, [...o.querySelectorAll('.kartya .cim')].map((k) => k.textContent?.trim().split(/\s+/)[0])]);

describe('Kanban', () => {
  it('az oszlopok a csoportok; a Status a séma sorrendjében, üres oszloppal is', async () => {
    const { container } = render(Kanban, { props: { valasz: valasz(), cellaIras: true } });
    await waitFor(() => expect(container.querySelectorAll('.oszlop')).toHaveLength(4));
    expect(oszlopok(container)).toEqual([
      ['Nincs érték', ['A']],
      ['Completed', []],
      ['In progress', []],
      ['Review', ['B', 'C']],
    ]);
  });

  it('más tulajdonságnál az oszlopok a core csoportjai, séma nélkül', () => {
    const v = valasz({}, 'Genre');
    v.csoportok = [csoport('Próza', 0, 2), csoport('Vers', 2, 1)];
    const { container } = render(Kanban, { props: { valasz: v, cellaIras: true } });
    expect(oszlopok(container).map((o) => o[0])).toEqual(['Próza', 'Vers']);
  });

  it('csoportosítás nélkül útmutatás áll', () => {
    const v = valasz({ csoportok: null });
    v.nezet!.beallitas = {};
    const { container } = render(Kanban, { props: { valasz: v, cellaIras: true } });
    expect(container.textContent).toContain('csoportosítás kell');
    expect(container.querySelector('.oszlop')).toBeNull();
  });

  it('húzással a kártya az új oszlop értékét kapja: egy írás, pillanatkép, „Visszavonás” értesítés, azonnal az új oszlopban', async () => {
    const { container } = render(Kanban, { props: { valasz: valasz(), cellaIras: true } });
    await waitFor(() => expect(container.querySelectorAll('.oszlop')).toHaveLength(4));
    const kartya = container.querySelector<HTMLElement>('[data-ut="P/A.md"]')!.closest<HTMLElement>('.elem')!;
    const cel = container.querySelectorAll<HTMLElement>('.oszlop')[1]; // Completed
    await fireEvent.dragStart(kartya);
    await fireEvent.dragOver(cel);
    expect(cel.classList.contains('cel')).toBe(true);
    await fireEvent.drop(cel);
    await waitFor(() => expect(putok).toHaveLength(1));
    expect(putok[0]).toMatchObject({ ut: 'P/A.md', pillanat: true });
    expect(putok[0].tartalom).toContain('Status: Completed');
    await waitFor(() => expect(oszlopok(container)[1]).toEqual(['Completed', ['A']]));
    expect(oszlopok(container)[0]).toEqual(['Nincs érték', []]);
    expect(ertesitesek.lista.at(-1)?.muvelet?.nev).toBe('Visszavonás');
  });

  it('a „Nincs érték” oszlopba ejtés üres értéket ír, nem törli a kulcsot', async () => {
    const { container } = render(Kanban, { props: { valasz: valasz(), cellaIras: true } });
    await waitFor(() => expect(container.querySelectorAll('.oszlop')).toHaveLength(4));
    const kartya = container.querySelector<HTMLElement>('[data-ut="P/B.md"]')!.closest<HTMLElement>('.elem')!;
    await fireEvent.dragStart(kartya);
    await fireEvent.drop(container.querySelectorAll<HTMLElement>('.oszlop')[0]);
    await waitFor(() => expect(putok).toHaveLength(1));
    expect(putok[0].tartalom).toBe('---\nStatus:\n---\n');
    expect(modositasok[0].ertek).toBe('');
  });

  it('ugyanabba az oszlopba ejtés nem ír', async () => {
    const { container } = render(Kanban, { props: { valasz: valasz(), cellaIras: true } });
    await waitFor(() => expect(container.querySelectorAll('.oszlop')).toHaveLength(4));
    const kartya = container.querySelector<HTMLElement>('[data-ut="P/B.md"]')!.closest<HTMLElement>('.elem')!;
    await fireEvent.dragStart(kartya);
    await fireEvent.drop(container.querySelectorAll<HTMLElement>('.oszlop')[3]);
    await new Promise((r) => setTimeout(r, 30));
    expect(putok).toHaveLength(0);
    expect(modositasok).toHaveLength(0);
  });

  it('a groupBy eltérő kis-nagybetűje: a frontmatterben álló kulcsot írja, nem újat (T165)', async () => {
    const v = valasz({}, 'status');
    const { container } = render(Kanban, { props: { valasz: v, cellaIras: true } });
    await waitFor(() => expect(container.querySelectorAll('.oszlop')).toHaveLength(2));
    const kartya = container.querySelector<HTMLElement>('[data-ut="P/A.md"]')!.closest<HTMLElement>('.elem')!;
    await fireEvent.dragStart(kartya);
    await fireEvent.drop(container.querySelectorAll<HTMLElement>('.oszlop')[1]);
    await waitFor(() => expect(putok).toHaveLength(1));
    expect(modositasok[0].kulcs).toBe('Status');
    expect(putok[0].tartalom).toBe('---\nStatus: Review\n---\n');
  });

  it('billentyűzettel: a ⋯ menü „Áthelyezés ide” elemei', async () => {
    const { container } = render(Kanban, { props: { valasz: valasz(), cellaIras: true } });
    await waitFor(() => expect(container.querySelectorAll('.oszlop')).toHaveLength(4));
    await fireEvent.click(container.querySelector('[aria-label="A áthelyezése"]')!);
    const elemek = [...document.querySelectorAll('.nt-lebego .nt-menu-nev')].map((e) => e.textContent);
    expect(elemek).toEqual(['Áthelyezés ide: Nincs érték', 'Áthelyezés ide: Completed', 'Áthelyezés ide: In progress', 'Áthelyezés ide: Review']);
    const cel = [...document.querySelectorAll<HTMLElement>('.nt-lebego .nt-menu-elem')].find((e) => e.textContent?.includes('In progress'))!;
    await fireEvent.click(cel);
    await waitFor(() => expect(putok).toHaveLength(1));
    expect(putok[0].tartalom).toContain('Status: In progress');
  });

  it('séma-sértésnél „Mégis beírom”: addig nem ír', async () => {
    mod = 'sertes';
    const { container } = render(Kanban, { props: { valasz: valasz(), cellaIras: true } });
    await waitFor(() => expect(container.querySelectorAll('.oszlop')).toHaveLength(4));
    const kartya = container.querySelector<HTMLElement>('[data-ut="P/A.md"]')!.closest<HTMLElement>('.elem')!;
    await fireEvent.dragStart(kartya);
    await fireEvent.drop(container.querySelectorAll<HTMLElement>('.oszlop')[1]);
    const figy = await waitFor(() => {
      const f = container.querySelector<HTMLElement>('.uzenet.figyelmeztetes');
      expect(f).not.toBeNull();
      return f!;
    });
    expect(figy.textContent).toContain('nem illik a sémába');
    expect(putok).toHaveLength(0);
    await fireEvent.click([...figy.querySelectorAll('button')].find((b) => b.textContent === 'Mégis beírom')!);
    await waitFor(() => expect(putok).toHaveLength(1));
    expect(modositasok.map((m) => m.megerosit)).toEqual([false, true]);
  });

  it('nem húzható: csak olvasható nézet, nem jegyzet sor, nem note-tulajdonság oszlopa', async () => {
    const a = render(Kanban, { props: { valasz: valasz(), cellaIras: false } });
    await waitFor(() => expect(a.container.querySelectorAll('.oszlop')).toHaveLength(4));
    expect(a.container.querySelector('.elem[draggable=true]')).toBeNull();
    expect(a.container.querySelector('.menu-gomb')).toBeNull();
    a.unmount();
    const v = valasz();
    v.sorok[0] = sor('A', null, false);
    const b = render(Kanban, { props: { valasz: v, cellaIras: true } });
    await waitFor(() => expect(b.container.querySelectorAll('.oszlop')).toHaveLength(4));
    expect(b.container.querySelector<HTMLElement>('[data-ut="P/A.md"]')!.closest('.elem')!.getAttribute('draggable')).toBe('false');
    b.unmount();
    const f = valasz({}, 'file.folder');
    f.csoportok = [csoport('P', 0, 3, false)];
    const c = render(Kanban, { props: { valasz: f, cellaIras: true } });
    expect(c.container.querySelector('.elem[draggable=true]')).toBeNull();
    expect(c.container.textContent).toContain('nem frontmatter-tulajdonságból');
    const kartya = c.container.querySelector<HTMLElement>('.elem')!;
    await fireEvent.dragStart(kartya);
    await fireEvent.drop(c.container.querySelector('.oszlop')!);
    expect(putok).toHaveLength(0);
  });
});
