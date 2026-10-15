// A tulajdonság-javaslatok (gépelés közbeni kiegészítés): a közös logika (`javaslat.ts`), a javaslatos mező (combobox +
// listbox, aria-activedescendant, ↑↓/↩/Tab/Esc), a tulajdonság-panel bekötése (címke, link a core link-céljával és a
// horgony megtartásával, Status-lista, új tulajdonság neve és típusa, séma-jelölés), és a nyers frontmatter kiegészítése
// a szerkesztőben (`fmKiegeszites.ts`).

import { CompletionContext, type Completion } from '@codemirror/autocomplete';
import { ensureSyntaxTree } from '@codemirror/language';
import { EditorState, Text } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { FajlInfo } from '../src/lib/vault/fajlok.svelte';
import { bovitmenyek } from '../src/szerkeszto/beallitas';
import type { Csere } from '../src/szerkeszto/dokumentum/kulonbseg';
import { fmForras, fmHely, yamlSkalar } from '../src/szerkeszto/tulajdonsagok/fmKiegeszites';
import { JavaslatTar, NINCS_A_SEMABAN, ertekLista, javaslatFajta, kulcsLista, linkLekerdezes, linkLista } from '../src/szerkeszto/tulajdonsagok/javaslat';
import Tulajdonsagok from '../src/szerkeszto/tulajdonsagok/Tulajdonsagok.svelte';
import type { Elemzes, ErtekJavaslat, KulcsJavaslat, ModositEredmeny, Sema, TulajdonsagApi } from '../src/szerkeszto/tulajdonsagok/tipusok';

const f = (ut: string, tipus: FajlInfo['tipus'] = 'md', mtime = 1): FajlInfo => ({ ut, tipus, meret: 1, mtime });
const FAJLOK: FajlInfo[] = [
  f('Matek/Mértani sorozat.md', 'md', 50),
  f('Gyümölcs/Körte.md', 'md', 40),
  f('Könyvek/11 - Digitális Kultúra.pdf', 'pdf', 30),
  f('D01 - Szöveg/D01 - Szöveg.canvas', 'canvas', 20),
  f('Gyümölcs/Alma.md', 'md', 10),
];
const FORRAS = { fajlok: () => FAJLOK, legutobbi: () => ['Gyümölcs/Alma.md'] };
const LINKCEL: Record<string, string> = { 'Gyümölcs/Körte.md': 'Körte', 'Könyvek/11 - Digitális Kultúra.pdf': '11 - Digitális Kultúra.pdf' };
const linkCel = vi.fn(async (ut: string) => LINKCEL[ut] ?? ut.replace(/\.md$/, ''));

const CIMKEK: ErtekJavaslat[] = [
  { ertek: 'Physics', db: 40, sema: true },
  { ertek: 'Mathematics', db: 30, sema: true },
  { ertek: 'Napló', db: 0, sema: true },
  { ertek: 'Fizika/Optika', db: 2, sema: false },
];
const STATUSOK: ErtekJavaslat[] = [
  { ertek: 'Completed', db: 9, sema: true },
  { ertek: 'In progress', db: 4, sema: true },
  { ertek: 'Review', db: 1, sema: true },
];
const KULCSOK: KulcsJavaslat[] = [
  { kulcs: 'Tags', db: 50, sema: true, tipus: 'tags' },
  { kulcs: 'Source', db: 40, sema: true, tipus: null },
  { kulcs: 'Status', db: 30, sema: true, tipus: null },
  { kulcs: 'NN', db: 20, sema: true, tipus: null },
  { kulcs: 'Canvas', db: 20, sema: true, tipus: null },
  { kulcs: 'Szerző', db: 3, sema: false, tipus: 'text' },
];
const ERTEKEK: Record<string, ErtekJavaslat[]> = {
  Tags: CIMKEK,
  Status: STATUSOK,
  Szerző: [
    { ertek: 'Arany János', db: 2, sema: null },
    { ertek: 'Petőfi Sándor', db: 1, sema: null },
  ],
};

