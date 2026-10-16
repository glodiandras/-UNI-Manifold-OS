import { Text } from '@codemirror/state';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiHiba } from '../src/lib/core/api';
import type { Csere } from '../src/szerkeszto/dokumentum/kulonbseg';
import Tulajdonsagok from '../src/szerkeszto/tulajdonsagok/Tulajdonsagok.svelte';
import { JavaslatTar } from '../src/szerkeszto/tulajdonsagok/javaslat';
import { TulajdonsagModell, tipusokValtoztak, tipusValtozas } from '../src/szerkeszto/tulajdonsagok/modell.svelte';
import { rogzitettTipus, type Elemzes, type TaroltTulajdonsagTipus, type TulajdonsagTipusok } from '../src/szerkeszto/tulajdonsagok/tipusok';

const FM = '---\nDue: tomorrow\nCount: 3\nTags: [Topic]\naliases: [Alpha]\n---\n\nBody';
let szam = 0;
function fixture() {
  let types: Record<string, string> = { Due: 'text', Count: 'number' };
  let rev = `fixture-${++szam}`;
  const elemez = vi.fn(async (): Promise<Elemzes> => ({ van: true, hiba: null, osztaly: 'normal', kulcsok: ['Due', 'Count', 'Tags', 'aliases'], problemak: [], tulajdonsagok: [
    { kulcs: 'Due', tipus: types.Due as TaroltTulajdonsagTipus, ertek: 'tomorrow', ervenyes: types.Due === 'text' },
    { kulcs: 'Count', tipus: 'number', ertek: 3, ervenyes: true },
    { kulcs: 'Tags', tipus: 'tags', ertek: ['Topic'], ervenyes: true },
    { kulcs: 'aliases', tipus: 'aliases', ertek: ['Alpha'], ervenyes: true },
  ] }));
  const api = {
    elemez,
    sema: vi.fn(async () => ({ mezosorrend: [], extra_kulcsok: [], tags_ertekkeszlet: [], status_ertekkeszlet: [], status_gazdai: false, osztaly: null })),
    modosit: vi.fn(async () => ({ ok: true, fm_uj: null, megerositheto: false, valtozas: false, problemak: [] })),
    tipusok: vi.fn(async (): Promise<TulajdonsagTipusok> => ({ rev, types: { ...types } })),
    tipusBeallit: vi.fn(async (kulcs: string, tipus: TaroltTulajdonsagTipus, kapott: string): Promise<TulajdonsagTipusok> => {
      if (kapott !== rev) throw new ApiHiba(409, 'Conflict');
      types = { ...types, [kulcs]: tipus };
      rev = `fixture-${++szam}`;
      return { rev, types: { ...types } };
    }),
  };
  const alkalmaz = vi.fn<(c: Csere) => void>();
  const doc = Text.of(FM.split('\n'));
  return { api, alkalmaz, doc, modell: new TulajdonsagModell('Synthetic.md', api, () => doc, alkalmaz) };
}
afterEach(() => { cleanup(); document.body.textContent = ''; });
beforeEach(() => { tipusValtozas.rev = null; });

