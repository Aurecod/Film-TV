#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import re
import time
import json
import base64
import html as html_lib
import urllib.request
import urllib.parse
from urllib.parse import urlparse, quote, unquote
from http.cookiejar import CookieJar
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

_AES_SBOX = [
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
    0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16
]
_AES_INV_SBOX = [0] * 256
for _i, _v in enumerate(_AES_SBOX):
    _AES_INV_SBOX[_v] = _i
_AES_RCON = [0x01,0x02,0x04,0x08,0x10,0x20,0x40,0x80,0x1b,0x36]

def _xtime(a):
    return ((a << 1) ^ 0x1b) & 0xff if a & 0x80 else (a << 1) & 0xff

def _gmul(a, b):
    r = 0
    for _ in range(8):
        if b & 1:
            r ^= a
        a = _xtime(a)
        b >>= 1
    return r

def _aes_key_expansion(key):
    w = [int.from_bytes(key[i*4:(i+1)*4], "big") for i in range(4)]
    for i in range(4, 44):
        t = w[i-1]
        if i % 4 == 0:
            t = (_AES_SBOX[(t >> 16) & 0xff] << 24 |
                 _AES_SBOX[(t >> 8) & 0xff] << 16 |
                 _AES_SBOX[t & 0xff] << 8 |
                 _AES_SBOX[(t >> 24) & 0xff]) ^ (_AES_RCON[i // 4 - 1] << 24)
        w.append(w[i-4] ^ t)
    return [b"".join(x.to_bytes(4, "big") for x in w[i:i+4]) for i in range(0, 44, 4)]

def _aes_decrypt_block(rks, block):
    s = [block[i] ^ rks[10][i] for i in range(16)]
    for rnd in range(9, 0, -1):
        s = [_AES_INV_SBOX[b] for b in
             (s[0],s[13],s[10],s[7],s[4],s[1],s[14],s[11],
              s[8],s[5],s[2],s[15],s[12],s[9],s[6],s[3])]
        rk = rks[rnd]
        s = [s[i] ^ rk[i] for i in range(16)]
        for c in range(4):
            a0,a1,a2,a3 = s[4*c],s[4*c+1],s[4*c+2],s[4*c+3]
            s[4*c]   = _gmul(a0,0x0e)^_gmul(a1,0x0b)^_gmul(a2,0x0d)^_gmul(a3,0x09)
            s[4*c+1] = _gmul(a0,0x09)^_gmul(a1,0x0e)^_gmul(a2,0x0b)^_gmul(a3,0x0d)
            s[4*c+2] = _gmul(a0,0x0d)^_gmul(a1,0x09)^_gmul(a2,0x0e)^_gmul(a3,0x0b)
            s[4*c+3] = _gmul(a0,0x0b)^_gmul(a1,0x0d)^_gmul(a2,0x09)^_gmul(a3,0x0e)
    s = [_AES_INV_SBOX[b] for b in
         (s[0],s[13],s[10],s[7],s[4],s[1],s[14],s[11],
          s[8],s[5],s[2],s[15],s[12],s[9],s[6],s[3])]
    return bytes(s[i] ^ rks[0][i] for i in range(16))

def _pkcs7_unpad(data):
    if not data:
        return data
    pad = data[-1]
    if 1 <= pad <= 16 and len(data) >= pad and data[-pad:] == bytes([pad]) * pad:
        return data[:-pad]
    return data

def _aes_ecb_decrypt(key, data):
    data = data[:len(data) - len(data) % 16]
    if len(data) < 16:
        return b""
    try:
        from javax.crypto import Cipher
        from javax.crypto.spec import SecretKeySpec
        _c = Cipher.getInstance("AES/ECB/PKCS5Padding")
        _c.init(_c.DECRYPT_MODE, SecretKeySpec(key, "AES"))
        return bytes(bytearray(_c.doFinal(data)))
    except Exception:
        pass
    try:
        from Crypto.Cipher import AES
        return _pkcs7_unpad(AES.new(key, AES.MODE_ECB).decrypt(data))
    except Exception:
        pass
    rks = _aes_key_expansion(key)
    pt = b"".join(_aes_decrypt_block(rks, data[i:i+16]) for i in range(0, len(data), 16))
    return _pkcs7_unpad(pt)

def _aes_cbc_decrypt(key, iv, data):
    data = data[:len(data) - len(data) % 16]
    if len(data) < 16:
        return b""
    try:
        from javax.crypto import Cipher
        from javax.crypto.spec import SecretKeySpec, IvParameterSpec
        _c = Cipher.getInstance("AES/CBC/NoPadding")
        _c.init(_c.DECRYPT_MODE, SecretKeySpec(key, "AES"), IvParameterSpec(iv))
        return bytes(bytearray(_c.doFinal(data)))
    except Exception:
        pass
    try:
        from Crypto.Cipher import AES
        return AES.new(key, AES.MODE_CBC, iv).decrypt(data)
    except Exception:
        pass
    rks = _aes_key_expansion(key)
    out = b""
    prev = iv
    for i in range(0, len(data), 16):
        pt = _aes_decrypt_block(rks, data[i:i+16])
        out += bytes(a ^ b for a, b in zip(pt, prev))
        prev = data[i:i+16]
    return out

def format_remarks(brand="蝴蝶影视", meta=""):
    clean_meta = str(meta or "").strip()
    clean_meta = re.sub(r"[\r\n\t]+", " ", clean_meta).strip()
    if clean_meta:
        return "%s | %s" % (brand, clean_meta)
    return brand

class Spider(SpiderBase):
    def __init__(self):
        super(Spider, self).__init__()
        self.siteUrl = "https://91porna.com"
        self._hosts = ["https://91porna.com", "https://www.91porna.com"]
        self.tgGroup = "https://t.me/tvshare23"
        self.brandActor = "🦋 TG群: @tvshare23"
        self.brandDirector = "🦋 蝴蝶影视"
        self._ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        self.options = {}

        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE

        self.cj = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj),
            urllib.request.HTTPSHandler(context=self.ctx)
        )

        self._cover_key = b"525202f9149e061d"
        self._post_key = b"f5d965df75336270"
        self._post_iv = b"97b60394abc2fbe1"
        self._pic_cache = {}

        self.categoryRoutes = {
            "now_month_hot": "/comic/index/video?category=now_month_hot",
            "original": "/comic/index/video?category=original",
            "shunv": "/comic/index/search?keyword=%E7%86%9F%E5%A5%B3",
            "luoli": "/comic/index/search?keyword=%E8%90%9D%E8%8E%89",
            "dongman": "/comic/index/search?keyword=%E5%8A%A8%E6%BC%AB",
            "heiren": "/comic/index/search?keyword=%E9%BB%91%E4%BA%BA",
            "juru": "/comic/index/search?keyword=%E5%B7%A8%E4%B9%B3",
            "huanqi": "/comic/index/search?keyword=%E6%8D%A2%E5%A6%BB",
            "neishe": "/comic/index/search?keyword=%E5%86%85%E5%B0%84",
            "anmo": "/comic/index/search?keyword=%E6%8C%89%E6%91%A9",
            "tanhua": "/comic/index/search?keyword=%E6%8E%A2%E8%8A%B1",
            "luanlun": "/comic/index/search?keyword=%E5%AE%B6%E5%BA%AD%E4%B9%B1%E4%BC%A6",
            "sanji": "/comic/index/search?keyword=%E4%B8%89%E7%BA%A7%E7%89%87",
            "cr_duanju": "/ai/chengren-duanju",
            "cr_manju": "/ai/chengren-manju",
            "ai_huanlian": "/ai/ai-huanlian",
            "ai_mogai": "/ai/ai-mogai",
            "ai_91duanju": "/ai",
            "ms_amateur": "/melonshort/amateur",
            "ms_hunjian": "/melonshort/hunjian",
            "ms_fancha": "/melonshort/fancha",
            "ms_wanghong": "/melonshort/wanghong",
            "ms_mingxing": "/melonshort/mingxing",
            "ms_zipai": "/melonshort/zipai",
            "theme_1": "/comic/av/relvideo?model=1&type=theme&order=week",
            "theme_12": "/comic/av/relvideo?model=12&type=theme&order=week",
            "theme_5": "/comic/av/relvideo?model=5&type=theme&order=week",
            "theme_6": "/comic/av/relvideo?model=6&type=theme&order=week",
            "tag_107": "/comic/av/relvideo?model=107&type=tag&order=week",
            "theme_7": "/comic/av/relvideo?model=7&type=theme&order=week"
        }

    def init(self, extend=""):
        if isinstance(extend, dict):
            self.options = extend
        elif extend:
            try:
                self.options = json.loads(extend)
            except Exception:
                self.options = {}
        host = str(self.options.get("host", "")).strip().rstrip("/")
        if host:
            self.siteUrl = host
        return True

    def getName(self):
        return "91PornA·蝴蝶影视"

    def isVideoFormat(self, url):
        if not url:
            return False
        low = url.lower()
        if any(bad in low for bad in ("preview.mp4", "sample.mp4", "trailer.mp4", "poster_loading", "loading.svg")):
            return False
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".ts", "index.png"))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self.options = {}

    def _clean_text(self, text):
        clean = re.sub(r'<[^>]+>', '', text or '')
        clean = html_lib.unescape(clean)
        return re.sub(r'[\r\n\t\s]+', ' ', clean).strip()

    def _mime(self, data):
        if not data or len(data) < 12:
            return ""
        if data[:2] == b"\xff\xd8":
            return "image/jpeg"
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return "image/webp"
        return ""

    def _decrypt_cover(self, raw, url=""):
        if not raw:
            return b""
        if self._mime(raw):
            return raw
        is_bnc = url.lower().split("?")[0].endswith(".bnc")
        modes = ("ecb", "cbc") if is_bnc else ("cbc", "ecb")
        for mode in modes:
            try:
                if mode == "ecb":
                    pt = _aes_ecb_decrypt(self._cover_key, raw)
                else:
                    pt = _aes_cbc_decrypt(self._post_key, self._post_iv, raw)
                if self._mime(pt):
                    return pt
            except Exception:
                continue
        return b""

    def _fetch_bytes(self, url, timeout=20):
        headers = {
            "User-Agent": self._ua,
            "Referer": self.siteUrl + "/"
        }
        try:
            req = urllib.request.Request(url, headers=headers)
            with self.opener.open(req, timeout=timeout) as resp:
                return resp.read()
        except Exception:
            return b""

    def _proxy_pic_url(self, pic):
        if not pic or pic.startswith("http://127.0.0.1"):
            return pic
        base = ""
        try:
            base = self.getProxyUrl() or ""
        except Exception:
            base = ""
        if not base:
            base = "http://127.0.0.1:9978/proxy?do=py"
        sep = "&" if "?" in base else "?"
        return "%s%surl=%s" % (base, sep, urllib.parse.quote(pic, safe=""))

    def _fetch(self, target_url, referer=""):
        if not target_url:
            return {"code": 0, "text": "", "bytes": b"", "err": "", "final_url": target_url}
        if target_url.startswith("//"):
            target_url = "https:" + target_url
        elif target_url.startswith("/"):
            target_url = self.siteUrl + target_url

        headers = {
            "User-Agent": self._ua,
            "Referer": referer if referer else (self.siteUrl + "/"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive"
        }

        last_err = ""
        for attempt in range(2):
            try:
                req = urllib.request.Request(target_url, headers=headers)
                with self.opener.open(req, timeout=12) as resp:
                    code = resp.getcode()
                    final_url = resp.geturl()
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
                    return {"code": code, "text": text, "bytes": raw, "err": "", "final_url": final_url}
            except urllib.error.HTTPError as e:
                last_err = "HTTP %s" % e.code
                if e.code in (451, 403, 429) and attempt == 0:
                    continue
                err_raw = ""
                try:
                    err_raw = e.read().decode("utf-8", errors="ignore")
                except Exception:
                    pass
                return {"code": e.code, "text": err_raw, "bytes": b"", "err": str(e), "final_url": target_url}
            except Exception as e:
                last_err = str(e)
                if attempt == 0:
                    continue
                return {"code": -1, "text": "", "bytes": b"", "err": str(e), "final_url": target_url}

        return {"code": -1, "text": "", "bytes": b"", "err": last_err, "final_url": target_url}

    def homeContent(self, filter):
        classes = [
            {"type_name": "热门排行榜", "type_id": "now_month_hot"},
            {"type_name": "国产原创", "type_id": "original"},
            {"type_name": "熟女做爱", "type_id": "shunv"},
            {"type_name": "可爱萝莉", "type_id": "luoli"},
            {"type_name": "成人动漫", "type_id": "dongman"},
            {"type_name": "大屌黑人", "type_id": "heiren"},
            {"type_name": "童颜巨乳", "type_id": "juru"},
            {"type_name": "少妇换妻", "type_id": "huanqi"},
            {"type_name": "内射中出", "type_id": "neishe"},
            {"type_name": "会所按摩", "type_id": "anmo"},
            {"type_name": "91探花", "type_id": "tanhua"},
            {"type_name": "家庭乱伦", "type_id": "luanlun"},
            {"type_name": "三级片", "type_id": "sanji"},
            {"type_name": "成人短剧", "type_id": "cr_duanju"},
            {"type_name": "成人漫剧", "type_id": "cr_manju"},
            {"type_name": "AI换脸", "type_id": "ai_huanlian"},
            {"type_name": "AI魔改", "type_id": "ai_mogai"},
            {"type_name": "91成人短剧", "type_id": "ai_91duanju"},
            {"type_name": "素人自拍", "type_id": "ms_amateur"},
            {"type_name": "高燃混剪", "type_id": "ms_hunjian"},
            {"type_name": "反差系列", "type_id": "ms_fancha"},
            {"type_name": "网红达人", "type_id": "ms_wanghong"},
            {"type_name": "明星大瓜", "type_id": "ms_mingxing"},
            {"type_name": "原创自拍", "type_id": "ms_zipai"},
            {"type_name": "多P群交", "type_id": "theme_1"},
            {"type_name": "无码解放", "type_id": "theme_12"},
            {"type_name": "中文字幕", "type_id": "theme_5"},
            {"type_name": "制服诱惑", "type_id": "theme_6"},
            {"type_name": "黑人专区", "type_id": "tag_107"},
            {"type_name": "SM调教", "type_id": "theme_7"}
        ]

        result = {"class": classes}

        if filter:
            video_filters = [
                {
                    "key": "category",
                    "name": "榜单子分类",
                    "value": [
                        {"n": "全部/默认", "v": ""},
                        {"n": "正在播放", "v": "play"},
                        {"n": "当前最热", "v": "now_hot"},
                        {"n": "最近更新", "v": "new_update"},
                        {"n": "91原创", "v": "original"},
                        {"n": "本月最热", "v": "now_month_hot"},
                        {"n": "10分钟以上", "v": "ten_minutes"},
                        {"n": "20分钟以上", "v": "twenty_minutes"},
                        {"n": "本月收藏", "v": "now_month_collect"},
                        {"n": "高清", "v": "hd"},
                        {"n": "每月最热", "v": "month_hot"},
                        {"n": "本月讨论", "v": "now_month_comment"},
                        {"n": "收藏最多", "v": "max_collect"}
                    ]
                },
                {
                    "key": "model",
                    "name": "题材标签",
                    "value": [
                        {"n": "全部", "v": ""},
                        {"n": "多P群交", "v": "1"},
                        {"n": "无码解放", "v": "12"},
                        {"n": "中文字幕", "v": "5"},
                        {"n": "制服诱惑", "v": "6"},
                        {"n": "黑人专区", "v": "107"},
                        {"n": "SM调教", "v": "7"}
                    ]
                }
            ]

            av_filters = [
                {
                    "key": "order",
                    "name": "排序",
                    "value": [
                        {"n": "本周最热", "v": "week"},
                        {"n": "最新发布", "v": "new"},
                        {"n": "最多播放", "v": "play"}
                    ]
                }
            ]

            filters_dict = {}
            for target_id in ("now_month_hot", "original"):
                filters_dict[target_id] = video_filters

            for av_id in ("theme_1", "theme_12", "theme_5", "theme_6", "tag_107", "theme_7"):
                filters_dict[av_id] = av_filters

            result["filters"] = filters_dict

        return result

    def homeVideoContent(self):
        return {"list": []}

    def _extract_pic_clean(self, block):
        for attr in ("data-src", "data-original", "data-thumb", "data-url"):
            m = re.search(r'%s=["\']([^"\']+)["\']' % attr, block, re.I)
            if m:
                cand = m.group(1).strip()
                if cand and not cand.startswith("data:image") and "loading" not in cand.lower():
                    return cand
        src_m = re.search(r'src=["\']([^"\']+)["\']', block, re.I)
        if src_m:
            cand = src_m.group(1).strip()
            if cand and not cand.startswith("data:image") and "loading" not in cand.lower():
                return cand
        return ""

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg or 1)
        raw_tid = str(tid).strip()

        base_path = self.categoryRoutes.get(raw_tid, "/comic/index/video?category=" + raw_tid)

        if base_path.startswith("/ai"):
            if page > 1:
                target_url = "%s/page/%d" % (base_path.rstrip("/"), page)
            else:
                target_url = base_path
        else:
            sep = "&" if "?" in base_path else "?"
            target_url = "%s%spage=%d" % (base_path, sep, page)

        if extend and isinstance(extend, dict):
            c_val = extend.get("category", "")
            if c_val:
                target_url = re.sub(r'category=[^&]*', "category=%s" % urllib.parse.quote(c_val), target_url)
                if "category=" not in target_url:
                    sep = "&" if "?" in target_url else "?"
                    target_url += "%scategory=%s" % (sep, urllib.parse.quote(c_val))
            m_val = extend.get("model", "")
            if m_val:
                target_url += "&model=%s" % urllib.parse.quote(m_val)
            o_val = extend.get("order", "")
            if o_val:
                target_url += "&order=%s" % urllib.parse.quote(o_val)

        res = self._fetch(target_url)
        html_text = res.get("text", "")

        clean_html = re.sub(r'<(?:header|nav|footer|aside)[^>]*>[\s\S]*?</(?:header|nav|footer|aside)>', '', html_text, flags=re.I)
        vod_list = []

        if "video-item" in clean_html:
            cards = clean_html.split('class="video-item"')
            for block in cards[1:]:
                href_m = re.search(r'<a\s+[^>]*href=["\']([^"\']+)["\']', block, re.I)
                if not href_m:
                    continue
                v_href = href_m.group(1).strip()
                if any(bad in v_href for bad in ("javascript", "#", "login", "register")):
                    continue

                title = ""
                title_m = re.search(r'title=["\']([^"\']+)["\']', block, re.I)
                if title_m:
                    title = self._clean_text(title_m.group(1))
                if not title:
                    alt_m = re.search(r'alt=["\']([^"\']+)["\']', block, re.I)
                    if alt_m:
                        title = self._clean_text(alt_m.group(1))
                if not title:
                    text_m = re.search(r'<(?:h\d|div|p|span)[^>]*class=["\'][^"\']*(?:title|name)[^"\']*["\'][^>]*>([\s\S]*?)</(?:h\d|div|p|span)>', block, re.I)
                    if text_m:
                        title = self._clean_text(text_m.group(1))

                pic = self._extract_pic_clean(block)

                dur_m = re.search(r'(?:class=["\'][^"\']*(?:duration|time)[^"\']*["\'][^>]*>|>\s*)(\d{1,2}:\d{2}(?::\d{2})?)', block, re.I)
                duration = dur_m.group(1).strip() if dur_m else ""
                remarks = format_remarks("蝴蝶影视", duration)

                full_href = v_href if v_href.startswith("http") else urllib.parse.urljoin(self.siteUrl, v_href)
                full_pic = pic if pic.startswith("http") else (urllib.parse.urljoin(self.siteUrl, pic) if pic else "")

                vod_list.append({
                    "vod_id": full_href,
                    "vod_name": title or "正片视频",
                    "vod_pic": self._proxy_pic_url(full_pic),
                    "vod_remarks": remarks,
                    "style": {"type": "rect", "ratio": 1.78}
                })

        elif "drama-card" in clean_html:
            cards = re.findall(r'(<a[^>]*class=["\'][^"\']*drama-card[^"\']*["\'][^>]*>[\s\S]*?</a>)', clean_html, re.I)
            for block in cards:
                href_m = re.search(r'href=["\']([^"\']+)["\']', block, re.I)
                if not href_m:
                    continue
                v_href = href_m.group(1).strip()

                title = ""
                title_m = re.search(r'title=["\']([^"\']+)["\']', block, re.I)
                if title_m:
                    title = self._clean_text(title_m.group(1))
                if not title:
                    h3_m = re.search(r'<h3[^>]*>([\s\S]*?)</h3>', block, re.I)
                    if h3_m:
                        title = self._clean_text(h3_m.group(1))

                pic = self._extract_pic_clean(block)

                eps_m = re.search(r'class=["\'][^"\']*drama-card__eps[^"\']*["\'][^>]*>([\s\S]*?)</span>', block, re.I)
                eps_str = self._clean_text(eps_m.group(1)) if eps_m else ""
                remarks = format_remarks("蝴蝶影视", eps_str)

                full_href = v_href if v_href.startswith("http") else urllib.parse.urljoin(self.siteUrl, v_href)
                full_pic = pic if pic.startswith("http") else (urllib.parse.urljoin(self.siteUrl, pic) if pic else "")

                vod_list.append({
                    "vod_id": full_href,
                    "vod_name": title or "成人短剧",
                    "vod_pic": self._proxy_pic_url(full_pic),
                    "vod_remarks": remarks,
                    "style": {"type": "rect", "ratio": 0.75}
                })

        elif "video-card" in clean_html:
            cards = re.findall(r'(<article[^>]*class=["\'][^"\']*video-card[^"\']*["\'][^>]*>[\s\S]*?</article>)', clean_html, re.I)
            if not cards:
                cards = re.findall(r'(<(?:div|article|li)[^>]*class=["\'][^"\']*video-card[^"\']*["\'][^>]*>[\s\S]*?</(?:div|article|li)>)', clean_html, re.I)
            if not cards:
                cards = clean_html.split('class="video-card')[1:]

            for block in cards:
                href_m = re.search(r'<a[^>]*href=["\']([^"\']+)["\']', block, re.I)
                if not href_m:
                    continue
                v_href = href_m.group(1).strip()

                title_m = re.search(r'title=["\']([^"\']+)["\']', block, re.I)
                title = self._clean_text(title_m.group(1)) if title_m else ""
                if not title:
                    alt_m = re.search(r'alt=["\']([^"\']+)["\']', block, re.I)
                    if alt_m:
                        title = self._clean_text(alt_m.group(1))
                if not title:
                    t_m = re.search(r'<[^>]*class=["\'][^"\']*title[^"\']*["\'][^>]*>([\s\S]*?)</', block, re.I)
                    if t_m:
                        title = self._clean_text(t_m.group(1))

                pic = self._extract_pic_clean(block)

                dur_m = re.search(r'class=["\'][^"\']*badge-duration[^"\']*["\'][^>]*>([\s\S]*?)</span>', block, re.I)
                dur_str = self._clean_text(dur_m.group(1)) if dur_m else ""
                remarks = format_remarks("蝴蝶影视", dur_str)

                full_href = v_href if v_href.startswith("http") else urllib.parse.urljoin(self.siteUrl, v_href)
                full_pic = pic if pic.startswith("http") else (urllib.parse.urljoin(self.siteUrl, pic) if pic else "")

                vod_list.append({
                    "vod_id": full_href,
                    "vod_name": title or "微视频",
                    "vod_pic": self._proxy_pic_url(full_pic),
                    "vod_remarks": remarks,
                    "style": {"type": "rect", "ratio": 1.78}
                })

        return {
            "page": page,
            "pagecount": page + 1 if len(vod_list) >= 15 else page,
            "limit": 20,
            "total": 9999,
            "list": vod_list
        }

    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        target_url = raw_id if raw_id.startswith("http") else urllib.parse.urljoin(self.siteUrl, raw_id)

        res = self._fetch(target_url)
        detail_html = res.get("text", "")

        title_m = re.search(r'<title[^>]*>(.*?)</title>', detail_html, re.I)
        raw_title = title_m.group(1).split("-")[0].split("_")[0].strip() if title_m else "正片详情"
        vod_name = self._clean_text(raw_title)

        pic = self._extract_pic_clean(detail_html)
        full_pic = pic if pic.startswith("http") else (urllib.parse.urljoin(self.siteUrl, pic) if pic else "")

        desc = (
            "【🔥 官方交流群: %s】\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "蝴蝶专线 极速硬解 | 4K全景原画画质"
        ) % self.tgGroup

        episodes = []

        if "/ai" in target_url:
            ep_list_match = re.search(r'<(?:div|ul)[^>]*class=["\'][^"\']*(?:ep|chapter|series|list)[^"\']*["\'][^>]*>([\s\S]*?)</(?:div|ul)>', detail_html, re.I)
            ep_corpus = ep_list_match.group(1) if ep_list_match else detail_html

            ep_links = re.findall(r'<a[^>]+href=["\']([^"\']*(?:/ai/|\?ep=|\/play)[^"\']*)["\'][^>]*>([\s\S]*?)</a>', ep_corpus, re.I)
            seen_eps = set()
            for ep_href, ep_anchor in ep_links:
                ep_text = self._clean_text(ep_anchor)
                if not ep_text or any(bad in ep_text for bad in ("短剧", "漫剧", "换脸", "魔改", "首页", "返回")):
                    continue
                if ep_href in seen_eps:
                    continue
                seen_eps.add(ep_href)
                full_ep_href = ep_href if ep_href.startswith("http") else urllib.parse.urljoin(self.siteUrl, ep_href)
                episodes.append("%s$%s" % (ep_text, full_ep_href))

        if not episodes:
            episodes.append("超清正片$%s" % target_url)

        play_url_str = "#".join(episodes)

        vod = {
            "vod_id": raw_id,
            "vod_name": vod_name,
            "vod_pic": self._proxy_pic_url(full_pic),
            "vod_actor": self.brandActor,
            "vod_director": self.brandDirector,
            "vod_remarks": format_remarks("蝴蝶影视", "正片"),
            "vod_content": desc,
            "vod_play_from": "蝴蝶专线",
            "vod_play_url": play_url_str
        }
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        raw_target = str(id).strip()
        target_play_page = raw_target if raw_target.startswith("http") else urllib.parse.urljoin(self.siteUrl, raw_target)

        headers = {
            "User-Agent": self._ua,
            "Referer": self.siteUrl + "/"
        }

        return {
            "parse": 1,
            "playUrl": "",
            "url": target_play_page,
            "header": headers
        }

    def searchContent(self, key, quick, pg="1"):
        page = int(pg or 1)
        search_path = "/comic/index/search?keyword=%s" % urllib.parse.quote_plus(str(key).strip())
        if page > 1:
            search_path += "&page=%d" % page

        res = self._fetch(search_path)
        html_text = res.get("text", "")

        splits = html_text.split('class="video-item"')
        vod_list = []
        for block in splits[1:]:
            href_m = re.search(r'<a\s+[^>]*href=["\']([^"\']+)["\']', block, re.I)
            if not href_m:
                continue
            v_href = href_m.group(1).strip()
            title_m = re.search(r'title=["\']([^"\']+)["\']', block, re.I)
            title = self._clean_text(title_m.group(1)) if title_m else "正片视频"
            pic = self._extract_pic_clean(block)

            full_href = v_href if v_href.startswith("http") else urllib.parse.urljoin(self.siteUrl, v_href)
            full_pic = pic if pic.startswith("http") else (urllib.parse.urljoin(self.siteUrl, pic) if pic else "")

            vod_list.append({
                "vod_id": full_href,
                "vod_name": title,
                "vod_pic": self._proxy_pic_url(full_pic),
                "vod_remarks": "蝴蝶影视",
                "style": {"type": "rect", "ratio": 1.78}
            })

        return {
            "page": page,
            "pagecount": page + 1 if len(vod_list) >= 15 else page,
            "limit": 20,
            "total": 9999,
            "list": vod_list
        }

    def action(self, action):
        return {"msg": "ok"}

    def liveContent(self):
        return ""

    def localProxy(self, params):
        try:
            if not isinstance(params, dict):
                return [404, "text/plain", b"Not Found"]
            url = (params.get("url") or params.get("pic") or "").strip()
            if not url or url.startswith("http://127.0.0.1"):
                return [404, "text/plain", b"Not Found"]

            if url in self._pic_cache:
                return self._pic_cache[url]

            raw = self._fetch_bytes(url, timeout=15)
            if not raw:
                return [404, "text/plain", b"Not Found"]

            img = self._decrypt_cover(raw, url)
            if img:
                mime = self._mime(img) or "image/jpeg"
                res = [200, mime, img]
                if len(self._pic_cache) < 80:
                    self._pic_cache[url] = res
                return res

            return [404, "text/plain", b"Not Found"]
        except Exception:
            return [404, "text/plain", b"Not Found"]