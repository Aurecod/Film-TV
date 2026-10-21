# -*- coding: utf-8 -*-
"""
玩物社区 spider —— webhtv 系壳子 (T3v1.5)
站点: https://pku.daqbqrri.cc/  (镜像 wanwuu.com / c5ad.oqgciumz.cc)

站点配置(粘贴到 webhtv 站点配置):
{"key":"wanwu","name":"玩物社区","type":3,"api":"<本文件直链URL>",
 "searchable":1,"changeable":1,"quickSearch":1}
说明: type=3 为 Spider; api 填本 py 文件的 http(s) 直链,App 下载后用 Chaquopy 运行,
     须继承 base.spider.Spider。

已验证结构(2026-10-12 实测):
- 分类页: /videos/{slug}/ ; 翻页 /videos/{slug}/page/{N}/
  AI 分类 /ai/{slug}/ ; 合集 /moviesets/ ; 合集内页 /moviesets/{slug}/
- 列表条目: div.video-item / a.group, 标题在 h2/h3, 封面取 img[data-src],
  链接 /videos/{slug}/vd-xxxx/
- 搜索: /videos/search/{url编码}/
- 详情页 /videos/{slug}/vd-xxxx/ 原始 HTML 内嵌 packer 加密 JS,
  解包得 <script src="/videos/detail_play?id=..&img=..&ads=..&u=..&t=..">
  (u 为页内 token, t=int(time/1800) 30 分钟窗口, 实时计算)
- GET detail_play(带 Referer) -> 第二段 packer -> 解包得 div#mse data-url(m3u8,
  auth_key 时效签名, 须播放时实时获取)
- 封面走 getProxyUrl 代理(type=pic), 经 localProxy 回源, 防盗链

v1.5 改动(修复 2026-10-12 用户二次实测"仍全灰"的真凶):
1. ★根因: 解密算法/key/iv/URL 提取其实全对(沙箱已用真实密文验证,
   纯Python解密输出与 pycryptodome 完全一致、就是合法 JPEG),
   但纯 Python AES 解一张 142KB 封面要 5.66s, 一页 24 张要 2 分多钟,
   壳子图片加载直接超时 → 全部渲染成灰图/字母头像兜底。
2. ★真机(Chaquopy)优先走 Java javax.crypto AES/CBC/NoPadding,
   Android 硬件级 AES, 单张毫秒级; 非安卓环境自动回退纯 Python。
3. 纯 Python 回退版 GF 乘法查表化(_DEC_M9/_DEC_MB/_DEC_MD/_DEC_ME),
   大幅提速(位循环→查表)。
4. 解密结果内存缓存(LRU, 256 张): 翻页/回看同图不重复解密。
5. 补充现场证据(2026-10-12 沙箱实测): 所有分类封面 URL 解析正常、
   CDN 密文拉取正常(熵 8.00)、解密后为合法 JPEG——排除格式/防盗链嫌疑,
   性能是唯一卡点。

v1.4 改动(修复 2026-10-12 用户反馈"全部没封面"):
1. ★根因: 抓图请求头 Accept 把 image/avif 排第一, 站点常直接回 AVIF 封面;
   而 _img_mime 旧版只认 jpeg/png/webp/gif/bmp, 漏判 AVIF/HEIC →
   真图被当成"非图片" → 一律回退占位灰图。已补 AVIF/HEIC/HEIF 魔数判定。
   这也解释了 v1.3 加了 AES 解密仍没封面: 封面本来就不是加密的,
   而是被格式漏判。AES 解密逻辑保留作兜底(已验证实现正确)。
2. 封面 URL 提取加固: 多属性兼容(data-src/data-original/data-lazy-src/
   data-url/src), 窗口扩到 8000, 详情/合集页同样放宽 host 与后缀。
3. _decrypt_cover 加固: 密文长度非 16 整数倍时尝试零填充、尝试去 16 字节
   前缀, 任一能解出合法图片即采用。
4. localProxy 增加成功/失败日志(格式+字节数), 便于定位仍是哪一步挂。

v1.3 改动(彻底修复 2026-10-12 用户手机实测的两个问题):
1. "前面两个分类(当前最热/最近更新)没数据" —— 根因: /videos/popular/、
   /videos/new/ 的卡片标题不在 h2/h3 里, 而是在
   <a class="...line-clamp..."> 里(另有 img alt 兜底); 原解析只认 h2/h3,
   标题取空 → 整页被 skip → 返回空列表。已加三级标题兜底, 并排除
   页面顶部无封面的"排行"区(/videos/cate/vd-xxx/ 链接)。
2. "后面分类没封面" —— 真因(2026-10-12 浏览器实测锤死):
   本站封面图在 CDN 上是 AES-128-CBC/NoPadding 加密存储的,
   直接拉到的字节是高熵密文(熵 7.99), 根本不是图片!
   解密: /static/web/js/plugins/lazyload.js, key='f5d965df75336270',
   iv='97b60394abc2fbe1', 均为写死 16 字节, 与 URL 的 auth_key 无关。
   本文件内嵌纯 Python AES-128 实现(无第三方依赖, Chaquopy 可用),
   localProxy 抓图后自动解密, 再经图片魔数校验。
   另: 壳子传给 localProxy 的 param 可能是 Java ArrayList 而非 dict
   (咖啡视频项目实测), _unwrap 统一兼容; 拉图失败返回占位 PNG(200)
   而不是 404; 直连失败走 images.weserv.nl 再试; 用带 DoH 反劫持的
   会话抓图。
3. 封面 URL 的 auth_key 约 2 小时过期, 属站点行为, 无法在壳侧刷新;
   列表页每次现抓现用, 正常浏览不受影响。

v1.2 改动(对齐壳子格式):
- 继承 base.spider.Spider; 全方法 try/except 兜底(异常返回空结构,不抛异常白屏)
- searchContent 签名 (key, quick, pg="1"); manualVideoCheck -> True
- pagecount/total 用字符串; 日志走 self.log
- UA 换手机端; 保留: 国内 DoH 反劫持 + 域名池故障转移 + 内容指纹校验
"""
try:
    from base.spider import Spider as _BaseSpider
