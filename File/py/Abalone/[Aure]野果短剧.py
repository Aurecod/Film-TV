# -*- coding: utf-8 -*-
# [野果短剧¹⁸  更新于:2026-10-31 13:23]
import json
import re
import base64
import time
import threading
import gzip
import zlib
import urllib.request
from urllib.parse import quote, unquote

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        def proxy(self, params):
            return [404, "text/plain", ""]

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad
    HAS_CRYPTO = True
except Exception:
    HAS_CRYPTO = False

NAME = "野果短剧"
SITE_URL = "https://www.yeguodj.com"
API_BASE = "https://www.yeguodj.com/api.php"
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
PAGE_SIZE = 24

API_KEY = b"2acf7e91e9864673"
API_IV = b"1c29882d3ddfcfd6"
MEDIA_KEY = b"f5d965df75336270"
MEDIA_IV = b"97b60394abc2fbe1"

THEMES = [(7, "野果原创"), (8, "真人短剧"), (9, "魔改漫剧"), (10, "网红改编"), (11, "PMV裸舞")]
SETTINGS = [(23, "禁忌伦理"), (24, "职场反差"), (25, "改造调教"), (26, "出轨绿帽"),
            (27, "高H剧情"), (28, "后宫多人"), (29, "逆袭系统")]
BACKGROUNDS = [(39, "校园"), (40, "都市"), (41, "年代"), (43, "古代"),
               (44, "玄幻"), (45, "末世"), (46, "灵异")]
TIMES = [(1, "7天内"), (2, "14天内"), (3, "30天内"), (4, "90天内")]
RECOMMENDS = [(1, "最新"), (2, "最热")]
FOLDER_GROUPS = {"theme": THEMES, "setting": SETTINGS, "background": BACKGROUNDS}


