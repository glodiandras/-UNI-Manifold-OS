// A beágyazott kvíz (C22a), ál-core-ral jsdom-ban: a kvízjegyzet beágyazása kitölthető blokk (a többi jegyzet és a `#fejezet`
// beágyazás a jegyzet szövege marad), végigkitölthető gombbal és billentyűvel, a core értékel, a tracker-esemény megy.

import { cleanup, fireEvent, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { trackerKliens } from '../src/lib/tracker/kliens.svelte';
import { linkek } from '../src/lib/vault/linkek.svelte';
import { kvizTelepit } from '../src/kviz';
import { kvizUt } from '../src/kviz/allando';
import { jegyzetOsztalyRenderelok } from '../src/szerkeszto/beagyazas/regiszter';
import { obsidianElemzo } from '../src/szerkeszto/markdown/elemzo';
import { dokumentumRenderel } from '../src/szerkeszto/olvaso/html';
import { LustaRajzolo } from '../src/szerkeszto/olvaso/lusta';

const KVIZ_UT = 'ATTCHMNTS - quizes/Cím — Kvíz 2026-10-04 2030.md';
const HELYES = [1, 2, 0];
let kerelmek: { ut: string; torzs?: any }[];
let le: () => void;
let esemeny: ReturnType<typeof vi.spyOn>;

const json = (adat: unknown, kod = 200) => new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });

function kvizValasz() {
  return {
    ok: true,
    ut: KVIZ_UT,
    forras_ut: 'M03/Forrás.md',
    kviz: {
      azon: 'KVIZ-20261004-203015',
      cim: 'Forrás',
      forras: 'M03/Forrás',
      modell: 'm',
      keszult: '2026-10-04 2030',
      kerdesek: [0, 1, 2].map((i) => ({
        id: `k${i + 1}`,
        kerdes: i === 0 ? 'Mi a $a^2$ értéke?' : `Kérdés ${i + 1}?`,
        valaszok: ['A-válasz', 'B-válasz', 'C-válasz', 'D-válasz'].map((v) => `${v} ${i + 1}`),
        szakasz: 'Első szakasz',
        jelolt: false,
      })),
    },
    token: 'tok-1',
    hibak: [],
    ujra: [],
    megvaltozott: false,
    elozmenyek: [{ mikor: '2026-10-03T10:00:00+00:00', mod: 'teljes', pont: 2, osszes: 3, szazalek: 67 }],
  };
}

function ertekeles() {
  return {
    mod: 'teljes',
    eredmenyek: [],
    osszegzes: { pont: 3, osszes: 3, szazalek: 100, matrix: { tudja: 3, szerencses: 0, tevkepzet: 0, hiany: 0 }, atnezni: [], jelolt: [] },
    szakaszok: [{ szakasz: 'Első szakasz', horgony: 'Első szakasz', osszes: 3, helyes: 3, allapot: 'rendben' }],
    javaslatok: [],
    fo_uzenet: 'Hibátlan és magabiztos: ez a jegyzet megy.',
    onismeret: { biztos: 3, biztos_helyes: 3, tipp: 0, tipp_helyes: 0 },
    trend: null,
    fedetlen_szakaszok: [],
    ujra: [],
    ido_ms: 5000,
  };
}

beforeEach(() => {
  kerelmek = [];
  linkek.mediaToken = 'tok';
  esemeny = vi.spyOn(trackerKliens, 'esemeny').mockImplementation(() => {});
  vi.stubGlobal('fetch', async (url: string, o?: { body?: string }) => {
    const u = new URL(url, 'http://127.0.0.1/');
    const torzs = o?.body ? JSON.parse(o.body) : undefined;
    kerelmek.push({ ut: u.pathname + u.search, torzs });
    if (u.pathname === '/api/vault/beagyazas') {
      const cel = u.searchParams.get('cel');
      if (cel === 'Kvíz') return json({ tipus: 'jegyzet', ut: KVIZ_UT, szoveg: '# Kvíz\n\nA kvíz nyers szövege.\n' });
      if (cel === 'Jegyzet') return json({ tipus: 'jegyzet', ut: 'M/Jegyzet.md', szoveg: 'Sima jegyzet.' });
    }
    if (u.pathname === '/api/kviz/kviz') return json(kvizValasz());
    if (u.pathname === '/api/kviz/megoldas') {
      const i = Number(torzs.kerdes.slice(1)) - 1;
      return json({
        ok: true,
        kerdes: torzs.kerdes,
        helyes: torzs.valasz === HELYES[i],
        helyes_index: HELYES[i],
        helyes_valasz: `helyes ${i + 1}`,
        magyarazat: 'Mert **így**.',
        idezet: 'A jegyzet mondata: $x$.',
        szakasz: 'Első szakasz',
        horgony: 'Első szakasz',
        jegyzet: 'M03/Forrás',
        forras_ut: 'M03/Forrás.md',
      });
    }
    if (u.pathname === '/api/kviz/kitoltes') return json({ ok: true, uj: true, ertekeles: ertekeles(), token: 'tok-2', tracker: { ut: 'M03/Forrás.md', adat: { kviz: 'KVIZ-20261004-203015', pont: 3 } } });
    if (u.pathname === '/api/kviz/jelol') return json({ ok: true, jelolesek: ['k1'] });
    return json({ tipus: 'nincs' });
  });
  le = kvizTelepit();
});

