<!-- Az osztásfa rekurzív megjelenítése: levél = panel, belső csomópont = két rész egy elválasztóval. -->
<script lang="ts">
  import type { Csomopont } from '../lib/elrendezes/munkaterulet.svelte';
  import { kornyezet } from '../lib/kornyezet';
  import Elvalaszto from './Elvalaszto.svelte';
  import Osztas from './Osztas.svelte';
  import Panel from './Panel.svelte';

  let { cs }: { cs: Csomopont } = $props();
  const { felulet } = kornyezet();
  let tarolo: HTMLDivElement | undefined = $state();
</script>

{#if cs.tipus === 'panel'}
  <Panel panel={cs} />
{:else}
  <div class="osztas {cs.irany}" bind:this={tarolo}>
    <div class="resz" style:flex="{cs.arany} 1 0">
      <Osztas cs={cs.a} />
    </div>
    <Elvalaszto
      irany={cs.irany}
      arany={cs.arany}
      {tarolo}
      onvaltozas={(a) => felulet.munkaterulet.aranyBeallit(cs.id, a)}
    />
    <div class="resz" style:flex="{1 - cs.arany} 1 0">
      <Osztas cs={cs.b} />
    </div>
  </div>
{/if}

<style>
  .osztas {
    display: flex;
    width: 100%;
    height: 100%;
    min-width: 0;
    min-height: 0;
  }

  .osztas.oszlop {
    flex-direction: column;
  }

  .resz {
    min-width: 0;
    min-height: 0;
    display: flex;
  }

  .resz > :global(*) {
    flex: 1;
  }
</style>