const alTar = () => ({ kulcsok: async () => KULCSOK, ertekek: async (_ut: string, k: string) => ERTEKEK[k] ?? [] });

afterEach(() => {
  cleanup();
  document.body.textContent = '';
});

// ---------------------------------------------------------------------- a közös logika

describe('javaslat.ts', () => {
  it('érték: üresen minden (a meglévő nélkül), gépelve ékezet- és elírástűrő fuzzy, a nem értékkészletbeli jelölve', () => {
    const l = ertekLista(CIMKEK, '', ['Mathematics']);
    expect(l.elemek.map((e) => e.nev)).toEqual(['Physics', 'Napló', 'Fizika/Optika']);
    expect(l.eros).toBe(false);
    expect(l.elemek.find((e) => e.nev === 'Fizika/Optika')!.megjegyzes).toBe(NINCS_A_SEMABAN);
    expect(l.elemek[0].jelzo).toBe('40');
    const g = ertekLista(CIMKEK, 'naplo');
    expect(g.elemek[0].nev).toBe('Napló');
    expect(g.eros).toBe(true);
    expect(g.elemek[0].kiemeles).toBeTruthy();
    // gyenge (részsorozat-) találat: nincs alapból kiemelt elem, az ↩ a gépelt szöveget hagyja
    expect(ertekLista(CIMKEK, 'phcs').eros).toBe(false);
  });

  it('kulcs: a jegyzetben álló kulcs kimarad, a séma-kulcs jelölve', () => {
    const l = kulcsLista(KULCSOK, 'S', ['Source']);
    expect(l.elemek.map((e) => e.nev)).not.toContain('Source');
    expect(l.elemek.find((e) => e.nev === 'Status')!.jelzo).toBe('séma');
    expect(kulcsLista(KULCSOK, 'szer').elemek[0].nev).toBe('Szerző');
  });

  it('a mező fajtája: a séma link-kulcsa és a csupa wikilink értékű mező link', () => {
    expect(javaslatFajta('Source')).toBe('link');
    expect(javaslatFajta('Canvas')).toBe('link');
    expect(javaslatFajta('Tags')).toBe('ertek');
    expect(javaslatFajta('Kapcsolódik', ['[[A]]'])).toBe('link');
    expect(javaslatFajta('Szerző', 'Arany')).toBe('ertek');
  });

  it('link-lekérdezés: az idézőjel és a zárójelek lemaradnak, a horgony és az alias marad', () => {
    expect(linkLekerdezes('"[[Digit#page=12]]"')).toEqual({ cel: 'Digit', horgony: '#page=12', alias: '' });
    expect(linkLekerdezes('Körte|gyümölcs')).toEqual({ cel: 'Körte', horgony: '', alias: '|gyümölcs' });
    expect(linkLekerdezes('![[Alm')).toEqual({ cel: 'Alm', horgony: '', alias: '' });
  });

  it('link: a cél a core link-céljából, a PDF oldalszáma megmarad; a mezőben álló link kimarad, ugyanannak a PDF-nek másik oldala nem', async () => {
    const l = linkLista(FORRAS, 'digit#page=19', 'Source', 'J.md', linkCel, ['[[11 - Digitális Kultúra.pdf#page=18]]']);
    expect(l.elemek[0].nev).toBe('11 - Digitális Kultúra.pdf');
    expect(await l.elemek[0].feloldas!()).toBe('[[11 - Digitális Kultúra.pdf#page=19]]');
    expect(linkCel).toHaveBeenCalledWith('Könyvek/11 - Digitális Kultúra.pdf', 'J.md');
    const ugyanaz = linkLista(FORRAS, 'digit#page=18', 'Source', 'J.md', linkCel, ['[[11 - Digitális Kultúra.pdf#page=18]]']);
    expect(ugyanaz.elemek.map((e) => e.nev)).not.toContain('11 - Digitális Kultúra.pdf');
    // a core nem érhető el: a fájlnév a tartalék
    const hibas = linkLista(FORRAS, 'kort', 'NN', 'J.md', async () => Promise.reject(new Error('le')));
    expect(await hibas.elemek[0].feloldas!()).toBe('[[Körte]]');
  });

  it('link: üresen a legutóbbiak, utána a mező típusa (Canvas: a vászon elöl); a saját jegyzet nem javaslat', () => {
    const l = linkLista(FORRAS, '', 'Canvas', 'Matek/Mértani sorozat.md', linkCel);
    expect(l.elemek[0].nev).toBe('Alma');
    expect(l.elemek[1].nev).toBe('D01 - Szöveg.canvas');
    expect(l.elemek.map((e) => e.nev)).not.toContain('Mértani sorozat');
  });

  it('a tár: a lista gyorsítótárazva, lejárat után újra; a hibás válasz nem marad benne', async () => {
    let ido = 0;
    const kulcsok = vi.fn(async () => ({ kulcsok: KULCSOK, index_kesz: true }));
    const ertekek = vi.fn().mockRejectedValueOnce(new Error('503')).mockResolvedValue({ kulcs: 'Tags', ertekkeszlet: true, ertekek: CIMKEK, index_kesz: true });
    const tar = new JavaslatTar({ kulcsok, ertekek }, () => ido);
    await tar.kulcsok('J.md');
    await tar.kulcsok('J.md');
    expect(kulcsok).toHaveBeenCalledTimes(1);
    ido = 20_000;
    await tar.kulcsok('J.md');
    expect(kulcsok).toHaveBeenCalledTimes(2);
    await expect(tar.ertekek('J.md', 'Tags')).rejects.toThrow('503');
    expect(await tar.ertekek('J.md', 'Tags')).toEqual(CIMKEK);
    expect(await new JavaslatTar({}).ertekek('J.md', 'Tags')).toEqual([]);
  });
});

