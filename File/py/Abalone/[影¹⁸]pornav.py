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
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        def getCache(self, key): return None
        def setCache(self, key, value): return "fail"
        def delCache(self, key): return "fail"

def format_remarks(brand="蝴蝶影视", meta=""):
    clean_meta = str(meta or "").strip()
    clean_meta = re.sub(r"[\r\n\t]+", " ", clean_meta).strip()
    if clean_meta:
        return "%s · %s" % (brand, clean_meta)
    return brand

class Spider(BaseSpider):
    def __init__(self):
        super(Spider, self).__init__()
        self.siteUrl = "https://app-1.pornavav.shop"
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

        self.categories = [
            "精品推荐", "国产精品", "主播秀色", "日本有码", "日本无码",
            "中文字幕", "童颜巨乳", "性感人妻", "强奸乱伦", "欧美情色",
            "三级伦理", "卡通动漫", "丝袜OL", "自拍偷拍", "日本片商",
            "剧情介绍", "网曝系列", "麻豆传媒", "明星换脸", "国产乱伦",
            "国产丝袜", "国产SM", "国产人妻", "探花嫖娼", "同性恋"
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
        return "蝴蝶影视"

    def isVideoFormat(self, url):
        low = (url or "").lower()
        if any(bad in low for bad in ("preview.mp4", "sample.mp4", "trailer.mp4", "top_banner", "adc", "stat.php")):
            return False
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".mkv", ".avi", ".ts", ".mpd", "index.png"))

    def manualVideoCheck(self):
        return False

    def _clean_m3u8_url(self, raw_str):
        if not raw_str:
            return ""
        m = re.search(r'(https?://(?:(?!localhost|127\.0\.0\.1)[^\s"\'\$<>])+\.m3u8[^\s"\'\$<>]*)', raw_str)
        if m:
            return m.group(1).replace("\\u002F", "/").replace("\\/", "")
        return ""

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
                with self.opener.open(req, timeout=12) as resp:
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
        classes = []
        for c_name in self.categories:
            classes.append({"type_name": c_name, "type_id": c_name})

        sort_values = [
            {"n": "最新视频", "v": ""},
            {"n": "最新点播", "v": "db"},
            {"n": "最多点击", "v": "h"},
            {"n": "最多弹幕", "v": "d"},
            {"n": "最新弹幕", "v": "dt"},
            {"n": "最多评论", "v": "p"},
            {"n": "最新评论", "v": "pt"},
            {"n": "最多收藏", "v": "s"},
            {"n": "最新收藏", "v": "st"},
            {"n": "最多点赞", "v": "z"},
            {"n": "最新点赞", "v": "zt"}
        ]

        filters_dict = {}
        for c_name in self.categories:
            filters_dict[c_name] = [
                {
                    "key": "rq",
                    "name": "排序",
                    "value": sort_values
                }
            ]

        result = {"class": classes}
        if filter:
            result["filters"] = filters_dict
        return result

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        del filter
        slug = str(tid).strip("/")
        page_num = int(pg) if pg else 1
        extend_dict = extend if isinstance(extend, dict) else {}
        rq_val = extend_dict.get("rq", "")

        target_category = slug if slug in self.categories else "精品推荐"
        encoded_fenlei = quote(target_category)

        if page_num > 1:
            req_path = "/?fenlei=%s&video=%d.html" % (encoded_fenlei, page_num)
        else:
            req_path = "/?fenlei=%s" % encoded_fenlei

        if rq_val:
            req_path += "&rq=%s" % rq_val

        res = self._fetch(self.siteUrl + req_path)
        html_text = res.get("text", "")
        clean_html = re.sub(r'<(?:nav|header|footer)[^>]*>[\s\S]*?</(?:nav|header|footer)>', '', html_text, flags=re.I)

        card_blocks = re.findall(
            r'(<a[^>]+href=["\']([^"\']*(?:\.html|\?play=|\/v\/|\/view\/)[^"\']*)["\'][^>]*>[\s\S]*?</a>)',
            clean_html,
            re.I
        )

        extracted_cards = []
        for block, href in card_blocks:
            if any(bad in href for bad in ("fenlei=", "categories=", "tags-ch", "share", "logins", "history", "liked", "collect", "watchlater", "logout")):
                continue

            img_m = re.search(r'(?:src|data-src|data-original|data-thumb)=["\']([^"\']+\.(?:jpg|jpeg|png|webp)[^"\']*)["\']', block, re.I)
            if not img_m:
                continue

            pic = img_m.group(1).strip()
            if pic.startswith("//"):
                pic = "https:" + pic
            elif pic.startswith("/"):
                pic = self.siteUrl + pic

            title_m = re.search(r'title=["\']([^"\']+)["\']', block)
            if not title_m:
                title_m = re.search(r'<img[^>]+alt=["\']([^"\']+)["\']', block)
            title = title_m.group(1).strip() if title_m else ""
            if not title:
                text_clean = re.sub(r'<[^>]+>', '', block).strip()
                title = text_clean.split("\n")[0].strip()

            meta_m = re.search(r'class=["\'][^"\']*(?:duration|time|score|hd|views)[^"\']*["\'][^>]*>([\s\S]*?)<', block, re.I)
            meta_val = re.sub(r'<[^>]+>', '', meta_m.group(1)).strip() if meta_m else ""

            extracted_cards.append({
                "vod_id": href,
                "vod_name": title if title else "未命名视频",
                "vod_pic": pic,
                "vod_remarks": format_remarks("🦋 蝴蝶影视", meta_val),
                "style": {"type": "rect", "ratio": 1.78}
            })

        max_page = 1
        page_nums = re.findall(r'video=(\d+)\.html', html_text)
        if page_nums:
            max_page = max([int(x) for x in page_nums])

        return {
            "page": page_num,
            "pagecount": max_page if max_page > 0 else 1,
            "limit": 20,
            "total": max_page * 20,
            "list": extracted_cards
        }

    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        detail_path = raw_id
        if not detail_path.startswith("http"):
            detail_path = self.siteUrl + ("/" + detail_path.lstrip("/"))

        res = self._fetch(detail_path)
        detail_html = res.get("text", "")

        title_m = re.search(r'<title>(.*?)</title>', detail_html, re.I)
        raw_title = title_m.group(1).split("-")[0].strip() if title_m else "正片"

        desc_m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)["\']', detail_html, re.I)
        raw_desc = desc_m.group(1).strip() if desc_m else ""
        if raw_desc:
            vod_content = "🦋 蝴蝶影视专线直连 | %s | 官方交流群: @tvshare23" % raw_desc
        else:
            vod_content = "🦋 蝴蝶影视专线加速播放 | 官方TG交流群：@tvshare23 | 4K高清原生极速画质"

        m3u8_matches = re.findall(r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', detail_html, re.I)
        final_play_url = ""
        if m3u8_matches:
            clean_url = self._clean_m3u8_url(m3u8_matches[0])
            final_play_url = clean_url if clean_url else m3u8_matches[0]
        else:
            mp4_matches = re.findall(r'["\'](https?://[^"\']+\.mp4[^"\']*)["\']', detail_html, re.I)
            if mp4_matches:
                final_play_url = mp4_matches[0]
            else:
                play_vars = re.findall(r'(?:var|let|const)?\s*(?:url|videoUrl|playUrl|m3u8|src|file)\s*=\s*["\']([^"\']+)["\']', detail_html, re.I)
                for cand in play_vars:
                    if any(ext in cand.lower() for ext in (".m3u8", ".mp4")):
                        final_play_url = cand
                        break

        play_url_entry = "超清正片$%s" % (final_play_url if final_play_url else detail_path)

        vod = {
            "vod_id": raw_id,
            "vod_name": raw_title,
            "vod_pic": "",
            "vod_actor": self.brandActor,
            "vod_director": self.brandDirector,
            "vod_remarks": format_remarks("🦋 蝴蝶影视", "超清"),
            "vod_content": vod_content,
            "vod_play_from": "蝴蝶专线",
            "vod_play_url": play_url_entry
        }

        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        target = str(id).strip()
        headers = {
            "User-Agent": self._ua,
            "Referer": self.siteUrl + "/"
        }
        return {
            "parse": 0 if any(k in target.lower() for k in (".m3u8", ".mp4")) else 1,
            "playUrl": "",
            "url": target,
            "header": headers
        }

    def searchContent(self, key, quick, pg="1"):
        clean_key = quote(str(key).strip())
        page_num = int(pg) if pg else 1
        req_path = "/?wd=%s&video=%d.html" % (clean_key, page_num) if page_num > 1 else "/?wd=%s" % clean_key

        res = self._fetch(self.siteUrl + req_path)
        html_text = res.get("text", "")
        clean_html = re.sub(r'<(?:nav|header|footer)[^>]*>[\s\S]*?</(?:nav|header|footer)>', '', html_text, flags=re.I)

        card_blocks = re.findall(
            r'(<a[^>]+href=["\']([^"\']*(?:\.html|\?play=|\/v\/|\/view\/)[^"\']*)["\'][^>]*>[\s\S]*?</a>)',
            clean_html,
            re.I
        )

        extracted_cards = []
        for block, href in card_blocks:
            if any(bad in href for bad in ("fenlei=", "categories=", "tags-ch", "share", "logins", "history", "liked", "collect", "watchlater", "logout")):
                continue

            img_m = re.search(r'(?:src|data-src|data-original|data-thumb)=["\']([^"\']+\.(?:jpg|jpeg|png|webp)[^"\']*)["\']', block, re.I)
            if not img_m:
                continue

            pic = img_m.group(1).strip()
            if pic.startswith("//"):
                pic = "https:" + pic
            elif pic.startswith("/"):
                pic = self.siteUrl + pic

            title_m = re.search(r'title=["\']([^"\']+)["\']', block)
            if not title_m:
                title_m = re.search(r'<img[^>]+alt=["\']([^"\']+)["\']', block)
            title = title_m.group(1).strip() if title_m else ""
            if not title:
                text_clean = re.sub(r'<[^>]+>', '', block).strip()
                title = text_clean.split("\n")[0].strip()

            meta_m = re.search(r'class=["\'][^"\']*(?:duration|time|score|hd|views)[^"\']*["\'][^>]*>([\s\S]*?)<', block, re.I)
            meta_val = re.sub(r'<[^>]+>', '', meta_m.group(1)).strip() if meta_m else ""

            extracted_cards.append({
                "vod_id": href,
                "vod_name": title if title else "未命名视频",
                "vod_pic": pic,
                "vod_remarks": format_remarks("🦋 蝴蝶影视", meta_val),
                "style": {"type": "rect", "ratio": 1.78}
            })

        max_page = 1
        page_nums = re.findall(r'video=(\d+)\.html', html_text)
        if page_nums:
            max_page = max([int(x) for x in page_nums])

        return {
            "page": page_num,
            "pagecount": max_page if max_page > 0 else 1,
            "limit": 20,
            "total": max_page * 20,
            "list": extracted_cards
        }

    def action(self, action):
        return {"msg": "ok"}

    def liveContent(self):
        return ""

    def localProxy(self, params):
        return [404, "text/plain; charset=utf-8", "Proxy not configured"]

    def destroy(self):
        self.options = {}