<!--
  A Használat nézet (C27, a V2.1 mérése): parancsonkénti használat, a gépi írások elfogadása és visszavonása
  funkciónként, a mentési és a gépelési késleltetés (p50, p95, max), a memóriaőr szünetei. Jegyzettartalmat és
  útvonalat nem tartalmaz: csak azonosítók és számok. Az „elfogadás” származtatott (írás − visszavonás): a gépi írás
  automatikus döntés, egykattintásos visszavonással (D1). A késleltetés p95-e a vödör felső határa („legfeljebb”).
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { t, tk, tp } from '../lib/i18n';
  import type { NezetProps } from '../lib/elrendezes/nezetek.svelte';
  import { vezerloKapcsolok } from '../lib/vezerlo/kapcsolok.svelte';
  import Adatkezeles from '../lib/tracker/Adatkezeles.svelte';
  import { HasznalatAdat } from '../lib/tracker/adat.svelte';
  import Kesleltetes from '../lib/tracker/grafikon/Kesleltetes.svelte';
  import { forrasNev, idoSzoveg, msSzoveg, szamSzoveg, szazalekSzoveg } from '../lib/tracker/megjelenites';

  let {}: NezetProps = $props();
  const modell = new HasznalatAdat();

  // A nézet a csatolástól a lebontásig látszik (a panel nem aktív fülét a Panel le sem csatolja): addig tölt és
  // frissül, akkor is, ha a panel nem az aktív (T167).
  onMount(() => modell.megjelenik());

  const adat = $derived(modell.adat);
  const KESLELTETESEK = [
    { kulcs: 'gepeles', cim: tk('Gépelés'), leiras: tk('a billentyű leütésétől a szerkesztő frissítéséig (a képernyő frissítésére várás nélkül)') },
    { kulcs: 'mentes', cim: tk('Mentés'), leiras: tk('az automatikus mentés kérésétől a válaszig') },
  ] as const;
</script>

