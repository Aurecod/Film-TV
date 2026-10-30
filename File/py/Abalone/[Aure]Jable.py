# -*- coding: utf-8 -*-
"""
Jable (jable.my / jable666.net) — FongMi py spider
站点：jable 系成人站镜像（免 Cloudflare，py 路线可直连）。
官方域名 jable.tv 有 CF 保护，需用同目录 jar/JableTv.jar（WebView 路线）。

结构（2026-10-28 逆向，jable.my 验证）：
  列表   /latest-updates/<page>/  /hot/<page>/  /tags/<slug>/<page>/
        卡片 = div.col-6 > div.video-img-box：<a href=.../videos/<code>/> +
        <img data-src=封面> + span.label(时长) + h6.title(标题)
  详情   /videos/<code>/  —— 播放地址在 <script>var hlsUrl='<m3u8>';</script>
        hlsUrl 含短时效 token（约 3h），每次播放重取详情页拿新鲜地址
  搜索   /search/<kw>/    —— 仅第 1 页有效（站点分页为会话机制）
  播放   m3u8 CDN 免鉴权直连，parse=0
"""

import sys
import re
import json
import threading
from urllib.parse import quote

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        def homeContent(self, filter):
                return {"class": []}
        def homeVideoContent(self):
                return {"list": []}
        def categoryContent(self, tid, pg, filter, extend):
                return {"list": []}
        def detailContent(self, ids):
                return {"list": []}
        def searchContent(self, key, quick, pg="1"):
                return {"list": []}
        def playerContent(self, flag, id, vipFlags):
                return {}
        def liveContent(self, url):
                return ""
        def proxy(self, params):
                return [404, "text/plain", ""]
        def localProxy(self, params):
                return [404, "text/plain", ""]
        def isVideoFormat(self, url):
                return False
        def manualVideoCheck(self):
                return False
        def action(self, action):
                return {}
        def getDependence(self):
                return []

NAME = "Jable"
HOSTS = ["https://jable.my", "https://jable666.net"]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
DEBUG = False
STYLE = {"type": "rect", "ratio": 1.33}
PAGE_SIZE = 24

CARD_RE = re.compile(
    r'<a href="(https?://[^"]*/videos/([^"]+?)/)"[^>]*>\s*'
    r'<img[^>]*data-src="([^"]+)"[\s\S]*?'
    r'<span class="label">([^<]*)</span>[\s\S]*?'
    r'<h6 class="title"><a href="[^"]*">([\s\S]*?)</a></h6>'
)

