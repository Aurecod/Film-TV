# -*- coding: utf-8 -*-
# 美人姬影视 app-1.mmnnxx.shop —— TVBox / 影视仓 / OK影视 Python 爬虫源  v1.0
#
# 站点结构备忘（实测）
#   列表卡片  div.thumb > a.thumb-image[href="/?play-{cid}-1-.html"]
#             img[src=封面, alt=标题]，icon-top-right=时长 / icon-bottom-right=播放量 / icon-bottom-left=日期
#   入口      最新 /?video={p}.html    分类 /?fenlei={名}&p={p}    标签 /?tag={名}&p={p}
#             搜索 /?search={词}&p={p} 明星 /?pornstar={名}&p={p} 排序统一 &rq={码}
#             分类总表 /?categories={p}.html（7页271个） 标签总表 /?tags-ch-all.html（260个）
#             明星总表 /?pornstars=md&p={p}（55页）
#   总页数    <h1>标题 {总页} / {当前页}</h1>
#   详情      h1=标题；.categories-row a.linkss 给分类与标签（年份在标签里）；.gline 给日期/播放量/时长；cid 在 cid="{cid}"
#   播放      /?api=play&id={cid} 返回 var config={..."url":"...index.m3u8"...}
#   封面      只有列表页有（详情页与播放接口的 pic 均为空），故封面随 vod_id 一起带过去
#   去广告    站点向 m3u8 里注入来自别的视频目录的 ppvod 广告段，并在页面塞广告 iframe/script；
#             本源按“分片是否落在本片自己的目录下”剔除广告段，并清洗页面上的广告标签
#
import re
import sys
import threading
from html import unescape
from base64 import urlsafe_b64encode, urlsafe_b64decode
from urllib.parse import quote, urljoin, urlparse
import requests
sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    HOST = "https://app-1.mmnnxx.shop"
    UA = "Mozilla/5.0 (Linux; Android 12; SM-G975F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36"
    RQ = [("db", "最新点播"), ("h", "最多点击"), ("z", "最多点赞"), ("s", "最多收藏"), ("p", "最多评论"), ("d", "最多弹幕"), ("bs", "播放时长")]
    AD = ("ads.xnavxx.com", "ad.kavxx.com", "add-aps.98765428.xyz", "histats.com", "addtoany.com", "/add.php", "/adds.php", "/cull.php")
    PAGE_MAX = 12
    STAR_PAGE = 2
    FALLBACK_CAT = "日韩无码"

    def getName(self):
        return "美人姬"

    def init(self, extend=""):
        self.headers = {"User-Agent": self.UA, "Referer": self.HOST + "/", "Accept-Language": "zh-CN,zh;q=0.9"}
        self.hls = {"User-Agent": self.UA, "Referer": self.HOST + "/"}
        self._cache = {}
        return {}

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def action(self, action):
        pass

    def destroy(self):
        pass

    def _clean(self, h):
        if not h:
            return ""
        h = re.sub(r'<script\b[^>]*>.*?</script>', lambda m: "" if any(a in m.group(0) for a in self.AD) else m.group(0), h, flags=re.I | re.S)
        h = re.sub(r'<iframe\b[^>]*>.*?</iframe>', lambda m: "" if any(a in m.group(0) for a in self.AD) else m.group(0), h, flags=re.I | re.S)
        return re.sub(r'<noscript\b[^>]*>.*?</noscript>', lambda m: "" if any(a in m.group(0) for a in self.AD) else m.group(0), h, flags=re.I | re.S)

    def _get(self, url, headers=None, raw=False):
        try:
            r = requests.get(url, headers=headers or self.headers, timeout=20)
            t = r.content if raw else r.text
            return t if raw else self._clean(t)
        except Exception:
            return b"" if raw else ""

    def _multi(self, urls):
        out = {}

        def work(u):
            try:
                out[u] = self._get(u)
            except Exception:
                out[u] = ""

        ts = [threading.Thread(target=work, args=(u,)) for u in urls]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        return out

    @staticmethod
    def _pages(h, pg=1):
        m = re.search(r'<h1[^>]*>(.*?)</h1>', h or "", re.S)
        if m:
            n = re.findall(r'(\d+)\s*/\s*(\d+)', re.sub(r'<[^>]+>', ' ', m.group(1)))
            if n:
                return max(1, int(n[0][0]))
        return int(pg) if str(pg).isdigit() else 1

    @staticmethod
    def _div(seg, cls):
        m = re.search(r'class="%s"[^>]*>(.*?)</div>' % cls, seg, re.S)
        return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', unescape(m.group(1)))).replace('\xa0', ' ').strip() if m else ""

    @staticmethod
    def _attr(seg, key):
        m = re.search(r'\b%s="([^"]*)"' % key, seg)
        return unescape(m.group(1)).strip() if m else ""

    def _list(self, h):
        out = []
        for seg in (h or "").split('<div class="thumb">')[1:]:
            e = seg.find('</a>')
            seg = seg[:e + 4] if e > 0 else seg[:1500]
            m = re.search(r'href="[^"]*?\?play-(\d+)-', seg)
            if not m:
                continue
            cid = m.group(1)
            pic = self._attr(seg, 'src')
            name = self._attr(seg, 'alt')
            if not name:
                continue
            rm = " ".join(x for x in (self._div(seg, "icon-top-right"), self._div(seg, "icon-bottom-left")) if x)
            out.append({
                "vod_id": "%s|%s" % (cid, pic),
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": rm,
                "style": {"type": "rect", "ratio": 1.33},
            })
        return out

    def _categories(self):
        if "cats" in self._cache:
            return self._cache["cats"]
        first = self._get("%s/?categories=1.html" % self.HOST)
        n = min(self._pages(first, 1), self.PAGE_MAX)
        urls = ["%s/?categories=%d.html" % (self.HOST, i) for i in range(2, n + 1)]
        d = self._multi(urls) if urls else {}
        pages = [first] + [d.get(u, "") for u in urls]
        c = []
        for h in pages:
            for m in re.finditer(r'href="/\?fenlei=([^"&]+)"', h or ""):
                v = unescape(m.group(1)).strip()
                if v and v not in c:
                    c.append(v)
        self._cache["cats"] = c or [self.FALLBACK_CAT]
        return self._cache["cats"]

    def _tags(self):
        if "tags" in self._cache:
            return self._cache["tags"]
        h = self._get("%s/?tags-ch-all.html" % self.HOST)
        t = []
        for m in re.finditer(r'href="/\?tag=([^"&]+)"', h or ""):
            v = unescape(m.group(1)).strip()
            if v and v not in t:
                t.append(v)
        self._cache["tags"] = t
        return t

    def _stars(self):
        if "stars" in self._cache:
            return self._cache["stars"]
        urls = ["%s/?pornstars=md&p=%d" % (self.HOST, i) for i in range(1, self.STAR_PAGE + 1)]
        s = []
        for h in self._multi(urls).values():
            for m in re.finditer(r'href="/\?pornstar=([^"&]+)"', h or ""):
                v = unescape(m.group(1)).strip()
                if v and v not in s:
                    s.append(v)
        self._cache["stars"] = s
        return s

    def homeContent(self, filter):
        classes = [
            {"type_name": "最新视频", "type_id": "video"},
            {"type_name": "类型", "type_id": "fenlei"},
            {"type_name": "标签", "type_id": "tag"},
            {"type_name": "明星", "type_id": "pornstar"},
        ]
        sort = [{"n": n, "v": v} for v, n in self.RQ]
        cats = [{"n": c, "v": c} for c in self._categories()]
        tags = [{"n": t, "v": t} for t in self._tags()]
        stars = [{"n": s, "v": s} for s in self._stars()]
        filters = {
            "video": [{"key": "rq", "name": "排序", "value": sort}],
            "fenlei": [{"key": "fenlei", "name": "类型", "value": cats}, {"key": "rq", "name": "排序", "value": sort}],
            "tag": [{"key": "tag", "name": "标签", "value": tags}, {"key": "rq", "name": "排序", "value": sort}],
            "pornstar": [{"key": "pornstar", "name": "明星", "value": stars}],
        }
        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        return {"list": self._list(self._get(self.HOST + "/"))}

    def _rq(self, ext):
        v = str(ext.get("rq") or "").strip()
        return "&rq=" + quote(v) if v else ""

    def categoryContent(self, tid, pg, filter, extend):
        pg = str(pg or 1)
        ext = extend or {}
        if tid == "video":
            url = "%s/?video=%s.html%s" % (self.HOST, pg, self._rq(ext))
        elif tid == "fenlei":
            url = "%s/?fenlei=%s&p=%s%s" % (self.HOST, quote(str(ext.get("fenlei") or self._categories()[0])), pg, self._rq(ext))
        elif tid == "tag":
            url = "%s/?tag=%s&p=%s%s" % (self.HOST, quote(str(ext.get("tag") or (self._tags() or [""])[0])), pg, self._rq(ext))
        elif tid == "pornstar":
            url = "%s/?pornstar=%s&p=%s" % (self.HOST, quote(str(ext.get("pornstar") or (self._stars() or [""])[0])), pg)
        else:
            url = "%s/?video=%s.html" % (self.HOST, pg)
        h = self._get(url)
        lst = self._list(h)
        return {"list": lst, "page": int(pg), "pagecount": self._pages(h, pg), "limit": len(lst) or 30, "total": 999999}

    def detailContent(self, ids):
        raw = (ids or [""])[0]
        cid, _, pic = str(raw).partition("|")
        cid = re.sub(r'\D', '', cid) or cid
        h = self._get("%s/?play-%s-1-.html" % (self.HOST, cid))
        seg = h[h.find('<h1'):h.find('相关视频')] if '<h1' in h and '相关视频' in h else h
        title = ""
        m = re.search(r'<h1[^>]*>(.*?)</h1>', seg, re.S)
        if m:
            title = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', unescape(m.group(1)))).strip()
        fen = re.findall(r'href="/\?fenlei=([^"&]+)"', seg)
        tgs = []
        for m in re.finditer(r'href="/\?tag=([^"&]+)"', seg):
            v = unescape(m.group(1)).strip()
            if v and v not in tgs:
                tgs.append(v)
        cls = unescape(fen[0]).strip() if fen else ""
        year = ""
        for t in tgs:
            if re.fullmatch(r'(19|20)\d{2}', t):
                year = t
                break
        gl = [re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', x)).replace('\xa0', ' ').strip() for x in re.findall(r'<span class="gline">(.*?)</span>', seg, re.S)]
        date = gl[0] if len(gl) > 0 else ""
        views = gl[1] if len(gl) > 1 else ""
        dur = gl[2] if len(gl) > 2 else ""
        content = " | ".join(x for x in [
            ("类型：" + cls) if cls else "",
            ("标签：" + "、".join(tgs)) if tgs else "",
            ("时长：" + dur + "分钟") if dur else "",
            ("播放：" + views) if views else "",
            ("上传：" + date) if date else "",
        ] if x)
        vod = {
            "vod_id": raw,
            "vod_name": title,
            "vod_pic": pic,
            "vod_year": year,
            "vod_class": cls,
            "vod_tag": ",".join(tgs),
            "vod_remarks": " ".join(x for x in (dur + "m" if dur else "", date) if x),
            "vod_content": content,
            "vod_play_from": "美人姬",
            "vod_play_url": "正片$" + cid,
        }
        return {"list": [vod]}

    def searchContent(self, key, quick, pg="1", extend=None):
        url = "%s/?search=%s&p=%s%s" % (self.HOST, quote(str(key)), pg, self._rq(extend or {}))
        h = self._get(url)
        lst = self._list(h)
        return {"list": lst, "page": int(pg), "pagecount": self._pages(h, pg)}

    def _m3u8(self, cid):
        h = self._get("%s/?api=play&id=%s" % (self.HOST, cid))
        m = re.search(r'"url"\s*:\s*"([^"]+)"', h or "")
        return m.group(1).replace('\\/', '/') if m else ""

    def playerContent(self, flag, id, vipFlags):
        cid = str(id).split("|")[0].strip()
        url = self._m3u8(cid)
        try:
            p = (self.getProxyUrl() or "").strip()
        except Exception:
            p = "http://127.0.0.1:9978/proxy?do=py"
        if url and p:
            url = p + "&url=" + urlsafe_b64encode(url.encode('utf-8')).decode('utf-8').rstrip("=") + "&type=m3u8"
        return {"parse": 0, "url": url, "header": self.hls}

    def localProxy(self, param):
        if (param or {}).get("type") == "m3u8":
            return [200, "application/vnd.apple.mpegurl", self._fixm3u8(self._dec(param.get("url", "")))]
        return [404, "text/plain", ""]

    @staticmethod
    def _dec(s):
        s = str(s or "").replace(" ", "+")
        s += "=" * (-len(s) % 4)
        try:
            return urlsafe_b64decode(s.encode('utf-8')).decode('utf-8', 'ignore')
        except Exception:
            return ""

    def _text(self, url):
        try:
            return requests.get(url, headers=self.hls, timeout=20).text
        except Exception:
            return ""

    def _fixm3u8(self, url):
        if not str(url).startswith("http"):
            return ""
        txt = self._text(url)
        if "#EXTM3U" not in txt:
            return ""
        if "#EXT-X-STREAM-INF" in txt:
            for line in txt.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    v = urljoin(url, line)
                    t = self._text(v)
                    if t:
                        url, txt = v, t
                    break
        own = "/".join(urlparse(url).path.split("/")[:3])
        out = []
        for line in txt.splitlines():
            s = line.strip()
            if not s:
                continue
            if s.startswith("#"):
                if s.startswith("#EXT-X-DISCONTINUITY") or "ad-injected" in s:
                    continue
                if s.startswith("#EXT-X-KEY") or s.startswith("#EXT-X-MAP"):
                    s = re.sub(r'URI="([^"]+)"', lambda m: 'URI="%s"' % urljoin(url, m.group(1)), s)
                out.append(s)
                continue
            full = urljoin(url, s)
            if own and own not in full:
                continue
            out.append(full)
        if not [x for x in out if not x.startswith("#")]:
            out = [urljoin(url, x.strip()) if not x.strip().startswith("#") else x.strip() for x in txt.splitlines() if x.strip()]
        if "#EXT-X-ENDLIST" not in out:
            out.append("#EXT-X-ENDLIST")
        return "\n".join(out)