afterEach(() => {
  le();
  cleanup();
  document.body.textContent = '';
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function rajzol(szoveg: string, ut = 'M03/Fő.md'): HTMLElement {
  const kont = document.createElement('div');
  document.body.appendChild(kont);
  kont.appendChild(dokumentumRenderel(obsidianElemzo.parse(szoveg), { olvas: (a, b) => szoveg.slice(a, b), ut, lusta: LustaRajzolo.azonnali() }));
  return kont;
}

const kviz = (k: HTMLElement) => within(k.querySelector<HTMLElement>('.kviz')!);

describe('a beágyazás', () => {
  it('az állandó a kvízmappa alatti .md-t ismeri fel', () => {
    expect(kvizUt(KVIZ_UT)).toBe(true);
    expect(kvizUt(KVIZ_UT.normalize('NFD'))).toBe(true);
    expect(kvizUt('M03/Jegyzet.md')).toBe(false);
    expect(kvizUt('ATTCHMNTS - quizes/kep.png')).toBe(false);
    expect(kvizUt('ATTCHMNTS - quizes.md')).toBe(false);
    expect(kvizUt(undefined)).toBe(false);
  });

  it('a kvízjegyzet kitölthető blokk, a többi jegyzet és a #fejezet a szöveg', async () => {
    const k = rajzol('![[Kvíz]]\n\n![[Jegyzet]]\n');
    await vi.waitFor(() => expect(k.querySelector('.beagyazas-kviz .kviz')).not.toBeNull());
    expect(k.querySelector('.beagyazas-kviz .beagyazas-torzs')).toBeNull();                     // nem a nyers szöveg
    expect(k.querySelector('.beagyazas-jegyzet')!.textContent).toContain('Sima jegyzet.');
    expect(kerelmek.some((r) => r.ut === `/api/kviz/kviz?ut=${encodeURIComponent(KVIZ_UT)}`)).toBe(true);
    await waitFor(() => expect(k.querySelector('.kviz-cim')?.textContent).toBe('Kvíz · Forrás'));
    expect(k.querySelector('.kviz-al')!.textContent).toContain('3 kérdés · legutóbb 2/3 (67 %)');
  });

  it('a fejezet-beágyazás a jegyzet szövege marad', async () => {
    const eredeti = globalThis.fetch;
    vi.stubGlobal('fetch', async (url: string, o?: unknown) => {
      if (url.includes('/api/vault/beagyazas') && url.includes('alcel=')) return json({ tipus: 'jegyzet', ut: KVIZ_UT, alcel: 'Kérdések', szoveg: '## Kérdések\nrész' });
      return eredeti(url, o as never);
    });
    const k = rajzol('![[Kvíz#Kérdések]]');
    await vi.waitFor(() => expect(k.querySelector('.beagyazas-jegyzet')).not.toBeNull());
    expect(k.querySelector('.kviz')).toBeNull();
  });

  it('a regiszter kettős regisztrációt nem enged; a leállítás kivezeti a renderelőt', () => {
    expect(() => kvizTelepit()).toThrow(/már regisztrált/);
    le();
    expect(jegyzetOsztalyRenderelok.keres({ tipus: 'jegyzet', ut: KVIZ_UT }, { cel: 'x' } as never)).toBeUndefined();
    le = kvizTelepit();
  });
});

describe('kitöltés a blokkban', () => {
  async function indit(): Promise<HTMLElement> {
    const k = rajzol('![[Kvíz]]');
    await vi.waitFor(() => expect(k.querySelector('.kviz-gomb.elsodleges')).not.toBeNull());
    await fireEvent.click(kviz(k).getByRole('button', { name: 'Kitöltés' }));
    return k;
  }

  async function valaszt(k: HTMLElement, betu: string) {
    await fireEvent.click(kviz(k).getAllByRole('radio').find((r) => r.textContent!.trim().startsWith(betu))!);
  }

  it('gombokkal végigkitölthető: visszajelzés, elemzés, tracker-esemény', async () => {
    const k = await indit();
    expect(k.querySelector('.kviz-kerdes .katex')).not.toBeNull();                              // a képlet a jegyzet renderelőjével
    expect(kviz(k).getAllByRole('radio')).toHaveLength(4);
    await valaszt(k, 'A');
    // az „A” pozíció a tárolt sorrend szerint ennyi indexet jelent: a core kapja
    await fireEvent.click(kviz(k).getByRole('button', { name: 'Ellenőrzés — biztos vagyok' }));
    await waitFor(() => expect(k.querySelector('.kviz-visszajelzes')).not.toBeNull());
    const megoldasKeres = kerelmek.filter((r) => r.ut === '/api/kviz/megoldas');
    expect(megoldasKeres).toHaveLength(1);
    expect(megoldasKeres[0].torzs).toMatchObject({ ut: KVIZ_UT, token: 'tok-1', kerdes: 'k1', tipp: false });
    expect(typeof megoldasKeres[0].torzs.valasz).toBe('number');
    expect(k.querySelector('.kviz-itelet')!.textContent).toMatch(/^(✓ Helyes|✗ Nem ez)/);
    expect(k.querySelector('.kviz-visszajelzes strong')).not.toBeNull();                       // a magyarázat Markdownja
    expect(k.querySelector('.kviz-idezet .katex')).not.toBeNull();
    for (const _ of [1, 2]) {
      await fireEvent.click(kviz(k).getByRole('button', { name: /Következő|Kiértékelés/ }));
      await valaszt(k, 'B');
      await fireEvent.click(kviz(k).getByRole('button', { name: 'Csak tippeltem' }));
      await waitFor(() => expect(k.querySelector('.kviz-visszajelzes')).not.toBeNull());
    }
    await fireEvent.click(kviz(k).getByRole('button', { name: 'Kiértékelés' }));
    await waitFor(() => expect(k.querySelector('.kviz-pontszam')).not.toBeNull());
    expect(k.querySelector('.kviz-pontszam')!.textContent).toContain('3/3');
    expect(k.querySelector('.kviz-fo')!.textContent).toContain('Hibátlan');
    const kit = kerelmek.find((r) => r.ut === '/api/kviz/kitoltes')!.torzs;
    expect(megoldasKeres.length + 2).toBe(3);
    expect(kerelmek.filter((r) => r.ut === '/api/kviz/megoldas').map((r) => r.torzs.tipp)).toEqual([false, true, true]);
    expect(kit.token).toBe('tok-1');
    expect(kit.valaszok).toBeUndefined();                                                       // a pontszámot a core a rögzített válaszokból számolja
    expect(kit.kulcs).toMatch(/^[A-Za-z0-9_-]{8,80}$/);
    expect(esemeny).toHaveBeenCalledTimes(1);
    expect(esemeny).toHaveBeenCalledWith('kviz_eredmeny', 'M03/Forrás.md', { kviz: 'KVIZ-20261004-203015', pont: 3 });
    expect(kviz(k).getByText('Nincs mit átnézni: minden válasz helyes volt, és biztos voltál benne.')).toBeTruthy();
  });

  it('billentyűvel: 2 választ, Enter ellenőriz, Enter lép tovább; a blokkon kívüli billentyű nem hat', async () => {
    const k = await indit();
    const blokk = k.querySelector<HTMLElement>('.kviz')!;
    await fireEvent.keyDown(blokk, { key: '2' });
    expect(kviz(k).getAllByRole('radio').filter((r) => r.getAttribute('aria-checked') === 'true')).toHaveLength(1);
    await fireEvent.keyDown(blokk, { key: 'Enter' });
    await waitFor(() => expect(k.querySelector('.kviz-visszajelzes')).not.toBeNull());
    await fireEvent.keyDown(blokk, { key: 'Enter' });
    await waitFor(() => expect(k.querySelector('.kviz-al')!.textContent).toContain('2/3. kérdés'));
    await fireEvent.keyDown(document.body, { key: 'n' });                                        // a blokkon kívül: semmi
    expect(k.querySelector('.kviz-visszajelzes')).toBeNull();
  });

  it('a „nem tudom” válasz nélkül megy; a választás nélküli ellenőrzés tiltva', async () => {
    const k = await indit();
    expect((kviz(k).getByRole('button', { name: 'Ellenőrzés — biztos vagyok' }) as HTMLButtonElement).disabled).toBe(true);
    await fireEvent.click(kviz(k).getByRole('button', { name: 'Nem tudom' }));
    await waitFor(() => expect(k.querySelector('.kviz-visszajelzes')).not.toBeNull());
    expect(kerelmek.find((r) => r.ut === '/api/kviz/megoldas')!.torzs.valasz).toBeNull();
    expect(k.querySelector('.kviz-itelet')!.textContent).toBe('Ez lett volna a helyes');
  });

  it('a kilépés megerősítése beágyazott, nem böngésző-párbeszéd', async () => {
    const k = await indit();
    await valaszt(k, 'A');
    await fireEvent.click(kviz(k).getByRole('button', { name: 'Csak tippeltem' }));
    await waitFor(() => expect(k.querySelector('.kviz-visszajelzes')).not.toBeNull());
    const confirm = vi.fn();
    vi.stubGlobal('confirm', confirm);
    await fireEvent.click(kviz(k).getByRole('button', { name: 'Kilépés' }));
    expect(kviz(k).getByText(/Abbahagyod\? 1 megválaszolt kérdés számít\./)).toBeTruthy();
    await fireEvent.click(kviz(k).getByRole('button', { name: 'Folytatom' }));
    expect(kviz(k).queryByText(/Abbahagyod/)).toBeNull();
    await fireEvent.click(kviz(k).getByRole('button', { name: 'Kilépés' }));
    await fireEvent.click(kviz(k).getByRole('button', { name: 'Kiértékelés most' }));
    await waitFor(() => expect(k.querySelector('.kviz-pontszam')).not.toBeNull());
    expect(confirm).not.toHaveBeenCalled();
    expect(kerelmek.filter((r) => r.ut === '/api/kviz/megoldas')).toHaveLength(1);
    expect(kerelmek.find((r) => r.ut === '/api/kviz/kitoltes')!.torzs.token).toBe('tok-1');
  });

  it('a „hibás a kérdés?” jelölés a core-nak megy, a gomb átvált', async () => {
    const k = await indit();
    await valaszt(k, 'C');
    await fireEvent.click(kviz(k).getByRole('button', { name: 'Ellenőrzés — biztos vagyok' }));
    await waitFor(() => expect(k.querySelector('.kviz-visszajelzes')).not.toBeNull());
    await fireEvent.click(kviz(k).getByRole('button', { name: 'Hibás a kérdés?' }));
    await waitFor(() => expect(kviz(k).getByRole('button', { name: 'Hibásnak jelölve — visszavonás' })).toBeTruthy());
    expect(kerelmek.find((r) => r.ut === '/api/kviz/jelol')!.torzs).toEqual({ ut: KVIZ_UT, token: 'tok-1', kerdes: 'k1', hibas: true });
  });

  it('a betöltési hiba a blokkban, újrapróbával', async () => {
    vi.stubGlobal('fetch', async (url: string) => {
      const u = new URL(url, 'http://127.0.0.1/');
      if (u.pathname === '/api/vault/beagyazas') return json({ tipus: 'jegyzet', ut: KVIZ_UT, szoveg: '' });
      return json({ hiba: 'nem kitölthető kvízjegyzet: nincs benne érvényes kérdés' }, 400);
    });
    const k = rajzol('![[Kvíz]]');
    await vi.waitFor(() => expect(k.querySelector('.kviz-hiba')).not.toBeNull());
    expect(k.querySelector('.kviz-hiba')!.textContent).toContain('nem kitölthető kvízjegyzet');
    expect(kviz(k).getByRole('button', { name: 'Újra' })).toBeTruthy();
  });
});

describe('az élmény a Csend és elérés szerint', () => {
  it('a kezdőlapon csak a fejléc és egy gomb van (a kérdések nem látszanak)', async () => {
    const k = rajzol('![[Kvíz]]');
    await vi.waitFor(() => expect(k.querySelector('.kviz-gomb.elsodleges')).not.toBeNull());
    expect(k.querySelectorAll('.kviz-opcio')).toHaveLength(0);
    expect(k.querySelector('.kviz-kerdes')).toBeNull();
    expect(screen.queryByText('A-válasz 1')).toBeNull();
  });
});
