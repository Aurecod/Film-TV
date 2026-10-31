# -*- coding: utf-8 -*-
# [Hubff¹⁸  更新于:2026-10-31 13:23]
import json
import re
import time
import threading
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

NAME = "Hubff"
HOSTS = ["https://hubff.com"]
UA = "Mozilla/5.0 (Linux; Android 13; Pixel) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
PAGE_SIZE = 39
CACHE_TTL = 300
DEBUG = False

CATS = [
    ("latest", "最新"),
    ("hot", "熱門"),
    ("tag/國產", "國產"),
    ("tag/日本", "日本"),
    ("tag/歐美", "歐美"),
    ("tag/韓國", "韓國"),
    ("tag/無碼", "無碼"),
    ("tag/中文", "中文"),
    ("tag/美乳", "美乳"),
    ("tag/巨乳", "巨乳"),
    ("tag/少女", "少女"),
    ("tag/本土", "本土"),
    ("tag/動畫", "動畫"),
    ("tag/有碼", "有碼"),
    ("tag/變態", "變態"),
    ("tag/痴漢", "痴漢"),
    ("tag/騎乘", "騎乘"),
    ("tag/顏射", "顏射"),
    ("tag/教師", "教師"),
    ("tag/凌辱", "凌辱"),
    ("tag/拘束", "拘束"),
    ("tag/熟女", "熟女"),
    ("tag/亂倫", "亂倫"),
    ("tag/人妻", "人妻"),
    ("tag/少婦", "少婦"),
    ("tag/母親", "母親"),
    ("tag/近親", "近親"),
    ("tag/母乳", "母乳"),
    ("tag/口交", "口交"),
    ("tag/中出", "中出"),
    ("tag/高潮", "高潮"),
    ("tag/虐待", "虐待"),
    ("tag/SM", "SM"),
    ("tag/學生", "學生"),
    ("tag/女同", "女同"),
    ("tag/蘿莉", "蘿莉"),
    ("tag/亂交", "亂交"),
    ("tag/3P", "3P"),
    ("tag/制服", "制服"),
    ("tag/調教", "調教"),
    ("tag/主播", "主播"),
    ("tag/網紅", "網紅"),
    ("tag/強姦", "強姦"),
    ("tag/媚藥", "媚藥"),
    ("tag/孕婦", "孕婦"),
    ("tag/妊婦", "妊婦"),
    ("tag/偷拍", "偷拍"),
    ("tag/自慰", "自慰"),
    ("tag/素人", "素人"),
    ("tag/處女", "處女"),
    ("tag/白虎", "白虎"),
    ("tag/黑人", "黑人"),
    ("tag/Deepfake", "Deepfake"),
    ("tag/野外露出", "野外露出"),
    ("tag/Onlyfans", "Onlyfans"),
]


