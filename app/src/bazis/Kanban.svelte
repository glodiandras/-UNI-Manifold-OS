<!--
  A Bases Kanban-nézete (C12b): az oszlop a `groupBy` tulajdonság egy értéke („Nincs érték” az üres értékeké; `Status`-nál a
  séma értékkészletének sorrendjében, üres oszloppal is). A kártya húzásra (HTML5) és az áthelyezés menüből (⋯, billentyűvel is)
  a jegyzet frontmatterébe írja az oszlop értékét, a nyitott dokumentumon át: egy írási út, mentés, pillanatkép és
  „Visszavonás” értesítés. A séma-sértő érték nem íródik csendben („Mégis beírom”). Csak `.md` sor és note-tulajdonság húzható.
-->
<script lang="ts">
  import { t, tp } from '../lib/i18n';
  import { tick } from 'svelte';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { Ellipsis } from '../lib/ikon/ikonok';
  import { lebegoMenu, type MenuElem } from '../szerkeszto/notion/menu';
  import { tulajdonsagApi } from '../szerkeszto/tulajdonsagok/api';
  import type { SemaProblema } from '../szerkeszto/tulajdonsagok/tipusok';
  import { cellaErtesites, cellaIr, cellaOlvas } from './cellaIr';
  import { iroTipus } from './cellaErtek';
  import Kartya from './Kartya.svelte';
  import { csoportKulcs, ejtesErtek, oszlopok as oszlopokSzamol, type KanbanOszlop } from './kanban';
  import type { Sor, Valasz } from './tipusok';

  interface Props {
    valasz: Valasz;
    ez?: string | null;
    /** a kártyák áthúzhatók (a jegyzetek szerkeszthetők, nem az Olvasó) */
    cellaIras?: boolean;
  }
  let { valasz, ez = null, cellaIras = false }: Props = $props();

  const kulcs = $derived(csoportKulcs(valasz));
  const tipus = $derived(valasz.fajl?.elerheto.find((e) => e.id === (valasz.nezet?.beallitas?.groupBy as { property?: string } | undefined)?.property)?.tipus ?? 'text');
  let statusSorrend = $state<string[] | undefined>(undefined);
  let semaKert = false;
  $effect(() => {
    if (kulcs === 'Status' && !semaKert) {
      semaKert = true;
      void tulajdonsagApi()
        .sema(ez ?? '')
        .then((s) => (statusSorrend = s.status_ertekkeszlet))
        .catch(() => (semaKert = false));
    }
  });

  /** az áthelyezett kártyák (út → oszlop-index): addig látszanak az új oszlopban, amíg az új válasz meg nem érkezik */
  let athelyezett = $state<Record<string, number>>({});
  $effect(() => {
    void valasz;
    athelyezett = {};
  });

  const alap = $derived(oszlopokSzamol(valasz, statusSorrend));
  const oszlopok = $derived.by((): KanbanOszlop[] => {
    const mozgott = Object.entries(athelyezett);
    if (!mozgott.length) return alap;
    const ki = alap.map((o) => ({ ...o, sorok: o.sorok.filter((s) => !(s.ut in athelyezett)) }));
    for (const [ut, i] of mozgott) {
      const sor = alap.flatMap((o) => o.sorok).find((s) => s.ut === ut);
      if (sor && ki[i]) ki[i].sorok = [...ki[i].sorok, sor];
    }
    return ki;
  });

  const beall = $derived(valasz.nezet?.beallitas ?? {});
  const arany = $derived(typeof beall.imageAspectRatio === 'number' && beall.imageAspectRatio > 0 ? beall.imageAspectRatio : null);
  const illesztes = $derived(String(beall.imageFit ?? 'cover'));

  const huzhato = (sor: Sor) => cellaIras && kulcs !== null && sor.md && !['tags', 'multitext', 'aliases'].includes(tipus);

  // ------------------------------------------------------------------ áthelyezés

  let fuggo = $state<{ sor: Sor; oszlop: number; ertek: string | number | boolean; problemak: SemaProblema[] } | null>(null);
  let hiba = $state<string | null>(null);

  async function athelyez(sor: Sor, cel: number, megerosit = false) {
    const o = oszlopok[cel];
    const ertek = o ? ejtesErtek(o) : undefined;
    if (!o || kulcs === null || ertek === undefined) return;
    const jelenlegi = alap.findIndex((x) => x.sorok.some((s) => s.ut === sor.ut));
    if (jelenlegi === cel && !megerosit) return;
    hiba = null;
    fuggo = null;
    // a frontmatterben ténylegesen álló kulcsot írja (mint a Tabla): eltérő kis-nagybetűnél se keletkezzen új kulcs (T165)
    const iroKulcs = (await cellaOlvas(sor.ut, kulcs).catch(() => null))?.kulcs ?? kulcs;
    const r = await cellaIr(sor.ut, iroKulcs, ertek, iroTipus(tipus === 'formula' ? 'text' : tipus), megerosit);
    if (r.ok) {
      athelyezett = { ...athelyezett, [sor.ut]: cel };
      cellaErtesites(sor.nev, iroKulcs, r.pillanat);
    } else if (r.fuggo) fuggo = { sor, oszlop: cel, ertek, problemak: r.fuggo };
    else hiba = r.elutasitva ?? t('Az áthelyezés nem írható.');
  }

  // ------------------------------------------------------------------ húzás

  let huzott = $state<Sor | null>(null);
  let celOszlop = $state<number | null>(null);

  function huzasKezd(e: DragEvent, sor: Sor) {
    if (!huzhato(sor)) return e.preventDefault();
    huzott = sor;
    e.dataTransfer?.setData('text/plain', sor.ut);
    if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move';
  }

  function oszlopFolott(e: DragEvent, i: number) {
    if (!huzott || !oszlopok[i]?.fogad) return;
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
    celOszlop = i;
  }

  function ejtes(e: DragEvent, i: number) {
    const sor = huzott;
    huzasVege();
    if (!sor || !oszlopok[i]?.fogad) return;
    e.preventDefault();
    void athelyez(sor, i);
  }

  function huzasVege() {
    huzott = null;
    celOszlop = null;
  }

  // ------------------------------------------------------------------ billentyűs áthelyezés (⋯ menü)

  function menu(e: MouseEvent, sor: Sor) {
    e.preventDefault();
    e.stopPropagation();
    const el = e.currentTarget as HTMLElement;
    const r = el.getBoundingClientRect();
    const aktualis = alap.findIndex((o) => o.sorok.some((s) => s.ut === sor.ut));
    const elemek: MenuElem[] = [];
    const akciok = new Map<string, () => void>();
    oszlopok.forEach((o, i) => {
      if (!o.fogad) return;
      const id = `o-${i}`;
      elemek.push({ id, nev: t('Áthelyezés ide: {cimke}', { cimke: o.cimke }), kijelolt: i === aktualis });
      akciok.set(id, () => void athelyez(sor, i));
    });
    lebegoMenu({ focus: () => el.focus() }, r.left, r.bottom + 2, elemek, akciok, t('{nev} áthelyezése', { nev: sor.nev }));
    void tick();
  }
