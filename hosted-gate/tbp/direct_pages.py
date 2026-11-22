"""One-hop, keyless discovery from the experiment's fixed public Pages origin."""
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import build_opener, Request
from urllib.robotparser import RobotFileParser
from .protocol import allowed, require
from .sources import BYTES, CAP, NoRedirect, extract

HOST = "https://projectwhiteoak.github.io"
PREFIX = HOST + "/tbp-001/"
ROBOTS = HOST + "/robots.txt"
AGENT = "TBP-001-Discovery"

class RootLinks(HTMLParser):
    def __init__(self, root):
        super().__init__()
        self.root, self.urls = root, set()
    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        hrefs = [value for key, value in attrs if key == "href"]
        if len(hrefs) == 1 and hrefs[0]:
            url = urljoin(self.root,hrefs[0])
            if allowed(self.root,url) and url != self.root:
                self.urls.add(url)

def https(url, kind):
    require((kind == "robots" and url == ROBOTS) or
            (kind == "html" and allowed(PREFIX,url)), "HTTPS destination blocked")
    opener = build_opener(NoRedirect())
    req = Request(url,headers={"User-Agent":AGENT,"Cache-Control":"no-cache",
                              "Accept":"text/html" if kind=="html" else "text/plain"})
    try:
        res = opener.open(req,timeout=6)
    except HTTPError as exc:
        if kind=="robots" and exc.code in (404,410):
            return exc.code,b""
        raise
    with res:
        require(res.status==200 and res.geturl()==url,"unexpected HTTPS response")
        if kind=="html":
            require(res.headers.get_content_type()=="text/html","not a public HTML document")
        size = min(BYTES,512_000) if kind=="robots" else BYTES
        body = res.read(size+1)
        require(len(body)<=size,"public response exceeded byte limit")
    return 200,body

def crawl(root, capture, request=https):
    require(allowed(PREFIX,root) and root.endswith("/"),"root must be within the approved site")
    status, body = request(ROBOTS,"robots")
    require(status in (200,404,410),"robots could not be established")
    capture("robots",ROBOTS,status,body)
    robots = RobotFileParser()
    robots.parse(body.decode("utf-8").splitlines() if status==200 else [])
    def html(url):
        require(allowed(root,url) and robots.can_fetch(AGENT,url),"robots or URL scope denied")
        code, raw = request(url,"html")
        require(code==200,"public page was not reachable")
        capture("html",url,code,raw)
        return raw.decode("utf-8")
    content = html(root)
    links = RootLinks(root)
    links.feed(content)
    links.close()
    require(len(links.urls)+1 < CAP,"link limit reached; uniqueness not established")
    return [(root,extract(content))]+[(url,extract(html(url))) for url in sorted(links.urls)]
