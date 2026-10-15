<!-- Név a keresési egyezések kiemelésével. -->
<script lang="ts">
  import { darabol } from '../lib/kereses/fuzzy';

  let { szoveg, kiemeles }: { szoveg: string; kiemeles: [number, number][] } = $props();
</script>

{#each darabol(szoveg, kiemeles) as d, i (i)}{#if d.kiemelt}<mark>{d.szoveg}</mark>{:else}{d.szoveg}{/if}{/each}

<style>
  mark {
    background: none;
    color: var(--kiemeles);
    font-weight: var(--suly-felkover);
  }
</style>
