<!--
  „Új” jegyzet a nézetből (10-bases-07) és a Kanban-oszlop „+”-ja (10-bases-14). A gomb egy névmezőt nyit; a Létrehozás a meglévő
  biztonságos úton hoz létre jegyzetet (meglévő fájlt nem ír felül: ütközésnél a hiba látszik, a név megmarad), majd az egyértelmű,
  szűrőkből (vagy az oszlopból) származó tulajdonságokat a tulajdonság-műveleten át beírja. Az előtöltés a mezők alatt előre látszik.
  Billentyű: Enter létrehoz, Esc zár.
-->
<script lang="ts">
  import { t, tp } from '../lib/i18n';
  import { tick } from 'svelte';
  import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { Plus } from '../lib/ikon/ikonok';
  import { beallitasok } from '../lib/beallitasok/allapot.svelte';
  import { getContext } from 'svelte';
  import { KORNYEZET_KULCS, type Kornyezet } from '../lib/kornyezet';
  import { pillanatVisszavon } from './cellaIr';
  import { alapMappa, ujAdat, ujJegyzetLetrehoz } from './ujJegyzet';
  import type { Ertek, Valasz } from './tipusok';

  interface Props {
    v: Valasz;
    /** a nézetet tartalmazó fájl (az alapértelmezett mappa ehhez igazodik) */
    ez?: string | null;
    /** egy csoport (Kanban-oszlop) értéke: a csoportosító tulajdonságot ez adja */
    oszlop?: { ertek: Ertek; cimke: string };
    /** csak ikon (a Kanban-oszlop fejlécében) */
    ikonCsak?: boolean;
    /** a létrehozott jegyzet útja (a hívó, pl. teszt, kapja meg); alapból megnyílik */
    kesz?: (ut: string) => void;
    /** a hívó aktuális írási kapuja; a nyitott űrlap alatt megváltozó readonly/ütközés is érvényesül */
    letrehozasTiltva?: () => string | null;
  }
  let { v, ez = null, oszlop, ikonCsak = false, kesz, letrehozasTiltva }: Props = $props();

  const kornyezet = getContext<Kornyezet | undefined>(KORNYEZET_KULCS);
  let nyitva = $state(false);
  let nev = $state('');
  let hiba = $state<string | null>(null);
  let folyamat = $state(false);
  let mezo: HTMLInputElement | undefined = $state();

  const adat = $derived(ujAdat(v, oszlop ? { ertek: oszlop.ertek } : undefined));
  const mappa = $derived(adat.mappa ?? alapMappa(beallitasok.adat ? beallitasok.ertek.fajlok.uj_mappa : '', ez));
  const cimke = $derived(oszlop ? t('Új jegyzet ebben az oszlopban: {oszlop}', { oszlop: oszlop.cimke }) : t('Új jegyzet'));
  const elozetes = $derived(
    [...adat.tulajdonsagok.map((x) => `${x.kulcs}: ${Array.isArray(x.ertek) ? x.ertek.join(', ') : String(x.ertek)}`)].join(' · '),
  );

  async function kapcsol() {
    nyitva = !nyitva;
    hiba = null;
    if (nyitva) {
      await tick();
      mezo?.focus();
    }
  }

  async function letrehoz() {
    if (folyamat) return;
    const tiltas = letrehozasTiltva?.();
    if (tiltas) {
      hiba = tiltas;
      return;
    }
    folyamat = true;
    hiba = null;
    const r = await ujJegyzetLetrehoz(nev, mappa, adat);
    folyamat = false;
    if (!r.ok || !r.ut) {
      hiba = r.hiba ?? t('A jegyzet nem jött létre.');
      await tick();
      mezo?.focus();
      return;
    }
    nyitva = false;
    nev = '';
    for (const f of r.figyelmeztetesek) ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: t('Az új jegyzet tulajdonsága nem íródott be'), szoveg: f });
    if (r.pillanat) {
      const p = r.pillanat;
      ertesitesek.ertesit({
        szint: 'info',
        cim: t('Új jegyzet létrehozva'),
        szoveg: r.ut,
        idotartam: 6000,
        muvelet: { nev: t('Tulajdonságok visszavonása'), futtat: () => void pillanatVisszavon(p) },
      });
    }
    if (kesz) kesz(r.ut);
    else kornyezet?.felulet.munkaterulet.megnyit(r.ut, 'aktiv');
  }

  function billentyu(e: KeyboardEvent) {
    if (e.isComposing) return;
    if (e.key === 'Enter') {
      e.preventDefault();
      void letrehoz();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      nyitva = false;
    }
  }