# 分类表：{type_name, type_id}。type_id 直接拼进 /<tid>/<page>/。
CATS = [
    ("最近更新", "latest-updates"),
    ("热门影片", "hot"),
    ("和服", "tags/kimono"),
    ("兽耳", "tags/kemonomimi"),
    ("肉丝", "tags/flesh-toned-pantyhose"),
    ("兔女郎", "tags/bunny-girl"),
    ("黑丝", "tags/black-pantyhose"),
    ("丝袜", "tags/pantyhose"),
    ("过膝袜", "tags/knee-socks"),
    ("眼镜娘", "tags/glasses"),
    ("水着", "tags/swimsuit"),
    ("校服", "tags/school-uniform"),
    ("运动装", "tags/sportswear"),
    ("Cosplay", "tags/Cosplay"),
    ("吊带袜", "tags/stockings"),
    ("渔网", "tags/fishnets"),
    ("婚纱", "tags/wedding-dress"),
    ("女仆", "tags/maid"),
    ("旗袍", "tags/cheongsam"),
    ("贫乳", "tags/small-tits"),
    ("白虎", "tags/hairless-pussy"),
    ("娇小", "tags/dainty"),
    ("纹身", "tags/tattoo"),
    ("熟女", "tags/mature-woman"),
    ("软体", "tags/flexible-body"),
    ("美尻", "tags/beautiful-butt"),
    ("美腿", "tags/beautiful-leg"),
    ("短发", "tags/short-hair"),
    ("黑肉", "tags/suntan"),
    ("长身", "tags/tall"),
    ("少女", "tags/girl"),
    ("巨乳", "tags/big-tits"),
    ("中出", "tags/creampie"),
    ("肛交", "tags/anal-sex"),
    ("深喉", "tags/deep-throat"),
    ("口交", "tags/blowjob"),
    ("接吻", "tags/kiss"),
    ("脚交", "tags/footjob"),
    ("痉挛", "tags/spasms"),
    ("潮吹", "tags/squirting"),
    ("口爆", "tags/cum-in-mouth"),
    ("颜射", "tags/facial"),
    ("乳交", "tags/tit-wank"),
    ("泡姬", "tags/soapland"),
    ("多P", "tags/groupsex"),
    ("母乳", "tags/breast-milk"),
    ("痴汉", "tags/chikan"),
    ("痴女", "tags/chizyo"),
    ("按摩", "tags/massage"),
    ("放尿", "tags/piss"),
    ("集团进犯", "tags/gang-intrusion"),
    ("进犯", "tags/intrusion"),
    ("3P", "tags/3p"),
    ("捆绑", "tags/bondage"),
    ("一日十回", "tags/10-times-a-day"),
    ("凌辱", "tags/insult"),
    ("男M", "tags/masochism-guy"),
    ("露出", "tags/outdoor"),
    ("泥醉", "tags/crapulence"),
    ("瞬间插入", "tags/quickie"),
    ("刑具", "tags/grip"),
    ("调教", "tags/tune"),
    ("黑人", "tags/black"),
    ("夫目前犯", "tags/sex-beside-husband"),
    ("丑男", "tags/ugly-man"),
    ("年龄差", "tags/age-difference"),
    ("亲属", "tags/kinship"),
    ("催眠", "tags/hypnosis"),
    ("复仇", "tags/avenge"),
    ("媚药", "tags/love-potion"),
    ("巨汉", "tags/giant"),
    ("时间停止", "tags/time-stop"),
    ("童贞", "tags/virginity"),
    ("出轨", "tags/affair"),
    ("NTR", "tags/ntr"),
    ("偷拍", "tags/private-cam"),
    ("下雨天", "tags/rainy-day"),
    ("诱惑", "tags/temptation"),
    ("球队经理", "tags/team-manager"),
    ("家庭教师", "tags/private-teacher"),
    ("风俗娘", "tags/club-hostess-and-sex-worker"),
    ("OL", "tags/ol"),
    ("家政妇", "tags/housewife"),
    ("人妻", "tags/wife"),
    ("偶像", "tags/idol"),
    ("空姐", "tags/flight-attendant"),
    ("护士", "tags/nurse"),
    ("主播", "tags/female-anchor"),
    ("医生", "tags/doctor"),
    ("情侣", "tags/couple"),
    ("搜查官", "tags/detective"),
    ("逃犯", "tags/fugitive"),
    ("老师", "tags/teacher"),
    ("未亡人", "tags/widow"),
    ("便利店", "tags/store"),
    ("图书馆", "tags/library"),
    ("学校", "tags/school"),
    ("监狱", "tags/prison"),
    ("洗浴场", "tags/bathing-place"),
    ("汽车", "tags/car"),
    ("温泉", "tags/hot-spring"),
    ("泳池", "tags/swimming-pool"),
    ("健身房", "tags/gym-room"),
    ("厕所", "tags/toilet"),
    ("电车", "tags/tram"),
    ("魔镜号", "tags/magic-mirror"),
    ("处女", "tags/first-night"),
    ("节日主题", "tags/festival"),
    ("4小时以上", "tags/more-than-4-hours"),
    ("感谢祭", "tags/thanksgiving"),
    ("综艺", "tags/variety-show"),
    ("录像", "tags/video-recording"),
    ("处女作/引退作", "tags/debut-retires"),
]

