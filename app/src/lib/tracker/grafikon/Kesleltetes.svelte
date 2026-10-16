<!--
  A késleltetés eloszlása (C27 használati mérés): vödrönként a darabszám, a p50 és a p95 függőleges jelölővel.
  A p95 a vödör felső határa (a core fix vödrös hisztogramot tárol), ezért „legfeljebb” értelmű.
-->
<script lang="ts">
  import { t } from '../../i18n';
  import { szelessegFigyel } from '../szelesseg';
  import { msSzoveg } from '../megjelenites';

  let {
    vedrok,
    hatarok,
    p50,
    p95,
    leiras,
  }: { vedrok: number[]; hatarok: number[]; p50: number | null; p95: number | null; leiras: string } = $props();

  let szel = $state(0);
  const W = $derived(szel > 80 ? Math.floor(szel) : 480);
  const H = 136;
  const FEL = 30; // a p50/p95 feliratok két sora
  const ALSO = 20;
  const max = $derived(Math.max(1, ...vedrok));
  const sav = $derived(W / Math.max(1, vedrok.length));
  const rovid = (n: number) => (n >= 1000 ? `${n / 1000}k` : String(n));
  const cimke = (i: number) => (i < hatarok.length ? rovid(hatarok[i]) : `>${rovid(hatarok[hatarok.length - 1])}`);
  const vedorIdx = (ms: number | null) => {
    if (ms === null) return -1;
    const i = hatarok.findIndex((h) => ms <= h);
    return i === -1 ? hatarok.length : i;
  };
  // azonos vödörbe eső p50 és p95 egy jelölő, egy felirat (különben a feliratok egymásra csúsznának)
  const jel = $derived.by(() => {
    const a = { nev: 'p50', i: vedorIdx(p50), ertek: p50 };
    const b = { nev: 'p95', i: vedorIdx(p95), ertek: p95 };
    if (a.i >= 0 && a.i === b.i) return [{ nev: t('p50 és p95'), i: a.i, ertek: b.ertek }];
    return [a, b].filter((j) => j.i >= 0);
  });
</script>

<div class="hely" use:szelessegFigyel={(w) => (szel = w)}>
<svg class="kes" width={W} height={H} viewBox="0 0 {W} {H}" role="img" aria-label={leiras}>
  <line class="alap" x1="0" x2={W} y1={H - ALSO} y2={H - ALSO} />
  {#each vedrok as db, i (i)}
    {@const h = (db / max) * (H - ALSO - FEL)}
    <g>
      <title>≤ {i < hatarok.length ? hatarok[i] : `>${hatarok[hatarok.length - 1]}`} ms: {db} minta</title>
      {#if db > 0}<rect class="oszlop" x={i * sav + 2} y={H - ALSO - h} width={sav - 4} height={Math.max(h, 1.5)} rx="2" />{/if}
      <text class="cimke" x={i * sav + sav / 2} y={H - 6} text-anchor="middle">{cimke(i)}</text>
    </g>
  {/each}
  {#each jel as j, k (j.nev)}
    {@const x = j.i * sav + sav / 2}
    <line class="jelolo" x1={x} x2={x} y1={12 + k * 12} y2={H - ALSO} />
    <text class="jelszoveg" x={Math.min(Math.max(x, 48), W - 48)} y={10 + k * 12} text-anchor="middle">{j.nev} ≤ {msSzoveg(j.ertek)}</text>
  {/each}
</svg>
</div>

<style>
  .hely {
    width: 100%;
  }

  .kes {
    display: block;
  }

  .alap {
    stroke: var(--keret);
  }

  .oszlop {
    fill: var(--akcent);
    opacity: var(--atlatszosag-felig);
  }

  .jelolo {
    stroke: var(--szoveg);
    stroke-width: 1.2;
    stroke-dasharray: 3 2;
  }

  .cimke,
  .jelszoveg {
    fill: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
    font-variant-numeric: tabular-nums;
  }

  .jelszoveg {
    fill: var(--szoveg);
  }
</style>
