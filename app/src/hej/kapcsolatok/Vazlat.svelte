<!--
  Vázlat (C10, 11-graph-06/07/08): a jegyzet fejezetei az ÉLŐ szövegből (a szerkesztő szintaxisfájából), gépelés közben is
  frissül. Kattintásra a szerkesztő a fejezetre ugrik. Fa: a szülő fejezet összecsukható (nyíl-gomb, `aria-expanded`),
  az összes összecsukható / kibontható; szűrő (ékezetfüggetlen, a találat őseivel); a szakaszok húzással — billentyűzetről Alt+↑/↓,
  vagy a jobb gombos menüből — átrendezhetők. Az áthelyezés a jegyzetet csak a szerkesztő saját tranzakciójával írja (a meglévő
  mentési út: ütközés-felismerés, csak olvasható fájl, visszavonás egy lépésben); tiltásnál a Vázlat kimondja az okot.
-->
<script lang="ts">
  import { onDestroy, tick } from 'svelte';
  import { t } from '../../lib/i18n';
  import Ikon from '../../lib/ikon/Ikon.svelte';
  import { ChevronDown, ChevronRight, ChevronsDownUp, GripVertical, ListTree, TriangleAlert } from '../../lib/ikon/ikonok';
  import IkonGomb from '../../lib/ui/IkonGomb.svelte';
  import { lebegoMenu, type MenuElem } from '../../szerkeszto/notion/menu';
  import { szerkesztok } from '../../szerkeszto/szerkesztok.svelte';
  import {
    latszoSorok,
    osszecsukhatok,
    testverIndex,
    vazlatSorok,
    type AthelyezTilt,
    type Hova,
    type TervHiba,
    type VazlatSor,
  } from '../../szerkeszto/vazlat';
  import { vazlatAllapot } from './vazlatAllapot.svelte';

  /** A szűrő mezője ennyi fejezet fölött jelenik meg (kevés fejezetnél csendes marad). */
  const SZURO_KUSZOB = 5;

  const peldany = $derived(szerkesztok.aktiv);
  const ut = $derived(peldany?.ut ?? '');
  const elemek = $derived.by(() => {
    const p = peldany;
    if (!p) return [];
    void p.valtozat(); // a szöveg változására újraszámol
    return p.vazlat();
  });
  const sorok = $derived(vazlatSorok(elemek));
  const osszecsukott = $derived(vazlatAllapot.kap(ut));
  let szuro = $state('');
  const latszo = $derived(latszoSorok(sorok, osszecsukott, szuro));
  const osszecsukhato = $derived(osszecsukhatok(sorok));
  /** Az áthelyezés tilalmának oka (a szerkesztőtől; a hiányzó támogatás is tilt) — a húzás és a billentyűk ebből engedélyezettek. */
  const tilt = $derived<AthelyezTilt | null>(peldany ? (peldany.athelyezTilt ? peldany.athelyezTilt() : 'nincsNezet') : 'nincsNezet');
  const athelyezheto = $derived(tilt === null);

  let ulElem: HTMLElement | undefined = $state();
  let uzenet = $state<string | null>(null);
  let allapotSzoveg = $state('');
  let uzenetIdozito: ReturnType<typeof setTimeout> | null = null;

  // másik jegyzet: a szűrő és az üzenet nem öröklődik
  $effect(() => {
    void ut;
    szuro = '';
    uzenet = null;
  });
  onDestroy(() => {
    if (uzenetIdozito) clearTimeout(uzenetIdozito);
  });

  const TILTAS_SZOVEG: Record<AthelyezTilt | TervHiba, () => string> = {
    olvaso: () => t('Olvasó módban a szakaszok nem mozgathatók; váltson szerkesztésre.'),
    nincsNezet: () => t('A jegyzet még nem szerkeszthető, a szakaszok nem mozgathatók.'),
    csakOlvashato: () => t('A jegyzet csak olvasható, ezért a szakaszok nem mozgathatók.'),
    utkozes: () => t('Mentési ütközés van: oldja fel, mielőtt szakaszt mozgat.'),
    eltunt: () => t('A jegyzet eltűnt a lemezről, a szakaszok nem mozgathatók.'),
    betoltes: () => t('A jegyzet még töltődik, a szakaszok nem mozgathatók.'),
    elavult: () => t('A jegyzet közben megváltozott; semmi sem mozdult. Próbálja újra.'),
    sajatReszben: () => t('A szakasz nem helyezhető önmagába.'),
    nincsValtozas: () => '',
    ervenytelen: () => t('Ez az áthelyezés nem lehetséges.'),
  };

  function figyelmeztet(szoveg: string) {
    uzenet = szoveg || null;
    if (uzenetIdozito) clearTimeout(uzenetIdozito);
    if (szoveg) uzenetIdozito = setTimeout(() => (uzenet = null), 8000);
  }

  // ------------------------------------------------------------------ összecsukás

  function valt(s: VazlatSor) {
    vazlatAllapot.valt(ut, s.kulcs);
  }
  const mindOssze = () => vazlatAllapot.allit(ut, osszecsukhato);
  const mindKi = () => vazlatAllapot.allit(ut, []);

  // ------------------------------------------------------------------ áthelyezés

  function sorGomb(kulcs: string): HTMLButtonElement | null {
    if (!ulElem) return null;
    return [...ulElem.querySelectorAll<HTMLButtonElement>('button.sor')].find((b) => b.dataset.kulcs === kulcs) ?? null;
  }

  async function athelyez(forras: VazlatSor, cel: VazlatSor, hova: Hova, valtozat?: number) {
    const p = peldany;
    if (!p?.szakaszAthelyez) return;
    const r = p.szakaszAthelyez({ forras: forras.elem, cel: cel.elem, hova, valtozat: valtozat ?? p.valtozat() });
    if (r.kesz) {
      figyelmeztet('');
      allapotSzoveg = t('Szakasz áthelyezve: {fejezet}', { fejezet: forras.elem.szoveg });
      await tick();
      sorGomb(forras.kulcs)?.focus({ preventScroll: true });
    } else figyelmeztet(TILTAS_SZOVEG[r.ok]());
  }

  /** Egy szinttel feljebb / lejjebb a testvérek között (billentyű és menü). */
  function mozgat(s: VazlatSor, irany: -1 | 1) {
    if (tilt) return figyelmeztet(TILTAS_SZOVEG[tilt]());
    const j = testverIndex(sorok, s.i, irany);
    if (j < 0) return;
    void athelyez(s, sorok[j], irany < 0 ? 'elott' : 'utan');
  }

  // húzás
  let huzas = $state<{ i: number; valtozat: number } | null>(null);
  let celJel = $state<{ i: number; hova: Hova } | null>(null);

  function utodja(s: VazlatSor, osI: number): boolean {
    for (let k = s.szulo; k >= 0; k = sorok[k].szulo) if (k === osI) return true;
    return false;
  }

  function huzasKezd(e: DragEvent, s: VazlatSor) {
    if (tilt) {
      e.preventDefault();
      figyelmeztet(TILTAS_SZOVEG[tilt]());
      return;
    }
    huzas = { i: s.i, valtozat: peldany!.valtozat() };
    if (e.dataTransfer) {
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', s.elem.szoveg);
    }
  }

  function huzasFelett(e: DragEvent, s: VazlatSor) {
    if (!huzas || s.i === huzas.i || utodja(s, huzas.i)) {
      celJel = null;
      return;
    }
    e.preventDefault(); // csak ide lehet ejteni
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    celJel = { i: s.i, hova: e.clientY < r.top + r.height / 2 ? 'elott' : 'utan' };
  }

  function ejtes(e: DragEvent) {
    e.preventDefault();
    const h = huzas;
    const c = celJel;
    huzasVege();
    if (!h || !c) return;
    void athelyez(sorok[h.i], sorok[c.i], c.hova, h.valtozat);
  }

  function huzasVege() {
    huzas = null;
    celJel = null;
  }

  // ------------------------------------------------------------------ billentyűk és menü

  function sorBillentyu(e: KeyboardEvent, s: VazlatSor) {
    if (e.isComposing) return;
    const osszecsukva = osszecsukott.has(s.kulcs);
    if (e.altKey && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
      e.preventDefault();
      mozgat(s, e.key === 'ArrowUp' ? -1 : 1);
    } else if (e.key === 'ArrowRight' && s.gyerek && osszecsukva && !szuro) {
      e.preventDefault();
      valt(s);
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      if (s.gyerek && !osszecsukva && !szuro) valt(s);
      else if (s.szulo >= 0) sorGomb(sorok[s.szulo].kulcs)?.focus();
    } else if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
      e.preventDefault();
      const k = latszo.findIndex((x) => x.sor.i === s.i) + (e.key === 'ArrowUp' ? -1 : 1);
      if (latszo[k]) sorGomb(latszo[k].sor.kulcs)?.focus();
    } else if (e.key === 'ContextMenu' || (e.key === 'F10' && e.shiftKey)) {
      e.preventDefault();
      const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
      menu(s, r.left + 24, r.bottom);
    }
  }

  function menu(s: VazlatSor, x: number, y: number) {
    const elemekM: MenuElem[] = [];
    const akciok = new Map<string, () => void>();
    const hozzaad = (id: string, nev: string, fn: () => void, letiltva = false) => {
      elemekM.push({ id, nev, ...(letiltva ? { letiltva } : {}) });
      akciok.set(id, fn);
    };
    hozzaad('ugras', t('Ugrás a fejezetre'), () => peldany?.ugras(s.elem.sor));
    hozzaad('fel', t('Szakasz mozgatása felfelé'), () => mozgat(s, -1), tilt !== null || testverIndex(sorok, s.i, -1) < 0);
    hozzaad('le', t('Szakasz mozgatása lefelé'), () => mozgat(s, 1), tilt !== null || testverIndex(sorok, s.i, 1) < 0);
    if (s.gyerek) hozzaad('valt', osszecsukott.has(s.kulcs) ? t('Szakasz kibontása') : t('Szakasz összecsukása'), () => valt(s));
    if (osszecsukhato.length) {
      hozzaad('mind-ossze', t('Összes összecsukása'), mindOssze);
      hozzaad('mind-ki', t('Összes kibontása'), mindKi);
    }
    lebegoMenu({ focus: () => sorGomb(s.kulcs)?.focus() }, x, y, elemekM, akciok, t('Vázlat menü'));
  }

  function sorMenu(e: MouseEvent, s: VazlatSor) {
    e.preventDefault();
    e.stopPropagation();
    menu(s, e.clientX, e.clientY);
  }

  function szuroBillentyu(e: KeyboardEvent) {
    if (e.key === 'Escape' && szuro) {
      e.preventDefault();
      e.stopPropagation();
      szuro = '';
    }
  }
