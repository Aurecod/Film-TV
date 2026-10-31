# coding=utf-8
#!/usr/bin/python
# ============================================================================
#  暗夜蜜桃 · honeypeach.cc   —— TVBox / 蜂蜜影视 专用 Python 源 (type 3)
# ----------------------------------------------------------------------------
#  覆盖分组(站点首页有几个就接几个):
#     🔴 蜜桃直播   🎬 蜜桃短剧   💋 擦边短剧   📺 蜜桃视频
#     🎭 蜜桃动漫   🇨🇳 国产精品   🍉 黑料吃瓜
#
#  接口(站点前端公开接口):
#     GET /api/handshake?dev=xxx        → 下发 {sid, skey, exp},之后 /api/* 必须带签名
#     签名头: X-Hp-Sid / X-Hp-Ts / X-Hp-Nonce / X-Hp-Sign
#     canon = method + "\n" + path + "\n" + query + "\n" + sha256(body) + "\n"
#             + ts + "\n" + nonce + "\n" + sid      (HMAC-SHA256,key = skey 的字节)
#
#     首页   /api/home
#     分类   /api/cats?key=&v=3
#     列表   /api/module?key=&cat=&src=&sub=&page=
#     详情   /api/detail/<key>/<id>?src=
#     播放   /api/play/<key>/<id>/<ep>?src=      → {src, src_proxy, type}
#     搜索   /api/search?key=&kw=&page=          (直播 / 黑料不开放搜索)
#     弹幕   /api/comments/live/<主播id>
#
#  播放线路:每条给三路 —— ① 站内直连 ② 站内中转 ③ 本地智能转发。
#     播放地址里的票据 t= 大约 3 分钟作废,③ 每次请求都重新取票,
#     长时间挂着看 / 反复拉进度条都不会失效;某条不灵切下一条即可。
#
#  限流自愈(重要):
#     站点对每个会话(sid)有请求配额,超了接口会回 err=rl_sid。
#     表现就是分组点进去全是空白。本源遇到限流会自动换会话重签并重放,
#     同时分类表 / 首页模块 / 列表结果都带缓存,正常情况下点分组几乎不消耗配额。
#
#  配置(写在配置 json 的 ext 里,不写就用默认值):
#     {
#       "host": "https://honeypeach.cc",   // 换域名
#       "ua": "...",                       // 换 UA
#       "danmaku": true,                    // 直播弹幕开关
#       "timeout": 15,                      // 单次请求超时(秒)
#       "cache": true,                      // 关掉=不吃本地缓存
#       "filters": true,                    // 关掉=各分组不带筛选下拉(排障用)
#       "video_filters": true               // 关掉=蜜桃视频不带 类型/女优/发行商
#     }
# ============================================================================

import hashlib
import hmac
import json
import os
import random
import re
import string
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.append('..')

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        def log(self, msg):
            pass

try:
    import requests
except Exception:
    requests = None


# ------------------------------ 常量 ----------------------------------------

DEFAULT_HOST = "https://honeypeach.cc"

UA = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")

# 分组清单(key, 兜底名)。站点 /api/home 拉不到时也能正常出分组。
MODULES = [
    ("live", "🔴蜜桃直播"),
    ("duanju", "🎬蜜桃短剧"),
    ("caibian", "💋擦边短剧"),
    ("video", "📺蜜桃视频"),
    ("shortv", "🎭蜜桃动漫"),
    ("guochan", "🇨🇳国产精品"),
    ("heiliao", "🍉黑料吃瓜"),
]
VALID_KEYS = tuple(k for k, _ in MODULES)

# 能搜索的分组(其余后端会 400)
SEARCH_MODULES = ["video", "duanju", "caibian", "shortv", "guochan"]

# 短剧类分组的默认上游(详情 / 播放必须带对,否则拿不到集数和地址)
DEFAULT_SRC = {
    "duanju": "huangguo",
    "caibian": "huangdou",
    "heiliao": "huangdou",
}

# /cover/<x>? 里能出现的上游名,可用来反推真实 src
SRC_NAMES = ("huangguo", "huangdou", "missav", "dongman", "guochan", "video")

# 分组默认分类(拿不到 /api/cats 时兜底)
DEFAULT_CAT = {
    "live": "girls",
    "duanju": "tuijian",
    "caibian": "0",
    "video": "new",
    "shortv": "all",
    "guochan": "",
    "heiliao": "0",
}


# ------------------------------ 小工具 --------------------------------------

def _s(v):
    """任何值 → 干净字符串。"""
    if v is None:
        return ''
    if isinstance(v, (dict, list, tuple)):
        return ''
    return str(v).strip()


def _as_dict(v):
    """extend 参数归一化:None / 空串 / JSON 字符串 / URL 编码 JSON / dict / list 全吃。"""
    if isinstance(v, dict):
        return v
    if isinstance(v, (list, tuple)):
        # 少数内核会传 [{key,value}] 这种结构
        out = {}
        for it in v:
            if isinstance(it, dict):
                k = it.get('key') or it.get('k')
                val = it.get('value', it.get('v'))
                if k:
                    out[str(k)] = val
        return out
    if isinstance(v, str):
        t = v.strip()
        if not t:
            return {}
        for cand in (t, urllib.parse.unquote(t)):
            if cand[:1] in '{[':
                try:
                    d = json.loads(cand)
                    if isinstance(d, dict):
                        return d
                except Exception:
                    pass
        return {}
    return {}


def _to_int(v, dft=0, low=None, high=None):
    try:
        n = int(float(str(v).strip()))
    except Exception:
        n = dft
    if low is not None and n < low:
        n = low
    if high is not None and n > high:
        n = high
    return n


