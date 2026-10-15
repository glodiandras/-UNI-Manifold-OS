<!--
  Vázlat (C10): a jegyzet fejezetei az ÉLŐ szövegből (a szerkesztő szintaxisfájából), gépelés közben is frissül.
  Kattintásra a szerkesztő a fejezetre ugrik.
-->
<script lang="ts">
  import { szerkesztok } from '../../szerkeszto/szerkesztok.svelte';

  const peldany = $derived(szerkesztok.aktiv);
  const elemek = $derived.by(() => {
    const p = peldany;
    if (!p) return [];
    void p.valtozat(); // a szöveg változására újraszámol
    return p.vazlat();
  });
  const legkisebb = $derived(elemek.reduce((m, e) => Math.min(m, e.szint), 6));
</script>

{#if !peldany}
  <p class="ures">Nincs megnyitott jegyzet.</p>
{:else if !elemek.length}
  <p class="ures">A jegyzetben nincs fejezet.</p>
{:else}
  <ul>
    {#each elemek as e, i (`${e.sor}:${i}`)}
      <li style:padding-left="{(e.szint - legkisebb) * 12}px">
        <button type="button" class="sor" onclick={() => peldany?.ugras(e.sor)}>{e.szoveg}</button>
      </li>
    {/each}
  </ul>
{/if}

<style>
  .ures {
    margin: 0;
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  ul {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .sor {
    display: block;
    width: 100%;
    padding: 2px var(--t-1);
    border-radius: var(--kerekites-kicsi);
    text-align: left;
    font-size: var(--betu-ui);
    color: var(--szoveg-masodlagos);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .sor:hover {
    background: var(--hatter-hover);
    color: var(--szoveg);
  }
</style>
