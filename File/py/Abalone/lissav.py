
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

NAME = "LissAV"
HOSTS = ["https://lissav.com"]
UA = "Mozilla/5.0 (Linux; Android 13; Pixel) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36"
PAGE_SIZE = 24
CACHE_TTL = 30
STYLE = {"type": "rect", "ratio": 1.33}


LOCALE_PREFIX = "/asian/zh-CN"


class Spider(BaseSpider):

    def __init__(self):
        self.hosts = list(HOSTS)
        self.host = self.hosts[0]
        self.name = NAME
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": UA,
            "Referer": self.host + "/",
            "Accept": "*/*",
        })
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

    def getName(self):
        return self.name

    def getDependence(self):
        return []

    def destroy(self):
        with self._lock:
            self._cache.clear()
            self._cache_time.clear()

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4|flv|mkv|ts)(\?|$)", str(url)))

    def manualVideoCheck(self):
        return False

    def action(self, action):
        if action == "toast":
            return {"msg": "LissAV Spider"}
        return {"msg": "不支持此操作"}


    def homeContent(self, filter):
        classes = [
            {"type_id": "new-releases", "type_name": "最新发布", "style": STYLE},
            {"type_id": "recent-updates", "type_name": "最近更新", "style": STYLE},
            {"type_id": "hot-today", "type_name": "今日热门", "style": STYLE},
            {"type_id": "hot-week", "type_name": "本周热门", "style": STYLE},
            {"type_id": "hot-month", "type_name": "本月热门", "style": STYLE},
        ]
        result = {"class": classes}
        if filter:
            result["filters"] = {
                "new-releases": [
                    {"key": "order", "name": "排序", "init": "latest",
                     "value": [{"n": "最新", "v": "latest"}, {"n": "最热", "v": "hot"}]}
                ],
                "hot-today": [
                    {"key": "order", "name": "排序", "init": "today",
                     "value": [{"n": "今日", "v": "today"}, {"n": "本周", "v": "week"}, {"n": "本月", "v": "month"}]}
                ],
            }

        items = self._fetch_home_items()
        result["list"] = [self._vod(x) for x in items[:PAGE_SIZE]]
        return result

    def homeVideoContent(self):
        return {"list": []}


    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        extend = extend or {}

        path = self._tid_to_path(tid, extend)
        url = self.host + LOCALE_PREFIX + path
        if pg > 1:
            url = url.rstrip("/") + "/page/" + str(pg)
        html = self._get_html(url)
        if not html:
            return {"list": [], "page": pg, "pagecount": 1, "limit": PAGE_SIZE, "total": 0}
        items = self._parse_list_html(html)
        total = self._get_total_from_html(html)
        has_more = self._has_more(html, pg)
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": pg if not has_more else 9999,
            "limit": PAGE_SIZE,
            "total": total,
        }


    def detailContent(self, ids):
        vid = str(ids[0] if ids else "")
        if not vid:
            return {"list": [], "msg": "未找到此影片"}

        cid = vid.replace("vod/", "", 1) if vid.startswith("vod/") else vid
        detail_url = self.host + LOCALE_PREFIX + "/video/cid/" + quote(cid)
        html = self._get_html(detail_url)
        data = self._parse_detail(html, cid) if html else {}
        if not data:
            return {"list": [], "msg": "未找到此影片"}

        eps = data.get("episodes") or []
        if eps:
            lines = []
            for i, ep in enumerate(eps, 1):
                title = self._safe_label(ep.get("name") or f"第{i}集")
                url = ep.get("url") or ""
                if url:
                    lines.append(f"{title}${url}")
            play_url = "#".join(lines)
            play_from = data.get("source") or self.name
        else:
            url = data.get("url") or ""
            play_url = f"正片${url}" if url else ""
            play_from = self.name

        vod = {
            "vod_id": self._vod_id(cid),
            "vod_name": data.get("name") or cid,
            "vod_pic": data.get("pic") or "",
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
        key = (key or "").strip()
        if not key:
            return {"list": [], "page": 1, "pagecount": 1, "limit": PAGE_SIZE, "total": 0}
        path = "/videos/search/" + quote(key, safe="")
        if pg > 1:
            path = path.rstrip("/") + "/page/" + str(pg)
        url = self.host + LOCALE_PREFIX + path
        html = self._get_html(url)
        if not html:
            return {"list": [], "page": pg, "pagecount": 1, "limit": PAGE_SIZE, "total": 0}
        items = self._parse_list_html(html)
        has_more = self._has_more(html, pg)
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": pg if not has_more else 9999,
            "limit": PAGE_SIZE,
            "total": 999999,
        }


    def playerContent(self, flag, id, vipFlags):


        url = str(id or "").strip()
        if not url or url == "None":
            return {"parse": 0, "msg": "无法获取播放地址"}

        if url.startswith("http://") or url.startswith("https://"):
            return {
                "parse": 0,
                "jx": 0,
                "url": url,
                "header": self._string_map({
                    "User-Agent": UA,
                    "Referer": self.host + "/",
                }),
            }

        play_url = self._fetch_play(url)
        if not play_url:
            return {"parse": 0, "msg": "无法获取播放地址"}
        return {
            "parse": 0,
            "jx": 0,
            "url": play_url,
            "header": self._string_map({
                "User-Agent": UA,
                "Referer": self.host + "/",
            }),
        }

    def liveContent(self, url):
        return "[]"

    def localProxy(self, param):
        return [404, "text/plain", "not found"]


    def _tid_to_path(self, tid, extend):
        mapping = {
            "new-releases": "/videos/new-releases",
            "recent-updates": "/videos/recent",
            "hot-today": "/videos/hot/today",
            "hot-week": "/videos/hot/week",
            "hot-month": "/videos/hot/month",
        }

        if tid.startswith("tag/"):
            return "/videos/tag/" + unquote(tid.replace("tag/", "", 1))

        if tid.startswith("search/"):
            return "/videos/search/" + unquote(tid.replace("search/", "", 1))
        return mapping.get(tid, "/videos/new-releases")

    def _get_html(self, url, **kw):
        try:
            r = self.session.get(url, timeout=kw.get("timeout", 15), verify=False,
                                 allow_redirects=True)
            r.encoding = r.apparent_encoding or "utf-8"
            r.raise_for_status()
            return r.text
        except Exception:
            return None

    def _get_json(self, url, **kw):
        try:
            r = self.session.get(url, timeout=kw.get("timeout", 15), verify=False)
            r.encoding = r.apparent_encoding or "utf-8"
            return r.json()
        except Exception:
            return {}

    def _fetch_home_items(self):
        url = self.host + LOCALE_PREFIX + "/"
        html = self._get_html(url)
        if not html:
            return []
        return self._parse_list_html(html)

    def _parse_list_html(self, html):
        items = []
        seen = set()
        for m in re.finditer(
            r'<div class="streamit-video-card[^>]+'
            r'data-video-uid="([^"]+)"[^>]+'
            r'data-preview="([^"]+)".*?'
            r'<button[^>]+data-streamit-card-watch-later[^>]+>.*?</button>',
            html, re.S
        ):
            uid = m.group(1)
            if uid in seen:
                continue
            seen.add(uid)
            block = m.group(0)

            href_m = re.search(r'href="[^"]+/video/cid/([^"]+)"', block)
            cid = href_m.group(1) if href_m else uid

            img_m = re.search(r'<img[^>]+alt="([^"]+)"', block)
            title = img_m.group(1) if img_m else cid

            poster_m = re.search(r'<img[^>]+(?:data-src|src)="([^"]+)"', block)
            pic = poster_m.group(1) if poster_m else ""
            if not pic:
                poster_m = re.search(r'data-poster="([^"]+)"', block)
                pic = poster_m.group(1) if poster_m else ""

            time_m = re.search(r'<p class="mb-0">([^<]+)</p>', block)
            duration = time_m.group(1) if time_m else ""

            edition_m = re.search(r'<span class="streamit-video-card__edition[^"]*"[^>]*>(.*?)</span>', block, re.S)
            edition = re.sub(r'<[^>]+>', '', edition_m.group(1)).strip() if edition_m else ""
            remarks = edition or duration
            items.append({
                "id": cid,
                "title": title,
                "pic": pic,
                "remarks": remarks,
                "video_uid": uid,
            })
        return items

    def _parse_detail(self, html, cid):
        data = {"episodes": [], "url": ""}

        uid_m = re.search(r'window\.__STREAMIT_ME_QUERY__\s*=\s*\{"videoUid"\s*:\s*"([^"]+)"\}', html)
        video_uid = uid_m.group(1) if uid_m else ""
        if not video_uid:

            video_uid = cid
        data["video_uid"] = video_uid


        og_title_m = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', html)
        if og_title_m:
            data["name"] = og_title_m.group(1).replace("LissAV | ", "", 1).strip()
        else:
            title_m = re.search(r'<title>LissAV \| (.*?)</title>', html)
            data["name"] = title_m.group(1).strip() if title_m else cid

        desc_m = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]+)"', html)
        data["description"] = desc_m.group(1) if desc_m else ""

        og_img_m = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html)
        data["pic"] = og_img_m.group(1) if og_img_m else ""

        kw_m = re.search(r'<meta[^>]+name="keywords"[^>]+content="([^"]+)"', html)
        if kw_m:
            keywords = [k.strip() for k in kw_m.group(1).split(",")]

            filtered = [k for k in keywords if k and k != "LissAV" and k.lower() != cid.lower()]
            data["actors"] = filtered[:10]
            data["category"] = filtered[0] if filtered else ""

        date_m = re.search(r'"uploadDate"\s*:\s*"(\d{4})', html)
        data["year"] = date_m.group(1) if date_m else ""

        jsonld_m = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
        if jsonld_m:
            try:
                jd = json.loads(jsonld_m.group(1))
                if not data.get("name") and jd.get("name"):
                    data["name"] = jd["name"]
                if not data.get("description") and jd.get("description"):
                    data["description"] = jd["description"]
                if not data.get("pic") and jd.get("thumbnailUrl"):
                    data["pic"] = jd["thumbnailUrl"][0] if isinstance(jd["thumbnailUrl"], list) else jd["thumbnailUrl"]
                if not data.get("year") and jd.get("uploadDate"):
                    data["year"] = jd["uploadDate"][:4]
            except Exception:
                pass


        play_url = self._fetch_play(video_uid)
        if play_url:
            data["url"] = play_url
            data["episodes"] = [{"name": "正片", "url": play_url}]
        return data

    def _fetch_play(self, video_uid):
        if not video_uid:
            return ""
        url = self.host + LOCALE_PREFIX + "/api/video/stream?video_uid=" + quote(str(video_uid), safe="")
        try:
            r = self.session.get(url, timeout=15, verify=False,
                                 headers={"Referer": self.host + "/"})
            r.encoding = r.apparent_encoding or "utf-8"
            if r.status_code == 200:
                obj = r.json()
                playlist = obj.get("playlist") or []
                if playlist:

                    for item in playlist:
                        if item.get("urlType") == "m3u8" and item.get("url"):
                            return item["url"]

                    for item in playlist:
                        if item.get("url"):
                            return item["url"]
        except Exception:
            pass
        return ""

    def _has_more(self, html, pg):

        next_pg = pg + 1
        if "/page/" + str(next_pg) in html:
            return True

        if 'data-has-more="true"' in html:
            return True

        if re.search(r'href="[^"]*/page/' + str(next_pg) + r'["\s>]', html):
            return True
        return False

    def _get_total_from_html(self, html):

        cards = re.findall(r'data-video-uid="[^"]+"', html)
        if cards:
            return len(cards) * 100
        return 999999

    def _vod(self, item):
        item = item or {}
        vid = str(item.get("id") or item.get("video_uid") or "")
        return {
            "vod_id": self._vod_id(vid),
            "vod_name": item.get("title") or vid,
            "vod_pic": self._pic(item),
            "vod_remarks": item.get("remarks") or "",
            "style": STYLE,
        }

    def _pic(self, item):
        for k in ("pic", "cover", "img", "thumb", "vod_pic", "poster"):
            v = item.get(k)
            if v:
                return v
        return ""


    def _safe_label(self, text: str) -> str:
        return str(text or "").replace("$", "＄").replace("#", "＃").strip()

    def _vod_id(self, site_id: str) -> str:
        return f"vod/{site_id}"

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
