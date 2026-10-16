<!--
  Settings › AI › Models (Model Manager): a modellek listája szerep és nyelv szerint, telepítettség a lemezről, letöltés
  folyamatjelzővel és megszakítással, törlés megerősítéssel, „Test this model”. A betöltés semmit nem tölt le: a letöltés
  és a mérés csak kattintásra indul (D3). A haladás a feladatsor WS-eseményein érkezik (a lassú felület sem marad le: letöltés
  közben a feladatsort kis késleltetéssel újraolvassa).
-->
<script lang="ts">
  import { onDestroy, onMount, untrack } from 'svelte';
  import { Cpu } from 'lucide';
  import { t } from '../lib/i18n';
  import { modellek as alapTar, type ModellTar } from '../lib/modellek/allapot.svelte';
  import { SZEREP_CIM, nyelvNev, tobbnyelvu } from '../lib/modellek/megjelenites';
  import HibaPanel from '../lib/ui/HibaPanel.svelte';
  import UresAllapot from '../lib/ui/UresAllapot.svelte';
  import Ajanlott from './Ajanlott.svelte';
  import ModellSor from './ModellSor.svelte';

  let { tar = alapTar, oneszeg, onkalibracio }: {
    tar?: ModellTar;
    /** A Health oldal megnyitása (a hibapanel „Open diagnostics” gombja). */
    oneszeg?: () => void;
    /** A Calibration szakasz megnyitása (saját aranyhalmaz). */
    onkalibracio?: () => void;
  } = $props();

  let szerep = $state('');
  let nyelv = $state('');

  const szerepek = $derived([...new Set(tar.modellek.map((m) => m.szerep))].sort());
  const nyelvek = $derived([...new Set(tar.modellek.flatMap((m) => m.nyelvek).filter((n) => n !== '*'))].sort());
  const lathato = $derived(tar.modellek.filter((m) => (!szerep || m.szerep === szerep) && (!nyelv || tobbnyelvu(m) || m.nyelvek.includes(nyelv))));
  const csoportok = $derived([...new Set(lathato.map((m) => m.szerep))].sort((a, b) => (a === 'szoveg' ? -1 : b === 'szoveg' ? 1 : a.localeCompare(b))));

  onMount(() => {
    void tar.betolt();
    void tar.halmazokBetolt();
  });
  // a befejezett letöltések és mérések lezárása a feladatsor friss állapotából
  $effect(() => {
    const lista = tar.feladatsor.lista;
    void tar.kovetes;
    untrack(() => void tar.szinkron(lista));
  });
  // WS nélkül (vagy elmaradt esemény mellett) a követett feladatok állapotát lassan újraolvassuk, csak amíg van ilyen
  let ido: ReturnType<typeof setInterval> | null = null;
  $effect(() => {
    if (tar.dolgozik && !ido) ido = setInterval(() => void tar.feladatsor.betolt(), 3000);
    else if (!tar.dolgozik && ido) { clearInterval(ido); ido = null; }
  });
  onDestroy(() => { if (ido) clearInterval(ido); });
</script>

<section class="modellkezelo" data-modellkezelo>
  <p class="leiras">{t('modellek.leiras')}</p>
  {#if tar.lista?.keretek && Object.keys(tar.lista.keretek).length}
    <p class="leiras">{t('Az AI memóriakerete: {munka} GB munka közben, {tavol} GB távollétben.', { munka: tar.lista.keretek.munka ?? '–', tavol: tar.lista.keretek.tavol ?? '–' })}</p>
  {/if}

  {#if tar.hiba && !tar.lista}
    <HibaPanel mi={tar.hiba} javitas={t('modellek.hiba_javitas')} ujra={() => tar.betolt()} diagnosztika={oneszeg} />
  {:else if !tar.lista}
    <p role="status" class="leiras">{t('modellek.betoltes')}</p>
  {:else if tar.modellek.length === 0}
    <UresAllapot ikon={Cpu} cim={t('modellek.ures')} leiras={t('modellek.ures_leiras')} muvelet={{ cimke: t('modellek.ujratolt'), onclick: () => void tar.betolt() }} />
  {:else}
    <div class="blokk">
      <h3>{t('modellek.ajanlott.cim')}</h3>
      <Ajanlott {tar} />
    </div>

    <div class="szuro" role="group" aria-label={t('modellek.szuro')}>
      <label>{t('modellek.szuro.szerep')}
        <select bind:value={szerep}>
          <option value="">{t('modellek.szuro.mind')}</option>
          {#each szerepek as s (s)}<option value={s}>{SZEREP_CIM[s] ? t(SZEREP_CIM[s]) : s}</option>{/each}
        </select>
      </label>
      <label>{t('modellek.szuro.nyelv')}
        <select bind:value={nyelv}>
          <option value="">{t('modellek.szuro.minden_nyelv')}</option>
          {#each nyelvek as n (n)}<option value={n}>{nyelvNev(n)}</option>{/each}
        </select>
      </label>
      <button type="button" class="m-gomb semleges" disabled={tar.betoltes} onclick={() => void tar.betolt()}>{t('modellek.ujratolt')}</button>
    </div>
    {#if tar.hiba}<p class="hiba" role="alert">{tar.hiba}</p>{/if}

    {#if lathato.length === 0}
      <UresAllapot kicsi cim={t('modellek.nincs_talalat')} leiras={t('modellek.nincs_talalat_leiras')} muvelet={{ cimke: t('modellek.szuro.torol'), onclick: () => { szerep = ''; nyelv = ''; } }} />
    {/if}
    {#each csoportok as cs (cs)}
      <h3 class="csoport">{SZEREP_CIM[cs] ? t(SZEREP_CIM[cs]) : cs}</h3>
      <ul class="lista">
        {#each lathato.filter((m) => m.szerep === cs) as m (m.id)}<ModellSor {m} {tar} />{/each}
      </ul>
    {/each}

    {#if onkalibracio}
      <p class="leiras">{t('modellek.kalibracio_hint')} <button type="button" class="m-gomb link" onclick={onkalibracio}>{t('modellek.kalibracio_nyit')}</button></p>
    {/if}
  {/if}
</section>

<style>
  .modellkezelo { display: flex; flex-direction: column; gap: var(--t-3); }
  p { margin: 0; }
  .leiras { color: var(--szoveg-masodlagos); font-size: var(--betu-kicsi); line-height: var(--sor-kicsi); }
  h3 { margin: 0; font-size: var(--betu-ui); font-weight: var(--suly-felkover); }
  .csoport { margin-top: var(--t-3); color: var(--szoveg-masodlagos); font-weight: var(--suly-kozepes); }
  .blokk { display: flex; flex-direction: column; gap: var(--t-2); padding: var(--t-4); background: var(--hatter-oldalsav); border-radius: var(--kerekites); }
  .szuro { display: flex; flex-wrap: wrap; align-items: flex-end; gap: var(--t-3); }
  .szuro label { display: flex; flex-direction: column; gap: var(--t-1); font-size: var(--betu-kicsi); color: var(--szoveg-masodlagos); }
  select { min-width: 0; padding: var(--t-2); color: var(--szoveg); background: var(--hatter); border: var(--keret-vastag) solid var(--keret-mezo); border-radius: var(--kerekites); font: inherit; font-size: var(--betu-ui); }
  .lista { display: flex; flex-direction: column; gap: var(--t-3); margin: 0; padding: 0; }
</style>
