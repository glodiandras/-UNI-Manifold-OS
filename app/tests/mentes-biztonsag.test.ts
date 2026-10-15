// C10.5 (audit K1, H6): a mentési hiba értesítést kap, nem csak állapotfeliratot; a core git-figyelmeztetése
// (`pillanat_hiba`) és az indulási helyreállítás üzenetei (`hello.figyelmeztetesek`) értesítésként jelennek meg;
// a kilépés jelentése a héjnak megmondja, maradt-e mentetlen jegyzet.

import { ChangeSet } from '@codemirror/state';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiHiba } from '../src/lib/core/api';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { Regiszter } from '../src/lib/parancsok/regiszter';
import { kilepesMentes, szerkesztoTelepit } from '../src/szerkeszto';
import type { FajlIras, FajlIrasKeres, FajlOlvasas, VaultApi } from '../src/szerkeszto/dokumentum/api';
import { Dokumentum, Dokumentumok } from '../src/szerkeszto/dokumentum/dokumentum.svelte';

class AlCore implements VaultApi {
  lemez = '# A\n';
  hiba: ApiHiba | null = null;
  async olvas(ut: string): Promise<FajlOlvasas> {
    return { ut, tartalom: this.lemez, hash: 'h:' + this.lemez, jel: '', mtime: 0 };
  }
  async ir(k: FajlIrasKeres): Promise<FajlIras> {
    if (this.hiba) throw this.hiba;
    this.lemez = k.tartalom;
    return { ok: true, ut: k.ut, hash: 'h:' + k.tartalom, jel: '', uzenet: 'mentve', pillanat: null, elotte: null, git: true };
  }
}

function urit() {
  for (const e of [...ertesitesek.lista]) ertesitesek.elvet(e.id);
}

beforeEach(() => {
  vi.useFakeTimers();
  urit();
});
afterEach(() => {
  vi.useRealTimers();
  urit();
});

describe('mentési hiba → értesítés (K1)', () => {
  it('az első hibánál egy hiba-értesítés, az újrapróbák nem szaporítják; a sikeres mentés elveszi', async () => {
    const core = new AlCore();
    const d = new Dokumentum(core, await core.olvas('A.md'));
    core.hiba = new ApiHiba(500, 'SnapshotError: index.lock');
    const v = ChangeSet.of([{ from: 0, insert: 'x' }], d.szoveg.length);
    d.valtozott(v, v.apply(d.szoveg), null);
    await vi.advanceTimersByTimeAsync(1100);
    expect(d.allapot).toBe('hiba');
    const hibak = () => ertesitesek.lista.filter((e) => e.szint === 'hiba');
    expect(hibak()).toHaveLength(1);
    expect(hibak()[0].cim).toBe('A mentés nem sikerült');
    expect(hibak()[0].szoveg).toContain('A.md');
    await vi.advanceTimersByTimeAsync(2100); // újrapróba, még mindig hiba
    expect(hibak()).toHaveLength(1);
    core.hiba = null;
    await vi.advanceTimersByTimeAsync(5100);
    expect(d.allapot).toBe('tiszta');
    expect(hibak()).toHaveLength(0);
  });
});

describe('a core figyelmeztetései (K1, H3)', () => {
  it('`pillanat_hiba` → figyelmeztetés; `hello.figyelmeztetesek` → egy-egy figyelmeztetés', () => {
    const k = new CoreKapcsolat('ws://127.0.0.1:1/ws');
    const le = szerkesztoTelepit(new Regiszter(), k);
    k.szetoszt({ tipus: 'pillanat_hiba', tar: 'vault', ut: 'A.md', uzenet: 'a git hibát jelzett' });
    const f = ertesitesek.lista.filter((e) => e.szint === 'figyelmeztetes');
    expect(f).toHaveLength(1);
    expect(f[0].szoveg).toContain('a git hibát jelzett');
    k.szetoszt({ tipus: 'hello', figyelmeztetesek: ['index.lock eltávolítva', 'átnevezés visszaállítva'] });
    expect(ertesitesek.lista.filter((e) => e.szint === 'figyelmeztetes')).toHaveLength(3);
    k.szetoszt({ tipus: 'hello', figyelmeztetesek: [] });
    expect(ertesitesek.lista.filter((e) => e.szint === 'figyelmeztetes')).toHaveLength(3);
    le();
  });
});

