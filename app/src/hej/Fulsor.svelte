<!--
  Egy panel fülsora (role="tablist"): ←→ a fülek között (automatikus aktiválás), középső kattintás zár,
  a fülek húzhatók (sorrend, és át egy másik panelre).
-->
<script lang="ts">
  import { t } from '../lib/i18n';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import JegyzetIkon from '../lib/ui/JegyzetIkon.svelte';
  import { CalendarDays, ChartNoAxesColumn, Gauge, GraduationCap, Network, Pin, Plus, X, ArrowLeft, ArrowRight } from '../lib/ikon/ikonok';
  import { kornyezet } from '../lib/kornyezet';
  import { nezetFul, type Ful, type PanelCs } from '../lib/elrendezes/munkaterulet.svelte';
  import IkonGomb from '../lib/ui/IkonGomb.svelte';
  import { lebegoMenu, type MenuElem } from '../szerkeszto/notion/menu';
  import { vagolapra } from '../szerkeszto/vagolap';
  import { regiszter } from '../lib/parancsok/regiszter';
  import { fajlNev } from '../lib/vault/fajlok.svelte';

  const HUZAS_TIPUS = 'application/x-manifold-ful';

  let { panel, aktivPanel, nezetId }: { panel: PanelCs; aktivPanel: boolean; nezetId: string } = $props();
  const { felulet, fajlok } = kornyezet();
  const m = felulet.munkaterulet;

  let lista: HTMLDivElement | undefined = $state();
  let ejtesHely = $state<number | null>(null);

  /** Az önálló nézet-fül (gráf, Ma) címe; a helyi gráfé a középpont neve. */
  function nezetCim(f: Ful): string {
    if (f.nezet?.tipus === 'ma' || f.nezet?.tipus === 'manifold') return t('Manifold');
    if (f.nezet?.tipus === 'dolgozat') return t('Dolgozat');
    if (f.nezet?.tipus === 'statisztika') return t('Statisztika');
    if (f.nezet?.tipus === 'hasznalat') return t('Használat');
    if (f.nezet?.tipus !== 'graf') return t('Új fül');
    const kozep = typeof f.nezet.kozeppont === 'string' ? fajlNev(f.nezet.kozeppont) : '';
    return f.nezet.mod === 'helyi' && kozep ? t('Helyi gráf: {kozep}', { kozep }) : t('Gráf');
  }
  const nezetIkon = (f: Ful) =>
    (f.nezet?.tipus === 'ma' || f.nezet?.tipus === 'manifold') ? CalendarDays : f.nezet?.tipus === 'dolgozat' ? GraduationCap : f.nezet?.tipus === 'statisztika' ? ChartNoAxesColumn : f.nezet?.tipus === 'hasznalat' ? Gauge : Network;
  const cim = (f: Ful) => (f.ut ? fajlNev(f.ut) : nezetFul(f) ? nezetCim(f) : t('Új fül'));
  const tabId = (f: Ful) => `ful-${f.id}`;

  function aktival(f: Ful) {
    m.aktival(panel.id, f.id);
  }

  function billentyu(e: KeyboardEvent, i: number) {
    if (e.key === 'ContextMenu' || (e.shiftKey && e.key === 'F10')) {
      e.preventDefault();
      const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
      menu(panel.fulek[i], r.left, r.bottom);
      return;
    }
    let j: number;
    if (e.key === 'ArrowRight') j = (i + 1) % panel.fulek.length;
    else if (e.key === 'ArrowLeft') j = (i - 1 + panel.fulek.length) % panel.fulek.length;
    else if (e.key === 'Home') j = 0;
    else if (e.key === 'End') j = panel.fulek.length - 1;
    else if (e.key === 'Delete' || e.key === 'Backspace') {
      e.preventDefault();
      m.bezar(panel.id, panel.fulek[i].id);
      return;
    } else return;
    e.preventDefault();
    const f = panel.fulek[j];
    aktival(f);
    lista?.querySelector<HTMLElement>(`#${tabId(f)}`)?.focus();
  }

  function menu(f: Ful, x: number, y: number) {
    aktival(f);
    const elemek: MenuElem[] = [], akciok = new Map<string, () => void>();
    const hozzaad = (id: string, nev: string, fn: () => void) => { elemek.push({ id, nev }); akciok.set(id, fn); };
    hozzaad('rogzit', f.rogzitett ? t('Fül rögzítésének feloldása') : t('Fül rögzítése'), () => m.rogzit(panel.id, f.id));
    hozzaad('bezar', t('Fül bezárása'), () => m.bezar(panel.id, f.id));
    hozzaad('tobbi', t('Többi nem rögzített fül bezárása'), () => m.bezarTobbit('tobbi', panel.id, f.id));
    hozzaad('jobb', t('Jobbra lévő nem rögzített fülek bezárása'), () => m.bezarTobbit('jobb', panel.id, f.id));
    hozzaad('mind', t('Csoport nem rögzített füleinek bezárása'), () => m.bezarTobbit('mind', panel.id, f.id));
    hozzaad('oszt-jobbra', t('Osztás jobbra'), () => m.oszt('sor'));
    hozzaad('oszt-le', t('Osztás lefelé'), () => m.oszt('oszlop'));
    if (f.ut) {
      const ut = f.ut;
      hozzaad('megmutat', t('Megmutatás a fájlfában'), () => felulet.megmutatFaban(ut));
      hozzaad('ut', t('Vault-út másolása'), () => void vagolapra(ut));
      if (regiszter.kap('vault.atnevezes') && regiszter.elerheto(regiszter.kap('vault.atnevezes')!)) hozzaad('atnevez', t('Átnevezés…'), () => void regiszter.futtat('vault.atnevezes', 'gomb'));
    }
    hozzaad('csoport', t('Fülcsoport bezárása'), () => m.bezarPanel(panel.id));
    lebegoMenu({ focus: () => lista?.querySelector<HTMLElement>(`#${tabId(panel.fulek.find(f => f.id === panel.aktiv) ?? f)}`)?.focus() }, x, y, elemek, akciok, t('Fül menü'));
  }

  function navigal(irany: -1 | 1) { m.aktival(panel.id); m.navigal(irany); }

  function huzasKezd(e: DragEvent, f: Ful) {
    e.dataTransfer?.setData(HUZAS_TIPUS, f.id);
    if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move';
  }

  function hely(e: DragEvent): number {
    const fulek = [...(lista?.querySelectorAll<HTMLElement>('.ful') ?? [])];
    for (const [i, el] of fulek.entries()) {
      const r = el.getBoundingClientRect();
      if (e.clientX < r.left + r.width / 2) return i;
    }
    return fulek.length;
  }

  function felett(e: DragEvent) {
    if (!e.dataTransfer?.types.includes(HUZAS_TIPUS)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    ejtesHely = hely(e);
  }

  function ejt(e: DragEvent) {
    const id = e.dataTransfer?.getData(HUZAS_TIPUS);
    const i = ejtesHely ?? hely(e);
    ejtesHely = null;
    if (!id) return;
    e.preventDefault();
    m.athelyez(id, panel.id, i);
  }
</script>

<div class="fulsor" class:aktiv-panel={aktivPanel} data-csend-halvanyul data-csend-terulet>
  <IkonGomb ikon={ArrowLeft} cimke={t('Vissza az előző jegyzethez')} kicsi disabled={!m.navigalhato(-1, panel.aktiv ?? undefined)} onclick={() => navigal(-1)} />
  <IkonGomb ikon={ArrowRight} cimke={t('Előre a következő jegyzethez')} kicsi disabled={!m.navigalhato(1, panel.aktiv ?? undefined)} onclick={() => navigal(1)} />
  <div
    class="fulek"
    role="tablist"
    aria-label={t('Fülek')}
    tabindex="-1"
    bind:this={lista}
    ondragover={felett}
    ondragleave={() => (ejtesHely = null)}
    ondrop={ejt}
    ondblclick={(e) => { if (e.target === e.currentTarget) m.ujFul(panel.id); }}
  >
    {#each panel.fulek as f, i (f.id)}
      {@const aktiv = f.id === panel.aktiv}
      <div
        class="ful"
        class:aktiv
        class:ejtes-elott={ejtesHely === i}
        class:ejtes-utan={ejtesHely === panel.fulek.length && i === panel.fulek.length - 1}
        draggable="true"
        role="presentation"
        ondragstart={(e) => huzasKezd(e, f)}
        oncontextmenu={(e) => { e.preventDefault(); menu(f, e.clientX, e.clientY); }}
        onauxclick={(e) => {
          if (e.button === 1) m.bezar(panel.id, f.id);
        }}
      >
        <button
          type="button"
          role="tab"
          id={tabId(f)}
          class="fej"
          aria-selected={aktiv}
          aria-label={f.rogzitett ? `${cim(f)} · ${t('Rögzített fül')}` : undefined}
          aria-controls={aktiv ? nezetId : undefined}
          tabindex={aktiv ? 0 : -1}
          title={f.ut ?? cim(f)}
          onclick={() => aktival(f)}
          onkeydown={(e) => billentyu(e, i)}
        >
          {#if nezetFul(f)}
            <Ikon ikon={nezetIkon(f)} meret={14} />
          {:else}
            <JegyzetIkon ut={f.ut} tipus={f.ut ? fajlok.info(f.ut)?.tipus : undefined} meret={14} />
          {/if}
          <span class="nev">{cim(f)}</span>
          {#if f.rogzitett}<span title={t('Rögzített fül')}><Ikon ikon={Pin} meret={14} /></span>{/if}
        </button>
        <button
          type="button"
          class="bezar"
          tabindex="-1"
          aria-label={t('{cim} bezárása', { cim: cim(f) })}
          title={t('Bezárás (⌘W)')}
          onclick={() => m.bezar(panel.id, f.id)}
        >
          <Ikon ikon={X} meret={14} />
        </button>
      </div>
    {/each}
  </div>
  <IkonGomb ikon={Plus} cimke={t('Új fül')} billentyu="Mod+T" kicsi data-csend-rejt onclick={() => m.ujFul(panel.id)} />
</div>

<style>
  .fulsor {
    flex: none;
    display: flex;
    align-items: center;
    gap: var(--t-1);
    height: var(--fulsor-teljes);
    padding: 0 var(--t-2);
    border-bottom: var(--keret-vastag) solid var(--keret);
    background: var(--hatter);
  }

  .fulek {
    display: flex;
    align-items: center;
    gap: 2px;
    min-width: 0;
    overflow-x: auto;
    scrollbar-width: none;
    height: 100%;
  }

  .fulek::-webkit-scrollbar {
    display: none;
  }

  .ful {
    position: relative;
    display: flex;
    align-items: center;
    flex: 0 1 200px;
    min-width: 88px;
    height: var(--magassag-sor);
    border-radius: var(--kerekites);
    color: var(--szoveg-halvany);
    transition:
      background-color var(--mozgas-gyors) var(--mozgas-gorbe),
      color var(--mozgas-gyors) var(--mozgas-gorbe);
  }

  .ful:hover {
    background: var(--hatter-hover);
    color: var(--szoveg-masodlagos);
  }

  .ful.aktiv {
    background: var(--hatter-hover);
    color: var(--szoveg-masodlagos);
  }

  .aktiv-panel .ful.aktiv {
    background: var(--hatter-aktiv);
    color: var(--szoveg);
  }

  .ful.ejtes-elott::before,
  .ful.ejtes-utan::after {
    content: '';
    position: absolute;
    top: 4px;
    bottom: 4px;
    width: 2px;
    border-radius: var(--kerekites-jel);
    background: var(--akcent);
  }

  .ful.ejtes-elott::before {
    left: -2px;
  }

  .ful.ejtes-utan::after {
    right: -2px;
  }

  .fej {
    display: flex;
    align-items: center;
    gap: 6px;
    flex: 1;
    min-width: 0;
    height: 100%;
    padding: 0 var(--t-1) 0 var(--t-2);
    border-radius: var(--kerekites);
    color: inherit;
  }

  .fej:focus-visible {
    outline-offset: var(--fokusz-tav-befele);
  }

  .fej:active {
    background: var(--hatter-aktiv);
  }

  .nev {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .bezar {
    display: grid;
    place-items: center;
    flex: none;
    width: var(--magassag-gomb-kicsi);
    height: var(--magassag-gomb-kicsi);
    margin-right: var(--t-1);
    border-radius: var(--kerekites-kicsi);
    color: var(--szoveg-halvany);
    opacity: 0;
    transition: opacity var(--mozgas-gyors) var(--mozgas-gorbe);
  }

  .ful:hover .bezar,
  .ful.aktiv .bezar,
  .ful:focus-within .bezar {
    opacity: 1;
  }

  /* C38: csendben az aktív fül bezáró gombja is csak hoverre és fókuszra (⌘W) */
  :global(html[data-csend]) .ful.aktiv:not(:hover):not(:focus-within) .bezar {
    opacity: 0;
  }

  .bezar:hover {
    background: var(--hatter-aktiv);
    color: var(--szoveg);
  }

  .bezar:active {
    background: var(--keret-eros);
  }
</style>
