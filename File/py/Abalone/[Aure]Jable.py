
import sys
import re
import json
import threading
from urllib.parse import quote

import requests

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        pass

NAME = "Jable"
HOSTS = ["https://jable.my", "https://jable666.net"]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
DEBUG = False
STYLE = {"type": "rect", "ratio": 1.33}
PAGE_SIZE = 24

CARD_RE = re.compile(
    r'<a href="(https?://[^"]*/videos/([^"]+?)/)"[^>]*>\s*'
    r'<img[^>]*data-src="([^"]+)"[\s\S]*?'
    r'<span class="label">([^<]*)</span>[\s\S]*?'
    r'<h6 class="title"><a href="[^"]*">([\s\S]*?)</a></h6>'
)


class Spider(BaseSpider):

    def __init__(self):
        self.hosts = list(HOSTS)
        self.host = self.hosts[0]
        self.name = NAME
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": UA, "Accept": "*/*"})
        self._good_host = None
        self._cards_cache = {}
        self._lock = threading.Lock()

    def init(self, extend=""):
        cfg = {}
        if isinstance(extend, dict):
            cfg = extend
        elif extend:
            try:
                cfg = json.loads(extend)
            except Exception:
                cfg = {}
        if isinstance(cfg, dict):
            site = (cfg.get("site") or cfg.get("url") or "").strip().rstrip("/")
            if site:
                with self._lock:
                    self.hosts = [site] + [h for h in self.hosts if h != site]
                    self.host = self.hosts[0]
                    self._good_host = site
        self.options = cfg if isinstance(cfg, dict) else {}

    def getName(self):
        return self.name

    def getDependence(self):
        return []

    def destroy(self):
        with self._lock:
            self._cards_cache.clear()
        self.options = {}

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4|flv|mkv|ts)(\?|/|$)", str(url)))

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return {"msg": "不支持此操作"}

    def homeContent(self, filter):
        classes = [
            {"type_id": "latest-updates", "type_name": "最近更新"},
            {"type_id": "hot", "type_name": "热门影片"},
            {"type_id": "categories/chinese-subtitle", "type_name": "中文字幕"},
            {"type_id": "categories/roleplay", "type_name": "角色剧情"},
            {"type_id": "categories/uniform", "type_name": "制服诱惑"},
            {"type_id": "categories/sex-only", "type_name": "直接开啪"},
            {"type_id": "categories/pantyhose", "type_name": "丝袜美腿"},
            {"type_id": "categories/groupsex", "type_name": "多P群交"},
            {"type_id": "categories/bdsm", "type_name": "主奴调教"},
            {"type_id": "categories/pov", "type_name": "男友视角"},
            {"type_id": "categories/insult", "type_name": "凌辱快感"},
            {"type_id": "categories/private-cam", "type_name": "盗摄偷拍"},
            {"type_id": "categories/uncensored", "type_name": "无码解放"},
            {"type_id": "categories/lesbian", "type_name": "女同欢愉"},
        ]
        result = {"class": classes}
        if filter:
            sort_filter = {
                "key": "sort_by", "name": "排序", "init": "post_date",
                "value": [
                    {"n": "时间", "v": "post_date"},
                    {"n": "热度", "v": "post_date_and_popularity"},
                    {"n": "浏览", "v": "video_viewed"},
                    {"n": "收藏", "v": "most_favourited"},
                ],
            }
            result["filters"] = {c["type_id"]: [sort_filter] for c in classes}
        items = self._fetch_list("latest-updates", 1, {})
        result["list"] = [self._vod(x) for x in items]
        return result

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        items = self._fetch_list(str(tid), pg, extend or {})
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": pg if len(items) < PAGE_SIZE else 9999,
        }

    def detailContent(self, ids):
        vid = str(ids[0] if ids else "").strip()
        if vid.startswith("http"):
            vid = vid.rstrip("/").rsplit("/", 1)[-1]
        html = self._get("/videos/%s/" % quote(vid))
        if not html:
            return {"list": [], "msg": "获取详情失败"}
        m = re.search(r'<h4>([^<]+)</h4>', html)
        name = m.group(1).strip() if m else vid
        m = re.search(r'property="og:image" content="([^"]+)"', html) or re.search(r'poster="([^"]+)"', html)
        pic = m.group(1) if m else ""
        m = re.search(r'<span class="mr-3">([^<]*(?:前|ago)[^<]*)</span>', html)
        remarks = m.group(1).strip() if m else ""
        m = re.search(r'class="text-info fs-1 mr-2">[^<]*</span>([^<]+)<', html)
        cat = m.group(1).strip() if m else ""
        actors = []
        for mm in re.finditer(r'<a class="model"[^>]*>[\s\S]*?title="([^"]+)"', html):
            a = mm.group(1).strip()
            if a and a not in actors:
                actors.append(a)
        m = re.search(r'<span class="label">([0-9:]+)</span>', html)
        duration = m.group(1) if m else ""
        content = "番号:%s  时长:%s" % (vid, duration)
        vod = {
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": pic,
            "type_name": cat,
            "vod_remarks": remarks,
            "vod_actor": "、".join(actors),
            "vod_content": content,
            "vod_play_from": "Jable",
            "vod_play_url": "正片$" + vid,
        }
        return {"list": [vod]}

    def searchContent(self, key, quick, pg="1"):
        pg = self._int(pg, 1)
        key = str(key or "").strip()
        items = self._fetch_search(key, pg)
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": pg if len(items) < PAGE_SIZE else 9999,
        }

    def playerContent(self, flag, id, vipFlags):
        vid = str(id or "").strip()
        page_url = self.host + "/videos/" + quote(vid) + "/"
        html = self._get("/videos/%s/" % quote(vid), referer=self.host + "/")
        m = re.search(r"hlsUrl\s*=\s*'([^']+)'", html or "") or re.search(r'hlsUrl\s*=\s*"([^"]+)"', html or "")
        if not m:
            return {"parse": 0, "msg": "未找到播放地址"}
        return {
            "parse": 0,
            "jx": 0,
            "url": m.group(1),
            "format": "application/x-mpegURL",
            "header": {"User-Agent": UA, "Referer": page_url},
        }

    def liveContent(self, url):
        return "[]"


    def _get(self, path, referer=None):
        path = "/" + str(path).lstrip("/")
        hosts = list(self.hosts)
        if self._good_host in hosts:
            hosts.remove(self._good_host)
            hosts.insert(0, self._good_host)
        for h in hosts:
            try:
                hdr = {"Referer": referer or (h + "/")}
                r = self.session.get(h + path, headers=hdr, timeout=12)
                if r.status_code == 200 and len(r.text) > 2000:
                    r.encoding = "utf-8"
                    self._good_host = h
                    if DEBUG:
                        print("[jable] GET %s%s -> %d" % (h, path, len(r.text)))
                    return r.text
            except Exception as e:
                if DEBUG:
                    print("[jable] GET fail %s%s: %s" % (h, path, e))
                continue
        return ""

    def _fetch_list(self, tid, pg, extend):
        tid = str(tid or "latest-updates").strip().strip("/")
        sort_by = str((extend or {}).get("sort_by") or "").strip()
        if sort_by not in ("post_date", "post_date_and_popularity", "video_viewed", "most_favourited"):
            sort_by = "post_date"
        path = "/%s/%d/?sort_by=%s" % (tid, pg, sort_by)
        if pg <= 1:
            path = "/%s/?sort_by=%s" % (tid, sort_by)
        html = self._get(path)
        if html and ("video-img-box" not in html) and pg <= 1:
            html = self._get("/%s/1/?sort_by=%s" % (tid, sort_by))
        return self._parse_cards(html)

    def _fetch_search(self, key, pg):
        if not key:
            return []
        if pg <= 1:
            path = "/search/%s/" % quote(key)
        else:
            path = "/search/%s/%d/" % (quote(key), pg)
        return self._parse_cards(self._get(path))

    def _parse_cards(self, html):
        items = []
        if not html:
            return items
        seen = set()
        for m in CARD_RE.finditer(html):
            url, vid, pic, dur, title = m.group(1), m.group(2), m.group(3), m.group(4).strip(), m.group(5).strip()
            if not vid or vid in seen:
                continue
            seen.add(vid)
            items.append({"id": vid, "name": title, "pic": pic, "remarks": dur})
            if len(items) >= 48:
                break
        if DEBUG:
            print("[jable] parsed %d cards" % len(items))
        return items

    def _vod(self, item):
        return {
            "vod_id": item.get("id") or "",
            "vod_name": item.get("name") or item.get("id") or "",
            "vod_pic": item.get("pic") or "",
            "vod_remarks": item.get("remarks") or "",
            "style": STYLE,
        }

    def _int(self, x, d=0):
        try:
            return int(x)
        except Exception:
            return d
