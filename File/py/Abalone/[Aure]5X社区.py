# -*- coding: utf-8 -*-
# [5X社区¹⁸  更新于:2026-10-31 13:23]
import gzip
import html as html_mod
import re
import ssl
import threading
import time
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        def homeContent(self, filter):
                return {"class": []}
        def homeVideoContent(self):
                return {"list": []}
        def categoryContent(self, tid, pg, filter, extend):
                return {"list": []}
        def detailContent(self, ids):
                return {"list": []}
        def searchContent(self, key, quick, pg="1"):
                return {"list": []}
        def playerContent(self, flag, id, vipFlags):
                return {}
        def liveContent(self, url):
                return ""
        def proxy(self, params):
                return [404, "text/plain", ""]
        def localProxy(self, params):
                return [404, "text/plain", ""]
        def isVideoFormat(self, url):
                return False
        def manualVideoCheck(self):
                return False
        def action(self, action):
                return {}
        def getDependence(self):
                return []

NAME = "5X社区"
HOSTS = ["https://84d9yt.youkiy2.cyou"]
UA = "Mozilla/5.0 (Linux; Android 13; Pixel) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
PAGE_SIZE = 28
CACHE_TTL = 60
STYLE = {"type": "rect", "ratio": 1.33}

_CATS = [
    ("/videos", "视频"),
    ("/recommendation", "精选视频"),
    ("/uncensored", "未审查"),
    ("/censored", "审查视频"),
    ("/videos/5XSQ members original works", "5X社区会员原创作品"),
    ("/videos/Pacopacomama", "Paco"),
    ("/videos/sm", "SM性虐"),
    ("/videos/Tertiary film", "三级片"),
    ("/videos/Tokyo Hot", "东京热"),
    ("/videos/Pantyhose temptation", "丝袜诱惑"),
    ("/videos/Chinese subtitle", "中文字幕"),
    ("/videos/Public places and outdoors", "公众场所及户外"),
    ("/videos/Caribbeancom", "加勒比"),
    ("/videos/Cumshot", "口爆颜射"),
    ("/videos/Masturbation", "器具自慰"),
    ("/videos/homemade-selfie", "国产AV"),
    ("/videos/10musume", "天然素人"),
    ("/videos/Lesbian", "女同"),
    ("/videos/Small format synthesis", "小格式综合"),
    ("/videos/Sex party", "性party"),
    ("/videos/Adult Anime", "成人动漫"),
    ("/videos/chinese-anchor", "成人直播&主播福利"),
    ("/videos/tanhua-god", "探花大神"),
    ("/videos/reducing-mosaic", "无码破解"),
    ("/videos/Japan Uncensored", "日本无码"),
    ("/videos/Japan Coded", "日本有码"),
    ("/videos/pondo", "本道"),
    ("/videos/The Complete Works of Li Zongrui", "李宗瑞全集"),
    ("/videos/Europe and America", "欧美"),
    ("/videos/Squirting", "潮吹"),
    ("/videos/Anal sex", "肛交"),
    ("/videos/Korean female anchor series", "韩国女主播系列"),
    ("/videos/Korea General", "韩国综合"),
    ("/videos/HD", "高清"),
]

