# -*- coding: utf-8 -*-
"""
SUPJAV (supjav.pics) — FongMi Type3 Python Spider
站点: WordPress REST API 型越南 JAV 站
协议依据: FongMi/TV@fongmi 分支源码 (chaquo/base/spider.py, app.py, bean/*.java)

关键逆向结论 (2026-10-28):
- 主域名 supjav.com 被 CF managed challenge 整站 403; 真实活动域名是 supjav.pics (WP 站, 免 CF)
- 全站走 WP REST API: /wp-json/wp/v2/{categories,posts,actor} + 自定义播放端点 /wp-json/fb/v1/player/
- 播放: /wp-json/fb/v1/player/?id=<post_id> -> {"success":true,"data":"<ArtPlayer HTML>"} 内 url:'...m3u8'
- 视频是 PNG 图片序列 m3u8 (948 帧, VOD, 无加密, byteimg CDN) —— FongMi 可直接播 (parse=0)
- 封面为 .avif; FongMi Glide 5.0.9 带 glide-avif-integration, 原生支持
- 演员是 WP 自定义分类法 (taxonomy=actor), 有 term id; 点击走 posts?actor=<id> (比搜索可靠)

自测: python3 /var/minis/skills/Quss/scripts/test_spider.py "[Aure]SUPJAV.py"
"""
import sys
import json
import re
import time
import threading
from urllib.parse import quote, unquote

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
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

NAME = "SUPJAV"
HOST = "https://supjav.pics"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
PAGE_SIZE = 30
CACHE_TTL = 120
DEBUG = False

# 封面样式: 横版 (WP 卡片是 300x225 = 4:3)
STYLE = {"type": "rect", "ratio": 1.33}

# 分类缓存 key
_CLS_KEY = "__cls"

