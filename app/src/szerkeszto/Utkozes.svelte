<!--
  Ütközés (409): a jegyzet a lemezen közben megváltozott (Obsidian, szinkron vagy egy lánc írta), ezért a
  szerkesztő nem írta felül. Három döntés (a legacy pult szerződése):
    - „Az enyém”: a lemezen lévőre építve ír, `elso`-val — a core a lemezen lévőt előbb kézi pillanatképbe
      teszi, így az sem vész el. Foglalt kör-zárnál (423/503) a párbeszéd nyitva marad, és 2 s-onként újrapróbál;
    - „A lemezen lévő”: betölti (visszavonhatóan: ⌘Z), a saját szöveg a vágólapra is kerül;
    - „Összevetés”: kétoldalas összefésülés (a lemezen lévő szakaszai átvehetők), a kész szöveg mentése.
-->
<script lang="ts">
  import { MergeView } from '@codemirror/merge';
  import { syntaxHighlighting } from '@codemirror/language';
  import { EditorState } from '@codemirror/state';
  import { EditorView } from '@codemirror/view';
  import { classHighlighter } from '@lezer/highlight';
  import { onDestroy, onMount } from 'svelte';
  import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { TriangleAlert } from '../lib/ikon/ikonok';
  import Atfedes from '../lib/ui/Atfedes.svelte';
  import { MAGYAR_FELIRATOK, markdownNyelv } from './beallitas';
  import type { FajlOlvasas } from './dokumentum/api';
  import type { Dokumentum, MentesEredmeny } from './dokumentum/dokumentum.svelte';
  import { vagolapra } from './vagolap';

  /** `ellenoriz`: az összefésült szöveg érvényességi vizsgálata mentés előtt (a canvasnál a JSON Canvas); a hiba magyar mondat */
  let { dok, onbezar, ellenoriz }: { dok: Dokumentum; onbezar: () => void; ellenoriz?: (szoveg: string) => string | null } = $props();

  let lemez = $state.raw<FajlOlvasas | null>(null);
  let hiba = $state<string | null>(null);
  let osszevetes = $state(false);
  let dolgozik = $state(false);
  /** foglalt kör-zár: a mentés 2 s múlva újra próbál (T116) */
  let varakozik = $state(false);
  /** az összefésült szöveg érvénytelen (az `ellenoriz` hibája): nem menthető (T030) */
  let osszefesultHiba = $state<string | null>(null);
  let mergeHely: HTMLDivElement | undefined = $state();
  let merge: MergeView | null = null;
  let ujraIdozito: ReturnType<typeof setTimeout> | null = null;
  let megszunt = false;
  const UJRA_MS = 2000;

  onMount(() => {
    dok.olvasLemezrol().then(
      (d) => (lemez = d),
      (e) => (hiba = e instanceof Error ? e.message : String(e)),
    );
  });

  onDestroy(() => {
    megszunt = true;
    if (ujraIdozito) clearTimeout(ujraIdozito);
    merge?.destroy();
  });

  // közben újabb külső változás (új 409): a párbeszéd az új lemezes változatot mutatja
  let utolsoHash: string | null = null;
  $effect(() => {
    const h = dok.utkozes?.hash ?? null;
    if (!h || h === utolsoHash) return;
    const elozo = utolsoHash;
    utolsoHash = h;
    if (elozo === null) return; // az első betöltés az onMount-é
    dok.olvasLemezrol().then(
      (d) => {
        if (!megszunt) lemez = d;
      },
      () => {},
    );
  });

  $effect(() => {
    if (!osszevetes || !mergeHely || !lemez || merge) return;
    const kozos = [
      markdownNyelv(),
      EditorView.lineWrapping,
      syntaxHighlighting(classHighlighter),
      EditorState.phrases.of(MAGYAR_FELIRATOK),
    ];
    merge = new MergeView({
      parent: mergeHely,
      a: { doc: lemez.tartalom.replace(/\r\n?/g, '\n'), extensions: [...kozos, EditorState.readOnly.of(true), EditorView.editable.of(false)] },
      b: {
        doc: dok.szoveg,
        extensions: [
          ...kozos,
          EditorView.updateListener.of((u) => {
            if (u.docChanged && ellenoriz) osszefesultHiba = ellenoriz(u.state.doc.toString());
          }),
        ],
      },
      revertControls: 'a-to-b',
      highlightChanges: true,
      gutter: true,
      collapseUnchanged: { margin: 3, minSize: 8 },
    });
  });

  /** Az ütközés feloldásának mentése: siker esetén a párbeszéd bezárul; foglalt kör-zárnál (a lemezen lévő változat még
   *  nem kerülhet pillanatképbe) nyitva marad és újrapróbál; egyéb hibánál nyitva marad, az ok látszik (T116). */
  async function ment(muvelet: () => Promise<MentesEredmeny>) {
    if (ujraIdozito) clearTimeout(ujraIdozito);
    ujraIdozito = null;
    varakozik = false;
    dolgozik = true;
    const r = await muvelet();
    dolgozik = false;
    if (megszunt) return;
    if (r.ok) {
      if (r.git === false) felulirtFigyelmeztetes();
      onbezar();
      return;
    }
    if (r.foglalt) {
      varakozik = true;
      ujraIdozito = setTimeout(() => void ment(muvelet), UJRA_MS);
    }
  }

  /** Védőháló: a mentés pillanatkép nélkül ment, tehát a felülírt külső változat nincs a git-ben — a vágólapra kerül. */
  function felulirtFigyelmeztetes() {
    const kulso = lemez?.tartalom;
    if (kulso !== undefined) void vagolapra(kulso);
    ertesitesek.ertesit({
      szint: 'figyelmeztetes',
      cim: 'A lemezen lévő változat nem került pillanatképbe',
      szoveg: 'A mentés pillanatkép nélkül ment (a core éppen a vaultot írta, vagy a git hibázott). A felülírt, külső változatot a vágólapra másoltam.',
      idotartam: 0,
    });
  }

  async function enyem() {
    if (!lemez) return;
    const hash = lemez.hash;
    await ment(() => dok.enyemet(hash));
  }

  async function lemezenLevo() {
    if (!lemez) return;
    if (ujraIdozito) clearTimeout(ujraIdozito);
    ujraIdozito = null;
    const sajat = dok.fajlSzoveg();
    dok.lemezrolBetolt(lemez, true);
    const ok = await vagolapra(sajat);
    ertesitesek.ertesit({
      szint: 'info',
      cim: 'A lemezen lévő változat betöltve',
      szoveg: ok ? 'A saját szöveged a vágólapon van, és ⌘Z-vel is visszahozható.' : 'A saját szöveged ⌘Z-vel visszahozható.',
    });
    onbezar();
  }

  async function osszefesultMent() {
    if (!lemez || !merge) return;
    const hash = lemez.hash;
    const m = merge;
    const szoveg = m.b.state.doc.toString();
    const hiba = ellenoriz?.(szoveg) ?? null;
    if (hiba) {
      osszefesultHiba = hiba; // az érvénytelen szöveget a core úgyis elutasítaná (400): nem is küldjük
      return;
    }
    await ment(() => dok.osszefesultet(hash, szoveg));
  }
