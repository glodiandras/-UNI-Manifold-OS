<!--
  A „Rendszer” szakasz (C17): memória, a modellzár birtokosa, a betöltött modell és a keret, az SSD, az utolsó mentés
  és a „Mentés most” gomb. Az adat csak nyitott lap és látszó ablak mellett frissül.
-->
<script lang="ts">
  import { t } from '../../lib/i18n';
  import { onMount } from 'svelte';
  import { ertesitesek } from '../../lib/ertesites/ertesites.svelte';
  import { vezerloApi } from '../../lib/vezerlo/api';
  import { gb, idoRovid, mb } from '../../lib/vezerlo/megjelenites';
  import { rendszerAllapot } from '../../lib/vezerlo/rendszer.svelte';
  import TeljesMentes from './TeljesMentes.svelte';
  import { epitesAllapot } from '../../lib/vezerlo/epites.svelte';
  import { fejlesztoMod } from '../../lib/beallitasok/fejleszto';
  import { egeszsegMegnyit } from '../../lib/egeszseg/allapot.svelte';
  import HibaPanel from '../../lib/ui/HibaPanel.svelte';

  let mentesFut = $state(false);
  // a build-állapot a közös tárból: a friss (60 s-on belüli) választ a szakasz újranyitása nem kéri újra (a core minden
  // lekérésre hash-el); amíg a core a mag ujjlenyomatát számolja, 3 s-onként újrakérdez
  const epites = $derived(epitesAllapot.adat);
  const epitesHiba = $derived(epitesAllapot.hiba);
  onMount(() => {
    if (fejlesztoMod()) void epitesAllapot.frissit();
  });
  $effect(() => {
    if (!fejlesztoMod() || !epitesAllapot.szamol) return;
    const t = setTimeout(() => void epitesAllapot.frissit(true), 3000);
    return () => clearTimeout(t);
  });
  const r = $derived(rendszerAllapot.adat);

  onMount(() => rendszerAllapot.indit());

  async function mentes() {
    mentesFut = true;
    try {
      await vezerloApi.mentesInditas();
      ertesitesek.ertesit({ szint: 'info', cim: t('A mentés elindult'), szoveg: t('A belső lemezre készül a szöveges pillanatkép.') });
    } catch (e) {
      ertesitesek.ertesit({ szint: 'hiba', cim: t('A mentés nem indult el'), szoveg: e instanceof Error ? e.message : String(e) });
    } finally {
      mentesFut = false;
      setTimeout(() => void rendszerAllapot.frissit(), 3000);
    }
  }

  const zarSzoveg = $derived.by(() => {
    if (!r) return '';
    const z = r.modellzar;
    if (z.szabad) return z.elavult ? t('szabad (elavult bejegyzés)') : t('szabad');
    return `${z.repo ?? t('ismeretlen modell')}${fejlesztoMod() ? ` · pid ${z.pid}` : ''}${z.ido ? ` · ${t('{ido} óta', { ido: z.ido })}` : ''}`;
  });
</script>

