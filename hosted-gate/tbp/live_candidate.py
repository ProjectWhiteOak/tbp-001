"""Network worker candidate. Deliberately cannot self-arm or claim a live pass."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
from .protocol import canonical, decode, digest, discover, match, make_response, require, stamp, time, verify
from .sources import api, firecrawl
from .direct_pages import crawl

ORIGIN = "https://projectwhiteoak.github.io/tbp-001/"
ID = r"TBP-001-(?:DRYRUN|LIVE)-[0-9]{3}"
MAIN = Path(__file__).resolve().parents[1]

def root_for(experiment_id):
    require(match(ID, experiment_id), "invalid run identifier")
    return ORIGIN + "runs/" + experiment_id.lower() + "/"

def candidate(experiment_id, start, out, request, pulse_reader):
    root = root_for(experiment_id)
    url, beacon, beacon_hash, trace = discover(root, firecrawl(root, request), experiment_id)
    return finish(experiment_id, start, out, url, beacon, beacon_hash, trace, pulse_reader)

def finish(experiment_id, start, out, url, beacon, beacon_hash, trace, pulse_reader):
    pulse = pulse_reader(start, out)
    end = datetime.now(timezone.utc)
    response = make_response(beacon, beacon_hash, pulse, start, end)
    response_hash = digest(response)
    verify(beacon, beacon_hash, response, response_hash, pulse, experiment_id, start)
    return {"beacon_url": url, "discovery_trace": trace, "response": response, "sha256": response_hash}

def runtime_pulse(start, out):
    result = subprocess.run(["node", str(MAIN/"quicknet.cjs"), stamp(start), str(out)],
      env={k:v for k,v in os.environ.items() if k.upper() in (
          "PATH","HTTPS_PROXY","HTTP_PROXY","ALL_PROXY","NO_PROXY","SSL_CERT_FILE","SSL_CERT_DIR")},
      stdout=subprocess.PIPE, check=True, timeout=32)
    return decode(result.stdout)

def stage(*, experiment_id, start, out, key=None):
    root_for(experiment_id)
    require(not experiment_id.startswith("TBP-001-LIVE-"),
      "official trial blocked: model, publisher and independent launch evidence not wired")
    out.mkdir()
    count = 0
    def capture(endpoint, raw):
        nonlocal count
        count += 1
        with (out/f"firecrawl-{count:02d}-{endpoint}.json").open("xb") as handle:
            handle.write(raw)
    if key is not None:
        result = candidate(experiment_id, start, out, api(key, capture), runtime_pulse)
    else:
        root = root_for(experiment_id)
        result = finish(experiment_id, start, out, *discover(
            root, crawl(root, capture_pages(out)), experiment_id), runtime_pulse)
    with (out/"response-candidate.json").open("xb") as handle:
        handle.write(canonical(result))
    return result["sha256"]

def capture_pages(out):
    count = 0
    def record(kind,url,status,raw):
        nonlocal count
        count += 1
        prefix = out / f"pages-{count:02d}-{kind}"
        prefix.with_suffix(".bin").write_bytes(raw)
        prefix.with_suffix(".json").write_bytes(canonical(
            {"url":url,"status":status,"observed_at":stamp(datetime.now(timezone.utc))}))
    return record

def main():
    start = datetime.now(timezone.utc)
    parser = argparse.ArgumentParser()
    parser.add_argument("experiment_id")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    sha = stage(experiment_id=args.experiment_id,start=start,out=args.out.resolve(),
                key=os.environ.get("FIRECRAWL_API_KEY") or None)
    print("CANDIDATE_RESPONSE_ONLY", sha)

if __name__=="__main__":
    main()
