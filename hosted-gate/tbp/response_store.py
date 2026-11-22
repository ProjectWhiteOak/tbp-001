"""Create-only public response transport. Call only after independent verification."""
from base64 import b64encode
import re
from urllib.request import build_opener, ProxyHandler, Request
from .protocol import canonical, decode, keys, match, check_hash, require
from .sources import NoRedirect
from .live_candidate import ID

REPO = "ProjectWhiteOak/tbp-001"
API = f"https://api.github.com/repos/{REPO}/contents/"
RAW = f"https://raw.githubusercontent.com/{REPO}/"
CAP = 32_768
SHA = r"[0-9a-f]{40}"

class PublicationUncertain(ValueError):
    """An attempted write may exist; inspect its exact path, never retry blindly."""

def store(experiment_id, response_envelope, explicitly_verified, token, request):
    require(explicitly_verified is True, "independent verification required")
    require(match(ID, experiment_id), "invalid run identifier")
    keys(response_envelope, "response", "sha256")
    response = response_envelope["response"]
    require(response["experiment_id"] == experiment_id, "run identifier mismatch")
    check_hash(response, response_envelope["sha256"])
    require(isinstance(token, str) and bool(re.fullmatch(r"[A-Za-z0-9_]{30,255}", token)), "missing scoped publisher token")
    path = "results/" + experiment_id.lower() + "/response.json"
    contents = canonical(response_envelope)
    require(len(contents) < CAP, "response too large")
    body = canonical({"message":"TBP-001 publish " + experiment_id, "branch":"main",
                      "content":b64encode(contents).decode("ascii")})
    try:
        receipt_raw = request("PUT", API+path, body, token, 201)
        receipt = decode(receipt_raw)
        commit = receipt["commit"]["sha"]
        require(match(SHA,commit) and receipt["content"]["path"] == path, "wrong write receipt")
        url = RAW+commit+"/"+path
        observed = request("GET", url, None, None, 200)
        require(observed == contents, "inexact public read-back")
    except (ValueError, KeyError, OSError) as exc:
        raise PublicationUncertain(f"Check exact path {path} before any further action") from exc
    return {"commit":commit,"url":url,"receipt":receipt_raw,"readback":observed}

def https(method, url, body, token, expected_status):
    require((method=="PUT" and url.startswith(API) and token is not None) or
            (method=="GET" and url.startswith(RAW) and token is None), "destination blocked")
    headers = {"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2026-03-10",
               "Content-Type":"application/json","User-Agent":"TBP-001-response-publisher"}
    if token is not None:
        headers["Authorization"] = "Bearer "+token
    opener = build_opener(ProxyHandler({}), NoRedirect())
    with opener.open(Request(url,method=method,data=body,headers=headers), timeout=10) as result:
        require(result.geturl()==url and result.status==expected_status,"unexpected GitHub response")
        raw = result.read(CAP+1)
    require(len(raw)<=CAP,"oversized GitHub response")
    return raw
