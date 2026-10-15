<!--
  A C++ AI-segítség a `.cpp` fül alján (C36b), csak kattintásra: „Mi a hiba?”, „Tipp” (lépcsőzetes felfedés; a teljes
  megoldás csak külön megerősítéssel), „Szélső tesztek”, „Stressz-teszt”. Ami fordítással vagy futtatással ellenőrizhető,
  „ellenőrizve” jelet kap, a többi „nem ellenőrzött”. A javaslat sosem íródik magától: a „Hozzáadás a feladathoz” és a
  „Beillesztés” a felhasználó egy szerkesztő-tranzakciója (`aiElfogad.ts`). Kalibrált modell nélkül a gombok tiltva, a sáv
  megmondja, miért (D9). Csak tokenből rajzol (25. döntés).
-->
<script lang="ts">
  import { untrack } from 'svelte';
  import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
  import { fajlNev } from '../lib/vault/fajlok.svelte';
  import { vagolapra } from '../szerkeszto/vagolap';
  import { AI_MOD_NEV, kodAI, type AIMod } from './ai.svelte';
  import { megoldasBeilleszt, tesztBeszur } from './aiElfogad';

  let {
    ut,
    onker,
    onugras,
  }: {
    ut: string;
    onker: (mod: AIMod, megerosit?: boolean) => void;
    onugras: (sor: number) => void;
  } = $props();

  const GOMBOK: AIMod[] = ['hiba', 'tipp', 'teszt', 'stressz'];
  const ESET_NEV: Record<string, string> = {
    elteres: 'a megoldásod eltér',
    egyezik: 'egyezik',
    nem_ellenorzott: 'nincs ellenőrzött várt kimenet',
    sajat_hiba: 'a megoldásod nem futott le',
    referencia_hiba: 'a referencia nem futott le',
  };

  const futas = $derived(kodAI.aktiv?.cpp === ut ? kodAI.aktiv : null);
  const fut = $derived(kodAI.fut);
  const tiltva = $derived(!kodAI.kalibralt || fut);
  const e = $derived((futas?.eredmeny ?? null) as Record<string, any> | null);
  let megerosites = $state(false);
  let elsoJelentve = '';

  $effect(() => {
    const f = futas;
    if (f && f.mod === 'tipp' && f.eredmeny && elsoJelentve !== f.ai) {
      elsoJelentve = f.ai;
      untrack(() => void kodAI.elsoSzint());
    }
  });

  async function hozzaad(blokk: string) {
    const j = futas?.jegyzet;
    if (!j) {
      const ok = await vagolapra(blokk);
      ertesitesek.ertesit({ szint: 'info', cim: 'Nincs feladat-jegyzet', szoveg: ok ? 'A teszt-blokk a vágólapon van.' : 'A teszt-blokk nem másolható.' });
      return;
    }
    const r = await tesztBeszur(j, blokk);
    ertesitesek.ertesit(
      r.ok
        ? { szint: 'siker', cim: 'A teszt bekerült a feladatba', szoveg: fajlNev(j) }
        : { szint: 'hiba', cim: 'A teszt nem került be', szoveg: r.uzenet },
    );
  }

  async function beilleszt(kod: string) {
    const r = await megoldasBeilleszt(ut, kod);
    ertesitesek.ertesit(
      r.ok
        ? { szint: 'info', cim: 'A javított program a szerkesztőben', szoveg: 'A ⌘Z visszahozza a sajátodat.' }
        : { szint: 'hiba', cim: 'A beillesztés nem sikerült', szoveg: r.uzenet },
    );
  }

  function ellenorzottJel(ok: boolean) {
    return ok ? 'ellenőrizve' : 'nem ellenőrzött';
  }
</script>

