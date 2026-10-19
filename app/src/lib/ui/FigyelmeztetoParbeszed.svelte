<!-- Közös megerősítő alertdialog a meglévő modális rétegen: fókuszcsapda, Escape, fókuszvisszaadás; alapfókusz a Mégse. -->
<script lang="ts">
  import { onMount, type Snippet } from 'svelte';
  import type { IconNode } from 'lucide';
  import { t } from '../i18n';
  import Ikon from '../ikon/Ikon.svelte';
  import { CircleAlert } from '../ikon/ikonok';
  import Atfedes from './Atfedes.svelte';

  let { nev, cim, megerosit, ikon = CircleAlert, folyamat = false, hiba = null, onbezar, onmegerosit, children }: {
    nev: string;
    cim: string;
    megerosit: string;
    ikon?: IconNode;
    folyamat?: boolean;
    hiba?: string | null;
    onbezar: () => void;
    onmegerosit: () => void;
    children: Snippet;
  } = $props();
  const id = $props.id();
  let megse: HTMLButtonElement | undefined = $state();
  const bezar = () => { if (!folyamat) onbezar(); };
  onMount(() => megse?.focus());
</script>

<Atfedes cimke={cim} {nev} onbezar={bezar} szerep="alertdialog" leirasId={`${id}-leiras`}>
  <div class="megerosites" aria-busy={folyamat}>
    <header class="fej">
      <span class="ikon" aria-hidden="true"><Ikon {ikon} meret={20} /></span>
      <h2>{cim}</h2>
    </header>
    <div class="leiras" id={`${id}-leiras`}>{@render children()}</div>
    {#if hiba}<p class="hiba" role="alert"><Ikon ikon={CircleAlert} meret={16} /><span>{hiba}</span></p>{/if}
    <footer class="muveletek">
      <button type="button" class="m-gomb semleges" bind:this={megse} disabled={folyamat} onclick={bezar}>{t('Mégse')}</button>
      <button type="button" class="m-gomb" disabled={folyamat} onclick={onmegerosit}>{megerosit}</button>
    </footer>
  </div>
</Atfedes>

<style>
  .megerosites { display: flex; flex-direction: column; gap: var(--t-4); min-height: 0; padding: var(--t-5); }
  .fej { flex: none; display: flex; align-items: center; gap: var(--t-3); }
  .ikon { flex: none; display: grid; place-items: center; width: var(--t-6); height: var(--t-6); color: var(--szoveg-masodlagos); }
  h2 { margin: 0; font-size: var(--betu-torzs); line-height: var(--magassag-suru); font-weight: var(--suly-felkover); }
  .leiras { flex: 1; min-height: 0; overflow: auto; overflow-wrap: anywhere; color: var(--szoveg-masodlagos); font-size: var(--betu-ui); line-height: var(--sor-ui); }
  .hiba { display: flex; align-items: start; gap: var(--t-2); margin: 0; overflow-wrap: anywhere; color: var(--hiba); font-size: var(--betu-ui); }
  .hiba :global(svg) { flex: none; }
  .muveletek { flex: none; display: flex; flex-wrap: wrap; justify-content: flex-end; gap: var(--t-2); }
  .muveletek button { max-width: 100%; white-space: normal; height: auto; min-height: var(--magassag-gomb); }
</style>
