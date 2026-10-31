# -*- coding: utf-8 -*-
# ============ 淫花宫 (breplc.yhg5.help) TVBox / OK影视 标准爬虫 ============
# 站点: https://breplc.yhg5.help ，苹果CMS四壳结构
# 路由(实测 2026-10-17):
#   首页     /cn/home/web/            卡片 <a href="/{vid}.html" title data-original>
#   分类     /vodtype/{tid}.html      翻页 /vodtype/{tid}-{pg}.html (标题"{分类}_第N页")
#            注意: /vodtype/{tid}---page/{pg}.html 返回 200 但内容错乱(标题"_第1页",
#            分类名丢失), 只能做兜底, 必须用 check_category_page 拦掉
#   详情     /{vid}.html             m3u8 直链直接嵌在详情页 HTML 里, 无独立播放页
#   搜索     /s/{kw}.html
#   播放     详情页内嵌 m3u8 (如 https://2609.sysl2026.com/.../index.m3u8), master 列表有效
# 由 OmniBox 版改写为 TVBox 标准 Spider 类(OK影视/peekpro/TVBox 通用)

import base64
import html as _html
import json
import re
import ssl
import time
import urllib.parse
import urllib.request

BASE_URL = "https://breplc.yhg5.help"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36")
TIMEOUT = 20
RETRY = 2
PAGE_SIZE = 30

CATEGORY_MAP = {
    "20": "熟母少妇",
    "21": "网红直播",
    "22": "自拍偷拍",
    "23": "强奸乱伦",
    "24": "高清国产",
    "25": "韩国专区",
    "26": "日本有码",
    "27": "日本无码",
    "28": "欧美情色",
    "29": "动漫卡通",
    "30": "三级伦理",
}
# 真实翻页 /vodtype/{tid}-{pg}.html 必须排第一; ---page 模板错乱只做兜底
CATEGORY_TEMPLATES = [
    "/vodtype/{tid}-{pg}.html",
    "/vodtype/{tid}.html",
    "/vodtype/{tid}---page/{pg}.html",
    "/vodtype/{tid}/page/{pg}.html",
]
SEARCH_TEMPLATES = [
    "/s/{kw}.html",
    "/index.php/vod/search/search/wd/{kw}/page/{pg}.html",
    "/vodsearch/{kw}/page/{pg}.html",
]
HOME_PATHS = ["/cn/home/web/", "/index.html", "/"]

SORT_FILTER_MAP = {"综合": "", "最新": "time", "最热": "hit", "评分": "score"}

FIELD_LABELS = {
    "导演": "vod_director", "主演": "vod_actor", "编剧": "vod_writer",
    "地区": "vod_area", "制片国家/地区": "vod_area", "语言": "vod_lang",
    "上映日期": "vod_pubdate", "年份": "vod_year", "片长": "vod_remarks",
    "又名": "vod_subtitle", "类型": "type_name",
}

DETAIL_PATH_RE = re.compile(r"^(\d+)\.html$")
PLAY_PATH_RE = re.compile(r"/(?:vodplay|vplay|play)/(\d+)-(\d+)-(\d+)\.html", re.I)
BAD_PAGE_MARKERS = ("404", "页面不存在", "页面已删除", "已删除", "找不到", "not found", "访问出错")

_HOME_VIDS = None
_TEMPLATE_CACHE = {}


def _ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _decode_body(body):
    if not isinstance(body, (bytes, bytearray)):
        return str(body or "")
    raw = bytes(body)
    m = re.search(rb'charset\s*=\s*["\']?\s*([a-zA-Z0-9_\-]+)', raw[:4096], re.I)
    enc = m.group(1).decode("ascii", "ignore").lower() if m else ""
    for cand in ([enc] if enc else []) + ["utf-8", "gb18030", "gbk"]:
        if not cand:
            continue
        try:
            return raw.decode(cand)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", "ignore")


def _fetch(url, referer=None, retry=RETRY):
    last_err = None
    for _ in range(retry + 1):
        headers = {
            "User-Agent": UA,
            "Referer": referer or (BASE_URL + "/"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Connection": "close",
        }
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT,
                                        context=_ssl_ctx()) as r:
                data = r.read()
            if r.getcode() == 200 and data:
                return _decode_body(data)
            last_err = "HTTP %s/%dB" % (r.getcode(), len(data or b""))
        except Exception as e:
            last_err = str(e)
        time.sleep(0.5)
    raise IOError("fetch failed (%s): %s" % (last_err, url))


def _abs(url):
    url = str(url or "").strip()
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return BASE_URL + url
    return BASE_URL + "/" + url.lstrip("./")


