<!--
  A Markdown-jegyzet nézete (C08): Live Preview, Forrás és Olvasó. A szöveg a jegyzet Dokumentumában él
  (a mentés, az ütközés és a külső változás ott); ez a komponens a CodeMirror-nézet, az olvasó és a fejléc.
  A fülváltás után a CodeMirror-állapot (kurzor, görgetés, visszavonás) a fülhöz tárolva megmarad; a mód és
  a felső sor a fül tartós nézet-állapotába kerül. A jegyzet elhagyása lezárja a szerkesztést (pillanatkép).
-->
<script lang="ts">
  import { t } from '../lib/i18n';
  import { EditorState, StateEffect, Transaction } from '@codemirror/state';
  import { EditorView } from '@codemirror/view';
  import { onMount, untrack } from 'svelte';
  import { ApiHiba } from '../lib/core/api';
  import type { NezetProps } from '../lib/elrendezes/nezetek.svelte';
  import { BookOpen, SquarePen } from '../lib/ikon/ikonok';
  import { kornyezet } from '../lib/kornyezet';
  import { regiszter } from '../lib/parancsok/regiszter';
  import { valtozasMeret } from '../lib/tracker/karakter';
  import { trackerKliens } from '../lib/tracker/kliens.svelte';
  import IkonGomb from '../lib/ui/IkonGomb.svelte';
  import JegyzetIkon from '../lib/ui/JegyzetIkon.svelte';
  import { fajlNev, mappa } from '../lib/vault/fajlok.svelte';
  import { linkek } from '../lib/vault/linkek.svelte';
  import { vezerloKapcsolok } from '../lib/vezerlo/kapcsolok.svelte';
  import { bovitmenyek, elonezetMod, forrasMod, irhatosagKapcsolo, modKapcsolo, szinkronJel } from './beallitas';
  import { felismertNyelv } from './nyelv';
  import type { Csatolt, Dokumentum } from './dokumentum/dokumentum.svelte';
  import { csere } from './dokumentum/kulonbseg';
  import { alapKliens, javaslatUrit } from './asszisztens/javaslat';
  import { folytatasBovitmeny, folytatasForras, folytatasKliens, folytatasUrit } from './asszisztens/folytatas';
  import { kartyaUtemezo, kartyaUtemezoForras } from './asszisztens/kartyaUtemezo';
  import { kartyaAllapot } from '../lib/asszisztens/kartya.svelte';
  import { asszisztensApi } from '../lib/asszisztens/api';
  import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
  import { linkVerzioValt } from './beagyazas/widget';
  import { eloFejezetek } from './linkek/kiegeszites';
  import Olvaso from './Olvaso.svelte';
  import Boritokep from './tulajdonsagok/Boritokep.svelte';
  import Tulajdonsagok from './tulajdonsagok/Tulajdonsagok.svelte';
  import { eloKurzorIgazit, eloTulajdonsagForras } from './tulajdonsagok/elo.svelte';
  import { szerkesztok, type Mod, type SzerkesztoPeldany } from './szerkesztok.svelte';
  import MentesJelzes from './MentesJelzes.svelte';
  import FajlCim from './FajlCim.svelte';
  import { csatolmanyBovitmeny } from './csatolmany';
  import Utkozes from './Utkozes.svelte';

  let { ful, aktiv }: NezetProps = $props();
  const { felulet, fajlok } = kornyezet();
  const ut = untrack(() => ful.ut ?? '');
  const fulId = untrack(() => ful.id);

  let mod = $state<Mod>(kezdoMod());
  let dok = $state.raw<Dokumentum | null>(null);
  let betoltesHiba = $state<string | null>(null);
  let utkozesNyitva = $state(true);
  let cmHely: HTMLDivElement | undefined = $state();
  let olvaso: Olvaso | undefined = $state();
  let view = $state.raw<EditorView | null>(null);
  let docValtozat = $state(0);
  let tartalmiKod = $state('');

  function kezdoMod(): Mod {
    const m = untrack(() => ful.nezet?.mod);
    return m === 'elo' || m === 'forras' || m === 'olvaso' ? m : untrack(() => felulet.szerkesztoMod);
  }

  function nezetAllapotIr(tobbi: Record<string, unknown> = {}) {
    ful.nezet = { ...(ful.nezet ?? {}), mod, ...tobbi };
  }

  const csatolt: Csatolt = {
    alkalmaz(valtozas, elozmenybe = false) {
      view?.dispatch({
        changes: valtozas,
        annotations: [szinkronJel.of(true), Transaction.addToHistory.of(elozmenybe)],
      });
      docValtozat++;
    },
  };

  /** A blokklink neve: a core legrövidebb egyértelmű cél-szövege (L42); ha nem érhető el, a fájlnév. */
  async function linkNev(): Promise<string> {
    try {
      return await linkek.linkCel(ut, ut);
    } catch {
      return fajlNev(ut);
    }
  }

  /** A javaslat linkjének célja: a core legrövidebb egyértelmű alakja (L42); ha nem érhető el, a fájlnév. */
  async function javaslatLinkCel(celUt: string): Promise<string> {
    try {
      return await linkek.linkCel(celUt, ut);
    } catch {
      return fajlNev(celUt);
    }
  }

  /** J1: a beírt jegyzet-link a tanuló magnak (ismétlődő művelet); kikapcsolt Asszisztensnél nem megy ki semmi. */
  function asszisztensTanulLink(cel: string): void {
    if (vezerloKapcsolok.ertek.asszisztens && ut.toLowerCase().endsWith('.md'))
      void asszisztensApi.tanul('link', ut, cel).catch(() => undefined);
  }

  /** J3: a javaslat-kártya ütemezője ebben a szerkesztőben (csak .md jegyzetben; a kártya maga a héjban él). */
  const kartyaBeallitas = {
    ut,
    kapcsolo: () => vezerloKapcsolok.ertek.asszisztens && ut.toLowerCase().endsWith('.md') && mod !== 'olvaso',
    latszik: () => !!kartyaAllapot.aktiv,
    ker: (alkalom: 'megnyitas' | 'szunet', szoveg: string, jel: AbortSignal) => asszisztensApi.kartya(ut, szoveg, alkalom, jel),
    mutat: (j: Parameters<typeof kartyaAllapot.mutat>[0], v: EditorView) =>
      kartyaAllapot.mutat(j, v, { ut, linkCel: javaslatLinkCel, sablon: async (s: string) => (await import('../ma/naplo')).sablonBeszurasAktiv(s) }),
    bezar: (v: EditorView) => kartyaAllapot.elrejt('figyelmen_kivul', v),
  };

  function letrehoz(d: Dokumentum) {
    if (!cmHely) return;
    const tarolt = szerkesztok.allapot(fulId, ut);
    const szerkMod = mod === 'olvaso' ? felulet.szerkesztoMod : mod;
    const ex = bovitmenyek({
          mod: szerkMod,
          csakOlvashato: !!d.csakOlvashato,
          ut,
          cimke: t('Jegyzet: {nev}', { nev: fajlNev(ut) }),
          linkNev,
          kiegeszites: { fajlok: () => fajlok.lista, legutobbi: () => felulet.legutobbiFajlok, tanul: asszisztensTanulLink },
          tovabbi: [folytatasBovitmeny(), folytatasForras.of({ ...folytatasKliens,
            kapcsolo: () => vezerloKapcsolok.ertek.asszisztens,
            jelzes: szoveg => ertesitesek.ertesit({ szint: 'info', cim: t('Asszisztens'), szoveg }),
          }), kartyaUtemezo(), kartyaUtemezoForras.of(kartyaBeallitas), csatolmanyBovitmeny(ut), eloTulajdonsagForras.of({ ut, nyitottsag: felulet.tulajdonsagok,
            kiegeszites: { fajlok: () => fajlok.lista, legutobbi: () => felulet.legutobbiFajlok } })],
          // C30b-mag: a linkeletlen említések javaslata (Tab/Esc); a kapcsoló élő értéke a core állapota (10. döntés)
          javaslat: { ut, kapcsolo: () => vezerloKapcsolok.ertek.asszisztens, linkCel: javaslatLinkCel, kliens: alapKliens },
        });
    let state: EditorState;
    if (tarolt) {
      state = tarolt.allapot.update({ effects: [StateEffect.reconfigure.of(ex), folytatasUrit.of(null)] }).state;
      const c = csere(state.doc, d.szoveg.toString());
      if (c) state = state.update({ changes: c, annotations: [szinkronJel.of(true), Transaction.addToHistory.of(false)] }).state;
    } else {
      const kurzor = Number(ful.nezet?.kurzor);
      state = EditorState.create({
        doc: d.szoveg,
        selection: Number.isFinite(kurzor) && kurzor <= d.szoveg.length ? { anchor: kurzor } : undefined,
        extensions: ex,
      });
    }
    view = new EditorView({
      state,
      parent: cmHely,
      dispatchTransactions(trs, v) {
        v.update(trs);
        tartalmiKod = v.state.field(felismertNyelv);
        for (const tr of trs)
          if (tr.docChanged && !tr.annotation(szinkronJel)) {
            d.valtozott(tr.changes, tr.newDoc, csatolt);
            docValtozat++;
            const m = valtozasMeret(tr.changes); // C27: a szerkesztett karakterek száma (a szöveg nem megy sehova)
            trackerKliens.szerkesztes(ut, m.beszurt, m.torolt);
          }
      },
    });
    tartalmiKod = view.state.field(felismertNyelv);
    if (tarolt) {
      view.dispatch({ effects: modKapcsolo.reconfigure(szerkMod === 'elo' ? elonezetMod() : forrasMod()) });
      const g = tarolt.gorgetes;
      requestAnimationFrame(() => view && (view.scrollDOM.scrollTop = g));
    } else {
      const sor = Number(ful.nezet?.sor);
      if (Number.isFinite(sor) && sor > 1 && sor <= state.doc.lines)
        view.dispatch({ effects: EditorView.scrollIntoView(state.doc.line(sor).from, { y: 'start' }) });
    }
    eloKurzorIgazit(view); // CX-006: a kurzor nem marad a tulajdonság-widget mögötti, láthatatlan helyen
    view.scrollDOM.addEventListener('scroll', allapotUtemez, { passive: true });
    view.contentDOM.addEventListener('keyup', allapotUtemez);
    view.contentDOM.addEventListener('mouseup', allapotUtemez);
    if (aktiv && mod !== 'olvaso') queueMicrotask(() => view?.focus());
  }

  // a görgetés és a kurzor helye a fül tartós állapotába, a mozgás után 1 s-mal (újratöltéskor is megmarad)
  let allapotIdozito: ReturnType<typeof setTimeout> | null = null;
  function allapotUtemez() {
    if (allapotIdozito) clearTimeout(allapotIdozito);
    allapotIdozito = setTimeout(() => {
      allapotIdozito = null;
      if (view && mod !== 'olvaso' && ful.ut === ut) nezetAllapotIr({ sor: felsoSor(), kurzor: view.state.selection.main.head });
    }, 1000);
  }

  function felsoSor(): number {
    if (!view) return 1;
    const blokk = view.lineBlockAtHeight(Math.max(0, view.scrollDOM.getBoundingClientRect().top - view.documentTop));
    return view.state.doc.lineAt(blokk.from).number;
  }

  function lebont() {
    if (allapotIdozito) clearTimeout(allapotIdozito);
    if (view) {
      const nyit = view.state.selection.main.head;
      // csak ha a fül még ezt a jegyzetet mutatja: másik fájl megnyitásakor a fül nézet-állapota már az újé
      if (mod !== 'olvaso' && ful.ut === ut) nezetAllapotIr({ sor: felsoSor(), kurzor: nyit });
      szerkesztok.tarol(fulId, { ut, allapot: view.state, gorgetes: view.scrollDOM.scrollTop });
      view.destroy();
      view = null;
    }
  }

  // ------------------------------------------------------------------ módok

  function modBeallit(uj: Mod) {
    if (uj === mod) return;
    const felso = mod === 'olvaso' ? olvaso?.felsoPozicio() : view ? view.state.doc.line(felsoSor()).from : 0;
    if (uj === 'olvaso') void dok?.lezar(); // az olvasóra váltás lezárja a szerkesztést (legacy)
    else {
      view?.dispatch({ effects: modKapcsolo.reconfigure(uj === 'elo' ? elonezetMod() : forrasMod()) });
      felulet.szerkesztoMod = uj;
    }
    mod = uj;
    nezetAllapotIr();
    requestAnimationFrame(() => {
      if (felso === undefined) return;
      if (uj === 'olvaso') olvaso?.gorget(felso);
      else if (view) {
        view.dispatch({ effects: EditorView.scrollIntoView(felso, { y: 'start' }) });
        if (aktiv) view.focus();
      }
    });
  }

  const peldany: SzerkesztoPeldany = {
    ut,
    nezet: () => view,
    mod: () => mod,
    olvasoValt: () => modBeallit(mod === 'olvaso' ? felulet.szerkesztoMod : 'olvaso'),
    forrasValt: () => modBeallit(mod === 'elo' ? 'forras' : mod === 'forras' ? 'elo' : felulet.szerkesztoMod === 'elo' ? 'forras' : 'elo'),
    mentes: async () => {
      await dok?.ment();
    },
    pillanatkep: async () => {
      await dok?.ment({ pillanat: true });
    },
    fokuszban: () => !!view?.hasFocus,
    ugras(sor, oszlop = 0) {
      if (!view) return;
      const d = view.state.doc;
      const s = d.line(Math.min(Math.max(1, Math.floor(sor)), d.lines));
      if (mod === 'olvaso') {
        olvaso?.gorget(s.from);
        return;
      }
      const kurzor = Math.min(s.from + Math.max(0, oszlop), s.to);
      view.dispatch({ selection: { anchor: kurzor }, effects: EditorView.scrollIntoView(kurzor, { y: 'center' }) });
      if (aktiv) view.focus();
    },
    vazlat: () => (view ? eloFejezetek(view.state) : []),
    valtozat: () => docValtozat,
  };

  $effect(() => {
    if (aktiv) {
      szerkesztok.beallit(peldany);
      if (view) {
        const u = szerkesztok.fuggoUgrasKap(ut); // a (most megnyílt vagy aktiválódó) fülre várt ugrás
        if (u) queueMicrotask(() => peldany.ugras(u.sor, u.oszlop));
      }
    } else szerkesztok.elenged(peldany);
  });

  // a fájlszerkezet változása (új fájl): a függő beágyazások újrafeloldódnak
  $effect(() => {
    const v = linkek.verzio;
    untrack(() => view?.dispatch({ effects: linkVerzioValt.of(v) }));
  });

  // ------------------------------------------------------------------ életciklus

  onMount(() => {
    let el = true;
    let leCsatol: (() => void) | null = null;
    szerkesztok.dokumentumok.megnyit(ut).then(
      (d) => {
        if (!el) {
          void szerkesztok.dokumentumok.elenged(d); // a fül közben bezárult: a nézet nélküli dokumentum nem ragad a térképben (T119)
          return;
        }
        dok = d;
        leCsatol = d.csatol(csatolt);
        letrehoz(d);
      },
      (e) => {
        if (!el) return;
        betoltesHiba =
          e instanceof ApiHiba && e.statusz === 404 ? t('A jegyzet nincs meg (törölték vagy áthelyezték).') : t('A jegyzet nem tölthető be: {hiba}', { hiba: e instanceof Error ? e.message : String(e) });
      },
    );
    return () => {
      el = false;
      szerkesztok.megszunt(peldany);
      lebont();
      leCsatol?.();
      if (dok) void szerkesztok.dokumentumok.elenged(dok);
    };
  });

  // az Asszisztens kikapcsolása azonnal eltünteti a linkjavaslat aláhúzásait (10. döntés)
  $effect(() => {
    if (!vezerloKapcsolok.ertek.asszisztens) untrack(() => { view?.dispatch({ effects: [javaslatUrit.of(null), folytatasUrit.of(null)] }); kartyaAllapot.elrejt(null); });
  });

  // a csak olvasható állapot változhat (pl. ütközés közben nem), a Compartment követi
  $effect(() => {
    const ro = !!dok?.csakOlvashato;
    view?.dispatch({ effects: irhatosagKapcsolo.reconfigure(EditorState.readOnly.of(ro)) });
  });

  $effect(() => {
    if (dok?.allapot === 'utkozes') utkozesNyitva = true;
  });

  const allapotSzoveg = $derived.by(() => {
    switch (dok?.allapot) {
      case 'hiba':
        return dok.zarraVar ? t('Nincs mentve — várakozás a zárra') : t('Nincs mentve — újrapróbálás');
      case 'eltunt':
        return t('A fájl eltűnt — nincs mentve');
      default:
        return '';
    }
  });
