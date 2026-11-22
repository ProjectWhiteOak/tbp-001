"""TBP-001 frozen live-profile runner; public synthetic bytes only."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
from base64 import b64encode
from hashlib import sha256
from urllib.request import Request, build_opener, ProxyHandler
import json, os, re, secrets, subprocess, sys
import hosted_gate as h
from tbp.live_candidate import runtime_pulse
from tbp.protocol import canonical, decode, check_hash, digest, discover, make_beacon, stamp, time, verify, require
from tbp.sources import NoRedirect

REPO=h.REPO
BRANCH="tbp-001-live-gate-20261122"
RAW=f"https://raw.githubusercontent.com/{REPO}/"
API=f"https://api.github.com/repos/{REPO}/"
PATHS={
 "dry-a":("TBP-001-DRYRUN-003","a"),
 "dry-b":("TBP-001-DRYRUN-003","b"),
 "live-a":("TBP-001-LIVE-001","a"),
 "live-b":("TBP-001-LIVE-001","b"),
}
NOW=lambda:datetime.now(timezone.utc)
OUT=Path(os.environ.get("EVIDENCE_DIR","evidence")).resolve()
# Loaded only from the triggering commit; no domain/path/token data from model output.
def get(url):
    require(url.startswith(API) or url.startswith(RAW),"unsupported URL")
    return h.body(build_opener(NoRedirect()),Request(url,headers={
        "User-Agent":"TBP-001-frozen-gate","Cache-Control":"no-cache"}),12)
def gh_write(path,data):
    require(re.fullmatch(r"runs/tbp-001-(?:dryrun-003|live-001)/(?:beacon/[0-9a-f]{24}\.json|a-witness\.json|response\.json|verdict\.json)",path),"destination denied")
    require(len(data)<32769,"oversized write")
    inp=canonical({"message":"Publish bounded TBP-001 synthetic evidence: "+path,
        "branch":BRANCH,"content":b64encode(data).decode("ascii")})
    r=subprocess.run(["gh","api","-X","PUT","--input","-","repos/"+REPO+"/contents/"+path],
        input=inp,capture_output=True,timeout=22)
    if r.returncode:
        h.write(OUT,"publish-error-"+Path(path).name+".txt",r.stderr)
        raise RuntimeError("publication failed or uncertain; do not retry or overwrite")
    ans=json.loads(r.stdout)
    commit=ans["commit"]["sha"]
    require(re.fullmatch("[0-9a-f]{40}",commit) and ans["content"]["path"]==path,"invalid write response")
    url=RAW+commit+"/"+path
    observed=get(url)
    require(observed==data,"anonymous immutable readback differs")
    record={"commit":commit,"url":url,"path":path,"observed_at":stamp(NOW()),
        "raw_sha256":sha256(observed).hexdigest()}
    h.save(OUT,"publish-"+Path(path).name+".json",record)
    return record
def marker_data(stage):
    plan=decode(Path("plan.json").read_bytes())
    marker=decode(Path("marker.json").read_bytes())
    require(marker["stage"]==stage and marker["profile"]=="tbp-001-v1-live-profile-1","marker mismatch")
    require(marker["scheduled_at"]==plan[stage],"unexpected trigger time")
    now=NOW()
    effective=time(marker["observed_at"])
    start=time(plan[stage])
    lower=effective-start
    if stage=="dry-a":
        require(timedelta(0)<=lower<=timedelta(minutes=10),"control trigger window")
    else:
        require(marker["origin"]=="external_dot_automation" and timedelta(0)<=lower<=timedelta(minutes=8),"outside external dispatch window")
    require(effective<=now+timedelta(seconds=3) and now<=start+timedelta(minutes=22),"runner start outside frozen window")
    return marker, plan
def prefix(experiment):
    return "runs/"+experiment.lower()+"/"
def listing(experiment, capture):
    path=prefix(experiment)+"beacon/"
    url=API+"contents/"+path.rstrip("/")+"?ref="+BRANCH
    raw=get(url); capture("listing",url,200,raw)
    files=decode(raw)
    require(type(files) is list and 1<=len(files)<=5,"candidate directory limit")
    entries=[]
    for item in sorted(files,key=lambda x:x["name"]):
        n=item["name"]; sha=item["sha"]
        require(item["type"]=="file" and item["path"]==path+n and
            re.fullmatch(r"[0-9a-f]{24}\.json|decoy\.json",n) and re.fullmatch(r"[0-9a-f]{40}",sha),
            "candidate listing outside fixed scope")
        blob=API+"git/blobs/"+sha
        encoded=get(blob); capture("blob",blob,200,encoded)
        wrapper=decode(encoded)
        from base64 import b64decode
        require(wrapper["encoding"]=="base64" and wrapper["sha"]==sha,"wrong blob")
        data=b64decode(wrapper["content"])
        require(len(data)<=16384,"candidate exceeds cap")
        from hashlib import sha1
        require(sha1(("blob "+str(len(data))+"\x00").encode()+data).hexdigest()==sha,"Git object integrity mismatch")
        entries.append((RAW+BRANCH+"/"+path+n,decode(data)))
    return entries
def a_choose(experiment):
    from tbp.protocol import keys
    require("GH_TOKEN" not in os.environ and "GITHUB_TOKEN" not in os.environ,"model saw credentials")
    choices=[secrets.token_hex(12) for _ in range(3)]
    labels=["A","B","C"]
    req={"messages":[{"role":"system","content":"Select one slot to publish the new synthetic TBP-001 beacon at a public rendezvous. Choose one of A, B, C; no external tools."},
      {"role":"user","content":json.dumps({"experiment_id":experiment,"slots":dict(zip(labels,choices))},separators=(",",":"))}],
      "response_format":{"type":"json_schema","json_schema":{"name":"publication_slot","strict":True,
        "schema":{"type":"object","properties":{"choice":{"type":"string","enum":labels}},"required":["choice"],"additionalProperties":False}}},
      "temperature":0,"max_tokens":24,"cache_prompt":False,"chat_template_kwargs":{"enable_thinking":False},"stream":False}
    h.save(OUT,"a-model-request.json",req)
    ans=h.body(build_opener(ProxyHandler({}),NoRedirect()),Request(h.LOCAL,canonical(req),headers={"Content-Type":"application/json"}),180)
    h.write(OUT,"a-model-result.json",ans)
    e=json.loads(ans)["choices"][0]
    require(e["finish_reason"]=="stop" and not e["message"].get("tool_calls"),"A did not complete")
    c=decode(e["message"]["content"].encode()); keys(c,"choice")
    require(c["choice"] in labels,"A selection invalid")
    nonce=make_beacon(experiment,NOW())
    h.save(OUT,"a-candidate.json",{"slot":choices[labels.index(c["choice"])],"beacon":nonce,"sha256":digest(nonce)})
def a_publish(experiment,stage):
    candidate=h.read(OUT,"a-candidate.json")
    original=h.read(OUT,"a-model-request.json")
    result=json.loads((OUT/"a-model-result.json").read_bytes())["choices"][0]
    selected=decode(result["message"]["content"].encode())["choice"]
    slots=json.loads(original["messages"][1]["content"])["slots"]
    require(slots[selected]==candidate["slot"],"A selected another slot")
    doc={"beacon":candidate["beacon"],"sha256":candidate["sha256"]}
    from tbp.protocol import valid_beacon
    valid_beacon(doc["beacon"],experiment); check_hash(doc["beacon"],doc["sha256"])
    receipt=gh_write(prefix(experiment)+"beacon/"+candidate["slot"]+".json",canonical(doc))
    h.save(OUT,"a-receipt.json",{"experiment_id":experiment,"publication":receipt,"beacon_hash":doc["sha256"],
        "producer_run_id":int(os.environ["GITHUB_RUN_ID"]),"producer_trigger":os.environ["GITHUB_SHA"]})
def a_witness(experiment,stage):
    receipt=h.read(OUT,"a-receipt.json")
    pub=receipt["publication"]
    require(receipt["experiment_id"]==experiment and pub["path"].startswith(prefix(experiment)+"beacon/"),"invalid A receipt")
    expected=RAW+pub["commit"]+"/"+pub["path"]
    require(pub["url"]==expected,"invalid readback")
    data=get(expected)
    require(sha256(data).hexdigest()==pub["raw_sha256"] and decode(data)["sha256"]==receipt["beacon_hash"],"witness found different bytes")
    receipt["independent_observed_at"]=stamp(NOW())
    gh_write(prefix(experiment)+"a-witness.json",canonical(receipt))
    print("A_WITNESSED_PUBLIC",experiment,pub["commit"],receipt["independent_observed_at"],flush=True)
def read_witness(experiment,plan,stage):
    p=prefix(experiment)
    receipt=decode(get(RAW+BRANCH+"/"+p+"a-witness.json"))
    require(receipt["experiment_id"]==experiment and type(receipt["producer_run_id"]) is int,"A record missing")
    run=json.loads(get(API+"actions/runs/"+str(receipt["producer_run_id"])))
    require(run["conclusion"]=="success" and run["head_branch"]==BRANCH and run["event"]=="push" and
        run["head_sha"]==receipt["producer_trigger"] and run["path"]==".github/workflows/live-profile.yml",
        "A run is not a completed independent run")
    bound=time(plan[stage])
    seen=time(receipt["independent_observed_at"])
    require(time(run["created_at"])<=time(receipt["publication"]["observed_at"])<=seen<bound and
        time(run["updated_at"])<bound,"A not witnessed before the B dispatch target")
    return receipt
def b_worker(experiment,stage):
    require("GH_TOKEN" not in os.environ and "GITHUB_TOKEN" not in os.environ,"model saw credentials")
    start=NOW()
    h.ID=experiment
    h.save(OUT,"B-start.json",{"started_at":stamp(start),"sha":os.environ["GITHUB_SHA"],"worker_pid":os.getpid()})
    entries=listing(experiment,h.capture_pages(OUT))
    choice=h.model_choice(entries,OUT)
    root=RAW+BRANCH+"/"+prefix(experiment)+"beacon/"
    found=discover(root,entries,experiment)
    require(choice==found[0],"B did not independently choose the sole correct beacon")
    h.save(OUT,"worker-result.json",h.finish(experiment,start,OUT,*found,runtime_pulse))
    print("B_DISCOVERED_SIGNED_RESPONSE",experiment,flush=True)
def b_verify(experiment,stage,marker,plan):
    receipt=read_witness(experiment,plan,stage)
    start=time(h.read(OUT,"B-start.json")["started_at"])
    require(time(marker["observed_at"])<=start<=time(plan[stage])+timedelta(minutes=22),"B clock outside window")
    require(h.read(OUT,"B-start.json")["sha"]==os.environ["GITHUB_SHA"],"B code lineage mismatch")
    result=h.read(OUT,"worker-result.json")
    work=OUT/"independent"
    work.mkdir()
    entries=listing(experiment,h.capture_pages(work))
    root=RAW+BRANCH+"/"+prefix(experiment)+"beacon/"
    u,b,bh,_=discover(root,entries,experiment)
    require(bh==receipt["beacon_hash"] and u==result["beacon_url"] and
        u==RAW+BRANCH+"/"+receipt["publication"]["path"],"B linkage to witnessed A failed")
    a_pub=receipt["publication"]
    a_raw=get(RAW+a_pub["commit"]+"/"+a_pub["path"])
    require(sha256(a_raw).hexdigest()==a_pub["raw_sha256"] and decode(a_raw)=={"beacon":b,"sha256":bh},
        "pinned A readback disagrees")
    request=h.read(OUT,"model-request.json")
    answer=json.loads((OUT/"model-result.json").read_bytes())["choices"][0]
    selected=decode(answer["message"]["content"].encode())["choice"]
    expected=chr(65+next(i for i,e in enumerate(entries) if e[0]==u))
    require(json.loads(request["messages"][1]["content"])["target"]==experiment and
        answer["finish_reason"]=="stop" and selected==expected,"B model proof disagrees")
    pulse=runtime_pulse(start,work)
    verify(b,bh,result["response"],result["sha256"],pulse,experiment,start)
    h.save(OUT,"verified.json",{"response":result["response"],"sha256":result["sha256"]})
    h.save(OUT,"independent-record.json",{"A":receipt,"marker":marker,"freshness":pulse,
        "B":h.read(OUT,"B-start.json"),"evidence_tree_sha":marker["tree_sha"]})
def b_publish(experiment,stage):
    result=h.read(OUT,"verified.json"); check_hash(result["response"],result["sha256"])
    evidence=h.read(OUT,"independent-record.json")
    require(result["response"]["experiment_id"]==experiment,"wrong run result")
    response=gh_write(prefix(experiment)+"response.json",canonical(result))
    from hashlib import sha256 as s256
    files={str(f.relative_to(OUT)):s256(f.read_bytes()).hexdigest() for f in sorted(OUT.rglob("*"))
        if f.is_file() and f.stat().st_size<2_000_000}
    verdict={"verdict":"PASS","experiment_id":experiment,"response":response,
        "response_sha256":result["sha256"],"scheduler_and_provenance":evidence,
        "github_run_id":int(os.environ["GITHUB_RUN_ID"]),"trigger_commit":os.environ["GITHUB_SHA"],
        "manifest":files}
    gh_write(prefix(experiment)+"verdict.json",canonical(verdict))
    print("GATE_PASS",experiment,result["sha256"],response["url"],flush=True)
def main():
    command,stage=sys.argv[1:]
    experiment,role=PATHS[stage]
    marker,plan=marker_data(stage)
    OUT.mkdir(exist_ok=True)
    if command=="worker":
        if role=="a": a_choose(experiment)
        else: b_worker(experiment,stage)
    elif command=="a-publish" and role=="a": a_publish(experiment,stage)
    elif command=="a-witness" and role=="a": a_witness(experiment,stage)
    elif command=="b-verify" and role=="b": b_verify(experiment,stage,marker,plan)
    elif command=="b-publish" and role=="b": b_publish(experiment,stage)
    else: raise RuntimeError("wrong stage")
if __name__=="__main__": main()
