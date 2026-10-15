<script lang="ts">
  import { FilePlus, PanelLeft, Search, LayoutDashboard } from '../lib/ikon/ikonok';
  import { kornyezet } from '../lib/kornyezet';
  import { regiszter } from '../lib/parancsok/regiszter';
  import IkonGomb from '../lib/ui/IkonGomb.svelte';
  import Jelenlet from './vezerlo/Jelenlet.svelte';
  const { felulet } = kornyezet();
</script>
<nav class="ikonsav" aria-label="Gyorsműveletek">
  <IkonGomb ikon={PanelLeft} cimke={felulet.oldalsav.nyitva ? 'Fájlfa elrejtése' : 'Fájlfa megnyitása'} onclick={() => regiszter.futtat('hej.oldalsav', 'gomb')} />
  <IkonGomb ikon={Search} cimke="Keresés a vaultban" billentyu="Mod+Shift+F" onclick={() => regiszter.futtat('kereses.panel', 'gomb')} />
  <IkonGomb ikon={FilePlus} cimke="Új jegyzet" onclick={() => regiszter.futtat('fa.uj-jegyzet', 'gomb')} />
  <div class="also">
    <IkonGomb ikon={LayoutDashboard} cimke="Manifold áttekintő" billentyu="Mod+Shift+M" onclick={() => regiszter.futtat('manifold.vezerlo', 'gomb')} />
    <Jelenlet />
  </div>
</nav>
<style>
  .ikonsav { grid-area: ikon; display: flex; align-items: center; flex-direction: column; padding: var(--t-2) 0; gap: var(--t-2); background: var(--hatter-oldalsav); border-right: var(--keret-vastag) solid var(--keret); }
  .also { margin-top: auto; display: flex; flex-direction: column; align-items: center; gap: var(--t-2); }
</style>
