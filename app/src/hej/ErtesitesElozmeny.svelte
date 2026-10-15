<!-- Az értesítések munkamenet-előzménye (az állapotsor gombja nyitja); Esc vagy kattintás kívül zárja. -->
<script lang="ts">
  import { onMount } from 'svelte';
  import { fly } from 'svelte/transition';
  import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
  import { ido } from '../lib/elrendezes/mozgas';
  import { visszaad } from '../lib/fokusz/fokusz';

  let { nyito, onbezar }: { nyito: HTMLElement | undefined; onbezar: () => void } = $props();
  let doboz: HTMLDivElement | undefined = $state();
  const idoFormatum = new Intl.DateTimeFormat('hu-HU', { hour: '2-digit', minute: '2-digit' });

  onMount(() => {
    ertesitesek.olvasva();
    doboz?.focus();
    const kivul = (e: PointerEvent) => {
      if (!doboz?.contains(e.target as Node) && !nyito?.contains(e.target as Node)) onbezar();
    };
    window.addEventListener('pointerdown', kivul, true);
    return () => {
      window.removeEventListener('pointerdown', kivul, true);
      if (doboz?.contains(document.activeElement)) visszaad(nyito ?? null);
    };
  });
</script>

<div
  class="elozmeny"
  id="ertesites-elozmeny"
  role="dialog"
  aria-label="Értesítések"
  tabindex="-1"
  bind:this={doboz}
  transition:fly={{ y: 4, duration: ido('gyors') }}
  onkeydown={(e) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      onbezar();
    }
  }}
>
  <header>
    <h2>Értesítések</h2>
    {#if ertesitesek.elozmeny.length}
      <button type="button" class="szoveg-gomb" onclick={() => ertesitesek.elozmenyTorles()}>Törlés</button>
    {/if}
  </header>
  {#if ertesitesek.elozmeny.length}
    <ul role="list">
      {#each ertesitesek.elozmeny as e (e.id)}
        <li class={e.szint}>
          <span class="cim">{e.cim}{#if e.darab > 1}<span class="darab"> ×{e.darab}</span>{/if}</span>
          {#if e.szoveg}<span class="szoveg">{e.szoveg}</span>{/if}
          <time>{idoFormatum.format(e.ido)}</time>
        </li>
      {/each}
    </ul>
  {:else}
    <p class="ures">Ebben a munkamenetben még nem jött értesítés.</p>
  {/if}
</div>

<style>
  .elozmeny {
    position: absolute;
    right: var(--t-2);
    bottom: calc(100% + var(--t-2));
    z-index: var(--reteg-ertesites);
    width: 320px;
    max-height: 360px;
    display: flex;
    flex-direction: column;
    background: var(--hatter-emelt);
    border-radius: var(--kerekites-nagy);
    box-shadow: var(--arnyek-atfedes);
    color: var(--szoveg);
    font-size: var(--betu-ui);
    line-height: var(--sor-ui);
    overflow: hidden;
  }

  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: calc(var(--magassag-fejlec) + var(--keret-vastag));
    padding: 0 var(--t-2) 0 var(--t-4);
    border-bottom: var(--keret-vastag) solid var(--keret);
  }

  h2 {
    margin: 0;
    font-size: var(--betu-ui);
    font-weight: var(--suly-felkover);
  }

  .szoveg-gomb {
    height: var(--magassag-gomb);
    padding: 0 var(--t-2);
    border-radius: var(--kerekites);
    color: var(--akcent-szoveg);
  }

  .szoveg-gomb:hover {
    background: var(--hatter-hover);
  }

  .szoveg-gomb:active {
    background: var(--hatter-aktiv);
  }

  ul {
    margin: 0;
    padding: var(--t-1) 0;
    overflow: auto;
  }

  li {
    display: grid;
    grid-template-columns: 1fr auto;
    column-gap: var(--t-2);
    padding: var(--t-2) var(--t-4);
  }

  li + li {
    border-top: var(--keret-vastag) solid var(--keret);
  }

  .cim {
    font-weight: var(--suly-kozepes);
  }

  .hiba .cim {
    color: var(--hiba);
  }

  .darab {
    color: var(--szoveg-halvany);
    font-weight: var(--suly-normal);
  }

  .szoveg {
    grid-column: 1;
    color: var(--szoveg-masodlagos);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  time {
    grid-column: 2;
    grid-row: 1;
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
    font-variant-numeric: tabular-nums;
  }

  .ures {
    padding: var(--t-4);
    color: var(--szoveg-halvany);
  }
</style>
