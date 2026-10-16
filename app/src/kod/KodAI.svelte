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
  import { t, tk } from '../lib/i18n';
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
    elteres: tk('a megoldásod eltér'),
    egyezik: tk('egyezik'),
    nem_ellenorzott: tk('nincs ellenőrzött várt kimenet'),
    sajat_hiba: tk('a megoldásod nem futott le'),
    referencia_hiba: tk('a referencia nem futott le'),
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
      ertesitesek.ertesit({ szint: 'info', cim: t('Nincs feladat-jegyzet'), szoveg: ok ? t('A teszt-blokk a vágólapon van.') : t('A teszt-blokk nem másolható.') });
      return;
    }
    const r = await tesztBeszur(j, blokk);
    ertesitesek.ertesit(
      r.ok
        ? { szint: 'siker', cim: t('A teszt bekerült a feladatba'), szoveg: fajlNev(j) }
        : { szint: 'hiba', cim: t('A teszt nem került be'), szoveg: r.uzenet },
    );
  }

  async function beilleszt(kod: string) {
    const r = await megoldasBeilleszt(ut, kod);
    ertesitesek.ertesit(
      r.ok
        ? { szint: 'info', cim: t('A javított program a szerkesztőben'), szoveg: t('A ⌘Z visszahozza a sajátodat.') }
        : { szint: 'hiba', cim: t('A beillesztés nem sikerült'), szoveg: r.uzenet },
    );
  }

  function ellenorzottJel(ok: boolean) {
    return ok ? t('ellenőrizve') : t('nem ellenőrzött');
  }
</script>

