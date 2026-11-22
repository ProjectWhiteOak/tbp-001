"""TBP-001/v1 deterministic, offline verification core."""
from datetime import datetime, timezone
from hashlib import sha256
from hmac import compare_digest
import ipaddress
import json
import re
import secrets
from urllib.parse import urlsplit

VERSION = "TBP-001/v1"
ID_PATTERN = r"TBP-001-(?:DEV|DRYRUN|LIVE)-[0-9]{3}"
CONTEXT = "TBP-001 rendezvous"
INSTRUCTIONS = {k: True for k in ("discover", "verify", "obtain_freshness_proof", "publish_response")}

class ProtocolError(ValueError):
    pass

def require(ok, message):
    if not ok:
        raise ProtocolError(message)

def unique(pairs):
    obj = {}
    for k, v in pairs:
        require(k not in obj, "duplicate JSON key")
        obj[k] = v
    return obj

def reject_number(_):
    raise ProtocolError("non-integer JSON number")

def decode(data):
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=unique,
                          parse_float=reject_number, parse_constant=reject_number)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ProtocolError("invalid strict JSON") from exc

def check_type(o):
    if type(o) in (str, int, bool, type(None)):
        return
    if type(o) is dict and all(type(k) is str for k in o):
        for v in o.values(): check_type(v)
        return
    if type(o) is list:
        for v in o: check_type(v)
        return
    raise ProtocolError("unsupported canonical JSON type")

def canonical(o):
    try:
        check_type(o)
        return json.dumps(o, ensure_ascii=False, sort_keys=True,
                          allow_nan=False, separators=(",", ":")).encode("utf-8")
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ProtocolError("not canonicalizable") from exc

def digest(o):
    return sha256(canonical(o)).hexdigest()

def match(pattern, s):
    return type(s) is str and re.fullmatch(pattern, s) is not None

def stamp(dt):
    require(isinstance(dt, datetime) and dt.utcoffset() is not None, "timezone required")
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00","Z")

def time(s):
    require(match(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z",s), "UTC timestamp required")
    try:
        return datetime.fromisoformat(s)
    except ValueError as exc:
        raise ProtocolError("invalid timestamp") from exc

def keys(o, *fields):
    require(type(o) is dict and o.keys() == set(fields),"unexpected object shape")

def valid_beacon(b, expected):
    keys(b,"protocol","experiment_id","created_at","origin_agent","challenge_nonce",
         "instructions","discovery_context","response_schema_version","hash_algorithm")
    require(match(ID_PATTERN,expected) and b["experiment_id"] == expected,"wrong experiment")
    require(b["protocol"] == VERSION and b["origin_agent"] == "AGENT-A"
            and b["hash_algorithm"] == "SHA-256" and b["response_schema_version"] == "1"
            and b["discovery_context"] == CONTEXT
            and canonical(b["instructions"]) == canonical(INSTRUCTIONS),"unsupported beacon")
    require(match(r"[a-f0-9]{64}",b["challenge_nonce"]),"invalid nonce")
    return time(b["created_at"])

def make_beacon(experiment_id, now):
    obj = {"protocol":VERSION,"experiment_id":experiment_id,"created_at":stamp(now),
           "origin_agent":"AGENT-A","challenge_nonce":secrets.token_hex(32),
           "instructions":dict(INSTRUCTIONS),"discovery_context":CONTEXT,
           "response_schema_version":"1","hash_algorithm":"SHA-256"}
    valid_beacon(obj,experiment_id)
    return obj

def check_hash(o,h):
    require(match(r"[a-f0-9]{64}",h) and compare_digest(digest(o),h),"hash mismatch")

def parsed_url(s):
    # Deliberately narrow URL profile. No redirects, encoding or path normalization.
    require(match(r"https://[a-z0-9.-]+/[A-Za-z0-9./_-]*",s),"invalid scoped HTTPS URL")
    item = urlsplit(s)
    host = item.hostname
    require("." in host and match(r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z][a-z0-9-]*",host)
            and not host.endswith((".local",".internal",".localhost",".test",".invalid")),
            "not a public DNS name")
    try: ipaddress.ip_address(host)
    except ValueError: pass
    else: raise ProtocolError("IP literals forbidden")
    require(not any(p in (".","..") for p in item.path.split("/")) and "//" not in item.path,
            "ambiguous path")
    return item

def allowed(root,url):
    try:
        a,b = parsed_url(root),parsed_url(url)
        return a.path.endswith("/") and a.netloc == b.netloc and b.path.startswith(a.path)
    except ProtocolError:
        return False

def discover(root, entries, expected):
    require(allowed(root,root),"invalid discovery root")
    require(match(ID_PATTERN,expected),"invalid experiment ID")
    found, report, seen = [], [], set()
    for i,(url,candidate) in enumerate(entries):
        require(i<20,"discovery page limit exceeded")
        if not allowed(root,url):
            report.append({"url":None,"result":"OUT_OF_SCOPE"})
            continue
        if url in seen: continue
        seen.add(url)
        try:
            keys(candidate,"beacon","sha256")
            b,h = candidate["beacon"],candidate["sha256"]
            valid_beacon(b,expected)
            check_hash(b,h)
        except ProtocolError:
            report.append({"url":url,"result":"REJECTED"})
            continue
        found.append((url,b,h))
        report.append({"url":url,"result":"HASH_OK"})
    require(len(found)==1,"expected exactly one qualifying beacon, found %d" % len(found))
    return *found[0],report

def validate_pulse(pulse,start,end):
    keys(pulse,"source","event_id","source_timestamp","value")
    require(match(r"[A-Za-z0-9_.:-]{1,128}",pulse["source"]) and
            match(r"[A-Za-z0-9_.:-]{1,128}",pulse["event_id"]) and
            match(r"[a-f0-9]{128}",pulse["value"]),"malformed freshness record")
    require(start < time(pulse["source_timestamp"]) <= end,"pulse outside T1 window")

def make_response(b,h,pulse,start,end):
    check_hash(b,h)
    require(valid_beacon(b,b.get("experiment_id")) < start,"beacon not before T1")
    validate_pulse(pulse,start,end)
    return {"protocol":VERSION,"experiment_id":b["experiment_id"],
            "responding_agent":"AGENT-B","started_at":stamp(start),"executed_at":stamp(end),
            "discovered_beacon":{"hash_algorithm":"SHA-256","hash":h,
                                 "challenge_nonce":b["challenge_nonce"]},
            "freshness_proof":pulse,"status":"HANDSHAKE_COMPLETE"}

def verify(b,h,r,rh,independent_pulse,expected,t1):
    valid_beacon(b,expected)
    check_hash(b,h)
    check_hash(r,rh)
    require(type(r) is dict and r.get("started_at") == stamp(t1),"unmatched scheduler timestamp")
    want = make_response(b,h,independent_pulse,t1,time(r.get("executed_at")))
    require(canonical(r)==canonical(want),"response not bound to verified inputs")
