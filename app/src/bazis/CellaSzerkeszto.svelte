<!--
  Egy cella szerkesztője (C12b): a cella helyén nyílik (dupla kattintás, ↩ vagy F2), a típus szerint: szöveg, szám,
  dátum, lista (vesszővel), választó (Status). ↩ ment, Esc elvet, a fókus elhagyása ment. A séma-sértő érték nem
  íródik csendben: a mező alatt „Mégis beírom” jelenik meg; a nem írható értéknél az ok látszik, és a mező nyitva marad.
  A kezdőérték a jegyzet frontmatterének nyers értéke (nem a megjelenített cella), így az álnév és a formátum sértetlen.
-->
<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import { tulajdonsagApi } from '../szerkeszto/tulajdonsagok/api';
  import type { SemaProblema } from '../szerkeszto/tulajdonsagok/tipusok';
  import { bevitelbol, fajta as fajtaValaszt, iroTipus, kezdoSzoveg, valtozatlan, type Fajta } from './cellaErtek';
  import { cellaIr, cellaOlvas, type CellaEredmeny } from './cellaIr';

  interface Props {
    ut: string;
    kulcs: string;
    oszlopTipus: string;
    /** a mentés sikere után (a cella visszaáll olvasásra) */
    kesz: (e: CellaEredmeny, kulcs: string) => void;
    megse: () => void;
  }
  let { ut, kulcs, oszlopTipus, kesz, megse }: Props = $props();

  let valos = $state(untrack(() => kulcs));
  let f = $state<Fajta>('szoveg');
  let kezdo = $state('');
  let szoveg = $state('');
  let tolt = $state(true);
  let dolgozik = $state(false);
  let hiba = $state<string | null>(null);
  let fuggo = $state<SemaProblema[] | null>(null);
  let valasztek = $state<string[]>([]);
  let mezo: HTMLInputElement | HTMLSelectElement | undefined = $state();
  let kesz_jelzo = false;

  onMount(() => {
    let el = true;
    void (async () => {
      try {
        const o = await cellaOlvas(ut, kulcs);
        if (!el) return;
        valos = o.kulcs;
        f = fajtaValaszt(o.tipus ?? oszlopTipus, o.kulcs, o.ertek);
        kezdo = szoveg = kezdoSzoveg(f, o.ertek);
        if (f === 'valaszto') {
          const s = await tulajdonsagApi().sema(ut).catch(() => null);
          if (!el) return;
          valasztek = s?.status_ertekkeszlet ?? [];
          if (kezdo && !valasztek.includes(kezdo)) valasztek = [...valasztek, kezdo];
        }
      } catch (e) {
        if (!el) return;
        hiba = e instanceof Error ? e.message : String(e);
      } finally {
        if (el) {
          tolt = false;
          queueMicrotask(() => {
            mezo?.focus();
            if (mezo instanceof HTMLInputElement && f !== 'datum' && f !== 'datumido') mezo.select();
          });
        }
      }
    })();
    return () => (el = false);
  });

  async function ment(megerosit = false) {
    if (dolgozik || kesz_jelzo) return;
    if (!megerosit && valtozatlan(f, kezdo, szoveg)) return megseKilep();
    const b = bevitelbol(f, szoveg, valos);
    if ('hiba' in b) {
      hiba = b.hiba;
      return;
    }
    dolgozik = true;
    hiba = null;
    const r = await cellaIr(ut, valos, b.ertek, iroTipus(oszlopTipus), megerosit);
    dolgozik = false;
    if (r.ok) {
      kesz_jelzo = true;
      kesz(r, valos);
    } else if (r.fuggo) {
      fuggo = r.fuggo;
    } else {
      fuggo = null;
      hiba = r.elutasitva ?? 'A módosítás nem írható.';
    }
  }

  function megseKilep() {
    if (kesz_jelzo) return;
    kesz_jelzo = true;
    megse();
  }

  function billentyu(e: KeyboardEvent) {
    if (e.isComposing) return;
    if (e.key === 'Enter') {
      e.preventDefault();
      e.stopPropagation();
      void ment();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      megseKilep();
    }
  }

  function fokuszElhagy(e: FocusEvent) {
    const cel = e.relatedTarget as Node | null;
    if (cel && (e.currentTarget as HTMLElement).parentElement?.contains(cel)) return; // a „Mégis beírom” gombra lép
    if (fuggo || hiba) return; // a hibás mező nyitva marad
    void ment();
  }
</script>

<span class="szerkeszto" role="group" aria-label="{valos} szerkesztése">
  {#if tolt}
    <span class="tolt">…</span>
  {:else if f === 'valaszto'}
    <select bind:this={mezo} bind:value={szoveg} onkeydown={billentyu} onchange={() => void ment()} onblur={fokuszElhagy} disabled={dolgozik} aria-label={valos}>
      <option value="">(nincs)</option>
      {#each valasztek as v (v)}<option value={v}>{v}</option>{/each}
    </select>
  {:else}
    <input
      bind:this={mezo}
      bind:value={szoveg}
      type={f === 'datum' ? 'date' : f === 'datumido' ? 'datetime-local' : 'text'}
      inputmode={f === 'szam' ? 'decimal' : undefined}
      placeholder={f === 'lista' ? 'elem, elem' : ''}
      onkeydown={billentyu}
      onblur={fokuszElhagy}
      disabled={dolgozik}
      aria-label={valos}
      aria-invalid={hiba ? 'true' : undefined}
    />
  {/if}
  {#if hiba}
    <span class="uzenet hiba" role="alert">{hiba}</span>
  {/if}
  {#if fuggo}
    <span class="uzenet figyelmeztetes" role="alert">
      {fuggo[0]?.uzenet ?? 'A séma sérül.'}
      <button type="button" class="m-gomb semleges gomb" onclick={() => void ment(true)}>Mégis beírom</button>
      <button type="button" class="m-gomb semleges gomb" onclick={megseKilep}>Mégse</button>
    </span>
  {/if}
</span>

<style>
  .szerkeszto {
    position: relative;
    display: flex;
    flex: 1;
    min-width: 0;
    align-items: center;
  }

  input,
  select {
    flex: 1;
    min-width: 0;
    height: calc(100% - 4px);
    margin: 0;
    padding: 0 var(--t-1);
    border: 1px solid var(--akcent);
    border-radius: var(--kerekites-kicsi);
    background: var(--hatter);
    color: var(--szoveg);
    font: inherit;
    outline: none;
  }

  .tolt {
    color: var(--szoveg-halvany);
  }

  .uzenet {
    position: absolute;
    z-index: 5;
    top: 100%;
    left: 0;
    min-width: 100%;
    width: max-content;
    max-width: 360px;
    padding: var(--t-1) var(--t-2);
    border-radius: var(--kerekites-kicsi);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    white-space: normal;
    box-shadow: var(--arnyek-atfedes);
  }

  .hiba {
    color: var(--hiba);
    background: var(--hiba-hatter);
    border: var(--keret-vastag) solid var(--keret);
  }

  .figyelmeztetes {
    color: var(--figyelmeztetes);
    background: var(--figyelmeztetes-hatter);
    border: var(--keret-vastag) solid var(--keret);
  }

  .gomb {
    margin-left: var(--t-1);
    padding: 0 var(--t-2);
  }
</style>
