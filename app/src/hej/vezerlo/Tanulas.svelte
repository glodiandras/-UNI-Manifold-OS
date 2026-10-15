<!--
  A vezérlő Tanulás szakasza (C23b; TERV 5.3, docs/C23-TERV.md 7.): a „Mai ismétlés” — az összes esedékes kártya, utánuk az
  újak a napi limitig, egy menetben (szóköz fordít, 1–4 értékel, ⌘Z visszavon); a kártya forrására egy kattintás ugrik.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { trackerKuld } from '../../kartya/beagyazas';
  import { IsmetlesMenet } from '../../kartya/menet.svelte';
  import Pakli from '../../kartya/Pakli.svelte';

  const menet = new IsmetlesMenet({ tipus: 'mai' }, { tracker: trackerKuld });
  onMount(() => {
    void menet.betolt();
  });
</script>

<div class="vezerlo-tanulas">
  {#if menet.fazis !== 'betolt' && menet.fazis !== 'hiba'}
    <p class="osszeg">
      Ma: <b>{menet.esedekes}</b> esedékes · <b>{menet.uj}</b> új
      {#if menet.fazis === 'kesz' || menet.fazis === 'ures'}
        <button class="m-gomb link" type="button" onclick={() => menet.betolt()}>Frissítés</button>
      {/if}
    </p>
  {/if}
  <Pakli {menet} cim="Mai ismétlés" />
</div>

<style>
  .vezerlo-tanulas {
    display: flex;
    flex-direction: column;
    gap: var(--t-2);
  }

  .osszeg {
    margin: 0;
    color: var(--szoveg-masodlagos);
    font-variant-numeric: tabular-nums;
  }
</style>