describe('a core állapotjelzései (C29.6 → C29.7b)', () => {
  it('`indulasi_uzenet` (a háttér-újrapróba késői üzenete) ugyanúgy figyelmeztetés, mint a hello-é', () => {
    const k = new CoreKapcsolat('ws://127.0.0.1:1/ws');
    const le = szerkesztoTelepit(new Regiszter(), k);
    k.szetoszt({ tipus: 'indulasi_uzenet', uzenetek: ['egy megszakadt átnevezés visszaállt', 'index.lock eltávolítva'] });
    const f = ertesitesek.lista.filter((e) => e.szint === 'figyelmeztetes');
    expect(f.map((e) => e.szoveg)).toEqual(['egy megszakadt átnevezés visszaállt', 'index.lock eltávolítva']);
    expect(f[0].cim).toBe('Helyreállítás induláskor');
    k.szetoszt({ tipus: 'indulasi_uzenet', uzenetek: 'nem lista' }); // a hibás alak nem dob
    k.szetoszt({ tipus: 'indulasi_uzenet' });
    le();
  });

  it('`vault_elerheto`: eltűnt kötetnél tartós hiba-értesítés (egy, kulcsos), visszatérésnél elvész + rövid tájékoztató', () => {
    const k = new CoreKapcsolat('ws://127.0.0.1:1/ws');
    const le = szerkesztoTelepit(new Regiszter(), k);
    k.szetoszt({ tipus: 'vault_elerheto', elerheto: false });
    k.szetoszt({ tipus: 'vault_elerheto', elerheto: false });
    const hibak = () => ertesitesek.lista.filter((e) => e.szint === 'hiba');
    expect(hibak()).toHaveLength(1);
    expect(hibak()[0].cim).toBe('A vault nem érhető el');
    expect(hibak()[0].idotartam).toBe(0);
    expect(hibak()[0].szoveg).toMatch(/szerkesztőben.*megvan/);
    k.szetoszt({ tipus: 'vault_elerheto', elerheto: true });
    expect(hibak()).toHaveLength(0);
    expect(ertesitesek.lista.some((e) => e.szint === 'siker' && e.cim === 'A vault újra elérhető')).toBe(true);
    le();
  });

  it('az „újra elérhető” tájékoztató csak előzetes kiesés után jön', () => {
    const k = new CoreKapcsolat('ws://127.0.0.1:1/ws');
    const le = szerkesztoTelepit(new Regiszter(), k);
    k.szetoszt({ tipus: 'vault_elerheto', elerheto: true });
    expect(ertesitesek.lista).toHaveLength(0);
    le();
  });
});

describe('kilépés: a héjnak szóló jelentés (H6)', () => {
  it('mentetlen vagy hibás jegyzetnél ok: false a listával; rendben ok: true', async () => {
    const core = new AlCore();
    const dk = new Dokumentumok(core);
    const a = await dk.megnyit('A.md');
    await dk.megnyit('B.md');
    const v = ChangeSet.of([{ from: 0, insert: 'x' }], a.szoveg.length);
    a.valtozott(v, v.apply(a.szoveg), null);
    core.hiba = new ApiHiba(500, 'a lemez megtelt');
    const j = await kilepesMentes(dk);
    expect(j.ok).toBe(false);
    expect(j.mentetlen).toEqual([{ ut: 'A.md', allapot: 'hiba', hiba: 'a lemez megtelt' }]);
    core.hiba = null;
    const j2 = await kilepesMentes(dk);
    expect(j2).toEqual({ ok: true, mentetlen: [] });
    expect(core.lemez.startsWith('x')).toBe(true);
  });
});