<section class="kod-ai" aria-label="AI-segítség">
  <div class="sav">
    <span class="cim">AI</span>
    {#each GOMBOK as m (m)}
      <button type="button" class="gomb" disabled={tiltva} onclick={() => onker(m)}>{AI_MOD_NEV[m]}</button>
    {/each}
    {#if !kodAI.kalibralt}
      <span class="jel" title={kodAI.allapot?.indok ?? ''}>nincs kalibrált modell</span>
    {:else if futas?.allapot === 'fut'}
      <span class="jel" role="status">{futas.tokenek ? `${AI_MOD_NEV[futas.mod]}: ${futas.tokenek} token…` : `${AI_MOD_NEV[futas.mod]}: ellenőrzés…`}</span>
      <button type="button" class="gomb" onclick={() => void kodAI.megszakit()}>Megszakítás</button>
    {/if}
  </div>

  {#if futas && futas.allapot === 'hiba'}
    <p class="uzenet hiba" role="alert">{futas.hiba?.uzenet}</p>
  {:else if futas && futas.allapot === 'megszakitva'}
    <p class="uzenet">Megszakítva.</p>
  {:else if futas && e}
    <div class="eredmeny" aria-live="polite">
      {#if e.nincs_hiba}
        <p class="uzenet">{e.uzenet}</p>
      {:else if futas.mod === 'hiba'}
        <p class="sor">
          {#if e.sor}<button type="button" class="link" onclick={() => onugras(e.sor)}>{e.sor}. sor</button>{/if}
          {#if e.fajta_szoveg}<span class="halvany">· {e.fajta_szoveg}</span>{/if}
          <span class="jel" class:jo={e.ellenorzott}>{ellenorzottJel(!!e.ellenorzott)}</span>
        </p>
        <p class="szoveg">{e.magyarazat}</p>
      {:else if futas.mod === 'tipp'}
        <ol class="tippek">
          {#each (e.szintek ?? []).slice(0, Math.max(1, futas.felfedve)) as sz (sz.szint)}
            <li>
              <strong>{sz.cim}:</strong>
              {#if sz.kiszurve}<span class="halvany">(a tipp kódot tartalmazott, ezért nem mutatom)</span>
              {:else if sz.hianyzik}<span class="halvany">(ez a szint hiányzik a válaszból)</span>
              {:else}{sz.szoveg}{/if}
              {#if sz.szint === 3 && e.hely_sor}
                <button type="button" class="link" onclick={() => onugras(e.hely_sor)}>{e.hely_sor}. sor</button>
                <span class="jel" class:jo={e.ellenorzott}>{ellenorzottJel(!!e.ellenorzott)}</span>
              {/if}
            </li>
          {/each}
        </ol>
        <p class="muveletek">
          {#if futas.felfedve < 3}
            <button type="button" class="gomb" onclick={() => void kodAI.felfed()}>Következő tipp</button>
          {:else if !megerosites}
            <button type="button" class="gomb" disabled={tiltva} onclick={() => (megerosites = true)}>Teljes megoldás…</button>
          {:else}
            <span>A teljes megoldás elveszi a gyakorlás lényegét. Biztosan kéred?</span>
            <button type="button" class="gomb" onclick={() => { megerosites = false; onker('megoldas', true); }}>Igen, mutasd</button>
            <button type="button" class="gomb" onclick={() => (megerosites = false)}>Mégse</button>
          {/if}
        </p>
      {:else if futas.mod === 'megoldas'}
        <p class="sor">
          <span class="jel" class:jo={e.ellenorzott}>
            {e.ellenorzott ? `ellenőrizve: ${e.atment_db}/${e.ossz} teszt átment` : e.kod ? `nem ellenőrzött (${e.atment_db ?? 0}/${e.ossz ?? 0} teszt)` : 'nem ellenőrzött'}
          </span>
        </p>
        {#if e.magyarazat}<p class="szoveg">{e.magyarazat}</p>{/if}
        {#if e.kod}
          <pre class="kod">{e.kod}</pre>
          <p class="muveletek">
            <button type="button" class="gomb" onclick={() => void beilleszt(e.kod)}>Beillesztés a szerkesztőbe</button>
            <button type="button" class="gomb" onclick={() => void vagolapra(e.kod)}>Másolás</button>
          </p>
        {:else}<p class="uzenet">{e.uzenet}</p>{/if}
      {:else if futas.mod === 'teszt'}
        <p class="sor">
          <span class="jel" class:jo={e.referencia?.ellenorzott}>
            {e.referencia?.ellenorzott ? `a referencia a feladat ${e.referencia.ossz} tesztjén átment` : `nem ellenőrzött: ${e.referencia?.uzenet ?? ''}`}
          </span>
        </p>
        {#each e.esetek ?? [] as eset, i (i)}
          <div class="eset">
            <p class="sor"><span class="jel" class:rossz={eset.allapot === 'elteres' || eset.allapot === 'sajat_hiba'} class:jo={eset.allapot === 'egyezik'}>{ESET_NEV[eset.allapot] ?? eset.allapot}</span></p>
            <div class="harom">
              <div><span class="halvany">Bemenet</span><pre>{eset.bemenet}</pre></div>
              <div><span class="halvany">Várt</span><pre>{eset.vart ?? '—'}</pre></div>
              <div><span class="halvany">A tiéd</span><pre>{eset.kapott ?? '—'}</pre></div>
            </div>
            {#if eset.blokk}<button type="button" class="gomb" onclick={() => void hozzaad(eset.blokk)}>Hozzáadás a feladathoz</button>{/if}
          </div>
        {/each}
      {:else if futas.mod === 'stressz'}
        {#if e.ellenpelda}
          <p class="sor"><span class="jel rossz">eltérés a(z) {e.menet}. véletlen bemeneten</span>
            <span class="jel" class:jo={e.ellenorzott}>{ellenorzottJel(!!e.ellenorzott)}</span></p>
          <div class="harom">
            <div><span class="halvany">Bemenet</span><pre>{e.ellenpelda.bemenet}</pre></div>
            <div><span class="halvany">Várt</span><pre>{e.ellenpelda.vart}</pre></div>
            <div><span class="halvany">A tiéd</span><pre>{e.ellenpelda.kapott || '—'}</pre></div>
          </div>
          {#if e.ellenpelda.blokk}<button type="button" class="gomb" onclick={() => void hozzaad(e.ellenpelda.blokk)}>Hozzáadás a feladathoz</button>{/if}
        {:else}
          <p class="uzenet">{e.uzenet || `${e.menet} véletlen bemeneten nem találtam eltérést.`}</p>
        {/if}
      {/if}
      {#if futas.modell}<p class="halvany kicsi">Modell: {futas.modell}</p>{/if}
    </div>
  {/if}
</section>

<style>
  .kod-ai {
    flex: none;
    display: flex;
    flex-direction: column;
    max-height: 40%;
    min-height: 0;
    border-top: 1px solid var(--keret);
    background: var(--hatter-emelt);
    font-size: var(--betu-ui);
    line-height: var(--sor-ui);
    color: var(--szoveg);
  }

  .sav {
    flex: none;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--t-1);
    min-height: var(--magassag-fejlec);
    padding: 0 var(--t-3);
  }

  .cim {
    font-size: var(--betu-kicsi);
    color: var(--szoveg-halvany);
    margin-right: var(--t-1);
  }

  .gomb,
  .link {
    font: inherit;
    color: inherit;
    background: none;
    border: none;
    cursor: pointer;
    padding: 2px var(--t-2);
    border-radius: var(--kerekites-kicsi);
  }

  .gomb:hover:not(:disabled),
  .link:hover {
    background: var(--hatter-hover);
  }

  .gomb:disabled {
    color: var(--szoveg-halvany);
    cursor: default;
  }

  .gomb:focus-visible,
  .link:focus-visible {
    outline: var(--fokusz-vastag) solid var(--fokusz-gyuru);
    outline-offset: var(--fokusz-tav-befele);
  }

  .link {
    color: var(--akcent-szoveg);
  }

  .jel {
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    padding: 2px var(--t-2);
    border-radius: var(--kerekites-kicsi);
    color: var(--szoveg-masodlagos);
    background: var(--hatter-hover);
  }

  .jel.jo {
    color: var(--siker);
    background: var(--siker-hatter);
  }

  .jel.rossz {
    color: var(--hiba);
    background: var(--hiba-hatter);
  }

  .eredmeny {
    overflow: auto;
    padding: 0 var(--t-4) var(--t-3);
  }

  .uzenet,
  .szoveg,
  .sor,
  .muveletek {
    margin: var(--t-1) 0;
  }

  .uzenet {
    padding: 0 var(--t-4) var(--t-2);
    color: var(--szoveg-masodlagos);
  }

  .uzenet.hiba {
    color: var(--hiba);
  }

  .sor,
  .muveletek {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--t-2);
  }

  .szoveg {
    white-space: pre-wrap;
  }

  .tippek {
    margin: var(--t-1) 0;
    padding-left: var(--t-5);
  }

  .tippek li {
    margin: var(--t-1) 0;
  }

  .halvany {
    color: var(--szoveg-halvany);
  }

  .kicsi {
    font-size: var(--betu-kicsi);
  }

  pre {
    margin: 0;
    padding: var(--t-2);
    max-height: 12em;
    overflow: auto;
    font-family: var(--betu-mono);
    font-size: var(--betu-kicsi);
    background: var(--hatter-kod);
    border-radius: var(--kerekites-kicsi);
    white-space: pre;
  }

  .eset {
    margin: var(--t-2) 0;
  }

  .harom {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--t-2);
    margin: var(--t-1) 0;
  }
</style>
