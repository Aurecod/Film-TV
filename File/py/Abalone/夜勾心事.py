# -*- coding: utf-8 -*-
"""
心事影视 爬虫  ——  适配 影视仓 / OK影视 / TVBox 等空壳影视 APP（py 接口）

站点：https://moj.ygxs.lol/    （MacCMS10 内核，模板 x016）
规范：CatVod/hipy 风格 py 蜘蛛，类名 Spider，推荐文件名 XinShi.py（对应 api: csp_XinShi）

实现功能
  1) 分类：父分类（10 组）+ 子分类（站点 81 个 type）+ 站点自带"全部/筛选"根分类
  2) 分页：type/id/{tid}/page/{n}.html，支持与筛选条件组合
  3) 详情：片名 / 封面 / 类型 / 标签 / 年代 / 简介 / 播放线路
  4) 播放：解析播放页 player_aaaa 里的直连 m3u8（parse=0，无需解析接口）
  5) 搜索：/index.php/vod/search.html?wd=关键词&page=n
  6) 封面：直接取详情/列表页图片地址（外链图床，无需 referer）
  7) 完整筛选器：子分类 / 年代 / 字母 / 排序（by=time|hits|score）

站点可用的筛选 URL 语法（实测）
  /index.php/vod/type/id/{tid}/page/{pg}.html
  /index.php/vod/type/id/{tid}/year/{year}/page/{pg}.html
  /index.php/vod/type/id/{tid}/letter/{A}/page/{pg}.html
  /index.php/vod/type/id/{tid}/by/{hits}/page/{pg}.html
  /index.php/vod/type/id/{tid}/year/{year}/letter/{A}/by/{hits}/page/{pg}.html   (可叠加)
  /index.php/vod/search.html?wd={kw}&page={pg}
  /index.php/vod/search/class/{标签}/page/{pg}.html          (全局标签筛选)
  /index.php/vod/search/year/{year}/page/{pg}.html           (全局年代筛选)

本地自测：python3 XinShi.py test
"""

import json
import re
import time
from urllib.parse import quote, unquote, urljoin

# ---------------------------------------------------------------- 基类兼容
try:                                                            # 在影视壳 py 环境里
    from base.spider import Spider as _BaseSpider
except Exception:                                               # 本地自测时
    class _BaseSpider(object):
        def init(self, extend=""):
            pass

        def getDependence(self):
            return []

        def isVideoFormat(self, url):
            return False

        def manualVideoCheck(self):
            return False

        def destroy(self):
            pass

        def getName(self):
            return "XinShi"


try:
    import requests
except Exception:
    requests = None

try:
    import urllib3
    urllib3.disable_warnings()
except Exception:
    pass


# ---------------------------------------------------------------- 配置区
class _Cfg(object):
    HOST = "https://moj.ygxs.lol"
    UA = ("Mozilla/5.0 (Linux; Android 12; Pixel 5) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")
    TIMEOUT = 15
    RETRY = 2
    # 列表页每页条数（站点实际值 18~24，用页面里的"共X条/共Y页"反推）
    DEFAULT_LIMIT = 24
    # True = 详情阶段就把真实 m3u8 抓出来（慢、请求多）
    # False = 播放在 playerContent 里懒解析（推荐，列表/详情更快）
    EAGER_RESOLVE = False
    # 父分类分组模式下，"全部"子项合并抓取的最大并发
    THREADS = 8


# 父分类（站点导航本身是扁平的 81 个子分类，这里按站点导航顺序做语义分组，
# 想改分组直接改这个表即可）
PARENT_GROUPS = [
    ("g_guochan", "国产自拍", [20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35]),
    ("g_men", "门事件黑料", [36, 37, 38, 39, 40, 41, 42, 43]),
    ("g_zhifu", "制服诱惑", [44, 45, 46, 47, 48, 49, 50, 51]),
    ("g_lunli", "伦理片", [52, 53, 54, 55, 56, 57, 58, 59, 60]),
    ("g_zhibo", "直播专区", [61, 62, 63, 64, 65, 66, 71, 98]),
    ("g_gcav", "国产AV主播", [67, 68, 72]),
    ("g_oumei", "欧美专区", [69, 70, 73, 74, 75, 78]),
    ("g_zhongkou", "重口区", [76, 77, 79, 80, 81, 82]),
    ("g_dongman", "动漫专区", [83, 84, 85, 86, 87, 88, 89, 90]),
    ("g_riben", "日本AV", [91, 92, 93, 94, 95, 96, 97, 99, 100]),
]

