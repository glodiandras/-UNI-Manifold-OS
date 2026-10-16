<!--
  Az ikonsáv (06-workspace-12): a parancsregiszter ikonjai a `felulet.ikonsav` szerint (rejtés, sorrend, az egész sáv
  elrejtése). Az ikon, a tooltip és a gyorsbillentyű a regiszterből jön, így a billentyű-testreszabással együtt marad.
  Jobb klikk (vagy a ContextMenu billentyű) az ikonon: elrejtés, mozgatás, a sáv elrejtése; az ikonok húzással is
  átrendezhetők a csoportjukon belül.
-->
<script lang="ts">
  import { modulEngedelyezett } from '../lib/beallitasok/allapot.svelte';
  import { parancsEngedelyezett } from '../lib/beallitasok/modulok';
  import { t } from '../lib/i18n';
  import { ikonAthelyez, ikonMozgat, ikonsavElemek, type IkonsavDef } from '../lib/elrendezes/ikonsav';
  import { kornyezet } from '../lib/kornyezet';
  import { parancsNev, regiszter } from '../lib/parancsok/regiszter';
  import IkonGomb from '../lib/ui/IkonGomb.svelte';
  import { lebegoMenu, type MenuElem } from '../szerkeszto/notion/menu';
  import Jelenlet from './vezerlo/Jelenlet.svelte';
  const { felulet } = kornyezet();

  const HUZAS = 'application/x-manifold-ikon';
  const elemek = $derived(ikonsavElemek(felulet.ikonsav));
  /** Látszik-e az ikon: a modul engedélyezett, és a regisztrált parancs elérhető (a shell nélküli futásban a munkaterület-váltó nem). */
  const lathato = (d: IkonsavDef) => {
    const p = regiszter.kap(d.id);
    return parancsEngedelyezett(d.id) && (!p || regiszter.elerheto(p));
  };
  const CIMKE: Record<string, () => string> = {
    'hej.oldalsav': () => (felulet.oldalsav.nyitva ? t('Fájlfa elrejtése') : t('Fájlfa megnyitása')),
    'kereses.panel': () => t('Keresés a vaultban'),
    'fa.uj-jegyzet': () => t('Új jegyzet'),
    'munkater.valto': () => t('Munkaterület váltása'),
    'manifold.vezerlo': () => t('Manifold áttekintő'),
    'beallitasok.megnyit': () => t('beallitasok.cim'),
  };
  /** A regisztrált parancs neve; a regiszter nélküli (teszt) környezetben a gomb így is felirattal áll. */
  function cimke(id: string): string {
    const p = regiszter.kap(id);
    return CIMKE[id]?.() ?? (p ? parancsNev(p) : id);
  }
  const billentyu = (id: string) => regiszter.kap(id)?.billentyu;

  function menu(e: MouseEvent | KeyboardEvent, id: string | null) {
    e.preventDefault();
    const elemMenu: MenuElem[] = [], akciok = new Map<string, () => void>();
    const hozzaad = (mid: string, nev: string, fn: () => void) => { elemMenu.push({ id: mid, nev }); akciok.set(mid, fn); };
    if (id) {
      hozzaad('rejt', t('Ikon elrejtése'), () => { felulet.ikonsav.rejtett = [...felulet.ikonsav.rejtett, id]; });
      hozzaad('fel', t('Mozgatás felfelé'), () => { felulet.ikonsav = ikonMozgat(felulet.ikonsav, id, -1); });
      hozzaad('le', t('Mozgatás lefelé'), () => { felulet.ikonsav = ikonMozgat(felulet.ikonsav, id, 1); });
    }
    for (const rejtett of ikonsavElemek(felulet.ikonsav, true).felso.concat(ikonsavElemek(felulet.ikonsav, true).also)) {
      if (felulet.ikonsav.rejtett.includes(rejtett.id) && lathato(rejtett))
        hozzaad(`mutat-${rejtett.id}`, t('Ikon megjelenítése: {nev}', { nev: cimke(rejtett.id) }), () => { felulet.ikonsav.rejtett = felulet.ikonsav.rejtett.filter((x) => x !== rejtett.id); });
    }
    hozzaad('sav', t('Ikonsáv elrejtése'), () => { felulet.ikonsav.lathato = false; });
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const x = e instanceof MouseEvent && e.clientX ? e.clientX : r.right, y = e instanceof MouseEvent && e.clientY ? e.clientY : r.top;
    lebegoMenu({ focus: () => (e.currentTarget as HTMLElement | null)?.focus?.() }, x, y, elemMenu, akciok, t('Ikonsáv menü'));
  }
  const billentyuMenu = (e: KeyboardEvent, id: string | null) => { if (e.key === 'ContextMenu' || (e.shiftKey && e.key === 'F10')) menu(e, id); };

  let huzott = $state<string | null>(null);
  function ejt(e: DragEvent, cel: string) {
    const id = e.dataTransfer?.getData(HUZAS) || huzott;
    huzott = null;
    if (!id) return;
    e.preventDefault();
    felulet.ikonsav = ikonAthelyez(felulet.ikonsav, id, cel);
  }
  function felett(e: DragEvent) {
    if (huzott && e.dataTransfer?.types.includes(HUZAS)) { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; }
  }
</script>

{#snippet ikonGomb(d: IkonsavDef)}
  <IkonGomb
    ikon={d.ikon}
    cimke={cimke(d.id)}
    billentyu={billentyu(d.id)}
    data-ikonsav={d.id}
    draggable="true"
    ondragstart={(e) => { huzott = d.id; e.dataTransfer?.setData(HUZAS, d.id); if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move'; }}
    ondragover={felett}
    ondrop={(e) => ejt(e, d.id)}
    ondragend={() => (huzott = null)}
    oncontextmenu={(e) => menu(e, d.id)}
    onkeydown={(e) => billentyuMenu(e, d.id)}
    onclick={() => regiszter.futtat(d.id, 'gomb')}
  />
{/snippet}

<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<nav class="ikonsav" class:rejtett={!felulet.ikonsav.lathato} inert={!felulet.ikonsav.lathato} aria-label={t('Gyorsműveletek')} oncontextmenu={(e) => { if (e.target === e.currentTarget) menu(e, null); }}>
  {#each elemek.felso as d (d.id)}{#if lathato(d)}{@render ikonGomb(d)}{/if}{/each}
  <div class="also">
    {#each elemek.also as d (d.id)}{#if lathato(d)}{@render ikonGomb(d)}{/if}{/each}
    {#if modulEngedelyezett('asszisztens')}<Jelenlet />{/if}
  </div>
</nav>

<style>
  .ikonsav { grid-area: ikon; display: flex; align-items: center; flex-direction: column; padding: var(--t-2) 0; gap: var(--t-2); background: var(--hatter-oldalsav); border-right: var(--keret-vastag) solid var(--keret); overflow: hidden; }
  .ikonsav.rejtett { visibility: hidden; border-right-width: 0; padding: 0; }
  .also { margin-top: auto; display: flex; flex-direction: column; align-items: center; gap: var(--t-2); }
</style>
