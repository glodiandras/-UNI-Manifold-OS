<!--
  Ikonos gomb: a címke kötelező (aria-label + natív tooltip a gyorsbillentyűvel). Állapotok: hover, aktív
  (lenyomva), :focus-visible, és a kapcsoló-állapot (`lenyomva` → aria-pressed).
-->
<script lang="ts">
  import type { IconNode } from 'lucide';
  import type { HTMLButtonAttributes } from 'svelte/elements';
  import Ikon from '../ikon/Ikon.svelte';
  import { ariaAlak, megjelenit } from '../parancsok/billentyuk';

  let {
    ikon,
    cimke,
    billentyu,
    lenyomva,
    kicsi = false,
    ...tobbi
  }: {
    ikon: IconNode;
    cimke: string;
    billentyu?: string;
    lenyomva?: boolean;
    kicsi?: boolean;
  } & Omit<HTMLButtonAttributes, 'aria-label'> = $props();
</script>

<button
  type="button"
  class="ikon-gomb"
  class:kicsi
  aria-label={cimke}
  aria-pressed={lenyomva}
  aria-keyshortcuts={billentyu ? ariaAlak(billentyu) : undefined}
  title={billentyu ? `${cimke} (${megjelenit(billentyu)})` : cimke}
  {...tobbi}
>
  <Ikon {ikon} meret={kicsi ? 14 : 16} />
</button>

<style>
  .ikon-gomb {
    display: inline-grid;
    place-items: center;
    flex: none;
    width: var(--magassag-gomb);
    height: var(--magassag-gomb);
    border-radius: var(--kerekites);
    color: var(--szoveg-halvany);
    transition:
      background-color var(--mozgas-gyors) var(--mozgas-gorbe),
      color var(--mozgas-gyors) var(--mozgas-gorbe);
  }

  .ikon-gomb.kicsi {
    width: var(--magassag-gomb-kicsi);
    height: var(--magassag-gomb-kicsi);
    border-radius: var(--kerekites-kicsi);
  }

  .ikon-gomb:hover {
    background: var(--hatter-hover);
    color: var(--szoveg);
  }

  .ikon-gomb:active {
    background: var(--hatter-aktiv);
    color: var(--szoveg);
  }

  .ikon-gomb[aria-pressed='true'] {
    color: var(--szoveg);
  }

  .ikon-gomb:focus-visible {
    outline-offset: var(--fokusz-tav-befele);
  }

  .ikon-gomb:disabled {
    opacity: var(--tiltott-atlatszosag);
    pointer-events: none;
  }
</style>
