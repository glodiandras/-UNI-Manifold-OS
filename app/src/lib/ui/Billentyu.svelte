<!-- Gyorsbillentyű megjelenítése (⌘⇧M): a képernyőolvasó a teljes nevet hallja. -->
<script lang="ts">
  import { ariaAlak, megjelenit } from '../parancsok/billentyuk';

  let { akkord }: { akkord: string } = $props();
</script>

<kbd class="billentyu" aria-label={ariaAlak(akkord).replaceAll('+', ' ')}>{megjelenit(akkord)}</kbd>

<style>
  .billentyu {
    display: inline-flex;
    align-items: center;
    height: var(--magassag-gomb-kicsi);
    padding: 0 var(--t-1);
    min-width: var(--magassag-gomb-kicsi);
    justify-content: center;
    border-radius: var(--kerekites-kicsi);
    background: var(--hatter-hover);
    color: var(--szoveg-masodlagos);
    letter-spacing: 0.04em;
    white-space: nowrap;
  }
</style>