</script>

{#if !peldany}
  <p class="ures">{t('Nincs megnyitott jegyzet.')}</p>
{:else if !elemek.length}
  <p class="ures">{t('A jegyzetben nincs fejezet.')}</p>
{:else}
  {#if elemek.length > SZURO_KUSZOB || szuro || osszecsukhato.length}
    <div class="eszkoztar">
      {#if elemek.length > SZURO_KUSZOB || szuro}
        <input
          class="szuro"
          type="text"
          spellcheck="false"
          autocomplete="off"
          aria-label={t('Fejezetek szűrése')}
          placeholder={t('Szűrés…')}
          bind:value={szuro}
          onkeydown={szuroBillentyu}
        />
      {/if}
      {#if osszecsukhato.length}
        <IkonGomb ikon={ChevronsDownUp} cimke={t('Összes összecsukása')} kicsi onclick={mindOssze} />
        <IkonGomb ikon={ListTree} cimke={t('Összes kibontása')} kicsi onclick={mindKi} />
      {/if}
    </div>
  {/if}
  {#if uzenet}
    <p class="figy" role="alert"><Ikon ikon={TriangleAlert} meret={14} /><span>{uzenet}</span></p>
  {/if}
  <div class="olvaso-allapot" role="status" aria-live="polite">{allapotSzoveg}</div>
  {#if !latszo.length}
    <p class="ures">{t('Nincs egyező fejezet.')}</p>
  {:else}
    <ul bind:this={ulElem} aria-label={t('Vázlat')} ondragleave={(e) => !(e.currentTarget as HTMLElement).contains(e.relatedTarget as Node | null) && (celJel = null)}>
      {#each latszo as { sor: s, talalat } (s.kulcs)}
        {@const osszecsukva = osszecsukott.has(s.kulcs)}
        <li
          class="elem"
          class:huz={huzas?.i === s.i}
          class:jel-elott={celJel?.i === s.i && celJel.hova === 'elott'}
          class:jel-utan={celJel?.i === s.i && celJel.hova === 'utan'}
          draggable={athelyezheto}
          ondragstart={(e) => huzasKezd(e, s)}
          ondragover={(e) => huzasFelett(e, s)}
          ondrop={ejtes}
          ondragend={huzasVege}
          oncontextmenu={(e) => sorMenu(e, s)}
          style:padding-left="{s.mely * 12}px"
        >
          {#if s.gyerek && !szuro}
            <button
              type="button"
              class="nyil"
              aria-expanded={!osszecsukva}
              aria-label={osszecsukva ? t('Szakasz kibontása: {nev}', { nev: s.elem.szoveg }) : t('Szakasz összecsukása: {nev}', { nev: s.elem.szoveg })}
              onclick={() => valt(s)}><Ikon ikon={osszecsukva ? ChevronRight : ChevronDown} meret={14} /></button
            >
          {:else}
            <span class="nyil ures-hely" aria-hidden="true"></span>
          {/if}
          <button
            type="button"
            class="sor"
            class:halvany={szuro && !talalat}
            data-kulcs={s.kulcs}
            aria-keyshortcuts={athelyezheto ? 'Alt+ArrowUp Alt+ArrowDown' : undefined}
            onclick={() => peldany?.ugras(s.elem.sor)}
            onkeydown={(e) => sorBillentyu(e, s)}>{s.elem.szoveg}</button
          >
          {#if athelyezheto}<span class="fogo" aria-hidden="true"><Ikon ikon={GripVertical} meret={14} /></span>{/if}
        </li>
      {/each}
    </ul>
  {/if}
{/if}

<style>
  .ures {
    margin: 0;
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  .eszkoztar {
    display: flex;
    align-items: center;
    gap: var(--t-1);
    margin-bottom: var(--t-1);
  }

  .szuro {
    flex: 1;
    min-width: 0;
    height: var(--magassag-gomb-kicsi);
    padding: 0 var(--t-2);
    border: 1px solid var(--keret-mezo);
    border-radius: var(--kerekites-kicsi);
    background: var(--hatter);
    color: var(--szoveg);
    font-size: var(--betu-kicsi);
  }

  .szuro::placeholder {
    color: var(--szoveg-halvany);
  }

  .szuro:focus-visible {
    outline: var(--fokusz-vastag) solid var(--fokusz-gyuru);
    outline-offset: 0;
  }

  /* a tiltás oka: ikonnal és szóval (a figyelmeztetés színe nem az akcent) */
  .figy {
    display: flex;
    align-items: flex-start;
    gap: var(--t-1);
    margin: 0 0 var(--t-1);
    color: var(--figyelmeztetes);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  .olvaso-allapot {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
  }

  ul {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .elem {
    display: flex;
    align-items: center;
    gap: 2px;
    border-radius: var(--kerekites-kicsi);
  }

  .elem[draggable='true'] .fogo {
    opacity: 0;
    color: var(--szoveg-halvany);
    cursor: grab;
  }

  .elem:hover .fogo,
  .elem:focus-within .fogo {
    opacity: 1;
  }

  .elem.huz {
    opacity: var(--atlatszosag-felig);
  }

  /* a húzás célvonala: az akcent mint jel vonala (nem állapot) */
  .elem.jel-elott {
    box-shadow: inset 0 var(--jel-vastag) 0 var(--akcent);
  }

  .elem.jel-utan {
    box-shadow: inset 0 calc(-1 * var(--jel-vastag)) 0 var(--akcent);
  }

  .nyil {
    flex: none;
    display: inline-grid;
    place-items: center;
    width: var(--magassag-gomb-kicsi);
    height: var(--magassag-gomb-kicsi);
    border-radius: var(--kerekites-kicsi);
    color: var(--szoveg-halvany);
  }

  button.nyil:hover {
    background: var(--hatter-hover);
    color: var(--szoveg);
  }

  .sor {
    display: block;
    flex: 1;
    min-width: 0;
    padding: 2px var(--t-1);
    border-radius: var(--kerekites-kicsi);
    text-align: left;
    font-size: var(--betu-ui);
    color: var(--szoveg-masodlagos);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .sor.halvany {
    color: var(--szoveg-halvany);
  }

  .sor:hover {
    background: var(--hatter-hover);
    color: var(--szoveg);
  }

  .fogo {
    flex: none;
    display: inline-grid;
    place-items: center;
  }
</style>
