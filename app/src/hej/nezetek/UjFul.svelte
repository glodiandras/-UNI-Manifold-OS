<!-- Üres fül: a következő lépések, gyorsbillentyűvel. -->
<script lang="ts">
  import type { NezetProps } from '../../lib/elrendezes/nezetek.svelte';
  import { regiszter } from '../../lib/parancsok/regiszter';
  import Billentyu from '../../lib/ui/Billentyu.svelte';

  let {}: NezetProps = $props();

  const LEHETOSEGEK: { id: string; nev: string; akkord?: string }[] = [
    { id: 'ma.megnyit', nev: 'Ma' },
    { id: 'naplo.napi', nev: 'Napi jegyzet', akkord: 'Mod+Shift+D' },
    { id: 'hej.valto', nev: 'Fájl megnyitása', akkord: 'Mod+O' },
    { id: 'hej.paletta', nev: 'Parancsok', akkord: 'Mod+P' },
    { id: 'ful.bezar', nev: 'Fül bezárása', akkord: 'Mod+W' },
  ];
</script>

<div class="uj-ful">
  <h2>Nincs megnyitott jegyzet</h2>
  <ul role="list">
    {#each LEHETOSEGEK as l (l.id)}
      <li>
        <button type="button" onclick={() => regiszter.futtat(l.id, 'gomb')}>
          <span>{l.nev}</span>
          {#if l.akkord}<Billentyu akkord={l.akkord} />{/if}
        </button>
      </li>
    {/each}
  </ul>
</div>

<style>
  .uj-ful {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: var(--t-4);
    min-height: 100%;
    padding: var(--t-7) var(--t-5) 12vh;
  }

  h2 {
    font-size: var(--betu-torzs);
    line-height: var(--magassag-suru);
    font-weight: var(--suly-kozepes);
    color: var(--szoveg-masodlagos);
  }

  ul {
    margin: 0;
    padding: 0;
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 2px;
    width: 240px;
  }

  button {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    height: var(--magassag-lista-sor);
    padding: 0 var(--t-1) 0 var(--t-3);
    border-radius: var(--kerekites);
    color: var(--akcent-szoveg);
    transition: background-color var(--mozgas-gyors) var(--mozgas-gorbe);
  }

  button:hover {
    background: var(--hatter-hover);
  }

  button:active {
    background: var(--hatter-aktiv);
  }
</style>
