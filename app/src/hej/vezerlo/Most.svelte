<!-- A „Most” szakasz (C17): a futó és várakozó feladatok, alattuk a legutóbbiak. -->
<script lang="ts">
  import { t } from '../../lib/i18n';
  import { feladatsor } from '../../lib/vezerlo/feladatsor.svelte';
  import type { Feladat } from '../../lib/vezerlo/tipusok';
  import FeladatSor from './FeladatSor.svelte';
  import Ures from './Ures.svelte';
  import UresAllapot from '../../lib/ui/UresAllapot.svelte';
  import HibaPanel from '../../lib/ui/HibaPanel.svelte';
  import { egeszsegMegnyit } from '../../lib/egeszseg/allapot.svelte';
  import { modulEngedelyezett } from '../../lib/beallitasok/allapot.svelte';
  import { fejlesztoMod } from '../../lib/beallitasok/fejleszto';
  import { Activity } from '../../lib/ikon/ikonok';
  import { regiszter } from '../../lib/parancsok/regiszter';

  let { onnyit }: { onnyit: (id: string) => void } = $props();
  const elo = $derived([...feladatsor.futo, ...feladatsor.sorban]);
  const reszletes = $derived(fejlesztoMod());
  let elozmenyekNyitva = $state(false);
  const figyelmetKer = (f: Feladat) => f.allapot === 'hiba' || f.allapot === 'megszakadt' || f.figyelmeztetes.length > 0;
  const legutobbi = $derived(feladatsor.legutobbi.filter((f) => f.allapot !== 'torolve'
    && (reszletes || figyelmetKer(f))).slice(0, 8));
  const csendesElozmenyek = $derived(reszletes ? [] : feladatsor.legutobbi.filter(f => f.allapot !== 'torolve' && !figyelmetKer(f)).slice(0, 8));
</script>

{#if feladatsor.hiba}
  <HibaPanel mi={t('A feladatsor nem érhető el: {hiba}', { hiba: feladatsor.hiba })} javitas={t('rendszer.hiba_javitas')} diagnosztika={() => egeszsegMegnyit('folyamatok')} />
{:else if feladatsor.betoltve && !elo.length && !legutobbi.length && !csendesElozmenyek.length}
  <UresAllapot kicsi ikon={Activity} cim={t('ures.most_cim')} leiras={t('Nem fut és nem vár feladat. Amit a Manifold a háttérben csinál, itt látszik.')} muvelet={modulEngedelyezett('video') ? { cimke: t('ures.video_hozzaadas'), onclick: () => regiszter.futtat('video.link', 'gomb') } : undefined} />
{:else}
  {#if elo.length}
    <ul class="lista" aria-label={t('Futó és várakozó feladatok')}>
      {#each elo as f (f.id)}<li><FeladatSor feladat={f} {onnyit} /></li>{/each}
    </ul>
  {:else if feladatsor.betoltve}
    <Ures szoveg={t('Most nem fut feladat.')} />
  {/if}
  {#if legutobbi.length}
    <h3 class="alcim">{reszletes ? t('Legutóbbi') : t('Figyelmet igényel')}</h3>
    <ul class="lista" aria-label={reszletes ? t('Legutóbbi feladatok') : t('Figyelmet igénylő feladatok')}>
      {#each legutobbi as f (f.id)}<li><FeladatSor feladat={f} {onnyit} /></li>{/each}
    </ul>
  {/if}
  {#if csendesElozmenyek.length}
    <details class="elozmenyek" bind:open={elozmenyekNyitva}>
      <summary>{t('Legutóbbi feladatok')}</summary>
      {#if elozmenyekNyitva}
        <ul class="lista" aria-label={t('Legutóbbi feladatok')}>
          {#each csendesElozmenyek as f (f.id)}<li><FeladatSor feladat={f} {onnyit} /></li>{/each}
        </ul>
      {/if}
    </details>
  {/if}
{/if}

<style>
  .elozmenyek { margin-top: var(--t-3); }
  summary { cursor: pointer; color: var(--szoveg-masodlagos); font-size: var(--betu-kicsi); line-height: var(--magassag-gomb); }
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
</style>
