"""F9 security audit §3: SSRF on the explicit external-image download (`core/kulso_kep.py`) and the video downloader's address check
(`core/videolanc._helyi_cim`), which share `videolanc._nem_nyilvanos`. No real network: the resolver is replaced, and a safety net
fails the test on any real `getaddrinfo` / `create_connection`.

Found and fixed in F9 (regression): the IPv4-compatible `::a.b.c.d` and the NAT64 prefix `64:ff9b::/96` were reported as
global by `ipaddress`, so `https://[64:ff9b::7f00:1]/` (the gateway's loopback on a DNS64/NAT64 network) and a DNS answer of
`64:ff9b::a00:1` (its private 10/8) passed the check."""
from __future__ import annotations

import ipaddress
import socket
import unittest
from unittest import mock

from core import kulso_kep, videolanc
from core.utvonalak import HttpError


class SsrfTest(unittest.TestCase):
    def setUp(self):
        for nev in ("getaddrinfo", "create_connection"):
            p = mock.patch.object(socket, nev, side_effect=AssertionError("real network request"))
            p.start()
            self.addCleanup(p.stop)
        self.dns: dict[str, list[str]] = {"ok.example": ["93.184.216.34"], "nat64-ok.example": ["64:ff9b::5db8:d822"]}
        for modul in (kulso_kep, videolanc):
            p = mock.patch.object(modul, "_felold", side_effect=self._felold)
            p.start()
            self.addCleanup(p.stop)

    def _felold(self, host):
        if host not in self.dns:
            raise socket.gaierror("no such name")
        return self.dns[host]

    def assert_tiltott(self, host: str):
        with self.subTest(host=host):
            with self.assertRaises(HttpError) as e:
                kulso_kep.nyilvanos_cimek(host)
            self.assertEqual((e.exception.code, e.exception.kod), (403, "kulso_kep.helyi_cim"), host)
            self.assertTrue(videolanc._helyi_cim(host), f"video downloader: {host}")

    def test_beagyazott_ipv4_cimek(self):
        for host in ("64:ff9b::7f00:1", "64:ff9b::127.0.0.1", "64:ff9b::a00:1", "64:ff9b::c0a8:101", "64:ff9b::a9fe:a9fe",
                     "::127.0.0.1", "::7f00:1", "::a00:1", "::8.8.8.8", "::ffff:127.0.0.1", "0:0:0:0:0:ffff:7f00:1",
                     "2002:7f00:1::1", "2001:0:4136:e378:8000:63bf:3fff:fdd2", "::", "::1", "fe80::1", "fc00::1", "ff02::1"):
            self.assert_tiltott(host)

    def test_dns_valasz_nat64_belso_cimmel(self):
        self.dns.update({"nat64-loop.example": ["64:ff9b::7f00:1"], "nat64-priv.example": ["64:ff9b::a00:5"],
                         "vegyes.example": ["93.184.216.34", "64:ff9b::a9fe:a9fe"], "kompat.example": ["::7f00:1"]})
        for host in ("nat64-loop.example", "nat64-priv.example", "vegyes.example", "kompat.example"):
            self.assert_tiltott(host)

    def test_nyilvanos_cim_es_nyilvanos_nat64_engedett(self):
        self.assertEqual(kulso_kep.nyilvanos_cimek("ok.example"), ["93.184.216.34"])
        self.assertEqual(kulso_kep.nyilvanos_cimek("nat64-ok.example"), ["64:ff9b::5db8:d822"])
        self.assertFalse(videolanc._nem_nyilvanos(ipaddress.ip_address("64:ff9b::808:808")))
        self.assertFalse(videolanc._nem_nyilvanos(ipaddress.ip_address("2606:4700::1111")))

    def test_nev_es_szamalakok(self):
        for host in ("localhost", "LOCALHOST", "localhost.", "a.localhost", "printer.local", "x.internal", "router.lan",
                     "box.home.arpa", "127.1", "0x7f.1", "0177.0.0.1", "2130706433", "0", "0.0.0.0", "127.0.0.1.",
                     "１２７.０.０.１", "127。0。0。1", "[::1]", "169.254.169.254",
                     "100.64.0.1", "198.18.0.1", "224.0.0.1", "255.255.255.255", "192.0.0.1"):
            self.assert_tiltott(host)

    def test_url_szint(self):
        for url, kod in (("https://[64:ff9b::7f00:1]/a.png", 403), ("https://[::127.0.0.1]/a.png", 403),
                         ("https://[64:ff9b::a00:1]:443/a.png", 403), ("https://[fe80::1%25en0]/a.png", 403),
                         ("http://[64:ff9b::5db8:d822]/a.png", 400), ("https://ok.example:80/a.png", 400),
                         ("https://ok.example@127.0.0.1/a.png", 400), ("https://127.0.0.1#@ok.example/a.png", 403)):
            with self.subTest(url=url), self.assertRaises(HttpError) as e:
                kulso_kep.letolt_bajtok(url)
            self.assertEqual(e.exception.code, kod, url)
