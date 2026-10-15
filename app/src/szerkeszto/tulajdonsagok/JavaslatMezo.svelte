<!--
  Javaslatos bevitelmező a tulajdonság-panelhez: combobox + lebegő listbox (WAI-ARIA 1.2), a fókusz végig a mezőben marad,
  az aktív sort az `aria-activedescendant` jelöli. Gépeléskor (rövid késleltetéssel) a `javasol` adja a listát; a lista a
  `[[` kiegészítés menüjének megjelenését veszi át (`nt-menu`). Billentyűk: ↑↓ (⌃N/⌃P) lép (zárt listánál a ↓ nyit),
  ↩ és Tab a kiemelt javaslatot veszi (a Tab erős találat nélkül az elsőt), Esc bezár. Erős találat nélkül (a gépelt
  szöveg egyik javaslat nevében sem áll) nincs kiemelt sor: az ↩ ekkor a gépelt szöveget hagyja a hívóra.
  A beírás (és a séma-ellenőrzés) a hívóé (`onvalaszt`); ez a komponens csak a bevitel.
-->
<script lang="ts">
  import { onDestroy, untrack } from 'svelte';
  import Ikon from '../../lib/ikon/Ikon.svelte';
  import { TriangleAlert } from '../../lib/ikon/ikonok';
  import { darabol } from '../../lib/kereses/fuzzy';
  import type { JavaslatElem, JavaslatLista } from './javaslat';

  let {
    value = $bindable(''),
    javasol,
    onvalaszt,
    nyitFokuszra = false,
    cimke,
    id,
    placeholder,
    osztaly = '',
    readonly = false,
    disabled = false,
    inputmode,
    size,
    onkeydown,
    onchange,
    onblur,
    onfocus,
  }: {
    value?: string;
    /** a javaslatok a gépelt szövegre (szinkron vagy aszinkron) */
    javasol: (q: string) => JavaslatLista | Promise<JavaslatLista>;
    onvalaszt: (e: JavaslatElem) => void;
    /** fókuszra (és kattintásra) is nyílik: az értékkészletes mezőnél (Status), mint egy legördülő */
    nyitFokuszra?: boolean;
    cimke: string;
    id?: string;
    placeholder?: string;
    osztaly?: string;
    readonly?: boolean;
    disabled?: boolean;
    inputmode?: 'decimal' | 'text';
    size?: number;
    onkeydown?: (e: KeyboardEvent & { currentTarget: HTMLInputElement }) => void;
    onchange?: (e: Event & { currentTarget: HTMLInputElement }) => void;
    onblur?: (e: FocusEvent & { currentTarget: HTMLInputElement }) => void;
    onfocus?: (e: FocusEvent & { currentTarget: HTMLInputElement }) => void;
  } = $props();

  const sajat = $props.id();
  const listaId = `${sajat}-javaslatok`;
  const KESLELTETES_MS = 60;

  let elemek = $state.raw<JavaslatElem[]>([]);
  let aktiv = $state(-1);
  let nyitva = $state(false);
  let hely = $state<{ left: number; top?: number; bottom?: number; width: number } | null>(null);
  let mezo: HTMLInputElement | undefined = $state();
  let lista: HTMLElement | undefined = $state();
  let idozito: ReturnType<typeof setTimeout> | null = null;
  let sorszam = 0;

  const opcioId = (i: number) => `${sajat}-o${i}`;
  const aktivId = $derived(nyitva && aktiv >= 0 && aktiv < elemek.length ? opcioId(aktiv) : undefined);

  function elhelyez() {
    if (!mezo) return;
    const r = mezo.getBoundingClientRect();
    const lent = window.innerHeight - r.bottom;
    const width = Math.max(r.width, 240);
    const left = Math.max(8, Math.min(r.left, window.innerWidth - width - 8));
    hely = lent < 220 && r.top > lent ? { left, bottom: window.innerHeight - r.top + 2, width } : { left, top: r.bottom + 2, width };
  }

  async function frissit(nyit: boolean) {
    const en = ++sorszam;
    let l: JavaslatLista;
    try {
      l = await javasol(value);
    } catch {
      l = { elemek: [], eros: false };
    }
    if (en !== sorszam || document.activeElement !== mezo) return; // újabb gépelés, vagy a mező már nem aktív
    elemek = l.elemek;
    aktiv = l.eros ? 0 : -1;
    if (nyit || nyitva) {
      nyitva = l.elemek.length > 0;
      if (nyitva) elhelyez();
    }
  }

  function utemez() {
    if (idozito) clearTimeout(idozito);
    idozito = setTimeout(() => {
      idozito = null;
      void frissit(true);
    }, KESLELTETES_MS);
  }

  function bezar() {
    sorszam++;
    if (idozito) clearTimeout(idozito);
    idozito = null;
    nyitva = false;
    aktiv = -1;
  }

  function valaszt(i: number) {
    const e = elemek[i];
    if (!e) return;
    bezar();
    value = e.ertek; // a mező a választottat mutatja (a későbbi `change` nem a gépelt töredéket írja be); a hívó felülírhatja
    onvalaszt(e);
  }

  /** a kattintott vagy rámutatott sor indexe (a lista egy helyen kezeli az egeret; a fókusz a mezőben marad) */
  function sorIndex(t: EventTarget | null): number {
    const x = (t as HTMLElement | null)?.closest?.<HTMLElement>('[data-index]');
    return x ? Number(x.dataset.index) : -1;
  }

  function lep(d: number) {
    const n = elemek.length;
    if (!n) return;
    aktiv = aktiv < 0 ? (d > 0 ? 0 : n - 1) : (aktiv + d + n) % n;
    queueMicrotask(() => lista?.querySelector<HTMLElement>(`#${CSS.escape(opcioId(aktiv))}`)?.scrollIntoView?.({ block: 'nearest' }));
  }

  function billentyu(e: KeyboardEvent & { currentTarget: HTMLInputElement }) {
    if (e.isComposing || readonly || disabled) {
      onkeydown?.(e);
      return;
    }
    const ctrl = e.ctrlKey && !e.metaKey && !e.altKey;
    const le = e.key === 'ArrowDown' || (ctrl && e.key === 'n');
    const fel = e.key === 'ArrowUp' || (ctrl && e.key === 'p');
    if (le || fel) {
      e.preventDefault();
      if (!nyitva) void frissit(true).then(() => le && nyitva && aktiv < 0 && lep(1));
      else lep(le ? 1 : -1);
      return;
    }
    if (nyitva && (e.key === 'Enter' || e.key === 'Tab') && !e.shiftKey) {
      const i = aktiv >= 0 ? aktiv : e.key === 'Tab' && value.trim() ? 0 : -1;
      if (i >= 0) {
        e.preventDefault();
        e.stopPropagation();
        valaszt(i);
        return;
      }
    }
    if (e.key === 'Escape' && nyitva) {
      e.preventDefault();
      e.stopPropagation();
      bezar();
      return;
    }
    if (e.key === 'Enter' || e.key === 'Tab') bezar();
    onkeydown?.(e);
  }

  function bevitel() {
    if (readonly || disabled) return;
    utemez();
  }

  function fokusz(e: FocusEvent & { currentTarget: HTMLInputElement }) {
    onfocus?.(e);
    if (nyitFokuszra && !readonly && !disabled) void frissit(true);
  }

  function kattint() {
    if (nyitFokuszra && !nyitva && !readonly && !disabled) void frissit(true);
  }

  function elhagy(e: FocusEvent & { currentTarget: HTMLInputElement }) {
    bezar();
    onblur?.(e);
  }

  // a hívó kiürítette a mezőt (a vessző felvette az elemet): a lista a régi szövegre szólt, bezárul
  $effect(() => {
    if (value === '' && !nyitFokuszra) untrack(bezar);
  });

  // nyitott lista: görgetésre és átméretezésre a mező alatt marad
  $effect(() => {
    if (!nyitva) return;
    const f = () => elhelyez();
    window.addEventListener('scroll', f, true);
    window.addEventListener('resize', f);
    return () => {
      window.removeEventListener('scroll', f, true);
      window.removeEventListener('resize', f);
    };
  });

  onDestroy(() => {
    if (idozito) clearTimeout(idozito);
  });
