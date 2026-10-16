<!--
  „Undo import” (F8): megerősítés → visszavonás → eredmény. A visszavonás a Kukába tesz (sosem töröl véglegesen); a módosított és az
  idegen fájlok maradnak, és a panel megmondja, melyek. Az eredeti (forrás) vault érintetlen marad. Hibánál ikon + szó + teendő.
-->
<script lang="ts">
  import { onMount, tick } from 'svelte';
  import { CircleCheck, TriangleAlert } from '../lib/ikon/ikonok';
  import { t, tp } from '../lib/i18n';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import HibaPanel from '../lib/ui/HibaPanel.svelte';
  import { importApi } from '../lib/import/api';
  import { importHiba, kodSzoveg, MEGTARTVA_OKA, type ImportHiba } from '../lib/import/megjelenites';
  import type { ImportFajta, VisszaforditasEredmeny } from '../lib/import/tipusok';

  let { id, fajta, onkesz, onmegse }: { id: string; fajta: ImportFajta; onkesz?: (r: VisszaforditasEredmeny) => void; onmegse?: () => void } = $props();

  let fazis = $state<'kerdes' | 'fut' | 'kesz' | 'hiba'>('kerdes');
  let eredmeny = $state<VisszaforditasEredmeny | null>(null);
  let hiba = $state<ImportHiba | null>(null);
  let megseGomb = $state<HTMLButtonElement>();
  let eredmenyElem = $state<HTMLElement>();

  // a biztonságos válasz (az import megtartása) kap fókuszt: a visszavonás külön, tudatos kattintás
  onMount(() => { void tick().then(() => megseGomb?.focus()); });

  async function visszafordit() {
    if (fazis === 'fut') return;
    fazis = 'fut';
    hiba = null;
    try {
      eredmeny = await importApi.visszafordit(id);
      fazis = 'kesz';
      onkesz?.(eredmeny);
      await tick();
      eredmenyElem?.focus();
    } catch (e) {
      hiba = importHiba(e);
      fazis = 'hiba';
    }
  }
</script>

<section class="visszaford" aria-labelledby="visszaford-cim-{id}" data-visszaford={id}>
  {#if fazis === 'kesz' && eredmeny}
    <h4 id="visszaford-cim-{id}" tabindex="-1" bind:this={eredmenyElem}>
      <Ikon ikon={eredmeny.allapot === 'reszben_visszaforditva' ? TriangleAlert : CircleCheck} meret={16} />
      {eredmeny.allapot === 'reszben_visszaforditva' ? t('import.visszaford.reszben') : t('import.visszaford.kesz')}
    </h4>
    {#if fajta === 'v2'}
      <p>{tp('{n} beállításfájl visszaállítva', eredmeny.visszaallitva?.length ?? 0)}</p>
      {#if eredmeny.ujrainditas}<p>{t('import.v2.ujrainditas')}</p>{/if}
    {:else}
      <p>{tp('{n} elem a Kukába került', eredmeny.kukaba?.length ?? 0)}</p>
      {#if eredmeny.megtartva?.length}
        <p>{t('import.visszaford.megtartva_cim')}</p>
        <ul class="megtartva" aria-label={t('import.visszaford.megtartva_lista')}>
          {#each eredmeny.megtartva as m (m.ut)}<li><span class="ut">{m.ut}</span> <span class="halvany">{kodSzoveg(MEGTARTVA_OKA, m.ok, 'import.megtartva.idegen')}</span></li>{/each}
        </ul>
      {/if}
      <p class="halvany">{t('import.forras_erintetlen')}</p>
    {/if}
  {:else if fazis === 'hiba' && hiba}
    <HibaPanel mi={hiba.mi} javitas={hiba.javitas} ujra={() => void visszafordit()} ujraCimke={t('import.ujra')} />
  {:else}
    <h4 id="visszaford-cim-{id}">{t('import.visszaford.kerdes')}</h4>
    {#if fajta === 'v2'}
      <p>{t('import.visszaford.v2_leiras')}</p>
    {:else}
      <p>{t('import.visszaford.leiras')}</p>
      <p class="halvany">{t('import.forras_erintetlen')}</p>
    {/if}
    <div class="gombok">
      <button type="button" class="m-gomb" disabled={fazis === 'fut'} onclick={() => void visszafordit()}>{fazis === 'fut' ? t('import.visszaford.folyamatban') : t('import.visszaford.gomb')}</button>
      <button type="button" class="m-gomb semleges" disabled={fazis === 'fut'} bind:this={megseGomb} onclick={() => onmegse?.()}>{t('import.visszaford.megse')}</button>
    </div>
    {#if fazis === 'fut'}<p role="status" class="halvany">{t('import.visszaford.folyamatban_leiras')}</p>{/if}
  {/if}
</section>

<style>
  .visszaford { display: flex; flex-direction: column; gap: var(--t-2); padding: var(--t-4); background: var(--hatter-oldalsav); border: var(--keret-vastag) solid var(--keret); border-radius: var(--kerekites); }
  h4 { display: flex; align-items: center; gap: var(--t-2); margin: 0; font-size: var(--betu-torzs); font-weight: var(--suly-kozepes); }
  h4:focus { outline: none; }
  p { margin: 0; }
  .halvany { color: var(--szoveg-masodlagos); font-size: var(--betu-kicsi); }
  .gombok { display: flex; flex-wrap: wrap; gap: var(--t-2); }
  .megtartva { margin: 0; padding-inline-start: var(--t-5); }
  .megtartva li { margin-block: var(--t-1); }
  .ut { overflow-wrap: anywhere; user-select: text; }
</style>
