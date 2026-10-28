#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Javtiful (https://javtiful.com) 蜘蛛源
写法与结构参照 通用.py / X红颜.py / 555电影.py，纯 HTML + JSON 解析。

站点是自建 CMS（Laravel + Plyr 播放器），不是苹果CMS，没有采集接口，
全部走页面解析 + 一个取流接口。已实测的路由：

  首页        /                       → 302 到 /{lang}/main（lang 由 IP/语言决定，如 zh）
  推荐流      /{lang}/foryou
  有码/无码   /{lang}/censored   /{lang}/uncensored   /{lang}/reducing-mosaic
  分类总览    /{lang}/categories                      （21 个分类，slug 可能是中文）
  分类列表    /{lang}/category/{slug}                 第N页 ?page=N
  女优        /{lang}/actresses   单人 /{lang}/actress/{slug}?page=N
  频道        /{lang}/channels    单频道 /{lang}/channel/{slug}?page=N
  详情        /{lang}/video/{id}/{slug}
  搜索        /{lang}/search?q={kw}                   第N页 &page=N
  嵌入播放器   /embed/{id}                             （只有 7KB，取流专用）

列表卡片（video-card）：
  <article class="video-card">
    <a href="/zh/video/114824/abp-885-reducing-mosaic" class="video-card__thumbnail"
       data-front-video-preview-src="https://.../preview.mp4">
      <img src="/assets/front/media/video-thumb-placeholder.svg"
           data-front-lazy-src="/uploads/uploads/videos/thumbs/2026/10/21/xxxx.jpg" alt="...">
      <span class="video-card__type">Reducing Mosaic</span>
      <span class="video-card__details"><strong>FHD</strong>03:22:46</span>
    </a>
    <div class="video-card__copy">
      <a href="/zh/video/114824/..." class="video-card__title" title="ABP-885 ...">ABP-885 ...</a>
      <div class="video-card__meta">28.1K views · 13 hours ago</div>
    </div>
  </article>
  ※ 广告卡片 class 带 video-card--partner，href 是外链，靠「/video/{数字}/」过滤掉

取流（关键）：播放器不把地址写在页面里，而是先领票再换流
  1) 打开 /embed/{id}，取出
     <script id="watch-config" type="application/json">
       {...,"playback":{"endpoint":"/zh/video/114820/playback",
                        "ticket":"p1.114820.0.<时间戳>.<hash>.<签名>"},...}
     </script>
  2) POST {endpoint}，表单 ticket=xxx，头带 X-Requested-With
     → {"success":true,"sources":[{"src":"https://fast-stream.jav.si/p/xxxx",
                                    "type":"video/mp4","size":720,"label":"720p"}],
         "defaultQuality":720}
  ※ ticket 有效期很短（几十秒到几分钟），所以必须「取票 → 立刻换流」，
    不能把 ticket 缓存到下一次播放；票过期会返回 419 Session expired。
  ※ 换出来的直链在 fast-stream.jav.si，实测不带 Referer 也能 206，
    但源里依旧带上 Referer/Origin，防 CDN 策略变化。
