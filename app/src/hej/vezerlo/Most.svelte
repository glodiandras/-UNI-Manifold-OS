<!-- A „Most” szakasz (C17): a futó és várakozó feladatok, alattuk a legutóbbiak. -->
<script lang="ts">
  import { t } from '../../lib/i18n';
  import { feladatsor } from '../../lib/vezerlo/feladatsor.svelte';
  import FeladatSor from './FeladatSor.svelte';
  import Ures from './Ures.svelte';

  let { onnyit }: { onnyit: (id: string) => void } = $props();
  const elo = $derived([...feladatsor.futo, ...feladatsor.sorban]);
  const legutobbi = $derived(feladatsor.legutobbi.filter((f) => f.allapot !== 'torolve').slice(0, 8));
</script>

{#if feladatsor.hiba}
  <p class="hiba" role="alert">{t('A feladatsor nem érhető el: {hiba}', { hiba: feladatsor.hiba })}</p>
{:else if feladatsor.betoltve && !elo.length && !legutobbi.length}
  <Ures szoveg={t('Nem fut és nem vár feladat. Amit a Manifold a háttérben csinál, itt látszik.')} />
{:else}
  {#if elo.length}
    <ul class="lista" aria-label={t('Futó és várakozó feladatok')}>
      {#each elo as f (f.id)}<li><FeladatSor feladat={f} {onnyit} /></li>{/each}
    </ul>
  {:else if feladatsor.betoltve}
    <Ures szoveg={t('Most nem fut feladat.')} />
  {/if}
  {#if legutobbi.length}
    <h3 class="alcim">{t('Legutóbbi')}</h3>
    <ul class="lista" aria-label={t('Legutóbbi feladatok')}>
      {#each legutobbi as f (f.id)}<li><FeladatSor feladat={f} {onnyit} /></li>{/each}
    </ul>
  {/if}
{/if}

<style>
  .lista {
    list-style: none;
    margin: 0;
    padding: 0;
    margin-inline: calc(-1 * var(--t-2));
  }

  .alcim {
    margin: var(--t-3) 0 var(--t-1);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    font-weight: var(--suly-felkover);
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--szoveg-halvany);
  }

  .hiba {
    margin: 0;
    padding: var(--t-2);
    border-radius: var(--kerekites);
    background: var(--hiba-hatter);
    color: var(--hiba);
    font-size: var(--betu-kicsi);
  }
</style>
