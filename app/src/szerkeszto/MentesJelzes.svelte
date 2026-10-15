<!--
  A jegyzet jobb alsó sarkának halk mentés-jelzése (E12): „Mentve” a mentés után ~2 s-ig erősebben, utána halványan marad;
  gépelés közben legfeljebb egy halvány pont. A hiba, az ütközés és az eltűnt fájl jele nem ez: az a fejlécben áll, és soha
  nem rejtett (25. döntés). Az állapotgép: `dokumentum/mentesJelzes.ts`.
-->
<script lang="ts">
  import { untrack } from 'svelte';
  import type { Dokumentum } from './dokumentum/dokumentum.svelte';
  import { ERES_MS, LASSU_MS, mentesJelzes } from './dokumentum/mentesJelzes';

  let { dok }: { dok: Dokumentum | null } = $props();

  let most = $state(Date.now());
  let mentesKezdet = $state<number | null>(null);
  let ora: ReturnType<typeof setTimeout> | null = null;

  function oraBeallit(ms: number) {
    if (ora) clearTimeout(ora);
    ora = setTimeout(() => {
      ora = null;
      most = Date.now();
    }, ms + 20);
  }

  // az erősebb „Mentve” lecsengése: a sikeres mentéstől ERES_MS múlva újraértékel
  $effect(() => {
    const m = dok?.utolsoMentes;
    if (!m) return;
    untrack(() => {
      most = Date.now();
      oraBeallit(ERES_MS);
    });
  });

  // a lassú mentés szövege: a mentés kezdetétől LASSU_MS múlva
  $effect(() => {
    if (dok?.allapot === 'mentes') {
      untrack(() => {
        mentesKezdet = Date.now();
        most = mentesKezdet;
        oraBeallit(LASSU_MS);
      });
    } else untrack(() => (mentesKezdet = null));
  });

  $effect(() => () => {
    if (ora) clearTimeout(ora);
  });

  const jelzes = $derived(mentesJelzes(dok?.allapot, dok?.utolsoMentes?.ido ?? null, most, mentesKezdet));
</script>

{#if jelzes.fajta !== 'nincs'}
  <span class="mentes-jelzes {jelzes.fajta}" title={jelzes.cimke} aria-label={jelzes.cimke} data-mentes-jelzes={jelzes.fajta}>
    {#if jelzes.fajta === 'pont'}<span class="pont" aria-hidden="true"></span>{:else}{jelzes.szoveg}{/if}
  </span>
{/if}

<style>
  .mentes-jelzes {
    position: absolute;
    right: var(--t-4);
    bottom: var(--t-2);
    z-index: 1;
    display: inline-flex;
    align-items: center;
    min-height: var(--t-4);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    color: var(--szoveg-halvany);
    pointer-events: none;
    user-select: none;
    transition: color var(--mozgas-lassu) var(--mozgas-gorbe);
  }

  .mentes-jelzes.mentve-eros {
    color: var(--szoveg-masodlagos);
  }

  .pont {
    width: var(--t-1);
    height: var(--t-1);
    border-radius: var(--kerekites-kor);
    background: var(--szoveg-halvany);
  }
</style>
