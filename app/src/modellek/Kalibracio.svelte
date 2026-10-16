<!--
  Settings › AI › Calibration: a feladatok küszöbei és hogy melyik modell kalibrált rájuk, a mellékelt aranyhalmazok állapota,
  és a saját aranyhalmaz-varázsló. A jelet (Calibrated / Trial) a mérés adja a Models oldalon („Test this model”); itt látszik, mi
  számít kalibráltnak, és ezen mérhet a felhasználó a saját példáin. Csak olvas és a saját halmazt kezeli: modellt nem tölt le.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { CircleCheck, FlaskConical } from 'lucide';
  import { t, tk } from '../lib/i18n';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { modellek as alapTar, type ModellTar } from '../lib/modellek/allapot.svelte';
  import { nyelvNev } from '../lib/modellek/megjelenites';
  import HibaPanel from '../lib/ui/HibaPanel.svelte';
  import HalmazVarazslo from './HalmazVarazslo.svelte';
  import ProbaJel from './ProbaJel.svelte';

  let { tar = alapTar, oneszeg, onmodellek }: { tar?: ModellTar; oneszeg?: () => void; onmodellek?: () => void } = $props();

  onMount(() => {
    if (!tar.lista) void tar.betolt();
    void tar.halmazokBetolt();
  });

  const feladatok = $derived(Object.entries(tar.lista?.feladatok ?? {}).sort(([, a], [, b]) => a.cim.localeCompare(b.cim)));
  const kalibraltak = (f: string) => tar.modellek.flatMap((m) => m.kalibracio.filter((k) => k.feladat === f && k.kalibralt).map((k) => ({ modell: m.id, mero: k.mero, pontszam: k.pontszam })));
  const ALLAPOT: Record<string, string> = {
    jovahagyott: tk('modellek.halmaz.allapot.jovahagyott'),
    vazlat: tk('modellek.halmaz.allapot.vazlat'),
    hianyzik: tk('modellek.halmaz.allapot.hianyzik'),
    hibas: tk('modellek.halmaz.allapot.hibas'),
  };
</script>

<section class="kalibracio" data-kalibracio>
  <p class="leiras">{t('modellek.kal.leiras')}</p>
  <p class="leiras">{t('modellek.kal.jel_leiras')}</p>
  {#if onmodellek}<p><button type="button" class="m-gomb semleges" onclick={onmodellek}><Ikon ikon={FlaskConical} />{t('modellek.kal.modellek_nyit')}</button></p>{/if}

  {#if tar.hiba && !tar.lista}
    <HibaPanel mi={tar.hiba} javitas={t('modellek.hiba_javitas')} ujra={() => tar.betolt()} diagnosztika={oneszeg} />
  {:else if !tar.lista}
    <p role="status" class="leiras">{t('modellek.betoltes')}</p>
  {:else}
    <h3>{t('modellek.kal.feladatok')}</h3>
    <table class="tabla">
      <thead><tr><th scope="col">{t('modellek.kal.feladat')}</th><th scope="col">{t('modellek.kal.kuszob')}</th><th scope="col">{t('modellek.kal.jel')}</th></tr></thead>
      <tbody>
        {#each feladatok as [f, v] (f)}
          {@const k = kalibraltak(f)}
          <tr data-feladat={f}>
            <th scope="row">{v.cim}<span class="leiras"> {v.leiras}</span></th>
            <td>{v.kuszob == null ? t('modellek.kal.nincs_kuszob') : t('Legalább {kuszob} pont, legalább {min} tételen', { kuszob: v.kuszob, min: v.min_tetel ?? 0 })}</td>
            <td>
              {#if k.length}
                {#each k as x (x.modell + x.mero)}<span class="sor"><ProbaJel jel="kalibralt" mero={x.mero} /> {x.modell}</span>{/each}
              {:else}
                <ProbaJel jel="proba" />
              {/if}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}

  <h3>{t('modellek.kal.szallitott')}</h3>
  {#if tar.halmazok}
    {#if tar.halmazok.szallitott.length}
      <ul class="szallitott">
        {#each tar.halmazok.szallitott as h (h.feladat)}
          <li data-szallitott={h.feladat}>
            <span class="nev" title={h.feladat}>{tar.feladatCim(h.router_feladat)}</span>
            <span class="leiras">{t('{n} tétel · nyelv: {nyelv} · licenc: {licenc}', { n: h.tetelszam, nyelv: h.nyelv ? nyelvNev(h.nyelv) : '–', licenc: h.licenc ?? '–' })}</span>
            <span class="allapot"><Ikon ikon={h.allapot === 'jovahagyott' ? CircleCheck : FlaskConical} />{ALLAPOT[h.allapot] ? t(ALLAPOT[h.allapot]) : h.allapot}</span>
          </li>
        {/each}
      </ul>
    {:else}
      <p class="leiras">{t('modellek.kal.nincs_szallitott')}</p>
    {/if}
  {:else if tar.halmazHiba}
    <p class="hiba" role="alert">{tar.halmazHiba}</p>
  {/if}

  <HalmazVarazslo {tar} />
</section>

<style>
  .kalibracio { display: flex; flex-direction: column; gap: var(--t-3); }
  p { margin: 0; }
  h3 { margin: var(--t-2) 0 0; font-size: var(--betu-ui); font-weight: var(--suly-felkover); }
  .leiras { color: var(--szoveg-masodlagos); font-size: var(--betu-kicsi); line-height: var(--sor-kicsi); }
  .tabla { width: 100%; border-collapse: collapse; font-size: var(--betu-ui); }
  th, td { padding: var(--t-2); text-align: start; vertical-align: top; border-bottom: var(--keret-vastag) solid var(--keret); }
  thead th { font-size: var(--betu-kicsi); color: var(--szoveg-masodlagos); font-weight: var(--suly-kozepes); }
  tbody th { font-weight: var(--suly-kozepes); }
  .sor { display: flex; flex-wrap: wrap; align-items: center; gap: var(--t-2); }
  .szallitott { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--t-2); }
  .szallitott li { display: flex; flex-wrap: wrap; align-items: center; gap: var(--t-1) var(--t-4); padding: var(--t-2) 0; border-bottom: var(--keret-vastag) solid var(--keret); }
  .nev { font-weight: var(--suly-kozepes); }
  .allapot { display: inline-flex; align-items: center; gap: var(--t-1); margin-inline-start: auto; }
</style>
