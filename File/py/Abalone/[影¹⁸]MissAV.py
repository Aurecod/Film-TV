# coding=utf-8
# MissAV - Hawk spider
# 域名并行探测 + packer 解包 + surrit 直链 + fourhoi 封面
# 参考: ~/workspace/fwd-study/MissAV_TuT.js (v3.8.2)
try:
    from base.spider import Spider
except ImportError:
    class Spider:
        pass

import re, json, time, ssl, html as html_mod
import urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor

DOMAINS = [
    "https://missav.fans",
    "https://missav.media",
    "https://missav.ai",
    "https://missav.ws",
    "https://missav.live",
]
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1"

CATEGORIES = [
    ("dm539/cn/new", "最近更新"),
    ("dm278/cn/chinese-subtitle", "中文字幕"),
    ("dm632/cn/release", "日本AV"),
    ("dm36/cn/siro", "素人 SIRO"),
    ("dm34/cn/luxu", "素人 LUXU"),
    ("dm32/cn/gana", "素人 GANA"),
    ("dm816/cn/uncensored-leak", "无码流出"),
    ("dm473/cn/fc2", "FC2"),
    ("dm1977446/cn/heyzo", "HEYZO"),
    ("dm63/cn/madou", "麻豆传媒"),
    ("actress_index", "👩女优"),
    ("actress_ranking", "🏆女优排行"),
    ("genre_index", "🎬类型"),
    ("maker_index", "🏢发行商"),
]

_CTX = ssl._create_unverified_context()

def _http_get(url, referer="", timeout=20, retries=3):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Referer": referer or url,
                "Connection": "keep-alive",
            })
            resp = urllib.request.urlopen(req, timeout=timeout, context=_CTX)
            data = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                import gzip
                data = gzip.decompress(data)
            return data.decode("utf-8", errors="ignore")
        except Exception as e:
            last = e
            time.sleep(0.4 * (2 ** i))
    return None

def _looks_like_list(html):
    if not html:
        return False
    if re.search(r"<title>Just a moment|Attention Required|Please wait", html, re.I):
        return False
    return ("text-secondary" in html or "thumbnail" in html or
            "fourhoi" in html or "surrit" in html)

_WINNER = [""]
_ACT_HOST = [""]

def _race_domain():
    """并行探测域名：谁先返回合法列表页用谁，总预算 12 秒封顶
    （旧写法按顺序等每个结果，挂起的域名能把加载拖到几十秒）"""
    if _WINNER[0]:
        return _WINNER[0]
    def probe(domain):
        html = _http_get(domain + "/dm539/cn/new", referer=domain + "/", timeout=8, retries=1)
        if _looks_like_list(html):
            return domain
        return None
    import concurrent.futures as _cf
    winner = None
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(probe, d): d for d in DOMAINS}
        try:
            for f in _cf.as_completed(futs, timeout=12):
                try:
                    r = f.result()
                except Exception:
                    r = None
                if r:
                    winner = r
                    break
        except Exception:
            pass
        for ff in futs:
            ff.cancel()
    _WINNER[0] = winner or DOMAINS[0]
    return _WINNER[0]

def _unpack_packer(html):
    """packer 解包 (TuT unpackPacker 的 Python 版)"""
    out = []
    pat = re.compile(
        r"eval\s*\(\s*function\s*\(\s*p\s*,\s*a\s*,\s*c\s*,\s*k\s*,\s*e\s*,\s*d\s*\)"
        r"[\s\S]+?\}\s*\(\s*'([\s\S]+?)'\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*'([\s\S]+?)'[\s\S]+?\)",
        re.S)
    b36 = "0123456789abcdefghijklmnopqrstuvwxyz"
    for m in pat.finditer(html or ""):
        try:
            p = m.group(1).replace("\\'", "'")
            c = int(m.group(3))
            k = m.group(4).split("|")
            idx = c
            while idx > 0:
                idx -= 1
                if idx < len(k) and k[idx]:
                    n, w = idx, ""
                    if n == 0:
                        w = "0"
                    else:
                        while n > 0:
                            w = b36[n % 36] + w
                            n //= 36
                    p = re.sub(r"\b" + re.escape(w) + r"\b", k[idx], p)
            out.append(p)
        except Exception:
            pass
    return "\n".join(out)

