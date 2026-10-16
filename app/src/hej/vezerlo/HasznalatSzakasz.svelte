<!--
  A vezérlő „Használat” szakasza (C27): a legtöbbet használt parancsok és a p95-ös késleltetés egy pillantásra; a
  teljes nézet a Használat nézet-fülben, az adatok exportja és törlése alul.
-->
<script lang="ts">
  import { t } from '../../lib/i18n';
  import { onMount } from 'svelte';
  import { regiszter } from '../../lib/parancsok/regiszter';
  import Adatkezeles from '../../lib/tracker/Adatkezeles.svelte';
  import { hasznalatVezerlo as modell } from '../../lib/tracker/adat.svelte';
  import { msSzoveg, szamSzoveg } from '../../lib/tracker/megjelenites';

  onMount(() => modell.megjelenik());

  const adat = $derived(modell.adat);

  function reszletek() {
    regiszter.futtat('manifold.hasznalat', 'gomb');
  }
</script>

{#if modell.hiba && !adat}
  <p class="hiba" role="alert">{t('A használati adat nem érhető el: {hiba}', { hiba: modell.hiba })}</p>
{:else if !adat}
  <p class="halvany" role="status">{t('Betöltés…')}</p>
{:else}
  {#if modell.hiba}<p class="hiba" role="alert">{t('A frissítés nem sikerült ({hiba}): a korábban betöltött adat látszik.', { hiba: modell.hiba })}</p>{/if}
  <dl>
    <dt>{t('Gépelés p95')}</dt>
    <dd>{adat.kesleltetes.gepeles.db ? `≤ ${msSzoveg(adat.kesleltetes.gepeles.p95_ms)}` : t('még nincs minta')}</dd>
    <dt>{t('Mentés p95')}</dt>
    <dd>{adat.kesleltetes.mentes.db ? `≤ ${msSzoveg(adat.kesleltetes.mentes.p95_ms)}` : t('még nincs minta')}</dd>
    <dt>{t('Memóriaőr-szünet')}</dt>
    <dd>{szamSzoveg(adat.szunetek.memoria.db)}</dd>
  </dl>
  {#if adat.parancsok.length}
    <ol class="lista">
      {#each adat.parancsok.slice(0, 5) as p (p.parancs)}
        <li><code>{p.parancs}</code><span class="szam">{szamSzoveg(p.db)}</span></li>
      {/each}
    </ol>
  {:else}
    <p class="halvany">{t('Még nincs rögzített parancshasználat.')}</p>
  {/if}
  <button type="button" class="m-gomb semleges gomb" onclick={reszletek}>{t('Részletek')}</button>
  <Adatkezeles />
{/if}

<style>
  dl {
    display: grid;
    grid-template-columns: max-content 1fr;
    gap: var(--t-1) var(--t-3);
    margin: 0 0 var(--t-2);
  }

  dt {
    color: var(--szoveg-halvany);
  }

  dd {
    margin: 0;
    font-variant-numeric: tabular-nums;
  }

  .lista {
    margin: 0 0 var(--t-2);
    padding: 0;
    list-style: none;
  }

  .lista li {
    display: flex;
    justify-content: space-between;
    gap: var(--t-3);
    min-height: var(--magassag-sor);
    align-items: center;
  }

  code {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-family: var(--betu-mono);
    font-size: var(--betu-kicsi);
  }

  .szam {
    font-variant-numeric: tabular-nums;
    color: var(--szoveg-halvany);
  }

  .halvany {
    margin: 0 0 var(--t-2);
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
  }

  .hiba {
    margin: 0;
    padding: var(--t-2);
    border-radius: var(--kerekites);
    background: var(--hiba-hatter);
    color: var(--hiba);
  }

</style>
