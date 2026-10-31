# -*- coding: utf-8 -*-
# [黄果短剧¹⁸  更新于:2026-10-31 13:23]
import base64
import json
import re
import sys
import time
from urllib.parse import quote as _quote


sys.path.append('..')
try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        pass

HOST = "https://huangguoai.com"
UA = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")
PAGE_SIZE = 21
CACHE_TTL = 60


PIC_KEY = b"f5d965df75336270"
PIC_IV = b"97b60394abc2fbe1"


STYLE = {"type": "rect", "ratio": 0.75}


CHANNELS = [
    ("ai-duanju", "AI成人短剧"),
    ("ai-manju", "AI成人漫剧"),
    ("ai-huanlian", "AI换脸"),
    ("ai-mogai", "AI魔改"),
]


TAGS = [
    ("", "全部"), ("dushi", "都市"), ("wanghong", "网红"), ("xiandai", "现代"),
    ("zhichang", "职场"), ("xiaoyuan", "校园"), ("yulequan", "娱乐圈"),
    ("haomen", "豪门"), ("bazong", "霸总"), ("tianchong", "甜宠"),
    ("nixi", "逆袭"), ("chuanyue", "穿越"), ("chongsheng", "重生"),
    ("xianxia", "仙侠"), ("xuanhuan", "玄幻"), ("gufeng", "古风"),
    ("qihuan", "奇幻"), ("kehuan", "科幻"), ("lingyi", "灵异"),
    ("xuanyi", "悬疑"), ("fanzui", "犯罪"), ("quanmou", "权谋"),
    ("wuxia", "武侠"), ("xitong", "系统"), ("naodong", "脑洞"),
    ("chaonengli", "超能力"), ("dananzhu", "大男主"), ("danvzhu", "大女主"),
    ("hougong", "后宫"), ("nuelian", "虐恋"), ("mingxing", "明星"),
    ("shunv", "熟女"), ("zhuixu", "赘婿"), ("mengzhai", "萌宅"),
]


PANELS = [("latest", "最新"), ("hot", "最热"), ("original", "原创"), ("random", "随机")]

RE_CARD = re.compile(
    r'<div class="hg-drama-card"[^>]*data-track-id="(\d+)"'
    r'[^>]*data-track-title="([^"]*)"[^>]*>(.*?)</div>\s*</div>', re.S)
RE_PIC = re.compile(r'data-src="([^"]+)"')
RE_EP = re.compile(r'hg-drama-card__episode">([^<]+)<')
RE_SCORE = re.compile(r'hg-drama-card__score">([^<]+)<')
RE_DESC = re.compile(r'hg-drama-card__desc">([^<]*)<')
RE_TAG = re.compile(r'<a class="hg-tag" href="/tag/[^"]*">([^<]+)</a>')