// ---------------------------------------------------------------------- a panel

const FM = '---\nTags:\n  - Mathematics\nSource:\n  - "[[Alma]]"\nStatus: Completed\nCanvas:\nSzerző: Arany\n---\n\n# Cím\n';
const ELEMZES: Elemzes = {
  van: true,
  hiba: null,
  osztaly: 'normal',
  kulcsok: ['Tags', 'Source', 'Status', 'Canvas', 'Szerző'],
  problemak: [],
  tulajdonsagok: [
    { kulcs: 'Tags', tipus: 'tags', ertek: ['Mathematics'], ervenyes: true },
    { kulcs: 'Source', tipus: 'multitext', ertek: ['[[Alma]]'], ervenyes: true },
    { kulcs: 'Status', tipus: 'text', ertek: 'Completed', ervenyes: true },
    { kulcs: 'Canvas', tipus: 'text', ertek: null, ervenyes: true },
    { kulcs: 'Szerző', tipus: 'text', ertek: 'Arany', ervenyes: true },
  ],
};
const SEMA: Sema = {
  mezosorrend: ['Tags', 'Source', 'Status', 'NN', 'Canvas'],
  extra_kulcsok: ['version'],
  tags_ertekkeszlet: ['Mathematics', 'Physics', 'Napló'],
  status_ertekkeszlet: ['Completed', 'In progress', 'Review'],
  status_gazdai: true,
  osztaly: { nev: 'normal', mezosorrend: ['Tags', 'Source', 'Status', 'NN', 'Canvas'], ertekek: true, sema_nelkul: false },
};
const OK: ModositEredmeny = { ok: true, fm_uj: FM.slice(0, FM.indexOf('---\n\n') + 4), megerositheto: false, valtozas: false, problemak: [] };

let api: TulajdonsagApi & { modosit: ReturnType<typeof vi.fn>; ertekek: ReturnType<typeof vi.fn> };

