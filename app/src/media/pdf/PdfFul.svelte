<!--
  PDF-olvasó fülben (C16): a pdf.js nézője (virtualizált lapok, szövegréteg, keresés), saját eszköztárral és
  oldalbélyegekkel. A `[[x.pdf#page=N]]` a pontos lapon nyit (a fül `nezet.horgony`-a), a tartós állapot (lap,
  nagyítás, bélyegsáv) a fül `nezet`-jében. Kiemelés: a kijelölt szöveg a PDF melletti kiemelés-fájlba kerül (a
  core írja), és idézetként `Source`-horgonnyal az aktív jegyzetbe. A lapok papírfehérek mindkét témában.
-->
<script lang="ts">
  import type { PDFDocumentProxy } from 'pdfjs-dist';
  import type { EventBus, PDFViewer } from 'pdfjs-dist/web/pdf_viewer.mjs';
  import { onMount, untrack } from 'svelte';
  import type { NezetProps } from '../../lib/elrendezes/nezetek.svelte';
  import { ertesitesek } from '../../lib/ertesites/ertesites.svelte';
  import { t } from '../../lib/i18n';
  import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp, Highlighter, PanelLeft, Search, X, ZoomIn, ZoomOut } from '../../lib/ikon/ikonok';
  import { kornyezet } from '../../lib/kornyezet';
  import IkonGomb from '../../lib/ui/IkonGomb.svelte';
  import JegyzetIkon from '../../lib/ui/JegyzetIkon.svelte';
  import { fajlNev, mappa } from '../../lib/vault/fajlok.svelte';
  import { linkek } from '../../lib/vault/linkek.svelte';
  import { mediaHorgony } from '../../szerkeszto/linkek/adat';
  import { mediaNezetek, type MediaParancs, type MediaPeldany } from '../aktiv.svelte';
  import { blokkHely, celSzerkeszto, idezetBeszur } from '../beszuras';
  import { fmBlokk } from '../../szerkeszto/tulajdonsagok/fm';
  import Belyegek from './Belyegek.svelte';
  import { nyit, type PdfHivatkozas } from './dokumentum';
  import { kiemelesApi, retegRajzol, type Kiemeles, type KiemelesLista } from './kiemelesek';
  import { kijelolesOlvas, type Kijeloles } from './kijeloles';
  import { MagyarL10n } from './magyarL10n';
  import { pdfjs } from './pdfjs';

  let { ful, aktiv }: NezetProps = $props();
  const { felulet, kapcsolat } = kornyezet();
  const ut = untrack(() => ful.ut ?? '');

  const kezdo = untrack(() => {
    const n = ful.nezet ?? {};
    const h = typeof n.horgony === 'string' ? mediaHorgony(n.horgony).page : undefined;
    return {
      oldal: h ?? (typeof n.oldal === 'number' ? n.oldal : 1),
      nagyitas: typeof n.nagyitas === 'string' ? n.nagyitas : 'page-width',
      sav: n.sav === true,
    };
  });

  let doboz = $state<HTMLElement | null>(null);
  let kont = $state<HTMLDivElement | null>(null);
  let lapok = $state<HTMLDivElement | null>(null);
  let keresoMezo = $state<HTMLInputElement | null>(null);
  let oldalMezo = $state<HTMLInputElement | null>(null);

  let dok = $state.raw<PDFDocumentProxy | null>(null);
  let hiba = $state<string | null>(null);
  let oldal = $state(kezdo.oldal);
  let oldalSzoveg = $state(String(kezdo.oldal));
  let skala = $state(1);
  let nagyitas = $state(kezdo.nagyitas);
  let sav = $state(kezdo.sav);
  let kereso = $state(false);
  let keres = $state('');
  let talalat = $state<{ aktualis: number; osszes: number; nincs: boolean }>({ aktualis: 0, osszes: 0, nincs: false });
  let kijeloles = $state.raw<Kijeloles | null>(null);
  let kiemelesek = $state.raw<KiemelesLista | null>(null);
  let menu = $state.raw<{ k: Kiemeles; x: number; y: number } | null>(null);
  let dolgozik = $state(false);

  let viewer: PDFViewer | null = null;
  let busz: EventBus | null = null;

  // ------------------------------------------------------------------ tartós állapot

  let mentesIdozito: ReturnType<typeof setTimeout> | null = null;
  function allapotMent() {
    if (mentesIdozito) clearTimeout(mentesIdozito);
    mentesIdozito = setTimeout(() => {
      mentesIdozito = null;
      const n = { ...(ful.nezet ?? {}) };
      delete n.horgony;
      ful.nezet = { ...n, oldal, nagyitas, sav };
    }, 800);
  }

  // ------------------------------------------------------------------ navigáció és nagyítás

  function ugras(n: number) {
    if (!viewer || !dok) return;
    const cel = Math.max(1, Math.min(dok.numPages, Math.round(n)));
    viewer.currentPageNumber = cel;
    oldal = cel;
    oldalSzoveg = String(cel);
  }

  function nagyit(ertek: string | number) {
    if (!viewer) return;
    if (typeof ertek === 'number') viewer.currentScale = Math.max(0.25, Math.min(6, ertek));
    else viewer.currentScaleValue = ertek;
    nagyitas = viewer.currentScaleValue;
    allapotMent();
  }

  const lepes = (irany: 1 | -1) => nagyit(Math.round((skala * (irany > 0 ? 1.15 : 1 / 1.15)) * 100) / 100);

  // ------------------------------------------------------------------ keresés

  function keresKuld(tipus: '' | 'again', elozo = false) {
    busz?.dispatch('find', {
      source: null,
      type: tipus,
      query: keres,
      caseSensitive: false,
      entireWord: false,
      highlightAll: true,
      findPrevious: elozo,
      matchDiacritics: false,
    });
  }

  let keresIdozito: ReturnType<typeof setTimeout> | null = null;
  function keresGepel() {
    if (keresIdozito) clearTimeout(keresIdozito);
    keresIdozito = setTimeout(() => keresKuld(''), 250);
  }

  function keresoNyit() {
    kereso = true;
    queueMicrotask(() => {
      keresoMezo?.focus();
      keresoMezo?.select();
    });
  }

  function keresoZar() {
    kereso = false;
    keres = '';
    talalat = { aktualis: 0, osszes: 0, nincs: false };
    busz?.dispatch('findbarclose', { source: null });
    kont?.focus();
  }

  // ------------------------------------------------------------------ kiemelések

  function retegek() {
    if (!lapok) return;
    const lista = kiemelesek?.kiemelesek ?? [];
    for (const div of lapok.querySelectorAll<HTMLElement>('.page[data-page-number]')) {
      const n = Number(div.dataset.pageNumber);
      retegRajzol(
        div,
        lista.filter((k) => k.oldal === n),
        (k, el) => {
          const r = el.getBoundingClientRect();
          const d = doboz!.getBoundingClientRect();
          menu = { k, x: r.left - d.left, y: r.bottom - d.top + 4 };
        },
      );
    }
  }

  async function kiemelesekBetolt() {
    try {
      kiemelesek = await kiemelesApi.lista(ut);
      retegek();
    } catch {
      /* a kiemelések nélkül is olvasható */
    }
  }

  function kijelolesFrissit() {
    if (!lapok) return;
    const { k, tobbLap } = kijelolesOlvas(lapok, document.getSelection());
    kijeloles = k;
    if (tobbLap) kijeloles = null;
  }

  function lebegoHely(k: Kijeloles): { x: number; y: number } {
    const d = doboz!.getBoundingClientRect();
    return { x: Math.max(8, Math.min(d.width - 120, k.hely.x - d.left - 48)), y: k.hely.y - d.top + 6 };
  }

  async function kiemel() {
    const sel = document.getSelection();
    const olvasott = lapok ? kijelolesOlvas(lapok, sel) : { k: null, tobbLap: false };
    if (olvasott.tobbLap) {
      ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: t('A kiemelés egy oldalon belül legyen'), szoveg: t('Jelöld ki külön a két oldal részét.') });
      return;
    }
    const k = olvasott.k ?? kijeloles;
    if (!k) {
      await oldalLinkBeszur();
      return;
    }
    if (dolgozik) return;
    dolgozik = true;
    try {
      const uj = await kiemelesApi.hozzaad(ut, k.oldal, k.szoveg, k.teglalapok);
      sel?.removeAllRanges();
      kijeloles = null;
      await kiemelesekBetolt();
      const b = await idezetBeszur(ut, uj.oldal, uj.szoveg);
      ertesitesek.ertesit({
        szint: 'siker',
        cim: b ? t('Kiemelve, idézet: {nev}', { nev: fajlNev(b.ut) }) : t('Kiemelve'),
        szoveg: b?.source ? t('A Source mezőbe: {n}. oldal', { n: uj.oldal }) : `${fajlNev(uj.fajl)} · ` + t('{n}. oldal', { n: uj.oldal }),
        idotartam: 3000,
      });
      if (uj.figyelmeztetes) ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: t('Pillanatkép nélkül mentve'), szoveg: uj.figyelmeztetes });
    } catch (e) {
      ertesitesek.ertesit({ szint: 'hiba', cim: t('A kiemelés nem mentődött'), szoveg: e instanceof Error ? e.message : String(e) });
    } finally {
      dolgozik = false;
    }
  }

  /** Kijelölés nélkül: link az aktuális lapra a jegyzet kurzorához. */
  async function oldalLinkBeszur() {
    const p = celSzerkeszto();
    const v = p?.nezet();
    if (!p || !v) {
      ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: t('Jelölj ki szöveget a PDF-ben'), szoveg: t('A kiemelés idézetként a nyitott jegyzetbe kerül.') });
      return;
    }
    const cel = await linkek.linkCel(ut, p.ut).catch(() => `${fajlNev(ut)}.pdf`);
    const link = `[[${cel}#page=${oldal}]]`;
    const { from, to } = v.state.selection.main;
    const fm = fmBlokk(v.state.doc);
    if (fm && from < fm.ig) {
      const b = blokkHely(v.state.doc.toString(), fm.ig, link, fm.ig);
      v.dispatch({ changes: b, userEvent: 'input.paste', scrollIntoView: true });
    } else v.dispatch({ changes: { from, to, insert: link }, selection: { anchor: from + link.length }, userEvent: 'input.paste', scrollIntoView: true });
    ertesitesek.ertesit({ szint: 'siker', cim: t('Link a {n}. oldalra', { n: oldal }), szoveg: fajlNev(p.ut), idotartam: 2000 });
  }

  async function menuIdezet() {
    const m = menu;
    menu = null;
    if (!m) return;
    const b = await idezetBeszur(ut, m.k.oldal, m.k.szoveg);
    if (b) ertesitesek.ertesit({ szint: 'siker', cim: t('Idézet: {nev}', { nev: fajlNev(b.ut) }), idotartam: 2000 });
  }

  function menuMegnyit(e: MouseEvent) {
    const f = kiemelesek?.fajl;
    menu = null;
    if (f) felulet.munkaterulet.megnyit(f, e.metaKey || e.ctrlKey ? 'ujful' : 'osztas');
  }

  async function menuTorol() {
    const m = menu;
    menu = null;
    if (!m) return;
    try {
      await kiemelesApi.torol(ut, m.k.id, kiemelesek?.hash ?? null);
      await kiemelesekBetolt();
      ertesitesek.ertesit({ szint: 'info', cim: t('Kiemelés törölve'), szoveg: t('A pillanatképből visszavonható.'), idotartam: 2500 });
    } catch (e) {
      ertesitesek.ertesit({ szint: 'hiba', cim: t('A kiemelés nem törölhető'), szoveg: e instanceof Error ? e.message : String(e) });
    }
  }

  // ------------------------------------------------------------------ parancsok

  function parancs(p: MediaParancs) {
    switch (p) {
      case 'beszur':
        return void kiemel();
      case 'kereses':
        return keresoNyit();
      case 'kov-oldal':
        return ugras(oldal + 1);
      case 'elozo-oldal':
        return ugras(oldal - 1);
      case 'ugras':
        oldalMezo?.focus();
        return oldalMezo?.select();
      case 'belyegek':
        sav = !sav;
        return allapotMent();
      case 'nagyit':
        return lepes(1);
      case 'kicsinyit':
        return lepes(-1);
      case 'oldalszelesseg':
        return nagyit('page-width');
      case 'egesz-oldal':
        return nagyit('page-fit');
    }
  }

  const peldany: MediaPeldany = { ut, tipus: 'pdf', parancs };

  $effect(() => {
    if (aktiv) mediaNezetek.beallit(peldany);
    else mediaNezetek.elenged(peldany);
  });

  // a már nyitott fülre érkező új horgony (link a jegyzetből)
  $effect(() => {
    const h = ful.nezet?.horgony;
    if (typeof h !== 'string' || !dok) return;
    untrack(() => {
      const p = mediaHorgony(h).page;
      if (p) ugras(p);
      const n = { ...(ful.nezet ?? {}) };
      delete n.horgony;
      ful.nezet = n;
    });
  });

  // ⌘F, ⌘+/−/0 a fülben (a szerkesztő ⌘F-je csak akkor fut, ha szerkesztő az aktív)
  function ablakBillentyu(e: KeyboardEvent) {
    if (!aktiv || e.defaultPrevented || !(e.metaKey || e.ctrlKey) || e.altKey) return;
    const k = e.key;
    if (k === 'f' || k === 'F') {
      e.preventDefault();
      keresoNyit();
    } else if (k === '+' || k === '=') {
      e.preventDefault();
      lepes(1);
    } else if (k === '-') {
      e.preventDefault();
      lepes(-1);
    } else if (k === '0') {
      e.preventDefault();
      nagyit('page-width');
    }
  }

  // trackpad-csípés: a WKWebView `gesture*` eseményei, máshol a ⌃/⌘-görgő
  let csipesKezd = 1;
  function gesztusKezd(e: Event) {
    e.preventDefault();
    csipesKezd = skala;
  }
  let csipesKocka = 0;
  function gesztus(e: Event) {
    e.preventDefault();
    const s = (e as Event & { scale: number }).scale;
    cancelAnimationFrame(csipesKocka);
    csipesKocka = requestAnimationFrame(() => nagyit(Math.round(csipesKezd * s * 100) / 100));
  }
  function gorgo(e: WheelEvent) {
    if (!(e.ctrlKey || e.metaKey)) return;
    e.preventDefault();
    cancelAnimationFrame(csipesKocka);
    const f = Math.exp(-e.deltaY / 200);
    csipesKocka = requestAnimationFrame(() => nagyit(Math.round(skala * f * 100) / 100));
  }

  function lapBillentyu(e: KeyboardEvent) {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if ((e.target as HTMLElement).closest('input')) return;
    if (e.key === 'Escape' && menu) {
      menu = null;
      e.preventDefault();
    } else if (e.key === 'PageDown' && e.shiftKey) {
      e.preventDefault();
      ugras(oldal + 1);
    } else if (e.key === 'PageUp' && e.shiftKey) {
      e.preventDefault();
      ugras(oldal - 1);
    }
  }

  // ------------------------------------------------------------------ életciklus

  onMount(() => {
    let el = true;
    mediaNezetek.bejegyez(peldany);
    let hiv: PdfHivatkozas | null = null;
    const le: (() => void)[] = [];
    (async () => {
      const { lib, viewer: V } = await pdfjs();
      hiv = await nyit(ut);
      if (!el) return hiv.elenged();
      if (!kont || !lapok) return;
      const eb = new V.EventBus();
      // magyar akadálymentes címkék (C32b): a GenericL10n angol tartaléka helyett; a viewer a gyökeret nem maga fordítja, ha kap l10n-t
      const l10n = new MagyarL10n();
      void l10n.translate(kont);
      le.push(() => void l10n.destroy());
      const linkSzolg = new V.PDFLinkService({ eventBus: eb });
      linkSzolg.externalLinkEnabled = false; // a PDF külső linkje ne vigye el az app ablakát
      const kc = new V.PDFFindController({ eventBus: eb, linkService: linkSzolg });
      const v = new V.PDFViewer({
        container: kont,
        viewer: lapok,
        eventBus: eb,
        linkService: linkSzolg,
        findController: kc,
        l10n: l10n as unknown as NonNullable<ConstructorParameters<typeof V.PDFViewer>[0]['l10n']>,
        removePageBorders: true,
        textLayerMode: 1,
        annotationMode: lib.AnnotationMode.ENABLE,
        annotationEditorMode: lib.AnnotationEditorType.DISABLE,
      });
      linkSzolg.setViewer(v);
      viewer = v;
      busz = eb;
      eb.on('pagesinit', () => {
        nagyit(kezdo.nagyitas);
        ugras(kezdo.oldal);
        const n = { ...(ful.nezet ?? {}) };
        if ('horgony' in n) {
          delete n.horgony;
          ful.nezet = n;
        }
      });
      eb.on('pagechanging', (e: { pageNumber: number }) => {
        oldal = e.pageNumber;
        if (document.activeElement !== oldalMezo) oldalSzoveg = String(e.pageNumber);
        allapotMent();
      });
      eb.on('scalechanging', (e: { scale: number; presetValue?: string }) => {
        skala = e.scale;
      });
      eb.on('pagerendered', () => retegek());
      eb.on('updatefindmatchescount', (e: { matchesCount: { current: number; total: number } }) => {
        talalat = { aktualis: e.matchesCount.current, osszes: e.matchesCount.total, nincs: talalat.nincs };
      });
      eb.on('updatefindcontrolstate', (e: { state: number; matchesCount: { current: number; total: number } }) => {
        talalat = { aktualis: e.matchesCount.current, osszes: e.matchesCount.total, nincs: e.state === 1 };
      });
      linkSzolg.setDocument(hiv.dok);
      v.setDocument(hiv.dok);
      dok = hiv.dok;
      void kiemelesekBetolt();
    })().catch((e: Error & { name?: string }) => {
      if (!el) return;
      hiba =
        e?.name === 'PasswordException'
          ? t('A PDF jelszóval védett; a Manifold nem nyitja meg.')
          : e?.name === 'InvalidPDFException'
            ? t('A fájl nem érvényes vagy sérült PDF.')
            : t('A PDF nem tölthető be: {hiba}', { hiba: String(e?.message ?? e) });
    });

    const valtozas = (utak: string[]) => {
      const f = kiemelesek?.fajl ?? null;
      if (f && utak.includes(f)) void kiemelesekBetolt();
    };
    le.push(
      kapcsolat.figyel('vault_iras', (e) => valtozas([String(e.ut ?? '')])),
      kapcsolat.figyel('vault_valtozas', (e) => valtozas([...((e.kulso as string[]) ?? [])])),
    );
    let kijelIdozito: ReturnType<typeof setTimeout> | null = null;
    const kijel = () => {
      if (kijelIdozito) clearTimeout(kijelIdozito);
      kijelIdozito = setTimeout(kijelolesFrissit, 120);
    };
    document.addEventListener('selectionchange', kijel);
    window.addEventListener('keydown', ablakBillentyu);
    le.push(() => document.removeEventListener('selectionchange', kijel), () => window.removeEventListener('keydown', ablakBillentyu));

    return () => {
      el = false;
      le.forEach((f) => f());
      if (mentesIdozito) {
        clearTimeout(mentesIdozito);
        const n = { ...(ful.nezet ?? {}) };
        delete n.horgony;
        ful.nezet = { ...n, oldal, nagyitas, sav };
      }
      if (keresIdozito) clearTimeout(keresIdozito);
      cancelAnimationFrame(csipesKocka);
      viewer?.setDocument(null as unknown as PDFDocumentProxy);
      viewer?.cleanup();
      viewer = null;
      hiv?.elenged();
      mediaNezetek.megszunt(peldany);
    };
  });

  $effect(() => {
    if (!kont) return;
    const k = kont;
    k.addEventListener('gesturestart', gesztusKezd);
    k.addEventListener('gesturechange', gesztus);
    k.addEventListener('wheel', gorgo, { passive: false });
    // a pdf.js nézője átméretezéskor nem számolja újra az „Oldalszélesség” / „Egész oldal” nagyítást
    let szel = k.clientWidth;
    let mag = k.clientHeight;
    let kocka = 0;
    const meret = new ResizeObserver(() => {
      if (Math.abs(k.clientWidth - szel) < 2 && Math.abs(k.clientHeight - mag) < 2) return;
      szel = k.clientWidth;
      mag = k.clientHeight;
      cancelAnimationFrame(kocka);
      kocka = requestAnimationFrame(() => {
        if (viewer && (nagyitas === 'page-width' || nagyitas === 'page-fit' || nagyitas === 'auto')) viewer.currentScaleValue = nagyitas;
      });
    });
    meret.observe(k);
    return () => {
      meret.disconnect();
      cancelAnimationFrame(kocka);
      k.removeEventListener('gesturestart', gesztusKezd);
      k.removeEventListener('gesturechange', gesztus);
      k.removeEventListener('wheel', gorgo);
    };
  });

  const szazalek = $derived(`${Math.round(skala * 100)}%`);
