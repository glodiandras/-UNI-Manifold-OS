<script lang="ts">
  import { modulEngedelyezett } from '../lib/beallitasok/allapot.svelte';
  import { t } from '../lib/i18n';
  import { FilePlus, PanelLeft, Search, Settings, LayoutDashboard } from '../lib/ikon/ikonok';
  import { kornyezet } from '../lib/kornyezet';
  import { regiszter } from '../lib/parancsok/regiszter';
  import IkonGomb from '../lib/ui/IkonGomb.svelte';
  import Jelenlet from './vezerlo/Jelenlet.svelte';
  const { felulet } = kornyezet();
</script>
<nav class="ikonsav" aria-label={t('Gyorsműveletek')}>
  <IkonGomb ikon={PanelLeft} cimke={felulet.oldalsav.nyitva ? t('Fájlfa elrejtése') : t('Fájlfa megnyitása')} onclick={() => regiszter.futtat('hej.oldalsav', 'gomb')} />
  {#if modulEngedelyezett('kereses')}
  <IkonGomb ikon={Search} cimke={t('Keresés a vaultban')} billentyu="Mod+Shift+F" onclick={() => regiszter.futtat('kereses.panel', 'gomb')} />
  {/if}
  <IkonGomb ikon={FilePlus} cimke={t('Új jegyzet')} onclick={() => regiszter.futtat('fa.uj-jegyzet', 'gomb')} />
  <div class="also">
    <IkonGomb ikon={LayoutDashboard} cimke={t('Manifold áttekintő')} billentyu="Mod+Shift+M" onclick={() => regiszter.futtat('manifold.vezerlo', 'gomb')} />
    <IkonGomb ikon={Settings} cimke={t('beallitasok.cim')} billentyu="Mod+," onclick={() => regiszter.futtat('beallitasok.megnyit', 'gomb')} />
    {#if modulEngedelyezett('asszisztens')}<Jelenlet />{/if}
  </div>
</nav>
<style>
  .ikonsav { grid-area: ikon; display: flex; align-items: center; flex-direction: column; padding: var(--t-2) 0; gap: var(--t-2); background: var(--hatter-oldalsav); border-right: var(--keret-vastag) solid var(--keret); }
  .also { margin-top: auto; display: flex; flex-direction: column; align-items: center; gap: var(--t-2); }
</style>
