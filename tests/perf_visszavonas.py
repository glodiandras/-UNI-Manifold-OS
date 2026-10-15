"""Perf-készlet (C33, T174, A2-soak1-4): a kör szerinti visszavonás és az ismétlés-ellenőrzés ideje a történet hosszával.
NEM része az alap készletnek (nem `test*.py`): `bin/mos perf`, tétlen gépen.

A `Repo.log(run=…)` korábban a teljes naplót Pythonban bontotta (kétszer: a forrás-statisztika és a visszavonás), így a kör-
visszavonás ~12 ms-mal nőtt 1000 commitonként. Most a git szűr (`--fixed-strings --grep`), és a két hívás megosztja az
eredményt. A kapu: 6000 idegen commit mellett a kör commitjainak keresése legfeljebb háromszor annyi, mint 60 mellett
(+50 ms ráhagyás), és a teljes kör-visszavonás 1 s alatt van."""
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from core import snapshot

KOR = "SOAK-20261008-120000-abc123"


def _tarolo(alap: Path, idegen: int) -> snapshot.Repo:
    wt = alap / "Vault"
    (wt / ".obsidian").mkdir(parents=True)
    (wt / "a.md").write_text("alap\n", encoding="utf-8")
    repo = snapshot.Repo("vault", wt, alap / "vault.git", [".DS_Store"])
    repo.init()
    repo.commit("alap", {"Mos-Forras": "kezi"})
    if idegen:
        # `git fast-import`: sok idegen (más körös) commit gyorsan, a munkafa érintetlen (a fájl tartalma ugyanaz marad)
        fej = repo.git("rev-parse", "HEAD").stdout.strip()
        blob = repo.git("rev-parse", "HEAD:a.md").stdout.strip()
        sorok = []
        for i in range(idegen):
            uzenet = f"gépi {i}\n\nMos-Kor: MAS-20261008-{i:06d}-aaaaaa\nMos-Forras: mos-proba\n".encode()
            sorok.append(f"commit refs/heads/main\ncommitter M <m@x> {1790000000 + i} +0000\ndata {len(uzenet)}\n".encode()
                         + uzenet + (f"from {fej}\n".encode() if i == 0 else b"") + f"M 100644 {blob} a.md\n\n".encode())
        subprocess.run(["git", "--git-dir", str(repo.git_dir), "fast-import", "--quiet", "--force"], input=b"".join(sorok),
                       check=True)
        repo.git("symbolic-ref", "HEAD", "refs/heads/main")
    (wt / "a.md").write_text("alap\nkör sora\n", encoding="utf-8")
    repo.commit_machine("kör tétele", {"Mos-Kor": KOR, "Mos-Forras": "mos-proba"}, ["a.md"])
    return repo


def _ido(f, n: int = 5) -> float:
    idok = []
    for _ in range(n):
        t0 = time.perf_counter()
        f()
        idok.append((time.perf_counter() - t0) * 1000)
    return sorted(idok)[n // 2]


class KorVisszavonasPerf(unittest.TestCase):
    def test_a_kor_keresese_nem_no_linearisan_a_tortenettel(self):
        with tempfile.TemporaryDirectory() as t1, tempfile.TemporaryDirectory() as t2:
            kicsi, nagy = _tarolo(Path(t1), 60), _tarolo(Path(t2), 6000)
            self.assertEqual(len(nagy.kor_commitok(KOR)), 1)
            self.assertEqual(len(nagy.log(run=KOR)), 1)
            a, b = _ido(lambda: kicsi.log(run=KOR)), _ido(lambda: nagy.log(run=KOR))
            self.assertLess(b, 3 * a + 50, f"60 commit: {a:.1f} ms, 6000 commit: {b:.1f} ms")
            t0 = time.perf_counter()
            nagy.undo_run(KOR)
            ido = (time.perf_counter() - t0) * 1000
            self.assertLess(ido, 1000, f"a kör-visszavonás 6000 commit mellett {ido:.0f} ms")
            print(f"\n[T174] kör keresése: 60 commit {a:.1f} ms, 6000 commit {b:.1f} ms; visszavonás {ido:.0f} ms", flush=True)


if __name__ == "__main__":
    unittest.main()