def _clean(text):
    text = re.sub(r"<(br|/p|/div|/li)\s*/?>", " ", str(text or ""), flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = _html.unescape(text)
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def _uniq(seq):
    out, seen = [], set()
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _is_detail_url(url):
    path = (urllib.parse.urlparse(_abs(url)).path or "").strip("/")
    m = DETAIL_PATH_RE.match(path)
    return m.group(1) if m else ""


def _tag_attr(tag, *names):
    for name in names:
        m = re.search(r'%s\s*=\s*["\']([^"\']+)["\']' % re.escape(name),
                      tag, re.I)
        if m and m.group(1).strip():
            return _html.unescape(m.group(1).strip())
    return ""


def _is_bad_page(text):
    m = re.search(r"<title[^>]*>(.*?)</title>", str(text or ""), re.S | re.I)
    title = _clean(m.group(1)) if m else ""
    return any(k in title for k in BAD_PAGE_MARKERS)


def _head_scope(text):
    parts = []
    for pat in (r"<title[^>]*>(.*?)</title>", r"<h1[^>]*>(.*?)</h1>"):
        m = re.search(pat, text, re.S | re.I)
        if m:
            parts.append(_clean(m.group(1)))
    return " ".join(p for p in parts if p)


def _check_category_page(text, type_id):
    """真分类页标题必带分类名(如"熟母少妇_第1页"); 标题里没有本分类名直接判失败,
    拦掉 /vodtype/20---page/2.html 这类软 200 错乱页(标题"_第1页", 分类名丢失)。"""
    if _is_bad_page(text):
        return False
    scope = _head_scope(text)
    name = CATEGORY_MAP.get(str(type_id), "")
    if not name:
        return True
    if name in scope:
        return True
    for tid, other in CATEGORY_MAP.items():
        if tid != str(type_id) and other and other in scope:
            return False
    return False


def _iter_cards(text, type_id="0", type_name="", limit=200):
    cards, seen = [], set()
    for m in re.finditer(r"<a\s([^>]+)>", text, re.I):
        attrs = m.group(1)
        vid = _is_detail_url(_tag_attr(attrs, "href"))
        if not vid or vid in seen:
            continue
        seen.add(vid)
        title = _clean(_tag_attr(attrs, "title"))
        close_at = text.find("</a>", m.end())
        inner = text[m.end(): close_at if close_at > 0 else m.end() + 300]
        if not title:
            title = _clean(inner)
        pic = _tag_attr(attrs, "data-original", "data-src", "src")
        if not pic:
            im = re.search(r"<img\s([^>]+)>", inner, re.I)
            if im:
                pic = _tag_attr(im.group(1), "data-original", "data-src", "src")
        if pic and not pic.startswith("data:"):
            pic = _abs(pic)
        window = text[m.end(): m.end() + 600]
        remarks = ""
        nm = re.search(r'class="[^"]*(?:module-item-note|pic-text)[^"]*"[^>]*>(.*?)</',
                       window, re.S | re.I)
        if nm:
            remarks = _clean(nm.group(1))
        if not title:
            continue
        cards.append({"vod_id": vid, "vod_name": title[:120],
                      "vod_pic": pic, "vod_remarks": remarks,
                      "type_id": str(type_id), "type_name": type_name})
        if len(cards) >= limit:
            break
    return cards


def _extract_pagecount(text, current_page):
    pages = set()
    scope = text
    for marker in ('class="pagination"', 'class="page"', "mac-page"):
        idx = text.find(marker)
        if idx >= 0:
            scope = text[idx: idx + 3000]
            break
    for pat in (r"page[/=-](\d+)", r"/vodtype/\d+-(\d+)\.html"):
        for m in re.finditer(pat, scope, re.I):
            try:
                pages.add(int(m.group(1)))
            except (TypeError, ValueError):
                pass
    m = re.search(r"(?:totalpage|pagecount)\D{0,6}(\d+)", scope, re.I)
    if m:
        pages.add(int(m.group(1)))
    return max(max(pages), current_page) if pages else current_page + 1


def _extend_dict(extend):
    """OK影视传进来的 extend 可能是 dict 也可能是 JSON 字符串; filter 是布尔值,
    筛选项一律从 extend 里取, 不能对 filter 做 .get() (会 AttributeError 崩掉整页)。"""
    if not extend:
        return {}
    if isinstance(extend, dict):
        return extend
    if isinstance(extend, str):
        try:
            d = json.loads(extend)
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}
    return {}


def _vid_overlap(cards, vids):
    cur = {c["vod_id"] for c in cards if c.get("vod_id")}
    if not cur or not vids:
        return 0.0
    return len(cur & vids) / len(cur)


