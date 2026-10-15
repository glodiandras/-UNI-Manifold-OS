<!-- A vezérlő még nem épült szakaszainak tiszta üres állapota: egy mondat, hogy melyik chat tölti meg (C17). -->
<script lang="ts">
  let { szoveg }: { szoveg: string } = $props();
</script>

<p class="ures">{szoveg}</p>

<style>
  .ures {
    margin: 0;
    padding: var(--t-1) 0;
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    max-width: 36ch;
  }
</style>
