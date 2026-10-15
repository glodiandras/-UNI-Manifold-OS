<!--
  A `.canvas` fül nézete (C14): a fájl a `Dokumentum`-án át nyílik (ugyanaz a mentés/ütközés/külső változás út, mint
  a jegyzetnél), a vászon a `Vaszon`. A fejlécben a morzsa, a mentés és az írhatóság állapota; ha a fájl nem
  olvasható JSON Canvas-ként, a hiba helye és szövege látszik, és a canvas csak olvasható (a nézet nem ír).
-->
<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import { ApiHiba } from '../lib/core/api';
  import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
  import type { NezetProps } from '../lib/elrendezes/nezetek.svelte';
  import { kornyezet } from '../lib/kornyezet';
  import JegyzetIkon from '../lib/ui/JegyzetIkon.svelte';
  import { fajlNev, mappa } from '../lib/vault/fajlok.svelte';
  import { szerkesztok } from '../szerkeszto/szerkesztok.svelte';
  import { vagolapra } from '../szerkeszto/vagolap';
  import Utkozes from '../szerkeszto/Utkozes.svelte';
  import { CanvasForras } from './forras';
  import { beolvas } from './modell';
  import Vaszon from './Vaszon.svelte';

  let { ful, aktiv }: NezetProps = $props();
  const { kapcsolat } = kornyezet();
  const ut = untrack(() => ful.ut ?? '');
  let forras = $state.raw<CanvasForras | null>(null);
  let hiba = $state<string | null>(null);
  let utkozesNyitva = $state(true);
  let olvasasJel = $state(0);

  onMount(() => {
    let el = true;
    let nyitott: CanvasForras | null = null;
    let le = () => {};
    CanvasForras.nyit(ut, szerkesztok.dokumentumok).then(
      (f) => {
        if (!el) return void f.lezar();
        nyitott = forras = f;
        le = f.figyel(() => olvasasJel++);
      },
      (e) => {
        if (!el) return;
        hiba =
          e instanceof ApiHiba && e.statusz === 404
            ? 'A canvas nincs meg (törölték vagy áthelyezték).'
            : `A canvas nem tölthető be: ${e instanceof Error ? e.message : e}`;
      },
    );
    return () => {
      el = false;
      le();
      void nyitott?.lezar();
    };
  });

  const dok = $derived(forras?.dok ?? null);

  /** Mentési hibánál kiút: a lemezen lévő változat betöltése (visszavonhatóan); a saját szöveg a vágólapra is kerül. */
  async function lemezenLevoBetolt() {
    const d = dok;
    if (!d) return;
    try {
      const lemez = await d.olvasLemezrol();
      const sajat = d.fajlSzoveg();
      d.lemezrolBetolt(lemez, true);
      const ok = await vagolapra(sajat);
      ertesitesek.ertesit({
        szint: 'info',
        cim: 'A lemezen lévő változat betöltve',
        szoveg: ok ? 'A saját szöveged a vágólapon van.' : 'A canvas visszaállt a lemezen lévő változatra.',
      });
    } catch (e) {
      ertesitesek.ertesit({ szint: 'hiba', cim: 'A lemezen lévő változat nem tölthető be', szoveg: e instanceof Error ? e.message : String(e) });
    }
  }
  const olvasas = $derived.by(() => {
    void olvasasJel;
    return forras?.allapot ?? null;
  });
  const allapotSzoveg = $derived.by(() => {
    switch (dok?.allapot) {
      case 'mentes':
        return 'Mentés…';
      case 'hiba':
        return 'Mentési hiba';
      case 'eltunt':
        return 'A fájl eltűnt';
      default:
        return '';
    }
  });
</script>

