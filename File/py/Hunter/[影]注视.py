"""
@header({
  searchable: 1,
  filterable: 1,
  quickSearch: 1,
  title: '注视',
  lang: 'hipy'
})
"""

# coding=utf-8
"""
================================================================================
GAZES 注视影视 · t3 本地源（TVBox/hipy type=3，无需服务器）
================================================================================
【导入方式】手机壳内新增源：
  {"name": "注视", "type": 3, "api": "file:///storage/emulated/0/Ma/注视_t3.py"}
  注：本文件不是 t4 那种 Flask 服务器源，用 type=3 + file:/// 绝对路径导入；
      之前把 t4 文件当 t3 导入，壳里找不到 Spider 类，所以分类栏是空的。

【与 t4 服务器源的差异】
  1) 无 Flask、无端口、无局域网服务器：首页/分类/详情/搜索全部在壳内直连源站完成。
  2) 过盾逻辑与 t4 完全一致（v3）：随机名盾 cookie（__Host-*）+ rsw 模幂 + 419/428 重过盾
     + 像素证明头 + DOM token。
  3) 播放：t3 无法在本机跑 playwright 解 WASM，改为把播放页 URL + 已过盾的 Cookie
     交给壳内浏览器加载，由站点自身 JS 解密 data-src 吐出 m3u8 由壳嗅探；
     若弹「访问验证」，在播放器里点一次即可。需要服务器直链请继续用 t4 版。
  4) 分类永不为空：即使源站请求失败，homeContent 也会回退到内置分类表；
     若首页/分类/搜索真的取不到数据，会返回一条名为「[诊断] ...」的条目，
     点开即可看到具体原因（网络不通 / 盾失败 / 源站风控），方便截图定位。

【v3.1 变更（借鉴用户提供的 6 个已验证源）】
  1) 盾 cookie 持久化：过盾成功即写入 /storage/emulated/0/Ma/.gazes_shield.json，
     冷启动直接复用（借鉴 TVB云播/1234视频 的验证态复用，少过一次盾=少一次被风控）。
  2) 播放页预检：返回壳之前先由源带新鲜盾 cookie 访问一次播放页，
     命中 419/428/验证页先本地过盾，确保壳内 webview 打开的是已放行页面
     （借鉴歪比巴卜 的「首次请求下发 cookie、二次才返回真实页」会话校验）。
  3) 失败原因显性化为可点击的「诊断」条目；playerContent 同时返回 header/headers。

【v3.3 变更：本地播放页代理，解决播放弹「点击完成验证」】
  播放不再直接把源站播放页交给壳（webview 无盾 cookie，必弹验证），
  改为在手机本机起只读代理（默认 19777 起，端口占用自动 +1）：
  由源侧会话带新鲜盾 cookie 取页面，页面内绝对地址全部改写成本机同源地址，
  再把本机地址（局域网 IP 优先，退回 127.0.0.1）交给壳内 webview。
  页面内 CDN（oos-cn.ctyunapi.cn）请求也经 /__cdn 前缀回流本代理，全程带盾。
  开关：PX_ENABLE / PX_BIND_ALL / PX_BASE_PORT / PX_PAGE_TTL（文件前部第 06 节）；
  代理起不来时自动回退 v3.2 旧行为。

【v3.2 变更：多域名自适应】
  站点公告本身就在轮换线路：gaze.red / gazes.store / gazes.top / gaze.show /
  gazes.host / gazes.site（gaze.run 已被 DNS 污染）。不同域名走不同 CDN，
  是否被本地运营商 DNS 污染、风控松紧都不一样。
  现在首页/分类会先按「上次成功落盘的域名 -> 候选表」探测，取到数据即锁定；
  某域名取不到数据时自动换下一个域名重试一次（单次最多试 3 个，避免超时），
  可用域名与盾 cookie 一起落盘复用。

【注意】6 个参考源的过验证手法（滑块参数伪造 / 验证码 OCR / human_check 直提交 /
       外部验证接口）与本源的盾（rsw 模幂 PoW + 随机名 __Host-* 盾 cookie）不同，
       算法层面无可直接移植者；能借鉴的是工程模式（验证态复用、统一放行、可见化排查）。

【依赖】requests（壳内自带）；beautifulsoup4 可选（缺失时用本文件内置极简解析器）
================================================================================
"""
import hashlib
import re
import struct
import binascii
import time
import threading
import urllib.parse
import base64
import json
import os
import socket
import http.server
import socketserver
import ssl

try:
    from concurrent.futures import ThreadPoolExecutor
except Exception:
    ThreadPoolExecutor = None

import requests

try:
    from requests.adapters import HTTPAdapter
except Exception:
    class HTTPAdapter(object):
        def __init__(self, *a, **kw):
            pass

try:
    from bs4 import BeautifulSoup as _BS4
except Exception:
    _BS4 = None

# ======================================================================
# 00b 极简 HTML 解析兜底（壳内无 beautifulsoup4 时自动启用）
#     支持的选择器子集：tag / .class / #id / [attr] / [attr=v] / [attr*=v]
#     支持空格后代组合与逗号并列；不支持 > + ~ :nth-of-type 等
# ======================================================================
_VOID_TAGS = set(('area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
                  'link', 'meta', 'param', 'source', 'track', 'wbr'))

_MINI_TAG_RE = re.compile(
    r'<!--.*?-->'
    r'|<\s*(script|style)\b[^>]*>.*?<\s*/\s*\1\s*>'
    r'|<\s*(/?)\s*([a-zA-Z][\w:.-]*)((?:"[^"]*"|\'[^\']*\'|[^>"\'])*?)\s*(/?)\s*>',
    re.S | re.I)
_MINI_ATTR_RE = re.compile(
    r'([\w:.-]+)(?:\s*=\s*("[^"]*"|\'[^\']*\'|[^\s"\'>]+))?')


class _MiniNode(object):
    """极简 DOM 节点：只保留本文件用得到的 select / get_text / get 能力。"""

    __slots__ = ('tag', 'attrs', 'children', 'parent')

    def __init__(self, tag, attrs=None, parent=None):
        self.tag = (tag or '').lower()
        self.attrs = attrs or {}
        self.children = []          # _MiniNode 或 str
        self.parent = parent

    def get(self, name, default=None):
        return self.attrs.get((name or '').lower(), default)

    def iter_nodes(self):
        for ch in self.children:
            if isinstance(ch, _MiniNode):
                yield ch
                for n in ch.iter_nodes():
                    yield n

    def _collect_text(self, sep):
        out = []
        for ch in self.children:
            if isinstance(ch, str):
                out.append(ch)
            else:
                out.append(ch._collect_text(sep))
        return sep.join([x for x in out if x])

    def get_text(self, sep='', strip=False):
        txt = self._collect_text(sep)
        return txt.strip() if strip else txt

    @property
    def text(self):
        return self.get_text(strip=True)

    # --- 选择器 ---
    def select(self, selector):
        return _mini_select(self, selector)

    def select_one(self, selector):
        got = _mini_select(self, selector)
        return got[0] if got else None

    @property
    def title(self):
        got = _mini_select(self, 'title')
        return got[0] if got else None


def _mini_parse(html):
    root = _MiniNode('[doc]')
    cur = root
    pos = 0
    for m in _MINI_TAG_RE.finditer(html or ''):
        # 标签之间的裸文本是节点的文字内容，必须保留（否则 get_text 全为空白）
        text = html[pos:m.start()]
        if text:
            cur.children.append(text)
        pos = m.end()
        whole = m.group(0)
        if whole.startswith('<!--') or (m.group(2) is None and m.group(1)):
            continue                      # 注释 / script / style 整体丢弃
        closing, tag, raw_attrs, self_close = m.group(2), m.group(3), m.group(4), m.group(5)
        tag = (tag or '').lower()
        if closing:
            node = cur
            while node is not None and node.tag != tag:
                node = node.parent
            if node is not None and node is not root:
                cur = node.parent
            continue
        attrs = {}
        for am in _MINI_ATTR_RE.finditer(raw_attrs or ''):
            key = am.group(1).lower()
            val = am.group(2)
            if val is None:
                val = ''
            elif val[:1] in ('"', "'"):
                val = val[1:-1]
            attrs[key] = val
        node = _MiniNode(tag, attrs, cur)
        cur.children.append(node)
        if tag not in _VOID_TAGS and not self_close:
            cur = node
    tail = (html or '')[pos:]
    if tail:
        root.children.append(tail)
    return root


def _mini_parse_step(step):
    tag_m = re.match(r'^[a-zA-Z][\w.-]*', step)
    tag = tag_m.group(0).lower() if tag_m else None
    ids, classes, attrs = [], [], []
    for part in re.findall(r'[.#][\w-]+|\[[^\]]+\]', step):
        if part.startswith('.'):
            classes.append(part[1:])
        elif part.startswith('#'):
            ids.append(part[1:])
        else:
            inner = part[1:-1]
            am = re.match(r'^([\w:.-]+)\s*(\*=|\^=|\$=|=)?\s*(.*)$', inner)
            if am:
                val = (am.group(3) or '').strip()
                if val[:1] in ('"', "'"):
                    val = val[1:-1]
                attrs.append((am.group(1).lower(), am.group(2) or '', val))
    return (tag, ids, classes, attrs)


def _mini_match(node, step):
    tag, ids, classes, attrs = step
    if tag and node.tag != tag:
        return False
    if ids and (node.get('id') or '') not in ids:
        return False
    if classes:
        cls = set((node.get('class') or '').split())
        for c in classes:
            if c not in cls:
                return False
    for name, op, val in attrs:
        got = node.get(name)
        if got is None:
            return False
        if op == '=' and got != val:
            return False
        if op == '*=' and val not in got:
            return False
        if op == '^=' and not got.startswith(val):
            return False
        if op == '$=' and not got.endswith(val):
            return False
    return True


def _mini_ancestors_match(node, steps):
    cur = node.parent
    need = list(steps)
    while cur is not None and need:
        if _mini_match(cur, need[-1]):
            need.pop()
        cur = cur.parent
    return not need


def _mini_select(root, selector):
    out = []
    for group in str(selector or '').split(','):
        steps = [_mini_parse_step(x) for x in group.split()]
        steps = [s for s in steps if s]
        if not steps:
            continue
        cands = [n for n in root.iter_nodes() if _mini_match(n, steps[-1])]
        if len(steps) > 1:
            cands = [n for n in cands if _mini_ancestors_match(n, steps[:-1])]
        for n in cands:
            if n not in out:
                out.append(n)
    return out


class _MiniSoup(_MiniNode):
    """替代 BeautifulSoup(html, 'html.parser') 的最小实现。"""

    def __init__(self, html, features=None):
        _MiniNode.__init__(self, '[doc]')
        built = _mini_parse(html)
        self.children = built.children
        for ch in self.children:
            if isinstance(ch, _MiniNode):
                ch.parent = self

# ---- bs4 可用性桥接：没装 beautifulsoup4 时用内置极简解析器兜底 ----
if _BS4 is not None:
    BeautifulSoup = _BS4
else:
    BeautifulSoup = _MiniSoup
    print('[注视] 未检测到 beautifulsoup4，已启用内置极简 HTML 解析器')

try:
    from base.spider import Spider as _BaseSpider
except ImportError:
    class _BaseSpider(object):
        """脱离壳独立运行（如本地自检）时的占位基类。"""

# ======================================================================
# 01 常量与配置
# ======================================================================
SITE_URL = "https://gazes.top"

# ----------------------------------------------------------------------
# 多域名自适应（v3.2）：站点公告里自己就在轮换线路，不同域名/CDN 后盾的风控策略
# 与是否被本地运营商 DNS 污染都不一样（公告点名 gaze.run 已被 DNS 污染）。
# 手机端「云端能过盾、本机却取不到数据」时，换一个域名往往直接可用。
# 顺序 = 上次成功并落盘的域名优先，其次按下列候选表。
# ----------------------------------------------------------------------
# v3.4：实测（2025-10）gazes.top 源站频繁 520（Cloudflare "2024913.xyz origin error"），
# gazes.store 走另一 CDN 后盾稳定可用，故调整候选顺序，store 优先。
SITE_CANDIDATES = ["https://gazes.store", "https://gazes.top", "https://gaze.red",
                   "https://gaze.show", "https://gazes.host", "https://gazes.site"]
