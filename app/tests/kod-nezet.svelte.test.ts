// A `.cpp` fül (C36a-UI) jsdom-ban, ál-core-ral: betöltés, gépelés → mentés az egyetlen írási úton (`PUT /api/vault/fajl`),
// a ⌘R előtt a mentés kivárása (a PUT megelőzi az ellenőrzést), az eredménypanel a WS-eseményekből (fordítási hiba →
// lista, aláhúzás, ugrás; hibás kimenet → diff), Esc → megszakítás, ütközés, többértelmű jegyzet → választó.

import { forEachDiagnostic } from '@codemirror/lint';
import { EditorView } from '@codemirror/view';
import { cleanup, fireEvent, render, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { kodFulok } from '../src/kod/aktiv.svelte';
import { kodFutasok } from '../src/kod/futas.svelte';
import KodFul from '../src/kod/KodFul.svelte';
import { ellenoriz } from '../src/kod/muveletek';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import type { Ful } from '../src/lib/elrendezes/munkaterulet.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import { sorVege } from '../src/szerkeszto/dokumentum/mentesSor';
import { szerkesztok } from '../src/szerkeszto/szerkesztok.svelte';

const UT = 'Info/Összeg.cpp';
const JEGYZET = 'Info/Összeg.md';
const FORRAS = '#include <bits/stdc++.h>\nusing namespace std;\n\nint main() {\n    int a, b;\n    cin >> a >> b;\n    cout << a - b;\n}\n';

let lemez: Map<string, string>;
let keresek: { modszer: string; ut: string; torzs: Record<string, unknown> | undefined }[];
let ellenorizValasz: () => Response;

const hash = (s: string) => `h${s.length}:${[...s].reduce((h, c) => (h * 31 + c.charCodeAt(0)) | 0, 7)}`;
const valasz = (kod: number, adat: unknown) => new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });
const FUTAS = 'futas-0123456789ab';

beforeEach(() => {
  lemez = new Map([[UT, FORRAS]]);
  keresek = [];
  ellenorizValasz = () => valasz(202, { futas: FUTAS, cpp: UT, jegyzet: JEGYZET, mod: 'gyors', tesztek_db: 2 });
  kodFutasok.aktiv = null;
  kodFutasok.tobbertelmu = null;
  kodFutasok.jegyzetValasztas.clear();
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://127.0.0.1/');
    const torzs = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : undefined;
    keresek.push({ modszer: init?.method ?? 'GET', ut: u.pathname, torzs });
    if (u.pathname === '/api/vault/fajl' && (!init?.method || init.method === 'GET')) {
      const ut = u.searchParams.get('ut')!;
      const t = lemez.get(ut);
      if (t === undefined) return valasz(404, { hiba: 'nincs ilyen fájl' });
      return valasz(200, { ut, tartalom: t, hash: hash(t), jel: '', mtime: 0, kodolas_hiba: false });
    }
    if (u.pathname === '/api/vault/fajl' && init?.method === 'PUT') {
      const k = torzs as { ut: string; tartalom: string; alap: string };
      const regi = lemez.get(k.ut)!;
      if (k.alap !== hash(regi)) return valasz(409, { hiba: 'ütközés', utkozes: true, hash: hash(regi) });
      lemez.set(k.ut, k.tartalom);
      return valasz(200, { ok: true, ut: k.ut, hash: hash(k.tartalom), jel: '', uzenet: 'mentve', pillanat: null, elotte: null, git: true });
    }
    if (u.pathname === '/api/cpp/ellenoriz') return ellenorizValasz();
    if (u.pathname === '/api/cpp/feladat')
      return valasz(200, {
        jegyzet: JEGYZET,
        cpp: UT,
        tesztek: [
          { sorszam: 1, sor: 10, cim: 'Példa', bemenet: '3 4\n', kimenet: '7\n', idokorlat_s: null, hiba: null },
          { sorszam: 2, sor: 20, cim: 'Nulla', bemenet: '0 0\n', kimenet: '0\n', idokorlat_s: null, hiba: null },
        ],
      });
    if (u.pathname === '/api/cpp/megszakit') return valasz(200, { megszakitva: true, allapot: 'fut' });
    return valasz(404, { hiba: `nincs: ${u.pathname}` });
  });
});

