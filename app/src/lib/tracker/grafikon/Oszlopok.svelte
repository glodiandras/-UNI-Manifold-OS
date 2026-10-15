<!--
  Oszlopdiagram (C27): napi vagy heti aktív idő; a naptár tervezett tanulási ideje vékony jelölő az oszlop fölött. Saját SVG,
  csak a meglévő tokenekből (`--akcent`, `--keret`, `--szoveg-halvany`): a téma-átváltást a CSS változók viszik.
  A szám mindig szövegben is látszik (a nézet táblázata); a `<title>` a hoverhez és a képernyőolvasóhoz.
-->
<script lang="ts">
  import { szelessegFigyel } from '../szelesseg';
  import { idoSzoveg } from '../megjelenites';

  interface Oszlop {
    cimke: string;
    ertek: number;
    terv?: number;
    cim: string;
  }

  let { oszlopok, kompakt = false, leiras }: { oszlopok: Oszlop[]; kompakt?: boolean; leiras: string } = $props();

  let szel = $state(0); // a tartály szélessége: a rajz 1:1 méretű (a szöveg nem kicsinyedik)
  const W = $derived(szel > 80 ? Math.floor(szel) : kompakt ? 280 : 480);
  const H = $derived(kompakt ? 64 : 168);
  const ALSO = $derived(kompakt ? 16 : 22); // a tengelycímkék helye
  const TETEJE = $derived(kompakt ? 6 : 18); // a nem kompakt rajzon a felső sávban a maximum felirata áll
  const max = $derived(Math.max(1, ...oszlopok.map((o) => Math.max(o.ertek, o.terv ?? 0))));
  const savSzel = $derived(W / Math.max(1, oszlopok.length));
  const oszlopSzel = $derived(Math.min(savSzel * 0.62, kompakt ? 22 : 44));
  const magassag = (v: number) => (v / max) * (H - ALSO - TETEJE);
</script>

<div class="hely" use:szelessegFigyel={(w) => (szel = w)}>
<svg class="oszlopok" width={W} height={H} viewBox="0 0 {W} {H}" role="img" aria-label={leiras}>
  <line class="alap" x1="0" x2={W} y1={H - ALSO} y2={H - ALSO} />
  {#each oszlopok as o, i (i)}
    {@const x = i * savSzel + (savSzel - oszlopSzel) / 2}
    {@const h = magassag(o.ertek)}
    <g>
      <title>{o.cim}</title>
      <rect class="sav" x={i * savSzel} y="0" width={savSzel} height={H - ALSO} />
      {#if o.ertek > 0}
        <rect class="oszlop" {x} y={H - ALSO - h} width={oszlopSzel} height={Math.max(h, 1.5)} rx="2" />
      {/if}
      {#if o.terv}
        <line class="terv" x1={x - 2} x2={x + oszlopSzel + 2} y1={H - ALSO - magassag(o.terv)} y2={H - ALSO - magassag(o.terv)} />
      {/if}
      <text class="cimke" x={i * savSzel + savSzel / 2} y={H - 5} text-anchor="middle">{o.cimke}</text>
    </g>
  {/each}
  {#if !kompakt && oszlopok.some((o) => o.ertek > 0 || (o.terv ?? 0) > 0)}
    <!-- csupa nulla mellett nincs skála (a „1 mp” csak a nullával osztás elleni alsó határ; C32) -->
    <text class="max" x="0" y="11">{idoSzoveg(max)}</text>
  {/if}
</svg>
</div>

<style>
  .hely {
    width: 100%;
  }

  .oszlopok {
    display: block;
    overflow: visible;
  }

  .alap {
    stroke: var(--keret);
    stroke-width: 1;
  }

  .sav {
    fill: transparent;
  }

  .sav:hover {
    fill: var(--hatter-aktiv);
  }

  .oszlop {
    fill: var(--akcent);
  }

  .terv {
    stroke: var(--szoveg-halvany);
    stroke-width: 1.5;
    stroke-dasharray: 3 2;
  }

  .cimke,
  .max {
    fill: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
    font-variant-numeric: tabular-nums;
  }
</style>