</script>

<span class="uj" class:ikoncsak={ikonCsak}>
  <button type="button" class="gomb" aria-expanded={nyitva} title={cimke} aria-label={ikonCsak ? cimke : undefined} onclick={() => void kapcsol()}>
    <Ikon ikon={Plus} meret={14} />{#if !ikonCsak}<span>{t('Új')}</span>{/if}
  </button>
  {#if nyitva}
    <span class="urlap" role="group" aria-label={cimke}>
      <input
        bind:this={mezo}
        type="text"
        class="nev"
        aria-label={t('Az új jegyzet neve')}
        aria-invalid={hiba ? 'true' : undefined}
        placeholder={t('Jegyzet neve')}
        autocomplete="off"
        spellcheck="false"
        bind:value={nev}
        onkeydown={billentyu}
      />
      <button type="button" class="m-gomb suru" disabled={folyamat || !nev.trim()} onclick={() => void letrehoz()}>{folyamat ? '…' : t('Létrehozás')}</button>
      <button type="button" class="m-gomb semleges suru" onclick={() => (nyitva = false)}>{t('Mégse')}</button>
      <span class="segito">
        {mappa ? t('Mappa: {mappa}', { mappa }) : t('Mappa: a vault gyökere')}{#if elozetes} · {elozetes}{/if}{#if adat.nemEgyertelmu.length} · {tp('{n} ellentmondó feltétel kimaradt', adat.nemEgyertelmu.length)}{/if}
      </span>
      {#if hiba}<span class="hiba" role="alert">{hiba}</span>{/if}
    </span>
  {/if}
</span>

<style>
  .uj {
    display: inline-flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--t-1);
  }

  .gomb {
    display: inline-flex;
    align-items: center;
    gap: var(--t-1);
    height: var(--magassag-gomb);
    padding: 0 var(--t-2);
    border: 0;
    border-radius: var(--kerekites-kicsi);
    background: transparent;
    color: var(--szoveg-masodlagos);
    font: inherit;
    white-space: nowrap;
    cursor: pointer;
  }

  .ikoncsak .gomb {
    height: var(--magassag-suru);
    padding: 0 var(--t-1);
    color: var(--szoveg-halvany);
  }

  .gomb:hover,
  .gomb[aria-expanded='true'] {
    background: var(--hatter-hover);
    color: var(--szoveg);
  }

  .gomb:focus-visible {
    outline: var(--fokusz-vastag) solid var(--fokusz-gyuru);
    outline-offset: var(--fokusz-tav);
  }

  .urlap {
    display: inline-flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--t-1);
  }

  .nev {
    box-sizing: border-box;
    height: var(--magassag-suru);
    width: 180px;
    padding: 0 var(--t-1);
    border: 1px solid var(--keret-mezo);
    border-radius: var(--kerekites-kicsi);
    background: var(--hatter);
    color: var(--szoveg);
    font: inherit;
  }

  .nev[aria-invalid='true'] {
    border-color: var(--hiba);
  }

  .nev:focus-visible {
    outline: var(--fokusz-vastag) solid var(--fokusz-gyuru);
    outline-offset: calc(-1 * var(--keret-vastag));
  }

  .segito {
    flex-basis: 100%;
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
  }

  .hiba {
    flex-basis: 100%;
    color: var(--hiba);
    font-size: var(--betu-kicsi);
  }
</style>