{#if rendszerAllapot.hiba && !r}
  <HibaPanel mi={t('A rendszerállapot nem érhető el: {hiba}', { hiba: rendszerAllapot.hiba })} javitas={t('rendszer.hiba_javitas')} ujra={() => rendszerAllapot.frissit()} diagnosztika={() => egeszsegMegnyit('folyamatok')} />
{:else if !r}
  <p class="halvany" role="status">{t('Betöltés…')}</p>
{:else}
  {#if fejlesztoMod() && epites}
    <p class:figy={!epites.ok && !epitesAllapot.szamol}>
      {epitesAllapot.szamol
        ? t('A build állapotának ellenőrzése folyik (a mag ujjlenyomata számolódik)…')
        : epites.ok
          ? t('A futó alkalmazás a forrással egyezik.')
          : t('Elavult alkalmazásrészek: újrafordítás vagy újraindítás szükséges.')}
      <small>{t('Mag:')} {epites.mag ?? t('számolás folyik')} · {epites.reszek.map((r) => `${r.resz}: ${r.azonosito || (epitesAllapot.szamol ? t('számolás folyik') : t('ismeretlen'))}${r.friss ? '' : ` ${t('(elavult)')}`}`).join(' · ')}</small>
    </p>
  {:else if fejlesztoMod() && epitesHiba}<p class="figy">{t('A build állapota nem ellenőrizhető: {hiba}', { hiba: epitesHiba })}</p>{/if}
  <dl>
    <dt>{t('Memória')}</dt>
    <dd>
      {r.memoria.szabad_szazalek >= 0 ? t('{n} % szabad', { n: r.memoria.szabad_szazalek }) : t('nem mérhető')} · {gb(r.memoria.osszes_gb)}
      {#if fejlesztoMod() && r.memoria.core_rss_mb}<small>{t('core:')} {mb(r.memoria.core_rss_mb)}{r.worker.fut && r.worker.rss_mb ? `, ${t('worker: {mb}', { mb: mb(r.worker.rss_mb) })}` : ''}</small>{/if}
    </dd>
    {#if fejlesztoMod()}
      <dt>{t('Modellzár')}</dt>
      <dd>{zarSzoveg}</dd>
    {/if}
    <dt>{t('Betöltött modell')}</dt>
    <dd>
      {#if r.worker.fut && r.worker.modell}
        {r.worker.modell}{r.worker.keret_gb ? ` · ${t('keret {gb}', { gb: gb(r.worker.keret_gb) })}` : ''}
        {#if r.worker.szunetek}<small>{t('{n} memóriaőr-szünet', { n: r.worker.szunetek })}</small>{/if}
      {:else if r.worker.fut}
        {t('nincs betöltve')} <small>{t('rendszer.motor_fut')}</small>
      {:else}
        {t('nincs')} <small>{t('rendszer.motor_all')}</small>
      {/if}
    </dd>
    <dt>{t('Kötet')}</dt>
    <dd>
      {#if r.ssd.elerheto}{r.ssd.kotet} · {t('{gb} szabad / {ossz}', { gb: gb(r.ssd.szabad_gb), ossz: gb(r.ssd.osszes_gb) })}{:else}{t('nem érhető el')}{/if}
    </dd>
    <dt>{t('Utolsó mentés')}</dt>
    <dd>
      {#if r.mentes.utolso}{idoRovid(r.mentes.utolso)}{:else}{t('még nem volt')}{/if}
      {#if !r.mentes.friss}<small class="figy">{t('a mentés régebbi a legutóbbi változásnál')}</small>{/if}
      {#if r.mentes.hiba}
        <small class="hiba-sor" role="alert">
          {t('A belső lemezes mentés nem sikerült')}{r.mentes.hiba.ido ? ` (${idoRovid(r.mentes.hiba.ido)})` : ''}:
          {Object.entries(r.mentes.hiba.hibak).map(([nev, uzenet]) => `${nev}: ${uzenet}`).join('; ')}
        </small>
      {/if}
    </dd>
  </dl>
  <button type="button" class="m-gomb semleges gomb" disabled={mentesFut} onclick={mentes}>{t('Mentés most|biztonsagi')}</button>
  <TeljesMentes />
{/if}

<style>
  dl {
    display: grid;
    grid-template-columns: max-content 1fr;
    gap: var(--t-1) var(--t-3);
    margin: 0 0 var(--t-3);
    font-size: var(--betu-ui);
    line-height: var(--sor-ui);
  }

  dt {
    color: var(--szoveg-halvany);
  }

  dd {
    margin: 0;
    min-width: 0;
    overflow-wrap: anywhere;
    font-variant-numeric: tabular-nums;
  }

  small {
    display: block;
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  small.figy {
    color: var(--figyelmeztetes);
  }

  small.hiba-sor {
    margin-top: var(--t-1);
    padding: var(--t-1) var(--t-2);
    border-radius: var(--kerekites-kicsi);
    background: var(--hiba-hatter);
    color: var(--hiba);
  }

  .halvany {
    margin: 0;
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
  }

</style>
