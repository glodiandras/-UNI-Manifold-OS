<!--
  A `.cpp` fül (C36a-UI): a forrás a `Dokumentum`-on át él (ugyanaz a mentés, ütközés, külső változás és kilépési mentés,
  mint a jegyzeté: az egyetlen írási út), a szerkesztő egy C++-ra hangolt CodeMirror (`szerkeszto.ts`), alul a ⌘R
  eredménye (`KodEredmeny`). A fül nem `SzerkesztoPeldany`: a Markdown-parancsok itt nem élnek; a ⌘S a `masNezet`-en át ment.
-->
<script lang="ts">
  import { EditorState, Transaction } from '@codemirror/state';
  import { EditorView } from '@codemirror/view';
  import { onMount, untrack } from 'svelte';
  import { ApiHiba } from '../lib/core/api';
  import type { NezetProps } from '../lib/elrendezes/nezetek.svelte';
  import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
  import { t } from '../lib/i18n';
  import { Bug, Play } from '../lib/ikon/ikonok';
  import { kornyezet } from '../lib/kornyezet';
  import { regiszter } from '../lib/parancsok/regiszter';
  import { valtozasMeret } from '../lib/tracker/karakter';
  import { trackerKliens } from '../lib/tracker/kliens.svelte';
  import IkonGomb from '../lib/ui/IkonGomb.svelte';
  import JegyzetIkon from '../lib/ui/JegyzetIkon.svelte';
  import { fajlNev, mappa } from '../lib/vault/fajlok.svelte';
  import { szinkronJel } from '../szerkeszto/beallitas';
  import type { Csatolt, Dokumentum } from '../szerkeszto/dokumentum/dokumentum.svelte';
  import { csere } from '../szerkeszto/dokumentum/kulonbseg';
  import { szerkesztok } from '../szerkeszto/szerkesztok.svelte';
  import { vagolapra } from '../szerkeszto/vagolap';
  import Utkozes from '../szerkeszto/Utkozes.svelte';
  import { kodFulok, type KodPeldany } from './aktiv.svelte';
  import { kodFutasok } from './futas.svelte';
  import { kodAI } from './ai.svelte';
  import { aiKer } from './aiElfogad';
  import KodAI from './KodAI.svelte';
  import KodEredmeny from './KodEredmeny.svelte';
  import { ellenoriz, mentesKivar } from './muveletek';
  import { cppNyelv, diagnosztikaBeallit, kodBovitmenyek, kodIrhatosag, nyelvKapcsolo } from './szerkeszto';

  let { ful, aktiv }: NezetProps = $props();
  const { felulet } = kornyezet();
  const ut = untrack(() => ful.ut ?? '');
  const fulId = untrack(() => ful.id);

  let dok = $state.raw<Dokumentum | null>(null);
  let view = $state.raw<EditorView | null>(null);
  let cmHely: HTMLDivElement | undefined = $state();
  let betoltesHiba = $state<string | null>(null);
  let utkozesNyitva = $state(true);

  const csatolt: Csatolt = {
    alkalmaz(valtozas, elozmenybe = false) {
      view?.dispatch({ changes: valtozas, annotations: [szinkronJel.of(true), Transaction.addToHistory.of(elozmenybe)] });
    },
  };

  function letrehoz(d: Dokumentum) {
    if (!cmHely) return;
    const tarolt = szerkesztok.allapot(fulId, ut);
    let state: EditorState;
    if (tarolt) {
      state = tarolt.allapot;
      const c = csere(state.doc, d.szoveg.toString());
      if (c) state = state.update({ changes: c, annotations: [szinkronJel.of(true), Transaction.addToHistory.of(false)] }).state;
    } else {
      const kurzor = Number(ful.nezet?.kurzor);
      state = EditorState.create({
        doc: d.szoveg,
        selection: Number.isFinite(kurzor) && kurzor <= d.szoveg.length ? { anchor: kurzor } : undefined,
        extensions: kodBovitmenyek({ csakOlvashato: !!d.csakOlvashato, cimke: t('C++ forrás: {nev}', { nev: fajlNev(ut) }) }),
      });
    }
    view = new EditorView({
      state,
      parent: cmHely,
      dispatchTransactions(trs, v) {
        v.update(trs);
        for (const tr of trs)
          if (tr.docChanged && !tr.annotation(szinkronJel)) {
            d.valtozott(tr.changes, tr.newDoc, csatolt);
            const m = valtozasMeret(tr.changes); // C27: csak a szám megy a trackerbe, a kód nem
            trackerKliens.szerkesztes(ut, m.beszurt, m.torolt);
          }
      },
    });
    if (tarolt) {
      const g = tarolt.gorgetes;
      requestAnimationFrame(() => view && (view.scrollDOM.scrollTop = g));
    }
    // a C++-nyelv lustán: a színezés a betöltés után kapcsol be
    void cppNyelv().then((nyelv) => {
      if (nyelv && view) view.dispatch({ effects: nyelvKapcsolo.reconfigure(nyelv) });
    });
    if (aktiv) queueMicrotask(() => view?.focus());
  }

  function lebont() {
    if (!view) return;
    if (ful.ut === ut) ful.nezet = { ...(ful.nezet ?? {}), kurzor: view.state.selection.main.head };
    szerkesztok.tarol(fulId, { ut, allapot: view.state, gorgetes: view.scrollDOM.scrollTop });
    view.destroy();
    view = null;
  }

  function irhato(): boolean {
    return !!dok && !dok.csakOlvashato && dok.allapot !== 'utkozes' && dok.allapot !== 'eltunt';
  }

  const peldany: KodPeldany = {
    ut,
    nezet: () => view,
    mentes: () => mentesKivar(ut),
    irhato,
    ugras(sor, oszlop) {
      if (!view) return;
      const d = view.state.doc;
      const s = d.line(Math.min(Math.max(1, Math.floor(sor)), d.lines));
      const kurzor = Math.min(s.from + Math.max(0, (oszlop ?? 1) - 1), s.to);
      view.dispatch({ selection: { anchor: kurzor }, effects: EditorView.scrollIntoView(kurzor, { y: 'center' }) });
      view.focus();
    },
  };
  const masNezet = { mentes: async () => void (await dok?.ment()) };

  $effect(() => {
    if (aktiv) {
      kodFulok.beallit(peldany);
      szerkesztok.masNezet = masNezet; // ⌘S a fül dokumentumát menti
    } else {
      kodFulok.elenged(peldany);
      if (szerkesztok.masNezet === masNezet) szerkesztok.masNezet = null;
    }
  });

  onMount(() => {
    let el = true;
    let leCsatol: (() => void) | null = null;
    szerkesztok.dokumentumok.megnyit(ut).then(
      (d) => {
        if (!el) {
          void szerkesztok.dokumentumok.elenged(d);
          return;
        }
        dok = d;
        leCsatol = d.csatol(csatolt);
        letrehoz(d);
      },
      (e) => {
        if (!el) return;
        betoltesHiba =
          e instanceof ApiHiba && e.statusz === 404 ? t('A fájl nincs meg (törölték vagy áthelyezték).') : t('A fájl nem tölthető be: {hiba}', { hiba: e instanceof Error ? e.message : String(e) });
      },
    );
    return () => {
      el = false;
      kodFulok.megszunt(peldany);
      if (szerkesztok.masNezet === masNezet) szerkesztok.masNezet = null;
      lebont();
      leCsatol?.();
      if (dok) void szerkesztok.dokumentumok.elenged(dok);
    };
  });

  $effect(() => {
    const ro = !!dok?.csakOlvashato;
    view?.dispatch({ effects: kodIrhatosag.reconfigure(EditorState.readOnly.of(ro)) });
  });

  $effect(() => {
    if (dok?.allapot === 'utkozes') utkozesNyitva = true;
  });

  // a ⌘R eredménye ehhez a fájlhoz
  const futas = $derived(kodFutasok.aktiv?.ut === ut ? kodFutasok.aktiv : null);
  const valasztas = $derived(kodFutasok.tobbertelmu?.ut === ut ? kodFutasok.tobbertelmu : null);

  // a fordító diagnosztikája aláhúzásként (új futás indulásakor törlődik)
  $effect(() => {
    const v = view;
    if (!v) return;
    const lista = futas?.fordit?.diagnosztika ?? [];
    untrack(() => diagnosztikaBeallit(v, lista));
  });

  function esc(e: KeyboardEvent) {
    if (e.key === 'Escape' && !e.defaultPrevented && futas?.allapot === 'fut') {
      e.preventDefault();
      void kodFutasok.megszakit();
    } else if (e.key === 'Escape' && !e.defaultPrevented && kodAI.fut && kodAI.aktiv?.cpp === ut) {
      e.preventDefault();
      void kodAI.megszakit();
    }
  }

  async function lemezenLevoBetolt() {
    const d = dok;
    if (!d) return;
    try {
      const lemez = await d.olvasLemezrol();
      const sajat = d.fajlSzoveg();
      d.lemezrolBetolt(lemez, true);
      const ok = await vagolapra(sajat);
      ertesitesek.ertesit({
        szint: 'info',
        cim: t('A lemezen lévő változat betöltve'),
        szoveg: ok ? t('A saját szöveged a vágólapon van.') : t('A fájl visszaállt a lemezen lévő változatra.'),
      });
    } catch (e) {
      ertesitesek.ertesit({ szint: 'hiba', cim: t('A lemezen lévő változat nem tölthető be'), szoveg: e instanceof Error ? e.message : String(e) });
    }
  }

  const allapotSzoveg = $derived.by(() => {
    switch (dok?.allapot) {
      case 'mentes':
        return t('Mentés…');
      case 'hiba':
        return t('Nincs mentve — újrapróbálás');
      case 'eltunt':
        return t('A fájl eltűnt — nincs mentve');
      default:
        return '';
    }
  });
