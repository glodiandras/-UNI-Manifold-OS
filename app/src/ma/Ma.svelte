<!--
  A „Ma” oldal (C15): a nap egy helyen, egy oszlopban, olvasótörzs-szélességben. Szakaszok: a következő dolgozat /
  határidő, a nap naptára, a napi jegyzet, a ma esedékes feladatok, az esedékes kártyák (helyőrző a C23-ig). Az üres
  szakasz egy sorra zsugorodik. Az adat a core `GET /api/ma` összesítőjéből jön (`maAdat`); az oldal csak olvas — a
  jegyzet és a feladat megnyitása a közös munkaterületen megy, a napi jegyzetet a `naplo.napi` parancs hozza létre.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { kodUzenet } from '../lib/core/api';
  import { t } from '../lib/i18n';
  import { modulEngedelyezett } from '../lib/beallitasok/allapot.svelte';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { CalendarCheck, FileText, GraduationCap } from '../lib/ikon/ikonok';
  import type { NezetProps } from '../lib/elrendezes/nezetek.svelte';
  import { kornyezet } from '../lib/kornyezet';
  import { regiszter } from '../lib/parancsok/regiszter';
  import Billentyu from '../lib/ui/Billentyu.svelte';
  import { fajlNev, mappa } from '../lib/vault/fajlok.svelte';
  import { nyitasMod } from '../szerkeszto/linkek/navigacio';
  import { szerkesztok } from '../szerkeszto/szerkesztok.svelte';
  import { maiIsmetles } from '../kartya';
  import TanulasiKeret from './TanulasiKeret.svelte';
  import ManifoldLap from '../hej/ManifoldLap.svelte';
  import StatisztikaSzakasz from '../hej/vezerlo/StatisztikaSzakasz.svelte';
  import Asszisztens from './Asszisztens.svelte';
  import Javaslatok from './Javaslatok.svelte';
  import NaptarJelzes from './NaptarJelzes.svelte';
  import { idoSzoveg, napokSzoveg, napRovid, napSzoveg, szinkronSzoveg } from './datum';
  import { maAdat } from './modell.svelte';
  import { hibas, type Dolgozat, type Feladat } from './tipusok';

  let {}: NezetProps = $props();
  const { felulet } = kornyezet();

  // A nézet a csatolástól a lebontásig látszik (a panel nem aktív fülét a Panel le sem csatolja): addig tölt és
  // frissül, akkor is, ha a panel nem az aktív (T167).
  onMount(() => maAdat.megjelenik());

  const adat = $derived(maAdat.adat);
  const napi = $derived(adat && !hibas(adat.napi) ? adat.napi : null);
  const naptar = $derived(adat && !hibas(adat.naptar) ? adat.naptar : null);
  const dolgozatok = $derived(adat && !hibas(adat.dolgozatok) ? adat.dolgozatok : null);
  const feladatok = $derived(adat && !hibas(adat.feladatok) ? adat.feladatok : null);
  const kartyak = $derived(adat && adat.kartyak && !hibas(adat.kartyak) ? adat.kartyak : null);
  // a core hibaszövege kisbetűvel kezdődik (naplóba is megy); a felületen mondatként áll
  const hibaSzoveg = (s: object | undefined) => (s && hibas(s) ? ((u) => u.charAt(0).toUpperCase() + u.slice(1))(kodUzenet(s)) : null);

  const elso = $derived(dolgozatok?.lista[0] ?? null);
  const tovabbi = $derived(dolgozatok?.lista.slice(1) ?? []);
  const regi = $derived(!!(naptar?.regi || dolgozatok?.regi));
  const szinkron = $derived(naptar?.utolso_szinkron ?? dolgozatok?.utolso_szinkron ?? null);

  function megnyit(ut: string, e: MouseEvent) {
    felulet.munkaterulet.megnyit(ut, nyitasMod(e));
  }

  function feladatNyit(f: Feladat, e: MouseEvent) {
    felulet.munkaterulet.megnyit(f.ut, nyitasMod(e));
    szerkesztok.ugras(f.ut, f.sor);
  }

  function dolgozatMeta(d: Dolgozat): string {
    const reszek = [napokSzoveg(d.napok), napSzoveg(d.nap)];
    if (d.ora) reszek.push(d.ora);
    if (d.hely) reszek.push(d.hely);
    return reszek.join(' · ');
  }
