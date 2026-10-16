"""F9 security audit §5–6: no hardcoded secret, no developer identity or developer path in what ships, and the pinned dependencies
are not older than the versions that fixed the known (offline-checkable) vulnerabilities.

- Secrets: every repository file (tracked or not ignored, `git ls-files -co --exclude-standard`; `node_modules`, `runtime`, `var`
  are not part of it) is scanned for token shapes (Hugging Face, OpenAI/Anthropic-style `sk-`, GitHub, AWS, Slack, Google API
  keys, private-key blocks). The scanner is checked on a planted sample, so a broken pattern cannot make the test vacuous.
- Identity and paths: the shipped trees (`core`, `modulok`, `app/src`, `app/index.html`, `shell`, `bin`, `config`, `packaging`,
  `docs/user`, `README.md`) carry no developer name, e-mail, home folder or developer disk path. Synthetic self-test values
  (`/Users/x`, `/Volumes/Disk`) are fine. Known exceptions are listed by file and exact text, with a reason.
- Dependencies (offline): `config/requirements.lock` and `app/package-lock.json` pins compared with a floor table of fixed
  versions for advisories known at the time of the audit (no network, no advisory database: see audit 07 §6)."""
from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path

from tests.helpers import REPO

TITOK_MINTAK = {
    "huggingface": r"\bhf_[A-Za-z0-9]{30,}\b",
    "sk_kulcs": r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{24,}\b",
    "github": r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b",
    "aws": r"\bAKIA[0-9A-Z]{16}\b",
    "slack": r"\bxox[abprs]-[0-9A-Za-z-]{10,}\b",
    "google": r"\bAIza[0-9A-Za-z_-]{35}\b",
    "privat_kulcs": r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----",
}
SZEMELYES = r"glodi|andras\b|@gmail\.com|/Users/(?!x\b|x y\b|<)[A-Za-z]|/home/[a-z]+/|/Volumes/Work\b|C:\\\\Users\\\\"
SZALLITOTT = ("core/", "modulok/", "app/src/", "app/index.html", "shell/", "bin/", "config/", "packaging/", "docs/user/", "README.md")
# (file, exact text) → why it may stay. Every entry must still match (a fixed exception is removed from the list).
ISMERT_KIVETEL = {
    ("shell/Sources/RootLocator.swift", "/Volumes/Work/Manifold-OS"):
        "self-test table: the developer checkout must NOT be taken for a bundle (audit 07 §5: rename to a neutral disk name)",
    ("shell/Sources/RootLocator.swift", "/Volumes/Work/Manifold.app"):
        "same self-test table (audit 07 §5)",
}

