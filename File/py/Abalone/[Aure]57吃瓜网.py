# -*- coding: utf-8 -*-
# [57吃瓜网¹⁸  更新于:2026-10-31 13:23]
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
        pass

NAME = "57吃瓜网"
HOSTS = ["https://57duanju.net", "https://57cg4.com", "https://57chigua.co"]
UA = "Mozilla/5.0 (Linux; Android 13; Pixel) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
PAGE_SIZE = 20
CACHE_TTL = 30
DEBUG = False
VOD_ID_PREFIX = "vod/"
STYLE = {"type": "rect", "ratio": 1.78}


class Spider(BaseSpider):

    def __init__(self):
        super().__init__()
        self.hosts = list(HOSTS)
        self.host = self.hosts[0]
        self.name = NAME
        self.headers = {"User-Agent": UA, "Referer": "https://57cg4.com/", "Accept": "*/*"}
        self._cache = {}
        self._cache_time = {}
        self._good_host = None
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

    def liveContent(self, url):
        return "[]"

    def homeContent(self, filter):
        classes = self._classes()
        result = {"class": classes}
        if filter:
            result["filters"] = self._filters(classes)
        result["list"] = [self._vod(x) for x in self._home_items()]
        return result

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        extend = extend or {}
        tid = str(tid).strip("/")

        if tid.startswith("actor/") or tid.startswith("director/"):
            name = unquote(tid.split("/", 1)[1])
            items = self._fetch_search(name, pg)
            return self._page(items, pg)

        if tid.startswith("tag/"):
            name = unquote(tid.replace("tag/", "", 1))
            items = self._fetch_search(name, pg)
            return self._page(items, pg)

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
        merged = {k: v for k, v in (responses[0] or {}).items() if k != "list"} if responses[0] else {}
        merged["list"] = [item for response in responses if response for item in (response.get("list") or [])]
        return merged

    def _detail(self, vid):
        vid = str(vid or "")
        if vid.startswith(VOD_ID_PREFIX):
            vid = vid[len(VOD_ID_PREFIX):]
        data = self._fetch_detail(vid)
        if not data:
            return {"list": [], "msg": "未找到此影片"}

        eps = data.get("episodes") or []
        if eps:
            lines = []
            for i, ep in enumerate(eps, 1):
                title = self._safe_label(ep.get("name") or f"第{i}集")
                url = ep.get("url") or ep.get("play_url") or ""
                if url:
                    lines.append(f"{title}${url}")
            play_url = "#".join(lines)
            play_from = "@AC_Film_TV"
        else:
            url = data.get("url") or data.get("play_url") or vid
            play_url = f"正片${url}"
            play_from = "@AC_Film_TV"

        vod = {
            "vod_id": self._vod_id(vid),
            "vod_name": data.get("name") or vid,
            "vod_pic": self._pic(data),
            "type_name": data.get("category") or "",
            "vod_year": str(data.get("year") or ""),
            "vod_area": data.get("area") or "",
            "vod_remarks": data.get("remarks") or "",
            "vod_director": self._clickable("director", data.get("director") or ""),
            "vod_actor": "、".join(self._clickable("actor", a) for a in data.get("actors") or []),
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
        url = self._fetch_play(str(id or ""))
        if not url:
            return {"parse": 0, "msg": "无法获取播放地址"}
        result = {
            "parse": 0,
            "jx": 0,
            "url": url,
            "header": self._string_map({"User-Agent": UA, "Referer": "https://57cg4.com/"}),
        }
        return result


    def _classes(self):
        return [
            {"type_id": "aichengduanju", "type_name": "成人AI短剧", "style": STYLE},
            {"type_id": "hot", "type_name": "热门精选", "style": STYLE},
            {"type_id": "jrcg", "type_name": "今日吃瓜", "style": STYLE},
            {"type_id": "mrds", "type_name": "每日大赛", "style": STYLE},
            {"type_id": "wanghong", "type_name": "网红黑料", "style": STYLE},
            {"type_id": "video", "type_name": "网黄合集", "style": STYLE},
            {"type_id": "cheating", "type_name": "出轨劈腿", "style": STYLE},
            {"type_id": "live", "type_name": "直播擦边", "style": STYLE},
            {"type_id": "society", "type_name": "社会事件", "style": STYLE},
            {"type_id": "star", "type_name": "明星八卦", "style": STYLE},
            {"type_id": "all", "type_name": "全部", "style": STYLE},
        ]

    def _filters(self, classes):
        sort_filter = {
            "key": "sort", "name": "排序", "init": "",
            "value": [{"n": "最新发布", "v": ""}, {"n": "全站最热", "v": "hot"}, {"n": "飙升热榜", "v": "trending"}],
        }
        return {c["type_id"]: [sort_filter] for c in classes}

    def _home_items(self):
        items = self._fetch_list("aichengduanju", 1, {})
        return items[:12]


    def _extract_json_ld(self, html):
        scripts = re.findall(r'<script\s+type=["\']application/ld\+json["\']>([\s\S]*?)</script>', html)
        results = []
        for s in scripts:
            try:
                results.append(json.loads(s.strip()))
            except Exception:
                pass
        return results

    def _pick_host_for_tid(self, tid):
        if tid in ("aichengduanju", "hot", "all", "search"):
            return self.hosts[0]
        return self.hosts[1]

    def _build_list_url(self, tid, pg, sort_val=""):
        host = self._pick_host_for_tid(tid)
        if tid == "all":
            url = f"{host}/page/{pg}/" if pg > 1 else f"{host}/"
        elif tid == "search":
            return ""
        else:
            url = f"{host}/{tid}/{pg}/" if pg > 1 else f"{host}/{tid}/"
        if sort_val:
            sep = "&" if "?" in url else "?"
            url += f"{sep}sort={sort_val}"
        return url

    def _fetch_html(self, url, referer=""):
        if not url:
            return ""
        headers = dict(self.headers)
        headers["Referer"] = referer or "https://57cg4.com/"
        if getattr(self, "net", None) is not None:
            try:
                resp = self.net.req(url, {"headers": headers, "timeout": 15000})
                if not resp.get("error") and 200 <= (resp.get("code") or 0) < 300:
                    return resp.get("content", "")
            except Exception:
                pass
        try:
            import urllib.request, ssl
            ctx = ssl._create_unverified_context()
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
                raw = r.read()
                enc = r.headers.get("Content-Encoding", "")
                if "gzip" in enc:
                    import gzip
                    raw = gzip.decompress(raw)
                try:
                    return raw.decode("utf-8", "ignore")
                except Exception:
                    return raw.decode("latin-1", "ignore")
        except Exception:
            return ""

    def _parse_list_from_jsonld(self, html):
        vod_list = []
        seen = set()
        for data in self._extract_json_ld(html):
            if isinstance(data, dict) and data.get("@type") == "ItemList":
                for elem in data.get("itemListElement", []):
                    if isinstance(elem, dict) and elem.get("@type") == "ListItem":
                        url = elem.get("url", "")
                        name = elem.get("name", "")
                        m = re.search(r'/events/(\d+)/', url)
                        if m:
                            eid = m.group(1)
                            if eid in seen or len(eid) < 2:
                                continue
                            seen.add(eid)
                            vod_list.append({
                                "id": eid,
                                "name": name,
                                "pic": "",
                                "remarks": "",
                            })
        return vod_list

    def _parse_list_from_html(self, html):
        vod_list = []
        seen = set()
        for m in re.finditer(r'<a[^>]+href=["\'](?:https?://[^/]+)?/events/(\d+)/?["\'][^>]*>([\s\S]*?)</a>', html):
            eid, inner = m.group(1), m.group(2)
            if eid in seen or len(eid) < 2:
                continue
            seen.add(eid)
            m_t = re.search(r'<h[23][^>]*>([\s\S]*?)</h[23]>', inner)
            name = re.sub(r'<[^>]+>', '', m_t.group(1)).strip() if m_t else ""
            if not name:
                raw = re.sub(r'<[^>]+>', ' ', inner).strip()
                name = raw[:40] if raw else f"视频 {eid}"
            pic = ""
            for src in re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', inner):
                if not src.endswith(".svg") and "logo" not in src:
                    pic = src.strip()
                    break
            vod_list.append({"id": eid, "name": name, "pic": self._fix_pic(pic), "remarks": ""})
        return vod_list

    def _fetch_list(self, tid, pg, extend):
        sort_val = extend.get("sort", "") if isinstance(extend, dict) else ""
        url = self._build_list_url(tid, pg, sort_val)
        if not url:
            return []
        html = self._fetch_html(url)
        items = self._parse_list_from_jsonld(html)
        if not items:
            items = self._parse_list_from_html(html)
        return items

    def _fetch_search(self, keyword, pg):
        url = f"https://57duanju.net/search/?q={quote(keyword)}"
        if pg > 1:
            url += f"&page={pg}"
        html = self._fetch_html(url)
        items = self._parse_list_from_html(html)
        return items

    def _fetch_detail(self, vid):
        for host in self.hosts:
            html = self._fetch_html(f"{host}/events/{vid}/")
            if html and len(html) >= 500:
                break
        if not html:
            return None

        title = f"视频 {vid}"
        cover = ""
        desc = ""
        episodes = []
        category = ""
        year = ""
        area = ""
        remarks = ""
        director = ""
        actors = []

        for data in self._extract_json_ld(html):
            if not isinstance(data, dict):
                continue
            dtype = data.get("@type", "")

            videos = data.get("video", [])
            if not videos and dtype == "VideoObject":
                videos = [data]
            elif not isinstance(videos, list):
                videos = [videos]

            for v in videos:
                if not isinstance(v, dict):
                    continue
                stream_url = ""
                m_hls = re.search(r'data-hls-src=["\']([^"\']+\.m3u8[^"\']*)["\']', html)
                if m_hls:
                    stream_url = m_hls.group(1).strip()
                else:
                    stream_url = v.get("contentUrl", "").strip()
                if stream_url:
                    ep_name = self._safe_label(v.get("name") or f"第 {len(episodes) + 1} 集")
                    episodes.append({"name": ep_name, "url": stream_url})
                if not cover:
                    cover = v.get("thumbnailUrl", "") or ""
                if not desc:
                    desc = v.get("description", "") or ""

            if dtype in ("NewsArticle", "Article", "VideoObject"):
                h = data.get("headline") or data.get("name")
                if h:
                    title = h
            if "articleSection" in data:
                category = data.get("articleSection", "")
            author = data.get("author", {})
            if isinstance(author, dict):
                director = author.get("name", "")
            elif isinstance(author, list) and author:
                director = author[0].get("name", "") if isinstance(author[0], dict) else ""

        if not episodes:
            for attr in re.findall(r'<video([^>]+)>', html):
                m_hls = re.search(r'data-hls-src=["\']([^"\']+)["\']', attr)
                m_src = re.search(r'src=["\']([^"\']+)["\']', attr)
                stream_url = m_hls.group(1).strip() if m_hls else (m_src.group(1).strip() if m_src else "")
                if not cover:
                    m_post = re.search(r'poster=["\']([^"\']+)["\']', attr)
                    if m_post:
                        cover = m_post.group(1).strip()
                if stream_url:
                    ep_name = self._safe_label(f"片段 {len(episodes) + 1:02d}")
                    episodes.append({"name": ep_name, "url": stream_url})

        if not episodes:
            seen = set()
            for m_url in re.findall(r'["\'](https?://[^"\'\s]+\.(?:m3u8|mp4)[^"\'\s]*)["\']', html):
                if m_url in seen:
                    continue
                seen.add(m_url)
                ep_name = self._safe_label(f"播放 {len(episodes) + 1:02d}")
                episodes.append({"name": ep_name, "url": m_url})

        if not cover:
            m = re.search(r'<meta property=["\']og:image["\'] content=["\']([^"\']+)["\']', html)
            if m:
                cover = m.group(1).strip()

        if not desc:
            m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)["\']', html)
            if m:
                desc = m.group(1).strip()

        for m in re.finditer(r'<a[^>]+href=["\']https?://[^/]+\.com/tags/([^/]+)/["\']', html):
            tag = unquote(m.group(1))
            if tag and tag not in actors:
                actors.append(tag)

        return {
            "name": title,
            "pic": self._fix_pic(cover),
            "episodes": episodes,
            "category": category,
            "year": year,
            "area": area,
            "remarks": remarks,
            "director": director,
            "actors": actors,
            "description": desc,
        }

    def _fetch_play(self, play_id):
        return play_id


    def _safe_label(self, text):
        return str(text or "").replace("$", "＄").replace("#", "＃").strip()

    def _vod_id(self, site_id):
        return f"{VOD_ID_PREFIX}{site_id}" if VOD_ID_PREFIX else str(site_id)

    def _clickable(self, kind, name):
        if not name:
            return ""
        ident = f"{kind}/{quote(name, safe='')}"
        payload = json.dumps({"id": ident, "name": name, "type_flag": "0"}, ensure_ascii=False, separators=(",", ":"))
        return f"[a=cr:{payload}/]{name}[/a]"

    def _fix_pic(self, url):
        if not url:
            return ""
        if url.startswith("//"):
            url = "https:" + url
        elif url.startswith("/"):
            url = "https://57duanju.net" + url
        if "s.chigua.media" in url and "@" not in url:
            return f"{url}@Referer=https://57cg4.com/@User-Agent={quote(UA)}"
        return url

    def _pic(self, item):
        for k in ("pic", "img", "cover", "thumb", "vod_pic"):
            v = item.get(k)
            if v:
                return v
        return ""

    def _vod(self, item):
        item = item or {}
        vid = str(item.get("id") or item.get("vod_id") or "")
        return {
            "vod_id": self._vod_id(vid),
            "vod_name": item.get("name") or item.get("title") or vid,
            "vod_pic": self._fix_pic(item.get("pic", "")),
            "vod_remarks": item.get("remarks") or "",
        }

    def _list(self, data):
        if isinstance(data, list):
            return data
        if not isinstance(data, dict):
            return []
        for k in ("list", "items", "records", "data"):
            v = data.get(k)
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                return self._list(v)
        return []

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

    def _page(self, items, pg):
        try:
            page = max(1, int(pg))
        except Exception:
            page = 1
        total = len(items)
        start = (page - 1) * PAGE_SIZE
        return {
            "list": items[start:start + PAGE_SIZE],
            "page": page,
            "pagecount": page if total < PAGE_SIZE else 9999,
            "limit": PAGE_SIZE,
            "total": total,
        }
