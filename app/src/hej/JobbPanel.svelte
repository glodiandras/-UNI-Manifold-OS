<!--
  Jobb panel (C10): a jegyzet kapcsolatai — visszahivatkozások a link sorával, linkeletlen említések (egy kattintás =
  link), kimenő linkek, az élő vázlat, az előzmények (C11b) és a hasonló jegyzetek (C25c) — összecsukható szakaszokban. Az adatot a core indexe adja
  (`lib/vault/kapcsolatok.svelte.ts`); a feloldás nem itt történik (L42).
-->
<script lang="ts">
  import { onDestroy, onMount, untrack } from 'svelte';
  import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
  import { JegyzetHigienia } from '../lib/asszisztens/adat.svelte';
  import { csend, kivul, regioMegjelenitKezel } from '../lib/elrendezes/csend.svelte';
  import { regioFokusz } from '../lib/fokusz/fokusz';
  import { FileClock, Link2, ListChecks, ListTree, Network, PanelRight, Unlink, ArrowRight } from '../lib/ikon/ikonok';
  import { HasonloJegyzetek } from '../lib/kereses/hasonlo.svelte';
  import { kornyezet } from '../lib/kornyezet';
  import { regiszter } from '../lib/parancsok/regiszter';
  import IkonGomb from '../lib/ui/IkonGomb.svelte';
  import { Kapcsolatok, type Emlites, type KimenoLink } from '../lib/vault/kapcsolatok.svelte';
  import { vezerloKapcsolok } from '../lib/vezerlo/kapcsolok.svelte';
  import { KatexHibak, osszevon } from '../szerkeszto/asszisztens/kepletHibak.svelte';
  import { emlitesLinkel } from '../szerkeszto/linkek/emlites';
  import { jegyzetLetrehoz, linkMegnyit, nyitasMod } from '../szerkeszto/linkek/navigacio';
  import { szerkesztok } from '../szerkeszto/szerkesztok.svelte';
  import Elozmenyek from './kapcsolatok/Elozmenyek.svelte';
  import Emlitesek from './kapcsolatok/Emlitesek.svelte';
  import Hasonlok from './kapcsolatok/Hasonlok.svelte';
  import Higienia from './kapcsolatok/Higienia.svelte';
  import KimenoLinkek from './kapcsolatok/KimenoLinkek.svelte';
  import Vazlat from './kapcsolatok/Vazlat.svelte';
  import Visszahivatkozasok from './kapcsolatok/Visszahivatkozasok.svelte';
  import Szakasz from './Szakasz.svelte';

  const { felulet, fajlok, kapcsolat } = kornyezet();
  const ful = $derived(felulet.munkaterulet.aktivFul);
  const k = new Kapcsolatok();
  const higienia = new JegyzetHigienia();           // C30a: a jegyzet higiénia-észrevételei (modell nélkül, az indexből)

  // C38: a rejtett jobb panel F6-ra átfedésként jön elő, a fókusz elhagyásáig; a DOM-ja és az adata rejtve is megmarad
  const atfedes = $derived(!felulet.jobbPanel.nyitva && csend.jobbAtfedes);
  const lathato = $derived(felulet.jobbPanel.nyitva || atfedes);
  let aside: HTMLElement | undefined = $state();
  onMount(() => regioMegjelenitKezel(aside!, () => (csend.jobbAtfedes = true)));

  function fokuszKi(e: FocusEvent) {
    if (atfedes && kivul(aside, e.relatedTarget)) csend.jobbAtfedes = false;
  }

  function esc(e: KeyboardEvent) {
    if (!atfedes || e.key !== 'Escape' || e.defaultPrevented) return;
    e.preventDefault();
    csend.jobbAtfedes = false;
    regioFokusz('munkaterulet');
  }

  // az aktív fül váltására (és a panel megjelenésére) újratölt; a vault változására a WS-figyelő. Rejtve nem tölt, de
  // nem is üríti a listát (C38: ugyanott nyílik ki, a görgetés megmarad); más jegyzetre nyílva előbb ürít.
  $effect(() => {
    const ut = ful?.ut ?? null;
    if (!lathato) return;
    untrack(() => {
      if (k.ut !== ut) void k.frissit(null);
      void k.frissit(ut);
    });
  });

  onMount(() => k.figyel(kapcsolat, () => (lathato ? (felulet.munkaterulet.aktivFul?.ut ?? null) : undefined)));

  // a higiénia csak látható panelnél és bekapcsolt Asszisztensnél tölt; gépelés közben nem (a változásra 1,5 s csend után frissül)
  const higieniaUt = () => (lathato && vezerloKapcsolok.ertek.asszisztens ? (felulet.munkaterulet.aktivFul?.ut ?? null) : null);
  $effect(() => {
    const ut = higieniaUt();
    untrack(() => void higienia.frissit(ut));
  });
  onMount(() => higienia.figyel(kapcsolat, higieniaUt));

  // C30b-mag: a valódi KaTeX-hibák a nyitott dokumentumból, csendes idő után (a gépelés útvonalán nem fut); csak nyitott
  // panelnél és bekapcsolt Asszisztensnél. A szerkesztő `valtozat()`-a a mentetlen szerkesztésre is frissít.
  const katex = new KatexHibak();
  let katexIdozito: ReturnType<typeof setTimeout> | null = null;
  let katexUt: string | null = null;
  $effect(() => {
    const ut = higieniaUt();
    void szerkesztok.aktiv?.valtozat();
    untrack(() => {
      if (katexIdozito) clearTimeout(katexIdozito);
      katexIdozito = null;
      if (!ut) {
        katexUt = null;
        katex.torol();
        return;
      }
      const uj = ut !== katexUt;
      katexUt = ut;
      katexIdozito = setTimeout(() => void katex.frissit(ut), uj ? 0 : 1500);
    });
  });
  onDestroy(() => {
    if (katexIdozito) clearTimeout(katexIdozito);
    katex.torol();
  });
  const higieniaTetelek = $derived(osszevon(higienia.tetelek, katex.tetelek));

  // C25c: a hasonló jegyzetek (a vektortárból, modell nélkül) csak a látható panel kinyitott szakaszában töltenek (C38: csend)
  const hasonlo = new HasonloJegyzetek();
  const hasonloUt = () => (lathato && felulet.jobbPanel.hasonlo ? (felulet.munkaterulet.aktivFul?.ut ?? null) : undefined);
  $effect(() => {
    const ut = hasonloUt();
    if (ut === undefined) return;
    untrack(() => void hasonlo.frissit(ut));
  });
  onMount(() => hasonlo.figyel(kapcsolat, hasonloUt));

  function hasonloNyit(ut: string, e: MouseEvent) {
    felulet.munkaterulet.megnyit(ut, nyitasMod(e));
  }

  function nyit(ut: string, sor: number | null, e: MouseEvent) {
    felulet.munkaterulet.megnyit(ut, nyitasMod(e));
    if (sor) szerkesztok.ugras(ut, sor);
  }

  function higieniaNyit(sor: number, e: MouseEvent) {
    if (ful?.ut) nyit(ful.ut, sor, e);
  }

  async function linkel(forras: string, t: Emlites) {
    if (!ful?.ut) return;
    if (await emlitesLinkel(ful.ut, forras, t)) void k.frissit(ful.ut);
  }

  function kimenoNyit(l: KimenoLink, e: MouseEvent) {
    if (!ful?.ut || !l.cel) return;
    void linkMegnyit({ forras: ful.ut, cel: l.cel_nyers, alcel: l.alcel }, nyitasMod(e));
  }

  async function letrehoz(l: KimenoLink) {
    if (!ful?.ut) return;
    const ut = await jegyzetLetrehoz(ful.ut, l.cel_nyers);
    if (ut) {
      ertesitesek.ertesit({ szint: 'siker', cim: 'Új jegyzet', szoveg: ut, idotartam: 3000 });
      felulet.munkaterulet.megnyit(ut, 'ujful');
    }
  }

  const darabVissza = $derived(k.visszahivatkozasok.reduce((n, f) => n + f.linkek.length, 0));
  const darabEml = $derived(k.emlitesek.reduce((n, f) => n + f.talalatok.length, 0));
