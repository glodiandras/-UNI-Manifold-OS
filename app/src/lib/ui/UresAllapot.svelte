<!--
  Közös üres állapot (F7): ikon, cím, egy mondat magyarázat és legfeljebb két művelet (az elsődleges kitöltött, a másodlagos
  semleges). Az üres nézet sosem zsákutca: mindig megmondja, mit lehet tenni. A burgundi csak a műveleten van (nem jelez állapotot).
-->
<script lang="ts">
  import type { IconNode } from 'lucide';
  import Ikon from '../ikon/Ikon.svelte';

  type UresMuvelet = { cimke: string; onclick: () => void };
  let { cim, leiras = '', ikon, muvelet, masodlagos, kicsi = false }: {
    cim: string;
    leiras?: string;
    ikon?: IconNode;
    muvelet?: UresMuvelet;
    masodlagos?: UresMuvelet;
    kicsi?: boolean;
  } = $props();
</script>

<div class="m-ures" class:kicsi data-ures>
  {#if ikon}<span class="ures-ikon"><Ikon {ikon} meret={20} /></span>{/if}
  <p class="ures-cim">{cim}</p>
  {#if leiras}<p class="ures-leiras">{leiras}</p>{/if}
  {#if muvelet || masodlagos}
    <div class="ures-gombok">
      {#if muvelet}<button type="button" class="m-gomb" onclick={muvelet.onclick}>{muvelet.cimke}</button>{/if}
      {#if masodlagos}<button type="button" class="m-gomb semleges" onclick={masodlagos.onclick}>{masodlagos.cimke}</button>{/if}
    </div>
  {/if}
</div>

<style>
  .m-ures {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--t-2);
    padding: var(--t-6) var(--t-5);
    text-align: center;
    color: var(--szoveg-masodlagos);
  }
  .m-ures.kicsi { padding: var(--t-3) var(--t-3); gap: var(--t-1); }
  .ures-ikon { color: var(--szoveg-halvany); }
  .ures-cim { margin: 0; font-weight: var(--suly-kozepes); color: var(--szoveg); }
  .ures-leiras { margin: 0; max-width: 40ch; font-size: var(--betu-kicsi); line-height: var(--sor-kicsi); }
  .ures-gombok { display: flex; flex-wrap: wrap; justify-content: center; gap: var(--t-2); margin-top: var(--t-2); }
</style>