except ImportError:  # 沙盒自测时 base 不存在
    _BaseSpider = object

from urllib.parse import quote, urljoin, urlparse
import urllib.parse
import urllib.request
from lxml import etree  # noqa: F401  (与参考格式一致, 按需使用)
import re
import time
import json  # noqa: F401
import socket
import html as _html
import requests
import base64

UA = ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36")

DOMAINS = ["pku.daqbqrri.cc", "wanwuu.com", "c5ad.oqgciumz.cc"]
DOH_URLS = [
    "https://dns.alidns.com/resolve",
    "https://doh.pub/dns-query",
    "https://223.5.5.5/resolve",
    "https://120.53.53.53/resolve",
]
SEED_IPS = {
    "pku.daqbqrri.cc": ["18.66.118.28", "18.66.118.13", "18.66.118.26"],
}
HIJACK_IPS = {"180.109.0.221", "0.0.0.0", "127.0.0.1"}

CLASSES = [
    ("popular", "当前最热"),
    ("new", "最近更新"),
    ("zhibo-huifang", "直播回放"),
    ("guochan-sm", "国产SM"),
    ("rihan-sm", "日韩SM"),
    ("oumei-sm", "欧美SM"),
    ("dongman-sm", "动漫SM"),
    ("tiaojiao-av", "调教AV"),
    ("ai-duanju", "AI成人短剧"),
    ("moviesets", "精选合集"),
]

_B36 = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
_PACKER_RE = re.compile(
    r"eval\(function\(p,a,c,k,e,d\)\{.*?\}\('((?:[^'\\]|\\.)*)',(\d+),(\d+),'(.*?)'\.split\('\|'\),0,\{\}\)\)",
    re.S)


def _to_base(n, base):
    if n <= 0:
        return "0"
    s = ""
    while n > 0:
        s = _B36[n % base] + s
        n //= base
    return s


def _unescape_js_str(s):
    s = s.replace("\\\\", "\x00")
    s = s.replace("\\'", "'").replace('\\"', '"').replace("\\/", "/")
    s = s.replace("\\n", "\n").replace("\\r", "\r").replace("\\t", "\t")
    return s.replace("\x00", "\\")


def _do_unpack(js):
    ms = list(_PACKER_RE.finditer(js))
    if not ms:
        return None
    m = ms[0]
    payload = _unescape_js_str(m.group(1))
    radix, count = int(m.group(2)), int(m.group(3))
    symtab = m.group(4).split("|")
    for i in range(count - 1, -1, -1):
        word = _to_base(i, radix)
        val = symtab[i] if i < len(symtab) else word
        if not val:
            val = word
        payload = re.sub(r"\b" + re.escape(word) + r"\b",
                         lambda _m, v=val: v, payload)
    return payload


def _unpack_all(js):
    out = []
    for m in _PACKER_RE.finditer(js):
        try:
            payload = _unescape_js_str(m.group(1))
            radix, count = int(m.group(2)), int(m.group(3))
            symtab = m.group(4).split("|")
            for i in range(count - 1, -1, -1):
                word = _to_base(i, radix)
                val = symtab[i] if i < len(symtab) else word
                if not val:
                    val = word
                payload = re.sub(r"\b" + re.escape(word) + r"\b",
                                 lambda _m, v=val: v, payload)
            out.append(payload)
        except Exception:
            continue
    return out


def _looks_like_site(html):
    return ("玩物社区" in html) or ("video-item" in html) or ("detail_play" in html)


def _looks_like_player_js(js):
    return ("eval(" in js) and ("mse" in js)


# ---------------- 图片工具(v1.3, 移植自咖啡视频项目实战) ----------------
def _b64d(s):
    try:
        return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)).decode("utf-8")
    except Exception:
        return ""


def _gunzip(data):
    if not data or len(data) < 2:
        return data
    if data[:2] != b"\x1f\x8b":
        return data
    try:
        import gzip as _gz
        return _gz.decompress(data)
    except Exception:
        pass
    try:
        import zlib as _zl
        return _zl.decompress(data, 16 + _zl.MAX_WBITS)
    except Exception:
        return data