# ---- v2.0 迁移: requests.Session -> self.net 兼容适配器 (内联) ----
class _NetResp(object):
    """模拟 requests.Response: 基于 self.net.req 或 urllib 返回的 dict。"""
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
    """requests.Session 兼容层: 优先宿主注入 self.net, 无则 urllib 直连(标准库, 任何播放器可跑)。"""
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
        self.host = HOST
        self.name = NAME
        self.session = None
        self._cache = {}
        self._cache_time = {}
        self._lock = threading.Lock()
        self.options = {}

    def init(self, extend=""):
        self.session = _NetSession(getattr(self, 'net', None))
        self.session.headers.update({
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
        })
        # 不要在这里发网络请求 (见模板注释); 全部按需延迟到 _api
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
        if site and site.startswith("http"):
            self.host = site
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

    # ================= 首页 =================
    def homeContent(self, filter):
        classes = self._classes()
        result = {"class": classes}
        if filter:
            result["filters"] = {}
        items, _ = self._posts({}, 1)
        result["list"] = [self._vod(x) for x in items]
        return result

    def homeVideoContent(self):
        return {"list": []}

    # ================= 分类 =================
    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        extend = extend or {}

        # 演员点击: tid = "actor/<term_id>" (FongMi 把 [a=cr] 的 id 原样传回)
        if tid.startswith("actor/"):
            actor_id = tid.split("/", 1)[1]
            items, totalpages = self._posts({"actor": actor_id}, pg)
            return self._page_result(items, pg, totalpages)

        # 普通分类: tid = category id
        items, totalpages = self._posts({"categories": tid}, pg)
        return self._page_result(items, pg, totalpages)

    # ================= 详情 =================

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        responses = [self._detail(str(video_id)) for video_id in ids]
        merged = {k: v for k, v in (responses[0] or {}).items() if k != "list"} if responses[0] else {}
        merged["list"] = [item for response in responses if response for item in (response.get("list") or [])]
        return merged
    def _detail(self, vid):
        vid = str(vid or "")
        post = self._post_detail(vid)
        if not post:
            return {"list": [], "msg": "未找到此影片"}

        title = self._clean(self._html_text(post.get("title", {}).get("rendered", "")))
        content = self._clean(self._html_text(post.get("content", {}).get("rendered", "")))

        # 演员 / 分类 (从 _embed 的 wp:term 提取)
        actors = []
        categories = []
        cat_ids = set(post.get("categories") or [])
        for group in (post.get("_embedded", {}).get("wp:term") or []):
            for t in group:
                if t.get("taxonomy") == "actor" and t.get("count", 1) > 0:
                    actors.append(t)
                elif t.get("taxonomy") == "category":
                    categories.append(t)

        actor_text = "、".join(self._clickable("actor", t.get("id"), t.get("name"))
                               for t in actors if t.get("id"))
        type_name = categories[0].get("name", "") if categories else ""

        # Cen/Uncen 标识: Jav Không Che (id=6) 为无码
        remarks = "Uncen" if 6 in cat_ids else "Cen"

        vod_pic = self._cover(post, "full")
        vod_year = (post.get("date") or "")[:4]

        vod = {
            "vod_id": str(post.get("id") or vid),
            "vod_name": title or vid,
            "vod_pic": vod_pic,
            "type_name": type_name,
            "vod_year": vod_year,
            "vod_area": "JAV",
            "vod_remarks": remarks,
            "vod_actor": actor_text,
            "vod_content": content,
            # 单集: 播放引用 = post id, playerContent 据此取流
            "vod_play_from": "SUPJAV",
            "vod_play_url": "正片$" + str(post.get("id") or vid),
        }
        return {"list": [vod]}

    # ================= 搜索 =================
    def searchContent(self, key, quick, pg="1"):
        pg = self._int(pg, 1)
        kw = str(key or "").strip()
        items, totalpages = self._posts({"search": kw}, pg)
        return self._page_result(items, pg, totalpages)

    # ================= 播放 =================
    def playerContent(self, flag, id, vipFlags):
        pid = str(id or "").strip()
        if not pid:
            return {"parse": 0, "msg": "无法获取播放地址"}
        m3u8 = self._fetch_play(pid)
        if not m3u8:
            return {"parse": 0, "msg": "无法获取播放地址"}
        return {
            "parse": 0,
            "jx": 0,
            "url": m3u8,
            "header": {"User-Agent": UA},
        }

    def liveContent(self, url):
        return "[]"

    # ================= 内部: REST API =================
    def _api(self, path, params=None):
        """GET WP REST JSON, 返回 (obj, totalpages). 失败返回 ({}, 0)."""
        path = "/" + str(path).lstrip("/")
        ck = path + json.dumps(params or {}, sort_keys=True)
        with self._lock:
            hit = self._cache.get(ck)
            if hit and time.time() - self._cache_time.get(ck, 0) < CACHE_TTL:
                return hit

        url = self.host.rstrip("/") + path
        try:
            r = self.session.get(url, params=params or {}, timeout=15)
            r.raise_for_status()
            obj = r.json()
            tp = 0
            try:
                tp = int(r.headers.get("X-WP-TotalPages", "0") or 0)
            except Exception:
                tp = 0
            if DEBUG:
                print("[SUPJAV DEBUG] %s -> %d bytes, totalpages=%s" % (r.url, len(r.text), tp))
            result = (obj, tp)
            with self._lock:
                self._cache[ck] = result
                self._cache_time[ck] = time.time()
            return result
        except Exception:
            if DEBUG:
                print("[SUPJAV DEBUG] FAIL %s?%s" % (url, params))
            return ({}, 0)

    def _classes(self):
        hit = self._cache.get(_CLS_KEY)
        if hit and time.time() - self._cache_time.get(_CLS_KEY, 0) < CACHE_TTL:
            return hit[0]
        cats, _ = self._api("/wp-json/wp/v2/categories", {"per_page": 100})
        arr = []
        if isinstance(cats, list):
            # 按视频数降序; 跳过 count=0 的垃圾分类
            for c in cats:
                try:
                    cnt = int(c.get("count", 0) or 0)
                except Exception:
                    cnt = 0
                if cnt <= 0:
                    continue
                tid = str(c.get("id") or "")
                nm = c.get("name") or tid
                if tid:
                    arr.append({"type_id": tid, "type_name": nm, "style": STYLE, "_cnt": cnt})
            arr.sort(key=lambda x: -x.get("_cnt", 0))
        if not arr:
            arr = [{"type_id": "4", "type_name": "Jav Online", "style": STYLE}]
        for x in arr:
            x.pop("_cnt", None)
        with self._lock:
            self._cache[_CLS_KEY] = (arr, time.time())
        return arr

    def _posts(self, params, pg):
        """GET posts 列表, 返回 (items, totalpages)."""
        q = {"per_page": PAGE_SIZE, "page": pg, "_embed": "true"}
        for k, v in (params or {}).items():
            if v not in (None, "", "0"):
                q[k] = v
        obj, tp = self._api("/wp-json/wp/v2/posts", q)
        if not isinstance(obj, list):
            return [], 0
        return obj, tp

    def _post_detail(self, vid):
        """GET 单篇 post 详情 (含 _embed)."""
        vid = vid.strip()
        if not vid:
            return {}
        obj, _ = self._api("/wp-json/wp/v2/posts/" + quote(vid, safe=""), {"_embed": "true"})
        return obj if isinstance(obj, dict) else {}

    def _fetch_play(self, pid):
        """取 m3u8 直链: 播放端点返回 ArtPlayer HTML, 内嵌 url:'...m3u8'."""
        obj, _ = self._api("/wp-json/fb/v1/player/", {"id": pid})
        if not isinstance(obj, dict) or not obj.get("success"):
            return ""
        data = obj.get("data") or ""
        # data 是 HTML 字符串; 提取 url:'...m3u8' (json.loads 已还原转义)
        m = re.search(r"url\s*:\s*['\"]([^'\"]+\.m3u8[^'\"]*)['\"]", data)
        if m:
            return m.group(1).strip()
        # 兜底: 任意 m3u8 URL
        m = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', data)
        return m.group(1).strip() if m else ""

    # ================= 内部: 映射 =================
    def _vod(self, post):
        post = post or {}
        pid = str(post.get("id") or "")
        title = self._clean(self._html_text(post.get("title", {}).get("rendered", "")))
        cat_ids = set(post.get("categories") or [])
        remarks = "Uncen" if 6 in cat_ids else "Cen"
        return {
            "vod_id": pid,
            "vod_name": title or pid,
            "vod_pic": self._cover(post, "thumb"),
            "vod_remarks": remarks,
        }

    def _cover(self, post, size="thumb"):
        """从 _embedded.wp:featuredmedia 取封面 URL."""
        em = post.get("_embedded", {})
        for fm in em.get("wp:featuredmedia") or []:
            if not isinstance(fm, dict):
                continue
            if size == "thumb":
                sizes = (fm.get("media_details") or {}).get("sizes") or {}
                for sname in ("video-thumb", "video-small", "full"):
                    s = sizes.get(sname) or {}
                    if s.get("source_url"):
                        return s["source_url"]
            u = fm.get("source_url")
            if u:
                return u
        return ""

    def _page_result(self, items, pg, totalpages):
        page = max(1, self._int(pg, 1))
        if not totalpages or totalpages < 1:
            # 无翻页头时: 有数据给大数, 空给当前页
            totalpages = page if not items else 9999
        return {
            "list": [self._vod(x) for x in items],
            "page": page,
            "pagecount": totalpages,
            "limit": PAGE_SIZE,
            "total": 999999,
        }

    def _clickable(self, kind, ident, name):
        """官方格式 [a=cr:{"id":"...","name":"...","type_flag":"0"}/]name[/a]"""
        if not ident:
            return ""
        payload = json.dumps(
            {"id": "%s/%s" % (kind, ident), "name": name, "type_flag": "0"},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return "[a=cr:%s/]%s[/a]" % (payload, name)

    @staticmethod
    def _html_text(html):
        if not html:
            return ""
        return re.sub(r"<[^>]+>", " ", html)

    @staticmethod
    def _clean(text):
        return re.sub(r"\s+", " ", str(text or "")).strip()

    @staticmethod
    def _int(x, d=0):
        try:
            return int(x)
        except Exception:
            return d