def _extract_m3u8(html):
    """详情页提取 surrit m3u8，优先 1080p > 720p"""
    if not html:
        return ""
    for script in re.findall(r"<script[^>]*>([\s\S]*?)</script>", html, re.I):
        if "surrit" in script and ".m3u8" in script:
            urls = re.findall(r"https:\\/\\/surrit\.[^\"'\\\s]+\/[a-f0-9\-]+\/[^\"'\s]*\.m3u8", script)
            urls = [u.replace("\\/", "/") for u in urls]
            if urls:
                for key in ("1080p", "720p"):
                    hit = [u for u in urls if key in u]
                    if hit:
                        return hit[0]
                return urls[0]
    unpacked = _unpack_packer(html)
    if unpacked:
        urls = re.findall(r"https:\/\/surrit\.[^\"'\\\s]+\/[a-f0-9\-]+\/[^\"'\s]*\.m3u8", unpacked.replace("\\/", "/"))
        if urls:
            for key in ("1080p", "720p"):
                hit = [u for u in urls if key in u]
                if hit:
                    return hit[0]
            return urls[0]
    flat = html.replace("\\/", "/")
    mu = re.search(r"https:\/\/(surrit\.[^\/\"'\s]+)\/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})", flat, re.I)
    if mu:
        return "https://%s/%s/playlist.m3u8" % (mu.group(1), mu.group(2))
    mu2 = re.search(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}", html)
    if mu2:
        return "https://surrit.mrstcdn.store/%s/playlist.m3u8" % mu2.group(0)
    return ""

def _video_id(href):
    if not href:
        return ""
    slug = href.split("#")[0].split("?")[0].rstrip("/").split("/")[-1]
    return re.sub(r"-(uncensored-leak|chinese-subtitle)$", "", slug, flags=re.I)

def _cover(vid):
    if not vid:
        return ""
    return "https://fourhoi.mrstcdn.store/%s/cover-t.jpg" % vid.lower()

