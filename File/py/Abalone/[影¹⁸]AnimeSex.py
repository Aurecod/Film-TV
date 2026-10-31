# -*- coding: utf-8 -*-

import sys
import os
import re
import json
import time
import base64
import html as html_lib
import urllib.parse
import requests

requests.packages.urllib3.disable_warnings()

sys.path.append('..')
try:
    from base.spider import Spider as BaseSpider
except ImportError:
    BaseSpider = object

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
BASE = "https://animesex.club"
TIMEOUT = 20

# 分类 type_id 直接对应站点分类路径：/{path}/，分页 /{path}/page/N/
CLASSES = [
    {"type_id": "latest", "type_name": "最新更新"},
    {"type_id": "anime/2d-hentai", "type_name": "2D Hentai"},
    {"type_id": "anime/3d-hentai", "type_name": "3D Hentai"},
    {"type_id": "genres/2d-hentai", "type_name": "2D 合集"},
    {"type_id": "genres/3d-hentai", "type_name": "3D 合集"},
    {"type_id": "genres/uncensored", "type_name": "无码"},
    {"type_id": "genres/ahegao", "type_name": "Ahegao"},
    {"type_id": "genres/3d", "type_name": "3D"},
    {"type_id": "genres/3dcg", "type_name": "3DCG"},
]