# 子分类表（tid -> 名称），首次运行会从站点导航自动抓取刷新
CHILD_TYPES = {
    20: "学生少女", 21: "技师风采", 22: "熟女少妇", 23: "国产热播", 24: "反差母狗",
    25: "美脚丝足", 26: "情侣自拍", 27: "私房俱乐部", 28: "偷情约炮", 29: "真实偷拍",
    30: "高潮喷水", 31: "强奸迷奸", 32: "户外露出", 33: "SM调教", 34: "情趣内衣",
    35: "精选探花", 36: "网曝门事件", 37: "校园猛料", 38: "网红流出", 39: "明星黑料",
    40: "裸贷肉偿", 41: "婚闹恶俗", 42: "抓奸名场面", 43: "男同女同", 44: "JK少女",
    45: "黑丝白丝", 46: "女仆", 47: "cosplay", 48: "OL制服", 49: "旗袍",
    50: "空姐制服", 51: "护士医生", 52: "伦理之爱", 53: "禁忌母子", 54: "兄弟姐妹",
    55: "爱上嫂子", 56: "狂操小姨", 57: "换夫换妻", 58: "淫荡儿媳", 59: "爷爷奶奶",
    60: "伦理精选", 61: "啪啪直播", 62: "学生直播", 63: "自慰诱惑", 64: "乱伦直播",
    65: "户外勾搭", 66: "车震直播", 67: "国产AV", 68: "网红主播", 69: "欧美精选",
    70: "户外搭讪", 71: "美女自慰", 72: "乱伦直播②", 73: "黑人大屌", 74: "群P大作战",
    75: "欧美重口", 76: "人兽性交", 77: "SM性虐", 78: "人妖伪娘", 79: "孕妇内射",
    80: "吃屎喝尿", 81: "扩阴拳交", 82: "阳具巨物", 83: "3D动漫", 84: "同人动漫",
    85: "剧情故事", 86: "国产动漫", 87: "日韩动漫", 88: "欧美动漫", 89: "港台动漫",
    90: "海外动漫", 91: "日本中文", 92: "无码流出", 93: "FC2", 94: "HEYZO",
    95: "东京热", 96: "一本道", 97: "人妻斩", 98: "主播网黄", 99: "色情综艺",
    100: "情色AV",
}

TYPE_TO_GROUP = {}
for _gid, _gname, _tids in PARENT_GROUPS:
    for _t in _tids:
        TYPE_TO_GROUP[_t] = _gid

YEARS = ["全部"] + [str(y) for y in range(2026, 2014, -1)]
LETTERS = ["全部"] + list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
SORTS = [("time", "最新"), ("hits", "最热"), ("score", "评分")]
# 站点根分类（聚合全部影片，自带 year/letter/by 筛选）
ROOT_TID = "19"

# ---------------------------------------------------------------- 正则
RE_ITEM = re.compile(
    r'<a[^>]+href="(?P<href>/index\.php/vod/detail/id/(?P<vid>\d+)\.html)"(?P<attrs>[^>]*)>'
    r'(?P<inner>[\s\S]*?)</a>', re.S)
RE_PAGE = re.compile(r'共(\d+)条数据[，,]?\s*当前(\d+)/(\d+)页')
RE_PAGE2 = re.compile(r'共(\d+)页')
RE_PLAY = re.compile(r'/index\.php/vod/play/id/(\d+)/sid/(\d+)/nid/(\d+)\.html')
RE_PLAYER = re.compile(r'player_aaaa\s*=\s*(\{[\s\S]{0,2000}?\})\s*(?:;|</script>)', re.S)
RE_M3U8 = re.compile(r'https?://[^\s"\'<>\\]+\.(?:m3u8|mp4)[^\s"\'<>\\]*')


