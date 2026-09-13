
import json
import re
import time
import requests
from urllib.parse import urlencode, parse_qs, urlparse

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        pass

NAME = "HoHoJ"
HOSTS = ["https://hohoj.tv"]
UA = "Mozilla/5.0 (Linux; Android 13; Pixel) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
PAGE_SIZE = 20
CACHE_TTL = 30
STYLE = {"type": "rect", "ratio": 1.33}


class Spider(BaseSpider):

    def __init__(self):
        self.hosts = list(HOSTS)
        self.host = self.hosts[0]
        self.name = NAME
        self.headers = {"User-Agent": UA, "Referer": self.host + "/", "Accept": "*/*"}
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self._cache = {}
        self._good_host = None

    def init(self, extend=""):
        if extend:
            try:
                cfg = json.loads(extend)
                site = (cfg.get("site") or cfg.get("url") or "").strip().rstrip("/")
                if site:
                    self.hosts = [site] + [h for h in self.hosts if h != site]
                    self.host = self.hosts[0]
            except Exception:
                pass

    def getName(self):
        return self.name

    def getDependence(self):
        return []

    def destroy(self):
        pass

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4|flv|mkv|ts)(\?|$)", str(url)))

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return ""


    def homeContent(self, filter):
        classes = self._classes()
        return {
            "class": classes,
            "filters": self._filters(classes),
            "list": [self._vod(x) for x in self._home_items()],
        }

    def homeVideoContent(self):
        return {"list": []}


    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        extend = extend or {}
        items = []
        try:
            data = self._get_category_list(tid, pg, extend)
            items = self._list_items(data)
        except Exception:
            items = []
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": 9999 if len(items) >= PAGE_SIZE else pg,
            "limit": PAGE_SIZE,
            "total": 999999,
        }


    def detailContent(self, ids):
        vid = str(ids[0])
        try:
            html = self._get(f"/video?id={vid}")
            info = self._parse_detail(html, vid)
        except Exception:
            return {"list": []}

        if not info:
            return {"list": []}

        play = []
        if info.get("episodes"):
            for i, ep in enumerate(info["episodes"], 1):
                title = str(ep.get("name") or f"第{i}集").replace("$", " ").replace("#", " ")
                play.append(f"{title}${vid}|{ep.get('seq') or i}")
        else:
            play = [f"正片${vid}|1"]

        vod = {
            "vod_id": vid,
            "vod_name": info.get("title") or vid,
            "vod_pic": info.get("pic") or "",
            "type_name": info.get("category") or "",
            "vod_year": str(info.get("year") or ""),
            "vod_area": info.get("area") or "",
            "vod_remarks": info.get("remarks") or "",
            "vod_actor": info.get("actor") or "",
            "vod_director": info.get("director") or "",
            "vod_content": info.get("description") or "",
            "vod_play_from": self.name,
            "vod_play_url": "#".join(play),
        }
        return {"list": [vod]}


    def searchContent(self, key, quick, pg="1"):
        pg = self._int(pg, 1)
        try:
            html = self._get(f"/search?text={requests.utils.quote(key)}&p={pg}")
            items = self._list_items(html)
        except Exception:
            items = []
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": 9999 if len(items) >= PAGE_SIZE else pg,
            "limit": PAGE_SIZE,
            "total": 999999,
        }


    def playerContent(self, flag, id, vipFlags):
        vid, seq = (str(id).split("|", 1) + ["1"])[:2]
        m3u8_url = ""
        try:
            html = self._get(f"/embed?id={vid}")
            m3u8_url = self._extract_m3u8(html)
        except Exception:
            pass
        return {
            "parse": 0,
            "url": m3u8_url,
            "header": {"User-Agent": UA, "Referer": f"{self.host}/embed?id={vid}"},
        }


    def _get(self, path):
        ck = path
        hit = self._cache.get(ck)
        if hit and time.time() - hit[1] < CACHE_TTL:
            return hit[0]
        for h in self.hosts:
            try:
                url = h + path
                r = self.session.get(url, timeout=10, verify=False)
                r.raise_for_status()
                self._good_host = h
                if h != self.host:
                    self.host = h
                self._cache[ck] = (r.text, time.time())
                return r.text
            except Exception:
                continue
        return ""

    def _classes(self):
        hit = self._cache.get("__cls")
        if hit:
            return hit[0]
        arr = []

        html = self._get("/")

        for m in re.finditer(r'/main_ctg\?id=(\d+)&name=([^"]+)', html):
            tid, nm = m.groups()
            arr.append({"type_id": f"main_{tid}", "type_name": nm, "style": STYLE})

        for m in re.finditer(r'/ctg\?id=(\d+)&name=([^"]+)', html):
            tid, nm = m.groups()
            arr.append({"type_id": f"ctg_{tid}", "type_name": nm, "style": STYLE})

        type_map = {
            "censored": "有碼",
            "uncensored": "無碼",
            "chinese": "中文字幕",
            "europe": "歐美",
        }
        for k, v in type_map.items():
            arr.append({"type_id": f"type_{k}", "type_name": v, "style": STYLE})

        arr.append({"type_id": "models", "type_name": "女優", "style": STYLE})
        if not arr:
            arr = [{"type_id": "all", "type_name": "全部", "style": STYLE}]
        self._cache["__cls"] = (arr, time.time())
        return arr

    def _filters(self, classes):
        common_order = [
            {"n": "最熱門", "v": "popular"},
            {"n": "最新", "v": "latest"},
            {"n": "最多觀看", "v": "views"},
            {"n": "最多讚好", "v": "likes"},
        ]
        common_type = [
            {"n": "全部", "v": "all"},
            {"n": "有碼", "v": "censored"},
            {"n": "中文字幕", "v": "chinese"},
            {"n": "無碼", "v": "uncensored"},
            {"n": "歐美", "v": "europe"},
        ]
        res = {}
        for c in classes:
            tid = c["type_id"]
            if tid.startswith("ctg_") or tid.startswith("main_") or tid.startswith("type_"):
                res[tid] = [
                    {"key": "type", "name": "類型", "value": common_type},
                    {"key": "order", "name": "排序", "value": common_order},
                ]
            elif tid == "models":
                res[tid] = [
                    {"key": "order", "name": "排序", "value": common_order},
                ]
        return res

    def _home_items(self):
        html = self._get("/")
        return self._list_items(html)

    def _get_category_list(self, tid, pg, extend):

        if tid.startswith("main_"):
            cid = tid.split("_", 1)[1]
            t = extend.get("type", "all")
            o = extend.get("order", "popular")
            return self._get(f"/main_ctg?id={cid}&type={t}&order={o}&p={pg}")
        elif tid.startswith("ctg_"):
            cid = tid.split("_", 1)[1]
            t = extend.get("type", "all")
            o = extend.get("order", "popular")
            return self._get(f"/ctg?id={cid}&type={t}&order={o}&p={pg}")
        elif tid.startswith("type_"):
            t = tid.split("_", 1)[1]
            o = extend.get("order", "popular")
            return self._get(f"/search?type={t}&order={o}&p={pg}")
        elif tid == "models":
            o = extend.get("order", "popular")
            return self._get(f"/all_models?order={o}&p={pg}")
        return self._get(f"/?p={pg}")

    def _list_items(self, html):
        items = []

        for m in re.finditer(r'<a\s+[^>]*href="/video\?id=(\d+)"[^>]*>.*?<img[^>]*src="([^"]+)"[^>]*alt="([^"]*)"', html, re.S):
            vid, img, alt = m.groups()
            title = alt
            badge = ""
            badge_match = re.search(r'video-item-badge">([^<]+)</div>', html[max(0,m.start()-500):m.end()+500])
            if badge_match:
                badge = badge_match.group(1)
            items.append({
                "id": vid,
                "title": title,
                "img": img,
                "badge": badge,
            })

        for m in re.finditer(r'<a\s+[^>]*href="/model\?id=(\d+)&name=([^"]+)"[^>]*>.*?<img[^>]*src="([^"]+)"', html, re.S):
            mid, name, img = m.groups()

            m2 = re.search(r'model-name[^>]*>([^<]+)</div>', html[m.start():m.end()+200])
            if m2:
                name = m2.group(1)
            items.append({
                "id": f"model_{mid}",
                "title": name,
                "img": img,
                "badge": "女優",
            })
        return items

    def _parse_detail(self, html, vid):
        info = {"id": vid}

        m = re.search(r'<h5[^>]*>([^<]+)</h5>', html)
        if m:
            info["title"] = m.group(1).strip()

        m = re.search(r'<img[^>]*hidden[^>]*src="([^"]+)"', html)
        if m:
            info["pic"] = m.group(1)

        m = re.search(r'/model\?id=\d+&name=([^"]+)"', html)
        if m:
            info["actor"] = m.group(1)

        cats = []
        for m in re.finditer(r'/ctg\?id=\d+&name=([^"]+)"', html):
            cats.append(m.group(1))
        for m in re.finditer(r'/main_ctg\?id=\d+&name=([^"]+)"', html):
            cats.append(m.group(1))
        for m in re.finditer(r'/search/\?type=([^"]+)"', html):
            t = m.group(1)
            if t == "censored": cats.append("有碼")
            elif t == "uncensored": cats.append("無碼")
            elif t == "chinese": cats.append("中文字幕")
            elif t == "europe": cats.append("歐美")
        if cats:
            info["category"] = ",".join(cats)

        m = re.search(r'video-item-badge">([^<]+)</div>', html)
        if m:
            info["remarks"] = m.group(1)

        m = re.search(r'<span>(\d{4}-\d{2}-\d{2})</span>', html)
        if m:
            info["year"] = m.group(1)[:4]

        m = re.search(r'<meta name="description" content="([^"]+)"', html)
        if m:
            info["description"] = m.group(1)
        info["episodes"] = [{"name": "正片", "seq": "1"}]
        return info

    def _extract_m3u8(self, html):

        m = re.search(r'videoSrc\s*=\s*"([^"]+\.m3u8)"', html)
        if m:
            return m.group(1)

        m = re.search(r'(https?://[^"\']+\.m3u8)', html)
        if m:
            return m.group(1)
        return ""

    def _vod(self, item):
        item = item or {}
        vid = str(item.get("id") or "")
        title = item.get("title") or vid

        title = re.sub(r'\s+', ' ', title).strip()
        return {
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": item.get("img") or "",
            "vod_remarks": item.get("badge") or "",
            "style": STYLE,
        }

    def _int(self, x, d=0):
        try:
            return int(x)
        except Exception:
            return d


