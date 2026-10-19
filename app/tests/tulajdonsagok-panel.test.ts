// A tulajdonság-panel (C11b): a mezők típus szerint, a módosítás a core-on át és a dokumentumba, a séma-sértés
// megerősítése („Mégis beírom” / „Mégse”; nem csendben), az elutasított érték, az írásvédett állapot, az új tulajdonság.

import { Text } from '@codemirror/state';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest';
import type { Csere } from '../src/szerkeszto/dokumentum/kulonbseg';
import Tulajdonsagok from '../src/szerkeszto/tulajdonsagok/Tulajdonsagok.svelte';
import type { Elemzes, ModositEredmeny, Sema, TulajdonsagApi } from '../src/szerkeszto/tulajdonsagok/tipusok';

const FM = '---\nTags:\n  - Mathematics\nSource:\n  - "[[Alma]]"\nStatus: Completed\nCanvas: "[[Vászon.canvas]]"\nPont: 3\nHatáridő: 2026-10-30\nKész: false\nMegjegyzés: szia\n---\n\n# Cím\n';

const ELEMZES: Elemzes = {
  van: true,
  hiba: null,
  osztaly: 'normal',
  kulcsok: ['Tags', 'Source', 'Status', 'Canvas', 'Pont', 'Határidő', 'Kész', 'Megjegyzés'],
  problemak: [{ kod: 'ismeretlen_kulcs', szint: 'sertes', kulcs: 'Pont', ertek: null, uzenet: 'A(z) „Pont” kulcs nincs a vault sémájában.' }],
  tulajdonsagok: [
    { kulcs: 'Tags', tipus: 'tags', ertek: ['Mathematics'], ervenyes: true },
    { kulcs: 'Source', tipus: 'multitext', ertek: ['[[Alma]]'], ervenyes: true },
    { kulcs: 'Status', tipus: 'text', ertek: 'Completed', ervenyes: true },
    { kulcs: 'Canvas', tipus: 'text', ertek: '[[Vászon.canvas]]', ervenyes: true },
    { kulcs: 'Pont', tipus: 'number', ertek: 3, ervenyes: true },
    { kulcs: 'Határidő', tipus: 'date', ertek: '2026-10-30', ervenyes: true },
    { kulcs: 'Kész', tipus: 'checkbox', ertek: false, ervenyes: true },
    { kulcs: 'Megjegyzés', tipus: 'text', ertek: 'szia', ervenyes: true },
  ],
};

const SEMA: Sema = {
  mezosorrend: ['Tags', 'Source', 'Status', 'NN', 'Canvas'],
  extra_kulcsok: ['version'],
  tags_ertekkeszlet: ['Mathematics'],
  status_ertekkeszlet: ['Completed', 'In progress', 'Review'],
  status_gazdai: true,
  osztaly: { nev: 'normal', mezosorrend: ['Tags', 'Source', 'Status', 'NN', 'Canvas'], ertekek: true, sema_nelkul: false },
};

const OK = (fm_uj: string): ModositEredmeny => ({ ok: true, fm_uj, megerositheto: false, valtozas: true, problemak: [] });

let api: TulajdonsagApi & { modosit: ReturnType<typeof vi.fn> };
let alkalmaz: Mock<(c: Csere) => void>;

function felallit(o: { irhato?: boolean } = {}) {
  alkalmaz = vi.fn<(c: Csere) => void>();
  render(Tulajdonsagok, {
    props: { ut: 'J.md', szoveg: () => Text.of(FM.split('\n')), alkalmaz, valtozat: 0, irhato: o.irhato ?? true, api },
  });
}

beforeEach(() => {
  api = {
    elemez: vi.fn(async () => ELEMZES),
    sema: vi.fn(async () => SEMA),
    modosit: vi.fn(async () => OK(FM.slice(0, FM.indexOf('---\n\n') + 4))),
  } as never;
});

afterEach(() => {
  cleanup();
  document.body.textContent = '';
});

