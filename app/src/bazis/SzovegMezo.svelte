<!--
  Szöveges mező élő ellenőrzéssel (C12b): a szűrő, a képlet és a teljes forrás szerkesztője. Gépelés közben 300 ms
  után a core ellenőrzi a szöveget (a `modosit` tiszta próbája); a hiba a mező alatt áll, és az „Alkalmaz” addig
  tiltott. ⌘↩ alkalmaz, Esc visszaállítja a mentett szöveget. A mentett érték változása (más nézetből, külső
  szerkesztésből) felülírja a mezőt, ha nincs benne befejezetlen szerkesztés.
-->
<script lang="ts">
  import { onDestroy, untrack } from 'svelte';
  import type { BazisHiba } from './tipusok';

  interface Props {
    /** a mentett szöveg */
    ertek: string;
    cimke: string;
    ellenorzes: (szoveg: string) => Promise<BazisHiba[]>;
    /** igaz, ha a szöveg beíródott */
    alkalmaz: (szoveg: string) => Promise<boolean>;
    sorok?: number;
    mono?: boolean;
    helyorzo?: string;
    /** az Alkalmaz gomb felirata */
    gomb?: string;
    /** üres szöveg is alkalmazható (a szűrő törlése) */
    uresEngedett?: boolean;
  }
  let { ertek, cimke, ellenorzes, alkalmaz, sorok = 3, mono = true, helyorzo = '', gomb = 'Alkalmaz', uresEngedett = true }: Props = $props();

  let szoveg = $state(untrack(() => ertek));
  let mentett = $state(untrack(() => ertek));
  let hibak = $state<BazisHiba[]>([]);
  let dolgozik = $state(false);
  let ellenorzott = $state(true);
  let idozito: ReturnType<typeof setTimeout> | null = null;
  let sorszam = 0;

  const valtozott = $derived(szoveg !== mentett);
  const alkalmazhato = $derived(valtozott && ellenorzott && hibak.length === 0 && !dolgozik && (uresEngedett || szoveg.trim() !== ''));

  // a mentett érték követése: csak akkor írja felül a mezőt, ha a felhasználó nem szerkeszt
  $effect(() => {
    const uj = ertek;
    if (uj === mentett) return;
    if (szoveg === mentett) szoveg = uj;
    mentett = uj;
    ellenoriz();
  });

  function ellenoriz() {
    if (idozito) clearTimeout(idozito);
    ellenorzott = false;
    if (szoveg === mentett) {
      hibak = [];
      ellenorzott = true;
      return;
    }
    const n = ++sorszam;
    idozito = setTimeout(async () => {
      idozito = null;
      try {
        const h = await ellenorzes(szoveg);
        if (n !== sorszam) return;
        hibak = h;
      } catch (e) {
        if (n !== sorszam) return;
        hibak = [{ hely: 'ellenorzes', uzenet: e instanceof Error ? e.message : String(e) }];
      }
      ellenorzott = true;
    }, 300);
  }

  async function ment() {
    if (!alkalmazhato) return;
    dolgozik = true;
    const kuldott = szoveg;
    const ok = await alkalmaz(kuldott);
    dolgozik = false;
    if (ok) {
      mentett = kuldott;
      hibak = [];
      ellenorzott = true;
    }
  }

  function billentyu(e: KeyboardEvent) {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      void ment();
    } else if (e.key === 'Escape' && valtozott) {
      e.preventDefault();
      e.stopPropagation();
      szoveg = mentett;
      ellenoriz();
    }
  }

  onDestroy(() => idozito && clearTimeout(idozito));
</script>

<div class="mezo">
  <textarea
    class:mono
    rows={sorok}
    spellcheck="false"
    autocomplete="off"
    autocapitalize="off"
    aria-label={cimke}
    aria-invalid={hibak.length ? 'true' : undefined}
    placeholder={helyorzo}
    bind:value={szoveg}
    oninput={ellenoriz}
    onkeydown={billentyu}
  ></textarea>
  {#each hibak as h, i (i)}
    <p class="hiba" role="alert">{h.uzenet}</p>
  {/each}
  {#if valtozott}
    <div class="sor">
      <button type="button" class="m-gomb suru alkalmaz" disabled={!alkalmazhato} onclick={() => void ment()}>{dolgozik ? '…' : gomb}</button>
      <button
        type="button"
        class="m-gomb semleges suru masodlagos"
        onclick={() => {
          szoveg = mentett;
          ellenoriz();
        }}>Elvet</button
      >
      {#if !ellenorzott && !hibak.length}<span class="jelzes">ellenőrzés…</span>{/if}
    </div>
  {/if}
</div>

<style>
  .mezo {
    display: flex;
    flex-direction: column;
    gap: var(--t-1);
  }

  textarea {
    box-sizing: border-box;
    width: 100%;
    resize: vertical;
    padding: var(--t-1) var(--t-2);
    border: 1px solid var(--keret-mezo);
    border-radius: var(--kerekites-kicsi);
    background: var(--hatter);
    color: var(--szoveg);
    font: inherit;
  }

  textarea.mono {
    font-family: var(--betu-mono);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  textarea[aria-invalid='true'] {
    border-color: var(--hiba);
  }

  textarea:focus-visible {
    outline: var(--fokusz-vastag) solid var(--fokusz-gyuru);
    outline-offset: calc(-1 * var(--keret-vastag));
  }

  .hiba {
    margin: 0;
    color: var(--hiba);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  .sor {
    display: flex;
    align-items: center;
    gap: var(--t-2);
  }

  .jelzes {
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
  }
</style>