def _home_vids():
    global _HOME_VIDS
    if _HOME_VIDS is not None:
        return _HOME_VIDS
    for path in HOME_PATHS:
        try:
            text = _fetch(_abs(path))
        except IOError:
            continue
        vids = {c["vod_id"] for c in _iter_cards(text) if c.get("vod_id")}
        if vids:
            _HOME_VIDS = frozenset(vids)
            break
    if _HOME_VIDS is None:
        _HOME_VIDS = frozenset()
    return _HOME_VIDS


def _decode_m3u8_payload(value):
    raw = str(value or "").strip().strip('"').strip("'")
    if not raw or raw.startswith("http"):
        return raw
    try:
        decoded = base64.b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8", "ignore")
    except Exception:
        return raw
    if "$$$" in decoded:
        decoded = decoded.split("$$$")[0]
    if "|" in decoded and not decoded.startswith("http"):
        decoded = decoded.rsplit("|", 1)[-1]
    return decoded.strip()


def _extract_m3u8(text):
    """详情页内嵌 m3u8 直链(本站无独立播放页, 播放地址直接写在详情页里)。"""
    for pat in (
        r"(?:var\s+)?(?:play_?url|playUrl|video_?url)\s*=\s*['\"]([^'\"]+)['\"]",
        r'"url"\s*:\s*"(https?://[^"\\]+)"',
        r"""['"](https?://[^'"\s<>]+\.(?:m3u8|mp4|flv)[^'"\s<>]*)['"]""",
    ):
        m = re.search(pat, text, re.I)
        if m:
            url = _decode_m3u8_payload(m.group(1)).replace("\\/", "/")
            if url.startswith("http"):
                return url
    return ""


def _extract_content(text):
    for pat in (
        r'class="[^"]*(?:stui-content|vod_content|content)[^"]*"[^>]*>(.*?)</div>',
        r"(?:剧情简介|剧情|简介)\s*[:：]\s*(.*?)(?=</li>|</p>|</div>|$)",
    ):
        m = re.search(pat, text, re.S | re.I)
        if m:
            v = _clean(m.group(1))
            if len(v) > 4 and "剧情简介" not in v[:6]:
                return v
    return ""


