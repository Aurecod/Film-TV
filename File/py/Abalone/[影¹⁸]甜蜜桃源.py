# coding: utf-8
# TVBox/FongMi 爬虫源 - tmcrownxlift.site
# 站点: https://tmcrownxlift.site/
# CMS: 苹果CMS (MacCMS) + React/antd 前端
# 内容类型: 影视 (成人)
# 特性: 分类列表、分页、详情、播放直链提取

import re
import json
import urllib.parse
from base.spider import Spider as BaseSpider

class Spider(BaseSpider):
    def __init__(self):
        self.host = "https://tmcrownxlift.site"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Referer": self.host + "/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9"
        }
        # 分类列表（从首页顶部 tab 提取）
        self.classes = [
            {"type_id": "43", "type_name": "国产精品"},
            {"type_id": "57", "type_name": "网暴黑料"},
            {"type_id": "49", "type_name": "网红主播"},
            {"type_id": "35", "type_name": "中文字幕"},
            {"type_id": "33", "type_name": "日本女优"},
            {"type_id": "23", "type_name": "女同性爱"},
            {"type_id": "29", "type_name": "人妖视频"},
            {"type_id": "39", "type_name": "欧美视频"},
            {"type_id": "31", "type_name": "捆绑调教"},
            {"type_id": "55", "type_name": "三级伦理"},
            {"type_id": "25", "type_name": "重口猎奇"}
        ]
        self.filters = {}

    def getName(self):
        return "甜蜜桃源"

    def getDependence(self):
        return []

    def init(self, extend=""):
        self.extend = extend or ""

    def _fix_url(self, url):
        if not url:
            return ""
        url = url.strip()
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("/"):
            return self.host + url
        if not url.startswith("http"):
            return self.host + "/" + url.lstrip("/")
        return url

    def _get_html(self, url):
        try:
            resp = self.fetch(url, headers=self.headers, timeout=15000)
            if resp and hasattr(resp, 'text'):
                return resp.text
            return ""
        except Exception as e:
            self.log({"action": "fetch_error", "url": url, "error": str(e)})
            return ""

    def _parse_extend(self, extend):
        if isinstance(extend, dict):
            return extend
        if isinstance(extend, str):
            try:
                return json.loads(extend)
            except:
                result = {}
                clean = extend.strip().strip('{}')
                if clean:
                    for part in clean.split(','):
                        if '=' in part:
                            key, val = part.split('=', 1)
                            result[key.strip()] = val.strip()
                return result
        return {}

    def _parse_videos(self, html):
        videos = []
        if not html:
            return videos

        # 方法1：按卡片块分割解析
        # 先找所有 _card_1oit3_1 卡片
        card_pattern = r'<div class="_card_1oit3_1[^"]*"[^>]*>(.*?)</div>\s*</div>'
        card_blocks = re.findall(card_pattern, html, re.DOTALL)

        for block in card_blocks:
            # 提取链接 (a标签在卡片内)
            link_match = re.search(r'<a[^>]+href="([^"]+)"', block)
            if not link_match:
                continue
            link = link_match.group(1)

            # 提取封面图
            pic_match = re.search(r'<img[^>]+src="([^"]+)"', block)
            pic = pic_match.group(1) if pic_match else ""

            # 提取时长
            duration_match = re.search(r'<div class="_creator_1oit3_26">([^<]+)</div>', block)
            duration = duration_match.group(1) if duration_match else ""

            # 提取标题 (从 _desc_1oit3_290)
            title_match = re.search(r'<p class="_desc_1oit3_290">\s*(.*?)\s*</p>', block, re.DOTALL)
            if not title_match:
                continue
            title = title_match.group(1).strip()

            # 提取视频ID
            vid_match = re.search(r'/id/(\d+)/', link)
            if not vid_match:
                continue
            vid = vid_match.group(1)

            vod_id = f"{vid}|$|{title}|$|{pic}|$|{duration}|$|{link}"
            videos.append({
                "vod_id": vod_id,
                "vod_name": title,
                "vod_pic": self._fix_url(pic),
                "vod_remarks": duration
            })

        # 方法2：如果方法1没解析到，用备用正则
        if not videos:
            # 直接用更宽松的正则
            alt_pattern = r'<a[^>]+href="(/index.php/vod/play/id/\d+/[^"]+)"[^>]*>.*?<img[^>]+src="([^"]+)".*?<div class="_creator_1oit3_26">([^<]+)</div>.*?<p class="_desc_1oit3_290">\s*(.*?)\s*</p>'
            matches = re.findall(alt_pattern, html, re.DOTALL)
            for link, pic, duration, title in matches:
                vid_match = re.search(r'/id/(\d+)/', link)
                if not vid_match:
                    continue
                vid = vid_match.group(1)
                title = title.strip()
                vod_id = f"{vid}|$|{title}|$|{pic}|$|{duration}|$|{link}"
                videos.append({
                    "vod_id": vod_id,
                    "vod_name": title,
                    "vod_pic": self._fix_url(pic),
                    "vod_remarks": duration
                })

        return videos

    def homeContent(self, filter):
        return {"class": self.classes, "filters": self.filters if filter else {}}

    def getHomeContent(self, filter):
        return self.homeContent(filter)

    def homeVideoContent(self):
        return self.categoryContent("43", "1", False, {})

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg) if pg else 1
            if page < 1:
                page = 1
        except:
            page = 1

        url = f"{self.host}/index.php/vod/type/id/{tid}/page/{page}.html"
        html = self._get_html(url)
        videos = self._parse_videos(html)

        pagecount = 1
        if html:
            page_links = re.findall(r'<a[^>]+href="[^"]*/page/(\d+)\.html"[^>]*>', html)
            if page_links:
                max_page = max([int(p) for p in page_links])
                pagecount = max_page if max_page > 1 else 1
            total_match = re.search(r'共(\d+)页', html)
            if total_match:
                pagecount = int(total_match.group(1))

        return {
            "list": videos,
            "page": page,
            "pagecount": pagecount,
            "limit": 20,
            "total": pagecount * 20
        }

    def detailContent(self, ids):
        if not ids:
            return {"list": []}

        raw = ids[0]
        parts = raw.split('|$|')
        if len(parts) < 5:
            return {"list": []}

        vid = parts[0]
        name = parts[1] if len(parts) > 1 else "视频"
        pic = parts[2] if len(parts) > 2 else ""
        duration = parts[3] if len(parts) > 3 else ""
        play_url = parts[4] if len(parts) > 4 else ""

        vod = {
            "vod_id": raw,
            "vod_name": name,
            "vod_pic": self._fix_url(pic),
            "vod_remarks": duration,
            "vod_content": name,
            "vod_play_from": "播放",
            "vod_play_url": f"播放${play_url}"
        }
        return {"list": [vod]}

    def searchContent(self, key, quick, pg="1"):
        try:
            page = int(pg) if pg else 1
        except:
            page = 1

        search_url = f"{self.host}/index.php/vod/search.html"
        data = {"wd": key}

        try:
            resp = self.post(search_url, data=data, headers=self.headers, timeout=15000)
            if not resp or not hasattr(resp, 'text'):
                return {"list": [], "page": page}
            html = resp.text
        except Exception as e:
            self.log({"action": "search_error", "error": str(e)})
            return {"list": [], "page": page}

        videos = self._parse_videos(html)
        return {"list": videos, "page": page}

    def playerContent(self, flag, id, vipFlags):
        if id.startswith(("http://", "https://")):
            if id.endswith((".m3u8", ".mp4", ".ts")):
                return {"parse": 0, "url": id, "header": self.headers}

        play_url = self._fix_url(id)
        html = self._get_html(play_url)
        if not html:
            return {"parse": 1, "url": id, "header": self.headers}

        # 查找 iframe 中的播放地址
        iframe_pattern = r'<iframe[^>]+src="([^"]+)"'
        iframe_matches = re.findall(iframe_pattern, html)
        for iframe_src in iframe_matches:
            if "aojiexi.com" in iframe_src or "url=" in iframe_src:
                url_match = re.search(r'[?&]url=([^&]+)', iframe_src)
                if url_match:
                    real_url = urllib.parse.unquote(url_match.group(1))
                    if real_url.endswith((".m3u8", ".mp4")):
                        return {"parse": 0, "url": real_url, "header": self.headers}

        # 直接查找 m3u8
        m3u8_pattern = r'(https?://[^\s"\']+\.m3u8[^\s"\']*)'
        m3u8_matches = re.findall(m3u8_pattern, html)
        if m3u8_matches:
            return {"parse": 0, "url": m3u8_matches[0], "header": self.headers}

        return {"parse": 1, "url": id, "header": self.headers}

    def isVideoFormat(self, url):
        return url.endswith((".m3u8", ".mp4", ".ts"))

    def destroy(self):
        pass