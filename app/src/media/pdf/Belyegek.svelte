<!--
  A PDF oldalbélyegei (C16): csak a látszó bélyeg rajzolódik (IntersectionObserver), kis felbontásban, és legfeljebb
  `MAX_RAJZOLT` vászon él egyszerre (a legrégebben látott ürül) — a 600 lapos tankönyv sem foglal sok memóriát, és a
  nagy fájlból csak a látszó lapok bájtjai töltődnek (Range). Kattintás vagy ↩ a lapra ugrik; ↑↓ léptet.
-->
<script lang="ts">
  import { t } from '../../lib/i18n';
  import type { PDFDocumentProxy, RenderTask } from 'pdfjs-dist';
  import { onMount, tick } from 'svelte';

  let { dok, oldal, onvalaszt }: { dok: PDFDocumentProxy; oldal: number; onvalaszt: (n: number) => void } = $props();

  const SZELESSEG = 112;
  const MAX_RAJZOLT = 40;

  let lista = $state<HTMLElement | null>(null);
  let arany = $state(1.414);
  const aranyok = $state<Record<number, number>>({});
  const oldalak = $derived(Array.from({ length: dok.numPages }, (_, i) => i + 1));
  const rajzolt = new Map<number, HTMLCanvasElement>(); // beszúrási sorrend = LRU
  const folyamatban = new Map<number, RenderTask>();
  /** a már elkezdett (a getPage-re váró) bélyegek: két IntersectionObserver-jelzés ne indítson két render()-t egy vászonra (T067) */
  const kezdett = new Set<number>();
  let figyelo: IntersectionObserver | null = null;

  async function rajzol(n: number, vaszon: HTMLCanvasElement) {
    if (rajzolt.has(n) || kezdett.has(n)) {
      if (rajzolt.has(n)) {
        rajzolt.delete(n);
        rajzolt.set(n, vaszon);
      }
      return;
    }
    kezdett.add(n);
    try {
      const lap = await dok.getPage(n);
      const alap = lap.getViewport({ scale: 1 });
      aranyok[n] = alap.height / alap.width;
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const vp = lap.getViewport({ scale: (SZELESSEG * dpr) / alap.width });
      vaszon.width = Math.round(vp.width);
      vaszon.height = Math.round(vp.height);
      const feladat = lap.render({ canvas: vaszon, viewport: vp });
      folyamatban.set(n, feladat);
      await feladat.promise;
      rajzolt.set(n, vaszon);
      while (rajzolt.size > MAX_RAJZOLT) {
        const [regi, v] = rajzolt.entries().next().value as [number, HTMLCanvasElement];
        rajzolt.delete(regi);
        v.width = 0;
        v.height = 0;
      }
    } catch {
      /* megszakítva vagy hibás lap: a bélyeg üres marad */
    } finally {
      folyamatban.delete(n);
      kezdett.delete(n);
    }
  }

  onMount(() => {
    void dok.getPage(1).then((l) => {
      const v = l.getViewport({ scale: 1 });
      arany = v.height / v.width;
    });
    figyelo = new IntersectionObserver(
      (bejegyzesek) => {
        for (const b of bejegyzesek) {
          if (!b.isIntersecting) continue;
          const el = b.target as HTMLElement;
          const v = el.querySelector('canvas');
          if (v) void rajzol(Number(el.dataset.n), v);
        }
      },
      { root: lista, rootMargin: '200px 0px' },
    );
    for (const el of lista?.querySelectorAll('[data-n]') ?? []) figyelo.observe(el);
    return () => {
      figyelo?.disconnect();
      for (const f of folyamatban.values()) f.cancel();
      for (const v of rajzolt.values()) {
        v.width = 0;
        v.height = 0;
      }
      rajzolt.clear();
    };
  });

  function figyel(el: HTMLElement) {
    figyelo?.observe(el);
    return { destroy: () => figyelo?.unobserve(el) };
  }

  // az aktuális lap bélyege látszódjon
  $effect(() => {
    const n = oldal;
    void tick().then(() => lista?.querySelector<HTMLElement>(`[data-n="${n}"]`)?.scrollIntoView({ block: 'nearest' }));
  });

  function billentyu(e: KeyboardEvent, n: number) {
    const cel = e.key === 'ArrowDown' ? n + 1 : e.key === 'ArrowUp' ? n - 1 : e.key === 'Home' ? 1 : e.key === 'End' ? dok.numPages : 0;
    if (!cel || cel < 1 || cel > dok.numPages) return;
    e.preventDefault();
    lista?.querySelector<HTMLButtonElement>(`[data-n="${cel}"] button`)?.focus();
    onvalaszt(cel);
  }
</script>

<nav class="belyegek" bind:this={lista} aria-label={t('Oldalbélyegek')}>
  <ol>
    {#each oldalak as n (n)}
      <li data-n={n} use:figyel>
        <button
          type="button"
          class:aktualis={n === oldal}
          aria-current={n === oldal ? 'page' : undefined}
          aria-label={t('{n}. oldal', { n })}
          tabindex={n === oldal ? 0 : -1}
          onclick={() => onvalaszt(n)}
          onkeydown={(e) => billentyu(e, n)}
        >
          <canvas style:width="{SZELESSEG}px" style:aspect-ratio={`1 / ${aranyok[n] ?? arany}`}></canvas>
          <span class="szam">{n}</span>
        </button>
      </li>
    {/each}
  </ol>
</nav>

<style>
  .belyegek {
    height: 100%;
    overflow-y: auto;
    background: var(--hatter-oldalsav);
    border-right: 1px solid var(--keret);
  }

  ol {
    margin: 0;
    padding: var(--t-3) 0;
    list-style: none;
  }

  button {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--t-1);
    width: 100%;
    padding: var(--t-2) var(--t-3);
    border: none;
    background: none;
    cursor: pointer;
    font: inherit;
  }

  canvas {
    display: block;
    height: auto;
    background: var(--pdf-lap);
    border-radius: var(--kerekites-jel);
    box-shadow: 0 0 0 var(--keret-vastag) var(--keret);
  }

  button:hover canvas {
    box-shadow: 0 0 0 var(--keret-vastag) var(--keret-eros);
  }

  button.aktualis canvas {
    box-shadow: 0 0 0 var(--jel-vastag) var(--akcent);
  }

  button:focus-visible {
    outline: var(--fokusz-vastag) solid var(--fokusz-gyuru);
    outline-offset: var(--fokusz-tav-befele);
  }

  .szam {
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    color: var(--szoveg-halvany);
    font-variant-numeric: tabular-nums;
  }

  .aktualis .szam {
    color: var(--szoveg);
  }
</style>
