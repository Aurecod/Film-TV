#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# BestJavPorn spider - bestjavporn.me mirror
# Play: extract /xx/ embed pox/dp, AES-256-CBC decrypt to m3u8

import re
import json
import base64
import hashlib
import urllib.request
import urllib.parse
from urllib.parse import quote, urljoin
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


Sbox = (
    0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,
    0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,
    0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,
    0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,
    0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,
    0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,
    0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,
    0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,
    0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,
    0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,
    0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,
    0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,
    0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,
    0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,
    0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,
    0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16,
)
Rcon = (0x00,0x01,0x02,0x04,0x08,0x10,0x20,0x40,0x80,0x1b,0x36)

def _xtime(a):
    return (((a << 1) ^ 0x1B) & 0xFF) if (a & 0x80) else ((a << 1) & 0xFF)

def _sub(s):
    return [Sbox[b] for b in s]

def _shift(s):
    return [s[0],s[5],s[10],s[15], s[4],s[9],s[14],s[3], s[8],s[13],s[2],s[7], s[12],s[1],s[6],s[11]]

def _mix(s):
    out = []
    for i in range(4):
        t = s[4*i:4*i+4]
        out += [
            _xtime(t[0]) ^ _xtime(t[1]) ^ t[1] ^ t[2] ^ t[3],
            t[0] ^ _xtime(t[1]) ^ _xtime(t[2]) ^ t[2] ^ t[3],
            t[0] ^ t[1] ^ _xtime(t[2]) ^ _xtime(t[3]) ^ t[3],
            _xtime(t[0]) ^ t[0] ^ t[1] ^ t[2] ^ _xtime(t[3]),
        ]
    return out

def _add(s, k):
    return [s[i] ^ k[i] for i in range(16)]

