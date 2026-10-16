// 01-rendering-05/06, 05-editing-03: az összecsukás a fül nézet-állapotában él (újranyitás után visszajön), az Olvasó
// ugyanazt mutatja, és a jegyzet szövegébe / a lemezre soha nem íródik.
import { foldedRanges } from '@codemirror/language';
import { cleanup, render, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import Szerkeszto from '../src/szerkeszto/Szerkeszto.svelte';
import { mindetHajt } from '../src/szerkeszto/hajtogatas';
import { szerkesztok } from '../src/szerkeszto/szerkesztok.svelte';

const SZOVEG = '# Első\nEgy\n\n## Al\nKettő\n\n# Második\n- Szülő\n  - Gyerek\n';
let irasok = 0;
let fulSorszam = 0;
const valasz = (kod: number, adat: unknown) => new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });

beforeEach(() => {
  irasok = 0;
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://127.0.0.1/');
    if (u.pathname === '/api/vault/fajl' && (!init?.method || init.method === 'GET'))
      return valasz(200, { ut: 'Hajtas.md', tartalom: SZOVEG, hash: 'h1', jel: '', mtime: 0, kodolas_hiba: false });
    if (init?.method === 'PUT') irasok++;
    return valasz(404, { hiba: 'nincs' });
  });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function megjelenit(nezet?: Record<string, unknown>) {
  const felulet = new Felulet({});
  const ful = $state({ id: `h${++fulSorszam}`, ut: 'Hajtas.md' as string | null, nezet: nezet as Record<string, unknown> | undefined });
  const context = new Map<unknown, unknown>([[KORNYEZET_KULCS, { felulet, fajlok: new VaultFajlok(), kapcsolat: new CoreKapcsolat('ws://127.0.0.1:1/ws') }]]);
  return { ...render(Szerkeszto, { props: { ful, info: undefined, aktiv: true }, context }), ful };
}

it('a hajtás a fül nézet-állapotába kerül, újranyitáskor visszajön, az Olvasó követi; a szöveg érintetlen', async () => {
  const { container, ful, unmount } = megjelenit();
  await waitFor(() => expect(container.querySelector('.cm-content')?.textContent).toContain('Első'));
  const v = szerkesztok.aktiv!.nezet()!;
  mindetHajt(v);
  await waitFor(() => expect(ful.nezet?.hajtott).toEqual([1, 4, 7, 8]));
  expect(v.state.doc.toString()).toBe(SZOVEG);

  szerkesztok.aktiv!.olvasoValt();
  await waitFor(() => expect(container.querySelector('.olvaso h1 button.olvaso-hajto')?.getAttribute('aria-expanded')).toBe('false'));
  expect((container.querySelector('.olvaso h2') as HTMLElement).style.display).toBe('none');
  // kibontás az Olvasóból: a szerkesztő állapota és a fül nézet-állapota is követi
  container.querySelector<HTMLButtonElement>('.olvaso h1 button.olvaso-hajto')!.click();
  expect((container.querySelector('.olvaso h2') as HTMLElement).style.display).toBe('');
  await waitFor(() => expect(ful.nezet?.hajtott).toEqual([4, 7, 8]));
  const mentett = { ...ful.nezet };
  unmount();

  const masodik = megjelenit(mentett);
  await waitFor(() => expect(masodik.container.querySelector('.olvaso h2')).not.toBeNull());
  const w = szerkesztok.aktiv!.nezet()!;
  const csukott: number[] = [];
  foldedRanges(w.state).between(0, w.state.doc.length, (a) => { csukott.push(w.state.doc.lineAt(a).number); });
  expect(csukott.sort((a, b) => a - b)).toEqual([4, 7, 8]);
  expect((masodik.container.querySelector('.olvaso h2 button.olvaso-hajto') as HTMLElement).getAttribute('aria-expanded')).toBe('false');
  expect(w.state.doc.toString()).toBe(SZOVEG);
  expect(irasok).toBe(0);
});