describe('F11: explicit vault-szintű tulajdonságtípus a modellen', () => {
  it('csak types konfigurációt ment CAS-sal; a jegyzet szövege és write útja érintetlen', async () => {
    const f = fixture();
    await f.modell.frissit();
    await f.modell.tipusokatTolt();
    const rev = f.modell.tipusAdat!.rev;
    expect(await f.modell.tipusValt('Due', 'date')).toBe(true);
    expect(f.api.tipusBeallit).toHaveBeenCalledWith('Due', 'date', rev);
    expect(f.modell.elemzes?.tulajdonsagok[0]).toMatchObject({ tipus: 'date', ertek: 'tomorrow', ervenyes: false });
    expect(f.api.modosit).not.toHaveBeenCalled();
    expect(f.alkalmaz).not.toHaveBeenCalled();
    expect(f.doc.toString()).toBe(FM);
  });

  it('típusmódosítás minden javaslattárat érvénytelenít; ugyanazon rev WS-ismétlése no-op', async () => {
    const kulcsok = vi.fn(async () => ({ kulcsok: [], index_kesz: true }));
    const a = new JavaslatTar({ kulcsok });
    const b = new JavaslatTar({ kulcsok });
    await a.kulcsok('A.md'); await b.kulcsok('B.md');
    const elotte = tipusValtozas.verzio;
    tipusokValtoztak({ rev: 'external-change' });
    expect(tipusValtozas.verzio).toBe(elotte + 1);
    tipusokValtoztak({ rev: 'external-change' });
    expect(tipusValtozas.verzio).toBe(elotte + 1);
    await a.kulcsok('A.md'); await b.kulcsok('B.md');
    expect(kulcsok).toHaveBeenCalledTimes(4);
    tipusokValtoztak({});
    expect(tipusValtozas.rev).toBeNull();
    expect(tipusValtozas.verzio).toBe(elotte + 2);
    await a.kulcsok('A.md');
    expect(kulcsok).toHaveBeenCalledTimes(5);
  });

  it('readOnly, fenntartott kulcsok és fenntartott típusok nem indítanak POST-ot', async () => {
    const f = fixture();
    const m = new TulajdonsagModell('Readonly.md', f.api, () => f.doc, f.alkalmaz, () => false);
    await m.tipusokatTolt();
    expect(await m.tipusValt('Due', 'date')).toBe(false);
    await f.modell.tipusokatTolt();
    for (const k of ['Tags', 'tag', 'TAG', 'aliases', 'alias', 'ALIASES']) expect(await f.modell.tipusValt(k, 'text')).toBe(false);
    expect(await f.modell.tipusValt('Due', 'tags')).toBe(false);
    expect(await f.modell.tipusValt('Due', 'aliases')).toBe(false);
    expect(f.api.tipusBeallit).not.toHaveBeenCalled();
    expect(rogzitettTipus('Alias')).toBe('aliases');
  });

  it('CAS409 után nincs automatikus retry; friss rev újraolvasása kell', async () => {
    const f = fixture();
    await f.modell.tipusokatTolt();
    f.api.tipusBeallit.mockRejectedValueOnce(new ApiHiba(409, 'Conflict'));
    expect(await f.modell.tipusValt('Due', 'date')).toBe(false);
    expect(f.modell.tipusUtkozes).toBe(true);
    expect(await f.modell.tipusValt('Due', 'date')).toBe(false);
    expect(f.api.tipusBeallit).toHaveBeenCalledTimes(1);
    await f.modell.tipusokatTolt();
    expect(await f.modell.tipusValt('Due', 'date')).toBe(true);
  });
});