if __name__ == "__main__":

    s = Spider()
    s.init()
    print("Name:", s.getName())
    print("Home:")
    home = s.homeContent(True)
    print(f"  Classes: {len(home.get('class', []))}")
    print(f"  List: {len(home.get('list', []))}")
    if home.get('list'):
        print(f"  First: {home['list'][0]}")
    print("Category (type_censored):")
    cat = s.categoryContent("type_censored", "1", {}, {})
    print(f"  List: {len(cat.get('list', []))}")
    if cat.get('list'):
        print(f"  First: {cat['list'][0]}")
    print("Search 'dldss':")
    sr = s.searchContent("dldss", False, "1")
    print(f"  List: {len(sr.get('list', []))}")
    if sr.get('list'):
        print(f"  First: {sr['list'][0]}")
    print("Detail:")
    if sr.get('list'):
        dt = s.detailContent([sr['list'][0]['vod_id']])
        print(f"  List: {len(dt.get('list', []))}")
        if dt.get('list'):
            v = dt['list'][0]
            print(f"  Title: {v.get('vod_name')}")
            print(f"  Play from: {v.get('vod_play_from')}")
            print(f"  Play url: {v.get('vod_play_url')[:100]}...")
    print("Player:")
    if sr.get('list'):
        pl = s.playerContent("", f"{sr['list'][0]['vod_id']}|1", {})
        print(f"  URL: {pl.get('url')}")
