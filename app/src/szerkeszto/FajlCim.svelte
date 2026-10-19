<script lang="ts">
  import { onDestroy, tick, untrack } from 'svelte';
  import { t } from '../lib/i18n';
  import { fajlNev, mappa } from '../lib/vault/fajlok.svelte';
  import { kornyezet } from '../lib/kornyezet';
  import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
  import { modalisNyitva } from '../lib/fokusz/hatokor';
  import { fokuszban } from '../lib/fokusz/fokusz';
  import { beallitasAblak } from '../beallitasok/allapot.svelte';
  import { egeszsegAblak } from '../lib/egeszseg/allapot.svelte';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { ChevronRight, TriangleAlert } from '../lib/ikon/ikonok';
  import { szerkesztok } from './szerkesztok.svelte';
  import { atnevezesTerv, atnevezesVegrehajt, atnevezesErtesites } from './linkek/atnevezes';

  let { ut, irhato = true, aktiv = true, hajthato = false, hajtott = false, onhajtas, onkesz }: {
    ut: string; irhato?: boolean; aktiv?: boolean; hajthato?: boolean; hajtott?: boolean;
    onhajtas?: () => void; onkesz?: () => void;
  } = $props();
  const { felulet } = kornyezet();
  let dolgozik = $state(false);
  let hiba = $state('');
  let piszkozat = $state(untrack(() => fajlNev(ut)));
  let mezo: HTMLInputElement | undefined = $state();
  let gyoker: HTMLDivElement | undefined = $state();
  let eloUt = untrack(() => ut);
  let el = true;
  let sorszam = 0;
  let ime = false;
  let blurElvet = false;
  let keszNev: string | null = null;
  onDestroy(() => { el = false; sorszam++; });
  $effect(() => {
    const most = ut;
    if (most !== eloUt) untrack(() => {
      eloUt = most; sorszam++; piszkozat = fajlNev(most); hiba = ''; dolgozik = false; keszNev = null; blurElvet = false; ime = false;
    });
  });

  export function fokusz(): void {
    const cel = mezo && !mezo.disabled ? mezo : gyoker;
    cel?.focus({ preventScroll: true });
    cel?.scrollIntoView({ block: 'nearest' });
  }

  // A Setup/Settings/Health és a komponáló is a közös modális hatókörbe lép. A két külön ablak flagje
  // az Atfedes mountja előtti pillanatot is lefedi; a paletta a felület saját állapota.
  const modalisAkadaly = () => felulet.atfedes !== null || modalisNyitva() || beallitasAblak.nyitva || egeszsegAblak.nyitva;
  function fokuszAtveheto(): boolean {
    const f = fokuszban();
    return !modalisAkadaly() && (!f || !!gyoker?.contains(f));
  }

  async function ment(visszaFokusz = false) {
    const regi = ut;
    const nev = piszkozat.trim();
    if (!el || !aktiv || !irhato || ime || dolgozik || modalisAkadaly()) return;
    if (!nev || nev === fajlNev(regi) || nev === keszNev) {
      if (!nev) piszkozat = fajlNev(regi);
      if (visszaFokusz && fokuszAtveheto()) onkesz?.();
      return;
    }
    const en = ++sorszam;
    const ervenyes = () => el && aktiv && irhato && ut === regi && en === sorszam && !modalisAkadaly();
    const uj = [mappa(regi), nev + (nev.toLowerCase().endsWith('.md') ? '' : '.md')].filter(Boolean).join('/');
    if (uj === regi) { piszkozat = fajlNev(regi); if (visszaFokusz && fokuszAtveheto()) onkesz?.(); return; }
    dolgozik = true; hiba = '';
    let elkuldve = false;
    try {
      await szerkesztok.dokumentumok.mindLezar();
      if (!ervenyes()) return;
      const terv = await atnevezesTerv(regi, uj);
      // A közben megnyitott Setup/egyéb Atfedes előbb beléphet a meglévő fókusz-hatókörbe.
      await tick();
      if (!ervenyes()) return;
      if (!terv.ok || terv.blokkolok.length) throw new Error(terv.blokkolok.join(' ') || t('Az átnevezés nem lehetséges.'));
      if (terv.fajlok?.length || terv.figyelmeztetesek?.length) {
        if (!fokuszAtveheto()) return;
        // A fájlfa meglévő terv-átfedése: több fájlt érintő változás látható a végrehajtás előtt.
        piszkozat = fajlNev(regi);
        blurElvet = true;
        felulet.atnevezes = { ut: regi, mod: 'nev', nev };
        felulet.atfedes = 'atnevezes';
        return;
      }
      const r = await atnevezesVegrehajt(regi, uj, terv.terv_hash, () => {
        const igen = ervenyes();
        if (igen) elkuldve = true; // közvetlenül a meglévő szolgáltatás POST-ja előtt
        return igen;
      });
      // A befejezett írás eredménye/Undo bezárt nézet után is látszik; fókuszt csak az élő kérő kap.
      atnevezesErtesites(r, felulet);
      if (!ervenyes()) return;
      keszNev = nev;
      if (visszaFokusz && fokuszAtveheto()) onkesz?.();
    } catch (e) {
      const uzenet = e instanceof Error ? e.message : String(e);
      if (ervenyes()) {
        dolgozik = false;
        hiba = uzenet; // A szerkesztett név megmarad: javítható és újrapróbálható.
        await tick();
        if (ervenyes() && visszaFokusz && fokuszAtveheto() && !fokuszban()) fokusz();
      } else if (elkuldve) {
        ertesitesek.ertesit({ szint: 'hiba', cim: t('s1.cim.rename_failed'), szoveg: `${regi}: ${uzenet}`, idotartam: 0 });
      }
    } finally {
      if (el && ut === regi && en === sorszam) dolgozik = false;
    }
  }