class Spider(BaseSpider):

    def __init__(self):
        self.hosts = list(HOSTS)
        self.host = self.hosts[0]
        self.name = NAME
        self._cache = {}
        self._cache_time = {}
        self._lock = threading.Lock()

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
        if action == "toast":
            return {"msg": "这是测试 Toast"}
        return {"msg": "不支持此操作"}

    def homeContent(self, filter):
        classes = [{"type_id": tid, "type_name": name} for tid, name in CATS]
        result = {"class": classes}
        if filter:
            result["filters"] = {c["type_id"]: [] for c in classes}
        items = self._fetch_list("home", 1, {})
        result["list"] = [self._vod(x) for x in items]
        return result

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        tid = str(tid or "").strip()
        extend = extend or {}

        if tid.startswith("actor/") or tid.startswith("director/"):
            name = unquote(tid.split("/", 1)[1])
            items = self._fetch_search(name, pg)
        elif tid.startswith("tag/"):
            name = unquote(tid[len("tag/"):])
            items = self._fetch_search(name, pg)
        else:
            items = self._fetch_list(tid, pg, extend)

        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": pg if len(items) < PAGE_SIZE else 9999,
            "limit": PAGE_SIZE,
            "total": 999999,
        }

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        responses = [self._detail(str(video_id)) for video_id in ids]
        merged = {k: v for k, v in (responses[0] or {}).items() if k != "list"}
        merged["list"] = [item for response in responses for item in (response.get("list") or [])]
        return merged

    def _detail(self, vid):
        vid = str(vid or "").strip()
        if not vid:
            return {"list": [], "msg": "缺少视频 ID"}
        data = self._fetch_detail(vid)
        if not data:
            return {"list": [], "msg": "未找到此影片"}

        eps = data.get("episodes") or []
        if eps:
            lines = []
            for ep in eps:
                title = self._safe_label(ep.get("name") or "正片")
                url = ep.get("url") or ""
                if url:
                    lines.append("%s$%s" % (title, url))
            play_url = "#".join(lines)
            play_from = data.get("source_name") or "正片"
        else:
            url = data.get("url") or ""
            play_url = ("正片$" + url) if url else "正片$"
            play_from = data.get("source_name") or "正片"

        vod = {
            "vod_id": vid,
            "vod_name": data.get("name") or vid,
            "vod_pic": data.get("pic") or "",
            "type_name": data.get("category") or "",
            "vod_year": data.get("year") or "",
            "vod_area": data.get("area") or "",
            "vod_remarks": data.get("remarks") or "",
            "vod_director": self._clickable("director", data.get("director") or ""),
            "vod_actor": "、".join(self._clickable("actor", a) for a in (data.get("actors") or [])),
            "vod_content": data.get("description") or "",
            "vod_play_from": play_from,
            "vod_play_url": play_url,
        }
        return {"list": [vod]}

    def searchContent(self, key, quick, pg="1"):
        pg = self._int(pg, 1)
        items = self._fetch_search(str(key or "").strip(), pg)
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": pg if len(items) < PAGE_SIZE else 9999,
            "limit": PAGE_SIZE,
            "total": 999999,
        }

    def playerContent(self, flag, id, vipFlags):
        url = self._fetch_play(str(id or "").strip())
        if not url:
            return {"parse": 0, "msg": "无法获取播放地址"}
        return {
            "parse": 0,
            "jx": 0,
            "url": url,
            "format": "application/x-mpegURL",
            "header": self._string_map({"User-Agent": UA, "Referer": self.host + "/"}),
        }

    def liveContent(self, url):
        return "[]"


    def _safe_label(self, text):
        return str(text or "").replace("$", "＄").replace("#", "＃").strip()

    def _int(self, x, d=0):
        try:
            return int(x)
        except Exception:
            return d

    def _clean(self, s):
        if not s:
            return ""
        import html as _h
        s = re.sub(r"<[^>]+>", "", str(s))
        s = _h.unescape(s)
        return re.sub(r"\s+", " ", s).strip()

    @staticmethod
    def _string_map(value, name="headers"):
        if value in (None, ""):
            return {}
        if not isinstance(value, dict):
            return {}
        return {str(k): str(v) for k, v in value.items() if v is not None}

    def _abs(self, path):
        path = str(path)
        if path.startswith("http"):
            return path
        return self.host.rstrip("/") + "/" + path.lstrip("/")

    def _req(self, url, **kw):
        net = getattr(self, "net", None)
        if net is not None:
            try:
                opts = {"timeout": kw.get("timeout", 15000)}
                for k in ("params", "headers", "method", "postType", "data", "body", "buffer", "redirect", "cookie"):
                    if k in kw and kw[k] is not None:
                        opts[k] = kw[k]
                resp = net.req(url, opts)
                if isinstance(resp, dict):
                    return resp
                if isinstance(resp, str):
                    return {"code": 200, "content": resp, "headers": {}, "error": None}
                return {"code": 0, "content": "", "headers": {}, "error": str(resp)}
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
                code = resp.getcode() or 0
                return {"code": code, "content": raw.decode("utf-8", "replace"), "headers": dict(resp.headers), "error": None}
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

    def _clickable(self, kind, name):
        if not name:
            return ""
        try:
            payload = json.dumps(
                {"id": kind + "/" + quote(name, safe=""), "name": name, "type_flag": "0"},
                ensure_ascii=False,
                separators=(",", ":"),
            )
            return "[a=cr:%s/]%s[/a]" % (payload, name)
        except Exception:
            return name

    def _vod(self, item):
        item = item or {}
        return {
            "vod_id": item.get("id") or "",
            "vod_name": item.get("name") or item.get("id") or "",
            "vod_pic": item.get("pic") or "",
            "vod_remarks": item.get("remarks") or "",
        }

    def _cat_path(self, tid, pg):
        tid = str(tid or "").strip()
        pg = self._int(pg, 1)
        if tid == "latest":
            path = "/update.php?tags=latest"
        elif tid == "hot":
            path = "/update.php?tags=hot"
        elif tid == "home":
            path = "/"
        elif tid.startswith("tag/"):
            path = "/tag.php?tags=" + quote(unquote(tid[len("tag/"):]), safe="")
        else:
            path = "/tag.php?tags=" + quote(unquote(tid), safe="")
        if pg > 1:
            path += "&page=%d" % pg
        return path

    def _fetch_list(self, tid, pg, extend):
        html = self._get_html(self._abs(self._cat_path(tid, pg)))
        if not html:
            return []
        return self._parse_cards(html)

    def _fetch_search(self, keyword, pg):
        if not keyword:
            return []
        html = self._get_html(self._abs(self._cat_path(keyword, pg)))
        if not html:
            return []
        return self._parse_cards(html)

    def _parse_cards(self, html):
        items = []
        seen = set()
        for m in re.finditer(r'<a\s+href="[^"]*view\.php\?[^"]*vid=([^"&]+)[^"]*"[^>]*>(.*?)</a>', html, re.S):
            vid = m.group(1).strip()
            inner = m.group(2)
            if not vid or vid in seen:
                continue
            title = ""
            tm = re.search(r'title="([^"]*)"', m.group(0))
            if tm:
                title = self._clean(tm.group(1))
            if not title:
                tm = re.search(r'<li class="title">([\s\S]*?)</li>', inner)
                if tm:
                    title = self._clean(tm.group(1))
            if not title:
                continue
            pic = ""
            cm = re.search(r'<img[^>]+(?:img|src)="([^"]+)"', inner)
            if cm:
                pic = self._clean(cm.group(1))
            remarks = ""
            sm = re.search(r'<span>([^<]*)</span>', inner)
            if sm:
                remarks = self._clean(sm.group(1))
            seen.add(vid)
            items.append({"id": vid, "name": title, "pic": pic, "remarks": remarks})
            if len(items) >= 60:
                break
        if DEBUG:
            print("[Hubff] parsed %d cards" % len(items))
        return items

    def _fetch_detail(self, vid):
        html = self._get_html(self._abs("/view.php?cid=&vid=" + quote(vid, safe="")))
        if not html:
            return None
        name = vid
        m = re.search(r"<h1>([\s\S]*?)</h1>", html)
        if m:
            name = self._clean(m.group(1))
        pic = ""
        m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', html)
        if not m:
            m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image', html)
        if m:
            pic = self._clean(m.group(1))
        if not pic:
            m = re.search(r'<img[^>]+src=["\'](https?://[^"\']*cover[^"\']*)', html)
            if m:
                pic = self._clean(m.group(1))
        tags = []
        tm = re.search(r'<div class="word"[^>]*style="text-align:\s*center;?\s*"[^>]*>([\s\S]*?)</div>', html)
        if tm:
            for a in re.finditer(r'<a\s+href="[^"]*tag\.php\?tags=([^"&]+)"[^>]*>([^<]+)</a>', tm.group(1)):
                nm = self._clean(a.group(2))
                if nm and nm not in tags:
                    tags.append(nm)
        embed_vid = vid
        m = re.search(r'<iframe[^>]+src=["\'][^"\']*embed\.php\?vid=([^"&]+)', html)
        if m:
            embed_vid = m.group(1).strip()
        year = ""
        m = re.search(r'timeago"\s+title=["\'](\d{4})', html)
        if m:
            year = m.group(1)
        desc_parts = []
        for t in tags:
            desc_parts.append(self._clickable("tag", t))
        description = " ".join(desc_parts)
        return {
            "name": name,
            "pic": pic,
            "category": "",
            "year": year,
            "area": "",
            "remarks": "",
            "director": "",
            "actors": [],
            "description": description,
            "source_name": "正片",
            "episodes": [{"name": "正片", "url": "play/" + embed_vid}],
        }

    def _fetch_play(self, play_id):
        pid = str(play_id or "").strip()
        if pid.startswith("play/"):
            pid = pid[len("play/"):]
        if not pid:
            return ""
        html = self._get_html(self._abs("/embed/embed.php?vid=" + quote(pid, safe="")))
        if not html:
            return ""
        m = re.search(r'source\s*:\s*["\']([^"\']+)["\']', html)
        if m:
            return m.group(1).strip()
        m = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', html)
        if m:
            return m.group(1).strip()
        return ""