class Spider(BaseSpider):
    def __init__(self):
        try:
            super(Spider, self).__init__()
        except Exception:
            pass
        self.siteName = "AnimeSex"

    def getName(self):
        return self.siteName

    def init(self, extend=""):
        self.session = requests.Session()
        self.headers = {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }
        self.session.headers.update(self.headers)
        self.baseUrl = BASE
        if extend and str(extend).strip().startswith("http"):
            self.baseUrl = str(extend).strip().rstrip("/")
        self.headers["Referer"] = self.baseUrl + "/"

    def getDependence(self):
        return []

    def _proxies(self):
        p = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY") \
            or os.environ.get("all_proxy") or os.environ.get("ALL_PROXY")
        return {"http": p, "https": p} if p else None

    def _get(self, url):
        for _ in range(2):
            try:
                r = self.session.get(url, headers=self.headers, timeout=TIMEOUT, verify=False, proxies=self._proxies())
                if r.status_code == 200:
                    return r.text
            except Exception:
                time.sleep(0.5)
        return ""

    def _clean(self, s):
        if not s:
            return ""
        t = html_lib.unescape(str(s))
        t = re.sub(r"\s+", " ", t).strip()
        t = re.sub(r"\s*[-|]\s*Anime\s*Sex\s*$", "", t, flags=re.I)
        return t.strip()

    def _fix_url(self, u):
        # 直链含空格（如 .../ASMR Sex With Nicole.mp4），需编码后请求
        if not u:
            return ""
        return urllib.parse.quote(u, safe=":/?&=%#")

    def _parse_list(self, html):
        items = []
        seen = set()
        for m in re.finditer(r'<article\b[^>]*>', html):
            head = m.group(0)
            seg = html[m.start(): m.start() + 3000]
            am = re.search(r'href="(?:%s)?/video/[^"]+"' % re.escape(self.baseUrl), seg)
            if not am:
                continue
            link = re.search(r'href="((?:%s)?/video/[^"]+)"' % re.escape(self.baseUrl), seg).group(1)
            if link.startswith("/"):
                link = self.baseUrl + link
            if link in seen:
                continue
            seen.add(link)
            cover = ""
            tm = re.search(r'data-main-thumb="([^"]+)"', head)
            if tm:
                cover = tm.group(1)
            title = ""
            t1 = re.search(r'title="([^"]+)"', seg)
            if t1:
                title = self._clean(t1.group(1))
            if not title:
                al = re.search(r'alt="([^"]+)"', seg)
                if al:
                    title = self._clean(al.group(1))
            if not title:
                title = self._clean(link.rstrip("/").split("/")[-1].replace("-", " "))
            if not cover:
                im = re.search(r'src="(https?://[^"]+/wp-content/uploads/[^"]+)"', seg)
                if im:
                    cover = im.group(1)
            items.append({"id": link, "title": title, "cover": cover})
        return items

    def _pagecount(self, html, pg, count):
        # 站点分页标题形如 "Page 2 of 58"，可直接取总页数
        m = re.search(r'Page\s+\d+\s+of\s+(\d+)', html)
        if m:
            return int(m.group(1))
        nums = [int(x) for x in re.findall(r'/page/(\d+)/', html)]
        if nums:
            return max(nums)
        return pg + 1 if count >= 20 else pg

    def _vod(self, it):
        return {
            "vod_id": it["id"],
            "vod_name": it["title"] or "AnimeSex",
            "vod_pic": it["cover"],
            "vod_remarks": "▶ AnimeSex",
        }

    def homeContent(self, filter):
        result = {"class": CLASSES}
        try:
            result["list"] = self.categoryContent("latest", 1, None, None)["list"]
        except Exception:
            result["list"] = []
        return result

    def homeVideoContent(self):
        return self.categoryContent("latest", 1, None, None)

    def categoryContent(self, tid, page, filter, ext):
        try:
            pg = max(int(page), 1) if page else 1
        except Exception:
            pg = 1
        tid = (tid or "").strip().strip("/")
        if tid == "latest":
            url = "%s/?filter=latest" % self.baseUrl if pg <= 1 else "%s/page/%d/?filter=latest" % (self.baseUrl, pg)
        elif tid:
            url = "%s/%s/" % (self.baseUrl, tid) if pg <= 1 else "%s/%s/page/%d/" % (self.baseUrl, tid, pg)
        else:
            url = self.baseUrl + "/" if pg <= 1 else "%s/page/%d/" % (self.baseUrl, pg)
        html = self._get(url)
        items = self._parse_list(html)
        pc = self._pagecount(html, pg, len(items))
        return {"list": [self._vod(it) for it in items], "page": pg, "pagecount": pc, "limit": 30, "total": pc * 30}

    def searchContent(self, key, quick, page="1"):
        try:
            pg = max(int(page), 1) if page else 1
        except Exception:
            pg = 1
        q = urllib.parse.quote(str(key))
        url = "%s/?s=%s" % (self.baseUrl, q) if pg <= 1 else "%s/page/%d/?s=%s" % (self.baseUrl, pg, q)
        html = self._get(url)
        items = self._parse_list(html)
        pc = self._pagecount(html, pg, len(items))
        return {"list": [self._vod(it) for it in items], "page": pg, "pagecount": pc, "limit": 30, "total": pc * 30}

    def _detail_title(self, html):
        m = re.search(r'<h1[^>]*class="[^"]*entry-title[^"]*"[^>]*>(.*?)</h1>', html, re.S)
        if not m:
            m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
        if m:
            t = self._clean(re.sub(r"<[^>]+>", "", m.group(1)))
            if t:
                return t
        m = re.search(r'<title>(.*?)</title>', html, re.S)
        if m:
            return self._clean(m.group(1))
        return ""

    def _detail_pic(self, html):
        for pat in (
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            r'data-main-thumb="([^"]+)"',
        ):
            m = re.search(pat, html)
            if m:
                return m.group(1)
        return ""

    def _detail_desc(self, html):
        m = re.search(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']*)["\']', html)
        if not m:
            m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)["\']', html)
        if m:
            return self._clean(m.group(1))
        return ""

    def _play(self, html):
        # 播放器地址藏在 player-x.php?q=<base64>，解码后是 <video src=...> 或 <iframe src=...>
        for m in re.finditer(r'player-x\.php\?q=([A-Za-z0-9+/=]+)', html):
            try:
                dec = base64.b64decode(m.group(1)).decode("utf-8", "ignore")
            except Exception:
                continue
            tag = urllib.parse.unquote(urllib.parse.parse_qs(dec).get("tag", [""])[0])
            srcs = re.findall(r'src=["\']([^"\']+)["\']', tag)
            if not srcs:
                continue
            if "<iframe" in tag:
                return srcs[0], 1
            return srcs[0], 0
        m2 = re.search(r'https?://[^"\']+\.(?:mp4|m3u8)[^"\']*', html)
        if m2:
            return m2.group(0), 0
        return "", 0

    def detailContent(self, ids):
        raw = ids[0] if ids else ""
        url = str(raw) if str(raw).startswith("http") else "%s/%s" % (self.baseUrl, str(raw).lstrip("/"))
        html = self._get(url)
        title = self._detail_title(html)
        cover = self._detail_pic(html)
        desc = self._detail_desc(html)
        play, need = self._play(html)
        vod = {
            "vod_id": raw,
            "vod_name": title or "AnimeSex",
            "vod_pic": cover,
            "vod_bg": cover,
            "vod_remarks": "需解析" if need else "▶ 直连",
            "vod_play_from": "AnimeSex",
            "vod_play_url": ("正片$%s" % self._fix_url(play)) if play else "",
            "vod_content": desc or "AnimeSex 动漫视频",
            "vod_director": "AnimeSex",
            "vod_actor": "AnimeSex",
        }
        return {"list": [vod]}

    def playerContent(self, flag, pid, vipFlags):
        target = str(pid).strip()
        if "$" in target:
            target = target.split("$", 1)[1]
        if not target:
            return {"parse": 0, "url": "", "msg": "无播放地址"}
        header = {"User-Agent": UA, "Referer": self.baseUrl + "/"}
        low = target.lower()
        if ".mp4" in low or ".m3u8" in low:
            return {"parse": 0, "url": target, "header": json.dumps(header)}
        return {"parse": 1, "url": target, "header": json.dumps(header)}

    def isVideoFormat(self, url):
        low = str(url or "").lower()
        return (".mp4" in low) or (".m3u8" in low)

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self.session = None


if __name__ == "__main__":
    sp = Spider()
    sp.init({})
    cls = sp.homeContent(True)["class"]
    print("分类数:", len(cls))
    for c in cls:
        print("  -", c["type_name"], "=>", c["type_id"] or "(首页)")
