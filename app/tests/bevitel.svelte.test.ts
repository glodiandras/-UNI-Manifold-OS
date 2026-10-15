// A Bevitel szakasz (C20a, C20b): a videólinkek beolvasása, a letöltés indítása a feladatsoron át (`video_letoltes`, alapból a bevitellel),
// a core 400-as magyar üzenetének megjelenítése, a „Videó hozzáadása linkből…” parancs (⌘P) összekötése a szakasszal; C20b: a staging
// várakozó videóinak bevitele (`video_integralas`) és a behúzott videó darabolt feltöltése.

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { Regiszter } from '../src/lib/parancsok/regiszter';
import { feladatsor } from '../src/lib/vezerlo/feladatsor.svelte';
import { videoBevitel } from '../src/lib/vezerlo/videoBevitel.svelte';
import { VIDEO_MAX, linkekBeolvas } from '../src/lib/vezerlo/videoLink';
import { BEJARAS_PLAFON, alapKijeloles, forrasLeiras, letoltesTerv, type BejarasTetel } from '../src/lib/vezerlo/videoBejaras';
import { DARAB, videoFajl, videoFeltolt } from '../src/lib/vezerlo/videoFeltoltes';
import type { Feladat } from '../src/lib/vezerlo/tipusok';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import { vezerloTelepit } from '../src/vezerlo';
import ManifoldLap from '../src/hej/ManifoldLap.svelte';
import Bevitel from '../src/hej/vezerlo/Bevitel.svelte';

function feladat(id: string, mezok: Partial<Feladat> = {}): Feladat {
  return {
    id, tipus: 'video_letoltes', cim: 'Videó letöltése', osszegzes: '', figyelmeztetes: [], lepesek: [{ cim: 'Videó letöltése' }],
    kulturalt_stop: true, allapot: 'sorban', letrehozva: '2026-10-04T10:00:00', indult: null, vegzett: null, szazalek: 0,
    lepes_i: 0, kilepes: null, hiba: null, leallitas_kerve: false, forras: '2.0', vault_ir: false, modell: false, ...mezok,
  };
}

const valasz = (adat: unknown, kod = 200) =>
  new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });

let kerelmek: { url: string; metodus: string; body?: Record<string, unknown> }[];
let valaszok: Record<string, (init?: RequestInit) => Response>;

function kornyezet() {
  const felulet = new Felulet();
  const kapcsolat = new CoreKapcsolat('ws://x');
  const context = new Map<unknown, unknown>([[KORNYEZET_KULCS, { felulet, fajlok: new VaultFajlok(), kapcsolat }]]);
  return { felulet, kapcsolat, context };
}

beforeEach(() => {
  kerelmek = [];
  valaszok = {};
  feladatsor.lista = [];
  feladatsor.betoltve = true;
  feladatsor.hiba = null;
  ertesitesek.lista = [];
  ertesitesek.elozmeny = [];
  videoBevitel.fokuszKer = 0;
  videoBevitel.kezelt = 0;
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://127.0.0.1/');
    kerelmek.push({ url: u.pathname, metodus: init?.method ?? 'GET', body: init?.body ? JSON.parse(String(init.body)) : undefined });
    const f = valaszok[`${init?.method ?? 'GET'} ${u.pathname}`];
    return f ? f(init) : valasz({ hiba: 'nincs' }, 404);
  });
});

afterEach(() => {
  cleanup();
  document.body.textContent = '';
  vi.unstubAllGlobals();
});

