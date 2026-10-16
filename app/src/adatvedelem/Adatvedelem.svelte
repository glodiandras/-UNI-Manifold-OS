<!--
  Privacy Center (F7): a Settings › Privacy szakaszai (Network, Telemetry, Data, Integrations, Permissions) és az AI › Memory a core VALÓS
  állapotából (`GET /api/adatvedelem`) — nem statikus szöveg: a hálózati mód a folyamat tényleges környezete, a méretek a lemezről,
  a darabszámok az asszisztens tárából jönnek. A kapcsolók a Settings piszkozatát szerkesztik (mentés a Settings láblécében).
  Törlés a meglévő végpontokon: AI-memória (tételenként és egyben), tracker (kétlépcsős megerősítéssel).
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { adatvedelem as alapTar, type AdatvedelemTar } from '../lib/adatvedelem/allapot.svelte';
  import { ENGEDELY_SZO, ENGEDETT_CIM, FAJTA_CIM, HELY_CIM, HELY_LEIRAS, TILTOTT_CIM, TRACKER_TAROL, meretSzoveg } from '../lib/adatvedelem/megjelenites';
  import type { Beallitasok } from '../lib/beallitasok/tipusok';
  import { t } from '../lib/i18n';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { CircleCheck, Database, TriangleAlert } from '../lib/ikon/ikonok';
  import { naptarHid } from '../lib/naptar/hid.svelte';
  import Adatkezeles from '../lib/tracker/Adatkezeles.svelte';
  import HibaPanel from '../lib/ui/HibaPanel.svelte';
  import UresAllapot from '../lib/ui/UresAllapot.svelte';
  import AsszisztensTanult from '../hej/vezerlo/AsszisztensTanult.svelte';

  let { szakasz, vazlat = $bindable(), tar = alapTar, onnyit, onszakasz, oneszeg }: {
    szakasz: string;
    vazlat: Beallitasok;
    tar?: AdatvedelemTar;
    /** A Manifold-panel egy szakaszának megnyitása (modellek, rendszer). */
    onnyit: (cel: string) => void;
    /** Másik Settings-szakaszra váltás (például Data → Memory). */
    onszakasz: (id: string) => void;
    /** A Health oldal megnyitása (a hibapanel „Open diagnostics” gombja). */
    oneszeg: (kod?: string) => void;
  } = $props();

  const a = $derived(tar.adat);
  onMount(() => void tar.betolt());

  const ertesitesAllapot = (): string => {
    if (typeof Notification === 'undefined') return 'ismeretlen';
    return Notification.permission === 'granted' ? 'engedelyezve' : Notification.permission === 'denied' ? 'megtagadva' : 'nincs_dontes';
  };
  const engedelySzo = (k: string | null | undefined) => t(ENGEDELY_SZO[k ?? 'ismeretlen'] ?? ENGEDELY_SZO.ismeretlen);
  const naptarEngedely = $derived(naptarHid.engedely?.esemeny ?? a?.engedelyek.naptar.esemeny ?? null);
  const mikor = (iso: string) => iso.replace('T', ' ').slice(0, 16);
</script>