</script>

<div class="kanban" aria-label="Kanban">
  {#if kulcs === null && valasz.csoportok}
    <p class="uzenet" role="status">{t('A Kanban oszlopai nem frontmatter-tulajdonságból állnak: az áthúzás nem írható.')}</p>
  {/if}
  {#if !valasz.csoportok}
    <p class="uzenet" role="status">{t('A Kanban-nézethez csoportosítás kell: a „Nézet” panelen válaszd ki azt a tulajdonságot (pl. Status), amely az oszlopokat adja.')}</p>
  {/if}
  {#if fuggo}
    <p class="uzenet figyelmeztetes" role="alert">
      {fuggo.problemak[0]?.uzenet ?? t('A séma sérül.')}
      <button type="button" class="m-gomb semleges gomb" onclick={() => fuggo && void athelyez(fuggo.sor, fuggo.oszlop, true)}>{t('Mégis beírom')}</button>
      <button type="button" class="m-gomb semleges gomb" onclick={() => (fuggo = null)}>{t('Mégse')}</button>
    </p>
  {/if}
  {#if hiba}<p class="uzenet hiba" role="alert">{hiba}</p>{/if}
  <div class="oszlopok">
    {#each oszlopok as o, i (i)}
      <!-- svelte-ignore a11y_no_static_element_interactions -->
      <section
        class="oszlop"
        class:cel={celOszlop === i}
        class:tiltott={huzott !== null && !o.fogad}
        aria-label={tp('{cimke}, {n} kártya', o.sorok.length, { cimke: o.cimke })}
        ondragover={(e) => oszlopFolott(e, i)}
        ondrop={(e) => ejtes(e, i)}
      >
        <h3 class="fej">
          <span class="cim">{o.cimke}</span>
          <span class="db">{o.sorok.length}</span>
        </h3>
        <div class="kartyak" role="list">
          {#each o.sorok as sor (sor.ut)}
            <!-- svelte-ignore a11y_no_static_element_interactions -->
            <div
              class="elem"
              class:huzott={huzott?.ut === sor.ut}
              role="listitem"
              draggable={huzhato(sor)}
              ondragstart={(e) => huzasKezd(e, sor)}
              ondragend={huzasVege}
            >
              <Kartya {sor} oszlopok={valasz.oszlopok} {ez} kepSzel={560} {illesztes} {arany}>
                {#snippet muvelet()}
                  {#if huzhato(sor)}
                    <button type="button" class="menu-gomb" aria-label={t('{nev} áthelyezése', { nev: sor.nev })} onclick={(e) => menu(e, sor)}>
                      <Ikon ikon={Ellipsis} meret={14} />
                    </button>
                  {/if}
                {/snippet}
              </Kartya>
            </div>
          {/each}
        </div>
      </section>
    {/each}
  </div>
</div>

<style>
  .kanban {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    font-size: var(--betu-ui);
    line-height: var(--sor-ui);
    color: var(--szoveg);
  }

  .uzenet {
    flex: none;
    margin: 0;
    padding: var(--t-1) var(--t-3);
    color: var(--szoveg-halvany);
  }

  .uzenet.figyelmeztetes {
    color: var(--figyelmeztetes);
    background: var(--figyelmeztetes-hatter);
  }

  .uzenet.hiba {
    color: var(--hiba);
    background: var(--hiba-hatter);
  }

  .gomb {
    margin-left: var(--t-1);
    padding: 0 var(--t-2);
  }

  .oszlopok {
    flex: 1;
    min-height: 0;
    display: flex;
    gap: var(--t-3);
    padding: var(--t-3);
    overflow: auto;
    align-items: stretch;
  }

  .oszlop {
    flex: none;
    display: flex;
    flex-direction: column;
    width: 280px;
    min-height: 0;
    border-radius: var(--kerekites);
    background: var(--hatter-oldalsav);
  }

  .oszlop.cel {
    outline: var(--jel-vastag) solid var(--akcent);
    outline-offset: var(--fokusz-tav-befele);
  }

  .oszlop.tiltott {
    opacity: var(--tiltott-atlatszosag);
  }

  .fej {
    flex: none;
    display: flex;
    align-items: baseline;
    gap: var(--t-2);
    margin: 0;
    padding: var(--t-2) var(--t-3);
    font-size: var(--betu-ui);
    font-weight: var(--suly-felkover);
  }

  .db {
    color: var(--szoveg-halvany);
    font-weight: var(--suly-normal);
    font-variant-numeric: tabular-nums;
  }

  .kartyak {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    gap: var(--t-2);
    padding: 0 var(--t-2) var(--t-2);
    overflow-y: auto;
  }

  .elem {
    min-width: 0;
  }

  .elem[draggable='true'] {
    cursor: grab;
  }

  .elem.huzott {
    opacity: var(--atlatszosag-felig);
  }

  .menu-gomb {
    display: grid;
    place-items: center;
    width: var(--magassag-suru);
    height: var(--magassag-suru);
    border: 0;
    border-radius: var(--kerekites-kicsi);
    background: transparent;
    color: var(--szoveg-halvany);
    cursor: pointer;
    opacity: 0;
  }

  .elem:hover .menu-gomb,
  .menu-gomb:focus-visible {
    opacity: 1;
  }

  .menu-gomb:hover {
    background: var(--hatter-hover);
  }
</style>
