<!--
  A „Rendszer” szakasz (C17): memória, a modellzár birtokosa, a betöltött modell és a keret, az SSD, az utolsó mentés
  és a „Mentés most” gomb. Az adat csak nyitott lap és látszó ablak mellett frissül.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { ertesitesek } from '../../lib/ertesites/ertesites.svelte';
  import { vezerloApi } from '../../lib/vezerlo/api';
  import { gb, idoRovid, mb } from '../../lib/vezerlo/megjelenites';
  import { rendszerAllapot } from '../../lib/vezerlo/rendszer.svelte';
  import TeljesMentes from './TeljesMentes.svelte';
  import { epitesAllapot } from '../../lib/vezerlo/epites.svelte';

  let mentesFut = $state(false);
  // a build-állapot a közös tárból: a friss (60 s-on belüli) választ a szakasz újranyitása nem kéri újra (a core minden
  // lekérésre hash-el); amíg a core a mag ujjlenyomatát számolja, 3 s-onként újrakérdez
  const epites = $derived(epitesAllapot.adat);
  const epitesHiba = $derived(epitesAllapot.hiba);
  onMount(() => {
    void epitesAllapot.frissit();
  });
  $effect(() => {
    if (!epitesAllapot.szamol) return;
    const t = setTimeout(() => void epitesAllapot.frissit(true), 3000);
    return () => clearTimeout(t);
  });
  const r = $derived(rendszerAllapot.adat);

  onMount(() => rendszerAllapot.indit());

  async function mentes() {
    mentesFut = true;
    try {
      await vezerloApi.mentesInditas();
      ertesitesek.ertesit({ szint: 'info', cim: 'A mentés elindult', szoveg: 'A belső lemezre készül a szöveges pillanatkép.' });
    } catch (e) {
      ertesitesek.ertesit({ szint: 'hiba', cim: 'A mentés nem indult el', szoveg: e instanceof Error ? e.message : String(e) });
    } finally {
      mentesFut = false;
      setTimeout(() => void rendszerAllapot.frissit(), 3000);
    }
  }

  const zarSzoveg = $derived.by(() => {
    if (!r) return '';
    const z = r.modellzar;
    if (z.szabad) return z.elavult ? 'szabad (elavult bejegyzés)' : 'szabad';
    return `${z.repo ?? 'ismeretlen modell'} · pid ${z.pid}${z.ido ? ` · ${z.ido} óta` : ''}`;
  });
</script>

{#if rendszerAllapot.hiba && !r}
  <p class="hiba" role="alert">A rendszerállapot nem érhető el: {rendszerAllapot.hiba}</p>
{:else if !r}
  <p class="halvany" role="status">Betöltés…</p>
{:else}
  {#if epites}
    <p class:figy={!epites.ok && !epitesAllapot.szamol}>
      {epitesAllapot.szamol
        ? 'A build állapotának ellenőrzése folyik (a mag ujjlenyomata számolódik)…'
        : epites.ok
          ? 'A futó alkalmazás a forrással egyezik.'
          : 'Elavult alkalmazásrészek: újrafordítás vagy újraindítás szükséges.'}
      <small>Mag: {epites.mag ?? 'számolás folyik'} · {epites.reszek.map((r) => `${r.resz}: ${r.azonosito || (epitesAllapot.szamol ? 'számolás folyik' : 'ismeretlen')}${r.friss ? '' : ' (elavult)'}`).join(' · ')}</small>
    </p>
  {:else if epitesHiba}<p class="figy">A build állapota nem ellenőrizhető: {epitesHiba}</p>{/if}
  <dl>
    <dt>Memória</dt>
    <dd>
      {r.memoria.szabad_szazalek >= 0 ? `${r.memoria.szabad_szazalek} % szabad` : 'nem mérhető'} · {gb(r.memoria.osszes_gb)}
      {#if r.memoria.core_rss_mb}<small>core: {mb(r.memoria.core_rss_mb)}{r.worker.fut && r.worker.rss_mb ? `, worker: ${mb(r.worker.rss_mb)}` : ''}</small>{/if}
    </dd>
    <dt>Modellzár</dt>
    <dd>{zarSzoveg}</dd>
    <dt>Betöltött modell</dt>
    <dd>
      {#if r.worker.fut && r.worker.modell}
        {r.worker.modell}{r.worker.keret_gb ? ` · keret ${gb(r.worker.keret_gb)}` : ''}
        {#if r.worker.szunetek}<small>{r.worker.szunetek} memóriaőr-szünet</small>{/if}
      {:else if r.worker.fut}
        nincs betöltve <small>a worker fut</small>
      {:else}
        nincs <small>a worker nem fut</small>
      {/if}
    </dd>
    <dt>Kötet</dt>
    <dd>
      {#if r.ssd.elerheto}{r.ssd.kotet} · {gb(r.ssd.szabad_gb)} szabad / {gb(r.ssd.osszes_gb)}{:else}nem érhető el{/if}
    </dd>
    <dt>Utolsó mentés</dt>
    <dd>
      {#if r.mentes.utolso}{idoRovid(r.mentes.utolso)}{:else}még nem volt{/if}
      {#if !r.mentes.friss}<small class="figy">a mentés régebbi a legutóbbi változásnál</small>{/if}
      {#if r.mentes.hiba}
        <small class="hiba-sor" role="alert">
          A belső lemezes mentés nem sikerült{r.mentes.hiba.ido ? ` (${idoRovid(r.mentes.hiba.ido)})` : ''}:
          {Object.entries(r.mentes.hiba.hibak).map(([nev, uzenet]) => `${nev}: ${uzenet}`).join('; ')}
        </small>
      {/if}
    </dd>
  </dl>
  <button type="button" class="m-gomb semleges gomb" disabled={mentesFut} onclick={mentes}>Mentés most</button>
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

  .hiba {
    margin: 0;
    padding: var(--t-2);
    border-radius: var(--kerekites);
    background: var(--hiba-hatter);
    color: var(--hiba);
    font-size: var(--betu-kicsi);
  }

</style>
