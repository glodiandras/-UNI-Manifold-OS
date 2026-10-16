// F11 (7. tétel): az összecsukás-állapot fájlonként is megmarad (az Obsidian fájlonként tárolja): a fül nézet-állapota mellett a
// felület-állapotban, út szerint, korlátos (LRU, legfeljebb 500 fájl, bájtkorlát), a jegyzet szövegét és a lemezt nem írja.
import { foldedRanges } from '@codemirror/language';
import { cleanup, render, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet, MAX_HAJTAS_SOR, MAX_HAJTASOK_BAJT, MAX_HAJTASOK_FAJL, hajtasokErvenyes } from '../src/lib/elrendezes/felulet.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import Szerkeszto from '../src/szerkeszto/Szerkeszto.svelte';
import { mindetHajt } from '../src/szerkeszto/hajtogatas';
import { szerkesztok } from '../src/szerkeszto/szerkesztok.svelte';

describe('Felulet: fájlonkénti összecsukások', () => {
  it('megjegyzés, lekérdezés, törlés; a sorok rendezett, egyedi, érvényes egészek', () => {
    const f = new Felulet({});
    f.hajtasMent('A.md', [7, 1, 7, 0, -3, 2.5, NaN, 4]);
    expect(f.hajtasLekerdez('A.md')).toEqual([1, 4, 7]);
    expect(f.hajtasLekerdez('Nincs.md')).toBeUndefined();
    f.hajtasMent('A.md', undefined);                      // nincs több csukott tartomány: a bejegyzés eltűnik
    expect(f.hajtasLekerdez('A.md')).toBeUndefined();
    f.hajtasMent('B.md', []);
    expect(f.hajtasok).toEqual([]);
  });

  it('a mentésbe kerül és újraindítás után visszajön (a régi mentés hajtasok nélkül is betölt)', () => {
    const f = new Felulet({});
    f.hajtasMent('Mappa/A.md', [3, 9]);
    f.hajtasMent('B.md', [1]);
    const mentes = JSON.parse(JSON.stringify(f.sorosit()));
    expect(mentes.hajtasok).toEqual([['Mappa/A.md', [3, 9]], ['B.md', [1]]]);
    const g = new Felulet(mentes);
    expect(g.hajtasLekerdez('Mappa/A.md')).toEqual([3, 9]);
    expect(g.hajtasLekerdez('B.md')).toEqual([1]);
    const regi = JSON.parse(JSON.stringify(new Felulet({}).sorosit()));
    expect('hajtasok' in regi).toBe(false);               // üres állapotnál a mentés alakja nem változik
    expect(new Felulet(regi).hajtasok).toEqual([]);
  });

  it('LRU: legfeljebb 500 fájl, a legrégebben használt esik ki; a lekérdezés is „használat”', () => {
    const f = new Felulet({});
    for (let i = 0; i < MAX_HAJTASOK_FAJL; i++) f.hajtasMent(`f${i}.md`, [i + 1]);
    expect(f.hajtasok).toHaveLength(MAX_HAJTASOK_FAJL);
    expect(f.hajtasLekerdez('f0.md')).toEqual([1]);       // a legrégebbi „használt” lett
    f.hajtasMent('uj.md', [2]);
    expect(f.hajtasok).toHaveLength(MAX_HAJTASOK_FAJL);
    expect(f.hajtasLekerdez('f1.md')).toBeUndefined();    // helyette a következő legrégebbi esett ki
    expect(f.hajtasLekerdez('f0.md')).toEqual([1]);
    expect(f.hajtasLekerdez('uj.md')).toEqual([2]);
    expect(f.hajtasok[f.hajtasok.length - 1][0]).toBe('uj.md');
  });

  it('változatlan mentés nem ír újra (nincs felesleges felület-mentés); az új tartalom a végére kerül', () => {
    const f = new Felulet({});
    f.hajtasMent('A.md', [1, 2]);
    f.hajtasMent('B.md', [3]);
    const elotte = f.hajtasok;
    f.hajtasMent('B.md', [3]);
    expect(f.hajtasok).toBe(elotte);
    f.hajtasMent('A.md', [1, 2, 5]);
    expect(f.hajtasok.map(([u]) => u)).toEqual(['B.md', 'A.md']);
  });

  it('korlátok: fájlonként legfeljebb MAX_HAJTAS_SOR sor; a mentett JSON a bájtkorláton belül, a legfrissebbek maradnak', () => {
    const f = new Felulet({});
    f.hajtasMent('Sok.md', Array.from({ length: 500 }, (_, i) => i + 1));
    expect(f.hajtasLekerdez('Sok.md')).toHaveLength(MAX_HAJTAS_SOR);
    const g = new Felulet({});
    for (let i = 0; i < MAX_HAJTASOK_FAJL; i++) g.hajtasMent(`Mappa/${'hosszú-név-'.repeat(8)}${i}.md`, Array.from({ length: MAX_HAJTAS_SOR }, (_, k) => (k + 1) * 1000 + i));
    const mentett = g.sorosit().hajtasok!;
    expect(JSON.stringify(mentett).length).toBeLessThanOrEqual(MAX_HAJTASOK_BAJT);
    expect(mentett.length).toBeGreaterThan(10);
    expect(mentett.length).toBeLessThan(MAX_HAJTASOK_FAJL);
    expect(mentett[mentett.length - 1][0]).toContain(`${MAX_HAJTASOK_FAJL - 1}.md`);    // a legfrissebb megmarad
  });

  it('megbízhatatlan mentés: hibás elemek kimaradnak, az azonos útból az utolsó él, a darabszám korlátos', () => {
    expect(hajtasokErvenyes('x')).toEqual([]);
    expect(hajtasokErvenyes([['A.md', [3, 1]], ['', [1]], [5, [1]], ['B.md', 'nem lista'], ['C.md', []], ['D.md', ['x', 2]], ['A.md', [9]], null, 7, ['L'.repeat(2000), [1]]]))
      .toEqual([['D.md', [2]], ['A.md', [9]]]);
    const sok = Array.from({ length: 800 }, (_, i) => [`f${i}.md`, [1]]);
    const v = hajtasokErvenyes(sok);
    expect(v).toHaveLength(MAX_HAJTASOK_FAJL);
    expect(v[0][0]).toBe('f300.md');
    expect(v[v.length - 1][0]).toBe('f799.md');
  });

  it('átnevezés: az út (és mappa átnevezésénél az előtag) követi', () => {
    const f = new Felulet({});
    f.hajtasMent('Régi/A.md', [2]);
    f.hajtasMent('Más.md', [4]);
    f.utatNevez('Régi', 'Új');
    expect(f.hajtasLekerdez('Új/A.md')).toEqual([2]);
    expect(f.hajtasLekerdez('Régi/A.md')).toBeUndefined();
    f.utatNevez('Más.md', 'Más2.md');
    expect(f.hajtasLekerdez('Más2.md')).toEqual([4]);
  });
});