_DUR_RE = re.compile(r'(\d{1,2}:\d{2}(?::\d{2})?)')
_ISO_DUR = re.compile(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?')
_VID_RE = re.compile(r'"/video/(\d+)/([^"]+)"')

class _NetResp(object):
    def __init__(self, resp_dict, url):
        self._d = resp_dict or {}
        self.url = url
        self.status_code = int(self._d.get("code") or 0)
        self._content = self._d.get("content", "")
        self.headers = self._d.get("headers") or {}
        self.encoding = None
        self.apparent_encoding = "utf-8"
        self.text = self._content if isinstance(self._content, str) else ""
        if not self.text and isinstance(self._content, (bytes, bytearray)):
            self.text = bytes(self._content).decode("utf-8", "ignore")
    @property
    def content(self):
        return self._content if isinstance(self._content, (bytes, bytearray)) else self.text.encode("utf-8", "ignore")
    def json(self):
        import json as _json
        return _json.loads(self.text)
    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception("HTTP %s" % self.status_code)
    def __repr__(self):
        return "<_NetResp %s %d>" % (self.url, self.status_code)

class _NetSession(object):
    def __init__(self, net, headers=None, default_headers=None):
        self.net = net
        self.headers = headers if headers is not None else {}
        if default_headers:
            for k, v in default_headers.items():
                self.headers.setdefault(k, v)
    def _merge(self, headers):
        h = dict(self.headers)
        if headers:
            for k, v in headers.items():
                h[k] = v
        return h
    @staticmethod
    def _build_url(url, params):
        if not params:
            return url
        import urllib.parse as _up
        sep = "&" if "?" in url else "?"
        return url + sep + _up.urlencode(params)
    def _urllib_get(self, full, headers, timeout):
        import urllib.request as _ur, ssl as _ssl
        try:
            ctx = _ssl._create_unverified_context()
        except Exception:
            ctx = None
        req = _ur.Request(full, headers=headers)
        with _ur.urlopen(req, timeout=timeout or 15, context=ctx) as resp:
            raw = resp.read()
            enc = resp.headers.get("Content-Encoding", "")
            if "gzip" in enc:
                import gzip as _g
                raw = _g.decompress(raw)
            return {"code": resp.status, "content": raw, "headers": dict(resp.headers), "error": ""}
    def _urllib_post(self, full, headers, data, timeout):
        import urllib.request as _ur, urllib.parse as _up, ssl as _ssl
        try:
            ctx = _ssl._create_unverified_context()
        except Exception:
            ctx = None
        body = _up.urlencode(data or {}).encode("utf-8")
        req = _ur.Request(full, data=body, headers=headers, method="POST")
        with _ur.urlopen(req, timeout=timeout or 15, context=ctx) as resp:
            raw = resp.read()
            return {"code": resp.status, "content": raw, "headers": dict(resp.headers), "error": ""}
    def get(self, url, params=None, headers=None, timeout=None, **kw):
        h = self._merge(headers)
        full = self._build_url(url, params)
        timeout_s = None
        if timeout:
            timeout_s = int(timeout) / 1000 if timeout > 100 else int(timeout)
        if self.net is not None:
            opts = {"headers": h}
            if timeout_s:
                opts["timeout"] = int(timeout_s * 1000)
            try:
                resp = self.net.req(full, opts)
                return _NetResp(resp, full)
            except Exception:
                pass
        try:
            return _NetResp(self._urllib_get(full, h, timeout_s), full)
        except Exception as e:
            return _NetResp({"code": 0, "content": b"", "headers": {}, "error": str(e)}, full)
    def post(self, url, data=None, params=None, headers=None, timeout=None, **kw):
        h = self._merge(headers)
        full = self._build_url(url, params)
        timeout_s = None
        if timeout:
            timeout_s = int(timeout) / 1000 if timeout > 100 else int(timeout)
        if self.net is not None:
            opts = {"method": "POST", "headers": h, "postType": "form", "data": data or {}}
            if timeout_s:
                opts["timeout"] = int(timeout_s * 1000)
            try:
                resp = self.net.req(full, opts)
                return _NetResp(resp, full)
            except Exception:
                pass
        try:
            return _NetResp(self._urllib_post(full, h, data or {}, timeout_s), full)
        except Exception as e:
            return _NetResp({"code": 0, "content": b"", "headers": {}, "error": str(e)}, full)

class Spider(BaseSpider):

    def __init__(self):
        super().__init__()
        self.hosts = list(HOSTS)
        self.host = self.hosts[0]
        self.name = NAME
        self.headers = {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": self.host + "/",
        }
        self._cj = CookieJar()
        self._last = 0.0
        self._cache = {}
        self._cache_time = {}
        self._lock = threading.Lock()

    def init(self, extend=""):
        if isinstance(extend, dict):
            cfg = extend
        elif extend:
            try:
                import json
                cfg = json.loads(extend)
            except Exception:
                cfg = {}
        else:
            cfg = {}
        if not isinstance(cfg, dict):
            return
        site = (cfg.get("site") or cfg.get("url") or "").strip().rstrip("/")
        if site:
            with self._lock:
                self.hosts = [site] + [h for h in self.hosts if h != site]
                self.host = self.hosts[0]
                self.headers["Referer"] = self.host + "/"

    def getDependence(self):
        return []

    def destroy(self):
        with self._lock:
            self._cache.clear()
            self._cache_time.clear()

    def isVideoFormat(self, url):
        u = str(url or "").lower()
        return u.endswith(".m3u8") or ".m3u8?" in u or u.endswith(".mp4") or ".mp4?" in u

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return {"msg": "不支持此操作"}

    def homeContent(self, filter):
        return {"class": self._classes(), "filters": {}}

    def homeVideoContent(self):
        items = self._parse_cards(self._fetch(self.host + "/"))
        return {"list": [self._vod(x) for x in items][:PAGE_SIZE]}

    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        if tid.startswith(("actor/", "director/", "tag/")):
            name = urllib.parse.unquote(tid.split("/", 1)[1])
            items = self._fetch_search(name, pg)
            return self._page(items, pg)
        path = str(tid or "/videos").strip()
        if not path.startswith("/"):
            path = "/videos/" + path
        items = self._parse_cards(self._fetch(self._list_url(path, pg)))
        return self._page(items, pg)


    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        responses = [self._detail(str(video_id)) for video_id in ids]
        merged = {k: v for k, v in (responses[0] or {}).items() if k != "list"} if responses[0] else {}
        merged["list"] = [item for response in responses if response for item in (response.get("list") or [])]
        return merged
    def _detail(self, vid):
        vid = str(vid or "").strip()
        shell = {"vod_id": vid, "vod_name": vid, "vod_pic": "",
                 "vod_remarks": "", "vod_play_from": "在线播放", "vod_play_url": ""}
        if not vid:
            return {"list": [shell]}
        url = self._abs(urllib.parse.unquote(vid))
        url = urllib.parse.quote(url, safe="/:?&=@.-~")
        html_data = self._fetch(url)
        if not html_data:
            return {"list": [shell]}
        tm = re.search(r"<h1[^>]*>(.*?)</h1>", html_data, re.S | re.I)
        if tm:
            shell["vod_name"] = self._clean(tm.group(1))
        if not shell["vod_name"]:
            tm = re.search(r"<title>(.*?)</title>", html_data, re.S | re.I)
            if tm:
                shell["vod_name"] = self._clean(tm.group(1))
        vm = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html_data)
        if not vm:
            vm = re.search(r'<meta[^>]+content="([^"]+)"[^>]+property="og:image"', html_data)
        if not vm:
            vm = re.search(r'<video[^>]+poster="([^"]+)"', html_data)
        if not vm:
            vm = re.search(r'<img[^>]+src="([^"]+)"', html_data)
        if vm:
            shell["vod_pic"] = self._abs(vm.group(1))
        dm = re.search(r'"duration":\s*"(PT[^"]*)"', html_data)
        if dm:
            shell["vod_remarks"] = self._iso_dur(dm.group(1))
        m3u8 = self._og_video_url(html_data)
        if m3u8:
            shell["vod_play_url"] = "正片$" + m3u8
        else:
            shell["vod_play_url"] = "正片$" + url
        return {"list": [shell]}

    def searchContent(self, key, quick, pg="1"):
        pg = self._int(pg, 1)
        key = str(key or "").strip()
        if not key:
            return self._page([], pg)
        items = self._parse_cards(self._fetch(self._search_url(key, pg)))
        return self._page(items, pg)

    def playerContent(self, flag, id, vipFlags):
        raw = urllib.parse.unquote(str(id or "").strip())
        if "$" in raw:
            raw = raw.rsplit("$", 1)[-1].strip()
        header = {"User-Agent": UA, "Referer": self.host + "/"}
        if raw.lower().startswith("http") and ".m3u8" in raw.lower():
            if self._sig_fresh(raw):
                return {"parse": 0, "playUrl": "", "url": raw, "header": header}
            vm = re.search(r'/url/(\d+)/', raw)
            url = self._abs("/video/" + vm.group(1)) if vm else raw
            html_data = self._fetch(url)
            play = self._scan_media(html_data)
            if play:
                return {"parse": 0, "playUrl": "", "url": play,
                        "header": {"User-Agent": UA, "Referer": url}}
            return {"parse": 0, "playUrl": "", "url": raw, "header": header}
        url = raw if raw.startswith("http") else self._abs(raw)
        url = urllib.parse.quote(url, safe="/:?&=@.-~")
        html_data = self._fetch(url)
        play = self._scan_media(html_data)
        if play:
            return {"parse": 0, "playUrl": "", "url": play,
                    "header": {"User-Agent": UA, "Referer": url}}
        return {"parse": 1, "playUrl": "", "url": url, "header": header}

    def liveContent(self, url):
        return "[]"

    def proxy(self, params):
        return [200, "text/plain;charset=utf-8", ""]


    localProxy = proxy

    def _abs(self, path):
        if not path:
            return ""
        if path.startswith("http"):
            return path
        if path.startswith("//"):
            return "https:" + path
        return urllib.parse.urljoin(self.host + "/", path)

    @staticmethod
    def _clean(text):
        if not text:
            return ""
        return re.sub(r"<[^>]+>", "", html_mod.unescape(text)).strip()

    def _int(self, x, d=0):
        try:
            return int(x)
        except Exception:
            return d

    def _classes(self):
        return [{"type_id": p, "type_name": n, "style": STYLE} for p, n in _CATS]

    def _fetch(self, url, timeout=15):
        key = "u|" + url
        with self._lock:
            hit = self._cache.get(key)
            if hit and time.time() - self._cache_time.get(key, 0) < CACHE_TTL:
                return hit
        gap = time.time() - self._last
        if gap < 0.2:
            time.sleep(0.2 - gap)
        self._last = time.time()
        text = ""
        for _ in range(2):
            try:
                ctx = ssl._create_unverified_context()
            except Exception:
                ctx = None
            try:
                req = urllib.request.Request(url, headers=self.headers)
                opener = urllib.request.build_opener(
                    urllib.request.HTTPSHandler(context=ctx),
                    urllib.request.HTTPCookieProcessor(self._cj))
                with opener.open(req, timeout=timeout) as resp:
                    raw = resp.read()
                    enc = (resp.headers.get("Content-Encoding", "") or "").lower()
                    if "gzip" in enc or raw[:2] == b"\x1f\x8b":
                        raw = gzip.decompress(raw)
                    text = raw.decode("utf-8", errors="ignore")
                    break
            except Exception:
                text = ""
        if text:
            with self._lock:
                self._cache[key] = text
                self._cache_time[key] = time.time()
        return text

    def _list_url(self, path, pg):
        path = urllib.parse.quote(path, safe="/")
        if pg > 1:
            return self.host + path + "?page=" + str(pg)
        return self.host + path

    def _search_url(self, kw, pg):
        url = self.host + "/search/videos/" + urllib.parse.quote(kw, safe="") + "/"
        if pg > 1:
            url += "?page=" + str(pg)
        return url

    def _parse_cards(self, html_data):
        cards, seen = [], set()
        if not html_data:
            return cards
        for m in re.finditer(r'href="(/video/(\d+)/[^"]+)"', html_data, re.I):
            link, vid = m.group(1), m.group(2)
            if vid in seen:
                continue
            seen.add(vid)
            title, pic, remarks = "", "", ""
            win = html_data[m.start():m.start() + 3000]
            for tm in re.finditer(r'<a[^>]*href="/video/%s/[^"]*"[^>]*>(.*?)</a>' % re.escape(vid), win, re.S | re.I):
                t = self._clean(tm.group(1))
                if t:
                    title = t
                    break
            if not title:
                am = re.search(r'<img[^>]+alt="([^"]+)"', win, re.I)
                if am:
                    title = self._clean(am.group(1))
            im = re.search(r'<img[^>]+src="([^"]+)"', win, re.I)
            if im:
                pic = self._abs(im.group(1))
            dm = _DUR_RE.search(win)
            if dm:
                remarks = dm.group(1)
            if not title:
                continue
            cards.append({"vid": link, "title": title, "pic": pic, "remarks": remarks})
        return cards

    def _og_video_url(self, html_data):
        m = re.search(r'<meta[^>]+property="og:video:url"[^>]+content="([^"]+)"', html_data or "")
        if not m:
            m = re.search(r'<meta[^>]+content="([^"]+)"[^>]+property="og:video:url"', html_data or "")
        return m.group(1).strip() if m else ""

    def _sig_fresh(self, url):
        m = re.search(r'[?&]expires=(\d+)', str(url or ""))
        if not m:
            return False
        try:
            exp = int(m.group(1))
        except Exception:
            return False
        return exp > time.time() + 300

    def _scan_media(self, html_data):
        m = re.search(r'<meta[^>]+property="og:video:url"[^>]+content="([^"]+)"', html_data)
        if not m:
            m = re.search(r'<meta[^>]+content="([^"]+)"[^>]+property="og:video:url"', html_data)
        if m:
            return self._abs(m.group(1))
        cands = []
        for pat in (r'<source[^>]+src="([^"]+)"', r'<video[^>]+src="([^"]+)"'):
            cands += re.findall(pat, html_data, re.I)
        cands += re.findall(r'"(https?://[^"]+\.(?:m3u8|mp4)[^"]*)"', html_data, re.I)
        cands += re.findall(r"'(https?://[^']+\.(?:m3u8|mp4)[^']*)'", html_data, re.I)
        seen = set()
        for cand in cands:
            cand = cand.strip().replace("\\/", "/")
            low = cand.lower()
            if cand in seen or any(k in low for k in ("preview", "sample", "trailer", "thumb")):
                continue
            seen.add(cand)
            return self._abs(cand)
        return ""

    def _page(self, items, pg):
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": pg if len(items) < PAGE_SIZE else 9999,
            "limit": PAGE_SIZE,
            "total": 999999,
        }

    def _vod(self, item):
        return {
            "vod_id": item.get("vid") or "",
            "vod_name": item.get("title") or "",
            "vod_pic": item.get("pic") or "",
            "vod_remarks": item.get("remarks") or "",
        }

    def _iso_dur(self, s):
        mm = _ISO_DUR.search(s or "")
        if not mm:
            return ""
        h = int(mm.group(1) or 0)
        mi = int(mm.group(2) or 0)
        se = int(mm.group(3) or 0)
        if h:
            return f"{h:02d}:{mi:02d}:{se:02d}"
        return f"{mi:02d}:{se:02d}"