class Spider(Spider):
    def getName(self):
        return "MissAV"

    def init(self, extend=""):
        # 加载阶段不做任何网络探测（竞速里 DNS/连接挂起不受超时控制，
        # 会把整个源加载拖死）：先钉实测可用的域名，真拉不到再竞速
        self.host = _WINNER[0] or "https://missav.fans"
        self.referer = self.host + "/"

    def _list_url(self, endpoint, pg):
        pg = int(pg or 1)
        url = "%s/%s" % (self.host, endpoint)
        if pg > 1:
            url += "?page=%d" % pg
        return url

    def _parse_cards(self, html):
        items = []
        if not html:
            return items
        cards = re.findall(
            r'<div[^>]*class="[^"]*thumbnail[^"]*"[^>]*>([\s\S]*?)</div>\s*</div>\s*</div>', html)
        if not cards:
            for m in re.finditer(
                    r'<a[^>]*class="[^"]*text-secondary[^"]*"[^>]*href="([^"]+)"[^>]*>([^<]{3,120})',
                    html):
                href, title = m.group(1), m.group(2).strip()
                vid = _video_id(href)
                if vid:
                    items.append({"vod_id": vid, "vod_name": title,
                                  "vod_pic": _cover(vid), "vod_remarks": ""})
            return items
        for card in cards:
            try:
                lm = re.search(r'href="([^"]*?/cn/[a-zA-Z0-9\-]+)"', card)
                if not lm:
                    continue
                href = lm.group(1)
                if href.startswith("/"):
                    href = self.host + href
                vid = _video_id(href)
                tm = re.search(r'class="[^"]*text-secondary[^"]*"[^>]*>([^<]{3,200})', card)
                title = tm.group(1).strip() if tm else vid
                pic = ""
                for im in re.finditer(r'<img[^>]*data-src="([^"]+)"', card):
                    u = im.group(1)
                    if u.startswith("data:") or u.endswith(".mp4"):
                        continue
                    pic = u
                    break
                if not pic:
                    im = re.search(r'<img[^>]*src="(https?://[^"]+)"', card)
                    if im and not im.group(1).startswith("data:"):
                        pic = im.group(1)
                if not pic:
                    pic = _cover(vid)
                dm = re.search(r'bottom-1[^"]*"[^>]*>\s*([\d:]+)', card)
                remarks = dm.group(1).strip() if dm else ""
                items.append({"vod_id": vid, "vod_name": title,
                              "vod_pic": pic, "vod_remarks": remarks})
            except Exception:
                continue
        return items

    def homeContent(self, filter=False):
        return {
            "class": [{"type_id": tid, "type_name": name} for tid, name in CATEGORIES],
            "filters": {},
        }

    def homeVideoContent(self):
        html = _http_get(self._list_url("dm539/cn/new", 1), referer=self.referer)
        if not self._parse_cards(html) and not _WINNER[0]:
            # 钉住的域名拉不到才竞速换域名重试一次
            self.host = _race_domain()
            self.referer = self.host + "/"
            html = _http_get(self._list_url("dm539/cn/new", 1), referer=self.referer)
        return {"list": self._parse_cards(html)[:24]}

    def _parse_actresses(self, html):
        """女优索引/排行页的人物卡（<li> 块：头像+名字+片数+出道年）"""
        items = []
        if not html:
            return items
        seen = set()
        for block in re.split(r"<li>", html):
            if "/cn/actresses/" not in block or "<h4" not in block:
                continue
            hm = re.search(r'href="https?://[^"]+/cn/actresses/([^"/]+)"', block)
            if not hm:
                continue
            path = "/cn/actresses/" + hm.group(1)
            if path in seen:
                continue
            nm = re.search(r"<h4[^>]*>([^<]+)</h4>", block)
            name = nm.group(1).strip() if nm else ""
            if not name:
                continue
            seen.add(path)
            im = re.search(r'<img[^>]*src="(https?://[^"]*actress[^"]*)"', block)
            cm = re.search(r"<p[^>]*>([^<]*条影片)</p>", block)
            dm = re.search(r"<p[^>]*>(\d{4} 出道)</p>", block)
            remarks = " · ".join(x for x in (
                cm.group(1) if cm else "", dm.group(1) if dm else "") if x)
            items.append({"vod_id": "actress:" + path, "vod_name": name,
                          "vod_pic": im.group(1) if im else "",
                          "vod_remarks": remarks})
        return items

    def _actress_fetch(self, path, kind, section="actresses"):
        """索引页专用抓取：有些域名列表页秒开、索引页却挂起（加载会被拖死），
        所以单次 8 秒、失败立刻换实测能出索引页的域名，通了记住下次直用。
        section 区分女优（actresses）与类型/发行商（genres/makers），校验标记不同"""
        hosts = []
        for h in (_ACT_HOST[0], self.host, "https://missav.fans",
                  "https://missav.media"):
            if h and h not in hosts:
                hosts.append(h)
        for h in hosts:
            html = _http_get(h + path, referer=h + "/", timeout=8, retries=1)
            if not html:
                continue
            if kind == "list":
                if section == "actresses":
                    ok = "/cn/actresses/" in html and "<h4" in html
                else:
                    ok = ("/cn/%s/" % section) in html and "text-nord13" in html
            else:
                ok = "<h1" in html and "thumbnail" in html
            if ok:
                _ACT_HOST[0] = h
                return html
        return None

    def _actress_list(self, kind, pg):
        if kind == "actress_ranking":
            path = "/cn/actresses/ranking"
        else:
            path = "/cn/actresses"
            if pg > 1:
                path += "?page=%d" % pg
        html = self._actress_fetch(path, "list")
        items = self._parse_actresses(html)
        pagecount = 1
        if kind == "actress_index":
            nums = [int(x) for x in re.findall(r"[?&]page=(\d+)", html or "")]
            pagecount = max(nums) if nums else (pg + 1 if items else pg)
        return {"list": items, "page": pg, "pagecount": pagecount,
                "limit": 24, "total": pagecount * 24}

    def _parse_index_entries(self, html, section, prefix):
        """类型/发行商索引页的文字网格条目（名字+片数，站上本身无图）。
        条目名在 class 带 text-nord13 的锚里（导航菜单也有同名链接但没这个类，
        靠它避开）；片数在紧随的 <p> 里另一个同址锚的"xx 条影片"文本里"""
        items = []
        if not html:
            return items
        counts = {}
        for cm in re.finditer(
                r'href="https?://[^"]+/cn/%s/([^"/]+)"[^>]*>\s*([\d,]+)\s*条影片' % section,
                html):
            counts[cm.group(1)] = cm.group(2)
        seen = set()
        pat = re.compile(
            r'<a[^>]*href="https?://[^"]+/cn/%s/([^"/]+)"[^>]*class="[^"]*text-nord13[^"]*"[^>]*>([\s\S]*?)</a>'
            % section)
        for m in pat.finditer(html):
            slug = m.group(1)
            if slug in seen:
                continue
            name = html_mod.unescape(re.sub(r"<[^>]+>", "", m.group(2)))
            name = re.sub(r"\s+", " ", name).strip()
            if not name:
                continue
            seen.add(slug)
            remarks = (counts[slug] + " 条影片") if slug in counts else ""
            items.append({"vod_id": "%s:/cn/%s/%s" % (prefix, section, slug),
                          "vod_name": name, "vod_pic": "",
                          "vod_remarks": remarks})
        return items

    def _index_list(self, tid, pg):
        """类型/发行商索引分类：分页出条目卡（类型 42 页、发行商 72 页）"""
        if tid == "genre_index":
            section, prefix = "genres", "genre"
        else:
            section, prefix = "makers", "maker"
        path = "/cn/" + section
        if pg > 1:
            path += "?page=%d" % pg
        html = self._actress_fetch(path, "list", section)
        items = self._parse_index_entries(html, section, prefix)
        nums = [int(x) for x in re.findall(r"[?&]page=(\d+)", html or "")]
        pagecount = max(nums) if nums else (pg + 1 if items else pg)
        return {"list": items, "page": pg, "pagecount": pagecount,
                "limit": 36, "total": pagecount * 36}

    def categoryContent(self, tid, pg, filter=False, extend=None):
        pg = int(pg or 1)
        if tid in ("actress_index", "actress_ranking"):
            return self._actress_list(tid, pg)
        if tid in ("genre_index", "maker_index"):
            return self._index_list(tid, pg)
        html = _http_get(self._list_url(tid, pg), referer=self.referer)
        items = self._parse_cards(html)
        return {"list": items, "page": pg, "pagecount": 2000 if items else 1,
                "limit": 24, "total": 48000 if items else 0}

    def _actress_detail(self, path):
        """女优合集：她的片单按页分线路（每线一页，最多收 8 页，各页并发抓；
        站上大牌女优动辄几千部，合集给最新部分，全量回站上看）"""
        html = self._actress_fetch(path, "detail")
        if not html:
            return {"list": []}
        base = (_ACT_HOST[0] or self.host) + path
        tm = re.search(r"<h1[^>]*>([\s\S]*?)</h1>", html)
        name = re.sub(r"<[^>]+>", "", tm.group(1)).strip() if tm else ""
        name = re.sub(r"出演的 AV 在线看.*$", "", name).strip() or "女优片单"
        pm = re.search(r"https://fourhoi\.mrstcdn\.store/actress/[^\"']+", html)
        pic = pm.group(0) if pm else ""
        nums = [int(x) for x in re.findall(r"[?&]page=(\d+)", html)]
        pagecount = max(nums) if nums else 1
        pages = min(pagecount, 8)
        # 各页片单并发抓：串行一页页等会把详情调用拖超时（真机实测）
        page_html = {1: html}
        if pages > 1:
            with ThreadPoolExecutor(max_workers=5) as ex:
                futs = {ex.submit(_http_get, base + "?page=%d" % pg,
                                   base, 10, 1): pg
                        for pg in range(2, pages + 1)}
                for f, pg in futs.items():
                    try:
                        page_html[pg] = f.result() or ""
                    except Exception:
                        page_html[pg] = ""
        froms, urls = [], []
        for pg in range(1, pages + 1):
            html = page_html.get(pg, "")
            eps = []
            ep_host = _ACT_HOST[0] or self.host
            for c in self._parse_cards(html):
                t = c["vod_name"].replace("#", " ").replace("$", " ")
                eps.append("%s$%s/cn/%s" % (t, ep_host, c["vod_id"]))
            if eps:
                froms.append("片单" if pages == 1 else "第%d页" % pg)
                urls.append("#".join(eps))
        return {"list": [{
            "vod_id": "actress:" + path,
            "vod_name": name,
            "vod_pic": pic,
            "vod_actor": name,
            "vod_remarks": "共 %d 页" % pagecount,
            "vod_content": name,
            "vod_play_from": "$$$".join(froms),
            "vod_play_url": "$$$".join(urls),
        }]}

    def _works_detail(self, path, prefix, section):
        """类型/发行商合集：与女优合集同法——作品按页分线路、各页并发抓、
        最多收 8 页（热门发行商上千页，合集给最新部分，全量回站上看）；
        封面用第一部作品的图（索引条目本身无图）"""
        html = self._actress_fetch(path, "detail", section)
        if not html:
            return {"list": []}
        base = (_ACT_HOST[0] or self.host) + path
        slug = path.rstrip("/").split("/")[-1]
        tm = re.search(r"<h1[^>]*>([\s\S]*?)</h1>", html)
        name = re.sub(r"<[^>]+>", "", tm.group(1)) if tm else ""
        name = re.sub(r"\s+", " ", name).strip()
        name = re.sub(r"的?\s*AV\s*在线看.*$", "", name).strip()
        if not name or len(name) > 40:
            name = urllib.parse.unquote(slug)
        nums = [int(x) for x in re.findall(r"[?&]page=(\d+)", html)]
        pagecount = max(nums) if nums else 1
        pages = min(pagecount, 8)
        page_html = {1: html}
        if pages > 1:
            with ThreadPoolExecutor(max_workers=5) as ex:
                futs = {ex.submit(_http_get, base + "?page=%d" % pg,
                                   base, 10, 1): pg
                        for pg in range(2, pages + 1)}
                for f, pg in futs.items():
                    try:
                        page_html[pg] = f.result() or ""
                    except Exception:
                        page_html[pg] = ""
        froms, urls = [], []
        pic = ""
        for pg in range(1, pages + 1):
            eps = []
            ep_host = _ACT_HOST[0] or self.host
            for c in self._parse_cards(page_html.get(pg, "")):
                if not pic:
                    pic = c["vod_pic"]
                t = c["vod_name"].replace("#", " ").replace("$", " ")
                eps.append("%s$%s/cn/%s" % (t, ep_host, c["vod_id"]))
            if eps:
                froms.append("片单" if pages == 1 else "第%d页" % pg)
                urls.append("#".join(eps))
        return {"list": [{
            "vod_id": prefix + ":" + path,
            "vod_name": name,
            "vod_pic": pic,
            "vod_remarks": "共 %d 页" % pagecount,
            "vod_content": name,
            "vod_play_from": "$$$".join(froms),
            "vod_play_url": "$$$".join(urls),
        }]}

    def detailContent(self, ids):
        vid = ids[0] if ids else ""
        if isinstance(vid, str) and vid.startswith("actress:"):
            return self._actress_detail(vid[len("actress:"):])
        if isinstance(vid, str) and vid.startswith("genre:"):
            return self._works_detail(vid[len("genre:"):], "genre", "genres")
        if isinstance(vid, str) and vid.startswith("maker:"):
            return self._works_detail(vid[len("maker:"):], "maker", "makers")
        url = "%s/cn/%s" % (self.host, vid.lower())
        html = _http_get(url, referer=self.referer)
        if not html:
            return {"list": []}
        tm = re.search(r"<title>([^<]+)</title>", html)
        title = tm.group(1).split(" - MissAV")[0].strip() if tm else vid
        m3u8 = _extract_m3u8(html)
        pic = _cover(vid)
        cm = re.search(r'property="og:image"\s+content="([^"]+)"', html)
        if cm:
            pic = cm.group(1)
        play_url = ("正片$%s" % m3u8) if m3u8 else ("正片$%s" % url)
        return {"list": [{
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": pic,
            "vod_play_from": "MissAV",
            "vod_play_url": play_url,
        }]}

    def searchContent(self, key, quick=False, pg="1"):
        pg = int(pg or 1)
        q = urllib.parse.quote(key.strip())
        url = "%s/cn/search/%s" % (self.host, q)
        if pg > 1:
            url += "?page=%d" % pg
        html = _http_get(url, referer=self.referer)
        items = self._parse_cards(html)
        if not items and pg == 1:
            html = _http_get(self._list_url("dm539/cn/new", 1), referer=self.referer)
            items = self._parse_cards(html)[:24]
        return {"list": items, "page": pg}

    def _fetch_video_page(self, url):
        """视频页抓取：原域名慢/挂时换镜像域名试（/cn/{番号} 路径各镜像通用），
        单次 8 秒不重试，别让点播调用耗在抓页上"""
        m = re.match(r"^(https?://[^/]+)(/.*)$", url or "")
        if not m:
            return _http_get(url, referer=self.referer), url
        path = m.group(2)
        hosts = []
        for h in (m.group(1), _ACT_HOST[0], self.host,
                  "https://missav.fans", "https://missav.media"):
            if h and h not in hosts:
                hosts.append(h)
        for h in hosts:
            html = _http_get(h + path, referer=h + "/", timeout=8, retries=1)
            if html:
                return html, h + path
        return None, url

    def playerContent(self, flag, id, vipFlags=None):
        url = (id or "").strip()
        if not url:
            return {"parse": 1, "url": "", "header": {}}
        if ".m3u8" in url:
            return {"parse": 0, "url": url,
                    "header": {"User-Agent": UA, "Referer": self.referer}}
        html, play_page = self._fetch_video_page(url)
        m3u8 = _extract_m3u8(html) if html else ""
        if m3u8:
            return {"parse": 0, "url": m3u8,
                    "header": {"User-Agent": UA, "Referer": self.referer}}
        return {"parse": 1, "url": play_page, "header": {"User-Agent": UA}}
