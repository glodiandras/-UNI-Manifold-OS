<!-- Összecsukható szakasz (a jobb panelben): fejléc-gomb aria-expanded-del, a tartalom alatta. -->
<script lang="ts">
  import type { IconNode } from 'lucide';
  import type { Snippet } from 'svelte';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { ChevronRight } from '../lib/ikon/ikonok';

  let { cim, ikon, nyitva = $bindable(), children }: { cim: string; ikon: IconNode; nyitva: boolean; children: Snippet } =
    $props();
  const id = $props.id();
</script>

<section class="szakasz" aria-labelledby="{id}-cim">
  <h2 class="fejlec">
    <button
      type="button"
      id="{id}-cim"
      class="kapcsolo"
      aria-expanded={nyitva}
      aria-controls="{id}-tartalom"
      onclick={() => (nyitva = !nyitva)}
    >
      <span class="nyil" class:nyitva><Ikon ikon={ChevronRight} meret={14} /></span>
      <Ikon {ikon} meret={14} />
      <span class="cim">{cim}</span>
    </button>
  </h2>
  <div id="{id}-tartalom" class="tartalom" hidden={!nyitva}>
    {@render children()}
  </div>
</section>

<style>
  .fejlec {
    margin: 0;
    font: inherit;
  }

  .kapcsolo {
    display: flex;
    align-items: center;
    gap: var(--t-2);
    width: 100%;
    height: var(--magassag-sor);
    padding: 0 var(--t-2);
    border-radius: var(--kerekites);
    color: var(--szoveg-masodlagos);
    font-weight: var(--suly-kozepes);
    transition: background-color var(--mozgas-gyors) var(--mozgas-gorbe);
  }

  .kapcsolo:hover {
    background: var(--hatter-hover);
    color: var(--szoveg);
  }

  .kapcsolo:active {
    background: var(--hatter-aktiv);
  }

  .kapcsolo:focus-visible {
    outline-offset: var(--fokusz-tav-befele);
  }

  .nyil {
    display: grid;
    color: var(--szoveg-halvany);
    transition: transform var(--mozgas-gyors) var(--mozgas-gorbe);
  }

  .nyil.nyitva {
    transform: rotate(90deg);
  }

  .cim {
    flex: 1;
    text-align: left;
  }

  .tartalom {
    padding: var(--t-1) var(--t-2) var(--t-3) var(--t-6);
  }
</style>