class _NetResp(object):
    def __init__(self, resp_dict, url):
        if isinstance(resp_dict, str):
            resp_dict = {"code": 200, "content": resp_dict, "headers": {}}
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
        return _json.loads(self.text or "{}")
    def raise_for_status(self):
        if self.status_code < 200 or self.status_code >= 300:
            raise RuntimeError("HTTP %s" % self.status_code)
    def __repr__(self):
        return "<_NetResp %s>" % self.status_code


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
    def _build_url(self, url, params):
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
            if kw.get("buffer") == 3:
                opts["buffer"] = 3
            if timeout_s:
                opts["timeout"] = int(timeout_s * 1000)
            try:
                if kw.get("buffer") == 3 and hasattr(self.net, "reqParts"):
                    parts = self.net.reqParts(full, opts)
                    if isinstance(parts, (list, tuple)) and len(parts) >= 2:
                        return _NetResp({"code": 200, "content": parts[1], "headers": {}}, full)
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


    def init(self, extend=""):
        self.host = HOST
        if extend:
            try:
                cfg = json.loads(extend)
                site = (cfg.get("site") or cfg.get("url") or "").strip().rstrip("/")
                if site:
                    self.host = site
            except Exception:
                pass
        self.headers = {
            "User-Agent": UA,
            "Referer": self.host + "/",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        self.session = _NetSession(getattr(self, "net", None))
        self.session.headers.update(self.headers)
        self._cache = {}


    def getDependence(self):
        return []

    def destroy(self):
        pass

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(m3u8|mp4|ts)(\?|$)', str(url)))

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return {"msg": "不支持此操作"}

    def proxy(self, params):
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except Exception:
                params = {}
        param = params or {}
        if param.get("type") != "pic":
            return [404, "text/plain", ""]
        url = self._d64(param.get("url", ""))
        if not url:
            return [404, "text/plain", ""]
        for i in range(2):
            try:
                r = self.session.get(url, timeout=20, verify=False, buffer=3)
                if r.status_code != 200 or not r.content:
                    continue
                img = self._pic_decrypt(r.content)
                return [200, self._mime(img), self._img_stream(img), {}]
            except Exception:
                continue
        return [404, "text/plain", ""]

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

    localProxy = proxy

    def homeContent(self, filter):
        classes = [{"type_id": c, "type_name": n, "style": STYLE} for c, n in CHANNELS]
        filters = {}
        for c, _ in CHANNELS:
            filters[c] = [
                {"key": "panel", "name": "排序",
                 "value": [{"n": n, "v": k} for k, n in PANELS]},
                {"key": "tag", "name": "标签",
                 "value": [{"n": n, "v": v} for v, n in TAGS]},
            ]
        return {"class": classes, "filters": filters,
                "list": self._cards(self._get("/") or "")}

    def homeVideoContent(self):
        return {"list": self._cards(self._get("/") or "")}


    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        extend = extend or {}
        tag = (extend.get("tag") or "").strip()
        panel = (extend.get("panel") or "latest").strip()


        if tag:
            if pg > 1:
                return {"list": [], "page": pg, "pagecount": pg, "limit": PAGE_SIZE, "total": 0}
            html = self._get("/tag/%s/" % tag) or ""
            items = self._cards(html)
            return {"list": items, "page": 1, "pagecount": 1,
                    "limit": len(items) or PAGE_SIZE, "total": len(items)}

        path = "/%s/" % tid if pg == 1 else "/%s/%d/" % (tid, pg)
        html = self._get(path) or ""
        items = self._cards(html, panel=panel)

        if panel == "latest":
            pages = self._int(self._one(r'data-pages="(\d+)"', html), 0) or 9999
        else:
            pages = 1
        return {"list": items, "page": pg, "pagecount": pages,
                "limit": PAGE_SIZE, "total": pages * PAGE_SIZE}



    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        responses = [self._detail(str(video_id)) for video_id in ids]
        merged = {k: v for k, v in (responses[0] or {}).items() if k != "list"} if responses[0] else {}
        merged["list"] = [item for response in responses if response for item in (response.get("list") or [])]
        return merged
    def _detail(self, vid):
        vid = str(vid).strip()
        raw = self._get("/detail/%s/" % vid)
        if not raw:
            return {"list": []}
        html = self._nostyle(raw)

        name = self._one(r'<h1>([^<]+)</h1>', html)
        pic = self._pic_url(self._one(r'hg-web-detail__poster.*?data-src="([^"]+)"', html, flags=re.S))

        desc = self._one(r'data-desc[^>]*>\s*([^<]*)', html).strip()
        remarks = self._one(r'hg-web-detail__episode">([^<]+)<', html)
        cate = self._one(r'data-track-type-name="([^"]*)"', html)
        actor = self._one(r'/author/\d+/">([^<]+)</a>', html)
        year = self._one(r'(\d{4})-\d{2}-\d{2}\s*上线', html)
        tags = "/".join(dict.fromkeys(RE_TAG.findall(html)))


        eps = sorted({self._int(x) for x in re.findall(r'data-ep-id="(\d+)"', html)})
        if not eps:
            eps = [1]
        play = "#".join("第%d集$%s|%d" % (n, vid, n) for n in eps)

        vod = {
            "vod_id": vid,
            "vod_name": name or vid,
            "vod_pic": pic,
            "type_name": cate or tags,
            "vod_year": year,
            "vod_area": "",
            "vod_remarks": remarks or ("共%d集" % len(eps)),
            "vod_actor": actor,
            "vod_director": "",
            "vod_content": desc,
            "vod_play_from": "黄果短剧",
            "vod_play_url": play,
        }
        return {"list": [vod]}


    def searchContent(self, key, quick, pg="1"):
        pg = self._int(pg, 1)
        kw = _quote(str(key), safe="")
        path = "/search/video/%s/" % kw if pg == 1 else "/search/video/%s/%d/" % (kw, pg)
        html = self._get(path) or ""
        items = self._cards(html)
        pages = self._int(self._one(r'data-pages="(\d+)"', html), 0) or (pg if not items else pg + 1)
        return {"list": items, "page": pg, "pagecount": pages,
                "limit": PAGE_SIZE, "total": pages * PAGE_SIZE}


    def playerContent(self, flag, id, vipFlags):
        vid, ep = self._split(id)
        path = "/video/%s/" % vid if ep <= 1 else "/video/%s/ep-%d/" % (vid, ep)
        html = self._get(path, ttl=0) or ""
        url = self._m3u8(html)
        return {
            "parse": 0,
            "url": url,
            "header": {"User-Agent": UA, "Referer": self.host + "/"},
        }


    def _get(self, path, ttl=CACHE_TTL, retry=2):
        url = path if path.startswith("http") else self.host + path
        if ttl:
            hit = self._cache.get(url)
            if hit and time.time() - hit[1] < ttl:
                return hit[0]
        txt = None
        for i in range(max(1, retry)):
            try:
                r = self.session.get(url, timeout=20, verify=False)
                if r.status_code != 200:
                    continue
                r.encoding = r.apparent_encoding or "utf-8"
                txt = r.text
                break
            except Exception:
                continue
        if txt is None:
            return None
        if ttl:
            self._cache[url] = (txt, time.time())
        return txt

    def _cards(self, html, panel=None):
        if not html:
            return []
        html = self._nostyle(html)
        if panel:
            seg = self._panel_seg(html, panel)
            if seg is not None:
                html = seg
        out, seen = [], set()
        for m in RE_CARD.finditer(html):
            try:
                vid, title, body = m.group(1), m.group(2), m.group(3)
                if not vid or vid in seen:
                    continue
                seen.add(vid)
                pic = RE_PIC.search(body)
                ep = RE_EP.search(body)
                sc = RE_SCORE.search(body)
                rem = ep.group(1).strip() if ep else ""
                if sc:
                    rem = ("%s %s" % (rem, sc.group(1).strip())).strip()
                out.append({
                    "vod_id": vid,
                    "vod_name": self._unesc(title) or vid,
                    "vod_pic": self._pic_url(pic.group(1) if pic else ""),
                    "vod_remarks": rem,
                })
            except Exception:
                continue
        return out

    def _panel_seg(self, html, panel):
        starts = [(m.start(), m.group(1) or m.group(2)) for m in re.finditer(
            r'hg-card-grid[^>]*data-channel-panel="(\w+)"|<template data-panel-cards="(\w+)"', html)]
        for i, (pos, key) in enumerate(starts):
            if key != panel:
                continue
            end = starts[i + 1][0] if i + 1 < len(starts) else len(html)
            seg = html[pos:end]
            if RE_CARD.search(seg):
                return seg
        return None

    def _m3u8(self, html):
        if not html:
            return ""
        for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
            try:
                data = json.loads(m.group(1))
            except Exception:
                continue
            for it in (data.get("@graph") or [data]):
                if not isinstance(it, dict):
                    continue
                if it.get("@type") == "VideoObject":
                    u = str(it.get("contentUrl") or "")
                    if ".m3u8" in u:
                        return self._unesc(u)
        m = re.search(r'data-play-src="([^"]+\.m3u8[^"]*)"', html)
        if m:
            return self._unesc(m.group(1))
        m = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', html)
        return self._unesc(m.group(1)) if m else ""

    def _nostyle(self, html):
        return re.sub(r'<style.*?</style>', '', html or '', flags=re.S)


    def _pic_url(self, u):
        u = self._fix(u)
        if not u:
            return ""
        enc = _quote(self._e64(u), safe="")
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

    def _pic_decrypt(self, raw):
        if raw[:2] == b'\xff\xd8' or raw[:4] == b'\x89PNG' or raw[8:12] == b'WEBP' or raw[:4] == b'GIF8':
            return raw
        n = len(raw) - (len(raw) % 16)
        if n <= 0:
            return raw
        try:
            from Crypto.Cipher import AES
            dec = AES.new(PIC_KEY, AES.MODE_CBC, PIC_IV).decrypt(raw[:n])
        except Exception:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            d = Cipher(algorithms.AES(PIC_KEY), modes.CBC(PIC_IV)).decryptor()
            dec = d.update(raw[:n]) + d.finalize()
        return self._trim(dec)

    def _trim(self, b):
        if b[:2] == b'\xff\xd8':
            i = b.rfind(b'\xff\xd9')
            return b[:i + 2] if i > 0 else b
        if b[:4] == b'\x89PNG':
            i = b.rfind(b'IEND')
            return b[:i + 8] if i > 0 else b
        return b

    def _mime(self, b):
        if b[:4] == b'\x89PNG':
            return "image/png"
        if b[:4] == b'GIF8':
            return "image/gif"
        if b[8:12] == b'WEBP':
            return "image/webp"
        return "image/jpeg"

    def _e64(self, s):

        return base64.urlsafe_b64encode(str(s).encode("utf-8")).decode("utf-8")

    def _d64(self, s):
        s = str(s or "").strip()
        s = _quote(s, safe="-_") if False else s
        from urllib.parse import unquote
        s = unquote(s).replace(" ", "+")
        for dec in (base64.urlsafe_b64decode, base64.b64decode):
            try:
                pad = "=" * (-len(s) % 4)
                return dec(s + pad).decode("utf-8")
            except Exception:
                continue
        return ""

    def _fix(self, u):
        u = (u or "").strip()
        if not u:
            return ""
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("/"):
            return self.host + u
        return u

    def _one(self, pat, html, flags=0):
        m = re.search(pat, html or "", flags)
        return self._unesc(m.group(1)) if m else ""

    def _unesc(self, s):
        return (str(s).replace("&amp;", "&").replace("&quot;", '"')
                .replace("&lt;", "<").replace("&gt;", ">")
                .replace("&#39;", "'").replace("\\u0026", "&"))

    def _split(self, x):
        p = str(x).split("|", 1)
        return p[0], self._int(p[1], 1) if len(p) > 1 else 1

    def _int(self, x, d=0):
        try:
            return int(str(x).strip())
        except Exception:
            return d

