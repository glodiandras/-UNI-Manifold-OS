<!--
  Modális átfedés (paletta, gyorsváltó): fátyol, középre igazított ablak, fókuszcsapda, Esc és kattintás
  a fátyolra zár. Amíg nyitva van, a globális gyorsbillentyűk közül csak az `atfedesben` jelölésűek élnek.
-->
<script lang="ts">
  import type { Snippet } from 'svelte';
  import { onMount } from 'svelte';
  import { fade } from 'svelte/transition';
  import { ido, gorbe } from '../elrendezes/mozgas';
  import { csapda, fokuszban } from '../fokusz/fokusz';
  import { belep } from '../fokusz/hatokor';

  let {
    cimke,
    nev,
    onbezar,
    children,
    szeles = false,
    szerep = 'dialog',
    leirasId,
  }: { cimke: string; nev: string; onbezar: () => void; children: Snippet; szeles?: boolean; szerep?: 'dialog' | 'alertdialog'; leirasId?: string } = $props();

  const megnyito = fokuszban(); // init közben: a mező autofókusza előtt

  // A hatókör a záró animáció ELEJÉN megszűnik, hogy a közvetlenül utána leütött billentyű már a héjé legyen.
  let kilep = () => {};
  onMount(() => {
    kilep = belep(nev);
    // Esc a fókuszvesztés után is zár (pl. a mező eltűnt, vagy a fókusz az átfedésen kívül maradt: a fájlfa húzása
    // után): az elemszintű kezelő előbb fut, és `preventDefault`-tal jelzi, ha már kezelte
    const esc = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !e.defaultPrevented) {
        e.preventDefault();
        onbezar();
      }
    };
    window.addEventListener('keydown', esc);
    return () => {
      window.removeEventListener('keydown', esc);
      kilep();
    };
  });

  function emelkedes(_: Element, { duration }: { duration: number }) {
    return {
      duration,
      easing: gorbe,
      css: (t: number) => `opacity: ${t}; transform: translateY(${(1 - t) * -4}px) scale(${0.985 + 0.015 * t})`,
    };
  }

  function billentyu(e: KeyboardEvent) {
    if (e.key === 'Escape' && !e.defaultPrevented) {
      e.preventDefault();
      onbezar();
    }
  }
</script>

<div
  class="fatyol"
  role="presentation"
  transition:fade={{ duration: ido('gyors') }}
  onoutrostart={() => kilep()}
  onpointerdown={(e) => {
    if (e.target === e.currentTarget) onbezar();
  }}
>
  <div
    class="ablak"
    class:szeles
    role={szerep}
    aria-modal="true"
    aria-label={cimke}
    aria-describedby={leirasId}
    tabindex="-1"
    use:csapda={megnyito}
    onkeydown={billentyu}
    transition:emelkedes={{ duration: ido('alap') }}
  >
    {@render children()}
  </div>
</div>

<style>
  .fatyol {
    position: fixed;
    inset: 0;
    z-index: var(--reteg-atfedes);
    background: var(--hatter-fatyol);
    display: flex;
    justify-content: center;
    align-items: flex-start;
    padding: 12vh var(--t-4) var(--t-4);
  }

  .ablak {
    width: min(var(--szelesseg-atfedes), 100%);
    max-height: min(560px, 76vh);
    display: flex;
    flex-direction: column;
    background: var(--hatter-emelt);
    border-radius: var(--kerekites-nagy);
    box-shadow: var(--arnyek-atfedes);
    overflow: hidden;
  }

  /* széles változat (a szerkesztő összefésülése, C08) */
  .ablak.szeles {
    width: min(var(--szelesseg-atfedes-szeles), 100%);
    height: 80vh;
    max-height: 80vh;
  }
</style>