"""

import sys
import re
import json
import urllib.request
import urllib.error
import urllib.parse
import http.cookiejar
import http.client
import gzip
import zlib
import ssl
import time

try:
    from urllib.parse import quote, unquote
except ImportError:  # pragma: no cover
    from urllib import quote, unquote

try:
    from base.spider import Spider as SpiderBase
except ImportError:
    class SpiderBase(object):
        def getCache(self, key):
            return None

        def setCache(self, key, value):
            return "fail"

        def delCache(self, key):
            return "fail"


# ---------------------------------------------------------------- 配置

SITE = "https://javtiful.com"
BRAND = ""
DEFAULT_LANG = "zh"          # 页面语言前缀；填 "" 表示跟随服务器跳转
STREAM_EXTS = (".m3u8", ".mp4", ".flv", ".mkv", ".avi", ".ts", ".mpd")
PAGE_SIZE = 24               # 站点每页约 23 条（含广告卡）

# 首页四大入口
HOME_SUBS = [
    {"n": "首页推荐", "v": "main"},
    {"n": "为你推荐", "v": "foryou"},
    {"n": "有码", "v": "censored"},
    {"n": "无码", "v": "uncensored"},
    {"n": "减码", "v": "reducing-mosaic"},
]

# 21 个分类（/categories 实测，slug 可能是中文，请求时会 quote）
CATEGORIES = [
    {"n": "女調查員", "v": "女調查員"},
    {"n": "国产AV", "v": "chinese-av"},
    {"n": "女老板", "v": "女老板"},
    {"n": "成熟的女人", "v": "成熟的女人"},
    {"n": "角色扮演", "v": "角色扮演"},
    {"n": "业余爱好者", "v": "业余爱好者"},
    {"n": "管家", "v": "管家"},
    {"n": "护士", "v": "护士"},
    {"n": "女学生", "v": "女学生"},
    {"n": "学校女生", "v": "学校女生"},
    {"n": "办公室女郎", "v": "办公室女郎"},
    {"n": "嫂子", "v": "嫂子"},
    {"n": "催眠", "v": "催眠"},
    {"n": "美丽的女孩", "v": "美丽的女孩"},
    {"n": "肥胖妇女", "v": "肥胖妇女"},
    {"n": "戏剧", "v": "戏剧"},
    {"n": "已婚妇女", "v": "已婚妇女"},
    {"n": "阿姨", "v": "阿姨"},
    {"n": "女教师", "v": "女教师"},
    {"n": "不忠行为", "v": "不忠行为"},
    {"n": "大乳房", "v": "大乳房"},
]

# 首页「热门女优」区块实测到的演员
ACTRESSES = [
    {"n": "Hana Himesaki", "v": "hana-himesaki"},
    {"n": "Hanazawa Himari", "v": "hanazawa-himari"},
    {"n": "Hatano Yui", "v": "hatano-yui"},
    {"n": "Iioka Kanako", "v": "iioka-kanako"},
    {"n": "Julia", "v": "julia"},
    {"n": "Kashiwagi Konatsu", "v": "kashiwagi-konatsu"},
    {"n": "Kitano Mina", "v": "kitano-mina"},
    {"n": "Kuramoto Sumire", "v": "kuramoto-sumire"},
    {"n": "Minatsuki Hikaru", "v": "minatsuki-hikaru"},
    {"n": "Misono Waka", "v": "misono-waka"},
    {"n": "Shinoda Yuu", "v": "shinoda-yuu"},
    {"n": "Tachibana Mary", "v": "tachibana-mary"},
    {"n": "Tenma Yui", "v": "tenma-yui"},
    {"n": "Yayoi Mizuki", "v": "yayoi-mizuki"},
    {"n": "Yoshine Yuria", "v": "yoshine-yuria"},
]

# 首页「热门频道」区块实测到的片商
CHANNELS = [
    {"n": "Attackers", "v": "attackers"},
    {"n": "DAS", "v": "das"},
    {"n": "Faleno", "v": "faleno"},
    {"n": "FC2PPV", "v": "fc2ppv"},
    {"n": "Hunter", "v": "hunter"},
    {"n": "Idea Pocket", "v": "idea-pocket"},
    {"n": "Madonna", "v": "madonna"},
    {"n": "MOODYZ", "v": "moodyz"},
    {"n": "Prestige", "v": "prestige"},
    {"n": "S1 NO.1 STYLE", "v": "s1-no1-style"},
    {"n": "SOD Create", "v": "sod-create"},
    {"n": "Venus", "v": "venus"},
]


# ---------------------------------------------------------------- 小工具

def _unescape(text):
    s = str(text or "")
    if "&" not in s:
        return s
    s = s.replace("&nbsp;", " ")
    s = s.replace("&quot;", '"').replace("&#39;", "'").replace("&apos;", "'")
    s = s.replace("&lt;", "<").replace("&gt;", ">")
    s = s.replace("&amp;", "&")
    return s


def format_remarks(brand=BRAND, meta=""):
    clean_meta = re.sub(r"[\r\n\t]+", " ", str(meta or "")).strip()
    if brand and clean_meta:
        return "%s | %s" % (brand, clean_meta)
    return clean_meta or brand


def clean_label(text):
    t = str(text or "")
    t = re.sub(r"</?em>", "", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = _unescape(t)
    t = re.sub(r"[\r\n\t\$#]+", " ", t)
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip()


def clean_pic(url):
    u = str(url or "").strip().replace("\\/", "/")
    if not u or u.startswith("data:"):
        return ""
    low = u.lower()
    for bad in ("placeholder", "blank.gif", "lazyload", "/logo"):
        if bad in low:
            return ""
    return u


def fixed_int(value, default=1):
    try:
        n = int(str(value or default).strip())
    except Exception:
        n = default
    return n if n >= 1 else default


# ---------------------------------------------------------------- 分区

ZONE_MATRIX = [
    {"id": "zone_home", "name": "🏠推荐", "subs": HOME_SUBS},
    {"id": "zone_cate", "name": "🏷️分类", "subs": CATEGORIES},
    {"id": "zone_actress", "name": "👩女优", "subs": ACTRESSES},
    {"id": "zone_channel", "name": "📺片商", "subs": CHANNELS},
    {"id": "zone_shorts", "name": "📱短视频", "subs": [{"n": "短视频", "v": "shorts"}]},
]

ZONE_PREFIX = {
    "zone_home": "",                  # 值是完整路径段：main / foryou / censored ...
    "zone_cate": "category",
    "zone_actress": "actress",
    "zone_channel": "channel",
}


# ---------------------------------------------------------------- 主体

class Spider(SpiderBase):
    def __init__(self):
        super(Spider, self).__init__()
        self.siteUrl = SITE
        self.brandActor = ""
        self.brandDirector = ""
        self._ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/128.0.0.0 Safari/537.36")
        self.options = {}
        self._lang = DEFAULT_LANG
        self._ref = ""
        self._init_session()

    def _init_session(self):
        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE
        self.cj = http.cookiejar.CookieJar()
        handlers = [
            urllib.request.HTTPCookieProcessor(self.cj),
            urllib.request.HTTPSHandler(context=self.ctx),
        ]
        # 部分地区/机房 IP 会被 Cloudflare 挡，可在扩展配置里填代理
        # 例：{"proxy": "http://192.168.1.5:7890"}
        proxy = str(self.options.get("proxy") or "").strip()
        if proxy:
            handlers.insert(0, urllib.request.ProxyHandler({
                "http": proxy, "https": proxy,
            }))
        self.opener = urllib.request.build_opener(*handlers)

    def init(self, extend=""):
        if isinstance(extend, dict):
            self.options = extend
        elif extend:
            try:
                self.options = json.loads(extend)
            except Exception:
                self.options = {}

        ua = str(self.options.get("ua") or "").strip()
        if ua:
            self._ua = ua
        # 语言前缀：默认 zh；填 "auto" 或留空则跟随服务器跳转
        lang = self.options.get("lang")
        if lang is not None:
            self._lang = str(lang).strip()
            if self._lang.lower() == "auto":
                self._lang = ""
        site = str(self.options.get("site") or self.options.get("url") or "").strip()
        if site.startswith("http"):
            self.siteUrl = site.rstrip("/")
        self._init_session()

    def getName(self):
        return "Javtiful"

    def isVideoFormat(self, url):
        low = str(url or "").lower()
        if not low:
            return False
        return any(k in low for k in STREAM_EXTS)

    def manualVideoCheck(self):
        return False

    # ---------------- 网络 ----------------

    def _abs(self, url):
        u = str(url or "").strip().replace("\\/", "/")
        if not u:
            return ""
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("http"):
            return u
        return (self.siteUrl + u) if u.startswith("/") else (self.siteUrl + "/" + u)

    def _path(self, path):
        """给路径加上语言前缀：/category/x → /zh/category/x"""
        p = str(path or "")
        if not p.startswith("/"):
            p = "/" + p
        if self._lang:
            return "/" + self._lang + p
        return p

    def _request(self, url, referer="", accept_encoding="gzip, deflate"):
        ref = referer or self._ref or (self.siteUrl + "/")
        headers = {
            "User-Agent": self._ua,
            "Referer": ref,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                      "image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": accept_encoding,
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "sec-ch-ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Connection": "close",
        }
        req = urllib.request.Request(url, headers=headers)
        with self.opener.open(req, timeout=15) as resp:
            code = resp.getcode()
            final = resp.geturl()
            try:
                enc = resp.headers.get("Content-Encoding", "") or ""
            except Exception:
                enc = ""
            try:
                raw = resp.read()
            except http.client.IncompleteRead as e:
                # 连接中途被掐：已到的部分先用（列表能出一大半，
                # _fetch_url 会对缺 </html> 的页面再重试）
                raw = e.partial or b""
        return code, final, enc, raw

    @staticmethod
    def _decompress(raw, enc):
        enc = (enc or "").lower()
        if raw[:2] == b"\x1f\x8b" or "gzip" in enc:
            try:
                return gzip.decompress(raw)
            except Exception:
                return raw
        if "deflate" in enc:
            try:
                return zlib.decompress(raw)
            except Exception:
                try:
                    return zlib.decompress(raw, -zlib.MAX_WBITS)
                except Exception:
                    return raw
        return raw

    @staticmethod
    def _decode(raw):
        for codec in ("utf-8", "gbk"):
            try:
                return raw.decode(codec)
            except Exception:
                pass
        return raw.decode("utf-8", "ignore")

    def _fetch_url(self, url, referer=""):
        last_err = ""
        for attempt in range(3):
            try:
                code, final, enc, raw = self._request(url, referer, "gzip, deflate")
                if "br" in enc.lower():
                    code, final, enc, raw = self._request(url, referer, "identity")
                raw = self._decompress(raw, enc)
                text = self._decode(raw)
                if code == 200 and "</html>" not in text and attempt < 2:
                    # 页面被截断，重试拿完整版
                    self._init_session()
                    time.sleep(0.5)
                    continue
                if code == 200:
                    self._ref = final or url
                return {"code": code, "text": text, "err": "", "final_url": final}
            except urllib.error.HTTPError as e:
                last_err = "HTTP %s" % e.code
                if e.code in (403, 429, 451, 502, 503, 520, 521, 522) and attempt < 2:
                    self._init_session()
                    time.sleep(0.2)
                    continue
                body = ""
                try:
                    body = e.read().decode("utf-8", "ignore")
                except Exception:
                    pass
                return {"code": e.code, "text": body, "err": last_err, "final_url": url}
            except Exception as e:
                last_err = str(e)
                if attempt < 2:
                    self._init_session()
                    time.sleep(0.2)
                    continue
                return {"code": -1, "text": "", "err": last_err, "final_url": url}
        return {"code": -1, "text": "", "err": last_err, "final_url": url}

    def _fetch(self, path, referer=""):
        """path 可以是相对路径（自动补语言前缀与域名）或完整 URL"""
        if not path:
            return {"code": 0, "text": "", "err": "", "final_url": ""}
        if path.startswith("//"):
            path = "https:" + path
        if path.startswith("http"):
            return self._fetch_url(path, referer)
        return self._fetch_url(self.siteUrl + self._path(path), referer)

    def _fetch_once(self, path):
        """单次抓取（不重试）：给并发抓多页的场景用——贵在有界，
        一页失败/截断就跳过，别把整个调用拖进连环重试"""
        try:
            if path.startswith("http"):
                url = path
            else:
                url = self.siteUrl + self._path(path)
            code, final, enc, raw = self._request(url, "", "gzip, deflate")
            if "br" in (enc or "").lower():
                code, final, enc, raw = self._request(url, "", "identity")
            return self._decode(self._decompress(raw, enc))
        except Exception:
            return ""

    def _cache_get(self, key):
        try:
            return self.getCache(key)
        except Exception:
            return None

    def _cache_set(self, key, value):
        try:
            self.setCache(key, value)
        except Exception:
            pass

    def _channel_subs(self, lazy=False):
        """片商全量（站上约 330 家、索引 14 页）：运行时抓索引页补齐，
        缓存 7 天；首页只读缓存/静态热门，不现抓（别拖慢首页）"""
        raw = self._cache_get("jv_channels_v1")
        if raw:
            try:
                data = json.loads(raw)
                if time.time() - float(data.get("ts") or 0) < 7 * 86400 \
                        and data.get("items"):
                    return data["items"]
            except Exception:
                pass
        if lazy:
            return CHANNELS
        items, seen = [], set()
        first = self._fetch("/channels")
        html = first.get("text", "")
        pages = min(self._pagecount(html, 1, 24), 30)
        # 名单页并发抓：旧版串行一页页抓（每页还带 3 次重试），十几页下来
        # 经常超过 Hawk 的耐心，片商区时好时坏；改并发后只等最慢的一页
        page_html = {1: html}
        if pages > 1:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=5) as ex:
                futs = {ex.submit(self._fetch_once, "/channels?page=%d" % pg): pg
                        for pg in range(2, pages + 1)}
                for f, pg in futs.items():
                    try:
                        page_html[pg] = f.result() or ""
                    except Exception:
                        page_html[pg] = ""
        for pg in range(1, pages + 1):
            for m in re.finditer(
                    r"""href=["'][^"']*?/channel/([^/"']+)["'][^>]*>([\s\S]*?)</a>""",
                    page_html.get(pg, ""), re.I):
                slug = m.group(1)
                if slug in seen:
                    continue
                nm = re.search(r"""directory-card__name[^>]*>([^<]+)<""", m.group(2))
                name = clean_label(nm.group(1)) if nm else ""
                if not name or len(name) > 30:
                    continue
                seen.add(slug)
                items.append({"n": name, "v": slug})
        if len(items) > len(CHANNELS):
            self._cache_set("jv_channels_v1", json.dumps(
                {"ts": time.time(), "items": items}))
            return items
        return CHANNELS

    def _detect_lang(self):
        """语言前缀未指定时，跟一次首页跳转拿到（如 /zh/main → zh）"""
        if self._lang:
            return
        res = self._fetch_url(self.siteUrl + "/")
        m = re.match(r"^https?://[^/]+/([a-z]{2})(?:/|$)", res.get("final_url", "") or "")
        if m:
            self._lang = m.group(1)

    # ---------------- 列表解析 ----------------

    @staticmethod
    def _block_pic(block):
        for attr in ("data-front-lazy-src", "data-src", "data-original",
                     "data-lazy-src", "src"):
            m = re.search(r"""\s%s=["']([^"']+)["']""" % attr, block, re.I)
            if m:
                cand = clean_pic(_unescape(m.group(1)))
                if cand:
                    return cand
        m = re.search(r"""background-image\s*:\s*url\(\s*['"]?([^'")]+)""", block, re.I)
        if m:
            cand = clean_pic(_unescape(m.group(1)))
            if cand:
                return cand
        return ""

    @staticmethod
    def _block_title(block, href_title=""):
        if href_title:
            return clean_label(href_title)
        m = re.search(r"""class=["'][^"']*video-card__title[^"']*["'][^>]*>([\s\S]*?)</a>""",
                      block, re.I)
        if m:
            return clean_label(m.group(1))
        m = re.search(r"""<h[1-6][^>]*>([\s\S]*?)</h[1-6]>""", block, re.I)
        if m:
            return clean_label(m.group(1))
        m = re.search(r"""alt=["']([^"']*)["']""", block, re.I)
        if m:
            t = clean_label(re.sub(r"^Thumbnail for\s*", "", m.group(1), flags=re.I))
            if t:
                return t
        return ""

    @staticmethod
    def _block_note(block):
        parts = []
        m = re.search(r"""class=["'][^"']*video-card__details[^"']*["'][^>]*>([\s\S]*?)</span>""",
                      block, re.I)
        if m:
            inner = m.group(1)
            strong = re.search(r"<strong>([\s\S]*?)</strong>", inner, re.I)
            if strong:
                parts.append(clean_label(strong.group(1)))
            tail = clean_label(re.sub(r"<strong>[\s\S]*?</strong>", " ", inner))
            if tail:
                parts.append(tail)
        m = re.search(r"""class=["'][^"']*video-card__type[^"']*["'][^>]*>([^<]{1,24})<""",
                      block, re.I)
        if m:
            t = clean_label(m.group(1))
            if t and t not in parts:
                parts.append(t)
        m = re.search(r"""class=["'][^"']*video-card__meta[^"']*["'][^>]*>([\s\S]*?)</div>""",
                      block, re.I)
        if m:
            t = clean_label(m.group(1))
            if t:
                parts.append(t)
        return " · ".join([x for x in parts if x])[:40]

    def _cards(self, html):
        """解析 video-card 卡片；广告卡（外链）会被 /video/{数字}/ 过滤掉"""
        if not html:
            return []

        out = []
        seen = set()
        # 注意：卡片可能带额外属性（foryou 页是
        # <article class="video-card" data-recommendation-id="107099">）
        blocks = re.findall(r"""<article class=["']video-card[^>]*>([\s\S]*?)</article>""",
                            html, re.I)
        for block in blocks:
            hm = re.search(r"""href=["']([^"']*?/(?:[a-z]{2}/)?video/(\d+)/([^"'#]+))["']""",
                           block, re.I)
            if not hm:
                continue
            vid = hm.group(2)
            if vid in seen:
                continue
            seen.add(vid)

            href = _unescape(hm.group(1))
            tm = re.search(r"""video-card__title[^>]*title=["']([^"']+)["']""", block, re.I)
            title = self._block_title(block, _unescape(tm.group(1)) if tm else "")
            if not title:
                continue

            pic = self._block_pic(block)
            out.append({
                "vod_id": self._abs(href),
                "vod_name": title,
                "vod_pic": self._abs(pic),
                "vod_remarks": format_remarks(BRAND, self._block_note(block)),
                "style": {"type": "rect", "ratio": 1.78},
            })
        return out

    @staticmethod
    def _pagecount(html, page, count):
        """总页数从分页条取：<a class="pagination__link" href="...?page=2218">"""
        nums = [int(x) for x in re.findall(r"[?&]page=(\d+)", html or "")]
        nums = [n for n in nums if n <= 20000]
        if nums:
            return max(nums)
        return page + 1 if count >= PAGE_SIZE else page

    def _list(self, path, page):
        """通用列表：路径 + ?page=N"""
        p = path
        if page > 1:
            p = "%s%s%spage=%d" % (path, "&" if "?" in path else "?", "", page)
        res = self._fetch(p)
        html = res.get("text", "")
        vod_list = self._cards(html)
        pagecount = self._pagecount(html, page, len(vod_list))
        return {
            "page": page,
            "pagecount": pagecount,
            "limit": PAGE_SIZE,
            "total": pagecount * PAGE_SIZE,
            "list": vod_list,
        }

    def _zone_subs(self, zid):
        """各区实际生效的细分列表（女优置顶全量索引，片商走运行时全量）"""
        for z in ZONE_MATRIX:
            if z["id"] == zid:
                if zid == "zone_actress":
                    return [{"n": "全部女优", "v": "__all__"}] + ACTRESSES
                if zid == "zone_channel":
                    return self._channel_subs(lazy=True)
                return z["subs"]
        return []

    # ---------------- 首页 ----------------

    def homeContent(self, filter):
        classes = [{"type_name": z["name"], "type_id": z["id"]} for z in ZONE_MATRIX]
        filters = {}
        for z in ZONE_MATRIX:
            subs = self._zone_subs(z["id"])
            if len(subs) > 1:
                filters[z["id"]] = [{
                    "key": "sub",
                    "name": "细分",
                    "init": subs[0]["v"],
                    "value": subs,
                }]
        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        self._detect_lang()
        res = self._fetch("/main")
        cards = self._cards(res.get("text", ""))
        if not cards:
            res = self._fetch("/foryou")
            cards = self._cards(res.get("text", ""))
        return {"list": cards[:30]}

    # ---------------- 分类 ----------------

    def categoryContent(self, tid, pg, filter, extend):
        self._detect_lang()
        if tid == "zone_channel":
            self._channel_subs()          # 首次进片商区时把全量名单补齐并缓存
        page = fixed_int(pg, 1)
        if tid == "zone_shorts":
            return self._shorts_list(page)

        sub = ""
        if isinstance(extend, str) and extend.strip():
            try:
                extend = json.loads(extend)
            except Exception:
                extend = {}
        if isinstance(extend, dict) and extend.get("sub"):
            sub = str(extend["sub"]).strip()
        if not sub:
            subs = self._zone_subs(tid)
            sub = subs[0]["v"] if subs else ""
        if not sub:
            sub = "main"

        if tid == "zone_actress" and sub == "__all__":
            return self._actress_index(page)

        prefix = ZONE_PREFIX.get(tid, "")
        if prefix:
            path = "/%s/%s" % (prefix, quote(sub, safe=""))
        else:
            path = "/" + sub.lstrip("/")          # main / foryou / censored ...

        return self._list(path, page)

    # ---------------- 短视频（Shorts） ----------------

    def _shorts_bootstrap(self, html):
        """短视频页内嵌的 feed JSON（#shorts-bootstrap）：每条自带
        标题/封面/m3u8 直链/完整版地址，feed.cursor 是翻页凭证"""
        m = re.search(r'id="shorts-bootstrap"[^>]*>([\s\S]*?)</script>', html or "")
        if not m:
            return [], ""
        try:
            data = json.loads(m.group(1))
        except Exception:
            return [], ""
        feed = data.get("feed") or {}
        return feed.get("items") or [], str(feed.get("cursor") or "")

    def _shorts_cards(self, items):
        out, seen = [], set()
        for it in items or []:
            if not isinstance(it, dict):
                continue
            uid = str(it.get("uid") or "").strip()
            if not uid or uid in seen:
                continue
            seen.add(uid)
            actress = it.get("actress") or {}
            aname = clean_label(actress.get("name") or "") \
                if isinstance(actress, dict) else ""
            out.append({
                "vod_id": "shorts:" + uid,
                "vod_name": clean_label(it.get("caption") or "") or uid,
                "vod_pic": str(it.get("poster") or ""),
                "vod_remarks": format_remarks("", aname),
                "style": {"type": "rect", "ratio": 0.56},
            })
        return out

    def _shorts_feed(self, cursor):
        """feed 接口：cursor 与会话绑定，必须走本会话（_fetch_once 保 Cookie、
        单次不重试）；返回 (items, 新cursor)，失败返回 ([], "")"""
        url = self.siteUrl + "/shorts/feed?cursor=" + quote(cursor, safe="")
        try:
            data = json.loads(self._fetch_once(url))
        except Exception:
            return [], ""
        if not isinstance(data, dict) or not data.get("success"):
            return [], ""
        return data.get("items") or [], str(data.get("cursor") or "")

    def _shorts_state(self):
        """短视频已取条目的队列状态（实例内存为主、缓存为备）：
        {items: [...], cursor: 下一批凭证, end: 是否到底}"""
        st = getattr(self, "_shorts_st", None)
        if isinstance(st, dict) and "items" in st:
            return st
        try:
            st = json.loads(self._cache_get("jv_shorts_state_v1") or "{}")
        except Exception:
            st = {}
        if not isinstance(st, dict) or "items" not in st:
            st = {"items": [], "cursor": "", "end": False}
        self._shorts_st = st
        return st

    def _shorts_save_state(self, st):
        self._shorts_st = st
        try:
            self._cache_set("jv_shorts_state_v1", json.dumps(st))
        except Exception:
            pass

    def _shorts_ensure(self, st, need):
        """把队列补到 need 条：feed 一批只有 8 条，靠 cursor 一批批往下接；
        单次调用有时间预算（8 秒），补不满就先交现有的。cursor 过期被拒时
        重新进 /shorts 拿新凭证（已取条目保留、靠 uid 去重，不会翻重复页）"""
        import time as _time
        deadline = _time.time() + 8
        seen = {str(it.get("uid") or "") for it in st["items"]
                if isinstance(it, dict)}
        booted = False
        while len(st["items"]) < need and not st.get("end"):
            if _time.time() > deadline:
                break
            if not st.get("cursor"):
                res = self._fetch(self.siteUrl + "/shorts")
                batch, cursor = self._shorts_bootstrap(res.get("text", ""))
                booted = True
                if not batch and not cursor:
                    st["end"] = True
                    break
            else:
                batch, cursor = self._shorts_feed(st["cursor"])
                if not batch and not cursor:
                    if booted:      # 刚换的新凭证也被拒：真到底/真故障，停
                        st["end"] = True
                        break
                    st["cursor"] = ""   # 凭证过期：清掉，下轮重进 /shorts 换新
                    continue
            fresh = [it for it in batch
                     if isinstance(it, dict)
                     and str(it.get("uid") or "") not in seen]
            for it in fresh:
                seen.add(str(it.get("uid") or ""))
            st["items"].extend(fresh)
            st["cursor"] = cursor
            if not cursor:
                st["end"] = True
            self._shorts_save_state(st)

    def _shorts_list(self, page):
        """短视频列表：一页 24 条（与站内其它区同规格，feed 批次在内部接）；
        已取条目在队列里按序切页，翻到哪页补到哪页"""
        per = 24
        st = self._shorts_state()
        self._shorts_ensure(st, page * per)
        chunk = st["items"][(page - 1) * per: page * per]
        cards = self._shorts_cards(chunk)
        has_more = len(st["items"]) > page * per or not st.get("end")
        return {"page": page,
                "pagecount": page + 1 if (cards and has_more) else page,
                "limit": per, "total": 999999, "list": cards}

    def _shorts_detail(self, uid):
        """短视频详情：单条页内嵌 JSON 里能按 uid 找到它（带 m3u8 直链）；
        抓不到就按 uid 拼直链规律兜底；条目带完整版地址时附一条完整版线路
        （走正片的领票换流）"""
        media = poster = caption = full = actress_name = ""
        res = self._fetch(self.siteUrl + "/shorts/" + uid)
        items, _ = self._shorts_bootstrap(res.get("text", ""))
        for it in items:
            if isinstance(it, dict) and str(it.get("uid") or "") == uid:
                media = str(it.get("media") or "")
                poster = str(it.get("poster") or "")
                caption = clean_label(it.get("caption") or "")
                full = str(it.get("fullVideoUrl") or "")
                actress = it.get("actress") or {}
                if isinstance(actress, dict):
                    actress_name = clean_label(actress.get("name") or "")
                break
        if not media:
            media = "https://shorts.avtik.com/shorts/playback/%s/v1/v720.m3u8" % uid
        if not poster:
            poster = "https://shorts.avtik.com/shorts/playback/%s/v1/cover.jpg" % uid
        froms, urls = ["短片"], ["短片$%s" % media]
        if full:
            froms.append("完整版")
            urls.append("正片$%s" % self._abs(full))
        return {"list": [{
            "vod_id": "shorts:" + uid,
            "vod_name": caption or "短视频",
            "vod_pic": poster,
            "vod_actor": actress_name,
            "vod_director": "",
            "vod_remarks": format_remarks("", "短视频"),
            "vod_content": caption,
            "vod_play_from": "$$$".join(froms),
            "vod_play_url": "$$$".join(urls),
        }]}

    # ---------------- 女优全量索引 ----------------

    def _actress_cards(self, html):
        """女优索引页的人物卡（directory-card）：点人进合集详情"""
        out, seen = [], set()
        for m in re.finditer(
                r"""href=["'][^"']*?/actress/([^/"']+)["'][^>]*>([\s\S]*?)</a>""",
                html or "", re.I):
            slug = m.group(1)
            if slug in seen:
                continue
            block = m.group(2)
            nm = re.search(r"""directory-card__name[^>]*>([^<]+)<""", block)
            name = clean_label(nm.group(1)) if nm else ""
            if not name:
                continue
            seen.add(slug)
            im = re.search(r"""<img[^>]+src=["']([^"']+)["']""", block, re.I)
            cm = re.search(r"""directory-card__count[^>]*>([^<]+)<""", block)
            out.append({
                "vod_id": self.siteUrl + "/%s/actress/%s" % (
                    self._lang or "zh", slug),
                "vod_name": name,
                "vod_pic": self._abs(_unescape(im.group(1))) if im else "",
                "vod_remarks": format_remarks(
                    "", clean_label(cm.group(1)) if cm else ""),
                "style": {"type": "rect", "ratio": 1.78},
            })
        return out

    def _actress_index(self, page):
        path = "/actresses" if page <= 1 else "/actresses?page=%d" % page
        res = self._fetch(path)
        html = res.get("text", "")
        cards = self._actress_cards(html)
        pagecount = self._pagecount(html, page, len(cards))
        return {
            "page": page,
            "pagecount": pagecount,
            "limit": PAGE_SIZE,
            "total": pagecount * PAGE_SIZE,
            "list": cards,
        }

    def _actress_detail(self, url):
        """女优合集：她的片单按页分线路（每线一页 24 部，最多收 6 页；
        页数更多的巨星走热门入口，分类翻页不限页）"""
        res = self._fetch(url)
        html = res.get("text", "")
        name = ""
        m = re.search(r"""<h1[^>]*>([\s\S]*?)</h1>""", html, re.I)
        if m:
            name = clean_label(m.group(1)).split(" JAV Videos")[0].strip()
        if not name:
            m = re.search(r"""<title>([\s\S]*?)</title>""", html, re.I)
            if m:
                name = clean_label(
                    re.split(r"\s*\|\s*", m.group(1))[0]).split(" JAV Videos")[0].strip()
        photo = ""
        m = re.search(r"""<meta[^>]+property=["']og:image["'][^>]+content=["']([^"']+)["']""",
                      html, re.I)
        if m:
            photo = self._abs(_unescape(m.group(1)))
        pagecount = self._pagecount(html, 1, 24)
        pages = min(pagecount, 6)
        # 片单各页并发抓（旧版串行抓 6 页，慢时详情调用会被 Hawk 掐超时，
        # 与片商名单串行抓同病）；单页单次抓，失败就跳过那一页
        page_html = {1: html}
        if pages > 1:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=5) as ex:
                futs = {ex.submit(self._fetch_once, url + "?page=%d" % pg): pg
                        for pg in range(2, pages + 1)}
                for f, pg in futs.items():
                    try:
                        page_html[pg] = f.result() or ""
                    except Exception:
                        page_html[pg] = ""
        froms, urls = [], []
        for pg in range(1, pages + 1):
            eps = ["%s$%s" % (c["vod_name"], c["vod_id"])
                   for c in self._cards(page_html.get(pg, ""))]
            if eps:
                froms.append("片单" if pages == 1 else "第%d页" % pg)
                urls.append("#".join(eps))
        vod = {
            "vod_id": url,
            "vod_name": name or "女优片单",
            "vod_pic": photo,
            "vod_actor": name,
            "vod_director": "",
            "vod_remarks": format_remarks("", "共 %d 页" % pagecount),
            "vod_content": name,
            "vod_play_from": "$$$".join(froms),
            "vod_play_url": "$$$".join(urls),
        }
        return {"list": [vod]}

    # ---------------- 详情 ----------------

    def detailContent(self, ids):
        raw_id = str(ids[0] if isinstance(ids, (list, tuple)) else ids).strip()
        if raw_id.startswith("shorts:"):
            return self._shorts_detail(raw_id[len("shorts:"):])
        url = self._abs(raw_id)
        if "/actress/" in url:
            return self._actress_detail(url)

        res = self._fetch(url)
        html = res.get("text", "")

        # 标题
        title = ""
        m = re.search(r"""<h1[^>]*>([\s\S]*?)</h1>""", html, re.I)
        if m:
            title = clean_label(m.group(1))
        if not title:
            m = re.search(r"""<title>([\s\S]*?)</title>""", html, re.I)
            if m:
                title = clean_label(re.split(r"\s*\|\s*", m.group(1))[0])
        if not title:
            title = "Javtiful"

        # 封面
        poster = ""
        for pat in (
            r"""<meta[^>]+property=["']og:image["'][^>]+content=["']([^"']+)["']""",
            r"""<meta[^>]+content=["']([^"']+)["'][^>]+property=["']og:image["']""",
        ):
            m = re.search(pat, html, re.I)
            if m:
                poster = self._abs(_unescape(m.group(1)))
                break
        if not poster:
            m = re.search(r"""data-front-lazy-src=["']([^"']+)["']""", html, re.I)
            if m:
                poster = self._abs(clean_pic(_unescape(m.group(1))))

        # 标签 / 简介
        tags = ""
        m = re.search(r"""<meta[^>]+name=["']keywords["'][^>]+content=["']([^"']+)["']""",
                      html, re.I)
        if m:
            tags = clean_label(m.group(1))

        desc = ""
        m = re.search(r"""<meta[^>]+name=["']description["'][^>]+content=["']([^"']+)["']""",
                      html, re.I)
        if m:
            desc = clean_label(m.group(1))

        # 演员：/actress/{slug} 链接文字
        actors = []
        for m in re.finditer(r"""href=["'][^"']*?/actress/([^"'#]+)["'][^>]*>([\s\S]*?)</a>""",
                             html, re.I):
            name = clean_label(m.group(2))
            if name and len(name) <= 24 and name not in actors:
                actors.append(name)
        actor = " / ".join(actors[:4])

        # 频道（片商）
        channel = ""
        m = re.search(r"""href=["'][^"']*?/channel/([^"'#]+)["'][^>]*>([\s\S]*?)</a>""", html, re.I)
        if m:
            channel = clean_label(m.group(2))

        # 分类
        cates = []
        for m in re.finditer(r"""href=["'][^"']*?/category/([^"'#]+)["'][^>]*>([\s\S]*?)</a>""",
                             html, re.I):
            name = clean_label(m.group(2))
            if name and len(name) <= 20 and name not in cates:
                cates.append(name)

        # 时长 / 年份 / 封面 / 播放地址：详情页带一份 JSON-LD（VideoObject），最准
        # {"name":..,"thumbnailUrl":[..],"uploadDate":"2026-10-21T02:10:32+07:00",
        #  "duration":"PT1H37M53S","embedUrl":"https://javtiful.com/embed/114820"}
        ld = self._jsonld(html)
        if not poster and ld.get("thumbnailUrl"):
            thumb = ld.get("thumbnailUrl")
            if isinstance(thumb, list) and thumb:
                thumb = thumb[0]
            poster = self._abs(_unescape(str(thumb)))
        if ld.get("name") and not title:
            title = clean_label(ld.get("name"))

        duration = self._duration(str(ld.get("duration") or ""))
        if not duration:
            m = re.search(r"""<strong>[\d]{2,3}</strong>\s*(\d{2}:\d{2}:\d{2})""", html)
            if m:
                duration = m.group(1)
        year = ""
        m = re.search(r"(\d{4})-\d{2}-\d{2}", str(ld.get("uploadDate") or ""))
        if m:
            year = m.group(1)

        views = ""
        m = re.search(r"""([\d.]+\s*[KM]?)\s*次观看""", html)
        if m:
            views = m.group(1).strip() + "次观看"

        vid = ""
        m = re.search(r"/(?:[a-z]{2}/)?video/(\d+)", url)
        if m:
            vid = m.group(1)

        # 播放地址优先用 embedUrl：页面只有 7KB，取流比拉详情页快得多
        play_page = url
        embed = str(ld.get("embedUrl") or "").strip()
        if embed:
            play_page = self._abs(embed)
        elif vid:
            play_page = self.siteUrl + "/embed/%s" % vid

        remarks = [x for x in (duration, views, cates[0] if cates else "") if x]
        content_bits = [x for x in (("标签：" + tags) if tags else "",
                                    ("片商：" + channel) if channel else "") if x]

        play_name = "高清"

        vod = {
            "vod_id": raw_id,
            "vod_name": title,
            "vod_pic": poster,
            "vod_actor": actor or self.brandActor,
            "vod_director": channel or self.brandDirector,
            "vod_year": year,
            "vod_area": " / ".join(cates[:3]),
            "vod_remarks": format_remarks(BRAND, " · ".join(remarks)),
            "vod_content": ("%s" % title)
                           + ((" | " + " / ".join(content_bits)) if content_bits else "")
                           + ((" | " + desc[:120]) if desc else ""),
            "vod_play_from": play_name,
            "vod_play_url": "正片$%s" % play_page,
        }
        return {"list": [vod]}

    # ---------------- 结构化数据 ----------------

    @staticmethod
    def _jsonld(html):
        """取 <script type="application/ld+json"> 里的 VideoObject"""
        if not html:
            return {}
        for m in re.finditer(
                r"""<script[^>]+type=["']application/ld\+json["'][^>]*>([\s\S]*?)</script>""",
                html, re.I):
            try:
                data = json.loads(m.group(1).strip())
            except Exception:
                continue
            if isinstance(data, dict) and data.get("@type") == "VideoObject":
                return data
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("@type") == "VideoObject":
                        return item
        return {}

    @staticmethod
    def _duration(iso):
        """PT1H37M53S → 01:37:53"""
        m = re.match(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$", str(iso or "").strip(), re.I)
        if not m:
            return ""
        h = int(m.group(1) or 0)
        mi = int(m.group(2) or 0)
        s = int(m.group(3) or 0)
        if h:
            return "%02d:%02d:%02d" % (h, mi, s)
        return "%02d:%02d" % (mi, s)

    # ---------------- 取流 ----------------

    @staticmethod
    def _watch_config(html):
        """取出 <script id="watch-config" type="application/json"> 里的配置"""
        if not html:
            return {}
        m = re.search(r"""<script[^>]+id=["']watch-config["'][^>]*>([\s\S]*?)</script>""",
                      html, re.I)
        if not m:
            return {}
        try:
            cfg = json.loads(m.group(1).strip())
        except Exception:
            return {}
        return cfg if isinstance(cfg, dict) else {}

    def _playback(self, vid, referer=""):
        """两步取流：/embed/{id} 领票 → POST playback 换直链"""
        res = self._fetch("/embed/%s" % vid, referer=referer)
        html = res.get("text", "")
        cfg = self._watch_config(html)

        # 详情页也带同一份配置，embed 拿不到就回落详情页
        playback = cfg.get("playback") or {}
        endpoint = str(playback.get("endpoint") or "").strip()
        ticket = str(playback.get("ticket") or "").strip()
        if not (endpoint and ticket) and referer:
            res = self._fetch(referer)
            cfg = self._watch_config(res.get("text", ""))
            playback = cfg.get("playback") or {}
            endpoint = str(playback.get("endpoint") or "").strip()
            ticket = str(playback.get("ticket") or "").strip()
        if not (endpoint and ticket):
            return [], res.get("final_url") or ""

        url = endpoint if endpoint.startswith("http") else (self.siteUrl + endpoint)
        body = urllib.parse.urlencode({"ticket": ticket}).encode("utf-8")
        headers = {
            "User-Agent": self._ua,
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "Referer": res.get("final_url") or (self.siteUrl + "/"),
            "Origin": self.siteUrl,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "close",
        }

        # 票过期（419）或网络被掐时，重新领一次票再试（票可能已被消费）
        def _refresh_ticket():
            nonlocal ticket, body
            again = self._fetch("/embed/%s" % vid, referer=referer)
            pb2 = self._watch_config(again.get("text", "")).get("playback") or {}
            if pb2.get("ticket"):
                ticket = str(pb2["ticket"])
                body = urllib.parse.urlencode({"ticket": ticket}).encode("utf-8")
                headers["Referer"] = again.get("final_url") or headers["Referer"]
                return True
            return False

        for _ in range(3):
            try:
                req = urllib.request.Request(url, data=body, headers=headers)
                with self.opener.open(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8", "ignore"))
            except urllib.error.HTTPError as e:
                if e.code == 419 and _ < 2 and _refresh_ticket():
                    continue
                return [], res.get("final_url") or ""
            except Exception:
                if _ < 2 and _refresh_ticket():
                    time.sleep(0.5)
                    continue
                return [], res.get("final_url") or ""

            sources = data.get("sources") or []
            if data.get("success") and sources:
                # 按清晰度（size）从高到低排，最高的排第一
                def _size(s):
                    try:
                        return int(s.get("size") or 0)
                    except Exception:
                        return 0
                sources = sorted(sources, key=_size, reverse=True)
                return sources, res.get("final_url") or ""
            if data.get("renewTicket"):
                ticket = str(data["renewTicket"])
                body = urllib.parse.urlencode({"ticket": ticket}).encode("utf-8")
                continue
            break
        return [], res.get("final_url") or ""

    def _quality_name(self, source, index):
        label = str(source.get("label") or "").strip()
        if not label:
            try:
                size = int(source.get("size") or 0)
                label = "%dp" % size if size else ""
            except Exception:
                label = ""
        if not label:
            src = str(source.get("src") or "")
            m = re.search(r"[/_](\d{3,4})[pP]", src)
            label = m.group(1) + "p" if m else ""
        return label or ("线路%d" % (index + 1))

    def playerContent(self, flag, id, vipFlags):
        raw = str(id or "").strip()
        page = self._abs(raw)

        # 已经拿到直链就直接放（例如外部复用本源）
        if self.isVideoFormat(raw):
            return {
                "parse": 0,
                "playUrl": "",
                "url": raw,
                "header": self._stream_header(raw, page),
            }

        vid = ""
        m = re.search(r"/(?:[a-z]{2}/)?video/(\d+)", page) or \
            re.search(r"/(?:[a-z]{2}/)?embed/(\d+)", page) or \
            re.search(r"\b(\d{4,8})\b", page)
        if m:
            vid = m.group(1)

        if vid:
            sources, final = self._playback(vid, referer=page)
            if sources:
                best = sources[0]
                stream = str(best.get("src") or "").strip().replace("\\/", "/")
                if stream:
                    return {
                        "parse": 0,
                        "playUrl": "",
                        "url": stream,
                        "header": self._stream_header(stream, final or page),
                    }

        # 换不到流就交给嗅探：打开播放页自己抓
        return {
            "parse": 1,
            "playUrl": "",
            "url": (self.siteUrl + "/embed/%s" % vid) if vid else page,
            "header": {
                "User-Agent": self._ua,
                "Referer": page,
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        }

    def _stream_header(self, stream_url, referer=""):
        """直链请求头：CDN 实测不校验 Referer，但带上更稳"""
        header = {
            "User-Agent": self._ua,
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
        }
        if referer:
            header["Referer"] = referer
        m = re.match(r"^(https?://[^/]+)", str(stream_url or ""))
        if m:
            header["Origin"] = m.group(1)
        return header

    # ---------------- 搜索 ----------------

    def searchContent(self, key, quick, pg="1"):
        self._detect_lang()
        page = fixed_int(pg, 1)
        kw = quote(str(key or "").strip(), safe="")
        path = "/search?q=%s" % kw
        return self._list(path, page)

    def searchContentPage(self, key, quick, pg="1"):
        return self.searchContent(key, quick, pg)

    # ---------------- 其他 ----------------

    def action(self, action):
        return {"msg": "ok"}

    def liveContent(self):
        return ""

    def localProxy(self, params):
        return [404, "text/plain; charset=utf-8", "Proxy not configured"]

    def destroy(self):
        self.options = {}


# ---------------------------------------------------------------- 自检

def _selftest():
    sp = Spider()
    sp.init("")
    print("源名称:", sp.getName())
    print("分区:", ", ".join([c["type_name"] for c in sp.homeContent(True)["class"]]))

    home = sp.homeVideoContent()
    print("[1] 首页推荐 %s 条" % len(home["list"]))
    for v in home["list"][:3]:
        print("    -", v["vod_name"][:40], "|", v["vod_remarks"][-28:])
        print("      pic:", v["vod_pic"][:90])

    cat = sp.categoryContent("zone_cate", "1", False, {"sub": CATEGORIES[-1]["v"]})
    print("[2] 分类「%s」第1页 %s 条, 总页 %s" % (CATEGORIES[-1]["n"], len(cat["list"]), cat["pagecount"]))
    cat2 = sp.categoryContent("zone_cate", "2", False, {"sub": CATEGORIES[-1]["v"]})
    # 站点存在同名不同片，重复判定必须按 vod_id
    dup = len(set(v["vod_id"] for v in cat["list"]) & set(v["vod_id"] for v in cat2["list"]))
    print("    第2页 %s 条, 两页重复 %s %s" % (len(cat2["list"]), dup, "✔" if not dup else "✘"))

    act = sp.categoryContent("zone_actress", "1", False, {"sub": "julia"})
    print("[3] 女优 Julia %s 条, 总页 %s" % (len(act["list"]), act["pagecount"]))
    chn = sp.categoryContent("zone_channel", "1", False, {"sub": "moodyz"})
    print("    片商 MOODYZ %s 条, 总页 %s" % (len(chn["list"]), chn["pagecount"]))

    sr = sp.searchContent("namh", False, "1")
    print("[4] 搜索 namh %s 条, 总页 %s" % (len(sr["list"]), sr["pagecount"]))

    if not home["list"]:
        print("列表为空，后面的步骤跳过")
        return

    vod = sp.detailContent([home["list"][0]["vod_id"]])["list"][0]
    print("[5] 详情  %s" % vod["vod_name"][:50])
    print("     封面:", vod["vod_pic"][:90])
    print("     演员:", vod["vod_actor"][:60], "| 片商:", vod["vod_director"][:30])
    print("     备注:", vod["vod_remarks"][:80])
    print("     线路:", vod["vod_play_from"])

    ep = vod["vod_play_url"].split("#")[0].split("$", 1)[1]
    play = sp.playerContent(vod["vod_play_from"], ep, [])
    print("[6] 取流   parse=%s" % play["parse"])
    print("     ", play["url"][:120])

    if play["url"].startswith("http"):
        code = -1
        try:
            req = urllib.request.Request(play["url"], headers=play["header"])
            req.add_header("Range", "bytes=0-1024")
            with sp.opener.open(req, timeout=15) as resp:
                code = resp.getcode()
                print("[7] 直链   HTTP %s %s" % (code, resp.headers.get("Content-Type", "")))
        except Exception as e:
            print("[7] 直链   失败", e)


if __name__ == "__main__":
    _selftest()
