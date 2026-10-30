# -*- coding: utf-8 -*-
"""
123AV (123av.com) — FongMi py spider
站点：123av.com 聚合站（聚合 jable/missav/supjav 等），免 CF 盾，py 路线直连。
官方主域名无 CF 挑战（首页/列表/详情/搜索裸请求 200）。

结构（2026-10-28 逆向）：
  列表   /en/new /en/hot /en/recent /en/all?sort=today|week|month
        /en/censored /en/uncensored /en/uncensored-leaked
        /en/genres/<slug> /en/actresses/<slug> /en/makers/<slug>
        /en/series/<slug> /en/tags/<slug>    分页 ?page=N
  卡片   div.card：<a class="card__cover" href="/en/v/<code>">
        <img class="card__img" src=封面> <span class="card__dur">时长</span>
        <h3 class="card__title"><a class="card__link" href="/en/v/<code>">标题</a>
  详情   /en/v/<code>：h1.watch__title 标题；player(JSON.parse('...')) 分集，
        每集 url = https://sadie-shop.site/e/<hashId>（嵌入页，无 token）；
        watch__info 行：Code/Type/Release date/Duration/Cast/Maker/Genres/Tags
  搜索   /en/search?keyword=<kw>&page=N
  播放   sadie-shop.site/stream?id=<hashId> → {media:{stream}} → m3u8。
        m3u8 CDN（*.clearpureheart.site）必须带 Referer=https://sadie-shop.site/，
        分片文件名伪装 .css/.svg/.webp 等扩展名，实为 MPEG-TS 视频。
        主 m3u8 返回 qc/v.m3u8（720p），流 token 稳定但可能过期 → playerContent 每次重取。
"""
import json
import re
import threading
import time
from urllib.parse import quote, unquote

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        pass

NAME = "123AV"
HOSTS = ["https://123av.com"]
EMBED_HOST = "https://sadie-shop.site"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
DEBUG = False
STYLE = {"type": "rect", "ratio": 1.33}
PAGE_SIZE = 12
CACHE_TTL = 60

CARD_RE = re.compile(
    r'<a class="card__cover" href="/en/v/([^"]+)"[^>]*>\s*'
    r'<img class="card__img" src="([^"]+)"[^>]*>[\s\S]*?'
    r'<span class="card__dur">([^<]*)</span>'
)
TITLE_RE = re.compile(
    r'<h3 class="card__title"><a class="card__link" href="/en/v/([^"]+)">([\s\S]*?)</a></h3>'
)
EP_RE = re.compile(r"JSON\.parse\('(\[[\s\S]*?\])'\)")
ROW_RE = re.compile(r'<div class="watch__info-row">\s*<dt>([^<]+)</dt>\s*<dd[^>]*>([\s\S]*?)</dd>\s*</div>')