beforeEach(() => {
  linkCel.mockClear();
  api = {
    elemez: vi.fn(async () => ELEMZES),
    sema: vi.fn(async () => SEMA),
    modosit: vi.fn(async () => OK),
    kulcsok: vi.fn(async () => ({ kulcsok: KULCSOK, index_kesz: true })),
    ertekek: vi.fn(async (_ut: string, k: string) => ({ kulcs: k, ertekkeszlet: k === 'Tags' || k === 'Status', ertekek: ERTEKEK[k] ?? [], index_kesz: true })),
  } as never;
});

function felallit(irhato = true) {
  render(Tulajdonsagok, {
    props: { ut: 'J.md', szoveg: () => Text.of(FM.split('\n')), alkalmaz: vi.fn<(c: Csere) => void>(), valtozat: 0, irhato, api, kiegeszites: FORRAS, linkCel },
  });
}

async function gepel(cimke: string, szoveg: string): Promise<HTMLInputElement> {
  const mezo = (await screen.findByLabelText(cimke)) as HTMLInputElement;
  mezo.focus();
  await fireEvent.input(mezo, { target: { value: szoveg } });
  return mezo;
}

const opciok = (cimke: string) => screen.queryByRole('listbox', { name: `${cimke}: javaslatok` });
const nevek = (cimke: string) => [...(opciok(cimke)?.querySelectorAll('[role="option"]') ?? [])].map((o) => o.querySelector('.nt-menu-nev')!.textContent);

