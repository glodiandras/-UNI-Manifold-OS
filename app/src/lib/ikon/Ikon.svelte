<!--
  Egy ikon a Lucide-készletből. Mindig díszítő (aria-hidden): a jelentést a gomb címkéje hordozza.
  Méret: 16 (alap, a felület krómja) vagy 20; a vonal 1,75 — egységesen, a design-rendszer szerint.
-->
<script lang="ts">
  import type { IconNode } from 'lucide';

  let { ikon, meret = 16 }: { ikon: IconNode; meret?: 16 | 20 | 14 } = $props();
</script>

<svg
  class="ikon"
  xmlns="http://www.w3.org/2000/svg"
  width={meret}
  height={meret}
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width={meret === 20 ? 1.6 : 1.75}
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
  focusable="false"
>
  {#each ikon as [tag, attrs], i (i)}
    <svelte:element this={tag} {...attrs} />
  {/each}
</svg>

<style>
  .ikon {
    display: block;
    flex: none;
  }
</style>
