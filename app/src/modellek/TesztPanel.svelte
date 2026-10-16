<!--
  „Test this model” (F6): előpróba (3 tétel) → mérés (az aranyhalmazon) → jel (Calibrated / Trial). A felület csak elindítja a core
  `modell_teszt` feladatát és követi a haladását; a jelet a core kapui adják (a felület nem dönt). Az eredmény riportja
  megnyitható: pontszám a küszöbhöz mérve, a mért tételek, az érvényesség és az okok (miért Trial). A mérés a felhasználó
  kattintására indul, és folytatható (leállítás után a kész tételektől megy tovább).
-->
<script lang="ts">
  import { untrack } from 'svelte';
  import { Check, CircleAlert, CircleDashed, FlaskConical, Loader, Square } from 'lucide';
  import { t } from '../lib/i18n';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { okokSzoveg, type ModellTar } from '../lib/modellek/allapot.svelte';
  import { merheto } from '../lib/modellek/megjelenites';
  import type { Modell } from '../lib/modellek/tipusok';
  import ProbaJel from './ProbaJel.svelte';

  let { m, tar }: { m: Modell; tar: ModellTar } = $props();

  const lehet = $derived(m.feladat.filter((f) => !!tar.lista?.feladatok[f]));
  let feladat = $state(untrack(() => (m.feladat.find((f) => tar.lista?.feladatok[f]?.kuszob != null) ?? m.feladat[0] ?? '')));
  let halmaz = $state<'szallitott' | 'sajat'>('szallitott');
  let reszletek = $state(false);

  const leiras = $derived(tar.lista?.feladatok[feladat]);
  const szallitott = $derived(tar.halmazok?.szallitott.find((h) => h.router_feladat === feladat || h.feladat === feladat));
  const sajat = $derived(tar.halmazok?.sajat[feladat]);
  const sajatKesz = $derived(sajat?.van && sajat.allapot === 'jovahagyott');
  const aktiv = $derived(tar.aktiv(m, 'teszt'));
  const masikFut = $derived(tar.modellek.some((x) => x.id !== m.id && tar.aktiv(x, 'teszt')));
  const riport = $derived(tar.riportok[`${m.id}:${feladat}`]);
  const ertek = $derived(riport?.ertekeles ?? null);
  const futo = $derived(aktiv?.feladat ?? feladat);
  // a core az előpróba végén jelzi az 5 %-ot; addig előpróba, utána mérés
  const lepes = $derived(!aktiv ? -1 : aktiv.allapot === 'sorban' || aktiv.szazalek < 5 ? 0 : 1);

  // a halmaz-választás követi a rendelkezésre állót: saját halmaz csak jóváhagyva választható
  $effect(() => {
    if (halmaz === 'sajat' && !sajatKesz) halmaz = 'szallitott';
  });
  $effect(() => {
    if (sajatKesz && sajat?.valasztva) untrack(() => { halmaz = 'sajat'; });
  });
  $effect(() => {
    const f = feladat;
    if (f && !untrack(() => tar.riportok[`${m.id}:${f}`])) void untrack(() => tar.riportBetolt(m.id, f));
  });

  const pont = (x: number | null | undefined) => (typeof x === 'number' ? x.toFixed(3) : '–');
  const ERV_CIM: Record<string, string> = {
    levagott: t('modellek.teszt.erv.levagott'),
    hurok: t('modellek.teszt.erv.hurok'),
    ures: t('modellek.teszt.erv.ures'),
    hiba: t('modellek.teszt.erv.hiba'),
    hianyzo: t('modellek.teszt.erv.hianyzo'),
  };
  const lepesJel = (i: number) => (lepes < 0 ? 'varakozik' : i < lepes ? 'kesz' : i === lepes ? 'folyamatban' : 'varakozik');
</script>

