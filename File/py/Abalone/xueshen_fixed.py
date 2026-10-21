# -*- coding: utf-8 -*-
# 学生合集站 (r2ymsjsf.student35.xyz) - student 模板
# 2026-10-08 封面代理修复版
# 修复：
#  1. 封面走 localProxy 代理（CDN 有反爬挑战，直链 403/JS挑战）
#  2. localProxy 真正下载图片并返回二进制（列表契约 [code, ctype, content, header, base64flag]）
#  3. _extract_pic 兜底 src；detail 封面同步走代理
#  4. PIC_INLINE=0 保持直链模式，但改为代理 URL（getProxyUrl+siteKey）
import re
import ssl
import gzip
import zlib
import json
import time
import base64
import urllib.request
import urllib.parse
import html

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass


class Spider(BaseSpider):

    def getName(self):
        return "学生合集"

    def init(self, extend=""):
        # extend 是 FongMi 传入的站点配置 JSON，含 key 字段（如 "local_xueshen"）
        # 用于 localProxy 的 siteKey 路由
        self._site_key = self.getName()  # 默认用显示名
        if extend:
            try:
                cfg = json.loads(extend)
                if isinstance(cfg, dict) and cfg.get("key"):
                    self._site_key = cfg["key"]
            except Exception:
                pass

    def __init__(self):
        super(Spider, self).__init__()
        self.site_url = "https://r2ymsjsf.student35.xyz"
        self._last_req = 0.0
        self._throttle = 1.0
        self._m3u8_cache = {}
        self._pic_cache = {}
        try:
            self.ssl_ctx = ssl._create_unverified_context()
        except Exception:
            self.ssl_ctx = None
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 12) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Mobile Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                      "image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
            "Referer": self.site_url + "/"
        }

    def _fetch(self, url, timeout=10, retries=2):
        gap = time.time() - self._last_req
        if gap < self._throttle:
            time.sleep(self._throttle - gap)
        self._last_req = time.time()
        req = urllib.request.Request(url, headers=self.headers)
        last_err = ""
        for attempt in range(retries + 1):
            try:
                if self.ssl_ctx:
                    resp = urllib.request.urlopen(
                        req, context=self.ssl_ctx, timeout=timeout)
                else:
                    resp = urllib.request.urlopen(req, timeout=timeout)
                raw = resp.read()
                enc = resp.headers.get("Content-Encoding", "").lower()
                if "gzip" in enc:
                    raw = gzip.decompress(raw)
                elif "deflate" in enc:
                    raw = zlib.decompress(raw)
                text = ""
                for charset in ("utf-8", "gbk", "gb2312", "iso-8859-1"):
                    try:
                        text = raw.decode(charset)
                        break
                    except Exception:
                        continue
                return {"success": True, "html": text,
                        "real_url": resp.geturl()}
            except Exception as e:
                last_err = str(e)
                if attempt < retries:
                    time.sleep(0.5)
        return {"success": False, "html": "", "error": last_err}

    def _fetch_bytes(self, url, timeout=10, extra_headers=None):
        hdrs = {
            "User-Agent": self.headers["User-Agent"],
            "Referer": self.site_url + "/",
        }
        if extra_headers:
            hdrs.update(extra_headers)
        req = urllib.request.Request(url, headers=hdrs)
        if self.ssl_ctx:
            with urllib.request.urlopen(req, context=self.ssl_ctx,
                                        timeout=timeout) as resp:
                return resp.read(), resp.headers.get("Content-Type", "image/jpeg")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(), resp.headers.get("Content-Type", "image/jpeg")

    def _proxy_pic_url(self, pic_url):
        """
        构造 localProxy 代理 URL。
        FongMi: getProxyUrl() 返回 http://127.0.0.1:PORT/proxy?do=py
        加上 siteKey 让 BaseLoader.proxy 路由到本 spider 的 localProxy。
        siteKey 取自 init(extend) 解析的配置 key（如 local_xueshen），
        兜底用 getName()。
        """
        if not pic_url or not pic_url.startswith("http"):
            return pic_url
        encoded = urllib.parse.quote(pic_url, safe="")
        site_key = urllib.parse.quote(getattr(self, "_site_key", self.getName()))
        # 优先用基类的 getProxyUrl()（FongMi 真机可用），沙箱兜底相对路径
        base = ""
        try:
            base = self.getProxyUrl()  # FongMi BaseSpider 提供
        except Exception:
            base = ""
        if base:
            # base 已含 do=py，追加参数
            sep = "&" if "?" in base else "?"
            return "%s%surl=%s&siteKey=%s" % (base, sep, encoded, site_key)
        # 沙箱/无 getProxyUrl 环境：相对路径，靠 App 补全
        return "/proxy?url=%s&siteKey=%s" % (encoded, site_key)

    def homeContent(self, filter):
        classes = [
            {"type_id": "20", "type_name": "媚黑母狗"}, {"type_id": "25", "type_name": "3D动漫"},
            {"type_id": "26", "type_name": "剧情故事"}, {"type_id": "55", "type_name": "偷拍自拍"},
            {"type_id": "57", "type_name": "淫乱学妹"}, {"type_id": "58", "type_name": "乱伦三观"},
            {"type_id": "60", "type_name": "嫖妓过程"}, {"type_id": "61", "type_name": "主播网红"},
            {"type_id": "63", "type_name": "国产制作"}, {"type_id": "65", "type_name": "黑料打烊"},
            {"type_id": "80", "type_name": "高清无码"}, {"type_id": "81", "type_name": "中文字幕"},
            {"type_id": "92", "type_name": "国产精品"}, {"type_id": "93", "type_name": "华语AV"},
            {"type_id": "94", "type_name": "黑料吃瓜"}, {"type_id": "95", "type_name": "欧美精品"},
            {"type_id": "96", "type_name": "动漫禁漫"}, {"type_id": "97", "type_name": "学生合集"},
            {"type_id": "98", "type_name": "乱伦精品"}, {"type_id": "99", "type_name": "探花约炮"},
            {"type_id": "100", "type_name": "日本无码"}, {"type_id": "101", "type_name": "日本有码"},
            {"type_id": "102", "type_name": "主播网红2"}, {"type_id": "103", "type_name": "日本素人"},
            {"type_id": "105", "type_name": "麻豆视频"}, {"type_id": "106", "type_name": "91制片厂"},
            {"type_id": "107", "type_name": "天美传媒"}, {"type_id": "108", "type_name": "蜜桃传媒"},
            {"type_id": "110", "type_name": "星空传媒"}, {"type_id": "111", "type_name": "精东影业"},
            {"type_id": "112", "type_name": "乐播传媒"}, {"type_id": "113", "type_name": "兔子先生"},
        ]
        return {"class": classes, "filters": {}}

    def homeVideoContent(self):
        res = self._fetch(f"{self.site_url}/vodtype/57.html")
        cards = self._parse_vod_list(res.get("html", "")) if res.get("success") else []
        self._apply_proxy_covers(cards)
        return {"list": cards}

    def _apply_proxy_covers(self, cards):
        """把 vod_pic 替换为代理 URL，避免 CDN 反爬"""
        for c in cards:
            pic = c.get("vod_pic", "")
            if pic and pic.startswith("http") and "loading.gif" not in pic:
                c["vod_pic"] = self._proxy_pic_url(pic)

    def _norm_pic(self, cand):
        if not cand:
            return ""
        cand = cand.strip()
        if cand.startswith("//"):
            return "https:" + cand
        if cand.startswith("/"):
            return urllib.parse.urljoin(self.site_url, cand)
        return cand

    def _extract_pic(self, inner):
        for im in re.finditer(r'<img[^>]+>', inner, re.I):
            tag = im.group(0)
            for attr in ('data-src', 'data-original', 'data-lazy-src',
                         'data-echo', 'data-url', 'srcset', 'src'):
                am = re.search(rf'{attr}\s*=\s*["\']([^"\']+)["\']', tag, re.I)
                if not am:
                    continue
                cand = am.group(1).strip().split(",")[0].split()[0]
                if not cand or cand.startswith('data:'):
                    continue
                low = cand.lower()
                if 'loading.gif' in low or 'placeholder' in low \
                        or 'blank.' in low or 'pixel.' in low \
                        or '/template/' in low:
                    continue
                return self._norm_pic(cand)
        return ""

    def _parse_vod_list(self, html_data):
        cards = []
        if not html_data:
            return cards
        blocks = re.findall(
            r'<li>\s*<a[^>]*href=["\']/voddetail/(\d+)\.html["\'][^>]*>(.*?)</a>\s*</li>',
            html_data, re.I | re.S)
        seen = set()
        for vid, inner in blocks:
            if vid in seen:
                continue
            seen.add(vid)

            title = ""
            hm = re.search(r'<h2[^>]*>(.*?)</h2>', inner, re.I | re.S)
            if hm:
                title = re.sub(r'<[^>]+>', '', hm.group(1)).strip()
            if not title:
                am = re.search(r'alt=["\']([^"\']+)["\']', inner, re.I)
                if am:
                    title = am.group(1).strip()
            if not title:
                continue
            title = html.unescape(title)

            pic = self._extract_pic(inner)

            cards.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": "学生合集",
                "style": {"type": "rect", "ratio": 1.78}
            })
        return cards

    def categoryContent(self, tid, pg, filter, extend):
        pg_int = int(pg) if str(pg).isdigit() else 1
        if pg_int <= 1:
            url = f"{self.site_url}/vodtype/{tid}.html"
        else:
            url = f"{self.site_url}/vodtype/{tid}-{pg_int}.html"
        res = self._fetch(url)
        cards = self._parse_vod_list(res.get("html", "")) if res.get("success") else []
        self._apply_proxy_covers(cards)
        return {
            "list": cards,
            "page": pg_int,
            "pagecount": pg_int + 1 if len(cards) >= 24 else pg_int,
            "limit": len(cards),
            "total": 9999
        }

    def _player_aaaa(self, h):
        start = h.find("var player_aaaa")
        if start < 0:
            return None
        start = h.find("{", start)
        if start < 0:
            return None
        depth, i = start, start
        while i < len(h):
            if h[i] == "{":
                depth += 1
            elif h[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        try:
            return json.loads(h[start:i + 1])
        except Exception:
            return None

    def detailContent(self, ids):
        vid = ids[0] if isinstance(ids, list) else ids
        res = self._fetch(f"{self.site_url}/voddetail/{vid}.html")
        h = res.get("html", "")

        title = ""
        tm = re.search(r'<title>(.*?)</title>', h, re.I | re.S)
        if tm:
            title = html.unescape(tm.group(1)).split("详情介绍")[0].strip()

        pic = ""
        pm = re.search(r'<img[^>]+class=["\'][^"\']*video-img[^"\']*["\'][^>]*>', h, re.I)
        if pm:
            pic = self._extract_pic(pm.group(0))
        if not pic:
            pm = re.search(r'<img[^>]+data-src=["\'][^"\']+["\'][^>]*>', h, re.I)
            if pm:
                pic = self._extract_pic(pm.group(0))
        pic = self._norm_pic(pic)
        if pic and pic.startswith("http"):
            pic = self._proxy_pic_url(pic)

        episodes = []
        for m in re.finditer(r'href=["\'](/vodplay/\d+-1-1\.html)["\']', h, re.I):
            episodes.append(f"正片${self.site_url}{m.group(1)}")
            break
        if not episodes:
            episodes.append(f"正片${self.site_url}/vodplay/{vid}-1-1.html")

        vod = {
            "vod_id": vid,
            "vod_name": html.unescape(title) if title else "学生合集",
            "vod_pic": pic,
            "type_name": "学生合集",
            "vod_remarks": "学生合集",
            "vod_content": "学生合集",
            "vod_play_from": "学生线路",
            "vod_play_url": "#".join(episodes)
        }
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        vid = str(id)
        m = re.search(r"/vodplay/(\d+)-", vid)
        if m:
            vid = m.group(1)
        play_url = id if id.startswith("http") else self.site_url + id
        res = self._fetch(play_url)
        h = res.get("html", "")
        target = ""
        if h:
            cfg = self._player_aaaa(h)
            if cfg and cfg.get("url"):
                target = cfg["url"].replace("\\/", "/").strip()
                if "%" in target:
                    target = urllib.parse.unquote(target)
            if not target:
                ms = re.findall(r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', h, re.I)
                if ms:
                    target = ms[0]
        if target and (".m3u8" in target or ".mp4" in target):
            self._m3u8_cache[vid] = target
        elif vid in self._m3u8_cache:
            target = self._m3u8_cache[vid]
        return {
            "parse": 0 if target else 1,
            "playUrl": "",
            "url": target if target else play_url,
            "header": {
                "User-Agent": self.headers["User-Agent"],
                "Referer": play_url
            }
        }

    def searchContent(self, key, quick, pg="1"):
        pg_int = int(pg) if str(pg).isdigit() else 1
        ek = urllib.parse.quote(key)
        if pg_int <= 1:
            url = f"{self.site_url}/vodsearch/{ek}-------------.html"
        else:
            url = f"{self.site_url}/vodsearch/{ek}----------{pg_int}---.html"
        res = self._fetch(url)
        cards = self._parse_vod_list(res.get("html", "")) if res.get("success") else []
        self._apply_proxy_covers(cards)
        return {
            "list": cards,
            "page": pg_int,
            "pagecount": pg_int + 1 if len(cards) >= 24 else pg_int,
            "limit": len(cards),
            "total": 9999
        }

    def action(self, action):
        return {}

    def liveContent(self):
        return {}

    def localProxy(self, params):
        """
        FongMi/TVBox 契约：返回 [code, content_type, content, header_dict, base64flag]
        - content: bytes (base64flag=0) 或 base64 字符串
        - header_dict: 可选，透传给下游
        兼容参数：url / s / v （不同版本键名不同）
        """
        # 兼容 dict 和 JSON 字符串
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except Exception:
                params = {}
        if not isinstance(params, dict):
            params = {}

        url = params.get("url") or params.get("s") or params.get("v") or ""
        if not url:
            return [400, "text/plain", b"missing url param", {}, 0]

        try:
            raw, ctype = self._fetch_bytes(url, timeout=10)
            if not raw:
                return [404, "text/plain", b"empty response", {}, 0]
            # 修正 content-type
            if not ctype or ctype == "text/html":
                if raw[:2] == b"\xff\xd8":
                    ctype = "image/jpeg"
                elif raw[:8] == b"\x89PNG\r\n\x1a\n":
                    ctype = "image/png"
                elif raw[:6] in (b"GIF87a", b"GIF89a"):
                    ctype = "image/gif"
                elif raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
                    ctype = "image/webp"
                else:
                    ctype = "application/octet-stream"
            return [200, ctype, raw, {}, 0]
        except Exception as e:
            # 返回错误信息便于排查（会显示在图片位置）
            err_msg = ("proxy error: %s" % str(e)[:120]).encode()
            return [502, "text/plain", err_msg, {}, 0]

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        return ".m3u8" in str(url)

    def destroy(self):
        pass


PIC_INLINE = 0