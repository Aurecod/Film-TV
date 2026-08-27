# -*- coding: utf-8 -*-
# 黄豆短剧 huangdoudj.com 爬虫 (Fongmi type 3)
# 静态站点 HTML 解析 + /play/<id>/<ep>.m3u8 直链
# 稳定性设计: TTL缓存 / 过期数据兜底 / 双域名自动回退 / 风控页识别 / 连接级重试
import json
import re
import time
import requests

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        pass


class Spider(BaseSpider):
    def __init__(self):
        self.host = "https://huangdoudj.com"
        self.name = "黄豆短剧"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept-Encoding": "gzip, deflate",
        })
        self._retry_adapter()
        self._cache = {}      # path -> (ts, html)
        self._ep_cache = {}   # vid -> (ts, {ep: bool})
        self._cookie = ""     # 用户自己的站点登录态(付费后填入)
        self._warmed = False
        self.class_list = [
            {"type_id": "all", "type_name": "全部短剧"},
            {"type_id": "yuandou", "type_name": "独家原创"},
            {"type_id": "mgdj", "type_name": "魔改短剧"},
            {"type_id": "ai", "type_name": "AI漫剧"},
            {"type_id": "erciyuan", "type_name": "二次元"},
            {"type_id": "cbdj", "type_name": "擦边短剧"},
            {"type_id": "real", "type_name": "真人短剧"},
            {"type_id": "heiliao", "type_name": "黑料"},
        ]

    def _retry_adapter(self):
        """连接级自动重试: 移动端 keep-alive 断连/DNS 抖动时透明恢复"""
        try:
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
            try:
                retry = Retry(total=2, connect=2, read=2, status=2,
                              backoff_factor=0.5, status_forcelist=(502, 503),
                              allowed_methods=frozenset(["GET"]))
            except TypeError:  # 旧版 urllib3
                retry = Retry(total=2, connect=2, read=2, status=2,
                              backoff_factor=0.5, status_forcelist=(502, 503),
                              method_whitelist=frozenset(["GET"]))
            adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=8)
            self.session.mount("https://", adapter)
            self.session.mount("http://", adapter)
        except Exception:
            pass

    def init(self, extend=""):
        if extend:
            try:
                cfg = json.loads(extend)
                site = (cfg.get("site") or cfg.get("base_url") or "").strip().rstrip("/")
                if site:
                    self.host = site
                cookie = (cfg.get("cookie") or "").strip()
                if cookie:
                    # 用户自己在站点付费/开会员后的登录态, 用于播放已购集
                    self._cookie = cookie
                    self.session.headers["Cookie"] = cookie
            except Exception:
                pass
        # 预热: 只预热一次, 提前建好 TCP+TLS 并探测可用域名
        if not self._warmed:
            self._warmed = True
            try:
                self._get("/", expect="dm-card")
            except Exception:
                pass

    def getName(self):
        return self.name

    # ---------------- 首页 ----------------
    def homeContent(self, filter):
        html = self._get("/", expect="dm-card", ttl=60)
        items = self._feature_cards(html) + self._cards(html)
        seen, list_ = set(), []
        for it in items:
            if it["vod_id"] and it["vod_id"] not in seen:
                seen.add(it["vod_id"])
                list_.append(it)
            # 重复 id 时保留带集数角标的那条 (推荐位卡片没有集数)
            elif it["vod_id"] in seen and "集" in it.get("vod_remarks", ""):
                for j, old in enumerate(list_):
                    if old["vod_id"] == it["vod_id"] and "集" not in old.get("vod_remarks", ""):
                        list_[j] = it
                        break
        return {"class": self.class_list, "filters": {}, "list": list_, "parse": 0, "jx": 0}

    # ---------------- 分类 ----------------
    def categoryContent(self, tid, pg, filter, extend):
        tid = (tid or "all").strip()
        pg = max(1, self._int(pg, 1))
        if tid == "all":
            path = "/page/%d/" % pg if pg > 1 else "/"
        else:
            path = "/category/%s/" % tid if pg == 1 else "/category/%s/page/%d/" % (tid, pg)
        html = self._get(path, expect="dm-card", ttl=60)
        items = self._cards(html)
        return {
            "page": pg,
            "pagecount": pg + 1 if len(items) >= 30 else pg,
            "limit": 36,
            "total": 4500,
            "list": items,
            "parse": 0,
            "jx": 0,
        }

    # ---------------- 详情 ----------------
    def detailContent(self, ids):
        vid = self._sid(ids[0]) if isinstance(ids, (list, tuple)) else self._sid(ids)
        html = self._get("/series/details/%s.html" % vid, expect=vid, ttl=300)
        if not html:
            return {"list": []}
        data = {"vod_id": vid, "vod_name": vid, "vod_pic": "", "type_name": "",
                "vod_year": "", "vod_area": "", "vod_remarks": "", "vod_actor": "",
                "vod_director": "", "vod_content": "", "vod_play_from": self.name,
                "vod_play_url": ""}

        m = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
        if m:
            data["vod_name"] = self._clean(m.group(1))

        m = re.search(r'data-video-cover="([^"]+)"', html)
        if m:
            data["vod_pic"] = m.group(1)
        if not data["vod_pic"]:
            ld = self._json_ld(html)
            img = ld.get("image")
            if isinstance(img, list) and img:
                data["vod_pic"] = img[0]
            elif isinstance(img, str):
                data["vod_pic"] = img

        m = re.search(r'<a[^>]*class="dm-detail-types"[^>]*>([^<]+)</a>', html)
        if m:
            data["type_name"] = self._clean(m.group(1))

        m = re.search(r'dm-detail-meta-label">([^<]+)<', html)
        if m:
            m2 = re.search(r'全\s*\d+\s*集', m.group(1))
            data["vod_remarks"] = m2.group(0) if m2 else self._clean(m.group(1))

        ld = self._json_ld(html)
        data["vod_year"] = (ld.get("datePublished") or "")[:4]
        kws = ld.get("keywords") or []
        if isinstance(kws, list) and kws:
            data["vod_content"] = "标签: " + " / ".join(str(k) for k in kws)
        m = re.search(r'<meta name="description" content="([^"]+)"', html)
        desc = m.group(1) if m else ""
        if desc and desc != data["vod_name"]:
            data["vod_content"] = (desc + " " + data["vod_content"]).strip()

        # 集数 + 付费标记: 解析每个集锚点的 data-ep-free / data-pay-price
        ep_info = {}
        for m in re.finditer(r'<a class="dm-ep[^"]*"[^>]*?data-ep="(\d+)"\s*data-ep-free="(\d)"\s*data-pay-method="([^"]*)"\s*data-pay-price="([^"]*)"', html):
            ep, free, method, price = int(m.group(1)), m.group(2) == "1", m.group(3), m.group(4)
            ep_info[ep] = (free, price)
        if not ep_info:
            m = re.search(r'全\s*(\d+)\s*集', html)
            n = self._int(m.group(1), 0) if m else 0
            ep_info = {e: (True, "") for e in range(1, n + 1)}
        eps = sorted(ep_info)

        play = []
        free_eps = [e for e in eps if ep_info[e][0]]
        locked_eps = [e for e in eps if not ep_info[e][0]]
        # 免费集: 探测, 只列真实有文件的 (站点偶有漏传)
        n_free_playable = 0
        if free_eps:
            real = self._probe_eps(vid, free_eps)
            keep = free_eps if real is None else real
            n_free_playable = len(keep)
            play.extend(("第%d集" % e, e) for e in keep)
        # 付费集: 有登录态则探测是否已购, 否则列出并标"金币N"
        if locked_eps:
            if self._cookie:
                real = self._probe_eps(vid, locked_eps)
                if real is None:
                    play.extend(("第%d集" % e, e) for e in locked_eps)
                else:
                    realset = set(real)
                    for e in locked_eps:
                        if e in realset:
                            play.append(("第%d集" % e, e))
                        else:
                            play.append(("第%d集·金币%s" % (e, ep_info[e][1] or "?"), e))
            else:
                play.extend(("第%d集·金币%s" % (e, ep_info[e][1] or "?"), e) for e in locked_eps)
        play.sort(key=lambda x: x[1])

        if eps:
            if locked_eps and not self._cookie:
                data["vod_remarks"] = "全%d集·免费%d集" % (len(eps), n_free_playable)
            elif n_free_playable < len(free_eps):
                data["vod_remarks"] = "全%d集·可播%d集" % (len(eps), n_free_playable)
        data["vod_play_url"] = "#".join(
            "%s$%s/play/%s/%d.m3u8" % (name, self.host, vid, e) for name, e in play)
        if not play:
            data["vod_remarks"] = "暂无资源"
        return {"list": [data], "parse": 0, "jx": 0}

    # ---------------- 搜索 ----------------
    def searchContent(self, key, quick, pg="1"):
        from urllib.parse import quote
        pg = max(1, self._int(pg, 1))
        q = quote(str(key or ""))
        path = ("/search/page/%d/?keyword=%s" % (pg, q)) if pg > 1 else ("/search/?keyword=%s" % q)
        html = self._get(path, ttl=60)  # 搜索结果可能为空, 不强制标记
        items = self._cards(html)
        return {
            "page": pg,
            "pagecount": pg + 1 if len(items) >= 30 else pg,
            "limit": 36,
            "total": 99999,
            "list": items,
            "parse": 0,
            "jx": 0,
        }

    # ---------------- 播放 ----------------
    def playerContent(self, flag, id, vipFlags):
        url = str(id or "").split("#", 1)[0].strip()
        if not url.startswith("http"):
            return {"parse": 0, "playUrl": "", "url": "", "jx": 0, "header": {}}
        url = self._precheck(url)
        header = {
            "User-Agent": self.session.headers["User-Agent"],
            "Referer": self.host + "/",
            "Origin": self.host,
        }
        if self._cookie:
            header["Cookie"] = self._cookie
        return {
            "parse": 0,
            "playUrl": "",
            "url": url,
            "jx": 0,
            "header": header,
        }

    def _precheck(self, url):
        """播放前预检 m3u8: 吸收 CF 429/403 限流抖动, 必要时换域名。
        404 (剧集文件真缺失) 直接返回原 URL, 不做替换。"""
        import urllib.parse
        candidates = [url]
        try:
            parsed = urllib.parse.urlsplit(url)
            alt = self._alt_host()
            if parsed.netloc not in ("hddj.tv", "www.hddj.tv") and alt.startswith("https://hddj.tv"):
                candidates.append("https://" + "hddj.tv" + parsed.path)
            else:
                candidates.append("https://huangdoudj.com" + parsed.path)
        except Exception:
            pass
        for u in candidates:
            for attempt in range(3):
                try:
                    r = self.session.get(u, timeout=8)
                except Exception:
                    time.sleep(1 + attempt)
                    continue
                if r.status_code == 200:
                    return u
                if r.status_code in (403, 429, 502, 503, 504):
                    time.sleep(1 + attempt)  # 限流/风控: 退避后重试
                    continue
                # 404: 该集文件缺失, 尝试自动跳到下一个有文件的集
                if r.status_code == 404:
                    return self._skip_missing(u)
                return u
        return candidates[-1]

    def _skip_missing(self, url):
        """404 时向后探测最多3集, 返回第一个有文件的集 URL; 都没有则原样返回"""
        m = re.search(r'(\d+)(\.m3u8)', url)
        if not m:
            return url
        seq = int(m.group(1))
        for n in range(1, 4):
            e = seq + n
            new_url = url[:m.start(1)] + str(e) + url[m.end(1):]
            try:
                r = self.session.head(new_url, timeout=8)
            except Exception:
                break
            if r.status_code == 200:
                return new_url
            if r.status_code != 404:
                break
        return url

    # ---------------- 内部工具 ----------------
    def _alt_host(self):
        return "https://huangdoudj.com" if "hddj.tv" in self.host else "https://hddj.tv"

    def _get(self, path, expect=None, ttl=60):
        """GET 页面。TTL缓存 -> 双域名回退 -> 风控页识别 -> 过期缓存兜底"""
        now = time.time()
        hit = self._cache.get(path)
        if hit and now - hit[0] < ttl:
            return hit[1]
        hosts = [self.host]
        alt = self._alt_host()
        if alt != self.host:
            hosts.append(alt)
        for host in hosts:
            try:
                r = self.session.get(host + path, timeout=12)
            except Exception:
                continue  # 连接错误: 换域名
            if r.status_code != 200:
                # 403 风控 / 429 频控 / 5xx: 换另一个域名再试
                continue
            html = r.text
            if expect and expect not in html:
                # 200 但内容不对 (CF 挑战页/跳转页) — 不当作有效数据
                continue
            if host != self.host:
                self.host = host  # 记住当前可用域名
            self._cache[path] = (now, html)
            return html
        # 全部失败: 有旧缓存就返回旧的 (保数据连续性), 否则空
        if hit:
            return hit[1]
        return ""

    def _probe_eps(self, vid, eps, ttl=300):
        """并行 HEAD 探测哪些集真实有文件。
        返回存在的集列表; 网络异常(探测不可信)时返回 None 表示不过滤。"""
        now = time.time()
        hit = self._ep_cache.get(vid)
        cached = hit[1] if hit and now - hit[0] < ttl else {}
        missing = [e for e in eps if e not in cached]
        if missing:
            from concurrent.futures import ThreadPoolExecutor
            def probe(e):
                try:
                    r = self.session.head("%s/play/%s/%d.m3u8" % (self.host, vid, e), timeout=8)
                    return e, (r.status_code == 200)
                except Exception:
                    return e, None
            results = {}
            with ThreadPoolExecutor(max_workers=10) as ex:
                for e, ok in ex.map(probe, missing):
                    results[e] = ok
            if any(v is None for v in results.values()):
                return None  # 有探测失败, 结果不可信, 保持原列表
            cached.update(results)
            self._ep_cache[vid] = (now, cached)
        return [e for e in eps if cached.get(e)]

    def _cards(self, html):
        """解析 <article class="dm-card"> 列表卡片"""
        if not html:
            return []
        items = []
        for m in re.finditer(r'<article class="dm-card"[^>]*data-article-id="([0-9a-f]+)"[^>]*>(.*?)</article>', html, re.S):
            aid, block = m.group(1), m.group(2)
            name, pic, heat, ep = "", "", "", ""
            m2 = re.search(r'class="dm-card-title"[^>]*>.*?<a[^>]*title="([^"]*)"', block, re.S)
            if m2:
                name = self._clean(m2.group(1))
            m2 = re.search(r'<img class="dm-card-img" src="([^"]+)"', block)
            if m2:
                pic = m2.group(1)
            m2 = re.search(r'class="dm-card-heat-text">([^<]+)</span>', block)
            if m2:
                heat = self._clean(m2.group(1))
            m2 = re.search(r'dm-ep-badge">\s*([^<]+?)\s*<', block)
            if m2:
                ep = self._clean(m2.group(1))
            if not name:
                m2 = re.search(r'<a class="dm-card-cover"[^>]*aria-label="([^"]*)"', block)
                if m2:
                    name = self._clean(m2.group(1))
            if name:
                items.append({"vod_id": aid, "vod_name": name, "vod_pic": pic,
                              "vod_remarks": ep or heat, "type_name": ""})
        return items

    def _feature_cards(self, html):
        """解析首页推荐位 dm-feature-card"""
        if not html:
            return []
        items = []
        for m in re.finditer(r'<div class="dm-feature-card">(.*?)</div>\s*</div>\s*</div>', html, re.S):
            block = m.group(1)
            m2 = re.search(r'<h3 class="dm-feature-title"><a[^>]*title="([^"]*)"', block)
            name = self._clean(m2.group(1)) if m2 else ""
            m3 = re.search(r'href="(/series/details/([0-9a-f]+)\.html)"', block)
            aid = m3.group(2) if m3 else ""
            m4 = re.search(r'<img class="dm-feature-cover-(?:bg|img)" src="([^"]+)"', block)
            pic = m4.group(1) if m4 else ""
            if name and aid:
                items.append({"vod_id": aid, "vod_name": name, "vod_pic": pic,
                              "vod_remarks": "推荐", "type_name": ""})
        return items

    def _json_ld(self, html):
        """返回 JSON-LD 中 @type=Article 的节点"""
        for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
            try:
                d = json.loads(m.group(1))
            except Exception:
                continue
            graph = d.get("@graph") if isinstance(d, dict) else d
            if isinstance(graph, list):
                for it in graph:
                    if isinstance(it, dict) and it.get("@type") == "Article":
                        return it
        return {}

    def _sid(self, x):
        s = str(x or "")
        m = re.search(r'([0-9a-f]{16,})', s)
        return m.group(1) if m else s

    def _clean(self, s):
        return re.sub(r"\s+", " ", str(s or "")).strip()

    def _int(self, x, d=0):
        try:
            return int(x)
        except Exception:
            return d
