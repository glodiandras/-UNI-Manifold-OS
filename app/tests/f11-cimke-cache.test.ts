import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { beallitasok } from '../src/lib/beallitasok/allapot.svelte';
import { alapBeallitasok } from '../src/lib/beallitasok/tipusok';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';

const api = vi.hoisted(() => ({ kerdez: vi.fn() }));
vi.mock('../src/lib/core/api', async (importOriginal) => ({ ...await importOriginal<typeof import('../src/lib/core/api')>(), kerdez: api.kerdez }));
import { ApiHiba } from '../src/lib/core/api';
import { VaultCimkek } from '../src/lib/vault/cimkek.svelte';

const LISTA = [{ cimke: 'Topic', kis: 'topic', db: 1, ossz: 1 }];
const eredeti = beallitasok.adat;
function modul(be: boolean): void {
  const ertek = alapBeallitasok();
  ertek.modulok.cimkek = be;
  beallitasok.fogad({ verzio: 1, rev: 'cache-test', ertek, munkater: { id: 'cache-test', nev: 'Synthetic', vault: '/synthetic' }, setup_szukseges: false, ujrainditas: [] });
}
function halasztott<T>() {
  let kesz!: (v: T) => void;
  const p = new Promise<T>((resolve) => { kesz = resolve; });
  return { p, kesz };
}

beforeEach(() => { vi.useFakeTimers(); api.kerdez.mockReset().mockResolvedValue({ cimkek: LISTA }); modul(true); });
afterEach(() => { vi.useRealTimers(); beallitasok.adat = eredeti; });

describe('F11: közös címke-cache fogyasztói', () => {
  it('több editor és kiegészítés egyetlen futó/betöltött kérést oszt meg', async () => {
    const d = halasztott<{ cimkek: typeof LISTA }>();
    api.kerdez.mockReturnValueOnce(d.p);
    const c = new VaultCimkek();
    const le1 = c.igenyel();
    const le2 = c.igenyel();
    const kesz = c.kerjen();
    expect(api.kerdez).toHaveBeenCalledTimes(1);
    d.kesz({ cimkek: LISTA });
    await kesz;
    await c.kerjen();
    expect(c.lista).toEqual(LISTA);
    expect(c.betoltve).toBe(true);
    expect(api.kerdez).toHaveBeenCalledTimes(1);
    le1(); le1(); le2();
  });

  it('rejtett panel mellett editor fogyasztóval frissül; utolsó release után nincs háttérkérés', async () => {
    const c = new VaultCimkek();
    const k = new CoreKapcsolat('ws://test');
    const leWs = c.figyel(k);
    const le1 = c.igenyel();
    const le2 = c.igenyel();
    await c.kerjen();
    le1();
    k.szetoszt({ tipus: 'vault_valtozas' });
    await vi.advanceTimersByTimeAsync(800);
    expect(api.kerdez).toHaveBeenCalledTimes(2);
    k.szetoszt({ tipus: 'vault_valtozas' });
    le2();
    await vi.advanceTimersByTimeAsync(1000);
    expect(api.kerdez).toHaveBeenCalledTimes(2);
    k.szetoszt({ tipus: 'index' });
    await vi.advanceTimersByTimeAsync(0);
    expect(api.kerdez).toHaveBeenCalledTimes(2);
    const uj = c.igenyel();
    await c.kerjen();
    expect(api.kerdez).toHaveBeenCalledTimes(3);
    uj(); leWs();
  });

  it('látható panel továbbra is fogyasztó; rejtés után egy már ütemezett refresh sem kér', async () => {
    const c = new VaultCimkek();
    const k = new CoreKapcsolat('ws://test');
    const le = c.figyel(k);
    c.megjelenik();
    await c.kerjen();
    k.szetoszt({ tipus: 'vault_valtozas' });
    c.latszik = false;
    await vi.advanceTimersByTimeAsync(800);
    expect(api.kerdez).toHaveBeenCalledTimes(1);
    c.megjelenik();
    await c.kerjen();
    expect(api.kerdez).toHaveBeenCalledTimes(2);
    le();
  });

  it('futó kérés alatt érkezett index esemény nem vész el a deduplikáláskor', async () => {
    const d = halasztott<{ cimkek: typeof LISTA }>();
    api.kerdez.mockReturnValueOnce(d.p).mockResolvedValue({ cimkek: [{ ...LISTA[0], db: 2, ossz: 2 }] });
    const c = new VaultCimkek();
    const k = new CoreKapcsolat('ws://test');
    const leWs = c.figyel(k);
    const le = c.igenyel();
    k.szetoszt({ tipus: 'index' });
    await vi.advanceTimersByTimeAsync(0);
    expect(api.kerdez).toHaveBeenCalledTimes(1);
    d.kesz({ cimkek: LISTA });
    await c.kerjen();
    await vi.advanceTimersByTimeAsync(0);
    expect(api.kerdez).toHaveBeenCalledTimes(2);
    expect(c.lista[0].db).toBe(2);
    le(); leWs();
  });

  it('kikapcsolt címkemodul nem indít kérést; visszakapcsoláskor a cache újra használható', async () => {
    modul(false);
    const c = new VaultCimkek();
    const k = new CoreKapcsolat('ws://test');
    const leWs = c.figyel(k);
    const le = c.igenyel();
    c.megjelenik();
    await c.kerjen();
    k.szetoszt({ tipus: 'index' });
    await vi.advanceTimersByTimeAsync(1000);
    expect(api.kerdez).not.toHaveBeenCalled();
    modul(true);
    await c.kerjen();
    expect(api.kerdez).toHaveBeenCalledTimes(1);
    le(); leWs();
  });

  it('503 indexépítés után index eseményre újrapróbál; megszüntetett kapcsolat válasza nem ír vissza', async () => {
    api.kerdez.mockRejectedValueOnce(new ApiHiba(503, 'Building'));
    const c = new VaultCimkek();
    const k = new CoreKapcsolat('ws://test');
    const leWs = c.figyel(k);
    const le = c.igenyel();
    await c.kerjen();
    expect(c.betoltve).toBe(false);
    expect(c.hiba).toBeNull();
    k.szetoszt({ tipus: 'index' });
    await vi.advanceTimersByTimeAsync(0);
    expect(c.betoltve).toBe(true);
    const d = halasztott<{ cimkek: typeof LISTA }>();
    api.kerdez.mockReturnValueOnce(d.p);
    const kesz = c.frissit();
    leWs();
    d.kesz({ cimkek: [{ ...LISTA[0], cimke: 'Stale' }] });
    await kesz;
    expect(c.lista[0].cimke).toBe('Topic');
    le();
  });
});