# 分类表：(显示名, type_id)。type_id 语义见 _cat_path()。
CATS = [
    ("最新", "new"),
    ("热门", "hot"),
    ("最近更新", "recent"),
    ("今日热门", "today"),
    ("本周热门", "week"),
    ("本月热门", "month"),
    ("有码", "censored"),
    ("无码", "uncensored"),
    ("无码泄露", "uncensored-leaked"),
    # 制作商
    ("[M]S-CUTE", "maker/s-cute"),
    ("[M]FC2", "maker/fc2"),
    ("[M]HEYZO", "maker/heyzo"),
    ("[M]1pondo", "maker/1pondo"),
    ("[M]Caribbeancom", "maker/caribbeancom"),
    ("[M]10musume", "maker/10musume"),
    ("[M]Pacopacomama", "maker/pacopacomama"),
    ("[M]Tokyo Hot", "maker/tokyo-hot"),
    ("[M]XXX-AV", "maker/xxx-av"),
    # 标签
    ("[T]SIRO", "tag/siro"),
    ("[T]LUXU", "tag/259luxu"),
    ("[T]200GANA", "tag/200gana"),
    ("[T]PRESTIGE", "tag/prestige-premium"),
    ("[T]ORECO", "tag/230oreco"),
    ("[T]ARA", "tag/261ara"),
    ("[T]390JAC", "tag/390jac"),
    # 演员
    ("[A]Yui Hatano", "actress/yui-hatano"),
    ("[A]Shinoda Yu", "actress/shinoda-yu"),
    ("[A]Hibiki Ohtsuki", "actress/hibiki-ohtsuki"),
    ("[A]Hamazaki Mao", "actress/hamazaki-mao"),
    ("[A]Ichika Matsumoto", "actress/ichika-matsumoto"),
    ("[A]Hasumi Claire", "actress/hasumi-claire"),
    ("[A]Niimura Akari", "actress/niimura-akari"),
    ("[A]Aika", "actress/aika"),
    ("[A]Mizuki Yayoi", "actress/mizuki-yayoi-1"),
    ("[A]Kobayakawa Reiko", "actress/kobayakawa-reiko"),
    ("[A]Waka Misono", "actress/waka-misono"),
    ("[A]Julia", "actress/julia"),
    # 系列
    ("[S]Acrobatic Sex", "series/sex"),
    ("[S]Amateur AV Interview", "series/av"),
    ("[S]Luxury TV", "series/tv"),
    ("[S]AV Debut (Kimihore)", "series/av-debut"),
    ("[S]Tokyo-Hot", "series/tokyo-hot"),
    ("[S]Magic Mirror", "series/58b73f0b7a"),
    ("[S]Sod Female Employee", "series/sod"),
    ("[S]Luxury OL", "series/ol"),
    ("[S]Kawaii Orgy", "series/kawaii"),
    ("[S]Exclusive No.1 Style", "series/no1-style"),
    ("[S]NTR", "series/ntr"),
    # 类型（top 30 by 数量）
    ("[G]Solowork", "genre/solowork"),
    ("[G]Creampie", "genre/creampie"),
    ("[G]Big Boobs", "genre/big-tits"),
    ("[G]Married/Housewife", "genre/married-womanhousewife"),
    ("[G]Amateur", "genre/amateur"),
    ("[G]High Vision", "genre/high-vision"),
    ("[G]Blowjob", "genre/e22f5b4c15"),
    ("[G]Beautiful Girl", "genre/beautiful-girl"),
    ("[G]Beautiful Breasts", "genre/beautiful-breasts"),
    ("[G]Slender", "genre/slender"),
    ("[G]Gonzo", "genre/gonzo"),
    ("[G]Slut", "genre/slut"),
    ("[G]3P/4P", "genre/threesome-foursome"),
    ("[G]Squirting", "genre/squirting"),
    ("[G]Cuckold/NTR", "genre/cuckold-cuckolded-ntr"),
    ("[G]Exclusive", "genre/exclusive"),
    ("[G]4 Hours Or More", "genre/over-4-hours"),
    ("[G]Titjob", "genre/paizuri"),
    ("[G]Cowgirl", "genre/cowgirl"),
    ("[G]Facial", "genre/facial"),
    ("[G]Schoolgirl", "genre/schoolgirl"),
    ("[G]Older Sister", "genre/older-sister"),
    ("[G]Handjob", "genre/handjob"),
    ("[G]Big Ass", "genre/big-ass"),
    ("[G]Masturbation", "genre/masturbation"),
    ("[G]Affair", "genre/adultery"),
    ("[G]Pick-Up", "genre/nampa"),
    ("[G]Incest", "genre/incest"),
    ("[G]Cosplay", "genre/7889ef8307"),
    ("[G]Bareback", "genre/bareback"),
]


