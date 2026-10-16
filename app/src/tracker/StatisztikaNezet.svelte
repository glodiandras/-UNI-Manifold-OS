<!--
  A Statisztika nézet (C27): a tanulási tevékenység napokra és hetekre — aktív idő, szerkesztett karakterek, kártya-,
  kvíz- és integrálás-darabok (a gyűjtőik a C20–C23-ban kötnek be, addig „nincs adat”), a naptár tervezett tanulási blokkjai —
  tantárgyanként és jegyzetenként, saját SVG-grafikonokkal. A szám mindig szövegben is látszik. Az adatot a
  core aggregálja; ez a nézet csak olvas. Csak az app eseményeit látja (a kapcsoló a vezérlőben van).
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { t } from '../lib/i18n';
  import type { NezetProps } from '../lib/elrendezes/nezetek.svelte';
  import { fajlNev } from '../lib/vault/fajlok.svelte';
  import { vezerloKapcsolok } from '../lib/vezerlo/kapcsolok.svelte';
  import { StatisztikaAdat } from '../lib/tracker/adat.svelte';
  import Oszlopok from '../lib/tracker/grafikon/Oszlopok.svelte';
  import Savok from '../lib/tracker/grafikon/Savok.svelte';
  import { idoSzoveg, napCimke, napSzoveg, szamSzoveg } from '../lib/tracker/megjelenites';

  let {}: NezetProps = $props();
  const modell = new StatisztikaAdat();

  // A nézet a csatolástól a lebontásig látszik (a panel nem aktív fülét a Panel le sem csatolja): addig tölt és
  // frissül, akkor is, ha a panel nem az aktív (T167).
  onMount(() => modell.megjelenik());

  const adat = $derived(modell.adat);
  const bontas = $derived(adat?.bontas ?? modell.bontas);
  const oszlopok = $derived(
    (adat?.napok ?? []).map((n) => ({
      cimke: napCimke(n.nap, bontas),
      ertek: n.aktiv_mp,
      terv: n.terv_mp || undefined,
      cim: n.terv_mp
        ? t('{nap}: {ido} aktív, tervezett {terv}', { nap: napSzoveg(n.nap, bontas), ido: idoSzoveg(n.aktiv_mp), terv: idoSzoveg(n.terv_mp) })
        : t('{nap}: {ido} aktív', { nap: napSzoveg(n.nap, bontas), ido: idoSzoveg(n.aktiv_mp) }),
    })),
  );
  const savok = $derived((adat?.tantargyak ?? []).map((x) => ({ nev: x.tantargy, ertek: x.aktiv_mp, szoveg: idoSzoveg(x.aktiv_mp) })));
  const nincsAdat = (v: number, ok: boolean) => (ok || v > 0 ? szamSzoveg(v) : t('nincs adat'));
</script>