_SITE_STATE = {'ready': False, 'cur': SITE_URL, 'probe_from': 0}
_SITE_LOCK = threading.Lock()

# ----------------------------------------------------------------------
# 盾 cookie / 可用域名的落盘位置（借鉴 TVB云播、1234视频 的「验证态持久化」）：
# 过盾成功即落盘，下次冷启动直接复用，少过一次盾 = 少一次被 429/520 风控的机会。
# 路径写不进去（无存储权限）时静默忽略，不影响主流程。
# 注意：必须定义在模块前部——_sess 单例在模块中部创建时就会读该文件。
# ----------------------------------------------------------------------
_SHIELD_FILES = ['/storage/emulated/0/Ma/.gazes_shield.json',
                 '/sdcard/Ma/.gazes_shield.json']


def _read_shield_site():
    for p in _SHIELD_FILES:
        try:
            if not os.path.exists(p):
                continue
            with open(p, 'r') as f:
                d = json.load(f) or {}
            s = str(d.get('site') or '').strip().rstrip('/')
            if s.startswith('http'):
                return s
        except Exception:
            continue
    return ''


def _save_shield_site(site):
    try:
        for p in _SHIELD_FILES:
            try:
                d = os.path.dirname(p)
                if d and not os.path.isdir(d):
                    continue
                old = {}
                if os.path.exists(p):
                    try:
                        with open(p, 'r') as f:
                            old = json.load(f) or {}
                    except Exception:
                        old = {}
                old['site'] = str(site).rstrip('/')
                old.setdefault('ts', time.time())
                with open(p, 'w') as f:
                    json.dump(old, f)
                return True
            except Exception:
                continue
    except Exception:
        pass
    return False

SITE_DOMAINS = ["https://gazes.top"]
PORT = 16999

UA = ('Mozilla/5.0 (Linux; Android 16; V2425A Build/BP2A.250605.031.A3_V000L1; wv) '
      'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/138.0.7204.179 Mobile Safari/537.36')
# 共享 Session：复用 HTTP 连接池，避免每次探测都新建 TCP+TLS 握手。
# 实测天翼源(xhscdn)探测提速约3倍（9.3s→3.1s@60片），冷启动626片从~79s降至~25s。
_SESSION = requests.Session()
_SESSION.headers.update({'User-Agent': UA})
_SESSION.mount('https://', HTTPAdapter(pool_connections=32, pool_maxsize=32))

CATEGORIES = [
    {"type_id": "movie",           "type_name": "电影"},
    {"type_id": "series",          "type_name": "电视剧"},
    {"type_id": "chinese_cartoon", "type_name": "国漫"},
    {"type_id": "bangumi",         "type_name": "动漫"},
]
MFORM_MAP = {
    "movie":           "1",
    "series":          "2",
    "chinese_cartoon": "chinese_cartoon",
    "bangumi":         "bangumi",
}

_TYPE_OPTIONS = [
    ("剧情", "1"), ("动作", "2"), ("喜剧", "3"), ("爱情", "4"), ("科幻", "5"),
    ("悬疑", "6"), ("惊悚", "7"), ("恐怖", "8"), ("犯罪", "9"), ("音乐", "10"),
    ("冒险", "11"), ("历史", "12"), ("战争", "13"), ("奇幻", "14"), ("黑帮", "15"),
    ("文艺", "16"), ("传记", "17"), ("运动", "18"), ("同性", "19"), ("情色", "20"),
]
_AREA_OPTIONS = [
    ("中国大陆", "1"), ("中国台湾", "2"), ("中国香港", "3"), ("韩国", "4"), ("俄罗斯", "5"),
    ("美国", "6"), ("日本", "7"), ("印度", "8"), ("英国", "9"), ("德国", "10"),
    ("法国", "11"), ("意大利", "12"), ("泰国", "13"), ("爱沙尼亚", "14"), ("哈萨克斯坦", "15"),
    ("西班牙", "16"), ("黎巴嫩", "17"), ("巴西", "18"), ("澳大利亚", "19"), ("丹麦", "20"),
    ("瑞典", "21"), ("以色列", "22"), ("荷兰", "23"), ("伊朗", "24"), ("墨西哥", "25"),
    ("奥地利", "26"), ("智利", "27"), ("马来西亚", "28"), ("哥伦比亚", "29"), ("挪威", "30"),
    ("爱尔兰", "31"), ("罗马尼亚", "32"), ("比利时", "33"), ("瑞士", "34"), ("加拿大", "35"),
    ("波兰", "36"),
]
_SORT_OPTIONS = [
    ("默认排序", ""), ("评分排序", "grade"), ("名称排序", "name"),
    ("添加时间", "createtime"), ("更新时间", "updatetime"),
]


def _filter_meta():
    """按分类 id 分组的筛选结构（TVBox 规范：顶层 key 是分类 id，value 是筛选组数组）。
    返回 {"分类id": [ {key,name,value}, ... ], ...}"""
    now_year = time.localtime().tm_year
    groups = [
        {"key": "sort", "name": "排序",
         "value": [{"n": n, "v": v} for n, v in _SORT_OPTIONS]},
        {"key": "genre", "name": "类型",
         "value": [{"n": "全部", "v": ""}] +
                  [{"n": n, "v": v} for n, v in _TYPE_OPTIONS]},
        {"key": "area", "name": "地区",
         "value": [{"n": "全部", "v": ""}] +
                  [{"n": n, "v": v} for n, v in _AREA_OPTIONS]},
        {"key": "year", "name": "年份",
         "value": [{"n": "全部", "v": ""}] +
                  [{"n": str(now_year - i), "v": str(now_year - i)}
                   for i in range(54)]},
    ]
    return {c["type_id"]: groups for c in CATEGORIES}

# ======================================================================
# 02 TLS 指纹 + cap PoW（与 t3 完全一致，t4 增加 cffi 可选）
# ======================================================================
_CHROME_CIPHERS = (
    'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:'
    'ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:'
    'ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:'
    'ECDHE-RSA-AES128-SHA:ECDHE-RSA-AES256-SHA:'
    'AES128-GCM-SHA256:AES256-GCM-SHA384:AES128-SHA:AES256-SHA'
)


def _chrome_ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        ctx.set_ciphers(_CHROME_CIPHERS)
    except Exception:
        pass
    return ctx


class _CtxAdapter(HTTPAdapter):
    # 并发加固：显式扩大连接池，缓解单例 _sess 在多线程下争抢默认 10 连接导致的竞态。
    # 针对 2G2H 校准：信号量 _net_sem=8 已是真正并发闸门（同时最多 8 个连接被用），
    # pool_connections/maxsize=12（>8 留余量）即可，避免 32 造成低配机无谓的源站连接积压。
    def __init__(self, ctx=None, pool_connections=12, pool_maxsize=12):
        self._ctx = ctx
        super().__init__(pool_connections=pool_connections,
                         pool_maxsize=pool_maxsize,
                         max_retries=0)

    def init_poolmanager(self, *args, **kwargs):
        if self._ctx is not None:
            kwargs['ssl_context'] = self._ctx
        return super().init_poolmanager(*args, **kwargs)


def _fnv1a(data):
    h = 0x811c9dc5
    if isinstance(data, str):
        data = data.encode('utf-8')
    for b in data:
        h ^= b
        h = (h * 0x01000193) & 0xffffffff
    return h


def _pfunc(seed_str, length):
    bits = _fnv1a(seed_str)
    out = []
    while len(''.join(out)) < length:
        bits &= 0xffffffff
        bits ^= (bits << 13) & 0xffffffff
        bits ^= bits >> 17
        bits ^= (bits << 5) & 0xffffffff
        bits &= 0xffffffff
        out.append('%08x' % bits)
    return ''.join(out)[:length]


def _solve_one(salt, target_hex):
    full_bytes = len(target_hex) // 2
    want = bytes.fromhex(target_hex[:full_bytes * 2])
    nonce = 0
    base = salt.encode('utf-8') if isinstance(salt, str) else salt
    while True:
        digest = hashlib.sha256(base + str(nonce).encode('utf-8')).digest()
        if digest[:full_bytes] == want:
            return nonce
        nonce += 1


def _xhr_headers(site):
    return {
        'Accept': 'application/json, text/plain, */*',
        'Referer': site + '/',
        'Origin': site,
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
    }


def _shield_cookie(jar=None):
    """返回当前会话持有的盾 cookie 名（v3.0）。

    源站每次 redeem 随机下发 __Host-<随机名>（不再固定 __Host-vs），故一切
    "有没有盾" 的判断都必须走这里，禁止写死名字。无盾返回 None。"""
    try:
        for c in (jar if jar is not None else _sess.sess.cookies):
            if c.name.startswith('__Host-'):
                return c.name
    except Exception:
        pass
    return None


def _solve_rsw(x_hex, t, n_hex):
    """v3.0 新版 cap 挑战协议 rsw：求 y = x^(2^t) mod N 的 hex 字符串。

    x/N 为 hex 字符串，t 为二进制移位次数（页面 cap.js 用 BigInt 反复平方实现）。
    Python 的 pow(x, 1<<t, N) 与之等价，且 t 很小时耗时 <1ms。"""
    if not x_hex or not n_hex:
        raise ValueError('rsw payload 缺 x/N')
    x = int(str(x_hex), 16)
    n = int(str(n_hex), 16)
    y = pow(x, 1 << int(t), n)
    return format(y, 'x')