class Spider(_BaseSpider):
    # ------------------------------------------------------------------ 基础
    def __init__(self):
        self.host = _Cfg.HOST
        self.timeout = _Cfg.TIMEOUT
        self.header = {
            "User-Agent": _Cfg.UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": _Cfg.HOST + "/",
        }
        self._child = dict(CHILD_TYPES)
        self._child_loaded = False

    def getName(self):
        return "心事影视"

    def init(self, extend=""):
        """影视壳加载蜘蛛时调用；extend 可传站点根域名覆盖，如 'https://xxx.com'"""
        if extend and isinstance(extend, str) and extend.startswith("http"):
            self.host = extend.rstrip("/")
            self.header["Referer"] = self.host + "/"
        return self

    def getDependence(self):
        return []

    def isVideoFormat(self, url):
        return bool(url and re.search(r'\.(m3u8|mp4|flv)(\?|$)', url, re.I))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def localProxy(self, param):
        """备用：若某天图床/CDN 开始校验 referer，可在壳里走本地代理带 header"""
        return [200, "video/MP2T", b"", {}]

    # ------------------------------------------------------------------ HTTP
    def _get(self, url, referer=None, tries=None):
        if url.startswith("/"):
            url = self.host + url
        elif not url.startswith("http"):
            url = urljoin(self.host + "/", url)
        tries = tries or _Cfg.RETRY
        headers = dict(self.header)
        if referer:
            headers["Referer"] = referer
        last = None
        for i in range(tries + 1):
            try:
                if requests is not None:
                    r = requests.get(url, headers=headers, timeout=self.timeout, verify=False)
                    if r.status_code == 200:
                        r.encoding = r.apparent_encoding or "utf-8"
                        return r.text
                    last = "HTTP %s" % r.status_code
                else:
                    import urllib.request
                    req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                        body = resp.read()
                    for enc in ("utf-8", "gbk"):
                        try:
                            return body.decode(enc)
                        except Exception:
                            continue
                    return body.decode("utf-8", "ignore")
            except Exception as e:
                last = str(e)
            if i < tries:
                time.sleep(0.6)
        return ""

    # ------------------------------------------------------------------ 解析
    @staticmethod
    def _abs(pic):
        if not pic:
            return ""
        if pic.startswith("//"):
            return "https:" + pic
        if pic.startswith("/"):
            return _Cfg.HOST + pic
        return pic

    def _parse_list(self, h):
        """列表页/搜索页解析，兼容首页(标题在 img 上)与列表页(标题在 a 上)两种排布"""
        out, seen = [], set()
        for m in RE_ITEM.finditer(h or ""):
            inner = m.group("inner")
            if "<img" not in inner:
                continue
            vid = m.group("vid")
            if vid in seen:
                continue
            seen.add(vid)

            pic = ""
            mp = re.search(r'<img[^>]+src="([^"]+)"', inner)
            if mp:
                pic = self._abs(mp.group(1))

            title = ""
            mt = re.search(r'title="([^"]*)"', m.group("attrs") or "")
            if mt:
                title = mt.group(1)
            if not title:
                mt = re.search(r'<img[^>]+title="([^"]*)"', inner)
                if mt:
                    title = mt.group(1)
            if not title:
                title = re.sub(r'<[^>]+>', '', inner)
            title = re.sub(r'\s+', ' ', title).strip()

            note = ""
            mn = re.search(r'<span>([^<]*)</span>', inner)
            if mn:
                note = mn.group(1).strip().strip(".")

            out.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": note,
            })
        return out

    @staticmethod
    def _parse_page(h):
        m = RE_PAGE.search(h or "")
        if m:
            total, cur, pages = int(m.group(1)), int(m.group(2)), int(m.group(3))
            limit = int(total / pages) + (1 if total % pages else 0) if pages else _Cfg.DEFAULT_LIMIT
            return total, cur, max(pages, 1), max(limit, 1)
        m2 = RE_PAGE2.search(h or "")
        pages = int(m2.group(1)) if m2 else 1
        return 0, 1, max(pages, 1), _Cfg.DEFAULT_LIMIT

    @staticmethod
    def _strip(s):
        s = re.sub(r'<script[\s\S]*?</script>', ' ', s or '')
        s = re.sub(r'<[^>]+>', ' ', s)
        s = s.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&quot;', '"')
        return re.sub(r'\s+', ' ', s).strip()

    def _parse_detail(self, h, vid):
        blk = ""
        m = re.search(r'<div class="media">([\s\S]*?)<div class="clearfix">', h or "")
        if m:
            blk = m.group(1)
        if not blk:
            blk = h or ""

        name = ""
        mt = re.search(r'片名[:：]\s*([^<\n]*)', blk)
        if mt:
            name = mt.group(1).strip()
        if not name:
            mt = re.search(r'<title>([^<]*)</title>', h or "")
            if mt:
                name = mt.group(1).split('详情')[0].strip()

        type_name = ""
        mt = re.search(r'类型[:：]\s*<a[^>]*>([^<]*)</a>', blk)
        if mt:
            type_name = self._strip(mt.group(1))

        pic = ""
        mt = re.search(r'<img[^>]+src="([^"]+)"', blk)
        if mt:
            pic = self._abs(mt.group(1))

        year = ""
        mt = re.search(r'年代[:：]?\s*(\d{4})', blk) or re.search(r'/search/year/(\d{4})\.html', blk)
        if mt:
            year = mt.group(1)

        tags = []
        for t in re.findall(r'/index\.php/vod/search/class/([^"\'?]+)\.html', blk):
            t = unquote(t).strip()
            if t and t not in tags:
                tags.append(t)

        content = ""
        mt = re.search(r'简介[:：]\s*([^<\n]*)', blk)
        if mt:
            content = mt.group(1).strip()
        if not content:
            mt = re.search(r'name="description"\s+content="([^"]*)"', h or "")
            if mt:
                content = mt.group(1).strip()
        if content and name and content == name:
            content = name

        actor = ""
        mt = re.search(r'主演[:：]\s*([^<\n]*)', blk)
        if mt:
            actor = mt.group(1).strip()
        director = ""
        mt = re.search(r'导演[:：]\s*([^<\n]*)', blk)
        if mt:
            director = mt.group(1).strip()

        area = ""
        mt = re.search(r'地区[:：]\s*<a[^>]*>([^<]*)</a>', blk)
        if mt:
            area = self._strip(mt.group(1))

        # 播放线路：sid 为线路，nid 为集数
        plays = []
        seen = set()
        for sid, nid in re.findall(r'/index\.php/vod/play/id/%s/sid/(\d+)/nid/(\d+)\.html' % vid, h or ""):
            key = (sid, nid)
            if key in seen:
                continue
            seen.add(key)
            plays.append((sid, nid))
        plays.sort(key=lambda x: (int(x[0]), int(x[1])))

        urls = []
        if plays:
            by_sid = {}
            for sid, nid in plays:
                by_sid.setdefault(sid, []).append(nid)
            for sid in sorted(by_sid, key=lambda x: int(x)):
                eps = []
                for nid in by_sid[sid]:
                    ep = "正片" if len(by_sid[sid]) == 1 else "第%s集" % nid
                    ep_url = "/index.php/vod/play/id/%s/sid/%s/nid/%s.html" % (vid, sid, nid)
                    if _Cfg.EAGER_RESOLVE:
                        real = self._resolve_play(ep_url)
                        ep_url = real or ep_url
                    eps.append("%s$%s" % (ep, ep_url))
                urls.append("#".join(eps))
        else:
            ep_url = "/index.php/vod/play/id/%s/sid/1/nid/1.html" % vid
            if _Cfg.EAGER_RESOLVE:
                ep_url = self._resolve_play(ep_url) or ep_url
            urls.append("正片$%s" % ep_url)

        vod = {
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": pic,
            "type_name": type_name or (self._child.get(int(vid)) or ""),
            "vod_year": year,
            "vod_area": area,
            "vod_actor": actor,
            "vod_director": director,
            "vod_content": content or name,
            "vod_remarks": "|".join(tags),
            "vod_play_from": "$$$".join(
                ["线路%s" % s for s in (sorted(set([x for x, _ in plays]), key=lambda v: int(v)) or ["1"])]),
            "vod_play_url": "$$$".join(urls),
        }
        return vod

    # ------------------------------------------------------------------ 播放
    def _resolve_play(self, play_url):
        """进入播放页，取 player_aaaa 里的直连地址（parse=0）"""
        h = self._get(play_url, referer=self.host + "/")
        if not h:
            return ""
        raw = ""
        m = RE_PLAYER.search(h)
        if m:
            txt = m.group(1).replace('\\/', '/')
            try:
                j = json.loads(txt)
                raw = (j.get("url") or "").strip()
            except Exception:
                mm = re.search(r'"url"\s*:\s*"([^"]+)"', txt)
                if mm:
                    raw = mm.group(1).replace('\\/', '/')
        if not raw:
            mm = RE_M3U8.search(h.replace('\\/', '/'))
            if mm:
                raw = mm.group(0)
        if raw and not re.match(r'^https?://', raw):
            raw = urljoin(self.host + "/", raw)
        return raw

    def playerContent(self, flag, id, vipFlags):
        url = id or ""
        if url.startswith("/") or (url.startswith("http") and 'vod/play/' in url):
            real = self._resolve_play(url)
            url = real or url
        elif not self.isVideoFormat(url):
            real = self._resolve_play(url)
            url = real or url
        return {
            "parse": 0,
            "playUrl": "",
            "url": url,
            "header": {"User-Agent": _Cfg.UA, "Referer": self.host + "/"},
            "jx": 0,
        }

    # ------------------------------------------------------------------ 分类
    def _load_child_types(self):
        """从站点导航抓最新的子分类表（失败就用内置表）"""
        if self._child_loaded:
            return self._child
        try:
            h = self._get("/")
            items = re.findall(
                r'<dd><a href="/index\.php/vod/type/id/(\d+)\.html"[^>]*>([^<]*)</a></dd>', h or "")
            if len(items) < 10:
                items = re.findall(
                    r'href="/index\.php/vod/type/id/(\d+)\.html"[^>]*>([^<]*)</a>', h or "")
            got = {}
            for tid, name in items:
                tid = int(tid)
                name = re.sub(r'\s+', '', name or '')
                if tid >= 20 and name and '更多' not in name and '首页' not in name:
                    got[tid] = name
            if len(got) > 10:
                self._child = got
                self._child_loaded = True
        except Exception:
            pass
        return self._child

    def _filters_for(self, tid):
        """按父/子分类生成完整筛选器"""
        fl = []
        # 子分类筛选（仅父分类 tab 提供）
        if str(tid).startswith("g_"):
            subs = []
            for gid, gname, tids in PARENT_GROUPS:
                if gid == tid:
                    subs.append({"n": "全部", "v": "all"})
                    for t in tids:
                        subs.append({"n": self._child.get(t, str(t)), "v": str(t)})
                    break
            if subs:
                fl.append({"key": "sub", "name": "子分类", "value": subs})
        else:
            # 子分类 tab：给出同组兄弟分类快速切换
            cur = int(tid) if str(tid).isdigit() else 0
            gid = TYPE_TO_GROUP.get(cur)
            if gid:
                for g, gname, tids in PARENT_GROUPS:
                    if g == gid:
                        fl.append({"key": "sub", "name": "分类", "value":
                                   [{"n": "全部", "v": "all"}] +
                                   [{"n": self._child.get(t, str(t)), "v": str(t)} for t in tids]})
                        break
        fl.append({"key": "year", "name": "年代",
                   "value": [{"n": y, "v": y} for y in YEARS]})
        fl.append({"key": "letter", "name": "字母",
                   "value": [{"n": l, "v": l} for l in LETTERS]})
        fl.append({"key": "by", "name": "排序",
                   "value": [{"n": n, "v": v} for v, n in SORTS]})
        return fl

    def homeContent(self, filter):
        child = self._load_child_types()
        classes = [
            {"type_id": "new", "type_name": "最近更新"},
            {"type_id": ROOT_TID, "type_name": "全部影片"},
        ]
        for gid, gname, tids in PARENT_GROUPS:
            classes.append({"type_id": gid, "type_name": gname})
        # 直接把 81 个子分类挂上（部分壳没有筛选器，靠这层也能进每一类）
        for tid in sorted(child.keys()):
            classes.append({"type_id": str(tid), "type_name": child[tid]})
        filters = {}
        for c in classes:
            filters[c["type_id"]] = self._filters_for(c["type_id"])
        return {"class": classes, "filters": filters, "list": []}

    def homeVideoContent(self):
        h = self._get("/index.php/vod/type/id/%s.html" % ROOT_TID)
        return {"list": self._parse_list(h)}

    # ------------------------------------------------------------------ 列表
    @staticmethod
    def _ext(extend, key, default=""):
        """兼容三种壳传参：dict / JSON 字符串 / 空"""
        if not extend:
            return default
        if isinstance(extend, str):
            try:
                extend = json.loads(extend)
            except Exception:
                return default
        if isinstance(extend, dict):
            v = extend.get(key, default)
            return default if v is None else str(v)
        return default

    def _build_list_url(self, tid, pg, year="", letter="", by="", letter_only=None):
        base = "/index.php/vod/type/id/%s" % tid
        if year and year != "全部":
            base += "/year/%s" % quote(str(year))
        if letter and letter != "全部":
            base += "/letter/%s" % quote(str(letter))
        if by and by in ("hits", "time", "score", "score"):
            base += "/by/%s" % by
        base += "/page/%s.html" % pg
        return base

    def _fetch_list(self, tid, pg, year="", letter="", by=""):
        h = self._get(self._build_list_url(tid, pg, year, letter, by))
        lst = self._parse_list(h)
        total, cur, pages, limit = self._parse_page(h)
        return lst, cur, pages, limit

    def categoryContent(self, tid, pg, filter, extend):
        tid = str(tid)
        try:
            pg = int(pg or 1)
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1

        year = self._ext(extend, "year", "全部")
        letter = self._ext(extend, "letter", "全部")
        by = self._ext(extend, "by", "time")
        sub = self._ext(extend, "sub", "")
        if by == "全部":
            by = ""

        # 最近更新
        if tid == "new":
            lst, cur, pages, limit = self._fetch_list(ROOT_TID, pg, year, letter, by)
            return {"list": lst, "page": cur, "pagecount": pages, "limit": limit,
                    "total": pages * limit if pages else len(lst)}

        # 父分类
        if tid.startswith("g_"):
            if sub and sub != "all" and sub.isdigit():
                lst, cur, pages, limit = self._fetch_list(sub, pg, year, letter, by)
                return {"list": lst, "page": cur, "pagecount": pages, "limit": limit,
                        "total": pages * limit if pages else len(lst)}
            tids = []
            for gid, gname, ts in PARENT_GROUPS:
                if gid == tid:
                    tids = ts
                    break
            if not tids:
                return {"list": [], "page": pg, "pagecount": 1, "limit": 0, "total": 0}
            merged, seen = [], set()
            pages_max, limit = 1, _Cfg.DEFAULT_LIMIT
            results = self._parallel([(t, pg, year, letter, by) for t in tids])
            for lst, cur, pages, lim in results:
                pages_max = max(pages_max, pages)
                limit = lim or limit
                for it in lst:
                    if it["vod_id"] in seen:
                        continue
                    seen.add(it["vod_id"])
                    merged.append(it)
            return {"list": merged, "page": pg, "pagecount": pages_max,
                    "limit": limit, "total": pages_max * limit}

        # 子分类 / 全部影片（子分类页也支持用筛选器切换到同组兄弟分类）
        if tid.isdigit() and sub.isdigit() and sub != tid:
            tid = sub
        lst, cur, pages, limit = self._fetch_list(tid, pg, year, letter, by)
        return {"list": lst, "page": cur, "pagecount": pages, "limit": limit,
                "total": pages * limit if pages else len(lst)}

    def _parallel(self, jobs):
        """组内子分类并发抓取，失败不影响整体"""
        out = []
        try:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=_Cfg.THREADS) as ex:
                futs = [ex.submit(self._fetch_list, t, p, y, l, b) for t, p, y, l, b in jobs]
                for f in futs:
                    try:
                        out.append(f.result())
                    except Exception:
                        out.append(([], 1, 1, _Cfg.DEFAULT_LIMIT))
        except Exception:
            for t, p, y, l, b in jobs:
                try:
                    out.append(self._fetch_list(t, p, y, l, b))
                except Exception:
                    out.append(([], 1, 1, _Cfg.DEFAULT_LIMIT))
        return out

    # ------------------------------------------------------------------ 详情
    def detailContent(self, array):
        if isinstance(array, (list, tuple)):
            vid = str(array[0]) if array else ""
        else:
            vid = str(array)
        vid = re.sub(r'\D', '', vid)
        if not vid:
            return {"list": []}
        h = self._get("/index.php/vod/detail/id/%s.html" % vid)
        if not h:
            return {"list": []}
        return {"list": [self._parse_detail(h, vid)]}

    # ------------------------------------------------------------------ 搜索
    def searchContent(self, key, quick, pg="1"):
        try:
            pg = int(pg or 1)
        except Exception:
            pg = 1
        url = "/index.php/vod/search.html?wd=%s&page=%s" % (quote(key or ""), pg)
        h = self._get(url, referer=self.host + "/")
        lst = self._parse_list(h)
        total, cur, pages, limit = self._parse_page(h)
        if not lst and '%' in (key or ''):
            # 兜底：路径式搜索
            h = self._get("/index.php/vod/search/wd/%s/page/%s.html" % (quote(key or ""), pg))
            lst = self._parse_list(h)
        return {"list": lst, "page": pg, "pagecount": pages, "limit": limit,
                "total": total}

    # ------------------------------------------------------------------ 自测
    def selftest(self):
        out = []
        out.append("== 1. 分类 ==")
        home = self.homeContent(True)
        out.append("一级分类 %d 个：%s" % (
            len(home["class"]), " / ".join([c["type_name"] for c in home["class"]])))
        out.append("筛选器 keys=%d  示例(%s)=%s" % (
            len(home["filters"]), "g_guochan",
            json.dumps(home["filters"].get("g_guochan", [])[:1], ensure_ascii=False)[:260]))

        out.append("\n== 2. 分页（子分类 20 第1页 / 父分类 g_guochan 第2页）==")
        c1 = self.categoryContent("20", 1, True, {})
        out.append("tid=20 pg=1 -> %d 条, pagecount=%s, limit=%s, 首条=%s" % (
            len(c1["list"]), c1["pagecount"], c1["limit"],
            c1["list"][0]["vod_name"][:24] if c1["list"] else "无"))
        c2 = self.categoryContent("g_guochan", 2, True, {"sub": "all"})
        out.append("g_guochan pg=2 -> %d 条, pagecount=%s" % (len(c2["list"]), c2["pagecount"]))
        c3 = self.categoryContent("20", 1, True, {"year": "2025", "letter": "A", "by": "hits"})
        out.append("tid=20 + 年代2025 + 字母A + 排序hits -> %d 条 (筛选器组合)" % len(c3["list"]))

        vid = c1["list"][0]["vod_id"] if c1["list"] else "30595"
        out.append("\n== 3./4. 详情 + 播放（id=%s）==" % vid)
        d = self.detailContent([vid])
        if d["list"]:
            v = d["list"][0]
            out.append("片名=%s" % v["vod_name"][:40])
            out.append("类型=%s 年代=%s 标签=%s" % (v["type_name"], v["vod_year"], v["vod_remarks"]))
            out.append("封面=%s" % v["vod_pic"])
            out.append("简介=%s" % v["vod_content"][:50])
            out.append("线路=%s" % v["vod_play_from"])
            first = (v["vod_play_url"].split("#")[0] or "").split("$")[-1]
            out.append("播放页=%s" % first)
            p = self.playerContent("", first, None)
            out.append("直连(parse=0)= %s" % p["url"])

        out.append("\n== 5. 搜索（关键词：学妹）==")
        s = self.searchContent("学妹", False, "1")
        out.append("结果 %d 条, pagecount=%s, 首条=%s" % (
            len(s["list"]), s["pagecount"], s["list"][0]["vod_name"][:30] if s["list"] else "无"))
        s2 = self.searchContent("学妹", False, "2")
        out.append("第2页 %d 条" % len(s2["list"]))

        out.append("\n== 6. 封面 ==")
        if s["list"]:
            out.append("搜索首条封面=%s" % s["list"][0]["vod_pic"])
        return "\n".join(out)


if __name__ == "__main__":
    import sys
    sp = Spider()
    sp.init("")
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        print(sp.selftest())
    elif len(sys.argv) > 2:
        # 简易 CLI： python3 XinShi.py cat 20 [pg] / detail <id> / search <kw> / play <play_url>
        cmd = sys.argv[1]
        if cmd == "cat":
            r = sp.categoryContent(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else 1, True, {})
        elif cmd == "detail":
            r = sp.detailContent([sys.argv[2]])
        elif cmd == "search":
            r = sp.searchContent(sys.argv[2], False, "1")
        elif cmd == "play":
            r = sp.playerContent("", sys.argv[2], None)
        elif cmd == "home":
            r = sp.homeContent(True)
        else:
            r = {"err": "unknown cmd"}
        print(json.dumps(r, ensure_ascii=False, indent=2)[:4000])
    else:
        print("用法: python3 XinShi.py test            # 全流程自测")
        print("      python3 XinShi.py cat 20 1        # 分类列表")
        print("      python3 XinShi.py detail 30595    # 详情")
        print("      python3 XinShi.py search 学妹      # 搜索")
        print("      python3 XinShi.py play /index.php/vod/play/id/30595/sid/1/nid/1.html")