<article class="canvas-ful">
  <header class="fejlec">
    <p class="morzsa" title={ut}>
      <span class="morzsa-ikon"><JegyzetIkon {ut} tipus="canvas" meret={14} /></span>
      {#if mappa(ut)}<span class="mappa">{`${mappa(ut).replaceAll('/', ' / ')} / `}</span>{/if}<span class="nev">{fajlNev(ut)}</span>
    </p>
    <div class="jelek" role="status">
      {#if dok?.csakOlvashato || olvasas?.hiba}
        <span class="jel figyelmeztetes" title={dok?.csakOlvashato ?? olvasas?.hiba ?? undefined}>Csak olvasható</span>
      {/if}
      {#if olvasas?.figyelmeztetesek.length}
        <span class="jel" title={olvasas.figyelmeztetesek.join('\n')}>{olvasas.figyelmeztetesek.length} eltérés a spectől</span>
      {/if}
      {#if dok?.allapot === 'utkozes'}
        <button type="button" class="jel hiba gomb" onclick={() => (utkozesNyitva = true)}>Ütközés — döntés kell</button>
      {:else if allapotSzoveg}
        <span class="jel" class:hiba={dok?.allapot !== 'mentes'} title={dok?.hiba ?? undefined}>{allapotSzoveg}</span>
        {#if dok?.allapot === 'hiba'}
          <!-- a core elutasította a mentést (pl. 400), vagy a mentés újra és újra elbukik: a lemezen lévő változat a kiút (T030) -->
          <button type="button" class="jel gomb" onclick={lemezenLevoBetolt}>A lemezen lévő betöltése</button>
        {/if}
      {/if}
    </div>
  </header>

  {#if forras && olvasas?.vaszon}
    <Vaszon {forras} {ful} {aktiv} {kapcsolat} />
  {:else if forras && olvasas?.hiba}
    <div class="olvasasi-hiba" role="alert">
      <p>{olvasas.hiba}</p>
      <p class="halvany">A fájl változatlan marad; javítsd Obsidianban vagy szövegszerkesztőben, és a nézet magától újratölt.</p>
    </div>
  {:else if hiba}
    <p class="betoltes hiba" role="alert">{hiba}</p>
  {:else}
    <p class="betoltes" role="status">Betöltés…</p>
  {/if}

  {#if dok?.allapot === 'utkozes' && utkozesNyitva && aktiv}
    <Utkozes {dok} onbezar={() => (utkozesNyitva = false)} ellenoriz={(szoveg) => beolvas(szoveg).hiba} />
  {/if}
</article>

<style>
  .canvas-ful {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    background: var(--hatter);
  }

  .fejlec {
    flex: none;
    display: flex;
    align-items: center;
    gap: var(--t-2);
    height: var(--magassag-fejlec);
    padding: 0 var(--t-4);
  }

  .morzsa {
    flex: 1 1 auto;
    min-width: 0;
    margin: 0;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
    font-size: var(--betu-ui);
    line-height: var(--sor-ui);
    color: var(--szoveg-halvany);
  }

  .morzsa-ikon {
    display: inline-flex;
    vertical-align: -2px;
    margin-right: var(--t-1);
  }

  .nev {
    color: var(--szoveg-masodlagos);
  }

  .jelek {
    flex: none;
    display: flex;
    gap: var(--t-2);
  }

  .jel {
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi, 16px);
    color: var(--szoveg-halvany);
    padding: 2px var(--t-2);
    border-radius: var(--kerekites-kicsi);
  }

  .jel.figyelmeztetes {
    color: var(--figyelmeztetes);
    background: var(--figyelmeztetes-hatter);
  }

  .jel.hiba {
    color: var(--hiba);
    background: var(--hiba-hatter);
  }

  .gomb {
    border: none;
    cursor: pointer;
    font: inherit;
  }

  .olvasasi-hiba {
    margin: var(--t-4);
    padding: var(--t-3) var(--t-4);
    border-radius: var(--kerekites);
    background: var(--hiba-hatter);
    color: var(--hiba);
  }

  .olvasasi-hiba p {
    margin: 0 0 var(--t-1);
  }

  .olvasasi-hiba .halvany {
    color: var(--szoveg-masodlagos);
  }

  .betoltes {
    margin: var(--t-4);
    color: var(--szoveg-halvany);
  }

  .betoltes.hiba {
    color: var(--hiba);
  }
</style>
