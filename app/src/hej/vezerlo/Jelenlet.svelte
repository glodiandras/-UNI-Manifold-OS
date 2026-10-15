<!--
  Az OS jelenléte a munkafelületen (TERV 5.3, C17): egy akcent-színű pont (6 px, a MANIFOLD jel után fél em-nyire), amíg feladat fut. Nincs animáció, szám és szöveg;
  a képernyőolvasó a „feladat fut” szöveget kapja.
-->
<script lang="ts">
  import { feladatsor } from '../../lib/vezerlo/feladatsor.svelte';
</script>

{#if feladatsor.aktiv}
  <span class="jelenlet" title="Feladat fut"><span class="pont" aria-hidden="true"></span><span class="sr-only">, feladat fut</span></span>
{/if}

<style>
  .jelenlet {
    display: inline-flex;
    align-items: center;
    margin-left: 0.5em;
  }

  .pont {
    width: 6px;
    height: 6px;
    border-radius: var(--kerekites-kor);
    background: var(--akcent);
  }
</style>
