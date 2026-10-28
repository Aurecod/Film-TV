# -*- coding: utf-8 -*-

import re
import sys
import gzip
import zlib
import html as html_lib
import urllib.request
import urllib.parse
from urllib.parse import quote, unquote
import http.cookiejar
import ssl

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider(object):
        def getCache(self, key): return None
        def setCache(self, key, value): return "fail"
        def delCache(self, key): return "fail"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
BASE = "https://91porn.com"
TIMEOUT = 8

CLASSES = [
    {"type_id": "video", "type_name": "全部视频", "query": "next=watch"},
    {"type_id": "ori", "type_name": "91原创", "query": "category=ori&viewtype=basic"},
    {"type_id": "hot", "type_name": "当前最热", "query": "category=hot&viewtype=basic"},
    {"type_id": "top", "type_name": "本月最热", "query": "category=top&viewtype=basic"},
    {"type_id": "top_last", "type_name": "上月最热", "query": "category=top&m=-1&viewtype=basic"},
    {"type_id": "rf", "type_name": "最近加精", "query": "category=rf&viewtype=basic"},
    {"type_id": "long", "type_name": "10分钟以上", "query": "category=long&viewtype=basic"},
    {"type_id": "longer", "type_name": "20分钟以上", "query": "category=longer&viewtype=basic"},
    {"type_id": "tf", "type_name": "本月收藏", "query": "category=tf&viewtype=basic"},
    {"type_id": "mf", "type_name": "收藏最多", "query": "category=mf&viewtype=basic"},
    {"type_id": "md", "type_name": "本月讨论", "query": "category=md&viewtype=basic"},
    {"type_id": "hd", "type_name": "高清", "query": "category=hd&viewtype=basic"},
]

CLASS_MAP = {}
for _c in CLASSES:
    CLASS_MAP[_c["type_id"]] = _c

TITLE_CACHE_KEY = "91p_title_"

def format_remarks(brand="蝴蝶影视", meta=""):
    clean_meta = str(meta or "").strip()
    clean_meta = re.sub(r"[\r\n\t]+", " ", clean_meta).strip()
    if clean_meta:
        return "%s | %s" % (brand, clean_meta)
    return brand

