# -*- coding: utf-8 -*-
"""
蝙蝠视频 TVBox 爬虫（https://257915.xyz/）
站点分析：
  - 自研模板站，全站双层混淆：外层整页 base64 需反转后解码，
    内层文本分片 document.write(d('base64'))，分类名/标题中掺入
    <span style="display:none"> 干扰字符
  - 5 个分组 40 个分类：线路1~4（/video.php 在线播放），磁力1（/torrent.php 磁力链）
  - 列表 /list.php?id={tid}&page={pg}，搜索 /search.php?content={kw}&type=1|2
  - 播放：详情页 playFilteredHLS('video', play.php 直链) 直接返回 AES-128 m3u8，
    无需 token / Referer，parse:0
"""
import re
import base64

try:
    import requests as _requests
except Exception:
    _requests = None


class Spider:
    def __init__(self):
        self.site = "https://257915.xyz"
        self.name = "蝙蝠视频"
        self.header = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 13; SM-S9080) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            "Referer": self.site + "/",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        self.s = self.session = self.sess = _requests.Session() if _requests else None
        self._extend = {}
        self._home = None
        # ---- 站点结构 ----
        self.cat_scope = "dl"
        self.cat_href_re = r'<a[^>]+href="(/list\.php\?id=\d+[^"]*)"[^>]*>(.*?)</a>'
        self.list_scope = r"<dl>(.*?)</dl>"
        self.detail_tpl = "{site}{path}"
        self.play_tpl = "playFilteredHLS"
        self.m3u8_var = "regex"
        self.search_tpl = "{site}/search.php?content={key}&type={type}"
        self.page_mode = "page"

    def getDependence(self):
        return []

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        if not url:
            return False
        u = str(url).lower()
        return u.endswith((".m3u8", ".mp4", ".flv", ".mkv", ".ts", ".avi")) or "m3u8" in u

    def destroy(self):
        pass

    def action(self, action):
        return {}

    def _get(self, url, referer=None):
        h = dict(self.header)
        if referer:
            h["Referer"] = referer
        if self.s is not None:
            try:
                r = self.s.get(url, headers=h, timeout=12, allow_redirects=True)
                if r.status_code < 400:
                    return r.text
            except Exception:
                pass
        try:
            import urllib.request
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=12) as resp:
                return resp.read().decode("utf-8", "ignore")
        except Exception:
            return ""

    def _u(self, u):
        if not u:
            return u
        u = u.strip()
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("http"):
            return u
        if u.startswith("/"):
            m = re.match(r"(https?://[^/]+)", self.site)
            return (m.group(1) if m else self.site) + u
        return self.site.rstrip("/") + "/" + u.lstrip("/")

    def _unescape(self, s):
        import html as _h
        return _h.unescape(s) if s else s

    def _page(self, url):
        """抓取并还原混淆页面：外层反转 base64 -> 内层 d() 分片 -> 去隐藏干扰 span"""
        html = self._get(url)
        if not html:
            return ""
        m = re.search(r"\w+\('([A-Za-z0-9+/=]{1000,})", html)
        if m:
            try:
                raw = base64.b64decode(m.group(1)[::-1])
                i = raw.find(b"<!DOCTYPE")
                page = raw[i:].decode("utf-8", "ignore") if i >= 0 else raw.decode("utf-8", "ignore")
            except Exception:
                page = html
        else:
            page = html

        def _d(mo):
            try:
                return base64.b64decode(mo.group(1)).decode("utf-8", "ignore")
            except Exception:
                return ""

        page = re.sub(r"document\.write\(d\('([^']+)'\)\);", _d, page)
        page = re.sub(r"<span[^>]*?display\s*:\s*none[^>]*?>.*?</span>", "", page, flags=re.S)
        return page

    def _clean_text(self, s):
        s = re.sub(r"<[^>]+>", "", s or "")
        s = self._unescape(s)
        return re.sub(r"\s+", " ", s).strip()

    def _cats(self):
        groups = [
            ("线路1", [("64360061", "中文字幕"), ("64370061", "网红主播"), ("64380061", "成人动漫"),
                       ("64390061", "欧美情色"), ("64400061", "国模私拍"), ("64430061", "韩国伦理"),
                       ("64170061", "国产情色"), ("64180061", "日本无码")]),
            ("线路2", [("64170041", "日韩无码"), ("64190041", "欧美精品"), ("64200041", "国产精品"),
                       ("64340041", "中文字幕"), ("64360041", "动漫精品"), ("64390041", "日韩精品"),
                       ("64430041", "自拍偷拍"), ("64580041", "大秀视频")]),
            ("线路3", [("64360111", "精品推荐"), ("64380111", "国产色情"), ("64390111", "主播直播"),
                       ("64630111", "91探花"), ("64750111", "传媒出品"), ("64500111", "自拍偷拍"),
                       ("64530111", "日本精品"), ("64460111", "欧美精品")]),
            ("线路4", [("64170031", "国产自拍"), ("64180031", "欧美极品"), ("64190031", "日韩无码"),
                       ("64360031", "中文字幕"), ("64370031", "动漫精品"), ("64380031", "极骚萝莉"),
                       ("64410031", "三级自慰"), ("64420031", "强奸乱伦")]),
            ("磁力1", [("64169922", "国产专区"), ("64179922", "日本有码"), ("64189922", "日本无码"),
                       ("64199922", "欧美色情"), ("64209922", "传媒作品"), ("64219922", "探花直播"),
                       ("64229922", "网黄女神"), ("64239922", "绿帽淫妻")]),
        ]
        cats = []
        for gname, items in groups:
            for tid, name in items:
                cats.append({"type_id": tid, "type_name": "%s·%s" % (gname, name)})
        return cats

    def _items(self, html, base=None):
        vods = []
        for m in re.finditer(r"<dl>(.*?)</dl>", html, re.S):
            dl = m.group(1)
            a = re.search(r'<a[^>]+href="((?:/video\.php|/torrent\.php)\?id=\d+)"', dl)
            if not a:
                continue
            path = a.group(1)
            im = re.search(r'<img[^>]+src="([^"]+)"', dl)
            pic = self._u(im.group(1)) if im else ""
            t = re.search(r"<h3>(.*?)</h3>", dl, re.S)
            name = self._clean_text(t.group(1)) if t else ""
            if not name:
                continue
            vods.append({
                "vod_id": path + "|" + pic,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": "",
            })
        return vods

    def init(self, extend=""):
        try:
            import json
            cfg = json.loads(extend) if extend else {}
            if isinstance(cfg, dict):
                self._extend = cfg
                if cfg.get("host"):
                    self.site = cfg["host"].rstrip("/")
                    self.header["Referer"] = self.site + "/"
        except Exception:
            pass
        return {}

    def homeContent(self, filter=None):
        cats = self._cats()
        recs = []
        try:
            html = self._page(self.site + "/")
            recs = self._items(html)[:18]
        except Exception:
            pass
        return {"class": cats, "list": recs, "filters": {}}

    def homeVideoContent(self):
        return {}

    def _cat_url(self, tid, pg):
        tid = str(tid).strip()
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1
        return "%s/list.php?id=%s&page=%d" % (self.site, tid, pg)

    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        html = self._page(self._cat_url(tid, pg))
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        if not html:
            return {"list": [], "page": pg, "pagecount": 9999, "limit": 20, "total": 999999}
        vods = self._items(html)
        return {"list": vods, "page": pg, "pagecount": 9999, "limit": 20, "total": 999999}

    def detailContent(self, ids):
        raw = ids[0] if isinstance(ids, (list, tuple)) else ids
        raw = str(raw or "")
        path, _, pic = raw.partition("|")
        html = self._page(self._u(path))
        vod = {"vod_id": path, "vod_name": "", "vod_pic": pic, "vod_content": "",
               "vod_play_from": "", "vod_play_url": ""}
        if not html:
            return {"list": [vod]}
        m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
        if m:
            vod["vod_name"] = self._clean_text(m.group(1))
        if "/torrent.php" in path:
            mm = re.search(r"magnet:\?[^\s\"'<>]+", html)
            info = []
            for k, v in re.findall(r"【影片(..)】：</script>([^<]*)", html):
                v = v.replace("\\n", "").strip()
                if v:
                    info.append("%s:%s" % (k, v))
            if info:
                vod["vod_content"] = " ".join(info)
            if mm:
                vod["vod_play_from"] = "磁力链接"
                vod["vod_play_url"] = "磁力$" + mm.group(0)
        else:
            m2 = re.search(r"playFilteredHLS\('video',\s*'([^']+)'", html)
            if m2:
                vod["vod_play_from"] = "在线播放"
                vod["vod_play_url"] = "正片$" + m2.group(1).strip()
        return {"list": [vod]}

    def searchContent(self, key, quick=False, pg="1"):
        from urllib.parse import quote
        vods, seen = [], set()
        for stype in ("1", "2"):
            url = self.search_tpl.replace("{site}", self.site).replace("{key}", quote(str(key))).replace("{type}", stype)
            html = self._page(url)
            if not html:
                continue
            for v in self._items(html):
                vid = v["vod_id"]
                if vid not in seen:
                    seen.add(vid)
                    vods.append(v)
        return {"list": vods}

    def playerContent(self, flag, ids, vipFlags=None):
        url = ids[0] if isinstance(ids, (list, tuple)) else ids
        url = str(url or "").strip()
        if "$" in url:
            url = url.split("$")[-1]
        url = url.strip()
        if not url:
            return {"parse": 0, "url": "", "header": dict(self.header)}
        return {"parse": 0, "url": url, "header": dict(self.header)}

    def localProxy(self, param):
        u = param.get("url", "") if isinstance(param, dict) else ""
        if not u:
            return [403, "text/plain", b"", None]
        h = dict(self.header)
        if self.s is not None:
            try:
                r = self.s.get(u, headers=h, timeout=15)
                return [200, r.headers.get("Content-Type", "application/octet-stream"), r.content, None]
            except Exception:
                pass
        try:
            import urllib.request
            req = urllib.request.Request(u, headers=h)
            with urllib.request.urlopen(req, timeout=15) as resp:
                return [200, resp.headers.get("Content-Type", "application/octet-stream"), resp.read(), None]
        except Exception:
            return [403, "text/plain", b"", None]