describe('a mezők', () => {
  it('típus szerint: lista-chipek, link, Status-választó, szám, dátum, jelölő, szöveg', async () => {
    felallit();
    await screen.findByLabelText('Status');
    expect(screen.getByRole('list', { name: 'Tags' }).textContent).toContain('Mathematics');
    expect(screen.getByRole('button', { name: 'Alma' }).getAttribute('title')).toBe('[[Alma]]'); // link-chip (a nyers a tooltipben)
    // a Status az engedett értékek fókuszra nyíló javaslat-listája (combobox; a tartalma a tulajdonsag-javaslatok.test.ts-ben)
    const status = screen.getByLabelText('Status') as HTMLInputElement;
    expect(status.getAttribute('role')).toBe('combobox');
    expect(status.value).toBe('Completed');
    expect((screen.getByLabelText('Pont') as HTMLInputElement).value).toBe('3');
    expect((screen.getByLabelText('Határidő') as HTMLInputElement).type).toBe('date');
    expect((screen.getByLabelText('Határidő') as HTMLInputElement).value).toBe('2026-10-30');
    expect((screen.getByLabelText('Kész') as HTMLInputElement).type).toBe('checkbox');
    expect((screen.getByLabelText('Megjegyzés') as HTMLInputElement).value).toBe('szia');
    expect(screen.getByText('Vászon.canvas')).toBeTruthy();
  });

  it('a fejlécben a tulajdonságok száma és a séma-eltérések', async () => {
    felallit();
    await screen.findByLabelText('Status');
    expect(screen.getByText('8')).toBeTruthy();
    expect(screen.getByRole('button', { name: /1 eltérés/ })).toBeTruthy();
  });
});

describe('módosítás', () => {
  it('a Status választása a core-ból kapott új blokkot írja a dokumentumba (legkisebb csere)', async () => {
    const uj = FM.replace('Status: Completed', 'Status: Review');
    api.modosit.mockResolvedValue(OK(uj.slice(0, uj.indexOf('---\n\n') + 4)));
    felallit();
    const sel = (await screen.findByLabelText('Status')) as HTMLInputElement;
    await fireEvent.change(sel, { target: { value: 'Review' } });
    await waitFor(() => expect(alkalmaz).toHaveBeenCalledTimes(1));
    expect(api.modosit).toHaveBeenCalledWith('J.md', expect.stringMatching(/^---\n/), { muvelet: 'beallit', kulcs: 'Status', ertek: 'Review', tipus: 'text' }, false);
    const c = alkalmaz.mock.calls[0][0];
    expect(FM.slice(0, c.from) + c.insert + FM.slice(c.to)).toBe(uj);
    expect(c.insert).toBe('Review');
  });

  it('a lista elemének hozzáadása és eltávolítása', async () => {
    felallit();
    const mezo = (await screen.findByLabelText('Tags: új elem')) as HTMLInputElement;
    await fireEvent.input(mezo, { target: { value: 'Physics' } });
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    await waitFor(() => expect(api.modosit).toHaveBeenCalled());
    expect(api.modosit.mock.calls[0][2]).toEqual({ muvelet: 'beallit', kulcs: 'Tags', ertek: ['Mathematics', 'Physics'], tipus: 'tags' });
    api.modosit.mockClear();
    await fireEvent.click(screen.getByRole('button', { name: 'Mathematics eltávolítása' }));
    await waitFor(() => expect(api.modosit).toHaveBeenCalled());
    expect(api.modosit.mock.calls[0][2]).toMatchObject({ kulcs: 'Tags', ertek: [] });
  });

  it('a link-listába írt név wikilinkké alakul (Source)', async () => {
    felallit();
    const mezo = (await screen.findByLabelText('Source: új elem')) as HTMLInputElement;
    await fireEvent.input(mezo, { target: { value: 'Körte' } });
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    await waitFor(() => expect(api.modosit).toHaveBeenCalled());
    expect(api.modosit.mock.calls[0][2].ertek).toEqual(['[[Alma]]', '[[Körte]]']);
  });

  it('a szám, a jelölő és a törlés', async () => {
    felallit();
    const pont = (await screen.findByLabelText('Pont')) as HTMLInputElement;
    await fireEvent.change(pont, { target: { value: '4,5' } });
    await waitFor(() => expect(api.modosit).toHaveBeenCalled());
    expect(api.modosit.mock.calls[0][2]).toEqual({ muvelet: 'beallit', kulcs: 'Pont', ertek: 4.5, tipus: 'number' });
    api.modosit.mockClear();
    await fireEvent.click(screen.getByLabelText('Kész'));
    await waitFor(() => expect(api.modosit).toHaveBeenCalled());
    expect(api.modosit.mock.calls[0][2]).toEqual({ muvelet: 'beallit', kulcs: 'Kész', ertek: true, tipus: 'checkbox' });
    api.modosit.mockClear();
    await fireEvent.click(screen.getByRole('button', { name: 'Megjegyzés törlése' }));
    await waitFor(() => expect(api.modosit).toHaveBeenCalled());
    expect(api.modosit.mock.calls[0][2]).toEqual({ muvelet: 'torol', kulcs: 'Megjegyzés' });
  });

  it('érvénytelen szám: a core-hoz nem megy, a mező alatt magyar hiba', async () => {
    felallit();
    const pont = (await screen.findByLabelText('Pont')) as HTMLInputElement;
    await fireEvent.change(pont, { target: { value: 'sok' } });
    expect((await screen.findByRole('alert')).textContent).toContain('A szám alakja');
    expect(api.modosit).not.toHaveBeenCalled();
  });
});

