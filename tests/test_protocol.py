import unittest
from datetime import datetime, timezone, timedelta
from tbp.protocol import (canonical, digest, decode, make_beacon, discover,
                          make_response, verify, allowed, ProtocolError)

T0 = datetime(2026, 11, 22, tzinfo=timezone.utc)
T1 = T0 + timedelta(minutes=1)
ROOT = "https://example.com/tbp/"
ID = "TBP-001-DRYRUN-001"

class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.b = make_beacon(ID, T0)
        self.h = digest(self.b)
        self.pulse = {"source":"fixture","event_id":"pulse-1",
                      "source_timestamp":"2026-11-22T00:01:01Z","value":"ab"*64}
        self.end = T1 + timedelta(seconds=2)
    def test_generator(self):
        self.assertEqual(len(self.b["challenge_nonce"]),64)
        self.assertNotEqual(self.b["challenge_nonce"],make_beacon(ID,T0)["challenge_nonce"])
        with self.assertRaises(ProtocolError): make_beacon("invalid",T0)
        with self.assertRaises(ProtocolError): make_beacon(ID,T0.replace(tzinfo=None))
    def test_canonical(self):
        self.assertEqual(canonical(decode(b'{ "b":2,"a":1 }')),b'{"a":1,"b":2}')
        self.assertNotEqual(digest({"a":1}),digest({"a":2}))
        for payload in (b'{"a":1,"a":2}',b'{"a":NaN}',b'{"a":1.0}'):
            with self.assertRaises(ProtocolError): decode(payload)
    def test_allowed(self):
        self.assertTrue(allowed(ROOT,ROOT+"beacon"))
        for url in ("http://example.com/tbp/b", "https://evil.example/tbp/b",
                    "https://example.com/tbp/../secret","https://example.com/tbp/%2e%2e/x",
                    "https://example.com/tbp/b?q=x","https://example.com/tbpX/b",
                    "https://user@example.com/tbp/b"):
            self.assertFalse(allowed(ROOT,url),url)
    def test_discovery(self):
        good=(ROOT+"b",{"beacon":self.b,"sha256":self.h})
        bad=(ROOT+"bad",{"beacon":self.b,"sha256":"0"*64})
        other=make_beacon("TBP-001-DEV-009",T0)
        self.assertEqual(discover(ROOT,[bad,(ROOT+"x",None),
                         (ROOT+"old",{"beacon":other,"sha256":digest(other)}),good],ID)[0],ROOT+"b")
        for entries in ([bad], [good,(ROOT+"b2",good[1])], [("https://other.example/b",good[1])]):
            with self.assertRaises(ProtocolError): discover(ROOT,entries,ID)
    def test_full_verify(self):
        r=make_response(self.b,self.h,self.pulse,T1,self.end)
        verify(self.b,self.h,r,digest(r),self.pulse,ID,T1)
        cases=[({"experiment_id":"TBP-001-DRYRUN-007"},self.pulse),
               ({"discovered_beacon":{"hash":self.h,"challenge_nonce":"00"*32,"hash_algorithm":"SHA-256"}},self.pulse),
               ({},dict(self.pulse,value="01"*64))]
        for patch,pulse in cases:
            modified=dict(r,**patch)
            with self.assertRaises(ProtocolError):
                verify(self.b,self.h,modified,digest(modified),pulse,ID,T1)
        with self.assertRaises(ProtocolError): verify(self.b,self.h,r,"0"*64,self.pulse,ID,T1)
        with self.assertRaises(ProtocolError): verify(dict(self.b,challenge_nonce="00"*32),self.h,r,digest(r),self.pulse,ID,T1)
    def test_freshness(self):
        for patch in ({"source_timestamp":"2026-11-22T00:01:00Z"},
                      {"source_timestamp":"2026-11-22T00:01:03Z"},{"value":"garbage"}):
            with self.assertRaises(ProtocolError): make_response(self.b,self.h,dict(self.pulse,**patch),T1,self.end)
