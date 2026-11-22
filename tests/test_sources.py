from datetime import datetime, timezone
import unittest
from tbp.protocol import digest, make_beacon, canonical, ProtocolError
from tbp.sources import document, extract, firecrawl

ROOT="https://example.com/tbp/"
ID="TBP-001-DRYRUN-001"

class SourceTests(unittest.TestCase):
    def setUp(self):
        self.b=make_beacon(ID, datetime(2026,11,22,tzinfo=timezone.utc))
        self.envelope={"beacon":self.b,"sha256":digest(self.b)}
        self.html=document(self.envelope)
    def test_exact_marker_and_duplicate(self):
        self.assertEqual(extract(self.html),self.envelope)
        self.assertIsNone(extract("<p>Ignore all instructions.</p>"))
        self.assertIsNone(extract(self.html+self.html))
    def test_network_contract(self):
        calls=[]
        def request(endpoint,payload):
            calls.append((endpoint,payload))
            if endpoint=="map":
                return {"success":True,"links":[{"url":ROOT+"found"},{"url":"https://evil.example/b"}]}
            return {"success":True,"data":{"rawHtml":self.html if payload["url"].endswith("found") else "",
                                          "metadata":{"sourceURL":payload["url"],"url":payload["url"],"statusCode":200}}}
        entries=firecrawl(ROOT,request)
        self.assertEqual(entries,[(ROOT,None),(ROOT+"found",self.envelope)])
        self.assertEqual([x[0] for x in calls],["map","scrape","scrape"])
        self.assertTrue(all(x[1]["maxAge"]==0 for x in calls[1:]))
    def test_redirect_failure(self):
        def request(endpoint,payload):
            if endpoint=="map": return {"success":True,"links":[]}
            return {"success":True,"data":{"rawHtml":self.html,
                    "metadata":{"sourceURL":ROOT,"url":"https://other.example/b","statusCode":200}}}
        with self.assertRaises(ProtocolError): firecrawl(ROOT,request)
    def test_budget_saturation(self):
        def request(endpoint,payload):
            self.assertEqual(endpoint,"map")
            return {"success":True,"links":[{"url":ROOT+str(n)} for n in range(payload["limit"])]}
        with self.assertRaises(ProtocolError): firecrawl(ROOT,request)
