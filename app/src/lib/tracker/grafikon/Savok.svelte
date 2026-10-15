<!--
  Vízszintes sávdiagram (C27): tantárgyanként az aktív idő. Saját SVG; a tantárgyakat a felirat különbözteti meg
  (az egyetlen akcentus fokozatai csak segítenek, a jelentést nem hordozzák).
-->
<script lang="ts">
  import { szelessegFigyel } from '../szelesseg';
  interface Sav {
    nev: string;
    ertek: number;
    szoveg: string;
  }

  let { savok, leiras }: { savok: Sav[]; leiras: string } = $props();

  let szel = $state(0);
  const W = $derived(szel > 80 ? Math.floor(szel) : 480);
  const SOR = 24;
  const CIMKE = 112;
  const ERTEK = 64;
  const max = $derived(Math.max(1, ...savok.map((s) => s.ertek)));
  const hossz = $derived(Math.max(40, W - CIMKE - ERTEK));
</script>

<div class="hely" use:szelessegFigyel={(w) => (szel = w)}>
<svg class="savok" width={W} height={Math.max(1, savok.length) * SOR} viewBox="0 0 {W} {Math.max(1, savok.length) * SOR}" role="img" aria-label={leiras}>
  {#each savok as s, i (s.nev)}
    {@const y = i * SOR}
    <g>
      <title>{s.nev}: {s.szoveg}</title>
      <text class="nev" x="0" y={y + 16}>{s.nev}</text>
      <rect class="hatter" x={CIMKE} y={y + 6} width={hossz} height="12" rx="2" />
      {#if s.ertek > 0}
        <rect
          class="sav"
          x={CIMKE}
          y={y + 6}
          width={Math.max(2, (s.ertek / max) * hossz)}
          height="12"
          rx="2"
          style:opacity={Math.max(0.35, 1 - i * 0.14)}
        />
      {/if}
      <text class="ertek" x={W} y={y + 16} text-anchor="end">{s.szoveg}</text>
    </g>
  {/each}
</svg>
</div>

<style>
  .hely {
    width: 100%;
  }

  .savok {
    display: block;
  }

  .nev,
  .ertek {
    fill: var(--szoveg);
    font-size: var(--betu-kicsi);
  }

  .ertek {
    fill: var(--szoveg-halvany);
    font-variant-numeric: tabular-nums;
  }

  .hatter {
    fill: var(--hatter-aktiv);
  }

  .sav {
    fill: var(--akcent);
  }
</style>
