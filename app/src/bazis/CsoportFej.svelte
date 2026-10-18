<!--
  Egy csoport fejléce összecsukással (10-bases-06): a gomb `aria-expanded`-del nyit/zár; a csoport neve és a sorok száma látszik.
  A Kártyák és a Lista közös eleme; a Táblázat a saját csoportsorán belül használja.
-->
<script lang="ts">
  import { t } from '../lib/i18n';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { ChevronDown, ChevronRight } from '../lib/ikon/ikonok';

  interface Props {
    cimke: string;
    db: number;
    zart: boolean;
    kapcsol: () => void;
  }
  let { cimke, db, zart, kapcsol }: Props = $props();
  const nev = $derived(cimke || t('Nincs érték'));
</script>

<button
  type="button"
  class="csoport-fej"
  aria-expanded={!zart}
  aria-label={zart ? t('{nev} csoport kinyitása', { nev }) : t('{nev} csoport összecsukása', { nev })}
  onclick={kapcsol}
>
  <Ikon ikon={zart ? ChevronRight : ChevronDown} meret={14} />
  <span class="nev">{nev}</span>
  <span class="db">{db}</span>
</button>

<style>
  .csoport-fej {
    display: inline-flex;
    align-items: center;
    gap: var(--t-1);
    min-width: 0;
    padding: 0 var(--t-1);
    border: 0;
    border-radius: var(--kerekites-kicsi);
    background: transparent;
    color: inherit;
    font: inherit;
    font-weight: var(--suly-felkover);
    cursor: pointer;
  }

  .csoport-fej:hover {
    background: var(--hatter-hover);
  }

  .csoport-fej:focus-visible {
    outline: var(--fokusz-vastag) solid var(--fokusz-gyuru);
    outline-offset: var(--fokusz-tav);
  }

  .nev {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .db {
    color: var(--szoveg-halvany);
    font-weight: var(--suly-normal);
    font-variant-numeric: tabular-nums;
  }
</style>