</script>

<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<article class="pdf-ful" bind:this={doboz} onkeydown={lapBillentyu} aria-label={t('PDF: {nev}', { nev: fajlNev(ut) })}>
  <header class="eszkoztar">
    <IkonGomb ikon={PanelLeft} cimke={t('Oldalbélyegek')} lenyomva={sav} onclick={() => parancs('belyegek')} />
    <p class="morzsa" title={ut}>
      <span class="morzsa-ikon"><JegyzetIkon {ut} tipus="pdf" meret={14} /></span>
      {#if mappa(ut)}<span class="mappa">{`${mappa(ut).replaceAll('/', ' / ')} / `}</span>{/if}<span class="nev">{fajlNev(ut)}</span>
    </p>
    <div class="csoport" role="group" aria-label={t('Lapozás')}>
      <IkonGomb ikon={ChevronLeft} cimke={t('Előző oldal')} disabled={!dok || oldal <= 1} onclick={() => ugras(oldal - 1)} />
      <label class="oldal">
        <span class="rejtett">Oldal</span>
        <input
          bind:this={oldalMezo}
          type="text"
          inputmode="numeric"
          size="4"
          value={oldalSzoveg}
          disabled={!dok}
          oninput={(e) => (oldalSzoveg = e.currentTarget.value)}
          onkeydown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              const n = parseInt(oldalSzoveg, 10);
              if (Number.isFinite(n)) ugras(n);
              else oldalSzoveg = String(oldal);
              kont?.focus();
            } else if (e.key === 'Escape') {
              oldalSzoveg = String(oldal);
              kont?.focus();
            }
          }}
          onblur={() => (oldalSzoveg = String(oldal))}
        />
        <span class="osszes">/ {dok?.numPages ?? '–'}</span>
      </label>
      <IkonGomb ikon={ChevronRight} cimke={t('Következő oldal')} disabled={!dok || oldal >= (dok?.numPages ?? 1)} onclick={() => ugras(oldal + 1)} />
    </div>
    <div class="csoport" role="group" aria-label={t('Nagyítás')}>
      <IkonGomb ikon={ZoomOut} cimke={t('Kicsinyítés')} billentyu="Mod+-" disabled={!dok} onclick={() => lepes(-1)} />
      <select
        class="nagyitas"
        aria-label={t('Nagyítás')}
        disabled={!dok}
        value={nagyitas === 'page-width' || nagyitas === 'page-fit' ? nagyitas : 'egyeni'}
        onchange={(e) => nagyit(e.currentTarget.value === 'egyeni' ? skala : e.currentTarget.value)}
      >
        <option value="page-width">{t('Oldalszélesség')}</option>
        <option value="page-fit">{t('Egész oldal')}</option>
        <option value="egyeni">{szazalek}</option>
      </select>
      <IkonGomb ikon={ZoomIn} cimke={t('Nagyítás|gomb')} billentyu="Mod+=" disabled={!dok} onclick={() => lepes(1)} />
    </div>
    <IkonGomb ikon={Search} cimke={t('Keresés a PDF-ben')} billentyu="Mod+F" lenyomva={kereso} disabled={!dok} onclick={() => (kereso ? keresoZar() : keresoNyit())} />
    <IkonGomb ikon={Highlighter} cimke={t('Kiemelés és idézet a jegyzetbe')} billentyu="Mod+Shift+I" disabled={!dok || dolgozik} onclick={() => void kiemel()} />
  </header>

  {#if kereso}
    <div class="keresosav" role="search">
      <input
        bind:this={keresoMezo}
        type="search"
        placeholder={t('Keresés a PDF-ben')}
        aria-label={t('Keresés a PDF-ben')}
        bind:value={keres}
        oninput={keresGepel}
        onkeydown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            keresKuld('again', e.shiftKey);
          } else if (e.key === 'Escape') {
            e.preventDefault();
            keresoZar();
          }
        }}
      />
      <span class="talalat" role="status">
        {#if keres && talalat.nincs}{t('Nincs találat')}{:else if talalat.osszes}{talalat.aktualis} / {talalat.osszes}{/if}
      </span>
      <IkonGomb ikon={ChevronUp} cimke={t('Előző találat')} billentyu="Shift+Enter" disabled={!talalat.osszes} onclick={() => keresKuld('again', true)} />
      <IkonGomb ikon={ChevronDown} cimke={t('Következő találat')} billentyu="Enter" disabled={!talalat.osszes} onclick={() => keresKuld('again')} />
      <IkonGomb ikon={X} cimke={t('Keresés bezárása')} billentyu="Escape" onclick={keresoZar} />
    </div>
  {/if}

  <div class="test" class:sav>
    {#if sav && dok}
      <Belyegek {dok} {oldal} onvalaszt={ugras} />
    {/if}
    <div class="lapterulet">
      <!-- a pdf.js nézője abszolút pozíciójú tárolót kér -->
      <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
      <div class="lapkont" bind:this={kont} tabindex="0" role="document" aria-label="Lapok">
        <div class="pdfViewer" bind:this={lapok}></div>
      </div>
      {#if !dok && !hiba}<p class="allapot">{t('A PDF betöltése…')}</p>{/if}
      {#if hiba}<p class="allapot hiba" role="alert">{hiba}</p>{/if}
    </div>
  </div>

  {#if kijeloles && !menu}
    {@const h = lebegoHely(kijeloles)}
    <button
      type="button"
      class="m-gomb lebego"
      style:left="{h.x}px"
      style:top="{h.y}px"
      disabled={dolgozik}
      onmousedown={(e) => e.preventDefault()}
      onclick={() => void kiemel()}
      title={t('A kijelölés kiemelése; idézetként a jegyzetbe (⇧⌘I)')}
    >
      {t('Kiemelés')}
    </button>
  {/if}

  {#if menu}
    <div class="menu" role="menu" style:left="{menu.x}px" style:top="{menu.y}px" aria-label={t('Kiemelés')}>
      <button type="button" role="menuitem" onclick={() => void menuIdezet()}>{t('Idézet beszúrása a jegyzetbe')}</button>
      <button type="button" role="menuitem" onclick={menuMegnyit}>{t('Megnyitás a kiemelés-jegyzetben')}</button>
      <button type="button" role="menuitem" class="veszelyes" onclick={() => void menuTorol()}>{t('Kiemelés törlése')}</button>
    </div>
  {/if}
</article>

<svelte:window
  onpointerdown={(e) => {
    if (menu && !(e.target as HTMLElement).closest('.menu, .mf-kiemeles')) menu = null;
  }}
/>

<style>
  .pdf-ful {
    position: relative;
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    background: var(--hatter);
  }

  .eszkoztar {
    flex: none;
    display: flex;
    align-items: center;
    gap: var(--t-1);
    height: var(--magassag-fejlec);
    padding: 0 var(--t-2);
    border-bottom: 1px solid var(--keret);
  }

  .morzsa {
    flex: 1 1 auto;
    min-width: 0;
    margin: 0 var(--t-2);
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

  .csoport {
    flex: none;
    display: flex;
    align-items: center;
    gap: 2px;
  }

  .oldal {
    display: flex;
    align-items: center;
    gap: var(--t-1);
    font-size: var(--betu-ui);
    color: var(--szoveg-halvany);
    font-variant-numeric: tabular-nums;
  }

  .oldal input {
    width: var(--magassag-mezo);
    height: var(--magassag-suru);
    padding: 0 var(--t-1);
    border: 1px solid var(--keret-mezo);
    border-radius: var(--kerekites-kicsi);
    background: var(--hatter);
    color: var(--szoveg);
    font: inherit;
    text-align: right;
  }

  .nagyitas {
    height: var(--magassag-gomb);
    border: none;
    border-radius: var(--kerekites);
    background: none;
    color: var(--szoveg-masodlagos);
    font: inherit;
    font-size: var(--betu-ui);
    font-variant-numeric: tabular-nums;
  }

  .nagyitas:hover {
    background: var(--hatter-hover);
  }

  .rejtett {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
  }

  .keresosav {
    flex: none;
    display: flex;
    align-items: center;
    gap: var(--t-1);
    height: var(--magassag-fejlec);
    padding: 0 var(--t-2) 0 var(--t-3);
    border-bottom: 1px solid var(--keret);
    background: var(--hatter-oldalsav);
  }

  .keresosav input {
    flex: 0 1 320px;
    height: var(--magassag-gomb);
    padding: 0 var(--t-2);
    border: 1px solid var(--keret-mezo);
    border-radius: var(--kerekites);
    background: var(--hatter);
    color: var(--szoveg);
    font: inherit;
    font-size: var(--betu-ui);
  }

  .talalat {
    min-width: 88px;
    font-size: var(--betu-ui);
    color: var(--szoveg-halvany);
    font-variant-numeric: tabular-nums;
  }

  .test {
    flex: 1 1 auto;
    min-height: 0;
    display: grid;
    grid-template-columns: minmax(0, 1fr);
  }

  .test.sav {
    grid-template-columns: 160px minmax(0, 1fr);
  }

  .lapterulet {
    position: relative;
    min-width: 0;
    min-height: 0;
    background: var(--pdf-hatter);
  }

  .lapkont {
    position: absolute;
    inset: 0;
    overflow: auto;
    outline: none;
  }

  .lapkont:focus-visible {
    outline: var(--fokusz-vastag) solid var(--fokusz-gyuru);
    outline-offset: var(--fokusz-tav-befele);
  }

  /* a pdf.js lapjai: köz a lapok között, papírfehér lap, enyhe árnyék */
  .lapkont :global(.pdfViewer) {
    padding: var(--t-4) 0;
  }

  .lapkont :global(.pdfViewer .page) {
    margin: 0 auto var(--t-4);
    background: var(--pdf-lap);
    box-shadow: var(--arnyek-pdf-lap);
  }

  .lapkont :global(.mf-kiemeles-reteg) {
    position: absolute;
    inset: 0;
    z-index: 3;
    pointer-events: none;
    mix-blend-mode: multiply;
  }

  .lapkont :global(.mf-kiemeles) {
    position: absolute;
    display: block;
    padding: 0;
    border: none;
    border-radius: var(--kerekites-jel);
    background: var(--pdf-kiemeles);
    pointer-events: auto;
    cursor: pointer;
  }

  .lapkont :global(.mf-kiemeles:hover),
  .lapkont :global(.mf-kiemeles:focus-visible) {
    background: var(--pdf-kiemeles-aktiv);
    outline: none;
  }

  .allapot {
    position: absolute;
    top: var(--t-6);
    left: 50%;
    transform: translateX(-50%);
    margin: 0;
    padding: var(--t-2) var(--t-3);
    border-radius: var(--kerekites);
    background: var(--hatter-emelt);
    box-shadow: var(--arnyek-atfedes);
    color: var(--szoveg-masodlagos);
    font-size: var(--betu-ui);
  }

  .allapot.hiba {
    background: var(--hiba-hatter);
    color: var(--hiba);
  }

  .lebego {
    position: absolute;
    z-index: 5;
    /* lebegő gomb: a kitöltött gomb határa és a lebegő réteg árnyéka együtt */
    box-shadow:
      inset 0 0 0 var(--keret-vastag) var(--akcent-kitoltes-keret),
      var(--arnyek-atfedes);
  }

  .menu {
    position: absolute;
    z-index: 6;
    display: flex;
    flex-direction: column;
    min-width: 240px;
    padding: var(--t-1);
    border-radius: var(--kerekites-nagy);
    background: var(--hatter-emelt);
    box-shadow: var(--arnyek-atfedes);
  }

  .menu button {
    height: var(--magassag-lista-sor);
    padding: 0 var(--t-3);
    border: none;
    border-radius: var(--kerekites);
    background: none;
    color: var(--szoveg);
    font: inherit;
    font-size: var(--betu-ui);
    text-align: left;
    cursor: pointer;
  }

  .menu button:hover,
  .menu button:focus-visible {
    background: var(--hatter-hover);
    outline: none;
  }

  .menu .veszelyes {
    color: var(--hiba);
  }
</style>