class _CapSession:
    """带 cap 自动验证的 HTTP 会话（t4 模块级单例，常驻复用盾 cookie）

    v3.0：盾 cookie 名不再固定为 __Host-vs，每次 redeem 随机下发 __Host-<随机名>，
    一切判断统一走 _shield_cookie() / _vs_valid()，禁止写死名字。"""

    # v2.9.10: 捕获会话主动重过周期（秒）。捕获会话常驻复用一个 __Host-vs cookie，
    # 但 __Host-vs 实际寿命较短且其 expires 字段存在毫秒/s 单位错乱风险(见 _vs_valid)，
    # 长期复用会在源站判定旧盾失效后全站捕获失败(hls 永不就绪，需重启才恢复)。
    # 此处放弃信任 expires，改为记录「上次成功过盾时间」：超期后主动重新过盾，
    # 宁愿多过盾，也绝不复用可能已失效的旧 cookie。默认 1800s(30分钟)，远短于
    # __Host-vs 真实寿命，保证始终使用新鲜 cookie。
    _CAP_REDEEM_TTL = 1800

    def __init__(self):
        self._cap_redeem_ts = 0.0   # 上次成功过盾(redeem)的时间戳，0=从未过盾
        self.sess = requests.Session()
        try:
            self.sess.mount('https://', _CtxAdapter(_chrome_ssl_ctx()))
        except Exception as e:
            print('[gazes] ssl adapter mount fail:', e)
        self.sess.headers.update({
            'User-Agent': UA,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'Referer': 'https://gazes.top/',
            'Origin': 'https://gazes.top',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Upgrade-Insecure-Requests': '1',
        })
        self.site = 'https://gazes.top'
        self._redeem_fail_until = 0.0
        self._chal_info = ''
        self._last_redeem_diag = ''
        self._last_get_err = ''   # 并发加固：记录最近一次 _get 的真实异常，供诊断透出
        self._cap_lock = threading.Lock()
        # 并发加固：单例 _sess 被 Flask 多线程共享，同一时刻限制并发请求数，
        # 从源头消除连接池/cookie jar 争抢。N=8：常规并发下不排队，高峰削峰。
        # 防死锁关键：信号量仅在 _get 内最小临界区（只包 self.sess.get）持有，
        # 过盾(_ensure_cookie)等在信号量之外执行，绝不嵌套持锁。
        self._net_sem = threading.Semaphore(8)
        # 借鉴 TVB云播/1234视频：先尝试从上一次落盘的盾 cookie 恢复，冷启动即可免过盾
        try:
            self._load_shield()
        except Exception:
            pass

    # ---------- 盾 cookie 持久化（借鉴 TVB云播 / 1234视频 的验证态复用） ----------
    def _load_shield(self):
        """从落盘文件恢复上次过盾成功的 cookie（含每次随机命名的 __Host-* 盾）
        以及上次可用的域名。恢复失败/已过期都无所谓：后续请求命中 419/验证页时
        会自动重新过盾，域名失活则由 _auto_site 探测切换。"""
        for p in _SHIELD_FILES:
            try:
                if not os.path.exists(p):
                    continue
                with open(p, 'r') as f:
                    data = json.load(f)
                # 域名先恢复（cookie 是按 domain 存的，换域必须一起换）
                site = str(data.get('site') or '').strip().rstrip('/')
                if site.startswith('http'):
                    globals()['SITE_URL'] = site
                    self.site = site
                    _SITE_STATE['cur'] = site
                host = urllib.parse.urlparse(self.site).hostname or 'gazes.top'
                ck = data.get('cookies') or {}
                n = 0
                for k, v in ck.items():
                    if not k or not v:
                        continue
                    try:
                        self.sess.cookies.set(str(k), str(v), domain=host, path='/')
                        n += 1
                    except Exception:
                        pass
                if n:
                    ts = data.get('ts') or 0
                    self._cap_redeem_ts = float(ts) if ts else 0.0
                    print('[gazes] 已从 %s 恢复 %d 个 cookie（site=%s ts=%s）'
                          % (p, n, self.site, ts))
                    return True
            except Exception:
                continue
        return False

    def _save_shield(self):
        """过盾成功后落盘（含当前可用域名），供下次冷启动复用（写不进去就静默忽略）。"""
        try:
            data = {'ts': time.time(), 'site': SITE_URL,
                    'cookies': {c.name: c.value for c in self.sess.cookies if c.value}}
            for p in _SHIELD_FILES:
                try:
                    d = os.path.dirname(p)
                    if d and not os.path.isdir(d):
                        continue
                    with open(p, 'w') as f:
                        json.dump(data, f)
                    print('[gazes] 盾 cookie 已持久化 -> %s' % p)
                    return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    def _get(self, url, referer=None):
        headers = {'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'}
        if referer:
            headers['Referer'] = referer
        # 自愈重试：偶发异常（连接池竞态/keep-alive 过期）先短重试 1 次，
        # 命中则直接成功，降低 get_page 4 次全 None 的概率。
        for _attempt in range(2):
            try:
                with self._net_sem:
                    resp = self.sess.get(url, headers=headers, timeout=20)
                self._last_get_err = ''   # 成功则清空诊断
                return resp
            except Exception as e:
                self._last_get_err = '%s: %s' % (type(e).__name__, str(e)[:120])
                time.sleep(0.3)
        return None

    def _is_cap_page(self, text):
        if 'cap-widget' in text:
            return True
        head = re.sub(r'\s+', ' ', text[:400])
        if '请稍候' in head or '请稍等' in head or '访问验证' in head:
            return True
        if '验证' in text[:300]:
            return True

    def _vs_valid(self):
        """盾 cookie 是否真正有效（存在且未过期）。

        v3.0 变更：源站已把盾 cookie 从固定的 __Host-vs 改为【每次 redeem 随机命名】
        的 __Host-<随机名>（本例实测为 __Host-0x0081655aa7b8），故不能再写死名字，
        统一按 __Host- 前缀匹配。写死名字会导致「明明刚过盾成功，却永远判无盾」
        -> 每次请求都重走过盾 + 拿不到盾的请求全被 cap 页拦下，源直接不可用。

        源站签发的盾带 expires(epoch秒)，有效期约数分钟。必须基于真实过期时间判断，
        而非 .get() 是否存在——requests 的 CookieJar 在 cookie 过期后 .get() 仍返回
        旧值，但发送请求时会自动过滤掉过期 cookie，导致"判断有盾、实际却未携带"的
        死盾。若不校正，cookie 过期后所有未缓存片子的主/捕获请求都会误判有盾而跳过
        重新过盾 -> 全部命中验证页失败且不自愈。"""
        # v2.9.10: 主动重过周期优先——捕获会话记录的上次过盾时间距现在超过
        # _CAP_REDEEM_TTL 即视为需重新过盾，不再信任可能单位错乱/被源站判废的
        # 旧 cookie 的 expires 字段。宁可多过盾，也不复用可能已失效的死盾。
        if self._cap_redeem_ts and (time.time() - self._cap_redeem_ts) >= getattr(self, '_CAP_REDEEM_TTL', 600):
            return False
        jar = self.sess.cookies
        for c in jar:
            if not c.name.startswith('__Host-'):
                continue
            exp = getattr(c, 'expires', None)
            if exp is None:
                return True          # 无 expires 的会话 cookie 视为有效
            if exp > 10 ** 11:       # v2.9.10: 源站返回毫秒(13位)时转成秒再比较
                exp /= 1000.0
            return exp > time.time() # 未过期才算有效
        return False                  # 无盾 cookie

    def _ensure_cookie(self):
        with self._cap_lock:
            return self._ensure_cookie_locked()
    def _ensure_cookie_locked(self):
        if self._vs_valid():
            return True
        if time.time() < self._redeem_fail_until:
            print('[gazes] cap 冷却中，跳过验证 (until %s)' %
                  time.strftime('%H:%M:%S', time.localtime(self._redeem_fail_until)))
            return False
        # challenge 偶发 429/5xx/网络异常：短等待重试，冷启动过盾更稳
        data = None
        last_diag = ''
        for _try in range(3):
            try:
                if not self.sess.cookies:
                    try:
                        self.sess.get(self.site + '/', timeout=15)
                    except Exception:
                        pass
                r = self.sess.post(self.site + '/event/cap/challenge',
                                   headers=_xhr_headers(self.site), json={}, timeout=20)
                print('[gazes] challenge http=%s cookies=%s' %
                      (r.status_code, {k: v[:8] for k, v in self.sess.cookies.get_dict().items()}))
                if r.status_code == 200:
                    data = r.json()
                    break
                if r.status_code == 520:
                    # 明确风控信号：无需试满 3 次，直接放弃本轮（纯减法）。
                    # 后续由 _redeem_fail_until 60s 冷却短路，杜绝重试风暴。
                    last_diag = ('challenge 520 风控 body=%s' %
                                 re.sub(r'\s+', ' ', r.text[:150]))
                    print('[gazes] challenge 520 风控，直接放弃本轮')
                    data = None
                    break
                last_diag = ('challenge http=%s body=%s' %
                             (r.status_code, re.sub(r'\s+', ' ', r.text[:200])))
                print('[gazes] challenge 非200 http=%s 重试...' % r.status_code)
                time.sleep(1.0)
            except Exception as e:
                last_diag = 'challenge 异常 %s: %s' % (type(e).__name__, str(e)[:150])
                print('[gazes] challenge 请求异常:', type(e).__name__, str(e)[:150])
                time.sleep(1.0)
        if data is None:
            self._last_redeem_diag = last_diag or 'challenge 连续失败'
            # 520 风暴防护（纯减法）：challenge 连续失败说明源站处于风控期，
            # 立即进入 60s 冷却，避免后续每次命中风控都重新打 3 次 challenge 形成无限重试风暴、
            # 白白耗尽服务器线程与流量。期间 _ensure_cookie 直接短路返回，零额外请求。
            self._redeem_fail_until = time.time() + 60
            return False
        ch_list = data.get('challenges')
        token = data.get('token') or ''
        if isinstance(ch_list, list) and ch_list and token:
            # ---- v3.0 新版协议：{"token":"...","challenges":[{"protocol":"rsw","payload":{"x","t","N"}}]} ----
            # rsw = 模幂证明 y = x^(2^t) mod N（页面 cap.js 用 BigInt 平方链算），
            # 结果以 hex 字符串回填 solutions[i].y。单次响应可能含多个挑战，需全解。
            self._chal_info = 'rsw x%d token=%s...' % (len(ch_list), str(token)[:12])
            print('[gazes] 新版 cap 挑战(rsw) %d 个, token=%s...' % (len(ch_list), token[:12]))
            t0 = time.time()
            solutions = []
            for _ci, _ch in enumerate(ch_list):
                _proto = str((_ch or {}).get('protocol') or '').lower()
                _pl = (_ch or {}).get('payload') or {}
                if _proto in ('rsw', 'rsa_sw', 'pow_rsw', 'sw'):
                    try:
                        solutions.append({'y': _solve_rsw(_pl.get('x'), _pl.get('t'), _pl.get('N'))})
                    except Exception as _se:
                        self._last_redeem_diag = 'rsw 求解失败 #%d payload=%s err=%s' % (
                            _ci, str(_pl)[:120], str(_se)[:80])
                        return False
                else:
                    self._last_redeem_diag = '未知挑战协议 %r payload=%s' % (_proto, str(_pl)[:120])
                    return False
            print('[gazes] rsw 完成 %s 个, 耗时 %.0fms' % (len(solutions), (time.time() - t0) * 1000))
        else:
            # ---- v2.9 旧版协议：{"challenge":{"c","s","d"}} + FNV/sha256 PoW ----
            ch = data.get('challenge') or {}
            c, s, d = ch.get('c', 0), ch.get('s', 0), ch.get('d', 0)
            self._chal_info = 'c=%s s=%s d=%s token=%s...' % (c, s, d, str(token)[:10])
            if not (c and s and d and token):
                self._last_redeem_diag = 'challenge 缺字段: %s' % str(data)[:200]
                return False
            print('[gazes] 开始 PoW: c=%s s=%s d=%s token=%s...' % (c, s, d, token[:12]))
            t0 = time.time()
            solutions = []
            for idx in range(1, c + 1):
                salt = _pfunc(token + str(idx), s)
                target = _pfunc(token + str(idx) + 'd', d)
                nonce = _solve_one(salt, target)
                if nonce is None:
                    self._last_redeem_diag = 'PoW 无解 idx=%s' % idx
                    return False
                solutions.append(nonce)
            print('[gazes] PoW 完成 %s 个, 耗时 %.0fms' % (c, (time.time() - t0) * 1000))
        try:
            rr = self.sess.post(self.site + '/event/cap/redeem',
                                json={'token': token, 'solutions': solutions}, timeout=30,
                                headers=_xhr_headers(self.site))
            print('[gazes] redeem http=%s body=%s' % (rr.status_code, rr.text[:220]))
            if rr.status_code == 429:
                try:
                    wait = int((rr.json() or {}).get('retry_after', 20)) + 3
                except Exception:
                    wait = 23
                print('[gazes] 429 限频, 等待 %ss 重试' % wait)
                time.sleep(min(wait, 35))
                rr = self.sess.post(self.site + '/event/cap/redeem',
                                    json={'token': token, 'solutions': solutions}, timeout=30,
                                    headers=_xhr_headers(self.site))
                if rr.status_code != 200:
                    self._last_redeem_diag = ('redeem 429 重试仍 http=%s body=%s | chal=%s' %
                                              (rr.status_code, re.sub(r'\s+', ' ', rr.text[:200]),
                                               self._chal_info or '无'))
                    self._redeem_fail_until = time.time() + 60
                    return False
            if rr.status_code == 403:
                self._last_redeem_diag = ('redeem 403 body=%s | chal=%s' %
                                          (re.sub(r'\s+', ' ', rr.text[:200]),
                                           self._chal_info or '无'))
                self._redeem_fail_until = time.time() + 60
                return False
            ok = rr.status_code == 200 and bool(_shield_cookie(self.sess.cookies))
            if ok:
                self._last_redeem_diag = ''
                # v2.9.10: 记录本次成功过盾的时间戳，供 _vs_valid 的主动重过周期判断。
                # 即使 __Host-vs 的实际 expires 单位错乱(毫秒被当秒)，也不影响——到期后
                # 由 _CAP_REDEEM_TTL 强制重过，绝不长期复用可能失效的旧盾。
                self._cap_redeem_ts = time.time()
                try:
                    self._save_shield()
                except Exception:
                    pass
            else:
                self._last_redeem_diag = ('redeem http=%s(非200或无cookie) body=%s' %
                                          (rr.status_code, re.sub(r'\s+', ' ', rr.text[:200])))
            return ok
        except Exception as e:
            self._last_redeem_diag = 'redeem 异常 %s: %s' % (type(e).__name__, str(e)[:150])
            return False

    def get_page(self, url):
        # 冷会话首次访问可能偶发 CF 520（JS 挑战页）或站点 429（"请稍候"限流）。
        # 520/429 都不能当作普通 5xx 直接放弃——需进入过盾流程并重试取页。
        for _try in range(4):
            resp = self._get(url)
            if resp is None:
                time.sleep(0.8)
                continue
            if resp.status_code in (419, 429, 520):
                # 风控/限流/盾过期页：进入过盾流程（幂等，内部有锁与冷却）
                # v3.0: 新增 419 —— 新版源站判盾失效返回 419(旧版为 428)，
                # 页面 JS 收到 419 也是直接 location.reload() 重新过盾。
                print('[gazes] 命中风控 http=%s 开始过盾: %s' % (resp.status_code, url[:80]))
                ok = self._ensure_cookie()
                print('[gazes] 过盾结果: ok=%s' % ok)
                time.sleep(0.6)
                continue
            if resp.status_code >= 500:
                # 真正的服务器 5xx：短暂等待后重试一次
                time.sleep(0.8)
                continue
            if self._is_cap_page(resp.text):
                print('[gazes] 命中验证页, 开始过盾:', url[:90])
                ok = self._ensure_cookie()
                print('[gazes] 过盾结果: ok=%s' % ok)
                time.sleep(0.6)
                continue
            return resp
        return None

    def post_movielist(self, mform, page=1, title='', sort='default', mcountry='all',
                       genre_arr='all', album='all', years='all', retry=True):
        q = {'mform': mform}
        if sort != 'default':
            q['sort'] = sort
        if title:
            q['search'] = title
        page_url = self.site + '/filter?' + urllib.parse.urlencode(q)

        def attempt():
            resp = self.get_page(page_url)
            if resp is None:
                return None
            if resp.status_code in (419, 428):
                return resp
            proof = _solve_pixel_proof(resp.text)
            if not proof:
                print('[gazes] /filter 证明提取失败(页面已变?): %s' % page_url[:90])
                return None
            dom_hdr, dom_tok = _extract_dom_token(resp.text)
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
                'Accept': 'application/json, text/plain, */*',
                'Origin': self.site,
                'Referer': page_url,
                proof['header_name']: proof['header_value'],
            }
            if dom_hdr and dom_tok:
                headers[dom_hdr] = dom_tok
            body = {
                'mform': mform, 'mcountry': mcountry, 'genre_arr': genre_arr,
                'page': str(page), 'sort': sort, 'album': album,
                'title': title, 'years': years,
            }
            try:
                r = self.sess.post(self.site + '/filter_movielist', data=body,
                                   headers=headers, timeout=25)
            except Exception:
                return None
            return r

        r = attempt()
        # v3.0: 412/419/428 均为「盾已过期」信号（新版站点用 419，旧版 428；
        # 页面 JS 见 419/428 直接 location.reload() 重过盾）。证明提取失败(None)
        # 通常也是因为拿到的是 cap 页 -> 一律重过盾后重试一次。
        if retry and (r is None or getattr(r, 'status_code', 0) in (419, 428)):
            print('[gazes] /filter 首次未通过(status=%s)，重过盾后重试一次'
                  % getattr(r, 'status_code', None))
            self._ensure_cookie()
            time.sleep(0.5)
            r = attempt()
        if r is None:
            return None
        try:
            data = r.json()
        except Exception:
            return None
        data['_status'] = r.status_code
        return data


