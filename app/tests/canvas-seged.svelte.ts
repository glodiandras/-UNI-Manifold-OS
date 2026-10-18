// A 09-canvas paritás-tesztek közös vázlata: a canvas-fül jsdom-ban, ál-core-ral (fájlok, CAS-os mentés, új jegyzet,
// import, beágyazás), nem nulla vászonmérettel (különben a kártyák tartalma nem rajzolódna). Valódi vault és hálózat nincs.

import { cleanup, fireEvent, render, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, vi } from 'vitest';
import CanvasFul from '../src/canvas/CanvasFul.svelte';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import type { Ful } from '../src/lib/elrendezes/munkaterulet.svelte';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { VaultFajlok, type FajlInfo } from '../src/lib/vault/fajlok.svelte';
import { sorVege } from '../src/szerkeszto/dokumentum/mentesSor';
import { szerkesztok } from '../src/szerkeszto/szerkesztok.svelte';

export const UT = 'Maps/Probe.canvas';

export interface Iras {
  ut: string;
  tartalom: string;
  alap: string;
  elso: boolean;
  pillanat: boolean;
}

export interface UjKeres {
  mappa?: string;
  nev?: string;
  tartalom?: string;
  tipus?: string;
  link?: { cel: string; forras: string };
}

/** Az ál-core állapota; a tesztek ezt olvassák és állítják. */
export const hazi = {
  lemez: new Map<string, string>(),
  irasok: [] as Iras[],
  ujak: [] as UjKeres[],
  importok: [] as { nev: string; meret: number }[],
  utkozes: false,
  elutasit: false,
  putSzam: 0,
  /** a következő `POST /api/vault/uj` ennyi státusszal bukik (0 = rendben) */
  ujHiba: 0,
  fejezetek: {} as Record<string, { szint: number; szoveg: string; sor: number }[]>,
  /** a beágyazás-végpont válaszai út szerint (jegyzet-szelet); hiányzónál a lemezen álló szöveg az egész jegyzet */
  szeletek: {} as Record<string, { szoveg: string; kezd: number }>,
  navigaciok: [] as string[],
};

export const hash = (s: string) => `h${s.length}:${[...s].reduce((h, c) => (h * 31 + c.charCodeAt(0)) | 0, 7)}`;
export const valasz = (kod: number, adat: unknown) =>
  new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });

export function allapotAlap(): void {
  hazi.lemez = new Map();
  hazi.irasok = [];
  hazi.ujak = [];
  hazi.importok = [];
  hazi.utkozes = false;
  hazi.elutasit = false;
  hazi.putSzam = 0;
  hazi.ujHiba = 0;
  hazi.fejezetek = {};
  hazi.szeletek = {};
  hazi.navigaciok = [];
}

function canvasHiba(szoveg: string): string | null {
  try {
    const j = JSON.parse(szoveg);
    if (typeof j !== 'object' || j === null || Array.isArray(j)) return 'not an object';
    for (const k of ['nodes', 'edges'] as const) if (k in j && !Array.isArray(j[k])) return `${k} is not an array`;
    return null;
  } catch (e) {
    return String(e);
  }
}

export function telepit(): void {
  allapotAlap();
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
  // a vászon mérete (a `bind:clientWidth` induló értéke): különben a részletes kártya-tartalom nem rajzolódik
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
    configurable: true,
    get() {
      return (this as HTMLElement).classList?.contains('vaszon') ? 1200 : 0;
    },
  });
  Object.defineProperty(HTMLElement.prototype, 'clientHeight', {
    configurable: true,
    get() {
      return (this as HTMLElement).classList?.contains('vaszon') ? 800 : 0;
    },
  });
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://127.0.0.1/');
    const metodus = init?.method ?? 'GET';
    if (u.pathname === '/api/vault/fajl' && metodus === 'GET') {
      const ut = u.searchParams.get('ut')!;
      const t = hazi.lemez.get(ut);
      if (t === undefined) return valasz(404, { hiba: 'no such file' });
      return valasz(200, { ut, tartalom: t, hash: hash(t), jel: '', mtime: 0, kodolas_hiba: false });
    }
    if (u.pathname === '/api/vault/fajl' && metodus === 'PUT') {
      const k = JSON.parse(String(init!.body)) as Iras;
      const regi = hazi.lemez.get(k.ut);
      hazi.putSzam++;
      if (regi === undefined) return valasz(404, { hiba: 'no such file' });
      if (hazi.elutasit) return valasz(400, { hiba: 'the canvas is not a valid JSON Canvas, not saved' });
      if (k.ut.endsWith('.canvas')) {
        const h = canvasHiba(k.tartalom);
        if (h) return valasz(400, { hiba: `the canvas is not a valid JSON Canvas, not saved: ${h}` });
      }
      if (hazi.utkozes || k.alap !== hash(regi)) return valasz(409, { hiba: 'conflict', utkozes: true, hash: hash(regi) });
      hazi.irasok.push(k);
      hazi.lemez.set(k.ut, k.tartalom);
      return valasz(200, { ok: true, ut: k.ut, hash: hash(k.tartalom), jel: '', uzenet: 'saved', pillanat: null, elotte: null, git: true });
    }
    if (u.pathname === '/api/vault/uj' && metodus === 'POST') {
      const k = JSON.parse(String(init!.body)) as UjKeres;
      hazi.ujak.push(k);
      if (hazi.ujHiba) return valasz(hazi.ujHiba, { hiba: 'the core refused' });
      const nev = (k.link ? k.link.cel : k.nev ?? '').replace(/\.md$/i, '');
      const mappa = k.link ? '' : k.mappa ?? '';
      const ut = `${mappa ? mappa + '/' : ''}${nev}.md`;
      if ([...hazi.lemez.keys()].some((x) => x.toLowerCase() === ut.toLowerCase()))
        return valasz(400, { hiba: `a file with this name already exists: ${ut}`, kod: 'vault.van_ilyen_fajl', param: { ut } });
      hazi.lemez.set(ut, k.tartalom ?? `# ${nev}\n`);
      return valasz(201, { ok: true, ut, hash: hash(hazi.lemez.get(ut)!), pillanat: null, git: true, figyelmeztetes: null });
    }
    if (u.pathname === '/api/vault/import' && metodus === 'POST') {
      const k = JSON.parse(String(init!.body)) as { nev: string; adat: string; vege: boolean };
      hazi.importok.push({ nev: k.nev, meret: k.adat.length });
      const ut = `Attachments/${k.nev}`;
      hazi.lemez.set(ut, 'binary');
      return valasz(200, { ok: true, kesz: true, ut, azon: 'x', meglevo: false, figyelmeztetes: null });
    }
    if (u.pathname === '/api/vault/jegyzet') {
      const ut = u.searchParams.get('ut')!;
      return valasz(200, { ut, fejezetek: hazi.fejezetek[ut] ?? [] });
    }
    if (u.pathname === '/api/vault/beagyazas') {
      const cel = u.searchParams.get('cel')!;
      const ut = /\.[a-z0-9]+$/i.test(cel) ? cel : `${cel}.md`;
      const alcel = u.searchParams.get('alcel');
      const lemez = hazi.lemez.get(ut);
      if (lemez === undefined) return valasz(200, { tipus: 'nincs', cel });
      if (ut.endsWith('.pdf')) return valasz(200, { tipus: 'pdf', ut });
      if (ut.endsWith('.base')) return valasz(200, { tipus: 'base', ut });
      if (!ut.endsWith('.md')) return valasz(200, { tipus: 'egyeb', ut });
      const sz = alcel ? hazi.szeletek[`${ut}#${alcel}`] : null;
      return valasz(200, { tipus: 'jegyzet', ut, szoveg: sz?.szoveg ?? lemez, kezd: sz?.kezd ?? 1 });
    }
    return valasz(200, { eredmenyek: [] });
  });
}

