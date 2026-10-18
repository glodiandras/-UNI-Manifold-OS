<!--
  Csoportok kezelése (10-bases-05): a `groupOrder` szerkesztése. Soronként jelölőnégyzet (látszik-e), a csoport neve és a sorok száma,
  ↑↓ a sorrendhez; alul „Automatikus sorrend” (törli a kulcsot). Az elrejtett csoport sorai nem látszanak a nézetben. A csoportosító
  tulajdonságot a „Nézet” panel választja. Az írás a meglévő `nezet_beallit` művelet (az ismeretlen kulcsok érintetlenek).
-->
<script lang="ts">
  import { t } from '../lib/i18n';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { ArrowDown, ArrowUp } from '../lib/ikon/ikonok';
  import {
    csoportLathatoValt,
    csoportMozgat,
    csoportSorok,
    csoportSorrendMuvelet,
    kezdiSorrend,
    type CsoportKulcs,
  } from './csoportok';
  import type { BazisModell } from './modell.svelte';
  import { azonosNev } from './muveletek';
  import type { Valasz } from './tipusok';

  let { modell, v }: { modell: BazisModell; v: Valasz } = $props();

  const nezet = $derived(v.nezet?.index ?? 0);
  const sorok = $derived(csoportSorok(v));
  const kezi = $derived(kezdiSorrend(v) !== null);
  const tulajdonsag = $derived.by(() => {
    const g = v.nezet?.beallitas?.groupBy as { property?: string } | undefined;
    return g?.property ? azonosNev(v, g.property) : null;
  });
  const ir = (lista: CsoportKulcs[] | null) => void modell.alkalmaz(csoportSorrendMuvelet(nezet, lista));
</script>

<div class="csoportok">
  {#if !v.csoportok}
    <p class="segito">{t('Előbb válassz csoportosító tulajdonságot a „Nézet” panelen.')}</p>
  {:else}
    <p class="segito">
      {#if tulajdonsag}{t('Csoportosítás: {nev}', { nev: tulajdonsag })} · {/if}{kezi ? t('Kézi sorrend') : t('Automatikus sorrend')}
    </p>
    <ul class="lista" aria-label={t('Csoportok')}>
      {#each sorok as s, i (`${i}-${String(s.kulcs)}`)}
        <li class="sor" class:rejtett={!s.lathato}>
          <label class="jelolo">
            <input type="checkbox" checked={s.lathato} onchange={(e) => ir(csoportLathatoValt(sorok, i, e.currentTarget.checked))} />
            <span class="nev">{s.cimke || t('Nincs érték')}</span>
            <span class="db">{s.db}</span>
          </label>
          {#if s.lathato}
            <button type="button" class="gomb" aria-label={t('{nev} feljebb', { nev: s.cimke || t('Nincs érték') })} disabled={csoportMozgat(sorok, i, -1) === null} onclick={() => ir(csoportMozgat(sorok, i, -1))}>
              <Ikon ikon={ArrowUp} meret={14} />
            </button>
            <button type="button" class="gomb" aria-label={t('{nev} lejjebb', { nev: s.cimke || t('Nincs érték') })} disabled={csoportMozgat(sorok, i, 1) === null} onclick={() => ir(csoportMozgat(sorok, i, 1))}>
              <Ikon ikon={ArrowDown} meret={14} />
            </button>
          {/if}
        </li>
      {/each}
    </ul>
    {#if kezi}
      <button type="button" class="m-gomb semleges suru" onclick={() => ir(null)}>{t('Automatikus sorrend')}</button>
    {/if}
  {/if}
  {#if modell.irasHiba}<p class="hiba" role="alert">{modell.irasHiba}</p>{/if}
</div>

<style>
  .csoportok {
    display: flex;
    flex-direction: column;
    gap: var(--t-2);
  }

  .lista {
    display: flex;
    flex-direction: column;
    gap: 2px;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .sor {
    display: flex;
    align-items: center;
    gap: var(--t-1);
  }

  .sor.rejtett .nev {
    color: var(--szoveg-halvany);
    text-decoration: line-through;
  }

  .jelolo {
    flex: 1;
    display: flex;
    align-items: center;
    gap: var(--t-2);
    min-width: 0;
  }

  .nev {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .db {
    color: var(--szoveg-halvany);
    font-variant-numeric: tabular-nums;
  }

  .gomb {
    flex: none;
    display: inline-grid;
    place-items: center;
    height: var(--magassag-suru);
    width: var(--magassag-suru);
    border: 0;
    border-radius: var(--kerekites-kicsi);
    background: transparent;
    color: var(--szoveg-masodlagos);
    cursor: pointer;
  }

  .gomb:hover:not(:disabled) {
    background: var(--hatter-hover);
    color: var(--szoveg);
  }

  .gomb:disabled {
    opacity: var(--tiltott-atlatszosag);
    cursor: default;
  }

  .gomb:focus-visible {
    outline: var(--fokusz-vastag) solid var(--fokusz-gyuru);
    outline-offset: var(--fokusz-tav);
  }

  .segito {
    margin: 0;
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
  }

  .hiba {
    margin: 0;
    color: var(--hiba);
    font-size: var(--betu-kicsi);
  }
</style>
