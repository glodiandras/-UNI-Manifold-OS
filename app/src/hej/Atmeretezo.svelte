<!--
  Oldalsáv-szélesség húzással és billentyűzettel (←→ 16 px, ⇧ 48 px, Home/End). role="separator".
  `oldal`: melyik szélén áll a sávnak (bal oldalsáv → 'jobb' szél, jobb panel → 'bal' szél).
-->
<script lang="ts">
  let {
    ertek = $bindable(),
    min,
    max,
    oldal,
    cimke,
    onhuzas,
  }: {
    ertek: number;
    min: number;
    max: number;
    oldal: 'bal' | 'jobb';
    cimke: string;
    onhuzas: (huz: boolean) => void;
  } = $props();

  let huz = $state(false);
  let kezdoX = 0;
  let kezdoErtek = 0;
  const korlat = (x: number) => Math.round(Math.min(max, Math.max(min, x)));

  function le(e: PointerEvent) {
    if (e.button !== 0) return;
    e.preventDefault();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    huz = true;
    kezdoX = e.clientX;
    kezdoErtek = ertek;
    onhuzas(true);
  }

  function mozog(e: PointerEvent) {
    if (!huz) return;
    const d = e.clientX - kezdoX;
    ertek = korlat(kezdoErtek + (oldal === 'jobb' ? d : -d));
  }

  function fel() {
    if (!huz) return;
    huz = false;
    onhuzas(false);
  }

  function billentyu(e: KeyboardEvent) {
    const lepes = e.shiftKey ? 48 : 16;
    const novel = oldal === 'jobb' ? 'ArrowRight' : 'ArrowLeft';
    const csokkent = oldal === 'jobb' ? 'ArrowLeft' : 'ArrowRight';
    if (e.key === novel) ertek = korlat(ertek + lepes);
    else if (e.key === csokkent) ertek = korlat(ertek - lepes);
    else if (e.key === 'Home') ertek = min;
    else if (e.key === 'End') ertek = max;
    else return;
    e.preventDefault();
  }
</script>

<!-- A fókuszálható separator a WAI-ARIA szerint widget (ablaktábla-elválasztó), nem díszítés. -->
<!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
<div
  class="atmeretezo {oldal}"
  class:huz
  role="separator"
  aria-orientation="vertical"
  aria-label={cimke}
  aria-valuenow={ertek}
  aria-valuemin={min}
  aria-valuemax={max}
  tabindex="0"
  onpointerdown={le}
  onpointermove={mozog}
  onpointerup={fel}
  onpointercancel={fel}
  onkeydown={billentyu}
></div>

<style>
  .atmeretezo {
    position: absolute;
    top: 0;
    bottom: 0;
    width: 9px;
    z-index: 5;
    cursor: col-resize;
    touch-action: none;
  }

  .atmeretezo.jobb {
    right: -5px;
  }

  .atmeretezo.bal {
    left: -4px;
  }

  .atmeretezo::after {
    content: '';
    position: absolute;
    top: 0;
    bottom: 0;
    left: 4px;
    width: 1px;
    background: transparent;
    transition: background-color var(--mozgas-gyors) var(--mozgas-gorbe);
  }

  .atmeretezo:hover::after,
  .atmeretezo.huz::after,
  .atmeretezo:focus-visible::after {
    background: var(--akcent);
    box-shadow: 0 0 0 var(--keret-vastag) var(--akcent);
  }

  .atmeretezo:focus-visible {
    outline: none;
  }
</style>