describe('a javaslatos mező a panelen', () => {
  it('címke: gépelésre a vault címkéi jönnek (a meglévő nélkül), a combobox jelöli az aktív sort; ↩ felveszi', async () => {
    felallit();
    const mezo = await gepel('Tags: új elem', 'phy');
    await waitFor(() => expect(nevek('Tags: új elem')).toEqual(['Physics']));
    expect(mezo.getAttribute('role')).toBe('combobox');
    expect(mezo.getAttribute('aria-expanded')).toBe('true');
    const aktiv = mezo.getAttribute('aria-activedescendant')!;
    expect(document.getElementById(aktiv)!.getAttribute('aria-selected')).toBe('true');
    expect(api.ertekek).toHaveBeenCalledWith('J.md', 'Tags');
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    await waitFor(() => expect(api.modosit).toHaveBeenCalled());
    expect(api.modosit.mock.calls[0][2]).toEqual({ muvelet: 'beallit', kulcs: 'Tags', ertek: ['Mathematics', 'Physics'], tipus: 'tags' });
  });

  it('a nem értékkészletbeli címke jelölve; Esc bezárja a listát, és az ↩ a gépelt szöveget veszi', async () => {
    felallit();
    const mezo = await gepel('Tags: új elem', 'Optika');
    await waitFor(() => expect(nevek('Tags: új elem')).toEqual(['Fizika/Optika']));
    expect(opciok('Tags: új elem')!.textContent).toContain(NINCS_A_SEMABAN);
    await fireEvent.keyDown(mezo, { key: 'Escape' });
    expect(mezo.getAttribute('aria-expanded')).toBe('false');
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    await waitFor(() => expect(api.modosit).toHaveBeenCalled());
    expect(api.modosit.mock.calls[0][2].ertek).toEqual(['Mathematics', 'Optika']);
  });

  it('↓ lép, Tab a kiemeltet veszi fel; egérrel is választható', async () => {
    felallit();
    const mezo = await gepel('Tags: új elem', 'a');
    await waitFor(() => expect(nevek('Tags: új elem').length).toBeGreaterThan(1));
    await fireEvent.keyDown(mezo, { key: 'ArrowDown' });
    const masodik = nevek('Tags: új elem')[1];
    await fireEvent.keyDown(mezo, { key: 'Tab' });
    await waitFor(() => expect(api.modosit).toHaveBeenCalled());
    expect(api.modosit.mock.calls[0][2].ertek).toEqual(['Mathematics', masodik]);
  });

  it('Source: a fájl-javaslat a core link-célját írja be, a gépelt oldalszám megmarad', async () => {
    felallit();
    const mezo = await gepel('Source: új elem', 'digit#page=12');
    await waitFor(() => expect(nevek('Source: új elem')[0]).toBe('11 - Digitális Kultúra.pdf'));
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    await waitFor(() => expect(api.modosit).toHaveBeenCalled());
    expect(linkCel).toHaveBeenCalledWith('Könyvek/11 - Digitális Kultúra.pdf', 'J.md');
    expect(api.modosit.mock.calls[0][2].ertek).toEqual(['[[Alma]]', '[[11 - Digitális Kultúra.pdf#page=12]]']);
  });

  it('Canvas (üres skalár link-mező): a vászon-javaslat linkként kerül be', async () => {
    felallit();
    const mezo = await gepel('Canvas', 'szöveg');
    await waitFor(() => expect(nevek('Canvas')[0]).toBe('D01 - Szöveg.canvas'));
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    await waitFor(() => expect(api.modosit).toHaveBeenCalled());
    expect(api.modosit.mock.calls[0][2]).toEqual({ muvelet: 'beallit', kulcs: 'Canvas', ertek: '[[D01 - Szöveg/D01 - Szöveg.canvas]]', tipus: 'text' });
  });

  it('Status: fókuszra a teljes engedett lista nyílik (mint egy legördülő), a választás a core-on át íródik', async () => {
    felallit();
    const mezo = (await screen.findByLabelText('Status')) as HTMLInputElement;
    expect(mezo.value).toBe('Completed');
    mezo.focus();
    await fireEvent.focus(mezo);
    await waitFor(() => expect(nevek('Status')).toEqual(['Completed', 'In progress', 'Review']));
    const opcio = opciok('Status')!.querySelectorAll('[role="option"]')[2] as HTMLElement;
    await fireEvent.click(opcio);
    await waitFor(() => expect(api.modosit).toHaveBeenCalled());
    expect(api.modosit.mock.calls[0][2]).toEqual({ muvelet: 'beallit', kulcs: 'Status', ertek: 'Review', tipus: 'text' });
  });

  it('más szöveges kulcs: a vaultban használt értékei', async () => {
    felallit();
    await gepel('Szerző', 'pet');
    await waitFor(() => expect(nevek('Szerző')).toEqual(['Petőfi Sándor']));
  });

  it('írásvédett mező nem javasol', async () => {
    felallit(false);
    const mezo = (await screen.findByLabelText('Status')) as HTMLInputElement;
    mezo.focus();
    await fireEvent.focus(mezo);
    await new Promise((r) => setTimeout(r, 100));
    expect(mezo.getAttribute('aria-expanded')).toBe('false');
    expect(api.ertekek).not.toHaveBeenCalled();
  });

  it('új tulajdonság: a név a séma- és a vault-kulcsokból (a meglévő nélkül), a választott kulcs a típusát is hozza', async () => {
    felallit();
    await fireEvent.click(await screen.findByRole('button', { name: /Új tulajdonság/ }));
    const nev = await gepel('Új tulajdonság neve', 'n');
    await waitFor(() => expect(nevek('Új tulajdonság neve')).toContain('NN'));
    expect(nevek('Új tulajdonság neve')).not.toContain('Canvas'); // a jegyzetben már áll
    const i = nevek('Új tulajdonság neve').indexOf('NN');
    await fireEvent.click(opciok('Új tulajdonság neve')!.querySelectorAll('[role="option"]')[i] as HTMLElement);
    expect(nev.value).toBe('NN');
    expect((screen.getByLabelText('Típus') as HTMLSelectElement).value).toBe('multitext');
    // a lista-érték javaslata az utolsó (vessző utáni) elemre szól, a link a core link-céljával
    const ertek = await gepel('Érték', '[[Alma]], kör');
    await waitFor(() => expect(nevek('Érték')[0]).toBe('Körte'));
    await fireEvent.keyDown(ertek, { key: 'Enter' });
    await waitFor(() => expect(ertek.value).toBe('[[Alma]], [[Körte]], '));
  });
});

