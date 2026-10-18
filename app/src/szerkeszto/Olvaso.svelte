<!--
  Az Olvasó: a jegyzet HTML-ként, a szerkesztővel azonos elemzőből (olvaso/html.ts). A dokumentum
  változásakor (jelölőnégyzet, külső változás) újrarajzol, a görgetési hely megmarad. A jelölőnégyzetre
  kattintás a dokumentumot írja; a lábjegyzet-hivatkozás a lap aljára ugrik, a ↩ vissza.
-->
<script lang="ts">
  import { t } from '../lib/i18n';
  import { beallitasok } from '../lib/beallitasok/allapot.svelte';
  import { linkek } from '../lib/vault/linkek.svelte';
  import { ensureSyntaxTree } from '@codemirror/language';
  import type { EditorView } from '@codemirror/view';
  import { onDestroy, onMount, tick } from 'svelte';
  import { ChevronDown, ChevronUp, X } from '../lib/ikon/ikonok';
  import IkonGomb from '../lib/ui/IkonGomb.svelte';
  import type { Dokumentum } from './dokumentum/dokumentum.svelte';
  import { obsidianElemzo } from './markdown/elemzo';
  import { domCel, elonezetKapcsol } from './linkek/elonezet';
  import { kulsoLink } from './linkek/kulso';
  import { linkMegnyit, nyitasMod } from './linkek/navigacio';
  import { dokumentumRenderel } from './olvaso/html';
  import { LustaRajzolo } from './olvaso/lusta';
  import { feloldatlanJelol } from './linkek/feloldatlan';
  import { OlvasoKereses } from './olvaso/kereses';
  import { beagyazasFrissitesFigyel } from './beagyazas/rajzol';
  import { olvasoHajtas } from './olvaso/hajtas';

  let { view, dok, ut, valtozat, nyelv = '' }: { view: EditorView; dok: Dokumentum; ut: string; valtozat: number; nyelv?: string } = $props();

  let gorgeto: HTMLDivElement | undefined = $state();
  let tartalom: HTMLElement | undefined = $state();
  let lusta: LustaRajzolo | null = null;
  let kesleltetes: ReturnType<typeof setTimeout> | null = null;
  let kereses: OlvasoKereses | null = null;
  let keresesNyitva = $state(false);
  let lekerdezes = $state('');
  let betuerzekeny = $state(false);
  let talalatok = $state({ osszes: 0, aktualis: 0 });
  let keresoMezo: HTMLInputElement | undefined = $state();
  const elotag = `lj${Math.random().toString(36).slice(2, 8)}`;

  /** A kereső megnyitása; a `kezdo` előtölti a mezőt (pl. a ⌘⇧F ablak lekérdezéséből), különben a mező régi szövege marad. */
  export async function keresesNyit(kezdo?: string): Promise<void> {
    if (kezdo !== undefined && kezdo !== '') lekerdezes = kezdo;
    keresesNyitva = true;
    await tick();
    keresoMezo?.focus();
    keresoMezo?.select();
  }

  function keresesBezar() {
    keresesNyitva = false;
    kereses?.keres('');
    tartalom?.focus({ preventScroll: true });
  }

  function keresoBillentyu(e: KeyboardEvent) {
    if (e.isComposing) return;
    if (e.key === 'Enter') {
      e.preventDefault(); e.stopPropagation(); kereses?.lep(e.shiftKey ? -1 : 1);
    } else if (e.key === 'Escape') {
      e.preventDefault(); e.stopPropagation(); keresesBezar();
    }
  }

  $effect(() => {
    if (keresesNyitva) kereses?.keres(lekerdezes, betuerzekeny);
  });

  function rajzol() {
    if (!tartalom || !gorgeto) return;
    const state = view.state;
    const doc = state.doc;
    const fa = ensureSyntaxTree(state, doc.length, 3000) ?? obsidianElemzo.parse(doc.toString());
    const gorgetes = gorgeto.scrollTop;
    lusta?.leall();
    lusta = new LustaRajzolo(gorgeto);
    const f = dokumentumRenderel(fa, { olvas: (a, b) => doc.sliceString(a, b), ut, lusta, elotag, csakOlvashato: state.readOnly || !!dok.csakOlvashato });
    tartalom.replaceChildren(f);
    feloldatlanJelol(tartalom, lusta.jel);
    olvasoHajtas(tartalom, view);
    gorgeto.scrollTop = gorgetes;
  }

  /** A szerkesztő hajtás-állapotának változása (parancs, másik nézet): a gombok és a rejtés újra (újrarajzolás nélkül). */
  export function hajtasFrissit(): void {
    if (tartalom) olvasoHajtas(tartalom, view);
  }

  /** A legfelső látható blokk forrásbeli helye (a módváltás ide görget). */
  export function felsoPozicio(): number {
    if (!gorgeto || !tartalom) return 0;
    const teto = gorgeto.getBoundingClientRect().top;
    for (const e of tartalom.children) {
      if (!(e instanceof HTMLElement) || e.dataset.from === undefined) continue;
      if (e.getBoundingClientRect().bottom > teto + 4) return Number(e.dataset.from);
    }
    return 0;
  }

  export function gorget(pos: number): void {
    if (!tartalom || !gorgeto) return;
    let cel: HTMLElement | null = null;
    for (const e of tartalom.children) {
      if (!(e instanceof HTMLElement) || e.dataset.from === undefined) continue;
      if (Number(e.dataset.from) > pos) break;
      cel = e;
    }
    if (cel) gorgeto.scrollTop += cel.getBoundingClientRect().top - gorgeto.getBoundingClientRect().top - 8;
  }

  function linkNyit(e: MouseEvent | KeyboardEvent): boolean {
    const kulso = (e.target as HTMLElement).closest<HTMLElement>('a.link[data-url]');
    if (kulso?.dataset.url) {
      e.preventDefault();
      kulsoLink(kulso.dataset.url);
      return true;
    }
    const wl = (e.target as HTMLElement).closest<HTMLElement>('.wikilink[data-cel]');
    if (!wl || wl.dataset.forras === undefined) return false;
    e.preventDefault();
    void linkMegnyit({ forras: wl.dataset.forras, cel: wl.dataset.cel ?? '', alcel: wl.dataset.alcel ?? null }, nyitasMod(e));
    return true;
  }

  function kattintas(e: MouseEvent) {
    if (linkNyit(e)) return;
    const t = e.target as HTMLElement;
    const hiv = t.closest<HTMLElement>('[data-labjegyzet]');
    const vissza = t.closest<HTMLElement>('[data-labjegyzet-vissza]');
    if (hiv || vissza) {
      e.preventDefault();
      const id = hiv ? `${elotag}-def-${hiv.dataset.labjegyzet}` : `${elotag}-hiv-${vissza!.dataset.labjegyzetVissza}`;
      document.getElementById(id)?.scrollIntoView({ block: 'center' });
    }
  }

  /** Középső gomb a linken: új fül (02-links-08); más gomb (jobb) nem nyit. */
  function kozepsoKattintas(e: MouseEvent) {
    if (e.button === 1) linkNyit(e);
  }

  /** A középső gomb lenyomása a linken ne indítson automatikus görgetést (Windows/Linux). */
  function kozepsoLe(e: MouseEvent) {
    if (e.button === 1 && (e.target as HTMLElement).closest('.wikilink[data-cel], a.link[data-url]')) e.preventDefault();
  }

  function billentyu(e: KeyboardEvent) {
    if (keresesNyitva && e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); keresesBezar(); return; }
    if (e.key === 'Enter' && linkNyit(e)) return;
    if ((e.key === 'Enter' || e.key === ' ') && (e.target as HTMLElement).closest('[data-labjegyzet], [data-labjegyzet-vissza]')) {
      kattintas(e as unknown as MouseEvent);
    }
  }

  function valtas(e: Event) {
    const t = e.target as HTMLInputElement;
    if (!t.matches('input.feladat-jelolo') || t.dataset.jelolo === undefined) return;
    // A beágyazás saját dokumentumot ír. Szeletbeli pozíció soha nem értelmezhető a befogadó jegyzetben.
    if (t.dataset.beagyazas === 'true' || (t.dataset.jeloloUt !== undefined && t.dataset.jeloloUt !== ut)) return;
    if (view.state.readOnly || dok.csakOlvashato) {
      t.checked = !t.checked;
      return;
    }
    const pos = Number(t.dataset.jelolo);
    // az újrarajzolás késleltetett (120 ms): ha közben a dokumentum megváltozott, a jelölő pozíciója elavult lehet — ekkor
    // nem írunk, hanem újrarajzolunk (T120)
    if (!/^\[[^\r\n]\]$/u.test(view.state.sliceDoc(pos, pos + 3))) {
      t.checked = !t.checked;
      rajzol();
      return;
    }
    const allapot = view.state.sliceDoc(pos + 1, pos + 2);
    view.dispatch({ changes: { from: pos + 1, to: pos + 2, insert: allapot === ' ' ? 'x' : ' ' }, userEvent: 'input.feladat' });
  }

  onMount(() => {
    if (tartalom) kereses = new OlvasoKereses(tartalom, allapot => { talalatok = allapot; });
    rajzol();
    if (!tartalom) return undefined;
    // 04-embeds-07: más jegyzet tartalmi változása csak az érintett beágyazást rajzolja újra (a görgetés, a többi DOM marad)
    const le = [elonezetKapcsol(tartalom, domCel), beagyazasFrissitesFigyel(tartalom)];
    return () => { for (const f of le) f(); };
  });

  // a dokumentum változása (jelölőnégyzet, külső változás) után újrarajzol, kicsit késleltetve
  $effect(() => {
    void valtozat;
    void linkek.verzio;
    void Object.values(beallitasok.ertek.modulok);
    if (kesleltetes) clearTimeout(kesleltetes);
    kesleltetes = setTimeout(rajzol, 120);
  });

  onDestroy(() => {
    if (kesleltetes) clearTimeout(kesleltetes);
    lusta?.leall();
    kereses?.leallit();
  });
