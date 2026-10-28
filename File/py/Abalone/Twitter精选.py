# -*- coding: utf-8 -*-
import base64
import html
import http.cookiejar
import json
import random
import re
import ssl
import time
import urllib.parse
import urllib.request
from urllib.parse import unquote, urljoin, urlparse

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass

HOST = "https://pektino.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

CATEGORIES = [
    {"type_id": "feed_stream", "type_name": "🔥 沉浸连刷"},
    {"type_id": "daily", "type_name": "每日精选"},
    {"type_id": "weekly", "type_name": "每周热门"},
    {"type_id": "monthly", "type_name": "每月排行"},
    {"type_id": "all", "type_name": "历史最佳"},
]


class Spider(BaseSpider):

    def getName(self):
        return "pektino"

    def init(self, extend=""):
        pass

    def _req(self, url, retry=2, timeout=6, referer=None):
        headers = {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": referer if referer else (HOST + "/zh-CN"),
        }
        for i in range(retry):
            try:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE

                req_obj = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req_obj, timeout=timeout, context=ctx) as resp:
                    data = resp.read()
                    real_url = resp.geturl()
                    for enc in ["utf-8", "gbk", "latin-1"]:
                        try:
                            return resp.getcode(), real_url, data.decode(enc)
                        except Exception:
                            continue
                    return resp.getcode(), real_url, data.decode("utf-8", errors="ignore")
            except urllib.error.HTTPError as he:
                return he.code, url, ""
            except Exception:
                if i < retry - 1:
                    time.sleep(0.15)
                else:
                    return 0, url, ""
        return 0, url, ""

    def _convert_pic_proxy(self, pic_url):
        if not pic_url:
            return ""
        if pic_url.startswith("//"):
            pic_url = "https:" + pic_url
        if "twimg.com" in pic_url:
            return "https://wsrv.nl/?url=%s" % urllib.parse.quote(pic_url)
        return pic_url

    def _parse_cards_raw(self, html_text):
        cards = []
        if not html_text:
            return cards

        anchor_pattern = r'(<a[^>]+href="[^"]*(?:/zh-CN)?/(?:movies?|shorts)/[^"]+"[^>]*>.*?</a>)'
        matches = re.findall(anchor_pattern, html_text, re.DOTALL | re.IGNORECASE)

        seen_ids = set()
        for block in matches:
            href_m = re.search(r'href="([^"]*(?:/zh-CN)?/(?:movies?|shorts)/([^"/]+)/?)"', block)
            if not href_m:
                continue

            vid = href_m.group(2)
            if vid in seen_ids:
                continue
            seen_ids.add(vid)

            img_m = re.search(r'(?:src|data-src|poster)="([^"]+)"', block, re.IGNORECASE)
            pic = self._convert_pic_proxy(img_m.group(1)) if img_m else ""

            dur_m = re.search(r'(\d+:\d+(?::\d+)?)', block)
            dur = dur_m.group(1) if dur_m else ""

            alt_m = re.search(r'alt="([^"]+)"', block)
            if alt_m:
                raw_title = alt_m.group(1).replace("X (Twitter) adult video ", "").strip()
            else:
                raw_title = vid

            title = "精选影片 " + vid if raw_title == vid else raw_title
            cards.append({
                "vid": vid,
                "title": title,
                "pic": pic,
                "dur": dur
            })
        return cards

    def _extract_stream_from_html(self, html_text, vid=""):
        if not html_text:
            return ""
        clean_text = html_text.replace(r'\/', '/').replace('\\"', '"').replace('\\\\', '\\')
        raw_mp4s = re.findall(r'(https?://video\.twimg\.com/[^"\'\s<>\\]+\.mp4(?:\?[^"\'\s<>\\]*)?)', clean_text)

        valid = []
        for u in raw_mp4s:
            cu = u.replace('\\', '').strip()
            if cu.startswith("http") and cu not in valid:
                valid.append(cu)

        if vid:
            for u in valid:
                if vid in u:
                    return u
        return valid[0] if valid else ""

    def _check_stream_alive(self, url):
        if not url or not url.startswith("http"):
            return False
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            req.get_method = lambda: "HEAD"
            with urllib.request.urlopen(req, timeout=2.5, context=ctx) as resp:
                return resp.getcode() in (200, 206)
        except Exception:
            return False

    def homeContent(self, filter):
        return {
            "class": CATEGORIES,
            "list": [],
            "class_flag": 0,
            "style": {"type": "rect", "ratio": 1.78}
        }

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg="1", filter=False, extend=None):
        p = int(pg) if str(pg).isdigit() else 1
        clean_tid = tid.strip("/")

        if clean_tid == "feed_stream":
            pool_sections = ["weekly", "monthly", "all", "daily"]
            random.shuffle(pool_sections)

            raw_cards = []
            for sec in pool_sections:
                base_p = random.randint(1, 5)
                target_url = "%s/zh-CN" % HOST if sec == "daily" else "%s/zh-CN/%s" % (HOST, sec)
                if base_p > 1:
                    target_url = "%s?page=%s" % (target_url, base_p)

                code, real_url, html_text = self._req(target_url)
                cards = self._parse_cards_raw(html_text)
                if cards:
                    raw_cards.extend(cards)
                    break

            if not raw_cards:
                _, _, h_text = self._req("%s/zh-CN" % HOST)
                raw_cards = self._parse_cards_raw(h_text)

            random.shuffle(raw_cards)

            items = []
            for c in raw_cards:
                packed_id = "feed@@%s" % c["vid"]
                items.append({
                    "vod_id": packed_id,
                    "vod_name": c["title"],
                    "vod_pic": c["pic"],
                    "vod_remarks": "蝴蝶影视 | 连刷起播",
                    "style": {"type": "rect", "ratio": 1.78}
                })
            return {
                "list": items,
                "page": p,
                "pagecount": 999,
                "limit": len(items) if items else 20,
                "total": 9999,
                "style": {"type": "rect", "ratio": 1.78}
            }

        target_url = "%s/zh-CN" % HOST if clean_tid == "daily" else "%s/zh-CN/%s" % (HOST, clean_tid)
        if p > 1:
            target_url = "%s?page=%s" % (target_url, p)

        code, real_url, html_text = self._req(target_url)
        raw_cards = self._parse_cards_raw(html_text)

        items = []
        for c in raw_cards:
            items.append({
                "vod_id": c["vid"],
                "vod_name": c["title"],
                "vod_pic": c["pic"],
                "vod_remarks": "蝴蝶影视 | %s" % c["dur"] if c["dur"] else "蝴蝶影视",
                "style": {"type": "rect", "ratio": 1.78}
            })

        return {
            "list": items,
            "page": p,
            "pagecount": 999,
            "limit": len(items) if items else 20,
            "total": 9999,
            "style": {"type": "rect", "ratio": 1.78}
        }

    def detailContent(self, ids):
        if not ids:
            return {"list": []}

        raw_id = str(ids[0]).strip()

        if raw_id.startswith("feed@@"):
            parts = raw_id.split("@@")
            start_vid = parts[1]

            first_code, _, first_html = self._req("%s/zh-CN/movies/%s" % (HOST, start_vid))
            if not first_html or first_code == 404:
                first_code, _, first_html = self._req("%s/zh-CN/movie/%s" % (HOST, start_vid))
            first_stream = self._extract_stream_from_html(first_html, start_vid)

            random_pool = []
            seen_pool_ids = set([start_vid])

            sections = ["weekly", "monthly", "all", "daily"]
            sample_tasks = []
            for sec in sections:
                pages = random.sample(range(1, 8), 2)
                for pg_num in pages:
                    sample_tasks.append((sec, pg_num))
            random.shuffle(sample_tasks)

            for sec, pg_num in sample_tasks:
                t_url = "%s/zh-CN" % HOST if sec == "daily" else "%s/zh-CN/%s" % (HOST, sec)
                if pg_num > 1:
                    t_url = "%s?page=%s" % (t_url, pg_num)
                _, _, h_text = self._req(t_url)
                page_cards = self._parse_cards_raw(h_text)
                for pc in page_cards:
                    cvid = pc["vid"]
                    if cvid not in seen_pool_ids:
                        seen_pool_ids.add(cvid)
                        random_pool.append(cvid)
                if len(random_pool) >= 150:
                    break

            random.shuffle(random_pool)

            episodes = []
            if first_stream and self._check_stream_alive(first_stream):
                episodes.append("$%s" % first_stream)
            else:
                episodes.append("$feed_fetch@@%s" % start_vid)

            for r_vid in random_pool:
                episodes.append("$feed_fetch@@%s" % r_vid)

            vod = {
                "vod_id": raw_id,
                "vod_name": "🔥 沉浸连刷·全屏自适应",
                "vod_pic": "",
                "vod_actor": "🦋 TG群: @tvshare23",
                "vod_director": "🦋 蝴蝶影视",
                "vod_content": "🦋 沉浸式短视频连刷模式 | 遥控器按下键或自动无缝切集",
                "vod_remarks": "蝴蝶影视",
                "vod_play_from": "蝴蝶专线",
                "vod_play_url": "#".join(episodes),
            }
            return {"list": [vod]}

        vid = raw_id
        target_url = ("%s/zh-CN/movies/%s" % (HOST, vid)) if not vid.startswith("http") else vid
        code, real_url, html_text = self._req(target_url)
        if not html_text or code == 404:
            target_url = ("%s/zh-CN/movie/%s" % (HOST, vid)) if not vid.startswith("http") else vid
            code, real_url, html_text = self._req(target_url)

        title = ""
        t_m = re.search(r'<title>([^<]+)</title>', html_text)
        if t_m:
            title = t_m.group(1).split(" - ")[0].strip()

        pic_m = re.search(r'property="og:image"\s+content="([^"]+)"', html_text)
        pic = self._convert_pic_proxy(pic_m.group(1)) if pic_m else ""

        rec_cards = self._parse_cards_raw(html_text)

        main_stream = self._extract_stream_from_html(html_text, vid)
        main_target = main_stream if main_stream else ("rec_fetch@@%s" % vid)

        episodes = ["正片$%s" % main_target]
        rec_idx = 1
        for rc in rec_cards:
            if rc["vid"] != vid:
                clean_title = rc["title"].replace("$", "").replace("#", "")
                episodes.append("%02d·%s$rec_fetch@@%s" % (rec_idx, clean_title[:16], rc["vid"]))
                rec_idx += 1
                if rec_idx > 30:
                    break

        vod = {
            "vod_id": vid,
            "vod_name": title if title else "精选影片",
            "vod_pic": pic,
            "vod_actor": "🦋 TG群: @tvshare23",
            "vod_director": "🦋 蝴蝶影视",
            "vod_content": "🦋 蝴蝶影视专线 | 官方TG交流群：@tvshare23",
            "vod_remarks": "蝴蝶影视 | 推荐%s部" % (len(episodes) - 1),
            "vod_play_from": "蝴蝶专线",
            "vod_play_url": "#".join(episodes),
        }
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        raw_target = str(id).strip()
        stream_url = ""

        if raw_target.startswith("feed_fetch@@") or raw_target.startswith("rec_fetch@@"):
            target_vid = raw_target.split("@@")[1]
            code, _, page_html = self._req("%s/zh-CN/movies/%s" % (HOST, target_vid), timeout=4)
            if not page_html or code == 404:
                code, _, page_html = self._req("%s/zh-CN/movie/%s" % (HOST, target_vid), timeout=4)
            cand_stream = self._extract_stream_from_html(page_html, target_vid)

            if cand_stream and self._check_stream_alive(cand_stream):
                stream_url = cand_stream
            else:
                code_hot, _, hot_html = self._req("%s/zh-CN/weekly" % HOST, timeout=4)
                cand_cards = self._parse_cards_raw(hot_html)
                for cd in cand_cards:
                    if cd["vid"] != target_vid:
                        _, _, alt_html = self._req("%s/zh-CN/movies/%s" % (HOST, cd["vid"]), timeout=4)
                        if not alt_html:
                            _, _, alt_html = self._req("%s/zh-CN/movie/%s" % (HOST, cd["vid"]), timeout=4)
                        alt_stream = self._extract_stream_from_html(alt_html, cd["vid"])
                        if alt_stream and self._check_stream_alive(alt_stream):
                            stream_url = alt_stream
                            break
        else:
            if self._check_stream_alive(raw_target):
                stream_url = raw_target
            else:
                code_hot, _, hot_html = self._req("%s/zh-CN/weekly" % HOST, timeout=4)
                cand_cards = self._parse_cards_raw(hot_html)
                for cd in cand_cards:
                    _, _, alt_html = self._req("%s/zh-CN/movies/%s" % (HOST, cd["vid"]), timeout=4)
                    if not alt_html:
                        _, _, alt_html = self._req("%s/zh-CN/movie/%s" % (HOST, cd["vid"]), timeout=4)
                    alt_stream = self._extract_stream_from_html(alt_html, cd["vid"])
                    if alt_stream and self._check_stream_alive(alt_stream):
                        stream_url = alt_stream
                        break

        headers = {
            "User-Agent": UA
        }
        return {
            "parse": 0,
            "playUrl": "",
            "url": stream_url if stream_url else "https://video.twimg.com/tweet_video/error.mp4",
            "header": json.dumps(headers)
        }

    def searchContent(self, key, quick=False, pg="1"):
        p = int(pg) if str(pg).isdigit() else 1
        kw = urllib.parse.quote(key)
        url = "%s/zh-CN/search?tag=%s" % (HOST, kw)
        if p > 1:
            url = "%s&page=%s" % (url, p)

        code, real_url, html_text = self._req(url)
        raw_cards = self._parse_cards_raw(html_text)
        items = []
        for c in raw_cards:
            items.append({
                "vod_id": c["vid"],
                "vod_name": c["title"],
                "vod_pic": c["pic"],
                "vod_remarks": "蝴蝶影视",
                "style": {"type": "rect", "ratio": 1.78}
            })
        return {
            "list": items,
            "page": p,
            "pagecount": 999,
            "limit": 24,
            "total": 9999,
            "style": {"type": "rect", "ratio": 1.78}
        }

    def localProxy(self, params):
        return [200, "text/plain; charset=utf-8", b"", None]

    def action(self, action):
        return {}

    def liveContent(self):
        return {}

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        return False

    def destroy(self):
        pass