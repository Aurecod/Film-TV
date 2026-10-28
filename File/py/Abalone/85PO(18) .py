# -*- coding: utf-8 -*-
# 85PO / 85ro.com 四壳 Python 源（KVS 风格）
# 列表 HTML；详情 video_url / video_alt_url + v-acctoken → get_file 302 至真实 MP4
try:
    from base.spider import Spider as _BaseSpider
except Exception:
    class _BaseSpider(object):
        def getName(self):
            return ""

        def init(self, extend=""):
            pass


class Spider(_BaseSpider):
    def __init__(self):
        self.host = "https://www.85ro.com"
        self.ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
        self.headers = {
            "User-Agent": self.ua,
            "Referer": self.host + "/",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        }

    def getName(self):
        return "85PO"

    def init(self, extend=""):
        pass

    def getDependence(self):
        return ""

    def isVideoFormat(self, url):
        u = str(url or "").lower()
        return any(x in u for x in (".m3u8", ".mp4", ".mkv", ".flv"))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def localProxy(self, param):
        return [404, "text/plain", b""]

    def homeContent(self, filter):
        classes = [
            {"type_id": "latest-updates", "type_name": "最新"},
            {"type_id": "top-rated", "type_name": "高分"},
            {"type_id": "most-popular", "type_name": "最热"},
            {"type_id": "categories/ri-ben", "type_name": "日本"},
            {"type_id": "categories/zhong-guo", "type_name": "中国"},
            {"type_id": "categories/tai-wan", "type_name": "台湾"},
            {"type_id": "categories/xiang-gang", "type_name": "香港"},
            {"type_id": "categories/han-guo", "type_name": "韩国"},
            {"type_id": "categories/ma-lai-xi-ya", "type_name": "马来西亚"},
            {"type_id": "categories/xin-jia-po", "type_name": "新加坡"},
        ]
        result = {"class": classes}
        if filter:
            result["filters"] = {c["type_id"]: [] for c in classes}
        return result

    def homeVideoContent(self):
        return self.categoryContent("latest-updates", "1", False, {})

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = max(1, int(pg or 1))
        except Exception:
            page = 1
        tid = str(tid or "latest-updates").strip("/")
        if page <= 1:
            path = "/%s/" % tid
        else:
            path = "/%s/%s/" % (tid, page)
        html = self._fetch(self.host + path)
        items = self._parse_list(html)
        has_next = bool(
            html
            and (
                ("/%s/%s/" % (tid, page + 1)) in html
                or len(items) >= 20
            )
        )
        pagecount = page + 1 if has_next and items else max(1, page)
        return {
            "list": items,
            "page": page,
            "pagecount": pagecount,
            "limit": max(1, len(items) or 24),
            "total": pagecount * max(1, len(items) or 24),
        }

    def searchContent(self, key, quick, pg="1"):
        try:
            page = max(1, int(pg or 1))
        except Exception:
            page = 1
        q = str(key or "").strip()
        if not q:
            return {"list": [], "page": 1, "pagecount": 1, "limit": 0, "total": 0}
        if page <= 1:
            path = "/search/%s/" % self._quote(q)
        else:
            path = "/search/%s/%s/" % (self._quote(q), page)
        html = self._fetch(self.host + path)
        items = self._parse_list(html)
        has_next = bool(html and len(items) >= 20)
        pagecount = page + 1 if has_next and items else max(1, page)
        return {
            "list": items,
            "page": page,
            "pagecount": pagecount,
            "limit": max(1, len(items) or 24),
            "total": pagecount * max(1, len(items) or 24),
        }

    def detailContent(self, ids):
        vid = str(ids[0] if ids else "").strip()
        if not vid:
            return {"list": []}
        url = "%s/v/%s.html" % (self.host, vid)
        html = self._fetch(url)
        if not html:
            return {"list": []}
        name = self._meta_title(html) or ("影片 %s" % vid)
        if self._skip_minor(name):
            return {"list": []}
        pic = self._first(
            self._findall(
                r'(https://www\.85ro\.com/contents/videos_screenshots/[^"\']+)',
                html,
            )
        )
        # 多清晰度：1080p > 720p > 默认
        plays = []
        seen = set()
        for label, pat in (
            ("1080P", r'video_alt_url2\s*[:=]\s*[\'"]([^\'"]+)'),
            ("720P", r'video_alt_url\s*[:=]\s*[\'"]([^\'"]+)'),
            ("标清", r'video_url\s*[:=]\s*[\'"]([^\'"]+)'),
        ):
            for u in self._findall(pat, html):
                u = self._clean_url(u)
                if not u or u in seen:
                    continue
                seen.add(u)
                plays.append("%s$%s" % (label, u))
        # 兜底任意 get_file mp4
        if not plays:
            for u in self._findall(
                r'(https?://[^"\']+get_file/[^"\']+\.mp4[^"\']*)', html
            ):
                u = self._clean_url(u)
                if u and u not in seen:
                    seen.add(u)
                    plays.append("正片$%s" % u)
        if not plays:
            return {
                "list": [
                    {
                        "vod_id": vid,
                        "vod_name": name,
                        "vod_pic": pic or "",
                        "vod_content": "未解析到播放地址",
                        "vod_play_from": "提示",
                        "vod_play_url": "暂无$0",
                    }
                ]
            }
        return {
            "list": [
                {
                    "vod_id": vid,
                    "vod_name": name,
                    "vod_pic": pic or "",
                    "vod_content": name,
                    "vod_play_from": "85PO",
                    "vod_play_url": "#".join(plays),
                }
            ]
        }

    def playerContent(self, flag, id, vipFlags):
        url = str(id or "").strip()
        if not url or url == "0":
            return {"parse": 0, "jx": 0, "url": "", "msg": "无播放地址"}
        if url.startswith("//"):
            url = "https:" + url
        elif url.startswith("/"):
            url = self.host + url
        # 跟随 get_file 302 拿最终 CDN 地址（可选，播放器也可直接跟）
        final = self._resolve_redirect(url) or url
        headers = {
            "User-Agent": self.ua,
            "Referer": self.host + "/",
            "Origin": self.host,
        }
        return {"parse": 0, "jx": 0, "url": final, "header": headers}

    # ---------- helpers ----------
    def _parse_list(self, html):
        if not html:
            return []
        items = []
        seen = set()
        # 1) drop-card 完整块
        for m in self._finditer(
            r'href="https://www\.85ro\.com/v/(\d+)\.html"[\s\S]{0,1200}?data-original="(https://[^"]+)"[\s\S]{0,500}?class="card-title">([^<]+)<',
            html,
        ):
            vid, pic, title = m.group(1), m.group(2), self._clean(m.group(3))
            if vid in seen or self._skip_minor(title):
                continue
            seen.add(vid)
            items.append(
                {
                    "vod_id": vid,
                    "vod_name": title or ("影片 %s" % vid),
                    "vod_pic": pic,
                    "vod_remarks": "",
                }
            )
        # 2) 仅 data-original + 邻近 title 属性
        if len(items) < 8:
            pic_map = {}
            for m in self._finditer(
                r'href="https://www\.85ro\.com/v/(\d+)\.html"[\s\S]{0,800}?data-original="(https://[^"]+)"',
                html,
            ):
                pic_map[m.group(1)] = m.group(2)
            title_map = {}
            for m in self._finditer(
                r'href="https://www\.85ro\.com/v/(\d+)\.html"[^>]*title="([^"]+)"',
                html,
            ):
                title_map[m.group(1)] = self._clean(m.group(2))
            for m in self._finditer(
                r'href="https://www\.85ro\.com/v/(\d+)\.html"[\s\S]{0,600}?class="card-title">([^<]+)<',
                html,
            ):
                title_map[m.group(1)] = self._clean(m.group(2))
            for vid in list(dict.fromkeys(
                self._findall(r'href="https://www\.85ro\.com/v/(\d+)\.html"', html)
            )):
                if vid in seen:
                    continue
                title = title_map.get(vid) or ("影片 %s" % vid)
                if self._skip_minor(title):
                    continue
                seen.add(vid)
                items.append(
                    {
                        "vod_id": vid,
                        "vod_name": title,
                        "vod_pic": pic_map.get(vid, ""),
                        "vod_remarks": "",
                    }
                )
        return items

    def _resolve_redirect(self, url):
        try:
            import subprocess

            cmd = [
                "curl",
                "-sI",
                "-L",
                "--max-redirs",
                "5",
                "--max-time",
                "20",
                "-A",
                self.ua,
                "-e",
                self.host + "/",
                "-o",
                "/dev/null",
                "-w",
                "%{url_effective}",
                url,
            ]
            out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
            final = out.decode("utf-8", "ignore").strip()
            if final.startswith("http"):
                return final
        except Exception:
            pass
        return url

    @staticmethod
    def _clean_url(u):
        u = (u or "").replace("\\/", "/").replace("&amp;", "&").strip()
        return u

    @staticmethod
    def _skip_minor(name):
        n = (name or "").lower()
        keys = ("萝莉", "幼女", "小学生", "loli", "underage", "未成年", "女童", "幼")
        return any(k in n for k in keys)

    def _meta_title(self, html):
        for pat in (
            r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"',
            r"<title>([^<]+)</title>",
            r'class="card-title">([^<]+)<',
        ):
            m = self._search(pat, html)
            if m:
                t = self._clean(m)
                for s in (" - 85PO", " | 85PO", " - 85ro"):
                    if t.endswith(s):
                        t = t[: -len(s)]
                return t.strip()
        return ""

    def _fetch(self, url):
        try:
            import subprocess

            cmd = [
                "curl",
                "-sL",
                "--max-time",
                "25",
                "-A",
                self.ua,
                "-e",
                self.host + "/",
                url,
            ]
            out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
            text = out.decode("utf-8", "ignore")
            if text and "Just a moment" not in text[:500]:
                return text
        except Exception:
            pass
        try:
            import requests
            import urllib3

            urllib3.disable_warnings()
            r = requests.get(url, headers=self.headers, timeout=20, verify=False)
            if r.status_code == 200 and r.text:
                return r.text
        except Exception:
            pass
        return ""

    @staticmethod
    def _quote(s):
        try:
            from urllib.parse import quote

            return quote(str(s), safe="")
        except Exception:
            return str(s)

    @staticmethod
    def _clean(s):
        import re

        s = re.sub(r"<[^>]+>", "", str(s or ""))
        return (
            s.replace("&amp;", "&")
            .replace("&quot;", '"')
            .replace("&#039;", "'")
            .strip()
        )

    @staticmethod
    def _search(pat, text):
        import re

        m = re.search(pat, text or "", re.I)
        return m.group(1) if m else ""

    @staticmethod
    def _findall(pat, text):
        import re

        return re.findall(pat, text or "", re.I)

    @staticmethod
    def _finditer(pat, text):
        import re

        return list(re.finditer(pat, text or "", re.I | re.S))

    @staticmethod
    def _first(arr):
        return arr[0] if arr else ""
