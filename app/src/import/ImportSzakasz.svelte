<!--
  Az import szakasza a Settingsben: bevezető, „Import…” indító és az importok listája. A Files & links alatt az Obsidian-import
  él; a Developer › „Import from Manifold v2” szakaszban a v2-import (a hívó kapuja: csak Developer módban jelenik meg).
-->
<script lang="ts">
  import { untrack } from 'svelte';
  import { t } from '../lib/i18n';
  import { ImportTar } from '../lib/import/allapot.svelte';
  import type { CoreKapcsolat } from '../lib/core/ws.svelte';
  import type { ImportAllapot, ImportFajta } from '../lib/import/tipusok';
  import ImportFolyamat from './ImportFolyamat.svelte';
  import ImportLista from './ImportLista.svelte';

  let { fajta = 'obsidian', tar: kivulrol, kapcsolat, valaszto }: {
    fajta?: ImportFajta;
    tar?: ImportTar;
    kapcsolat?: CoreKapcsolat | null;
    valaszto?: (cim: string) => Promise<string | null>;
  } = $props();

  const tar = untrack(() => kivulrol ?? new ImportTar(fajta));
  const v2 = tar.fajta === 'v2';
  let nyitva = $state(false);
  let elozmeny = $state(v2);

  function indit() {
    if (tar.fazis === 'kesz') tar.ujKezdes();
    nyitva = true;
  }

  async function folytat(a: ImportAllapot) {
    nyitva = true;
    await tar.folytatBol(a);
  }
</script>

<section class="import" data-import-szakasz={tar.fajta}>
  {#if nyitva}
    <ImportFolyamat {tar} {kapcsolat} {valaszto} onbezar={() => { nyitva = false; elozmeny = true; }} onkesz={() => { nyitva = false; elozmeny = true; }} />
  {:else}
    <h3>{v2 ? t('import.v2.cim') : t('import.cim')}</h3>
    <p>{v2 ? t('import.v2.leiras') : t('import.leiras')}</p>
    <p class="halvany">{v2 ? t('import.v2.forras_erintetlen') : t('import.forras_erintetlen')}</p>
    <div class="gombok">
      <button type="button" class="m-gomb semleges" onclick={indit}>{tar.fazis === 'fut' ? t('import.fut.megtekint') : v2 ? t('import.v2.gomb') : t('import.gomb')}</button>
      {#if !v2}<button type="button" class="m-gomb link" aria-expanded={elozmeny} onclick={() => (elozmeny = !elozmeny)}>{elozmeny ? t('import.lista.elrejt') : t('import.lista.mutat')}</button>{/if}
    </div>
    {#if elozmeny}<ImportLista fajta={tar.fajta} {kapcsolat} onfolytat={(a) => void folytat(a)} />{/if}
  {/if}
</section>

<style>
  .import { display: flex; flex-direction: column; gap: var(--t-3); }
  h3 { margin: 0; font-size: var(--betu-h4); font-weight: var(--suly-kozepes); }
  p { margin: 0; }
  .halvany { color: var(--szoveg-masodlagos); font-size: var(--betu-kicsi); }
  .gombok { display: flex; flex-wrap: wrap; gap: var(--t-2); }
</style>