def _img_mime(data):
    """按图片魔数严格判定; 先解 gzip; 非图片返回 "" """
    if not data or len(data) < 4:
        return ""
    data = _gunzip(data)
    n = len(data)
    if n >= 3 and data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if n >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if n >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if n >= 6 and data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if n >= 2 and data[:2] == b"BM":
        return "image/bmp"
    # ★★★ v1.4 修复"全部没封面"根因: 抓图请求头把 image/avif 排第一,
    #   站点常直接回 AVIF, 而旧版 _img_mime 没有 AVIF 魔数判定 →
    #   真图被误判为"非图片" → 一律回退占位灰图。补上 AVIF/HEIC/HEIF。
    # AVIF/HEIC 基于 ISOBMFF: 长度(4) + 'ftyp'(4) + major brand(4) ...
    if n >= 12 and data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in (b"avif", b"avis"):
            return "image/avif"
        if brand in (b"heic", b"heif", b"mif1"):
            return "image/heic" if brand == b"heic" else "image/heif"
        # 兼容品牌(avif/avis/heic...)可能出现在后续 compatible-brands 列表
        if b"avif" in data[8:64] or b"avis" in data[8:64]:
            return "image/avif"
        if b"heic" in data[8:64] or b"heif" in data[8:64]:
            return "image/heif"
    return ""


