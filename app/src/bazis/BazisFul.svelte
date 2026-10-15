<!--
  A `.base` fül nézete (C12): a fájl a `Dokumentum`-án át nyílik (ugyanaz a mentés/ütközés/külső változás út, mint a
  jegyzetnél), a nézet a `BazisNezet`. Az aktív nézet sorszáma a fül tartós állapotában marad.
-->
<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import { ApiHiba } from '../lib/core/api';
  import type { NezetProps } from '../lib/elrendezes/nezetek.svelte';
  import { kornyezet } from '../lib/kornyezet';
  import JegyzetIkon from '../lib/ui/JegyzetIkon.svelte';
  import { fajlNev, mappa } from '../lib/vault/fajlok.svelte';
  import BazisNezet from './BazisNezet.svelte';
  import { fajlForras, type BazisForras } from './forras';

  let { ful }: NezetProps = $props();
  const { kapcsolat } = kornyezet();
  const ut = untrack(() => ful.ut ?? '');
  const kezdoNezet = untrack(() => {
    const n = ful.nezet?.bazisNezet;
    return typeof n === 'number' || typeof n === 'string' ? n : null;
  });
  let forras = $state.raw<BazisForras | null>(null);
  let hiba = $state<string | null>(null);

  onMount(() => {
    let el = true;
    let nyitott: BazisForras | null = null;
    fajlForras(ut).then(
      (f) => {
        if (!el) return void f.lezar();
        nyitott = forras = f;
      },
      (e) => {
        if (!el) return;
        hiba =
          e instanceof ApiHiba && e.statusz === 404
            ? 'Az adatbázis-nézet nincs meg (törölték vagy áthelyezték).'
            : `Az adatbázis-nézet nem tölthető be: ${e instanceof Error ? e.message : e}`;
      },
    );
    return () => {
      el = false;
      void nyitott?.lezar();
    };
  });

  function nezetValtott(i: number) {
    ful.nezet = { ...(ful.nezet ?? {}), bazisNezet: i };
  }
</script>

<article class="bazis-ful">
  <header class="fejlec">
    <p class="morzsa">
      <span class="morzsa-ikon"><JegyzetIkon {ut} tipus="base" /></span>
      {#if mappa(ut)}{mappa(ut).replaceAll('/', ' / ')} / {/if}<span class="nev">{fajlNev(ut)}</span>
    </p>
  </header>
  {#if forras}
    <BazisNezet {forras} {kapcsolat} nezet={kezdoNezet} {nezetValtott} />
  {:else if hiba}
    <p class="hiba" role="alert">{hiba}</p>
  {:else}
    <p class="betoltes" role="status">Betöltés…</p>
  {/if}
</article>

<style>
  .bazis-ful {
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
    height: var(--magassag-fejlec);
    padding: 0 var(--t-4);
  }

  .morzsa {
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
    vertical-align: -3px;
    margin-right: var(--t-1);
  }

  .nev {
    color: var(--szoveg-masodlagos);
  }

  .hiba,
  .betoltes {
    margin: var(--t-4);
    color: var(--szoveg-halvany);
  }

  .hiba {
    color: var(--hiba);
  }
</style>