<div class="hasznalat olvasas">
  <header>
    <h1>{t('Használat')}</h1>
    <div class="csoport" role="group" aria-label={t('Tartomány')}>
      {#each [7, 30, 90] as n (n)}
        <button type="button" aria-pressed={modell.napok === n} onclick={() => modell.valt(n)}>{tp('{n} nap', n)}</button>
      {/each}
    </div>
  </header>
  <p class="lab">{t('Mit használsz, mit vonsz vissza, hol lassú — a V2.1 rangsorához. Csak azonosítók és számok, jegyzettartalom nincs benne.')}</p>

  {#if modell.hiba && !adat}
    <p class="hiba" role="alert">{t('A használati adat nem tölthető be:')} {modell.hiba}</p>
  {:else if modell.hiba}
    <p class="hiba" role="alert">{t('A frissítés nem sikerült ({hiba}): a korábban betöltött adat látszik.', { hiba: modell.hiba })}</p>
  {/if}
  {#if !vezerloKapcsolok.ertek.tracker}
    <p class="figy" role="status">{t('A Tracker ki van kapcsolva: új adat nem gyűlik. A korábbi adatok látszanak.')}</p>
  {/if}

  {#if adat}
    <section aria-labelledby="h-parancs">
      <h2 id="h-parancs">{t('Parancsok')}</h2>
      {#if adat.parancsok.length}
        <table>
          <thead><tr><th>{t('Parancs')}</th><th class="szam">{t('Használat')}</th><th>{t('Honnan')}</th></tr></thead>
          <tbody>
            {#each adat.parancsok.slice(0, 25) as p (p.parancs)}
              <tr>
                <td><code>{p.parancs}</code></td>
                <td class="szam">{szamSzoveg(p.db)}</td>
                <td class="halvany">
                  {Object.entries(p.forrasok)
                    .sort((a, b) => b[1] - a[1])
                    .map(([f, d]) => `${forrasNev(f)} ${d}`)
                    .join(' · ')}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
        {#if adat.parancsok.length > 25}<p class="lab">{t('A leggyakoribb 25 a {n}-ból.', { n: adat.parancsok.length })}</p>{/if}
      {:else}
        <p class="ures">{t('Még nincs rögzített parancshasználat.')}</p>
      {/if}
    </section>

    <section aria-labelledby="h-gepi">
      <h2 id="h-gepi">{t('Gépi írások funkciónként')}</h2>
      {#if adat.gepi.length}
        <table>
          <thead><tr><th>{t('Funkció')}</th><th class="szam">{t('Írás')}</th><th class="szam">{t('Visszavonás')}</th><th class="szam">{t('Elfogadás')}</th></tr></thead>
          <tbody>
            {#each adat.gepi as g (g.funkcio)}
              <tr>
                <td><code>{g.funkcio}</code></td>
                <td class="szam">{szamSzoveg(g.iras)}</td>
                <td class="szam">{szamSzoveg(g.visszavonas)}</td>
                <td class="szam">{szazalekSzoveg(g.elfogadas)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      {:else}
        <p class="ures">{t('Még nem írt gép a vaultba.')}</p>
      {/if}
    </section>

    <section aria-labelledby="h-kes">
      <h2 id="h-kes">{t('Késleltetés')}</h2>
      {#each KESLELTETESEK as k (k.kulcs)}
        {@const v = adat.kesleltetes[k.kulcs]}
        <div class="kes">
          <h3>{t(k.cim)} <small>{t(k.leiras)}</small></h3>
          {#if v.db > 0 && v.vedrok}
            <p class="osszeg">
              <span>p50 ≤ <b>{msSzoveg(v.p50_ms)}</b></span>
              <span>p95 ≤ <b>{msSzoveg(v.p95_ms)}</b></span>
              <span>max <b>{msSzoveg(v.max_ms)}</b></span>
              <span class="halvany">{tp('{n} minta', v.db, { n: szamSzoveg(v.db) })}</span>
            </p>
            <Kesleltetes vedrok={v.vedrok} hatarok={adat.vedrok_ms} p50={v.p50_ms} p95={v.p95_ms} leiras={t('{nev} késleltetésének eloszlása', { nev: t(k.cim) })} />
          {:else}
            <p class="ures">{t('Még nincs minta.')}</p>
          {/if}
        </div>
      {/each}
      <p class="lab">{t('A p50 és a p95 a vödör felső határa (ms): a minták fele, illetve 95 %-a ennél nem lassabb.')}</p>
    </section>

    <section aria-labelledby="h-szunet">
      <h2 id="h-szunet">{t('Memóriaőr')}</h2>
      <dl class="szunet">
        <div><dt>{t('Memória-szünet')}</dt><dd>{szamSzoveg(adat.szunetek.memoria.db)} <small>{idoSzoveg(adat.szunetek.memoria.mp)}</small></dd></div>
        <div><dt>{t('Hűtési szünet')}</dt><dd>{szamSzoveg(adat.szunetek.hutes.db)}</dd></div>
      </dl>
    </section>

    <section aria-labelledby="h-adat">
      <h2 id="h-adat">{t('Adatok')}</h2>
      <p class="lab">{t('Az exportot a core a személyes mappába írja, és a vágólapra is másolja. A törlés csak a tracker adatát érinti.')}</p>
      <Adatkezeles />
    </section>
  {:else if !modell.hiba}
    <p class="ures" role="status">{t('Betöltés…')}</p>
  {/if}
</div>

<style>
  .hasznalat {
    max-width: var(--olvasasi-szelesseg);
    margin-inline: auto;
    padding: var(--t-7) var(--t-5) var(--t-8);
    font-size: var(--betu-ui);
    line-height: var(--sor-ui);
    color: var(--szoveg);
  }

  header {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--t-3);
  }

  h1 {
    margin: 0;
    font-size: var(--betu-h1);
    line-height: 1.25;
    font-weight: var(--suly-cim);
    letter-spacing: -0.015em;
  }

  .csoport {
    display: flex;
    gap: var(--t-2);
  }

  .csoport button {
    height: var(--magassag-gomb);
    padding: 0 var(--t-3);
    border: var(--keret-vastag) solid var(--keret-eros);
    border-radius: var(--kerekites);
    background: transparent;
    color: var(--szoveg);
    font: inherit;
    cursor: pointer;
  }

  .csoport button:hover {
    background: var(--hatter-hover);
  }

  .csoport button[aria-pressed='true'] {
    background: var(--hatter-aktiv);
    border-color: var(--akcent);
  }

  .csoport button:focus-visible {
    outline: var(--fokusz-vastag) solid var(--fokusz-gyuru);
    outline-offset: var(--fokusz-tav);
  }

  section {
    margin-top: var(--t-6);
  }

  h2 {
    margin: 0 0 var(--t-3);
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
    margin: var(--t-4) 0 var(--t-1);
    font-size: var(--betu-h5);
    font-weight: var(--suly-felkover);
  }

  h3 small {
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
    font-weight: var(--suly-normal);
  }

  .lab,
  .ures {
    margin: var(--t-2) 0 0;
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  table {
    width: 100%;
    border-collapse: collapse;
    font-variant-numeric: tabular-nums;
  }

  th,
  td {
    padding: var(--t-1) var(--t-2) var(--t-1) 0;
    text-align: left;
    font-size: var(--betu-kicsi);
    border-bottom: var(--keret-vastag) solid var(--keret);
  }

  th {
    color: var(--szoveg-halvany);
    font-weight: var(--suly-kozepes);
  }

  .szam {
    text-align: right;
    padding-right: var(--t-3);
  }

  code {
    font-family: var(--betu-mono);
  }

  .halvany {
    color: var(--szoveg-halvany);
  }

  .osszeg {
    display: flex;
    flex-wrap: wrap;
    gap: var(--t-2) var(--t-4);
    margin: 0 0 var(--t-2);
    font-variant-numeric: tabular-nums;
  }

  .szunet {
    display: flex;
    flex-wrap: wrap;
    gap: var(--t-3) var(--t-6);
    margin: 0;
  }

  dt {
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
  }

  dd {
    margin: 0;
    font-size: var(--betu-h4);
    font-weight: var(--suly-felkover);
    font-variant-numeric: tabular-nums;
  }

  dd small {
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
    font-weight: var(--suly-normal);
  }

  .hiba,
  .figy {
    margin: var(--t-3) 0 0;
    padding: var(--t-2) var(--t-3);
    border-radius: var(--kerekites);
  }

  .hiba {
    background: var(--hiba-hatter);
    color: var(--hiba);
  }

  .figy {
    background: var(--figyelmeztetes-hatter);
    color: var(--figyelmeztetes);
  }
</style>
