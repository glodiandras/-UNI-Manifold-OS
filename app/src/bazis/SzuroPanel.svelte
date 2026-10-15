<!--
  Szűrők és képletek (C12b): a szűrő és a képlet **szövegként** szerkeszthető, élő ellenőrzéssel (a core elemzi,
  a hiba a mező alatt áll). A „Minden nézetre” szűrő a fájl `filters` kulcsa, az „Ez a nézet” a nézeté; az
  egyetlen kifejezés mellett and/or/not YAML-szerkezet is írható. A képletek a `formulas` kulcsba kerülnek,
  és oszlopként (`formula.név`) jelölhetők ki az Oszlopok panelen.
-->
<script lang="ts">
  import type { BazisModell } from './modell.svelte';
  import SzovegMezo from './SzovegMezo.svelte';
  import type { BazisHiba, Muvelet, Valasz } from './tipusok';

  let { modell, v }: { modell: BazisModell; v: Valasz } = $props();

  const nezet = $derived(v.nezet?.index ?? 0);
  const fajl = $derived(v.fajl);
  let ujNev = $state('');

  const szuroMuvelet = (hol: 'globalis' | number, yaml: string): Muvelet => ({ fajta: 'szuro_beallit', hol, yaml });
  const kepletMuvelet = (nev: string, kifejezes: string | null): Muvelet => ({ fajta: 'keplet_beallit', nev, kifejezes });

  const ellenorzes = (m: Muvelet) => async (): Promise<BazisHiba[]> => (await modell.modosit(m)).hibak;

  async function alkalmaz(m: Muvelet): Promise<boolean> {
    const r = await modell.alkalmaz(m);
    return r.ok && r.irva;
  }

  const ujNevErvenyes = $derived(ujNev.trim() !== '' && !(ujNev.trim() in (fajl?.kepletek ?? {})));
</script>

{#if fajl}
  <div class="szuro">
    <section>
      <h4>Szűrő — minden nézetre</h4>
      <SzovegMezo
        cimke="Szűrő minden nézetre"
        ertek={fajl.szuro}
        helyorzo={'file.hasTag("könyv")'}
        sorok={3}
        ellenorzes={(s) => ellenorzes(szuroMuvelet('globalis', s))()}
        alkalmaz={(s) => alkalmaz(szuroMuvelet('globalis', s))}
      />
    </section>
    <section>
      <h4>Szűrő — {v.nezet?.nev ?? 'ez a nézet'}</h4>
      <SzovegMezo
        cimke="Szűrő erre a nézetre"
        ertek={fajl.szuro_nezet}
        helyorzo={'Status != "kész"'}
        sorok={3}
        ellenorzes={(s) => ellenorzes(szuroMuvelet(nezet, s))()}
        alkalmaz={(s) => alkalmaz(szuroMuvelet(nezet, s))}
      />
    </section>
    <p class="segito">
      Egy kifejezés (<code>ar &gt; 100</code>), vagy and / or / not szerkezet YAML-ban. Üres mező: nincs szűrő.
    </p>
    <section>
      <h4>Képletek</h4>
      {#each Object.entries(fajl.kepletek) as [nev, kif] (nev)}
        <div class="keplet">
          <div class="keplet-fej">
            <code>formula.{nev}</code>
            <button type="button" class="torol" onclick={() => void alkalmaz(kepletMuvelet(nev, null))}>Törlés</button>
          </div>
          <SzovegMezo
            cimke="{nev} képlet"
            ertek={kif}
            sorok={2}
            uresEngedett={false}
            ellenorzes={(s) => ellenorzes(kepletMuvelet(nev, s))()}
            alkalmaz={(s) => alkalmaz(kepletMuvelet(nev, s))}
          />
        </div>
      {/each}
      <div class="keplet uj">
        <input
          class="nev"
          type="text"
          placeholder="Új képlet neve"
          aria-label="Új képlet neve"
          autocapitalize="off"
          spellcheck="false"
          bind:value={ujNev}
        />
        {#if ujNevErvenyes}
          {#key ujNev.trim()}
            <SzovegMezo
              cimke="{ujNev.trim()} képlet"
              ertek=""
              sorok={2}
              uresEngedett={false}
              helyorzo={'price * quantity'}
              gomb="Létrehoz"
              ellenorzes={(s) => ellenorzes(kepletMuvelet(ujNev.trim(), s))()}
              alkalmaz={async (s) => {
                const ok = await alkalmaz(kepletMuvelet(ujNev.trim(), s));
                if (ok) ujNev = '';
                return ok;
              }}
            />
          {/key}
        {:else if ujNev.trim() !== ''}
          <p class="segito">Ilyen nevű képlet már van.</p>
        {/if}
      </div>
    </section>
  </div>
{/if}

<style>
  .szuro {
    display: flex;
    flex-direction: column;
    gap: var(--t-3);
  }

  h4 {
    margin: 0 0 var(--t-1);
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
    font-weight: var(--suly-kozepes);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .segito {
    margin: 0;
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  code {
    font-family: var(--betu-mono);
    font-size: var(--betu-kicsi);
  }

  .keplet {
    display: flex;
    flex-direction: column;
    gap: var(--t-1);
    margin-bottom: var(--t-2);
  }

  .keplet-fej {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .torol {
    border: 0;
    background: transparent;
    color: var(--szoveg-halvany);
    font: inherit;
    font-size: var(--betu-kicsi);
    cursor: pointer;
  }

  .torol:hover {
    color: var(--hiba);
  }

  .nev {
    box-sizing: border-box;
    width: 100%;
    height: 26px;
    padding: 0 var(--t-2);
    border: 1px solid var(--keret-mezo);
    border-radius: var(--kerekites-kicsi);
    background: var(--hatter);
    color: var(--szoveg);
    font: inherit;
  }
</style>
