/// A `--selftest` szkriptelt forgatókönyveinek lap-oldali része (C33, 3. pont): `callAsyncJavaScript` törzsként fut a valódi
/// WebKitben (a `jel` és a `titok` argumentumként jön). Nyers Swift-szöveg (`#"""`), hogy a JS-ben ne kelljen escape-elni.
/// A szerkesztő nézetét a CodeMirror `cmTile`/`cmView` jelén át éri el (mint a `kilepes` forgatókönyv). Az eredmény egy JSON
/// a mért időkkel; hibánál kivételt dob (a héj `SELFTEST HIBA`-ként írja ki).
enum SelftestSzkript {
    static let szerkesztes = #"""
    const alszik = (ms) => new Promise((r) => setTimeout(r, ms));
    // a selftest ablak nélkül fut (accessory app): a rAF nem tüzel, ezért a gépelés mérése a C08 `meres.ts` módszere — a
    // tranzakció + a kikényszerített elrendezés (layout) ideje —, a mért szám a festés nélküli rész
    const elrendez = (n) => { void n.contentDOM.offsetHeight; void n.dom.getBoundingClientRect(); };
    async function varj(f, ms, nev, reszlet) {
      const t0 = performance.now();
      while (performance.now() - t0 < ms) {
        const v = await f();
        if (v) return v;
        await alszik(50);
      }
      throw new Error('időtúllépés: ' + nev + (reszlet ? ' — ' + reszlet() : ''));
    }
    const nezetek = () => [...document.querySelectorAll('.cm-content')]
      .map((c) => c.cmTile?.root?.view || c.cmView?.view || c.cmView?.rootView?.view).filter(Boolean);
    const ki = {};
    let t = performance.now();
    // CX-007: az áttekintővel induló appban a megőrzött jegyzetfül kiválasztása a valódi felületen.
    document.querySelector('[role=tab][title$=".md"]')?.click();
    // 1. megnyitás: a mentett felület-állapotból nyílt jegyzet szerkesztője
    const v = await varj(() => nezetek().find((n) => n.state.doc.toString().includes('PROBA-JEL')), 10000, 'a jegyzet megnyitása',
      () => 'szerkesztők: ' + nezetek().length + '; oldal: ' + document.body.innerText.replace(/\s+/g, ' ').slice(0, 200));
    ki.megnyitas_ms = Math.round(performance.now() - t);
    // 2. beágyazás: a `![[Cel]]` a core feloldásával és tartalmával (a beágyazás-widget)
    t = performance.now();
    await varj(() => [...v.dom.querySelectorAll('.beagyazas')].some((e) => (e.textContent || '').includes('CEL-JEL')), 8000,
      'a beágyazás tartalma', () => [...v.dom.querySelectorAll('.beagyazas')].map((e) => e.className + ': ' + (e.textContent || '')
        .slice(0, 80)).join(' | ') || 'nincs .beagyazas; DOM: ' + v.dom.innerText.replace(/\s+/g, ' ').slice(0, 200));
    ki.beagyazas_ms = Math.round(performance.now() - t);
    // 3. gépelés: 20 beszúrás a dokumentum végére (a link és a beágyazás sora így nem aktív), mindegyik a következő képkockáig
    v.focus();
    const idok = [];
    for (let i = 0; i < 20; i++) {
      const t0 = performance.now();
      v.dispatch({ changes: { from: v.state.doc.length, insert: i === 0 ? '\n' + jel : 'x' }, userEvent: 'input.type' });
      elrendez(v);
      idok.push(performance.now() - t0);
      await alszik(30);
    }
    idok.sort((a, b) => a - b);
    ki.gepeles_p50_ms = Math.round(idok[9] * 10) / 10;
    ki.gepeles_p95_ms = Math.round(idok[18] * 10) / 10;
    ki.gepeles_max_ms = Math.round(idok[19] * 10) / 10;
    // 4. mentés: az automatikus mentés után a core a beírt szöveget adja vissza
    t = performance.now();
    let utolso = '';
    await varj(async () => {
      const r = await fetch('/api/vault/fajl?ut=' + encodeURIComponent('Proba.md'), { headers: { 'X-Manifold': titok }, cache: 'no-store' });
      utolso = r.status + ' ' + (await r.text()).slice(0, 160);
      return r.ok && utolso.includes(jel);
    }, 8000, 'a mentés (a core nem adja vissza a beírt szöveget)', () => utolso);
    ki.mentes_ms = Math.round(performance.now() - t);
    // 5. link: ⌘-kattintás a kirajzolt `[[Cel|celhivatkozas]]` linkre → a cél megnyílik
    const link = await varj(() => [...v.dom.querySelectorAll('.cm-wikilink')].find((e) => (e.textContent || '').includes('celhivatkozas')),
      5000, 'a kirajzolt link', () => [...v.dom.querySelectorAll('.cm-wikilink')].map((e) => e.textContent).join(' | '));
    const d = link.getBoundingClientRect();
    t = performance.now();
    link.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, button: 0, metaKey: true,
      clientX: d.left + Math.min(d.width / 2, 20), clientY: d.top + d.height / 2 }));
    await varj(() => nezetek().some((n) => n !== v && n.state.doc.toString().includes('CEL-JEL')
      && !n.state.doc.toString().includes('PROBA-JEL')), 8000, 'a link célja nem nyílt meg',
      () => 'szerkesztők: ' + nezetek().map((n) => n.state.doc.toString().slice(0, 30)).join(' | '));
    ki.link_ms = Math.round(performance.now() - t);
    return JSON.stringify(ki);
    """#
}
