# -*- coding: utf-8 -*-
# [GetAV¹⁸  更新于:2026-10-31 13:23]
import json
import re
import time
import threading
import gzip
import zlib
import urllib.request
import hashlib
import base64
from urllib.parse import quote, unquote

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        def proxy(self, params):
            return [404, "text/plain", ""]
        def localProxy(self, params):
            return [404, "text/plain", ""]

NAME = "GetAV"
HOSTS = [
    "https://getav.net",
    "https://getav.me",
    "https://getav.live",
    "https://getav.co",
    "https://getav.top",
]
NAV_SITE = "https://getav.info/zh/"
STATIC_HOST = "https://static.worldstatic.com"
TG_GROUP = "https://t.me/tvshare23"
BRAND_ACTOR = "🦋 TG群: @tvshare23"
BRAND_DIRECTOR = "🦋 蝴蝶影视"
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
PAGE_SIZE = 20
DEBUG = False
STYLE_VIDEO = {"type": "rect", "ratio": 1.42}
STYLE_OVAL = {"type": "oval", "ratio": 1.0}
STYLE_WIDE = {"type": "rect", "ratio": 1.78}

CATS = [
    ("最新", "api@@latest"),
    ("热门", "api@@hot"),
    ("新片上市", "api@@new-releases"),
    ("无码影片", "api@@uncensored"),
    ("有码影片", "api@@censored"),
    ("字幕影片", "api@@subtitle"),
    ("4K 视频", "api@@4k"),
    ("\U0001F5C2\ufe0f 类型", "folder/genres/_"),
    ("\U0001F483 演员", "folder/stars/_"),
    ("\U0001F3AC 制作商", "folder/studios/_"),
    ("\U0001F522 番号", "folder/codes/_"),
]

SORT_MAP = {
    "popular": ("latest", "最热", "最新"),
    "latest": ("duration", "最新", "时长"),
    "duration": ("popular", "时长", "最热"),
    "rating": ("latest", "评分", "最新"),
}


def format_seconds(secs):
    try:
        s = int(secs)
        h, m, sec = s // 3600, (s % 3600) // 60, s % 60
        return "%02d:%02d:%02d" % (h, m, sec) if h else "%02d:%02d" % (m, sec)
    except Exception:
        return ""


def clean_html_text(raw_html):
    txt = re.sub(r'<[^>]+>', '', raw_html or '')
    import html as html_lib
    txt = html_lib.unescape(txt)
    return re.sub(r'[\r\n\t\s]+', ' ', txt).strip()


def generate_color_card(text, is_ctrl=False):
    palette = [
        ("#4f46e5", "#7c3aed"), ("#2563eb", "#06b6d4"), ("#059669", "#10b981"),
        ("#d97706", "#f59e0b"), ("#dc2626", "#ea580c"), ("#db2777", "#f43f5e"),
        ("#475569", "#334155"), ("#0891b2", "#0284c7"),
    ]
    name_str = (text or "GetAV").strip()
    if is_ctrl:
        c1, c2 = ("#e11d48", "#be123c")
    else:
        h_val = int(hashlib.md5(name_str.encode("utf-8")).hexdigest()[:4], 16)
        c1, c2 = palette[h_val % len(palette)]
    display_title = name_str[:12]
    font_size = "40" if len(display_title) <= 6 else ("32" if len(display_title) <= 9 else "26")
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360">'
        '<defs><linearGradient id="g" x1="0%%" y1="0%%" x2="100%%" y2="100%%">'
        '<stop offset="0%%" stop-color="%s"/><stop offset="100%%" stop-color="%s"/>'
        '</linearGradient></defs>'
        '<rect width="640" height="360" rx="24" fill="url(#g)"/>'
        '<text x="50%%" y="54%%" font-size="%s" font-family="sans-serif" font-weight="bold" '
        'fill="#ffffff" text-anchor="middle" dominant-baseline="middle">%s</text></svg>'
    ) % (c1, c2, font_size, display_title)
    b64_svg = base64.b64encode(svg.encode("utf-8")).decode("utf-8")
    return "data:image/svg+xml;base64,%s" % b64_svg


