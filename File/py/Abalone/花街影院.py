# -*- coding: utf-8 -*-
import ssl
import time
import json
import re
import base64
import urllib.request
import urllib.parse
from http.cookiejar import CookieJar
import html as html_mod

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass

class Spider(BaseSpider):

    def __init__(self):
        self.site_url = "https://jx2huajy55.a6.yachts"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Linux; U; Android 10; zh-CN; GM1910 Build/QKQ1.190716.003) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/100.0.4896.58 Quark/6.9.0.481 Mobile Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "keep-alive"
        }
        self.cookie_jar = CookieJar()
        self.opener = self._build_opener()
        self.cats = [
            ("3", "黑料吃瓜"), ("4", "厂牌原创"), ("5", "国产精选"),
            ("6", "明星换脸"), ("7", "AV解说"), ("8", "禁漫精选"),
            ("9", "乱伦"), ("10", "父女"), ("11", "母子"),
            ("12", "兄妹"), ("13", "学生"), ("14", "嫂子"),
            ("15", "姐夫"), ("16", "师生"), ("17", "全家"),
            ("18", "猎奇"), ("28", "国产大片"), ("31", "欧美大片"),
            ("32", "网红直播"), ("33", "探花约炮"), ("34", "三级伦理"),
            ("35", "萝莉开苞"), ("66", "有声小说"), ("68", "cosplay"),
            ("69", "AI魔改"), ("70", "av综艺"), ("72", "嫩妹下海"),
            ("74", "每日甄选"), ("76", "ts人妖"), ("77", "姿势玩法"),
            ("78", "同性恋"), ("79", "真实缅北"), ("80", "恶心恐怖"),
            ("81", "黄金圣水"), ("82", "校园霸凌"), ("83", "战场实录"),
            ("84", "人兽乱交"), ("85", "灵异视频"), ("86", "N号房"),
            ("87", "日韩大片"), ("88", "SM调教")
        ]
        self._img_key = b"OzoTeoS7D>6Y^@z39JmD"
        self._enc_domains = (
            "cdn.bcebos.com", "vfile.meituan.net", "huaweicloudobs.ahjxjy.cn",
            "file.zhuyitai.com", "oss.zhuyitai.com", "ucloudqn.unipus.cn"
        )

    def _build_opener(self):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        https_handler = urllib.request.HTTPSHandler(context=ctx)
        cookie_handler = urllib.request.HTTPCookieProcessor(self.cookie_jar)
        return urllib.request.build_opener(https_handler, cookie_handler)

    def _fetch(self, url, retry=1, referer=None):
        headers = dict(self.headers)
        if referer:
            headers["Referer"] = referer
        for i in range(retry + 1):
            try:
                req = urllib.request.Request(url, headers=headers)
                with self.opener.open(req, timeout=10) as resp:
                    raw = resp.read()
                    try:
                        html = raw.decode("utf-8", errors="ignore")
                    except Exception:
                        html = ""
                    return {"success": True, "html": html}
            except Exception:
                if i < retry:
                    time.sleep(0.3)
        return {"success": False, "html": ""}

    def _decode_page(self, html_data):
        if not html_data:
            return ""
        m = re.search(r"var str = '([^']+)'", html_data)
        if not m:
            return html_data
        try:
            d1 = base64.b64decode(m.group(1)).decode("utf-8", errors="ignore")
            d2 = base64.b64decode(d1.strip()).decode("utf-8", errors="ignore")
            return d2 if len(d2) > 1000 else html_data
        except Exception:
            return html_data

    def _fetch_html(self, url, must_contain=None, referer=None):
        html_data = ""
        for _ in range(2):
            res = self._fetch(url, referer=referer)
            raw = res.get("html", "")
            html_data = self._decode_page(raw)
            if res.get("success") and (not must_contain or must_contain in html_data):
                return html_data
        return html_data

    @staticmethod
    def _clean(text):
        if not text:
            return ""
        text = html_mod.unescape(text)
        return re.sub(r"<[^>]+>", "", text).strip()

    def _abs_url(self, url):
        if not url:
            return ""
        url = url.strip()
        if url.startswith("http"):
            return url
        if url.startswith("//"):
            return "https:" + url
        return urllib.parse.urljoin(self.site_url, url)

    def _is_enc_pic(self, url):
        u = (url or "").lower()
        return any(d in u for d in self._enc_domains) or u.endswith(".txt")

    def _proxy_pic(self, url):
        url = self._abs_url(url)
        if not url:
            return ""
        if not self._is_enc_pic(url):
            return url
        try:
            base = self.getProxyUrl()
        except Exception:
            base = ""
        if not base:
            return url
        sep = "&" if "?" in base else "?"
        return "%s%surl=%s" % (base, sep, urllib.parse.quote(url, safe=""))

    def _extract_cover(self, inner):
        if not inner:
            return ""
        cands = []
        for im in re.finditer(r"<img[^>]+>", inner, re.I):
            tag = im.group(0)
            for attr in ("data-original", "data-src", "data-lazy-src", "data-echo", "srcset", "src"):
                am = re.search(r'%s\s*=\s*["\']([^"\']+)["\']' % attr, tag, re.I)
                if not am:
                    continue
                cand = am.group(1).strip().split()[0]
                if not cand or cand.startswith("data:"):
                    continue
                low = cand.lower()
                if any(k in low for k in ("loading.gif", "placeholder", "blank.", "pixel.", "spinner", "faiusr.com")):
                    continue
                cands.append(cand)
        for cand in cands:
            if self._is_enc_pic(cand):
                return self._proxy_pic(cand)
        for cand in cands:
            low = cand.lower()
            if any(low.endswith(ext) or ext in low for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".txt")):
                return self._proxy_pic(cand) if self._is_enc_pic(cand) else self._abs_url(cand)
        return self._proxy_pic(cands[0]) if cands else ""

    def _parse_vod_list(self, html_data):
        cards, seen = [], set()
        if not html_data:
            return cards
        for m in re.finditer(r'<li[^>]*class="[^"]*content-item[^"]*"[^>]*>(.*?)</li>', html_data, re.S | re.I):
            inner = m.group(1)
            am = re.search(r'href="(/index\.php/vod/detail/id/(\d+)\.html)"', inner)
            if not am:
                continue
            vid = am.group(2)
            if vid in seen:
                continue
            seen.add(vid)
            title = ""
            tm = re.search(r'title="([^"]{2,120})"', inner)
            if tm:
                title = tm.group(1).strip()
            title = self._clean(title)
            if not title:
                continue
            pic = self._extract_cover(inner)

            rm_match = re.search(r'<span[^>]+class=[\'"][^\'"]*remarks[^\'"]*[\'"][^>]*>([^<]+)</span>', inner, re.I)
            raw_rm = rm_match.group(1).strip() if rm_match else ""
            remarks = "蝴蝶影视 | %s" % raw_rm if raw_rm else "蝴蝶影视"

            cards.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": remarks,
                "style": {"type": "rect", "ratio": 1.78}
            })

        if not cards:
            for m in re.finditer(r'href="(/index\.php/vod/detail/id/(\d+)\.html)"[^>]*title="([^"]{2,120})"', html_data):
                vid = m.group(2)
                if vid in seen:
                    continue
                seen.add(vid)
                seg = html_data[max(0, m.start() - 500):m.end() + 1500]
                cards.append({
                    "vod_id": vid,
                    "vod_name": self._clean(m.group(3)),
                    "vod_pic": self._extract_cover(seg),
                    "vod_remarks": "蝴蝶影视",
                    "style": {"type": "rect", "ratio": 1.78}
                })
        return cards

    def _extract_play_url(self, html_data):
        if not html_data:
            return ""
        m = re.search(r'var player_aaaa\s*=\s*(\{.*?\})\s*</script>', html_data, re.S)
        if not m:
            m = re.search(r'var player_aaaa\s*=\s*(\{.*?\});', html_data, re.S)
        if m:
            try:
                um = re.search(r'"url"\s*:\s*"((?:[^"\\]|\\.)*)"', m.group(1))
                if um:
                    url = um.group(1).replace("\\/", "/").strip()
                    if url and self.isVideoFormat(url) and not self._is_sample(url):
                        return url
            except Exception:
                pass
        for pat in [r'"(https?://[^"]+\.m3u8[^"]*)"', r"'(https?://[^']+\.m3u8[^']*)'"]:
            for mm in re.findall(pat, html_data, re.I):
                u = mm.replace("\\/", "/")
                if self.isVideoFormat(u) and not self._is_sample(u):
                    return u
        for mm in re.findall(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', html_data, re.I):
            u = mm.replace("\\/", "/")
            if self.isVideoFormat(u) and not self._is_sample(u):
                return u
        return ""

    @staticmethod
    def _is_sample(url):
        low = (url or "").lower()
        return any(k in low for k in ("sample", "test", "preview", "trailer", "advert"))

    def init(self, extend=""):
        pass

    def getName(self):
        return "花街影院"

    def homeContent(self, filter):
        return {
            "class": [{"type_id": tid, "type_name": name} for tid, name in self.cats],
            "filters": {}
        }

    def homeVideoContent(self):
        return {"list": []}

    def _max_page(self, html_data, tid, pg):
        max_pg = pg
        for pm in re.finditer(r"/index\.php/vod/type/id/%s/page/(\d+)\.html" % tid, html_data):
            try:
                max_pg = max(max_pg, int(pm.group(1)))
            except Exception:
                pass
        return max_pg

    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1
        if pg <= 1:
            url = "%s/index.php/vod/type/id/%s.html" % (self.site_url, tid)
        else:
            url = "%s/index.php/vod/type/id/%s/page/%d.html" % (self.site_url, tid, pg)
        html_data = self._fetch_html(url, must_contain="vod/detail")
        cards = self._parse_vod_list(html_data)
        max_pg = self._max_page(html_data, tid, pg)
        pagecount = max_pg if max_pg > pg else (pg + 1 if cards else pg)
        return {
            "list": cards,
            "page": pg,
            "pagecount": pagecount,
            "limit": len(cards),
            "total": 0
        }

    def detailContent(self, ids):
        vid = str(ids[0]).strip() if ids else ""
        if not vid:
            return {"list": []}
        vod = {
            "vod_id": vid,
            "vod_name": vid,
            "vod_pic": "",
            "vod_remarks": "蝴蝶影视",
            "vod_actor": "🦋 TG群: @tvshare23",
            "vod_director": "🦋 蝴蝶影视",
            "vod_content": "🦋 官方交流群: @tvshare23 | 严禁盗卖，完全免费！\n\n影片ID: %s" % vid,
            "vod_play_from": "蝴蝶专线",
            "vod_play_url": "正片$%s/index.php/vod/play/id/%s/sid/1/nid/1.html" % (self.site_url, vid)
        }
        try:
            play_url = "%s/index.php/vod/play/id/%s/sid/1/nid/1.html" % (self.site_url, vid)
            ph = self._fetch_html(play_url, must_contain="player_aaaa", referer=self.site_url + "/")
            start = ph.find("var player_aaaa")
            if start >= 0:
                js = ph.find("{", start)
                if js >= 0:
                    depth, i = 0, js
                    while i < len(ph):
                        if ph[i] == "{":
                            depth += 1
                        elif ph[i] == "}":
                            depth -= 1
                            if depth == 0:
                                break
                        i += 1
                    try:
                        cfg = json.loads(ph[js:i + 1])
                        vd = cfg.get("vod_data", {})
                        if vd.get("vod_name"):
                            vod["vod_name"] = self._clean(str(vd["vod_name"]))
                    except Exception:
                        pass
            m3u8 = self._extract_play_url(ph)
            if m3u8:
                vod["vod_play_url"] = "正片$%s" % m3u8
        except Exception:
            pass
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        raw_id = str(id).strip()
        header = {
            "User-Agent": self.headers["User-Agent"],
            "Referer": self.site_url + "/"
        }
        if raw_id.startswith("http") and self.isVideoFormat(raw_id):
            return {"parse": 0, "url": raw_id, "header": header}
        try:
            vid = re.sub(r"\D", "", raw_id)
            if vid:
                d = self.detailContent([vid])
                ep = d["list"][0]["vod_play_url"]
                if "$" in ep:
                    u = ep.split("$", 1)[1]
                    if u.startswith("http") and self.isVideoFormat(u):
                        return {"parse": 0, "url": u, "header": header}
        except Exception:
            pass
        return {"parse": 1, "url": raw_id, "header": header}

    def searchContent(self, key, quick, pg="1"):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1
        kw = urllib.parse.quote(str(key).strip())
        if pg <= 1:
            url = "%s/index.php/vod/search.html?wd=%s" % (self.site_url, kw)
        else:
            url = "%s/index.php/vod/search/page/%d/wd/%s.html" % (self.site_url, pg, kw)
        html_data = self._fetch_html(url, must_contain="vod/detail")
        cards = self._parse_vod_list(html_data)
        return {
            "list": cards,
            "page": pg,
            "pagecount": pg + 1 if cards else pg,
            "limit": len(cards),
            "total": 0
        }

    def action(self, action):
        return None

    def liveContent(self):
        return {}

    def localProxy(self, params):
        # 1x1 像素透明 GIF 兜底，确保坏图时既不崩 App 也不反复重试
        blank_pixel = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
        try:
            if not isinstance(params, dict):
                params = {}
            url = (params.get("url") or params.get("pic") or "").strip()
            if not url.startswith("http"):
                return [200, "image/gif", blank_pixel]

            req = urllib.request.Request(url, headers={
                "User-Agent": self.headers["User-Agent"],
                "Referer": self.site_url + "/",
                "Accept": "*/*"
            })
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            # 缩短超时时间到 3 秒，坏图快速跳过，不阻塞其他海报加载
            with urllib.request.urlopen(req, context=ctx, timeout=3) as resp:
                raw = resp.read()

            if not raw:
                return [200, "image/gif", blank_pixel]

            try:
                text = raw.decode("utf-8", errors="ignore").strip()
            except Exception:
                text = ""

            text = re.sub(r"\s+", "", text)
            try:
                binary = base64.b64decode(text) if text else raw
            except Exception:
                binary = raw

            if not binary:
                return [200, "image/gif", blank_pixel]

            key = self._img_key
            kl = len(key)
            out = bytearray(len(binary))
            for i, b in enumerate(binary):
                out[i] = b ^ key[i % kl]

            if out[:3] == b"\xff\xd8\xff":
                mime = "image/jpeg"
            elif out[:4] == b"\x89PNG":
                mime = "image/png"
            elif out[:3] == b"GIF":
                mime = "image/gif"
            elif out[:4] == b"RIFF":
                mime = "image/webp"
            else:
                mime = "image/jpeg"

            return [200, mime, bytes(out)]
        except Exception:
            # 遇到任何 404、网络断开、超时或坏图片，直接安全返回占位图
            return [200, "image/gif", blank_pixel]

    def isVideoFormat(self, url):
        u = (url or "").lower()
        return u.endswith(".m3u8") or ".m3u8?" in u

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass