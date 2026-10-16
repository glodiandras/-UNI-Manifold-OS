// F10: the JavaScript / TypeScript "compile" step in the compile sandbox: `node js_fordit.js <source> [<output.js>]`.
// TypeScript: the embedded Node's own type stripping (`module.stripTypeScriptTypes`; `strip`, then `transform` for enums and
// namespaces), written to <output.js>. No type checking (there is no tsc in the runtime). Then a syntax check with
// `vm.Script` — nothing of the program runs. Errors are written gcc-style (`file:line:col: error: msg`).
// Exit code: 0 ok, 1 error, 2 unreadable source.
"use strict";
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const mod = require("node:module");

const ut = process.argv[2];
const ki = process.argv[3];
const nev = path.basename(ut);
let forras;
try {
  forras = fs.readFileSync(ut, "utf8");
} catch (e) {
  process.stderr.write(`${nev}:1:1: error: the source is not readable: ${e.message}\n`);
  process.exit(2);
}
let js = forras;
if (/\.[cm]?ts$/i.test(nev)) {
  if (typeof mod.stripTypeScriptTypes !== "function") {
    process.stderr.write(`${nev}:1:1: error: this Node.js has no TypeScript support (module.stripTypeScriptTypes)\n`);
    process.exit(1);
  }
  try {
    js = mod.stripTypeScriptTypes(forras, { mode: "strip" });
  } catch (e) {
    if (e && e.code === "ERR_UNSUPPORTED_TYPESCRIPT_SYNTAX") {
      try {
        js = mod.stripTypeScriptTypes(forras, { mode: "transform" });
      } catch (e2) {
        process.stderr.write(`${nev}:1:1: error: TypeScript: ${e2.message}\n`);
        process.exit(1);
      }
    } else {
      process.stderr.write(`${nev}:1:1: error: TypeScript: ${e && e.message}\n`);
      process.exit(1);
    }
  }
}
const esm = /^\s*(import|export)\s/m.test(js);
try {
  if (esm && typeof vm.SourceTextModule === "function") {
    new vm.SourceTextModule(js, { identifier: nev });
  } else if (!esm) {
    vm.compileFunction(js, ["exports", "require", "module", "__filename", "__dirname"], { filename: nev });
  }
} catch (e) {
  const m = /^(.*):(\d+)\n([^\n]*)\n(\s*)\^/.exec(String(e.stack || ""));
  let sor = 1, oszlop = 1;
  if (m) { sor = Number(m[2]); oszlop = m[4].length + 1; }
  process.stderr.write(`${nev}:${sor}:${oszlop}: error: ${e.name}: ${e.message}\n`);
  process.exit(1);
}
if (ki) {
  try {
    fs.writeFileSync(ki, js);
  } catch (e) {
    process.stderr.write(`${nev}:1:1: error: the output is not writable: ${e.message}\n`);
    process.exit(1);
  }
}
process.exit(0);
