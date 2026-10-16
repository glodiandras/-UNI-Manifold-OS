// A macOS NaturalLanguage keretrendszere a natív héjban, helyben ismeri fel a nyelvet.
// Böngészőben és régebbi héjjal nincs közelítő, UI-nyelvre kényszerített találat.
export interface FelismertNyelv {
  nyelv: string | null;
  bizalom: number;
  kevert: boolean;
}

interface NyelvHid {
  postMessage(adat: { szoveg: string }): Promise<unknown>;
}

function hid(): NyelvHid | undefined {
  return (window as unknown as { webkit?: { messageHandlers?: { nyelv?: NyelvHid } } }).webkit?.messageHandlers?.nyelv;
}

export function vanNyelvFelismeres(): boolean {
  return typeof hid()?.postMessage === 'function';
}

export async function nyelvFelismer(szoveg: string): Promise<FelismertNyelv | null> {
  const csatorna = hid();
  if (!csatorna) return null;
  let ora: ReturnType<typeof setTimeout> | undefined;
  try {
    const v = await Promise.race([
      csatorna.postMessage({ szoveg: szoveg.slice(0, 8000) }),
      new Promise<null>((kesz) => { ora = setTimeout(() => kesz(null), 3000); }),
    ]);
    if (!v || typeof v !== 'object') return null;
    const { nyelv, bizalom, kevert } = v as Record<string, unknown>;
    if (typeof bizalom !== 'number' || !Number.isFinite(bizalom) || bizalom < 0 || bizalom > 1) return null;
    if (kevert === true || nyelv === null) return { nyelv: null, bizalom: 0, kevert: kevert === true };
    if (typeof nyelv !== 'string' || nyelv.length > 50) return null;
    const kod = Intl.getCanonicalLocales(nyelv)[0];
    return kod ? { nyelv: kod, bizalom, kevert: false } : null;
  } catch {
    return null;
  } finally {
    if (ora) clearTimeout(ora);
  }
}