class Spider(BaseSpider):

    def __init__(self):
        super().__init__()
        self.hosts = list(HOSTS)
        self.host = self.hosts[0]
        self.name = NAME
        self._cache = {}
        self._lock = threading.Lock()

    def init(self, extend=""):
        cfg = {}
        if isinstance(extend, dict):
            cfg = extend
        elif extend:
            try:
                cfg = json.loads(extend)
            except Exception:
                cfg = {}
        if isinstance(cfg, dict):
            site = (cfg.get("site") or cfg.get("url") or "").strip().rstrip("/")
            if site:
                with self._lock:
                    self.hosts = [site] + [h for h in self.hosts if h != site]
                    self.host = self.hosts[0]
        self.options = cfg if isinstance(cfg, dict) else {}

    def getDependence(self):
        return []

    def destroy(self):
        with self._lock:
            self._cache.clear()
        self.options = {}

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4|flv|mkv|ts)(\?|/|$)", str(url)))

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return {"msg": "不支持此操作"}

    def homeContent(self, filter):
        classes = [{"type_id": tid, "type_name": name} for name, tid in CATS]
        items = self._fetch_list(self._cat_path("new", 1, {}))
        result = {
            "class": classes,
            "list": [self._vod(x) for x in items],
        }
        if filter:
            sort_filter = {
                "key": "sort", "name": "排序", "init": "release_date",
                "value": [
                    {"n": "发行日期", "v": "release_date"},
                    {"n": "最近收录", "v": "recent"},
                    {"n": "热门", "v": "hot"},
                    {"n": "今日浏览", "v": "today"},
                    {"n": "本周浏览", "v": "week"},
                    {"n": "本月浏览", "v": "month"},
                    {"n": "最多浏览", "v": "views"},
                    {"n": "最多收藏", "v": "follows"},
                    {"n": "最长", "v": "longest"},
                ],
            }
            result["filters"] = {c["type_id"]: [sort_filter] for c in classes}
        return result

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        tid = str(tid or "").strip()
        # 演员/导演点击 → 本站搜索（FongMi 把 BBCode id 原样传回作 tid）
        if tid.startswith("actor/") or tid.startswith("director/"):
            name = unquote(tid.split("/", 1)[1])
            items = self._fetch_search(name, pg)
        else:
            items = self._fetch_list(self._cat_path(tid, pg, extend or {}))
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": pg if len(items) < PAGE_SIZE else 9999,
        }

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        responses = [self._detail(str(video_id)) for video_id in ids]
        merged = {k: v for k, v in (responses[0] or {}).items() if k != "list"} if responses[0] else {}
        merged["list"] = [item for response in responses if response for item in (response.get("list") or [])]
        return merged

    def _detail(self, vid):
        vid = str(vid or "").strip()
        if vid.startswith("http"):
            vid = vid.rstrip("/").rsplit("/", 1)[-1]
        html = self._fetch("/en/v/" + quote(vid))
        if not html:
            return {"list": [], "msg": "获取详情失败"}
        m = re.search(r'<h1 class="watch__title">([\s\S]*?)</h1>', html)
        name = self._clean(m.group(1)) if m else vid
        pic = ""
        m = re.search(r"background-image:url\('([^']+)'\)", html)
        if m and "cover" in m.group(1):
            pic = m.group(1)
        if not pic:
            m = re.search(r'data-preview="([^"]+)"', html)
            if m:
                pic = m.group(1)
        info = {}
        for mm in ROW_RE.finditer(html):
            k = mm.group(1).strip()
            if k and k not in info:
                info[k] = mm.group(2)
        code = self._clean(info.get("Code", ""))
        release = self._clean(info.get("Release date", ""))
        duration = self._clean(info.get("Duration", ""))
        mtype = self._clean(info.get("Type", ""))
        maker = self._clean(info.get("Maker", ""))
        genres = self._clean(info.get("Genres", ""))
        tags = self._clean(info.get("Tags", ""))
        actors = []
        for mm in re.finditer(r'<a class="chip"[^>]*>([^<]+)</a>', info.get("Cast", "")):
            a = self._clean(mm.group(1))
            if a and a not in actors:
                actors.append(a)
        # 分集（每集一个嵌入页 URL，无 token，稳定）
        episodes = self._parse_episodes(html)
        plays = []
        for i, (nm, embed) in enumerate(episodes, 1):
            nm = str(nm or i).replace("$", " ").replace("#", " ")
            plays.append("%s$%s" % (nm, embed))
        if not plays:
            plays = ["正片$"]
        vod = {
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": pic,
            "type_name": mtype,
            "vod_year": (release.split("-")[0] if "-" in release else ""),
            "vod_remarks": duration,
            "vod_actor": "、".join([self._clickable("actor", a) for a in actors]),
            "vod_content": self._content(code, mtype, release, duration, maker, genres, tags),
            "vod_play_from": NAME,
            "vod_play_url": "#".join(plays),
        }
        return {"list": [vod]}

    def searchContent(self, key, quick, pg="1"):
        pg = self._int(pg, 1)
        key = str(key or "").strip()
        items = self._fetch_search(key, pg)
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": pg if len(items) < PAGE_SIZE else 9999,
        }

    def playerContent(self, flag, id, vipFlags):
        embed = str(id or "").strip()
        m = re.search(r"/e/([A-Za-z0-9_]+)", embed)
        hid = m.group(1) if m else embed
        url = ""
        try:
            txt = self._fetch_raw(EMBED_HOST + "/stream?id=" + quote(hid))
            d = json.loads(txt)
            url = ((d.get("media") or {}).get("stream")) or ""
        except Exception:
            url = ""
        if not url:
            return {"parse": 0, "msg": "未找到播放地址"}
        return {
            "parse": 0,
            "jx": 0,
            "url": url,
            "format": "application/x-mpegURL",
            "header": {"User-Agent": UA, "Referer": EMBED_HOST + "/"},
        }

    def liveContent(self, url):
        return "[]"

    # ================= 内部工具 =================
    def _cat_path(self, tid, pg, extend=None):
        tid = str(tid or "").strip()
        extend = extend or {}
        if tid.startswith("genre/"):
            path = "/en/genres/" + tid[len("genre/"):]
        elif tid.startswith("actress/"):
            path = "/en/actresses/" + tid[len("actress/"):]
        elif tid.startswith("maker/"):
            path = "/en/makers/" + tid[len("maker/"):]
        elif tid.startswith("series/"):
            path = "/en/series/" + tid[len("series/"):]
        elif tid.startswith("tag/"):
            path = "/en/tags/" + tid[len("tag/"):]
        elif tid in ("today", "week", "month"):
            path = "/en/all?sort=%s" % tid
        else:
            path = "/en/" + tid
            sort = str(extend.get("sort") or "").strip()
            if sort and sort != "release_date":
                path += "?sort=" + quote(sort)
        if pg and int(pg) > 1:
            sep = "&" if "?" in path else "?"
            path += "%spage=%d" % (sep, int(pg))
        return path

    def _fetch(self, path, referer=None):
        txt = self._fetch_raw(self._abs(path), referer)
        return txt

    def _abs(self, path):
        path = str(path)
        if path.startswith("http"):
            return path
        return self.host + "/" + path.lstrip("/")

    def _fetch_raw(self, url, referer=None):
        ck = url + (referer or "")
        hit = self._cache.get(ck)
        if hit and time.time() - hit[1] < CACHE_TTL:
            return hit[0]
        h = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9"}
        if referer:
            h["Referer"] = referer
        data = ""
        # 宿主注入 self.net: 用它
        if getattr(self, "net", None) is not None:
            try:
                resp = self.net.req(url, {"headers": h, "timeout": 15000})
                if not resp.get("error") and 200 <= (resp.get("code") or 0) < 300:
                    data = resp.get("content", "")
            except Exception:
                data = ""
        # 回退 urllib (其他播放器无 self.net 时可用)
        if not data:
            try:
                import urllib.request, ssl
                ctx = ssl._create_unverified_context()
                req = urllib.request.Request(url, headers=h)
                with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
                    raw = r.read()
                    enc = r.headers.get("Content-Encoding", "")
                    if "gzip" in enc:
                        import gzip
                        raw = gzip.decompress(raw)
                    data = raw.decode("utf-8", "ignore")
            except Exception:
                data = ""
        if data:
            self._cache[ck] = (data, time.time())
        return data

    def _fetch_list(self, path):
        html = self._fetch(path, referer=self.host + "/")
        return self._parse_cards(html)

    def _fetch_search(self, key, pg):
        if not key:
            return []
        path = "/en/search?keyword=" + quote(key)
        if pg and int(pg) > 1:
            path += "&page=%d" % int(pg)
        return self._parse_cards(self._fetch(path, referer=self.host + "/"))

    def _parse_cards(self, html):
        items = []
        if not html:
            return items
        titles = {}
        for m in TITLE_RE.finditer(html):
            titles[m.group(1)] = self._clean(m.group(2))
        seen = set()
        for m in CARD_RE.finditer(html):
            code = m.group(1)
            if not code or code in seen:
                continue
            seen.add(code)
            items.append({
                "id": code,
                "name": titles.get(code) or code,
                "pic": m.group(2),
                "remarks": m.group(3).strip(),
            })
            if len(items) >= 60:
                break
        if DEBUG:
            print("[123av] parsed %d cards" % len(items))
        return items

    def _parse_episodes(self, html):
        eps = []
        m = EP_RE.search(html)
        if not m:
            return eps
        raw = m.group(1)
        try:
            s = json.loads('"' + raw + '"')
            data = json.loads(s)
        except Exception:
            return eps
        if not isinstance(data, list):
            return eps
        for i, e in enumerate(data, 1):
            url = e.get("url") or ""
            if not url:
                continue
            nm = str(e.get("name") or i)
            hm = re.search(r"https?://[^\"'?\s]+?/e/[A-Za-z0-9_]+", url)
            base = hm.group(0) if hm else url
            eps.append((nm, base))
        return eps

    def _vod(self, item):
        item = item or {}
        return {
            "vod_id": item.get("id") or "",
            "vod_name": item.get("name") or item.get("id") or "",
            "vod_pic": item.get("pic") or "",
            "vod_remarks": item.get("remarks") or "",
        }

    def _clickable(self, kind, name):
        if not name:
            return ""
        try:
            payload = json.dumps(
                {"id": kind + "/" + quote(name), "name": name, "type_flag": "0"},
                ensure_ascii=False)
            return "[a=cr:%s/]%s[/a]" % (payload, name)
        except Exception:
            return name

    def _clean(self, s):
        if not s:
            return ""
        import html as _h
        s = re.sub(r"<[^>]+>", "", str(s))
        s = _h.unescape(s)
        return re.sub(r"\s+", " ", s).strip()

    def _content(self, code, mtype, release, duration, maker, genres, tags):
        lines = []
        if code:
            lines.append("番号:" + code)
        if mtype:
            lines.append("类型:" + mtype)
        if release:
            lines.append("发行日期:" + release)
        if duration:
            lines.append("时长:" + duration)
        if maker:
            lines.append("制作商:" + maker)
        if genres:
            lines.append("类型标签:" + genres)
        if tags:
            lines.append("标签:" + tags)
        return "\n".join(lines)

    def _int(self, x, d=0):
        try:
            return int(x)
        except Exception:
            return d
