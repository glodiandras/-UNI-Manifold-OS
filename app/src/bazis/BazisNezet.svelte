<!--
  A Bases-nézet kerete (C12): eszköztár, hibák és figyelmeztetések, és alatta a nézet maga (táblázat, kártyák vagy Kanban),
  vagy a teljes YAML-forrás. Három helyen él: `.base` fülön, ```` ```base ```` blokkban és `![[x.base]]` beágyazásban — a
  szöveget a `BazisForras` adja. A beállítások (rendezés, oszlopok, szűrők, nézetek…) az egyetlen írási úton íródnak vissza.
  A találatszám `title`-je a core és a rajzolás idejét mutatja (cél: 2000 soron együtt < 300 ms).
-->
<script lang="ts">
  import { onMount, tick, untrack } from 'svelte';
  import type { CoreKapcsolat } from '../lib/core/ws.svelte';
  import type { BazisApi } from './api';
  import Eszkoztar from './Eszkoztar.svelte';
  import type { BazisForras } from './forras';
  import Kanban from './Kanban.svelte';
  import Kartyak from './Kartyak.svelte';
  import { BazisModell } from './modell.svelte';
  import SzovegMezo from './SzovegMezo.svelte';
  import Tabla from './Tabla.svelte';
  import type { BazisHiba } from './tipusok';

  interface Props {
    forras: BazisForras;
    kapcsolat?: CoreKapcsolat | null;
    api?: BazisApi;
    /** a kezdő nézet (sorszám vagy név) */
    nezet?: number | string | null;
    /** a nézetváltás jelzése (a fül tartós állapotába) */
    nezetValtott?: (index: number) => void;
    /** beágyazva: korlátozott magasság, nincs külső keret */
    kompakt?: boolean;
    /** a ```` ```base ```` blokk forrásának megnyitása (csak a Live Preview blokkjában van) */
    forrasGomb?: () => void;
  }
  let { forras, kapcsolat = null, api, nezet = null, nezetValtott, kompakt = false, forrasGomb }: Props = $props();

  const modell = untrack(() => new BazisModell(forras, { api, kapcsolat, nezet }));
  const v = $derived(modell.valasz);
  let rajzIdo = $state<number | null>(null);

  onMount(() => {
    modell.indit();
    return () => modell.lebont();
  });

  // a rajzolás ideje: a válasz megérkezésétől az első kész festésig
  $effect(() => {
    if (!modell.valasz) return;
    const t0 = modell.megerkezett;
    void tick().then(() => {
      rajzIdo = Math.round(performance.now() - t0);
    });
  });

  const idoSzoveg = $derived(
    v
      ? `core: ${v.ido_ms} ms${v.tabla_ms ? ` + sorhalmaz: ${v.tabla_ms} ms` : ''}${rajzIdo !== null ? ` · rajz: ${rajzIdo} ms` : ''}`
      : '',
  );
  /** a nézet beállításai írhatók (a fájl nem csak olvasható, nincs ütközés); a válasz érkezésekor frissül */
  const irhato = $derived.by(() => {
    void modell.valasz;
    return forras.csakOlvashato() === null;
  });
  const cellaIras = $derived.by(() => {
    void modell.valasz;
    return forras.cellaIras?.() ?? true;
  });
  const forrasSzoveg = $derived.by(() => {
    void modell.valasz;
    return forras.szoveg();
  });

  async function forrasEllenorzes(szoveg: string): Promise<BazisHiba[]> {
    return (await modell.modosit({ fajta: 'forras_csere', szoveg })).hibak;
  }

  async function forrasIras(szoveg: string): Promise<boolean> {
    const r = await modell.alkalmaz({ fajta: 'forras_csere', szoveg });
    return r.ok && r.irva;
  }

  function valtott(i: number) {
    nezetValtott?.(i);
  }
</script>

<section class="bazis" class:kompakt aria-label="Adatbázis-nézet">
  {#if v}
    <Eszkoztar {modell} {v} {irhato} {idoSzoveg} nezetValtott={valtott} {forrasGomb} />
    {#if modell.irasHiba}
      <p class="uzenet hiba" role="alert">{modell.irasHiba}</p>
    {/if}
    {#each v.hibak as h, i (i)}
      <p class="uzenet hiba" role="alert">
        {h.hely === 'yaml' ? 'A .base fájl nem értelmezhető' : `Hiba (${h.hely})`}: {h.uzenet}{h.db ? ` — ${h.db} sort kihagytam` : ''}
      </p>
    {/each}
    {#each v.figyelmeztetesek as h, i (i)}
      <p class="uzenet figyelmeztetes" role="status">{h.uzenet}</p>
    {/each}
    {#if modell.forrasMod}
      <div class="forras-mod">
        <SzovegMezo
          cimke="A .base fájl teljes YAML-forrása"
          ertek={forrasSzoveg}
          sorok={kompakt ? 12 : 22}
          gomb="Alkalmaz"
          uresEngedett
          ellenorzes={forrasEllenorzes}
          alkalmaz={forrasIras}
        />
        <p class="segito">Forrásnézetben a megjegyzések megmaradnak; a nézet beállításainak módosítása a fájlt újraírja (a megjegyzések ilyenkor elvesznek).</p>
      </div>
    {:else if v.ok}
      {#if v.nezet?.tipus === 'cards'}
        <Kartyak valasz={v} ez={forras.ez} />
      {:else if v.nezet?.tipus === 'kanban'}
        <Kanban valasz={v} ez={forras.ez} {cellaIras} />
      {:else}
        <Tabla
          valasz={v}
          ez={forras.ez}
          magassag={kompakt ? 460 : null}
          {irhato}
          {cellaIras}
          muvelet={(m) => void modell.alkalmaz(m)}
          atnevez={(id, nev) => void modell.alkalmaz({ fajta: 'megjelenites_beallit', id, displayName: nev })}
        />
      {/if}
    {/if}
  {:else if modell.hiba}
    <p class="uzenet hiba" role="alert">Az adatbázis-nézet nem tölthető be: {modell.hiba}</p>
  {:else}
    <p class="uzenet" role="status">Betöltés…</p>
  {/if}
</section>

<style>
  .bazis {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
    min-width: 0;
    /* a szerkesztő (`.cm-content`) `pre-wrap`-ja nem szivároghat be: a sorok közti szóköz-csomópontok üres sorokat adnának */
    white-space: normal;
    cursor: default;
    text-align: left;
  }

  .bazis.kompakt {
    flex: none;
    border: var(--keret-vastag) solid var(--keret);
    border-radius: var(--kerekites);
  }

  .uzenet {
    flex: none;
    margin: 0;
    padding: var(--t-1) var(--t-3);
    color: var(--szoveg-halvany);
    font-size: var(--betu-ui);
    line-height: var(--sor-ui);
  }

  .uzenet.hiba {
    color: var(--hiba);
    background: var(--hiba-hatter);
  }

  .uzenet.figyelmeztetes {
    color: var(--figyelmeztetes);
    background: var(--figyelmeztetes-hatter);
  }

  .forras-mod {
    flex: 1;
    min-height: 0;
    overflow: auto;
    padding: var(--t-3);
    font-size: var(--betu-ui);
  }

  .segito {
    margin: var(--t-2) 0 0;
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
  }
</style>
