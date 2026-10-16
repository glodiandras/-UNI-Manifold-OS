<!--
  A vezérlő „Naptár és emlékeztetők” szakasza (C29): az engedélyek két sora, az utolsó szinkron és a „Szinkron most”,
  az emlékeztető-tükör számai, az ütközések (a jegyzet nyert) láttamozással, a naptárak kategóriái (a javaslatot
  meg kell erősíteni) és a legutóbbi naptár-változások. Csak nyitott szakasznál tölt; a naptárba itt nem írunk.
-->
<script lang="ts">
  import { t } from '../../lib/i18n';
  import { onMount } from 'svelte';
  import { naptarVezerlo as modell } from '../../lib/naptar/allapot.svelte';
  import { naptarHid } from '../../lib/naptar/hid.svelte';
  import { engedelySzoveg, mikorSzoveg, szinkronEredmeny, utkozesFajtaSzoveg, valtozasSor } from '../../lib/naptar/megjelenites';
  import { maiNap } from '../../lib/tracker/megjelenites';
  import { fajlNev } from '../../lib/vault/fajlok.svelte';

  onMount(() => modell.megjelenik());

  const a = $derived(modell.adat);
  const ma = $derived(maiNap());
  const hejben = $derived(naptarHid.elerheto);
  const kerheto = $derived(a?.esemeny_engedely === 'nincs_dontes' || a?.emlekezteto_engedely === 'nincs_dontes');
  const beallitando = $derived(
    [a?.esemeny_engedely, a?.emlekezteto_engedely].some((s) => s === 'megtagadva' || s === 'korlatozott' || s === 'csak_iras'),
  );
  const nyitottUtkozesek = $derived((a?.emlekezteto_allapot.utkozesek ?? []).filter((u) => !u.latva));
  const lattUtkozes = $derived((a?.emlekezteto_allapot.utkozesek.length ?? 0) - nyitottUtkozesek.length);
  const nevek = $derived(new Map((a?.naptarak ?? []).map((n) => [n.azon, n.nev])));
</script>

