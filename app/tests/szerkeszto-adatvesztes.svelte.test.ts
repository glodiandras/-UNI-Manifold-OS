// A szerkesztő nézetének adatvesztési leletei (C29.7a, 2. audit), a valódi `Szerkeszto.svelte`-on át, jsdom-ban,
// ál-core-ral: korai fülbezárás (T119) és a CRLF-es jegyzet beillesztése / táblázat-szerkesztése (T118).

import { cleanup, render } from '@testing-library/svelte';
import { EditorView } from '@codemirror/view';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import Szerkeszto from '../src/szerkeszto/Szerkeszto.svelte';
import { szerkesztok } from '../src/szerkeszto/szerkesztok.svelte';

interface Iras {
  ut: string;
  tartalom: string;
  alap: string;
  elso: boolean;
  pillanat: boolean;
}

const UT = 'Matek/Mertani.md';
let lemez: Map<string, string>;
let irasok: Iras[];
/** ha be van állítva, a GET ennek a feloldásáig vár */
let olvasasKapu: Promise<void> | null = null;

const hash = (s: string) => `h${s.length}:${[...s].reduce((h, c) => (h * 31 + c.charCodeAt(0)) | 0, 7)}`;
const valasz = (kod: number, adat: unknown) =>
  new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });

beforeEach(() => {
  lemez = new Map([[UT, '# Mértani\n\nszöveg\n']]);
  irasok = [];
  olvasasKapu = null;
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://127.0.0.1/');
    if (u.pathname === '/api/vault/fajl' && (!init?.method || init.method === 'GET')) {
      const ut = u.searchParams.get('ut')!;
      if (olvasasKapu) await olvasasKapu;
      const t = lemez.get(ut);
      if (t === undefined) return valasz(404, { hiba: 'nincs ilyen fájl' });
      return valasz(200, { ut, tartalom: t, hash: hash(t), jel: '', mtime: 0, kodolas_hiba: false });
    }
    if (u.pathname === '/api/vault/fajl' && init?.method === 'PUT') {
      const k = JSON.parse(String(init.body)) as Iras;
      const t = lemez.get(k.ut)!;
      if (hash(t) !== k.alap) return valasz(409, { hiba: 'ütközés', utkozes: true, hash: hash(t) });
      irasok.push(k);
      lemez.set(k.ut, k.tartalom);
      return valasz(200, { ok: true, ut: k.ut, hash: hash(k.tartalom), jel: '', uzenet: 'mentve', pillanat: k.pillanat ? 'abc' : null, elotte: null, git: true });
    }
    return valasz(404, { hiba: 'nincs' });
  });
});

afterEach(() => {
  cleanup();
  szerkesztok.dokumentumok.eldob(UT);
  vi.unstubAllGlobals();
});

function megjelenit() {
  const felulet = new Felulet({});
  const ful = $state({ id: 'f1', ut: UT as string | null, nezet: undefined as Record<string, unknown> | undefined });
  const context = new Map<unknown, unknown>([
    [KORNYEZET_KULCS, { felulet, fajlok: new VaultFajlok(), kapcsolat: new CoreKapcsolat('ws://127.0.0.1:1/ws') }],
  ]);
  const r = render(Szerkeszto, { props: { ful, info: undefined, aktiv: true }, context });
  return { ...r, ful, felulet };
}

describe('korai fülbezárás (T119)', () => {
  it('a betöltés előtt bezárt fül dokumentuma nem ragad a nyitott térképben', async () => {
    let enged!: () => void;
    olvasasKapu = new Promise<void>((r) => (enged = r));
    const r = megjelenit();
    r.unmount();
    enged();
    await vi.waitFor(() => expect(szerkesztok.dokumentumok.kap(UT)).toBeUndefined(), { timeout: 3000 });
  });
});

describe('CRLF-es jegyzet (T118)', () => {
  const CRLF = '# Mértani\r\n\r\n| a | b |\r\n|---|---|\r\n| 1 | 2 |\r\n';

  async function nyit(): Promise<{ v: EditorView; r: ReturnType<typeof megjelenit> }> {
    lemez.set(UT, CRLF);
    const r = megjelenit();
    const v = await vi.waitFor(() => {
      const e = r.container.querySelector('.cm-editor');
      const x = e ? EditorView.findFromDOM(e as HTMLElement) : null;
      expect(x).toBeTruthy();
      return x!;
    });
    return { v, r };
  }

  const csupaCrlf = (s: string) => expect(s.replace(/\r\n/g, '')).not.toMatch(/[\r\n]/); // nincs magányos CR vagy LF

  it('a programosan beszúrt, `\\n`-nel tagolt szöveg sorokra bomlik: a mentett fájl csupa `\\r\\n`', async () => {
    const { v } = await nyit();
    const sorok = v.state.doc.lines;
    v.dispatch({ changes: { from: v.state.doc.length, insert: 'első\nmásodik' } });
    expect(v.state.doc.lines).toBe(sorok + 1); // a `\n` sortörés, nem a sor része
    v.dispatch(v.state.replaceSelection('x\ny')); // a beillesztés útja
    await vi.waitFor(() => expect(irasok.length).toBeGreaterThan(0), { timeout: 4000 });
    const mentett = irasok.at(-1)!.tartalom;
    expect(mentett).toContain('első\r\nmásodik');
    csupaCrlf(mentett);
  });

  it('a táblázat-szerkesztő cellaírása CRLF-es jegyzetben sem vész el: a mentett fájl csupa `\\r\\n`, a többi sor bájtra azonos', async () => {
    const { v, r } = await nyit();
    const tabla = r.container.querySelector<HTMLElement>('.nt-tabla')!;
    expect(tabla).not.toBeNull();
    tabla.querySelector<HTMLElement>('[data-sor="1"][data-oszlop="0"]')!.click();
    const i = tabla.querySelector<HTMLInputElement>('input.nt-cella-mezo')!;
    i.value = 'x';
    i.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
    await vi.waitFor(() => expect(irasok.length).toBeGreaterThan(0), { timeout: 4000 });
    const mentett = irasok.at(-1)!.tartalom;
    expect(mentett.startsWith('# Mértani\r\n\r\n| a   | b   |\r\n| --- | --- |\r\n| x   | 2   |')).toBe(true);
    csupaCrlf(mentett);
    expect(v.state.doc.toString()).not.toMatch(/\r/);
  });
});