PIP_MINIMUM = {          # package: (fixed version, advisory)
    "jinja2": ("3.1.6", "CVE-2025-27516 sandbox breakout via |attr"),
    "h11": ("0.16.0", "CVE-2025-43859 request smuggling"),
    "requests": ("2.32.4", "CVE-2024-47081 .netrc credential leak"),
    "urllib3": ("2.5.0", "CVE-2025-50181/50182 redirect control"),
    "setuptools": ("78.1.1", "CVE-2025-47273 path traversal in PackageIndex"),
    "pillow": ("11.3.0", "CVE-2025-48379 DDS write overflow"),
    "certifi": ("2024.7.4", "GLOBALTRUST root removal"),
    "idna": ("3.7", "CVE-2024-3651 quadratic encode"),
    "starlette": ("0.47.2", "CVE-2025-54121 multipart DoS"),
    "python-multipart": ("0.0.18", "CVE-2024-53981 boundary DoS"),
    "pypdf": ("6.0.0", "CVE-2025-55197 FlateDecode bomb"),
    "torch": ("2.6.0", "CVE-2025-32434 torch.load weights_only RCE"),
    "transformers": ("4.53.0", "ReDoS advisories 2025"),
    "protobuf": ("5.29.5", "CVE-2025-4565 recursion DoS"),
    "yt-dlp": ("2025.1.15", "CVE-2024-38519 / --exec injection fixes"),
    "pyyaml": ("5.4", "CVE-2020-14343 full_load RCE"),
    "pygments": ("2.15.0", "CVE-2022-40896 ReDoS"),
    "tqdm": ("4.66.3", "CVE-2024-34062 CLI eval"),
    "scikit-learn": ("1.5.0", "CVE-2024-5206 token leak"),
    "huggingface-hub": ("0.23.0", "path handling fixes"),
    "websockets": ("10.0", "CVE-2021-33880 timing"),
    "pymupdf": ("1.24.0", "MuPDF CVE fixes 2023-2024"),
}
NPM_MINIMUM = {
    "dompurify": ("3.2.4", "CVE-2025-26791 mXSS"),
    "katex": ("0.16.21", "CVE-2025-23207 maxExpand bypass"),
    "pdfjs-dist": ("4.2.67", "CVE-2024-4367 arbitrary JS in font"),
    "mermaid": ("10.9.3", "CVE-2024 XSS fixes"),
    "dagre-d3-es": ("7.0.11", "XSS in node labels"),
    "d3-color": ("3.1.0", "ReDoS"),
    "lodash-es": ("4.17.21", "CVE-2021-23337 template injection"),
    "marked": ("4.0.10", "ReDoS"),
    "nanoid": ("3.3.8", "CVE-2024-55565 predictable ids"),
    "vite": ("6.2.7", "server.fs.deny bypasses 2025 (dev only)"),
    "undici": ("6.21.2", "CVE-2025-22150 weak multipart boundary (dev only)"),
    "postcss": ("8.4.31", "CVE-2023-44270 (dev only)"),
    "esbuild": ("0.25.0", "dev server CORS (dev only)"),
}


def _v(s: str) -> tuple:
    return tuple(int(x) if x.isdigit() else 0 for x in re.split(r"[.+-]", s)[:4])


def _repo_fajlok() -> list[str]:
    p = subprocess.run(["git", "-C", str(REPO), "ls-files", "-co", "--exclude-standard", "-z"], capture_output=True, timeout=60)
    if p.returncode != 0:
        raise unittest.SkipTest("[indokolt] not a git checkout")
    return [f for f in p.stdout.decode("utf-8", "surrogateescape").split("\0") if f]


def _szoveg(rel: str) -> str | None:
    p = REPO / rel
    try:
        if not p.is_file() or p.is_symlink() or p.stat().st_size > 4 * 1024 * 1024:
            return None
        b = p.read_bytes()
    except OSError:
        return None
    if b"\0" in b[:8192]:
        return None
    return b.decode("utf-8", "replace")


class TitokTest(unittest.TestCase):
    def test_a_mintak_mukodnek(self):
        minta = ("hf_" + "a1B2" * 9, "sk-ant-" + "x" * 30, "ghp_" + "Z" * 36, "AKIA" + "ABCDEFGHIJKLMNOP",
                 "-----BEGIN OPENSSH PRIVATE KEY-----", "AIza" + "0" * 35, "xoxb-" + "1" * 12)
        for m in minta:
            self.assertTrue(any(re.search(r, m) for r in TITOK_MINTAK.values()), m)
        for jo in ("sk-learn", "hf_hub_download", "risk-of-loss", "AKIA"):
            self.assertFalse(any(re.search(r, jo) for r in TITOK_MINTAK.values()), jo)

    def test_nincs_titok_a_repoban(self):
        talalat = []
        minta = re.compile("|".join(f"(?P<{k}>{v})" for k, v in TITOK_MINTAK.items()))
        for rel in _repo_fajlok():
            if rel == "tests/biztonsag/test_titok_es_ut.py":
                continue
            s = _szoveg(rel)
            if s is None:
                continue
            for m in minta.finditer(s):
                talalat.append(f"{rel}:{s.count(chr(10), 0, m.start()) + 1}: {m.lastgroup}")
        self.assertEqual(talalat, [], "a secret-shaped string in the repository")