// ---------------------------------------------------------------------- a nyers frontmatter a szerkesztőben

const NYERS = '---\nTags:\n  - Mathematics\n  - Ph\nSource:\n  - "[[Digit#page=3]]"\nStatus: Rev\nCanvas: \nSze\n---\n\n# Cím\n';

function allapot(doc: string, kurzor: number, csakOlvashato = false): EditorState {
  const s = EditorState.create({
    doc,
    selection: { anchor: kurzor },
    extensions: bovitmenyek({ mod: 'forras', csakOlvashato, ut: 'J.md', cimke: 'próba', kiegeszites: FORRAS }),
  });
  ensureSyntaxTree(s, s.doc.length, 5000);
  return s;
}

const poz = (doc: string, minta: string) => doc.indexOf(minta) + minta.length;

async function javaslatok(doc: string, kurzor: number, explicit = false) {
  const s = allapot(doc, kurzor);
  return fmForras({ tar: alTar(), linkCel })(new CompletionContext(s, kurzor, explicit));
}

function alkalmaz(doc: string, kurzor: number, c: Completion, from: number, to = kurzor): EditorView {
  const v = new EditorView({ state: allapot(doc, kurzor), parent: document.body });
  (c.apply as (v: EditorView, c: Completion, f: number, t: number) => void)(v, c, from, to);
  return v;
}

