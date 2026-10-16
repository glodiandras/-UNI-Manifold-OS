<!--
  A javaslat-kártya (J3): középen felül, „Mit szólnál…?” Igen/Nem. Nem modális és nem kér fókuszt (CX tartós döntése):
  a gépelés megy tovább, a kártya magától eltűnik. Billentyűről a ⌘P két parancsával is dönthetsz. Az elfogadás csak
  a nyitott jegyzetbe ír, a szerkesztőn át (egy ⌘Z-lépés).
-->
<script lang="ts">
  import { t } from '../i18n';
  import { fly } from 'svelte/transition';
  import { ido } from '../elrendezes/mozgas';
  import Ikon from '../ikon/Ikon.svelte';
  import { Sparkles, X } from '../ikon/ikonok';
  import { kartyaAllapot } from './kartya.svelte';
</script>

{#if kartyaAllapot.aktiv}
  {@const j = kartyaAllapot.aktiv.javaslat}
  <div
    class="kartya"
    role="dialog"
    aria-modal="false"
    tabindex="-1"
    aria-labelledby="asszisztens-kartya-cim"
    aria-describedby="asszisztens-kartya-indok"
    transition:fly={{ y: -8, duration: ido('alap') }}
    onpointerenter={() => kartyaAllapot.tart()}
  >
    <span class="ikon" aria-hidden="true"><Ikon ikon={Sparkles} meret={16} /></span>
    <div class="szovegek">
      <p class="cim" id="asszisztens-kartya-cim">{j.cim}</p>
      <p class="indok" id="asszisztens-kartya-indok">{j.indok}</p>
      <div class="gombok">
        <button type="button" class="m-gomb suru" disabled={kartyaAllapot.foglalt} onclick={() => void kartyaAllapot.igen()}>{t('Igen')}</button>
        <button type="button" class="m-gomb semleges suru" disabled={kartyaAllapot.foglalt} onclick={() => kartyaAllapot.nem()}>{t('Nem')}</button>
      </div>
    </div>
    <button type="button" class="bezar" aria-label={t('A javaslat bezárása döntés nélkül')} onclick={() => kartyaAllapot.elrejt('figyelmen_kivul')}>
      <Ikon ikon={X} meret={14} />
    </button>
  </div>
{/if}

<style>
  .kartya {
    position: fixed;
    top: calc(var(--magassag-fulsor) + var(--t-8));
    left: 50%;
    transform: translateX(-50%);
    z-index: var(--reteg-lebego);
    display: flex;
    align-items: flex-start;
    gap: var(--t-3);
    width: min(420px, calc(100vw - var(--t-6)));
    padding: var(--t-3) var(--t-2) var(--t-3) var(--t-3);
    background: var(--hatter-emelt);
    border: 1px solid var(--keret);
    border-radius: var(--kerekites-nagy);
    box-shadow: var(--arnyek-atfedes);
  }

  .ikon {
    padding-top: 2px;
    color: var(--szoveg-halvany);
  }

  .szovegek {
    flex: 1;
    min-width: 0;
  }

  .cim {
    font-weight: var(--suly-felkover);
    color: var(--szoveg);
    overflow-wrap: anywhere;
  }

  .indok {
    margin-top: 2px;
    color: var(--szoveg-masodlagos);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  .gombok {
    display: flex;
    gap: var(--t-2);
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
</style>
