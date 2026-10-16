<!--
  Az értesítések egyetlen helye: jobb alsó sarok, legfeljebb 3 egyszerre. Hover és fókusz megállítja az
  időzítőt. A hiba role="alert", a többi role="status" (élő régió).
-->
<script lang="ts">
  import { t } from '../lib/i18n';
  import { flip } from 'svelte/animate';
  import { fly } from 'svelte/transition';
  import { ertesitesek, type Szint } from '../lib/ertesites/ertesites.svelte';
  import { ido } from '../lib/elrendezes/mozgas';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { CircleAlert, CircleCheck, Info, TriangleAlert, X } from '../lib/ikon/ikonok';

  const IKON = { info: Info, siker: CircleCheck, figyelmeztetes: TriangleAlert, hiba: CircleAlert } satisfies Record<
    Szint,
    unknown
  >;
</script>

<section class="ertesitesek" aria-label={t('Értesítések')}>
  {#each ertesitesek.lathato as e (e.id)}
    <div
      class="ertesites {e.szint}"
      role={e.szint === 'hiba' ? 'alert' : 'status'}
      animate:flip={{ duration: ido('alap') }}
      transition:fly={{ x: 16, duration: ido('alap') }}
      onpointerenter={() => ertesitesek.szunet(e.id, true)}
      onpointerleave={() => ertesitesek.szunet(e.id, false)}
      onfocusin={() => ertesitesek.szunet(e.id, true)}
      onfocusout={() => ertesitesek.szunet(e.id, false)}
    >
      <span class="ikon"><Ikon ikon={IKON[e.szint]} /></span>
      <div class="szovegek">
        <p class="cim">{e.cim}{#if e.darab > 1}<span class="darab"> ×{e.darab}</span>{/if}</p>
        {#if e.szoveg}<p class="szoveg">{e.szoveg}</p>{/if}
        {#if e.muvelet}
          <button
            type="button"
            class="m-gomb muvelet"
            onclick={() => {
              e.muvelet?.futtat();
              ertesitesek.elvet(e.id);
            }}>{e.muvelet.nev}</button
          >
        {/if}
      </div>
      <button type="button" class="bezar" aria-label={t('Értesítés bezárása')} onclick={() => ertesitesek.elvet(e.id)}>
        <Ikon ikon={X} meret={14} />
      </button>
    </div>
  {/each}
</section>

<style>
  .ertesitesek {
    position: fixed;
    right: var(--t-3);
    bottom: calc(var(--allapotsor-teljes) + var(--t-3));
    z-index: var(--reteg-ertesites);
    display: flex;
    flex-direction: column;
    gap: var(--t-2);
    width: 340px;
    max-width: calc(100vw - var(--t-6));
    pointer-events: none;
  }

  .ertesites {
    pointer-events: auto;
    display: flex;
    align-items: flex-start;
    gap: var(--t-3);
    padding: var(--t-3) var(--t-2) var(--t-3) var(--t-3);
    background: var(--hatter-emelt);
    border-radius: var(--kerekites-nagy);
    box-shadow: var(--arnyek-atfedes);
  }

  .ikon {
    padding-top: 2px;
    color: var(--szoveg-halvany);
  }

  .siker .ikon {
    color: var(--siker);
  }

  .figyelmeztetes .ikon {
    color: var(--figyelmeztetes);
  }

  .hiba .ikon {
    color: var(--hiba);
  }

  .szovegek {
    flex: 1;
    min-width: 0;
  }

  .cim {
    font-weight: var(--suly-felkover);
    color: var(--szoveg);
  }

  .darab {
    font-weight: var(--suly-normal);
    color: var(--szoveg-halvany);
  }

  .szoveg {
    margin-top: 2px;
    color: var(--szoveg-masodlagos);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    overflow-wrap: anywhere;
    user-select: text;
    -webkit-user-select: text;
  }

  .muvelet {
    margin-top: var(--t-2);
  }

  .bezar {
    display: grid;
    place-items: center;
    flex: none;
    width: var(--magassag-gomb-kicsi);
    height: var(--magassag-gomb-kicsi);
    border-radius: var(--kerekites-kicsi);
    color: var(--szoveg-halvany);
  }

  .bezar:hover {
    background: var(--hatter-hover);
    color: var(--szoveg);
  }

  .bezar:active {
    background: var(--hatter-aktiv);
  }
</style>
