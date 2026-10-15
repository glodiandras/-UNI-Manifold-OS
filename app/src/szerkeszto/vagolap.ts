// Vágólapra másolás (a kódblokk gombja, az ütközésben „a lemezen lévő”). A WKWebView a `navigator.clipboard`-ot
// csak felhasználói mozdulatra engedi; ha az nem megy, a régi `execCommand('copy')` a tartalék.

export async function vagolapra(szoveg: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(szoveg);
    return true;
  } catch {
    const t = document.createElement('textarea');
    t.value = szoveg;
    t.setAttribute('readonly', '');
    t.style.position = 'fixed';
    t.style.opacity = '0';
    document.body.appendChild(t);
    t.select();
    let ok = false;
    try {
      ok = document.execCommand('copy');
    } catch {
      ok = false;
    }
    t.remove();
    return ok;
  }
}
