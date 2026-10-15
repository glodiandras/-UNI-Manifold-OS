<!--
  Eszköztár-gomb és a hozzá tartozó lebegő panel (C12b): kattintásra nyílik, kívülre kattintás és Esc zár (az Esc a
  gombra adja vissza a fókuszt). A panel `role="dialog"`; a tartalmát a hívó adja.
-->
<script lang="ts">
  import type { IconNode } from 'lucide';
  import type { Snippet } from 'svelte';
  import Ikon from '../lib/ikon/Ikon.svelte';

  interface Props {
    felirat: string;
    ikon?: IconNode;
    /** a gombon látszó szám / jelző (pl. a szűrők száma) */
    jelzo?: string | null;
    cimke: string;
    szeles?: boolean;
    nyitva?: boolean;
    children: Snippet;
  }
  let { felirat, ikon, jelzo = null, cimke, szeles = false, nyitva = $bindable(false), children }: Props = $props();

  let gyoker: HTMLSpanElement | undefined = $state();
  let gomb: HTMLButtonElement | undefined = $state();

  /** a panel `fixed`: a szülők `overflow`-ja nem vágja le; a gomb alatt nyílik, a nézeten belül marad */
  let hely = $state<{ bal: number; fent: number } | null>(null);

  function nyitasKapcsol() {
    nyitva = !nyitva;
    if (nyitva && gomb) {
      const r = gomb.getBoundingClientRect();
      const szel = szeles ? 460 : 320;
      hely = { bal: Math.max(8, Math.min(r.left, window.innerWidth - szel - 8)), fent: r.bottom + 4 };
    }
  }

  function kivul(e: PointerEvent) {
    if (nyitva && gyoker && !gyoker.contains(e.target as Node)) nyitva = false;
  }

  function billentyu(e: KeyboardEvent) {
    if (e.key === 'Escape' && nyitva) {
      e.preventDefault();
      e.stopPropagation();
      nyitva = false;
      gomb?.focus();
    }
  }
</script>

<svelte:window onpointerdown={kivul} />

<span class="popover" bind:this={gyoker} onkeydown={billentyu} role="presentation">
  <button
    type="button"
    class="gomb"
    class:aktiv={nyitva}
    class:jelolt={!!jelzo}
    aria-haspopup="dialog"
    aria-expanded={nyitva}
    title={cimke}
    bind:this={gomb}
    onclick={nyitasKapcsol}
  >
    {#if ikon}<Ikon {ikon} meret={14} />{/if}
    <span>{felirat}</span>
    {#if jelzo}<span class="jelzo">{jelzo}</span>{/if}
  </button>
  {#if nyitva}
    <div
      class="panel"
      class:szeles
      role="dialog"
      aria-label={cimke}
      style:left={hely ? `${hely.bal}px` : undefined}
      style:top={hely ? `${hely.fent}px` : undefined}
      style:max-height={hely ? `min(560px, calc(100vh - ${hely.fent}px - 16px))` : undefined}
    >
      {@render children()}
    </div>
  {/if}
</span>

<style>
  .popover {
    position: relative;
    display: inline-block;
  }

  .gomb {
    display: inline-flex;
    align-items: center;
    gap: var(--t-1);
    height: var(--magassag-gomb);
    padding: 0 var(--t-2);
    border: 0;
    border-radius: var(--kerekites-kicsi);
    background: transparent;
    color: var(--szoveg-masodlagos);
    font: inherit;
    cursor: pointer;
  }

  .gomb:hover,
  .gomb.aktiv {
    background: var(--hatter-hover);
    color: var(--szoveg);
  }

  .gomb.jelolt {
    color: var(--akcent-szoveg);
  }

  .jelzo {
    min-width: 16px;
    padding: 0 4px;
    border-radius: var(--kerekites-nagy);
    background: var(--hatter-aktiv);
    color: var(--szoveg-masodlagos);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    text-align: center;
    font-variant-numeric: tabular-nums;
  }

  .panel {
    position: fixed;
    z-index: var(--reteg-lap);
    width: 320px;
    max-width: calc(100vw - 16px);
    max-height: min(70vh, 560px);
    overflow: auto;
    padding: var(--t-3);
    border-radius: var(--kerekites-nagy);
    background: var(--hatter-emelt);
    box-shadow: var(--arnyek-atfedes);
    color: var(--szoveg);
    font-size: var(--betu-ui);
    line-height: var(--sor-ui);
    white-space: normal;
    text-align: left;
  }

  .panel.szeles {
    width: 460px;
  }
</style>
