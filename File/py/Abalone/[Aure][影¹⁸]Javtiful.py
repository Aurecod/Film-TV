# -*- coding: utf-8 -*-
# [Javtiful¹⁸  更新于:2026-10-31 15:30]
import json
import re
import time
import gzip
import zlib
import urllib.request
from urllib.parse import quote, unquote

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        def proxy(self, params):
            return [404, "text/plain", ""]
        def localProxy(self, params):
            return [404, "text/plain", ""]

NAME = "Javtiful"
HOSTS = ["https://javtiful.com"]
PREFIX = "/zh"
UA = "Mozilla/5.0 (Linux; Android 13; Pixel) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
PAGE_SIZE = 24
CACHE_TTL = 30
DEBUG = False

CATS = [
    ("videos", "视频"),
    ("censored", "有码"),
    ("uncensored", "无码"),
    ("reducing-mosaic", "减码"),
    ("folder/category/_", "\U0001F5C2\ufe0f 分类"),
    ("folder/actress/_", "\U0001F483 女优"),
    ("folder/channel/_", "\U0001F3AC 频道"),
]

SORT_VALUES = [
    ("", "默认"),
    ("added_today", "今日新增"),
    ("added_week", "本周新增"),
    ("added_month", "本月新增"),
    ("popular", "热门"),
    ("popular_today", "今日热门"),
    ("popular_week", "本周热门"),
    ("popular_month", "本月热门"),
    ("most_viewed", "最多观看"),
    ("most_liked", "最多点赞"),
]

VIDEO_TYPE_VALUES = [
    ("", "全部"),
    ("censored", "有码"),
    ("uncensored", "无码"),
    ("reducing_mosaic", "减码"),
]

STYLE = {"type": "rect", "ratio": 0.75}


