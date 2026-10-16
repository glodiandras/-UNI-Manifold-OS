<!--
  Állapotsor: oldalsáv- és panelkapcsolók, a core kapcsolata (csak ha baj van), az index állapota,
  az értesítések előzménye. Csendben (C38) átfedés az ablak alján: csak akkor csúszik be, ha mondanivalója van
  (megszakadt kapcsolat, index-hiba vagy épülő index, olvasatlan figyelmeztetés/hiba, futó feladat rejtett oldalsávnál),
  amíg az egér az alsó szélen áll, vagy a fókusz benne van (F6, ⌘P „Állapotsor megjelenítése”).
-->
<script lang="ts">
  import { t, tp, locale } from '../lib/i18n';
  import { onMount, untrack } from 'svelte';
  import { modulEngedelyezett } from '../lib/beallitasok/allapot.svelte';
  import { VisszaSzam } from '../lib/vault/visszaSzam.svelte';
  import { allapotsorLathato, csend, regioMegjelenitKezel } from '../lib/elrendezes/csend.svelte';
  import { statisztika } from '../lib/elrendezes/szovegStatisztika.svelte';
  import { feladatsor } from '../lib/vezerlo/feladatsor.svelte';
  import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { Bell, PanelLeft, PanelRight } from '../lib/ikon/ikonok';
  import { egeszsegMegnyit } from '../lib/egeszseg/allapot.svelte';
  import { kornyezet } from '../lib/kornyezet';
  import { regiszter } from '../lib/parancsok/regiszter';
  import IkonGomb from '../lib/ui/IkonGomb.svelte';
  import ErtesitesElozmeny from './ErtesitesElozmeny.svelte';
  import Jelenlet from './vezerlo/Jelenlet.svelte';

  const { felulet, fajlok, kapcsolat } = kornyezet();
  const aktivFul = $derived(felulet.munkaterulet.aktivFul);
  const szovegSzamok = $derived(statisztika.olvas(aktivFul?.id, aktivFul?.ut));
  const szam = $derived(new Intl.NumberFormat(locale()));

  const indexSzoveg = $derived.by(() => {
    const ix = fajlok.index;
    if (!ix) return '';
    if (ix.hiba) return t('Index: hiba');
    if (!ix.kesz) return t('Indexelés…');
    return `${szam.format(fajlok.jegyzetek)} jegyzet`;
  });
  // 06-workspace-17: az aktív jegyzet visszahivatkozásainak száma; kattintásra a jobb panel szakasza nyílik
  const visszaSzam = new VisszaSzam();
  const szamUt = $derived(aktivFul?.ut && /\.(md|canvas)$/i.test(aktivFul.ut) && modulEngedelyezett('hivatkozasok') ? aktivFul.ut : null);
  $effect(() => {
    const ut = szamUt;
    untrack(() => void visszaSzam.frissit(ut));
  });
  onMount(() => visszaSzam.figyel(kapcsolat, () => szamUt));
  function visszaMutat() {
    felulet.jobbPanel.visszahivatkozasok = true;
    if (!felulet.jobbPanel.nyitva) regiszter.futtat('hej.jobb-panel', 'gomb');
  }

  let gomb: HTMLButtonElement | undefined = $state();
  let sav: HTMLElement | undefined = $state();
  let fokuszBenne = $state(false);

  const lathato = $derived(
    allapotsorLathato({
      csend: csend.be,
      kapcsolatMegszakadt: kapcsolat.allapot === 'megszakadt',
      olvasatlanFontos: ertesitesek.olvasatlanFontos,
      indexEpul: !!fajlok.index && !fajlok.index.kesz && !fajlok.index.hiba,
      indexHiba: !!fajlok.index?.hiba,
      elozmenyNyitva: felulet.ertesitesPanel,
      feladatFut: feladatsor.aktiv,
      oldalsavRejtett: !felulet.oldalsav.nyitva,
      egerAlul: csend.egerAlul,
      fokuszBenne,
    }),
  );

  onMount(() => regioMegjelenitKezel(sav!, () => (fokuszBenne = true)));
</script>

<footer
  class="allapotsor"
  class:rejtett={!lathato}
  data-regio="allapotsor"
  data-regio-rejtett={lathato ? undefined : ''}
  aria-label={t('Állapotsor')}
  bind:this={sav}
  onfocusin={() => (fokuszBenne = true)}
  onfocusout={(e) => {
    if (!sav?.contains(e.relatedTarget as Node | null)) fokuszBenne = false;
  }}