{#if modell.hiba && !a}
  <p class="hiba" role="alert">{t('A naptár állapota nem érhető el: {hiba}', { hiba: modell.hiba })}</p>
{:else if !a}
  <p class="halvany" role="status">{t('Betöltés…')}</p>
{:else}
  <dl>
    <dt>{t('Naptár')}</dt>
    <dd>{engedelySzoveg(a.esemeny_engedely)}</dd>
    <dt>{t('Emlékeztetők')}</dt>
    <dd>{engedelySzoveg(a.emlekezteto_engedely)}</dd>
  </dl>
  {#if kerheto}
    {#if hejben}
      <button type="button" class="m-gomb semleges gomb" disabled={naptarHid.kerdesben} onclick={() => naptarHid.kerd()}>
        {naptarHid.kerdesben ? t('A rendszer ablakában döntsd el…') : t('Naptár-engedély kérése')}
      </button>
      {#if naptarHid.hiba}<p class="hiba" role="alert">{naptarHid.hiba}</p>{/if}
    {:else}
      <p class="halvany">{t('Az engedélyt a Manifold.app kéri; böngészőből nem kérhető.')}</p>
    {/if}
  {/if}
  {#if beallitando}
    <p class="halvany">{t('A hozzáférést a Rendszerbeállítások › Adatvédelem és biztonság › Naptárak (és Emlékeztetők) alatt engedélyezheted.')}</p>
  {/if}

  <dl>
    <dt>{t('Utolsó szinkron')}</dt>
    <dd>{mikorSzoveg(a.utolso ?? a.utolso_szinkron?.vege, ma)}</dd>
    <dt>{t('Eredmény')}</dt>
    <dd>{szinkronEredmeny(a)}</dd>
  </dl>
  <button type="button" class="m-gomb semleges gomb" disabled={modell.foglalt} onclick={() => void modell.szinkron()}>
    {modell.foglalt ? t('Szinkronizálás…') : t('Szinkron most')}
  </button>
  {#if modell.muveletHiba}<p class="hiba" role="alert">{modell.muveletHiba}</p>{/if}

  <h3>{t('Emlékeztetők tükre')}</h3>
  {#if a.emlekezteto_allapot.be}
    <dl>
      <dt>{t('Aktív')}</dt>
      <dd>{a.emlekezteto_allapot.tukor.aktiv}</dd>
      <dt>{t('Kézzel törölt')}</dt>
      <dd>{a.emlekezteto_allapot.tukor.kezi_torolt}</dd>
    </dl>
  {:else}
    <p class="halvany">{t('Az emlékeztető-tükör ki van kapcsolva.')}</p>
  {/if}

  <h3 class="sor">
    <span>{t('Ütközések')}</span>
    {#if nyitottUtkozesek.length > 1}
      <button type="button" class="szoveg-gomb" onclick={() => void modell.utkozesLatva()}>{t('Mind láttam')}</button>
    {/if}
  </h3>
  {#if nyitottUtkozesek.length}
    <ul class="lista">
      {#each nyitottUtkozesek as u (u.id)}
        <li>
          <div class="szoveg">
            <span class="cim" title={u.ut ?? ''}>{u.szoveg || (u.ut ? fajlNev(u.ut) : t('Emlékeztető'))}</span>
            <span class="halvany">{utkozesFajtaSzoveg(u.fajta)} · {mikorSzoveg(u.mikor, ma)}</span>
            {#if u.reszlet}<span class="halvany">{u.reszlet}</span>{/if}
          </div>
          <button type="button" class="szoveg-gomb" aria-label={t('Láttam: {mi}', { mi: u.szoveg || u.fajta })} onclick={() => void modell.utkozesLatva([u.id])}>
            {t('Láttam')}
          </button>
        </li>
      {/each}
    </ul>
  {:else}
    <p class="halvany">{t('Nincs új ütközés.')}{lattUtkozes ? ` ${t('({n} már látott)', { n: lattUtkozes })}` : ''}</p>
  {/if}

  <h3>{t('Naptárak')}</h3>
  {#if a.naptarak.length}
    <ul class="lista">
      {#each a.naptarak as n (n.azon)}
        {@const folyamatban = modell.kategoriaFolyamatban.includes(n.azon)}
        <li class="naptar" class:eltunt={!!n.eltunt}>
          <div class="szoveg">
            <span class="cim"><span class="pont" style:background={n.szin || 'var(--keret-eros)'} aria-hidden="true"></span>{n.nev}{n.eltunt ? ` ${t('(eltűnt)')}` : ''}</span>
            {#if n.kategoria_forras === 'javaslat'}
              <span class="javaslat">{t('javaslat — erősítsd meg')}</span>
            {/if}
          </div>
          <select
            aria-label={t('Kategória: {nev}', { nev: n.nev })}
            disabled={folyamatban}
            value={n.kategoria}
            onchange={(e) => void modell.kategoriaAllit(n.azon, e.currentTarget.value)}
          >
            {#each a.kategoriak as k (k.id)}
              <option value={k.id}>{k.nev}</option>
            {/each}
            {#if !a.kategoriak.some((k) => k.id === n.kategoria)}<option value={n.kategoria}>{n.kategoria}</option>{/if}
          </select>
          {#if n.kategoria_forras === 'javaslat'}
            <button
              type="button"
              class="szoveg-gomb"
              disabled={folyamatban}
              aria-label={t('Megerősítem: {nev}', { nev: n.nev })}
              onclick={() => void modell.kategoriaAllit(n.azon, n.kategoria)}
            >
              {t('Megerősítem')}
            </button>
          {/if}
        </li>
      {/each}
    </ul>
  {:else}
    <p class="halvany">{t('Még nincs beolvasott naptár.')}</p>
  {/if}

  {#if a.valtozasok.length}
    <h3>{t('Változások')}</h3>
    <ul class="lista">
      {#each a.valtozasok.slice(0, 5) as v, i (v.mikor + v.azon + v.fajta + i)}
        <li>
          <span class="szoveg"><span class="cim">{valtozasSor(v, nevek.get(v.azon))}</span></span>
          <span class="halvany ido">{mikorSzoveg(v.mikor, ma)}</span>
        </li>
      {/each}
    </ul>
  {/if}
{/if}

<style>
  dl {
    display: grid;
    grid-template-columns: max-content 1fr;
    gap: var(--t-1) var(--t-3);
    margin: 0 0 var(--t-2);
  }

  dt {
    color: var(--szoveg-halvany);
  }

  dd {
    margin: 0;
    min-width: 0;
    overflow-wrap: anywhere;
  }

  h3 {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin: var(--t-3) 0 var(--t-1);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    font-weight: var(--suly-felkover);
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--szoveg-halvany);
  }

  .lista {
    margin: 0 0 var(--t-2);
    padding: 0;
    list-style: none;
  }

  .lista li {
    display: flex;
    align-items: center;
    gap: var(--t-2);
    min-height: var(--magassag-sor);
    padding: var(--t-1) 0;
  }

  .szoveg {
    flex: 1 1 0;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }

  .cim {
    display: flex;
    align-items: center;
    gap: var(--t-2);
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .eltunt .cim {
    color: var(--szoveg-halvany);
  }

  .pont {
    flex: none;
    width: 8px;
    height: 8px;
    border-radius: var(--kerekites-kor);
  }

  .halvany {
    margin: 0 0 var(--t-2);
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  .szoveg .halvany,
  .lista .halvany {
    margin: 0;
  }

  .ido {
    flex: none;
    font-variant-numeric: tabular-nums;
  }

  .javaslat {
    color: var(--figyelmeztetes);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  .hiba {
    margin: var(--t-2) 0 0;
    padding: var(--t-2);
    border-radius: var(--kerekites);
    background: var(--hiba-hatter);
    color: var(--hiba);
  }

  select {
    flex: none;
    max-width: 150px;
    height: var(--magassag-gomb);
    padding: 0 var(--t-2);
    border: var(--keret-vastag) solid var(--keret-eros);
    border-radius: var(--kerekites);
    background: transparent;
    color: var(--szoveg);
    font: inherit;
    font-size: var(--betu-kicsi);
  }

  .szoveg-gomb {
    flex: none;
    padding: 0 var(--t-2);
    height: var(--magassag-gomb);
    border: 0;
    border-radius: var(--kerekites);
    background: transparent;
    color: var(--akcent-szoveg);
    font: inherit;
    font-size: var(--betu-kicsi);
    letter-spacing: 0;
    text-transform: none;
    cursor: pointer;
  }

  .szoveg-gomb:hover:not(:disabled) {
    background: var(--hatter-hover);
  }

  .gomb:disabled,
  .szoveg-gomb:disabled,
  select:disabled {
    cursor: default;
    color: var(--szoveg-halvany);
  }

  .gomb:focus-visible,
  .szoveg-gomb:focus-visible,
  select:focus-visible {
    outline: var(--fokusz-vastag) solid var(--fokusz-gyuru);
    outline-offset: var(--fokusz-tav);
  }
</style>
