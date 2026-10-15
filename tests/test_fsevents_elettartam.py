"""CX-014: a GCD visszahívása nem élheti túl a ctypes closure-t."""
import subprocess
import sys
import unittest
from tests import csak_darwin
from tests.helpers import REPO, env


class EletciklusTest(unittest.TestCase):
    @csak_darwin('A natív FSEvents/GCD életciklusa')
    def test_ismetelt_inditas_leallitas_gc_mellett(self):
        kod = '''
import gc, tempfile, threading
from pathlib import Path
from core.index.figyelo import FSEvents
with tempfile.TemporaryDirectory() as d:
    p = Path(d) / 'jegyzet.md'
    for i in range(60):
        jel = threading.Event()
        f = FSEvents(d, lambda *_: jel.set(), latencia=.001)
        f.indit()
        p.write_text(str(i))
        jel.wait(.04)
        f.leallit()
        del f
        gc.collect()
print('60 életciklus rendben')
'''
        r = subprocess.run([sys.executable, '-B', '-X', 'faulthandler', '-c', kod], cwd=REPO,
                           env=env(), capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('60 életciklus rendben', r.stdout)