<div class="statisztika olvasas">
  <header>
    <h1>{t('Statisztika')}</h1>
    <div class="vezerlok">
      <div class="csoport" role="group" aria-label={t('Bontás')}>
        <button type="button" aria-pressed={modell.bontas === 'nap'} onclick={() => modell.valt('nap')}>{t('Nap')}</button>
        <button type="button" aria-pressed={modell.bontas === 'het'} onclick={() => modell.valt('het')}>{t('Hét')}</button>
      </div>
      <div class="csoport" role="group" aria-label={t('Tartomány')}>
        <button type="button" aria-label={t('Korábbi tartomány')} onclick={() => modell.lapoz(1)}>←</button>
        <span class="tartomany">{adat ? `${napSzoveg(adat.tol)} – ${napSzoveg(adat.ig)}` : ''}</span>
        <button type="button" aria-label={t('Későbbi tartomány')} disabled={modell.lap === 0} onclick={() => modell.lapoz(-1)}>→</button>
      </div>
    </div>
  </header>

  {#if modell.hiba && !adat}
    <p class="hiba" role="alert">{t('A statisztika nem tölthető be:')} {modell.hiba}</p>
  {:else if modell.hiba}
    <p class="hiba" role="alert">{t('A frissítés nem sikerült ({hiba}): a korábban betöltött adat látszik.', { hiba: modell.hiba })}</p>
  {/if}
  {#if !vezerloKapcsolok.ertek.tracker}
    <p class="figy" role="status">{t('A Tracker ki van kapcsolva: új adat nem gyűlik (a vezérlőben kapcsolható be). A korábbi adatok látszanak.')}</p>
  {/if}

  {#if adat}
    <dl class="osszegzes">
      <div><dt>{t('Aktív idő')}</dt><dd>{idoSzoveg(adat.osszes.aktiv_mp)}</dd></div>
      <div>
        <dt>{t('Szerkesztett karakter')}</dt>
        <dd>{szamSzoveg(adat.osszes.beszurt + adat.osszes.torolt)} <small>+{szamSzoveg(adat.osszes.beszurt)} / −{szamSzoveg(adat.osszes.torolt)}</small></dd>
      </div>
      <div><dt>{t('Kártyaválasz')}</dt><dd>{nincsAdat(adat.osszes.kartya, adat.elerheto.kartya)}</dd></div>
      <div><dt>{t('Kvíz')}</dt><dd>{nincsAdat(adat.osszes.kviz, adat.elerheto.kviz)}</dd></div>
      <div><dt>{t('Integrált tétel')}</dt><dd>{nincsAdat(adat.osszes.integralt, adat.elerheto.integralt)}</dd></div>
      <div><dt>{t('Tervezett tanulási idő')}</dt><dd>{adat.elerheto.terv ? idoSzoveg(adat.osszes.terv_mp) : t('nincs adat')}</dd></div>
    </dl>

    <section aria-labelledby="st-ido">
      <h2 id="st-ido">{bontas === 'nap' ? t('Aktív idő naponta') : t('Aktív idő hetente')}</h2>
      <Oszlopok {oszlopok} leiras={bontas === 'nap' ? t('Az aktív idő naponta, a tervezett tanulási idővel jelölve') : t('Az aktív idő hetente, a tervezett tanulási idővel jelölve')} />
      <p class="lab">{t('Szaggatott vonal: a naptár tanulási blokkjainak tervezett ideje. Aktív idő: az ablak elöl van, és 60 mp-en belül volt bevitel.')}</p>
      <table>
        <thead><tr><th>{bontas === 'nap' ? t('Nap') : t('Hét')}</th><th>{t('Aktív')}</th><th>{t('Karakter')}</th><th>{t('Tervezett tanulás')}</th></tr></thead>
        <tbody>
          {#each adat.napok as n (n.nap)}
            <tr>
              <td>{napSzoveg(n.nap, bontas)}</td>
              <td>{idoSzoveg(n.aktiv_mp)}</td>
              <td>{szamSzoveg(n.beszurt + n.torolt)}</td>
              <td>{n.terv_mp ? idoSzoveg(n.terv_mp) : '–'}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </section>

    <section aria-labelledby="st-tantargy">
      <h2 id="st-tantargy">{t('Tantárgyanként')}</h2>
      {#if savok.length}
        <Savok {savok} leiras={t('Az aktív idő tantárgyanként')} />
      {:else}
        <p class="ures">{t('Ebben a tartományban nincs rögzített aktív idő.')}</p>
      {/if}
    </section>

    <section aria-labelledby="st-jegyzet">
      <h2 id="st-jegyzet">{t('Legtöbbet használt jegyzetek')}</h2>
      {#if adat.jegyzetek.length}
        <ul class="lista">
          {#each adat.jegyzetek as j (j.ut)}
            <li><span class="nev" title={j.ut}>{fajlNev(j.ut)}</span><span class="halvany">{j.tantargy}</span><span class="szam">{idoSzoveg(j.aktiv_mp)}</span></li>
          {/each}
        </ul>
      {:else}
        <p class="ures">{t('Még nincs adat.')}</p>
      {/if}
    </section>
  {:else if !modell.hiba}
    <p class="ures" role="status">{t('Betöltés…')}</p>
  {/if}
</div>

<style>
  .statisztika {
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

  .vezerlok,
  .csoport {
    display: flex;
    align-items: center;
    gap: var(--t-2);
  }

  .vezerlok {
    flex-wrap: wrap;
    gap: var(--t-4);
  }

  .csoport button {
    min-width: var(--magassag-gomb);
    height: var(--magassag-gomb);
    padding: 0 var(--t-3);
    border: var(--keret-vastag) solid var(--keret-eros);
    border-radius: var(--kerekites);
    background: transparent;
    color: var(--szoveg);
    font: inherit;
    cursor: pointer;
  }

  .csoport button:hover:not(:disabled) {
    background: var(--hatter-hover);
  }

  .csoport button[aria-pressed='true'] {
    background: var(--hatter-aktiv);
    border-color: var(--akcent);
  }

  .csoport button:disabled {
    opacity: var(--tiltott-atlatszosag);
    cursor: default;
  }

  .csoport button:focus-visible {
    outline: var(--fokusz-vastag) solid var(--fokusz-gyuru);
    outline-offset: var(--fokusz-tav);
  }

  .tartomany {
    min-width: 168px;
    text-align: center;
    color: var(--szoveg-halvany);
    font-variant-numeric: tabular-nums;
  }

  .osszegzes {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: var(--t-3) var(--t-4);
    margin: var(--t-5) 0 0;
  }

  .osszegzes div {
    min-width: 0;
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

  .lab,
  .ures {
    margin: var(--t-2) 0 0;
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  table {
    width: 100%;
    margin-top: var(--t-3);
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

  .nev {
    flex: 1 1 0;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .halvany {
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
  }

  .szam {
    min-width: 64px;
    text-align: right;
    font-variant-numeric: tabular-nums;
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
