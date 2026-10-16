<!--
  A „Ma” oldal naptár-szakaszának jelzése (C29): halk, de látható sor arról, miért nincs (friss) naptáradat — nincs
  segéd, nincs engedély vagy a szinkron hibát jelzett. Az engedély kérése csak a Manifold.app-ból megy (a rendszer
  ablakát a héj mutatja); böngészőből csak a magyarázat látszik. Megtagadott engedélynél csak a teendő szövege áll.
-->
<script lang="ts">
  import { t } from '../lib/i18n';
  import { naptarHid } from '../lib/naptar/hid.svelte';
  import { naptarJelzes } from '../lib/naptar/megjelenites';
  import type { NaptarAllapotSzakasz, Hiba } from './tipusok';

  let { szakasz }: { szakasz: NaptarAllapotSzakasz | Hiba | undefined } = $props();

  const jelzes = $derived(naptarJelzes(szakasz));
  const hejben = $derived(naptarHid.elerheto);
</script>

{#if jelzes}
  <div class="jelzes" role="status">
    <p>{jelzes.szoveg}</p>
    {#if jelzes.kerheto}
      {#if hejben}
        <button type="button" class="m-gomb semleges gomb" disabled={naptarHid.kerdesben} onclick={() => naptarHid.kerd()}>
          {naptarHid.kerdesben ? t('A rendszer ablakában döntsd el…') : t('Naptár-engedély kérése')}
        </button>
        {#if naptarHid.hiba}<p class="hiba" role="alert">{naptarHid.hiba}</p>{/if}
      {:else}
        <p class="halvany">{t('Az engedélyt a Manifold.app kéri; böngészőből nem kérhető.')}</p>
      {/if}
    {/if}
  </div>
{/if}

<style>
  .jelzes {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--t-2);
    margin: 0 0 var(--t-3);
    padding: var(--t-2) var(--t-3);
    border-radius: var(--kerekites);
    background: var(--figyelmeztetes-hatter);
    color: var(--szoveg-masodlagos);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  p {
    margin: 0;
  }

  .halvany {
    color: var(--szoveg-halvany);
  }

  .hiba {
    color: var(--hiba);
  }

</style>