describe('F11: tulajdonságtípus ikon és választó', () => {
  function felallit(irhato = true) {
    const f = fixture();
    const nezet = render(Tulajdonsagok, { props: { ut: 'Synthetic.md', szoveg: () => f.doc, alkalmaz: f.alkalmaz, valtozat: 0, irhato, api: f.api } });
    return { ...f, nezet };
  }
  async function megnyit() {
    const f = felallit();
    await fireEvent.click(await screen.findByRole('button', { name: 'Due típusa: Szöveg' }));
    await screen.findByRole('combobox', { name: 'Tulajdonság típusa' });
    await waitFor(() => expect(f.api.tipusok).toHaveBeenCalled());
    return f;
  }

  it('ikonok típussal; megnyitás csak olvas, választás önmagában még nem ment', async () => {
    const f = await megnyit();
    expect(screen.getByRole('button', { name: 'Count típusa: Szám' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Tags típusa: Címkék' })).toBeTruthy();
    expect(screen.getByText('Az összes jegyzetre érvényes. A meglévő értékek megmaradnak.')).toBeTruthy();
    await fireEvent.change(screen.getByRole('combobox', { name: 'Tulajdonság típusa' }), { target: { value: 'date' } });
    expect(f.api.tipusBeallit).not.toHaveBeenCalled();
    expect(f.alkalmaz).not.toHaveBeenCalled();
  });

  it('Save után a nem kompatibilis dátum szövege láthatóan megmarad; jegyzetmódosítás nincs', async () => {
    const f = await megnyit();
    await fireEvent.change(screen.getByRole('combobox', { name: 'Tulajdonság típusa' }), { target: { value: 'date' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Típus mentése' }));
    await screen.findByRole('button', { name: 'Due típusa: Dátum' });
    expect(screen.getByText('tomorrow')).toBeTruthy();
    expect(screen.getByText('A meglévő érték ehhez a típushoz nem érvényes; a forrásban megmaradt.')).toBeTruthy();
    expect(f.api.modosit).not.toHaveBeenCalled();
    expect(f.alkalmaz).not.toHaveBeenCalled();
    expect(f.doc.toString()).toBe(FM);
  });

  it('Save közben minden érték és duplamentés védett, a snapshot warning látható marad', async () => {
    const f = await megnyit();
    let kesz!: (v: TulajdonsagTipusok) => void;
    f.api.tipusBeallit.mockImplementationOnce(() => new Promise((r) => { kesz = r; }));
    await fireEvent.click(screen.getByRole('button', { name: 'Típus mentése' }));
    expect((screen.getByRole('button', { name: 'Típus mentése…' }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByLabelText('Count') as HTMLInputElement).readOnly).toBe(true);
    kesz({ rev: 'warn-rev', types: { Due: 'text' }, git: false, figyelmeztetes: 'Type saved; snapshot is unavailable.' });
    expect(await screen.findByText('Type saved; snapshot is unavailable.')).toBeTruthy();
    expect(f.api.tipusBeallit).toHaveBeenCalledTimes(1);
  });

  it('409 friss listát és új explicit Save-et kér; adat nem változik a hiba alatt', async () => {
    const f = await megnyit();
    f.api.tipusBeallit.mockRejectedValueOnce(new ApiHiba(409, 'Conflict'));
    await fireEvent.click(screen.getByRole('button', { name: 'Típus mentése' }));
    await screen.findByRole('alert');
    expect((screen.getByRole('button', { name: 'Típus mentése' }) as HTMLButtonElement).disabled).toBe(true);
    expect(f.api.tipusBeallit).toHaveBeenCalledTimes(1);
    await fireEvent.click(screen.getByRole('button', { name: 'Típusok újratöltése' }));
    await waitFor(() => expect((screen.getByRole('button', { name: 'Típus mentése' }) as HTMLButtonElement).disabled).toBe(false));
    expect(f.api.tipusBeallit).toHaveBeenCalledTimes(1);
    expect(f.alkalmaz).not.toHaveBeenCalled();
  });

  it('fixed tags/aliases csak magyarázatot mutat; readOnly és elérhetetlen vault nem ír', async () => {
    const f = felallit();
    await fireEvent.click(await screen.findByRole('button', { name: 'Tags típusa: Címkék' }));
    expect(screen.getByText('A beépített címke- és aliasmezők típusa rögzített.')).toBeTruthy();
    expect(f.api.tipusok).not.toHaveBeenCalled();
    cleanup();
    const zarolt = felallit(false);
    expect((await screen.findByRole('button', { name: 'Due típusa: Szöveg' }) as HTMLButtonElement).disabled).toBe(true);
    expect(zarolt.api.tipusok).not.toHaveBeenCalled();
    cleanup();
    const h = felallit();
    h.api.tipusok.mockRejectedValueOnce(new ApiHiba(503, 'Workspace unavailable'));
    await fireEvent.click(await screen.findByRole('button', { name: 'Due típusa: Szöveg' }));
    expect(await screen.findByText('Workspace unavailable')).toBeTruthy();
    expect((screen.getByRole('button', { name: 'Típus mentése' }) as HTMLButtonElement).disabled).toBe(true);
    expect(h.api.tipusBeallit).not.toHaveBeenCalled();
  });

  it('másik nyitott panel és változatlan YAML újraelemződik a típus-esemény után', async () => {
    const f = felallit();
    await screen.findByLabelText('Due');
    const elotte = f.api.elemez.mock.calls.length;
    tipusokValtoztak({ rev: 'external-ui-rev' });
    await waitFor(() => expect(f.api.elemez.mock.calls.length).toBeGreaterThan(elotte));
    expect(f.alkalmaz).not.toHaveBeenCalled();
  });

  it('Escape bezár és visszaadja a fókuszt a típusikonnak, POST nélkül', async () => {
    const f = await megnyit();
    await fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('group', { name: 'A(z) „Due” típusa' })).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Due típusa: Szöveg' }));
    expect(f.api.tipusBeallit).not.toHaveBeenCalled();
  });
});
