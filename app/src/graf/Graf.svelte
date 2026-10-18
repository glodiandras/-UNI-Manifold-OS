<!--
  A gráfnézet (C13): globális és helyi gráf (1–3 lépés; a helyi gráf a jegyzet mellett nyílhat és — kapcsolóval — az aktív
  jegyzetet követi), szűrők (címkék és feloldatlan célok csúcsként), színcsoportok, erők, megjelenítés-csúszkák, keresés
  repüléssel, kattintás = megnyitás, jobb gomb = a csúcs menüje. A csúcs- és élhalmaz a core gráfja (`/api/vault/graf`); a felület nem old fel linket. A rajzolás Canvas 2D
  (lib/graf/rajzolo.ts), a fizika Web Workerben fut (lib/graf/fizika.ts); nyugalomban sem a rajzolás, sem a fizika nem
  ütemez semmit, így a nézet CPU-használata nulla.
-->
<script lang="ts">
  import { t, tp } from '../lib/i18n';
  import { onMount, tick, untrack } from 'svelte';
  import { Maximize, Network, Pin, SlidersHorizontal, TriangleAlert } from '../lib/ikon/ikonok';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { fizikaBeallitas, effektiv } from '../lib/graf/beallitasok';
  import type { Be, Ki } from '../lib/graf/fizikaMotor';
  import { FizikaGazda } from '../lib/graf/fizikaGazda';
  import { kezdoAllas, pozicioFrissites } from '../lib/graf/kezdoallas';
  import { GrafAdat, MAX_MELYSEG, kereses, lathatoElDb, lathatosag, szinCsoportok } from '../lib/graf/modell';
  import { GrafRajzolo, type MegnyitasMod, type Szinek } from '../lib/graf/rajzolo';
  import { csucsMenu, type CsucsMenuKontextus } from './csucsMenu';
  import { celPanelAzon, fajlMegnyitPanelben } from './panelek';
  import type { NezetProps } from '../lib/elrendezes/nezetek.svelte';
  import { kornyezet } from '../lib/kornyezet';
  import IkonGomb from '../lib/ui/IkonGomb.svelte';
  import { fajlNev } from '../lib/vault/fajlok.svelte';
  import { grafAdat } from '../lib/vault/graf.svelte';
  import { grafMemoria } from './memoria';
  import GrafVezerlo from './GrafVezerlo.svelte';

  let { ful }: NezetProps = $props();
  const { felulet, fajlok } = kornyezet();
  let menuBezar: ((fokusz?: boolean) => void) | null = null;

  let vaszon: HTMLCanvasElement | undefined = $state();
  let proba: HTMLElement | undefined = $state();
  let rajzolo = $state.raw<GrafRajzolo | null>(null);
  let gazda: FizikaGazda | null = null;
  let lathatoLap = $state(typeof document === 'undefined' || document.visibilityState !== 'hidden');
  let tooltip = $state<{ i: number; x: number; y: number } | null>(null);
  let kijelolt = $state(-1);

  // ------------------------------------------------------------------ állapot

  const adat = $derived(grafAdat.adat);
  const eff = $derived(effektiv(grafAdat.json, felulet.graf));
  const mod = $derived<'globalis' | 'helyi'>(ful.nezet?.mod === 'helyi' ? 'helyi' : 'globalis');
  const kozeppontUt = $derived(typeof ful.nezet?.kozeppont === 'string' ? ful.nezet.kozeppont : null);
  const melyseg = $derived(Math.min(MAX_MELYSEG, Math.max(1, Math.round(Number(ful.nezet?.melyseg) || 1))));
  const panelNyitva = $derived(ful.nezet?.panel === true);
  /** A helyi gráf az aktív jegyzetet követi (11-graph-01): a kapcsoló a nézet tartós állapota; hiányában a középpont rögzített. */
  const kovet = $derived(ful.nezet?.kovet === true);
  const aktivJegyzetUt = $derived(felulet.munkaterulet.aktivFul?.ut ?? null);
  const szuroBe = $derived({ lekerdezes: eff.lekerdezes, mellekletek: eff.mellekletek, arvak: eff.arvak, cimkek: eff.cimkek, letezoCsak: eff.letezoCsak });
  const kozeppont = $derived(adat && kozeppontUt ? adat.csucsIndex(kozeppontUt) : -1);
  const helyi = $derived(adat && mod === 'helyi' && kozeppont >= 0 ? { kozeppont, melyseg } : null);
  const szuro = $derived(adat ? lathatosag(adat, szuroBe, helyi) : null);
  const szin = $derived(adat ? szinCsoportok(adat, eff.szincsoportok) : null);
  const lathatoEl = $derived(adat && szuro ? lathatoElDb(adat, szuro.lathato) : 0);

  function nezetAllapot(valtozas: Record<string, unknown>) {
    ful.nezet = { ...(ful.nezet ?? {}), ...valtozas };
  }

  /** A helyi gráf középpontja: a megadott, a kijelölt csúcs, vagy a legutóbb megnyitott fájl, ami a gráfban van. */
  function kozeppontValaszt(): string | null {
    if (!adat) return null;
    if (kozeppontUt && adat.csucsIndex(kozeppontUt) >= 0) return kozeppontUt;
    if (kijelolt >= 0) return adat.ut[kijelolt];
    return felulet.legutobbiFajlok.find((u) => adat.csucsIndex(u) >= 0) ?? null;
  }

  function modValt(uj: 'globalis' | 'helyi') {
    if (uj === mod) return;
    if (uj === 'helyi') {
      const k = kozeppontValaszt();
      if (k === null) return;
      nezetAllapot({ mod: 'helyi', kozeppont: k, melyseg });
    } else nezetAllapot({ mod: 'globalis' });
    ujIllesztes();
  }

  // ------------------------------------------------------------------ rajzoló és fizika

  let illesztesKell = true;
  let fizikaAlairas = '';
  let utolsoMaszk: Uint8Array | null = null;
  let utolsoErok = '';
  let utolsoPoz: Float32Array | null = null;
  let utolsoAdat: GrafAdat | null = null;

  function szinekOlvas(): Szinek | null {
    if (!proba) return null;
    const c = (nev: string) => getComputedStyle(proba!.querySelector<HTMLElement>(`.p-${nev}`)!).color;
    return {
      jegyzet: c('jegyzet'),
      canvas: c('canvas'),
      melleklet: c('melleklet'),
      el: c('el'),
      elKiemelt: c('el-kiemelt'),
      kijelolt: c('kijelolt'),
      felulet: c('felulet'),
      szoveg: c('szoveg'),
      halo: c('felulet'),
      talalat: c('talalat'),
      cimke: c('cimke'),
      feloldatlan: c('feloldatlan'),
    };
  }

  function szinFrissit() {
    const s = szinekOlvas();
    if (s && rajzolo && vaszon) rajzolo.szinBeallit(s, `11px ${getComputedStyle(vaszon).fontFamily}`);
  }

  function mentPoz() {
    // csak a globális elrendezés marad meg: a helyi gráf összehúzott helyzetei nem írják felül
    if (mod === 'globalis' && utolsoPoz && utolsoAdat) grafMemoria.poz = { alairas: utolsoAdat.alairas, ut: utolsoAdat.ut, poz: utolsoPoz.slice() };
  }

  function fogad(m: Ki) {
    const r = rajzolo;
    if (!r) return;
    if (m.tipus === 'kesz') {
      // az előmelegítés után az első kép már a teljes gráf
      if (!r.nezetModositva) r.teljesNezet(false);
      return;
    }
    r.pozBe(m.poz, m.fut);
    utolsoPoz = m.poz;
    if (!m.fut) {
      mentPoz();
      // lehűlés után sima illesztés, ha a felhasználó közben nem mozgatta a nézetet
      if (illesztesKell && !r.nezetModositva) r.teljesNezet(true);
      illesztesKell = false;
    }
  }

  /** A következő nyugalomnál a nézet újra a látható csúcsokra illeszkedik (mód- és szűrőváltáskor). */
  function ujIllesztes() {
    illesztesKell = true;
    if (rajzolo) rajzolo.nezetModositva = false;
  }

  function fizikaInit(a: GrafAdat, r: GrafRajzolo, maszk: Uint8Array) {
    gazda?.leallit();
    // a Worker hibájakor a gazda maga vált a fő szálra és küldi újra az utolsó initet (T068): itt nincs újraindítás
    gazda = new FizikaGazda(fogad);
    const csokkentett = matchMedia('(prefers-reduced-motion: reduce)').matches;
    const mentett = grafMemoria.poz;
    let poz: Float32Array;
    let alpha = 1;
    let elore = csokkentett ? 600 : 110;
    if (mentett && mentett.alairas === a.alairas && mentett.poz.length === 2 * a.n) {
      // ugyanaz a szerkezet: a nézet-váltás előtti elrendezés, nyugalomban (nem számol)
      poz = mentett.poz.slice();
      alpha = 0;
      elore = 0;
    } else if (mentett && mentett.ut.length) {
      const regi = new Map<string, [number, number]>();
      mentett.ut.forEach((u, i) => regi.set(u, [mentett.poz[2 * i], mentett.poz[2 * i + 1]]));
      const f = pozicioFrissites(a, regi);
      poz = f.poz;
      alpha = f.uj ? 0.6 : 0.3;
      elore = 0;
    } else {
      poz = kezdoAllas(a);
    }
    utolsoAdat = a;
    utolsoMaszk = maszk.slice();
    utolsoErok = JSON.stringify(fizikaBeallitas(eff));
    r.pozBe(poz.slice(), alpha > 0);
    const uzenet: Be = {
      tipus: 'init',
      n: a.n,
      elek: a.elek.slice().buffer,
      poz: poz.buffer as ArrayBuffer,
      beall: fizikaBeallitas(eff),
      alpha,
      aktiv: maszk.slice().buffer,
      elore,
      elore_ms: csokkentett ? 2500 : 450,
    };
    illesztesKell = true;
    gazda.kuld(uzenet);
    if (!lathatoLap) gazda.kuld({ tipus: 'szunet' });
    if (alpha === 0 && mod === 'globalis') {
      const v = grafMemoria.nezet;
      if (v) {
        illesztesKell = false;
        r.nezetBeallit(v.k, v.tx, v.ty);
      }
    }
  }

  // a rajzoló létrehozása a vászonhoz
  $effect(() => {
    const v = vaszon;
    if (!v) return;
    const r = new GrafRajzolo(v, {
      megnyit: (i, m, x, y) => untrack(() => csucsKattintas(i, m, x, y)),
      menu: (i, x, y) => untrack(() => csucsMenuNyit(i, x, y)),
      fizika: (m) => gazda?.kuld(m),
      hover: (i, x, y) => (tooltip = i >= 0 ? { i, x, y } : null),
      kijeloles: (i) => (kijelolt = i),
    });
    rajzolo = r;
    const meretFigyelo = new ResizeObserver(() => r.meretValtozas());
    meretFigyelo.observe(v);
    r.meretValtozas();
    (window as unknown as { __grafMeres?: () => unknown }).__grafMeres = () => ({
      kepek: r.meres.kepek,
      utemezesek: r.meres.utemezesek,
      rajzMs: [...r.meres.rajzMs],
      workerben: gazda?.workerben ?? false,
    });
    return () => {
      if (mod === 'globalis') grafMemoria.nezet = { k: r.k, tx: r.tx, ty: r.ty };
      mentPoz();
      meretFigyelo.disconnect();
      r.leallit();
      gazda?.leallit();
      gazda = null;
      rajzolo = null;
      fizikaAlairas = '';
      delete (window as unknown as { __grafMeres?: unknown }).__grafMeres;
    };
  });

  // a lap láthatósága és a téma
  onMount(() => {
    const lathatosag_ = () => (lathatoLap = document.visibilityState !== 'hidden');
    document.addEventListener('visibilitychange', lathatosag_);
    const tema = matchMedia('(prefers-color-scheme: dark)');
    const szinCsere = () => szinFrissit();
    tema.addEventListener('change', szinCsere);
    const figyelo = new MutationObserver(szinCsere);
    figyelo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-tema'] });
    return () => {
      document.removeEventListener('visibilitychange', lathatosag_);
      tema.removeEventListener('change', szinCsere);
      figyelo.disconnect();
    };
  });

  $effect(() => {
    if (rajzolo && proba) untrack(szinFrissit);
  });

  // az adat betöltése, amíg a nézet látszik
  $effect(() => {
    if (!lathatoLap) return;
    return grafAdat.megjelenik((ut) => fajlok.info(ut)?.tipus);
  });

  // a fájltípusok (fájllista) frissülése
  $effect(() => {
    void fajlok.lista;
    untrack(() => grafAdat.tipusokFrissit());
  });

  // a fizika (újra)indítása, ha a szerkezet változott
  $effect(() => {
    const a = adat;
    const r = rajzolo;
    if (!a || !r) return;
    untrack(() => {
      const sz = szuro;
      const cs = szin;
      if (!sz || !cs) return;
      if (fizikaAlairas === a.alairas && gazda) return;
      fizikaAlairas = a.alairas;
      // a rajzoló bemenete előbb: a vödrök és a tömbök a csúcsszámhoz igazodnak
      r.bemenet({ adat: a, lathato: sz.lathato, csoport: cs.csoport, csoportSzinek: eff.szincsoportok.map((c) => c.szin), nyil: eff.nyilak, meretSzorzo: eff.meretSzorzo, vonalSzorzo: eff.vonalSzorzo, szovegHalvany: eff.szovegHalvany });
      fizikaInit(a, r, sz.lathato);
      if (helyi) r.kijeloles(helyi.kozeppont);
    });
  });

  // a rajzoló bemenete: láthatóság, színek, kapcsolók
  $effect(() => {
    const a = adat;
    const r = rajzolo;
    const sz = szuro;
    const cs = szin;
    if (!a || !r || !sz || !cs) return;
    const nyil = eff.nyilak;
    const ms = eff.meretSzorzo;
    const vs = eff.vonalSzorzo;
    const sh = eff.szovegHalvany;
    const szinek = eff.szincsoportok.map((c) => c.szin);
    untrack(() => {
      r.bemenet({ adat: a, lathato: sz.lathato, csoport: cs.csoport, csoportSzinek: szinek, nyil, meretSzorzo: ms, vonalSzorzo: vs, szovegHalvany: sh });
      // a rejtett csúcsok a fizikában is kiesnek (csak ha a maszk tényleg változott)
      const m = sz.lathato;
      if (utolsoMaszk && utolsoMaszk.length === m.length && (utolsoMaszk as Uint8Array).some((v, i) => v !== m[i])) {
        utolsoMaszk = m.slice();
        gazda?.kuld({ tipus: 'aktiv', maszk: m.slice().buffer, alpha: helyi ? 0.7 : 0.35 });
        ujIllesztes();
      }
    });
  });

  // az erők: csak ha tényleg változtak
  $effect(() => {
    const e = JSON.stringify(fizikaBeallitas(eff));
    untrack(() => {
      if (!gazda || e === utolsoErok) return;
      utolsoErok = e;
      gazda.kuld({ tipus: 'beall', beall: JSON.parse(e) });
    });
  });

  // láthatatlan lapon a számolás és a rajz is áll
  $effect(() => {
    const lat = lathatoLap;
    gazda?.kuld({ tipus: lat ? 'folytat' : 'szunet' });
    rajzolo?.szunet(!lat);
  });

  // a kijelölés kövesse a helyi gráf középpontját
  $effect(() => {
    const k = helyi?.kozeppont ?? -1;
    if (k >= 0 && rajzolo)
      untrack(() => {
        rajzolo!.kijeloles(k);
        kijelolt = k;
      });
  });

  // a helyi gráf kövesse az aktív jegyzetet (11-graph-01): a szomszédos csoport jegyzetének váltására újra középre áll;
  // a nézet-fülek (a gráf maga) nem jegyzetek, a gráfban nem szereplő fájl nem csúcs
  $effect(() => {
    const ut = aktivJegyzetUt;
    const a = adat;
    if (!kovet || mod !== 'helyi' || !a || !ut) return;
    untrack(() => {
      if (ut === kozeppontUt || a.csucsIndex(ut) < 0) return;
      nezetAllapot({ kozeppont: ut });
      ujIllesztes();
    });
  });

  // ------------------------------------------------------------------ csúcs-műveletek (kattintás, menü)

  function fajlMegnyit(ut: string, m: MegnyitasMod) {
    fajlMegnyitPanelben(felulet.munkaterulet, celPanelAzon(felulet.munkaterulet, ful.id, ful.nezet), ut, m);
  }

  function kontextus(): CsucsMenuKontextus {
    return {
      felulet,
      fajlMegnyit,
      helyiGraf: (ut) => {
        nezetAllapot({ mod: 'helyi', kozeppont: ut, melyseg });
        ujIllesztes();
      },
      fokusz: () => vaszon?.focus({ preventScroll: true }),
    };
  }

  /** Kattintás / Enter: fájlnál megnyitás, címkénél keresés, a feloldatlan célnál felajánlott létrehozás. */
  function csucsKattintas(i: number, m: MegnyitasMod, x?: number, y?: number) {
    const a = adat;
    if (!a) return;
    if (!a.virtualis(i)) {
      fajlMegnyit(a.ut[i], m);
      return;
    }
    csucsMenuNyit(i, x ?? 0, y ?? 0, a.tipus[i] === 'cimke');
  }

  function csucsMenuNyit(i: number, x: number, y: number, kozvetlenCimke = false) {
    const a = adat;
    if (!a || !vaszon) return;
    menuBezar?.(false);
    const r = vaszon.getBoundingClientRect();
    menuBezar = csucsMenu(a, i, r.left + x, r.top + y, kontextus(), kozvetlenCimke);
  }

  // ------------------------------------------------------------------ keresés repüléssel

  let keresoSzoveg = $state('');
  let keresoNyitva = $state(false);
  let keresoAktiv = $state(0);
  const talalatok = $derived(adat && keresoSzoveg.trim() ? kereses(adat, keresoSzoveg, szuro?.lathato ?? null, 8) : []);

  $effect(() => {
    rajzolo?.talalatBeallit(keresoNyitva ? talalatok : []);
  });
  $effect(() => {
    void keresoSzoveg;
    keresoAktiv = 0;
  });

  async function ugras(i: number) {
    if (!adat) return;
    const globalis = lathatosag(adat, szuroBe, null).lathato;
    // a szűrő oldása: a keresés a rejtett csúcsot is megtalálja
    if (!globalis[i]) felulet.graf = { ...felulet.graf, lekerdezes: '', mellekletek: true, arvak: true };
    if (mod === 'helyi' && !(szuro && szuro.lathato[i])) nezetAllapot({ mod: 'globalis' });
    keresoNyitva = false;
    await tick();
    rajzolo?.kijeloles(i);
    kijelolt = i;
    rajzolo?.repul(i);
    vaszon?.focus({ preventScroll: true });
  }

  function keresoBillentyu(e: KeyboardEvent) {
    if (e.isComposing) return;
    const n = talalatok.length;
    if (e.key === 'ArrowDown' && n) keresoAktiv = (keresoAktiv + 1) % n;
    else if (e.key === 'ArrowUp' && n) keresoAktiv = (keresoAktiv - 1 + n) % n;
    else if (e.key === 'Enter' && n) void ugras(talalatok[keresoAktiv]);
    else if (e.key === 'Escape') {
      if (keresoSzoveg) keresoSzoveg = '';
      else {
        keresoNyitva = false;
        vaszon?.focus({ preventScroll: true });
      }
    } else return;
    e.preventDefault();
    e.stopPropagation();
  }

  // ------------------------------------------------------------------ nézet-billentyűk

  function nezetBillentyu(e: KeyboardEvent) {
    if ((e.key === '/' || ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'f')) && !e.altKey) {
      e.preventDefault();
      e.stopPropagation();
      document.getElementById('graf-kereso')?.focus();
    }
  }

  const cimke = $derived(
    adat
      ? t('Gráfnézet: {n} fájl és {el} kapcsolat{helyi}. + és − nagyít, nyilak mozgatnak, 0 a teljes nézet, Enter megnyitja a kijelölt jegyzetet.', {
          n: adat.nValos,
          el: adat.iranyitott.length / 2,
          helyi: mod === 'helyi' && kozeppontUt ? t(', helyi gráf: {fajl}, {m} lépés', { fajl: fajlNev(kozeppontUt), m: melyseg }) : '',
        })
      : t('Gráfnézet'),
  );
  const tooltipAdat = $derived(tooltip && adat && tooltip.i < adat.n ? tooltip : null);
