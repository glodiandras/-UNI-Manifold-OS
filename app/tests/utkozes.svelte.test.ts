// Az ütközés-párbeszéd (C29.7a, T116): „Az enyém” foglalt kör-zárnál (423) nyitva marad és újrapróbál, siker után
// zár; ha a mentés pillanatkép nélkül ment (`git: false`), a felülírt külső változat a vágólapra kerül, és
// figyelmeztetés jön. Valódi `Dokumentum`-mal, ál-core-ral.

import { cleanup, fireEvent, render, waitFor } from '@testing-library/svelte';
import { ChangeSet } from '@codemirror/state';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiHiba } from '../src/lib/core/api';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import type { FajlIras, FajlIrasKeres, FajlOlvasas, VaultApi } from '../src/szerkeszto/dokumentum/api';
import { Dokumentum } from '../src/szerkeszto/dokumentum/dokumentum.svelte';
import Utkozes from '../src/szerkeszto/Utkozes.svelte';

const UT = 'Jegyzet.md';
const hash = (s: string) => `h${s.length}:${[...s].reduce((h, c) => (h * 31 + c.charCodeAt(0)) | 0, 7)}`;

class AlCore implements VaultApi {
  lemez = 'alap\n';
  foglalt = 0;
  git = true;
  irasok: FajlIrasKeres[] = [];
  async olvas(ut: string): Promise<FajlOlvasas> {
    return { ut, tartalom: this.lemez, hash: hash(this.lemez), jel: '', mtime: 0 };
  }
  async ir(k: FajlIrasKeres): Promise<FajlIras> {
    if (this.foglalt > 0) {
      this.foglalt--;
      throw new ApiHiba(423, 'a kör-zár foglalt');
    }
    if (hash(this.lemez) !== k.alap) throw new ApiHiba(409, 'ütközés', { utkozes: true, hash: hash(this.lemez) });
    this.irasok.push(k);
    this.lemez = k.tartalom;
    return { ok: true, ut: k.ut, hash: hash(k.tartalom), jel: '', uzenet: 'mentve', pillanat: null, elotte: null, git: this.git };
  }
}

let core: AlCore;
const vagolap = vi.fn(async (_: string) => undefined);

/** Egy ütköző dokumentum: a lemezen az Obsidian írt, a szerkesztőben mentetlen saját szöveg áll. */
async function utkozoDokumentum(): Promise<Dokumentum> {
  const d = new Dokumentum(core, await core.olvas(UT));
  const cs = ChangeSet.of([{ from: 0, insert: 'enyém ' }], d.szoveg.length);
  d.valtozott(cs, cs.apply(d.szoveg), null);
  core.lemez = 'obsidian írta\n';
  await d.ment();
  expect(d.allapot).toBe('utkozes');
  return d;
}

beforeEach(() => {
  core = new AlCore();
  vagolap.mockClear();
  Object.defineProperty(navigator, 'clipboard', { value: { writeText: vagolap }, configurable: true });
  for (const e of [...ertesitesek.lista]) ertesitesek.elvet(e.id);
});

afterEach(() => {
  cleanup();
});

async function enyemGomb(r: { findByRole(szerep: string, o?: { name: string }): Promise<HTMLElement> }): Promise<HTMLButtonElement> {
  const g = (await r.findByRole('button', { name: 'Az enyém' })) as HTMLButtonElement;
  await waitFor(() => expect(g.disabled).toBe(false)); // a lemezes változat betöltődött
  return g;
}

describe('az ütközés-párbeszéd: „Az enyém”', () => {
  it('foglalt kör-zárnál (423) nyitva marad, jelzi a várakozást, 2 s múlva újrapróbál, siker után zár', async () => {
    const dok = await utkozoDokumentum();
    core.foglalt = 1;
    const onbezar = vi.fn();
    const r = render(Utkozes, { props: { dok, onbezar } });
    await fireEvent.click(await enyemGomb(r));
    await r.findByText(/a kör-zár foglalt/);
    expect(onbezar).not.toHaveBeenCalled();
    expect(dok.allapot).toBe('utkozes');
    expect(core.lemez).toBe('obsidian írta\n'); // nincs felülírás
    await waitFor(() => expect(onbezar).toHaveBeenCalledTimes(1), { timeout: 4000 });
    expect(core.lemez).toBe('enyém alap\n');
    expect(dok.allapot).toBe('tiszta');
    expect(core.irasok).toHaveLength(1);
    expect(core.irasok[0]).toMatchObject({ elso: true, alap: hash('obsidian írta\n') });
  });

  it('pillanatkép nélküli mentésnél (`git: false`) a felülírt külső változat a vágólapra kerül, és figyelmeztetés jön', async () => {
    const dok = await utkozoDokumentum();
    core.git = false;
    const onbezar = vi.fn();
    const r = render(Utkozes, { props: { dok, onbezar } });
    await fireEvent.click(await enyemGomb(r));
    await waitFor(() => expect(onbezar).toHaveBeenCalledTimes(1));
    expect(vagolap).toHaveBeenCalledWith('obsidian írta\n');
    const f = ertesitesek.lista.filter((e) => e.szint === 'figyelmeztetes');
    expect(f).toHaveLength(1);
    expect(f[0].cim).toMatch(/nem került pillanatképbe/);
  });

  it('pillanatképes mentésnél nincs vágólap és nincs figyelmeztetés', async () => {
    const dok = await utkozoDokumentum();
    const onbezar = vi.fn();
    const r = render(Utkozes, { props: { dok, onbezar } });
    await fireEvent.click(await enyemGomb(r));
    await waitFor(() => expect(onbezar).toHaveBeenCalledTimes(1));
    expect(vagolap).not.toHaveBeenCalled();
    expect(ertesitesek.lista.filter((e) => e.szint === 'figyelmeztetes')).toHaveLength(0);
  });
});