// ---------------------------------------------------------------------------------------------------------------------------------
const SZOVEG = '# Első\nEgy\n\n## Al\nKettő\n\n# Második\n- Szülő\n  - Gyerek\n';
let irasok = 0;
let fulSorszam = 0;
const valasz = (kod: number, adat: unknown) => new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });

beforeEach(() => {
  irasok = 0;
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://127.0.0.1/');
    if (u.pathname === '/api/vault/fajl' && (!init?.method || init.method === 'GET'))
      return valasz(200, { ut: u.searchParams.get('ut'), tartalom: SZOVEG, hash: 'h1', jel: '', mtime: 0, kodolas_hiba: false });
    if (init?.method && init.method !== 'GET' && ['/api/vault/fajl', '/api/vault/uj', '/api/vault/atnevez'].includes(u.pathname)) irasok++;      // a vault írása (az elemzés és a tracker-jelzés nem az)
    return valasz(404, { hiba: 'nincs' });
  });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function megjelenit(felulet: Felulet, ut: string) {
  const ful = $state({ id: `p${++fulSorszam}`, ut: ut as string | null, nezet: undefined as Record<string, unknown> | undefined });
  const context = new Map<unknown, unknown>([[KORNYEZET_KULCS, { felulet, fajlok: new VaultFajlok(), kapcsolat: new CoreKapcsolat('ws://127.0.0.1:1/ws') }]]);
  return { ...render(Szerkeszto, { props: { ful, info: undefined, aktiv: true }, context }), ful };
}
const csukottak = (v: NonNullable<ReturnType<NonNullable<typeof szerkesztok.aktiv>['nezet']>>) => {
  const ki: number[] = [];
  foldedRanges(v.state).between(0, v.state.doc.length, (a) => { ki.push(v.state.doc.lineAt(a).number); });
  return ki.sort((a, b) => a - b);
};

