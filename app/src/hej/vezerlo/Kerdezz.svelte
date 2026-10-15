<!-- „Kérdezz a vaulttól” (C25b; TERV 5.7, 58(d)): a válasz mondatonként érkezik (folyam), mindegyik a forrásával — a jegyzet
     blokkjára vagy fejezetére mutató linkkel és a jegyzet szó szerinti mondatával. Forrás nélkül nem válaszol. A válasz a vaultba
     nem íródik; a kattintás a forrás sorára nyit. -->
<script lang="ts">
  import { onDestroy } from 'svelte';
  import { kornyezet } from '../../lib/kornyezet';
  import { kerdezzAllapot as a, vegeSzoveg, type KerdezzMondat } from '../../lib/kereses/kerdezz.svelte';
  import { fajlNev } from '../../lib/vault/fajlok.svelte';
  import { nyitasMod } from '../../szerkeszto/linkek/navigacio';
  import { szerkesztok } from '../../szerkeszto/szerkesztok.svelte';

  const { felulet } = kornyezet();
  let szoveg = $state(a.kerdes);

  onDestroy(() => a.megszakit());

  function nyit(ut: string, sor: number, e: { metaKey: boolean; ctrlKey: boolean; altKey: boolean }) {
    felulet.munkaterulet.megnyit(ut, nyitasMod(e));
    szerkesztok.ugras(ut, sor, 0);
  }
  const hely = (m: KerdezzMondat) => [fajlNev(m.ut), ...m.fejezet.slice(-1)].join(' › ');
</script>

<form
  onsubmit={(e) => {
    e.preventDefault();
    void a.kerdez(szoveg);
  }}
>
  <label class="cimke" for="kerdezz-mezo">Kérdés a jegyzeteidhez</label>
  <input id="kerdezz-mezo" type="text" bind:value={szoveg} maxlength="2000" autocomplete="off" spellcheck="false" />
  <div class="sor">
    {#if a.fut}
      <button type="button" class="m-gomb semleges gomb" onclick={() => a.megszakit()}>Állj</button>
      <span class="halvany" aria-live="polite">{a.mondatok.length ? 'Válaszol…' : a.forrasok.length ? 'Gondolkodik…' : 'Forrásokat keres…'}</span>
    {:else}
      <button type="submit" class="m-gomb semleges gomb" disabled={!szoveg.trim()}>Kérdezz</button>
    {/if}
  </div>
</form>

{#if a.hiba}<p class="hiba" role="alert">{a.hiba}</p>{/if}

{#if a.mondatok.length}
  <ol class="valasz" aria-label="Válasz">
    {#each a.mondatok as m, i (i)}
      <li>
        <p class="mondat">{m.mondat}</p>
        <button type="button" class="forras" title={m.link} onclick={(e) => nyit(m.ut, m.sor_kezd, e)}>{hely(m)}</button>
        <blockquote class="idezet">{m.idezet}</blockquote>
      </li>
    {/each}
  </ol>
{/if}

{#if a.vege}
  {#if a.vege.allapot !== 'kesz'}<p class="halvany">{vegeSzoveg(a.vege)}</p>{/if}
  {#if a.vege.proba && a.vege.allapot === 'kesz'}<p class="halvany">Próba: a modell erre a feladatra nem kalibrált.</p>{/if}
{/if}

{#if a.forrasok.length && (a.vege?.allapot === 'nincs_modell' || (!a.fut && !a.mondatok.length))}
  <ul class="forrasok" aria-label="Források">
    {#each a.forrasok as f (f.szam)}
      <li>
        <button type="button" class="forras" title={f.ut} onclick={(e) => nyit(f.ut, f.sor_kezd, e)}>
          {[fajlNev(f.ut), ...f.fejezet.slice(-1)].join(' › ')}
        </button>
      </li>
    {/each}
  </ul>
{/if}

<style>
  form {
    display: flex;
    flex-direction: column;
    gap: var(--t-2);
  }
  .cimke {
    color: var(--szoveg);
    font-size: var(--betu-kicsi);
  }
  .halvany {
    margin: var(--t-2) 0 0;
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }
  input {
    width: 100%;
    height: var(--magassag-suru);
    padding: 0 var(--t-2);
    border: var(--keret-vastag) solid var(--keret-mezo);
    border-radius: var(--kerekites);
    background: transparent;
    color: var(--szoveg);
    font-size: var(--betu-kicsi);
  }
  .sor {
    display: flex;
    align-items: center;
    gap: var(--t-2);
  }
  .sor .halvany {
    margin: 0;
  }
  .gomb {
    display: inline-flex;
    align-items: center;
    height: var(--magassag-suru);
  }
  .hiba {
    margin: var(--t-2) 0 0;
    padding: var(--t-2);
    border-radius: var(--kerekites);
    background: var(--hiba-hatter);
    color: var(--hiba);
    font-size: var(--betu-kicsi);
  }
  .valasz,
  .forrasok {
    margin: var(--t-3) 0 0;
    padding: 0;
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: var(--t-3);
  }
  .forrasok {
    gap: var(--t-1);
  }
  .mondat {
    margin: 0;
    color: var(--szoveg);
    line-height: var(--sor-kicsi);
  }
  .forras {
    padding: 0;
    border: 0;
    background: none;
    color: var(--akcent-szoveg);
    font-size: var(--betu-kicsi);
    text-align: left;
    cursor: pointer;
  }
  .forras:hover {
    text-decoration: underline;
  }
  .idezet {
    margin: var(--t-1) 0 0;
    padding-left: var(--t-2);
    border-left: var(--keret-vastag) solid var(--keret);
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }
</style>
