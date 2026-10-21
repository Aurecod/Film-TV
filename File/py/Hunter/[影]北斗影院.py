
import re
import json
import time

import requests

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        pass

NAME = "北斗影院"
HOST = "http://www.bdjmcc.com"
UA = "Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
PAGE_SIZE = 36
CACHE_TTL = 30
STYLE = {"type": "rect", "ratio": 1.33}

class Spider(BaseSpider):

    def __init__(self):
        self.host = HOST
        self.name = NAME
        self.headers = {
            "User-Agent": UA,
            "Referer": HOST + "/",
            "Accept": "*/*",
            "Accept-Encoding": "identity",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self._cache = {}
        self._categories_cache = None

    def init(self, extend=""):
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

    def _fetch(self, url):
        ck = url
        hit = self._cache.get(ck)
        if hit and time.time() - hit[1] < CACHE_TTL:
            return hit[0]
        try:
            r = self.session.get(url, timeout=15)
            r.raise_for_status()
            r.encoding = r.apparent_encoding or "utf-8"
            html = r.text
            self._cache[ck] = (html, time.time())
            return html
        except requests.exceptions.ChunkedEncodingError:

            try:
                r = self.session.get(url, timeout=15, stream=True)
                r.raise_for_status()
                content = b''
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        content += chunk
                html = content.decode(r.apparent_encoding or "utf-8", errors="ignore")
                self._cache[ck] = (html, time.time())
                return html
            except Exception:
                return ""
        except Exception:
            return ""

    def _get_categories(self):
        if self._categories_cache is not None:
            return self._categories_cache
        html = self._fetch(self.host + "/")
        arr = []
        for href, name in re.findall(r'<li><a href="(/list/[^"]+)">([^<]+)</a></li>', html):
            tid = href.rstrip("/1.html")
            arr.append({"type_id": tid, "type_name": name, "style": STYLE})
        for href, name in re.findall(r'href="(/list/[^"]+)" class="t1e2x3t34s4">([^<]+)', html):
            tid = href.rstrip("/1.html")
            if not any(c["type_id"] == tid for c in arr):
                arr.append({"type_id": tid, "type_name": name, "style": STYLE})
        if not arr:
            arr = [{"type_id": "/list/A051pCM47kBg2", "type_name": "连续剧", "style": STYLE},
                   {"type_id": "/list/A1sQHJp3ggh3P", "type_name": "电影", "style": STYLE},
                   {"type_id": "/list/A2yIcGx03608i", "type_name": "动漫", "style": STYLE},
                   {"type_id": "/list/A1U43X24bwf2t", "type_name": "综艺", "style": STYLE}]
        self._categories_cache = arr
        return arr

    def homeContent(self, filter):
        classes = self._get_categories()
        return {"class": classes, "filters": self._filters(classes), "list": [self._vod(x) for x in self._home_items()]}

    def homeVideoContent(self):
        return {"list": []}

    def _filters(self, classes):
        common = [{"key": "order", "name": "排序", "value": [{"n": "默认", "v": ""}, {"n": "最新", "v": "new"}, {"n": "最热", "v": "hot"}]}]
        return {c["type_id"]: common for c in classes}

    def _home_items(self):
        html = self._fetch(self.host + "/")
        items = []
        for m in re.finditer(r'class="vbk423ssf">\s*<a class="kkfmdqwasda picture" href="(/v/[^"]+)" title="([^"]+)">\s*<img[^>]+data-original="([^"]+)"', html):
            items.append({"vod_id": m.group(1).replace("/v/", "").replace(".html", ""), "name": m.group(2), "pic": m.group(3), "remarks": ""})
        return items

    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        url = self.host + tid + "/" + str(pg) + ".html"
        html = self._fetch(url)
        items = []
        for m in re.finditer(r'class="vbk423ssf">\s*<a class="kkfmdqwasda picture" href="(/v/[^"]+)" title="([^"]+)">\s*<img[^>]+data-original="([^"]+)"', html):
            remarks = ""
            after_img = html[m.end():m.end()+200]
            rm = re.search(r'<span class="aecccdfg dfgdfgf4532328">([^<]+)</span>', after_img)
            if rm:
                remarks = rm.group(1)
            items.append({"vod_id": m.group(1).replace("/v/", "").replace(".html", ""), "name": m.group(2), "pic": m.group(3), "remarks": remarks})
        if not items:
            for m in re.finditer(r'<a class="mfbmf311 add42dss" href="(/v/[^"]+)" title="([^"]+)">\s*<span class="t1e2x3t34s4 fddpull-rigfht fkkdasdsdf3">([^<]+)</span>\s*([^<]+)</a>', html):
                items.append({"vod_id": m.group(1).replace("/v/", "").replace(".html", ""), "name": m.group(4).strip(), "pic": "", "remarks": m.group(3)})
        return {"list": [self._vod(x) for x in items], "page": pg, "pagecount": 9999 if len(items) >= PAGE_SIZE else pg, "limit": PAGE_SIZE, "total": 999999}

    def detailContent(self, ids):
        vid = str(ids[0])
        url = self.host + "/v/" + vid + ".html"
        html = self._fetch(url)
        if not html:
            return {"list": []}
        name = self._extract(html, r'<h1 class="title">([^<]+)</h1>') or self._extract(html, r'<h1 class="title">\s*([^<]+)') or vid
        pic = self._extract(html, r'data-original="([^"]+)"') or self._extract(html, r'<meta property="og:image" content="([^"]+)"') or ""
        type_name = self._extract(html, r'<span class="t1e2x3t34s4">类型：</span>([^<]+)') or ""
        area = self._extract(html, r'<span class="t1e2x3t34s4 sdf543">地区：</span>([^<]+)') or ""
        year = self._extract(html, r'<span class="t1e2x3t34s4 sdf543">年份：</span>([^<]+)') or ""
        actor = self._extract(html, r'<span class="vod-meta-label">主演：</span><span class="vod-meta-value">([^<]+)</span>') or ""
        director = self._extract(html, r'<span class="vod-meta-label">导演：</span><span class="vod-meta-value">([^<]+)</span>') or ""
        remarks = self._extract(html, r'<span class="vod-meta-label">更新：</span><span class="vod-meta-value">([^<]+)</span>') or ""
        content = self._extract(html, r'<span class="left t1e2x3t34s4">简介：</span>([\s\S]*?)</p>') or ""
        content = re.sub(r'<[^>]+>', '', content).strip()
        tabs = re.findall(r'class="playlist-group-btn"[^>]*onclick="return window.codexPlaylistSwitch\([^,]+,\s*(\d+)\s*\);\s*">([\s\S]*?)</button>', html)
        if not tabs:
            tabs = [(str(i), n) for i, n in enumerate(["高清线路", "非非线路", "无极云"], 1)]
        eps_by_tab = {}
        for tid, tname in tabs:
            pane_html = self._extract(html, r'data-group-pane="' + tid + r'"[\s\S]*?<ol class="dfs2_plsdfaylidst column8 clearfix">([\s\S]*?)</ol>')
            eps = []
            for href, title in re.findall(r'href="(/p/[^"]+)"[\s\S]*?data-group-id="' + tid + r'"[\s\S]*?title="([^"]+)"', pane_html):
                m = re.search(r'/p/[^/]+/' + tid + r'/(\d+)\.html', href)
                if m:
                    eps.append((m.group(1), title))
            if eps:
                eps_by_tab[tid] = (tname, eps)
        if not eps_by_tab:
            for tid, tname in tabs:
                eps = []
                for href in re.findall(r'href="(/p/' + vid + r'/' + tid + r'/\d+\.html)"', html):
                    m = re.search(r'/p/[^/]+/' + tid + r'/(\d+)\.html', href)
                    if m:
                        eps.append((m.group(1), "第" + m.group(1) + "集"))
                if eps:
                    eps_by_tab[tid] = (tname, eps)
        play_from = []
        play_url = []
        for tid, (tname, eps) in eps_by_tab.items():
            play_from.append(tname)
            ep_strs = []
            for ep_num, ep_title in eps:
                ep_title = ep_title.replace("$", " ").replace("#", " ")
                play_url_str = vid + "|" + tid + "|" + ep_num
                ep_strs.append(ep_title + "$" + play_url_str)
            play_url.append("#".join(ep_strs))
        vod = {
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": pic,
            "type_name": type_name,
            "vod_year": year,
            "vod_area": area,
            "vod_remarks": remarks,
            "vod_actor": actor,
            "vod_director": director,
            "vod_content": content,
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url),
        }
        return {"list": [vod]}

    def searchContent(self, key, quick, pg="1"):
        pg = self._int(pg, 1)
        import urllib.parse
        token = urllib.parse.quote(key).replace("%", "").replace("=", "").replace("+", "")
        token = self._b64url(key)
        url = self.host + "/search/" + token + "/" + str(pg) + ".html"
        html = self._fetch(url)
        items = []
        for m in re.finditer(r'class="vbk423ssf">\s*<a class="kkfmdqwasda picture" href="(/v/[^"]+)" title="([^"]+)">\s*<img[^>]+data-original="([^"]+)"[^>]*>\s*<span class="aecccdfg dfgdfgf4532328">([^<]+)</span>', html):
            items.append({"vod_id": m.group(1).replace("/v/", "").replace(".html", ""), "name": m.group(2), "pic": m.group(3), "remarks": m.group(4)})
        return {"list": [self._vod(x) for x in items], "page": pg, "pagecount": 9999 if len(items) >= PAGE_SIZE else pg, "limit": PAGE_SIZE, "total": 999999}

    def _b64url(self, s):
        try:
            utf8 = s.encode("utf-8")
            import base64
            return base64.urlsafe_b64encode(utf8).decode().rstrip("=")
        except Exception:
            return ""

    def playerContent(self, flag, id, vipFlags):
        parts = str(id).split("|")
        vid = parts[0] if len(parts) > 0 else ""
        tid = parts[1] if len(parts) > 1 else "1"
        ep = parts[2] if len(parts) > 2 else "1"
        url = self.host + "/p/" + vid + "/" + tid + "/" + ep + ".html"
        html = self._fetch(url)
        iframe_src = self._extract(html, r'id="playerFrame"\s+src="([^"]+)"')
        if not iframe_src:
            iframe_src = url
        return {"parse": 1, "url": iframe_src, "header": {"User-Agent": UA, "Referer": self.host + "/"}}

    def localProxy(self, param):
        return [404, "text/plain", "not found"]

    def _vod(self, item):
        item = item or {}
        vid = str(item.get("vod_id") or "")
        return {"vod_id": vid, "vod_name": item.get("name") or vid, "vod_pic": item.get("pic") or "", "vod_remarks": item.get("remarks") or "", "style": STYLE}

    def _extract(self, html, pattern):
        m = re.search(pattern, html)
        return m.group(1).strip() if m else ""

    def _int(self, x, d=0):
        try:
            return int(x)
        except Exception:
            return d