describe('a séma (nem csendben)', () => {
  const SERTES: ModositEredmeny = {
    ok: false,
    fm_uj: null,
    megerositheto: true,
    valtozas: true,
    problemak: [{ kod: 'ertekkeszlet', szint: 'sertes', kulcs: 'Tags', ertek: 'Active-recall', uzenet: 'A(z) „Active-recall” címke nincs az értékkészletben.' }],
  };

  async function sertesKivalt() {
    api.modosit.mockResolvedValueOnce(SERTES);
    felallit();
    const mezo = (await screen.findByLabelText('Tags: új elem')) as HTMLInputElement;
    await fireEvent.input(mezo, { target: { value: 'Active-recall' } });
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    return screen.findByText(/nincs az értékkészletben/);
  }

  it('a sértés a mező alatt látszik, és a dokumentumba semmi nem kerül', async () => {
    await sertesKivalt();
    expect(screen.getByRole('button', { name: 'Mégis beírom' })).toBeTruthy();
    expect(alkalmaz).not.toHaveBeenCalled();
  });

  it('„Mégis beírom”: ugyanaz a módosítás megerősítéssel, és csak ekkor kerül a dokumentumba', async () => {
    await sertesKivalt();
    const uj = FM.replace('  - Mathematics\n', '  - Mathematics\n  - Active-recall\n');
    api.modosit.mockResolvedValueOnce(OK(uj.slice(0, uj.indexOf('---\n\n') + 4)));
    await fireEvent.click(screen.getByRole('button', { name: 'Mégis beírom' }));
    await waitFor(() => expect(alkalmaz).toHaveBeenCalledTimes(1));
    expect(api.modosit.mock.calls[1][3]).toBe(true);
    expect(api.modosit.mock.calls[1][2]).toMatchObject({ kulcs: 'Tags', ertek: ['Mathematics', 'Active-recall'] });
    await waitFor(() => expect(screen.queryByText(/nincs az értékkészletben/)).toBeNull());
  });

  it('„Mégse”: a módosítás elvetve, a dokumentum érintetlen', async () => {
    await sertesKivalt();
    await fireEvent.click(screen.getByRole('button', { name: 'Mégse' }));
    await waitFor(() => expect(screen.queryByText(/nincs az értékkészletben/)).toBeNull());
    expect(alkalmaz).not.toHaveBeenCalled();
    expect(api.modosit).toHaveBeenCalledTimes(1);
  });

  it('az elutasított érték (hiba szint) nem megerősíthető: csak a hiba látszik', async () => {
    api.modosit.mockResolvedValueOnce({
      ok: false, fm_uj: null, megerositheto: false, valtozas: false,
      problemak: [{ kod: 'status_gep', szint: 'hiba', kulcs: 'Status', ertek: null, uzenet: 'A Status mezőt csak a felhasználó tölti, gép nem.' }],
    });
    felallit();
    await fireEvent.change(await screen.findByLabelText('Status'), { target: { value: 'Review' } });
    expect((await screen.findByRole('alert')).textContent).toContain('csak a felhasználó tölti');
    expect(screen.queryByRole('button', { name: 'Mégis beírom' })).toBeNull();
    expect(alkalmaz).not.toHaveBeenCalled();
  });
});