class Spider(BaseSpider):

    def __init__(self):
        self.hosts = list(HOSTS)
        self.host = self.hosts[0]
        self.name = NAME
        self._cache = {}
        self._cache_time = {}
        self._lock = __import__("threading").Lock()

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
        if not isinstance(cfg, dict):
            return
        site = (cfg.get("site") or cfg.get("url") or "").strip().rstrip("/")
        if site:
            with self._lock:
                self.hosts = [site] + [h for h in self.hosts if h != site]
                self.host = self.hosts[0]
        self.options = cfg

    def getDependence(self):
        return []

    def destroy(self):
        with self._lock:
            self._cache.clear()
            self._cache_time.clear()
        self.options = {}

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4|flv|mkv|ts)(\?|$)", str(url)))

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return {"msg": "不支持此操作"}

    def homeContent(self, filter):
        classes = self._classes()
        result = {"class": classes}
        if filter:
            result["filters"] = self._filters(classes)
        items, _ = self._fetch_list("videos", 1, {})
        result["list"] = [self._vod(x) for x in items]
        return result

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        extend = extend or {}
        if tid.startswith("actor/"):
            slug = unquote(tid.split("/", 1)[1])
            items, has_more = self._fetch_actor(slug, pg, extend)
            return self._page_items(items, pg, has_more)
        if tid.startswith("tag/"):
            name = unquote(tid.replace("tag/", "", 1))
            items, has_more = self._fetch_search(name, pg)
            return self._page_items(items, pg, has_more)
        if tid.startswith("folder/"):
            parts = tid.split("/", 2)
            if len(parts) == 3:
                f_type, f_val = parts[1], unquote(parts[2])
                if not f_val or f_val == "_":
                    items = self._fetch_folder_entries(f_type, pg)
                    if f_type == "category":
                        pc = 1
                    else:
                        pc = 9999 if items else pg
                    return {
                        "list": items,
                        "page": pg,
                        "pagecount": pc,
                        "limit": PAGE_SIZE,
                        "total": 999999,
                    }
                else:
                    items, has_more = self._fetch_folder(f_type, f_val, pg, extend)
                    return self._page_items(items, pg, has_more)
        items, has_more = self._fetch_list(tid, pg, extend)
        return self._page_items(items, pg, has_more)

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        responses = [self._detail(str(video_id)) for video_id in ids]
        merged = {k: v for k, v in (responses[0] or {}).items() if k != "list"}
        merged["list"] = [item for response in responses for item in (response.get("list") or [])]
        return merged

    def searchContent(self, key, quick, pg="1"):
        pg = self._int(pg, 1)
        items, has_more = self._fetch_search(str(key or "").strip(), pg)
        return self._page_items(items, pg, has_more)

    def playerContent(self, flag, id, vipFlags):
        vid = self._extract_id(str(id or ""))
        url = self._fetch_play(vid)
        if not url:
            return {"parse": 0, "msg": "无法获取播放地址"}
        result = {
            "parse": 0,
            "jx": 0,
            "url": url,
            "header": self._string_map({"User-Agent": UA, "Referer": self.host + PREFIX + "/"}),
        }
        return result

    def liveContent(self, url):
        return "[]"

    def getProxyUrl(self, params=None, local=True):
        from com.github.catvod import Proxy
        url = Proxy.getUrl(local)
        sk = getattr(self, "siteKey", "") or ""
        return url + "?do=py" + ("&siteKey=%s" % sk if sk else "")

    def proxyUrl(self, params=None, local=True):
        return self.getProxyUrl(params, local)

    def _img_stream(self, data):
        net = getattr(self, "net", None)
        if net is not None and hasattr(net, "stream"):
            try:
                def _gen():
                    yield data
                return net.stream(_gen())["stream"]
            except Exception:
                pass
        return data

    def proxy(self, params):
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except Exception:
                return [404, "text/plain", ""]
        if not isinstance(params, dict):
            return [404, "text/plain", ""]
        if params.get("type") == "pic":
            real = params["url"]
            try:
                real = unquote(str(params["url"]))
            except Exception:
                pass
            try:
                real = self._d64(real)
            except Exception:
                pass
            net = getattr(self, "net", None)
            if net is not None and hasattr(net, "reqParts"):
                raw = net.reqParts(real, {"buffer": 3})[1]
            elif net is not None:
                raw = net.req(real, {"buffer": 3})
                if isinstance(raw, dict):
                    raw = raw.get("content", b"")
            else:
                req = urllib.request.Request(real, headers={"User-Agent": UA, "Referer": self.host + "/"})
                raw = urllib.request.urlopen(req, timeout=20).read()
            return [200, self._mime(raw), self._img_stream(raw), {}]
        return [404, "text/plain", ""]

    localProxy = proxy

    def _mime(self, data):
        head = bytes(data[:4]) if data else b""
        if head[:3] == b"\xff\xd8\xff":
            return "image/jpeg"
        if head[:4] == b"\x89PNG":
            return "image/png"
        if head[:4] == b"GIF8":
            return "image/gif"
        if head[:4] == b"RIFF":
            return "image/webp"
        return "image/jpeg"

    def _pic(self, item):
        u = item.get("pic") or ""
        if not u:
            return ""
        u = self._fix_url(u)
        if not u:
            return ""
        enc = quote(self._e64(u), safe="")
        try:
            proxy = self.getProxyUrl()
            if proxy:
                sep = "&" if "?" in proxy else "?"
                key = getattr(self, "siteKey", "") or ""
                extra = ("&siteKey=%s" % key) if (key and "siteKey=" not in proxy) else ""
                return "%s%stype=pic&url=%s%s" % (proxy, sep, enc, extra)
        except Exception:
            pass
        if hasattr(self, "proxyUrl"):
            try:
                p = self.proxyUrl({"type": "pic", "url": self._e64(u)})
                if p:
                    return p
            except Exception:
                pass
        return u

    def _e64(self, s):
        import base64
        return base64.b64encode(s.encode("utf-8")).decode()

    def _d64(self, s):
        import base64
        return base64.b64decode(s).decode("utf-8", "replace")

    def _safe_label(self, text):
        return str(text or "").replace("$", "\uff04").replace("#", "\uff03").strip()

    def _int(self, x, d=0):
        try:
            return int(x)
        except Exception:
            return d

    @staticmethod
    def _string_map(value, name="headers"):
        if value in (None, ""):
            return {}
        if not isinstance(value, dict):
            return {}
        return {str(k): str(v) for k, v in value.items() if v is not None}

    def _fix_url(self, u):
        if not u:
            return ""
        u = u.strip()
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("/"):
            return self.host.rstrip("/") + u
        return u

    def _resp_dict(self, resp):
        if isinstance(resp, dict):
            return resp
        if isinstance(resp, str):
            return {"code": 200, "content": resp, "headers": {}, "error": None}
        if isinstance(resp, (bytes, bytearray)):
            return {"code": 200, "content": resp, "headers": {}, "error": None}
        return {"code": 0, "content": "", "headers": {}, "error": str(resp)}

    def _req(self, url, **kw):
        net = getattr(self, "net", None)
        if net is not None:
            try:
                opts = {"timeout": kw.get("timeout", 15000)}
                for k in ("params", "headers", "method", "postType", "data", "body", "buffer", "redirect", "callTimeout", "cookie"):
                    if k in kw and kw[k] is not None:
                        opts[k] = kw[k]
                resp = net.req(url, opts)
                return resp or {}
            except Exception:
                return {}
        return self._req_urllib(url, **kw)

    def _req_urllib(self, url, **kw):
        try:
            timeout = (kw.get("timeout") or 15000) / 1000.0
            data = None
            method = (kw.get("method") or "GET").upper()
            headers = dict(kw.get("headers") or {})
            headers.setdefault("User-Agent", UA)
            headers.setdefault("Accept", "*/*")
            if method == "POST":
                body = kw.get("data") or kw.get("body") or {}
                if isinstance(body, dict):
                    data = "&".join("%s=%s" % (k, quote(str(v), safe="")) for k, v in body.items()).encode()
                elif isinstance(body, str):
                    data = body.encode()
                else:
                    data = body
                headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                enc = (resp.headers.get("Content-Encoding") or "").lower()
                if enc == "gzip":
                    raw = gzip.decompress(raw)
                elif enc == "deflate":
                    raw = zlib.decompress(raw)
                return {"code": resp.getcode() or 0, "content": raw.decode("utf-8", "replace"), "headers": dict(resp.headers), "error": None}
        except Exception as e:
            return {"code": 0, "content": "", "headers": {}, "error": str(e)}

    def _get_html(self, url, **kw):
        resp = self._req(url, **kw)
        if resp.get("error"):
            return None
        code = resp.get("code") or 0
        if not 200 <= code < 300:
            return None
        return resp.get("content", "")

    def _get_cache(self, key):
        with self._lock:
            hit = self._cache.get(key)
            if hit and time.time() - self._cache_time.get(key, 0) < CACHE_TTL:
                return hit
        return None

    def _set_cache(self, key, val):
        with self._lock:
            self._cache[key] = val
            self._cache_time[key] = time.time()

    def _classes(self):
        hit = self._get_cache("__cls")
        if hit is not None:
            return hit
        arr = [{"type_id": tid, "type_name": nm} for tid, nm in CATS]
        self._set_cache("__cls", arr)
        return arr

    def _filters(self, classes):
        sort_filter = {
            "key": "sort", "name": "排序", "init": "",
            "value": [{"n": n, "v": v} for v, n in SORT_VALUES],
        }
        vt_filter = {
            "key": "video_type", "name": "类型", "init": "",
            "value": [{"n": n, "v": v} for v, n in VIDEO_TYPE_VALUES],
        }
        result = {}
        for c in classes:
            tid = c["type_id"]
            if tid.startswith("folder/"):
                result[tid] = [sort_filter, vt_filter]
            else:
                result[tid] = [sort_filter]
        return result

    def _page_items(self, items, pg, has_more=None):
        if has_more is None:
            has_more = len(items) >= PAGE_SIZE
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": 9999 if has_more else pg,
            "limit": PAGE_SIZE,
            "total": 999999,
        }

    def _has_more(self, html, pg):
        if not html:
            return False
        for m in re.finditer(r'<a[^>]*class="pagination__link([^"]*)"[^>]*href="([^"]*)"[^>]*>([^<]*)</a>', html):
            cls = m.group(1)
            href = m.group(2)
            if "is-disabled" in cls or "is-active" in cls:
                continue
            pm = re.search(r"page=(\d+)", href)
            if pm and int(pm.group(1)) > pg:
                return True
        return False

    def _vod(self, item):
        item = item or {}
        vid = str(item.get("id") or "")
        return {
            "vod_id": vid,
            "vod_name": item.get("name") or vid,
            "vod_pic": self._pic(item),
            "vod_remarks": item.get("remarks") or "",
        }

    def _extract_id(self, vid):
        m = re.search(r"(\d+)", str(vid or ""))
        return m.group(1) if m else str(vid or "")

    def _parse_cards(self, html):
        items = []
        if not html:
            return items
        blocks = re.split(r'<article class="video-card', html)
        for blk in blocks[1:]:
            m = re.search(r'href="(/zh/video/(\d+)[^"]*)"', blk)
            if not m:
                continue
            vid = m.group(2)
            pic = ""
            pm = re.search(r'data-front-lazy-src="([^"]+)"', blk)
            if pm:
                pic = pm.group(1)
            else:
                pm = re.search(r'<img[^>]+src="([^"]+)"', blk)
                if pm and "placeholder" not in pm.group(1):
                    pic = pm.group(1)
            name = ""
            tm = re.search(r'class="video-card__title"\s+title="([^"]*)"', blk)
            if tm:
                name = tm.group(1)
            else:
                tm = re.search(r'class="video-card__title"[^>]*>(.*?)</a>', blk, re.S)
                if tm:
                    name = re.sub(r"<[^>]+>", "", tm.group(1)).strip()
            type_badge = ""
            tm = re.search(r'class="video-card__type">([^<]*)<', blk)
            if tm:
                type_badge = tm.group(1).strip()
            details = ""
            dm = re.search(r'class="video-card__details">(.*?)</span>', blk, re.S)
            if dm:
                details = re.sub(r"<[^>]+>", " ", dm.group(1))
                details = re.sub(r"\s+", " ", details).strip()
            remarks = details or type_badge
            if type_badge and details:
                remarks = "%s · %s" % (type_badge, details)
            items.append({
                "id": vid,
                "name": name or vid,
                "pic": self._fix_url(pic),
                "remarks": remarks,
            })
        return items

    def _fetch_list(self, tid, pg, extend):
        extend = extend or {}
        path = {
            "videos": PREFIX + "/videos",
            "censored": PREFIX + "/censored",
            "uncensored": PREFIX + "/uncensored",
            "reducing-mosaic": PREFIX + "/reducing-mosaic",
        }.get(tid)
        if not path:
            return [], False
        url = self.host + path
        params = []
        if pg > 1:
            params.append("page=%d" % pg)
        sort = extend.get("sort")
        if sort:
            params.append("sort=" + quote(str(sort), safe=""))
        if params:
            url += "?" + "&".join(params)
        html = self._get_html(url, headers={"Referer": self.host + PREFIX + "/"})
        return self._parse_cards(html), self._has_more(html, pg)

    def _fetch_actor(self, slug, pg, extend):
        extend = extend or {}
        url = "%s%s/actress/%s" % (self.host, PREFIX, quote(slug, safe=""))
        params = []
        if pg > 1:
            params.append("page=%d" % pg)
        sort = extend.get("sort")
        if sort:
            params.append("sort=" + quote(str(sort), safe=""))
        vt = extend.get("video_type")
        if vt:
            params.append("video_type=" + quote(str(vt), safe=""))
        if params:
            url += "?" + "&".join(params)
        html = self._get_html(url, headers={"Referer": self.host + PREFIX + "/"})
        return self._parse_cards(html), self._has_more(html, pg)

    def _fetch_search(self, keyword, pg):
        if not keyword:
            return [], False
        url = "%s%s/search" % (self.host, PREFIX)
        params = ["q=" + quote(keyword, safe="")]
        if pg > 1:
            params.append("page=%d" % pg)
        url += "?" + "&".join(params)
        html = self._get_html(url, headers={"Referer": self.host + PREFIX + "/"})
        return self._parse_cards(html), self._has_more(html, pg)

    def _fetch_folder_entries(self, type_, pg):
        page_map = {
            "category": PREFIX + "/categories",
            "actress": PREFIX + "/actresses",
            "channel": PREFIX + "/channels",
        }
        base = page_map.get(type_)
        if not base:
            return []
        url = self.host + base
        if pg > 1:
            url += "?page=%d" % pg
        html = self._get_html(url, headers={"Referer": self.host + PREFIX + "/"})
        items = []
        if not html:
            return items
        if type_ == "category":
            blocks = re.split(r'<a class="category-card"', html)
            for blk in blocks[1:]:
                m = re.search(r'href="/zh/category/([^"]+)"', blk)
                if not m:
                    continue
                slug = unquote(m.group(1))
                name = ""
                nm = re.search(r'class="category-card__name">([^<]*)<', blk)
                if nm:
                    name = nm.group(1).strip()
                if not name:
                    nm = re.search(r'alt="([^"]*)"', blk)
                    if nm:
                        name = nm.group(1).strip()
                count = ""
                cm = re.search(r'class="category-card__count">([\d,]+)', blk)
                if cm:
                    count = cm.group(1).replace(",", "")
                pic = ""
                pm = re.search(r'<img[^>]+class="category-card__cover"[^>]+src="([^"]+)"', blk)
                if not pm:
                    pm = re.search(r'<img[^>]+src="([^"]+)"', blk)
                if pm:
                    pic = self._fix_url(pm.group(1))
                items.append(self._folder_vod("category", slug, name, count, pic))
        else:
            blocks = re.split(r'<article class="directory-card', html)
            for blk in blocks[1:]:
                m = re.search(r'href="/zh/(?:actress|channel)/([^"]+)"', blk)
                if not m:
                    continue
                slug = unquote(m.group(1))
                name = ""
                nm = re.search(r'class="directory-card__name">([^<]*)<', blk)
                if nm:
                    name = nm.group(1).strip()
                count = ""
                cm = re.search(r'class="directory-card__count">([\d,]+)', blk)
                if cm:
                    count = cm.group(1).replace(",", "")
                pic = ""
                pm = re.search(r'<img[^>]+src="([^"]+)"', blk)
                if pm:
                    pic = self._fix_url(pm.group(1))
                items.append(self._folder_vod(type_, slug, name, count, pic))
        return items

    def _folder_vod(self, type_, value, name, count=None, pic=""):
        return {
            "vod_id": "folder/%s/%s" % (type_, quote(value, safe="")),
            "vod_name": str(name or value or ""),
            "vod_pic": self._pic({"pic": pic}) if pic else "",
            "vod_remarks": ("%s部" % count) if count else "",
            "vod_tag": "folder",
        }

    def _fetch_folder(self, type_, value, pg, extend):
        extend = extend or {}
        if type_ == "category":
            url = "%s%s/category/%s" % (self.host, PREFIX, quote(value, safe=""))
        elif type_ == "actress":
            url = "%s%s/actress/%s" % (self.host, PREFIX, quote(value, safe=""))
        elif type_ == "channel":
            url = "%s%s/channel/%s" % (self.host, PREFIX, quote(value, safe=""))
        else:
            return [], False
        params = []
        if pg > 1:
            params.append("page=%d" % pg)
        sort = extend.get("sort")
        if sort:
            params.append("sort=" + quote(str(sort), safe=""))
        vt = extend.get("video_type")
        if vt:
            params.append("video_type=" + quote(str(vt), safe=""))
        if params:
            url += "?" + "&".join(params)
        html = self._get_html(url, headers={"Referer": self.host + PREFIX + "/"})
        return self._parse_cards(html), self._has_more(html, pg)

    def _detail(self, vid):
        vid = self._extract_id(vid)
        if not vid:
            return {"list": [], "msg": "未找到此影片"}
        url = "%s%s/video/%s" % (self.host, PREFIX, vid)
        html = self._get_html(url, headers={"Referer": self.host + PREFIX + "/"})
        if not html:
            return {"list": [], "msg": "未找到此影片"}
        name = ""
        m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
        if m:
            name = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        pic = ""
        m = re.search(r'<video[^>]+poster="([^"]+)"', html)
        if m:
            pic = m.group(1)
        else:
            m = re.search(r'property="og:image"\s+content="([^"]+)"', html)
            if m:
                pic = m.group(1)
        actors = []
        for m in re.finditer(r'<a[^>]+href="/zh/actress/([^"]+)"[^>]*class="watch-actor-card"[^>]*>\s*<img[^>]*alt="([^"]*)"[^>]*>\s*<span>([^<]*)</span>', html, re.S):
            nm = m.group(3).strip() or m.group(2).strip()
            if nm:
                actors.append((m.group(1), nm))
        tags = []
        for m in re.finditer(r'<a[^>]+href="/zh/search\?q=([^"]+)"[^>]*class="watch-link-chip"[^>]*>([^<]*)</a>', html):
            tags.append(m.group(2).strip())
        categories = []
        for m in re.finditer(r'<a[^>]+href="/zh/category/([^"]+)"[^>]*class="watch-link-chip[^"]*"[^>]*>([^<]*)</a>', html):
            categories.append(m.group(2).strip())
        channel = ""
        m = re.search(r'<a[^>]+href="/zh/channel/([^"]+)"[^>]*class="watch-inline-link"[^>]*>([^<]*)</a>', html)
        if m:
            channel = m.group(2).strip()
        video_type = ""
        m = re.search(r'<strong>Video Type</strong>\s*<span[^>]*class="watch-detail-value">([^<]*)</span>', html)
        if m:
            video_type = m.group(1).strip()
        duration = ""
        m = re.search(r'<strong>时长</strong>\s*<span[^>]*class="watch-detail-value">([^<]*)</span>', html)
        if m:
            duration = m.group(1).strip()
        year = ""
        m = re.search(r'<time[^>]+datetime="(\d{4})', html)
        if m:
            year = m.group(1)
        remarks = video_type
        if duration:
            remarks = ("%s · %s" % (video_type, duration)) if video_type else duration
        lines = []
        if actors:
            lines.append("女优：" + "、".join(nm for _sl, nm in actors))
        if tags:
            lines.append("标签：" + " ".join(tags))
        if categories:
            lines.append("分类：" + "、".join(categories))
        if channel:
            lines.append("频道：" + channel)
        if video_type:
            lines.append("类型：" + video_type)
        if duration:
            lines.append("时长：" + duration)
        if year:
            lines.append("发行：" + year)
        content = "\n".join(lines)
        vod = {
            "vod_id": vid,
            "vod_name": name or vid,
            "vod_pic": self._pic({"pic": pic}),
            "type_name": (categories[0] if categories else "") or "",
            "vod_year": year or "",
            "vod_area": "",
            "vod_remarks": remarks or "",
            "vod_director": "",
            "vod_actor": "、".join(self._clickable_actor(sl, nm) for sl, nm in actors),
            "vod_content": content,
            "vod_play_from": "正片",
            "vod_play_url": "正片$" + vid,
        }
        return {"list": [vod]}

    def _clickable_actor(self, slug, name):
        if not name:
            return ""
        ident = "actor/" + quote(slug, safe="")
        payload = json.dumps({"id": ident, "name": name, "type_flag": "0"}, ensure_ascii=False, separators=(",", ":"))
        return "[a=cr:%s/]%s[/a]" % (payload, name)

    def _fetch_play(self, vid):
        if not vid:
            return ""
        detail_url = "%s%s/video/%s" % (self.host, PREFIX, vid)
        html = self._get_html(detail_url, headers={"Referer": self.host + PREFIX + "/"})
        ticket = ""
        if html:
            m = re.search(r'"playback":\s*\{"endpoint":"[^"]*","ticket":"([^"]+)"', html)
            if m:
                ticket = m.group(1)
        if not ticket:
            return ""
        endpoint = "%s%s/video/%s/playback" % (self.host, PREFIX, vid)
        headers = {
            "User-Agent": UA,
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": detail_url,
        }
        resp = self._req(endpoint, method="POST", postType="form", data={"ticket": ticket}, headers=headers, timeout=20000)
        resp = self._resp_dict(resp)
        if resp.get("error"):
            return ""
        code = resp.get("code") or 0
        if not 200 <= code < 300:
            return ""
        try:
            obj = json.loads(resp.get("content", "") or "{}")
        except Exception:
            return ""
        sources = obj.get("sources") or []
        for s in sources:
            src = s.get("src") or ""
            if src and src.startswith("http"):
                return src
        return ""