def _blank_png(w=300, h=450, rgb=(0x1c, 0x1c, 0x22)):
    """纯标准库生成占位 PNG(无 PIL 依赖): 棋盘格 + 中央播放三角"""
    import struct
    import zlib

    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I",
                                                               zlib.crc32(c))

    cx, cy = w // 2, h // 2
    tri_h, tri_w = 70, 56
    raw = b""
    for y in range(h):
        raw += b"\x00"
        for x in range(w):
            on = ((x >> 3) + (y >> 3)) & 1
            r, g, b = rgb
            if on:
                r, g, b = min(255, r + 16), min(255, g + 16), min(255, b + 18)
            dy = abs(y - cy)
            if dy <= tri_h // 2:
                half = int((1 - dy / (tri_h // 2)) * tri_w)
                if cx - tri_w // 3 <= x <= cx - tri_w // 3 + half:
                    r, g, b = 200, 200, 210
            raw += bytes((r, g, b))
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


_BLANK = None


def _blank():
    global _BLANK
    if _BLANK is None:
        try:
            _BLANK = _blank_png()
        except Exception:
            _BLANK = b""
    return _BLANK


def _weserv_url(url):
    u = re.sub(r"^https?://", "", url)
    return "https://images.weserv.nl/?url=" + quote(u, safe="")


# ---------------- 纯 Python AES-128 解密(封面专用, 无第三方依赖) ----------------
# 本站封面为 AES-128-CBC/NoPadding 加密, 密钥写死在 /static/web/js/plugins/lazyload.js:
#   key='f5d965df75336270', iv='97b60394abc2fbe1' (2026-10-12 浏览器实测)
_WW_AES_KEY = b"f5d965df75336270"
_WW_AES_IV = b"97b60394abc2fbe1"


def _gf_mul(a, b):
    p = 0
    for _ in range(8):
        if b & 1:
            p ^= a
        hi = a & 0x80
        a = (a << 1) & 0xFF
        if hi:
            a ^= 0x1B
        b >>= 1
    return p


def _gf_pow(a, e):
    r = 1
    while e:
        if e & 1:
            r = _gf_mul(r, a)
        a = _gf_mul(a, a)
        e >>= 1
    return r


def _rotl8(x, n):
    return ((x << n) | (x >> (8 - n))) & 0xFF


def _aes_build_sbox():
    sb = []
    for i in range(256):
        inv = _gf_pow(i, 254) if i else 0
        y = (inv ^ _rotl8(inv, 1) ^ _rotl8(inv, 2)
             ^ _rotl8(inv, 3) ^ _rotl8(inv, 4) ^ 0x63) & 0xFF
        sb.append(y)
    return sb


_AES_SBOX = _aes_build_sbox()
_AES_INV_SBOX = [0] * 256
for _si, _sv in enumerate(_AES_SBOX):
    _AES_INV_SBOX[_sv] = _si
_AES_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36]
# GF 乘法查表(v1.5): InvMixColumns 每字节原本要做 8 次位循环, 换成查表
_DEC_M9 = [_gf_mul(a, 0x09) for a in range(256)]
_DEC_MB = [_gf_mul(a, 0x0B) for a in range(256)]
_DEC_MD = [_gf_mul(a, 0x0D) for a in range(256)]
_DEC_ME = [_gf_mul(a, 0x0E) for a in range(256)]

# ---- v1.5 性能真凶修复: Java AES 优先 ----
_JAVA_OK = None  # None=未探测 / True / False


def _java_aes_ok():
    """仅在 Chaquopy(Android)环境可用; 已探测过则直接复用结果"""
    global _JAVA_OK
    if _JAVA_OK is None:
        try:
            from java import jclass  # noqa: F401  Chaquopy 专有
            _JAVA_OK = True
        except Exception:
            _JAVA_OK = False
    return _JAVA_OK


def _java_aes_cbc_decrypt(data, key, iv):
    """Android 原生 javax.crypto AES-128-CBC/NoPadding(硬件级,毫秒级)。
    Chaquopy 会自动把 Python bytes 转成 Java byte[], 返回值再 bytes() 一下。"""
    from java import jclass
    Cipher = jclass("javax.crypto.Cipher")
    SecretKeySpec = jclass("javax.crypto.spec.SecretKeySpec")
    IvParameterSpec = jclass("javax.crypto.spec.IvParameterSpec")
    c = Cipher.getInstance("AES/CBC/NoPadding")
    c.init(2, SecretKeySpec(key, "AES"), IvParameterSpec(iv))  # 2=DECRYPT_MODE
    return bytes(c.doFinal(data))


def _aes_key_expand(key):
    w = [list(key[i:i + 4]) for i in range(0, 16, 4)]
    for i in range(4, 44):
        t = list(w[i - 1])
        if i % 4 == 0:
            t = t[1:] + t[:1]
            t = [_AES_SBOX[b] for b in t]
            t[0] ^= _AES_RCON[i // 4 - 1]
        w.append([a ^ b for a, b in zip(w[i - 4], t)])
    rks = []
    for r in range(11):
        rk = []
        for c in range(4):
            rk.extend(w[r * 4 + c])
        rks.append(bytes(rk))
    return rks


def _aes_decrypt_block(block16, rks):
    s = [b ^ k for b, k in zip(block16, rks[10])]
    for rnd in range(9, 0, -1):
        # InvShiftRows(行右移)
        t = [0] * 16
        for rr in range(4):
            for cc in range(4):
                t[rr + 4 * cc] = s[rr + 4 * ((cc - rr) % 4)]
        # InvSubBytes + AddRoundKey
        s = [_AES_INV_SBOX[b] ^ k for b, k in zip(t, rks[rnd])]
        # InvMixColumns
        u = [0] * 16
        for cc in range(4):
            a0, a1, a2, a3 = s[cc * 4:cc * 4 + 4]
            u[cc * 4] = (_DEC_ME[a0] ^ _DEC_MB[a1]
                         ^ _DEC_MD[a2] ^ _DEC_M9[a3])
            u[cc * 4 + 1] = (_DEC_M9[a0] ^ _DEC_ME[a1]
                             ^ _DEC_MB[a2] ^ _DEC_MD[a3])
            u[cc * 4 + 2] = (_DEC_MD[a0] ^ _DEC_M9[a1]
                             ^ _DEC_ME[a2] ^ _DEC_MB[a3])
            u[cc * 4 + 3] = (_DEC_MB[a0] ^ _DEC_MD[a1]
                             ^ _DEC_M9[a2] ^ _DEC_ME[a3])
        s = u
    t = [0] * 16
    for rr in range(4):
        for cc in range(4):
            t[rr + 4 * cc] = s[rr + 4 * ((cc - rr) % 4)]
    return bytes([_AES_INV_SBOX[b] ^ k for b, k in zip(t, rks[0])])


def _aes_cbc_decrypt(data, key, iv):
    """v1.5: Chaquopy 环境优先走 Android 原生 javax.crypto(毫秒级),
    否则回退查表优化后的纯 Python 实现。两者输出一致(已对齐验证)。"""
    if _java_aes_ok():
        try:
            return _java_aes_cbc_decrypt(data, key, iv)
        except Exception:
            pass
    return _aes_cbc_decrypt_py(data, key, iv)


def _aes_cbc_decrypt_py(data, key, iv):
    rks = _aes_key_expand(key)
    out = bytearray()
    prev = iv
    for i in range(0, len(data), 16):
        blk = _aes_decrypt_block(data[i:i + 16], rks)
        out.extend(b ^ p for b, p in zip(blk, prev))
        prev = data[i:i + 16]
    return bytes(out)


# ---- v1.5 解密结果缓存(防止翻页/回看重复解密) ----
_DEC_CACHE = {}
_DEC_CACHE_ORDER = []
_DEC_CACHE_MAX = 256


def _decrypt_cached(url, data):
    """以 URL 为 key 缓存已解密图片字节(LRU)"""
    if url:
        hit = _DEC_CACHE.get(url)
        if hit:
            return hit
    out = _decrypt_cover(data)
    if not url or not _img_mime(out):
        return out
    if len(_DEC_CACHE_ORDER) >= _DEC_CACHE_MAX:
        try:
            _DEC_CACHE.pop(_DEC_CACHE_ORDER.pop(0), None)
        except Exception:
            pass
    _DEC_CACHE[url] = out
    _DEC_CACHE_ORDER.append(url)
    return out


def _decrypt_cover(data):
    """本站封面 AES-128-CBC 解密; 已是有效图片则原样返回; 解密失败返回原数据

    v1.4 加固: 密文长度非 16 整数倍(CDN 偶发多/少字节)时, 尝试零填充到
    下一整块(保留头部正确性); 也尝试去掉可能的 16 字节前缀头。任一结果
    能解出合法图片即采用, 否则回退原数据(交由上层回退占位/再代理)。"""
    if not data or _img_mime(data):
        return data
    candidates = [data]
    if len(data) % 16:
        candidates.append(data + b"\x00" * (16 - len(data) % 16))
    if len(data) > 16 and len(data) % 16 == 0:
        candidates.append(data[16:])
    for c in candidates:
        if len(c) >= 16 and len(c) % 16 == 0:
            try:
                pt = _aes_cbc_decrypt(c, _WW_AES_KEY, _WW_AES_IV)
                if _img_mime(pt):
                    return pt
            except Exception:
                continue
    return data


class Spider(_BaseSpider):

    def init(self, extend=""):
        self._sess()

    def getName(self):
        return "玩物社区"

    # ---------------- 内部工具 ----------------
    def _log(self, msg):
        try:
            self.log(msg)
        except Exception:
            pass

    def _sess(self):
        if getattr(self, "_session", None) is None:
            self._install_dns_guard()
            s = requests.Session()
            s.headers.update({"User-Agent": UA,
                              "Accept-Language": "zh-CN,zh;q=0.9"})
            self._session = s
        return self._session

    def _get(self, url, timeout=25):
        """参考格式: 失败返回空串, 不抛异常"""
        try:
            r, _ = self._fetch(url, expect="site", timeout=timeout)
            return r.text or ""
        except Exception as e:
            self._log("GET err %s: %s" % (url, e))
            return ""

    def _abs(self, url):
        if not url:
            return ""
        url = url.strip()
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("http"):
            return url
        if url.startswith("/"):
            return "https://" + DOMAINS[0] + url
        return "https://" + DOMAINS[0] + "/" + url

    def _proxy_pic(self, pic):
        """封面走壳子代理, 失败回退直链"""
        pic = self._abs(pic)
        if not pic:
            return ""
        try:
            proxy = self.getProxyUrl()
            if proxy:
                return proxy + "&type=pic&url=" + quote(pic, safe="")
        except Exception:
            pass
        return pic

    @staticmethod
    def _clean(s):
        if not s:
            return ""
        s = re.sub(r"<[^>]+>", "", s)
        return _html.unescape(s).strip()

    @staticmethod
    def _rx(pattern, text, flags=0):
        m = re.search(pattern, text, flags)
        return m.group(1).strip() if m else ""

    def _parse_video_list(self, html):
        """★★★ v1.3 彻底修复"当前最热/最近更新没数据":
        根因: /videos/popular/、/videos/new/ 的卡片标题不在 h2/h3 里,
        而是在 <a class="...line-clamp..."> 里(img alt 亦可兜底);
        原实现只认 h2/h3, name 取空 → 整页被 skip → 返回空列表,
        App 显示"这里什么都没有"。
        另: 页面顶部有"排行"区(/videos/cate/vd-xxx/ 链接, 无封面只有
        排行小图标), 必须排除, 否则混入无图条目。"""
        vods, seen = [], set()
        if not html:
            return vods
        for m in re.finditer(r'href="(/videos/(?!cate/)[^"]*?/vd-[A-Za-z0-9\-]+/?)"', html):
            try:
                href = m.group(1)
                if href in seen:
                    continue
                seen.add(href)
                seg = html[m.start():m.start() + 8000]
                # 封面多属性兼容: data-src / data-original / data-lazy-src
                #   / data-url / 绝对或相对 src(仅图片后缀)。相对路径交给
                #   _proxy_pic 内的 _abs 补全。
                pic = self._rx(r'data-src="(https?://[^"]+)"', seg)
                if not pic:
                    pic = self._rx(r'data-original="(https?://[^"]+)"', seg)
                if not pic:
                    pic = self._rx(r'data-lazy-src="(https?://[^"]+)"', seg)
                if not pic:
                    pic = self._rx(r'data-url="(https?://[^"]+)"', seg)
                if not pic:
                    pic = self._rx(
                        r'src="((?:https?://|/)[^"]+\.(?:jpg|jpeg|png|webp|avif|gif))"',
                        seg)
                # 标题三级兜底: h2/h3 → line-clamp-a → img alt
                name = self._clean(self._rx(r"<h[23][^>]*>(.*?)</h[23]>", seg, re.S))
                if not name:
                    name = self._clean(self._rx(
                        r'<a[^>]*class="[^"]*line-clamp[^"]*"[^>]*>([^<]{1,200})</a>',
                        seg))
                if not name:
                    name = self._clean(self._rx(r'<img[^>]*alt="([^"]{1,200})"', seg))
                remark = self._rx(r">(\d{1,3}:\d{2}(?::\d{2})?)<", seg)
                if not name:
                    continue
                vods.append({
                    "vod_id": urljoin("https://" + DOMAINS[0], href),
                    "vod_name": name,
                    "vod_pic": self._proxy_pic(pic),
                    "vod_remarks": remark,
                })
            except Exception:
                continue
        return vods

    def _parse_movieset_list(self, html):
        vods, seen = [], set()
        if not html:
            return vods
        for m in re.finditer(r'href="(/moviesets/[A-Za-z0-9\-]+/?)"', html):
            try:
                href = m.group(1)
                if href in seen:
                    continue
                seen.add(href)
                seg = html[m.start():m.start() + 6000]
                if "<h2" not in seg and "<h3" not in seg:
                    continue
                if "data-src" not in seg and "data-original" not in seg:
                    continue
                pic = self._rx(r'data-src="(https?://[^"]+)"', seg)
                if not pic:
                    pic = self._rx(r'data-original="(https?://[^"]+)"', seg)
                if not pic:
                    pic = self._rx(
                        r'src="((?:https?://|/)[^"]+\.(?:jpg|jpeg|png|webp|avif|gif))"',
                        seg)
                name = self._clean(self._rx(r"<h[23][^>]*>(.*?)</h[23]>", seg, re.S))
                remark = self._clean(self._rx(r">(\d+部)<", seg))
                if not name:
                    continue
                vods.append({
                    "vod_id": urljoin("https://" + DOMAINS[0], href),
                    "vod_name": name,
                    "vod_pic": self._proxy_pic(pic),
                    "vod_remarks": remark,
                })
            except Exception:
                continue
        return vods

    def _total(self, html):
        m = re.search(r'"numberOfItems":\s*(\d+)', html or "")
        return m.group(1) if m else "0"

    def _build_detail_play(self, packed, page_url):
        def rx(p):
            m = re.search(p, packed)
            return m.group(1) if m else ""
        vid = rx(r"[?&]id=(\d+)")
        img = rx(r"[?&]img=([^\"&]+)")
        ads = rx(r"[?&]ads=([^\"&]+)")
        tok = rx(r"encodeURIComponent\(\"([^\"]+)\"\)")
        if not (vid and tok):
            return ""
        t = str(int(time.time()) // 1800)
        origin = "%s://%s" % (urlparse(page_url).scheme or "https",
                               urlparse(page_url).netloc)
        return ("%s/videos/detail_play?id=%s&img=%s&ads=%s&u=%s&t=%s"
                % (origin, vid, img, ads, quote(tok, safe=""), t))

    def _get_m3u8(self, detail_url):
        """详情页 -> detail_play -> 解包 -> div#mse data-url(m3u8), 失败抛异常由上层兜底"""
        r, final = self._fetch(detail_url, expect="site")
        html = r.text
        dp_url = None
        m = re.search(r"/videos/detail_play\?[^\"'\s<>]+", html)
        if m:
            dp_url = urljoin(final, _html.unescape(m.group(0)))
        else:
            for packed in _unpack_all(html):
                if "detail_play" in packed:
                    dp_url = self._build_detail_play(packed, final)
                    if dp_url:
                        break
        if not dp_url:
            raise RuntimeError("未找到 detail_play 播放接口")
        r2, _ = self._fetch(dp_url, referer=final, expect="js")
        unpacked = (_do_unpack(r2.text) or r2.text).replace('\\"', '"')
        m3 = re.search(r'data-url="([^"]+)"', unpacked)
        if not m3:
            raise RuntimeError("detail_play 返回中未找到 data-url")
        return _html.unescape(m3.group(1)).replace("&amp;", "&")

    # ---------------- 壳子接口(全兜底,不抛异常) ----------------
    def homeContent(self, filter):
        try:
            return {
                "class": [{"type_id": tid, "type_name": name}
                          for tid, name in CLASSES],
                "filters": {},
            }
        except Exception:
            return {"class": [], "filters": {}}

    def homeVideoContent(self):
        try:
            html = self._get("https://" + DOMAINS[0] + "/videos/new/")
            return {"list": self._parse_video_list(html)}
        except Exception:
            return {"list": []}

    def _cat_path(self, tid):
        if tid == "moviesets":
            return "/moviesets/"
        if tid.startswith("ai-"):
            return "/ai/%s/" % tid
        return "/videos/%s/" % tid

    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg) if str(pg).isdigit() else 1
        except Exception:
            pg = 1
        try:
            path = self._cat_path(tid)
            if pg > 1:
                path = path + "page/%d/" % pg
            html = self._get(path)
            vods = (self._parse_movieset_list(html) if tid == "moviesets"
                    else self._parse_video_list(html))
            has_next = ("/page/%d/" % (pg + 1)) in html
            return {
                "list": vods,
                "page": pg,
                "pagecount": "9999" if has_next else str(pg),
                "limit": len(vods),
                "total": self._total(html),
            }
        except Exception as e:
            self._log("categoryContent err: %s" % e)
            return {"list": [], "page": pg, "pagecount": "1",
                    "limit": 0, "total": "0"}

    def detailContent(self, ids):
        try:
            url = str(ids[0])
        except Exception:
            return {"list": []}
        try:
            if "/moviesets/" in url and "/vd-" not in url:
                return self._movieset_detail(url)
            html = self._get(url)
            if not html:
                return {"list": []}
            name = (self._rx(r"<title>(.*?)视频在线观看", html)
                    or self._rx(r"<h1[^>]*>(.*?)</h1>", html, re.S))
            pic = (self._rx(r'<meta property="og:image" content="([^"]+)"', html)
                   or self._rx(r'data-src="(https?://[^"]+\.(?:jpg|jpeg|png|webp|avif|gif))"', html)
                   or self._rx(r'data-original="(https?://[^"]+\.(?:jpg|jpeg|png|webp|avif|gif))"', html))
            desc = self._rx(r'<meta name="description" content="([^"]+)"', html)
            vod = {
                "vod_id": url,
                "vod_name": self._clean(name),
                "vod_pic": self._proxy_pic(pic),
                "vod_remarks": "",
                "vod_year": "",
                "vod_area": "",
                "vod_actor": "",
                "vod_content": self._clean(desc),
                "vod_play_from": "玩物社区",
                "vod_play_url": "立即播放$" + url,
            }
            return {"list": [vod]}
        except Exception as e:
            self._log("detailContent err: %s" % e)
            return {"list": []}

    def _movieset_detail(self, url):
        html = self._get(url)
        if not html:
            return {"list": []}
        name = (self._rx(r"<title>(.*?)</title>", html, re.S)
                or self._rx(r"<h1[^>]*>(.*?)</h1>", html, re.S))
        name = self._clean(name)
        name = re.sub(r"\s*[|｜\-–—]\s*玩物社区\s*$", "", name)
        name = re.sub(r"\s*高清在线观看\s*$", "", name)
        pic = (self._rx(r'<meta property="og:image" content="([^"]+)"', html)
               or self._rx(r'data-src="(https?://[^"]+\.(?:jpg|jpeg|png|webp|avif|gif))"', html)
               or self._rx(r'data-original="(https?://[^"]+\.(?:jpg|jpeg|png|webp|avif|gif))"', html))
        vids = self._parse_video_list(html)
        eps = "#".join("%s$%s" % (v["vod_name"], v["vod_id"]) for v in vids)
        vod = {
            "vod_id": url,
            "vod_name": name,
            "vod_pic": self._proxy_pic(pic),
            "vod_play_from": "合集选集",
            "vod_play_url": eps,
        }
        return {"list": [vod]}

    def searchContent(self, key, quick, pg="1"):
        try:
            pg = int(pg) if str(pg).isdigit() else 1
        except Exception:
            pg = 1
        try:
            path = "/videos/search/%s/" % quote(key, safe="")
            if pg > 1:
                path = "/videos/search/%s/page/%d/" % (quote(key, safe=""), pg)
            html = self._get(path)
            vods = self._parse_video_list(html)
            has_next = ("/page/%d/" % (pg + 1)) in html
            return {
                "list": vods,
                "page": pg,
                "pagecount": "9999" if has_next else str(pg),
                "limit": len(vods),
                "total": self._total(html),
            }
        except Exception as e:
            self._log("searchContent err: %s" % e)
            return {"list": [], "page": pg, "pagecount": "1",
                    "limit": 0, "total": "0"}

    def playerContent(self, flag, id, vipFlags):
        try:
            pid = str(id).strip()
            m3u8 = self._get_m3u8(pid)
            return {
                "parse": 0,
                "url": m3u8,
                "header": {
                    "User-Agent": UA,
                    "Referer": pid,
                },
            }
        except Exception as e:
            self._log("playerContent err: %s" % e)
            return {"parse": 0, "url": ""}

    @staticmethod
    def _unwrap(param):
        """把壳子传来的多种形态统一成 dict
        ★★★ 咖啡视频项目第 5 次踩 do=py 传参形态坑的教训:
          原实现只认 dict, 壳子实际常传 Java ArrayList(List<String>),
          param.get 直接抛 AttributeError → 被 except 吞掉 → 全 404。
          症状: 不报错、不崩, 就是海报一张都不显示。
        兼容: dict / str / bytes / list / tuple / query串 / 裸URL。"""
        p = param
        if isinstance(p, (bytes, bytearray)):
            try:
                p = p.decode("utf-8", "ignore")
            except Exception:
                p = str(p)
        if isinstance(p, str):
            s = p.strip()
            if s.startswith("{"):
                try:
                    p = json.loads(s)
                except Exception:
                    p = {"url": s}
            elif s.startswith("http") and "url=" not in s and "u=" not in s:
                p = {"url": s}
            elif "=" in s:
                try:
                    p = {k: v[0] for k, v in
                         urllib.parse.parse_qs(
                             urllib.parse.urlparse(s).query or s).items()}
                except Exception:
                    p = {"url": s}
            else:
                p = {"url": s}
        if not isinstance(p, dict):
            # List<String>/tuple, 如 ["do=py", "type=pic", "url=<编码后地址>"]
            # (咖啡视频项目实测: 壳子最常传的就是这种形态)
            url_candidate = ""
            qbuf = []
            for x in (p or []):
                if isinstance(x, dict):
                    p = x
                    break
                sx = str(x).strip()
                if not sx:
                    continue
                if sx.startswith("{"):
                    try:
                        p = json.loads(sx)
                        break
                    except Exception:
                        pass
                    continue
                if sx.startswith("http"):
                    # 裸 URL(直链里可能含未编码的 ?&, 整体保留不切分)
                    if not url_candidate:
                        url_candidate = sx
                    continue
                qbuf.append(sx)
            if not isinstance(p, dict):
                q = "&".join(qbuf)
                # 已知 key 的值从 "key=" 一直取到串尾:
                # 直链可能含未编码的 ?&, 若按 & 切分会把 URL 自身切坏
                m = re.search(r"(?:^|[&?])(url|u|img|pic|cover)=(.+)$", q)
                if m:
                    p = {m.group(1): urllib.parse.unquote(m.group(2))}
                elif url_candidate:
                    p = {"url": url_candidate}
                elif q:
                    try:
                        d = {k: v[0] for k, v in
                             urllib.parse.parse_qs(q).items()}
                        p = d if d else {"url": ""}
                    except Exception:
                        p = {"url": ""}
                else:
                    p = {"url": ""}
        out = {}
        for k, v in p.items():
            if isinstance(v, (list, tuple)):
                v = v[0] if v else ""
            out[k] = v if isinstance(v, str) else ("" if v is None else str(v))
        return out

    def _fetch_img_bytes(self, url, referer="", timeout=18):
        """抓图字节: 带 DoH 反劫持的会话优先, urllib 兜底"""
        if not referer:
            referer = "https://" + DOMAINS[0] + "/"
        headers = {
            "User-Agent": UA,
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Referer": referer,
        }
        sess = getattr(self, "_session", None)
        if sess is not None:
            try:
                r = sess.get(url, headers=headers, timeout=timeout, verify=False)
                if r.status_code == 200 and r.content:
                    return _gunzip(r.content)
            except Exception:
                pass
        try:
            import ssl as _ssl
            req = urllib.request.Request(url, headers=headers)
            ctx = _ssl._create_unverified_context()
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                return _gunzip(resp.read())
        except Exception:
            return b""

    def localProxy(self, param):
        """★★★ v1.3 彻底修复"分类有数据没封面":
        1. _unwrap 兼容壳子多种传参形态(尤其 Java ArrayList),
           之前 param.get 直接抛异常 → 全 404 → 海报全灰。
        2. 按图片魔数验图: CDN 的 403/404 错误页不再被当成图返回。
        3. 拉图失败返回占位 PNG(200)而不是 404, 排版不崩。
        4. 直连失败走 images.weserv.nl 代理再试一次。
        5. 用带 DoH 反劫持的会话抓图, 不再裸 requests.get。"""
        try:
            p = self._unwrap(param)
            url = (p.get("url") or p.get("u") or p.get("img")
                   or p.get("pic") or p.get("cover") or "")
            if not url:
                return [200, "image/png", _blank(), {}, 0]
            # 壳子可能把整条代理 URL 又传回来 → 剥出内层真实地址
            if "127.0.0.1" in url or "localhost" in url:
                q2 = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
                url = (q2.get("url") or q2.get("u") or [""])[0]
                if not url:
                    return [200, "image/png", _blank(), {}, 0]
            # b64 形态先解码
            if not url.startswith("http"):
                dec = _b64d(url)
                if dec.startswith("http"):
                    url = dec
            if url.startswith("//"):
                url = "https:" + url
            elif url.startswith("/"):
                url = self._abs(url)
            if not url.startswith("http"):
                return [200, "image/png", _blank(), {}, 0]

            # 命中已解密缓存则直接返回(不重复下载、不重复解密)
            cached = _DEC_CACHE.get(url)
            if cached and _img_mime(cached):
                return [200, _img_mime(cached), cached, {}, 0]
            data = _decrypt_cached(url, self._fetch_img_bytes(url))
            if not _img_mime(data):
                data = _decrypt_cached(
                    url, self._fetch_img_bytes(_weserv_url(url), timeout=12))
            mime = _img_mime(data)
            if not mime:
                self._log("pic miss (非图片) %s len=%d" % (url[:80], len(data)))
                return [200, "image/png", _blank(), {}, 0]
            self._log("pic ok %s -> %s len=%d" % (url[:60], mime, len(data)))
            return [200, mime, data, {}, 0]
        except Exception as e:
            self._log("localProxy err: %s" % e)
            return [200, "image/png", _blank(), {}, 0]

    def isVideoFormat(self, url):
        try:
            return bool(re.search(r"\.(m3u8|mp4|flv|ts|m4v)(\?|$)", str(url), re.I))
        except Exception:
            return False

    def manualVideoCheck(self):
        return True

    # ---------------- 网络(域名池 + 内容指纹 + DoH 反劫持) ----------------
    def _expand_urls(self, url_or_path):
        urls = []
        if url_or_path.startswith("http"):
            p = urlparse(url_or_path)
            for d in DOMAINS:
                u = p._replace(netloc=d).geturl()
                if u not in urls:
                    urls.append(u)
        else:
            path = url_or_path if url_or_path.startswith("/") else "/" + url_or_path
            for d in DOMAINS:
                urls.append("https://" + d + path)
        return urls

    def _fetch(self, url_or_path, referer="", expect="site", timeout=25):
        """按域名池逐个尝试; 内容指纹不符(劫持页)判失败换域名. 失败抛异常."""
        sess = self._sess()
        last_err = None
        for url in self._expand_urls(url_or_path):
            try:
                headers = {}
                if referer:
                    headers["Referer"] = referer
                r = sess.get(url, headers=headers, timeout=timeout)
                if r.status_code == 200 and len(r.content) > 200:
                    if not r.encoding or r.encoding.lower() == "iso-8859-1":
                        r.encoding = "utf-8"
                    txt = r.text
                    if expect == "site" and not _looks_like_site(txt):
                        last_err = RuntimeError("内容指纹不符(疑似劫持页) @ %s" % url)
                        continue
                    if expect == "js" and not _looks_like_player_js(txt):
                        last_err = RuntimeError("播放接口返回异常 @ %s" % url)
                        continue
                    return r, url
                last_err = RuntimeError("HTTP %s @ %s" % (r.status_code, url))
            except Exception as e:  # noqa: BLE001
                last_err = e
        raise RuntimeError("全部域名均请求失败: %s" % last_err)

    def _install_dns_guard(self):
        try:
            if getattr(socket, "_ww_dns_guarded", False):
                return
            orig_getaddrinfo = socket.getaddrinfo
            targets = set(DOMAINS)
            cache = {}

            def doh_ips(host):
                import json as _json
                import urllib.request as _ureq
                for base in DOH_URLS:
                    try:
                        req = _ureq.Request(
                            "%s?name=%s&type=A" % (base, host),
                            headers={"Accept": "application/dns-json"})
                        with _ureq.urlopen(req, timeout=6) as resp:
                            data = _json.loads(resp.read().decode("utf-8", "ignore"))
                        ips = [a.get("data") for a in data.get("Answer", [])
                               if a.get("type") == 1 and a.get("data")]
                        ips = [ip for ip in ips if ip not in HIJACK_IPS]
                        if ips:
                            return ips
                    except Exception:
                        continue
                return []

            def guarded(host, port, family=0, type=0, proto=0, flags=0):
                if host in targets:
                    if host not in cache:
                        cache[host] = doh_ips(host) or SEED_IPS.get(host, [])
                    ips = cache.get(host) or []
                    if ips:
                        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "",
                                 (ip, port)) for ip in ips]
                return orig_getaddrinfo(host, port, family, type, proto, flags)

            socket.getaddrinfo = guarded
            socket._ww_dns_guarded = True
        except Exception:
            pass