describe('linkekBeolvas', () => {
  it('soronként egy http(s) link, ismétlés nélkül, sorrendtartóan', () => {
    const r = linkekBeolvas('https://zanza.tv/a\n  https://youtu.be/x \nhttps://zanza.tv/a\n\nhttp://pelda.hu/v');
    expect(r.urlek).toEqual(['https://zanza.tv/a', 'https://youtu.be/x', 'http://pelda.hu/v']);
    expect(r.hibak).toEqual([]);
  });

  it('a nem http(s), a hitelesítést tartalmazó és a hibás darab figyelmen kívül marad, megnevezve', () => {
    const r = linkekBeolvas('ftp://x/y javascript:alert(1) https://u:p@h.hu/x nem-link file:///etc/passwd https://jo.hu/v');
    expect(r.urlek).toEqual(['https://jo.hu/v']);
    expect(r.hibak.length).toBe(5);
    expect(r.hibak[0]).toMatch(/^Nem http\(s\) link: ftp/);
  });

  it('a hosszú link a hibaüzenetben csonkul', () => {
    const r = linkekBeolvas('x' + 'a'.repeat(100));
    expect(r.hibak[0].length).toBeLessThan(90);
    expect(r.hibak[0]).toContain('…');
  });

  it(`a ${VIDEO_MAX}-nél több link hibát jelez`, () => {
    const sok = Array.from({ length: VIDEO_MAX + 1 }, (_, i) => `https://zanza.tv/${i}`).join('\n');
    const r = linkekBeolvas(sok);
    expect(r.urlek.length).toBe(VIDEO_MAX + 1);
    expect(r.hibak.at(-1)).toMatch(new RegExp(`legfeljebb ${VIDEO_MAX} link`));
  });

  it('üres szövegre semmi', () => {
    expect(linkekBeolvas('  \n ')).toEqual({ urlek: [], hibak: [] });
  });
});