>
  <IkonGomb
    ikon={PanelLeft}
    cimke={t('Oldalsáv')}
    billentyu="Mod+Alt+1"
    kicsi
    lenyomva={felulet.oldalsav.nyitva}
    onclick={() => regiszter.futtat('hej.oldalsav', 'gomb')}
  />
  <div class="elemek">
    {#if kapcsolat.allapot === 'megszakadt'}
      <span class="elem figyelmeztetes" role="status"><span class="pont"></span>{t('Nincs kapcsolat a core-ral, újrapróbálás…')}</span>
    {/if}
    {#if !felulet.oldalsav.nyitva}<span class="elem"><Jelenlet /></span>{/if}
    {#if fajlok.index?.hiba}
      <span role="status" title={fajlok.index.hiba}><button type="button" class="elem elem-gomb" data-index-hiba title={t('allapotsor.index_diagnosztika')} onclick={() => egeszsegMegnyit('index')}>{indexSzoveg}</button></span>
    {:else}
      <span class="elem" role="status">{indexSzoveg}</span>
    {/if}
    {#if szamUt && visszaSzam.ut === szamUt && visszaSzam.db !== null}
      <button type="button" class="elem elem-gomb" data-visszahivatkozasok title={t('Visszahivatkozások megnyitása')} onclick={visszaMutat}>{tp('{n} visszahivatkozás', visszaSzam.db)}</button>
    {/if}
    {#if szovegSzamok}
      <span class="elem szoveg-szamok" title={szovegSzamok.kijelolt ? t('Kijelölés. Teljes jegyzet: {szavak} szó, {karakterek} karakter.', { szavak: szovegSzamok.osszesSzavak, karakterek: szovegSzamok.osszesKarakterek }) : t('A teljes jegyzet szavai és karakterei')}>
        {#if szovegSzamok.kijelolt}<span>{t('Kijelölés:')}</span>{/if}
        <span>{tp('{n} szó', szovegSzamok.szavak)}</span>
        <span>{tp('{n} karakter', szovegSzamok.karakterek)}</span>
      </span>
    {/if}
  </div>
  <button
    type="button"
    class="ertesites-gomb"
    bind:this={gomb}
    aria-label={ertesitesek.olvasatlan ? t('Értesítések, {n} új', { n: ertesitesek.olvasatlan }) : t('Értesítések')}
    aria-expanded={felulet.ertesitesPanel}
    aria-controls="ertesites-elozmeny"
    title={t('Értesítések')}
    onclick={() => regiszter.futtat('ertesites.elozmeny', 'gomb')}
  >
    <Ikon ikon={Bell} meret={14} />
    {#if ertesitesek.olvasatlan}<span class="szam">{ertesitesek.olvasatlan}</span>{/if}
  </button>
  <IkonGomb
    ikon={PanelRight}
    cimke={t('Jobb panel')}
    billentyu="Mod+Alt+2"
    kicsi
    lenyomva={felulet.jobbPanel.nyitva}
    onclick={() => regiszter.futtat('hej.jobb-panel', 'gomb')}
  />
  {#if felulet.ertesitesPanel}
    <ErtesitesElozmeny nyito={gomb} onbezar={() => (felulet.ertesitesPanel = false)} />
  {/if}
</footer>

<style>
  .allapotsor {
    grid-area: allapot;
    position: relative;
    display: flex;
    align-items: center;
    gap: var(--t-1);
    height: var(--allapotsor-teljes);
    padding: 0 var(--t-1);
    border-top: var(--keret-vastag) solid var(--keret);
    background: var(--hatter-oldalsav);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    color: var(--szoveg-halvany);
    font-variant-numeric: tabular-nums;
  }

  /* C38: csendben átfedés az ablak alján; rejtve lecsúszik (a láthatóság a becsúszás végén vált) */
  :global(html[data-csend]) .allapotsor {
    position: absolute;
    left: var(--oldalsav-sz); /* a MANIFOLD jelet nem takarja */
    right: 0;
    bottom: 0;
    z-index: var(--reteg-lap);
    transition:
      transform var(--mozgas-alap) var(--mozgas-gorbe),
      visibility 0s linear 0s;
  }

  :global(html[data-csend]) .allapotsor.rejtett {
    transform: translateY(100%);
    visibility: hidden;
    transition:
      transform var(--mozgas-alap) var(--mozgas-gorbe),
      visibility 0s linear var(--mozgas-alap);
  }

  .elemek {
    flex: 1;
    display: flex;
    justify-content: flex-end;
    gap: var(--t-4);
    min-width: 0;
    padding: 0 var(--t-2);
  }

  .elem {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    white-space: nowrap;
  }

  .elem-gomb {
    padding: 0;
    color: inherit;
    font: inherit;
    border-radius: var(--kerekites-kicsi);
  }

  .elem-gomb:hover {
    color: var(--szoveg-masodlagos);
  }

  .figyelmeztetes {
    color: var(--figyelmeztetes);
  }

  .pont {
    width: 6px;
    height: 6px;
    border-radius: var(--kerekites-kor);
    background: currentColor;
  }

  .ertesites-gomb {
    display: inline-flex;
    align-items: center;
    gap: var(--t-1);
    height: var(--magassag-gomb-kicsi);
    min-width: var(--magassag-gomb-kicsi);
    padding: 0 3px;
    border-radius: var(--kerekites-kicsi);
    color: var(--szoveg-halvany);
    transition: background-color var(--mozgas-gyors) var(--mozgas-gorbe);
  }

  .ertesites-gomb:hover,
  .ertesites-gomb[aria-expanded='true'] {
    background: var(--hatter-hover);
    color: var(--szoveg);
  }

  .ertesites-gomb:active {
    background: var(--hatter-aktiv);
  }

  .ertesites-gomb:focus-visible {
    outline-offset: var(--fokusz-tav-befele);
  }

  .szam {
    color: var(--akcent-szoveg);
    font-weight: var(--suly-felkover);
  }
</style>