</script>

<Atfedes cimke="Ütközés: a jegyzet közben megváltozott" nev="utkozes" {onbezar} szeles={osszevetes}>
  <div class="utkozes">
    <header class="fej">
      <span class="ikon"><Ikon ikon={TriangleAlert} meret={20} /></span>
      <div>
        <h2>A jegyzet közben megváltozott</h2>
        <p>
          A lemezen lévő változatot más írta (Obsidian, szinkron vagy egy lánc), ezért nem írtam felül. A te
          változatod itt van, mentetlenül.
        </p>
      </div>
    </header>

    {#if hiba}
      <p class="hiba" role="alert">A lemezen lévő változat nem olvasható: {hiba}</p>
    {/if}
    {#if dok.utkozesUzenet}
      <p class="figyelmeztetes" role="status">{dok.utkozesUzenet}{varakozik ? ' Újrapróbálom…' : ''}</p>
    {/if}

    {#if osszevetes}
      <div class="oszlopfej" aria-hidden="true"><span>A lemezen lévő</span><span>Az enyém (szerkeszthető)</span></div>
      <div class="merge" bind:this={mergeHely}></div>
      <footer class="gombok">
        <button type="button" class="m-gomb semleges gomb" onclick={() => (osszevetes = false)}>Vissza</button>
        {#if osszefesultHiba}
          <p class="hiba" role="alert">Az összefésült szöveg nem menthető: {osszefesultHiba}</p>
        {/if}
        <button type="button" class="m-gomb gomb elsodleges" disabled={dolgozik || !!osszefesultHiba} onclick={osszefesultMent}>
          Az összefésült szöveg mentése
        </button>
      </footer>
    {:else}
      <p class="megjegyzes">
        „Az enyém”: a lemezen lévő változat előbb pillanatképbe kerül, tehát az sem vész el. „A lemezen lévő”:
        a te szöveged a vágólapra kerül, és ⌘Z-vel is visszahozható.
      </p>
      <footer class="gombok">
        <button type="button" class="m-gomb semleges gomb" disabled={!lemez} onclick={() => (osszevetes = true)}>Összevetés…</button>
        <button type="button" class="m-gomb semleges gomb" disabled={!lemez} onclick={lemezenLevo}>A lemezen lévő</button>
        <button type="button" class="m-gomb gomb elsodleges" disabled={!lemez || dolgozik} onclick={enyem}>Az enyém</button>
      </footer>
    {/if}
  </div>
</Atfedes>

<style>
  .utkozes {
    display: flex;
    flex-direction: column;
    gap: var(--t-3);
    padding: var(--t-5);
    min-height: 0;
    flex: 1;
  }

  .fej {
    display: flex;
    gap: var(--t-3);
  }

  .ikon {
    color: var(--figyelmeztetes);
    padding-top: 2px;
  }

  h2 {
    font-size: var(--betu-torzs);
    line-height: var(--magassag-suru);
    font-weight: var(--suly-felkover);
  }

  p {
    margin: var(--t-1) 0 0;
    color: var(--szoveg-masodlagos);
  }

  .megjegyzes {
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    color: var(--szoveg-halvany);
  }

  .hiba {
    color: var(--hiba);
  }

  .figyelmeztetes {
    color: var(--figyelmeztetes);
  }

  .oszlopfej {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--t-4);
    font-size: var(--betu-kicsi);
    color: var(--szoveg-halvany);
  }

  .merge {
    flex: 1;
    min-height: 240px;
    overflow: auto;
    border: var(--keret-vastag) solid var(--keret);
    border-radius: var(--kerekites);
  }

  .gombok {
    display: flex;
    justify-content: flex-end;
    gap: var(--t-2);
  }

</style>
