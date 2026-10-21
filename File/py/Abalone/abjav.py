# -*- coding: utf-8 -*-
import base64
import http.cookiejar
import html
import json
import re
import ssl
import urllib.parse
import urllib.request

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass


class Spider(BaseSpider):

    name = "ABJAV"
    host = "https://abjav.com"
    DEFAULT_PIC = "https://abjav.com/static/images/favicons/favicon.ico"

    CDN_MAP = {
        "1": "vv.abjav.com/c1/videos",
        "3": "vv2.abjav.com/c2/videos",
        "4": "vv3.abjav.com/c3/videos",
        "5": "vv4.abjav.com/c4/videos"
    }

    MAIN_CLASSES = (
        ("latest-updates", "最新发布"),
        ("most-popular", "最多播放"),
        ("longest", "最长时长"),
        ("top-rated", "最高评分")
    )

    def init(self, extend=""):
        self.ssl_ctx = ssl.create_default_context()
        self.ssl_ctx.check_hostname = False
        self.ssl_ctx.verify_mode = ssl.CERT_NONE
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        self.cookie_jar = http.cookiejar.CookieJar()
        cookie_processor = urllib.request.HTTPCookieProcessor(self.cookie_jar)
        https_handler = urllib.request.HTTPSHandler(context=self.ssl_ctx)
        self.opener = urllib.request.build_opener(https_handler, cookie_processor)

    def getHeaders(self, referer=None, is_api=False):
        hdr = {
            "User-Agent": self.user_agent,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": referer if referer else self.host + "/"
        }
        if is_api:
            hdr["Accept"] = "application/json, text/plain, */*"
            hdr["X-Requested-With"] = "XMLHttpRequest"
            hdr["Sec-Fetch-Dest"] = "empty"
            hdr["Sec-Fetch-Mode"] = "cors"
            hdr["Sec-Fetch-Site"] = "same-origin"
        else:
            hdr["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
        return hdr

    def _fetch_json(self, url, referer=None):
        req = urllib.request.Request(url, headers=self.getHeaders(referer, is_api=True))
        for _ in range(2):
            try:
                with self.opener.open(req, timeout=12) as resp:
                    raw = resp.read().decode("utf-8", "ignore")
                    return json.loads(raw)
            except Exception:
                continue
        return None

    def homeContent(self, filter):
        classes = []
        for type_id, type_name in self.MAIN_CLASSES:
            classes.append({"type_id": type_id, "type_name": type_name})
        return {"class": classes, "filters": {}}

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        page_num = int(pg) if str(pg).isdigit() else 1
        sort_key = str(tid).strip() if str(tid).strip() in ("latest-updates", "most-popular", "longest", "top-rated") else "latest-updates"

        api_path = "/api/json/videos2/86400/str/%s/60/..%d....json" % (sort_key, page_num)
        req_url = urllib.parse.urljoin(self.host, api_path)
        data = self._fetch_json(req_url)

        cards = []
        total_pages = page_num
        if data and isinstance(data, dict):
            videos = data.get("videos", [])
            total_pages = int(data.get("pages", page_num))
            for item in videos:
                vid = str(item.get("video_id") or "").strip()
                if not vid:
                    continue
                title = html.unescape(str(item.get("title") or "")).strip()
                pic = str(item.get("scr") or "").strip()
                duration = str(item.get("duration") or "").strip()
                sg_id = str(item.get("sg_id") or "5").strip()

                remarks = "蝴蝶影视"
                if duration:
                    remarks = "蝴蝶影视 | %s" % duration

                meta_token = "%s|%s|%s|%s" % (vid, sg_id, title, pic)
                encoded_id = base64.urlsafe_b64encode(meta_token.encode("utf-8")).decode("utf-8")

                cards.append({
                    "vod_id": encoded_id,
                    "vod_name": title,
                    "vod_pic": pic if pic else self.DEFAULT_PIC,
                    "vod_remarks": remarks,
                    "style": {"type": "rect", "ratio": 1.78}
                })

        return {
            "page": page_num,
            "pagecount": total_pages,
            "limit": 60,
            "total": total_pages * 60,
            "list": cards
        }

    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, list) and ids else str(ids)
        
        vid = raw_id
        sg_id = "5"
        vod_title = "视频 " + raw_id
        vod_pic = self.DEFAULT_PIC

        try:
            decoded = base64.urlsafe_b64decode(raw_id.encode("utf-8")).decode("utf-8")
            parts = decoded.split("|", 3)
            if len(parts) >= 2:
                vid = parts[0]
                sg_id = parts[1]
                if len(parts) >= 3 and parts[2]:
                    vod_title = parts[2]
                if len(parts) >= 4 and parts[3]:
                    vod_pic = parts[3]
        except Exception:
            if "@" in raw_id:
                parts = raw_id.split("@", 1)
                vid, sg_id = parts[0], parts[1]

        bucket_int = int(vid) // 1000 if vid.isdigit() else 0
        bucket_dir = "%s000" % bucket_int
        cdn_prefix = self.CDN_MAP.get(sg_id, "vv4.abjav.com/c4/videos")
        play_url = "https://%s/%s/%s/%s.mp4" % (cdn_prefix, bucket_dir, vid, vid)

        if vod_pic == self.DEFAULT_PIC:
            vod_pic = "https://ii.abjav.com/contents/videos_screenshots/%s/%s/480x270/1.jpg" % (bucket_dir, vid)

        vod = {
            "vod_id": raw_id,
            "vod_name": vod_title,
            "vod_pic": vod_pic,
            "vod_remarks": "蝴蝶影视",
            "vod_actor": "🦋 TG群: @tvshare23",
            "vod_director": "🦋 蝴蝶影视",
            "vod_content": "🦋 关注官方TG群: @tvshare23 | ABJAV高速专线",
            "vod_play_from": "ABJAV专线",
            "vod_play_url": "1080P/720P直连$" + play_url
        }
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        headers = {
            "User-Agent": self.user_agent,
            "Referer": self.host + "/"
        }
        return {
            "parse": 0,
            "playUrl": "",
            "url": str(id or "").strip(),
            "header": headers
        }

    def searchContent(self, key, quick, pg="1"):
        page_num = int(pg) if str(pg).isdigit() else 1
        encoded_k = urllib.parse.quote(str(key or "").strip())
        search_path = "/api/videos2.php?params=86400/str/relevance/60/search...%d...&s=%s" % (page_num, encoded_k)
        req_url = urllib.parse.urljoin(self.host, search_path)
        data = self._fetch_json(req_url)

        cards = []
        total_pages = page_num
        if data and isinstance(data, dict):
            videos = data.get("videos", [])
            total_pages = int(data.get("pages", page_num))
            for item in videos:
                vid = str(item.get("video_id") or "").strip()
                if not vid:
                    continue
                title = html.unescape(str(item.get("title") or "")).strip()
                pic = str(item.get("scr") or "").strip()
                duration = str(item.get("duration") or "").strip()
                sg_id = str(item.get("sg_id") or "5").strip()

                remarks = "蝴蝶影视"
                if duration:
                    remarks = "蝴蝶影视 | %s" % duration

                meta_token = "%s|%s|%s|%s" % (vid, sg_id, title, pic)
                encoded_id = base64.urlsafe_b64encode(meta_token.encode("utf-8")).decode("utf-8")

                cards.append({
                    "vod_id": encoded_id,
                    "vod_name": title,
                    "vod_pic": pic if pic else self.DEFAULT_PIC,
                    "vod_remarks": remarks,
                    "style": {"type": "rect", "ratio": 1.78}
                })

        return {
            "page": page_num,
            "pagecount": total_pages,
            "limit": 60,
            "total": total_pages * 60,
            "list": cards
        }

    def action(self, action):
        return {}

    def liveContent(self):
        return {}

    def localProxy(self, params):
        return [200, "text/plain", ""]

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(?:m3u8|mp4)(?:$|[?#])", str(url or ""), re.IGNORECASE))

    def destroy(self):
        pass