afterEach(async () => {
  cleanup();
  await sorVege();
  vi.unstubAllGlobals();
  for (const d of szerkesztok.dokumentumok.lista()) szerkesztok.dokumentumok.eldob(d.ut);
});

function nyit() {
  const ful = $state<Ful>({ id: 'f1', ut: UT });
  const felulet = new Felulet({});
  const kornyezet = { felulet, fajlok: new VaultFajlok(), kapcsolat: new CoreKapcsolat('ws://127.0.0.1:1/ws') };
  const c = render(KodFul, { props: { ful, info: undefined, aktiv: true }, context: new Map([[KORNYEZET_KULCS, kornyezet]]) });
  return { c, felulet };
}

async function nezet(c: { container: HTMLElement }): Promise<EditorView> {
  return await waitFor(() => {
    const el = c.container.querySelector<HTMLElement>('.cm-editor');
    expect(el).not.toBeNull();
    return EditorView.findFromDOM(el!)!;
  });
}

const ev = (szakasz: string, adat: Record<string, unknown> = {}) => ({ tipus: 'cpp_futas', futas: FUTAS, ut: UT, jegyzet: JEGYZET, mod: 'gyors', szakasz, ...adat });

describe('a .cpp fül', () => {
  it('betöltés: a forrás a szerkesztőben, a fül az aktív kód-fül, a ⌘S a dokumentumát menti', async () => {
    const { c } = nyit();
    const v = await nezet(c);
    expect(v.state.doc.toString()).toBe(FORRAS);
    expect(kodFulok.aktiv?.ut).toBe(UT);
    expect(szerkesztok.masNezet).not.toBeNull();
    expect(c.container.querySelector('.cm-kodszerkeszto')).not.toBeNull();
    expect(c.container.querySelector('.cm-lineNumbers')).not.toBeNull();
  });

  it('gépelés → mentés az egyetlen írási úton; a ⌘R előbb kivárja a mentést', async () => {
    const { c, felulet } = nyit();
    const v = await nezet(c);
    v.dispatch({ changes: { from: 0, insert: '// megoldás\n' } });
    expect(await ellenoriz(felulet, 'gyors')).toBe(true);
    const put = keresek.findIndex((k) => k.modszer === 'PUT' && k.ut === '/api/vault/fajl');
    const post = keresek.findIndex((k) => k.ut === '/api/cpp/ellenoriz');
    expect(put).toBeGreaterThanOrEqual(0);
    expect(post).toBeGreaterThan(put);
    expect(lemez.get(UT)!.startsWith('// megoldás\n')).toBe(true);
    expect(keresek[post].torzs).toEqual({ ut: UT, mod: 'gyors' });
  });

  it('fordítási hiba: lista, aláhúzás a szerkesztőben, kattintásra ugrás a sorra', async () => {
    const { c, felulet } = nyit();
    const v = await nezet(c);
    await ellenoriz(felulet, 'gyors');
    kodFutasok.esemeny(ev('indul', { tesztek_db: 2 }));
    kodFutasok.esemeny(
      ev('fordit_kesz', {
        fordit: {
          ok: false,
          allapot: 'hiba',
          ms: 300,
          hiba_db: 1,
          figyelmeztetes_db: 0,
          uzenet: '',
          diagnosztika: [
            { szint: 'error', fajl: 'Összeg.cpp', sor: 6, oszlop: 12, uzenet: "use of undeclared identifier 'bb'", sajat: true, kodreszlet: [] },
          ],
        },
      }),
    );
    kodFutasok.esemeny(ev('kesz', { atment: false, tesztek_db: 2, atment_db: 0, fordit_ok: false, ms: 320 }));
    const gomb = await waitFor(() => {
      const g = [...c.container.querySelectorAll<HTMLButtonElement>('.diag-gomb')].find((b) => b.textContent!.includes('undeclared'));
      expect(g).toBeTruthy();
      return g!;
    });
    expect(c.container.textContent).toContain('Fordítás sikertelen');
    let db = 0;
    forEachDiagnostic(v.state, () => db++);
    expect(db).toBe(1);
    await fireEvent.click(gomb);
    const kurzor = v.state.selection.main.head;
    expect(v.state.doc.lineAt(kurzor).number).toBe(6);
    expect(kurzor - v.state.doc.line(6).from).toBe(11);
  });

  it('hibás kimenet: n/m összegzés, a kinyitott teszt a bemenettel és a diff-fel', async () => {
    const { c, felulet } = nyit();
    await nezet(c);
    await ellenoriz(felulet, 'gyors');
    kodFutasok.esemeny(ev('fordit_kesz', { fordit: { ok: true, allapot: 'ok', ms: 400, diagnosztika: [], hiba_db: 0, figyelmeztetes_db: 0 } }));
    kodFutasok.esemeny(ev('teszt', { teszt: { sorszam: 1, cim: 'Példa', allapot: 'atment', ido_ms: 2, csucs_mb: 1, diff: null }, ossz: 2 }));
    kodFutasok.esemeny(
      ev('teszt', {
        teszt: {
          sorszam: 2,
          cim: 'Nulla',
          allapot: 'hibas_kimenet',
          ido_ms: 2,
          csucs_mb: 1,
          uzenet: 'a kimenet eltér a vártól',
          diff: {
            egyezik: false,
            vart_sor_db: 1,
            kapott_sor_db: 1,
            elteres_db: 1,
            elso_elteres: 1,
            levagva: false,
            mod: 'alap',
            elteres: { sor: 1, oszlop: 1, vart: '0', kapott: '-1', ok: 'a sor eltér' },
            sorok: [{ tipus: 'csere', vart_sor: 1, kapott_sor: 1, vart: '0', kapott: '-1' }],
          },
        },
        ossz: 2,
      }),
    );
    kodFutasok.esemeny(ev('kesz', { atment: false, tesztek_db: 2, atment_db: 1, fordit_ok: true, ms: 500 }));
    await waitFor(() => expect(c.container.textContent).toContain('1/2 teszt átment'));
    await waitFor(() => expect(c.container.querySelector('.diff-sor.beszurt code')?.textContent).toBe('-1'));
    expect(c.container.querySelector('.diff-sor.torolt code')!.textContent).toBe('0');
    expect(c.container.textContent).toContain('hibás kimenet');
    expect(c.container.textContent).toContain('Bemenet');
    expect(c.container.querySelector('pre.kimenet')!.textContent).toBe('0 0\n');
  });

  it('Esc futás közben megszakít', async () => {
    const { c, felulet } = nyit();
    await nezet(c);
    await ellenoriz(felulet, 'gyors');
    kodFutasok.esemeny(ev('indul', { tesztek_db: 2 }));
    await fireEvent.keyDown(c.container.querySelector('.kod-ful')!, { key: 'Escape' });
    await waitFor(() => expect(keresek.some((k) => k.ut === '/api/cpp/megszakit')).toBe(true));
    expect(c.container.textContent).toContain('Megszakítás…');
  });

  it('több feladat-jegyzet: választó, a választás a futás jegyzete', async () => {
    const { c, felulet } = nyit();
    await nezet(c);
    ellenorizValasz = () => valasz(409, { hiba: 'több feladat-jegyzet', kod: 'tobbertelmu', jegyzetek: ['Info/A.md', 'Info/B.md'] });
    expect(await ellenoriz(felulet, 'gyors')).toBe(false);
    const b = await waitFor(() => {
      const g = [...c.container.querySelectorAll<HTMLButtonElement>('.valasztas button')].find((x) => x.textContent === 'B');
      expect(g).toBeTruthy();
      return g!;
    });
    ellenorizValasz = () => valasz(202, { futas: FUTAS, cpp: UT, jegyzet: 'Info/B.md', mod: 'gyors', tesztek_db: 1 });
    await fireEvent.click(b);
    await waitFor(() => expect(keresek.filter((k) => k.ut === '/api/cpp/ellenoriz').at(-1)!.torzs).toEqual({ ut: UT, mod: 'gyors', jegyzet: 'Info/B.md' }));
    await waitFor(() => expect(c.container.querySelector('.valasztas')).toBeNull());
  });

  it('külső változás mentetlen szöveg mellett: ütközés, a gép nem ír', async () => {
    const { c } = nyit();
    const v = await nezet(c);
    const d = szerkesztok.dokumentumok.kap(UT)!;
    v.dispatch({ changes: { from: 0, insert: 'x' } });
    lemez.set(UT, FORRAS + '// kívülről\n');
    await d.kulsoValtozas();
    expect(d.allapot).toBe('utkozes');
    await waitFor(() => expect(c.container.textContent).toContain('Ütközés — döntés kell'));
  });
});