describe('Szerkeszto: az összecsukás fájlonként visszajön, fül nézet-állapot nélkül is', () => {
  it('összecsukás → a felület-állapotba kerül; új fülön (üres nézet-állapot), újraindított felületen is visszajön; semmi nem íródik', async () => {
    const felulet = new Felulet({});
    const elso = megjelenit(felulet, 'Mappa/Hajtas.md');
    await waitFor(() => expect(elso.container.querySelector('.cm-content')?.textContent).toContain('Első'));
    mindetHajt(szerkesztok.aktiv!.nezet()!);
    await waitFor(() => expect(felulet.hajtasok).toEqual([['Mappa/Hajtas.md', [1, 4, 7, 8]]]));
    elso.unmount();                                                      // a fül bezárul: a fül nézet-állapota elveszik, a fájlé nem

    const masodik = megjelenit(felulet, 'Mappa/Hajtas.md');              // új fül, nincs `nezet`
    await waitFor(() => expect(masodik.container.querySelector('.cm-content')?.textContent).toContain('Első'));
    expect(masodik.ful.nezet?.hajtott).toBeUndefined();
    expect(csukottak(szerkesztok.aktiv!.nezet()!)).toEqual([1, 4, 7, 8]);
    expect(szerkesztok.aktiv!.nezet()!.state.doc.toString()).toBe(SZOVEG);
    masodik.unmount();

    const ujFelulet = new Felulet(JSON.parse(JSON.stringify(felulet.sorosit())));        // a felület újraindítása a mentett állapotból
    const harmadik = megjelenit(ujFelulet, 'Mappa/Hajtas.md');
    await waitFor(() => expect(harmadik.container.querySelector('.cm-content')?.textContent).toContain('Első'));
    expect(csukottak(szerkesztok.aktiv!.nezet()!)).toEqual([1, 4, 7, 8]);
    expect(irasok).toBe(0);                                              // sem a jegyzet, sem a lemez nem íródott
  });

  it('egy másik fájlnak nincs hajtása; a teljes kibontás törli a bejegyzést', async () => {
    const felulet = new Felulet({});
    felulet.hajtasMent('Mappa/Hajtas.md', [1, 4]);
    const m = megjelenit(felulet, 'Mappa/Masik.md');
    await waitFor(() => expect(m.container.querySelector('.cm-content')?.textContent).toContain('Első'));
    expect(csukottak(szerkesztok.aktiv!.nezet()!)).toEqual([]);
    m.unmount();
    const h = megjelenit(felulet, 'Mappa/Hajtas.md');
    await waitFor(() => expect(h.container.querySelector('.cm-content')?.textContent).toContain('Első'));
    expect(csukottak(szerkesztok.aktiv!.nezet()!)).toEqual([1, 4]);
    const { mindetKibont } = await import('../src/szerkeszto/hajtogatas');
    mindetKibont(szerkesztok.aktiv!.nezet()!);
    await waitFor(() => expect(felulet.hajtasLekerdez('Mappa/Hajtas.md')).toBeUndefined());
  });
});
