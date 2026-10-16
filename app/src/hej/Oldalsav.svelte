<!--
  Bal oldalsáv: a fájlfa, a címkefa és a tartós keresőpanel. A ⇧⌘F gyors átfedésként is megmarad.
  A kereső listája a fülváltások alatt is megmarad; a nyitott oldalsáv-nézet a felület állapotában tartós.
-->
<script lang="ts">
  import { modulEngedelyezett } from '../lib/beallitasok/allapot.svelte';
  import { t, tk } from '../lib/i18n';
  import { onMount } from 'svelte';
  import { csend, kivul, regioMegjelenitKezel } from '../lib/elrendezes/csend.svelte';
  import { regioFokusz } from '../lib/fokusz/fokusz';
  import { PanelLeft } from '../lib/ikon/ikonok';
  import { kornyezet } from '../lib/kornyezet';
  import { regiszter } from '../lib/parancsok/regiszter';
  import IkonGomb from '../lib/ui/IkonGomb.svelte';
  import KeresoTartalom from '../lib/kereses/KeresoTartalom.svelte';
  import Cimkek from './Cimkek.svelte';
  import Fa from './Fa.svelte';

  const { felulet } = kornyezet();
  const nezet = $derived((felulet.oldalsav.nezet === 'cimkek' && !modulEngedelyezett('cimkek')) || (felulet.oldalsav.nezet === 'kereses' && !modulEngedelyezett('kereses')) ? 'fajlok' : felulet.oldalsav.nezet);
  let keresett = $state(false);
  $effect(() => { if (nezet === 'kereses') keresett = true; });
  // C38: a rejtett oldalsáv átfedésként jön elő (bal szél, F6); a DOM-ja rejtve is megmarad (nincs állapotvesztés)
  const atfedes = $derived(!felulet.oldalsav.nyitva && csend.oldalsavAtfedes);
  const rejtett = $derived(!felulet.oldalsav.nyitva && !atfedes);
  let nav: HTMLElement | undefined = $state();

  onMount(() => regioMegjelenitKezel(nav!, () => (csend.oldalsavAtfedes = true)));

  function fokuszKi(e: FocusEvent) {
    if (atfedes && kivul(nav, e.relatedTarget)) csend.oldalsavAtfedes = false;
  }

  function esc(e: KeyboardEvent) {
    if (!atfedes || e.key !== 'Escape' || e.defaultPrevented) return;
    e.preventDefault();
    csend.oldalsavAtfedes = false;
    regioFokusz('munkaterulet');
  }

  const ALAP_NEZETEK = [
    { id: 'fajlok', nev: tk('Fájlok') },
    { id: 'cimkek', nev: tk('Címkék') },
    { id: 'kereses', nev: tk('Keresés') },
  ] as const;

  const NEZETEK = $derived(ALAP_NEZETEK.filter(n => (n.id !== 'cimkek' || modulEngedelyezett('cimkek')) && (n.id !== 'kereses' || modulEngedelyezett('kereses'))));

  /** A fülek léptetése nyilakkal (← →): a kijelölt fül kapja a fókuszt. */
  function fulBillentyu(e: KeyboardEvent) {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    e.preventDefault();
    const i = NEZETEK.findIndex((n) => n.id === nezet);
    felulet.oldalsav.nezet = NEZETEK[(i + (e.key === 'ArrowRight' ? 1 : NEZETEK.length - 1)) % NEZETEK.length].id;
    queueMicrotask(() => document.getElementById(`oldalsav-ful-${felulet.oldalsav.nezet}`)?.focus());
  }
</script>

<!-- svelte-ignore a11y_no_noninteractive_element_interactions (az Esc csak az átfedést zárja, C38) -->
<nav
  class="oldalsav"
  class:atfedes
  data-regio="oldalsav"
  data-regio-rejtett={rejtett ? '' : undefined}
  data-csend-halvanyul
  data-csend-terulet
  aria-label={t('Oldalsáv')}
  inert={rejtett}
  bind:this={nav}
  onfocusout={fokuszKi}
  onkeydown={esc}
