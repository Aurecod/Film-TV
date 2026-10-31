import sys
import os
import re
import json
import base64
import hashlib
import time
import urllib.request
import urllib.parse
from urllib.parse import urlparse, quote, unquote
import http.cookiejar
import gzip
import zlib
import ssl

try:
    from base.spider import Spider as SpiderBase
except ImportError:
    class SpiderBase(object):
        def getCache(self, key): return None
        def setCache(self, key, value): return "fail"
        def delCache(self, key): return "fail"

def format_remarks(brand="🦋 蝴蝶影视", meta=""):
    clean_meta = str(meta or "").strip()
    clean_meta = re.sub(r"[\r\n\t]+", " ", clean_meta).strip()
    if clean_meta:
        return "%s | %s" % (brand, clean_meta)
    return brand

class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

class Spider(SpiderBase):
    def __init__(self):
        super(Spider, self).__init__()
        self.siteUrl = "https://www.jiujiu.live"
        self.tgGroup = "https://t.me/tvshare23"
        self.brandActor = "🦋 TG群: @tvshare23"
        self.brandDirector = "🦋 蝴蝶影视"
        self._ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        self.options = {}
        self.waf_cookie = ""
        self._mem_cache = {}

        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE

        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj),
            urllib.request.HTTPSHandler(context=self.ctx)
        )

        self.static_classes = [
            {"type_id": "23", "type_name": "日本無碼"},
            {"type_id": "9", "type_name": "中文字幕"},
            {"type_id": "82", "type_name": "日韓無碼"},
            {"type_id": "78", "type_name": "AV明星"},
            {"type_id": "31", "type_name": "制服誘惑"},
            {"type_id": "24", "type_name": "日本有碼"},
            {"type_id": "25", "type_name": "歐美精品"},
            {"type_id": "113", "type_name": "無碼專區"},
            {"type_id": "87", "type_name": "動漫精品"},
            {"type_id": "201", "type_name": "歐美-高清無碼"},
            {"type_id": "136", "type_name": "歐美情色"},
            {"type_id": "55", "type_name": "成人動漫"},
            {"type_id": "133", "type_name": "歐美性愛"},
            {"type_id": "271", "type_name": "日韓精品"},
            {"type_id": "116", "type_name": "卡通動漫"},
            {"type_id": "148", "type_name": "倫理三級"},
            {"type_id": "64", "type_name": "巨乳美乳"},
            {"type_id": "81", "type_name": "童顏巨乳"},
            {"type_id": "66", "type_name": "亞洲有碼"},
            {"type_id": "86", "type_name": "歐美極品"},
            {"type_id": "32", "type_name": "AV解說"},
            {"type_id": "110", "type_name": "女優明星"},
            {"type_id": "309", "type_name": "歐美"},
            {"type_id": "41", "type_name": "倫理片"},
            {"type_id": "100", "type_name": "SWAG"},
            {"type_id": "143", "type_name": "人妻熟女"},
            {"type_id": "8", "type_name": "高清無碼"},
            {"type_id": "358", "type_name": "日本-素人"},
            {"type_id": "90", "type_name": "日本片商"},
            {"type_id": "132", "type_name": "卡通動畫"},
            {"type_id": "71", "type_name": "歐美激情"},
            {"type_id": "155", "type_name": "明星換臉"},
            {"type_id": "176", "type_name": "動漫卡通"},
            {"type_id": "440", "type_name": "無碼流出"},
            {"type_id": "52", "type_name": "AI換臉"},
            {"type_id": "68", "type_name": "亞洲無碼"},
            {"type_id": "217", "type_name": "日本-高清有碼"},
            {"type_id": "122", "type_name": "麻豆視頻"},
            {"type_id": "163", "type_name": "換臉明星"},
            {"type_id": "269", "type_name": "倫理影片"},
            {"type_id": "238", "type_name": "日本素人"},
            {"type_id": "191", "type_name": "獨家DMM"},
            {"type_id": "101", "type_name": "三級倫理"},
            {"type_id": "109", "type_name": "麻豆傳媒"},
            {"type_id": "112", "type_name": "歐美系列"},
            {"type_id": "92", "type_name": "激情動漫"},
            {"type_id": "219", "type_name": "日本-無碼流出"},
            {"type_id": "331", "type_name": "劇情介紹"},
            {"type_id": "7", "type_name": "3D動漫"},
            {"type_id": "336", "type_name": "日本精品"},
            {"type_id": "193", "type_name": "HEY誘惑"},
            {"type_id": "200", "type_name": "動漫-黃漫"},
            {"type_id": "308", "type_name": "華語AV"},
            {"type_id": "203", "type_name": "日本-一本道"},
            {"type_id": "448", "type_name": "動漫精選"},
            {"type_id": "433", "type_name": "歐美勁爆"},
            {"type_id": "207", "type_name": "傳媒-麻豆傳媒"},
            {"type_id": "67", "type_name": "日本女優"},
            {"type_id": "402", "type_name": "日本動漫"},
            {"type_id": "73", "type_name": "有碼精品"},
            {"type_id": "199", "type_name": "動漫-里番中字"},
            {"type_id": "443", "type_name": "高清有碼"},
            {"type_id": "111", "type_name": "歐美無碼"},
            {"type_id": "489", "type_name": "韓國三級"}
        ]

    def init(self, extend=""):
        if isinstance(extend, dict):
            self.options = extend
        elif extend:
            try:
                self.options = json.loads(extend)
            except Exception:
                self.options = {}
        return True

    def getName(self):
        return "久久网"

    def isVideoFormat(self, url):
        low = (url or "").lower()
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".ts", ".mpd"))

    def manualVideoCheck(self):
        return False

    def _extract_cookie_from_headers(self, headers, target_key):
        if not headers:
            return ""
        all_cookies = []
        if hasattr(headers, "get_all"):
            all_cookies = headers.get_all("Set-Cookie") or []
        elif hasattr(headers, "getheaders"):
            all_cookies = headers.getheaders("Set-Cookie") or []
        else:
            raw_c = headers.get("Set-Cookie", "")
            if raw_c:
                all_cookies = [raw_c]

        for c_str in all_cookies:
            m = re.search(r'(%s=[^;,\s]+)' % target_key, c_str)
            if m:
                return m.group(1).strip()
        return ""

    def _solve_cdnlah_pow(self, waf_html, target_url):
        cfg_m = re.search(r'<script[^>]+id=["\']__cdnlah_pow_config["\'][^>]*>([\s\S]*?)</script>', waf_html, re.I)
        if not cfg_m:
            return False
        try:
            cfg = json.loads(cfg_m.group(1).strip())
        except Exception:
            return False

        seed = str(cfg.get("seed", ""))
        difficulty = int(cfg.get("difficulty", 0))
        verify_path = cfg.get("verify_path", "/__cdnlah/pow/verify")
        metadata_field = cfg.get("metadata_field", "challenge_metadata")
        metadata_token = cfg.get("metadata_token", "")
        challenge_cookie = cfg.get("challenge_cookie", "_chg_waf_pow")
        redirect_val = cfg.get("redirect", "/")

        if not seed or difficulty <= 0:
            return False

        target_prefix = "0" * difficulty
        nonce_hex = ""

        for n in range(1500000):
            cand_hex = "%016x" % n
            digest = hashlib.sha256((seed + cand_hex).encode("utf-8")).hexdigest()
            if digest[:difficulty] == target_prefix:
                nonce_hex = cand_hex
                break

        if not nonce_hex:
            return False

        verify_url = self.siteUrl + verify_path
        form_payload = {
            "seed": seed,
            "nonce": nonce_hex,
            "redirect": redirect_val,
            "challenge_cookie": challenge_cookie,
            metadata_field: metadata_token
        }
        post_bytes = urllib.parse.urlencode(form_payload).encode("utf-8")

        verify_opener = urllib.request.build_opener(
            NoRedirectHandler(),
            urllib.request.HTTPCookieProcessor(self.cj),
            urllib.request.HTTPSHandler(context=self.ctx)
        )

        v_headers = {
            "User-Agent": self._ua,
            "Origin": self.siteUrl,
            "Referer": target_url if target_url else (self.siteUrl + "/"),
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh-TW,zh;q=0.9,en;q=0.8",
            "Connection": "keep-alive"
        }
        if self.waf_cookie:
            v_headers["Cookie"] = self.waf_cookie

        try:
            v_req = urllib.request.Request(verify_url, data=post_bytes, headers=v_headers)
            try:
                with verify_opener.open(v_req, timeout=10) as v_resp:
                    ck = self._extract_cookie_from_headers(v_resp.headers, challenge_cookie)
                    if ck:
                        self.waf_cookie = ck
                        return True
            except urllib.error.HTTPError as he:
                ck = self._extract_cookie_from_headers(getattr(he, "headers", None), challenge_cookie)
                if ck:
                    self.waf_cookie = ck
                    return True
                if he.code in (301, 302, 303, 307):
                    return True
        except Exception:
            pass

        for cookie in self.cj:
            if cookie.name == challenge_cookie:
                self.waf_cookie = "%s=%s" % (cookie.name, cookie.value)
                return True

        return bool(self.waf_cookie)

    def _fetch(self, target_url, referer=""):
        if not target_url:
            return {"code": 0, "text": "", "bytes": b"", "err": "empty_url", "final_url": ""}
        if target_url.startswith("//"):
            target_url = "https:" + target_url
        elif target_url.startswith("/"):
            target_url = self.siteUrl + target_url

        headers = {
            "User-Agent": self._ua,
            "Referer": referer if referer else (self.siteUrl + "/"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh-TW,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive"
        }

        last_err = ""
        for attempt in range(4):
            if self.waf_cookie:
                headers["Cookie"] = self.waf_cookie

            try:
                req = urllib.request.Request(target_url, headers=headers)
                with self.opener.open(req, timeout=10) as resp:
                    raw = resp.read()
                    enc = resp.headers.get("Content-Encoding", "")
                    if raw.startswith(b"\x1f\x8b") or enc == "gzip":
                        raw = gzip.decompress(raw)
                    elif enc == "deflate":
                        try:
                            raw = zlib.decompress(raw)
                        except Exception:
                            raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                    try:
                        text = raw.decode("utf-8")
                    except Exception:
                        text = raw.decode("latin1", errors="ignore")

                    if "__cdnlah_pow_config" in text and attempt < 3:
                        if self._solve_cdnlah_pow(text, target_url):
                            continue

                    return {"code": resp.getcode(), "text": text, "bytes": raw, "err": "", "final_url": resp.geturl()}

            except urllib.error.HTTPError as e:
                last_err = "HTTP %s" % e.code
                err_text = ""
                try:
                    err_raw = e.read()
                    if err_raw.startswith(b"\x1f\x8b") or getattr(e, "headers", {}).get("Content-Encoding") == "gzip":
                        err_raw = gzip.decompress(err_raw)
                    err_text = err_raw.decode("utf-8", errors="ignore")
                except Exception:
                    pass

                if (e.code == 492 or "__cdnlah_pow_config" in err_text) and attempt < 3:
                    if self._solve_cdnlah_pow(err_text, target_url):
                        continue

                if e.code in (451, 403, 429, 502, 503) and attempt < 3:
                    time.sleep(0.3)
                    continue

                return {"code": e.code, "text": err_text, "bytes": b"", "err": str(e), "final_url": target_url}

            except Exception as e:
                last_err = str(e)
                if attempt < 3:
                    time.sleep(0.3)
                    continue
                return {"code": -1, "text": "", "bytes": b"", "err": str(e), "final_url": target_url}

        return {"code": -1, "text": "", "bytes": b"", "err": last_err, "final_url": target_url}

    def homeContent(self, filter):
        result = {
            "class": self.static_classes
        }
        if filter:
            result["filters"] = {
                c["type_id"]: [
                    {
                        "key": "sort",
                        "name": "排序",
                        "value": [
                            {"n": "最新发布", "v": ""},
                            {"n": "最多播放", "v": "hits"}
                        ]
                    }
                ] for c in self.static_classes
            }
        return result

    def homeVideoContent(self):
        return {"list": []}

    def _clean_pic_url(self, raw_pic):
        if not raw_pic:
            return ""
        pic = raw_pic.strip()
        if pic.startswith("data:image"):
            return ""
        if pic.startswith("//"):
            pic = "https:" + pic
        elif pic.startswith("/"):
            pic = self.siteUrl + pic
        return "%s@Referer=%s/" % (pic, self.siteUrl)

    def categoryContent(self, tid, pg, filter, extend):
        page = 1
        try:
            page = int(pg)
        except Exception:
            page = 1
        if page < 1:
            page = 1

        sort_val = ""
        if isinstance(extend, dict):
            sort_val = extend.get("sort", "")

        cache_key = "cat_%s_%d_%s" % (tid, page, sort_val)
        now_ts = time.time()
        if cache_key in self._mem_cache:
            entry = self._mem_cache[cache_key]
            if now_ts - entry["time"] < 120:
                return entry["data"]

        query_parts = []
        if page > 1:
            query_parts.append("page=%d" % page)
        if sort_val:
            query_parts.append("sort=%s" % sort_val)

        query_str = ("?" + "&".join(query_parts)) if query_parts else ""
        target_path = "/c/%s%s" % (tid, query_str)

        fetch_res = self._fetch(target_path)
        html_text = fetch_res.get("text", "")

        vod_items = []
        seen_ids = set()

        raw_blocks = html_text.split('<div class="col-')
        for block in raw_blocks[1:]:
            href_m = re.search(r'href=["\'](?:https?://[^/]+)?/(\d+)["\']', block)
            if not href_m:
                continue
            v_id = href_m.group(1).strip()
            if v_id in seen_ids:
                continue
            seen_ids.add(v_id)

            title = ""
            lines_m = re.search(r'<div[^>]+class=["\'][^"\']*\blines\b[^"\']*["\'][^>]*>([\s\S]*?)</div>', block, re.I)
            if lines_m:
                title = re.sub(r"<[^>]+>", "", lines_m.group(1)).strip()

            pic = ""
            for attr in ("data-original", "data-src", "data-url", "src"):
                attr_m = re.search(r'%s=["\']([^"\']+)["\']' % attr, block, re.I)
                if attr_m:
                    cand = attr_m.group(1).strip()
                    if not cand.startswith("data:image"):
                        pic = cand
                        break

            if not title:
                alt_m = re.search(r'<img[^>]+alt=["\']([^"\']+)["\']', block, re.I)
                if alt_m:
                    title = alt_m.group(1).strip()

            if not title:
                title = "影片 %s" % v_id

            badge_m = re.search(r'<span[^>]+class=["\'][^"\']*\bbadge\b[^"\']*["\'][^>]*>([^<]+)</span>', block, re.I)
            meta = badge_m.group(1).strip() if badge_m else "HD"

            vod_items.append({
                "vod_id": v_id,
                "vod_name": title,
                "vod_pic": self._clean_pic_url(pic),
                "vod_remarks": format_remarks("🦋 蝴蝶影视", meta),
                "style": {"type": "rect", "ratio": 1.78}
            })

        out_data = {
            "page": page,
            "pagecount": page + 1 if len(vod_items) >= 20 else page,
            "limit": len(vod_items) if vod_items else 20,
            "total": 9999,
            "list": vod_items
        }

        if vod_items:
            self._mem_cache[cache_key] = {"time": now_ts, "data": out_data}

        return out_data

    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        vid = str(raw_id).strip()

        detail_url = "/%s" % vid
        res = self._fetch(detail_url)
        html_text = res.get("text", "")

        title_m = re.search(r'<title>(.*?)</title>', html_text, re.I)
        vod_title = title_m.group(1).split("-")[0].strip() if title_m else ("影片 %s" % vid)

        poster_m = re.search(r'poster=["\']([^"\']+)["\']', html_text, re.I)
        if not poster_m:
            poster_m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html_text, re.I)
        vod_pic = poster_m.group(1).strip() if poster_m else ""

        play_url = ""
        source_m = re.search(r'<source[^>]+src=["\']([^"\']+\.m3u8[^"\']*)["\']', html_text, re.I)
        if source_m:
            play_url = source_m.group(1).strip()
        else:
            m3u8_all = re.findall(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', html_text, re.I)
            if m3u8_all:
                play_url = m3u8_all[0]
            else:
                video_src_m = re.search(r'<video[^>]+src=["\']([^"\']+)["\']', html_text, re.I)
                if video_src_m:
                    play_url = video_src_m.group(1).strip()
                else:
                    play_url = self.siteUrl + detail_url

        vod = {
            "vod_id": vid,
            "vod_name": vod_title,
            "vod_pic": self._clean_pic_url(vod_pic),
            "vod_actor": self.brandActor,
            "vod_director": self.brandDirector,
            "vod_remarks": format_remarks("🦋 蝴蝶影视", "正片"),
            "vod_content": "🦋 蝴蝶影视专线直连 | 极速高清画质 | 官方交流群: @tvshare23",
            "vod_play_from": "蝴蝶专线",
            "vod_play_url": "超清正片$%s" % play_url
        }

        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        url = str(id).strip()
        headers = {
            "User-Agent": self._ua,
            "Referer": self.siteUrl + "/"
        }
        return {
            "parse": 0 if any(k in url.lower() for k in (".m3u8", ".mp4", ".flv", ".ts")) else 1,
            "playUrl": "",
            "url": url,
            "header": headers
        }

    def searchContent(self, key, quick, pg="1"):
        page = 1
        try:
            page = int(pg)
        except Exception:
            page = 1
        if page < 1:
            page = 1

        query_str = "?keyword=%s" % quote(key)
        if page > 1:
            query_str += "&page=%d" % page

        search_url = "/node/search%s" % query_str
        res = self._fetch(search_url)
        html_text = res.get("text", "")

        vod_items = []
        seen_ids = set()

        raw_blocks = html_text.split('<div class="col-')
        for block in raw_blocks[1:]:
            href_m = re.search(r'href=["\'](?:https?://[^/]+)?/(\d+)["\']', block)
            if not href_m:
                continue
            v_id = href_m.group(1).strip()
            if v_id in seen_ids:
                continue
            seen_ids.add(v_id)

            title = ""
            lines_m = re.search(r'<div[^>]+class=["\'][^"\']*\blines\b[^"\']*["\'][^>]*>([\s\S]*?)</div>', block, re.I)
            if lines_m:
                title = re.sub(r"<[^>]+>", "", lines_m.group(1)).strip()

            pic = ""
            for attr in ("data-original", "data-src", "data-url", "src"):
                attr_m = re.search(r'%s=["\']([^"\']+)["\']' % attr, block, re.I)
                if attr_m:
                    cand = attr_m.group(1).strip()
                    if not cand.startswith("data:image"):
                        pic = cand
                        break

            if not title:
                alt_m = re.search(r'<img[^>]+alt=["\']([^"\']+)["\']', block, re.I)
                if alt_m:
                    title = alt_m.group(1).strip()

            if not title:
                title = "影片 %s" % v_id

            badge_m = re.search(r'<span[^>]+class=["\'][^"\']*\bbadge\b[^"\']*["\'][^>]*>([^<]+)</span>', block, re.I)
            meta = badge_m.group(1).strip() if badge_m else "HD"

            vod_items.append({
                "vod_id": v_id,
                "vod_name": title,
                "vod_pic": self._clean_pic_url(pic),
                "vod_remarks": format_remarks("🦋 蝴蝶影视", meta),
                "style": {"type": "rect", "ratio": 1.78}
            })

        return {
            "page": page,
            "pagecount": page + 1 if len(vod_items) >= 20 else page,
            "limit": len(vod_items) if vod_items else 20,
            "total": 9999,
            "list": vod_items
        }

    def action(self, action):
        return {"msg": "ok"}

    def liveContent(self):
        return ""

    def localProxy(self, params):
        return [404, "text/plain; charset=utf-8", "Proxy not configured"]

    def destroy(self):
        self.options = {}
        self._mem_cache.clear()