class Spider:
    """淫花宫 TVBox/OK影视 标准爬虫"""

    def init(self, extend=""):
        pass

    def destroy(self):
        pass

    def getDependence(self):
        return []

    def getName(self):
        return "淫花宫"

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return {}

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4|flv|ts)(\?|$)", url or "", re.I))

    def homeContent(self, filter=False):
        classes = [{"type_id": tid, "type_name": name}
                   for tid, name in CATEGORY_MAP.items()]
        filters = {}
        if filter:
            sorts = [{"n": n, "v": n} for n in SORT_FILTER_MAP.keys()]
            for tid in CATEGORY_MAP.keys():
                filters[tid] = [{"key": "sort", "name": "排序",
                                 "value": sorts}]
        result = {"class": classes, "filters": filters}
        if filter:
            return result
        cards = []
        for path in HOME_PATHS:
            try:
                text = _fetch(_abs(path))
            except IOError:
                continue
            cards = _iter_cards(text)
            if cards:
                break
        result["list"] = cards[:PAGE_SIZE]
        return result

    def homeVideoContent(self):
        for path in HOME_PATHS:
            try:
                text = _fetch(_abs(path))
            except IOError:
                continue
            cards = _iter_cards(text)
            if cards:
                return {"list": cards[:PAGE_SIZE]}
        return {"list": []}

    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        try:
            return self._categoryContent(tid, pg, filter, extend)
        except Exception:
            return {"list": [], "page": 1, "pagecount": 1,
                    "limit": PAGE_SIZE, "total": 0}

    def _categoryContent(self, tid, pg=1, filter=None, extend=None):
        try:
            pg = max(1, int(pg))
        except (TypeError, ValueError):
            pg = 1
        tid = str(tid or "20")
        type_name = CATEGORY_MAP.get(tid, "")
        templates = list(CATEGORY_TEMPLATES)
        if pg > 1:
            # 不带翻页占位符的模板第 2 页会返回第 1 页内容, 直接排除
            templates = [t for t in templates if "{pg}" in t] or templates
        if tid in _TEMPLATE_CACHE and _TEMPLATE_CACHE[tid] in templates:
            cached = _TEMPLATE_CACHE[tid]
            templates = [cached] + [t for t in templates if t != cached]

        ext = _extend_dict(extend)
        sort_by = SORT_FILTER_MAP.get(str(ext.get("sort") or "综合"), "")
        home_vids = _home_vids()
        cards, pagecount, used = [], pg, ""
        fallback = []
        for tmpl in templates:
            path = tmpl.format(tid=tid, pg=pg, page=pg)
            if sort_by:
                path += ("&" if "?" in path else "?") + "by=" + sort_by
            try:
                text = _fetch(_abs(path), referer=BASE_URL + "/")
            except IOError:
                continue
            candidate = _iter_cards(text, tid, type_name)
            if not candidate:
                continue
            if _vid_overlap(candidate, home_vids) >= 0.8:
                continue  # 被重定向回首页
            if not _check_category_page(text, tid):
                if not fallback:
                    fallback = candidate
                continue  # 软 200 错乱页
            cards, used = candidate, tmpl
            pagecount = _extract_pagecount(text, pg)
            break
        if not cards and fallback:
            cards = fallback
        if used:
            _TEMPLATE_CACHE[tid] = used
        else:
            _TEMPLATE_CACHE.pop(tid, None)
        has_more = len(cards) >= PAGE_SIZE
        pagecount = max(pg, pagecount) if has_more else pg
        return {"list": cards, "page": pg, "pagecount": pagecount,
                "limit": PAGE_SIZE,
                "total": pg * PAGE_SIZE + (1 if has_more else 0)}

    def detailContent(self, ids):
        vid = str((ids or [""])[0]).strip()
        if not vid.isdigit():
            vid = _is_detail_url(vid)
        if not vid:
            return {"list": []}
        try:
            text = _fetch(_abs("/%s.html" % vid),
                          referer=BASE_URL + "/")
        except IOError:
            return {"list": []}
        if _is_bad_page(text):
            return {"list": []}
        title = ""
        for pat in (r"<h1[^>]*>(.*?)</h1>", r"<title>(.*?)</title>"):
            m = re.search(pat, text, re.S | re.I)
            if m:
                title = _clean(m.group(1)).split("_")[0].split("-")[0].strip()
                if title:
                    break
        title = title or vid
        pic = ""
        m = re.search(r"<img\s([^>]+)>", text, re.S | re.I)
        if m:
            pic = _abs(_tag_attr(m.group(1), "data-original", "data-src", "src"))
        info = {}
        for label, key in FIELD_LABELS.items():
            m = re.search(r"%s\s*[:：]\s*(.*?)(?=</li>|</p>|</dd>|<br|$)"
                          % re.escape(label), text, re.S)
            if m:
                info[key] = _clean(m.group(1))
        type_id, type_name = "", info.get("type_name", "")
        tm = re.search(r'/vodtype/(\d+)\.html', text)
        if tm:
            type_id = tm.group(1)
            type_name = type_name or CATEGORY_MAP.get(type_id, "")
        m3u8 = _extract_m3u8(text)
        if not m3u8:
            return {"list": []}
        vod = {
            "vod_id": vid, "vod_name": title, "vod_pic": pic,
            "vod_year": info.get("vod_year", ""),
            "vod_area": info.get("vod_area", ""),
            "vod_remarks": info.get("vod_remarks", ""),
            "vod_actor": info.get("vod_actor", ""),
            "vod_director": info.get("vod_director", ""),
            "vod_content": _extract_content(text),
            "type_id": type_id, "type_name": type_name,
            "vod_play_from": "在线播放",
            "vod_play_url": "正片$%s" % m3u8,
        }
        return {"list": [vod]}

    def searchContent(self, key, quick=False, pg="1"):
        try:
            pg = max(1, int(pg))
        except (TypeError, ValueError):
            pg = 1
        key = str(key or "").strip()
        if not key:
            return {"list": []}
        home_vids = _home_vids()
        cards = []
        for tmpl in SEARCH_TEMPLATES:
            path = tmpl.format(kw=urllib.parse.quote(key), pg=pg, page=pg)
            try:
                text = _fetch(_abs(path), referer=BASE_URL + "/")
            except IOError:
                continue
            candidate = _iter_cards(text)
            if candidate and not _is_bad_page(text) \
                    and _vid_overlap(candidate, home_vids) < 0.8:
                cards = candidate
                break
        return {"list": cards}

    def searchContentPage(self, key, quick, pg):
        return self.searchContent(key, quick, pg)

    def playerContent(self, flag, id, vipFlags=None):
        pid = str(id or "").strip()
        headers = {"User-Agent": UA, "Referer": BASE_URL + "/"}
        if pid.startswith("http"):
            return {"parse": 0, "url": pid, "header": headers}
        # 兼容 "正片$..." 形式
        if "$" in pid:
            pid = pid.split("$")[-1]
            if pid.startswith("http"):
                return {"parse": 0, "url": pid, "header": headers}
        return {"parse": 0, "url": "", "header": headers}

    def localProxy(self, param):
        return None