class Spider(BaseSpider):

    def __init__(self):
        self.hosts = list(HOSTS)
        self.baseHost = self.hosts[0]
        self._host_idx = 0
        self._good_host = None
        self._net_dead = False
        self._live_host_cache = None
        self._cache = {}
        self._cache_time = {}
        self._lock = threading.Lock()
        self.options = {}
        self._seen = {}

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
        self.options = cfg
        custom_host = (cfg.get("host") or cfg.get("siteUrl") or "").strip().rstrip("/")
        if custom_host:
            if custom_host not in self.hosts:
                self.hosts.insert(0, custom_host)
            self.baseHost = custom_host
            self._good_host = custom_host
            return
        cached = self._get_local("getav_live_host")
        if cached and str(cached).startswith("http"):
            if cached not in self.hosts:
                self.hosts.insert(0, cached)
            self.baseHost = cached
            self._good_host = cached

    def destroy(self):
        with self._lock:
            self._cache.clear()
            self._cache_time.clear()
        self.options = {}

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(m3u8|mp4|ts)(\?|$)', str(url)))

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return {"msg": "不支持此操作"}

    def _get_local(self, key):
        local = getattr(self, "local", None)
        if local is not None:
            try:
                return local.get(key)
            except Exception:
                pass
        try:
            if self._live_host_cache is not None:
                return self._live_host_cache
        except Exception:
            pass
        return None

    def _set_local(self, key, value):
        local = getattr(self, "local", None)
        if local is not None:
            try:
                local.set(key, value)
                return
            except Exception:
                pass
        self._live_host_cache = value

    def _update_live_host(self):
        try:
            req = urllib.request.Request(NAV_SITE, headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            })
            with urllib.request.urlopen(req, timeout=6) as resp:
                raw = resp.read()
                enc = (resp.headers.get("Content-Encoding") or "").lower()
                if raw[:2] == b"\x1f\x8b" or enc == "gzip":
                    raw = gzip.decompress(raw)
                html = raw.decode("utf-8", errors="ignore")
            domains = re.findall(r'getav\.(?:net|me|live|co|top|[a-z0-9]+)', html, re.I)
            clean = []
            for d in domains:
                h = ("https://%s" % d.lower()).strip()
                if "info" not in h and h not in clean:
                    clean.append(h)
            if clean:
                for ch in reversed(clean):
                    if ch not in self.hosts:
                        self.hosts.insert(0, ch)
                self.baseHost = self.hosts[0]
                self._host_idx = 0
                self._good_host = self.baseHost
                self._set_local("getav_live_host", self.baseHost)
                return True
        except Exception:
            pass
        return False

    def _api_headers(self):
        host = self.baseHost
        return {
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Referer": host + "/zh",
            "Origin": host,
            "Connection": "keep-alive",
        }

    @staticmethod
    def _resp_dict(resp):
        if isinstance(resp, dict):
            return resp
        if isinstance(resp, str):
            return {"code": 200, "content": resp, "headers": {}, "error": None}
        if isinstance(resp, (bytes, bytearray)):
            return {"code": 200, "content": resp, "headers": {}, "error": None}
        return {"code": 0, "content": "", "headers": {}, "error": str(resp)}

    def _net_json(self, url):
        net = getattr(self, "net", None)
        if net is None or not hasattr(net, "req"):
            return None
        try:
            resp = net.req(url, {"headers": self._api_headers(), "timeout": 15000})
            r = self._resp_dict(resp)
            if r.get("error") or not 200 <= (r.get("code") or 0) < 300:
                self._net_dead = True
                return None
            data = json.loads(r["content"])
            return data if data else None
        except Exception:
            self._net_dead = True
            return None

    def _urllib_json(self, url):
        try:
            req = urllib.request.Request(url, headers=self._api_headers())
            with urllib.request.urlopen(req, timeout=12) as resp:
                raw = resp.read()
                enc = (resp.headers.get("Content-Encoding") or "").lower()
                if raw[:2] == b"\x1f\x8b" or enc == "gzip":
                    raw = gzip.decompress(raw)
                elif enc == "deflate":
                    try:
                        raw = zlib.decompress(raw)
                    except Exception:
                        raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                data = json.loads(raw.decode("utf-8", errors="ignore"))
                return data if data else {}
        except Exception:
            return {}

    def _req_json(self, url):
        if not self._net_dead:
            d = self._net_json(url)
            if d is not None:
                return d
        return self._urllib_json(url)

    def _fetch_api(self, api_path, timeout=12):
        for i in range(len(self.hosts)):
            idx = (self._host_idx + i) % len(self.hosts)
            cur_host = self.hosts[idx]
            url = cur_host + ("/" + str(api_path).lstrip("/"))
            data = self._req_json(url)
            if (data and isinstance(data, dict)
                    and data.get("success") is not False
                    and isinstance(data.get("data"), dict)):
                self._host_idx = idx
                self.baseHost = cur_host
                return data
        if self._update_live_host():
            return self._fetch_api(api_path, timeout)
        return {}

    def homeContent(self, filter):
        classes = [{"type_id": cid, "type_name": cname, "style": STYLE_VIDEO} for cname, cid in CATS]
        filters = {}
        for _, cid in CATS:
            if cid.startswith("api@@"):
                filters[cid] = self._video_filters("popular" if cid == "api@@hot" else "latest")
            elif cid.startswith("folder/"):
                filters[cid] = self._video_filters("latest")
                if cid == "folder/stars/_":
                    filters[cid] = [{
                        "key": "gender", "name": "性别", "value": [
                            {"n": "女优", "v": "2"}, {"n": "男优", "v": "1"}]},
                    ] + filters[cid]
        return {"class": classes, "filters": filters}

    def _video_filters(self, init="latest"):
        return [
            {"key": "sortBy", "name": "排序", "init": init, "value": [
                {"n": "最新", "v": "latest"}, {"n": "最热", "v": "popular"},
                {"n": "评分", "v": "rating"}, {"n": "时长", "v": "duration"}]},
        ]

    def homeVideoContent(self):
        data = self._fetch_api("/api/movies?category=latest&sortBy=latest&limit=%d&page=1&locale=zh" % PAGE_SIZE)
        movies = ((data.get("data") or {}).get("movies")) or []
        v_list = []
        for m in movies:
            v = self._movie_vod(m)
            if v:
                v_list.append(v)
        return {"list": v_list}

    def _movie_vod(self, m):
        cid = str(m.get("id", "")).strip().lower()
        if not cid or cid.isdigit():
            return None
        dur = format_seconds(m.get("videoLength", 0))
        badges = []
        if m.get("localM3u8Path4k") or m.get("is4k"):
            badges.append("4K")
        if m.get("subtitles") or m.get("subtitleLanguages"):
            badges.append("字幕")
        tag = " · ".join(badges + [dur]) if dur else " · ".join(badges)
        return {
            "vod_id": cid,
            "vod_name": m.get("title") or cid.upper(),
            "vod_pic": self._format_poster(m.get("localImg") or m.get("img")),
            "vod_remarks": tag,
        }

    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        extend = extend or {}
        tid = str(tid or "")

        if tid.startswith("folder/"):
            parts = tid.split("/", 2)
            if len(parts) == 3:
                f_type, f_value = parts[1], unquote(parts[2])
                if not f_value or f_value == "_":
                    return self._folder_entries(f_type, pg, extend)
                return self._folder_videos(f_type, f_value, pg, extend)
        if tid.startswith("actor/") or tid.startswith("director/"):
            name = unquote(tid.split("/", 1)[1])
            return self._search_page(name, pg)
        if tid.startswith("tag/"):
            name = unquote(tid.replace("tag/", "", 1))
            return self._search_page(name, pg)

        cat = tid.replace("api@@", "") if tid.startswith("api@@") else "latest"
        default_sort = "popular" if cat == "hot" else "latest"
        sort_by = extend.get("sortBy") or default_sort
        params = ["page=%d" % pg, "limit=%d" % PAGE_SIZE, "locale=zh", "sortBy=%s" % sort_by]
        data = self._fetch_api("/api/movies?category=%s&%s" % (cat, "&".join(params)))
        movies = ((data.get("data") or {}).get("movies")) or []
        v_list = [self._movie_vod(m) for m in movies]
        v_list = [v for v in v_list if v]
        return self._page_out(v_list, pg, len(movies) >= PAGE_SIZE, scope="api@@%s" % cat)

    def _folder_entries(self, f_type, pg, extend):
        extend = extend or {}
        if f_type == "stars":
            gender = extend.get("gender", "2")
            q = "page=%d&limit=24&sort=popular&locale=zh" % pg
            if gender:
                q += "&gender=%s" % gender
            data = self._fetch_api("/api/stars?" + q)
            items = ((data.get("data") or {}).get("stars")) or []
            v_list = []
            for s in items:
                sid = str(s.get("id", "")).strip()
                base_name = s.get("name") or s.get("originalName") or s.get("nameJp") or ""
                if not sid or not base_name:
                    continue
                count = s.get("movieCount") or s.get("movie_count") or ""
                display = "%s (%s部)" % (base_name, count) if count else base_name
                raw_av = s.get("localAvatar") or s.get("avatar") or s.get("localImg") or s.get("img")
                pic = self._format_poster(raw_av) if raw_av else generate_color_card(base_name)
                v_list.append({
                    "vod_id": "folder/stars/%s" % sid,
                    "vod_name": display,
                    "vod_pic": pic,
                    "vod_remarks": "%s部" % count if count else "",
                    "vod_tag": "folder",
                })
            total_pages = self._pg_from(data, pg, len(v_list))
            return self._page_out(v_list, pg, len(v_list) >= 24, pagecount=total_pages, scope="folder/stars/_")

        api_map = {"genres": "/api/genres", "studios": "/api/studios", "codes": "/api/codes"}
        key_map = {"genres": "genres", "studios": "studios", "codes": "codes"}
        id_key = {"genres": "id", "studios": "id", "codes": "id"}
        name_key = {"genres": "name", "studios": "name", "codes": "name"}
        if f_type not in api_map:
            return self._page_out([], pg, False)
        data = self._fetch_api("%s?limit=100&sort=popular&locale=zh-CN" % api_map[f_type])
        if not data:
            return self._page_out([], pg, False)
        items = ((data.get("data") or {}).get(key_map[f_type])) or []
        v_list = []
        for g in items:
            gid = str(g.get(id_key[f_type], "")).strip()
            name = g.get(name_key[f_type]) or g.get("name", "")
            if not gid or not name:
                continue
            count = g.get("movieCount") or g.get("movie_count") or ""
            v_list.append({
                "vod_id": "folder/%s/%s" % (f_type, gid),
                "vod_name": str(name).upper() if f_type == "codes" else str(name),
                "vod_pic": generate_color_card(name),
                "vod_remarks": "%s部" % count if count else "",
                "vod_tag": "folder",
            })
        return self._page_out(v_list, 1, False, pagecount=1, scope="folder/%s/_" % f_type)

    def _folder_videos(self, f_type, f_id, pg, extend):
        pg = self._int(pg, 1)
        extend = extend or {}
        ep_map = {"stars": "stars", "genres": "genres", "studios": "studios", "codes": "codes"}
        ep = ep_map.get(f_type, f_type)
        sort_by = extend.get("sortBy") or "latest"
        params = ["page=%d" % pg, "limit=%d" % PAGE_SIZE, "locale=zh", "sortBy=%s" % sort_by]
        data = self._fetch_api("/api/%s/%s?%s" % (ep, quote(f_id, safe=""), "&".join(params)))
        dd = data.get("data") or {}
        movies = dd.get("movies") or []
        pag = dd.get("pagination") or {}
        v_list = []
        for m in movies:
            v = self._movie_vod(m)
            if v:
                v_list.append(v)
        total_pages = pag.get("totalPages")
        has_more = bool(pag.get("hasMore")) or len(movies) >= PAGE_SIZE
        return self._page_out(v_list, pg, has_more,
                              pagecount=total_pages if total_pages else None,
                              scope="folder/%s/%s" % (f_type, f_id))

    def searchContent(self, key, quick, pg="1"):
        pg = self._int(pg, 1)
        return self._search_page(str(key or "").strip(), pg)

    def _search_page(self, kw, pg):
        if not kw:
            return self._page_out([], pg, False)
        data = self._fetch_api("/api/search?q=%s&limit=%d&page=%d&locale=zh" % (
            quote(kw), PAGE_SIZE, pg))
        movies = ((data.get("data") or {}).get("movies")) or []
        v_list = [v for m in movies if (v := self._movie_vod(m))]
        return self._page_out(v_list, pg, len(movies) >= PAGE_SIZE, scope="search:%s" % kw)

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        results = [self._detail(str(video_id)) for video_id in ids]
        merged = {k: v for k, v in (results[0] or {}).items() if k != "list"}
        merged["list"] = [item for r in results for item in (r.get("list") or [])]
        return merged

    def _detail(self, raw_id):
        if str(raw_id).startswith("subfolder@@"):
            return self._subfolder_content(raw_id, 1)
        code = str(raw_id).strip().lower()
        data = self._fetch_api("/api/movies/%s" % code)
        dd = data.get("data") or {}
        if not dd.get("id"):
            return {"list": [], "msg": "未找到此影片"}
        title = dd.get("title") or code.upper()
        poster = self._format_poster(dd.get("localImg") or dd.get("img"))

        actors_list = dd.get("stars") or []
        actor_names = []
        for a in actors_list:
            nm = clean_html_text(a.get("name", ""))
            if not nm:
                continue
            actor_names.append(self._clickable("actor/%s" % quote(nm, safe=""), nm))
        actor_str = " ".join(actor_names)

        genres_list = dd.get("genres") or []
        genre_names = []
        for g in genres_list:
            gn = clean_html_text(g.get("name", ""))
            if not gn:
                continue
            genre_names.append(self._clickable("tag/%s" % quote(gn, safe=""), gn))
        type_str = " ".join(genre_names)

        dur_str = format_seconds(dd.get("videoLength", 0))
        remarks = dur_str
        director_name = clean_html_text((dd.get("director") or {}).get("name", ""))
        director_str = self._clickable("director/%s" % quote(director_name, safe=""), director_name) if director_name else ""
        producer_name = clean_html_text((dd.get("producer") or {}).get("name", ""))
        publisher_name = clean_html_text((dd.get("publisher") or {}).get("name", ""))
        series_name = clean_html_text((dd.get("series") or {}).get("name", ""))

        content_lines = [
            "番号: %s" % code.upper(),
            "片名: %s" % title,
        ]
        if dur_str:
            content_lines.append("时长: %s" % dur_str)
        if dd.get("date"):
            content_lines.append("发行: %s" % str(dd["date"])[:10])
        if dd.get("rating"):
            content_lines.append("评分: %s" % dd["rating"])
        if director_name:
            content_lines.append("导演: %s" % director_name)
        if publisher_name:
            content_lines.append("片商: %s" % publisher_name)
        if producer_name and producer_name != publisher_name:
            content_lines.append("制作: %s" % producer_name)
        if series_name:
            content_lines.append("系列: %s" % series_name)
        if genre_names:
            content_lines.append("类型: %s" % " / ".join(clean_html_text(g.get("name", "")) for g in genres_list if g.get("name")))
        if actor_names:
            content_lines.append("演员: %s" % " / ".join(clean_html_text(a.get("name", "")) for a in actors_list if a.get("name")))
        stat_parts = []
        if dd.get("views") is not None:
            stat_parts.append("观看 %s" % dd["views"])
        if dd.get("likes") is not None:
            stat_parts.append("点赞 %s" % dd["likes"])
        if dd.get("favorites") is not None:
            stat_parts.append("收藏 %s" % dd["favorites"])
        if stat_parts:
            content_lines.append("数据: %s" % " | ".join(stat_parts))
        sub_langs = [s.get("language") for s in (dd.get("subtitles") or []) if s.get("language")]
        if sub_langs:
            content_lines.append("字幕: %s" % ", ".join(sorted(set(sub_langs))))
        desc = dd.get("description")
        if desc:
            content_lines.append("")
            content_lines.append("简介: %s" % clean_html_text(desc))
        full_content = "\n".join(content_lines)

        play_lines = []
        label_map = {"raw_1080p": "正片 1080P", "raw_720p": "高清 720P",
                     "raw_480p": "标清 480P", "raw_240p": "流畅 240P"}
        for vs in (dd.get("videoSources") or []):
            s_url = vs.get("url", "")
            if s_url:
                play_lines.append("%s$%s" % (label_map.get(vs.get("type", ""), vs.get("type") or "正片"), s_url))
        for k, lab in (("localM3u8Path4k", "超清 4K"), ("localM3u8Path", "高清 1080P"), ("localM3u8PathUc", "无码专线")):
            if dd.get(k):
                play_lines.append("%s$%s" % (lab, dd[k]))
        preview_url = dd.get("previewVideoUrl")
        if preview_url:
            full_pv = STATIC_HOST + preview_url if not preview_url.startswith("http") else preview_url
            play_lines.append("精彩预告$%s" % full_pv)

        play_url_str = "#".join(play_lines) if play_lines else "暂无可用线路$https://dummyimage.com/1x1/000/000.png"

        vod = {
            "vod_id": code,
            "vod_name": title,
            "vod_pic": poster,
            "type_name": type_str,
            "vod_year": str(dd.get("date", ""))[:4],
            "vod_area": "日本",
            "vod_remarks": remarks,
            "vod_actor": actor_str,
            "vod_director": director_str,
            "vod_content": full_content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"),
            "vod_play_from": "官方线路",
            "vod_play_url": play_url_str,
        }
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        url = str(id or "").strip()
        if not url:
            return {"parse": 0, "msg": "无法获取播放地址"}
        return {
            "parse": 0,
            "jx": 0,
            "url": url,
            "header": {"User-Agent": UA, "Referer": self.baseHost + "/"},
        }

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
        raw = self._fetch_img_bytes(url)
        if not raw:
            return [404, "text/plain", ""]
        return [200, self._mime(raw), self._img_stream(raw), {}]

    localProxy = proxy

    def _fetch_img_bytes(self, url):
        net = getattr(self, "net", None)
        if net is not None and not self._net_dead:
            try:
                if hasattr(net, "reqParts"):
                    b = net.reqParts(url, {"buffer": 3})[1]
                else:
                    r = net.req(url, {"buffer": 3})
                    b = r.get("content") if isinstance(r, dict) else r
                if b:
                    return bytes(b)
            except Exception:
                pass
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Referer": self.baseHost + "/",
                "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read()
        except Exception:
            return b""

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

    def _pic_url(self, u):
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

    def _format_poster(self, raw_url):
        if not raw_url:
            return ""
        pic = str(raw_url).strip()
        if pic.startswith("//"):
            pic = "https:" + pic
        elif pic.startswith("/"):
            pic = STATIC_HOST + pic
        return self._pic_url(pic)

    def _mime(self, b):
        if b[:4] == b'\x89PNG':
            return "image/png"
        if b[:4] == b'GIF8':
            return "image/gif"
        if b[8:12] == b'WEBP':
            return "image/webp"
        if b[4:8] == b'ftyp':
            return "image/avif"
        return "image/jpeg"

    @staticmethod
    def _e64(s):
        return base64.urlsafe_b64encode(str(s).encode("utf-8")).decode("utf-8")

    @staticmethod
    def _d64(s):
        s = str(s or "").strip()
        s = unquote(s).replace(" ", "+")
        for dec in (base64.urlsafe_b64decode, base64.b64decode):
            try:
                pad = "=" * (-len(s) % 4)
                return dec(s + pad).decode("utf-8")
            except Exception:
                continue
        return ""

    @staticmethod
    def _int(x, d=0):
        try:
            return int(x)
        except Exception:
            return d

    def _fix_url(self, u):
        if not u:
            return ""
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("/"):
            return self.baseHost.rstrip("/") + u
        return u

    def _pg_from(self, data, pg, fallback_has_more):
        try:
            total_pages = (data.get("data") or {}).get("pagination", {}).get("totalPages")
            if total_pages and int(total_pages) > 0:
                return int(total_pages)
        except Exception:
            pass
        return pg + 1 if fallback_has_more else pg

    def _page_out(self, v_list, pg, has_more, pagecount=None, scope=None):
        pg = max(1, self._int(pg, 1))
        if scope:
            st = self._seen.setdefault(scope, {"pg": 0, "ids": set()})
            if pg <= st["pg"]:
                st["ids"] = set()
            st["pg"] = pg
            out = []
            for v in v_list:
                vid = v.get("vod_id", "")
                if vid and vid in st["ids"]:
                    continue
                if vid:
                    st["ids"].add(vid)
                out.append(v)
            v_list = out
        if pagecount is None:
            pagecount = pg + 1 if has_more else pg
        return {
            "page": pg,
            "pagecount": pagecount,
            "limit": len(v_list),
            "total": 999999,
            "list": v_list,
        }

    def _clickable(self, ident, name):
        payload = json.dumps(
            {"id": ident, "name": name, "type_flag": "0"},
            ensure_ascii=False, separators=(",", ":"))
        return "[a=cr:%s/]%s[/a]" % (payload, name)