class Spider(BaseSpider):

    def __init__(self):
        self.siteName = NAME
        self.siteUrl = SITE_URL
        self._cache = {}
        self._cache_time = {}
        self._seen = {}
        self._lock = threading.Lock()
        self.options = {}

    def init(self, extend=""):
        if isinstance(extend, dict):
            self.options = extend
        elif extend:
            try:
                self.options = json.loads(extend)
            except Exception:
                self.options = {}
        return True

    def getDependence(self):
        return []

    def destroy(self):
        with self._lock:
            self._cache.clear()
            self._cache_time.clear()
            self._seen.clear()
        self.options = {}

    def isVideoFormat(self, url):
        low = (url or "").lower()
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".mkv", ".ts"))

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return {"msg": "ok"}

    def liveContent(self, url=""):
        return "[]"


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

    def _e64(self, s):
        return base64.urlsafe_b64encode(str(s).encode("utf-8")).decode("utf-8")

    def _d64(self, s):
        s = unquote(str(s or "")).replace(" ", "+")
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
            return SITE_URL + u
        return u

    def _pic_url(self, u):
        u = self._fix(u)
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

    def _download_img(self, url):
        net = getattr(self, "net", None)
        if net is not None:
            if hasattr(net, "reqParts"):
                try:
                    parts = net.reqParts(url, {"headers": {}, "buffer": 3})
                    return parts[1]
                except Exception:
                    pass
            try:
                r = net.req(url, {"headers": {}, "buffer": 3})
                if isinstance(r, dict):
                    return r.get("content", b"")
                return r
            except Exception:
                pass
        try:
            return urllib.request.urlopen(url, timeout=20).read()
        except Exception:
            return b""

    def _trim(self, b):
        if b[:2] == b"\xff\xd8":
            i = b.rfind(b"\xff\xd9")
            return b[:i + 2] if i > 0 else b
        if b[:4] == b"\x89PNG":
            i = b.rfind(b"IEND")
            return b[:i + 8] if i > 0 else b
        return b

    def _pic_decrypt(self, raw):
        if raw[:2] == b"\xff\xd8" or raw[:4] == b"\x89PNG" or raw[8:12] == b"WEBP" or raw[:4] == b"GIF8":
            return raw
        n = len(raw) - (len(raw) % 16)
        if n <= 0:
            return raw
        try:
            dec = unpad(AES.new(MEDIA_KEY, AES.MODE_CBC, MEDIA_IV).decrypt(raw[:n]), 16)
            return dec
        except Exception:
            pass
        try:
            return self._trim(AES.new(MEDIA_KEY, AES.MODE_CBC, MEDIA_IV).decrypt(raw[:n]))
        except Exception:
            return raw

    def _mime(self, b):
        if b[:4] == b"\x89PNG":
            return "image/png"
        if b[:4] == b"GIF8":
            return "image/gif"
        if b[8:12] == b"WEBP":
            return "image/webp"
        return "image/jpeg"

    def proxy(self, params):
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except Exception:
                params = {}
        params = params or {}
        if params.get("type") != "pic":
            return [404, "text/plain", ""]
        url = self._d64(params.get("url", ""))
        if not url:
            return [404, "text/plain", ""]
        raw = self._download_img(url)
        if not raw:
            return [404, "text/plain", ""]
        img = self._pic_decrypt(raw)
        return [200, self._mime(img), self._img_stream(img), {}]

    localProxy = proxy

    def _req(self, url, **kw):
        net = getattr(self, "net", None)
        if net is not None:
            try:
                opts = {"timeout": kw.get("timeout", 15000)}
                for k in ("headers", "method", "postType", "data", "buffer"):
                    if k in kw and kw[k] is not None:
                        opts[k] = kw[k]
                resp = net.req(url, opts)
                return resp or {}
            except Exception:
                return {}
        return self._req_urllib(url, **kw)

    def _req_urllib(self, url, **kw):
        try:
            data = None
            method = (kw.get("method") or "GET").upper()
            if method == "POST":
                body = kw.get("data") or {}
                data = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={
                "User-Agent": UA,
                "Referer": SITE_URL + "/",
                "Content-Type": "application/json",
                "Accept": "application/json, text/plain, */*",
                "Accept-Encoding": "gzip, deflate",
            }, method=method)
            with urllib.request.urlopen(req, timeout=(kw.get("timeout") or 15000) / 1000.0) as resp:
                raw = resp.read()
                enc = (resp.headers.get("Content-Encoding") or "").lower()
                if enc == "gzip":
                    raw = gzip.decompress(raw)
                elif enc == "deflate":
                    raw = zlib.decompress(raw)
                return {"code": resp.getcode() or 0, "content": raw.decode("utf-8", "replace"),
                        "headers": dict(resp.headers), "error": None}
        except Exception as e:
            return {"code": 0, "content": "", "headers": {}, "error": str(e)}

    def _api(self, path, body=None):
        url = API_BASE + path
        resp = self._req(url, method="POST", postType="json", data=body or {}, timeout=15000)
        if not resp or resp.get("error"):
            return {}
        if not 200 <= (resp.get("code") or 0) < 300:
            return {}
        try:
            obj = json.loads(resp.get("content", ""))
        except Exception:
            return {}
        return self._decrypt(obj)

    def _decrypt(self, obj):
        data = obj.get("data")
        if isinstance(data, str) and data:
            try:
                ct = base64.b64decode(data.replace(" ", "+"))
                pt = unpad(AES.new(API_KEY, AES.MODE_CBC, API_IV).decrypt(ct), 16)
                obj["data"] = json.loads(pt.decode("utf-8"))
            except Exception:
                pass
        return obj

    def _unwrap(self, d):
        if not isinstance(d, dict):
            return {}
        x = d.get("data") if d.get("data") is not None else d
        if isinstance(x, dict) and x.get("data") is not None and isinstance(x.get("data"), dict):
            return x.get("data")
        return x

    def homeContent(self, filter):
        classes = self._classes()
        result = {"class": classes}
        if filter:
            result["filters"] = self._filters(classes)
        return result

    def homeVideoContent(self):
        d = self._api("/api/home/homePage", {})
        inner = self._unwrap(d)
        combined = []
        if isinstance(inner, dict):
            combined.extend(inner.get("top_list") or [])
            mods = (inner.get("modules") or {}).get("list") or []
            for m in mods:
                items = m.get("items") or []
                if isinstance(items, list):
                    combined.extend(items)
        items = self._dedup("home", 1, combined)
        return {"list": [self._to_vod(x) for x in items][:30]}

    def _classes(self):
        return [
            {"type_id": "explore", "type_name": "发现"},
            {"type_id": "rank", "type_name": "排行榜"},
            {"type_id": "folder/theme/_", "type_name": "\U0001F3AD 主题"},
            {"type_id": "folder/setting/_", "type_name": "\u2699\ufe0f 设定"},
            {"type_id": "folder/background/_", "type_name": "\U0001F5BC\ufe0f 背景"},
        ]

    def _filters(self, classes):
        recommend_filter = {
            "key": "recommend", "name": "推荐", "init": "",
            "value": [{"n": "全部", "v": ""}] + [{"n": nm, "v": str(v)} for v, nm in RECOMMENDS],
        }
        time_filter = {
            "key": "time", "name": "时间", "init": "",
            "value": [{"n": "全部", "v": ""}] + [{"n": nm, "v": str(v)} for v, nm in TIMES],
        }
        return {"explore": [recommend_filter, time_filter]}

    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        extend = extend or {}
        if not isinstance(extend, dict):
            extend = {}

        if tid.startswith("actor/") or tid.startswith("director/") or tid.startswith("tag/"):
            name = unquote(tid.split("/", 1)[1])
            items = self._fetch_search(name, pg)
            return self._page(items, pg)

        if tid.startswith("folder/"):
            parts = tid.split("/", 2)
            if len(parts) == 3:
                f_type, f_value = parts[1], unquote(parts[2])
                if not f_value or f_value == "_":
                    cards = self._folder_entries(f_type)
                    return {"list": cards, "page": pg, "pagecount": pg if len(cards) < PAGE_SIZE else 9999,
                            "limit": PAGE_SIZE, "total": len(cards)}
                items = self._explore(f_type, f_value, pg, extend)
                return self._page(items, pg)

        if tid == "rank":
            items = self._rank(pg)
        else:
            items = self._explore(None, None, pg, extend)
        return self._page(items, pg)

    def _folder_entries(self, f_type):
        groups = FOLDER_GROUPS.get(f_type) or []
        cards = []
        for value, name in groups:
            cards.append({
                "vod_id": "folder/%s/%s" % (f_type, value),
                "vod_name": name,
                "vod_pic": "",
                "vod_remarks": "",
                "vod_tag": "folder",
            })
        return cards

    def _explore(self, f_type, f_value, pg, extend=None):
        body = {"page": pg, "limit": PAGE_SIZE}
        if f_type and f_value is not None and f_value != "":
            body[f_type] = self._int(f_value)
        if extend:
            t = extend.get("time")
            if t not in (None, "", "0"):
                body["time"] = self._int(t)
            r = extend.get("recommend")
            if r not in (None, "", "0"):
                body["recommend"] = self._int(r)
        d = self._api("/api/theater/exploreList", body)
        inner = self._unwrap(d)
        items = inner.get("list") if isinstance(inner, dict) else []
        scope = "explore:%s" % (f_type or "all")
        return self._dedup(scope, pg, items or [])

    def _rank(self, pg):
        d = self._api("/api/theater/videoRank", {"page": pg, "limit": PAGE_SIZE})
        inner = self._unwrap(d)
        items = inner.get("list") if isinstance(inner, dict) else []
        return self._dedup("rank", pg, items or [])

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        responses = [self._detail(str(video_id)) for video_id in ids]
        merged = {k: v for k, v in (responses[0] or {}).items() if k != "list"}
        merged["list"] = [item for response in responses for item in (response.get("list") or [])]
        return merged

    def _detail(self, vid):
        d = self._api("/api/playlet/detail", {"video_id": self._int(vid)})
        info = self._unwrap(d)
        if isinstance(info, dict) and info.get("video_id") is None and isinstance(info.get("data"), dict):
            info = info.get("data")
        if not isinstance(info, dict) or not info.get("title"):
            return {"list": [], "msg": "未找到此影片"}

        title = str(info.get("title") or vid).strip()
        raw_pic = str(info.get("cover") or info.get("cover_img") or "").strip()
        raw_desc = re.sub(r"<[^>]+>", "", str(info.get("description") or info.get("intro") or "")).strip()

        eps = info.get("episodes") if isinstance(info.get("episodes"), list) else []
        play_urls = []
        if eps:
            for idx, ep in enumerate(eps):
                n = str(ep.get("sort") or ep.get("episode") or (idx + 1)).strip()
                t_name = str(ep.get("title") or ("第%s集" % n)).strip()
                t_name = self._safe_label(t_name)
                play_urls.append("%s$%s:%s" % (t_name, vid, n))
        else:
            total_cnt = self._int(info.get("episode_count") or info.get("total_serial") or 1)
            for i in range(1, total_cnt + 1):
                play_urls.append("第%s集$%s:%s" % (i, vid, i))
        if not play_urls:
            return {"list": [], "msg": "无播放地址"}

        tags = self._tags_of(info)
        actors = self._actors_of(info)
        tag_str = "、".join(tags[:4])
        remark = "全%s集" % len(play_urls)
        if tag_str:
            remark = "%s | %s" % (remark, tag_str)
        actor_bb = "、".join(self._clickable("actor", a) for a in actors)
        tag_bb = "、".join(self._clickable("tag", t) for t in tags[:6])
        actor_meta = actor_bb + ("、" + tag_bb if tag_bb else "") if actor_bb else tag_bb

        vod = {
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": self._pic_url(raw_pic),
            "vod_actor": actor_meta,
            "vod_director": "",
            "vod_remarks": remark,
            "vod_content": raw_desc,
            "vod_play_from": "正片",
            "vod_play_url": "#".join(play_urls),
        }
        return {"list": [vod]}

    def searchContent(self, key, quick, pg="1"):
        pg = self._int(pg, 1)
        kw = str(key or "").strip()
        if not kw:
            return {"page": 1, "pagecount": 1, "limit": 0, "total": 0, "list": []}
        items = self._fetch_search(kw, pg)
        return self._page(items, pg)

    def _fetch_search(self, key, pg):
        d = self._api("/api/search/result", {"keyword": key, "page": pg})
        inner = self._unwrap(d)
        items = inner.get("list") if isinstance(inner, dict) else []
        return self._dedup("search:%s" % key, pg, items or [])

    def playerContent(self, flag, id, vipFlags):
        raw = str(id or "").strip()
        parts = raw.split(":")
        vid = parts[0]
        ep = parts[1] if len(parts) > 1 else "1"
        url = self._fetch_play(vid, ep)
        if not url:
            return {"parse": 0, "msg": "无法获取播放地址"}
        return {
            "parse": 0,
            "jx": 0,
            "url": url,
            "header": {"User-Agent": UA, "Referer": SITE_URL + "/"},
        }

    def _fetch_play(self, vid, ep):
        d = self._api("/api/playlet/play", {"video_id": self._int(vid), "ep": self._int(ep)})
        info = self._unwrap(d)
        if not isinstance(info, dict):
            return ""
        eps_all = info.get("episodeAll")
        if isinstance(eps_all, list) and eps_all:
            for e in eps_all:
                if str(e.get("sort")) == str(ep) or str(e.get("index")) == str(ep):
                    u = str(e.get("video_url") or "").strip()
                    if u:
                        return u
            try:
                i = self._int(ep) - 1
                if 0 <= i < len(eps_all):
                    u = str(eps_all[i].get("video_url") or "").strip()
                    if u:
                        return u
            except Exception:
                pass
        return str(info.get("video_url") or "").strip()

    def _to_vod(self, it):
        if not it:
            return None
        vid = str(it.get("video_id") if it.get("video_id") is not None else (it.get("id") or "")).strip()
        if not vid:
            return None
        title = str(it.get("title") or it.get("video_title") or it.get("name") or vid).strip()
        raw_pic = str(it.get("cover") or it.get("cover_img") or it.get("pic") or "").strip()
        label = ""
        app_badge = it.get("app_badge")
        if isinstance(app_badge, dict):
            label = str(app_badge.get("text") or "").strip()
        if not label:
            badge = it.get("badge")
            if isinstance(badge, dict):
                label = str(badge.get("text") or "").strip()
        if not label:
            label = str(it.get("serialize_status_text") or "").strip()
        vod = {
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": self._pic_url(raw_pic),
            "vod_remarks": label,
        }
        intro = str(it.get("intro") or it.get("description") or "").strip()
        if intro:
            vod["vod_content"] = intro
        return vod

    def _page(self, items, pg):
        page = max(1, self._int(pg, 1))
        return {
            "list": [self._to_vod(x) for x in items],
            "page": page,
            "pagecount": page if len(items) < PAGE_SIZE else 9999,
            "limit": PAGE_SIZE,
            "total": 999999,
        }

    def _dedup(self, scope, pg, items):
        with self._lock:
            st = self._seen.get(scope)
            if not st or pg <= st.get("pg", 0):
                st = {"pg": pg, "ids": set()}
                self._seen[scope] = st
            out = []
            for it in items:
                vid = str(it.get("video_id") if it.get("video_id") is not None else (it.get("id") or ""))
                if vid and vid in st["ids"]:
                    continue
                if vid:
                    st["ids"].add(vid)
                out.append(it)
            st["pg"] = pg
            return out

    def _clickable(self, kind, name):
        if not name:
            return ""
        ident = "%s/%s" % (kind, quote(name, safe=""))
        payload = json.dumps({"id": ident, "name": name, "type_flag": "0"},
                             ensure_ascii=False, separators=(",", ":"))
        return "[a=cr:%s/]%s[/a]" % (payload, name)

    def _tags_of(self, it):
        tags = (it or {}).get("tags") or []
        if isinstance(tags, str):
            tags = re.split(r"[,，|/、;；\s]+", tags)
        elif not isinstance(tags, list):
            tags = []
        return [str(t).strip() for t in tags if str(t).strip()]

    def _actors_of(self, it):
        al = (it or {}).get("actor_list") or []
        if isinstance(al, str):
            al = re.split(r"[,，;；\s]+", al)
        elif not isinstance(al, list):
            al = []
        out = []
        for a in al:
            if isinstance(a, dict):
                n = str(a.get("name") or a.get("actor_name") or "").strip()
            else:
                n = str(a).strip()
            if n and n not in out:
                out.append(n)
        return out

    def _safe_label(self, text):
        return str(text or "").replace("$", "\uff04").replace("#", "\uff03").strip()

    def _int(self, x, d=0):
        try:
            return int(x)
        except Exception:
            return d