_sess = _CapSession()

# ======================================================================
# 03 canvas 像素指纹证明头 + DOM token（与 t3 完全一致）
# ======================================================================
VAR = r'[A-Za-z_$][\w$]*'


def decode_data_bmp(data_uri):
    b64 = data_uri.split(',', 1)[1]
    raw = base64.b64decode(b64)
    off = struct.unpack_from('<I', raw, 10)[0]
    w = struct.unpack_from('<i', raw, 18)[0]
    h = struct.unpack_from('<i', raw, 22)[0]
    bpp = struct.unpack_from('<H', raw, 28)[0]
    nbytes = bpp // 8
    rowsz = ((w * bpp + 31) // 32) * 4
    rows = [raw[off + r * rowsz: off + r * rowsz + rowsz] for r in range(abs(h))]
    if h > 0:
        rows = rows[::-1]
    px = []
    for r in range(abs(h)):
        for c in range(w):
            b, g, red = rows[r][c * nbytes], rows[r][c * nbytes + 1], rows[r][c * nbytes + 2]
            a = 255 if nbytes == 3 else rows[r][c * nbytes + 3]
            px += [red, g, b, a]
    assert len(px) == w * abs(h) * 4
    return bytes(px)


# ----------------------------------------------------------------------
# v3.0 新版像素证明（站点改版后）
#   页面内联 JS 流程：chunk 数组乱序拼接 -> base64 解码 -> `.slice(x^y, x^y)`
#   取 BMP -> 24/32bpp 像素还原(RGBA) -> 32 槽洗牌映射 -> 两个请求头
#     header_name  = 前 16 槽字节 hex（站点侧名为 x-gaze-<24hex>）
#     header_value = 后 16 槽字节 hex（64hex）
#   与旧版(getImageData/65503/3571/Array.from 链)结构完全不同，故旧版实现
#   保留为 _solve_pixel_proof_v1 / _extract_dom_token_v1 作兼容回退。
# ----------------------------------------------------------------------

SLICE_RE = re.compile(r'\.slice\((\(?\d+\^\d+\)?)\s*,\s*(\(?\d+\^\d+\)?)\)')
KEYPAIR_RE = re.compile(
    r'(\w+)\s*=\s*\w+\.slice\((\(?\d+\^\d+\)?)\s*,\s*(\(?\d+\^\d+\)?)\),\s*'
    r'(\w+)\s*=\s*\w+\.slice\((\(?\d+\^\d+\)?)\s*,\s*(\(?\d+\^\d+\)?)\),\s*\w+\s*=\s*new Array\((\d+)\)')


def _xor_num(s):
    a, b = s.strip('()').split('^')
    return int(a) ^ int(b)


def _extract_proof_v3(html):
    """解析新版像素证明，成功返回 dict(header_name/header_value/...)，失败返回 {'fail': 原因}"""
    chunks = order = None
    for m in re.finditer(r'(\[[^\[\]]{0,6000}\])\s*,\s*\w+\s*=\s*(\[[0-9,\s]{1,140}\])', html):
        try:
            a, o = json.loads(m.group(1)), json.loads(m.group(2))
        except Exception:
            continue
        if (isinstance(a, list) and a and all(isinstance(x, str) for x in a)
                and isinstance(o, list) and len(o) == len(a) and sorted(o) == list(range(len(a)))):
            chunks, order = a, o
            break
    if chunks is None:
        return {'fail': 'chunk'}
    buf = base64.b64decode(''.join(chunks[i] for i in order))

    bmp = None
    for m in SLICE_RE.finditer(html):
        s, e = _xor_num(m.group(1)), _xor_num(m.group(2))
        if 0 <= s < e <= len(buf) and buf[s:s + 2] == b'BM':
            bmp = buf[s:e]
            break
    if bmp is None or len(bmp) < 60:
        return {'fail': 'bmp'}
    off, w, h, bpp = struct.unpack('<IiiH', bmp[10:14] + bmp[18:22] + bmp[22:26] + bmp[28:30])
    if not (1 <= w <= 64 and 1 <= h <= 64 and bpp in (24, 32)):
        return {'fail': 'dim %sx%s/%s' % (w, h, bpp)}
    stride = ((w * bpp // 8) + 3) // 4 * 4
    px = bytearray()
    for y in range(h - 1, -1, -1):
        row = off + y * stride
        for x in range(w):
            b, g, r = bmp[row + x * 3:row + x * 3 + 3]
            px += bytes((r, g, b, 255))

    mc = re.search(r'\(\(\(?(\d+)\s*\^\s*(\d+)\)?\s*\+\s*\w+\s*\*\s*(\d+)\)\s*&\s*2147483647\)', html)
    ms = re.search(r'\[(\w+)>>>(\d+)\]\s*=\s*(\w+)\[(\w+)\s*&\s*(\d+)\]', html)
    mk = KEYPAIR_RE.search(html)
    ml = (re.search(r'for\(let\s+(\w+)\s*=\s*0\s*;\s*\1\s*<\s*(\w+)\.length\s*>>>\s*2', html)
          or re.search(r'for\(let\s+(\w+)\s*=\s*0\s*;\s*\1\s*<\s*(\w+)\.length', html)
          or re.search(r'while\(\s*(\w+)\s*<\s*(\w+)\.length', html))
    if not (mc and ms and mk and ml):
        return {'fail': 'params mc=%s ms=%s mk=%s ml=%s' % (bool(mc), bool(ms), bool(mk), bool(ml))}

    base, step = _xor_num(mc.group(1) + '^' + mc.group(2)), int(mc.group(3))
    shift, pmask = int(ms.group(2)), int(ms.group(5))
    kv1, kv2 = mk.group(1), mk.group(4)
    kA = (_xor_num(mk.group(2)), _xor_num(mk.group(3)))
    kB = (_xor_num(mk.group(5)), _xor_num(mk.group(6)))
    lim = kB if ml.group(2) == kv2 else kA
    nbytes = lim[1] - lim[0]

    seg = html[mk.start(): mk.end() + 900]
    if re.search(r'getUint32\([^)]*,\s*false\s*\)', seg):
        endians = ['be', 'le']
    elif re.search(r'getUint32\([^)]*,\s*true\s*\)', seg):
        endians = ['le', 'be']
    else:
        sh = re.findall(r'\)\s*<<\s*(\d+)\)', seg)
        endians = (['le', 'be'] if sh[:2] == ['8', '16']
                   else (['be', 'le'] if sh[:2] == ['16', '8'] else ['le', 'be']))

    def gv(rg, i):
        return buf[rg[0] + i] if i < rg[1] - rg[0] else 0

    got = None
    for endian in endians:
        slots = {}
        for i in range(nbytes // 4):
            q = [gv(kA, 4 * i + j) ^ gv(kB, 4 * i + j) for j in range(4)]
            w32 = (q[0] | q[1] << 8 | q[2] << 16 | q[3] << 24) if endian == 'le' \
                else (q[0] << 24 | q[1] << 16 | q[2] << 8 | q[3])
            v = (w32 ^ ((base + i * step) & 0x7fffffff)) & 0xffffffff
            j, pth = v >> shift, v & pmask
            if j < 64:
                slots[j] = px[pth] if pth < len(px) else None
        if all(slots.get(k) is not None for k in range(32)):
            got = (endian, slots)
            break
    if not got:
        return {'fail': 'shuffle %s nbytes=%s px=%s' % (endians, nbytes, len(px))}
    endian, slots = got
    info = {
        'header_name': ''.join('%02x' % slots[k] for k in range(16)),
        'header_value': ''.join('%02x' % slots[k] for k in range(16, 32)),
        'shift': shift, 'pmask': pmask, 'endian': endian, 'nbytes': nbytes,
        'buf': len(buf), 'px': len(px), 'filled': len(slots),
    }
    mm = re.search(r'"(x-gaze-[0-9a-f]{24})"', html)
    m3 = re.search(r'\s(g[0-9a-f]{12,})="([0-9a-f]{32,})"', html)
    info['dom_header'] = mm.group(1) if mm else None
    info['dom_token'] = m3.group(2) if m3 else None
    info['ok'] = bool(info['dom_header'] and info['dom_token'])
    return info


def _solve_pixel_proof(html):
    """新版优先，失败自动回退旧版实现。返回 {'header_name','header_value'} 或 None"""
    try:
        info = _extract_proof_v3(html)
    except Exception as e:
        info = {'fail': 'exc %s: %s' % (type(e).__name__, str(e)[:120])}
    if info and info.get('header_name') and info.get('header_value'):
        if info['filled'] < 32:
            print('[gazes] 新版证明槽位未填满(%s/32) endian=%s' % (info['filled'], info['endian']))
        return {'header_name': info['header_name'], 'header_value': info['header_value']}
    print('[gazes] 新版证明提取失败: %s' % (info.get('fail') if isinstance(info, dict) else info))
    old = _solve_pixel_proof_v1(html)
    if old:
        print('[gazes] 已回退旧版证明提取(header=%s...)' % str(old.get('header_name'))[:24])
    return old


def _solve_pixel_proof_v1(html):
    try:
        m = re.search(r'<img id="([^"]+)" src="(data:image/bmp;base64,[^"]+)"', html)
        if not m:
            return None
        pixels = decode_data_bmp(m.group(2))

        st = html.find('getImageData(0, 0, 10, 10).data')
        ed = html.find('catch', st)
        if st < 0 or ed < 0:
            return None
        seg = html[st:ed]

        pair_re = re.compile(
            r"const (%s)=Uint8Array\.from\(atob\('([^']*)'\),%s=>%s\.charCodeAt\(0\)\),"
            r"(%s)=Uint8Array\.from\(atob\('([^']*)'\),%s=>%s\.charCodeAt\(0\)\)"
            % (VAR, VAR, VAR, VAR, VAR, VAR))
        pairs = []
        for pm in pair_re.finditer(seg):
            pairs.append((pm.group(1), base64.b64decode(pm.group(2)),
                          pm.group(3), base64.b64decode(pm.group(4)),
                          pm.start(), pm.end()))
        if not pairs:
            return None

        env = {}

        def run_pixel_loop(a, b, xor0):
            n = len(a) // 2
            out = bytearray(n)
            for k in range(n):
                w16 = (a[2 * k] ^ b[2 * k]) | ((a[2 * k + 1] ^ b[2 * k + 1]) << 8)
                w16 ^= (xor0 + k * 40503) & 0xffff
                out[k] = pixels[(((w16 >> 4) & 15) * 10 + (w16 & 15)) * 4 + ((w16 >> 8) & 3)]
            return bytes(out)

        name_hex = val_hex = None
        for pi, (n1, b1, n2, b2, ps, pe) in enumerate(pairs):
            nxt = pairs[pi + 1][5] if pi + 1 < len(pairs) else len(seg)
            t = seg[pe:nxt]

            if '3571' in t:
                gm = re.search(r'(%s)=\[((?:%s,)*%s)\]' % (VAR, VAR, VAR), t)
                if not gm:
                    return None
                garr = [env[n.strip()] for n in gm.group(2).split(',')]
                xys = re.findall(r'\(\((\d+)\^(\d+)\)\+(\w+)\*3571', t)
                x, y = int(xys[0][0]), int(xys[0][1])
                s = bytearray()
                for i in range(32):
                    w16 = (b1[2 * i] ^ b2[2 * i]) | ((b1[2 * i + 1] ^ b2[2 * i + 1]) << 8)
                    w16 ^= (x ^ y) + i * 3571
                    w16 &= 0xffff
                    s.append(garr[w16 & 7][w16 >> 3])
                name_hex = binascii.hexlify(bytes(s[:16])).decode()
                val_hex = binascii.hexlify(bytes(s[16:])).decode()
                break
            elif '40503' in t:
                xys = re.findall(r'\(\((\d+)\^(\d+)\)\+(\w+)\*40503', t)
                if not xys:
                    return None
                env['_PAIR_%d' % pi] = run_pixel_loop(b1, b2, int(xys[0][0]) ^ int(xys[0][1]))
            elif 'Array.from' in t:
                rm = re.search(r'const (%s)=Array\.from\(' % VAR, t)
                cm = re.search(
                    r'Array\.from\((%s),\((%s),(%s)\)=>(%s)\[\((%s)\^(%s)\[(%s)\]\)\^\(\(\((\d+)\^(\d+)\)\+%s\*29\)&255\)\]'
                    % (VAR, VAR, VAR, VAR, VAR, VAR, VAR, VAR), t)
                if not rm or not cm:
                    return None
                prev_name = cm.group(4)
                x, y = int(cm.group(8)), int(cm.group(9))
                src = env.get(prev_name) or env.get('_PAIR_%d' % (pi - 1))
                d, e_arr = b1, b2
                env[rm.group(1)] = bytes(
                    src[(d[i] ^ e_arr[i]) ^ ((x ^ y) + i * 29 & 255)] for i in range(len(d)))
        if name_hex and val_hex:
            return {'header_name': name_hex, 'header_value': val_hex}
        return None
    except Exception:
        return None


def _extract_dom_token(html):
    """新版优先：header 名形如 x-gaze-<24hex>，DOM 属性形如 g<12hex>="<32+hex token>"
    旧版(随机 randomDomHeader/randomDomAttr)作回退。返回 (header, token) 或 (None, None)"""
    try:
        m = re.search(r'"(x-gaze-[0-9a-f]{24})"', html)
        hdr = m.group(1) if m else None
        tok = None
        if hdr:
            m3 = re.search(r'\s(g[0-9a-f]{12,})="([0-9a-f]{32,})"', html)
            if m3:
                tok = m3.group(2)
        if hdr and tok:
            return hdr, tok
        if hdr and not tok:
            print('[gazes] 新版 DOM token 提取失败(header=%s)，回退旧版' % hdr)
        return _extract_dom_token_v1(html)
    except Exception:
        return None, None


def _extract_dom_token_v1(html):
    try:
        m2 = re.search(r'randomDomHeader\s*=\s*"([^"]+)"', html)
        hdr = m2.group(1) if m2 else None
        m = re.search(r'randomDomAttr\s*=\s*"([^"]+)"', html)
        if not m:
            return hdr, None
        attr = m.group(1)
        m3 = re.search(re.escape(attr) + r'="([^"]+)"', html)
        tok = m3.group(1) if m3 else None
        return hdr, tok
    except Exception:
        return None, None

# ======================================================================
# 04 页面解析 + 首页/分类/详情/搜索
#   说明：详情页记录的剧集列表仅用于「详情展示 + 播放页 URL 生成」，
#   t3 不再做服务器端的整集预热/捕获，故只需一个轻量字典与锁。
# ======================================================================
_CACHE_LOCK = threading.Lock()
_DETAIL_EPISODES = {}

def _parse_card(card):
    link_elem = card.select_one('a[href*="play/"]') or card.select_one('a[href]')
    if not link_elem:
        return None
    href = link_elem.get('href', '') or ''
    m = re.search(r'play/([0-9a-fA-F]+)', href)
    if not m:
        return None
    vod_id = m.group(1)

    vod_name = ''
    for sel in ('h3 span', 'h3', 'h5', 'h4', 'h2 span'):
        node = card.select_one(sel)
        if node:
            vod_name = node.get_text(strip=True)
            if vod_name:
                break
    if not vod_name:
        vod_name = (link_elem.get('aria-label') or '').replace('播放', '').strip()
    if not vod_name:
        img_alt = card.select_one('img[alt]')
        vod_name = (img_alt.get('alt') or '').strip() if img_alt else ''

    vod_pic = ''
    for img_elem in card.select('img'):
        src = (img_elem.get('data-src') or img_elem.get('src') or '').strip()
        if not src or 'colorful.svg' in src or 'nopic' in src or 'noimg' in src:
            continue
        if src.startswith('//'):
            src = 'https:' + src
        elif src.startswith('/'):
            src = SITE_URL + src
        vod_pic = src
        break

    remarks = []
    badges = card.select('.badge-pill') or card.select('.Q div')
    for badge in badges:
        txt = badge.get_text(strip=True)
        if txt and txt not in ('热门', '加入待看片单'):
            remarks.append(txt)

    if not vod_name:
        return None
    return {
        "vod_id": vod_id,
        "vod_name": vod_name,
        "vod_pic": vod_pic,
        "vod_remarks": ' '.join(remarks),
    }


def _parse_cards(soup):
    cards = soup.select('article') or soup.select('a[href*="play/"]')
    items = []
    for card in cards:
        item = _parse_card(card)
        if item:
            items.append(item)
    return items


def _is_cap_page(soup):
    if soup.select_one('cap-widget'):
        return True
    try:
        title = (soup.title.get_text(strip=True) if soup.title else '') or ''
    except Exception:
        title = ''
    try:
        head_text = soup.get_text(strip=True)[:300]
    except Exception:
        head_text = ''
    return bool(re.search(r'请稍候|请稍等|访问验证', title + head_text[:300]))


def _meta(soup, prop):
    node = soup.select_one('meta[property="%s"]' % prop) or \
           soup.select_one('meta[name="%s"]' % prop)
    if node:
        return (node.get('content') or '').strip()
    return ''


def _mlist_to_videos(mlist):
    items = []
    for movie in mlist:
        if not isinstance(movie, dict):
            continue
        mid = movie.get('mid')
        title = (movie.get('title') or '').strip()
        if not mid or not title:
            continue
        grade = movie.get('grade') or ''
        items.append({
            "vod_id": str(mid),
            "vod_name": title,
            "vod_pic": movie.get('cover_img') or '',
            "vod_remarks": (f"豆瓣 {grade}" if grade not in (None, '', '0', 0) else ''),
        })
    return items


def _set_site(url):
    """切换源站域名：同步全局与单例会话，换域时清空旧域 cookie/盾状态
    （盾 cookie 是按 domain 签发的，跨域必须重新过盾）。"""
    global SITE_URL
    url = str(url).rstrip('/')
    old = SITE_URL
    if url == old:
        _SITE_STATE['cur'] = url
        try:
            _sess.site = url
        except Exception:
            pass
        return
    SITE_URL = url
    _SITE_STATE['cur'] = url
    try:
        _sess.site = url
        _sess.sess.cookies.clear()
        _sess._cap_redeem_ts = 0.0
        _sess._redeem_fail_until = 0.0
        _sess._chal_info = ''
        _sess._last_get_err = ''
        # Referer/Origin 跟随当前域名，避免同一会话里跨域请求头自相矛盾触发风控
        _sess.sess.headers.update({'Referer': url + '/', 'Origin': url})
    except Exception:
        pass
    print('[注视] 切换源站域名: %s -> %s' % (old, url))


def _auto_site(force=False, budget=3):
    """多域名自适应：先信任落盘的可用域名，不可用则按候选表探测切换。

    单次最多试 budget 个域名，避免壳内 homeContent 超时；
    全部不可用时也置 ready，避免每次调用都全量重探（重启壳即重来）。
    """
    if _SITE_STATE['ready'] and not force:
        return SITE_URL
    with _SITE_LOCK:
        if _SITE_STATE['ready'] and not force:
            return SITE_URL
        order = []
        cur = _SITE_STATE['cur'] or _read_shield_site() or SITE_URL
        for c in [cur] + SITE_CANDIDATES:
            c = str(c).rstrip('/')
            if c and c not in order:
                order.append(c)
        n = len(order)
        start = _SITE_STATE['probe_from'] % n
        picked = [order[(start + i) % n] for i in range(min(budget, n))]
        for i, c in enumerate(picked):
            try:
                _set_site(c)
                got = _home()
                if got.get('list'):
                    _SITE_STATE['ready'] = True
                    _SITE_STATE['probe_from'] = (start + i + 1) % n
                    _save_shield_site(c)
                    print('[注视] 域名探测成功: %s（首页 %d 条）' % (c, len(got['list'])))
                    return c
                print('[注视] 域名 %s 首页无数据，试下一个' % c)
            except Exception as e:
                print('[注视] 域名 %s 不可用: %s: %s'
                      % (c, type(e).__name__, str(e)[:140]))
            _SITE_STATE['probe_from'] = (start + i + 1) % n
        _SITE_STATE['ready'] = True
        return SITE_URL


def _site_diag():
    """诊断串：当前域名 / 最近一次请求异常 / 盾状态 / 运行环境版本。
    环境版本一并透出，便于判断壳内 Python 栈（requests/urllib3 过旧会直接请求失败）。"""
    env = ''
    try:
        import sys as _sys
        _rv = ''
        try:
            _rv = getattr(__import__('requests'), '__version__', '?')
        except Exception:
            _rv = '?'
        try:
            _uv = getattr(__import__('urllib3'), '__version__', '?')
        except Exception:
            _uv = '?'
        env = 'py=%s req=%s u3=%s' % (_sys.version.split()[0], _rv, _uv)
    except Exception:
        pass
    return ('site=%s | get_err=%s | 盾=%s | %s'
            % (SITE_URL, (getattr(_sess, '_last_get_err', '') or '无')[:120],
               (getattr(_sess, '_last_redeem_diag', '') or '无')[:160], env))


def _home():
    """首页：公开 SSR，无需验证。"""
    resp = _sess.get_page(SITE_URL + '/')
    if resp is None:
        raise RuntimeError('GET / 失败：resp is None')
    soup = BeautifulSoup(resp.text, 'html.parser')
    if _is_cap_page(soup):
        raise RuntimeError('首页命中 cap 验证页，请检查会话/UA')
    return {"class": CATEGORIES, "list": _parse_cards(soup)[:40],
            "filters": _filter_meta()}


def _category(tid, pg=1, ext=None):
    page = int(pg) if pg else 1
    mform = MFORM_MAP.get(tid, '1')
    all_filters = _filter_meta()
    # 分类接口只下发当前分类 id 对应的筛选组（TVBox 规范）
    filters = {tid: all_filters.get(tid, [])} if tid else all_filters

    # t3：筛选参数由壳经 categoryContent(extend) 传入；空值回退站点默认
    ex = dict(ext or {})
    def ev(k):
        v = ex.get(k)
        return v if isinstance(v, str) and v else None
    sort = ev('sort') or 'updatetime'
    genre_arr = ev('genre') or 'all'
    mcountry = ev('area') or 'all'
    years = ev('year') or 'all'

    # 站点列表不 SSR：走 POST /filter_movielist（canvas 证明头 + DOM token）
    data = _sess.post_movielist(mform, page=page, sort=sort,
                                mcountry=mcountry, genre_arr=genre_arr,
                                years=years)
    if data is None:
        rdiag = getattr(_sess, '_last_redeem_diag', '') or '无(未进入过盾)'
        gerr = getattr(_sess, '_last_get_err', '')   # 并发加固：透出 _get 真实异常
        rdiag = ('%s | _get_err=%s' % (rdiag, gerr)) if gerr else rdiag
        raise RuntimeError('分类 movielist 失败(None) tid=%s rdiag=%s' % (tid, rdiag))
    if data.get('_status') in (419, 428):
        raise RuntimeError('分类 movielist 触发盾失效/冷却 http=%s tid=%s' % (data.get('_status'), tid))
    if data.get('code') != 1 or not isinstance(data.get('mlist'), list):
        raise RuntimeError('分类 movielist code!=1 tid=%s status=%s body=%s'
                           % (tid, data.get('_status'), str(data)[:200]))

    vids = _mlist_to_videos(data['mlist'])
    total = int(data.get('total') or 0)
    try:
        pagecount = max(1, int(data.get('pages') or 0) or 1)
    except (TypeError, ValueError):
        pagecount = 1
    if pagecount < page:
        pagecount = page
    return {"list": vids, "page": page, "pagecount": pagecount,
            "limit": 36, "total": total or len(vids), "filters": filters}


def _detail(vod_id):
    if not vod_id:
        raise ValueError('missing vod_id')
    url = '%s/play/%s' % (SITE_URL, vod_id)
    resp = _sess.get_page(url)
    if resp is None:
        raise RuntimeError('详情 GET 失败：resp is None id=%s' % vod_id)
    soup = BeautifulSoup(resp.text, 'html.parser')

    detail_ok = bool(soup.select_one('#play-source-panel-g1')
                     or soup.select_one('[data-source-group]')
                     or soup.select_one('.playbtn')
                     or soup.select_one('.eZ'))
    if _is_cap_page(soup) or not detail_ok:
        has_vs = bool(_shield_cookie(_sess.sess.cookies))
        raise RuntimeError('详情未过盾 id=%s cap=%s detail_ok=%s vs=%s title=%r len=%s'
                           % (vod_id, _is_cap_page(soup), detail_ok, has_vs,
                              (soup.title.get_text(strip=True)[:40] if soup.title else ''),
                              len(resp.text or '')))

    vod_name = _meta(soup, 'og:title')
    if vod_name:
        vod_name = re.sub(r'[（(]?在线播放[）)]?[-_|].*$', '', vod_name).strip()
    if not vod_name:
        h5 = soup.select('.eZ h5.lh')
        if h5:
            vod_name = h5[0].get_text(strip=True)
    if not vod_name:
        m = re.search(r'<title>([^<]+)</title>', resp.text)
        if m:
            vod_name = m.group(1).split('在线播放')[0].strip()

    vod_pic = _meta(soup, 'og:image')
    if not vod_pic:
        img_elem = soup.select_one('.dX .cq img.jr') or soup.select_one('img[data-src]') or soup.select_one('img')
        if img_elem:
            vod_pic = img_elem.get('data-src', '') or img_elem.get('src', '')

    vod_content = _meta(soup, 'og:description')
    if not vod_content:
        desc = soup.select_one('.eZ p.ey')
        vod_content = desc.get_text(' ', strip=True) if desc else ''

    remark_tags = []
    for a in soup.select('.eZ a.dG'):
        txt = a.get_text(strip=True)
        if txt:
            remark_tags.append(txt)
    vod_remarks = '/'.join(remark_tags)

    # 剧集：每个 playbtn 指向详情页（同 URL），由 /play 接口在服务器端解密
    episodes = []
    panel = soup.select_one('#play-source-panel-g1') or soup.select_one('[data-source-group]')
    playbtns = panel.select('.playbtn') if panel else []
    if not playbtns:
        playbtns = soup.select('.playbtn')
    for btn in playbtns:
        ep_name = btn.get_text(strip=True) or f"第{len(episodes)+1}集"
        # 每集 URL 携带唯一 path(集索引)/ep(data-id) 参数，供 _extract_vid 生成唯一 vid key、
        # _capture_vid_map 精确定位并点击对应 playbtn，避免「点哪集都播第1集」的串集问题
        dpath = btn.get('data-path', '') if hasattr(btn, 'get') else ''
        did = btn.get('data-id', '').strip() if hasattr(btn, 'get') else ''
        ep_suffix = ''
        if did:
            ep_suffix += '?ep=%s' % did
        if dpath:
            ep_suffix += ('&' if ep_suffix else '?') + 'path=%s' % dpath
        episodes.append(f"{ep_name}${url}{ep_suffix}")

    # 跟随式智能预载：打开详情页时记录完整剧集 URL 列表（按集顺序，供定位下一集），
    # 但【只预载第 1 集】。后续用户播放第 k 集时，在 /play 里再预载第 k+1 集，
    # 做到「始终超前 1 集」，避免全集预载浪费服务器流量（尤其动漫画数百上千集）。
    full_ep_urls = []
    for _e in episodes:
        _u = _e.split('$', 1)[1] if '$' in _e else _e
        full_ep_urls.append(_u)
    with _CACHE_LOCK:
        _DETAIL_EPISODES[vod_id] = full_ep_urls
        # LRU 上限：仅保留最近 20 部的全集 URL，防止长期运行无限增长占用 2G 内存
        _DETAIL_MAX = 20
        while len(_DETAIL_EPISODES) > _DETAIL_MAX:
            _DETAIL_EPISODES.pop(next(iter(_DETAIL_EPISODES)), None)
    # 智能预载策略（v2.3）：detail 阶段【不预载任何集】，仅记录全集 URL。
    # 原因：用户实测反馈"不是每次都看第一集"，播放器不选集就不预载。
    # v2.9.9.2：已移除 _warm_follow 跟随式预载（用户要求，避免浪费时间），
    # 切集时由 /play 即时捕获、返回前生成 m3u8。
    return {"list": [{
        "vod_id": vod_id,
        "vod_name": vod_name,
        "vod_pic": vod_pic,
        "vod_content": vod_content,
        "vod_remarks": vod_remarks,
        "vod_play_from": '默认',
        "vod_play_url": '#'.join(episodes) if episodes else '',
    }]}


def _search(key, pg=1):
    if not key:
        raise ValueError('missing wd')
    page = int(pg) if pg else 1
    data = _sess.post_movielist('all', page=page, title=key, sort='updatetime')
    if data is None:
        rdiag = getattr(_sess, '_last_redeem_diag', '') or '无(未进入过盾)'
        raise RuntimeError('搜索 movielist 失败(None) key=%r rdiag=%s' % (key, rdiag))
    if data.get('_status') in (419, 428):
        raise RuntimeError('搜索 movielist 触发盾失效/冷却 http=%s' % data.get('_status'))
    if data.get('code') != 1 or not isinstance(data.get('mlist'), list):
        raise RuntimeError('搜索 movielist code!=1 status=%s body=%s'
                           % (data.get('_status'), str(data)[:200]))

    vids = _mlist_to_videos(data['mlist'])
    try:
        pagecount = max(1, int(data.get('pages') or 0) or 1)
    except (TypeError, ValueError):
        pagecount = 1
    if pagecount < page:
        pagecount = page
    return {"list": vids, "page": page, "pagecount": pagecount}

# ======================================================================
# 05 hipy 本地源（t3）接口层：无需服务器，壳内 Python 直跑
# ======================================================================
_T3_VER = 't3-1.2'

# ----------------------------------------------------------------------
# 诊断外显（借鉴参考源「把失败原因变成可见条目/日志」的做法）：
# 壳里看不到 print 时，把失败原因作为一条可点击的条目塞进列表，
# 直接在电视/手机界面上就能看到到底是网络、风控还是解析问题。
# ----------------------------------------------------------------------
_DIAG_PREFIX = 'gazes_diag:'
_DIAG = {'msg': ''}


def _diag(msg):
    _DIAG['msg'] = str(msg)[:800]
    print('[注视][诊断] %s' % _DIAG['msg'])
    return _DIAG['msg']


def _diag_vod(text):
    return {'vod_id': _DIAG_PREFIX + '0',
            'vod_name': '[诊断] %s' % str(text)[:80],
            'vod_pic': '', 'vod_remarks': '点开看原因'}


# ----------------------------------------------------------------------
# 盾 cookie 持久化：_SHIELD_FILES 已在文件前部常量区定义（_sess 创建时即需读取）
# ----------------------------------------------------------------------


def _cookie_header():
    """把当前会话里的全部 cookie（含每次 redeem 随机命名的盾 cookie）拼成请求头，
    交给壳内浏览器/播放器复用，尽量免掉「访问验证」弹窗。"""
    try:
        return '; '.join('%s=%s' % (c.name, c.value) for c in _sess.sess.cookies)
    except Exception:
        return ''


def _play_header():
    hdr = {'User-Agent': UA, 'Referer': SITE_URL + '/', 'Origin': SITE_URL}
    ck = _cookie_header()
    if ck:
        hdr['Cookie'] = ck
    return hdr


def _norm_extend(extend):
    """壳可能把筛选参数作为 dict 传进来，也可能传 JSON 字符串，统一成 dict。"""
    if isinstance(extend, dict):
        return dict(extend)
    if isinstance(extend, str) and extend.strip().startswith('{'):
        try:
            got = json.loads(extend)
            return got if isinstance(got, dict) else {}
        except Exception:
            return {}
    return {}


# ======================================================================
# 06 本地播放页代理（v3.3 新增）
#   问题：壳体走 parse=1 把源站播放页交给 webview 时，webview 里没有盾 cookie，
#         站点会弹「点击完成验证」，用户必须手点一次才能播。
#   方案：源在手机本机起一个只读代理（内容全部来自源站），由源侧会话带上新鲜盾
#         cookie 去取页面，并把页面里的绝对地址全部改写成同源相对地址，
#         再把本地地址交给壳内 webview。webview 全程只访问本机 IP，恒有盾，不弹验证。
#   安全：只代理页面与页面所需资源；出口固定为源站域名与 CDN 域名，不开放任意目标；
#         监听仅本机/局域网，进程退出即消失。
#   回退：PX_ENABLE=False 或端口起不来时，自动回到 v3.2 旧行为（直接交源站 URL）。
# ======================================================================
# v3.4：默认改为 False（直接交源站播放页给壳内 webview）。
# 实测原因：gazes 的播放链路依赖页面内 Go WASM（DimGive/epi/rdx/nihilism）在真实
# 浏览器环境里解出 m3u8，且 WASM 会检测 navigator.webdriver / Error.stack 中的
# eval 痕迹 / canvas 渲染完整性 / $cdc_ 等自动化特征。壳内原生 webview 天然通过
# 这些检测；而本地代理改写页面后同源上下文被破坏，解流失败率显著升高。
# 如确需代理模式可手动改回 True。
PX_ENABLE = False
PX_BIND_ALL = True          # True=绑定 0.0.0.0 并对壳通告局域网 IP（躲开部分壳对 127.0.0.1 的过滤）
PX_BASE_PORT = 19777        # 起始端口，被占用则 +1，最多试 5 个；全失败则回退旧行为
PX_PAGE_TTL = 120           # 播放页在本地缓存秒数，避免反复打源站
PX_CDN_HOST = 'oos-cn.ctyunapi.cn'
PX_ORIGINS = ('https://gaze.red', 'https://gazes.top', 'https://gazes.store',
              'https://gaze.show', 'https://gazes.host', 'https://gazes.site',
              'https://gaze.run')

PX_WHITELIST_RE = re.compile(
    r'<script[^>]*>(?:(?!</script>).)*?location\.hostname\.toLowerCase\(\)'
    r'(?:(?!</script>).)*?</script>', re.S | re.I)
PX_CSP_RE = re.compile(
    r'<meta[^>]*http-equiv=["\']?Content-Security-Policy["\']?[^>]*>', re.I)

# 页面里站点 JS 自己也会拼 ctyunapi 的绝对地址；注入 shim 把 fetch/XHR 的 CDN 地址
# 改回本代理的 /__cdn 前缀，保证页面内所有请求都留在本机、都带盾。
PX_SHIM = """<script>
(function(){
  var B=location.origin;
  function fix(u){
    try{
      if(typeof u!=='string') return u;
      if(u.indexOf('//oos-cn.ctyunapi.cn')===0) return B+'/__cdn'+u.slice(20);
      if(u.indexOf('https://oos-cn.ctyunapi.cn')===0) return B+'/__cdn'+u.slice(26);
      if(u.indexOf('http://oos-cn.ctyunapi.cn')===0) return B+'/__cdn'+u.slice(25);
    }catch(e){}
    return u;
  }
  function log(s){ try{ console.log('[gaze-proxy] '+s); }catch(e){} }
  var _f=window.fetch;
  if(_f){ window.fetch=function(a,b){
    try{
      if(typeof a==='string'){ a=fix(a); }
      else if(a && a.url){ var nu=fix(a.url); if(nu!==a.url){ a=new Request(nu,{method:a.method,headers:a.headers,mode:a.mode,credentials:a.credentials,redirect:a.redirect,referrer:a.referrer,body:a.body}); } }
    }catch(e){}
    return _f.call(this,a,b); }; }
  var _o=XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open=function(m,u){ var a=[].slice.call(arguments); try{a[1]=fix(u);}catch(e){} return _o.apply(this,a); };
  try{
    var _cou=URL.createObjectURL;
    URL.createObjectURL=function(o){
      var u=_cou.call(URL,o);
      try{
        log('createObjectURL type='+((o&&o.type)||'')+' size='+((o&&o.size)||0));
        if(o && typeof Blob!=='undefined' && o instanceof Blob && o.size>0 && o.size<300000
           && (!o.type||o.type.indexOf('text')>=0||o.type.indexOf('json')>=0)){
          var fr=new FileReader();
          fr.onload=function(){ log('BLOB>> '+String(fr.result).slice(0,1500)); };
          fr.readAsText(o);
        }
      }catch(e){}
      return u; };
  }catch(e){}
  try{
    if(window.MediaSource && MediaSource.prototype.addSourceBuffer){
      var _asb=MediaSource.prototype.addSourceBuffer;
      MediaSource.prototype.addSourceBuffer=function(t){ log('addSourceBuffer '+t); return _asb.apply(this,arguments); };
    }
  }catch(e){}
  log('shim installed');
})();
</script>"""

_PX_STATE = {'base': '', 'httpd': None, 'lock': threading.Lock(), 'err': ''}
_PX_PAGE_CACHE = {}


def _px_lan_ip():
    """取本机局域网 IP（手机连 WiFi 时的 192.168.x.x）；失败返回空串。"""
    for probe in (('8.8.8.8', 80), ('114.114.114.114', 53)):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.6)
            s.connect(probe)
            ip = s.getsockname()[0]
            s.close()
            if ip and ip != '0.0.0.0' and not ip.startswith('127.'):
                return ip
        except Exception:
            try:
                s.close()
            except Exception:
                pass
    return ''


def _px_rewrite_html(text):
    text = PX_WHITELIST_RE.sub('', text)
    text = PX_CSP_RE.sub('', text)
    text = text.replace('https://' + PX_CDN_HOST + '/', '/__cdn/')
    text = text.replace('//' + PX_CDN_HOST + '/', '/__cdn/')
    for o in PX_ORIGINS:
        text = text.replace(o, '')
    if '<head>' in text:
        text = text.replace('<head>', '<head>' + PX_SHIM, 1)
    else:
        text = PX_SHIM + text
    return text


def _px_rewrite_text(text):
    text = text.replace('https://' + PX_CDN_HOST + '/', '/__cdn/')
    text = text.replace('//' + PX_CDN_HOST + '/', '/__cdn/')
    for o in PX_ORIGINS:
        text = text.replace(o, '')
    return text


def _px_fetch_page(url):
    """取播放页（自动过盾 + 本地缓存）。返回 (status, headers, content)。"""
    hit = _PX_PAGE_CACHE.get(url)
    if hit and time.time() - hit[0] < PX_PAGE_TTL:
        return hit[1], hit[2], hit[3]
    r = _sess.get_page(url)
    if r is None:
        raise IOError('get_page 返回空（网络不通或盾失败）')
    out = (r.status_code, r.headers, r.content or b'')
    _PX_PAGE_CACHE[url] = (time.time(), out[0], out[1], out[2])
    if len(_PX_PAGE_CACHE) > 24:
        _PX_PAGE_CACHE.clear()
        _PX_PAGE_CACHE[url] = (time.time(), out[0], out[1], out[2])
    return out


def _px_prime(url):
    """预检：让每次点播时页面已经在本地缓存里，webview 打开即秒出。"""
    try:
        st, _h, raw = _px_fetch_page(url)
        body = (raw or b'')[:400000].decode('utf-8', 'replace')
        if 'playbtn' in body or 'data-src' in body:
            return '播放页预检通过 http=%s len=%d' % (st, len(raw))
        return '播放页无播放结构 http=%s len=%d（可能仍是验证页）' % (st, len(raw))
    except Exception as e:
        return '播放页预检异常 %s: %s' % (type(e).__name__, str(e)[:120])


class _PXHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'GazeLocal/3.3'

    def log_message(self, fmt, *args):
        try:
            print('[注视][代理] %s %s' % (self.command, self.path[:150]))
        except Exception:
            pass

    def do_GET(self):
        self._px_handle('GET')

    def do_POST(self):
        self._px_handle('POST')

    def do_HEAD(self):
        self._px_handle('HEAD')

    def _px_handle(self, method):
        site = SITE_URL.rstrip('/')
        try:
            ln = int(self.headers.get('Content-Length') or 0)
        except Exception:
            ln = 0
        body = self.rfile.read(ln) if ln else None

        is_cdn = self.path.startswith('/__cdn')
        if is_cdn:
            url = 'https://' + PX_CDN_HOST + self.path[len('/__cdn'):]
        else:
            url = site + self.path
        # 只允许源站与 CDN，防止被当成开放代理
        if not (is_cdn or url.startswith(site)):
            self._px_send(403, 'text/plain; charset=utf-8',
                          b'local proxy: target not allowed', {}, method)
            return

        fwd = {}
        for k in ('Range', 'Content-Type', 'Accept', 'Accept-Language',
                  'If-None-Match', 'If-Modified-Since', 'X-Requested-With'):
            v = self.headers.get(k)
            if v:
                fwd[k] = v
        for k, v in self.headers.items():
            lk = k.lower()
            if lk.startswith('x-') or 'proof' in lk or lk == 'authorization':
                fwd[k] = v
        fwd['Referer'] = site + '/'
        fwd['Origin'] = site

        nav = (method == 'GET' and not is_cdn
               and 'text/html' in (self.headers.get('Accept') or ''))

        try:
            status, uh, raw = self._px_upstream(nav, url, method, body, fwd)
        except Exception as e:
            self._px_send(502, 'text/plain; charset=utf-8',
                          ('gaze-proxy upstream error: %s' % str(e)[:200]).encode('utf-8'),
                          {}, method)
            return

        ct = uh.get('Content-Type') or 'application/octet-stream'
        raw = raw or b''
        head = raw[:512]
        is_playlist = head.lstrip()[:7] == b'#EXTM3U'
        if is_playlist:
            print('[注视][代理] 命中播放清单 %d 字节 %s' % (len(raw), ct[:40]))

        lct = ct.lower()
        if not is_cdn and ('text/html' in lct or 'javascript' in lct or 'json' in lct):
            m = re.search(r'charset=([\w-]+)', ct, re.I)
            cs = m.group(1) if m else 'utf-8'
            try:
                txt = raw.decode(cs, 'replace')
            except Exception:
                txt = raw.decode('utf-8', 'replace')
            txt = _px_rewrite_html(txt) if 'text/html' in lct else _px_rewrite_text(txt)
            raw = txt.encode('utf-8')
            ct = re.sub(r'charset=[\w-]+', 'charset=utf-8', ct)

        hdrs = {}
        for k in ('Accept-Ranges', 'Content-Range', 'Last-Modified', 'ETag', 'Cache-Control'):
            v = uh.get(k)
            if v:
                hdrs[k] = v
        loc = uh.get('Location')
        if loc:
            for o in PX_ORIGINS:
                loc = loc.replace(o, '')
            loc = loc.replace('https://' + PX_CDN_HOST + '/', '/__cdn/')
        self._px_send(status, ct, raw, hdrs, method, loc)

    def _px_upstream(self, nav, url, method, body, fwd):
        if nav:
            return _px_fetch_page(url)
        r = _sess.sess.request(method, url, data=body, headers=fwd,
                               timeout=30, allow_redirects=False)
        return r.status_code, r.headers, (r.content or b'')

    def _px_send(self, code, ct, data, hdrs, method, loc=None):
        try:
            self.send_response(code)
            self.send_header('Content-Type', ct)
            self.send_header('Content-Length', str(len(data)))
            if loc:
                self.send_header('Location', loc)
            for k, v in hdrs.items():
                self.send_header(k, v)
            self.end_headers()
            if method != 'HEAD' and data:
                self.wfile.write(data)
        except Exception:
            pass


class _PXServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    timeout = 60


def _px_start():
    """启动本地代理，返回基地址（http://ip:port）；失败返回空串。"""
    if not PX_ENABLE:
        return ''
    if _PX_STATE['base']:
        return _PX_STATE['base']
    with _PX_STATE['lock']:
        if _PX_STATE['base']:
            return _PX_STATE['base']
        host = '0.0.0.0' if PX_BIND_ALL else '127.0.0.1'
        httpd = None
        last = ''
        for i in range(5):
            try:
                httpd = _PXServer((host, PX_BASE_PORT + i), _PXHandler)
                break
            except Exception as e:
                last = '%s: %s' % (type(e).__name__, str(e)[:80])
                httpd = None
        if httpd is None:
            _PX_STATE['err'] = '本地代理端口不可用(%s)' % last
            print('[注视][代理] 启动失败 %s' % _PX_STATE['err'])
            return ''
        port = httpd.server_address[1]
        t = threading.Thread(target=httpd.serve_forever, kwargs={'poll_interval': 0.3})
        t.daemon = True
        t.start()
        ip = _px_lan_ip() if PX_BIND_ALL else ''
        if not ip:
            ip = '127.0.0.1'
        _PX_STATE['httpd'] = httpd
        _PX_STATE['base'] = 'http://%s:%d' % (ip, port)
        print('[注视][代理] 已监听 %s（bind=%s）' % (_PX_STATE['base'], host))
        return _PX_STATE['base']


def _px_stop():
    try:
        if _PX_STATE['httpd']:
            _PX_STATE['httpd'].shutdown()
            _PX_STATE['httpd'].server_close()
    except Exception:
        pass
    _PX_STATE['httpd'] = None
    _PX_STATE['base'] = ''


def _px_play_url(src_url):
    """把源站播放页地址换成本地代理地址（/play/xxx?ep=.. 形式）。"""
    base = _PX_STATE['base']
    if not base:
        return ''
    try:
        p = urllib.parse.urlsplit(src_url)
        path = p.path or '/'
        q = ('?' + p.query) if p.query else ''
        return base + path + q
    except Exception:
        return ''


class Spider(_BaseSpider):
    """GAZES 注视影视 t3 本地源。

    与 t4 服务器源的差别只有两处：
      1) 没有 Flask，一切请求在壳内直连源站；
      2) 播放不在本机解 WASM，改为把播放页 URL + 盾 cookie 交给壳内浏览器嗅探。
    过盾（随机名盾 cookie / rsw 模幂 / 419+428 重过盾 / 像素证明头）与 t4 完全一致。
    """

    name = '注视'

    def getName(self):
        return self.name

    def init(self, extend=""):
        self._extend = extend or ''
        print('[注视] t3 本地源初始化 %s（无需服务器）' % _T3_VER)

        # 后台预热：先把盾 cookie 过出来，避免首页/分类首次请求卡在过盾
        def _warm():
            try:
                r = _sess.get_page(SITE_URL + '/')
                print('[注视] 预热完成 status=%s len=%s'
                      % (getattr(r, 'status_code', None), len(getattr(r, 'text', '') or '')))
            except Exception as e:
                print('[注视] 预热异常: %s' % str(e)[:160])

        try:
            threading.Thread(target=_warm, daemon=True).start()
        except Exception:
            pass

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(m3u8|mp4|m4v|ts)(\?|$)', str(url or ''), re.I))

    def manualVideoCheck(self):
        return False

    def homeVideoContent(self):
        return self.homeContent(True)

    def destroy(self):
        try:
            _sess.sess.close()
        except Exception:
            pass

    # ---------- 首页 ----------
    def homeContent(self, filter=True):
        """分类永不为空：源站请求失败也回退到内置分类表，避免壳里分类栏空白。"""
        result = {'class': CATEGORIES, 'list': [], 'filters': _filter_meta()}
        err = ''
        # v3.2：先做多域名自适应（落盘域名优先，不可用则按候选表探测切换）
        try:
            _auto_site()
        except Exception as e:
            print('[注视] 域名自适应异常:', str(e)[:150])
        for _round in range(2):
            err = ''
            try:
                got = _home()
                if got.get('list'):
                    result['list'] = got['list']
                if got.get('class'):
                    result['class'] = got['class']
                if got.get('filters'):
                    result['filters'] = got['filters']
                print('[注视] 首页 %d 条推荐 / %d 个分类（%s）'
                      % (len(result['list']), len(result['class']), SITE_URL))
            except Exception as e:
                err = '%s: %s' % (type(e).__name__, str(e)[:200])
                print('[注视] 首页异常(仍返回内置分类 %d 个): %s'
                      % (len(CATEGORIES), err))
            if result['list']:
                break
            if _round == 0:
                # 首轮失败：换域名再试一次（换域往往比死磕同一域名有效）
                print('[注视] 首页首轮失败，触发换域名重试')
                _auto_site(force=True)
        if not result['list']:
            # 首页取不到数据 = 网络/风控层面就挂了，把原因显性化，避免用户在壳里看到空白
            result['list'] = [_diag_vod(_diag('首页取不到数据 -> %s | %s'
                                              % (err or '源站返回空', _site_diag())))]
        return result

    # ---------- 分类 ----------
    def categoryContent(self, tid, pg, filter=True, extend=None):
        page = int(pg) if str(pg).isdigit() else 1
        result = {'list': [], 'page': page, 'pagecount': 1, 'limit': 36, 'total': 0}
        err = ''
        try:
            _auto_site()
        except Exception:
            pass
        ex = _norm_extend(extend)
        for _round in range(2):
            err = ''
            try:
                data = _category(tid, page, ex)
                result['list'] = data.get('list') or []
                result['page'] = data.get('page') or page
                result['pagecount'] = data.get('pagecount') or 1
                result['limit'] = data.get('limit') or 36
                result['total'] = data.get('total') or len(result['list'])
                print('[注视] 分类 tid=%s pg=%s -> %d 条 / 共 %s 页（%s）'
                      % (tid, page, len(result['list']), result['pagecount'], SITE_URL))
            except Exception as e:
                err = '%s: %s' % (type(e).__name__, str(e)[:220])
                print('[注视] 分类异常 tid=%s pg=%s: %s' % (tid, page, err))
            if result['list']:
                break
            if _round == 0:
                print('[注视] 分类首轮失败，触发换域名重试')
                _auto_site(force=True)
        if not result['list']:
            result['list'] = [_diag_vod(_diag('分类 %s 取不到数据 -> %s | %s'
                                              % (tid, err or '源站返回空', _site_diag())))]
        return result

    # ---------- 详情 ----------
    def detailContent(self, ids):
        vid = ids[0] if isinstance(ids, (list, tuple)) and ids else ids
        vid = str(vid or '')
        # 诊断条目：把最近一次失败原因当详情展示，用户截屏即可定位问题
        if vid.startswith(_DIAG_PREFIX):
            return {'list': [{
                'vod_id': vid, 'vod_name': '注视源诊断', 'vod_pic': '',
                'vod_content': _DIAG['msg'] or '无诊断信息',
                'vod_remarks': '', 'vod_play_from': '诊断', 'vod_play_url': '',
            }]}
        m = re.search(r'play/([0-9a-fA-F]+)', vid)
        if m:
            vid = m.group(1)
        try:
            return _detail(vid)
        except Exception as e:
            print('[注视] 详情异常 id=%s: %s' % (vid, str(e)[:240]))
            return {'list': []}

    # ---------- 搜索 ----------
    def searchContent(self, key, quick=None, pg="1"):
        page = int(pg) if str(pg).isdigit() else 1
        result = {'list': [], 'page': page, 'pagecount': 1, 'limit': 36, 'total': 0}
        err = ''
        try:
            data = _search(key, page)
            result['list'] = data.get('list') or []
            result['page'] = data.get('page') or page
            result['pagecount'] = data.get('pagecount') or 1
            result['total'] = len(result['list'])
            print('[注视] 搜索 key=%r pg=%s -> %d 条' % (key, page, len(result['list'])))
        except Exception as e:
            err = '%s: %s' % (type(e).__name__, str(e)[:220])
            print('[注视] 搜索异常 key=%r: %s' % (key, err))
        if not result['list']:
            result['list'] = [_diag_vod(_diag('搜索 %r 无结果 -> %s' % (key, err or '源站返回空')))]
        return result

    # ---------- 播放 ----------
    def playerContent(self, flag, id, vipFlags=None):
        """t3 无服务器：不在本机跑 playwright 解 WASM。

        v3.3：本机起只读代理，由源侧会话带新鲜盾 cookie 取播放页，
        页面里所有绝对地址都改写成本机同源地址，再把本机地址交给壳内 webview 加载：
        webview 全程只访问本机 IP，恒有盾，不再弹「点击完成验证」。
        代理起不来时自动回退 v3.2 旧行为（直接交源站地址 + 盾 cookie）。
        """
        raw = str(id or '')
        try:
            _auto_site()
        except Exception:
            pass
        url = raw
        if url.startswith('/'):
            url = SITE_URL + url
        elif not url.startswith('http'):
            url = '%s/play/%s' % (SITE_URL, url)

        hdr = _play_header()
        px_err = ''

        # ---- 首选：本地代理 ----
        try:
            base = _px_start()
        except Exception as e:
            base = ''
            px_err = '本地代理启动异常 %s: %s' % (type(e).__name__, str(e)[:100])
        if base:
            state = _px_prime(url)
            purl = _px_play_url(url)
            if purl:
                _diag('%s | 本地代理 %s' % (state, base))
                print('[注视] 播放(本地代理) %s -> %s | %s' % (url, purl, state))
                return {"parse": 1, "url": purl, "header": hdr,
                        "headers": hdr, "playUrl": ""}
            px_err = '本地代理地址生成失败'
        else:
            px_err = px_err or _PX_STATE['err'] or ('本地代理未启用 PX_ENABLE=%s' % PX_ENABLE)
        print('[注视] 本地代理不可用，回退旧行为：%s' % px_err)

        # ---- 回退：v3.2 旧行为（交源站播放页，可能仍需手点一次验证）----
        state = ''
        try:
            r = _sess.get_page(url)
            if r is None:
                state = '播放页取不到（网络不通或被风控）'
            else:
                body = getattr(r, 'text', '') or ''
                st = getattr(r, 'status_code', None)
                if st is not None and st >= 500:
                    # v3.4：源站 5xx（实测 gazes.top 频繁 520）时自动换域名重试一次
                    print('[注视] 播放页 http=%s，尝试切换域名' % st)
                    try:
                        new_site = _auto_site(force=True)
                    except Exception:
                        new_site = SITE_URL
                    if new_site and new_site.rstrip('/') != (SITE_URL or '').rstrip('/'):
                        url = new_site + ('/play/%s' % raw if not raw.startswith('http')
                                          else raw)
                        r = _sess.get_page(url)
                        body = getattr(r, 'text', '') or ''
                        st = getattr(r, 'status_code', None)
                        state = '切换域名->%s http=%s' % (new_site, st)
                if st in (419, 428):
                    state = '播放页盾失效 http=%s' % st
                elif 'playbtn' in body or 'data-src' in body:
                    state = '播放页预检通过 http=%s len=%d' % (st, len(body))
                else:
                    state = '播放页无播放结构 http=%s len=%d（可能仍是验证页）' % (st, len(body))
        except Exception as e:
            state = '播放页预检异常 %s: %s' % (type(e).__name__, str(e)[:120])
        _diag('%s | %s' % (state, px_err))
        print('[注视] 播放(交由壳嗅探) url=%s cookie_len=%d | %s'
              % (url, len(hdr.get('Cookie', '')), state))
        # header 与 headers 同时给出，兼容不同壳对字段名的取用差异
        return {"parse": 1, "url": url, "header": hdr, "headers": hdr, "playUrl": ""}
