
import sys
import json
import re
import time
import threading
from urllib.parse import quote, unquote

import requests
try:
    requests.packages.urllib3.disable_warnings()
except Exception:
    pass

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        pass

NAME = "JAVDAY"
HOSTS = ["https://javday.app"]
UA = ("Mozilla/5.0 (Linux; Android 13; Pixel) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")
PAGE_SIZE = 24
CACHE_TTL = 60
VOD_ID_PREFIX = ""
STYLE = {"type": "rect", "ratio": 1.33}


class Spider(BaseSpider):
    def __init__(self):
        self.hosts = list(HOSTS)
        self.host = self.hosts[0]
        self.name = NAME
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": UA,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        self._cache = {}
        self._cache_time = {}
        self._lock = threading.Lock()
        self.options = {}

    def init(self, extend=""):
        if isinstance(extend, dict):
            cfg = extend
        elif extend:
            try:
                cfg = json.loads(extend)
            except Exception:
                cfg = {}
        else:
            cfg = {}
        if isinstance(cfg, dict):
            site = (cfg.get("site") or cfg.get("url") or "").strip().rstrip("/")
            if site:
                with self._lock:
                    self.hosts = [site] + [h for h in self.hosts if h != site]
                    self.host = self.hosts[0]
            self.options = cfg

    def getName(self):
        return self.name

    def getDependence(self):
        return []

    def destroy(self):
        with self._lock:
            self._cache.clear()
            self._cache_time.clear()
        self.options = {}

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4|flv|mkv)(\?|$)", str(url)))

    def manualVideoCheck(self):
        return False


    def homeContent(self, filter):
        classes = self._classes()
        result = {"class": classes}
        if filter:
            result["filters"] = {}

        result["list"] = [self._vod(x) for x in self._fetch_list("/label/new/", 1)]
        return result

    def homeVideoContent(self):
        return {"list": []}


    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)

        if tid.startswith("actor/"):
            name = unquote(tid.split("/", 1)[1])
            items = self._fetch_search(name, pg)
            return self._page(items, pg)

        path = tid
        if pg > 1:
            path = path.rstrip("/") + "/page/{}/".format(pg)
        items = self._fetch_list(path, pg)
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": pg if not items else 9999,
            "limit": PAGE_SIZE,
            "total": 999999,
        }


    def detailContent(self, ids):
        vid = str(ids[0] if ids else "").strip()

        code = vid.strip("/").split("/")[-1] if "/" in vid else vid
        data = self._fetch_detail(code)
        if not data:
            return {"list": [], "msg": "未找到此影片"}

        episodes = data.get("episodes") or []
        lines = []
        for i, ep in enumerate(episodes, 1):
            t = self._safe_label(ep.get("name") or "EP{}".format(i))
            u = ep.get("url") or ""
            if u:
                lines.append("{}${}".format(t, u))
        if not lines:
            return {"list": [], "msg": "无播放源"}
        vod = {
            "vod_id": code,
            "vod_name": data.get("name") or code,
            "vod_pic": data.get("pic") or "",
            "type_name": data.get("category") or "",
            "vod_remarks": data.get("remarks") or "",
            "vod_content": data.get("content") or "",
            "vod_actor": "、".join(
                self._clickable("actor", a) for a in (data.get("actors") or [])
            ),
            "vod_play_from": "JAVDAY",
            "vod_play_url": "#".join(lines),
        }
        return {"list": [vod]}


    def searchContent(self, key, quick, pg="1"):
        pg = self._int(pg, 1)
        items = self._fetch_search(str(key or "").strip(), pg)
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": pg if not items else 9999,
            "limit": PAGE_SIZE,
            "total": 999999,
        }


    def playerContent(self, flag, id, vipFlags):

        url = str(id or "").strip()
        if not url:
            return {"parse": 0, "msg": "无法获取播放地址"}
        return {
            "parse": 0,
            "jx": 0,
            "url": url,
            "header": {
                "User-Agent": UA,
                "Referer": self.host + "/",
            },
        }

    def liveContent(self, url):
        return "[]"

    def action(self, action):
        return {"msg": "不支持此操作"}


    def _classes(self):

        return [
            {"type_id": "/label/new/", "type_name": "最近更新", "style": STYLE},
            {"type_id": "/label/hot/", "type_name": "人气系列", "style": STYLE},
            {"type_id": "/category/censored/", "type_name": "有码", "style": STYLE},
            {"type_id": "/category/new-release/", "type_name": "新作上市", "style": STYLE},
            {"type_id": "/category/uncensored-leaked/", "type_name": "无修正流出", "style": STYLE},
            {"type_id": "/category/aiav/", "type_name": "AI短剧", "style": STYLE},
        ]

    def _get(self, path_or_url, timeout=12):
        if path_or_url.startswith("http"):
            url = path_or_url
        else:
            url = self.host + path_or_url
        with self._lock:
            hit = self._cache.get(url)
            if hit and time.time() - self._cache_time.get(url, 0) < CACHE_TTL:
                return hit
        last_err = None
        for host in self.hosts:
            if path_or_url.startswith("http"):
                u = path_or_url
            else:
                u = host + path_or_url
            try:
                r = self.session.get(u, timeout=timeout, verify=False)
                if r.status_code != 200:
                    last_err = "http {}".format(r.status_code)
                    continue
                text = r.text

                if "Just a moment" in text and "challenge-platform" in text:
                    last_err = "cf challenge"
                    continue
                self.host = host
                with self._lock:
                    self._cache[url] = text
                    self._cache_time[url] = time.time()
                return text
            except Exception as e:
                last_err = str(e)
                continue
        return ""


    _VB_A = re.compile(
        r'<a href="(?P<href>/videos/[A-Za-z0-9]+/)"[^>]*class="videoBox".*?'
        r'videoBox-cover"[^>]*background-image:\s*url\((?:&quot;|"|)?(?P<pic>https?://[^)"&]+).*?'
        r'<span class="title">(?P<title>[^<]*)</span>.*?'
        r'<span class="views">.*?<span class="number">(?P<views>[^<]*)</span>',
        re.S,
    )

    _VB_B = re.compile(
        r'<a href="(?P<href>/videos/[A-Za-z0-9]+/)"[^>]*class="videoBox".*?'
        r'videoBox-cover"[^>]*background-image:\s*url\((?:&quot;|"|)?(?P<pic>https?://[^)"&]+).*?'
        r'<span class="title">(?P<title>[^<]*)</span>',
        re.S,
    )

    def _parse_boxes(self, html):
        if not html:
            return []
        out = []
        seen = set()
        items = list(self._VB_A.finditer(html))
        if not items:
            items = list(self._VB_B.finditer(html))
        for m in items:
            href = m.group("href")
            if href in seen:
                continue
            seen.add(href)
            code = href.strip("/").split("/")[-1]
            title = (m.group("title") or "").strip()
            pic = (m.group("pic") or "").strip()
            views = ""
            try:
                views = (m.group("views") or "").strip()
            except IndexError:
                views = ""
            remark = ""
            if views and views.isdigit():
                try:
                    n = int(views)
                    remark = "{}次".format(views) if n < 10000 else "{:.1f}万".format(n/10000.0)
                except Exception:
                    remark = views
            out.append({
                "id": code,
                "name": title,
                "pic": pic,
                "remarks": remark,
            })
        return out

    def _fetch_list(self, path, pg):

        html = self._get(path)
        return self._parse_boxes(html)

    def _fetch_search(self, keyword, pg):
        if not keyword:
            return []
        kw = quote(keyword, safe="")
        if pg and pg > 1:
            path = "/search/page/{}/wd/{}/".format(pg, kw)
        else:
            path = "/search/wd/{}/".format(kw)
        html = self._get(path)
        return self._parse_boxes(html)


    _RE_TITLE = re.compile(r'<h1 class="video-title">([^<]+)</h1>')
    _RE_ACTOR_BLOCK = re.compile(
        r'<span class="vod_actor">(.*?)</span>', re.S)
    _RE_ACTOR_LINK = re.compile(r'<a[^>]*>([^<]*)</a>')
    _RE_JPNUM = re.compile(r'<span class="jpnum">([^<]*)</span>')
    _RE_PLAY_COMMENT = re.compile(
        r'<!--\s*(EP\d+\$https?://[^<]*?)\s*-->', re.S)
    _RE_COVERS = re.compile(
        r'videoBox-cover"[^>]*background-image:\s*url\((?:&quot;|"|)?(https?://[^)"&]+)')

    def _fetch_detail(self, code):
        url = "/videos/{}/".format(code)
        html = self._get(url)
        if not html:
            return None
        m = self._RE_TITLE.search(html)
        name = m.group(1).strip() if m else code
        m = self._RE_JPNUM.search(html)
        jpnum = m.group(1).strip() if m else ""
        actors = []
        mb = self._RE_ACTOR_BLOCK.search(html)
        if mb:
            actors = [a.strip() for a in self._RE_ACTOR_LINK.findall(mb.group(1)) if a.strip()]

        episodes = []
        pm = self._RE_PLAY_COMMENT.search(html)
        if pm:
            raw = pm.group(1)


            parts = raw.split("#")
            for p in parts:
                p = p.strip()
                if not p:
                    continue
                if "$" in p:
                    name_, url_ = p.split("$", 1)
                    episodes.append({"name": name_.strip(), "url": url_.strip()})

        if not episodes:
            cand = re.findall(r'https?://[^\s"\'<>]+?\.m3u8[^\s"\'<>]*', html)

            seen = set()
            ordered = []
            for c in cand:
                if c not in seen:
                    seen.add(c)
                    ordered.append(c)

            for i, c in enumerate(ordered, 1):
                episodes.append({"name": "EP{}".format(i), "url": c})

        pic = ""
        cm = re.search(r'<meta property="og:image" content="([^"]+)"', html)
        if cm:
            pic = cm.group(1)
        if not pic:
            cm = self._RE_COVERS.search(html)
            if cm:
                pic = cm.group(1)
        content = ""
        dm = re.search(r'<meta name="description" content="([^"]*)"', html)
        if dm:
            content = dm.group(1)
        return {
            "name": name,
            "pic": pic,
            "category": "",
            "remarks": jpnum,
            "content": content,
            "actors": actors,
            "episodes": episodes,
        }


    def _vod(self, item):
        return {
            "vod_id": item.get("id") or "",
            "vod_name": item.get("name") or "",
            "vod_pic": item.get("pic") or "",
            "vod_remarks": item.get("remarks") or "",
            "style": STYLE,
        }

    def _safe_label(self, t):
        return str(t or "").replace("$", "＄").replace("#", "＃").strip()

    def _clickable(self, kind, name):
        if not name:
            return ""
        payload = json.dumps(
            {"id": "{}/{}".format(kind, quote(name, safe="")),
             "name": name, "type_flag": "1"},
            ensure_ascii=False, separators=(",", ":"),
        )
        return "[a=cr:{}/]{}[/a]".format(payload, name)

    def _page(self, items, pg):
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": pg if not items else 9999,
            "limit": PAGE_SIZE,
            "total": 999999,
        }

    def _int(self, x, d=0):
        try:
            return int(x)
        except Exception:
            return d
