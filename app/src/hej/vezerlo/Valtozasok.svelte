<!--
  „Mit változtatott” (C17): a feladat gépi commitjai körönként (`Mos-Feladat` trailer), fájlonként +/− számmal; a fájlra
  kattintva a változás összevetése nyílik. A kör egy mozdulattal visszavonható (a meglévő `visszavonas {kor}` végponton,
  revert-commitként, a kör-zár alatt); a már visszavont kört jelzi.
-->
<script lang="ts">
  import { untrack } from 'svelte';
  import { ApiHiba } from '../../lib/core/api';
  import { ertesitesek } from '../../lib/ertesites/ertesites.svelte';
  import Ikon from '../../lib/ikon/Ikon.svelte';
  import { Undo2 } from '../../lib/ikon/ikonok';
  import { kornyezet } from '../../lib/kornyezet';
  import { vezerloApi } from '../../lib/vezerlo/api';
  import { utReszei } from '../../lib/vezerlo/megjelenites';
  import { LEZART, type Feladat, type ValtozasFajl, type Valtozasok } from '../../lib/vezerlo/tipusok';
  import FeladatDiff from './FeladatDiff.svelte';

  let { feladat }: { feladat: Feladat } = $props();
  const { kapcsolat } = kornyezet();

  let adat = $state.raw<Valtozasok | null>(null);
  let hiba = $state<string | null>(null);
  let megerosit = $state<string | null>(null);
  let dolgozik = $state(false);
  let visszaHiba = $state<{ uzenet: string; fajlok: string[] } | null>(null);
  let diff = $state<{ fajl: ValtozasFajl; sha: string } | null>(null);
  let sorszam = 0;

  async function betolt() {
    const s = ++sorszam;
    try {
      const d = await vezerloApi.valtozasok(feladat.id);
      if (s === sorszam) {
        adat = d;
        hiba = null;
      }
    } catch (e) {
      if (s === sorszam) hiba = e instanceof ApiHiba ? e.message : String(e);
    }
  }

  // betöltés, és újra, ha a feladat véget ér, vagy bármely visszavonás történt
  $effect(() => {
    void feladat.id;
    void betolt();
    return kapcsolat.figyel('visszavonas', () => void betolt());
  });
  let elozoAllapot = untrack(() => feladat.allapot);
  $effect(() => {
    const a = feladat.allapot;
    if (a !== elozoAllapot && LEZART.has(a)) void betolt();
    elozoAllapot = a;
  });

  async function visszavon(kor: string) {
    dolgozik = true;
    visszaHiba = null;
    try {
      await vezerloApi.visszavon(kor);
      ertesitesek.ertesit({ szint: 'siker', cim: 'Visszavonva', szoveg: `${feladat.cim} — ${kor}` });
      megerosit = null;
      await betolt();
    } catch (e) {
      const fajlok = e instanceof ApiHiba && Array.isArray(e.adat.fajlok) ? (e.adat.fajlok as string[]) : [];
      visszaHiba = { uzenet: e instanceof ApiHiba ? e.message : String(e), fajlok };
    } finally {
      dolgozik = false;
    }
  }

  const darab = (n: number | null) => (n === null ? 'bin' : String(n));
</script>

