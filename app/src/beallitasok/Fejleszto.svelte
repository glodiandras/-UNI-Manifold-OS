<!--
  Settings › Developer (F7): a technikai nézetek — naplók, nyers diagnosztika, homokozó, modell-részletek, teszt-futtató, git. Csak
  Developer módban érhető el (a nav és a parancs is elrejti). Az adat valós: a Health jelentés, a Privacy állapot, a core végpontjai.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { adatvedelem } from '../lib/adatvedelem/allapot.svelte';
  import { meretSzoveg } from '../lib/adatvedelem/megjelenites';
  import { egeszseg } from '../lib/egeszseg/allapot.svelte';
  import { t } from '../lib/i18n';
  import { epitesAllapot } from '../lib/vezerlo/epites.svelte';
  import ImportSzakasz from '../import/ImportSzakasz.svelte';

  let { szakasz, onnyit, oneszeg }: { szakasz: string; onnyit: (cel: string) => void; oneszeg: (kod?: string) => void } = $props();

  let masolva = $state(false);
  onMount(() => {
    void adatvedelem.betolt();
    if (!egeszseg.adat) void egeszseg.betolt();
    void epitesAllapot.frissit();
  });
  const jelentes = $derived(egeszseg.adat ? JSON.stringify(egeszseg.adat, null, 2) : '');
  const hely = (kod: string) => adatvedelem.adat?.adat.find((h) => h.kod === kod);
  const tarak = $derived(egeszseg.adat?.ellenorzesek.find((s) => s.kod === 'pillanatkep')?.reszletek.find((r) => r.kulcs === 'tarak')?.ertek);

  async function masol() {
    try {
      await navigator.clipboard.writeText(jelentes);
      masolva = true;
    } catch {
      masolva = false;
    }
  }
</script>

<section class="fejleszto" data-fejleszto={szakasz}>
  {#if szakasz === 'fejleszto_naplok'}
    <p class="leiras">{t('fejleszto.naplok.leiras')}</p>
    <dl><dt>{t('fejleszto.naplok.mappa')}</dt><dd>{hely('logs')?.ut ?? '–'}</dd></dl>
    <button type="button" class="m-gomb semleges" onclick={() => onnyit('most')}>{t('fejleszto.naplok.feladatok')}</button>
  {:else if szakasz === 'fejleszto_diagnosztika'}
    <p class="leiras">{t('fejleszto.diagnosztika.leiras')}</p>
    <div class="gombok">
      <button type="button" class="m-gomb semleges" disabled={egeszseg.betoltes} onclick={() => egeszseg.betolt()}>{t('egeszseg.ujra')}</button>
      <button type="button" class="m-gomb semleges" disabled={!jelentes} onclick={masol}>{t('fejleszto.diagnosztika.masol')}</button>
      <button type="button" class="m-gomb semleges" onclick={() => oneszeg()}>{t('egeszseg.parancs')}</button>
    </div>
    {#if masolva}<p role="status" class="leiras">{t('fejleszto.diagnosztika.masolva')}</p>{/if}
    {#if egeszseg.hiba}<p class="hiba" role="alert">{egeszseg.hiba}</p>{/if}
    {#if jelentes}<pre data-nyers>{jelentes}</pre>{/if}
    {#if epitesAllapot.adat}
      <h3>{t('fejleszto.diagnosztika.build')}</h3>
      <dl>{#each epitesAllapot.adat.reszek as r}<dt>{r.resz}</dt><dd>{r.azonosito || '–'}{r.friss ? '' : ` (${t('fejleszto.diagnosztika.elavult')})`}</dd>{/each}</dl>
    {/if}
  {:else if szakasz === 'fejleszto_homokozo'}
    <p>{t('fejleszto.homokozo.leiras')}</p>
    <p class="leiras">{t('fejleszto.homokozo.halozat')}</p>
  {:else if szakasz === 'fejleszto_modell'}
    <p class="leiras">{t('fejleszto.modell.leiras')}</p>
    {#if adatvedelem.adat}
      {#if adatvedelem.adat.modellek.telepitve.length}
        <ul role="list">
          {#each adatvedelem.adat.modellek.telepitve as m (m.nev)}
            <li><strong>{m.nev}</strong> <span class="leiras">{m.repo} · {m.feladat.join(', ')} · {m.allapot} · {meretSzoveg(m.bajt)}</span></li>
          {/each}
        </ul>
      {:else}<p class="leiras">{t('fejleszto.modell.nincs')}</p>{/if}
      <dl><dt>{t('fejleszto.modell.mappa')}</dt><dd>{adatvedelem.adat.modellek.ut ?? '–'}</dd></dl>
    {/if}
    <button type="button" class="m-gomb semleges" onclick={() => onnyit('modellek')}>{t('privacy.modellek_megnyit')}</button>
  {:else if szakasz === 'fejleszto_teszt'}
    <p class="leiras">{t('fejleszto.teszt.leiras')}</p>
    <pre>bin/mos test
bin/mos app test</pre>
  {:else if szakasz === 'fejleszto_import'}
    <ImportSzakasz fajta="v2" />
  {:else if szakasz === 'fejleszto_git'}
    <p class="leiras">{t('fejleszto.git.leiras')}</p>
    <dl>
      <dt>{t('fejleszto.git.tarak')}</dt><dd>{tarak ?? '–'}</dd>
      <dt>{t('fejleszto.git.mappa')}</dt><dd>{hely('snapshots')?.ut ?? '–'}</dd>
    </dl>
  {/if}
</section>

<style>
  .fejleszto { display: flex; flex-direction: column; gap: var(--t-3); }
  p, h3 { margin: 0; }
  h3 { font-size: var(--betu-torzs); font-weight: var(--suly-kozepes); }
  .leiras { color: var(--szoveg-masodlagos); font-size: var(--betu-kicsi); }
  .gombok { display: flex; flex-wrap: wrap; gap: var(--t-2); }
  dl { display: grid; grid-template-columns: max-content 1fr; gap: var(--t-1) var(--t-4); margin: 0; }
  dt { color: var(--szoveg-masodlagos); }
  dd { margin: 0; overflow-wrap: anywhere; user-select: text; }
  ul { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: var(--t-2); }
  pre { margin: 0; padding: var(--t-3); background: var(--hatter-kod); color: var(--kod-szoveg); font-family: var(--betu-mono); font-size: var(--betu-kicsi); overflow: auto; max-height: 40vh; user-select: text; }
  .hiba { color: var(--hiba); }
</style>