<section class="kod-ai" aria-label={t('AI-segítség')}>
  <div class="sav">
    <span class="cim">{t('AI')}</span>
    {#each GOMBOK as m (m)}
      <button type="button" class="gomb" disabled={tiltva} onclick={() => onker(m)}>{t(AI_MOD_NEV[m])}</button>
    {/each}
    {#if !kodAI.kalibralt}
      <span class="jel" title={kodAI.allapot?.indok ?? ''}>{t('nincs kalibrált modell')}</span>
    {:else if futas?.allapot === 'fut'}
      <span class="jel" role="status">{futas.tokenek ? t('{mod}: {n} token…', { mod: t(AI_MOD_NEV[futas.mod]), n: futas.tokenek }) : t('{mod}: ellenőrzés…', { mod: t(AI_MOD_NEV[futas.mod]) })}</span>
      <button type="button" class="gomb" onclick={() => void kodAI.megszakit()}>{t('Megszakítás')}</button>
    {/if}
  </div>

  {#if futas && futas.allapot === 'hiba'}
    <p class="uzenet hiba" role="alert">{futas.hiba?.uzenet}</p>
  {:else if futas && futas.allapot === 'megszakitva'}
    <p class="uzenet">{t('Megszakítva.')}</p>
  {:else if futas && e}
    <div class="eredmeny" aria-live="polite">
      {#if e.nincs_hiba}
        <p class="uzenet">{e.uzenet}</p>
      {:else if futas.mod === 'hiba'}
        <p class="sor">
          {#if e.sor}<button type="button" class="link" onclick={() => onugras(e.sor)}>{t('{n}. sor', { n: e.sor })}</button>{/if}
          {#if e.fajta_szoveg}<span class="halvany">· {e.fajta_szoveg}</span>{/if}
          <span class="jel" class:jo={e.ellenorzott}>{ellenorzottJel(!!e.ellenorzott)}</span>
        </p>
        <p class="szoveg">{e.magyarazat}</p>
      {:else if futas.mod === 'tipp'}
        <ol class="tippek">
          {#each (e.szintek ?? []).slice(0, Math.max(1, futas.felfedve)) as sz (sz.szint)}
            <li>
              <strong>{sz.cim}:</strong>
              {#if sz.kiszurve}<span class="halvany">{t('(a tipp kódot tartalmazott, ezért nem mutatom)')}</span>
              {:else if sz.hianyzik}<span class="halvany">{t('(ez a szint hiányzik a válaszból)')}</span>
              {:else}{sz.szoveg}{/if}
              {#if sz.szint === 3 && e.hely_sor}
                <button type="button" class="link" onclick={() => onugras(e.hely_sor)}>{t('{n}. sor', { n: e.hely_sor })}</button>
                <span class="jel" class:jo={e.ellenorzott}>{ellenorzottJel(!!e.ellenorzott)}</span>
              {/if}
            </li>
          {/each}
        </ol>
        <p class="muveletek">
          {#if futas.felfedve < 3}
            <button type="button" class="gomb" onclick={() => void kodAI.felfed()}>{t('Következő tipp')}</button>
          {:else if !megerosites}
            <button type="button" class="gomb" disabled={tiltva} onclick={() => (megerosites = true)}>{t('Teljes megoldás…')}</button>
          {:else}
            <span>{t('A teljes megoldás elveszi a gyakorlás lényegét. Biztosan kéred?')}</span>
            <button type="button" class="gomb" onclick={() => { megerosites = false; onker('megoldas', true); }}>{t('Igen, mutasd')}</button>
            <button type="button" class="gomb" onclick={() => (megerosites = false)}>{t('Mégse')}</button>
          {/if}
        </p>
      {:else if futas.mod === 'megoldas'}
        <p class="sor">
          <span class="jel" class:jo={e.ellenorzott}>
            {e.ellenorzott ? t('ellenőrizve: {atment}/{ossz} teszt átment', { atment: e.atment_db, ossz: e.ossz }) : e.kod ? t('nem ellenőrzött ({atment}/{ossz} teszt)', { atment: e.atment_db ?? 0, ossz: e.ossz ?? 0 }) : t('nem ellenőrzött')}
          </span>
        </p>
        {#if e.magyarazat}<p class="szoveg">{e.magyarazat}</p>{/if}
        {#if e.kod}
          <pre class="kod">{e.kod}</pre>
          <p class="muveletek">
            <button type="button" class="gomb" onclick={() => void beilleszt(e.kod)}>{t('Beillesztés a szerkesztőbe')}</button>
            <button type="button" class="gomb" onclick={() => void vagolapra(e.kod)}>{t('Másolás')}</button>
          </p>
        {:else}<p class="uzenet">{e.uzenet}</p>{/if}
      {:else if futas.mod === 'teszt'}
        <p class="sor">
          <span class="jel" class:jo={e.referencia?.ellenorzott}>
            {e.referencia?.ellenorzott ? t('a referencia a feladat {ossz} tesztjén átment', { ossz: e.referencia.ossz }) : t('nem ellenőrzött: {uzenet}', { uzenet: e.referencia?.uzenet ?? '' })}
          </span>
        </p>
        {#each e.esetek ?? [] as eset, i (i)}
          <div class="eset">
            <p class="sor"><span class="jel" class:rossz={eset.allapot === 'elteres' || eset.allapot === 'sajat_hiba'} class:jo={eset.allapot === 'egyezik'}>{ESET_NEV[eset.allapot] ? t(ESET_NEV[eset.allapot]) : eset.allapot}</span></p>
            <div class="harom">
              <div><span class="halvany">{t('Bemenet')}</span><pre>{eset.bemenet}</pre></div>
              <div><span class="halvany">{t('Várt')}</span><pre>{eset.vart ?? '—'}</pre></div>
              <div><span class="halvany">{t('A tiéd')}</span><pre>{eset.kapott ?? '—'}</pre></div>
            </div>
            {#if eset.blokk}<button type="button" class="gomb" onclick={() => void hozzaad(eset.blokk)}>{t('Hozzáadás a feladathoz')}</button>{/if}
          </div>
        {/each}
      {:else if futas.mod === 'stressz'}
        {#if e.ellenpelda}
          <p class="sor"><span class="jel rossz">{t('eltérés a(z) {n}. véletlen bemeneten', { n: e.menet })}</span>
            <span class="jel" class:jo={e.ellenorzott}>{ellenorzottJel(!!e.ellenorzott)}</span></p>
          <div class="harom">
            <div><span class="halvany">{t('Bemenet')}</span><pre>{e.ellenpelda.bemenet}</pre></div>
            <div><span class="halvany">{t('Várt')}</span><pre>{e.ellenpelda.vart}</pre></div>
            <div><span class="halvany">{t('A tiéd')}</span><pre>{e.ellenpelda.kapott || '—'}</pre></div>
          </div>
          {#if e.ellenpelda.blokk}<button type="button" class="gomb" onclick={() => void hozzaad(e.ellenpelda.blokk)}>{t('Hozzáadás a feladathoz')}</button>{/if}
        {:else}
          <p class="uzenet">{e.uzenet || t('{n} véletlen bemeneten nem találtam eltérést.', { n: e.menet })}</p>
        {/if}
      {/if}
      {#if futas.modell}<p class="halvany kicsi">{t('Modell: {modell}', { modell: futas.modell })}</p>{/if}
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
