import http.client
import json
import signal
import socket
import subprocess
import sys
import threading
import time
import unittest

from tests.helpers import API_TITOK, REPO, alg_gyoker, env, tmpdir


class ServerTeszt(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        root = alg_gyoker(self._t.name)
        self.p = subprocess.Popen([sys.executable, "-B", "-m", "core", "start"], cwd=REPO, stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, env=env(MOS_ROOT=str(root), PYTHONPATH=str(REPO)))
        self.addCleanup(lambda: (self.p.kill(), self.p.wait()) if self.p.poll() is None else None)
        self.addCleanup(lambda: [f.close() for f in (self.p.stdout, self.p.stdin) if f and not f.closed])
        self.kezfogas = json.loads(self.p.stdout.readline())
        self.port = self.kezfogas["port"]

    def get(self, path, host=None, fejlec=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("GET", path, headers={"Host": host or f"127.0.0.1:{self.port}", **(fejlec or {})})
        r = c.getresponse()
        return r.status, r.read()

    def test_kezfogas(self):
        self.assertEqual(self.kezfogas["pid"], self.p.pid)
        self.assertGreater(self.port, 0)

    def test_ures_lap(self):
        st, body = self.get("/")
        self.assertEqual(st, 200)
        self.assertIn(b"<body></body>", body)

    def test_valaszfejlecek_keretezes_ellen(self):
        """T103 (2. audit): `X-Frame-Options: SAMEORIGIN` és `Content-Security-Policy: frame-ancestors 'self'` minden válaszon
        (statikus lap, JSON, hibák); a `<meta>` CSP-ben a `frame-ancestors` nem hat."""
        def fejlec(path, host=None, fej=None):
            c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
            c.request("GET", path, headers={"Host": host or f"127.0.0.1:{self.port}", **(fej or {})})
            r = c.getresponse()
            r.read()
            return r.status, {k.lower(): v for k, v in r.getheaders()}

        for path, host, fej, kod in (("/", None, None, 200), ("/health", None, {"X-Manifold": API_TITOK}, 200),
                                     ("/api/allapot", None, {"X-Manifold": API_TITOK}, 200), ("/api/nincs", None, {"X-Manifold": API_TITOK}, 404),
                                     ("/health", None, None, 403), ("/", "pelda.hu", None, 403)):
            st, f = fejlec(path, host, fej)
            self.assertEqual(st, kod, path)
            self.assertEqual(f.get("x-frame-options"), "SAMEORIGIN", path)
            self.assertIn("frame-ancestors 'self'", f.get("content-security-policy", ""), path)

    def test_idegen_gazda_tiltott(self):
        self.assertEqual(self.get("/", host="pelda.hu")[0], 403)

    def test_health_x_manifold_kell(self):
        self.assertEqual(self.get("/health")[0], 403)
        self.assertEqual(self.get("/health", fejlec={"X-Manifold": API_TITOK})[0], 200)

    def test_stdin_lezaras_leall(self):
        self.p.stdin.close()
        self.assertEqual(self.p.wait(timeout=5), 0)

    def _kezelo_elindult(self):
        """T085: egy MÁSODIK, teljes kérés válasza bizonyítja, hogy az első (félig küldött) kapcsolat kezelőszála már él: a
        szerver a kapcsolatokat sorban fogadja el, és kapcsolatonként új szálat indít."""
        self.assertEqual(self.get("/health", fejlec={"X-Manifold": API_TITOK})[0], 200)

    def _var_a_port_zarasara(self, mp=10):
        """A rendezett leállás eseménye (T085): a `httpd.shutdown()` után a `server_close()` bezárja a figyelő portot, és
        csak ezután vár a folyamatban lévő kérésekre. Fix `sleep` helyett erre várunk."""
        t0 = time.monotonic()
        while time.monotonic() - t0 < mp:
            try:
                socket.create_connection(("127.0.0.1", self.port), timeout=0.5).close()
            except OSError:
                return True
            time.sleep(0.05)
        return False

    def test_folyamatban_levo_kerest_megvarja(self):
        s = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        s.sendall(f"GET / HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n".encode())   # a kérés még nincs lezárva
        self._kezelo_elindult()
        self.p.stdin.close()
        self.assertTrue(self._var_a_port_zarasara(), "a rendezett leállás nem kezdődött el")
        self.assertIsNone(self.p.poll(), "a folyamatban lévő kérés előtt nem állhat le")
        s.sendall(b"\r\n")
        self.assertIn(b"200 OK", s.recv(4096))
        s.close()
        self.assertEqual(self.p.wait(timeout=5), 0)

    def test_sigterm_a_folyo_kerest_befejezi(self):
        """H6 (audit): a második ⌘Q SIGTERM-et küld — a core ne haljon meg azonnal: a folyamatban lévő kérés
        (mentés, átnevezés) befejeződik, utána rendben (0-val) kilép."""
        s = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        s.sendall(f"GET / HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n".encode())
        self._kezelo_elindult()
        self.p.send_signal(signal.SIGTERM)
        self.assertTrue(self._var_a_port_zarasara(), "a rendezett leállás nem kezdődött el")
        self.assertIsNone(self.p.poll(), "SIGTERM-re a folyamatban lévő kérés előtt nem állhat le")
        s.sendall(b"\r\n")
        self.assertIn(b"200 OK", s.recv(4096))
        s.close()
        self.assertEqual(self.p.wait(timeout=15), 0)

    def test_listen_sor_nagy_kapcsolat_rohamot_is_kiszolgal(self):
        """T021 (2. audit): a `ThreadingHTTPServer` listen-sora alapból 5, és minden kérés új kapcsolat (nincs keep-alive):
        roham alatt a kernel RST-vel visszautasított. A sor 128, 60 egyidejű kapcsolat mind választ kap."""
        from core import server
        self.assertGreaterEqual(server.Szerver.request_queue_size, 128)
        n, hibak, kapu = 60, [], threading.Barrier(60)

        def kapcsol():
            try:
                kapu.wait(20)
                st, _ = self.get("/health", fejlec={"X-Manifold": API_TITOK})
                if st != 200:
                    hibak.append(st)
            except (OSError, threading.BrokenBarrierError) as e:
                hibak.append(repr(e))

        szalak = [threading.Thread(target=kapcsol) for _ in range(n)]
        for t in szalak:
            t.start()
        for t in szalak:
            t.join(60)
        self.assertEqual(hibak, [])

    def test_sigterm_tetlenul_gyorsan_kilep(self):
        t0 = time.monotonic()
        self.p.send_signal(signal.SIGTERM)
        self.assertEqual(self.p.wait(timeout=10), 0)
        self.assertLess(time.monotonic() - t0, 5)


if __name__ == "__main__":
    unittest.main()
