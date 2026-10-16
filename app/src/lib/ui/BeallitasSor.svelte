<script lang="ts">
  import type { Snippet } from 'svelte';

  let { cim, leiras, children }: { cim: string; leiras?: string; children: Snippet } = $props();
</script>

<div class="beallitas-sor">
  <div class="szoveg">
    <div class="cim">{cim}</div>
    {#if leiras}<p>{leiras}</p>{/if}
  </div>
  <div class="vezerlo">{@render children()}</div>
</div>

<style>
  .beallitas-sor { display: flex; align-items: center; justify-content: space-between; gap: var(--t-5); padding: var(--t-4) 0; border-bottom: var(--keret-vastag) solid var(--keret); }
  .szoveg { min-width: 0; }
  .cim { font-weight: var(--suly-kozepes); }
  p { margin: var(--t-1) 0 0; color: var(--szoveg-masodlagos); }
  .vezerlo { flex: none; display: flex; align-items: center; gap: var(--t-2); }
  @media (max-width: 540px) { .beallitas-sor { align-items: flex-start; flex-wrap: wrap; gap: var(--t-2); } }
</style>