{#if hiba}
  <p class="hiba" role="alert">{hiba}</p>
{:else if !adat}
  <p class="halvany" role="status">Betöltés…</p>
{:else if adat.nincs_tar}
  <p class="halvany">A vault pillanatkép-tárolója nem érhető el, a változások nem listázhatók.</p>
{:else if !adat.korok.length}
  <p class="halvany">
    {#if feladat.forras !== '2.0'}Ehhez a feladathoz nem érhető el változás-előzmény.{:else if !LEZART.has(feladat.allapot)}Eddig nem írt a vaultba.{:else}Nem írt a vaultba.{/if}
  </p>
{:else}
  {#each adat.korok as kor (kor.kor)}
    <section class="kor" aria-label={`Kör: ${kor.kor}`}>
      <header>
        <span class="kor-nev">{kor.kor}</span>
        {#if kor.visszavonva}
          <span class="jelzo">visszavonva</span>
        {:else if kor.visszavonhato}
          {#if megerosit === kor.kor}
            <span class="megerosit">
              <button type="button" class="m-gomb semleges gomb" disabled={dolgozik} onclick={() => (megerosit = null)}>Mégse</button>
              <button type="button" class="m-gomb semleges gomb veszely" disabled={dolgozik} onclick={() => visszavon(kor.kor)}>Visszavonás</button>
            </span>
          {:else}
            <button type="button" class="m-gomb semleges gomb" onclick={() => ((megerosit = kor.kor), (visszaHiba = null))}>
              <Ikon ikon={Undo2} meret={14} /> Visszavonás
            </button>
          {/if}
        {/if}
      </header>
      {#if megerosit === kor.kor}
        <p class="figy">A kör változásai visszafordulnak (új commit); ez is visszavonható. A kézi szerkesztéseid nem sérülnek.</p>
      {/if}
      {#if visszaHiba && megerosit === kor.kor}
        <div class="hiba" role="alert">
          {visszaHiba.uzenet}
          {#if visszaHiba.fajlok.length}<ul>{#each visszaHiba.fajlok as f (f)}<li>{f}</li>{/each}</ul>{/if}
        </div>
      {/if}
      {#each kor.commitok as c (c.sha)}
        <ul class="fajlok" aria-label={c.targy}>
          {#each c.fajlok as f (f.ut)}
            {@const r = utReszei(f.ut)}
            <li>
              <button type="button" class="fajl" title={f.ut} onclick={() => (diff = { fajl: f, sha: c.sha })}>
                <span class="all a-{f.allapot}" aria-label={f.allapot === 'A' ? 'új' : f.allapot === 'D' ? 'törölve' : 'módosítva'}>{f.allapot}</span>
                <span class="nev"><b>{r.nev}</b>{#if r.mappa}<small>{r.mappa}</small>{/if}</span>
                <span class="szam"><i class="p">+{darab(f.plusz)}</i><i class="m">−{darab(f.minusz)}</i></span>
              </button>
            </li>
          {/each}
        </ul>
      {/each}
    </section>
  {/each}
  {#if adat.levagva}
    <p class="halvany" role="status">A lista csonka: a feladatnak ennél több gépi commitja van, csak a legfrissebbek látszanak.</p>
  {/if}
{/if}

{#if diff}
  <FeladatDiff fajl={diff.fajl} sha={diff.sha} onbezar={() => (diff = null)} />
{/if}

<style>
  .halvany {
    margin: 0;
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
  }

  .hiba {
    margin: var(--t-1) 0;
    padding: var(--t-2);
    border-radius: var(--kerekites);
    background: var(--hiba-hatter);
    color: var(--hiba);
    font-size: var(--betu-kicsi);
  }

  .hiba ul {
    margin: var(--t-1) 0 0;
    padding-left: var(--t-4);
  }

  .kor + .kor {
    margin-top: var(--t-3);
  }

  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--t-2);
    min-height: var(--magassag-sor);
  }

  .kor-nev {
    font-family: var(--betu-mono);
    font-size: var(--betu-kicsi);
    color: var(--szoveg-masodlagos);
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .jelzo {
    font-size: var(--betu-kicsi);
    color: var(--figyelmeztetes);
  }

  .figy {
    margin: var(--t-1) 0;
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    color: var(--figyelmeztetes);
  }

  .megerosit {
    display: inline-flex;
    gap: var(--t-1);
  }

  .gomb {
    display: inline-flex;
    align-items: center;
    gap: var(--t-1);
    height: var(--magassag-suru);
    padding: 0 var(--t-2);
  }

  .gomb.veszely {
    border-color: var(--hiba);
    color: var(--hiba);
  }

  .fajlok {
    list-style: none;
    margin: 0;
    padding: 0;
    margin-inline: calc(-1 * var(--t-2));
  }

  .fajl {
    display: flex;
    align-items: center;
    gap: var(--t-2);
    width: 100%;
    height: var(--magassag-sor);
    padding: 0 var(--t-2);
    border-radius: var(--kerekites);
    text-align: left;
  }

  .fajl:hover {
    background: var(--hatter-hover);
  }

  .fajl:focus-visible {
    outline-offset: var(--fokusz-tav-befele);
  }

  .all {
    flex: none;
    width: 14px;
    text-align: center;
    font-size: var(--betu-kicsi);
    font-weight: var(--suly-felkover);
  }

  .a-A {
    color: var(--siker);
  }

  .a-D {
    color: var(--hiba);
  }

  .a-M {
    color: var(--figyelmeztetes);
  }

  .nev {
    flex: 1;
    display: flex;
    align-items: baseline;
    gap: var(--t-2);
    min-width: 0;
  }

  .nev b {
    font-weight: var(--suly-kozepes);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .nev small {
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .szam {
    flex: none;
    display: inline-flex;
    gap: var(--t-1);
    font-size: var(--betu-kicsi);
    font-variant-numeric: tabular-nums;
  }

  .szam i {
    font-style: normal;
  }

  .p {
    color: var(--siker);
  }

  .m {
    color: var(--hiba);
  }
</style>