describe('a Bevitel szakasz', () => {
  it('érvényes link nélkül a Letöltés tiltott; a hibás darab megnevezve', async () => {
    const { context } = kornyezet();
    render(Bevitel, { context, props: { onnyit: () => {} } });
    const gomb = screen.getByRole('button', { name: 'Letöltés' }) as HTMLButtonElement;
    expect(gomb.disabled).toBe(true);
    await fireEvent.input(screen.getByLabelText(/Videólinkek/), { target: { value: 'ftp://x/y' } });
    expect(gomb.disabled).toBe(true);
    expect(screen.getByText(/Nem http\(s\) link: ftp/)).toBeTruthy();
    await fireEvent.input(screen.getByLabelText(/Videólinkek/), { target: { value: 'https://zanza.tv/a' } });
    expect(gomb.disabled).toBe(false);
  });

  it('a letöltés a feladatsoron át indul (video_letoltes, urlek), az új feladat a listába kerül, a mező kiürül', async () => {
    valaszok['POST /api/feladatok'] = () => valasz(feladat('F-1'), 201);
    const { context } = kornyezet();
    render(Bevitel, { context, props: { onnyit: () => {} } });
    await fireEvent.input(screen.getByLabelText(/Videólinkek/), { target: { value: 'https://zanza.tv/a\nhttps://youtu.be/x' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Letöltés' }));
    await waitFor(() => expect(kerelmek.find((k) => k.metodus === 'POST')?.body).toEqual({
      tipus: 'video_letoltes', parameterek: { urlek: ['https://zanza.tv/a', 'https://youtu.be/x'], bevitel: true },
    }));
    await waitFor(() => expect(feladatsor.lista.map((f) => f.id)).toEqual(['F-1']));
    expect((screen.getByLabelText(/Videólinkek/) as HTMLTextAreaElement).value).toBe('');
    expect(ertesitesek.elozmeny[0]?.cim).toBe('A letöltés elindult');
    expect(await screen.findByRole('list', { name: 'A legutóbbi letöltések' })).toBeTruthy();
  });

  it('a core 400-as magyar üzenete a mező alatt látszik, a link megmarad', async () => {
    valaszok['POST /api/feladatok'] = () => valasz({ hiba: 'Hiányzik az ffmpeg (runtime/ffmpeg/ffmpeg): bin/mos runtime fetch ffmpeg' }, 400);
    const { context } = kornyezet();
    render(Bevitel, { context, props: { onnyit: () => {} } });
    await fireEvent.input(screen.getByLabelText(/Videólinkek/), { target: { value: 'https://zanza.tv/a' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Letöltés' }));
    const hiba = await screen.findByRole('alert');
    expect(hiba.textContent).toContain('Hiányzik az ffmpeg');
    expect((screen.getByLabelText(/Videólinkek/) as HTMLTextAreaElement).value).toBe('https://zanza.tv/a');
    expect(feladatsor.lista).toEqual([]);
  });

  it('csak a video_letoltes feladatok látszanak, legfeljebb három', async () => {
    feladatsor.lista = [
      feladat('F-1'), feladat('F-2'), feladat('F-3'), feladat('F-4'),
      { ...feladat('F-9'), tipus: 'mentes', cim: 'Mentés a belső lemezre' },
    ];
    const { context } = kornyezet();
    render(Bevitel, { context, props: { onnyit: () => {} } });
    expect(screen.getAllByRole('button', { name: /Videó letöltése/ }).length).toBe(3);
    expect(screen.queryByText('Mentés a belső lemezre')).toBeNull();
  });

  it('a feladat sorára kattintva a részlet nyílik', async () => {
    feladatsor.lista = [feladat('F-1')];
    const nyit = vi.fn();
    const { context } = kornyezet();
    render(Bevitel, { context, props: { onnyit: nyit } });
    await fireEvent.click(screen.getByRole('button', { name: /Videó letöltése/ }));
    expect(nyit).toHaveBeenCalledWith('F-1');
  });
});

describe('C20b: a bevitel a vaultba', () => {
  it('a várakozó videók száma a gombon; a bevitel a video_integralas feladatot indítja', async () => {
    valaszok['GET /api/video/allapot'] = () => valasz({ staging: { pending: 2, integrated: 5 }, varakozik: 2 });
    valaszok['POST /api/feladatok'] = () => valasz(feladat('F-7', { tipus: 'video_integralas', cim: 'Videók bevitele a vaultba' }), 201);
    const { context } = kornyezet();
    render(Bevitel, { context, props: { onnyit: () => {} } });
    const gomb = await screen.findByRole('button', { name: 'Bevitel a vaultba (2)' });
    await fireEvent.click(screen.getByLabelText(/Próba/));
    await fireEvent.click(gomb);
    await waitFor(() => expect(kerelmek.find((k) => k.metodus === 'POST')?.body).toEqual({
      tipus: 'video_integralas', parameterek: { proba: true },
    }));
    await waitFor(() => expect(feladatsor.lista.map((f) => f.id)).toEqual(['F-7']));
  });

  it('86. d. (javasolt): célmappával csak a kijelölt várakozó videók mennek, a mappa javaslatokkal (tema_mappa, mappak)', async () => {
    valaszok['GET /api/video/allapot'] = () => valasz({
      staging: { pending: 3 }, varakozik: 3, temamappak: ['D08 - Algoritmizálás és programozás', 'D12 - A digitális eszközök használata'],
      fuggo: [
        { mappa: 'YouTube/Informatika/CS50x - Lecture 1 - C', cim: 'CS50x - Lecture 1 - C' },
        { mappa: 'YouTube/Irodalom/CS50x - Lecture 0 - Scratch', cim: 'CS50x - Lecture 0 - Scratch' },
        { mappa: 'Zanza/Történelem/A reformkor', cim: 'A reformkor' },
      ],
    });
    valaszok['POST /api/feladatok'] = () => valasz(feladat('F-8', { tipus: 'video_integralas', cim: 'Videók bevitele a vaultba' }), 201);
    const { context } = kornyezet();
    render(Bevitel, { context, props: { onnyit: () => {} } });
    await screen.findByRole('button', { name: 'Bevitel a vaultba (3)' });
    const javaslatok = [...document.querySelectorAll('#video-temamappak option')].map((o) => (o as HTMLOptionElement).value);
    expect(javaslatok).toEqual(['D08 - Algoritmizálás és programozás', 'D12 - A digitális eszközök használata']);
    await fireEvent.input(screen.getByLabelText(/Célmappa \(téma\)/), { target: { value: ' D13 - CS50 ' } });
    const gomb = screen.getByRole('button', { name: 'Bevitel a célmappába (0)' }) as HTMLButtonElement;
    expect(gomb.disabled).toBe(true);                       // célmappával az összes várakozó nem mehet: kijelölés kell
    expect(screen.getByRole('list', { name: 'A célmappába vihető videók' }).textContent).toContain('YouTube/Irodalom/');
    await fireEvent.click(screen.getByLabelText(/CS50x - Lecture 0 - Scratch/));
    await fireEvent.click(screen.getByLabelText(/CS50x - Lecture 1 - C/));
    expect(gomb.textContent).toContain('Bevitel a célmappába (2)');
    expect(gomb.disabled).toBe(false);
    await fireEvent.click(gomb);
    await waitFor(() => expect(kerelmek.find((k) => k.metodus === 'POST')?.body).toEqual({
      tipus: 'video_integralas',
      parameterek: {
        mappak: ['YouTube/Informatika/CS50x - Lecture 1 - C', 'YouTube/Irodalom/CS50x - Lecture 0 - Scratch'], tema_mappa: 'D13 - CS50',
      },
    }));
    expect(ertesitesek.elozmeny[0]?.szoveg).toContain('Célmappa: D13 - CS50.');
  });

  it('a letöltés vagy a bevitel végén és újracsatlakozáskor a staging állapota frissül (a letöltött videó bevihető)', async () => {
    let varakozik = 0;
    valaszok['GET /api/video/allapot'] = () => valasz({ staging: { pending: varakozik }, varakozik, fuggo: [] });
    feladatsor.lista = [feladat('F-1', { allapot: 'fut' })];
    const { context, kapcsolat } = kornyezet();
    render(Bevitel, { context, props: { onnyit: () => {} } });
    const gomb = (await screen.findByRole('button', { name: 'Bevitel a vaultba' })) as HTMLButtonElement;
    await waitFor(() => expect(gomb.disabled).toBe(true));
    const lekeresek = () => kerelmek.filter((k) => k.url === '/api/video/allapot').length;
    const elotte = lekeresek();
    varakozik = 1;
    feladatsor.lista = [feladat('F-1', { allapot: 'kesz' })];
    await screen.findByRole('button', { name: 'Bevitel a vaultba (1)' });
    expect(lekeresek()).toBe(elotte + 1);
    feladatsor.lista = [feladat('F-1', { allapot: 'kesz' }), feladat('F-2', { allapot: 'sorban' })]; // nem lezárt: nincs lekérés
    await Promise.resolve();
    expect(lekeresek()).toBe(elotte + 1);
    varakozik = 3;
    kapcsolat.szetoszt({ tipus: 'hello' });
    await screen.findByRole('button', { name: 'Bevitel a vaultba (3)' });
  });

  it('kitöltött célmappánál a letöltés után nincs automatikus (téma-felismeréses) bevitel, és ezt kimondja', async () => {
    valaszok['POST /api/feladatok'] = () => valasz(feladat('F-1'), 201);
    const { context } = kornyezet();
    render(Bevitel, { context, props: { onnyit: () => {} } });
    await fireEvent.input(screen.getByLabelText(/Célmappa \(téma\)/), { target: { value: 'D13 - CS50' } });
    expect((screen.getByLabelText(/Utána a vaultba is/) as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByText(/a letöltés után a bevitel nem indul magától/)).toBeTruthy();
    await fireEvent.input(screen.getByLabelText(/Videólinkek/), { target: { value: 'https://zanza.tv/a' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Letöltés' }));
    await waitFor(() => expect(kerelmek.find((k) => k.metodus === 'POST')?.body).toEqual({
      tipus: 'video_letoltes', parameterek: { urlek: ['https://zanza.tv/a'] },
    }));
    expect(ertesitesek.elozmeny[0]?.szoveg).toContain('„D13 - CS50” célmappába');
  });

  it('a link letöltése bevitel nélkül is kérhető', async () => {
    valaszok['POST /api/feladatok'] = () => valasz(feladat('F-1'), 201);
    const { context } = kornyezet();
    render(Bevitel, { context, props: { onnyit: () => {} } });
    await fireEvent.click(screen.getByLabelText(/Utána a vaultba is/));
    await fireEvent.input(screen.getByLabelText(/Videólinkek/), { target: { value: 'https://zanza.tv/a' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Letöltés' }));
    await waitFor(() => expect(kerelmek.find((k) => k.metodus === 'POST')?.body).toEqual({
      tipus: 'video_letoltes', parameterek: { urlek: ['https://zanza.tv/a'] },
    }));
  });

  it('a behúzott nem videó fájl hibát ad, feltöltés nincs', async () => {
    const { context } = kornyezet();
    render(Bevitel, { context, props: { onnyit: () => {} } });
    const huzo = screen.getByRole('button', { name: 'Videófájl behúzása vagy kiválasztása' });
    await fireEvent.drop(huzo, { dataTransfer: { files: [new File(['x'], 'kep.jpg')] } });
    expect((await screen.findByRole('alert')).textContent).toContain('Csak videófájl');
    expect(kerelmek.filter((k) => k.url === '/api/video/bejovo')).toEqual([]);
  });

  it('videoFeltolt: darabonként, sorrendhelyes offsettel, egy csoportba, majd a bevitel a csoportra', async () => {
    const hivasok: { ut: string; torzs: Record<string, unknown> }[] = [];
    const keres = (async (ut: string, o: { torzs: Record<string, unknown> }) => {
      hivasok.push({ ut, torzs: o.torzs });
      return ut === '/api/video/bejovo' ? { csoport: 'cs1' } : feladat('F-9', { tipus: 'video_integralas' });
    }) as never;
    const nagy = new File([new Uint8Array(DARAB + 10)], 'Előadás.mp4');
    const kicsi = new File(['abc'], 'b.mov');
    const f = await videoFeltolt([nagy, new File(['x'], 'jegyzet.txt'), kicsi], {}, keres);
    expect(f.id).toBe('F-9');
    const fel = hivasok.filter((h) => h.ut === '/api/video/bejovo').map((h) => [h.torzs.nev, h.torzs.offset, h.torzs.vege, h.torzs.csoport]);
    expect(fel).toEqual([['Előadás.mp4', 0, false, undefined], ['Előadás.mp4', DARAB, true, 'cs1'], ['b.mov', 0, true, 'cs1']]);
    expect(hivasok.at(-1)).toEqual({ ut: '/api/feladatok', torzs: { tipus: 'video_integralas', parameterek: { csoport: 'cs1' } } });
    expect([videoFajl({ name: 'a.MKV' }), videoFajl({ name: 'a.jpg' })]).toEqual([true, false]);
    await expect(videoFeltolt([kicsi.slice(0, 1) as File], {}, keres)).rejects.toThrow(/Nincs videófájl/);
  });
});

describe('a Manifold-lap és a parancs', () => {
  it('a Bevitel zárva nem rajzolja ki a mezőt; kattintásra nyílik (tartós állapot)', async () => {
    const { context, felulet } = kornyezet();
    render(ManifoldLap, { context });
    expect(screen.queryByLabelText(/Videólinkek/)).toBeNull();
    await fireEvent.click(screen.getByRole('button', { name: 'Bevitel' }));
    expect(screen.getByLabelText(/Videólinkek/)).toBeTruthy();
    expect(felulet.vezerlo.nyitott.bevitel).toBe(true);
  });

  it('a „Videó hozzáadása linkből…” parancs megnyitja a lapot, a szakaszt, és a mezőre teszi a fókuszt', async () => {
    const { context, felulet, kapcsolat } = kornyezet();
    const reg = new Regiszter();
    const le = vezerloTelepit(reg, felulet, kapcsolat);
    const parancs = reg.lista().find((p) => p.id === 'video.link');
    expect(parancs?.nev).toBe('Videó hozzáadása linkből…');
    expect(parancs?.kategoria).toBe('Manifold');
    expect(parancs?.elerheto?.() ?? true).toBe(true);
    await parancs!.futtat();
    expect(felulet.manifoldLap).toBe(true);
    expect(felulet.vezerlo.nyitott.bevitel).toBe(true);
    render(ManifoldLap, { context });
    await waitFor(() => expect(document.activeElement).toBe(screen.getByLabelText(/Videólinkek/)));
    le();
  });

  it('a parancs nem helyőrző: a helyőrzők listájában nincs videó', async () => {
    const { HELYORZOK } = await import('../src/vezerlo/helyorzok');
    expect(HELYORZOK.map((h) => h.id)).not.toContain('video.link');
  });
});

describe('84. döntés (javasolt): az oldal összes videója (bejárás)', () => {
  const START = 'https://cs50.harvard.edu/x/weeks/';
  const tetel = (h: string, megvan = false): BejarasTetel => ({
    oldal: `https://cs50.harvard.edu/x/weeks/${h}`, cim: `Week ${h} - CS50x 2026`, video: `https://www.youtube.com/watch?v=v${h}`, megvan,
  });

  it('az alapkijelölés a még meg nem lévők; a terv sorrendtartó, a korlát fölött megerősítést kér', () => {
    const t = [tetel('0', true), tetel('1'), tetel('2')];
    const k = alapKijeloles(t);
    expect([...k]).toEqual([t[1].video, t[2].video]);
    expect(letoltesTerv(t, new Set([t[2].video, t[0].video]), 50)).toEqual({
      urlek: [t[0].video, t[2].video], megerositesKell: false, tulSok: false,
    });
    expect(letoltesTerv(t, k, 1).megerositesKell).toBe(true);
    const sok = Array.from({ length: BEJARAS_PLAFON + 1 }, (_, i) => tetel(String(i)));
    expect(letoltesTerv(sok, alapKijeloles(sok), 50).tulSok).toBe(true);
  });

  it('felderítés → lista → kijelölés → letöltés a kijelöltekkel (bejaras: true)', async () => {
    let post = 0;
    valaszok['POST /api/feladatok'] = () =>
      ++post === 1
        ? valasz(feladat('B-1', { tipus: 'video_bejaras', cim: 'Az oldal videóinak felderítése' }), 201)
        : valasz(feladat('F-2'), 201);
    valaszok['GET /api/video/bejaras'] = () =>
      valasz({ kesz: true, start: START, oldalak: 13, max_db: 50, tetelek: [tetel('0', true), tetel('1'), tetel('ai')] });
    const { context } = kornyezet();
    render(Bevitel, { context, props: { onnyit: () => {} } });
    await fireEvent.click(screen.getByLabelText(/Az oldal összes videója/));
    await fireEvent.input(screen.getByLabelText(/Az oldal linkje/), { target: { value: START } });
    await fireEvent.click(screen.getByRole('button', { name: 'Videók keresése' }));
    await waitFor(() => expect(kerelmek.find((k) => k.metodus === 'POST')?.body).toEqual({
      tipus: 'video_bejaras', parameterek: { url: START },
    }));
    expect(kerelmek.some((k) => k.url === '/api/video/bejaras')).toBe(false);
    // a feladat vége (WS-esemény helyett a feladatsor frissül) → a lista betöltődik
    feladatsor.upsert(feladat('B-1', { tipus: 'video_bejaras', allapot: 'kesz' }));
    const lista = await screen.findByRole('region', { name: 'Az oldal videói' });
    expect(lista.textContent).toContain('3 videó · 13 oldal olvasva');
    expect(lista.textContent).toContain('megvan');
    const gomb = screen.getByRole('button', { name: 'Letöltés (2)' });
    await fireEvent.click(screen.getByLabelText(/Week 1 - CS50x/));
    expect(screen.getByRole('button', { name: 'Letöltés (1)' })).toBe(gomb);
    await fireEvent.click(gomb);
    await waitFor(() => expect(kerelmek.filter((k) => k.metodus === 'POST')[1]?.body).toEqual({
      tipus: 'video_letoltes', parameterek: { urlek: ['https://www.youtube.com/watch?v=vai'], bevitel: true, bejaras: true },
    }));
  });

  it('a lista megmondja, melyik forrás töltődik: közvetlen fájl vagy beágyazott lejátszó; a közvetlen fájl linkje megy a letöltésbe', async () => {
    const cdn = 'https://cdn.cs50.net/2025/fall/lectures/1/lecture1-1080p.mp4';
    const kozv: BejarasTetel = {
      ...tetel('1'), video: cdn, forras: 'kozvetlen', beagyazott: 'https://www.youtube.com/watch?v=v1', minoseg: '1080p', nyelv: 'en',
      felirat: 'https://cdn.cs50.net/2025/fall/lectures/1/lang/en/lecture1.srt', diak: 'https://cdn.cs50.net/2025/fall/lectures/1/lecture1.pdf',
    };
    expect(forrasLeiras(kozv)).toBe('közvetlen fájl (1080p, en, felirattal)');
    expect(forrasLeiras({ ...kozv, felirat: null, nyelv: null })).toBe('közvetlen fájl (1080p, felirat nélkül)');
    expect(forrasLeiras(tetel('2'))).toBe('beágyazott lejátszó');
    let post = 0;
    valaszok['POST /api/feladatok'] = () =>
      ++post === 1 ? valasz(feladat('B-4', { tipus: 'video_bejaras' }), 201) : valasz(feladat('F-4'), 201);
    valaszok['GET /api/video/bejaras'] = () =>
      valasz({ kesz: true, start: START, oldalak: 3, max_db: 50, tetelek: [kozv, { ...tetel('2'), forras: 'beagyazott' }] });
    const { context } = kornyezet();
    render(Bevitel, { context, props: { onnyit: () => {} } });
    await fireEvent.click(screen.getByLabelText(/Az oldal összes videója/));
    await fireEvent.input(screen.getByLabelText(/Az oldal linkje/), { target: { value: START } });
    await fireEvent.click(screen.getByRole('button', { name: 'Videók keresése' }));
    await waitFor(() => expect(feladatsor.kap('B-4')).toBeTruthy());
    feladatsor.upsert(feladat('B-4', { tipus: 'video_bejaras', allapot: 'kesz' }));
    const lista = await screen.findByRole('region', { name: 'Az oldal videói' });
    expect(lista.textContent).toContain('közvetlen fájl (1080p, en, felirattal) · diák: csak a link');
    expect(lista.textContent).toContain('beágyazott lejátszó');
    await fireEvent.click(screen.getByLabelText(/Week 2 - CS50x/));
    await fireEvent.click(screen.getByRole('button', { name: 'Letöltés (1)' }));
    await waitFor(() => expect(kerelmek.filter((k) => k.metodus === 'POST')[1]?.body).toEqual({
      tipus: 'video_letoltes', parameterek: { urlek: [cdn], bevitel: true, bejaras: true },
    }));
  });

  it('a korlát fölött csak megerősítéssel indul (megerosit: true)', async () => {
    valaszok['POST /api/feladatok'] = () => valasz(feladat('B-2', { tipus: 'video_bejaras' }), 201);
    valaszok['GET /api/video/bejaras'] = () =>
      valasz({ kesz: true, start: START, oldalak: 4, max_db: 2, tetelek: [tetel('0'), tetel('1'), tetel('2')] });
    const { context } = kornyezet();
    render(Bevitel, { context, props: { onnyit: () => {} } });
    await fireEvent.click(screen.getByLabelText(/Az oldal összes videója/));
    await fireEvent.input(screen.getByLabelText(/Az oldal linkje/), { target: { value: START } });
    await fireEvent.click(screen.getByRole('button', { name: 'Videók keresése' }));
    await waitFor(() => expect(feladatsor.kap('B-2')).toBeTruthy());
    feladatsor.upsert(feladat('B-2', { tipus: 'video_bejaras', allapot: 'kesz' }));
    const gomb = (await screen.findByRole('button', { name: 'Letöltés (3)' })) as HTMLButtonElement;
    expect(gomb.disabled).toBe(true);
    valaszok['POST /api/feladatok'] = () => valasz(feladat('F-3'), 201);
    await fireEvent.click(screen.getByLabelText(/Igen, mind a 3 videót/));
    expect(gomb.disabled).toBe(false);
    await fireEvent.click(gomb);
    await waitFor(() => expect(kerelmek.filter((k) => k.metodus === 'POST')[1]?.body).toMatchObject({
      tipus: 'video_letoltes', parameterek: { bejaras: true, megerosit: true },
    }));
  });

  it('a sikertelen bejárás hibája látszik', async () => {
    valaszok['POST /api/feladatok'] = () => valasz(feladat('B-3', { tipus: 'video_bejaras' }), 201);
    const { context } = kornyezet();
    render(Bevitel, { context, props: { onnyit: () => {} } });
    await fireEvent.click(screen.getByLabelText(/Az oldal összes videója/));
    await fireEvent.input(screen.getByLabelText(/Az oldal linkje/), { target: { value: START } });
    await fireEvent.click(screen.getByRole('button', { name: 'Videók keresése' }));
    await waitFor(() => expect(feladatsor.kap('B-3')).toBeTruthy());
    feladatsor.upsert(feladat('B-3', { tipus: 'video_bejaras', allapot: 'hiba', hiba: 'robots.txt tiltja' }));
    expect((await screen.findByRole('alert')).textContent).toContain('robots.txt tiltja');
  });
});