class Spider(BaseSpider):
    def __init__(self):
        super(Spider, self).__init__()
        self.siteName = "91Porn"
        self.siteUrl = BASE
        self.brandActor = "🦋 TG群: @tvshare23"
        self.brandDirector = "🦋 蝴蝶影视"
        self.brandDesc = "🦋 蝴蝶影视专线直连 | 极速硬解秒播 | 官方交流群: @tvshare23"
        self.brandLine = "蝴蝶专线"
        self._titles = {}
        self._entered = False

        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE

        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj),
            urllib.request.HTTPSHandler(context=self.ctx)
        )

    def getName(self):
        return self.siteName

    def init(self, extend=""):
        if isinstance(extend, dict):
            if extend.get("siteUrl"):
                self.siteUrl = extend["siteUrl"].rstrip("/")
        elif isinstance(extend, str) and extend.startswith("http"):
            self.siteUrl = extend.rstrip("/")
        self._entered = False
        return True

    def getDependence(self):
        return []

    def _clean_text(self, s):
        if not s:
            return ""
        t = str(s)
        for _ in range(3):
            prev = t
            t = html_lib.unescape(t)
            if t == prev:
                break
        if "%" in t and re.search(r"%[0-9A-Fa-f]{2}", t):
            try:
                u = unquote(t)
                if u != t and re.search(r"[\u4e00-\u9fa5]", u) and not re.search(r"[\u4e00-\u9fa5]", t):
                    t = u
            except Exception:
                pass
        t = t.replace("\r", " ").replace("\n", " ").replace("\t", " ")
        t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", t)
        t = t.replace("\ufffd", "")
        t = re.sub(r"\s{2,}", " ", t)
        t = re.sub(r"^(91\s*porn(\.com)?)\s*[-|_]\s*", "", t, flags=re.I)
        t = re.sub(r"\s*[-|_]\s*(91\s*porn(\.com)?|91p\d+)\s*$", "", t, flags=re.I)
        t = re.sub(r"\s+\d{1,3}:\d{2}(?::\d{2})?\s*$", "", t)
        return t.strip()

    def _valid_title(self, t, vid=""):
        if not t:
            return False
        s = str(t).strip()
        if len(s) < 2:
            return False
        if vid and s.lower() == str(vid).lower():
            return False
        if re.fullmatch(r"[0-9a-fA-F]{8,40}", s) and re.search(r"[a-fA-F]", s):
            return False
        if re.fullmatch(r"[\d\W_]+", s):
            return False
        if s.lower() in ("91porn", "91porn.com", "首页", "登录", "注册", "视频", "watch"):
            return False
        return True

    def _remember_title(self, vid, title):
        if not vid or not title:
            return
        if len(self._titles) > 3000:
            self._titles.clear()
        self._titles[vid] = title
        try:
            fn = getattr(self, "setCache", None)
            if fn:
                fn(TITLE_CACHE_KEY + vid, title)
        except Exception:
            pass

    def _known_title(self, vid):
        t = self._titles.get(vid, "")
        if t:
            return t
        try:
            fn = getattr(self, "getCache", None)
            if fn:
                t = fn(TITLE_CACHE_KEY + vid)
        except Exception:
            t = None
        if t and self._valid_title(t, vid):
            self._titles[vid] = t
            return t
        return ""

    def _fetch(self, target_url, referer=""):
        if not target_url:
            return ""
        if target_url.startswith("//"):
            target_url = "https:" + target_url
        elif target_url.startswith("/"):
            target_url = self.siteUrl + target_url

        headers = {
            "User-Agent": UA,
            "Referer": referer if referer else (self.siteUrl + "/index.php"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh-Hans;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        }

        for attempt in range(2):
            try:
                req = urllib.request.Request(target_url, headers=headers)
                with self.opener.open(req, timeout=TIMEOUT) as resp:
                    raw = resp.read()
                    enc = getattr(resp, "headers", {}).get("Content-Encoding", "")
                    if raw.startswith(b"\x1f\x8b") or enc == "gzip":
                        raw = gzip.decompress(raw)
                    elif enc == "deflate":
                        try:
                            raw = zlib.decompress(raw)
                        except Exception:
                            raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                    
                    head = raw[:4096].decode("ascii", "ignore")
                    meta_enc = ""
                    m = re.search(r'<meta[^>]+charset=["\']?\s*([A-Za-z0-9_\-]+)', head, re.I)
                    if not m:
                        m = re.search(r'charset=["\']?\s*([A-Za-z0-9_\-]+)', head, re.I)
                    if m:
                        meta_enc = m.group(1).strip().strip("\"'").lower()
                    if meta_enc in ("gb2312", "gbk", "gb-2312", "gb_2312"):
                        meta_enc = "gb18030"
                    
                    cands = [meta_enc] if meta_enc else []
                    for e in ("utf-8", "gb18030", "gbk", "big5", "latin1"):
                        if e not in cands:
                            cands.append(e)
                    for e in cands:
                        try:
                            return raw.decode(e)
                        except Exception:
                            continue
                    return raw.decode("utf-8", "ignore")
            except Exception:
                if attempt == 0:
                    continue
                return ""
        return ""

    def _enter(self):
        if self._entered:
            return
        self._fetch(self.siteUrl + "/index.php")
        self._entered = True

    def _pick_title(self, html, vid=""):
        pats = [
            r'<div[^>]+id=["\']videodetails["\'][^>]*>.*?<h4[^>]*>(.*?)</h4>',
            r'<title>(.*?)</title>',
            r'<div[^>]+id=["\']viewvideo-title["\'][^>]*>\s*([^<]{2,300})',
            r'id=["\']viewvideo-title["\'][^>]*>(.*?)</div>',
            r'property=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']',
            r'content=["\']([^"\']+)["\'][^>]*property=["\']og:title["\']',
            r'<h1[^>]*>(.*?)</h1>',
            r'class=["\'][^"\']*login_registerHeader[^"\']*["\'][^>]*>(.*?)</h4>',
            r'id=["\']player_one["\'][^>]*>.*?<h4[^>]*>(.*?)</h4>',
            r'<h4[^>]*>(.*?)</h4>',
            r'class=["\'][^"\']*video-title[^"\']*["\'][^>]*>(.*?)</div>',
            r'video_?title\s*[=:]\s*["\']([^"\']{2,200})["\']',
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']{2,200})["\']',
        ]
        for p in pats:
            m = re.search(p, html, re.S | re.I)
            if not m:
                continue
            raw = re.sub(r"<[^>]+>", " ", m.group(1))
            t = self._clean_text(raw)
            if self._valid_title(t, vid):
                return t
        return ""

    def _parse_list(self, html):
        items = []
        seen = set()
        parts = re.split(r'(?=<div class="well well-sm)', html)
        for b in parts:
            if "viewkey=" not in b:
                continue
            vk = re.search(r'viewkey=([a-z0-9]+)', b)
            if not vk:
                continue
            vid = vk.group(1)
            if vid in seen:
                continue
            seen.add(vid)

            thumb = re.search(r'src="(https?://[^"]+thumb[^"]+)"', b)
            if not thumb:
                thumb = re.search(r'<img[^>]+src="(https?://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', b)
            dur = re.search(r'duration">([^<]+)<', b)

            cands = []
            title_node = re.search(r'<span[^>]+class=["\'][^"\']*(?:title|video-title)[^"\']*["\'][^>]*>(.*?)</span>', b, re.S | re.I)
            if title_node:
                inner = title_node.group(1)
                inner_text = re.sub(r'<[^>]+>', '', inner).strip()
                if inner_text:
                    cands.append(inner_text)
                tm = re.search(r'title=["\']([^"\']+)["\']', inner)
                if tm:
                    cands.append(tm.group(1))

            link_with_title = re.search(r'<a[^>]+href=["\'][^"\']*viewkey=[^"\']*["\'][^>]*title=["\']([^"\']+)["\']', b, re.I)
            if link_with_title:
                cands.append(link_with_title.group(1))

            vt = re.search(r'class=["\'][^"\']*video-title[^"\']*["\'][^>]*>(.*?)</div>', b, re.S | re.I)
            if vt:
                seg = vt.group(1)
                ta = re.search(r'<a[^>]*title="([^"]+)"', seg)
                tt = re.search(r'<a[^>]*>([^<]+)</a>', seg)
                if ta:
                    cands.append(ta.group(1))
                if tt:
                    cands.append(tt.group(1))

            text_link = re.search(r'<a[^>]+href=["\'][^"\']*viewkey=%s[^"\']*["\'][^>]*>([^<]{4,100})</a>' % vid, b, re.I)
            if text_link:
                cands.append(text_link.group(1))

            alt = re.search(r'alt=["\']([^"\']{4,})["\']', b)
            if alt:
                cands.append(alt.group(1))

            title = ""
            for c in cands:
                t = self._clean_text(c)
                if self._valid_title(t, vid):
                    title = t
                    break

            if not title:
                title = self._known_title(vid)
            if not title:
                title = "视频 %s" % vid[-6:]

            self._remember_title(vid, title)
            items.append({
                "id": vid,
                "title": title,
                "pic": thumb.group(1) if thumb else "",
                "dur": self._clean_text(dur.group(1)) if dur else "",
            })
        return items

    def _vod(self, it):
        return {
            "vod_id": it["id"],
            "vod_name": it["title"],
            "vod_pic": it["pic"],
            "vod_remarks": format_remarks(self.brandDirector, it["dur"]),
            "style": {"type": "rect", "ratio": 1.78}
        }

    def _page(self, pg, count):
        return {
            "page": pg,
            "pagecount": pg + 1 if count >= 20 else pg,
            "limit": 24,
            "total": 999999 if count >= 20 else pg * 24,
        }

    def homeContent(self, filter):
        res = {"class": CLASSES}
        if filter:
            res["filters"] = {}
        return res

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, cid, page, filter, ext):
        try:
            pg = int(page) if page else 1
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1
        self._enter()
        conf = CLASS_MAP.get(str(cid).strip())
        query = conf["query"] if conf else "next=watch"
        url = "%s/v.php?%s&page=%d" % (self.siteUrl, query, pg)
        html = self._fetch(url)
        items = self._parse_list(html)
        res = self._page(pg, len(items))
        res["list"] = [self._vod(it) for it in items]
        return res

    def _extract_mp4(self, html):
        if not html:
            return ""
        m = re.search(r'strencode2\("([^"]+)"\)', html)
        if m:
            dec = unquote(m.group(1))
            src = re.search(r"src='([^']+)'", dec)
            if src:
                return src.group(1)
        m2 = re.search(r'https?://[^"\']+\.mp4[^"\']*', html)
        if m2:
            return m2.group(0)
        m3 = re.search(r'<(?:video|iframe)[^>]+src=["\']([^"\']+)["\']', html)
        if m3:
            return m3.group(1)
        return ""

    def _detail_pic(self, html):
        m = re.search(r'id=["\']vid["\'][^>]+poster=["\']([^"\']+)["\']', html)
        if not m:
            m = re.search(r'<video[^>]+poster=["\']([^"\']+)["\']', html)
        if not m:
            m = re.search(r'property=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']', html)
        if not m:
            m = re.search(r'content=["\']([^"\']+)["\'][^>]*property=["\']og:image["\']', html)
        if not m:
            m = re.search(r'poster=["\']([^"\']+)["\']', html)
        if not m:
            m = re.search(r'src="(https?://[^"]+thumb[^"]+)"', html)
        return m.group(1).strip() if m else ""

    def detailContent(self, did):
        raw_id = did[0] if isinstance(did, (list, tuple)) else str(did)
        vid = str(raw_id).strip()
        self._enter()
        html = self._fetch("%s/view_video.php?viewkey=%s" % (self.siteUrl, vid)) if vid else ""
        url = self._extract_mp4(html)
        title = self._pick_title(html, vid)
        if not title:
            title = self._known_title(vid)
        if not title:
            title = "超清正片"
        self._remember_title(vid, title)
        pic = self._detail_pic(html)
        vod = {
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": pic,
            "vod_bg": pic,
            "vod_background": pic,
            "vod_banner": pic,
            "vod_actor": self.brandActor,
            "vod_director": self.brandDirector,
            "vod_content": self.brandDesc,
            "vod_remarks": format_remarks(self.brandDirector, "超清正片"),
            "vod_play_from": self.brandLine,
            "vod_play_url": "正片$%s" % url,
        }
        return {"list": [vod]}

    def searchContent(self, key, quick, page="1"):
        try:
            pg = int(page) if page else 1
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1
        self._enter()
        url = "%s/search_result.php?search_id=%s&page=%d" % (
            self.siteUrl, quote(str(key)), pg)
        html = self._fetch(url)
        items = self._parse_list(html)
        res = self._page(pg, len(items))
        res["list"] = [self._vod(it) for it in items]
        return res

    def playerContent(self, flag, pid, vipFlags):
        target = str(pid).strip()
        if "$" in target:
            target = target.split("$", 1)[1]
        if "@@@" in target:
            target = target.split("@@@", 1)[0]
        return {"url": target, "header": {"User-Agent": UA, "Referer": self.siteUrl + "/"}, "parse": 0}

    def isVideoFormat(self, url):
        low = str(url or "").lower()
        return ("mp4" in low) or ("m3u8" in low)

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return {"msg": "ok"}

    def liveContent(self):
        return ""

    def localProxy(self, params):
        return [404, "text/plain; charset=utf-8", "Proxy not configured"]

    def destroy(self):
        self._titles.clear()
        self._entered = False