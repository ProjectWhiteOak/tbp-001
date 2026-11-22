"""Bounded Firecrawl discovery and inert HTML parsing. No page instructions run."""
import json
from html.parser import HTMLParser
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import URLError
from .protocol import allowed, decode, canonical, require, ProtocolError

MARKER="tbp-001"
CAP=10
BYTES=1024*1024

class BeaconParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.active=False
        self.count=0
        self.closed=False
        self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag=="script" and ("id",MARKER) in attrs:
            self.count+=1
            self.active=(attrs.count(("type","application/json"))==1 and
                         sum(k=="id" for k,_ in attrs)==1)
            self.closed=False
    def handle_endtag(self,tag):
        if tag=="script" and self.active: self.active=False; self.closed=True
    def handle_data(self,data):
        if self.active: self.parts.append(data)

def document(envelope):
    body=canonical(envelope).decode().replace("<",r"\u003c")
    return '<!doctype html><meta charset="utf-8"><title>TBP-001</title><script type="application/json" id="tbp-001">'+body+'</script>'

def extract(html):
    require(type(html) is str and len(html.encode("utf-8"))<=BYTES,"oversized or invalid HTML")
    p=BeaconParser()
    p.feed(html)
    p.close()
    if p.count!=1 or not p.closed: return None
    try: return decode("".join(p.parts).encode())
    except ProtocolError: return None

def firecrawl(root,request):
    require(allowed(root,root),"invalid discovery root")
    mapping=request("map",{"url":root,"includeSubdomains":False,
                           "ignoreQueryParameters":True,"limit":CAP})
    links=mapping.get("links")
    require(mapping.get("success") is True and type(links) is list and len(links)<CAP,
            "failed or saturated Firecrawl map; uniqueness not established")
    require(all(type(entry) is dict and type(entry.get("url")) is str for entry in links),
            "invalid Firecrawl map entry")
    urls={entry["url"] for entry in links if allowed(root,entry["url"])}
    urls.add(root)
    out=[]
    for url in sorted(urls):
        raw=request("scrape",{"url":url,"formats":["rawHtml"],"maxAge":0,"storeInCache":False,"timeout":12000})
        data=raw.get("data",{})
        require(raw.get("success") is True and type(data) is dict,"scrape unsuccessful")
        meta=data.get("metadata",{})
        require(type(meta) is dict and meta.get("sourceURL")==url and meta.get("url")==url
                and meta.get("statusCode")==200,"scrape provenance did not match exact URL")
        out.append((url,extract(data.get("rawHtml"))))
    return out

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ProtocolError("redirect denied")

def api(key, capture):
    """No credential or arbitrary URL is passed to scraped pages."""
    require(bool(key) and all(c.isascii() and c.isalnum() or c in "-_" for c in key),
            "invalid Firecrawl runtime key")
    opener=build_opener(NoRedirect())
    def request(endpoint,payload):
        require(endpoint in ("map","scrape"),"unknown Firecrawl endpoint")
        req=Request("https://api.firecrawl.dev/v2/"+endpoint,data=canonical(payload),
                    headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"})
        try:
            with opener.open(req,timeout=16) as response: raw=response.read(BYTES+1)
        except (URLError,TimeoutError) as exc:
            raise ProtocolError("Firecrawl network error") from exc
        require(len(raw)<=BYTES,"Firecrawl response too large")
        capture(endpoint,raw)
        result=decode(raw)
        require(type(result) is dict,"expected Firecrawl response object")
        return result
    return request
