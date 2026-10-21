#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import re
import json
import urllib.request
from urllib.parse import quote, unquote
import http.cookiejar
import gzip
import ssl

try:
    from base.spider import Spider as SpiderBase
except ImportError:
    class SpiderBase(object):
        def getCache(self, key): return None
        def setCache(self, key, value): return "fail"
        def delCache(self, key): return "fail"

class Spider(SpiderBase):
    # =====================================================================
    # 模块一：初始化与网络配置
    # =====================================================================
    def __init__(self):
        super(Spider, self).__init__()
        
        # 1. 域名配置 (主用与备用防封锁)
        self.primaryHost = "https://www.missav123.nl"
        self.fallbackHost = "https://www.thisav.my"
        
        # 2. 全局伪装 UA
        self._ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

        # 3. 网站路由字典
        self.categoryRoutes = {
            "chinese_subtitle": "/dm278/cn/chinese-subtitle",
            "new": "/dm539/cn/new",
            "release": "/dm635/cn/release",
            "uncensored_leak": "/dm817/cn/uncensored-leak",
            "today_hot": "/dm301/cn/today-hot",
            "weekly_hot": "/dm170/cn/weekly-hot",
            "monthly_hot": "/dm273/cn/monthly-hot",
            "actresses": "/cn/actresses",
            "actresses_ranking": "/cn/actresses/ranking",
            "genres": "/cn/genres",
            "makers": "/cn/makers",
            "vr": "/cn/genres/VR",
            "fc2": "/dm597/cn/fc2",
            "heyzo": "/dm2208642/cn/heyzo",
            "tokyohot": "/dm42/cn/tokyohot",
            "1pondo": "/dm5199603/cn/1pondo",
            "caribbeancom": "/dm7704788/cn/caribbeancom",
            "caribbeancompr": "/dm91887/cn/caribbeancompr",
            "10musume": "/dm7208981/cn/10musume",
            "pacopacomama": "/dm3600557/cn/pacopacomama",
            "gachinco": "/dm150/cn/gachinco",
            "siro": "/dm36/cn/siro",
            "luxu": "/dm34/cn/luxu",
            "gana": "/dm34/cn/gana",
            "scute": "/dm38/cn/scute",
            "maan": "/dm1004/cn/maan",
            "ara": "/dm34/cn/ara",
            "naughty4610": "/dm33/cn/naughty4610",
            "naughty0930": "/dm37/cn/naughty0930",
            "madou": "/dm63/cn/madou",
            "twav": "/dm31/cn/twav",
            "furuke": "/dm15/cn/furuke",
            "marriedslash": "/dm37/cn/marriedslash",
            "xxxav": "/dm42/cn/xxxav"
        }

        # 4. 忽略 SSL 证书校验，保障请求畅通
        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE
        
        # 5. Cookie 容器
        self.cj = http.cookiejar.CookieJar()
        self._build_opener()

    def _build_opener(self):
        """构建底层网络请求拦截器"""
        handlers = [
            urllib.request.HTTPCookieProcessor(self.cj),
            urllib.request.HTTPSHandler(context=self.ctx)
        ]
        self.opener = urllib.request.build_opener(*handlers)

    # 【YJ-Gemini 标识规范】：明确网站名和网络环境，实用至上
    def getName(self): return "Missav（免翻）"

    def init(self, extend=""): return True
    def isVideoFormat(self, url): return ".m3u8" in url.lower()
    def manualVideoCheck(self): return False

    def _fetch(self, url, ref=""):
        """统一的网络请求抓取模块，自带 Gzip 解压与异常拦截"""
        h = {
            "User-Agent": self._ua, 
            "Accept-Encoding": "gzip, deflate",
            "Referer": self.primaryHost + "/"
        }
        if ref: h["Referer"] = ref
        req = urllib.request.Request(url, headers=h)
        try:
            with self.opener.open(req, timeout=12) as resp:
                raw = resp.read()
                if raw.startswith(b"\x1f\x8b") or resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return raw.decode("utf-8", errors="ignore")
        except Exception:
            return ""

    # =====================================================================
    # 模块二：主页与分类模块 (OK影视特供版)
    # =====================================================================
    def homeContent(self, filter):
        classes = [{"type_name": v, "type_id": k} for k, v in zip(self.categoryRoutes.keys(), [
            "中文字幕", "最近更新", "新作上市", "无码流出", "今日热门", "本周热门", "本月热门",
            "女优一览", "女优排行", "全部类型", "全部发行商", "VR 专区", "FC2", "HEYZO",
            "东京热", "一本道", "加勒比", "加勒比PR", "天然素人", "熟女俱乐部", "Gachinco",
            "SIRO", "LUXU", "GANA", "S-CUTE", "PRESTIGE", "ARA", "顽皮4610", "顽皮0930",
            "麻豆传媒", "TWAV", "Furuke", "人妻斩", "XXX-AV"
        ])]
        return {"class": classes, "filters": {}}

    def homeVideoContent(self): return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if str(pg).isdigit() else 1
        tid_str = str(tid)
        
        # 1. 处理带 folder@ 的动态二次请求 (实现女优/分类无限下拉)
        if tid_str.startswith("folder@"):
            target_url = tid_str.replace("folder@", "")
            if not target_url.startswith("http"):
                target_url = f"{self.primaryHost}/{target_url.lstrip('/')}"
            
            if page > 1:
                target_url += f"?page={page}" if "?" not in target_url else f"&page={page}"
                
            html = self._fetch(target_url)
            vod_list = self._parse_cards(html) 
            
        # 2. 处理顶级常规分类请求
        else:
            route = self.categoryRoutes.get(tid_str, "/dm539/cn/new")
            target_url = f"{self.primaryHost}{route}"
            if page > 1: target_url += f"?page={page}"

            html = self._fetch(target_url, ref=self.primaryHost + "/enter")
            
            # 分流引擎：将特殊目录丢给专属解析器渲染 folder 标签
            if tid_str in ["actresses", "actresses_ranking", "genres", "makers"]:
                vod_list = self._parse_directory_cards(html, tid_str)
            else:
                vod_list = self._parse_cards(html)
        
        return {
            "page": page,
            "pagecount": page + 1 if len(vod_list) > 0 else page, 
            "limit": len(vod_list),
            "total": 999,
            "list": vod_list
        }

    # =====================================================================
    # 模块三：UI 卡片解析层
    # =====================================================================
    def _parse_directory_cards(self, html, tid):
        """专门解析女优/分类等中间层目录，赋予影视壳无限下拉能力"""
        vod_list = []
        base_path = ""
        is_actress = False
        if "actress" in tid: 
            base_path = "/actresses/"
            is_actress = True
        elif "genre" in tid: base_path = "/genres/"
        elif "maker" in tid: base_path = "/makers/"
        
        matches = re.findall(rf'<a\s+[^>]*href=["\']([^"\']+{base_path}[^"\']+)["\'][^>]*>([\s\S]*?)</a>', html, re.I)
        seen = set()
        
        # 预设一组高颜值莫兰迪色系，用于动态生成分类封面
        color_palette = [
            ("1e3a8a", "60a5fa"), ("14532d", "4ade80"), ("701a75", "f472b6"),
            ("7c2d12", "fb923c"), ("1f2937", "38bdf8"), ("312e81", "818cf8"),
            ("831843", "fb7185"), ("064e3b", "34d399"), ("3b0764", "c084fc")
        ]
        
        for idx, (href, inner_html) in enumerate(matches):
            if href in seen: continue
            
            clean_href = href.split('?')[0].rstrip('/')
            last_part = clean_href.split('/')[-1]
            if last_part in ['genres', 'actresses', 'makers', 'ranking']: continue
            
            title = ""
            alt_m = re.search(r'alt=["\']([^"\']+)["\']', inner_html, re.I)
            if alt_m: title = alt_m.group(1).strip()
            if not title:
                text_m = re.sub(r'<[^>]+>', '', inner_html).strip()
                if text_m: title = text_m.split('\n')[0].strip()
                
            if not title or title.isdigit(): continue
            
            pic = ""
            pic_match = re.search(r'(?:data-src|data-original|src)=["\']([^"\']+\.(?:jpg|jpeg|png|webp)[^"\']*)["\']', inner_html, re.I)
            if pic_match:
                pic = pic_match.group(1).strip()
                if "@Referer=" in pic: pic = pic.split("@Referer=")[0]
                
            # 【UI 升级】：如果没有抓到图片（比如分类页），根据标题的首字符动态生成一张纯色卡片
            if not pic:
                first_char = title[0].strip().upper() if title else "A"
                bg_color, fg_color = color_palette[idx % len(color_palette)]
                pic = f"https://dummyimage.com/640x360/{bg_color}/{fg_color}.png&text={quote(first_char)}"
                
            seen.add(href)
            
            vod_list.append({
                "vod_id": f"folder@{href}",
                "vod_name": title,
                "vod_pic": pic,
                # 【UI 升级】：直接留空，去除丑陋的黑色半透明遮罩，让头像和卡片更干净
                "vod_remarks": "",
                "vod_tag": "folder", 
                "style": {"type": "oval", "ratio": 1.0} if is_actress else {"type": "rect", "ratio": 1.78}
            })
        return vod_list


    def _parse_cards(self, html):
        """精准视频卡片解析器，防止越界吞噬，强制清洗纯净标题"""
        vod_list = []
        chunks = re.split(r'(?=<a\s+[^>]*href=)', html, flags=re.I)
        temp_dict = {}
        
        # 将分离的 HTML 切片按视频 ID 进行自动组装
        for chunk in chunks:
            href_m = re.search(r'href=["\']([^"\']+)["\']', chunk, re.I)
            if not href_m: continue
            href = href_m.group(1)
            
            if any(x in href for x in ['/genres/', '/actresses/', '/makers/', '/search/', 'flags/', '/localize/', 'login', 'playlist']):
                continue
                
            clean_href = href.split('?')[0].rstrip('/')
            dvd_match = re.search(r'/([A-Za-z0-9_-]+)$', clean_href)
            if not dvd_match: continue
            dvd_id = dvd_match.group(1)
            
            if dvd_id not in temp_dict:
                temp_dict[dvd_id] = {"href": clean_href, "html_blob": ""}
            temp_dict[dvd_id]["html_blob"] += chunk

        for dvd_id, data in temp_dict.items():
            blob = data["html_blob"]
            href = data["href"]
            
            if "<img" not in blob.lower() and "data-src" not in blob.lower(): continue
                
            full_href = href if href.startswith("http") else self.primaryHost.rstrip("/") + "/" + href.lstrip("/")
            
            # 全网罗选最长：舍弃短番号，保留最长中文剧情介绍
            title_candidates = []
            title_candidates.extend(re.findall(r'alt=["\']([^"\']+)["\']', blob, re.I))
            title_candidates.extend(re.findall(r'title=["\']([^"\']+)["\']', blob, re.I))
            title_candidates.extend(re.findall(r'>\s*([^<]{4,150}?)\s*</a>', blob))
            
            title = ""
            for t in title_candidates:
                t = t.strip()
                ignore_words = ["4k", "vr", "中文字幕", "无码流出", "今日热门", "本周热门", "新作上市"]
                if len(t) > len(title) and t.lower() not in ignore_words:
                    title = t
            
            if not title: continue 
            
            # 标题提纯：干掉多余标签和番号前缀
            title = re.sub(rf'^{dvd_id}[-\s_]*', '', title, flags=re.I).strip()
            title = re.sub(r'^[A-Za-z0-9]+-\d+[A-Za-z]*[-\s_]*', '', title).strip()
            title = re.sub(r'^(?:\[?中文字幕\]?|【中文字幕】|\[?无码流出\]?|【无码流出】)\s*', '', title, flags=re.I).strip()
            
            pic_match = re.search(r'(?:data-src|data-original|src)=["\']([^"\']+\.(?:jpg|jpeg|png|webp)[^"\']*)["\']', blob, re.I)
            if not pic_match: continue
            pic = pic_match.group(1).strip()
            if "@Referer=" in pic: pic = pic.split("@Referer=")[0]
            
            dur_m = re.search(r'(\d{1,2}:\d{2}(?::\d{2})?)', blob)
            dur = dur_m.group(1) if dur_m else ""
            
            # 智能徽章提取
            res_tag = "1080P"
            if re.search(r'(4[kK])', blob): res_tag = "4K"
            elif re.search(r'(1080[pP]|FHD)', blob): res_tag = "1080P"
            elif re.search(r'(720[pP]|HD)', blob): res_tag = "720P"
            
            tags = []
            if "无码" in title or re.search(r'uncensored', href, re.I) or re.search(r'>(无码流出|无码|Uncensored)<', blob, re.I): 
                tags.append("无码")
            if "VR" in title or re.search(r'>VR<', blob, re.I): 
                tags.append("VR")
            
            if tags:
                res_tag = f"{res_tag} · {'|'.join(tags)}"
                
            remarks = f"{res_tag} · {dur}" if dur else res_tag
            
            pack_id = f"{dvd_id}@@{full_href}"
            
            vod_list.append({
                "vod_id": pack_id,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": remarks
            })

        return vod_list

    # =====================================================================
    # 模块四：核心解密引擎
    # =====================================================================
    def pure_python_unpack(self, packed_js):
        """纯 Python 版 Dean Edwards Packer 解密，无视运行环境限制"""
        match = re.search(r"}\s*\(\s*['\"](.*?)['\"]\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*['\"](.*?)['\"]\s*\.split\(['\"]\|['\"]\)", packed_js, re.S)
        if not match: return ""
        p, a, c = match.group(1), int(match.group(2)), int(match.group(3))
        k = match.group(4).split('|')
        def base36(n):
            chars = '0123456789abcdefghijklmnopqrstuvwxyz'
            if n == 0: return '0'
            res = ''
            while n > 0:
                n, r = divmod(n, 36)
                res = chars[r] + res
            return res
        d = {base36(i): (k[i] if i < len(k) and k[i] else base36(i)) for i in range(c)}
        return re.sub(r'\b\w+\b', lambda m: d.get(m.group(0), m.group(0)), p)

    def _extract_surrit_uuid(self, html):
        """备选引擎：原生 Surrit 播放源 UUID 嗅探"""
        if not html: return ""
        m = re.search(r'hls\.loadSource\(["\']https?://[^/]+/([a-f0-9-]{36})/playlist\.m3u8["\']\)', html)
        if m: return m.group(1)
        m = re.search(r'urls:\s*\[\s*["\']([^"\']+)["\']', html)
        if m and "sample" not in m.group(1):
            u_m = re.search(r'([a-f0-9-]{36})', m.group(1))
            if u_m: return u_m.group(1)
        scripts = re.findall(r'<script[^>]*>([\s\S]*?)</script>', html)
        for sc in scripts:
            if ("surrit.com" in sc or "sixyik.com" in sc) and "sample" not in sc:
                uuids = re.findall(r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', sc)
                for u in uuids: return u
        pack_match = re.search(r'(eval\s*\(\s*function\s*\(\s*p\s*,\s*a\s*,\s*c\s*.*?\.split\([\'"]\|[\'"]\).*?\)\s*\))', html, re.I | re.S)
        if pack_match:
            unpacked = self.pure_python_unpack(pack_match.group(1))
            u_m = re.search(r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', unpacked)
            if u_m: return u_m.group(1)
        return ""

    def _extract_m3u8_from_html(self, html, cand_urls):
        """直链嗅探：强制筛选最高清 1080P/720P 画质通道"""
        best_link = ""
        pack_match = re.search(r'(eval\s*\(\s*function\s*\(\s*p\s*,\s*a\s*,\s*c\s*.*?\.split\([\'"]\|[\'"]\).*?\)\s*\))', html, re.I | re.S)
        if pack_match:
            unpacked = self.pure_python_unpack(pack_match.group(1))
            m3u8_links = re.findall(r'https?://[^\s\'"<>\\;]+\.m3u8', unpacked.replace('\\/', '/'))
            unique_links = list(set(m3u8_links))
            for link in unique_links:
                if "1080p" in link.lower():
                    best_link = link
                    break
            if not best_link:
                for link in unique_links:
                    if "720p" in link.lower():
                        best_link = link
                        break
            if not best_link and unique_links:
                best_link = unique_links[0]
        if not best_link:
            surrit_uuid = self._extract_surrit_uuid(html)
            best_link = f"https://surrit.com/{surrit_uuid}/playlist.m3u8" if surrit_uuid else (cand_urls[0] if cand_urls else "")
        return best_link

    # =====================================================================
    # 模块五：详情页与播放验证 (YJ-Gemini 品牌核心注入区)
    # =====================================================================
    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        
        if "@@" in raw_id:
            vid, origin_href = raw_id.split("@@", 1)
        else:
            vid = raw_id.replace("vod@", "").strip("/")
            origin_href = f"{self.primaryHost}/dm247/cn/{vid}"

        cand_urls = [
            origin_href if origin_href.startswith("http") else f"{self.primaryHost}/{origin_href.lstrip('/')}",
            f"{self.primaryHost}/dm247/cn/{vid}",
            f"{self.fallbackHost}/dm247/cn/{vid}"
        ]

        html = ""
        for u in cand_urls:
            html = self._fetch(u)
            if len(html) > 2000: break 

        title_match = re.search(r'<title>(.*?)</title>', html, re.I)
        if title_match:
            vod_name = title_match.group(1).split("|")[0].strip()
            vod_name = re.sub(r'(?:\[?中文字幕\]?|【中文字幕】|\[?无码流出\]?|【无码流出】|无码|流出)', '', vod_name, flags=re.I).strip()
            vod_name = re.sub(rf'^{vid}[-\s_]*', '', vod_name, flags=re.I).strip()
            if re.match(r'^[A-Za-z0-9]+-\d+', vod_name):
                vod_name = re.sub(r'^[A-Za-z0-9]+-\d+[A-Za-z]*[-\s_]*', '', vod_name).strip()
        else:
            vod_name = vid.upper()

        best_link = self._extract_m3u8_from_html(html, cand_urls)

        return {
            "list": [{
                "vod_id": raw_id,
                "vod_name": vod_name,
                "vod_director": "YJ-Gemini",
                # 【严格执行 V1.0 协议标准】
                "vod_play_from": "YJ-Gemini 专线", 
                "vod_play_url": "原画直连$" + best_link
            }]
        }

    def playerContent(self, flag, id, vipFlags):
        """直连播放器头域欺骗，强行放行防盗链"""
        url = str(id).strip()
        return {
            "parse": 0,
            "jx": 0,
            "url": url,
            "header": {
                "User-Agent": self._ua,
                "Referer": "https://missav.ws/",
                "Origin": "https://missav.ws",
                "Accept": "*/*",
                "Connection": "keep-alive"
            }
        }

    # =====================================================================
    # 模块六：全局搜索模块
    # =====================================================================
    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if str(pg).isdigit() else 1
        search_url = "%s/search/%s" % (self.primaryHost + "/dm247/cn", urllib.parse.quote(key))
        if page > 1:
            search_url = "%s?page=%d" % (search_url, page)

        html = self._fetch(search_url)
        if not html and self.fallbackHost:
            search_url = "%s/search/%s" % (self.fallbackHost + "/dm247/cn", urllib.parse.quote(key))
            if page > 1:
                search_url = "%s?page=%d" % (search_url, page)
            html = self._fetch(search_url)

        vod_list = self._parse_cards(html) if html else []

        return {
            "page": page,
            "pagecount": (page + 1) if len(vod_list) >= 12 else page,
            "limit": len(vod_list),
            "total": 999,
            "list": vod_list
        }

    def action(self, action): return {"msg": "ok"}
    def liveContent(self): return ""
    def localProxy(self, params): return [404, "text/plain; charset=utf-8", "Disabled"]
    def destroy(self): pass
