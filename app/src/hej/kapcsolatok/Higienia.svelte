<!--
  Jegyzet-higiénia (C30a): a jegyzet észrevételei a core indexéből — törött és többértelmű link, hibás képlet vagy
  tulajdonság, hiányzó forráshorgony vagy média, árva jegyzet. Modell nélkül számolódik; a sorra kattintva a szerkesztő
  a helyre ugrik. Csak olvas (a javítás a szerkesztőben, a megszokott úton megy). A tételeket a `JobbPanel` kéri
  (`GET /api/higienia?ut=`: egyetlen indexelt lekérdezés), ez a komponens csak megjeleníti.
-->
<script lang="ts">
  import { t, tp } from '../../lib/i18n';
  import { fajtaCim } from '../../lib/asszisztens/megjelenites';
  import type { HigieniaTetel } from '../../lib/asszisztens/tipusok';
  import Ikon from '../../lib/ikon/Ikon.svelte';
  import { CircleAlert, TriangleAlert } from '../../lib/ikon/ikonok';

  let {
    tetelek,
    hiba = null,
    onnyit,
  }: { tetelek: HigieniaTetel[]; hiba?: string | null; onnyit: (sor: number, e: MouseEvent) => void } = $props();

  const MAX = 50;
  const lathato = $derived(tetelek.slice(0, MAX));
</script>

{#if hiba}
  <p class="hiba" role="alert">{hiba}</p>
{:else if !tetelek.length}
  <p class="ures" role="status">{t('Nincs észrevétel ebben a jegyzetben.')}</p>
{:else}
  <ul class="lista" aria-label={t('A jegyzet higiénia-észrevételei')}>
    {#each lathato as it (it.azonosito)}
      <li>
        {#if it.sor}
          <button type="button" class="elem" title={t('{fajta} — ugrás a {sor}. sorra', { fajta: fajtaCim(it.fajta), sor: it.sor })} onclick={(e) => onnyit(it.sor!, e)}>
            <span class="jel" class:hiba-szint={it.szint === 'hiba'}><Ikon ikon={it.szint === 'hiba' ? CircleAlert : TriangleAlert} meret={14} /></span>
            <span class="szoveg">{it.uzenet}</span>
            <span class="sor">{it.sor}.</span>
          </button>
        {:else}
          <div class="elem statikus" title={fajtaCim(it.fajta)}>
            <span class="jel"><Ikon ikon={TriangleAlert} meret={14} /></span>
            <span class="szoveg">{it.uzenet}</span>
          </div>
        {/if}
      </li>
    {/each}
  </ul>
  {#if tetelek.length > MAX}<p class="ures">{tp('… és még {n} észrevétel.', tetelek.length - MAX)}</p>{/if}
{/if}

<style>
  .ures,
  .hiba {
    margin: 0;
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    color: var(--szoveg-halvany);
  }

  .hiba {
    color: var(--hiba);
  }

  .lista {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .elem {
    display: flex;
    align-items: flex-start;
    gap: var(--t-2);
    width: 100%;
    padding: var(--t-1) var(--t-2);
    border-radius: var(--kerekites-kicsi);
    text-align: left;
    color: var(--szoveg);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  button.elem:hover {
    background: var(--hatter-hover);
  }

  button.elem:focus-visible {
    outline-offset: var(--fokusz-tav-befele);
  }

  .statikus {
    color: var(--szoveg-masodlagos);
  }

  .jel {
    flex: none;
    display: inline-flex;
    margin-top: 1px;
    color: var(--figyelmeztetes);
  }

  .jel.hiba-szint {
    color: var(--hiba);
  }

  .szoveg {
    flex: 1;
    min-width: 0;
    overflow-wrap: anywhere;
  }

  .sor {
    flex: none;
    color: var(--szoveg-halvany);
    font-variant-numeric: tabular-nums;
  }
</style>
