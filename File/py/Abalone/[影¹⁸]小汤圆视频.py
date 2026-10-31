# coding: utf-8
"""
小汤圆视频 mmajj.icu - TVBox/FongMi Python 爬虫
主域名: https://mmajj.icu
内容类型: 成人视频
最后验证: 2026-10-22
站点特征: 标准 HTML 站, 无独立详情页, 卡片直接跳 play 页, player_aaaa JSON 明码
"""
import re
import json
from urllib.parse import quote, urljoin, unquote, urlparse

from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    def __init__(self):
        self.extend = ""
        self.host = "https://mmajj.icu"
        self.classes = [
 {
  "type_id": "1",
  "type_name": "国产"
 },
 {
  "type_id": "2",
  "type_name": "日韩"
 },
 {
  "type_id": "3",
  "type_name": "欧美"
 },
 {
  "type_id": "4",
  "type_name": "动漫"
 },
 {
  "type_id": "10",
  "type_name": "吃瓜黑料"
 },
 {
  "type_id": "11",
  "type_name": "酒店探花"
 },
 {
  "type_id": "12",
  "type_name": "网红主播"
 },
 {
  "type_id": "13",
  "type_name": "网络传媒"
 },
 {
  "type_id": "19",
  "type_name": "伦理影片"
 },
 {
  "type_id": "20",
  "type_name": "自拍偷拍"
 },
 {
  "type_id": "21",
  "type_name": "反差母狗"
 },
 {
  "type_id": "8",
  "type_name": "中文字幕"
 },
 {
  "type_id": "9",
  "type_name": "高清无码"
 },
 {
  "type_id": "16",
  "type_name": "日韩精品"
 },
 {
  "type_id": "17",
  "type_name": "AV明星"
 },
 {
  "type_id": "18",
  "type_name": "AV解说"
 },
 {
  "type_id": "22",
  "type_name": "熟女少妇"
 },
 {
  "type_id": "23",
  "type_name": "乱伦强奸"
 },
 {
  "type_id": "14",
  "type_name": "欧美精品"
 },
 {
  "type_id": "15",
  "type_name": "成人动漫"
 }
]
        self.filters = {}
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 14; 22127RK46C) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
            "Referer": self.host + "/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

    def getName(self):
        return "小汤圆视频"

    def getDependence(self):
        return []

    def init(self, extend=""):
        self.extend = extend or ""
        if extend and isinstance(extend, str) and extend.startswith("http"):
            self.host = extend.rstrip("/")
            self.headers["Referer"] = self.host + "/"

    def homeContent(self, filter):
        return {"class": self.classes, "filters": self.filters if filter else {}}

    def getHomeContent(self, filter):
        return self.homeContent(filter)

    def homeVideoContent(self):
        try:
            r = self.fetch(self.host + "/", headers=self.headers, timeout=15)
            if not r or r.status_code != 200:
                return {"list": []}
            return {"list": self._parse_list(r.text)}
        except Exception as e:
            self.log("home error: " + type(e).__name__)
            return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        page = str(pg or "1")
        if page == "1":
            url = f"{self.host}/index.php/vod/type/id/{tid}.html"
        else:
            url = f"{self.host}/index.php/vod/type/id/{tid}/page/{page}.html"
        try:
            r = self.fetch(url, headers=self.headers, timeout=15)
            if not r or r.status_code != 200:
                return {"list": [], "page": int(page), "pagecount": 1, "limit": 28, "total": 0}
            return {
                "list": self._parse_list(r.text),
                "page": int(page),
                "pagecount": self._parse_pagecount(r.text),
                "limit": 28,
                "total": 99999,
            }
        except Exception as e:
            self.log("cat error: " + type(e).__name__)
            return {"list": [], "page": int(page), "pagecount": 1, "limit": 28, "total": 0}

    def _parse_list(self, html):
        items = []
        seen = set()
        try:
            from lxml import html as lh
            doc = lh.fromstring(html)
        except Exception:
            return items
        cards = doc.xpath('//div[contains(@class,"xv-video-card")]')
        for c in cards:
            hrefs = c.xpath('.//a/@href')
            href = ""
            for h in hrefs:
                if "/vod/play/id/" in h:
                    href = h
                    break
            if not href:
                continue
            m = re.search(r'/id/(\d+)/sid/(\d+)/nid/(\d+)', href)
            if not m:
                continue
            vid, sid, nid = m.group(1), m.group(2), m.group(3)
            key = f"{vid}_{sid}_{nid}"
            if key in seen:
                continue
            seen.add(key)
            ti = c.xpath('.//*[contains(@class,"xv-video-title")]//text()')
            title = "".join(ti).strip()
            if not title:
                continue
            im = c.xpath('.//img/@data-original | .//img/@src')
            pic = urljoin(self.host + "/", im[0]) if im else ""
            items.append({
                "vod_id": f"{vid}|$|{sid}|$|{nid}|$|{title}|$|{pic}",
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": "",
            })
        return items

    def _parse_pagecount(self, html):
        # 优先从分页容器抓总页数
        m = re.search(r'共\s*(\d+)\s*页', html)
        if m:
            return int(m.group(1))
        nums = re.findall(r'/type/id/\d+/page/(\d+)\.html', html)
        nums = [int(n) for n in nums if n.isdigit()]
        return max(nums) if nums else 1

    @staticmethod
    def _norm_ids(ids):
        if ids is None:
            return ""
        if isinstance(ids, (list, tuple)):
            if not ids:
                return ""
            ids = ids[0]
        if isinstance(ids, bytes):
            ids = ids.decode("utf-8", errors="ignore")
        return str(ids).strip()

    def _skeleton(self, vid):
        parts = str(vid).split("|$|")
        pid = parts[0] if parts else ""
        return {"list": [{
            "vod_id": vid, "vod_name": parts[3] if len(parts) > 3 else "未知标题",
            "vod_pic": parts[4] if len(parts) > 4 else "",
            "vod_remarks": "", "vod_content": "",
            "vod_play_from": "小汤圆", "vod_play_url": "播放$" + pid,
        }]}

    def detailContent(self, ids):
        raw = self._norm_ids(ids)
        if not raw:
            return {"list": []}
        try:
            parts = raw.split("|$|")
            vid = parts[0] if len(parts) > 0 else ""
            sid = parts[1] if len(parts) > 1 else "1"
            nid = parts[2] if len(parts) > 2 else "1"
            title = parts[3] if len(parts) > 3 else ""
            pic = parts[4] if len(parts) > 4 else ""
            if not vid:
                return {"list": []}
            play_path = f"/index.php/vod/play/id/{vid}/sid/{sid}/nid/{nid}.html"
            # 尝试补全标题（列表阶段有则用，无则从 play 页补）
            if not title:
                try:
                    r = self.fetch(self.host + play_path, headers=self.headers, timeout=15)
                    if r and r.status_code == 200 and len(r.text) > 500:
                        tm = re.search(r'<title>(.*?)</title>', r.text, re.S)
                        if tm:
                            t = tm.group(1).strip()
                            t = re.sub(r'\s*-\s*小汤圆视频$', '', t)
                            title = t
                except Exception:
                    pass
            vod = {
                "vod_id": raw,
                "vod_name": title or "视频",
                "vod_pic": pic,
                "vod_remarks": "",
                "vod_content": "",
                "vod_play_from": "小汤圆",
                "vod_play_url": "播放$" + self.host + play_path,
            }
            return {"list": [vod]}
        except Exception as e:
            self.log("detail error: " + type(e).__name__)
            return self._skeleton(raw)

    def searchContent(self, key, quick, pg="1"):
        page = str(pg or "1")
        q = quote(key)
        if page == "1":
            url = f"{self.host}/index.php/vod/search/wd/{q}.html"
        else:
            url = f"{self.host}/index.php/vod/search/wd/{q}/page/{page}.html"
        try:
            r = self.fetch(url, headers=self.headers, timeout=15)
            if not r or r.status_code != 200:
                return {"list": [], "page": int(page)}
            return {"list": self._parse_list(r.text), "page": int(page)}
        except Exception as e:
            self.log("search error: " + type(e).__name__)
            return {"list": [], "page": int(page)}

    def playerContent(self, flag, id, vipFlags):
        play_url = id if id.startswith("http") else f"{self.host}{id}"
        try:
            r = self.fetch(play_url, headers=self.headers, timeout=15)
            if not r or r.status_code != 200:
                return {"parse": 1, "url": play_url, "header": self.headers}
            js = self._grab_player_json(r.text)
            if js:
                try:
                    data = json.loads(js)
                except Exception:
                    data = json.loads(js.replace("\\/", "/"))
                encrypt = data.get("encrypt", 0)
                real = data.get("url", "")
                if encrypt == 0 and real:
                    if real.endswith(".m3u8") or ".m3u8?" in real:
                        return {"parse": 0, "url": self._m3u8_proxy_url(real), "header": {}}
                    if real.startswith("http"):
                        return {"parse": 0, "url": real, "header": {"User-Agent": self.headers["User-Agent"], "Referer": self.host + "/"}}
            return {"parse": 1, "url": play_url, "header": self.headers}
        except Exception as e:
            self.log("player error: " + type(e).__name__)
            return {"parse": 1, "url": play_url, "header": self.headers}

    def _grab_player_json(self, text):
        m = re.search(r'var\s+player_[a-zA-Z0-9_]+\s*=\s*', text)
        if not m:
            return None
        i = m.end()
        if i >= len(text) or text[i] != "{":
            return None
        depth = 0
        start = i
        while i < len(text):
            c = text[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i+1]
            i += 1
        return None

    def _m3u8_proxy_url(self, url):
        return self.getProxyUrl() + "&url=" + quote(str(url or ""), safe="")

    def localProxy(self, param):
        try:
            target = unquote(str((param or {}).get("url", "") or ""))
            if not re.match(r"^https?://", target, re.I):
                return [400, "text/plain", b"invalid"]
            r = self.fetch(target, headers={
                "User-Agent": self.headers["User-Agent"],
                "Referer": self.host + "/",
            }, timeout=15)
            if not r or r.status_code != 200:
                return [502, "text/plain", b"fetch failed"]
            raw = getattr(r, "content", b"") or b""
            text = raw.decode("utf-8", errors="ignore")
            if "#EXTM3U" not in text:
                return [502, "text/plain", b"invalid m3u8"]
            cleaned = self._clean_m3u8(text, target)
            return [200, "application/vnd.apple.mpegurl", cleaned.encode("utf-8")]
        except Exception as e:
            self.log("proxy error: " + type(e).__name__)
            return [500, "text/plain", b"error"]

    def _clean_m3u8(self, text, source_url):
        lines = [l.strip() for l in str(text or "").replace("\r", "").split("\n") if l.strip()]
        if not lines:
            return "#EXTM3U\n"

        # 多码率主表：子流改代理
        if any(l.startswith("#EXT-X-STREAM-INF") for l in lines):
            out = []
            for l in lines:
                if l.startswith("#"):
                    out.append(self._rewrite_tag(l, source_url))
                else:
                    child = urljoin(source_url, l)
                    if ".m3u8" in child.lower():
                        out.append(self._m3u8_proxy_url(child))
                    else:
                        out.append(child)
            return "\n".join(out) + "\n"

        # 单码率：动态众数锚点
        import os
        from collections import Counter
        seg_urls = []
        for l in lines:
            if not l.startswith("#"):
                seg_urls.append(urljoin(source_url, l))
        dir_counter = Counter()
        for u in seg_urls:
            d = os.path.dirname(urlparse(u).path) + "/"
            dir_counter[d] += 1
        anchor_dir = None
        total = len(seg_urls)
        if dir_counter:
            top_dir, top_cnt = dir_counter.most_common(1)[0]
            if top_cnt / max(total, 1) >= 0.5:
                anchor_dir = top_dir

        out = []
        pending = []
        removed = 0
        kept = 0
        for l in lines:
            if l.startswith("#EXTINF"):
                pending = [l]
                continue
            if pending and l.startswith("#"):
                pending.append(self._rewrite_tag(l, source_url))
                continue
            if not l.startswith("#") and pending:
                media = urljoin(source_url, l)
                keep = True
                if anchor_dir:
                    d = os.path.dirname(urlparse(media).path) + "/"
                    if d != anchor_dir:
                        keep = False
                if keep:
                    out.extend(pending)
                    out.append(media)
                    kept += 1
                else:
                    removed += 1
                pending = []
                continue
            out.append(self._rewrite_tag(l, source_url))

        if removed > 0 and (kept == 0 or removed > kept):
            out = []
            for l in lines:
                if l.startswith("#"):
                    out.append(self._rewrite_tag(l, source_url))
                else:
                    out.append(urljoin(source_url, l))
            removed = 0

        cleaned = []
        for l in out:
            if l == "#EXT-X-DISCONTINUITY" and cleaned and cleaned[-1] == "#EXT-X-DISCONTINUITY":
                continue
            cleaned.append(l)
        if removed:
            self.log("m3u8 filtered: kept=%d removed=%d" % (kept, removed))
        return "\n".join(cleaned) + "\n"

    def _rewrite_tag(self, line, source_url):
        if line.startswith("#EXT-X-KEY") or line.startswith("#EXT-X-MAP"):
            def repl(m):
                return 'URI="' + urljoin(source_url, m.group(1)) + '"'
            return re.sub(r'URI="([^"]+)"', repl, line)
        return line

    def destroy(self):
        pass
