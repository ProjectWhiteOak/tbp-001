"""Fixture only. Separate processes exercise the control flow without claiming live proof."""
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import os
import secrets
import subprocess
import sys
from .protocol import (canonical, decode, digest, discover, make_beacon, make_response,
                       require, stamp, time, verify, ProtocolError)
from .sources import document, extract

ROOT="https://example.com/tbp-fixture/"
ID="TBP-001-DRYRUN-001"

def now():
    return datetime.now(timezone.utc)

def write(path,data):
    with path.open("xb") as file: file.write(data)

def put(path,obj): write(path,canonical(obj)+b"\n")
def read(path): return decode(path.read_bytes())
def files(root):
    return {p.relative_to(root).as_posix():sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and p!=root/"manifest.json"}

def a(public, evidence):
    b=make_beacon(ID,now())
    h=digest(b)
    put(evidence/"beacon.json",b)
    write(evidence/"beacon.sha256",(h+"\n").encode())
    name=secrets.token_hex(12)+".html"
    write(public/name,document({"beacon":b,"sha256":h}).encode())
    put(evidence/"publication.json",{"mode":"local fixture","url":ROOT+name,
                                     "observed_at":stamp(now()),"pid":os.getpid()})

def b(public, pulse_path, output):
    start=now()
    pages=sorted(public.glob("*.html"))
    require(len(pages)<=10 and all(not p.is_symlink() and p.stat().st_size<=1024*1024 for p in pages),
            "fixture bounds exceeded")
    url,beacon,h,report=discover(ROOT,[(ROOT+p.name,extract(p.read_text(encoding="utf-8")))
                                       for p in pages],ID)
    # Signal only readiness. The parent writes synthetic freshness data after start.
    print(stamp(start),flush=True)
    require(sys.stdin.readline().strip()=="READY","fixture source not released")
    pulse=read(pulse_path)
    end=now()
    r=make_response(beacon,h,pulse,start,end)
    put(output/"discovery.json",{"selected":url,"considered":report,"started_at":stamp(start),"pid":os.getpid()})
    put(output/"response.json",r)
    write(output/"response.sha256",(digest(r)+"\n").encode())

def verify_evidence(run):
    t0,t1=run/"t0",run/"t1"
    beacon=read(t0/"beacon.json")
    publication=read(t0/"publication.json")
    h=(t0/"beacon.sha256").read_text().strip()
    trace=read(t1/"discovery.json")
    started=time(trace["started_at"])
    require(time(publication["observed_at"])<started and publication["pid"]!=trace["pid"],
            "fixture isolation failure")
    url,b,h2,report=discover(ROOT,[(ROOT+p.name,extract(p.read_text(encoding="utf-8")))
                                  for p in sorted((run/"rendezvous").glob("*.html"))],ID)
    require((url,b,h2,report)==(publication["url"],beacon,h,trace["considered"]) and trace["selected"]==url,
            "fixture discovery evidence diverged")
    verify(beacon,h,read(t1/"response.json"),(t1/"response.sha256").read_text().strip(),
           read(run/"freshness"/"pulse.json"),ID,started)

def check(run):
    manifest=read(run/"manifest.json")
    require(manifest=={"mode":"fixture","files":files(run)},"bundle byte manifest mismatch")
    verify_evidence(run)
    print("FIXTURE PASS: separate processes, scoped rediscovery, challenge and freshness binding, evidence hashes")

def run(path):
    path.mkdir()
    public=path/"rendezvous"
    for name in ("rendezvous","t0","t1","freshness"): (path/name).mkdir()
    write(public/"unrelated.html",b"<p>Ordinary public fixture text</p>")
    env={"PATH":os.defpath,"PYTHONDONTWRITEBYTECODE":"1"}
    launch=[sys.executable,"-m","tbp.rehearsal"]
    subprocess.run([*launch,"a",str(public),str(path/"t0")],check=True,env=env)
    pulse=path/"freshness"/"pulse.json"
    # B only receives the rendezvous and pulse-source locations and its own output path.
    with subprocess.Popen([*launch,"b",str(public),str(pulse),str(path/"t1")],env=env,
                          stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True) as child:
        try:
            started=child.stdout.readline().strip()
            require(bool(started),"B did not start")
            when=now()
            require(when>time(started),"fixture clock did not advance")
            put(pulse,{"source":"fixture","event_id":"pulse-1","source_timestamp":stamp(when),
                       "value":secrets.token_hex(64)})
            child.stdin.write("READY\n")
            child.stdin.flush()
            require(child.wait(timeout=10)==0,"B failed")
        finally:
            if child.poll() is None: child.kill()
    verify_evidence(path)
    put(path/"verification.json",{"mode":"fixture","result":"PASS","verified_at":stamp(now()),
                                  "not_tested":["public publication","external randomness","scheduler",
                                                "sandbox isolation","model decisions","remote response publishing"]})
    put(path/"manifest.json",{"mode":"fixture","files":files(path)})
    check(path)

def main(args):
    mode,*paths=args
    actions={"run":run,"a":a,"b":b,"verify":check}
    actions[mode](*(Path(p).resolve() for p in paths))

if __name__=="__main__":
    try: main(sys.argv[1:])
    except (ProtocolError,OSError,subprocess.SubprocessError) as exc:
        sys.exit("TBP fixture failed: "+str(exc))