</script>

<!-- svelte-ignore a11y_no_noninteractive_element_interactions (Esc a futás megszakítására, a fül egészén) -->
<article class="kod-ful" onkeydown={esc}>
  <header class="fejlec">
    <p class="morzsa" title={ut}>
      <span class="morzsa-ikon"><JegyzetIkon {ut} tipus="egyeb" meret={14} /></span>
      {#if mappa(ut)}<span class="mappa">{`${mappa(ut).replaceAll('/', ' / ')} / `}</span>{/if}<span class="nev">{fajlNev(ut)}</span>
    </p>
    <div class="jelek" role="status">
      {#if dok?.csakOlvashato}
        <span class="jel figyelmeztetes" title={dok.csakOlvashato}>{t('Csak olvasható')}</span>
      {/if}
      {#if dok?.allapot === 'utkozes'}
        <button type="button" class="jel hiba gomb" onclick={() => (utkozesNyitva = true)}>{t('Ütközés — döntés kell')}</button>
      {:else if allapotSzoveg}
        <span class="jel" class:hiba={dok?.allapot !== 'mentes'} title={dok?.hiba ?? undefined}>{allapotSzoveg}</span>
        {#if dok?.allapot === 'hiba'}
          <button type="button" class="jel gomb" onclick={lemezenLevoBetolt}>{t('A lemezen lévő betöltése')}</button>
        {/if}
      {/if}
    </div>
    <IkonGomb ikon={Bug} cimke={t('Ellenőrzés hibakereső móddal')} billentyu="Mod+Shift+R" onclick={() => regiszter.futtat('kod.ellenorzes-hibakereso', 'gomb')} />
    <IkonGomb ikon={Play} cimke={t('Ellenőrzés')} billentyu="Mod+R" onclick={() => regiszter.futtat('kod.ellenorzes', 'gomb')} />
  </header>

  {#if betoltesHiba}
    <p class="betoltes hiba" role="alert">{betoltesHiba}</p>
  {/if}

  <div class="cm-hely" bind:this={cmHely}></div>

  {#if valasztas}
    <div class="valasztas" role="group" aria-label={t('Melyik feladat-jegyzet tesztjei fussanak?')}>
      <span>{t('Több feladat-jegyzet ágyazza be ezt a fájlt. Melyik tesztjei fussanak?')}</span>
      {#each valasztas.jegyzetek as j (j)}
        <button
          type="button"
          class="jel gomb"
          onclick={() => {
            kodFutasok.jegyzetValasztas.set(ut, j);
            void ellenoriz(felulet, valasztas.mod, { ut, jegyzet: null }, j);
          }}>{fajlNev(j)}</button
        >
      {/each}
      <button type="button" class="jel gomb" onclick={() => (kodFutasok.tobbertelmu = null)}>{t('Mégse')}</button>
    </div>
  {/if}

  {#if futas}
    <KodEredmeny
      {futas}
      leirasok={kodFutasok.leirasok[futas.futas]}
      onugras={(sor, oszlop) => peldany.ugras(sor, oszlop)}
      onmegszakit={() => void kodFutasok.megszakit()}
    />
  {/if}

  <KodAI
    {ut}
    onker={(mod, megerosit) => void aiKer(felulet, mod, megerosit, { ut, jegyzet: null })}
    onugras={(sor) => peldany.ugras(sor)}
  />

  {#if dok?.allapot === 'utkozes' && utkozesNyitva && aktiv}
    <Utkozes {dok} onbezar={() => (utkozesNyitva = false)} />
  {/if}
</article>

<style>
  .kod-ful {
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
    padding: 0 var(--t-4);
  }

  .morzsa {
    flex: 1 1 auto;
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
    vertical-align: -2px;
    margin-right: var(--t-1);
  }

  .nev {
    color: var(--szoveg-masodlagos);
  }

  .jelek {
    flex: none;
    display: flex;
    gap: var(--t-2);
  }

  .jel {
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    color: var(--szoveg-halvany);
    padding: 2px var(--t-2);
    border-radius: var(--kerekites-kicsi);
  }

  .jel.figyelmeztetes {
    color: var(--figyelmeztetes);
    background: var(--figyelmeztetes-hatter);
  }

  .jel.hiba {
    color: var(--hiba);
    background: var(--hiba-hatter);
  }

  .gomb {
    border: none;
    cursor: pointer;
    font: inherit;
    background: var(--hatter-hover);
  }

  .gomb:focus-visible {
    outline: var(--fokusz-vastag) solid var(--fokusz-gyuru);
    outline-offset: var(--fokusz-tav);
  }

  .cm-hely {
    flex: 1 1 auto;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }

  .cm-hely :global(.cm-editor) {
    flex: 1 1 auto;
    min-height: 0;
  }

  .valasztas {
    flex: none;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--t-2);
    padding: var(--t-2) var(--t-4);
    border-top: 1px solid var(--keret);
    font-size: var(--betu-ui);
    color: var(--szoveg-masodlagos);
  }

  .betoltes {
    margin: var(--t-4);
    color: var(--szoveg-halvany);
  }

  .betoltes.hiba {
    color: var(--hiba);
  }
</style>
