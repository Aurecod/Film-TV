# -*- coding: utf-8 -*-
# [小chu女¹⁸  更新于:2026-10-31 13:23]
import base64
import re
import json
import time
import threading
import urllib.parse
from urllib.parse import urljoin, urlparse, parse_qs, urlencode

try:
    requests.packages.urllib3.disable_warnings()
except Exception:
    pass

try:
    from lxml import etree
except Exception:
    etree = None

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass

NAME = "小chu女"
HOSTS = ["https://ukqfm.myacetweay.buzz"]
UA = ("Mozilla/5.0 (Linux; Android 13; Pixel 6) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")
PAGE_SIZE = 20
MIN_HTML = 6000
STYLE = {"type": "rect", "ratio": 1.33}
SRC = "8k3u8"

CATEGORIES = [
    ("vodtype/18",  "日本精选"),
    ("vodtype/48",  "抖音热瓜"),
    ("vodtype/61",  "日式美女"),
    ("vodtype/132", "杏吧资源"),
    ("vodtype/268", "奶香香"),
    ("vodtype/296", "国产精品"),
    ("vodtype/382", "黄色仓库"),
    ("vodtype/423", "麻豆资源"),
]

HOME_PATH = "chu/"
HOME_LIMIT = 80

ITEM_BOX = re.compile(r"<section class=\"item-box\">(.*?)</section>", re.S)
ANCHOR = re.compile(r"<a\s+href=\"([^\"]+)\"[^>]*?title=\"([^\"]*)\"", re.S)
LAZY_IMG = re.compile(r"<img[^>]*data-src=\"([^\"]+)\"", re.S)
DATE_BOX = re.compile(r"<small[^>]*>\s*(\d{2}-\d{2}-\d{2}|\d{4}-\d{2}-\d{2})\s*</small>", re.S)
PAGE_TIP = re.compile(r"共\s*(\d+)\s*条\s*数据?[^<]*当前\s*(\d+)\s*/\s*(\d+)\s*页")

RE_TITLE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S)
RE_COVER = re.compile(r"<img[^>]*class=\"lazy-image\"[^>]*data-src=\"([^\"]+)\"", re.S)
RE_DATE = re.compile(r"<h6[^>]*>\s*([\d\- :]+?)\s*</h6>", re.S)
RE_CAT = re.compile(r"<a href=\"[^\"]*vodtype/\d+/?\" title=\"([^\"]+)\"", re.S)
RE_TAGS = re.compile(r"<ul class=\"info-auxiliary-txt.*?</ul>", re.S)
RE_TAG_A = re.compile(r"<a[^>]*>([^<]+)</a>", re.S)
RE_DESC = re.compile(r"<div class=\"tx-text[^\"]*\">\s*<p>(.*?)</p>", re.S)
RE_PLAY_BTN = re.compile(r"href\s*=\s*\"(/vodplay/\d+-\d+-\d+/)\"", re.S)
RE_PLAYER_DATA = re.compile(r"player_data\s*=\s*(\{.*?\})\s*</script>", re.S)
RE_M3U8 = re.compile(r"https?://[^\s\"'<>]+?\.m3u8[^\s\"'<>]*")