</script>

<div class="fajlcim" role="heading" aria-level="1" tabindex="-1" bind:this={gyoker}>
  {#if hajthato}
    <button type="button" class="hajto" class:csukva={hajtott} aria-expanded={!hajtott} aria-label={hajtott ? t('Kibontás') : t('Összecsukás')} onclick={onhajtas}><Ikon ikon={ChevronRight} meret={14} /></button>
  {/if}
  <input bind:this={mezo} aria-label={t('Jegyzet fájlneve')} title={t('Fájlnév szerkesztése — a tartalom címsora ettől független')}
    bind:value={piszkozat} disabled={!irhato || dolgozik} spellcheck="false" autocomplete="off"
    oninput={() => { keszNev = null; hiba = ''; blurElvet = false; }}
    oncompositionstart={() => (ime = true)} oncompositionend={() => (ime = false)}
    onblur={() => { if (blurElvet) { blurElvet = false; return; } void ment(); }}
    onkeydown={(e) => {
      if (e.isComposing || ime) return;
      if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); blurElvet = true; void ment(true); }
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); sorszam++; dolgozik = false; piszkozat = fajlNev(ut); hiba = ''; blurElvet = true; if (fokuszAtveheto()) onkesz?.(); }
    }} />
  {#if hiba}<p class="hiba" role="alert"><Ikon ikon={TriangleAlert} meret={14} />{hiba}</p>{/if}
</div>

<style>
  .fajlcim { position: relative; width: 100%; flex: none; max-width: var(--olvasasi-szelesseg); margin: 0 auto; padding: var(--t-2) var(--t-6); box-sizing: border-box; }
  input { width: 100%; border: 0; background: transparent; color: var(--szoveg); font: inherit;
    font-size: var(--betu-h2); font-weight: var(--suly-felkover); padding: var(--t-1) 0; }
  .hajto { position: absolute; left: var(--t-2); top: var(--t-3); display: grid; place-items: center; width: var(--magassag-suru); height: var(--magassag-suru); color: var(--szoveg-halvany); }
  .hajto:not(.csukva) :global(svg) { transform: rotate(90deg); }
  .hiba { display: flex; align-items: center; gap: var(--t-1); color: var(--hiba); font-size: var(--betu-kicsi); }
</style>
