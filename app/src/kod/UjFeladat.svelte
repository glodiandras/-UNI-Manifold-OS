<!--
  „Új C++ feladat…” (C36a-UI): név és mappa → `POST /api/cpp/feladat` (a core a `.cpp`-t és a sablonos feladat-jegyzetet
  hozza létre, két commitban); utána a jegyzet nyílik, a `.cpp` osztásban. A felhasználó művelete: gép `.cpp`-t nem ír (53(d)).
-->
<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import { kornyezet } from '../lib/kornyezet';
  import Atfedes from '../lib/ui/Atfedes.svelte';
  import { mappa as mappaja } from '../lib/vault/fajlok.svelte';
  import { ujFeladat } from './muveletek';

  const { felulet, fajlok } = kornyezet();
  const alapMappa = untrack(() => {
    const ut = felulet.munkaterulet.aktivFul?.ut;
    return ut ? mappaja(ut) : '';
  });

  let nev = $state('');
  let hely = $state(alapMappa);
  let folyik = $state(false);
  let hiba = $state<string | null>(null);
  let bevitel: HTMLInputElement | undefined = $state();

  onMount(() => bevitel?.focus());

  function bezar() {
    felulet.atfedes = null;
  }

  async function letrehoz() {
    const n = nev.trim();
    if (!n || folyik) return;
    const m = hely.trim().replace(/^\/+|\/+$/g, '');
    if (m && !fajlok.mappak.includes(m)) {
      hiba = `Nincs ilyen mappa: ${m}`;
      return;
    }
    folyik = true;
    hiba = null;
    const r = await ujFeladat(felulet, m, n);
    folyik = false;
    if (r.ok) bezar();
    else hiba = r.hiba;
  }

  function billentyu(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.isComposing) {
      e.preventDefault();
      void letrehoz();
    }
  }
</script>

<Atfedes cimke="Új C++ feladat" nev="cpp-feladat" onbezar={bezar}>
  <div class="doboz">
    <h2 class="cim">Új C++ feladat</h2>
    <label class="mezo">
      <span>Név</span>
      <input bind:this={bevitel} bind:value={nev} onkeydown={billentyu} spellcheck="false" autocomplete="off" placeholder="pl. Két szám összege" />
    </label>
    <label class="mezo">
      <span>Mappa</span>
      <input bind:value={hely} onkeydown={billentyu} list="cpp-feladat-mappak" spellcheck="false" autocomplete="off" placeholder="(a vault gyökere)" />
      <datalist id="cpp-feladat-mappak">
        {#each fajlok.mappak as m (m)}<option value={m}></option>{/each}
      </datalist>
    </label>
    <p class="seg">Elkészül a feladat-jegyzet (leírás, `teszt` blokkok) és a kísérő <code>.cpp</code>; a ⌘R a teszteken futtatja.</p>
    {#if hiba}<p class="hiba" role="alert">{hiba}</p>{/if}
    <div class="gombok">
      <button type="button" class="m-gomb semleges masodlagos" onclick={bezar}>Mégse</button>
      <button type="button" class="m-gomb elso" disabled={!nev.trim() || folyik} onclick={() => void letrehoz()}>
        {folyik ? 'Létrehozás…' : 'Létrehozás'}
      </button>
    </div>
  </div>
</Atfedes>

<style>
  .doboz {
    display: flex;
    flex-direction: column;
    gap: var(--t-3);
    padding: var(--t-4) var(--t-5);
  }

  .cim {
    margin: 0;
    font-size: var(--betu-h4);
  }

  .mezo {
    display: flex;
    flex-direction: column;
    gap: var(--t-1);
    font-size: var(--betu-ui);
    color: var(--szoveg-masodlagos);
  }

  .mezo input {
    padding: var(--t-2) var(--t-3);
    border: var(--keret-vastag) solid var(--keret-mezo);
    border-radius: var(--kerekites);
    background: var(--hatter);
    color: var(--szoveg);
    font: inherit;
  }

  .mezo input:focus-visible {
    outline: var(--fokusz-vastag) solid var(--fokusz-gyuru);
    outline-offset: var(--fokusz-tav);
  }

  .seg {
    margin: 0;
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
  }

  .hiba {
    margin: 0;
    color: var(--hiba);
    font-size: var(--betu-ui);
  }

  .gombok {
    display: flex;
    justify-content: flex-end;
    gap: var(--t-2);
  }

</style>