</script>

{#if keresesNyitva}
  <div class="olvaso-kereso" role="search" aria-label={t('Keresés az olvasóban')}>
    <input bind:this={keresoMezo} bind:value={lekerdezes} aria-label={t('Keresés az olvasóban')} placeholder={t('Keresés a megjelenített szövegben…')} onkeydown={keresoBillentyu} spellcheck="false" />
    <label class="betuerzekeny"><input type="checkbox" bind:checked={betuerzekeny} />{t('Kis- és nagybetű megkülönböztetése')}</label>
    <span class="kereso-eredmeny" role="status" aria-live="polite">{lekerdezes ? t('{aktualis}/{osszes} találat', talalatok) : ''}</span>
    <IkonGomb ikon={ChevronUp} cimke={t('Előző találat')} kicsi disabled={!talalatok.osszes} onclick={() => kereses?.lep(-1)} />
    <IkonGomb ikon={ChevronDown} cimke={t('Következő találat')} kicsi disabled={!talalatok.osszes} onclick={() => kereses?.lep(1)} />
    <IkonGomb ikon={X} cimke={t('Keresés bezárása')} kicsi onclick={keresesBezar} />
  </div>
{/if}
<div class="olvaso-gorgeto gorgeto" bind:this={gorgeto}>
  <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_noninteractive_element_interactions -->
  <article
    class="olvaso tipo olvasas md"
    lang={nyelv}
    bind:this={tartalom}
    aria-label={t('Olvasó nézet')}
    tabindex="-1"
    onclick={kattintas}
    onauxclick={kozepsoKattintas}
    onmousedown={kozepsoLe}
    onkeydown={billentyu}
    onchange={valtas}
  ></article>
</div>

<style>
  .olvaso-kereso {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--t-2);
    padding: var(--t-2) var(--t-3);
    background: var(--hatter-emelt);
    border-bottom: var(--keret-vastag) solid var(--keret);
    font-size: var(--betu-kicsi);
  }

  .olvaso-kereso > input {
    flex: 1;
    min-width: var(--magassag-mezo);
    padding: var(--t-1) var(--t-2);
    background: var(--hatter);
    color: var(--szoveg);
    border: var(--keret-vastag) solid var(--keret);
    border-radius: var(--kerekites-kicsi);
  }

  .betuerzekeny { display: inline-flex; align-items: center; gap: var(--t-1); }
  .kereso-eredmeny { color: var(--szoveg-masodlagos); font-variant-numeric: tabular-nums; }
  :global(.olvaso mark.olvaso-talalat) { background: var(--jeloles-hatter); color: inherit; }
  :global(.olvaso mark.olvaso-talalat-aktiv) { outline: var(--keret-vastag) solid var(--szoveg); }

  .olvaso-gorgeto {
    flex: 1;
    min-height: 0;
  }

  .olvaso {
    padding: var(--t-5) var(--t-6) 30vh;
    font-family: var(--betu-jegyzet);
  }
</style>