<div class="teszt" data-teszt={m.id}>
  <p class="leiras">{t('modellek.teszt.leiras')}</p>

  {#if !merheto(m)}
    <p class="info"><Ikon ikon={CircleAlert} />{t('modellek.teszt.nincs_telepitve')}</p>
  {/if}

  <div class="mezok">
    <label>{t('modellek.teszt.feladat')}
      <select bind:value={feladat} disabled={!!aktiv}>
        {#each lehet as f (f)}<option value={f}>{tar.feladatCim(f)}{tar.lista?.feladatok[f]?.kuszob == null ? ` (${t('modellek.teszt.nincs_kuszob')})` : ''}</option>{/each}
      </select>
    </label>
    <label>{t('modellek.teszt.halmaz')}
      <select bind:value={halmaz} disabled={!!aktiv}>
        <option value="szallitott">{szallitott ? t('Mellékelt példák ({n} tétel)', { n: szallitott.tetelszam }) : t('modellek.teszt.halmaz_szallitott_nincs')}</option>
        <option value="sajat" disabled={!sajatKesz}>{sajatKesz ? t('Saját példák ({n} tétel)', { n: sajat?.tetelszam ?? 0 }) : t('modellek.teszt.halmaz_sajat_nincs')}</option>
      </select>
    </label>
  </div>
  {#if leiras}<p class="leiras">{leiras.leiras}{leiras.kuszob != null ? ` ${t('Kalibrált jelhez legalább {kuszob} pont kell, legalább {min} tételen.', { kuszob: leiras.kuszob, min: leiras.min_tetel ?? 0 })}` : ` ${t('modellek.teszt.kuszob_nincs')}`}</p>{/if}

  {#if aktiv}
    <ol class="lepesek" aria-label={t('modellek.teszt.lepesek')}>
      {#each [t('modellek.teszt.lepes.eloproba'), t('modellek.teszt.lepes.meres'), t('modellek.teszt.lepes.jel')] as cim, i (i)}
        <li data-lepes={lepesJel(i)}>
          <Ikon ikon={lepesJel(i) === 'kesz' ? Check : lepesJel(i) === 'folyamatban' ? Loader : CircleDashed} />
          <span>{cim}</span>
          <span class="allapotszo">{lepesJel(i) === 'kesz' ? t('modellek.teszt.kesz') : lepesJel(i) === 'folyamatban' ? t('modellek.teszt.folyamatban') : t('modellek.teszt.varakozik')}</span>
        </li>
      {/each}
    </ol>
    <progress max="100" value={aktiv.szazalek} aria-label={t('{feladat} mérésének haladása', { feladat: tar.feladatCim(futo) })}></progress>
    <span class="szazalek">{Math.round(aktiv.szazalek)} %</span>
  {/if}

  <div class="gombok">
    {#if aktiv}
      <button type="button" class="m-gomb semleges" onclick={() => void tar.tesztLeallit(m)}><Ikon ikon={Square} />{t('modellek.teszt.leallit')}</button>
    {:else}
      <button type="button" class="m-gomb" disabled={!merheto(m) || !feladat || masikFut || tar.foglalt[m.id]} onclick={() => void tar.tesztInditas(m, feladat, halmaz)}><Ikon ikon={FlaskConical} />{t('modellek.teszt.inditas')}</button>
      {#if masikFut}<span class="halvany">{t('modellek.teszt.masik_fut')}</span>{/if}
    {/if}
  </div>

  {#if riport && !aktiv && riport.feladat === feladat}
    <div class="eredmeny" data-jel={riport.jel}>
      <p class="jelsor"><ProbaJel jel={riport.jel} mero={riport.halmaz} />
        <span>{riport.allapot === 'megallitva' ? t('modellek.teszt.megallitva') : riport.jel === 'kalibralt' ? t('modellek.teszt.eredmeny_kalibralt') : t('modellek.teszt.eredmeny_proba')}</span></p>
      {#if ertek?.pontszam != null}<p>{t('Pontszám: {pont} (küszöb: {kuszob})', { pont: pont(ertek.pontszam), kuszob: riport.kuszob ?? '–' })}</p>{/if}
      {#if riport.okok?.length}
        <ul class="okok">{#each okokSzoveg(riport.okok) as o, i (i)}<li class="ok-sor"><Ikon ikon={CircleAlert} />{o}</li>{/each}</ul>
      {/if}
      {#if riport.uzenet}<p class="halvany">{riport.uzenet}</p>{/if}
      <button type="button" class="m-gomb link" aria-expanded={reszletek} onclick={() => (reszletek = !reszletek)}>{reszletek ? t('modellek.teszt.riport_zar') : t('modellek.teszt.riport_nyit')}</button>
      {#if reszletek}
        <dl class="riport" data-riport>
          <dt>{t('modellek.teszt.r.modell')}</dt><dd>{riport.modell}</dd>
          <dt>{t('modellek.teszt.r.feladat')}</dt><dd>{tar.feladatCim(riport.feladat)}</dd>
          <dt>{t('modellek.teszt.r.halmaz')}</dt><dd>{riport.halmaz === 'sajat' ? t('modellek.jel.sajat_halmaz') : t('modellek.jel.szallitott_halmaz')}</dd>
          <dt>{t('modellek.teszt.r.datum')}</dt><dd>{riport.datum.replace('T', ' ').slice(0, 16)}</dd>
          {#if ertek}
            <dt>{t('modellek.teszt.r.tetelek')}</dt><dd>{t('{n} / {osszes}', { n: ertek.n ?? 0, osszes: ertek.tetelszam ?? 0 })}</dd>
            <dt>{t('modellek.teszt.r.ervenyes')}</dt><dd>{ertek.ervenyes ? t('modellek.teszt.igen') : t('modellek.teszt.nem')}</dd>
            {#each Object.keys(ERV_CIM) as k (k)}{#if typeof ertek.ervenyesseg?.[k] === 'number'}<dt>{ERV_CIM[k]}</dt><dd>{ertek.ervenyesseg[k]}</dd>{/if}{/each}
          {/if}
          <dt>{t('modellek.teszt.r.rogzitve')}</dt><dd>{riport.rogzitve ? t('modellek.teszt.igen') : t('modellek.teszt.nem')}</dd>
        </dl>
      {/if}
    </div>
  {/if}
</div>

<style>
  .teszt { display: flex; flex-direction: column; gap: var(--t-3); padding: var(--t-3); background: var(--hatter-oldalsav); border-radius: var(--kerekites); }
  p { margin: 0; }
  .leiras, .halvany { color: var(--szoveg-masodlagos); font-size: var(--betu-kicsi); line-height: var(--sor-kicsi); }
  .info { display: flex; align-items: center; gap: var(--t-2); }
  .mezok { display: flex; flex-wrap: wrap; gap: var(--t-3); }
  label { display: flex; flex-direction: column; gap: var(--t-1); min-width: 0; flex: 1; font-size: var(--betu-kicsi); color: var(--szoveg-masodlagos); }
  select { min-width: 0; padding: var(--t-2); color: var(--szoveg); background: var(--hatter); border: var(--keret-vastag) solid var(--keret-mezo); border-radius: var(--kerekites); font: inherit; font-size: var(--betu-ui); }
  .lepesek { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--t-1); }
  .lepesek li { display: flex; align-items: center; gap: var(--t-2); }
  .lepesek li[data-lepes='varakozik'] { color: var(--szoveg-masodlagos); }
  .allapotszo { margin-inline-start: auto; color: var(--szoveg-masodlagos); font-size: var(--betu-kicsi); }
  progress { width: 100%; accent-color: var(--akcent-kitoltes); }
  .szazalek { color: var(--szoveg-masodlagos); font-size: var(--betu-kicsi); font-variant-numeric: tabular-nums; }
  .gombok { display: flex; flex-wrap: wrap; align-items: center; gap: var(--t-2); }
  .eredmeny { display: flex; flex-direction: column; gap: var(--t-2); padding-top: var(--t-3); border-top: var(--keret-vastag) solid var(--keret); }
  .jelsor { display: flex; flex-wrap: wrap; align-items: center; gap: var(--t-2); }
  .okok { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--t-1); }
  .ok-sor { display: flex; align-items: flex-start; gap: var(--t-2); }
  .riport { display: grid; grid-template-columns: max-content 1fr; gap: var(--t-1) var(--t-4); margin: 0; font-size: var(--betu-kicsi); }
  .riport dt { color: var(--szoveg-masodlagos); }
  .riport dd { margin: 0; overflow-wrap: anywhere; }
</style>