describe('a nyers frontmatter kiegészítése', () => {
  it('a hely: lista-elem a gazda kulccsal, kulcs-hely, érték a sorban; a blokkon kívül és a záró soron semmi', () => {
    const s = allapot(NYERS, poz(NYERS, '  - Ph'));
    expect(fmHely(s, poz(NYERS, '  - Ph'))).toMatchObject({ fajta: 'ertek', kulcs: 'Tags', q: 'Ph', lista: true, tarsak: ['Mathematics'] });
    expect(fmHely(s, poz(NYERS, 'Status: Rev'))).toMatchObject({ fajta: 'ertek', kulcs: 'Status', q: 'Rev', lista: false });
    expect(fmHely(s, poz(NYERS, '\nSze'))).toMatchObject({ fajta: 'kulcs', q: 'Sze', kulcsok: ['Tags', 'Source', 'Status', 'Canvas'] });
    expect(fmHely(s, poz(NYERS, '# Cím'))).toBeNull();
    expect(fmHely(s, NYERS.indexOf('---\n\n') + 2)).toBeNull();
    const h = fmHely(s, poz(NYERS, '"[[Digit'));
    expect(h).toMatchObject({ fajta: 'ertek', kulcs: 'Source', q: '"[[Digit' });
    expect(NYERS.slice(h!.from, (h as { to: number }).to)).toBe('"[[Digit'); // a `#page=3]]"` a kurzor után nem a záró pár
  });

  it('címke a lista-elemen: a séma és a vault címkéi, a már álló elem nélkül; a beírás YAML-hű', async () => {
    const k = poz(NYERS, '  - Ph');
    const r = (await javaslatok(NYERS, k))!;
    expect(r.options.map((o) => o.label)).toEqual(['Physics']);
    expect(r.filter).toBe(false);
    const v = alkalmaz(NYERS, k, r.options[0], r.from, r.to);
    expect(v.state.doc.toString()).toContain('  - Mathematics\n  - Physics\n');
    v.destroy();
    expect(yamlSkalar('Physics')).toBe('Physics');
    expect(yamlSkalar('#todo')).toBe('"#todo"');
    expect(yamlSkalar('12')).toBe('"12"');
    expect(yamlSkalar('a: b')).toBe('"a: b"');
  });

  it('Status: az engedett értékek; a nem értékkészletbeli jelölés a részletben', async () => {
    const r = (await javaslatok(NYERS, poz(NYERS, 'Status: Rev')))!;
    expect(r.options[0].label).toBe('Review');
    const egysoros = '---\nTags: opt\n---\n';
    const t = (await javaslatok(egysoros, poz(egysoros, 'Tags: opt')))!;
    expect(t.options[0].label).toBe('Fizika/Optika');
    expect(t.options[0].detail).toContain(NINCS_A_SEMABAN);
  });

  it('kulcs-hely: a hiányzó kulcsok, a beírás `Kulcs: `', async () => {
    const k = poz(NYERS, '\nSze');
    const r = (await javaslatok(NYERS, k))!;
    expect(r.options[0].label).toBe('Szerző');
    const v = alkalmaz(NYERS, k, r.options[0], r.from, r.to);
    expect(v.state.doc.toString()).toContain('\nSzerző: \n---');
    v.destroy();
  });

  it('link-kulcs: a fájl a core link-céljával, idézve, a gépelt horgony megmarad', async () => {
    const doc = '---\nSource:\n  - digit#page=7\n---\n';
    const k = poz(doc, 'digit#page=7');
    const r = (await javaslatok(doc, k))!;
    expect(r.options[0].label).toBe('11 - Digitális Kultúra.pdf');
    const v = alkalmaz(doc, k, r.options[0], r.from, r.to);
    await vi.waitFor(() => expect(v.state.doc.toString()).toBe('---\nSource:\n  - "[[11 - Digitális Kultúra.pdf#page=7]]"\n---\n'));
    v.destroy();
  });

  it('a `[[` pár és a záró idézőjel a cserélt tartományba tartozik', async () => {
    const doc = '---\nNN:\n  - "[[kör]]"\n---\n';
    const k = poz(doc, '[[kör');
    const r = (await javaslatok(doc, k))!;
    expect(r.options[0].label).toBe('Körte');
    const v = alkalmaz(doc, k, r.options[0], r.from, r.to);
    await vi.waitFor(() => expect(v.state.doc.toString()).toBe('---\nNN:\n  - "[[Körte]]"\n---\n'));
    v.destroy();
  });

  it('a törzsben gépelve a forrás nem kér listát, és a hely-döntés olcsó (5000 soros jegyzet)', async () => {
    const doc = `---\nTags:\n  - Physics\n---\n${Array.from({ length: 5000 }, (_, i) => `Sor ${i} Phy`).join('\n')}\n`;
    const s = allapot(doc, doc.length - 2);
    const tar = { kulcsok: vi.fn(async () => KULCSOK), ertekek: vi.fn(async () => CIMKEK) };
    expect(await fmForras({ tar, linkCel })(new CompletionContext(s, doc.length - 2, false))).toBeNull();
    expect(tar.kulcsok).not.toHaveBeenCalled();
    expect(tar.ertekek).not.toHaveBeenCalled();
    const t0 = performance.now();
    for (let i = 0; i < 1000; i++) fmHely(s, doc.length - 2 - i);
    expect(performance.now() - t0).toBeLessThan(1000); // ~µs/hívás; a bő határ a terhelt gépnek szól
  });

  it('magától csak gépelt szövegre nyílik; csak olvasható dokumentumban és a blokkon kívül nincs', async () => {
    const doc = '---\nTags:\n  - \n---\n# Ph\n';
    expect(await javaslatok(doc, poz(doc, '  - '))).toBeNull();
    expect((await javaslatok(doc, poz(doc, '  - '), true))!.options.length).toBeGreaterThan(0);
    expect(await javaslatok(doc, poz(doc, '# Ph'))).toBeNull();
    const s = allapot(NYERS, poz(NYERS, '  - Ph'), true);
    expect(await fmForras({ tar: alTar(), linkCel })(new CompletionContext(s, poz(NYERS, '  - Ph'), false))).toBeNull();
  });
});