</script>

<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<div class="graf" role="group" aria-label={t('Gráf')} onkeydown={nezetBillentyu}>
  <!-- svelte-ignore a11y_no_interactive_element_to_noninteractive_role -->
  <!-- a vászon billentyűzettel kezelhető (nagyítás, mozgatás, megnyitás): `application`, magyar leírással -->
  <canvas bind:this={vaszon} class="vaszon" tabindex="0" role="application" aria-label={cimke} data-fokusz-cel></canvas>

  <!-- a rajzoló színeit a témából olvassa: rejtett próbaelemek -->
  <div class="proba" bind:this={proba} aria-hidden="true">
    <i class="p-jegyzet"></i><i class="p-canvas"></i><i class="p-melleklet"></i><i class="p-el"></i><i class="p-el-kiemelt"></i>
    <i class="p-kijelolt"></i><i class="p-felulet"></i><i class="p-szoveg"></i><i class="p-talalat"></i><i class="p-cimke"></i><i class="p-feloldatlan"></i>
  </div>

  <div class="eszkoztar" role="toolbar" aria-label={t('Gráf eszközök')}>
    <div class="szegmens" role="group" aria-label={t('Gráf módja')}>
      <button type="button" aria-pressed={mod === 'globalis'} onclick={() => modValt('globalis')}>{t('Globális')}</button>
      <button type="button" aria-pressed={mod === 'helyi'} disabled={mod !== 'helyi' && kozeppontValaszt() === null} onclick={() => modValt('helyi')}>{t('Helyi')}</button>
    </div>
    {#if mod === 'helyi'}
      <div class="szegmens" role="group" aria-label={t('Lépések száma a középponttól')}>
        {#each [1, 2, 3] as m (m)}
          <button
            type="button"
            aria-pressed={melyseg === m}
            title={tp('{n} lépés', m)}
            aria-label={tp('{n} lépés', m)}
            onclick={() => {
              nezetAllapot({ melyseg: m });
              ujIllesztes();
            }}>{m}</button
          >
        {/each}
      </div>
      <IkonGomb ikon={Pin} cimke={t('Aktív jegyzet követése')} lenyomva={kovet} onclick={() => nezetAllapot({ kovet: !kovet })} />
    {/if}
    <div class="kereso">
      <input
        id="graf-kereso"
        type="text"
        role="combobox"
        aria-expanded={keresoNyitva && talalatok.length > 0}
        aria-controls="graf-talalatok"
        aria-activedescendant={keresoNyitva && talalatok.length ? `graf-t-${keresoAktiv}` : undefined}
        aria-label={t('Keresés a gráfban')}
        placeholder={t('Ugrás csúcshoz…')}
        spellcheck="false"
        autocomplete="off"
        bind:value={keresoSzoveg}
        onfocus={() => (keresoNyitva = true)}
        onblur={() => setTimeout(() => (keresoNyitva = false), 120)}
        onkeydown={keresoBillentyu}
      />
      {#if keresoNyitva && talalatok.length && adat}
        <ul id="graf-talalatok" class="talalatok" role="listbox" aria-label={t('Találatok')}>
          {#each talalatok as i, q (i)}
            <li id={`graf-t-${q}`} role="option" aria-selected={q === keresoAktiv}>
              <button type="button" tabindex="-1" class:aktiv={q === keresoAktiv} onmousedown={(e) => (e.preventDefault(), void ugras(i))}>
                <span class="nev">{adat.nev[i]}</span>
                <span class="ut">{adat.ut[i]}</span>
              </button>
            </li>
          {/each}
        </ul>
      {/if}
    </div>
    <IkonGomb ikon={Maximize} cimke={t('Teljes nézet')} onclick={() => rajzolo?.teljesNezet()} />
    <IkonGomb ikon={SlidersHorizontal} cimke={t('Szűrők, színek és erők')} lenyomva={panelNyitva} onclick={() => nezetAllapot({ panel: !panelNyitva })} />
  </div>

  {#if panelNyitva && adat && szuro && szin}
    <GrafVezerlo {eff} {adat} {szuro} szinTamogatott={szin.tamogatott} json={grafAdat.json} />
  {/if}

  <div class="allapot" role="status" aria-live="polite">
    {#if grafAdat.hiba}
      <span class="hiba">{t('A gráf nem tölthető be: {hiba}', { hiba: grafAdat.hiba })}</span>
    {:else if !adat}
      <span>{grafAdat.betoltve ? '' : t('Gráf betöltése…')}</span>
    {:else if adat.n === 0}
      <span>{t('A vaultban még nincs fájl.')}</span>
    {:else}
      <span>{t('{db} / {n} csúcs · {el} él', { db: szuro?.csucsDb ?? 0, n: adat.n, el: lathatoEl })}</span>
      {#if adat.csonkolt}
        <span class="figy"><Ikon ikon={TriangleAlert} meret={14} />{t('Egyes címkék vagy feloldatlan célok a korlát miatt kimaradtak.')}</span>
      {/if}
    {/if}
  </div>

  {#if tooltipAdat && adat}
    <div class="tooltip" role="tooltip" style:left="{tooltipAdat.x + 14}px" style:top="{tooltipAdat.y + 14}px">
      <strong>{adat.nev[tooltipAdat.i]}</strong>
      {#if adat.tipus[tooltipAdat.i] === 'cimke'}
        <span>{t('Címke')} · {tp('{n} jegyzet', adat.fok[tooltipAdat.i])}</span>
      {:else if adat.tipus[tooltipAdat.i] === 'feloldatlan'}
        <span>{t('Még nem létező jegyzet')} · {tp('{n} jegyzet hivatkozik rá', adat.fok[tooltipAdat.i])}</span>
      {:else}
        <span>{adat.ut[tooltipAdat.i]}</span>
        <span>{adat.fok[tooltipAdat.i]} kapcsolat{adat.cimkek[tooltipAdat.i].length ? ` · ${adat.cimkek[tooltipAdat.i].slice(0, 4).join(', ')}` : ''}</span>
      {/if}
    </div>
  {/if}

  {#if !adat && !grafAdat.hiba}
    <div class="ures" aria-hidden="true"><Ikon ikon={Network} meret={20} /></div>
  {/if}
</div>

<style>
  .graf {
    position: relative;
    width: 100%;
    height: 100%;
    min-height: 0;
    overflow: hidden;
    background: var(--hatter);
  }

  .vaszon {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    display: block;
    touch-action: none;
    user-select: none;
    -webkit-user-select: none;
  }

  .vaszon:focus-visible {
    outline: var(--fokusz-vastag) solid var(--fokusz-gyuru);
    outline-offset: var(--fokusz-tav-befele);
  }

  .proba {
    position: absolute;
    width: 0;
    height: 0;
    overflow: hidden;
    visibility: hidden;
  }

  .proba :global(i) {
    display: block;
  }
  .proba :global(.p-jegyzet) {
    color: var(--graf-jegyzet);
  }
  .proba :global(.p-canvas) {
    color: var(--graf-canvas);
  }
  .proba :global(.p-melleklet) {
    color: var(--graf-melleklet);
  }
  .proba :global(.p-el) {
    color: var(--szoveg-halvany);
  }
  .proba :global(.p-el-kiemelt) {
    color: var(--akcent);
  }
  .proba :global(.p-kijelolt) {
    color: var(--akcent);
  }
  .proba :global(.p-felulet) {
    color: var(--hatter);
  }
  .proba :global(.p-szoveg) {
    color: var(--szoveg);
  }
  .proba :global(.p-talalat) {
    color: var(--figyelmeztetes);
  }
  .proba :global(.p-cimke) {
    color: var(--graf-cimke);
  }
  .proba :global(.p-feloldatlan) {
    color: var(--graf-feloldatlan);
  }

  .eszkoztar {
    position: absolute;
    top: var(--t-2);
    left: var(--t-2);
    right: var(--t-2);
    display: flex;
    align-items: center;
    gap: var(--t-2);
    pointer-events: none;
  }

  .eszkoztar > :global(*) {
    pointer-events: auto;
  }

  .eszkoztar :global(.ikon-gomb) {
    background: var(--hatter-emelt);
    border: 1px solid var(--keret);
  }

  .szegmens {
    display: flex;
    padding: 2px;
    gap: 2px;
    border: 1px solid var(--keret);
    border-radius: var(--kerekites);
    background: var(--hatter-emelt);
  }

  .szegmens button {
    min-width: var(--magassag-gomb);
    height: var(--magassag-suru);
    padding: 0 var(--t-2);
    border-radius: var(--kerekites-kicsi);
    color: var(--szoveg-masodlagos);
  }

  .szegmens button:hover:not(:disabled) {
    background: var(--hatter-hover);
    color: var(--szoveg);
  }

  .szegmens button[aria-pressed='true'] {
    background: var(--hatter-kijelolt);
    color: var(--szoveg);
  }

  .szegmens button:disabled {
    color: var(--szoveg-halvany);
    opacity: var(--tiltott-atlatszosag);
  }

  .kereso {
    position: relative;
    flex: 0 1 260px;
    min-width: 120px;
  }

  .kereso input {
    width: 100%;
    height: var(--magassag-sor);
    padding: 0 var(--t-2);
    border: 1px solid var(--keret-mezo);
    border-radius: var(--kerekites);
    background: var(--hatter-emelt);
    color: var(--szoveg);
  }

  .kereso input::placeholder {
    color: var(--szoveg-halvany);
  }

  .kereso input:focus-visible {
    outline: var(--fokusz-vastag) solid var(--fokusz-gyuru);
    outline-offset: 0;
  }

  .talalatok {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    right: 0;
    z-index: 2;
    margin: 0;
    padding: var(--t-1);
    border: 1px solid var(--keret-eros);
    border-radius: var(--kerekites);
    background: var(--hatter-emelt);
  }

  .talalatok button {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    width: 100%;
    padding: 2px var(--t-2);
    border-radius: var(--kerekites-kicsi);
    text-align: left;
  }

  .talalatok button.aktiv,
  .talalatok button:hover {
    background: var(--hatter-kijelolt);
  }

  .talalatok .nev {
    color: var(--szoveg);
  }

  .talalatok .ut {
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: var(--betu-kicsi);
    color: var(--szoveg-halvany);
  }

  .allapot {
    position: absolute;
    left: var(--t-3);
    bottom: var(--t-2);
    font-size: var(--betu-kicsi);
    color: var(--szoveg-halvany);
    pointer-events: none;
  }

  .allapot .hiba {
    color: var(--hiba);
  }

  .allapot .figy {
    display: inline-flex;
    align-items: center;
    gap: var(--t-1);
    margin-left: var(--t-2);
    color: var(--figyelmeztetes);
  }

  .tooltip {
    position: absolute;
    z-index: 3;
    display: flex;
    flex-direction: column;
    max-width: 320px;
    padding: var(--t-1) var(--t-2);
    border: 1px solid var(--keret-eros);
    border-radius: var(--kerekites);
    background: var(--hatter-emelt);
    color: var(--szoveg-masodlagos);
    font-size: var(--betu-kicsi);
    pointer-events: none;
  }

  .tooltip strong {
    color: var(--szoveg);
    font-weight: var(--suly-kozepes);
  }

  .ures {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    color: var(--szoveg-halvany);
    pointer-events: none;
  }
</style>