</script>

<!-- svelte-ignore a11y_no_noninteractive_element_interactions (az Esc csak az átfedést zárja, C38) -->
<aside
  class="jobb"
  class:atfedes
  data-regio="jobb"
  data-regio-rejtett={lathato ? undefined : ''}
  aria-label="Jegyzet-kapcsolatok"
  inert={!lathato}
  bind:this={aside}
  onfocusout={fokuszKi}
  onkeydown={esc}
>
  <header class="fejlec">
    <IkonGomb
      ikon={PanelRight}
      cimke={atfedes ? 'Jobb panel rögzítése' : 'Jobb panel elrejtése'}
      billentyu="Mod+Alt+2"
      onclick={() => regiszter.futtat('hej.jobb-panel', 'gomb')}
    />
  </header>
  <div class="tartalom gorgeto">
    {#if !ful?.ut}
      <p class="ures">Nincs megnyitott fájl.</p>
    {:else}
      {#if k.hiba}<p class="hiba" role="alert">{k.hiba}</p>{/if}
      <Szakasz cim={`Visszahivatkozások${darabVissza ? ` (${darabVissza})` : ''}`} ikon={Link2} bind:nyitva={felulet.jobbPanel.visszahivatkozasok}>
        <Visszahivatkozasok forrasok={k.visszahivatkozasok} onnyit={nyit} />
      </Szakasz>
      <Szakasz cim={`Linkeletlen említések${darabEml ? ` (${darabEml})` : ''}`} ikon={Unlink} bind:nyitva={felulet.jobbPanel.emlitesek}>
        <Emlitesek forrasok={k.emlitesek} onlinkel={linkel} onnyit={nyit} />
      </Szakasz>
      <Szakasz cim="Kimenő linkek" ikon={ArrowRight} bind:nyitva={felulet.jobbPanel.kimeno}>
        <KimenoLinkek linkek={k.kimeno} info={(u) => fajlok.info(u)} onnyit={kimenoNyit} onletrehoz={letrehoz} />
      </Szakasz>
      <Szakasz cim="Vázlat" ikon={ListTree} bind:nyitva={felulet.jobbPanel.vazlat}>
        <Vazlat />
      </Szakasz>
      <Szakasz cim="Előzmények" ikon={FileClock} bind:nyitva={felulet.jobbPanel.elozmenyek}>
        <Elozmenyek ut={ful.ut} nyitva={felulet.jobbPanel.elozmenyek && lathato} />
      </Szakasz>
      {#if vezerloKapcsolok.ertek.asszisztens}
        <Szakasz cim={`Higiénia${higieniaTetelek.length ? ` (${higieniaTetelek.length})` : ''}`} ikon={ListChecks} bind:nyitva={felulet.jobbPanel.higienia}>
          <Higienia tetelek={higieniaTetelek} hiba={higienia.hiba} onnyit={higieniaNyit} />
        </Szakasz>
      {/if}
      <Szakasz cim="Hasonló jegyzetek" ikon={Network} bind:nyitva={felulet.jobbPanel.hasonlo}>
        <Hasonlok valasz={hasonlo.valasz} betolt={hasonlo.betolt} hiba={hasonlo.hiba} onnyit={hasonloNyit} />
      </Szakasz>
    {/if}
  </div>
</aside>

<style>
  .jobb {
    grid-area: jobb;
    position: relative;
    display: flex;
    flex-direction: column;
    min-width: 0;
    overflow: hidden;
    background: var(--hatter-oldalsav);
    border-left: var(--keret-vastag) solid var(--keret);
  }

  .jobb[inert] {
    border-left-color: transparent;
  }

  /* C38: a rejtett jobb panel átfedésként (F6), a jobb szélről */
  .jobb.atfedes {
    position: fixed;
    top: 0;
    bottom: var(--allapotsor-hely);
    right: 0;
    width: var(--jobb-atfedes-sz);
    z-index: var(--reteg-lap);
    box-shadow: var(--arnyek-lap);
    transition: transform var(--mozgas-alap) var(--mozgas-gorbe);
  }

  @starting-style {
    .jobb.atfedes {
      transform: translateX(100%);
    }
  }

  .fejlec {
    flex: none;
    display: flex;
    align-items: center;
    justify-content: flex-end;
    height: var(--magassag-fejlec);
    padding: 0 var(--t-1);
  }

  .tartalom {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    gap: var(--t-1);
    padding: 0 var(--t-2) var(--t-4);
  }

  .ures {
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  .hiba {
    margin: 0 0 var(--t-2);
    color: var(--hiba);
    font-size: var(--betu-kicsi);
  }
</style>
