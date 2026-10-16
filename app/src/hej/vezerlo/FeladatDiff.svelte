<!--
  Egy fájl változása a feladat egy commitjában (C17): kétoldalas, csak olvasható összevetés — a commit előtti és utáni
  szöveg. A két szöveget a C11b előzmény-végpont adja (`/api/vault/elozmeny/valtozat`), a rajzolás az előzmények
  diffjével közös (`mergeNezet`). Visszaállítani innen nem lehet: a visszavonás a kör szintjén van.
-->
<script lang="ts">
  import { t } from '../../lib/i18n';
  import type { MergeView } from '@codemirror/merge';
  import { onDestroy, onMount } from 'svelte';
  import Atfedes from '../../lib/ui/Atfedes.svelte';
  import { elozmenyApi, type ElozmenyValtozat } from '../../lib/vault/elozmeny';
  import type { ValtozasFajl } from '../../lib/vezerlo/tipusok';
  import { lf, mergeNezet } from '../kapcsolatok/mergeNezet';

  let { fajl, sha, onbezar }: { fajl: ValtozasFajl; sha: string; onbezar: () => void } = $props();

  let valtozat = $state.raw<ElozmenyValtozat | null>(null);
  let hiba = $state<string | null>(null);
  let hely: HTMLDivElement | undefined = $state();
  let merge: MergeView | null = null;

  onMount(() => {
    elozmenyApi.valtozat(fajl.ut, sha).then(
      (v) => (valtozat = v),
      (e) => (hiba = e instanceof Error ? e.message : String(e)),
    );
  });
  onDestroy(() => merge?.destroy());

  $effect(() => {
    if (!hely || !valtozat) return;
    merge?.destroy();
    merge = mergeNezet(hely, lf(valtozat.elozo), lf(valtozat.szoveg));
    return () => {
      merge?.destroy();
      merge = null;
    };
  });

  const megjegyzes = $derived.by(() => {
    if (!valtozat) return '';
    if (valtozat.szoveg_ok === 'kodolas') return t('A változat nem érvényes UTF-8, az összevetés nem érhető el.');
    if (valtozat.szoveg_ok === 'nagy') return t('A változat túl nagy az összevetéshez.');
    return '';
  });
  const balCim = $derived(fajl.allapot === 'A' ? t('Még nem létezett') : t('A feladat előtt'));
  const jobbCim = $derived(fajl.allapot === 'D' ? t('Törölve lett') : t('A feladat után'));
</script>

<Atfedes cimke={t('A feladat változása egy fájlban')} nev="feladatdiff" {onbezar} szeles>
  <div class="diff">
    <header>
      <h2>{fajl.ut}</h2>
    </header>
    {#if hiba}<p class="hiba" role="alert">{hiba}</p>{/if}
    {#if megjegyzes}<p class="megjegyzes" role="status">{megjegyzes}</p>{/if}
    <div class="oszlopfej" aria-hidden="true"><span>{balCim}</span><span>{jobbCim}</span></div>
    <div class="merge" bind:this={hely}>
      {#if !valtozat && !hiba}<p class="megjegyzes" role="status">{t('Betöltés…')}</p>{/if}
    </div>
    <footer>
      <button type="button" class="m-gomb semleges gomb" onclick={onbezar}>{t('Bezárás')}</button>
    </footer>
  </div>
</Atfedes>

<style>
  .diff {
    display: flex;
    flex-direction: column;
    gap: var(--t-3);
    flex: 1;
    min-height: 0;
    padding: var(--t-5);
  }

  h2 {
    margin: 0;
    font-size: var(--betu-torzs);
    line-height: var(--magassag-suru);
    font-weight: var(--suly-felkover);
    overflow-wrap: anywhere;
  }

  .oszlopfej {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--t-4);
    font-size: var(--betu-kicsi);
    color: var(--szoveg-halvany);
  }

  .merge {
    flex: 1;
    min-height: 280px;
    overflow: auto;
    border: var(--keret-vastag) solid var(--keret);
    border-radius: var(--kerekites);
  }

  .megjegyzes {
    margin: 0;
    padding: var(--t-3);
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
  }

  .hiba {
    margin: 0;
    color: var(--hiba);
  }

  footer {
    display: flex;
    justify-content: flex-end;
  }

</style>