>
  <header class="fejlec">
    <div class="fulek" role="tablist" aria-label={t('Az oldalsáv nézetei')} tabindex="-1" onkeydown={fulBillentyu}>
      {#each NEZETEK as n (n.id)}
        <button
          type="button"
          id={`oldalsav-ful-${n.id}`}
          class="ful"
          role="tab"
          aria-selected={nezet === n.id}
          aria-controls="oldalsav-panel"
          tabindex={nezet === n.id ? 0 : -1}
          onclick={() => (felulet.oldalsav.nezet = n.id)}
        >
          {t(n.nev)}
        </button>
      {/each}
    </div>
    <IkonGomb
      ikon={PanelLeft}
      cimke={atfedes ? t('Oldalsáv rögzítése') : t('Oldalsáv elrejtése')}
      billentyu="Mod+Alt+1"
      data-csend-rejt
      onclick={() => regiszter.futtat('hej.oldalsav', 'gomb')}
    />
  </header>
  <div class="tartalom" id="oldalsav-panel" role="tabpanel" aria-labelledby={`oldalsav-ful-${nezet}`}>
    {#if nezet === 'fajlok'}
      <Fa />
    {:else if nezet === 'cimkek'}
      <Cimkek />
    {/if}
    {#if keresett}
      <div class="kereso-panel" hidden={nezet !== 'kereses'} inert={nezet !== 'kereses'}>
        <KeresoTartalom dokkolt lathato={nezet === 'kereses' && !rejtett && felulet.atfedes === null && modulEngedelyezett('kereses')} />
      </div>
    {/if}
  </div>
</nav>

<style>
  .oldalsav {
    grid-area: oldalsav;
    position: relative;
    display: flex;
    flex-direction: column;
    min-width: 0;
    overflow: hidden;
    background: var(--hatter-oldalsav);
    border-right: var(--keret-vastag) solid var(--keret);
  }

  .oldalsav[inert] {
    border-right-color: transparent;
  }

  /* C38: a rejtett oldalsáv átfedésként (bal szél, F6); a becsúszás a tokenből, csökkentett mozgásnál azonnali */
  .oldalsav.atfedes {
    position: fixed;
    top: 0;
    bottom: var(--allapotsor-hely);
    left: var(--szelesseg-ikonsav);
    width: var(--oldalsav-atfedes-sz);
    z-index: var(--reteg-lap);
    box-shadow: var(--arnyek-lap-balrol);
    transition: transform var(--mozgas-alap) var(--mozgas-gorbe);
  }

  @starting-style {
    .oldalsav.atfedes {
      transform: translateX(-100%);
    }
  }

  .fejlec {
    flex: none;
    display: flex;
    align-items: center;
    gap: var(--t-2);
    height: var(--magassag-fejlec);
    padding: 0 var(--t-1) 0 var(--t-2);
  }

  .fulek {
    flex: 1;
    display: flex;
    align-items: center;
    gap: var(--t-1);
    min-width: 0;
  }

  .ful {
    height: var(--magassag-sor);
    padding: 0 var(--t-2);
    border-radius: var(--kerekites);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    font-weight: var(--suly-felkover);
    color: var(--szoveg-halvany);
    letter-spacing: 0.02em;
    white-space: nowrap;
    transition:
      background-color var(--mozgas-gyors) var(--mozgas-gorbe),
      color var(--mozgas-gyors) var(--mozgas-gorbe);
  }

  .ful:hover {
    background: var(--hatter-hover);
    color: var(--szoveg);
  }

  .ful[aria-selected='true'] {
    background: var(--hatter-aktiv);
    color: var(--szoveg);
  }

  .ful:focus-visible {
    outline-offset: var(--fokusz-tav-befele);
  }

  .kereso-panel { height: 100%; }

  .tartalom {
    flex: 1;
    min-height: 0;
    min-width: 0;
  }

</style>
