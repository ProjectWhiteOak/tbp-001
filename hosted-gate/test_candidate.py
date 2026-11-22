import json
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from datetime import datetime, timedelta, timezone
from tbp.live_candidate import root_for, stage
from tbp.protocol import canonical, digest, make_beacon, make_response, stamp
from tbp.response_store import store, PublicationUncertain

class CandidateTests(unittest.TestCase):
    def payload(self):
        eid="TBP-001-DRYRUN-009"
        t=datetime.now(timezone.utc)
        b=make_beacon(eid,t-timedelta(seconds=2))
        pulse={"source":"fixture","event_id":"test","source_timestamp":stamp(t+timedelta(seconds=1)),"value":"a"*128}
        r=make_response(b,digest(b),pulse,t,t+timedelta(seconds=2))
        return eid, {"response":r,"sha256":digest(r)}
    def test_live_blocked_before_network_or_output(self):
        with TemporaryDirectory() as d:
            out=Path(d)/"unused"
            with self.assertRaisesRegex(ValueError,"official trial blocked"):
                stage(experiment_id="TBP-001-LIVE-001",start=datetime.now(timezone.utc),out=out,key="bad")
            self.assertFalse(out.exists())
    def test_root_cannot_escape(self):
        with self.assertRaises(ValueError): root_for("../CrewGuard")
    def test_write_only_if_verified_and_anonymous_readback(self):
        eid, data=self.payload()
        transcript=[]
        def request(method,url,body,token,expected):
            transcript.append((method,url,token,expected))
            if method=="PUT":
                self.assertNotIn("sha",json.loads(body))
                return canonical({"commit":{"sha":"a"*40},"content":{"path":"results/tbp-001-dryrun-009/response.json"}})
            return canonical(data)
        with self.assertRaisesRegex(ValueError,"independent"):
            store(eid,data,False,"x"*40,request)
        self.assertEqual(transcript,[])
        self.assertEqual(store(eid,data,True,"x"*40,request)["commit"],"a"*40)
        self.assertEqual(transcript[-1][0::2],("GET",None))
    def test_conflict_never_retried(self):
        eid, data=self.payload()
        calls=[]
        def request(*args):
            calls.append(args[0]); raise OSError("conflict")
        with self.assertRaises(PublicationUncertain):
            store(eid,data,True,"x"*40,request)
        self.assertEqual(calls,["PUT"])

if __name__=="__main__":
    unittest.main()