def _looks_like_garbage(v):
    """判断一个筛选值是不是 JSON 串被当字符串用剩下的垃圾。"""
    t = _s(v)
    if not t:
        return False
    if any(c in t for c in '{}\'"') and ':' in t:
        return True
    if ' ' in t and (',' in t or ':' in t):
        return True
    return len(t) > 60


# ------------------------------ 主体 ----------------------------------------

class Spider(BaseSpider):

    # ---- 类级默认值:即使 init() 没被调、或实例被并发使用,也不会有属性缺失 ----
    host = DEFAULT_HOST
    ua = UA
    timeout = 15
    danmaku_on = True
    filters_on = True
    video_filters_on = True

    _ready = False
    _sid = ""
    _skey = b""
    _skexp = 0
    _dev = ""
    _sess = None
    _boot_lock = threading.RLock()

    # ---------------- 启动 / 配置 ----------------

    def _ensure(self):
        """幂等初始化:标志位最后才置位,避免并发下拿到半成品实例。"""
        if self._ready:
            return
        with Spider._boot_lock:
            if self._ready:
                return
            self._sid = _s(getattr(self, '_sid', ''))
            self._skey = self._skey if isinstance(self._skey, bytes) else b''
            self._skexp = _to_int(getattr(self, '_skexp', 0), 0)
            self._sign_lock = threading.RLock()
            self._cat_cache = {}
            self._cat_lock = threading.RLock()
            self._home_cache = None
            self._filter_defaults = {}   # 分组 → {筛选键: 默认值}(判断下拉是否被改过)
            self._cat_defaults = {}      # 分组 → (分类, 上游, sub)
            self._api_cache = {}         # 接口结果缓存(带 TTL)
            self._disk_done = False
            self._last_err = ''
            self._ready = True

    def init(self, extend="", ext=None, *args, **kwargs):
        self._ensure()
        if ext is None:
            ext = kwargs.get('extend')
        cfg = {}
        if isinstance(extend, dict):
            cfg = extend
        elif isinstance(extend, str) and extend.strip():
            cfg = _as_dict(extend)
        if isinstance(ext, dict):
            cfg = dict(cfg)
            cfg.update(ext)
        elif isinstance(ext, str) and ext.strip():
            d = _as_dict(ext)
            cfg = dict(cfg)
            cfg.update(d)

        host = _s(cfg.get('host') or cfg.get('site') or cfg.get('domain'))
        if host:
            if not host.startswith('http'):
                host = 'https://' + host
            self.host = host.rstrip('/')
        ua = _s(cfg.get('ua'))
        if ua:
            self.ua = ua
        self.timeout = _to_int(cfg.get('timeout') or 15, 15, 3, 60)
        self.danmaku_on = bool(cfg.get('danmaku', True))
        # filters=false 时不出筛选下拉(个别内核筛选解析有毛病的排障开关)
        self.filters_on = bool(cfg.get('filters', True))
        self.video_filters_on = bool(cfg.get('video_filters', True))
        # cache=false 时不吃本地缓存(站点改版后想立刻看到新数据时用)
        self.cache_on = bool(cfg.get('cache', True))
        self.log('暗夜蜜桃 · 源已加载 host=%s' % self.host)

    def getName(self):
        return "暗夜蜜桃"

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def destroy(self):
        try:
            if getattr(self, '_sess', None) is not None:
                self._sess.close()
        except Exception:
            pass
        return None

    # ---------------- 网络层 ----------------

    def _session(self):
        s = getattr(self, '_sess', None)
        if s is not None:
            return s
        if requests is None:
            self._sess = None
            return None
        try:
            s = requests.Session()
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
            rt = Retry(total=2, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
            ad = HTTPAdapter(max_retries=rt, pool_connections=10, pool_maxsize=20)
            s.mount('http://', ad)
            s.mount('https://', ad)
            self._sess = s
        except Exception:
            self._sess = None
        return self._sess

    def _req(self, url, headers=None, data=None, method=None, timeout=None):
        """返回 (status, bytes);任何异常都吞掉转成 (0, b'')。"""
        h = {"User-Agent": self.ua, "Accept": "application/json, text/plain, */*"}
        if headers:
            h.update(headers)
        to = timeout or self.timeout
        sess = self._session()
        if sess is not None:
            try:
                r = sess.request(method or ("POST" if data else "GET"), url,
                                 headers=h, data=data, timeout=to, allow_redirects=True)
                return r.status_code, r.content
            except Exception as e:
                self.log('请求失败 %s: %s' % (url.split('?')[0], e))
                return 0, b''
        try:
            rq = urllib.request.Request(url, headers=h, data=data, method=method)
            with urllib.request.urlopen(rq, timeout=to) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            try:
                return e.code, e.read()
            except Exception:
                return e.code, b''
        except Exception as e:
            self.log('请求失败 %s: %s' % (url.split('?')[0], e))
            return 0, b''

    def _json(self, url, headers=None, timeout=None):
        st, body = self._req(url, headers=headers, timeout=timeout)
        if not body:
            return {}
        try:
            d = json.loads(body.decode('utf-8', 'replace'))
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}

    # ---------------- 握手 / 签名 ----------------

    def _dev_file(self, name):
        """配置/缓存文件落点:优先跟源同目录,不可写就退到临时目录。"""
        base = getattr(self, '_dev_dir', None)
        if base is None:
            base = ''
            cands = []
            try:
                cands.append(os.path.dirname(os.path.abspath(__file__)))
            except Exception:
                pass
            try:
                import tempfile
                cands.append(tempfile.gettempdir())
            except Exception:
                pass
            cands += [os.path.expanduser('~'), os.getcwd(), '/sdcard']
            for cand in cands:
                try:
                    if not cand or not os.path.isdir(cand):
                        continue
                    probe = os.path.join(cand, '.hani.w')
                    fh = open(probe, 'w')
                    fh.write('1')
                    fh.close()
                    os.remove(probe)
                    base = cand
                    break
                except Exception:
                    continue
            self._dev_dir = base
        return os.path.join(base, name) if base else ''

    def _dev_id(self):
        if self._dev:
            return self._dev
        path = self._dev_file('.hani.dev')
        if path:
            try:
                if os.path.exists(path):
                    d = open(path, 'r').read().strip()
                    if d:
                        self._dev = d
                        return d
            except Exception:
                pass
        d = 'zp' + ''.join(random.choice(string.ascii_lowercase + string.digits)
                           for _ in range(24))
        if path:
            try:
                fh = open(path, 'w')
                fh.write(d)
                fh.close()
            except Exception:
                pass
        self._dev = d
        return d

    # 握手结果落盘:某些内核每个请求新建实例,这样不用反复握手
    def _load_sign_cache(self):
        path = self._dev_file('.hani.sk')
        if not path:
            return False
        try:
            if not os.path.exists(path):
                return False
            parts = open(path, 'r').read().strip().split('|')
            if len(parts) != 4:
                return False
            dev, sid, key, exp = parts
            if dev != self._dev_id():
                return False
            if _to_int(exp, 0) - 180 < time.time():
                return False
            self._sid = sid
            self._skey = bytes.fromhex(key)
            self._skexp = _to_int(exp, 0)
            return bool(self._sid and self._skey)
        except Exception:
            return False

    def _save_sign_cache(self):
        path = self._dev_file('.hani.sk')
        if not path:
            return
        try:
            fh = open(path, 'w')
            fh.write('%s|%s|%s|%s' % (self._dev_id(), self._sid,
                                      self._skey.hex(), self._skexp))
            fh.close()
        except Exception:
            pass

    def _handshake(self, force_new_dev=False):
        """握手;失败自动重试,任何情况都不往外抛异常。"""
        if force_new_dev:
            self._dev = ''
            self._dev_id()
        last = ''
        for attempt in range(3):
            try:
                url = self.host + '/api/handshake?dev=' + urllib.parse.quote(self._dev_id())
                d = self._json(url, timeout=min(self.timeout, 12))
                if d.get('skey') and d.get('sid'):
                    self._sid = _s(d.get('sid'))
                    self._skey = bytes.fromhex(_s(d.get('skey')))
                    self._skexp = _to_int(d.get('exp'), 0)
                    self._save_sign_cache()
                    return True
                last = _s(d.get('err')) or 'skey/sid 为空'
            except Exception as e:
                last = str(e)
            time.sleep(0.3 * (attempt + 1))
        self.log('握手失败: %s' % last)
        return False

    def _ensure_sign(self, force=False):
        with self._sign_lock:
            if self._skey and not force and time.time() < (self._skexp - 120):
                return True
            if not force and not self._skey and self._load_sign_cache():
                return True
            if self._handshake(force_new_dev=force):
                return True
            # 再兜一次:换个设备号重新握手(避开服务端对单个 dev 的偶发拒绝)
            if not force:
                return self._handshake(force_new_dev=True)
            return False

    # 站点有按会话(sid)的限流:被限时接口会回 err=rl_sid。换一个设备号重新握手
    # 立刻就能恢复,所以这里遇到限流就轮换签名再重放。
    RL_ERRS = ('rl_sid', 'rl_dev', 'rl_ip', 'rl', 'rate', 'limit', 'toomany', 'busy')
    # 缓存时长(秒):播放地址带票据,绝不能缓存;列表短缓存;分类/首页模块长缓存
    CACHE_TTL = {
        '/api/home': 21600,
        '/api/cats': 21600,
        '/api/module': 90,
        '/api/detail': 600,
        '/api/search': 120,
        '/api/comments': 3,
    }

    def _rotate_dev(self):
        """换一个设备号(相当于换会话,绕开按 sid 的限流)。"""
        with self._sign_lock:
            self._dev = 'zp' + ''.join(random.choice(string.ascii_lowercase + string.digits)
                                       for _ in range(24))
            path = self._dev_file('.hani.dev')
            if path:
                try:
                    fh = open(path, 'w')
                    fh.write(self._dev)
                    fh.close()
                except Exception:
                    pass
            self._sid = ''
            self._skey = b''
            self._skexp = 0
        return True

    def _sign(self, path, params):
        """单次签名请求,返回 (data, err)。"""
        p = {}
        for k, v in (params or {}).items():
            v = _s(v)
            if v == '':
                continue
            p[k] = v
        qs = urllib.parse.urlencode(p)
        if not self._ensure_sign():
            return {}, 'nosign'
        ts = str(int(time.time()))
        nonce = ''.join(random.choice(string.ascii_lowercase + string.digits)
                        for _ in range(16))
        bh = hashlib.sha256(b'').hexdigest()
        canon = "GET\n%s\n%s\n%s\n%s\n%s\n%s" % (path, qs, bh, ts, nonce, self._sid)
        sig = hmac.new(self._skey, canon.encode('utf-8'), hashlib.sha256).hexdigest()
        url = self.host + path + (('?' + qs) if qs else '')
        st, body = self._req(url, headers={
            "X-Hp-Sid": self._sid,
            "X-Hp-Ts": ts,
            "X-Hp-Nonce": nonce,
            "X-Hp-Sign": sig,
            "Referer": self.host + '/',
        })
        d = {}
        if body:
            try:
                d = json.loads(body.decode('utf-8', 'replace'))
            except Exception:
                d = {}
        if not isinstance(d, dict):
            d = {}
        err = _s(d.get('err'))
        if not err and st == 429:
            err = 'rl_sid'
        self._last_err = err
        return d, err

    def _cache_ttl(self, path):
        for pfx, ttl in self.CACHE_TTL.items():
            if path.startswith(pfx):
                return ttl
        return 0

    def _cache_key(self, path, params):
        items = sorted((_s(k), _s(v)) for k, v in (params or {}).items() if _s(v))
        return path + '?' + '&'.join('%s=%s' % kv for kv in items)

    def _cache_get(self, key, allow_stale=False):
        c = getattr(self, '_api_cache', None) or {}
        hit = c.get(key)
        if not hit:
            return None
        ts, ttl, data = hit
        age = time.time() - ts
        if age <= ttl:
            return data
        if allow_stale and age <= 1800:      # 被限流时,30 分钟内的旧数据也能顶一下
            return data
        return None

    def _cache_put(self, key, data, ttl):
        if ttl <= 0 or not isinstance(data, dict) or not data:
            return
        if not (data.get('list') or data.get('cats') or data.get('modules')):
            return                            # 空结果不进缓存
        c = getattr(self, '_api_cache', None)
        if c is None:
            c = self._api_cache = {}
        if len(c) > 400:
            c.clear()
        c[key] = (time.time(), ttl, data)
        if key.startswith('/api/cats') or key.startswith('/api/home'):
            self._disk_put(key, data)

    # 分类表 / 首页模块 / 首页筛选 落盘:下次启动直接复用,首页几乎不发请求
    def _disk_path(self):
        return self._dev_file('.hani.cache.json')

    def _disk_raw(self):
        path = self._disk_path()
        if not path or not os.path.exists(path):
            return {}
        try:
            raw = json.loads(open(path, 'r').read() or '{}')
            return raw if isinstance(raw, dict) else {}
        except Exception:
            return {}

    def _disk_load(self):
        if getattr(self, '_disk_done', False):
            return
        self._disk_done = True
        c = getattr(self, '_api_cache', None)
        if c is None:
            c = self._api_cache = {}
        now = time.time()
        for k, v in self._disk_raw().items():
            if k.startswith('/api/') and isinstance(v, list) and len(v) == 3:
                ts, ttl, data = v
                if isinstance(data, dict) and now - _to_int(ts, 0) <= _to_int(ttl, 0):
                    c[k] = (ts, ttl, data)

    def _disk_set(self, key, data, ttl):
        path = self._disk_path()
        if not path:
            return
        try:
            raw = self._disk_raw()
            raw[key] = [time.time(), ttl, data]
            if len(raw) > 40:
                raw = dict(list(raw.items())[-40:])
            fh = open(path, 'w')
            fh.write(json.dumps(raw, ensure_ascii=False))
            fh.close()
        except Exception:
            pass

    def _disk_get(self, key, ttl):
        v = self._disk_raw().get(key)
        if not v:
            return None
        if not (isinstance(v, list) and len(v) == 3):
            return None
        ts, t, data = v
        if time.time() - _to_int(ts, 0) > _to_int(t, ttl):
            return None
        return data

    def _disk_put(self, key, data):
        self._disk_set(key, data, self._cache_ttl(key) or 21600)

    def _api(self, path, params=None, _retry=1, _rotate=2):
        """带签名 + 缓存 + 限流自愈的 /api/* 请求。失败一律返回 {},绝不抛异常。"""
        try:
            ttl = self._cache_ttl(path) if getattr(self, 'cache_on', True) else 0
            if ttl > 0:
                self._disk_load()
                ck = self._cache_key(path, params)
                hit = self._cache_get(ck)
                if hit is not None:
                    return hit
            else:
                ck = ''

            d, err = self._sign(path, params)

            if err in ('nosig', 'nosign', 'badsig', 'expired') and _retry > 0:
                self._ensure_sign(True)
                return self._api(path, params, _retry - 1, _rotate)

            if err in self.RL_ERRS and _rotate > 0:
                # 被限流:换会话重来(实测换 dev 重签立即恢复)
                self.log('接口被限流(%s),轮换会话重试' % err)
                self._rotate_dev()
                time.sleep(0.3)
                return self._api(path, params, _retry, _rotate - 1)

            if err:
                self.log('接口返回错误 %s: %s' % (path, err))
                if ck:
                    stale = self._cache_get(ck, allow_stale=True)
                    if stale is not None:
                        return stale
                return {}

            # 站点在 IP 级限流时会"返回空列表但不报错",这时用旧缓存顶上,别给用户空白
            if ck and ttl > 0 and not (d.get('list') or d.get('cats') or d.get('modules')):
                stale = self._cache_get(ck, allow_stale=True)
                if stale is not None:
                    return stale

            if ck and ttl > 0:
                self._cache_put(ck, d, ttl)
            return d
        except Exception as e:
            self.log('接口异常 %s: %s' % (path, e))
            return {}

    def _api_list(self, path, params=None):
        d = self._api(path, params)
        lst = [x for x in (d.get('list') or []) if isinstance(x, dict)]
        return lst, d

    # ---------------- 本地代理地址 ----------------

    def _px_base(self):
        try:
            u = self.getProxyUrl()
            if u:
                return str(u)
        except Exception:
            pass
        return 'http://127.0.0.1:9978/proxy'

    def _px(self, **kw):
        base = self._px_base()
        sep = '&' if '?' in base else '?'
        return base + sep + urllib.parse.urlencode(kw)

    # ---------------- 小工具 ----------------

    def _abs(self, u):
        u = _s(u)
        if not u:
            return ''
        if u.startswith('//'):
            return 'https:' + u
        if u.startswith('/'):
            return self.host + u
        return u

    def _norm_tid(self, tid):
        """分组ID归一:key / 中文名 / 带 emoji 的名字都能认出来。"""
        t = _s(tid)
        if t in VALID_KEYS:
            return t
        for k, name in MODULES:
            if k and k in t:
                return k
        core = re.sub(r'[^0-9A-Za-z\u4e00-\u9fff]+', '', t)
        if core:
            for k, name in MODULES:
                n = re.sub(r'[^0-9A-Za-z\u4e00-\u9fff]+', '', name)
                if n and (n in core or core in n):
                    return k
        return t or 'video'

    def _pack(self, key, src, vid, ep):
        return "%s|%s|%s|%s" % (key, src or '', vid, ep if ep is not None else 1)

    def _split_vod(self, s):
        p = _s(s).split('|')
        if len(p) >= 3:
            return self._norm_tid(p[0]), p[1], p[2]
        return 'video', '', _s(s)

    def _split_play(self, s):
        p = _s(s).split('|')
        if len(p) >= 4:
            return self._norm_tid(p[0]), p[1], p[2], p[3]
        if len(p) == 3:
            return self._norm_tid(p[0]), p[1], p[2], '1'
        return 'video', '', _s(s), '1'

    def _guess_src(self, mod, item):
        """详情 / 播放必须带对上游 src;列表里没有就按封面路径反推。"""
        s = _s((item or {}).get('src'))
        if s:
            return s
        cov = _s((item or {}).get('cover'))
        m = re.match(r'^/cover/([^?/]+)\?', cov)
        if m:
            c = m.group(1)
            if c in ('huangguo', 'huangdou') and mod in ('duanju', 'caibian', 'heiliao'):
                return c
        return DEFAULT_SRC.get(mod, '')

    def _brief(self, mod, src, x):
        return {
            "vod_id": "%s|%s|%s" % (mod, src or '', _s(x.get('id'))),
            "vod_name": _s(x.get('title') or x.get('name')),
            "vod_pic": self._abs(x.get('cover')),
            "vod_remarks": _s(x.get('remark')),
            "vod_content": _s(x.get('desc')),
        }

    # ---------------- 首页 / 分类 ----------------

    def _home_modules(self):
        if self._home_cache is not None:
            return self._home_cache
        out = {}
        try:
            d = self._api('/api/home')
            for m in (d.get('modules') or []):
                if isinstance(m, dict) and m.get('key'):
                    out[_s(m['key'])] = _s(m.get('icon')) + _s(m.get('name') or m['key'])
        except Exception as e:
            self.log('首页模块拉取失败: %s' % e)
        self._home_cache = out
        return out

    def _cats_of(self, key):
        """分组分类表;并发只拉一次。"""
        cache = getattr(self, '_cat_cache', None)
        if cache is None:
            cache = self._cat_cache = {}
        if key in cache:
            return cache[key]
        with self._cat_lock:
            if key in cache:
                return cache[key]
            cats = []
            try:
                d = self._api('/api/cats', {'key': key, 'v': 3}, )

                cats = [c for c in (d.get('cats') or []) if isinstance(c, dict)]
            except Exception as e:
                self.log('分类拉取失败 %s: %s' % (key, e))
            if cats:                     # 空结果(限流/抖动)别缓存,下次还能重试
                cache[key] = cats
            return cats

    def _default_cat(self, key):
        """该分组的默认分类(第一个可用分类)。"""
        dft = getattr(self, '_cat_defaults', None)
        if dft is None:
            dft = self._cat_defaults = {}
        if key in dft:
            return dft[key]
        cat, src, sub = DEFAULT_CAT.get(key, ''), DEFAULT_SRC.get(key, ''), 0
        for c in self._cats_of(key):
            code = _s(c.get('code'))
            if code:
                cat = code
                src = _s(c.get('src')) or src
                sub = _to_int(c.get('sub'), 0)
                break
        dft[key] = (cat, src, sub)
        return dft[key]

    def _tag_options(self, cat_code, limit=200):
        """蜜桃视频的「类型 / 女优 / 发行商」二级入口。"""
        out = []
        try:
            lst, _ = self._api_list('/api/module',
                                    {'key': 'video', 'cat': cat_code, 'page': 1})
            for x in lst:
                code = _s(x.get('code'))
                if not code:
                    continue
                out.append({"n": _s(x.get('name')) or code, "v": code})
                if len(out) >= limit:
                    break
        except Exception as e:
            self.log('二级入口拉取失败 %s: %s' % (cat_code, e))
        return out

    def homeContent(self, filter=True):
        self._ensure()
        try:
            mods = self._home_modules()
            classes = []
            for key, fallback in MODULES:
                classes.append({"type_id": key,
                                "type_name": mods.get(key) or fallback})

            filters = {}
            if not self.filters_on:
                return {"class": classes, "filters": {}}

            # 筛选结构整块落盘缓存:下次启动直接复用,不再打那十几个请求
            # (站点按会话限流,首页请求越少越稳)
            if getattr(self, 'cache_on', True):
                cached = self._disk_get('home_filters', 21600)
                if isinstance(cached, dict) and cached:
                    for k, v in cached.items():
                        if isinstance(v, list) and v:
                            filters[k] = v
                            self._filter_defaults[k] = {
                                f.get('key'): (f.get('value') or [{}])[0].get('v')
                                for f in v if f.get('value')}
                    if len(filters) == len(MODULES):
                        return {"class": classes, "filters": filters}

            # 各分组分类表并发拉,避免首屏被串行请求拖超时
            boxes = {}

            def _work(k):
                try:
                    boxes[k] = self._cats_of(k)
                except Exception:
                    boxes[k] = []

            ts = [threading.Thread(target=_work, args=(k,)) for k, _ in MODULES]
            for t in ts:
                t.daemon = True
                t.start()
            for t in ts:
                t.join(8)

            for key, _ in MODULES:
                opts = []
                dflt = None
                for c in boxes.get(key) or []:
                    if c.get('kind') in ('tags', 'actress', 'todo'):
                        continue        # 这三个是二级入口,单独做下拉
                    code = _s(c.get('code'))
                    label = _s(c.get('name')) or code or '全部'
                    val = json.dumps({"c": code, "s": _s(c.get('src')),
                                      "b": _to_int(c.get('sub'), 0)},
                                     ensure_ascii=False)
                    if dflt is None:
                        dflt = val
                    opts.append({"n": label, "v": val})
                if not opts:
                    val = json.dumps({"c": DEFAULT_CAT.get(key, ''),
                                      "s": DEFAULT_SRC.get(key, ''), "b": 0},
                                     ensure_ascii=False)
                    opts = [{"n": "全部", "v": val}]
                    dflt = val
                flt = [{"key": "cat", "name": "分类", "value": opts}]
                self._filter_defaults[key] = dict(self._filter_defaults.get(key) or {})
                self._filter_defaults[key]['cat'] = dflt or ''

                if key == 'video' and self.video_filters_on:
                    try:
                        for kk, nm, cc in (("tag", "类型", "genres"),
                                           ("actress", "女优", "actresses-ranking"),
                                           ("maker", "发行商", "makers")):
                            vals = self._tag_options(cc)
                            if vals:
                                flt.append({"key": kk, "name": nm, "value": vals})
                                self._filter_defaults[key][kk] = vals[0]['v']
                    except Exception as e:
                        self.log('二级入口构建失败: %s' % e)
                filters[key] = flt

            if getattr(self, 'cache_on', True) and len(filters) == len(MODULES):
                self._disk_set('home_filters', filters, 21600)
            return {"class": classes, "filters": filters}
        except Exception as e:
            self.log('homeContent 异常: %s' % e)
            return {"class": [{"type_id": k, "type_name": n} for k, n in MODULES],
                    "filters": {}}

    def homeVideoContent(self):
        """首页推荐位。站点有按会话限流,这里只发一次请求,省配额。"""
        self._ensure()
        vlist = []
        try:
            for mod, cat in (('video', 'new'), ('duanju', 'tuijian'),
                             ('guochan', ''), ('shortv', 'all'), ('heiliao', '0')):
                lst, _ = self._api_list('/api/module',
                                        {'key': mod, 'cat': cat, 'page': 1,
                                         'src': DEFAULT_SRC.get(mod, '')})
                if lst:
                    for x in lst[:12]:
                        vlist.append(self._brief(mod, self._guess_src(mod, x), x))
                    break
                if getattr(self, '_last_err', ''):
                    break
        except Exception as e:
            self.log('推荐位拉取失败: %s' % e)
        return {"list": vlist}

    def _parse_filter(self, key, extend):
        """把内核传下来的筛选值,解析成 (cat, src, sub)。各种传法都吃得下。"""
        ext = _as_dict(extend)
        if not ext and isinstance(extend, str) and extend.strip():
            ext = {'cat': extend.strip()}          # 裸值当分类用

        def raw(k):
            v = ext.get(k)
            if isinstance(v, (list, tuple)):
                v = v[0] if v else ''
            return v

        tmp = {}
        for k in ('cat', 'tag', 'actress', 'maker'):
            v = raw(k)
            if isinstance(v, dict):                 # 内核把 JSON 解析成对象了
                tmp[k] = _s(v.get('c') if v.get('c') is not None else v.get('code'))
                tmp[k + '_src'] = _s(v.get('s') or v.get('src'))
                tmp[k + '_sub'] = _to_int(v.get('b', v.get('sub')), 0)
                continue
            t = _s(v)
            if not t:
                continue
            if t[:1] in '{[' or '%7B' in t.upper():
                o = _as_dict(t)
                if o:
                    tmp[k] = _s(o.get('c') if o.get('c') is not None else o.get('code'))
                    tmp[k + '_src'] = _s(o.get('s') or o.get('src'))
                    tmp[k + '_sub'] = _to_int(o.get('b', o.get('sub')), 0)
                    continue
                m = re.search(r'["\']c["\']\s*:\s*["\']([^"\']*)["\']', t)
                if m:
                    tmp[k] = m.group(1)
                    continue
            if _looks_like_garbage(t):
                continue
            tmp[k] = t

        dflt = (getattr(self, '_filter_defaults', None) or {}).get(key) or {}
        picked, picked_k = '', ''
        # 二级筛选(类型/女优/发行商)优先于普通分类,只要它不是默认值
        for k in ('tag', 'actress', 'maker'):
            v = tmp.get(k)
            if v and v != dflt.get(k):
                picked, picked_k = v, k
                break
        if not picked:
            c = tmp.get('cat')
            if c and (c != _json_cat(dflt.get('cat')) or not dflt.get('cat')):
                picked, picked_k = c, 'cat'
        if not picked:
            dc, dsrc, dsub = self._default_cat(key)
            return dc, dsrc, dsub
        src = tmp.get(picked_k + '_src') or ''
        sub = _to_int(tmp.get(picked_k + '_sub'), 0)
        if not src and picked_k == 'cat':
            src = DEFAULT_SRC.get(key, '')
        if picked_k != 'cat':
            src = ''          # 二级入口走各自主上游
        return picked, src, sub

    def _empty_page(self, page):
        return {"list": [], "page": page, "pagecount": page,
                "limit": 30, "total": 0}

    def categoryContent(self, tid, pg="1", filter=None, extend=None, *args, **kwargs):
        try:
            self._ensure()
            key = self._norm_tid(tid)
            page = _to_int(pg, 1, 1)
            try:
                cat, src, sub = self._parse_filter(key, extend)
            except Exception as e:
                self.log('筛选解析失败,改用默认: %s' % e)
                cat, src, sub = self._default_cat(key)

            plans = [(cat, src, sub)]
            if page == 1:
                dc, dsrc, dsub = self._default_cat(key)
                for p in ((dc, dsrc, dsub), ('', '', 0)):
                    if p not in plans:
                        plans.append(p)
            plans = plans[:3]

            first = None
            for (c, s, b) in plans:
                lst, d = self._api_list('/api/module',
                                        {'key': key, 'cat': c, 'src': s,
                                         'sub': b, 'page': page})
                if first is None:
                    first = d
                if lst:
                    vlist = [self._brief(key, _s(x.get('src')) or s, x) for x in lst]
                    pages = _to_int(d.get('pages'), 0, 0)
                    if pages > 0:
                        pagecount = pages
                    elif d.get('has_more'):
                        pagecount = page + 1
                    else:
                        pagecount = page
                    return {"list": vlist, "page": page, "pagecount": pagecount,
                            "limit": len(vlist), "total": pagecount * max(len(vlist), 1)}
                # 被限流 / 网络错就别接着刷了,否则只会把会话打得更死
                if getattr(self, '_last_err', ''):
                    self.log('列表拉取受挫(%s),停止兜底重试' % self._last_err)
                    break

            # 一条都没拿到:第 1 页给个空页提示,翻页越界就直接回空
            d = first or {}
            pagecount = _to_int(d.get('pages'), 0, 0) or page
            if page > 1 and pagecount >= page:
                pagecount = page
            return {"list": [], "page": page, "pagecount": pagecount,
                    "limit": 30, "total": 0}
        except Exception as e:
            self.log('categoryContent 异常 %s: %s' % (tid, e))
            return self._empty_page(_to_int(pg, 1, 1))

    # ---------------- 详情 ----------------

    def detailContent(self, array=None, *args, **kwargs):
        try:
            self._ensure()
            ids = ''
            if isinstance(array, (list, tuple)):
                ids = _s(array[0]) if array else ''
            else:
                ids = _s(array)
            if not ids:
                ids = _s(kwargs.get('ids') or kwargs.get('id'))
            if not ids:
                return {"list": []}

            key, src, vid = self._split_vod(ids)
            if not src:
                src = DEFAULT_SRC.get(key, '')
            params = {'src': src} if src else {}
            d = self._api('/api/detail/%s/%s' % (key, urllib.parse.quote(vid)), params)
            det = d.get('detail') or {}
            if not isinstance(det, dict) or not det:
                self.log('详情为空 %s' % ids)
                return {"list": []}

            eps = det.get('episodes') or []
            ep_list = []
            for i, e in enumerate(eps):
                if not isinstance(e, dict):
                    continue
                ep = e.get('ep') or (i + 1)
                nm = _s(e.get('name')) or ('第%s集' % ep)
                if e.get('lock') or e.get('vip') or e.get('price'):
                    nm = nm + '🔒'
                ep_list.append("%s$%s" % (nm, self._pack(key, src, vid, ep)))
            if not ep_list:
                ep_list = ["播放$%s" % self._pack(key, src, vid, 1)]

            vod = {
                "vod_id": ids,
                "vod_name": _s(det.get('title')),
                "vod_pic": self._abs(det.get('cover')),
                "vod_content": _s(det.get('desc')),
                "vod_remarks": _s(det.get('remark') or det.get('duration')),
                "vod_play_from": "直播" if key == 'live' else "蜜桃",
                "vod_play_url": "#".join(ep_list),
            }
            if det.get('actor'):
                vod['vod_actor'] = _s(det.get('actor'))
            if det.get('area'):
                vod['vod_area'] = _s(det.get('area'))
            if det.get('tag'):
                vod['vod_tag'] = _s(det.get('tag'))
            if key == 'live' and det.get('viewers'):
                vod['vod_remarks'] = '在线 %s 人' % det.get('viewers')
            return {"list": [vod]}
        except Exception as e:
            self.log('detailContent 异常: %s' % e)
            return {"list": []}

    # ---------------- 搜索 ----------------

    def searchContent(self, key, quick=True, pg="1", *args, **kwargs):
        try:
            self._ensure()
            kw = _s(key)
            page = _to_int(pg, 1, 1)
            if not kw:
                return {"list": [], "page": page}
            out, seen = [], set()
            for mod in SEARCH_MODULES:
                lst, _ = self._api_list('/api/search', {'key': mod, 'kw': kw, 'page': page})
                for x in lst:
                    vid = _s(x.get('id'))
                    if not vid or vid in seen:
                        continue
                    seen.add(vid)
                    out.append(self._brief(mod, self._guess_src(mod, x), x))
            return {"list": out, "page": page}
        except Exception as e:
            self.log('searchContent 异常: %s' % e)
            return {"list": [], "page": 1}

    # ---------------- 播放 ----------------

    def _play_data(self, key, src, vid, ep, _retry=1):
        params = {'src': src} if src else {}
        d = self._api('/api/play/%s/%s/%s' % (key, urllib.parse.quote(vid), ep or '1'),
                      params)
        pl = d.get('play') or {}
        if not isinstance(pl, dict):
            pl = {}
        if not pl.get('src') and _retry > 0:
            time.sleep(0.5)
            return self._play_data(key, src, vid, ep, _retry - 1)
        return pl

    def playerContent(self, flag=None, id=None, vipFlags=None, *args, **kwargs):
        res = {"parse": 0}
        try:
            self._ensure()
            raw = _s(id)
            if raw and '%' in raw:
                try:
                    raw = urllib.parse.unquote(raw)
                except Exception:
                    pass
            key, src, vid, ep = self._split_play(raw)
            if not src:
                src = DEFAULT_SRC.get(key, '')
            if not ep:
                ep = '1'

            header = {"User-Agent": self.ua, "Referer": self.host + '/'}
            try:
                pl = self._play_data(key, src, vid, ep)
            except Exception as e:
                self.log('取播放地址失败 %s: %s' % (raw, e))
                pl = {}

            s = _s(pl.get('src'))
            px = _s(pl.get('src_proxy'))
            smart = self._px(type='hls', key=key, src=src, vid=vid, ep=ep)
            lines = []
            if s.startswith('/'):
                lines += ["线路一·直连", self.host + s]
                if px.startswith('/'):
                    lines += ["线路二·中转", self.host + px]
                lines += ["线路三·智能", smart]
            elif s:
                if px.startswith('/'):
                    lines += ["线路一·中转", self.host + px]
                lines += ["线路二·直连", s]
                lines += ["线路三·智能", smart]
            else:
                lines += ["线路一·智能", smart]

            res["header"] = header
            if len(lines) >= 4:
                res["url"] = lines
            else:
                res["url"] = lines[1] if len(lines) > 1 else ''
            if key == 'live' and self.danmaku_on:
                res["danmaku"] = self._px(type='danmu', sid=vid)
            return res
        except Exception as e:
            self.log('playerContent 异常: %s' % e)
            res["url"] = ''
            return res

    # ---------------- 本地代理 ----------------

    def _xml_esc(self, s):
        return (_s(s).replace('&', '&amp;').replace('<', '&lt;')
                .replace('>', '&gt;').replace('"', '&quot;'))

    def _rewrite_m3u8(self, url):
        """把播放列表里的相对地址补成绝对地址。"""
        st, body = self._req(url, headers={"Referer": self.host + '/'}, timeout=20)
        if st not in (200, 206) or not body:
            return None
        try:
            txt = body.decode('utf-8', 'replace')
        except Exception:
            return None
        if '#EXTM3U' not in txt:
            return None

        def _abs_uri(m):
            q, u = m.group(1), m.group(2)
            if u.startswith('http') or u.startswith('//'):
                return m.group(0)
            if u.startswith('/'):
                return 'URI=%s%s%s' % (q, self.host, u)
            return 'URI=%s%s/%s%s' % (q, self.host, u.lstrip('./'), q)

        txt = re.sub(r'URI=(["\'])([^"\']+)\1', _abs_uri, txt)

        out = []
        for line in txt.split('\n'):
            ln = line.strip()
            if ln and not ln.startswith('#'):
                if ln.startswith('/'):
                    ln = self.host + ln
                elif not ln.startswith('http'):
                    ln = self.host + '/' + ln.lstrip('./')
                out.append(ln)
            else:
                out.append(line)
        return '\n'.join(out)

    def _danmaku_xml(self, sid):
        head = '<?xml version="1.0" encoding="UTF-8"?>'
        try:
            d = self._api('/api/comments/live/%s' % urllib.parse.quote(_s(sid)))
            msgs = d.get('messages') or []
            rows = []
            i = 0
            for m in msgs:
                if not isinstance(m, dict):
                    continue
                u = _s(m.get('u'))
                t = _s(m.get('t'))
                if not t:
                    continue
                show = ('%s: %s' % (u, t)) if u else t
                rows.append('\t<d p="%.1f,1,25,16777215,0">%s</d>'
                            % (i * 0.8, self._xml_esc(show[:80])))
                i += 1
            if not rows:
                return [200, 'text/xml', head + '<i></i>']
            return [200, 'text/xml', '\n'.join([head, '<i>'] + rows + ['</i>'])]
        except Exception as e:
            self.log('弹幕生成失败: %s' % e)
            return [200, 'text/xml', head + '<i></i>']

    def localProxy(self, param=None, *args, **kwargs):
        self._ensure()
        try:
            if not isinstance(param, dict):
                p = {}
                if isinstance(param, str) and '=' in param:
                    for k, v in urllib.parse.parse_qsl(param.lstrip('?&')):
                        p[k] = v
                param = p
            typ = _s(param.get('type'))
            # ① 智能播放线路:每次请求都重新取票,票据不过期
            if typ == 'hls':
                key = self._norm_tid(param.get('key') or 'video')
                src = _s(param.get('src'))
                vid = _s(param.get('vid'))
                ep = _s(param.get('ep')) or '1'
                pl = self._play_data(key, src, vid, ep)
                s = _s(pl.get('src'))
                if not s:
                    return [404, 'text/plain', '']
                url = s if s.startswith('http') else (self.host + s)
                txt = self._rewrite_m3u8(url)
                if txt is None and pl.get('src_proxy'):
                    txt = self._rewrite_m3u8(self._abs(pl.get('src_proxy')))
                if txt is None:
                    return [404, 'text/plain', '']
                return [200, 'application/vnd.apple.mpegurl', txt]
            # ② 直播弹幕
            if typ == 'danmu':
                return self._danmaku_xml(param.get('sid') or '')
        except Exception as e:
            self.log('本地代理异常: %s' % e)
        return [404, 'text/plain', '']


# 筛选下拉里那个 JSON 串 → 取回里面的分类 code(用于判断是否被改过)
def _json_cat(v):
    t = _s(v)
    if not t:
        return ''
    if t[:1] == '{':
        try:
            o = json.loads(t)
            if isinstance(o, dict):
                return _s(o.get('c'))
        except Exception:
            pass
    return t