describe('írásvédett és új tulajdonság', () => {
  it('írásvédett dokumentumnál nincs törlés, nincs új tulajdonság, a mezők nem szerkeszthetők', async () => {
    felallit({ irhato: false });
    await screen.findByLabelText('Status');
    expect(screen.queryByRole('button', { name: /törlése/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /Új tulajdonság/ })).toBeNull();
    expect((screen.getByLabelText('Status') as HTMLInputElement).readOnly).toBe(true);
    expect((screen.getByLabelText('Megjegyzés') as HTMLInputElement).readOnly).toBe(true);
    expect(screen.queryByLabelText('Tags: új elem')).toBeNull();
  });

  it('új tulajdonság: név, típus, érték → a core-nak a típussal; siker után az űrlap bezárul', async () => {
    felallit();
    await fireEvent.click(await screen.findByRole('button', { name: /Új tulajdonság/ }));
    await fireEvent.input(screen.getByLabelText('Új tulajdonság neve'), { target: { value: 'Pontszám' } });
    await fireEvent.change(screen.getByLabelText('Típus'), { target: { value: 'number' } });
    await fireEvent.input(screen.getByLabelText('Érték'), { target: { value: '12' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Hozzáadás' }));
    await waitFor(() => expect(api.modosit).toHaveBeenCalled());
    expect(api.modosit.mock.calls[0][2]).toEqual({ muvelet: 'beallit', kulcs: 'Pontszám', ertek: 12, tipus: 'number' });
    await waitFor(() => expect(screen.queryByLabelText('Új tulajdonság neve')).toBeNull());
  });

  it('új, séma-sértő kulcs (icon): a megerősítés az űrlap alatt jelenik meg', async () => {
    api.modosit.mockResolvedValueOnce({
      ok: false, fm_uj: null, megerositheto: true, valtozas: true,
      problemak: [{ kod: 'ismeretlen_kulcs', szint: 'sertes', kulcs: 'icon', ertek: null, uzenet: 'A(z) „icon” kulcs nincs a vault sémájában.' }],
    });
    felallit();
    await fireEvent.click(await screen.findByRole('button', { name: /Új tulajdonság/ }));
    await fireEvent.input(screen.getByLabelText('Új tulajdonság neve'), { target: { value: 'icon' } });
    await fireEvent.input(screen.getByLabelText('Érték'), { target: { value: '📘' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Hozzáadás' }));
    expect(await screen.findByText(/nincs a vault sémájában/)).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Mégis beírom' })).toBeTruthy();
    expect(alkalmaz).not.toHaveBeenCalled();
  });
});

describe('frontmatter nélkül', () => {
  it('az üres jegyzet csak hozzáadási műveletet kínál, diagnosztikai szövegblokk nélkül', async () => {
    api.elemez = vi.fn(async () => ({ van: false, tulajdonsagok: [], hiba: null, kulcsok: [], problemak: [], osztaly: 'normal' }));
    alkalmaz = vi.fn<(c: Csere) => void>();
    render(Tulajdonsagok, { props: { ut: 'J.md', szoveg: () => Text.of(['# Cím']), alkalmaz, valtozat: 0, irhato: true, api } });
    const hozzaad = await screen.findByRole('button', { name: 'Új tulajdonság' });
    await waitFor(() => expect(hozzaad.title).toContain('nincs frontmattere'));
    expect(screen.queryByText(/nincs frontmattere/)).toBeNull();
    expect(alkalmaz).not.toHaveBeenCalled();
    await fireEvent.click(hozzaad);
    expect(await screen.findByRole('combobox', { name: 'Új tulajdonság neve' })).toBeTruthy();
  });
});
