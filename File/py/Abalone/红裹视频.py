#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import re
import json
import base64
import urllib.request
import urllib.parse
from urllib.parse import quote, unquote
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

def format_remarks(brand="蝴蝶影视", meta=""):
    clean_meta = str(meta or "").strip()
    clean_meta = re.sub(r"[\r\n\t]+", " ", clean_meta).strip()
    if clean_meta:
        return "%s | %s" % (brand, clean_meta)
    return brand

def clean_label(text):
    clean = re.sub(r"[\$\#\r\n\t]+", " ", str(text or "")).strip()
    clean = re.sub(r"\s+", " ", clean)
    if len(clean) > 20:
        clean = clean[:20] + "..."
    return clean

class Spider(SpiderBase):
    def __init__(self):
        super(Spider, self).__init__()
        self.siteUrl = "https://hguoo.com"
        self.tgGroup = "https://t.me/tvshare23"
        self.brandActor = "🦋 TG群: @tvshare23"
        self.brandDirector = "🦋 蝴蝶影视"
        self._ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        self.options = {}

        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE

        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj),
            urllib.request.HTTPSHandler(context=self.ctx)
        )

        self.classes = [
            {"type_id": "/category/%E4%BA%BA%E5%A6%BB%E7%B3%BB%E5%88%97-101", "type_name": "人妻系列"},
            {"type_id": "/category/%E6%97%A5%E9%9F%A9%E7%B2%BE%E5%93%81-102", "type_name": "日韩精品"},
            {"type_id": "/category/%E5%8E%9F%E5%88%9B%E4%B9%B1%E4%BC%A6-104", "type_name": "原创乱伦"},
            {"type_id": "/category/%E9%AC%BC%E7%88%B6%E6%93%8D%E5%A5%B3-105", "type_name": "鬼父操女"},
            {"type_id": "/category/%E5%AB%82%E5%AD%90%E8%AF%B1%E6%83%91-106", "type_name": "嫂子诱惑"},
            {"type_id": "/category/%E5%A7%90%E5%A4%AB%E5%B0%8F%E5%A7%A8%E5%AD%90-107", "type_name": "姐夫小姨子"},
            {"type_id": "/category/%E5%85%84%E5%BC%9F%E5%A7%90%E5%A6%B9-108", "type_name": "兄弟姐妹"},
            {"type_id": "/category/%E9%A3%8E%E9%9F%B5%E5%B2%B3%E6%AF%8D-109", "type_name": "风韵岳母"},
            {"type_id": "/category/%E5%84%BF%E5%AA%B3%E7%8C%AE%E7%A9%B4-110", "type_name": "儿媳献穴"},
            {"type_id": "/category/%E5%AE%B6%E6%97%8F%E6%B7%AB%E8%B6%B4-111", "type_name": "家族淫趴"},
            {"type_id": "/category/%E4%B8%AD%E6%96%87%E5%AD%97%E5%B9%95-112", "type_name": "中文字幕"},
            {"type_id": "/category/%E5%88%B6%E6%9C%8D%E8%AF%B1%E6%83%91-113", "type_name": "制服诱惑"},
            {"type_id": "/category/%E5%B8%88%E7%94%9F%E8%BF%B7%E6%83%85-114", "type_name": "师生迷情"},
            {"type_id": "/category/av%E8%A7%A3%E8%AF%B4-115", "type_name": "AV解说"},
            {"type_id": "/category/sm%E9%87%8D%E5%91%B3-116", "type_name": "SM重味"},
            {"type_id": "/category/%E4%BC%A6%E7%90%86%E5%BD%B1%E7%89%87-117", "type_name": "伦理影片"},
            {"type_id": "/category/%E6%97%A5%E9%9F%A9%E6%97%A0%E7%A0%81-118", "type_name": "日韩无码"},
            {"type_id": "/category/%E5%BC%BA%E5%A5%B8%E4%B9%B1%E4%BC%A6-119", "type_name": "强奸乱伦"},
            {"type_id": "/category/%E5%90%83%E7%93%9C%E9%BB%91%E6%96%99-120", "type_name": "吃瓜黑料"},
            {"type_id": "/category/%E9%85%92%E5%BA%97%E6%8E%A2%E8%8A%B1-121", "type_name": "酒店探花"},
            {"type_id": "/category/sm%E8%B0%83%E6%95%99-122", "type_name": "SM调教"},
            {"type_id": "/category/ai%E6%8D%A2%E8%84%B8-123", "type_name": "AI换脸"},
            {"type_id": "/category/%E5%9B%BD%E4%BA%A7%E4%B8%BB%E6%92%AD-124", "type_name": "国产主播"},
            {"type_id": "/category/%E6%B7%AB%E6%AF%8D%E5%85%BD%E5%84%BF-125", "type_name": "淫母兽儿"},
            {"type_id": "/category/%E8%BF%91%E4%BA%B2%E7%9B%B8%E5%A5%B8-126", "type_name": "近亲相奸"},
            {"type_id": "/category/%E6%AC%A7%E7%BE%8E%E5%8A%B2%E7%88%86-127", "type_name": "欧美劲爆"},
            {"type_id": "/category/%E5%BC%BA%E5%A5%B8%E8%BF%B7%E5%A5%B8-144", "type_name": "强奸迷奸"},
            {"type_id": "/category/%E9%87%8E%E6%88%98%E8%BD%A6%E9%9C%87-145", "type_name": "野战车震"},
            {"type_id": "/category/%E7%86%9F%E5%A5%B3%E5%B0%91%E5%A6%87-146", "type_name": "熟女少妇"},
            {"type_id": "/category/%E5%8F%8D%E5%B7%AE%E6%AF%8D%E7%8B%97-147", "type_name": "反差母狗"},
            {"type_id": "/category/%E4%BA%BA%E5%A6%BB%E5%B7%A8%E4%B9%B3-148", "type_name": "人妻巨乳"},
            {"type_id": "/category/%E8%87%AA%E6%8B%8D%E5%81%B7%E6%8B%8D-149", "type_name": "自拍偷拍"},
            {"type_id": "/category/%E6%95%99%E5%B8%88%E5%AD%A6%E7%94%9F-150", "type_name": "教师学生"},
            {"type_id": "/category/3d%E5%8A%A8%E6%BC%AB-151", "type_name": "3D动漫"},
            {"type_id": "/category/%E7%9F%AD%E8%A7%86%E9%A2%91-152", "type_name": "短视频"}
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
        return "红裹视频"

    def isVideoFormat(self, url):
        low = (url or "").lower()
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".mkv", ".ts"))

    def manualVideoCheck(self):
        return False

    def _fetch(self, target_url, referer=""):
        if not target_url:
            return {"code": 0, "text": "", "bytes": b"", "err": "", "final_url": ""}
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
                with self.opener.open(req, timeout=8) as resp:
                    code = resp.getcode()
                    final_url = resp.geturl()
                    raw = resp.read()
                    enc = getattr(resp, "headers", {}).get("Content-Encoding", "")
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
        result = {"class": self.classes}
        if filter:
            result["filters"] = {}
        return result

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        del filter, extend
        page = 1
        try:
            page = int(pg)
        except Exception:
            page = 1

        cat_path = str(tid).strip()
        sep = "&" if "?" in cat_path else "?"
        target_url = "%s%s%spage=%s" % (self.siteUrl, cat_path, sep, page) if page > 1 else (self.siteUrl + cat_path)

        res = self._fetch(target_url)
        html = res.get("text", "")

        items = []
        raw_cards = re.findall(r'<a[^>]+href=["\'](/video/[^"\']+)["\'][^>]*>([\s\S]*?)</a>', html, re.I)
        seen_vids = set()

        for href, inner in raw_cards:
            if href in seen_vids:
                continue
            seen_vids.add(href)

            img_m = re.search(r'(?:src|data-src|data-original)=["\']([^"\']+)["\']', inner)
            pic = img_m.group(1) if img_m else ""
            if pic.startswith("//"):
                pic = "https:" + pic
            elif pic.startswith("/"):
                pic = self.siteUrl + pic

            title_m = re.search(r'(?:title=["\']([^"\']+)["\']|alt=["\']([^"\']+)["\']|<div[^>]*class=["\'][^"\']*(?:title|name)[^"\']*["\'][^>]*>([\s\S]*?)</div>|<span[^>]*class=["\'][^"\']*(?:title|name)[^"\']*["\'][^>]*>([\s\S]*?)</span>)', inner, re.I)
            name = ""
            if title_m:
                name = title_m.group(1) or title_m.group(2) or title_m.group(3) or title_m.group(4)
                name = re.sub(r'<[^>]+>', '', name or "").strip()

            dur_m = re.search(r'class=["\'][^"\']*(?:duration|time|tag)[^"\']*["\'][^>]*>([\s\S]*?)<', inner, re.I)
            remark = dur_m.group(1).strip() if dur_m else "HD"

            if name and href:
                items.append({
                    "vod_id": href,
                    "vod_name": name,
                    "vod_pic": pic,
                    "vod_remarks": format_remarks("蝴蝶影视", remark),
                    "style": {"type": "rect", "ratio": 1.78}
                })

        return {
            "page": page,
            "pagecount": page + 1 if len(items) >= 20 else page,
            "limit": len(items) if items else 20,
            "total": 999 if len(items) >= 20 else len(items),
            "list": items
        }

    def _extract_play_stream(self, html):
        m_vip = re.search(r'["\']vipPlayUrl["\']\s*:\s*["\']([^"\']+)["\']', html)
        if m_vip:
            cand = m_vip.group(1)
            if "url=" in cand:
                raw_url = cand.split("url=", 1)[1].split("&")[0]
                return unquote(raw_url)

        m_play = re.search(r'window\.__MAYI_PLAY_URL__\s*=\s*["\']([^"\']+)["\']', html)
        if m_play:
            cand = m_play.group(1)
            if "url=" in cand:
                raw_url = cand.split("url=", 1)[1].split("&")[0]
                return unquote(raw_url)
            elif cand.startswith("http"):
                return cand

        direct_m = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', html)
        if direct_m:
            return direct_m.group(1)

        return ""

    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        detail_url = self.siteUrl + raw_id if str(raw_id).startswith("/") else str(raw_id)

        res = self._fetch(detail_url)
        html = res.get("text", "")

        title = ""
        h1_m = re.search(r'<h1[^>]*>([\s\S]*?)</h1>', html, re.I)
        if h1_m:
            title = re.sub(r'<[^>]+>', '', h1_m.group(1)).strip()

        if not title:
            title_m = re.search(r'<title>(.*?)</title>', html, re.I)
            if title_m:
                raw_t = title_m.group(1).strip()
                if " - " in raw_t:
                    parts = raw_t.split(" - ")
                    title = " - ".join(parts[:-2]) if len(parts) >= 3 else parts[0]
                else:
                    title = raw_t

        title = re.sub(r'[\$\#\r\n\t]+', ' ', title).strip() or "超清正片"

        img_m = re.search(r'property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
        pic = img_m.group(1) if img_m else ""
        if pic.startswith("//"):
            pic = "https:" + pic

        main_stream = self._extract_play_stream(html)

        rec_cards = re.findall(r'<a[^>]+href=["\'](/video/\d+)["\'][^>]*>([\s\S]*?)</a>', html, re.I)
        seen_urls = set([raw_id, raw_id.replace(self.siteUrl, ""), detail_url])

        episodes = ["正片$%s@@@%s" % (main_stream, quote(title))]
        rec_idx = 1

        for href, inner in rec_cards:
            if href in seen_urls:
                continue
            seen_urls.add(href)

            t_match = re.search(r'(?:title=["\']([^"\']+)["\']|alt=["\']([^"\']+)["\']|<div[^>]*class=["\'][^"\']*(?:title|name)[^"\']*["\'][^>]*>([\s\S]*?)</div>|<span[^>]*class=["\'][^"\']*(?:title|name)[^"\']*["\'][^>]*>([\s\S]*?)</span>)', inner, re.I)
            r_title = ""
            if t_match:
                r_title = t_match.group(1) or t_match.group(2) or t_match.group(3) or t_match.group(4)
                r_title = re.sub(r'<[^>]+>', '', r_title or "").strip()
            if not r_title:
                clean_inner = re.sub(r'<[^>]+>', '', inner).strip()
                if len(clean_inner) >= 4:
                    r_title = clean_inner.split("\n")[0].strip()

            if r_title:
                r_title = re.sub(r'[\$\#\r\n\t]+', ' ', r_title).strip()
                clean_t = clean_label(r_title)
                episodes.append("%02d·%s$%s@@@%s" % (rec_idx, clean_t, href, quote(r_title)))
                rec_idx += 1
                if rec_idx > 24:
                    break

        full_desc = "🦋 蝴蝶影视专线直连 | 官方交流群: @tvshare23 | 4K高清原生画质"

        vod = {
            "vod_id": raw_id,
            "vod_name": title,
            "vod_pic": pic,
            "vod_actor": self.brandActor,
            "vod_director": self.brandDirector,
            "vod_remarks": format_remarks("蝴蝶影视", "全%s部连播" % len(episodes)),
            "vod_content": full_desc,
            "vod_play_from": "蝴蝶专线",
            "vod_play_url": "#".join(episodes)
        }

        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        raw_val = str(id).strip()
        desc_title = ""
        if "@@@" in raw_val:
            target, raw_title = raw_val.split("@@@", 1)
            desc_title = unquote(raw_title)
        else:
            target = raw_val

        if ".m3u8" in target.lower() or ".mp4" in target.lower():
            real_stream = target
        else:
            target_url = self.siteUrl + target if str(target).startswith("/") else str(target)
            res = self._fetch(target_url)
            real_stream = self._extract_play_stream(res.get("text", ""))
            if not real_stream:
                real_stream = target_url

        result = {
            "parse": 0 if (".m3u8" in real_stream.lower() or ".mp4" in real_stream.lower()) else 1,
            "playUrl": "",
            "url": real_stream,
            "header": {
                "User-Agent": self._ua,
                "Referer": self.siteUrl + "/"
            }
        }
        if desc_title:
            result["desc"] = desc_title
        return result

    def searchContent(self, key, quick, pg="1"):
        return {"page": 1, "pagecount": 1, "limit": 0, "total": 0, "list": []}

    def action(self, action):
        return {"msg": "ok"}

    def liveContent(self):
        return ""

    def localProxy(self, params):
        return [404, "text/plain; charset=utf-8", "Proxy not configured"]

    def destroy(self):
        self.options = {}