export function lebont(): void {
  cleanup();
  vi.unstubAllGlobals();
  delete (HTMLElement.prototype as unknown as Record<string, unknown>).clientWidth;
  delete (HTMLElement.prototype as unknown as Record<string, unknown>).clientHeight;
  for (const d of szerkesztok.dokumentumok.lista()) szerkesztok.dokumentumok.eldob(d.ut);
}

export async function lebontAsync(): Promise<void> {
  cleanup();
  await sorVege();
  lebont();
}

export function beallit(): void {
  beforeEach(() => {
    telepit();
    ertesitesek.lista = [];
  });
  afterEach(lebontAsync);
}

export type Nyitott = ReturnType<typeof nyit>;

export interface NyitOpciok {
  fajlok?: FajlInfo[];
  nezet?: { tx: number; ty: number; z: number };
}

export function nyit(szoveg: string, o: NyitOpciok = {}, ut = UT) {
  hazi.lemez.set(ut, szoveg);
  const ful = $state<Ful>({ id: 'f1', ut, nezet: { canvas: o.nezet ?? { tx: 0, ty: 0, z: 1 }, racs: false } });
  const fajlok = new VaultFajlok();
  if (o.fajlok) fajlok.beallit(o.fajlok);
  const felulet = new Felulet({});
  const megnyitottak: string[] = [];
  const eredeti = felulet.munkaterulet.megnyit.bind(felulet.munkaterulet);
  felulet.munkaterulet.megnyit = ((u: string, ...r: unknown[]) => {
    megnyitottak.push(u);
    return (eredeti as (...a: unknown[]) => unknown)(u, ...r);
  }) as typeof felulet.munkaterulet.megnyit;
  const kornyezet = { felulet, fajlok, kapcsolat: new CoreKapcsolat('ws://127.0.0.1:1/ws') };
  const c = render(CanvasFul, {
    props: { ful, info: undefined, aktiv: true },
    context: new Map([[KORNYEZET_KULCS, kornyezet]]),
  });
  return Object.assign(c, { ful, fajlok, felulet, megnyitottak, ut });
}

export async function vaszon(c: Nyitott): Promise<HTMLElement> {
  return await waitFor(() => {
    const v = c.container.querySelector<HTMLElement>('.vaszon');
    if (!v) throw new Error('no canvas');
    return v;
  });
}

export const kartya = (c: Nyitott, id: string): HTMLElement =>
  c.container.querySelector<HTMLElement>(`.kartya[data-id="${CSS.escape(id)}"]`)!;

export function node(id: string, kiegeszites: Record<string, unknown> = {}, x = 0, y = 0): string {
  return JSON.stringify({ id, type: 'text', text: id, x, y, width: 260, height: 60, ...kiegeszites });
}

/** Egy Obsidian-alakú (tabulátoros, soronkénti tömör elemű) canvas-fájl. */
export function fajl(nodes: string[], edges: string[] = []): string {
  return `{\n\t"nodes":[\n${nodes.map((n) => `\t\t${n}`).join(',\n')}\n\t],\n\t"edges":[\n${edges.map((e) => `\t\t${e}`).join(',\n')}\n\t]\n}`;
}

export async function iras(db: number, timeout = 3500): Promise<void> {
  await waitFor(() => {
    if (hazi.irasok.length < db) throw new Error(`writes: ${hazi.irasok.length}/${db}`);
  }, { timeout });
}

export const utolso = (): string => hazi.irasok.at(-1)!.tartalom;

export { fireEvent, waitFor };
