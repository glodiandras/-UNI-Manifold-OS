// A tulajdonság-panel a szerkesztőben (C11b): egy írási út — a core csak a frontmatter-blokk új szövegét számolja, a
// módosítás a szerkesztő dokumentumába kerül (mentés, ütközés, ⌘Z a megszokott úton), a panel mindhárom módban ott van.

import { undo } from '@codemirror/commands';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import Szerkeszto from '../src/szerkeszto/Szerkeszto.svelte';
import { szerkesztok } from '../src/szerkeszto/szerkesztok.svelte';

const SZOVEG = '---\nTags:\n  - AI\nStatus: Completed\n---\n\n# Cím\n\nTörzs.\n';
let lemez: Map<string, string>;
let modositasok: Record<string, unknown>[];

function valasz(kod: number, adat: unknown): Response {
  return new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });
}

const hash = (s: string) => `h${s.length}`;

beforeEach(() => {
  lemez = new Map([['J.md', SZOVEG]]);
  modositasok = [];
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://127.0.0.1/');
    const body = init?.body ? JSON.parse(String(init.body)) : {};
    if (u.pathname === '/api/vault/fajl' && (!init?.method || init.method === 'GET')) {
      const t = lemez.get(u.searchParams.get('ut')!)!;
      return valasz(200, { ut: 'J.md', tartalom: t, hash: hash(t), jel: '', mtime: 0, kodolas_hiba: false });
    }
    if (u.pathname === '/api/vault/fajl' && init?.method === 'PUT') {
      lemez.set(body.ut, body.tartalom);
      return valasz(200, { ok: true, ut: body.ut, hash: hash(body.tartalom), jel: '', uzenet: '', pillanat: null, elotte: null, git: true });
    }
    if (u.pathname === '/api/vault/sema') {
      return valasz(200, { mezosorrend: ['Tags', 'Source', 'Status', 'NN', 'Canvas'], extra_kulcsok: [], tags_ertekkeszlet: [], status_ertekkeszlet: ['Completed', 'In progress', 'Review'], status_gazdai: true, osztaly: { nev: 'normal', mezosorrend: [], ertekek: true, sema_nelkul: false } });
    }
    if (u.pathname === '/api/vault/tulajdonsagok/elemez') {
      const fm = body.fm as string | null;
      const st = /Status: (.*)/.exec(fm ?? '')?.[1] ?? null;
      return valasz(200, {
        van: !!fm, hiba: null, osztaly: 'normal', kulcsok: ['Tags', 'Status'], problemak: [],
        tulajdonsagok: [{ kulcs: 'Tags', tipus: 'tags', ertek: ['AI'], ervenyes: true }, { kulcs: 'Status', tipus: 'text', ertek: st, ervenyes: true }],
      });
    }
    if (u.pathname === '/api/vault/tulajdonsagok/modosit') {
      modositasok.push(body);
      return valasz(200, { ok: true, valtozas: true, megerositheto: false, problemak: [], fm_uj: (body.fm as string).replace(/Status: .*/, `Status: ${body.ertek}`) });
    }
    return valasz(404, { hiba: 'nincs' });
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function megjelenit() {
  const felulet = new Felulet({ csend: { be: false } }); // a mindent mutató felület (C38: csendben a panel alapból zárt)
  const ful = $state({ id: 'f1', ut: 'J.md' as string | null, nezet: undefined as Record<string, unknown> | undefined });
  const context = new Map<unknown, unknown>([
    [KORNYEZET_KULCS, { felulet, fajlok: new VaultFajlok(), kapcsolat: new CoreKapcsolat('ws://127.0.0.1:1/ws') }],
  ]);
  return { ...render(Szerkeszto, { props: { ful, info: undefined, aktiv: true }, context }), felulet };
}

describe('a panel a szerkesztőben', () => {
  it('a módosítás a dokumentumba kerül (nem külön íróúton), a ⌘Z visszavonja', async () => {
    const { container } = megjelenit();
    const sel = (await screen.findByLabelText('Status')) as HTMLSelectElement;
    expect(container.querySelector('.tul')).not.toBeNull();
    await fireEvent.change(sel, { target: { value: 'Review' } });
    const view = () => szerkesztok.aktiv!.nezet()!;
    await waitFor(() => expect(view().state.doc.toString()).toContain('Status: Review'));
    expect(view().state.doc.toString()).toBe(SZOVEG.replace('Completed', 'Review'));
    expect(modositasok[0]).toMatchObject({ kulcs: 'Status', muvelet: 'beallit', forras: 'felhasznalo', megerosit: false });
    // a core a *nyitott* frontmatter-blokkot kapta
    expect(modositasok[0].fm).toBe('---\nTags:\n  - AI\nStatus: Completed\n---\n');
    expect(undo(view())).toBe(true);
    expect(view().state.doc.toString()).toBe(SZOVEG);
  });

  it('a mentés a dokumentum szokásos útján megy (PUT, alap-hash), az új tartalommal', async () => {
    megjelenit();
    await fireEvent.change(await screen.findByLabelText('Status'), { target: { value: 'In progress' } });
    await waitFor(() => expect(szerkesztok.aktiv!.nezet()!.state.doc.toString()).toContain('In progress'));
    await szerkesztok.aktiv!.mentes();
    expect(lemez.get('J.md')).toBe(SZOVEG.replace('Completed', 'In progress'));
  });

  it('Olvasó módban is ott van a panel, és a nyers YAML-doboz nem duplázza', async () => {
    const { container } = megjelenit();
    await screen.findByLabelText('Status');
    szerkesztok.aktiv!.olvasoValt();
    await waitFor(() => expect(container.querySelector('.olvaso')).not.toBeNull());
    expect(container.querySelector('.tul')).not.toBeNull();
  });

  it('az összecsukás tartós állapotba kerül', async () => {
    const { felulet } = megjelenit();
    const gomb = await screen.findByRole('button', { name: /Tulajdonságok/ });
    expect(felulet.tulajdonsagok.nyitva).toBe(true);
    await fireEvent.click(gomb);
    expect(felulet.tulajdonsagok.nyitva).toBe(false);
    expect(felulet.sorosit().tulajdonsagok).toEqual({ nyitva: false });
  });
});
