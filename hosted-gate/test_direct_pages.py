import unittest
from tbp.direct_pages import PREFIX, ROBOTS, crawl

class DirectPagesTests(unittest.TestCase):
    root = PREFIX + "rehearsal/"
    def test_scope_and_exact_budget(self):
        calls=[]
        def transport(url,kind):
            calls.append(url)
            if url==ROBOTS: return 404,b""
            if url==self.root:
                return 200,b'<a href="beacon.html"><a href="../outside.html"><a href="https://example.org/no"><a href="./beacon.html"><a href="q.html?x=1">'
            return 200,b"test page"
        result=crawl(self.root,lambda *a:None,transport)
        self.assertEqual(calls,[ROBOTS,self.root,self.root+"beacon.html"])
        self.assertEqual(len(result),2)
    def test_robot_denial_fails_closed(self):
        def transport(url,kind):
            self.assertEqual(url,ROBOTS)
            return 200,b"User-agent: *\nDisallow: /tbp-001/"
        with self.assertRaisesRegex(ValueError,"robots"):
            crawl(self.root,lambda *a:None,transport)
    def test_no_page_fetch_on_saturation(self):
        def transport(url,kind):
            if url==ROBOTS: return 404,b""
            self.assertEqual(url,self.root)
            return 200,"".join(f'<a href="{i}.html">' for i in range(10)).encode()
        with self.assertRaisesRegex(ValueError,"link limit"):
            crawl(self.root,lambda *a:None,transport)