def _clean(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                 ("&quot;", '"'), ("&#39;", "'"), ("&hellip;", "...")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


def _label(t):
    return str(t or "").replace("$", "＄").replace("#", "＃").replace("@", "＠").strip()


def _abs(base, url):
    if not url:
        return ""
    return urljoin(base, url.strip())


KEY_URI = re.compile(r"URI\s*=\s*['\"]([^'\"]+)['\"]")


def _abs_key(line, plist_url):
    m = KEY_URI.search(line)
    if not m:
        return line
    u = m.group(1)
    if u.startswith("http"):
        return line
    return line.replace(u, _abs(plist_url, u))


def _e64(s):
    return base64.urlsafe_b64encode(str(s or "").encode("utf-8")).decode("utf-8")


def _d64(s):
    s = str(s or "").strip()
    s = urllib.parse.unquote(s).replace(" ", "+")
    for dec in (base64.urlsafe_b64decode, base64.b64decode):
        try:
            return dec(s + "=" * (-len(s) % 4)).decode("utf-8")
        except Exception:
            continue
    return ""


def _mime(raw):
    if len(raw) > 4 and raw[:4] == b"\x89PNG":
        return "image/png"
    if len(raw) > 4 and raw[:4] == b"GIF8":
        return "image/gif"
    if len(raw) > 12 and raw[8:12] == b"WEBP":
        return "image/webp"
    if len(raw) > 3 and raw[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    return "application/octet-stream"


def _is_image(raw):
    return (len(raw) > 4 and raw[:4] == b"\x89PNG") or \
           (len(raw) > 4 and raw[:4] == b"GIF8") or \
           (len(raw) > 12 and raw[8:12] == b"WEBP") or \
           (len(raw) > 3 and raw[:3] == b"\xff\xd8\xff")


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

    def __init__(self):
        super().__init__()
        self.hosts = list(HOSTS)
        self.host = self.hosts[0]
        self.name = NAME
        self.session = None
        self.options = {}
        self._cache = {}
        self._t = {}
        self._lock = threading.Lock()
        self._proxy_base_cache = None

    def init(self, extend=""):
        self.session = _NetSession(getattr(self, "net", None))
        self.session.verify = False
        self.session.headers.update({
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })
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


    def getDependence(self):
        return []

    def destroy(self):
        with self._lock:
            self._cache.clear()
            self._t.clear()
        self.options = {}

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4|flv|mkv|ts)(\?|$)", str(url)))

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return {"msg": "不支持此操作"}

    def liveContent(self, url):
        return "[]"


    def homeContent(self, filter):
        classes = [{"type_id": c, "type_name": n, "style": STYLE} for c, n in CATEGORIES]
        result = {"class": classes, "list": self._home_list()}
        if filter:
            result["filters"] = {}
        return result

    def homeVideoContent(self):
        return {"list": self._home_list()}

    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        tid = str(tid or "").strip().strip("/")
        if not tid:
            return {"list": [], "page": pg, "pagecount": 1, "limit": PAGE_SIZE, "total": 0}
        if not re.match(r"^vod(?:type|show|search)", tid):
            tid = "vodtype/1"
        data = self._type_page(tid, pg)
        return {
            "list": data["vods"],
            "page": pg,
            "pagecount": pg if data["pagecount"] < 2 else data["pagecount"],
            "limit": PAGE_SIZE,
            "total": data["total"] or data["pagecount"] * PAGE_SIZE,
        }

    def searchContent(self, key, quick, pg="1"):
        pg = self._int(pg, 1)
        key = str(key or "").strip()
        if not key:
            return {"list": [], "page": 1, "pagecount": 1, "limit": PAGE_SIZE, "total": 0}
        html = self._get("vodsearch/-------------.html?wd=%s" % urllib.parse.quote(key), 45)
        items = self._parse_items(html)
        return {
            "list": [self._vod(x) for x in items],
            "page": 1,
            "pagecount": 1,
            "limit": PAGE_SIZE,
            "total": len(items),
        }



    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        responses = [self._detail(str(video_id)) for video_id in ids]
        merged = {k: v for k, v in (responses[0] or {}).items() if k != "list"} if responses[0] else {}
        merged["list"] = [item for response in responses if response for item in (response.get("list") or [])]
        return merged
    def playerContent(self, flag, id, vipFlags):
        raw = str(id or "").strip()
        if not raw:
            return {"parse": 0, "msg": "无法获取播放地址"}
        if "$" in raw:
            raw = raw.split("$", 1)[1].strip()

        m3u8 = ""
        if raw.startswith("http"):
            m3u8 = raw
        elif re.match(r"^\d+$", raw):
            m3u8 = self._m3u8(raw, "")
        elif raw.startswith("/vodplay/") or raw.startswith("vodplay/"):
            m3u8 = self._m3u8("", raw.lstrip("/"))
        if not m3u8:
            return {"parse": 0, "msg": "无法获取播放地址"}

        wrapped = self._wrap(m3u8)
        return {
            "parse": 0,
            "jx": 0,
            "url": wrapped or m3u8,
            "header": {"User-Agent": UA, "Referer": self.host + "/"},
        }

    def proxy(self, params):
        p = self._param(params)
        typ = str(p.get("type") or p.get("t") or "").strip().lower()
        url = (p.get("url") or "").strip()
        if typ == "pic":
            raw = url if url.startswith("http") else _d64(url)
            return self._pic(raw, p)
        if not url:
            return [404, "text/plain", ""]
        if (p.get("do") or "") == "raw":
            return self._upstream(url, p)
        try:
            return self._strip(url, p)
        except Exception:
            return self._upstream(url, p)

    localProxy = proxy

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

    def _pic(self, url, p):
        if not url or not url.startswith("http"):
            return [404, "image/png", b""]
        cands = [url]
        try:
            pu = urlparse(url)
            if pu.path:
                cands.append(self.host.rstrip("/") + pu.path)
            if pu.query:
                cands.append(url.split("?", 1)[0])
                cands.append(self.host.rstrip("/") + pu.path)
            if url.startswith("https://"):
                cands.append("http://" + url[len("https://"):])
        except Exception:
            pass
        seen = set()
        cands = [c for c in cands if not (c in seen or seen.add(c))][:3]
        base_hh = {"User-Agent": UA, "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                  "Accept-Encoding": "identity"}
        for cand in cands:
            for ref in (self.host.rstrip("/") + "/", "https://"):
                hh = dict(base_hh)
                if ref:
                    hh["Referer"] = ref
                try:
                    r = self.session.get(cand, timeout=8, verify=False, headers=hh, buffer=3)
                    b = r.content or b""
                    ct = str(r.headers.get("Content-Type") or "")
                    if r.status_code == 200 and len(b) > 100 and len(b) <= 8 * 1024 * 1024 \
                            and (ct.startswith("image/") or _is_image(b)):
                        if not ct.startswith("image/"):
                            ct = _mime(b)
                        return [200, ct, self._img_stream(b), {"Content-Type": ct,
                                             "Cache-Control": "public, max-age=86400"}]
                except Exception:
                    continue
        return [404, "image/png", b""]


    def _url(self, path):
        if not path:
            return ""
        if path.startswith("http"):
            return path
        return self.host.rstrip("/") + "/" + path.lstrip("/")

    def _get(self, path, ttl=60, timeout=20, headers=None):
        key = self._url(path)
        with self._lock:
            hit = self._cache.get(key)
            if hit and time.time() - hit[1] < ttl:
                return hit[0]
        text = self._fetch(path, timeout, headers)
        with self._lock:
            self._cache[key] = (text, time.time())
            if len(self._cache) > 240:
                for k, _ in sorted(self._cache.items(), key=lambda kv: kv[1][1])[:80]:
                    self._cache.pop(k, None)
        return text

    def _fetch(self, path, timeout=20, headers=None):
        hh = None
        if headers:
            hh = dict(self.session.headers)
            hh.update(headers)
        bad = ""
        for i in range(4):
            for host in self.hosts:
                path_only = not path.startswith("http")
                url = path if not path_only else host.rstrip("/") + "/" + path.lstrip("/")
                try:
                    r = self.session.get(url, timeout=timeout, headers=hh, verify=False,
                                         allow_redirects=True)
                    text = r.text
                    low = text[:600].lower()
                    if "just a moment" in low and "challenge-platform" in low:
                        bad = "cf challenge"
                        continue
                    if "server_name_session" in text or ("location.href" in text and len(text) < 2000):
                        bad = "entry redirect"
                        time.sleep(0.35)
                        continue
                    if r.status_code != 200 or len(text) < MIN_HTML:
                        bad = "http %s len %d" % (r.status_code, len(text))
                        time.sleep(0.35)
                        continue
                    return text
                except Exception as e:
                    bad = str(e)[:120]
            time.sleep(0.25 + 0.2 * i)
        return ""

    def _upstream(self, url, p):
        rng = ""
        for k in list(p.keys()):
            if str(k).lower() in ("range", "Range"):
                rng = str(p.get(k) or "")
                p.pop(k, None)
        hh = {"User-Agent": UA, "Accept": "*/*", "Accept-Encoding": "identity",
              "Referer": self.host + "/"}
        if rng:
            hh["Range"] = rng
        for _ in range(3):
            try:
                r = self.session.get(url, timeout=30, headers=hh, verify=False)
                body = r.content or b""
                cd = str(r.headers.get("Content-Type") or "application/octet-stream")
                if "html" in cd.lower():
                    cd = "text/plain"
                out = {}
                if cd:
                    out["Content-Type"] = cd
                cr = r.headers.get("Content-Range")
                if cr:
                    out["Content-Range"] = cr
                cl = r.headers.get("Content-Length")
                if cl:
                    out["Content-Length"] = cl
                return [r.status_code or 200, cd, self._img_stream(body), out]
            except Exception:
                time.sleep(0.5)
        return [404, "text/plain", b""]


    def _type_page(self, tid, pg):
        tid = tid.strip().strip("/")
        if tid.endswith(".html"):
            tid = tid[:-5]
        if pg <= 1:
            path = tid + "/"
        elif re.match(r"^vodshow/\d+-(.+)-\d+$", tid):
            path = tid + "/"
        else:
            parts = tid.split("/")
            head, rest = parts[0], parts[1:]
            if rest and "-" in (rest[0] or ""):
                rest[0] = rest[0].split("-")[0]
            path = "/".join([head] + rest) + "-%d/" % pg
        html = self._get(path, 60)
        out = {"vods": [self._vod(x) for x in self._parse_items(html)], "pagecount": pg, "total": 0}
        m = PAGE_TIP.search(html or "")
        if m:
            try:
                out["total"] = int(m.group(1))
                out["pagecount"] = max(int(m.group(3)), 1)
            except Exception:
                pass
        return out

    def _vod_list(self, tid, pg):
        return self._type_page(tid, pg)["vods"]

    def _home_list(self):
        vods = self._vod_list(HOME_PATH, 1)
        return vods[:HOME_LIMIT] if HOME_LIMIT > 0 else vods

    def _parse_items(self, html):
        if not html:
            return []
        out = []
        seen = set()
        for m in ITEM_BOX.finditer(html):
            blk = m.group(1)
            am = ANCHOR.search(blk)
            if not am:
                continue
            href = am.group(1).strip()
            if not re.match(r"^/vod(?:detail|play)/\d+", href):
                continue
            nm = re.search(r"/vod(?:detail|play)/(\d+)", href)
            if not nm:
                continue
            vid = nm.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            title = _clean(am.group(2)) or vid
            pic = ""
            im = LAZY_IMG.search(blk)
            if im:
                pic = self._fix_url(im.group(1))
            remarks = ""
            rm = re.search(r"<span class=\"item-auxiliary\">(.*?)</span>", blk, re.S)
            if rm:
                ds = DATE_BOX.search(rm.group(1))
                if ds:
                    remarks = ds.group(1)
            out.append({"id": vid, "name": title, "pic": pic, "remarks": remarks})
        return out


    def _detail(self, vid):
        html = self._get("voddetail/%s/" % vid, 120)
        if not html:
            return None
        info = {"vid": vid}
        tm = RE_TITLE.search(html)
        info["name"] = _clean(tm.group(1)) if tm else vid
        pm = RE_COVER.search(html)
        if pm:
            pic = pm.group(1).strip()
            info["pic"] = pic if pic.startswith("http") else self.host.rstrip("/") + pic
        else:
            info["pic"] = ""
        dm = RE_DATE.search(html)
        info["date"] = (dm.group(1) or "").strip() if dm else ""
        cm = RE_CAT.search(html)
        info["cat"] = _clean(cm.group(1)) if cm else ""
        tags = []
        tb = RE_TAGS.search(html)
        if tb:
            tags = [_clean(x) for x in RE_TAG_A.findall(tb.group(0)) if _clean(x)]
        info["tags"] = "、".join(tags[:12])
        sm = RE_DESC.search(html)
        desc = _clean(sm.group(1)) if sm else ""
        info["desc"] = desc if len(desc) >= 8 else info["name"]

        order = []
        for b in RE_PLAY_BTN.findall(html):
            mm = re.match(r"^/vodplay/(\d+)-(\d+)-(\d+)/$", b.strip())
            if mm and mm.group(1) == str(vid):
                g = (mm.group(2), mm.group(3))
                if g not in order:
                    order.append(g)
        if not order:
            order = [("1", "1")]
        eps = [{"name": "正片", "url": "/vodplay/%s-%s-%s/" % (vid, g[0], g[1])} for g in order]
        play_url = "#".join("%s$%s" % (e["name"], e["url"]) for e in eps)
        vod = {
            "vod_id": vid,
            "vod_name": info.get("name") or vid,
            "vod_pic": self._pic_url(info.get("pic") or ""),
            "vod_year": (info.get("date") or "")[:4],
            "vod_area": "",
            "vod_actor": "",
            "vod_content": info.get("desc") or "",
            "vod_remarks": info.get("tags") or "",
            "type_name": info.get("cat") or "",
            "vod_play_from": "小chu女",
            "vod_play_url": play_url,
        }
        return {"list": [vod]}


    def _m3u8(self, vid, rel_path):
        path = rel_path or "vodplay/%s-1-1/" % vid
        url = path if path.startswith("http") else self.host.rstrip("/") + "/" + path.lstrip("/")
        html = self._get(url, 120)
        if not html:
            return ""
        m = RE_PLAYER_DATA.search(html)
        if m:
            blob = m.group(1).replace("\\/", "/")
            u = ""
            try:
                u = (json.loads(blob).get("url") or "")
            except Exception:
                mm = re.search(r'"url"\s*:\s*"([^"]+)"', blob)
                u = mm.group(1) if mm else ""
            u = u.strip()
            if u:
                if u.startswith("http"):
                    return u
                return self.host.rstrip("/") + u
        for u in RE_M3U8.findall(html):
            return u
        return ""


    def _param(self, param):
        if isinstance(param, dict):
            return dict(param)
        if isinstance(param, (list, tuple)) and param:
            return self._param(param[0])
        s = str(param or "").strip()
        if not s:
            return {}
        if s.startswith("{"):
            try:
                return json.loads(s)
            except Exception:
                pass
        q = s
        if "?" in q:
            q = q.split("?", 1)[1]
        try:
            out = {}
            for k, v in parse_qs(q, keep_blank_values=True).items():
                out[k] = v[0] if v else ""
            if q and not out:
                out["url"] = q
            return out
        except Exception:
            return {}

    def _proxy_base(self):
        if self._proxy_base_cache:
            return self._proxy_base_cache
        base = ""
        if hasattr(self, "proxyUrl"):
            try:
                u = self.proxyUrl(local=False)
                p = urlparse(str(u or ""))
                if p.netloc:
                    base = "%s://%s%s" % (p.scheme, p.netloc, p.path.rstrip("/"))
                    self._proxy_base_cache = base
                    return base
            except Exception:
                pass
        for args in ((), (None, False)):
            try:
                u = self.getProxyUrl(*args)
                p = urlparse(str(u or ""))
                if p.netloc:
                    base = "%s://%s%s" % (p.scheme, p.netloc, p.path.rstrip("/"))
                    break
            except Exception:
                continue
        if base:
            self._proxy_base_cache = base
        return base

    def _wrap(self, url):
        if not url.startswith("http"):
            return ""
        if hasattr(self, "proxyUrl"):
            try:
                p = self.proxyUrl({"url": url})
                if p:
                    return p
            except Exception:
                pass
        base = self._proxy_base()
        if not base:
            return ""
        qs = {k: v[0] for k, v in parse_qs(urlparse(url).query, keep_blank_values=True).items()}
        qs["url"] = url
        qs["do"] = "py"
        try:
            sk = getattr(self, "siteKey", "") or ""
        except Exception:
            sk = ""
        if sk:
            qs["siteKey"] = sk
        return "%s?%s" % (base, urlencode(qs))

    def _fix_url(self, u):
        u = str(u or "").strip()
        if not u:
            return ""
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("/"):
            return self.host.rstrip("/") + u
        return u

    def _pic_url(self, u):
        u = self._fix_url(u)
        if not u:
            return ""
        if hasattr(self, "proxyUrl"):
            try:
                p = self.proxyUrl({"type": "pic", "url": _e64(u)})
                if p:
                    return p
            except Exception:
                pass
        base = self._proxy_base()
        if not base:
            return u
        key = ""
        try:
            key = str(getattr(self, "siteKey", "") or "")
        except Exception:
            key = ""
        out = "%s?do=py&type=pic&url=%s" % (base, urllib.parse.quote(_e64(u), safe=""))
        return out + ("&siteKey=%s" % key if key else "")

    def _strip(self, url, p):
        text, plist = "", url
        for i in range(3):
            try:
                r = self.session.get(url, timeout=30, verify=False,
                                     headers={"User-Agent": UA, "Referer": self.host + "/",
                                              "Accept-Encoding": "identity"})
                if r.status_code in (403, 404, 410):
                    return [r.status_code, "text/plain",
                            self._img_stream(r.text.encode("utf-8", "replace"))]
                text = (r.text or "")
                if not text.lstrip().startswith("#EXTM3U"):
                    return [r.status_code or 200, "text/plain",
                            self._img_stream(r.content or text.encode("utf-8", "replace"))]
                break
            except Exception:
                time.sleep(0.5)
                text = ""
        if not text or not text.lstrip().startswith("#EXTM3U"):
            return self._upstream(url, p)

        sm = re.search(r"#EXT-X-STREAM-INF:[^\r\n]*\r?\n\s*(\S+)", text)
        if sm:
            child = _abs(plist, sm.group(1))
            ok = False
            try:
                rc = self.session.get(child, timeout=30, verify=False,
                                      headers={"User-Agent": UA, "Referer": self.host + "/",
                                               "Accept-Encoding": "identity"})
                if rc.status_code == 200 and (rc.text or "").lstrip().startswith("#EXTM3U"):
                    text, plist, ok = rc.text, child, True
            except Exception:
                ok = False
            if not ok:
                text = text.replace(sm.group(1).strip(), child)
                return [200, "application/vnd.apple.mpegurl",
                        self._img_stream(text.encode("utf-8", "replace")),
                        {"Content-Type": "application/vnd.apple.mpegurl",
                         "Access-Control-Allow-Origin": "*"}]

        cleaned = self._clean_playlist(text, plist)
        if cleaned is None:
            return self._upstream(url, p)
        return [200, "application/vnd.apple.mpegurl", self._img_stream(cleaned.encode("utf-8", "replace")),
                {"Content-Type": "application/vnd.apple.mpegurl",
                 "Access-Control-Allow-Origin": "*"}]

    def _clean_playlist(self, text, plist_url):
        raw = [ln.rstrip("\r\n") for ln in text.splitlines()]
        head = []
        segs = []
        cur_key = None
        i = 0
        n = len(raw)
        while i < n:
            s = raw[i].strip()
            if not s:
                i += 1
                continue
            if s.startswith("#EXTINF"):
                mm = re.match(r"^#EXTINF:([\d.]+)", s)
                dur = float(mm.group(1)) if mm else 0.0
                i += 1
                while i < n and not raw[i].strip():
                    i += 1
                if i < n and not raw[i].strip().startswith("#"):
                    segs.append({"dur": dur, "url": raw[i].strip(), "key": cur_key})
                    i += 1
                continue
            if s.startswith("#EXT-X-KEY"):
                cur_key = s
                i += 1
                continue
            if s.startswith("#EXT-X-MAP"):
                i += 1
                continue
            head.append(s)
            i += 1
        if not segs:
            return None
        groups = {}
        for sg in segs:
            k = _abs(plist_url, sg["url"]).rsplit("/", 1)[0]
            groups[k] = groups.get(k, 0.0) + sg["dur"]
        total = sum(groups.values())
        main_path = max(groups, key=lambda k: groups[k])
        if total and len(groups) > 1 and groups[main_path] < total * 0.98:
            kept = [sg for sg in segs
                    if _abs(plist_url, sg["url"]).rsplit("/", 1)[0] == main_path]
            if len(kept) >= 2:
                segs = kept
        return self._build_playlist(head, segs, plist_url)

    @staticmethod
    def _build_playlist(head, segs, plist_url):
        body = [s for s in head if not s.startswith("#EXT-X-DISCONTINUITY")]
        last_key = None
        for sg in segs:
            if sg["key"] != last_key:
                if sg["key"]:
                    body.append(_abs_key(sg["key"], plist_url))
                last_key = sg["key"]
            body.append("#EXTINF:%.6f," % sg["dur"])
            body.append(_abs(plist_url, sg["url"]))
        return "\n".join(body) + "\n"


    def _vod(self, item):
        item = item or {}
        return {
            "vod_id": item.get("id") or "",
            "vod_name": item.get("name") or item.get("id") or "",
            "vod_pic": self._pic_url(item.get("pic") or ""),
            "vod_remarks": item.get("remarks") or "",
        }

    def _int(self, x, d=0):
        try:
            return int(str(x).strip() or d)
        except Exception:
            return d