</script>

<input
  bind:this={mezo}
  bind:value
  {id}
  type="text"
  class={osztaly}
  role="combobox"
  aria-label={cimke}
  aria-autocomplete="list"
  aria-expanded={nyitva}
  aria-controls={listaId}
  aria-activedescendant={aktivId}
  autocomplete="off"
  spellcheck="false"
  {placeholder}
  {readonly}
  {disabled}
  {inputmode}
  {size}
  oninput={bevitel}
  onkeydown={billentyu}
  onfocus={fokusz}
  onclick={kattint}
  onblur={elhagy}
  {onchange}
/>
<div
  bind:this={lista}
  class="nt-menu nt-linkmenu jm-lista"
  hidden={!nyitva}
  style:left={hely ? `${hely.left}px` : undefined}
  style:top={hely?.top !== undefined ? `${hely.top}px` : undefined}
  style:bottom={hely?.bottom !== undefined ? `${hely.bottom}px` : undefined}
  style:min-width={hely ? `${hely.width}px` : undefined}
  role="presentation"
  onmousedown={(e) => e.preventDefault()}
  onmousemove={(e) => {
    const i = sorIndex(e.target);
    if (i >= 0) aktiv = i;
  }}
  onclick={(e) => valaszt(sorIndex(e.target))}
>
  <div class="nt-menu-lista" id={listaId} role="listbox" aria-label="{cimke}: javaslatok">
    {#each elemek as e, i (e.id)}
      <div
        id={opcioId(i)}
        class="nt-menu-elem"
        class:aktiv={i === aktiv}
        role="option"
        aria-selected={i === aktiv}
        data-index={i}
        title={e.leiras}
      >
        {#if e.ikon}<span class="nt-menu-ikon"><Ikon ikon={e.ikon} meret={16} /></span>{/if}
        <span class="nt-menu-nev">
          {#each e.kiemeles ? darabol(e.nev, e.kiemeles) : [{ szoveg: e.nev, kiemelt: false }] as d, j (j)}{#if d.kiemelt}<mark>{d.szoveg}</mark>{:else}{d.szoveg}{/if}{/each}
        </span>
        {#if e.megjegyzes}
          <span class="megj"><Ikon ikon={TriangleAlert} meret={14} />{e.megjegyzes}</span>
        {/if}
        {#if e.jelzo}<span class="nt-menu-jelzo">{e.jelzo}</span>{/if}
      </div>
    {/each}
  </div>
</div>

<style>
  .jm-lista {
    position: fixed;
    z-index: var(--reteg-atfedes);
    border-radius: var(--kerekites-nagy);
    box-shadow: var(--arnyek-atfedes);
  }

  .jm-lista[hidden] {
    display: none;
  }

  .megj {
    display: inline-flex;
    flex: none;
    align-items: center;
    gap: 2px;
    color: var(--figyelmeztetes);
    font-size: var(--betu-kicsi);
  }
</style>