</script>

<div class="ma olvasas">
  <header>
    <h1 class="manifold-jel">Manifold</h1>
    <p class="datum">{adat?.felirat ?? ' '}</p>
    {#if regi}<p class="regi" role="status">{szinkronSzoveg(szinkron)}</p>{/if}
  </header>

  <nav class="gyors-muveletek" aria-label={t('Gyors műveletek')}>
    <button type="button" class="m-gomb semleges" onclick={() => regiszter.futtat('hej.valto', 'gomb')}>{t('Fájl megnyitása')}</button>
    {#if modulEngedelyezett('napi')}
      <button type="button" class="m-gomb semleges" onclick={() => regiszter.futtat('naplo.napi', 'gomb')}>{t('Mai jegyzet')}</button>
    {/if}
    <button type="button" class="m-gomb semleges" onclick={() => regiszter.futtat('beallitasok.megnyit', 'gomb')}>{t('beallitasok.cim')}</button>
  </nav>

  {#if maAdat.hiba && !adat}
    <p class="hiba" role="alert">{t('A Ma oldal adata nem tölthető be:')} {maAdat.hiba}</p>
  {:else if !adat}
    <p class="ures" role="status">{t('Betöltés…')}</p>
  {/if}

  <section aria-label={t('Tanulási idő')}><h2>{t('Tanulás a héten')}</h2><StatisztikaSzakasz /><TanulasiKeret /></section>

  <!-- ------------------------------------------------------------- következő dolgozat -->
  <section aria-labelledby="ma-dolgozat">
    <h2 id="ma-dolgozat">{t('Következő dolgozat / határidő')}</h2>
    {#if hibaSzoveg(adat?.dolgozatok)}
      <p class="ures">{hibaSzoveg(adat?.dolgozatok)}</p>
    {:else if elso}
      <div class="kartya">
        <p class="cim">
          {#if elso.szin}<span class="pont" style:background={elso.szin} aria-hidden="true"></span>{/if}{elso.cim}
        </p>
        <p class="meta">{dolgozatMeta(elso)}</p>
        {#if elso.jegyzet}
          <button type="button" class="m-gomb semleges gomb" onclick={(e) => megnyit(elso.jegyzet!, e)} title={elso.jegyzet}>
            <Ikon ikon={FileText} /> {t('Felkészülési jegyzet')}
          </button>
        {/if}
        <button type="button" class="m-gomb semleges gomb" onclick={() => felulet.munkaterulet.megnyitNezet('dolgozat', { azon: elso.azon })}>
          <Ikon ikon={GraduationCap} /> {t('Felkészültség')}
        </button>
      </div>
      {#if tovabbi.length}
        <ul class="lista" role="list">
          {#each tovabbi as d (d.azon)}
            <li>
              <span class="ido">{napRovid(d.nap)}</span>
              <span class="szoveg">{d.cim}</span>
              <span class="halvany">{napokSzoveg(d.napok)}</span>
            </li>
          {/each}
        </ul>
      {/if}
    {:else if dolgozatok}
      <p class="ures">{t('Nincs közelgő határidő a naptárban.')}</p>
    {/if}
    <Javaslatok szakasz={adat?.javaslatok} />
  </section>

  <!-- ------------------------------------------------------------- a nap -->
  <section aria-labelledby="ma-nap">
    <h2 id="ma-nap">{t('A nap')}</h2>
    <NaptarJelzes szakasz={adat?.naptar_allapot} />
    {#if hibaSzoveg(adat?.naptar)}
      <p class="ures">{hibaSzoveg(adat?.naptar)}</p>
    {:else if naptar && naptar.esemenyek.length}
      <ul class="lista" role="list">
        {#each naptar.esemenyek as e (e.azon)}
          <li>
            <span class="ido">{idoSzoveg(e)}</span>
            <span class="pont" style:background={e.szin || 'var(--keret-eros)'} aria-hidden="true"></span>
            <span class="szoveg">{e.cim}</span>
            {#if e.hely}<span class="halvany">{e.hely}</span>{/if}
          </li>
        {/each}
      </ul>
    {:else if naptar}
      <p class="ures">{t('Nincs esemény a naptárban.')}</p>
    {/if}
  </section>

  <!-- ------------------------------------------------------------- napi jegyzet -->
  <section aria-labelledby="ma-napi">
    <h2 id="ma-napi">{t('Napi jegyzet')}</h2>
    {#if hibaSzoveg(adat?.napi)}
      <p class="ures">{hibaSzoveg(adat?.napi)}</p>
    {:else if napi?.letezik}
      <div class="kartya">
        <p class="cim">{fajlNev(napi.ut)}</p>
        {#if napi.kivonat}<p class="kivonat">{napi.kivonat}</p>{:else}<p class="ures">{t('A jegyzet még üres.')}</p>{/if}
        <button type="button" class="m-gomb semleges gomb" onclick={() => regiszter.futtat('naplo.napi', 'gomb')}>
          <Ikon ikon={CalendarCheck} /> {t('Megnyitás')} <Billentyu akkord="Mod+Shift+D" />
        </button>
      </div>
    {:else if napi}
      <div class="sor">
        <span class="ures">{t('Még nincs.')}</span>
        <button type="button" class="m-gomb semleges gomb" onclick={() => regiszter.futtat('naplo.napi', 'gomb')}>
          <Ikon ikon={CalendarCheck} /> {t('Létrehozás')} <Billentyu akkord="Mod+Shift+D" />
        </button>
      </div>
    {/if}
  </section>

  <!-- ------------------------------------------------------------- feladatok -->
  <section aria-labelledby="ma-feladat">
    <h2 id="ma-feladat">
      {t('Feladatok ma')}
      {#if feladatok}<span class="szam">{feladatok.osszes_ma}</span>{/if}
    </h2>
    {#if hibaSzoveg(adat?.feladatok)}
      <p class="ures">{hibaSzoveg(adat?.feladatok)}</p>
    {:else if feladatok && feladatok.ma.length}
      <ul class="lista" role="list">
        {#each feladatok.ma as f (f.ut + ':' + f.sor)}
          <li>
            <button type="button" class="sor-gomb" onclick={(e) => feladatNyit(f, e)} title={f.ut}>
              <span class="szoveg">{f.szoveg}</span>
              <span class="halvany">{fajlNev(f.ut)}</span>
            </button>
          </li>
        {/each}
      </ul>
    {:else if feladatok}
      <p class="ures" title={t('A feladat végére írt 📅 ÉÉÉÉ-HH-NN (vagy [due:: ÉÉÉÉ-HH-NN]) adja a határidőt.')}>{t('Nincs mára esedékes feladat.')}</p>
    {/if}
    {#if feladatok && feladatok.lejart.length}
      <h3>{t('Lejárt')} <span class="szam">{feladatok.osszes_lejart}</span></h3>
      <ul class="lista" role="list">
        {#each feladatok.lejart as f (f.ut + ':' + f.sor)}
          <li>
            <button type="button" class="sor-gomb" onclick={(e) => feladatNyit(f, e)} title={mappa(f.ut) || f.ut}>
              <span class="ido">{f.hatarido ? napRovid(f.hatarido) : ''}</span>
              <span class="szoveg">{f.szoveg}</span>
              <span class="halvany">{fajlNev(f.ut)}</span>
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  </section>

  <!-- ------------------------------------------------------------- kártyák (C23b) -->
  <section aria-labelledby="ma-kartya">
    <h2 id="ma-kartya">
      {t('Kártyák')}
      <span class="szam">{kartyak && kartyak.allapot === 'kesz' ? kartyak.esedekes + (kartyak.uj ?? 0) : '—'}</span>
    </h2>
    {#if kartyak && kartyak.allapot === 'kesz'}
      <p class="halvany kartya-sor">
        {t('{n} esedékes', { n: kartyak.esedekes })} · {t('{n} új', { n: kartyak.uj ?? 0 })}{kartyak.holnap ? ` · ${t('holnap {n}', { n: kartyak.holnap })}` : ''}
        {#if kartyak.esedekes + (kartyak.uj ?? 0) > 0}
          <button class="m-gomb link" type="button" onclick={() => maiIsmetles(felulet)}>{t('Ismétlés')}</button>
        {/if}
      </p>
    {:else if adat && hibas(adat.kartyak)}
      <p class="halvany">{hibaSzoveg(adat.kartyak)}</p>
    {/if}
  </section>

  <!-- ------------------------------------------------------------- asszisztens (csak ha van mit mutatni) -->
  <Asszisztens szakasz={adat?.asszisztens} datum={adat?.datum} />
  <details class="rendszer" bind:open={felulet.manifoldRendszer}>
    <summary>{t('Rendszer és beállítások')}</summary>
    {#if felulet.manifoldRendszer}<ManifoldLap />{/if}
  </details>
</div>

<style>
  .gyors-muveletek { display: flex; flex-wrap: wrap; gap: var(--t-2); margin-block: var(--t-4); }
  .datum { margin: var(--t-2) 0; color: var(--szoveg-halvany); }
  .rendszer { margin-top: var(--t-8); border-top: var(--keret-vastag) solid var(--keret); padding-top: var(--t-4); }
  summary { cursor: pointer; color: var(--szoveg-halvany); }

  .ma {
    max-width: var(--olvasasi-szelesseg);
    margin-inline: auto;
    padding: var(--t-7) var(--t-5) var(--t-8);
    font-size: var(--betu-ui);
    line-height: var(--sor-ui);
    color: var(--szoveg);
  }

  h1 {
    margin: 0;
    font-size: var(--betu-h1);
    line-height: 1.25;
    font-weight: var(--suly-cim);
    letter-spacing: -0.015em;
  }

  .regi {
    margin: var(--t-2) 0 0;
    color: var(--szoveg-halvany);
  }

  section {
    margin-top: var(--t-6);
  }

  h2,
  h3 {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin: 0 0 var(--t-2);
    padding-bottom: var(--t-1);
    border-bottom: var(--keret-vastag) solid var(--keret);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    font-weight: var(--suly-felkover);
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--szoveg-halvany);
  }

  h3 {
    margin-top: var(--t-4);
    border-bottom: 0;
    padding-bottom: 0;
  }

  .szam {
    font-variant-numeric: tabular-nums;
    letter-spacing: 0;
  }

  .kartya {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--t-2);
  }

  .cim {
    display: flex;
    align-items: center;
    gap: var(--t-2);
    margin: 0;
    font-size: var(--betu-h3);
    line-height: var(--magassag-sor);
    font-weight: var(--suly-felkover);
  }

  .meta,
  .kivonat {
    margin: 0;
    color: var(--szoveg-masodlagos);
  }

  .kivonat {
    display: -webkit-box;
    -webkit-line-clamp: 3;
    line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
    max-width: 100%;
  }

  .lista {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .lista li {
    display: flex;
    align-items: center;
    gap: var(--t-3);
    min-height: var(--magassag-sor);
  }

  .ido {
    flex: none;
    min-width: 88px;
    color: var(--szoveg-halvany);
    font-variant-numeric: tabular-nums;
  }

  .szoveg {
    flex: 0 1 auto;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .halvany {
    flex: 1 1 0;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
  }

  .pont {
    flex: none;
    width: 8px;
    height: 8px;
    border-radius: var(--kerekites-kor);
  }

  .ures {
    margin: 0;
    color: var(--szoveg-halvany);
  }

  .hiba {
    margin: var(--t-4) 0 0;
    padding: var(--t-2) var(--t-3);
    border-radius: var(--kerekites);
    background: var(--hiba-hatter);
    color: var(--hiba);
  }

  .sor {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--t-3);
    min-height: var(--magassag-sor);
  }

  .gomb {
    display: inline-flex;
    align-items: center;
    gap: var(--t-2);
  }

  .gomb:focus-visible,
  .sor-gomb:focus-visible {
    outline: var(--fokusz-vastag) solid var(--fokusz-gyuru);
    outline-offset: var(--fokusz-tav);
  }

  .sor-gomb {
    display: flex;
    align-items: center;
    gap: var(--t-3);
    width: 100%;
    min-height: var(--magassag-sor);
    padding: 0 var(--t-2);
    margin-inline: calc(var(--t-2) * -1);
    border: 0;
    border-radius: var(--kerekites-kicsi);
    background: transparent;
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
  }

  .sor-gomb:hover {
    background: var(--hatter-hover);
  }

  .sor-gomb:active {
    background: var(--hatter-aktiv);
  }

  .sor-gomb:focus-visible {
    outline-offset: var(--fokusz-tav-befele);
  }

  .kartya-sor {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--t-2);
    margin: 0;
    font-variant-numeric: tabular-nums;
  }
</style>
