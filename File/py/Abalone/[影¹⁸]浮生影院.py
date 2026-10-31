#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import re
import json
import base64
import html as html_lib
import urllib.request
import urllib.parse
from urllib.parse import urlparse, urljoin, quote, unquote
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
        self.siteUrl = "https://tv.fushengr.cc"
        self.fallbackPublishUrl = "https://madou2025.com"
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
        return "浮生影院"

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

    def _ensure_active_domain(self):
        test_res = self._fetch(self.siteUrl)
        if test_res.get("code") == 200:
            return self.siteUrl
        pub_res = self._fetch(self.fallbackPublishUrl)
        if pub_res.get("code") == 200:
            candidates = re.findall(r'https?://[a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,}', pub_res.get("text", ""))
            for cand in candidates:
                cand_clean = cand.rstrip("/")
                if "fusheng" in cand_clean:
                    check = self._fetch(cand_clean)
                    if check.get("code") == 200:
                        self.siteUrl = cand_clean
                        return self.siteUrl
        return self.siteUrl

    def _parse_card_list(self, html_text):
        cards = []
        seen_ids = set()

        anchor_pattern = re.compile(r'<a\b[^>]*href=["\'](?:.*?/video/(\d+)/?)["\'][^>]*>([\s\S]*?)</a>', re.I)
        matches = anchor_pattern.finditer(html_text)

        for m in matches:
            vod_id = m.group(1)
            if vod_id in seen_ids:
                continue

            full_a_tag = m.group(0)
            inner_html = m.group(2)

            name = ""
            aria_m = re.search(r'aria-label=["\']([^"\']+)["\']', full_a_tag, re.I)
            if aria_m:
                name = aria_m.group(1).strip()
            if not name:
                title_attr = re.search(r'title=["\']([^"\']+)["\']', full_a_tag, re.I)
                if title_attr:
                    name = title_attr.group(1).strip()
            if not name:
                tag_text_m = re.search(r'<(?:strong|em|h\d+)[^>]*>(.*?)</(?:strong|em|h\d+)>', inner_html, re.I)
                if tag_text_m:
                    name = tag_text_m.group(1).strip()
            if not name:
                alt_m = re.search(r'alt=["\']([^"\']+)["\']', inner_html, re.I)
                if alt_m:
                    name = alt_m.group(1).strip()
            if not name:
                continue

            name = re.sub(r'<[^>]+>', '', name).strip()
            name = html_lib.unescape(name)

            pic = ""
            data_src_m = re.search(r'data-src=["\']([^"\']+)["\']', inner_html, re.I)
            if data_src_m:
                pic = data_src_m.group(1).strip()
            else:
                img_src_m = re.search(r'src=["\']([^"\']+)["\']', inner_html, re.I)
                if img_src_m and "loading.gif" not in img_src_m.group(1):
                    pic = img_src_m.group(1).strip()

            if pic.startswith("//"):
                pic = "https:" + pic
            elif pic.startswith("/"):
                pic = self.siteUrl + pic

            dur_m = re.search(r'class=["\'][^"\']*duration[^"\']*["\'][^>]*>(.*?)</span>', inner_html, re.I)
            duration = dur_m.group(1).strip() if dur_m else ""

            cards.append({
                "vod_id": vod_id,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": format_remarks("蝴蝶影视", duration),
                "style": {"type": "rect", "ratio": 1.78}
            })
            seen_ids.add(vod_id)

        return cards

    def homeContent(self, filter):
        classes = [
            {"type_name": "一手原创", "type_id": "cate29"},
            {"type_name": "独家热播", "type_id": "cate37"},
            {"type_name": "乱伦之爱", "type_id": "cate17"},
            {"type_name": "福利姬", "type_id": "cate47"},
            {"type_name": "优选UP", "type_id": "cate65"},
            {"type_name": "P站精选", "type_id": "cate81"},
            {"type_name": "国产传媒", "type_id": "cate98"},
            {"type_name": "日本AV", "type_id": "cate113"},
            {"type_name": "性癖", "type_id": "cate129"},
            {"type_name": "动漫", "type_id": "cate138"},
            {"type_name": "欧美", "type_id": "cate148"},
            {"type_name": "劲爆综艺", "type_id": "cate162"}
        ]
        
        filters = {
            "cate29": [{"key": "sub_cat", "name": "细分子频道", "value": [
                {"n": "全部", "v": ""}, {"n": "御姐李老师", "v": "cate31"}, {"n": "奶气草莓", "v": "cate32"},
                {"n": "会喷水的姐姐", "v": "cate33"}, {"n": "伊藤诚", "v": "cate34"}, {"n": "狠台北", "v": "cate35"},
                {"n": "公鸡俱乐部", "v": "cate36"}
            ]}],
            "cate37": [{"key": "sub_cat", "name": "细分子频道", "value": [
                {"n": "全部", "v": ""}, {"n": "颜值女神", "v": "cate39"}, {"n": "探花嫖妓", "v": "cate40"},
                {"n": "绿帽淫妻", "v": "cate41"}, {"n": "母狗性奴", "v": "cate42"}, {"n": "针孔偷拍", "v": "cate43"},
                {"n": "野战户外", "v": "cate44"}, {"n": "成人综艺", "v": "cate45"}, {"n": "网红骚播", "v": "cate46"}
            ]}],
            "cate17": [{"key": "sub_cat", "name": "细分子频道", "value": [
                {"n": "全部", "v": ""}, {"n": "鬼父操女", "v": "cate19"}, {"n": "淫母兽儿", "v": "cate20"},
                {"n": "嫂子诱惑", "v": "cate21"}, {"n": "姐夫小姨子", "v": "cate22"}, {"n": "爷孙禁忌", "v": "cate26"}
            ]}],
            "cate47": [],
            "cate65": [{"key": "sub_cat", "name": "细分子频道", "value": [
                {"n": "全部", "v": ""}, {"n": "菠萝啤beer~", "v": "cate67"}, {"n": "网红妹妹", "v": "cate68"},
                {"n": "香艳职场", "v": "cate69"}, {"n": "捅主任", "v": "cate70"}, {"n": "双生の恋", "v": "cate71"},
                {"n": "台湾臀后艾丽", "v": "cate72"}, {"n": "粉红兔的诱惑", "v": "cate73"}, {"n": "COS美少女", "v": "cate74"},
                {"n": "女王梨奈", "v": "cate75"}, {"n": "性感小猫咪", "v": "cate76"}, {"n": "宜家门", "v": "cate77"},
                {"n": "颜射少女", "v": "cate78"}, {"n": "迷奸柚", "v": "cate79"}, {"n": "拳交女皇", "v": "cate80"}
            ]}],
            "cate81": [{"key": "sub_cat", "name": "细分子频道", "value": [
                {"n": "全部", "v": ""}, {"n": "米胡桃", "v": "cate83"}, {"n": "Andmlove", "v": "cate84"},
                {"n": "羞羞兔", "v": "cate85"}, {"n": "Roko", "v": "cate86"}, {"n": "Yominokuni", "v": "cate87"},
                {"n": "桃子派", "v": "cate88"}, {"n": "下面有根棒棒糖", "v": "cate89"}, {"n": "宝贝奶兽", "v": "cate90"},
                {"n": "BabyYurin", "v": "cate91"}, {"n": "优咪Yumi", "v": "cate92"}, {"n": "台湾兔兔", "v": "cate93"},
                {"n": "爱玩熊熊", "v": "cate94"}, {"n": "鸡教练", "v": "cate95"}, {"n": "樱桃空空", "v": "cate96"},
                {"n": "Miuzxc", "v": "cate97"}
            ]}],
            "cate98": [{"key": "sub_cat", "name": "细分子频道", "value": [
                {"n": "全部", "v": ""}, {"n": "精东影业", "v": "cate108"}
            ]}],
            "cate113": [{"key": "sub_cat", "name": "细分子频道", "value": [
                {"n": "全部", "v": ""}, {"n": "凌辱快感", "v": "cate121"}
            ]}],
            "cate129": [{"key": "sub_cat", "name": "细分子频道", "value": [
                {"n": "全部", "v": ""}, {"n": "SM调教", "v": "cate131"}, {"n": "媚黑骚逼", "v": "cate132"},
                {"n": "强奸迷奸", "v": "cate133"}, {"n": "人妖伪娘", "v": "cate134"}, {"n": "百合女同", "v": "cate135"},
                {"n": "男男之恋", "v": "cate136"}, {"n": "偷窥偷拍", "v": "cate137"}
            ]}],
            "cate138": [{"key": "sub_cat", "name": "细分子频道", "value": [
                {"n": "全部", "v": ""}, {"n": "王者荣耀", "v": "cate140"}, {"n": "经典老片", "v": "cate141"},
                {"n": "禁漫里番", "v": "cate142"}, {"n": "巨乳动漫", "v": "cate143"}, {"n": "中文字幕", "v": "cate144"},
                {"n": "魔", "v": "cate145"}, {"n": "原神", "v": "cate146"}, {"n": "综合", "v": "cate147"}
            ]}],
            "cate148": [],
            "cate162": [{"key": "sub_cat", "name": "细分子频道", "value": [
                {"n": "全部", "v": ""}, {"n": "性爱自修室", "v": "cate164"}, {"n": "突袭女优家", "v": "cate165"},
                {"n": "淫娃培训营", "v": "cate166"}, {"n": "淫欲游戏王", "v": "cate167"}, {"n": "情趣K歌房", "v": "cate168"},
                {"n": "乱伦家庭", "v": "cate169"}
            ]}]
        }

        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        del filter
        self._ensure_active_domain()
        page_num = int(pg or 1)
        sub_cat = ""
        if isinstance(extend, dict):
            sub_cat = extend.get("sub_cat", "")

        if sub_cat:
            target_path = "/category/%s/" % sub_cat if page_num <= 1 else ("/category/%s/%s/" % (sub_cat, page_num))
        else:
            target_path = "/group-category/%s/" % tid if page_num <= 1 else ("/group-category/%s/page/%s/" % (tid, page_num))

        fetch_res = self._fetch(target_path)
        html_text = fetch_res.get("text", "")

        cards = self._parse_card_list(html_text)

        total_pages = page_num + 1 if len(cards) >= 12 else page_num
        return {
            "page": page_num,
            "pagecount": total_pages,
            "limit": len(cards),
            "total": 9999,
            "list": cards
        }

    def detailContent(self, ids):
        self._ensure_active_domain()
        raw_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        clean_id = re.search(r'\d+', str(raw_id))
        vod_id = clean_id.group(0) if clean_id else str(raw_id)

        target_url = "%s/video/%s/" % (self.siteUrl, vod_id)
        detail_res = self._fetch(target_url)
        detail_html = detail_res.get("text", "")

        vod_name = "超清视频"
        title_m = re.search(r'<title>(.*?)</title>', detail_html, re.I)
        if title_m:
            raw_title = title_m.group(1).split("-")[0].strip()
            vod_name = html_lib.unescape(raw_title)

        raw_path = ""
        primary_cdn = "https://d32bg2g0w9aqg4.cloudfront.net"
        vod_pic = ""

        player_data_m = re.search(r'window\.__ARCHIVE_PLAYER__\s*=\s*(\{[\s\S]*?\});', detail_html)
        if player_data_m:
            try:
                p_info = json.loads(player_data_m.group(1))
                raw_path = p_info.get("rawPath", "").replace("\\/", "/")
                primary_cdn = p_info.get("cdnLine", primary_cdn).replace("\\/", "/")
                vod_pic = p_info.get("posterImg", "").replace("\\/", "/")
            except Exception:
                pass

        if not raw_path:
            direct_m = re.search(r'[\'"](/video/[^\'"]+?\.m3u8)[\'"]', detail_html)
            if direct_m:
                raw_path = direct_m.group(1)

        cdn_candidates = []
        cdn_lines_m = re.search(r'var\s+cdn_lines\s*=\s*([\'"].*?[\'"]);', detail_html)
        if cdn_lines_m:
            try:
                raw_cdn_json = json.loads(cdn_lines_m.group(1))
                parsed_lines = json.loads(raw_cdn_json) if isinstance(raw_cdn_json, str) else raw_cdn_json
                if isinstance(parsed_lines, list):
                    for item in parsed_lines:
                        line_url = item.get("cdnLine", "").replace("\\/", "").rstrip("/")
                        line_name = item.get("lineName", "专线")
                        if line_url and (line_name, line_url) not in cdn_candidates:
                            cdn_candidates.append((line_name, line_url))
            except Exception:
                pass

        if not cdn_candidates:
            cdn_candidates = [
                ("国际线路01", "https://d32bg2g0w9aqg4.cloudfront.net"),
                ("播放线路01", "https://vsdsq.tjacq.com")
            ]

        play_from_list = []
        play_url_list = []

        clean_path = ("/" + raw_path.lstrip("/")) if raw_path else ""

        for line_name, cdn_base in cdn_candidates:
            if clean_path:
                full_stream_url = "%s%s" % (cdn_base.rstrip("/"), clean_path)
            else:
                full_stream_url = target_url

            play_from_list.append(line_name)
            play_url_list.append("超清正片$%s" % full_stream_url)

        full_desc = (
            "【🔥 官方交流群: %s】\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "蝴蝶专线 直链极速秒播"
        ) % self.tgGroup

        escaped_desc = full_desc.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        vod = {
            "vod_id": vod_id,
            "vod_name": vod_name,
            "vod_pic": vod_pic,
            "vod_actor": self.brandActor,
            "vod_director": self.brandDirector,
            "vod_remarks": format_remarks("蝴蝶影视", "正片直链"),
            "vod_content": escaped_desc,
            "vod_play_from": "$$$".join(play_from_list),
            "vod_play_url": "$$$".join(play_url_list)
        }
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        del flag, vipFlags
        stream_url = str(id).strip()

        headers = {
            "User-Agent": self._ua,
            "Referer": self.siteUrl + "/",
            "Accept": "*/*",
            "Connection": "keep-alive"
        }

        return {
            "parse": 0,
            "playUrl": "",
            "url": stream_url,
            "header": headers
        }

    def searchContent(self, key, quick, pg="1"):
        del quick
        self._ensure_active_domain()
        page_num = int(pg or 1)
        encoded_key = quote(str(key or "").strip())
        if not encoded_key:
            return {"page": 1, "pagecount": 1, "limit": 0, "total": 0, "list": []}

        if page_num <= 1:
            target_path = "/search/%s/" % encoded_key
        else:
            target_path = "/search/%s/%s/" % (encoded_key, page_num)

        fetch_res = self._fetch(target_path)
        html_text = fetch_res.get("text", "")

        cards = self._parse_card_list(html_text)

        total_pages = page_num + 1 if len(cards) >= 12 else page_num
        return {
            "page": page_num,
            "pagecount": total_pages,
            "limit": len(cards),
            "total": 9999,
            "list": cards
        }

    def action(self, action):
        return {"msg": "ok"}

    def liveContent(self):
        return ""

    def localProxy(self, params):
        return [404, "text/plain; charset=utf-8", "Proxy not configured"]