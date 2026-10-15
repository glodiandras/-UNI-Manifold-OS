// C++ kódrészletek (C36a-UI; a TERV 5.14 „kódrészletek” pontja, modell és LSP nélkül): a kiegészítő listában jelennek meg
// (a szó elejét gépelve, vagy ⌃Space), a Tab a `${…}` mezők között lép. Magától semmi nem íródik a szövegbe: a
// beszúrás a felhasználó választása, egy szerkesztő-tranzakció (⌘Z egy lépés).

import { snippetCompletion, type Completion, type CompletionContext, type CompletionResult } from '@codemirror/autocomplete';

export interface Reszlet {
  /** a gépelt előtag, amire illeszkedik */
  cimke: string;
  /** rövid magyar leírás a listában */
  leiras: string;
  /** a CodeMirror-sablon (`${név}` mező, `${}` a kurzor helye) */
  sablon: string;
}

export const RESZLETEK: Reszlet[] = [
  {
    cimke: 'main',
    leiras: 'teljes program: fejléc, gyors I/O, main',
    sablon: '#include <bits/stdc++.h>\nusing namespace std;\n\nint main() {\n    ios::sync_with_stdio(false);\n    cin.tie(nullptr);\n\n    ${}\n    return 0;\n}\n',
  },
  { cimke: 'gyorsio', leiras: 'gyors beolvasás (sync_with_stdio, cin.tie)', sablon: 'ios::sync_with_stdio(false);\ncin.tie(nullptr);\n${}' },
  { cimke: 'for', leiras: 'számlálós ciklus 0-tól n-ig', sablon: 'for (int ${i} = 0; ${i} < ${n}; ++${i}) {\n    ${}\n}' },
  { cimke: 'forr', leiras: 'visszafelé számláló ciklus', sablon: 'for (int ${i} = ${n} - 1; ${i} >= 0; --${i}) {\n    ${}\n}' },
  { cimke: 'fore', leiras: 'tartomány-alapú ciklus', sablon: 'for (auto& ${x} : ${v}) {\n    ${}\n}' },
  { cimke: 'while', leiras: 'elöltesztelő ciklus', sablon: 'while (${feltetel}) {\n    ${}\n}' },
  { cimke: 'if', leiras: 'elágazás', sablon: 'if (${feltetel}) {\n    ${}\n}' },
  { cimke: 'ifelse', leiras: 'kétirányú elágazás', sablon: 'if (${feltetel}) {\n    ${}\n} else {\n    \n}' },
  { cimke: 'vbe', leiras: 'n elemű vektor beolvasása', sablon: 'int ${n};\ncin >> ${n};\nvector<${long long}> ${v}(${n});\nfor (auto& x : ${v}) cin >> x;\n${}' },
  { cimke: 'vki', leiras: 'vektor kiírása szóközzel', sablon: 'for (size_t i = 0; i < ${v}.size(); ++i) cout << ${v}[i] << " \\n"[i + 1 == ${v}.size()];\n${}' },
  { cimke: 'sort', leiras: 'rendezés növekvő sorrendbe', sablon: 'sort(${v}.begin(), ${v}.end());${}' },
  { cimke: 'sortc', leiras: 'rendezés saját összehasonlítással', sablon: 'sort(${v}.begin(), ${v}.end(), [](const auto& a, const auto& b) { return ${a < b}; });${}' },
  { cimke: 'll', leiras: 'using ll = long long', sablon: 'using ll = long long;\n${}' },
  { cimke: 'pair', leiras: 'pár típus', sablon: 'pair<${int}, ${int}>${}' },
  { cimke: 'fv', leiras: 'függvény', sablon: '${int} ${nev}(${}) {\n    \n}' },
  { cimke: 'struct', leiras: 'struktúra', sablon: 'struct ${Nev} {\n    ${}\n};' },
  { cimke: 'graf', leiras: 'szomszédsági lista n csúcsra, m éllel', sablon: 'int ${n}, ${m};\ncin >> ${n} >> ${m};\nvector<vector<int>> ${g}(${n});\nfor (int i = 0; i < ${m}; ++i) {\n    int a, b;\n    cin >> a >> b;\n    ${g}[a].push_back(b);\n    ${g}[b].push_back(a);\n}\n${}' },
  { cimke: 'bfs', leiras: 'szélességi bejárás egy kezdőcsúcsból', sablon: 'vector<int> tav(${n}, -1);\nqueue<int> q;\ntav[${s}] = 0;\nq.push(${s});\nwhile (!q.empty()) {\n    int u = q.front();\n    q.pop();\n    for (int w : ${g}[u])\n        if (tav[w] < 0) {\n            tav[w] = tav[u] + 1;\n            q.push(w);\n        }\n}\n${}' },
  { cimke: 'binker', leiras: 'bináris keresés a válaszra', sablon: 'long long lo = ${also}, hi = ${felso};\nwhile (lo < hi) {\n    long long mid = lo + (hi - lo) / 2;\n    if (${jo(mid)}) hi = mid;\n    else lo = mid + 1;\n}\n${}' },
];

/** A részletek a kiegészítő listához (a `snippetCompletion` a Tab-os mezőket adja). */
export const RESZLET_OPCIOK: Completion[] = RESZLETEK.map((r) =>
  snippetCompletion(r.sablon, { label: r.cimke, detail: r.leiras, type: 'text', boost: 1 }),
);

/** A kiegészítés forrása: csak szó elején és nem megjegyzésben vagy szövegben (a kódban). */
export function reszletForras(ctx: CompletionContext): CompletionResult | null {
  const szo = ctx.matchBefore(/[A-Za-z_]\w*/);
  if (!szo && !ctx.explicit) return null;
  if (szo && szo.from === szo.to && !ctx.explicit) return null;
  const sor = ctx.state.doc.lineAt(ctx.pos);
  const elotte = sor.text.slice(0, ctx.pos - sor.from);
  if (/\/\/|"[^"]*$/.test(elotte)) return null; // megjegyzésben vagy nyitott sztringben nem ajánl
  return { from: szo ? szo.from : ctx.pos, options: RESZLET_OPCIOK, validFor: /^\w*$/ };
}
