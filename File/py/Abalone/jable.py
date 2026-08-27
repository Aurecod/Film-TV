#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
jable.py — JableTV FongMi 影视 Type3 单文件 Python 爬虫
由 jable.user.js (GMSpider 油猴脚本) 移植为纯 Python 实现。

依赖优先级: curl_cffi(过 Cloudflare, 推荐) > requests > urllib
配置示例(FongMi 规则里添加):
{
  "key": "local_jable_spider",
  "name": "Jable",
  "type": 3,
  "api": "./File/py/Hunter/jable.py",
  "searchable": 1,
  "quickSearch": 1,
  "filterable": 1,
  "order_num": 0,
  "style": { "type": "rect" }
}
"""

import json
import os
import re
import sys
import time
import traceback
import urllib.parse
import urllib.request
from datetime import datetime

# ---------------- 基础常量 ----------------

HOST = "https://jable.tv"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

CACHE = {}          # url -> (timestamp, html)
CACHE_TTL = 180     # 列表缓存秒数

# ---------------- 调试日志(写到手机存储根目录) ----------------
# 用文件管理器看: /sdcard/jable_debug.log (即内部存储根目录 jable_debug.log)


def _pick_log_path():
    cands = ["/sdcard/jable_debug.log",
             "/storage/emulated/0/jable_debug.log",
             os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "jable_debug.log"),
             "/tmp/jable_debug.log"]
    for p in cands:
        try:
            d = os.path.dirname(p)
            if not os.path.isdir(d):
                continue
            probe = os.path.join(d, ".jable_w_test")
            with open(probe, "a"):
                pass
            os.remove(probe)
            return p
        except Exception:
            continue
    return None


LOG_PATH = _pick_log_path()


def _log(msg):
    try:
        if not LOG_PATH:
            return
        if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > 512 * 1024:
            with open(LOG_PATH, "w") as f:
                f.write("")  # 超512KB清空重来
        with open(LOG_PATH, "a") as f:
            f.write("[%s] %s\n"
                    % (datetime.now().strftime("%m-%d %H:%M:%S"), msg))
    except Exception:
        pass


def _log_init():
    _log("=" * 30 + " 会话开始 " + "=" * 30)
    _log("python %s | log=%s" % (sys.version.split()[0], LOG_PATH))
    cf_ver = None
    if _cf:
        try:
            import curl_cffi
            cf_ver = getattr(curl_cffi, "__version__", "未知版本")
        except Exception:
            cf_ver = "已安装"
    _log("curl_cffi: %s" % (cf_ver if _cf else "未安装!!"))
    _log("requests: %s"
         % ((getattr(_rq, "__version__", "已安装") or "已安装") if _rq else "未安装"))
    _log("urllib 兜底始终可用")


# ---------------- HTTP 库探测 ----------------
_FPS = ["chrome124", "chrome123", "chrome120", "chrome116",
        "chrome110", "safari18_0", "safari17_0", "firefox133"]
_OK_FP = None       # 记住当前网络环境下可用的指纹
_JARS = {}          # 指纹 -> cookie罐(cf_clearance 必须随指纹一起复用)

try:
    from curl_cffi import requests as _cf
except Exception:
    _cf = None

try:
    import requests as _rq
except Exception:
    _rq = None


def _looks_like_cf(text):
    if not text or len(text) < 6000:
        return True
    head = text[:4000]
    return ("Just a moment" in head or "cf-wrapper" in head
            or "challenge-platform" in head)


UA_MOB = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.6414.0 Mobile Safari/537.36")
_JAVA_OK = None  # 记录 Chaquopy Java 层是否可用


def _wv_state():
    return _WV


_WV = {"lock": __import__("threading").Lock()}  # WebView 单例状态
_UA_WEBVIEW = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36")


def _wv_imports():
    """返回 (Handler, HandlerThread, WebView, WebViewClient, ValueCallback,
             Runnable, Class)。非 Android 环境抛异常。"""
    from android.os import Handler, HandlerThread
    from android.webkit import WebView, WebViewClient, ValueCallback
    from java.lang import Runnable, Class
    from java.lang.reflect import Proxy
    return Handler, HandlerThread, WebView, WebViewClient, ValueCallback, \
        Runnable, Class, Proxy


def _wv_ctx(Class):
    ctx = Class.forName("android.app.ActivityThread") \
        .getMethod("currentApplication").invoke(None)
    if ctx is None:
        raise RuntimeError("无法获取 Application 上下文")
    return ctx


def _wv_fetch(url, timeout=35):
    """用系统 WebView(真Chromium内核)加载页面并返回最终 HTML。
    成功后 WebView 常驻复用; 失败会标记 _WV['err'] 不再重试该层。"""
    st = _WV
    if st.get("err"):
        raise RuntimeError(st["err"])
    import threading as _threading
    from concurrent.futures import Future
    import json as _json

    try:
        Handler, HandlerThread, WebView, WebViewClient, ValueCallback, \
            Runnable, Class, Proxy = _wv_imports()
    except Exception as e:
        st["err"] = "WebView层不可用(导入失败): %r" % (e,)
        _log("WEBVIEW 初始化放弃: %s" % st["err"])
        raise RuntimeError(st["err"])

    with st["lock"]:
        try:
            if not st.get("ready"):
                ctx = _wv_ctx(Class)
                ht = HandlerThread("jable-wv")
                ht.start()
                handler = Handler(ht.getLooper())
                created = Future()
                holder = {}

                def create():
                    wv = WebView(st["ctx"])
                    s = wv.getSettings()
                    s.setJavaScriptEnabled(True)
                    s.setDomStorageEnabled(True)
                    s.setUserAgentString(_UA_WEBVIEW)
                    s.setBlockNetworkImage(True)
                    wv.setBackgroundColor(-1)
                    holder["wv"] = wv
                    created.set_result(wv)

                handler.post(_mk_runnable(create))
                wv = created.result(20)
                st.update({"ctx": ctx, "handler": handler,
                           "wv": wv, "holder": holder,
                           "client_flag": {}, "ready": True})
                _log("WEBVIEW 创建成功(常驻复用)")

            wv = st["wv"]
            fut = Future()
            st["pending"] = fut
            flag = {"done": False}

            def grab(u):
                if flag["done"]:
                    return
                flag["done"] = True

                def cb(v):
                    try:
                        html = _json.loads(v) if v else ""
                        if isinstance(html, str) and len(html) > 500:
                            fut.set_result(html)
                        else:
                            fut.set_exception(
                                RuntimeError("页面内容过短 len=%s" % len(html or "")))
                    except Exception as e:
                        fut.set_exception(e)

                wv.evaluateJavascript(
                    "document.documentElement.outerHTML", _mk_vcb(cb))

            def load():
                wv.setWebViewClient(_mk_client(grab))
                wv.loadUrl(url, {"Referer": HOST + "/"})

            st["handler"].post(_mk_runnable(load))
            # Python 3.10 兼容: 用 threading.Event 等待, 不依赖 Future.TimeoutError
            evt = _threading.Event()
            result = {"val": None, "exc": None}
            def on_done(f):
                try:
                    result["val"] = f.result()
                except Exception as e:
                    result["exc"] = e
                evt.set()
            fut.add_done_callback(on_done)
            if not evt.wait(timeout):
                raise RuntimeError("WEBVIEW 超时(%ds): %s" % (timeout, url[:70]))
            if result["exc"]:
                raise result["exc"]
            html = result["val"]
            CACHE[url] = (time.time(), html)
            _log("WEBVIEW 取页成功 %s len=%d" % (url[:70], len(html)))
            return html
        except Exception as e:
            # 超时不永久禁用, 只记录本次
            if "超时" in str(e):
                st["err"] = ""
                _log("!! " + str(e))
            else:
                st["err"] = "WebView层故障: %r" % (e,)
                _log("!! %s\n%s" % (st["err"], traceback.format_exc(limit=3)))
            raise RuntimeError(str(e))


# ---------------- WebView 回调类(模块顶层, Chaquopy 要求直接实现接口) ----------------
try:
    from java.lang import Runnable
    from android.webkit import WebViewClient, ValueCallback
    _HAS_JAVA = True
except Exception:
    _HAS_JAVA = False
    class Runnable:
        pass
    class WebViewClient:
        pass
    class ValueCallback:
        pass

class _WVRunnable:
    __javainterfaces__ = [Runnable] if _HAS_JAVA else []
    def __init__(self, fn):
        self._fn = fn
    def run(self):
        try:
            self._fn()
        except Exception as e:
            _log("WEBVIEW runnable 异常: %r" % (e,))

class _WVClient:
    __javainterfaces__ = [WebViewClient] if _HAS_JAVA else []
    def __init__(self, on_done):
        self._on_done = on_done
    def onPageFinished(self, view, u):
        try:
            self._on_done(u)
        except Exception as e:
            _log("WEBVIEW onPageFinished 异常: %r" % (e,))

class _WVCallback:
    __javainterfaces__ = [ValueCallback] if _HAS_JAVA else []
    def __init__(self, on_val):
        self._on_val = on_val
    def onReceiveValue(self, v):
        try:
            self._on_val(v)
        except Exception as e:
            _log("WEBVIEW vcb 异常: %r" % (e,))


def _mk_runnable(fn):
    return _WVRunnable(fn)

def _mk_client(on_done):
    return _WVClient(on_done)

def _mk_vcb(on_val):
    return _WVCallback(on_val)


def _java_get(url, timeout=30):
    """Chaquopy 环境: 用 Java 的 HTTPS 栈请求(TLS指纹与Python不同, 有概率过CF)。"""
    global _JAVA_OK
    if _JAVA_OK is False:
        raise RuntimeError("java layer unavailable")
    try:
        # 延迟导入, 仅 Chaquopy(FongMi) 环境存在
        from java.io import BufferedReader, InputStreamReader
        from java.net import URL
        conn = URL(url).openConnection()
        conn.setConnectTimeout(timeout * 1000)
        conn.setReadTimeout(timeout * 1000)
        conn.setUseCaches(False)
        conn.setRequestProperty("User-Agent", UA_MOB)
        conn.setRequestProperty("Referer", HOST + "/")
        conn.setRequestProperty("Accept-Language", "zh-TW,zh;q=0.9,en;q=0.8")
        conn.setRequestProperty(
            "Accept",
            "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
        code = conn.getResponseCode()
        stream = (conn.getInputStream() if code < 400
                  else conn.getErrorStream())
        body = ""
        if stream is not None:
            reader = BufferedReader(InputStreamReader(stream, "UTF-8"))
            parts = []
            while True:
                line = reader.readLine()
                if line is None:
                    break
                parts.append(line)
                parts.append("\n")
            body = "".join(parts)
            reader.close()
        _JAVA_OK = True
        return code, body
    except ImportError as e:
        _JAVA_OK = False
        raise RuntimeError("no java bridge: %s" % e)
    except Exception as e:
        if _JAVA_OK is None:
            _JAVA_OK = True  # 已能导入, 只是本次网络错误
        raise RuntimeError(str(e)[:120])


def _http(url, retries=None):
    """带指纹轮换/cookie持久化/重试/TTL缓存的 GET。失败抛异常。
    层优先级: curl_cffi(有) -> WebView(无cf且Android) -> java HttpsURLConnection -> requests -> urllib"""
    hit = CACHE.get(url)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]

    # 无 curl_cffi 的环境(如 FongMi/Chaquopy)快速失败, 避免UI干转半分钟
    if _cf is None and retries is None:
        retries = 4
    retries = retries or 6

    t0 = time.time()
    err = None
    layers = []
    if _cf is not None:
        layers.append(("cf", None))
    else:
        # 优先 WebView(真Chromium内核), 失败再试 java/requests/urllib
        layers.append(("webview", None))
        layers.append(("java", None))
        if _rq is not None:
            layers.append(("requests", None))
        layers.append(("urllib", None))

    for i in range(retries):
        kind = layers[min(i // max(1, retries // len(layers)),
                          len(layers) - 1)][0]
        try:
            if kind == "cf":
                global _OK_FP
                fps = [_OK_FP] if _OK_FP else _FPS
                fp = fps[i] if i < len(fps) else fps[-1]
                r = _cf.get(url, impersonate=fp,
                            cookies=_JARS.get(fp) or None,
                            timeout=30,
                            headers={"Referer": HOST + "/",
                                     "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8"})
                ok = r.status_code == 200 and not _looks_like_cf(r.text)
                _log("HTTP#%d [%s fp=%s] %s -> %d len=%d cf=%s %ums"
                     % (i + 1, "curl_cffi", fp, url[:90], r.status_code,
                        len(r.text), _looks_like_cf(r.text),
                        int((time.time() - t0) * 1000)))
                if ok:
                    _OK_FP = fp
                    try:
                        _JARS[fp] = dict(r.cookies.get_dict())
                    except Exception:
                        pass
                    CACHE[url] = (time.time(), r.text)
                    return r.text
                err = "http %s" % r.status_code
            elif kind == "webview":
                body = _wv_fetch(url)
                ok = len(body) > 500 and not _looks_like_cf(body)
                _log("HTTP#%d [webview] %s -> len=%d cf=%s %ums"
                     % (i + 1, url[:90], len(body),
                        _looks_like_cf(body),
                        int((time.time() - t0) * 1000)))
                if ok:
                    CACHE[url] = (time.time(), body)
                    return body
                err = "webview cf/short"
            elif kind == "java":
                code, body = _java_get(url)
                ok = code == 200 and not _looks_like_cf(body)
                _log("HTTP#%d [java] %s -> %d len=%d cf=%s %ums"
                     % (i + 1, url[:90], code, len(body),
                        _looks_like_cf(body),
                        int((time.time() - t0) * 1000)))
                if ok:
                    CACHE[url] = (time.time(), body)
                    return body
                err = "http %s" % code
            elif kind == "requests":
                r = _rq.get(url, timeout=15, headers={
                    "User-Agent": UA_MOB, "Referer": HOST + "/",
                    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8"},
                    cookies=_JARS.get("rq") or None)
                ok = r.status_code == 200 and not _looks_like_cf(r.text)
                _log("HTTP#%d [requests] %s -> %d len=%d cf=%s"
                     % (i + 1, url[:90], r.status_code, len(r.text),
                        _looks_like_cf(r.text)))
                if ok:
                    try:
                        _JARS["rq"] = r.cookies.get_dict()
                    except Exception:
                        pass
                    CACHE[url] = (time.time(), r.text)
                    return r.text
                err = "http %s" % r.status_code
            else:
                req = urllib.request.Request(url, headers={
                    "User-Agent": UA_MOB, "Referer": HOST + "/"})
                with urllib.request.urlopen(req, timeout=20) as resp:
                    body = resp.read().decode("utf-8", "ignore")
                _log("HTTP#%d [urllib] %s -> %s len=%d cf=%s"
                     % (i + 1, url[:90], resp.getcode(), len(body),
                        _looks_like_cf(body)))
                if not _looks_like_cf(body):
                    CACHE[url] = (time.time(), body)
                    return body
                err = "cloudflare challenge"
        except Exception as e:
            err = str(e)[:150]
            _log("HTTP#%d [%s] 异常: %s"
                 % (i + 1, kind, repr(e)[:130]))
        time.sleep(1.2 * (i + 1))
    _log("!! 最终失败 [%s] 共%d次(%s层): %s%s"
         % (url[:90], retries, "/".join(k for k, _ in layers), err,
            "" if _cf is not None else
            " | 提示: 本环境无curl_cffi, Python栈过不了CF"))
    raise RuntimeError("GET fail [%s]: %s" % (url[:80], err))


def _safe(fn, default):
    try:
        return fn()
    except Exception as e:
        print("  [ERR]", str(e)[:150])
        return default


def _ext_dict(extend):
    """extend 可能是 dict / json 字符串 / None"""
    if isinstance(extend, dict):
        return extend
    if isinstance(extend, str) and extend.strip():
        try:
            v = json.loads(extend)
            return v if isinstance(v, dict) else {}
        except Exception:
            return {}
    return {}


# ---------------- 页面解析(纯正则, 无 bs4 依赖) ----------------

_RE_TITLE = re.compile(
    r'<h6 class="title">\s*<a href="(?:https://jable\.tv)?(/videos/[^"]+)"[^>]*>(.*?)</a>',
    re.S)
_RE_BOXPOS = re.compile(r'class="video-img-box')
_RE_PAGECOUNT = re.compile(r'<ul class="pagination.*?</ul>', re.S)


def _clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def _num(s):
    return re.sub(r"[^\d]", "", s or "")


def _parse_items(html):
    """解析列表页视频卡片 → vod 数组"""
    boxes = [m.start() for m in _RE_BOXPOS.finditer(html)]
    out, seen = [], set()
    for m in _RE_TITLE.finditer(html):
        start = 0
        for b in boxes:
            if b <= m.start():
                start = b
            else:
                break
        end = html.find("</p>", m.end())
        end = end + 4 if end > 0 else m.end() + 700
        seg = html[start:end]

        slug = m.group(1).strip("/").split("/")[-1].lower()
        if slug in seen:
            continue
        seen.add(slug)

        pic = ""
        mpic = re.search(r'data-src="([^"]+)"', seg)
        if mpic:
            pic = mpic.group(1)
        else:
            mpic = re.search(r'src="(https://assets-cdn\.jable\.tv[^"]+)"', seg)
            if mpic:
                pic = mpic.group(1)

        mdur = re.search(r'absolute-bottom-right">\s*<span class="label">([^<]+)', seg)
        dur = _clean(mdur.group(1)) if mdur else ""

        nums = re.findall(r"</svg>\s*([\d\s,]+)\s*<", seg)
        views = _num(nums[0]) if nums else ""
        likes = _num(nums[1]) if len(nums) > 1 else ""

        remarks = " ".join(x for x in
                           [("👁" + views) if views else "",
                            ("❤" + likes) if likes else "",
                            dur] if x)

        out.append({
            "vod_id": slug,
            "vod_name": _clean(m.group(2)),
            "vod_pic": pic,
            "vod_remarks": remarks,
            "vod_year": dur,
        })
    return out


def _pagecount(html):
    m = _RE_PAGECOUNT.search(html)
    if not m:
        return 1
    nums = [int(x) for x in re.findall(r">\s*(\d+)\s*<", m.group(0))]
    return max(nums) if nums else 1


def _parse_categories(html):
    """/categories/ 页卡片 → 文件夹数组"""
    out = []
    pat = re.compile(
        r'<a href="(?:https://jable\.tv)?/categories/([a-z0-9-]+)/">'
        r'\s*<div class="overlay"></div>\s*<img src="([^"]*)"'
        r'.*?<h4>(.*?)</h4>\s*<span[^>]*>(.*?)</span>', re.S)
    for m in pat.finditer(html):
        out.append({
            "vod_id": "categories/" + m.group(1),
            "vod_name": _clean(m.group(3)),
            "vod_pic": m.group(2),
            "vod_remarks": _clean(m.group(4)),
            "vod_tag": "folder",
        })
    return out


def _parse_nav_tags(html):
    """导航里的标签分区(衣著/身材/交合...) → 文件夹数组"""
    marks = list(re.finditer(
        r'<div class="title-box">\s*<h2 class="h3-md">([^<]+)</h2>\s*</div>', html))
    out = []
    for i, m in enumerate(marks):
        group = _clean(m.group(1))
        end = marks[i + 1].start() if i + 1 < len(marks) else (
            html.find("</nav>", m.end()) if html.find("</nav>", m.end()) > 0
            else min(m.end() + 20000, len(html)))
        seg = html[m.end():end]
        for t in re.finditer(
                r'<a class="tag text-light" href="(?:https://jable\.tv)?/tags/([a-z0-9-]+)/">([^<]+)</a>',
                seg):
            out.append({
                "vod_id": "tags/" + t.group(1),
                "vod_name": _clean(t.group(2)),
                "vod_remarks": group,
                "vod_tag": "folder",
            })
    return out


# ---------------- 分类与筛选定义 ----------------

SORT_FRESH = [
    {"n": "近期最佳", "v": "&sort_by=post_date_and_popularity"},
    {"n": "最近更新", "v": "&sort_by=post_date"},
    {"n": "最多观看", "v": "&sort_by=video_viewed"},
    {"n": "最高收藏", "v": "&sort_by=most_favourited"},
]
SORT_HOT = [
    {"n": "所有时间", "v": "&sort_by=video_viewed"},
    {"n": "本月热门", "v": "&sort_by=video_viewed_month"},
    {"n": "本周热门", "v": "&sort_by=video_viewed_week"},
    {"n": "今日热门", "v": "&sort_by=video_viewed_today"},
]


def _classes():
    return [
        {"type_id": "latest-updates", "type_name": "🆕 最近更新"},
        {"type_id": "hot", "type_name": "🔥 热门影片"},
        {"type_id": "new-release", "type_name": "💿 全新上市"},
        {"type_id": "categories/chinese-subtitle", "type_name": "🀄 中文字幕"},
        {"type_id": "categories", "type_name": "📚 主题&标签"},
    ]


def _filters():
    return {
        "latest-updates": [{"key": "sort_by", "name": "排序", "value": SORT_FRESH}],
        "new-release": [{"key": "sort_by", "name": "排序", "value": SORT_FRESH}],
        "hot": [{"key": "sort_by", "name": "热度", "value": SORT_HOT}],
        "categories/chinese-subtitle": [{"key": "sort_by", "name": "排序", "value": SORT_FRESH}],
        "categories": [{"key": "sort_by", "name": "排序", "value": SORT_FRESH}],
    }


# KVS 异步接口的 block_id(latest-updates 页与其余页面不同)
def _block_id(tid):
    if tid.startswith("latest-updates"):
        return "list_videos_latest_videos_list"
    if tid.startswith("search"):
        return "list_videos_videos_list_search_result"
    return "list_videos_common_videos_list"


# ---------------- Spider 主类 ----------------

_log_init()  # 模块被加载即记录环境信息


class Spider(object):

    def getName(self):
        return "Jable"

    def init(self, extend=""):
        _log("init(extend=%r)" % (extend,))

    def destroy(self):
        pass

    def isVideoFormat(self, url):
        return False

    def isTextFormat(self, url):
        return False

    def localProxy(self, params):
        return {}

    # ---------- 首页 ----------

    def homeContent(self, filter):
        _log("homeContent(filter=%r)" % (filter,))
        return {"class": _classes(), "filters": _filters(), "list": []}

    def homeVideoContent(self):
        _log("homeVideoContent 进入")
        try:
            html = _http(HOST + "/")
            lst = _parse_items(html)
            _log("homeVideoContent 出来 %d 条" % len(lst))
            return {"list": lst}
        except Exception as e:
            _log("!! homeVideoContent 失败: %s\n%s"
                 % (e, traceback.format_exc(limit=3)))
            return {"list": []}

    # ---------- 分类列表 ----------

    def categoryContent(self, tid, pg, filter, extend):
        _log("categoryContent(tid=%s pg=%s filter=%s extend=%r)"
             % (tid, pg, filter, extend))
        pg = int(pg) if str(pg).strip().isdigit() else 1
        ext = _ext_dict(extend)
        raw = ext.get("sort_by") or ""
        sort_by = raw.split("sort_by=")[-1].strip() if "sort_by=" in raw else ""

        result = {"list": [], "pagecount": 1, "limit": 24, "total": 0}

        # 主题&标签 目录页
        if tid == "categories":
            html = _http(HOST + "/categories/")
            cats = _parse_categories(html)
            tags = _parse_nav_tags(html)
            result["list"] = cats + tags
            result["pagecount"] = 1
            result["total"] = len(result["list"])
            _log("categoryContent[categories] 出目录 %d 项" % len(result["list"]))
            return result

        tid = tid.strip("/")
        base = "%s/%s/" % (HOST, tid)
        try:
            # latest-updates 的路径式分页被服务端忽略, 必须走 KVS async;
            # 带 sort_by 时其余分类也统一走 async
            need_async = bool(sort_by) or tid.startswith("latest-updates")
            if need_async:
                url = ("%s?mode=async&function=get_block&block_id=%s&from=%d"
                       % (base, _block_id(tid), pg))
                if sort_by:
                    url += "&sort_by=" + urllib.parse.quote(sort_by)
                if pg <= 1 and not sort_by:
                    url = base  # 首页直接用完整页(自带分页条)
            else:
                url = base if pg <= 1 else "%s%d/" % (base, pg)
            html = _http(url)
            result["list"] = _parse_items(html)
            result["pagecount"] = _pagecount(html)
            if result["pagecount"] <= 1 and need_async and (pg > 1 or sort_by):
                # async 响应可能不含分页条, 用普通首页补页数(有缓存)
                result["pagecount"] = _safe(
                    lambda: _pagecount(_http(base)), 1)
            result["total"] = result["pagecount"] * 24
            _log("categoryContent[%s] 出 %d 条 pc=%s (url=%s)"
                 % (tid, len(result["list"]), result["pagecount"], url[:90]))
        except Exception as e:
            _log("!! categoryContent[%s] 失败: %s\n%s"
                 % (tid, e, traceback.format_exc(limit=3)))
        return result

    # ---------- 详情 ----------

    def detailContent(self, ids):
        try:
            return self._detail(ids)
        except Exception as e:
            _log("!! detailContent(%r) 失败: %s\n%s"
                 % (ids, e, traceback.format_exc(limit=3)))
            slug = str(ids[0]) if ids else "?"
            return {"list": [{"vod_id": slug, "vod_name": slug.upper(),
                              "vod_content": "详情获取失败: " + str(e)[:100],
                              "vod_play_from": "Jable",
                              "vod_play_url": ""}]}

    def _detail(self, ids):
        slug = str(ids[0]).strip("/").split("/")[-1].lower()
        _log("detailContent 进入 id=%s" % slug)
        html = _http("%s/videos/%s/" % (HOST, slug))

        # 只取正文区(info-header 之后、footer 之前), 避免吃到导航里的同名链接
        k = html.find('class="info-header"')
        region = html[k:] if k > 0 else html
        foot = region.find('id="site-footer"')
        if foot > 0:
            region = region[:foot]

        mhls = re.search(r"hlsUrl\s*=\s*'([^']+)'", html)
        m3u8 = mhls.group(1) if mhls else ""
        mpost = re.search(r'<video[^>]*poster="([^"]+)"', html)
        poster = mpost.group(1) if mpost else ""
        mtitle = re.search(r'<div class="info-header">\s*<div class="header-left">\s*<h4>(.*?)</h4>',
                           html, re.S)
        title = _clean(mtitle.group(1)) if mtitle else slug.upper()

        actors = []
        for m in re.finditer(
                r'<a class="model"[^>]*href="(?:https://jable\.tv)?(/models/[^/"]+/)"'
                r'[^>]*>\s*<span[^>]*title="([^"]*)"', region):
            name = _clean(m.group(2)) or "女优"
            actors.append('[a=cr:%s/]%s[/a]' %
                          (json.dumps({"id": m.group(1).strip("/"),
                                       "name": name},
                                      ensure_ascii=False, separators=(",", ":")),
                           name))

        cats, tags = [], []
        for m in re.finditer(
                r'href="(?:https://jable\.tv)?/(categories/[a-z0-9-]+|tags/[a-z0-9-]+)/"'
                r'[^>]*>([^<]+)</a>', region):
            path, name = m.group(1), _clean(m.group(2))
            link = ('[a=cr:%s/]%s[/a]' %
                    (json.dumps({"id": path, "name": name},
                                ensure_ascii=False, separators=(",", ":")),
                     "#" + name))
            if path.startswith("categories/"):
                cats.append(link)
            else:
                tags.append(link)

        mviews = re.search(r'icon-eye"></use></svg>\s*(?:<span[^>]*>)?\s*([\d\s,]+)', region)
        views = _num(mviews.group(1)) if mviews else ""
        mdate = re.search(r'class="inactive-color">\s*([^<]+)', region)
        date = _clean(mdate.group(1)) if mdate else ""
        mflag = re.search(r'class="header-right[^"]*"[^>]*>\s*<h6>(.*?)</h6>',
                          region, re.S)
        flag = _clean(re.sub(r"<[^>]+>", "", mflag.group(1))) if mflag else "高清原片"

        content_parts = [title]
        if views:
            content_parts.append("👁 " + views)
        if date:
            content_parts.append(date)
        if tags:
            content_parts.append(" ".join(tags))

        vod = {
            "vod_id": slug,
            "vod_name": title,
            "vod_pic": poster,
            "vod_year": date,
            "vod_remarks": flag,
            "vod_actor": " ".join(actors) + ((" " + " ".join(cats)) if cats else ""),
            "vod_content": "\n".join(content_parts),
            "vod_play_from": "Jable_" + flag,
            "vod_play_url": ("第1集$" + m3u8) if m3u8 else "",
        }
        if not m3u8:
            vod["vod_content"] = "未取到播放地址(可能被CF拦截或已下架)" + vod["vod_content"]
            _log("!! detail[%s] 未取到hlsUrl! 页面长度=%d" % (slug, len(html)))
        else:
            _log("detail[%s] OK 标题=%s m3u8=%s" % (slug, title[:40], m3u8[:70]))
        return {"list": [vod]}

    # ---------- 播放 ----------

    def playContent(self, flag, pid, vipFlags):
        headers = {"User-Agent": UA, "Referer": HOST + "/"}
        _log("playContent(flag=%s pid=%s)" % (flag, str(pid)[:90]))
        return {"parse": 0, "playUrl": "", "url": pid, "header": headers}

    playerContent = playContent  # 兼容两种方法名

    # ---------- 搜索 ----------

    def searchContentPage(self, key, quick, pg="1"):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        kw = urllib.parse.quote(str(key).strip())
        url = "%s/search/%s/" % (HOST, kw) if pg <= 1 else "%s/search/%s/%d/" % (HOST, kw, pg)
        try:
            html = _http(url)
            lst = _parse_items(html)
            pc = _pagecount(html)
            _log("search(%s) 出 %d 条 pc=%d" % (key, len(lst), pc))
            return {"list": lst, "pagecount": pc}
        except Exception as e:
            _log("!! search(%s) 失败: %s\n%s"
                 % (key, e, traceback.format_exc(limit=2)))
            return {"list": [], "pagecount": 1}

    def searchContent(self, key, quick, pg="1"):
        return self.searchContentPage(key, quick, 1)



# ---------------- 本地测试入口 ----------------

if __name__ == "__main__":
    sp = Spider()

    def show(name, obj, n=3):
        print("\n===== %s =====" % name)
        s = json.dumps(obj, ensure_ascii=False)
        print(s[:900] + ("..." if len(s) > 900 else ""))

    show("homeContent", sp.homeContent(True))
    hv = _safe(lambda: sp.homeVideoContent(), {})
    print("homeVideo:", len(hv.get("list", [])), "items")

    c1 = _safe(lambda: sp.categoryContent("latest-updates", 1, 1, {}), {})
    print("latest-updates p1:", len(c1.get("list", [])), "pc =", c1.get("pagecount"))
    c2 = _safe(lambda: sp.categoryContent("latest-updates", 1, 1,
                                          {"sort_by": "&sort_by=most_favourited"}), {})
    print("latest-updates fav:", [v["vod_id"] for v in c2.get("list", [])][:3])
    ch = _safe(lambda: sp.categoryContent("hot", 1, 1,
                                          {"sort_by": "&sort_by=video_viewed_today"}), {})
    print("hot today:", [v["vod_id"] for v in ch.get("list", [])][:3])

    cc = _safe(lambda: sp.categoryContent("categories", 1, 1, {}), {})
    print("categories folders:", len(cc.get("list", [])))
    if cc.get("list"):
        fid = cc["list"][0]["vod_id"]
        cf = _safe(lambda: sp.categoryContent(fid, 1, 1, {}), {})
        print("folder[%s]:" % fid, len(cf.get("list", [])), "videos")

    d = _safe(lambda: sp.detailContent(["snos-373"]), {})
    if d.get("list"):
        v = d["list"][0]
        print("detail:", v["vod_name"][:40], "| m3u8:",
              (v["vod_play_url"].split("$", 1)[-1][:60] + "..."))
    s = _safe(lambda: sp.searchContentPage("SNOS", False, 1), {})
    print("search SNOS:", len(s.get("list", [])), "pc =", s.get("pagecount"))