# ---- v2.0 迁移: requests.Session -> self.net 兼容适配器 (内联) ----
class _NetResp(object):
    """模拟 requests.Response: 基于 self.net.req 或 urllib 返回的 dict。"""
    def __init__(self, resp_dict, url):
        self._d = resp_dict or {}
        self.url = url
        self.status_code = int(self._d.get("code") or 0)
        self._content = self._d.get("content", "")
        self.headers = self._d.get("headers") or {}
        self.encoding = None
        self.apparent_encoding = "utf-8"
        self.text = self._content if isinstance(self._content, str) else ""
        if not self.text and isinstance(self._content, (bytes, bytearray)):
            self.text = bytes(self._content).decode("utf-8", "ignore")
    @property
    def content(self):
        return self._content if isinstance(self._content, (bytes, bytearray)) else self.text.encode("utf-8", "ignore")
    def json(self):
        import json as _json
        return _json.loads(self.text)
    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception("HTTP %s" % self.status_code)
    def __repr__(self):
        return "<_NetResp %s %d>" % (self.url, self.status_code)

class _NetSession(object):
    """requests.Session 兼容层: 优先宿主注入 self.net, 无则 urllib 直连(标准库, 任何播放器可跑)。"""
    def __init__(self, net, headers=None, default_headers=None):
        self.net = net
        self.headers = headers if headers is not None else {}
        if default_headers:
            for k, v in default_headers.items():
                self.headers.setdefault(k, v)
    def _merge(self, headers):
        h = dict(self.headers)
        if headers:
            for k, v in headers.items():
                h[k] = v
        return h
    @staticmethod
    def _build_url(url, params):
        if not params:
            return url
        import urllib.parse as _up
        sep = "&" if "?" in url else "?"
        return url + sep + _up.urlencode(params)
    def _urllib_get(self, full, headers, timeout):
        import urllib.request as _ur, ssl as _ssl
        try:
            ctx = _ssl._create_unverified_context()
        except Exception:
            ctx = None
        req = _ur.Request(full, headers=headers)
        with _ur.urlopen(req, timeout=timeout or 15, context=ctx) as resp:
            raw = resp.read()
            enc = resp.headers.get("Content-Encoding", "")
            if "gzip" in enc:
                import gzip as _g
                raw = _g.decompress(raw)
            return {"code": resp.status, "content": raw, "headers": dict(resp.headers), "error": ""}
    def _urllib_post(self, full, headers, data, timeout):
        import urllib.request as _ur, urllib.parse as _up, ssl as _ssl
        try:
            ctx = _ssl._create_unverified_context()
        except Exception:
            ctx = None
        body = _up.urlencode(data or {}).encode("utf-8")
        req = _ur.Request(full, data=body, headers=headers, method="POST")
        with _ur.urlopen(req, timeout=timeout or 15, context=ctx) as resp:
            raw = resp.read()
            return {"code": resp.status, "content": raw, "headers": dict(resp.headers), "error": ""}
    def get(self, url, params=None, headers=None, timeout=None, **kw):
        h = self._merge(headers)
        full = self._build_url(url, params)
        timeout_s = None
        if timeout:
            timeout_s = int(timeout) / 1000 if timeout > 100 else int(timeout)
        if self.net is not None:
            opts = {"headers": h}
            if timeout_s:
                opts["timeout"] = int(timeout_s * 1000)
            try:
                resp = self.net.req(full, opts)
                return _NetResp(resp, full)
            except Exception:
                pass
        try:
            return _NetResp(self._urllib_get(full, h, timeout_s), full)
        except Exception as e:
            return _NetResp({"code": 0, "content": b"", "headers": {}, "error": str(e)}, full)
    def post(self, url, data=None, params=None, headers=None, timeout=None, **kw):
        h = self._merge(headers)
        full = self._build_url(url, params)
        timeout_s = None
        if timeout:
            timeout_s = int(timeout) / 1000 if timeout > 100 else int(timeout)
        if self.net is not None:
            opts = {"method": "POST", "headers": h, "postType": "form", "data": data or {}}
            if timeout_s:
                opts["timeout"] = int(timeout_s * 1000)
            try:
                resp = self.net.req(full, opts)
                return _NetResp(resp, full)
            except Exception:
                pass
        try:
            return _NetResp(self._urllib_post(full, h, data or {}, timeout_s), full)
        except Exception as e:
            return _NetResp({"code": 0, "content": b"", "headers": {}, "error": str(e)}, full)