</script>

<div class="szerkeszto" class:olvaso-mod={mod === 'olvaso'}>
  <header class="fejlec" data-csend-terulet>
    <p class="morzsa" title={ut} data-csend-rejt>
      <span class="morzsa-ikon"><JegyzetIkon {ut} tipus="md" meret={14} /></span>
      {#if mappa(ut)}<span class="mappa">{`${mappa(ut).replaceAll('/', ' / ')} / `}</span>{/if}<span class="nev">{fajlNev(ut)}</span>
    </p>
    <div class="jelek" role="status">
      {#if dok?.csakOlvashato}
        <span class="jel figyelmeztetes" title={dok.csakOlvashato}>{t('Csak olvasható')}</span>
      {/if}
      {#if dok?.allapot === 'utkozes'}
        <button type="button" class="jel hiba gomb" onclick={() => (utkozesNyitva = true)}>
          {t('Ütközés — döntés kell')}
        </button>
      {:else if allapotSzoveg}
        <!-- C38: a hibás állapot jele mindig látszik; a halk „Mentés…”/„Mentve” a jobb alsó sarokban áll (E12) -->
        <span class="jel" class:hiba={!dok?.zarraVar} class:figyelmeztetes={dok?.zarraVar} title={dok?.hiba ?? undefined}>{allapotSzoveg}</span>
      {/if}
    </div>
    {#if mod === 'olvaso'}
      <IkonGomb ikon={SquarePen} cimke={t('Szerkesztés')} billentyu="Mod+E" data-csend-rejt onclick={() => regiszter.futtat('szerkeszto.olvaso', 'gomb')} />
    {:else}
      <IkonGomb
        ikon={BookOpen}
        cimke={t('Olvasó nézet')}
        billentyu="Mod+E"
        data-csend-rejt
        onclick={() => regiszter.futtat('szerkeszto.olvaso', 'gomb')}
      />
    {/if}
  </header>

  {#if betoltesHiba}
    <p class="betoltes-hiba" role="alert">{betoltesHiba}</p>
  {/if}

  <Boritokep {ut} />
  <FajlCim {ut} irhato={!!dok && !dok.csakOlvashato && dok.allapot !== 'utkozes' && dok.allapot !== 'eltunt'} />
  {#if dok && view && mod === 'olvaso'}
    <Tulajdonsagok
      {ut}
      szoveg={() => dok!.szoveg}
      alkalmaz={(c) => view?.dispatch({ changes: c, userEvent: 'input.tulajdonsag' })}
      valtozat={docValtozat}
      irhato={!dok.csakOlvashato && dok.allapot !== 'utkozes' && dok.allapot !== 'eltunt'}
      bind:nyitva={felulet.tulajdonsagok.nyitva}
      kiegeszites={{ fajlok: () => fajlok.lista, legutobbi: () => felulet.legutobbiFajlok }}
    />
  {/if}

  <div class="cm-hely" bind:this={cmHely} hidden={mod === 'olvaso'}></div>

  {#if mod === 'olvaso' && dok && view}
    <Olvaso bind:this={olvaso} {view} {dok} {ut} valtozat={docValtozat} nyelv={tartalmiKod} />
  {/if}

  {#if dok?.allapot === 'utkozes' && utkozesNyitva && aktiv}
    <Utkozes {dok} onbezar={() => (utkozesNyitva = false)} />
  {/if}

  <MentesJelzes {dok} />
</div>

<style>
  .szerkeszto {
    position: relative;
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    background: var(--hatter);
  }

  .fejlec {
    flex: none;
    display: flex;
    align-items: center;
    gap: var(--t-2);
    height: var(--magassag-fejlec);
    padding: 0 var(--t-2) 0 var(--t-4);
  }

  .morzsa {
    flex: 1;
    min-width: 0;
    margin: 0;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
    font-size: var(--betu-ui);
    line-height: var(--sor-ui);
    color: var(--szoveg-halvany);
  }

  .morzsa-ikon {
    display: inline-flex;
    vertical-align: -3px;
    margin-right: var(--t-1);
  }

  .morzsa .nev {
    color: var(--szoveg-masodlagos);
  }

  .jelek {
    display: flex;
    align-items: center;
    gap: var(--t-2);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    color: var(--szoveg-halvany);
  }

  .jel {
    white-space: nowrap;
  }

  .jel.hiba {
    color: var(--hiba);
  }

  .jel.figyelmeztetes {
    color: var(--figyelmeztetes);
  }

  .jel.gomb {
    height: var(--magassag-gomb-kicsi);
    padding: 0 var(--t-2);
    border-radius: var(--kerekites-kicsi);
    background: var(--hiba-hatter);
  }

  .jel.gomb:hover {
    background: var(--hatter-hover);
  }

  .betoltes-hiba {
    margin: var(--t-6) auto;
    max-width: var(--olvasasi-szelesseg);
    color: var(--hiba);
  }

  .cm-hely {
    flex: 1;
    min-height: 0;
    display: flex;
  }

  .cm-hely[hidden] {
    display: none;
  }
</style>