<section class="adatvedelem" data-adatvedelem={szakasz}>
  {#if tar.hiba && !a}
    <HibaPanel mi={tar.hiba} javitas={t('privacy.nem_elerheto_javitas')} ujra={() => tar.betolt()} diagnosztika={() => oneszeg()} />
  {:else if !a}
    <p role="status" class="leiras">{t('privacy.betoltes')}</p>
  {/if}

  {#if szakasz === 'halozat' && a}
    <p class="allapot" role="status"><Ikon ikon={a.halozat.offline ? CircleCheck : TriangleAlert} />
      <span>{a.halozat.offline ? t('privacy.halozat.offline_be') : t('privacy.halozat.offline_ki')}</span></p>
    <p class="leiras">{t('privacy.halozat.leiras')}</p>
    <h3>{t('privacy.halozat.engedett_cim')}</h3>
    <ul role="list">
      {#each a.halozat.engedett as e (e.kod)}
        <li>{t(ENGEDETT_CIM[e.kod])} <span class="jel">{e.elerheto ? t('privacy.halozat.elerheto') : t('privacy.halozat.kikapcsolva')}</span></li>
      {/each}
    </ul>
    <h3>{t('privacy.halozat.tiltott_cim')}</h3>
    <ul role="list">{#each a.halozat.tiltott as k (k)}<li>{t(TILTOTT_CIM[k] ?? TILTOTT_CIM.telemetry)}</li>{/each}</ul>
    <h3>{t('privacy.halozat.utolso_cim')}</h3>
    {#if a.halozat.utolso_letoltesek.length}
      <ul role="list" class="letoltesek">
        {#each a.halozat.utolso_letoltesek as l (l.fajta + l.nev + l.mikor)}
          <li><span>{t(FAJTA_CIM[l.fajta])}: {l.nev}</span> <span class="jel">{mikor(l.mikor)}{l.eredmeny ? ` · ${l.eredmeny}` : ''}</span></li>
        {/each}
      </ul>
    {:else}
      <UresAllapot kicsi ikon={Database} cim={t('privacy.halozat.nincs_letoltes')} leiras={t('privacy.halozat.nincs_letoltes_leiras')} muvelet={{ cimke: t('privacy.modellek_megnyit'), onclick: () => onnyit('modellek') }} />
    {/if}

  {:else if szakasz === 'telemetria' && a}
    <p class="leiras">{t('privacy.telemetria.leiras')}</p>
    <label class="kapcsolo"><input type="checkbox" bind:checked={vazlat.adatvedelem.tracker} />{t('beallitasok.modul.tracker')}</label>
    <dl>
      <dt>{t('privacy.tracker.mit_tarol')}</dt><dd>{a.tracker.tarol.map((k) => t(TRACKER_TAROL[k])).join(', ')}</dd>
      <dt>{t('privacy.tracker.mit_nem')}</dt><dd>{a.tracker.nem_tarol.map((k) => t(TRACKER_TAROL[k])).join(', ')}</dd>
      <dt>{t('privacy.tracker.hol')}</dt><dd>{a.tracker.van ? `${a.tracker.ut} (${meretSzoveg(a.tracker.bajt)})` : t('privacy.tracker.meg_nincs')}</dd>
    </dl>
    <Adatkezeles onvaltozas={() => tar.betolt()} />

  {:else if szakasz === 'adatok' && a}
    <p class="leiras">{t('privacy.adatok.leiras')}</p>
    <h3>{t('privacy.adatok.hol_cim')}</h3>
    <ul role="list" class="helyek">
      {#each a.adat as h (h.kod)}
        <li data-hely={h.kod}>
          <div><strong>{t(HELY_CIM[h.kod])}</strong> <span class="jel">{h.van ? meretSzoveg(h.bajt) : t('privacy.adatok.meg_nincs')}</span></div>
          <div class="leiras">{t(HELY_LEIRAS[h.kod])}</div>
          {#if h.ut}<div class="ut">{h.ut}</div>{/if}
        </li>
      {/each}
    </ul>
    <h3>{t('privacy.adatok.modellek_cim')}</h3>
    {#if a.modellek.telepitve.length}
      <ul role="list" class="letoltesek">
        {#each a.modellek.telepitve as m (m.nev)}<li><span>{m.nev}</span> <span class="jel">{meretSzoveg(m.bajt)}</span></li>{/each}
      </ul>
      <p class="leiras">{t('privacy.adatok.modellek_osszes')} {meretSzoveg(a.modellek.bajt)}</p>
    {:else}
      <UresAllapot kicsi ikon={Database} cim={t('privacy.adatok.nincs_modell')} leiras={t('privacy.adatok.nincs_modell_leiras')} muvelet={{ cimke: t('privacy.modellek_megnyit'), onclick: () => onnyit('modellek') }} />
    {/if}
    <h3>{t('privacy.adatok.memoria_cim')}</h3>
    <p>{a.memoria.osszes} {t('privacy.adatok.memoria_tetelek')}</p>
    <button type="button" class="m-gomb semleges" onclick={() => onszakasz('memoria')}>{t('privacy.adatok.memoria_kezel')}</button>

  {:else if szakasz === 'integraciok' && a}
    <p class="leiras">{t('privacy.integraciok.leiras')}</p>
    <label class="kapcsolo"><input type="checkbox" bind:checked={vazlat.adatvedelem.naptar} />{t('beallitasok.naptar')}</label>
    <label class="kapcsolo"><input type="checkbox" bind:checked={vazlat.adatvedelem.ertesitesek} />{t('beallitasok.ertesitesek')}</label>
    <label class="kapcsolo"><input type="checkbox" bind:checked={vazlat.adatvedelem.asszisztens} />{t('beallitasok.modul.asszisztens')}</label>
    <label class="kapcsolo"><input type="checkbox" bind:checked={vazlat.adatvedelem.tracker} />{t('beallitasok.modul.tracker')}</label>
    <p class="leiras">{t('beallitasok.naptar_leiras')}</p>
    {#each a.integraciok.filter((i) => i.kod === 'calendar' && i.be && i.elerheto === false) as i (i.kod)}
      <HibaPanel mi={t('privacy.integraciok.naptar_nem_elerheto')} javitas={t('privacy.integraciok.naptar_javitas')} diagnosztika={() => oneszeg()} />
    {/each}

  {:else if szakasz === 'engedelyek' && a}
    <p class="leiras">{t('privacy.engedelyek.leiras')}</p>
    <dl>
      <dt>{t('privacy.engedelyek.naptar')}</dt><dd data-engedely="naptar">{engedelySzo(naptarEngedely)}</dd>
      <dt>{t('privacy.engedelyek.ertesitesek')}</dt><dd data-engedely="ertesitesek">{engedelySzo(ertesitesAllapot())}</dd>
    </dl>
    {#if naptarHid.elerheto}<button type="button" class="m-gomb semleges" disabled={naptarHid.kerdesben} onclick={() => naptarHid.kerd()}>{t('beallitasok.naptar_engedely')}</button>{/if}
    {#if naptarHid.hiba}<p role="alert" class="hiba">{naptarHid.hiba}</p>{/if}
    <p class="leiras">{t('beallitasok.naptar_leiras')}</p>
    <label class="kapcsolo"><input type="checkbox" bind:checked={vazlat.adatvedelem.ertesitesek} />{t('beallitasok.ertesitesek')}</label>
    <label class="kapcsolo"><input type="checkbox" bind:checked={vazlat.adatvedelem.naptar} />{t('beallitasok.naptar')}</label>

  {:else if szakasz === 'memoria' && a}
    <p class="allapot" role="status"><Ikon ikon={a.memoria.kapcsolo ? CircleCheck : TriangleAlert} />
      <span>{a.memoria.kapcsolo ? t('privacy.memoria.be') : t('privacy.memoria.ki')}</span></p>
    <p class="leiras">{t('privacy.memoria.leiras')}</p>
    <label class="kapcsolo"><input type="checkbox" bind:checked={vazlat.adatvedelem.asszisztens} />{t('beallitasok.modul.asszisztens')}</label>
    <AsszisztensTanult />

  {:else if szakasz === 'asszisztens' && a}
    <p class="leiras">{t('privacy.asszisztens.leiras')}</p>
    <label class="kapcsolo"><input type="checkbox" bind:checked={vazlat.adatvedelem.asszisztens} />{t('beallitasok.modul.asszisztens')}</label>
    <button type="button" class="m-gomb semleges" onclick={() => onszakasz('memoria')}>{t('privacy.adatok.memoria_kezel')}</button>
  {/if}
</section>

<style>
  .adatvedelem { display: flex; flex-direction: column; gap: var(--t-3); }
  h3 { margin: var(--t-3) 0 0; font-size: var(--betu-torzs); font-weight: var(--suly-kozepes); }
  p { margin: 0; }
  .leiras { color: var(--szoveg-masodlagos); font-size: var(--betu-kicsi); }
  .allapot { display: flex; align-items: center; gap: var(--t-2); font-weight: var(--suly-kozepes); }
  ul { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: var(--t-2); }
  li { display: flex; flex-direction: column; gap: var(--t-1); }
  .letoltesek li { flex-direction: row; justify-content: space-between; gap: var(--t-3); }
  .jel { color: var(--szoveg-masodlagos); font-size: var(--betu-kicsi); }
  .ut { color: var(--szoveg-masodlagos); font-size: var(--betu-kicsi); overflow-wrap: anywhere; user-select: text; }
  dl { display: grid; grid-template-columns: max-content 1fr; gap: var(--t-1) var(--t-4); margin: 0; }
  dt { color: var(--szoveg-masodlagos); }
  dd { margin: 0; overflow-wrap: anywhere; }
  label.kapcsolo { display: flex; align-items: center; gap: var(--t-3); padding: var(--t-2) 0; }
  input[type='checkbox'] { accent-color: var(--akcent-kitoltes); }
  .hiba { color: var(--hiba); }
</style>
