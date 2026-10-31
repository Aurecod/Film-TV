#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import re
import json
import base64
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

def format_remarks(brand="蝴蝶影视", meta=""):
    clean_meta = str(meta or "").strip()
    clean_meta = re.sub(r"[\r\n\t]+", " ", clean_meta).strip()
    if clean_meta:
        return "%s | %s" % (brand, clean_meta)
    return brand

class Spider(SpiderBase):
    def __init__(self):
        super(Spider, self).__init__()
        self.siteUrl = "https://allclassic.porn"
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

        self.routeMap = {
            "home": "",
            "years_40s": "40s",
            "years_50s": "50s",
            "years_60s": "60s",
            "years_70s": "70s",
            "years_80s": "80s",
            "years_90s": "90s",
            "years_2000s": "2000s",
            "dir_categories": "categories",
            "dir_models": "models",
            "dir_tags": "tags",
            "dir_catalog": "catalog",
            "dir_studios": "studios"
        }

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
        return "🦋 经典老片"

    def isVideoFormat(self, url):
        low = (url or "").lower()
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".mkv", ".avi", ".ts", ".mpd", "index.png"))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self.options = {}

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

        for attempt in range(2):
            try:
                req = urllib.request.Request(target_url, headers=headers)
                with self.opener.open(req, timeout=12) as resp:
                    raw = resp.read()
                    enc = getattr(resp, "headers", {}).get("Content-Encoding", "").lower()
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
                    return {"code": resp.getcode(), "text": text, "bytes": raw, "err": "", "final_url": resp.geturl()}
            except Exception as e:
                if attempt == 0:
                    continue
                return {"code": -1, "text": "", "bytes": b"", "err": str(e), "final_url": target_url}
        return {"code": -1, "text": "", "bytes": b"", "err": "timeout", "final_url": target_url}

    def homeContent(self, filter):
        classes = [
            {"type_id": "home", "type_name": "推荐"},
            {"type_id": "years_40s", "type_name": "40年代及以前"},
            {"type_id": "years_50s", "type_name": "50年代"},
            {"type_id": "years_60s", "type_name": "60年代"},
            {"type_id": "years_70s", "type_name": "70年代"},
            {"type_id": "years_80s", "type_name": "80年代"},
            {"type_id": "years_90s", "type_name": "90年代"},
            {"type_id": "years_2000s", "type_name": "2000年代"},
            {"type_id": "dir_categories", "type_name": "全部分类"},
            {"type_id": "dir_models", "type_name": "老牌明星"},
            {"type_id": "dir_tags", "type_name": "热门标签"},
            {"type_id": "dir_catalog", "type_name": "聚合目录"},
            {"type_id": "dir_studios", "type_name": "制作片商"}
        ]

        filters = {}
        home_filters = [
            {
                "key": "sort",
                "name": "排序",
                "value": [
                    {"n": "最新发布", "v": "latest-updates"},
                    {"n": "评分最高", "v": "top-rated"},
                    {"n": "最受欢迎", "v": "most-popular"},
                    {"n": "最多收藏", "v": "most-favourited"},
                    {"n": "评论最多", "v": "most-commented"}
                ]
            }
        ]
        filters["home"] = home_filters

        years_filter = [
            {
                "key": "sort_by",
                "name": "排序",
                "value": [
                    {"n": "按日期", "v": "post_date"},
                    {"n": "按评分", "v": "rating"}
                ]
            }
        ]
        for y_key in ("years_40s", "years_50s", "years_60s", "years_70s", "years_80s", "years_90s", "years_2000s"):
            filters[y_key] = years_filter

        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        return self.categoryContent("home", 1, None, {})

    def _get_kvs_thumb(self, vid):
        try:
            v_int = int(vid)
            folder_idx = v_int // 1000 * 1000
            return "%s/contents/videos_screenshots/%d/%s/preview.jpg" % (self.siteUrl, folder_idx, vid)
        except Exception:
            return "https://dummyimage.com/400x600/1e293b/ffffff.png&text=VINTAGE"

    def _parse_videos(self, html):
        if not html:
            return []

        work_html = re.sub(r'id=["\']list_categories_top_categories_list_thumbs["\'][\s\S]*?</div>\s*</div>', '', html, flags=re.I)
        work_html = re.sub(r'<(?:header|footer)[^>]*>[\s\S]*?</(?:header|footer)>', '', work_html, flags=re.I)

        blocks = re.findall(r'<div[^>]+class=["\'][^"\']*\bitem\b[^"\']*["\'][^>]*>([\s\S]*?)</div>\s*</div>', work_html, re.I)
        if not blocks:
            blocks = re.findall(r'(<a[^>]+href=["\'][^"\']*/videos/\d+/[^"\']*["\'][\s\S]*?)(?=<a[^>]+href=["\'][^"\']*/videos/\d+/|$)', work_html, re.I)

        vod_list = []
        seen = set()

        for chunk in blocks:
            link_m = re.search(r'href=["\']([^"\']*/videos/(\d+)/([^"\']*))["\']', chunk, re.I)
            if not link_m:
                continue

            full_href = link_m.group(1).strip()
            vid = link_m.group(2).strip()
            slug = link_m.group(3).strip()

            if vid in seen:
                continue
            seen.add(vid)

            full_url = full_href if full_href.startswith("http") else urllib.parse.urljoin(self.siteUrl, full_href)

            title = ""
            title_m = re.search(r'title=["\']([^"\']+)["\']', chunk, re.I)
            if title_m and len(title_m.group(1).strip()) > 1:
                title = title_m.group(1).strip()
            if not title or title.lower() in ("video", "thumb", "play"):
                t_inner = re.search(r'class=["\'][^"\']*title[^"\']*["\'][^>]*>([\s\S]*?)</', chunk, re.I)
                if t_inner:
                    title = re.sub(r'<[^>]+>', '', t_inner.group(1)).strip()
            if not title:
                title = re.sub(r'^\d+-?', '', slug.strip("/")).replace("-", " ").title()

            img_m = re.search(r'(?:data-original|data-src|data-webp)=["\']([^"\']+)["\']', chunk, re.I)
            if img_m and "video-thumb-pending" not in img_m.group(1):
                raw_pic = img_m.group(1).strip()
                pic = raw_pic if raw_pic.startswith("http") else urllib.parse.urljoin(self.siteUrl, raw_pic)
            else:
                pic = self._get_kvs_thumb(vid)

            dur_m = re.search(r'class=["\'][^"\']*(?:duration|time)[^"\']*["\'][^>]*>([\s\S]*?)</(?:div|span)>', chunk, re.I)
            duration = re.sub(r'<[^>]+>', '', dur_m.group(1)).strip() if dur_m else ""
            remarks = format_remarks("蝴蝶影视", duration)

            vod_list.append({
                "vod_id": full_url,
                "vod_name": title or ("经典胶片 #%s" % vid),
                "vod_pic": pic,
                "vod_remarks": remarks,
                "style": {"type": "rect", "ratio": 1.78}
            })

        return vod_list

    def _parse_catalog_direct(self, html):
        if not html:
            return []
        matches = re.findall(r'<a[^>]+href=["\'](?:https?://[^"\']*)?/videos/(\d+)/([^"\']*)["\'][^>]*>([\s\S]*?)</a>', html, re.I)
        vod_list = []
        seen = set()

        for vid, slug, name_html in matches:
            if vid in seen:
                continue
            seen.add(vid)

            clean_title = re.sub(r'<[^>]+>', '', name_html).strip()
            if not clean_title or clean_title.lower() in ("video", "thumb", "play"):
                clean_title = slug.strip("/").replace("-", " ").title()

            full_url = "%s/videos/%s/%s" % (self.siteUrl, vid, slug)
            pic = self._get_kvs_thumb(vid)

            vod_list.append({
                "vod_id": full_url,
                "vod_name": clean_title,
                "vod_pic": pic,
                "vod_remarks": format_remarks("蝴蝶影视", "完整长片"),
                "style": {"type": "rect", "ratio": 1.78}
            })

            if len(vod_list) >= 60:
                break

        return vod_list

    def _parse_folders(self, html, sub_type=""):
        if not html:
            return []

        work_html = re.sub(r'id=["\']list_categories_top_categories_list_thumbs["\'][\s\S]*?</div>\s*</div>', '', html, flags=re.I)
        work_html = re.sub(r'class=["\']dropdown-thumbs["\'][\s\S]*?</div>\s*</div>', '', work_html, flags=re.I)
        work_html = re.sub(r'<(?:header|footer)[^>]*>[\s\S]*?</(?:header|footer)>', '', work_html, flags=re.I)

        if "model" in sub_type:
            blocks = re.findall(r'(<a[^>]+href=["\'][^"\']*/models/[^"\']+["\'][\s\S]*?</a>)', work_html, re.I)
        elif "tag" in sub_type:
            blocks = re.findall(r'(<a[^>]+href=["\'][^"\']*/tags/[^"\']+["\'][\s\S]*?</a>)', work_html, re.I)
        elif "studio" in sub_type:
            blocks = re.findall(r'(<a[^>]+href=["\'][^"\']*/studios/[^"\']+["\'][\s\S]*?</a>)', work_html, re.I)
        else:
            blocks = re.findall(r'(<a[^>]+class=["\'][^"\']*\bths\b[^"\']*["\'][^>]*>[\s\S]*?</a>)', work_html, re.I)
            if not blocks or len(blocks) < 20:
                blocks = re.findall(r'(<a[^>]+href=["\'][^"\']*/categories/[^"\']+["\'][\s\S]*?</a>)', work_html, re.I)

        vod_list = []
        seen = set()

        for chunk in blocks:
            link_m = re.search(r'href=["\']([^"\']+)["\']', chunk, re.I)
            if not link_m:
                continue
            href = link_m.group(1).strip()
            if href.startswith("javascript:") or href == "#" or not href:
                continue

            if href.rstrip("/") in (self.siteUrl, self.siteUrl + "/categories", self.siteUrl + "/models", self.siteUrl + "/tags", self.siteUrl + "/studios"):
                continue

            full_url = href if href.startswith("http") else urllib.parse.urljoin(self.siteUrl, href)
            if full_url in seen:
                continue
            seen.add(full_url)

            title = ""
            title_m = re.search(r'alt=["\']([^"\']+)["\']|title=["\']([^"\']+)["\']', chunk, re.I)
            if title_m:
                title = title_m.group(1) or title_m.group(2)
            if not title:
                t_inner = re.search(r'class=["\'][^"\']*(?:title|name)[^"\']*["\'][^>]*>([\s\S]*?)</', chunk, re.I)
                if t_inner:
                    title = re.sub(r'<[^>]+>', '', t_inner.group(1)).strip()
            if not title:
                title = href.rstrip("/").split("/")[-1].replace("-", " ").title()

            pic = ""
            img_m = re.search(r'<img[^>]+(?:src|data-src|data-original)=["\']([^"\']+)["\']', chunk, re.I)
            if img_m:
                raw_pic = img_m.group(1).strip()
                if "pending" not in raw_pic:
                    pic = raw_pic if raw_pic.startswith("http") else urllib.parse.urljoin(self.siteUrl, raw_pic)

            count_m = re.search(r'(\d+)\s*(?:videos|部|movies)', chunk, re.I)
            count_str = ("%s部" % count_m.group(1)) if count_m else ""
            remarks = format_remarks("蝴蝶影视", count_str)

            if "categories" in sub_type:
                style_type = {"type": "rect", "ratio": 1.78}
            elif "model" in sub_type:
                style_type = {"type": "rect", "ratio": 0.65}
            elif "studio" in sub_type:
                style_type = {"type": "rect", "ratio": 1.78}
            else:
                style_type = {"type": "rect", "ratio": 0.75}

            vod_list.append({
                "vod_id": "folder@@" + full_url,
                "vod_name": title,
                "vod_pic": pic or "https://dummyimage.com/400x600/1e293b/ffffff.png&text=DIR",
                "vod_remarks": remarks,
                "vod_tag": "folder",
                "style": style_type
            })

        return vod_list

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg or 1)
        raw_tid = str(tid).strip("/")
        ext = extend or {}

        if raw_tid.startswith("folder@@"):
            target_url = raw_tid.replace("folder@@", "")
            if page > 1:
                target_url = target_url.rstrip("/") + ("/%d/" % page)
            res = self._fetch(target_url)
            v_list = self._parse_videos(res.get("text", ""))
            return {
                "page": page,
                "pagecount": page + 1 if len(v_list) >= 20 else max(page, 1),
                "limit": 20,
                "total": 9999,
                "list": v_list
            }

        route_slug = self.routeMap.get(raw_tid, raw_tid)
        is_folder_dir = raw_tid in ("dir_categories", "dir_models", "dir_tags", "dir_studios")

        if is_folder_dir:
            if page > 1:
                req_url = "%s/%s/%d/" % (self.siteUrl, route_slug, page)
            else:
                req_url = "%s/%s/" % (self.siteUrl, route_slug)
            res = self._fetch(req_url)
            v_list = self._parse_folders(res.get("text", ""), raw_tid)

        elif raw_tid == "dir_catalog":
            req_url = "%s/catalog/" % self.siteUrl
            res = self._fetch(req_url)
            v_list = self._parse_catalog_direct(res.get("text", ""))

        elif raw_tid == "home":
            sort_val = ext.get("sort", "latest-updates")
            if sort_val and sort_val != "latest-updates":
                if page > 1:
                    req_url = "%s/%s/%d/" % (self.siteUrl, sort_val, page)
                else:
                    req_url = "%s/%s/" % (self.siteUrl, sort_val)
            else:
                if page > 1:
                    req_url = "%s/latest-updates/%d/" % (self.siteUrl, page)
                else:
                    req_url = self.siteUrl + "/"
            res = self._fetch(req_url)
            v_list = self._parse_videos(res.get("text", ""))

        else:
            sort_by = ext.get("sort_by", "post_date")
            ts = int(time.time() * 1000)
            base_year_url = "%s/%s/" % (self.siteUrl, route_slug)
            if page > 1:
                base_year_url = "%s/%s/%d/" % (self.siteUrl, route_slug, page)

            req_url = "%s?mode=async&function=get_block&block_id=list_videos_years_videos_list&sort_by=%s&_=%s" % (
                base_year_url, sort_by, ts
            )
            res = self._fetch(req_url, referer=self.siteUrl + "/" + route_slug + "/")
            v_list = self._parse_videos(res.get("text", ""))
            if not v_list:
                res_fallback = self._fetch(base_year_url)
                v_list = self._parse_videos(res_fallback.get("text", ""))

        return {
            "page": page,
            "pagecount": page + 1 if len(v_list) >= 20 else max(page, 1),
            "limit": len(v_list) if v_list else 20,
            "total": 9999,
            "list": v_list
        }

    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        target_url = str(raw_id)

        if target_url.startswith("folder@@"):
            return self.categoryContent(target_url, 1, None, {})

        if not target_url.startswith("http"):
            target_url = urllib.parse.urljoin(self.siteUrl, target_url)

        res = self._fetch(target_url)
        html = res.get("text", "")

        title_m = re.search(r'<title>([\s\S]*?)</title>', html, re.I)
        vod_name = ""
        if title_m:
            vod_name = title_m.group(1).replace(". Best vintage porn videos", "").replace(". Vintage Porn", "").strip()
        if not vod_name:
            vod_name = target_url.rstrip("/").split("/")[-1].replace("-", " ").title()

        vid = ""
        vid_m = re.search(r'/videos/(\d+)/', target_url)
        if vid_m:
            vid = vid_m.group(1)
        vod_pic = self._get_kvs_thumb(vid) if vid else ""

        real_play_url = ""
        fv_match = re.search(r'flashvars\s*=\s*(\{[\s\S]*?\});', html)
        if fv_match:
            fv_raw = fv_match.group(1)
            v_url_m = re.search(r'["\']?video_url["\']?\s*:\s*["\']([^"\']+)["\']', fv_raw)
            if v_url_m:
                cand_url = v_url_m.group(1).strip()
                if cand_url.startswith("//"):
                    cand_url = "https:" + cand_url
                elif cand_url.startswith("/"):
                    cand_url = self.siteUrl + cand_url
                real_play_url = cand_url

        if not real_play_url and vid:
            embed_url = "%s/embed/%s" % (self.siteUrl, vid)
            em_res = self._fetch(embed_url, referer=target_url)
            em_fv = re.search(r'flashvars\s*=\s*(\{[\s\S]*?\});', em_res.get("text", ""))
            if em_fv:
                em_v_m = re.search(r'["\']?video_url["\']?\s*:\s*["\']([^"\']+)["\']', em_fv.group(1))
                if em_v_m:
                    cand_em = em_v_m.group(1).strip()
                    if cand_em.startswith("//"):
                        real_play_url = "https:" + cand_em
                    elif cand_em.startswith("/"):
                        real_play_url = self.siteUrl + cand_em
                    else:
                        real_play_url = cand_em

        if not real_play_url:
            real_play_url = target_url

        desc_text = "蝴蝶专线为您提供极速复古经典流媒体体验。正片直链已完成纯算法逆向解析，支持秒播与高清拖拽。"
        full_desc = (
            "【🔥 官方交流群: %s】\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "%s"
        ) % (self.tgGroup, desc_text)

        escaped_desc = full_desc.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        vod = {
            "vod_id": target_url,
            "vod_name": vod_name or "经典复古高清原片",
            "vod_pic": vod_pic,
            "vod_actor": self.brandActor,
            "vod_director": self.brandDirector,
            "vod_remarks": format_remarks("蝴蝶影视", "超清原片"),
            "vod_content": escaped_desc,
            "vod_play_from": "蝴蝶专线",
            "vod_play_url": "超清正片$%s" % real_play_url
        }
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        raw_url = str(id).strip()
        play_url = raw_url

        if "/videos/" in play_url and "get_file" not in play_url:
            res = self._fetch(play_url)
            fv_m = re.search(r'flashvars\s*=\s*(\{[\s\S]*?\});', res.get("text", ""))
            if fv_m:
                vu_m = re.search(r'["\']?video_url["\']?\s*:\s*["\']([^"\']+)["\']', fv_m.group(1))
                if vu_m:
                    cand = vu_m.group(1).strip()
                    if cand.startswith("//"):
                        play_url = "https:" + cand
                    elif cand.startswith("/"):
                        play_url = self.siteUrl + cand
                    else:
                        play_url = cand

        headers = {
            "User-Agent": self._ua,
            "Referer": self.siteUrl + "/"
        }

        return {
            "parse": 0,
            "jx": 0,
            "url": play_url,
            "header": headers
        }

    def searchContent(self, key, quick, pg="1"):
        return {"page": 1, "pagecount": 1, "limit": 0, "total": 0, "list": []}

    def action(self, action):
        return {"msg": "ok"}

    def liveContent(self):
        return ""

    def localProxy(self, params):
        return [404, "text/plain; charset=utf-8", "Proxy not configured"]