def _key_expand(key):
    nk = len(key) // 4
    nr = {4: 10, 6: 12, 8: 14}[nk]
    w = list(key)
    i = nk
    while len(w) < 16 * (nr + 1):
        t = w[-4:]
        if i % nk == 0:
            t = _sub(t[1:] + t[:1])
            t[0] ^= Rcon[i // nk]
        elif nk > 6 and i % nk == 4:
            t = _sub(t)
        for j in range(4):
            w.append(w[-nk * 4] ^ t[j])
        i += 1
    return [w[i:i+16] for i in range(0, 16 * (nr + 1), 16)], nr

def _inv_sub(s):
    inv = [0]*256
    for i, v in enumerate(Sbox):
        inv[v] = i
    return [inv[b] for b in s]

def _inv_shift(s):
    return [s[0],s[13],s[10],s[7], s[4],s[1],s[14],s[11], s[8],s[5],s[2],s[15], s[12],s[9],s[6],s[3]]

def _inv_mix(s):
    out = []
    def m(a, n):
        r = 0
        for _ in range(8):
            if n & 1:
                r ^= a
            hi = a & 0x80
            a = (a << 1) & 0xFF
            if hi:
                a ^= 0x1B
            n >>= 1
        return r
    for i in range(4):
        t = s[4*i:4*i+4]
        out += [
            m(t[0],14)^m(t[1],11)^m(t[2],13)^m(t[3],9),
            m(t[0],9)^m(t[1],14)^m(t[2],11)^m(t[3],13),
            m(t[0],13)^m(t[1],9)^m(t[2],14)^m(t[3],11),
            m(t[0],11)^m(t[1],13)^m(t[2],9)^m(t[3],14),
        ]
    return out

def aes_decrypt_block(block, round_keys, nr):
    s = _add(list(block), round_keys[nr])
    for r in range(nr - 1, 0, -1):
        s = _inv_shift(s)
        s = _inv_sub(s)
        s = _add(s, round_keys[r])
        s = _inv_mix(s)
    s = _inv_shift(s)
    s = _inv_sub(s)
    s = _add(s, round_keys[0])
    return bytes(s)

def aes_cbc_decrypt(ct, key, iv):
    round_keys, nr = _key_expand(list(key))
    out = b""
    prev = iv
    for i in range(0, len(ct), 16):
        block = ct[i:i+16]
        dec = aes_decrypt_block(block, round_keys, nr)
        out += bytes(dec[j] ^ prev[j] for j in range(16))
        prev = block
    pad = out[-1]
    if 1 <= pad <= 16:
        out = out[:-pad]
    return out

def evp_kdf(password, salt, key_len=32, iv_len=16):
    dtot = b""
    d = b""
    pw = password.encode("utf-8") if isinstance(password, str) else password
    while len(dtot) < key_len + iv_len:
        d = hashlib.md5(d + pw + salt).digest()
        dtot += d
    return dtot[:key_len], dtot[key_len:key_len + iv_len]

def cryptojs_aes_decrypt(pox, dp_b64):
    try:
        data = json.loads(base64.b64decode(dp_b64).decode("utf-8"))
        ct = base64.b64decode(data["ct"].replace("\\/", "/"))
        iv = bytes.fromhex(data["iv"])
        salt = bytes.fromhex(data["s"])
        parts = pox.split("+")
        if len(parts) < 2:
            return ""
        key_str = parts[1][1:] if len(parts[1]) > 1 else parts[1]
        key, _ = evp_kdf(key_str, salt, 32, 16)
        pt = aes_cbc_decrypt(ct, key, iv)
        text = pt.decode("utf-8", errors="ignore").strip().strip('"').replace("\\/", "/")
        return text
    except Exception:
        return ""


def format_remarks(brand="蝴蝶影视", meta=""):
    clean_meta = re.sub(r"[\r\n\t]+", " ", str(meta or "").strip()).strip()
    if clean_meta:
        return "%s | %s" % (brand, clean_meta)
    return brand


class Spider(SpiderBase):
    def __init__(self):
        super(Spider, self).__init__()
        self.siteUrl = "https://bestjavporn.me"
        self.tgGroup = "https://t.me/tvshare23"
        self.brandActor = "🦋 TG群: @tvshare23"
        self.brandDirector = "🦋 蝴蝶影视"
        self._ua = "Mozilla/5.0 (Linux; Android 13; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
        self.options = {}
        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE
        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj),
            urllib.request.HTTPSHandler(context=self.ctx)
        )

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
        return "蝴蝶·BestJavPorn"

    def isVideoFormat(self, url):
        low = (url or "").lower()
        if any(b in low for b in ("preview.mp4", "sample.mp4", "trailer.mp4")):
            return False
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".mkv", ".ts", ".mpd"))

    def manualVideoCheck(self):
        return False

    def _fetch(self, target_url, data=None, referer="", headers_custom=None):
        if not target_url:
            return {"code": 0, "text": "", "bytes": b"", "err": ""}
        if target_url.startswith("//"):
            target_url = "https:" + target_url
        elif target_url.startswith("/"):
            target_url = self.siteUrl + target_url
        headers = {
            "User-Agent": self._ua,
            "Referer": referer if referer else (self.siteUrl + "/"),
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }
        if headers_custom:
            headers.update(headers_custom)
        req_data = None
        if isinstance(data, dict):
            req_data = urllib.parse.urlencode(data).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        last_err = ""
        for attempt in range(2):
            try:
                req = urllib.request.Request(target_url, data=req_data, headers=headers)
                with self.opener.open(req, timeout=15) as resp:
                    raw = resp.read()
                    enc = getattr(resp, "headers", {}).get("Content-Encoding", "")
                    if raw.startswith(b"\x1f\x8b") or enc == "gzip":
                        try:
                            raw = gzip.decompress(raw)
                        except Exception:
                            pass
                    elif enc == "deflate":
                        try:
                            raw = zlib.decompress(raw)
                        except Exception:
                            try:
                                raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                            except Exception:
                                pass
                    try:
                        text = raw.decode("utf-8")
                    except Exception:
                        text = raw.decode("latin1", errors="ignore")
                    return {"code": resp.getcode(), "text": text, "bytes": raw, "err": ""}
            except Exception as e:
                last_err = str(e)
                if attempt == 0:
                    continue
                return {"code": -1, "text": "", "bytes": b"", "err": last_err}
        return {"code": -1, "text": "", "bytes": b"", "err": last_err}

    def _clean_text(self, raw):
        t = re.sub(r"<[^>]+>", "", raw or "")
        return re.sub(r"[\r\n\t\s]+", " ", t).strip()

    def homeContent(self, filter):
        return {
            "class": [
                {"type_name": "有码专区", "type_id": "censored"},
                {"type_name": "素人专区", "type_id": "amateur"},
                {"type_name": "去码专区", "type_id": "reducing-mosaic"},
                {"type_name": "最新更新", "type_id": "latest"},
                {"type_name": "最多观看", "type_id": "most-viewed"},
                {"type_name": "最长时长", "type_id": "longest"},
                {"type_name": "随机推荐", "type_id": "random"},
            ]
        }

    def homeVideoContent(self):
        return self.categoryContent("censored", 1, None, {})

    def _extract_img(self, chunk):
        for attr in ("data-src", "data-lazy-src", "data-original", "src"):
            m = re.search(r'\b%s=["\']([^"\']+)["\']' % attr, chunk, re.I)
            if m:
                val = m.group(1).strip()
                if val and not val.startswith("data:") and "svg" not in val:
                    if val.startswith("//"):
                        val = "https:" + val
                    elif val.startswith("http://"):
                        val = "https://" + val[7:]
                    return val
        return ""

    def _wrap_img(self, img_url):
        if not img_url:
            return ""
        if not img_url.startswith("http"):
            img_url = urljoin(self.siteUrl, img_url)
        return "%s@Referer=%s@User-Agent=%s" % (img_url, self.siteUrl + "/", quote(self._ua))

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        tid = str(tid).strip()
        route = {
            "censored": "/category/censored/",
            "amateur": "/category/amateur/",
            "reducing-mosaic": "/category/reducing-mosaic/",
            "latest": "/?filter=latest",
            "most-viewed": "/?filter=most-viewed",
            "longest": "/?filter=longest",
            "random": "/?filter=random",
        }
        if tid.startswith("http") or tid.startswith("/") or tid.startswith("?s="):
            base = tid if tid.startswith("http") else (self.siteUrl + (tid if tid.startswith("/") or tid.startswith("?") else "/" + tid))
        elif tid in route:
            base = self.siteUrl + route[tid]
        else:
            base = self.siteUrl + "/category/censored/"
        if page > 1:
            if "filter=" in base or "?s=" in base:
                sep = "&" if "?" in base else "?"
                req_url = base + ("%spaged=%d" % (sep, page))
            else:
                req_url = base.rstrip("/") + "/page/%d/" % page
        else:
            req_url = base
        res = self._fetch(req_url)
        html = res.get("text", "")
        if not html or len(html) < 500:
            return {"page": page, "pagecount": 1, "limit": 0, "total": 0, "list": []}
        scoped = re.sub(r"<header[\s\S]*?</header>", "", html, flags=re.I)
        scoped = re.sub(r"<nav[\s\S]*?</nav>", "", scoped, flags=re.I)
        articles = re.findall(r'(<article[^>]*class="[^"]*loop-video[^"]*"[^>]*>[\s\S]*?</article>)', scoped, re.I)
        if not articles:
            parts = scoped.split("thumb-block")
            if len(parts) > 2:
                articles = parts[1:]
        video_list = []
        for chunk in articles:
            link_m = re.search(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*title=["\']([^"\']*)["\']', chunk, re.I)
            if not link_m:
                link_m = re.search(r'<a[^>]+href=["\']([^"\']+)["\']', chunk, re.I)
            if not link_m:
                continue
            href = link_m.group(1).strip()
            title = self._clean_text(link_m.group(2)) if link_m.lastindex and link_m.lastindex >= 2 else ""
            if not title:
                t2 = re.search(r'<header[^>]*>[\s\S]*?<span[^>]*>([\s\S]*?)</span>', chunk, re.I)
                if t2:
                    title = self._clean_text(t2.group(1))
            if not href or href.startswith("javascript:"):
                continue
            full_href = href if href.startswith("http") else urljoin(self.siteUrl, href)
            pic = self._wrap_img(self._extract_img(chunk))
            dur_m = re.search(r'class="duration"[^>]*>[\s\S]*?</i>\s*([0-9:]+)', chunk, re.I)
            if not dur_m:
                dur_m = re.search(r'duration[^>]*>[\s\S]*?([0-9]{1,2}:[0-9]{2}(?::[0-9]{2})?)', chunk, re.I)
            duration = self._clean_text(dur_m.group(1)) if dur_m else ""
            video_list.append({
                "vod_id": full_href,
                "vod_name": title or "未知片目",
                "vod_pic": pic,
                "vod_remarks": format_remarks("蝴蝶影视", duration),
                "style": {"type": "rect", "ratio": 1.78}
            })
        has_next = bool(re.search(r'/page/%d[/\"\']' % (page + 1), scoped)) or bool(re.search(r'paged=%d' % (page + 1), scoped))
        return {
            "page": page,
            "pagecount": (page + 1) if has_next else page,
            "limit": len(video_list),
            "total": 9999 if has_next else len(video_list),
            "list": video_list
        }

    def _extract_embed_url(self, html):
        m = re.search(r"data-rocketlazyloadscript=['\"]data:text/javascript;base64,([A-Za-z0-9+/=]+)['\"]", html)
        if m:
            try:
                js = base64.b64decode(m.group(1)).decode("utf-8", errors="ignore")
                um = re.search(r'defaultUrl\s*=\s*["\']([^"\']+)["\']', js)
                if um:
                    u = um.group(1)
                    if u.startswith("http://"):
                        u = "https://" + u[7:]
                    return u
            except Exception:
                pass
        m2 = re.search(r'(https?://[^"\']+/xx/[A-Za-z0-9]+)', html)
        if m2:
            u = m2.group(1)
            if u.startswith("http://"):
                u = "https://" + u[7:]
            return u
        return ""

    def _resolve_stream(self, page_url, html=None):
        if not html:
            res = self._fetch(page_url)
            html = res.get("text", "")
        if not html:
            return ""
        m3 = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', html)
        if m3 and "preview" not in m3.group(1).lower():
            return m3.group(1)
        embed = self._extract_embed_url(html)
        if not embed:
            return ""
        emb = self._fetch(embed, referer=page_url)
        emb_html = emb.get("text", "")
        pox_m = re.search(r"let\s+pox\s*=\s*['\"]([^'\"]+)['\"]", emb_html)
        dp_m = re.search(r"let\s+dp\s*=\s*['\"]([^'\"]+)['\"]", emb_html)
        if pox_m and dp_m:
            stream = cryptojs_aes_decrypt(pox_m.group(1), dp_m.group(1))
            if stream and ("m3u8" in stream or stream.startswith("http")):
                return stream.strip().strip('"')
        m3b = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', emb_html)
        if m3b:
            return m3b.group(1)
        return ""

    def _prefer_media_playlist(self, master_url):
        if not master_url or "master.m3u8" not in master_url:
            return master_url
        res = self._fetch(master_url, referer=self.siteUrl + "/")
        text = res.get("text", "")
        if not text or "#EXTM3U" not in text:
            return master_url
        pairs = re.findall(r"#EXT-X-STREAM-INF:([^\n]*)\n([^\s]+)", text)
        if not pairs:
            return master_url
        base = master_url.rsplit("/", 1)[0] + "/"
        best_u, best_bw = None, -1
        for info, u in pairs:
            if not u.startswith("http"):
                u = base + u
            bw_m = re.search(r"BANDWIDTH=(\d+)", info)
            bw = int(bw_m.group(1)) if bw_m else 0
            if bw >= best_bw:
                best_bw, best_u = bw, u
        return best_u or master_url

    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        target_url = str(raw_id)
        res = self._fetch(target_url)
        html = res.get("text", "")
        title_m = re.search(r'<h1[^>]*>([\s\S]*?)</h1>', html, re.I)
        if not title_m:
            title_m = re.search(r'itemprop="name"\s+content="([^"]+)"', html, re.I)
        title = self._clean_text(title_m.group(1)) if title_m else "正片详情"
        cover = self._wrap_img(self._extract_img(html))
        dur_m = re.search(r'class="duration"[^>]*>[\s\S]*?([0-9:]+)', html, re.I)
        dur_str = self._clean_text(dur_m.group(1)) if dur_m else ""
        # 详情只记页面，播放时再实时解密（避免 token 过期）
        final_deliver = "raw_page@@%s" % target_url
        intro = (
            "【🔥 蝴蝶影视交流群: %s】\n"
            "• 影片标题: %s\n"
            "• 时长: %s\n"
            "• 源站: bestjavporn.me"
        ) % (self.tgGroup, title, dur_str or "完整正片")
        return {
            "list": [{
                "vod_id": target_url,
                "vod_name": title,
                "vod_pic": cover,
                "vod_actor": self.brandActor,
                "vod_director": self.brandDirector,
                "vod_remarks": "蝴蝶影视",
                "vod_content": intro.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"),
                "vod_play_from": "蝴蝶专线",
                "vod_play_url": "超清正片$%s" % final_deliver
            }]
        }

    def playerContent(self, flag, id, vipFlags):
        raw = str(id).strip()
        stream_url = ""
        if raw.startswith("raw_page@@"):
            stream_url = self._resolve_stream(raw.split("@@", 1)[1])
        elif raw.startswith("http") and (".m3u8" in raw or "videplay" in raw or ".mp4" in raw):
            stream_url = raw
        elif raw.startswith("http"):
            stream_url = self._resolve_stream(raw)

        if stream_url and "master.m3u8" in stream_url:
            try:
                stream_url = self._prefer_media_playlist(stream_url)
            except Exception:
                pass

        headers = {
            "User-Agent": self._ua,
            "Referer": "https://bestjavporn.me/",
            "Origin": "https://bestjavporn.me",
            "Accept": "*/*",
        }
        return {
            "parse": 0 if stream_url else 1,
            "playUrl": "",
            "url": stream_url if stream_url else raw,
            "header": headers
        }

    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        q = quote(str(key).strip())
        path = ("/page/%d/?s=%s" % (page, q)) if page > 1 else ("/?s=%s" % q)
        return self.categoryContent(path, page, None, {})

    def localProxy(self, params):
        url = params.get("url", "")
        if not url:
            return [404, "text/plain", b""]
        res = self._fetch(url, referer=self.siteUrl + "/")
        raw_b = res.get("bytes", b"")
        mime = "image/jpeg"
        if raw_b.startswith(b"\x89PNG"):
            mime = "image/png"
        elif raw_b.startswith(b"GIF8"):
            mime = "image/gif"
        return [res.get("code", 200), mime, raw_b]

    def action(self, action):
        return {"msg": "ok"}

    def liveContent(self):
        return ""

    def destroy(self):
        self.options = {}