class Spider(BaseSpider):

    def __init__(self):
        super().__init__()
        self.hosts = list(HOSTS)
        self.host = self.hosts[0]
        self.name = NAME
        self.session = None
        self._good_host = None
        self._cards_cache = {}
        self._lock = threading.Lock()

    def init(self, extend=""):
        self.session = _NetSession(getattr(self, 'net', None))
        self.session.headers.update({"User-Agent": UA, "Accept": "*/*"})
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
                    self._good_host = site
        self.options = cfg if isinstance(cfg, dict) else {}

    def getDependence(self):
        return []

    def destroy(self):
        with self._lock:
            self._cards_cache.clear()
        self.options = {}

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4|flv|mkv|ts)(\?|/|$)", str(url)))

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return {"msg": "不支持此操作"}

    def homeContent(self, filter):
        classes = [{"type_id": tid, "type_name": name} for name, tid in CATS]
        result = {"class": classes}
        if filter:
            sort_filter = {
                "key": "sort_by", "name": "排序", "init": "post_date",
                "value": [
                    {"n": "时间", "v": "post_date"},
                    {"n": "热度", "v": "post_date_and_popularity"},
                    {"n": "浏览", "v": "video_viewed"},
                    {"n": "收藏", "v": "most_favourited"},
                ],
            }
            result["filters"] = {c["type_id"]: [sort_filter] for c in classes}
        items = self._fetch_list("latest-updates", 1, {})
        result["list"] = [self._vod(x) for x in items]
        return result

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        tid = str(tid or "").strip()
        # 演员可点击（BBCode [a=cr:...]），点击后 FongMi 把 id 作为 tid 传回
        if tid.startswith("actor/"):
            from urllib.parse import unquote
            name = unquote(tid[len("actor/"):])
            items = self._fetch_search(name, pg)
        else:
            items = self._fetch_list(tid, pg, extend or {})
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
        html = self._get("/videos/%s/" % quote(vid))
        if not html:
            return {"list": [], "msg": "获取详情失败"}
        m = re.search(r'<h4>([^<]+)</h4>', html)
        name = m.group(1).strip() if m else vid
        m = (re.search(r'property="og:image" content="([^"]+)"', html)
             or re.search(r'poster="([^"]+)"', html))
        pic = m.group(1) if m else ""
        m = re.search(r'<span class="mr-3">([^<]*(?:前|ago)[^<]*)</span>', html)
        remarks = m.group(1).strip() if m else ""
        m = re.search(r'class="text-info fs-1 mr-2">[^<]*</span>([^<]+)<', html)
        cat = m.group(1).strip() if m else ""
        actors = []
        for mm in re.finditer(r'<a class="model"[^>]*>[\s\S]*?title="([^"]+)"', html):
            a = mm.group(1).strip()
            if a and a not in actors:
                actors.append(a)
        m = re.search(r'<span class="label">([0-9:]+)</span>', html)
        duration = m.group(1) if m else ""
        content = "番号:%s  时长:%s" % (vid, duration)
        vod = {
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": pic,
            "type_name": cat,
            "vod_remarks": remarks,
            "vod_actor": "、".join([self._clickable(a) for a in actors]),
            "vod_content": content,
            "vod_play_from": "Jable",
            "vod_play_url": "正片$" + vid,
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
        vid = str(id or "").strip()
        page_url = self.host + "/videos/" + quote(vid) + "/"
        # hlsUrl 含短时效 token（约 3h），必须重新取详情页拿新鲜地址
        html = self._get("/videos/%s/" % quote(vid), referer=self.host + "/")
        m = (re.search(r"hlsUrl\s*=\s*'([^']+)'", html or "")
             or re.search(r'hlsUrl\s*=\s*"([^"]+)"', html or ""))
        if not m:
            return {"parse": 0, "msg": "未找到播放地址"}
        return {
            "parse": 0,
            "jx": 0,
            "url": m.group(1),
            "format": "application/x-mpegURL",
            "header": {"User-Agent": UA, "Referer": page_url},
        }

    def liveContent(self, url):
        return "[]"

    def _get(self, path, referer=None):
        path = "/" + str(path).lstrip("/")
        hosts = list(self.hosts)
        if self._good_host in hosts:
            hosts.remove(self._good_host)
            hosts.insert(0, self._good_host)
        for h in hosts:
            try:
                hdr = {"Referer": referer or (h + "/")}
                r = self.session.get(h + path, headers=hdr, timeout=12)
                if r.status_code == 200 and len(r.text) > 2000:
                    r.encoding = "utf-8"
                    self._good_host = h
                    if DEBUG:
                        print("[jable] GET %s%s -> %d" % (h, path, len(r.text)))
                    return r.text
            except Exception as e:
                if DEBUG:
                    print("[jable] GET fail %s%s: %s" % (h, path, e))
                continue
        return ""

    def _fetch_list(self, tid, pg, extend):
        tid = str(tid or "latest-updates").strip().strip("/")
        sort_by = str((extend or {}).get("sort_by") or "").strip()
        if sort_by not in ("post_date", "post_date_and_popularity",
                           "video_viewed", "most_favourited"):
            sort_by = "post_date"
        if pg <= 1:
            path = "/%s/?sort_by=%s" % (tid, sort_by)
        else:
            path = "/%s/%d/?sort_by=%s" % (tid, pg, sort_by)
        html = self._get(path)
        if html and ("video-img-box" not in html) and pg <= 1:
            html = self._get("/%s/1/?sort_by=%s" % (tid, sort_by))
        return self._parse_cards(html)

    def _fetch_search(self, key, pg):
        if not key:
            return []
        if pg <= 1:
            path = "/search/%s/" % quote(key)
        else:
            path = "/search/%s/%d/" % (quote(key), pg)
        return self._parse_cards(self._get(path))

    def _parse_cards(self, html):
        items = []
        if not html:
            return items
        seen = set()
        for m in CARD_RE.finditer(html):
            url, vid, pic, dur, title = (m.group(1), m.group(2), m.group(3),
                                         m.group(4).strip(), m.group(5).strip())
            if not vid or vid in seen:
                continue
            seen.add(vid)
            items.append({"id": vid, "name": title, "pic": pic, "remarks": dur})
            if len(items) >= 48:
                break
        if DEBUG:
            print("[jable] parsed %d cards" % len(items))
        return items

    def _vod(self, item):
        return {
            "vod_id": item.get("id") or "",
            "vod_name": item.get("name") or item.get("id") or "",
            "vod_pic": item.get("pic") or "",
            "vod_remarks": item.get("remarks") or "",
        }

    def _clickable(self, name):
        """FongMi 可点击 BBCode：点击后调用 categoryContent(id, ...)。"""
        if not name:
            return ""
        try:
            payload = json.dumps(
                {"id": "actor/" + quote(name), "name": name, "type_flag": "0"},
                ensure_ascii=False)
            return "[a=cr:%s/]%s[/a]" % (payload, name)
        except Exception:
            return name

    def _int(self, x, d=0):
        try:
            return int(x)
        except Exception:
            return d