class SzemelyesUtTest(unittest.TestCase):
    def test_a_szallitott_faban_nincs_fejlesztoi_ut_vagy_nev(self):
        minta = re.compile(SZEMELYES, re.I)
        talalat, hasznalt = [], set()
        for rel in _repo_fajlok():
            if not rel.startswith(SZALLITOTT):
                continue
            s = _szoveg(rel)
            if s is None:
                continue
            for i, sor in enumerate(s.splitlines(), 1):
                for m in minta.finditer(sor):
                    kiv = next((k for k in ISMERT_KIVETEL if k[0] == rel and k[1] in sor and sor.find(k[1]) <= m.start() <= sor.find(k[1]) + len(k[1])), None)
                    if kiv:
                        hasznalt.add(kiv)
                    else:
                        talalat.append(f"{rel}:{i}: {sor.strip()[:120]}")
        self.assertEqual(talalat, [], "a developer name or path in a shipped file")
        self.assertEqual(set(ISMERT_KIVETEL) - hasznalt, set(), "a known exception no longer occurs: remove it from ISMERT_KIVETEL")

    def test_a_minta_felismeri_a_szemelyes_utat(self):
        m = re.compile(SZEMELYES, re.I)
        for rossz in ("/Users/john/Documents", "/Volumes/Work/Manifold", "/home/dev/x", "glodi.andras"):
            self.assertTrue(m.search(rossz), rossz)
        for jo in ("/Users/x/Downloads", "/Users/x y/Library", "/Volumes/Disk/Manifold", "/Users/<you>/Notes"):
            self.assertFalse(m.search(jo), jo)


class FuggosegTest(unittest.TestCase):
    def test_python_pinek_a_javitott_verziok_felett(self):
        pin = {}
        for sor in (REPO / "config" / "requirements.lock").read_text(encoding="utf-8").splitlines():
            m = re.match(r"([A-Za-z0-9_.-]+)==([^\s;\\]+)", sor)
            if m:
                pin[m.group(1).lower().replace("_", "-")] = m.group(2)
        self.assertGreater(len(pin), 30)
        regi = [f"{n} {pin[n]} < {v} ({ok})" for n, (v, ok) in PIP_MINIMUM.items() if n in pin and _v(pin[n]) < _v(v)]
        self.assertEqual(regi, [])

    def test_npm_pinek_a_javitott_verziok_felett(self):
        lock = json.loads((REPO / "app" / "package-lock.json").read_text(encoding="utf-8"))
        regi = []
        for kulcs, adat in lock.get("packages", {}).items():
            nev = kulcs.rsplit("node_modules/", 1)[-1]
            if nev in NPM_MINIMUM and _v(adat.get("version", "0")) < _v(NPM_MINIMUM[nev][0]):
                regi.append(f"{kulcs} {adat.get('version')} < {NPM_MINIMUM[nev][0]} ({NPM_MINIMUM[nev][1]})")
        self.assertEqual(regi, [])

    def test_nincs_tavoli_forras_a_lockban(self):
        """The npm lock resolves only from the registry (no git/http tarball that could change under the same version)."""
        lock = json.loads((REPO / "app" / "package-lock.json").read_text(encoding="utf-8"))
        idegen = [k for k, a in lock.get("packages", {}).items()
                  if k and a.get("resolved") and not a["resolved"].startswith("https://registry.npmjs.org/")]
        self.assertEqual(idegen, [])
        hash_nelkul = [k for k, a in lock.get("packages", {}).items() if k and a.get("resolved") and not a.get("integrity")]
        self.assertEqual(hash_nelkul, [])
        nyers = (REPO / "config" / "requirements.lock").read_text(encoding="utf-8")
        self.assertNotRegex(nyers, r"(?m)^\s*(?:git\+|https?://|-e\s)", "a direct URL / editable requirement in the lock")
