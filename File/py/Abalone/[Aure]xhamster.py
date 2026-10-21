
import sys
import json
import re
import time
import threading
from urllib.parse import quote, unquote, urlsplit, urljoin

import requests

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        pass

NAME = "xHamster"
HOSTS = ["https://xhamster.com"]
UA = "Mozilla/5.0 (Linux; Android 13; Pixel) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
PAGE_SIZE = 24
CACHE_TTL = 30
DEBUG = False
VOD_ID_PREFIX = "vod/"
STYLE = {"type": "rect", "ratio": 1.78}


class Spider(BaseSpider):


    def __init__(self):
        self.hosts = list(HOSTS)
        self.host = self.hosts[0]
        self.name = NAME
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": UA, "Referer": self.host + "/", "Accept": "*/*"})
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
        return bool(re.search(r"\.(m3u8|mp4|flv|mkv|ts)(\?|$)", str(url)))

    def manualVideoCheck(self):
        return False


    def action(self, action):
        if action == "toast":
            return {"msg": "xHamster 源已就绪"}
        return {"msg": "不支持此操作"}


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
        vid = str(ids[0] if ids else "")

        if vid.startswith("vod/"):
            vid = vid[4:]

        slug = None
        if "|" in vid:
            vid, slug = vid.split("|", 1)
        data = self._fetch_detail(vid, slug)
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

        play_id = str(id or "")
        url = play_id


        if not (play_id.startswith("http://") or play_id.startswith("https://")):
            url = self._fetch_play(play_id)

        if not url:
            return {"parse": 0, "msg": "无法获取播放地址"}

        result = {
            "parse": 0,
            "jx": 0,
            "url": url,
            "header": self._string_map({"User-Agent": UA, "Referer": self.host + "/"}),
        }
        return result


    def liveContent(self, url):
        return "[]"


    def _safe_label(self, text: str) -> str:
        return str(text or "").replace("$", "＄").replace("#", "＃").strip()

    def _vod_id(self, site_id: str) -> str:
        return f"{VOD_ID_PREFIX}{site_id}" if VOD_ID_PREFIX else str(site_id)

    def _folder_id(self, type_: str, value: str) -> str:
        return f"folder/{type_}/{quote(value, safe='')}"

    def _actor_id(self, name: str) -> str:
        return f"actor/{quote(name, safe='')}"

    def _director_id(self, name: str) -> str:
        return f"director/{quote(name, safe='')}"

    def _action_id(self, value: str) -> str:
        return f"action/{value}"

    def _play_id(self, site_id: str, ep_idx: int, source: str) -> str:
        return f"play/{site_id}/{ep_idx}/{source}"

    def _clickable(self, kind: str, name: str) -> str:
        if not name:
            return ""
        ident = f"{kind}/{quote(name, safe='')}"
        payload = json.dumps(
            {"id": ident, "name": name, "type_flag": "1"},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return f"[a=cr:{payload}/]{name}[/a]"

    def _api(self, path, params=None, method="GET"):
        path = "/" + str(path).lstrip("/")
        ck = path + json.dumps(params or {}, sort_keys=True)
        with self._lock:
            hit = self._cache.get(ck)
            if hit and time.time() - self._cache_time.get(ck, 0) < CACHE_TTL:
                return hit

        hosts = list(self.hosts)
        if self._good_host in hosts:
            hosts.remove(self._good_host)
            hosts.insert(0, self._good_host)

        for h in hosts:
            try:
                url = h + "/api" + path
                if method == "GET":
                    r = self.session.get(url, params=params, timeout=10, verify=False)
                else:
                    r = self.session.post(url, data=params, timeout=10, verify=False)
                r.raise_for_status()
                if DEBUG:
                    print("[Quss DEBUG] %s -> %d bytes host=%s" % (url, len(r.text), h))
                obj = json.loads(r.text)
                self._good_host = h
                if h != self.host:
                    self.host = h
                with self._lock:
                    self._cache[ck] = obj
                    self._cache_time[ck] = time.time()
                return obj
            except Exception:
                continue
        return {}

    def _classes(self):
        hit = self._cache.get("__cls")
        if hit and time.time() - self._cache_time.get("__cls", 0) < CACHE_TTL:
            return hit[0]

        main_cats = [
            ("", "推荐"),
            ("japanese", "日本"),
            ("chinese", "中国"),
            ("asian", "亚洲"),
            ("jav", "JAV"),
            ("indonesian", "印尼"),
            ("russian", "俄罗斯"),
            ("indian", "印度"),
            ("taiwanese", "台湾"),
            ("korean", "韩国"),
            ("thai", "泰国"),
            ("american", "欧美"),
            ("filipina", "菲律宾"),
            ("pakistani", "巴基斯坦"),
            ("vietnamese", "越南"),
            ("iranian", "伊朗"),
            ("colombian", "哥伦比亚"),
            ("bangladeshi", "孟加拉"),
            ("european", "欧洲"),
            ("4k", "4K"),
            ("hd", "高清"),
            ("vr", "VR"),
        ]
        arr = []
        for slug, name in main_cats:
            tid = f"cat/{slug}" if slug else "cat/recommended"
            arr.append({"type_id": tid, "type_name": name, "style": STYLE})
        with self._lock:
            self._cache["__cls"] = (arr, time.time())
        return arr

    def _filters(self, classes):
        sort_filter = {
            "key": "order", "name": "排序", "init": "newest",
            "value": [{"n": "最新", "v": "newest"}, {"n": "最热", "v": "hot"}, {"n": "评分", "v": "rating"}, {"n": "最长", "v": "longest"}],
        }
        duration_filter = {
            "key": "duration", "name": "时长", "init": "all",
            "value": [{"n": "全部", "v": "all"}, {"n": "短 (<10min)", "v": "short"}, {"n": "中 (10-20min)", "v": "medium"}, {"n": "长 (>20min)", "v": "long"}],
        }
        quality_filter = {
            "key": "quality", "name": "画质", "init": "all",
            "value": [{"n": "全部", "v": "all"}, {"n": "HD", "v": "hd"}, {"n": "4K", "v": "4k"}],
        }
        return {c["type_id"]: [sort_filter, duration_filter, quality_filter] for c in classes}

    def _home_items(self):

        try:
            html = self._get_html(self.host + "/")
            if html:
                return self._parse_video_list(html)
        except Exception:
            pass
        return []

    def _vod(self, item):
        item = item or {}
        vid = str(item.get("id") or item.get("vod_id") or "")
        slug = item.get("slug", "")

        vod_id = vid
        if slug:
            vod_id = f"{vid}|{slug}"
        return {
            "vod_id": self._vod_id(vod_id),
            "vod_name": item.get("name") or item.get("title") or vid,
            "vod_pic": self._pic(item),
            "vod_remarks": item.get("remarks") or item.get("duration") or "",
            "style": STYLE,
        }

    def _pic(self, item):
        for k in ("thumb", "thumbUrl", "imageURL", "previewThumbURL", "poster", "cover", "pic", "img", "vod_pic"):
            v = item.get(k)
            if v:
                return v
        return ""

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
        except (TypeError, ValueError):
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


    def _get_html(self, url, **kw):
        try:
            r = self.session.get(url, timeout=kw.get("timeout", 15), verify=False, **kw)
            r.encoding = r.apparent_encoding or "utf-8"
            r.raise_for_status()
            return r.text
        except Exception:
            return None

    def _get_json(self, url, **kw):
        try:
            r = self.session.get(url, timeout=kw.get("timeout", 15), verify=False, **kw)
            r.encoding = r.apparent_encoding or "utf-8"
            return r.json()
        except Exception:
            return {}

    def _fix_url(self, u):
        if not u:
            return ""
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("/") and self.host:
            return self.host.rstrip("/") + u
        return u

    def _extract_initials(self, html):
        if not html:
            return {}

        m = re.search(r'<script[^>]*id="initials-script"[^>]*>', html)
        if not m:

            m = re.search(r'window\.initials\s*=', html)
        if not m:
            return {}

        start_pos = m.end()

        brace_pos = html.find('{', start_pos)
        if brace_pos == -1:
            return {}


        stack = 0
        end_pos = -1
        in_string = False
        escape = False
        for i in range(brace_pos, len(html)):
            ch = html[i]
            if escape:
                escape = False
                continue
            if ch == '\\':
                escape = True
                continue
            if ch == '"' and not escape:
                in_string = not in_string
                continue
            if not in_string:
                if ch == '{':
                    stack += 1
                elif ch == '}':
                    stack -= 1
                    if stack == 0:
                        end_pos = i + 1
                        break
        if end_pos == -1:
            return {}

        json_str = html[brace_pos:end_pos]
        try:
            return json.loads(json_str)
        except Exception as e:
            if DEBUG:
                print(f"[Quss DEBUG] JSON parse failed: {e}")
            return {}

    def _decrypt_token(self, token):
        if not token or len(token) < 12 or len(token) % 2 != 0:
            return None
        try:
            data = bytes.fromhex(token)
        except ValueError:
            return None

        if len(data) < 5:
            return token

        algo = data[0]
        if algo < 1 or algo > 7:
            return token

        seed = data[1] | (data[2] << 8) | (data[3] << 16) | (data[4] << 24)

        def make_xor_stream(algo, seed):
            i = seed & 0xFFFFFFFF
            if algo == 1:

                while True:
                    i = (i * 1664525 + 0x3c6ef35f) & 0xFFFFFFFF
                    yield i & 0xFF
            elif algo == 2:

                while True:
                    i ^= (i << 13) & 0xFFFFFFFF
                    i ^= (i >> 17) & 0xFFFFFFFF
                    i ^= (i << 5) & 0xFFFFFFFF
                    yield i & 0xFF
            elif algo == 3:

                while True:
                    i = (i + 0x9e3779b9) & 0xFFFFFFFF
                    e = i ^ (i >> 16)
                    e = (e * 0x85ebca77) & 0xFFFFFFFF
                    e ^= (e >> 13)
                    e = (e * 0xc2b2ae3d) & 0xFFFFFFFF
                    e ^= (e >> 16)
                    yield e & 0xFF
            elif algo == 4:

                while True:
                    i = ((i + 0x6d2b79f5) & 0xFFFFFFFF)
                    i = ((i << 7) | (i >> 25)) & 0xFFFFFFFF
                    e = (i + 0x9e3779b9) & 0xFFFFFFFF
                    e ^= (e >> 11)
                    e = (e * 0x27d4eb2d) & 0xFFFFFFFF
                    yield e & 0xFF
            elif algo == 5:

                while True:
                    i = (i + 0xa5a5a5a5) & 0xFFFFFFFF
                    i ^= (i << 7) & 0xFFFFFFFF
                    i ^= (i >> 9) & 0xFFFFFFFF
                    i ^= (i << 8) & 0xFFFFFFFF
                    yield i & 0xFF
            elif algo == 6:

                while True:
                    i = (i * 0x5deece66d + 0xb) & 0xFFFFFFFF
                    yield (i >> 16) & 0xFF
            elif algo == 7:

                while True:
                    i = (i + 0x9e3779b9) & 0xFFFFFFFF
                    e = i ^ ((i << 5) & 0xFFFFFFFF)
                    e = (e * 0x7feb352d) & 0xFFFFFFFF
                    e ^= (e >> 15)
                    e = (e * 0x846ca68b) & 0xFFFFFFFF
                    yield e & 0xFF
            else:
                return iter([])

        stream = make_xor_stream(algo, seed)
        result = bytearray()
        for b in data[5:]:
            try:
                result.append(b ^ next(stream))
            except StopIteration:
                break

        try:
            return result.decode('utf-8')
        except UnicodeDecodeError:
            return None

    def _parse_video_list(self, html):
        items = []
        if not html:
            return items


        initials = self._extract_initials(html)
        if initials:

            layout_page = initials.get("layoutPage", {})
            if isinstance(layout_page, dict):
                video_list_props = layout_page.get("videoListProps", {})
                if isinstance(video_list_props, dict):
                    video_thumb_props = video_list_props.get("videoThumbProps", [])
                    if isinstance(video_thumb_props, list):
                        for v in video_thumb_props:
                            item = self._normalize_video_item(v)
                            if item:
                                items.append(item)
                        if items:
                            return items


                trending_props = layout_page.get("trendingVideoListProps", {})
                if isinstance(trending_props, dict):
                    video_thumb_props = trending_props.get("videoThumbProps", [])
                    if isinstance(video_thumb_props, list):
                        for v in video_thumb_props:
                            item = self._normalize_video_item(v)
                            if item:
                                items.append(item)
                        if items:
                            return items


            for key in ("videoTabInitialData", "recommendedVideos", "homeVideos"):
                data = initials.get(key)
                if isinstance(data, dict):
                    video_list = data.get("videoListProps", {}).get("videoThumbProps") or data.get("videoThumbProps") or []
                    if isinstance(video_list, list):
                        for v in video_list:
                            item = self._normalize_video_item(v)
                            if item:
                                items.append(item)
                        if items:
                            break


        if not items:
            for m in re.finditer(r'href="/videos/([^"]+)"[^>]*>.*?<img[^>]+src="([^"]+)"[^>]*>.*?>([^<]+)<', html, re.DOTALL):
                slug = m.group(1)
                vid = slug.split("-")[-1]
                thumb = self._fix_url(m.group(2))
                title = m.group(3).strip()
                if vid and title:
                    items.append({
                        "id": vid,
                        "name": title,
                        "thumb": thumb,
                    })
        return items

    def _normalize_video_item(self, v):
        if not isinstance(v, dict):
            return None

        page_url = v.get("pageURL") or v.get("url") or ""
        vid = ""
        slug = ""
        if page_url:

            m = re.search(r'/videos/([^/]+)-xh([A-Za-z0-9]+)/?', page_url)
            if m:
                slug = m.group(1)
                vid = f"xh{m.group(2)}"

        if not vid:
            vid = str(v.get("idHash") or v.get("id") or v.get("videoId") or "")


        if not vid.startswith("xh") and v.get("idHash"):
            vid = v["idHash"]

        if not vid:
            return None

        return {
            "id": vid,
            "slug": slug,
            "name": v.get("title") or v.get("name") or vid,
            "thumb": v.get("thumbURL") or v.get("thumbUrl") or v.get("imageURL") or v.get("previewThumbURL") or "",
            "duration": v.get("duration") or 0,
            "views": v.get("views") or 0,
        }

    def _fetch_list(self, tid, pg, extend):
        items = []


        if tid.startswith("cat/"):
            slug = tid[4:]
            url = f"{self.host}/categories/{slug}"
        elif tid == "all" or tid == "recommended":
            url = self.host + "/"
        else:
            url = self.host + "/categories/" + tid


        if pg > 1:
            url += f"?page={pg}"


        if extend:
            params = []
            if extend.get("order"):
                params.append(f"order={extend['order']}")
            if extend.get("duration") and extend["duration"] != "all":
                params.append(f"duration={extend['duration']}")
            if extend.get("quality") and extend["quality"] != "all":
                params.append(f"quality={extend['quality']}")
            if params:
                sep = "&" if "?" in url else "?"
                url += sep + "&".join(params)

        html = self._get_html(url)
        if html:
            items = self._parse_video_list(html)

        return items

    def _fetch_detail(self, vid, slug=None):

        if vid.startswith("xh") and "-" not in vid:
            video_url = None

            if slug:
                video_url = f"{self.host}/videos/{slug}-{vid}"
            else:

                search_url = f"{self.host}/search/{quote(vid)}"
                html = self._get_html(search_url)

                if html:

                    m = re.search(r'href="(/videos/[^"]+' + re.escape(vid) + r')[^"]*"', html)
                    if m:
                        video_url = self.host + m.group(1)

                if not video_url:

                    video_url = f"{self.host}/videos/{vid}"
        else:
            video_url = f"{self.host}/videos/{vid}"

        html = self._get_html(video_url)
        if not html:
            return None


        initials = self._extract_initials(html)
        if not initials:
            return None

        video_info = initials.get("videoInfo", {}).get("videoInfo", {})
        video_entity = initials.get("videoEntity", {})
        xplayer_settings = initials.get("xplayerSettings", {})


        episodes = []
        sources = xplayer_settings.get("sources", {})
        hls_sources = sources.get("hls", {})


        hls_urls = []
        for codec in ("h264", "av1"):
            hls = hls_sources.get(codec, {})
            if isinstance(hls, dict) and hls.get("url"):
                decrypted = self._decrypt_token(hls["url"])
                if decrypted:
                    hls_urls.append({"name": f"HLS ({codec.upper()})", "url": decrypted})
                else:

                    hls_urls.append({"name": f"HLS ({codec.upper()})", "url": hls["url"]})


        if hls_urls:
            for i, p in enumerate(hls_urls):
                episodes.append({"name": p["name"], "url": p["url"]})


        if not episodes:
            std_sources = sources.get("standard", {})
            for codec in ("h264", "av1"):
                codec_sources = std_sources.get(codec, [])
                if isinstance(codec_sources, list):
                    for src in codec_sources:
                        if isinstance(src, dict) and src.get("url"):
                            quality = src.get("label") or src.get("quality") or "auto"
                            url = src["url"]

                            decrypted = self._decrypt_token(url)
                            if decrypted:
                                episodes.append({"name": quality, "url": decrypted})
                elif isinstance(codec_sources, dict) and codec_sources.get("url"):
                    quality = codec_sources.get("label") or codec_sources.get("quality") or "auto"
                    url = codec_sources["url"]
                    decrypted = self._decrypt_token(url)
                    if decrypted:
                        episodes.append({"name": quality, "url": decrypted})


        tags = initials.get("videoTagsComponent", {}).get("tags", [])
        categories = [t.get("name") for t in tags if t.get("isCategory")]
        pornstars = [t.get("name") for t in tags if t.get("isPornstar")]
        channel = None
        for t in tags:
            if t.get("isChannel"):
                channel = t.get("name")
                break

        return {
            "name": video_info.get("title") or video_entity.get("title") or vid,
            "episodes": episodes,
            "category": ", ".join(categories[:3]) if categories else (channel or ""),
            "year": str(video_entity.get("addTime", "")[:4]) if video_entity.get("addTime") else "",
            "area": "",
            "remarks": f"{video_info.get('views', 0):,} views · {self._format_duration(video_entity.get('duration', 0))}",
            "director": channel or "",
            "actors": pornstars,
            "description": video_info.get("description") or "",
        }

    def _format_duration(self, seconds):
        if not seconds:
            return ""
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    def _fetch_search(self, keyword, pg):
        if not keyword:
            return []
        url = f"{self.host}/search/{quote(keyword)}"
        if pg > 1:
            url += f"?page={pg}"
        html = self._get_html(url)
        if not html:
            return []
        return self._parse_video_list(html)

    def _fetch_play(self, play_id):


        if play_id.startswith("play/"):
            parts = play_id.split("/")
            if len(parts) >= 3:
                vid = parts[1]
                ep_idx = self._int(parts[2], 1)
            else:
                vid = play_id
                ep_idx = 1
        else:
            vid = play_id
            ep_idx = 1


        data = self._fetch_detail(vid)
        if not data:
            return ""

        episodes = data.get("episodes") or []
        if ep_idx <= len(episodes):
            return episodes[ep_idx - 1].get("url", "")
        elif episodes:
            return episodes[0].get("url", "")
        return ""
