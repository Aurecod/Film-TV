#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
肉视频（rou.video）OK影视 插件

覆盖范围：首页推荐、六大分类、标签分类（含分页）、搜索、影片详情、剧集（短剧）选集、播放
已知说明：站点的清单和分片都是伪装成 PNG 的容器，播放器无法直接识别，插件会在本机
          起一个轻量服务（不用 http.server，纯 socket 实现，启动后自检，连不通自动换端口），
          把清单还原成标准 m3u8、分片实时解包成原生 TS 再交给播放器；
          详情页给两条线：本机回环 + 局域网地址，回环被播放器代理拦掉时切第二条即可。
更新方式：站点换域名时改下面的 SITE 一行即可。
"""

from base.spider import Spider


import gzip
import hashlib
import re
import socket
import struct
import threading
import time
import zlib
from urllib.parse import quote, urljoin, urlsplit

SITE = "https://rou.video"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
TIMEOUT = 20
PAGE_SIZE = 26


# ---------------------------------------------------------------- HTTP

def _http_get(url, referer=None, timeout=TIMEOUT):
    import urllib.request
    hdrs = {
        "User-Agent": UA,
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    if referer:
        hdrs["Referer"] = referer
    req = urllib.request.Request(url, headers=hdrs)
    resp = urllib.request.urlopen(req, timeout=timeout)
    body = resp.read()
    enc = (resp.headers.get("Content-Encoding") or "").lower()
    if "gzip" in enc:
        try:
            body = gzip.decompress(body)
        except Exception:
            pass
    elif "deflate" in enc:
        try:
            body = zlib.decompress(body)
        except Exception:
            try:
                body = zlib.decompress(body, -zlib.MAX_WBITS)
            except Exception:
                pass
    return body, resp.geturl(), dict(resp.headers)


def _get_html(path):
    return _http_get(urljoin(SITE + "/", path.lstrip("/")), referer=SITE + "/home", timeout=TIMEOUT)[0].decode("utf-8", "replace")


# ---------------------------------------------------------------- SSR 内联数据还原
# 站点把页面数据以“引用表”形式内联在 <script> 里：$R[3]={a:$R[4]=[...]}，
# 值是 JS 字面量（!0 / !1 / void 0），需要按引用展开。

class _Ref(object):
    __slots__ = ("n",)

    def __init__(self, n):
        self.n = n


class _Parser(object):
    def __init__(self, s):
        self.s = s
        self.i = 0
        self.store = {}

    def _ws(self):
        s, n = self.s, len(self.s)
        while self.i < n and s[self.i] in " \t\r\n":
            self.i += 1

    def _peek(self):
        self._ws()
        return self.s[self.i] if self.i < len(self.s) else ""

    def _eat(self, ch):
        self._ws()
        if self.s.startswith(ch, self.i):
            self.i += len(ch)
            return True
        return False

    def _string(self):
        s = self.s
        self.i += 1
        out = []
        while self.i < len(s):
            c = s[self.i]
            if c == "\\":
                d = s[self.i + 1]
                if d == "u":
                    try:
                        out.append(chr(int(s[self.i + 2:self.i + 6], 16)))
                    except Exception:
                        pass
                    self.i += 6
                    continue
                out.append({"n": "\n", "t": "\t", "r": "\r", "b": "\b",
                            "f": "\f", "/": "/", '"': '"', "\\": "\\"}.get(d, d))
                self.i += 2
                continue
            if c == '"':
                self.i += 1
                break
            out.append(c)
            self.i += 1
        return "".join(out)

    def _ident(self):
        s = self.s
        st = self.i
        while self.i < len(s) and (s[self.i].isalnum() or s[self.i] in "_$"):
            self.i += 1
        return s[st:self.i]

    def _number(self):
        s = self.s
        st = self.i
        if self.i < len(s) and s[self.i] in "+-":
            self.i += 1
        while self.i < len(s) and (s[self.i].isdigit() or s[self.i] in ".eE+-"):
            if s[self.i] in "+-" and s[self.i - 1] not in "eE":
                break
            self.i += 1
        txt = s[st:self.i]
        try:
            return float(txt) if any(c in txt for c in ".eE") else int(txt)
        except Exception:
            return 0

    def expr(self):
        c = self._peek()
        if c == "{":
            return self._obj()
        if c == "[":
            return self._arr()
        if c == '"':
            return self._string()
        if c == "!":
            self.i += 2
            return self.s[self.i - 1] == "0"
        if c == "-" or c.isdigit():
            return self._number()
        if self.s.startswith("$R[", self.i):
            self.i += 3
            st = self.i
            while self.i < len(self.s) and self.s[self.i] != "]":
                self.i += 1
            try:
                n = int(self.s[st:self.i])
            except Exception:
                n = -1
            self.i += 1
            self._ws()
            if self.i < len(self.s) and self.s[self.i] == "=":
                self.i += 1
                val = self.expr()
                self.store[n] = val
                return val
            return _Ref(n)
        word = self._ident()
        if word == "true":
            return True
        if word == "false":
            return False
        if word == "void":
            self.expr()
            return None
        return None

    def _obj(self):
        self.i += 1
        out = {}
        while True:
            c = self._peek()
            if c == "}":
                self.i += 1
                break
            if c == "":
                break
            if c == '"':
                k = self._string()
            else:
                k = self._ident()
                if not k:
                    self.i += 1
                    continue
            if not self._eat(":"):
                continue
            out[k] = self.expr()
            if not self._eat(","):
                if self._peek() == "}":
                    self.i += 1
                break
        return out

    def _arr(self):
        self.i += 1
        out = []
        while True:
            c = self._peek()
            if c == "]":
                self.i += 1
                break
            if c == "":
                break
            out.append(self.expr())
            if not self._eat(","):
                if self._peek() == "]":
                    self.i += 1
                break
        return out


def _resolve(v, store, depth=0):
    if depth > 300:
        return None
    if isinstance(v, _Ref):
        return _resolve(store.get(v.n), store, depth + 1) if v.n in store else None
    if isinstance(v, dict):
        return dict((k, _resolve(x, store, depth + 1)) for k, x in v.items())
    if isinstance(v, list):
        return [_resolve(x, store, depth + 1) for x in v]
    return v


def _parse_ssr(html):
    """取页面里 $_TSR.router 的内联引用表，返回还原后的 {manifest, matches}。"""
    m = re.search(r"\$_TSR\.router=\(\$R=>\$R\[0\]=", html)
    if not m:
        return None
    p = _Parser(html)
    p.i = m.end()
    try:
        root = p.expr()
    except Exception:
        return None
    return _resolve(root, p.store)


def _loader(html):
    """取最后一个 match 的 loader 数据（页面实际数据都挂在这里）。"""
    d = _parse_ssr(html)
    if not d:
        return {}
    ms = d.get("matches") or []
    if not ms:
        return {}
    lod = ms[-1].get("l")
    return lod if isinstance(lod, dict) else {}


# ---------------------------------------------------------------- PNG 容器解包
# 站点的清单和分片都是真 PNG：第一字节是标志位（1=zlib 压缩，0=明文），
# 其后才是真实数据，全部装在自定义块 roUd 里。

_PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _unwrap_container(buf):
    """若是 PNG 容器则返回真实数据，否则原样返回。"""
    if not buf[:8] == _PNG_SIG:
        return buf
    i, n = 8, len(buf)
    while i + 8 <= n:
        try:
            ln = struct.unpack(">I", buf[i:i + 4])[0]
        except Exception:
            return buf
        typ = buf[i + 4:i + 8]
        if typ == b"roUd":
            d = buf[i + 8:i + 8 + ln]
            if not d:
                return buf
            if d[0] == 1:
                try:
                    return zlib.decompress(d[1:])
                except Exception:
                    return d[1:]
            return d[1:]
        if typ == b"IEND":
            break
        i += 12 + ln
    return buf


# ---------------------------------------------------------------- 本地播放服务
# 播放器不认“伪装成图片”的地址，这里在本机起一个极轻的服务：
# 清单还原成标准 m3u8，分片实时解包成原生 TS，一律按真实内容给正确的 Content-Type。
# 为了在各种播放器/网络环境里都能连上，这里不用 http.server，直接上裸 socket：
#   1) 启动后自己回连一发 GET 自检，连不通就换端口/换绑定地址，绝不把死端口交给播放器
#   2) 同时绑定 0.0.0.0，本机回环和局域网地址都能连（某些播放器会把回环请求走代理，回环会失效）
#   3) 服务有守护线程，被回收/异常退出会自动重启

def _lan_ip():
    """取本机在局域网里的地址，取不到就返回空串。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        finally:
            s.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if ip and not ip.startswith("127."):
                return ip
    except Exception:
        pass
    return ""


def _img_ctype(data):
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"\x89PNG":
        return "image/png"
    if data[:4] == b"GIF8":
        return "image/gif"
    if data[:4] == b"RIFF":
        return "image/webp"
    return "image/jpeg"


_REASON = {200: "OK", 206: "Partial Content", 302: "Found", 404: "Not Found",
           502: "Bad Gateway", 500: "Internal Server Error"}


class _Proxy(object):
    def __init__(self):
        self.port = None
        self.sock = None
        self.lock = threading.Lock()
        self.cache = {}
        self.cache_bytes = 0
        self.pl_cache = {}
        self.tokens = {}
        self.img_handed = 0
        self.img_hits = 0
        self.img_first_ts = 0.0
        self.proxy_img = None
        self.probe_ok = None
        self.probe_ts = 0.0
        self._watch = False

    # ---------------- 启动 / 自检 / 守护
    @staticmethod
    def _listen(host, port):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            s.listen(128)
            s.settimeout(1.0)
            return s
        except Exception:
            return None

    def _ping_port(self, port):
        """自检：真发一个请求，读完整响应再判断，别拿报文头当正文。"""
        try:
            c = socket.create_connection(("127.0.0.1", port), 1.5)
            c.settimeout(2.5)
            try:
                c.sendall(b"GET /rou/ping HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
                buf = b""
                while len(buf) < 4096:
                    ch = c.recv(1024)
                    if not ch:
                        break
                    buf += ch
            finally:
                c.close()
            return buf.startswith(b"HTTP/1.1 200") and buf.rstrip().endswith(b"ok")
        except Exception:
            return False

    def _alive_locked(self):
        if self.sock is None or not self.port:
            return False
        return self._ping_port(self.port)

    def _shutdown_locked(self):
        s, self.sock = self.sock, None
        self.port = None
        if s is not None:
            try:
                s.close()
            except Exception:
                pass

    def ensure(self, force=False):
        """返回一个“确实能连上”的端口；连不上就自己换，绝不把死端口交出去。"""
        with self.lock:
            if self.sock is not None and not force and self._alive_locked():
                return self.port
            self._shutdown_locked()
            for host in ("0.0.0.0", "127.0.0.1"):
                for p in range(9978, 10040):
                    s = self._listen(host, p)
                    if s is None:
                        continue
                    self.sock, self.port = s, p
                    t = threading.Thread(target=self._accept, args=(s,))
                    t.daemon = True
                    t.start()
                    ok = False
                    for i in range(4):
                        if self._ping_port(p):
                            ok = True
                            break
                        time.sleep(0.1 + 0.1 * i)
                    if ok:
                        self.pl_cache.clear()
                        self._start_watch()
                        return p
                    self._shutdown_locked()
            return None

    def _start_watch(self):
        if self._watch:
            return
        self._watch = True

        def loop():
            while True:
                time.sleep(20)
                try:
                    with _PROXY.lock:
                        if _PROXY.sock is not None and not _PROXY._alive_locked():
                            _PROXY.sock = None
                    if _PROXY.sock is None:
                        _PROXY.ensure(force=True)
                except Exception:
                    pass

        t = threading.Thread(target=loop)
        t.daemon = True
        t.start()

    def _accept(self, s):
        while True:
            try:
                c, _ = s.accept()
            except Exception:
                if self.sock is not s:
                    break
                continue
            try:
                c.settimeout(20)
            except Exception:
                pass
            t = threading.Thread(target=self._conn, args=(c,))
            t.daemon = True
            t.start()

    # ---------------- 请求处理
    def _conn(self, c):
        try:
            buf = b""
            while b"\r\n\r\n" not in buf and len(buf) < 16384:
                ch = c.recv(4096)
                if not ch:
                    break
                buf += ch
            if not buf:
                return
            head = buf.split(b"\r\n\r\n", 1)[0].decode("latin-1", "replace")
            rows = head.split("\r\n")
            parts = rows[0].split()
            if len(parts) < 2:
                return
            method, target = parts[0].upper(), parts[1]
            hdrs = {}
            for ln in rows[1:]:
                if ":" in ln:
                    k, v = ln.split(":", 1)
                    hdrs[k.strip().lower()] = v.strip()
            path = target.split("?", 1)[0]
            if path.startswith("http"):
                path = urlsplit(path).path
            code, ctype, body, extra = self.dispatch(path, hdrs)
            out = ["HTTP/1.1 %d %s" % (code, _REASON.get(code, "OK")),
                   "Content-Type: " + ctype,
                   "Content-Length: " + str(len(body)),
                   "Accept-Ranges: bytes",
                   "Access-Control-Allow-Origin: *",
                   "Cache-Control: no-cache",
                   "Connection: close"]
            for k, v in (extra or {}).items():
                out.append("%s: %s" % (k, v))
            c.sendall(("\r\n".join(out) + "\r\n\r\n").encode("latin-1"))
            if method != "HEAD" and body:
                c.sendall(body)
        except Exception:
            pass
        finally:
            try:
                c.close()
            except Exception:
                pass

    def dispatch(self, path, hdrs):
        try:
            if path == "/rou/ping" or path == "/rou/ping/":
                return 200, "text/plain; charset=utf-8", b"ok", {}
            if path.startswith("/rou/v/"):
                vid = path[len("/rou/v/"):].strip("/")
                if vid.endswith(".m3u8"):
                    vid = vid[:-5]
                if not vid:
                    return 404, "text/plain", b"no id", {}
                pl = self.build_playlist(vid, hdrs.get("host"))
                return 200, "application/vnd.apple.mpegurl", pl.encode("utf-8"), {}
            if path.startswith("/rou/i/"):
                tok = path[len("/rou/i/"):].rsplit(".", 1)[0]
                url = self.tokens.get(tok)
                if not url:
                    return 404, "text/plain", b"no token", {}
                self.img_hits += 1
                try:
                    data, ctype = self.fetch(url, unwrap=False)
                except Exception:
                    return 302, "text/plain", b"", {"Location": url}
                return 200, ctype, data, {}
            if path.startswith("/rou/p/"):
                tok = path[len("/rou/p/"):].rsplit(".", 1)[0]
                url = self.tokens.get(tok)
                if not url:
                    return 404, "text/plain", b"no token", {}
                data, ctype = self.fetch(url)
                m = re.match(r"bytes=(\d*)-(\d*)", hdrs.get("range") or "")
                if m:
                    total = len(data)
                    a = int(m.group(1)) if m.group(1) else 0
                    b = int(m.group(2)) if m.group(2) else total - 1
                    b = min(b, total - 1)
                    if a <= b:
                        return (206, ctype, data[a:b + 1],
                                {"Content-Range": "bytes %d-%d/%d" % (a, b, total)})
                return 200, ctype, data, {}
            return 404, "text/plain", b"not found", {}
        except Exception:
            return 502, "text/plain", b"upstream error", {}

    # ---------------- 缓存
    def get_cached(self, url):
        it = self.cache.get(url)
        if it and it[2] > time.time():
            return it[0], it[1]
        return None, None

    def put_cache(self, url, data, ctype, ttl):
        if len(data) > 12 * 1024 * 1024:
            return
        old = self.cache.pop(url, None)
        if old:
            self.cache_bytes -= len(old[0])
        self.cache[url] = (data, ctype, time.time() + ttl)
        self.cache_bytes += len(data)
        while self.cache_bytes > 64 * 1024 * 1024 and self.cache:
            k = next(iter(self.cache))
            self.cache_bytes -= len(self.cache.pop(k)[0])

    # ---------------- 地址重写
    def _pbase(self, host=None):
        host = (host or "").strip()
        if host and re.match(r"^[0-9A-Za-z\.\-]+(:\d+)?$", host):
            return "http://" + host
        return "http://127.0.0.1:%d" % self.port

    def local_url(self, uri, role, base, host=None):
        absu = urljoin(base or (SITE + "/"), uri)
        ext = "m3u8" if role == "pl" else ("key" if role == "key" else "ts")
        tok = hashlib.md5(absu.encode("utf-8")).hexdigest()[:20]
        self.tokens[tok] = absu
        return "%s/rou/p/%s.%s" % (self._pbase(host), tok, ext)

    def rewrite(self, text, base, host=None):
        out = []
        pending = None
        for line in text.splitlines():
            s = line.strip()
            if not s:
                continue
            if s.startswith("#"):
                if 'URI="' in s:
                    if "EXT-X-KEY" in s:
                        role = "key"
                    elif "EXT-X-MEDIA" in s or "I-FRAME-STREAM-INF" in s:
                        role = "pl"
                    else:
                        role = "seg"

                    def _rep(m):
                        return m.group(1) + self.local_url(m.group(2), role, base, host) + m.group(3)

                    s = re.sub(r'(URI=")([^"]+)(")', _rep, s)
                out.append(s)
                pending = "pl" if s.startswith("#EXT-X-STREAM-INF") else None
                continue
            out.append(self.local_url(s, pending or "seg", base, host))
            pending = None
        return "\n".join(out) + "\n"

    # ---------------- 清单
    def build_playlist(self, vid, host=None):
        now = time.time()
        key = (vid, (host or "").strip())
        hit = self.pl_cache.get(key)
        if hit and hit[1] > now:
            return hit[0]
        body, final, _ = _http_get(SITE + "/api/hls/" + vid, referer=SITE + "/v/" + vid, timeout=TIMEOUT)
        body = _unwrap_container(body)
        text = body.decode("utf-8", "replace")
        if not text.lstrip().startswith("#EXTM3U"):
            raise ValueError("unexpected playlist")
        out = self.rewrite(text, final, host)
        self.pl_cache[key] = (out, now + 1500)
        return out

    def warm(self, vid):
        """开播前先把清单和头几个分片热好，播放器第一次请求就是秒回。"""
        try:
            pl = self.build_playlist(vid)
        except Exception:
            return
        n = 0
        for line in pl.splitlines():
            if not line.startswith("http"):
                continue
            u = self.tokens.get(line.rsplit("/", 1)[-1].rsplit(".", 1)[0])
            if not u:
                continue
            t = threading.Thread(target=self.prefetch, args=(u,))
            t.daemon = True
            t.start()
            n += 1
            if n >= 3:
                break

    def prefetch(self, url):
        try:
            self.fetch(url)
        except Exception:
            pass

    # ---------------- 封面图
    def probe_img(self, absu):
        """确认本机网络能不能拿到封面，拿不到就别把图片也塞给本地代理。"""
        now = time.time()
        if self.probe_ok is not None and now - self.probe_ts < 600:
            return self.probe_ok
        ok = False
        try:
            import urllib.request
            req = urllib.request.Request(absu, headers={"User-Agent": UA, "Range": "bytes=0-1023"})
            resp = urllib.request.urlopen(req, timeout=8)
            try:
                ok = len(resp.read(1024)) > 32
            finally:
                resp.close()
        except Exception:
            ok = False
        self.probe_ok, self.probe_ts = ok, now
        return ok

    def img_url(self, uri):
        """封面：默认直连；本机服务可用且网络能拿到图时走本地代理，规避播放器/客户端的取图限制。"""
        if not uri:
            return ""
        absu = urljoin(SITE + "/", str(uri).strip())
        if absu.startswith("//"):
            absu = "https:" + absu
        if self.sock is None or self.port is None:
            return absu
        if self.proxy_img is None:
            self.proxy_img = self.probe_img(absu)
        if not self.proxy_img:
            return absu
        tok = hashlib.md5(absu.encode("utf-8")).hexdigest()[:20]
        self.tokens[tok] = absu
        if not self.img_handed:
            self.img_first_ts = time.time()
        self.img_handed += 1
        # 给出去一批图、过了宽限期一张都没被取过 → 说明客户端连不上本机代理，之后改直连
        if (self.img_handed >= 20 and self.img_hits == 0
                and time.time() - self.img_first_ts > 25):
            self.proxy_img = False
            return absu
        return "http://127.0.0.1:%d/rou/i/%s.jpg" % (self.port, tok)

    # ---------------- 分片 / 子清单 / 密钥
    def fetch(self, url, unwrap=True):
        data, ctype = self.get_cached(url)
        if data is not None:
            return data, ctype
        raw, final, hdrs = _http_get(url, referer=SITE + "/", timeout=TIMEOUT)
        if not unwrap:
            data = raw
            ctype = _img_ctype(data)
            self.put_cache(url, data, ctype, 3600)
            return data, ctype
        raw = _unwrap_container(raw)
        if raw.lstrip()[:7] == b"#EXTM3U":
            data = self.rewrite(raw.decode("utf-8", "replace"), final).encode("utf-8")
            ctype = "application/vnd.apple.mpegurl"
            self.put_cache(url, data, ctype, 1500)
        else:
            data = raw
            ctype = (hdrs.get("Content-Type") or "").split(";")[0].strip().lower()
            if not ctype or "png" in ctype or "octet" in ctype or "text" in ctype:
                ctype = "video/mp2t"
            self.put_cache(url, data, ctype, 300)
        return data, ctype


_PROXY = _Proxy()

# ---------------------------------------------------------------- 数据格式化

def _fmt_dur(sec):
    try:
        sec = int(float(sec))
    except Exception:
        return ""
    if sec <= 0:
        return ""
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    return ("%d:%02d:%02d" % (h, m, s)) if h else ("%d:%02d" % (m, s))


def _fmt_views(n):
    try:
        n = int(n)
    except Exception:
        return ""
    if n >= 100000000:
        return "%.1f亿" % (n / 100000000.0)
    if n >= 10000:
        return "%.1f万" % (n / 10000.0)
    return str(n)


def _res_of(v):
    srcs = v.get("sources") or []
    best = 0
    for s in srcs:
        try:
            best = max(best, int(s.get("resolution") or 0))
        except Exception:
            pass
    return ("%dP" % best) if best else ""


def _remarks(v):
    parts = []
    r = _res_of(v)
    if r:
        parts.append(r)
    d = _fmt_dur(v.get("duration"))
    if d:
        parts.append(d)
    views = _fmt_views(v.get("viewCount"))
    if views:
        parts.append(views)
    return " · ".join(parts)


def _vod_item(v):
    return {
        "vod_id": v.get("id") or "",
        "vod_name": v.get("nameZh") or v.get("name") or "",
        "vod_pic": _PROXY.img_url(v.get("coverImageUrl")),
        "vod_remarks": _remarks(v),
    }


def _series_item(s):
    epl = s.get("epLabel") or ""
    views = _fmt_views(s.get("viewCount"))
    return {
        "vod_id": "series:" + (s.get("id") or ""),
        "vod_name": s.get("nameZh") or s.get("name") or "",
        "vod_pic": _PROXY.img_url(s.get("coverImageUrl")),
        "vod_remarks": " · ".join([x for x in (epl, views) if x]),
    }


def _play_lines(lines):
    """线路与线路之间用 $$$，线路内集与集之间用 #。"""
    return "$$$".join([x for x in lines if x])


def _dedup(items, key="vod_id"):
    seen = set()
    out = []
    for it in items:
        k = it.get(key)
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out

class Spider(Spider):
    """OK影视 规范：getName / init + 五件套"""

    name = "肉视频"
    site_url = SITE
    headers = {"User-Agent": UA, "Referer": SITE + "/"}
    timeout = TIMEOUT
    page_size = PAGE_SIZE

    def getName(self):
        return self.name

    def init(self, extend=""):
        try:
            super(Spider, self).init(extend)
        except Exception:
            pass
        self.extend = extend or ""
        self._tax = None
        self._tax_ts = 0.0
        return None

    # ---------------- 分类 ----------------
    def _taxonomy(self):
        if getattr(self, "_tax", None) and time.time() - getattr(self, "_tax_ts", 0) < 1800:
            return self._tax
        try:
            tax = (_loader(_get_html("/cat")).get("taxonomy") or {})
        except Exception:
            tax = {}
        if tax:
            self._tax = tax
            self._tax_ts = time.time()
        return getattr(self, "_tax", None) or {}

    def _classes(self):
        out = [{"type_name": "短剧", "type_id": "__series__"}]
        tax = self._taxonomy()
        for c in (tax.get("cats") or []):
            name = c.get("id") or ""
            if name:
                out.append({"type_name": name, "type_id": name})
        genre = sorted(tax.get("genre") or [], key=lambda x: -(x.get("count") or 0))
        have = set(x["type_id"] for x in out)
        for g in genre[:18]:
            name = g.get("id") or ""
            if name and name not in have:
                out.append({"type_name": name, "type_id": name})
        return out

    # ---------------- 首页 ----------------
    def homeContent(self, filter):
        _PROXY.ensure()
        result = {"class": self._classes(), "list": []}
        try:
            lod = _loader(_get_html("/home"))
            items = []
            for key in ("latestVideos", "dailyHotCNAV", "dailyHotSelfie",
                        "dailyHot91", "hotCNAV", "hotSelfie", "hot91"):
                for v in (lod.get(key) or []):
                    if isinstance(v, dict) and v.get("id"):
                        items.append(_vod_item(v))
            result["list"] = _dedup(items)[:60]
        except Exception:
            pass
        return result

    # ---------------- 分类列表 ----------------
    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": 1, "pagecount": 0,
                  "limit": self.page_size, "total": 0}
        try:
            pg = int(pg) if str(pg).isdigit() else 1
        except Exception:
            pg = 1
        result["page"] = pg
        _PROXY.ensure()
        tid = str(tid or "")
        try:
            if tid == "__series__":
                lod = _loader(_get_html("/series?page=%d" % pg))
                rows = lod.get("list") or []
                result["list"] = _dedup([_series_item(s) for s in rows if isinstance(s, dict)])
                result["pagecount"] = int(lod.get("totalPage") or 0)
                result["total"] = int(lod.get("total") or 0)
            else:
                lod = _loader(_get_html("/t/%s?page=%d" % (quote(tid), pg)))
                rows = lod.get("videos") or []
                result["list"] = _dedup([_vod_item(v) for v in rows if isinstance(v, dict)])
                result["pagecount"] = int(lod.get("totalPage") or 0)
                result["total"] = int(lod.get("totalVideoNum") or 0)
        except Exception:
            pass
        return result

    # ---------------- 详情 ----------------
    def detailContent(self, ids):
        vid = ids if isinstance(ids, str) else (ids[0] if ids else "")
        vid = str(vid or "")
        if vid.startswith("series:"):
            return {"list": [self._series_detail(vid.split(":", 1)[1])]}
        return {"list": [self._video_detail(vid)]}

    def _play_payload(self, eps, fallback_id=""):
        """eps: [(集名, id)] → (vod_play_from, vod_play_url)。

        给两条线：本机回环，以及局域网地址。有些播放器会把 127.0.0.1 的请求
        塞进代理/走不通，这时候切第二条就能播。
        """
        if not eps and fallback_id:
            eps = [("正片", fallback_id)]
        if not eps:
            return "", ""
        port = _PROXY.ensure()
        if port is None:
            return "肉视频", "#".join(["%s$%s/api/hls/%s" % (nm, SITE, eid) for nm, eid in eps])
        hosts = [("肉视频", "127.0.0.1")]
        lan = _lan_ip()
        if lan:
            hosts.append(("肉视频·局域网", lan))
        froms, lines = [], []
        for label, host in hosts:
            froms.append(label)
            lines.append("#".join(["%s$http://%s:%d/rou/v/%s.m3u8" % (nm, host, port, eid)
                                   for nm, eid in eps]))
        return "$$$".join(froms), "$$$".join(lines)

    def _warm_async(self, vid):
        t = threading.Thread(target=_PROXY.warm, args=(vid,))
        t.daemon = True
        t.start()

    def _video_detail(self, vid):
        vod = {"vod_id": vid, "vod_name": "", "vod_pic": "", "vod_remarks": "",
               "vod_content": "", "vod_year": "", "vod_area": "",
               "vod_play_from": "肉视频", "vod_play_url": ""}
        eps = [("正片", vid)]
        try:
            lod = _loader(_get_html("/v/" + vid))
            v = lod.get("video") or {}
            if not v:
                return vod
            vod["vod_name"] = v.get("nameZh") or v.get("name") or vid
            vod["vod_pic"] = _PROXY.img_url(v.get("coverImageUrl"))
            vod["vod_remarks"] = _remarks(v)
            created = str(v.get("createdAt") or "")
            if created[:4].isdigit():
                vod["vod_year"] = created[:4]
            tags = v.get("tagsZh") or v.get("tags") or []
            desc = v.get("description") or ""
            head = "标签：" + " / ".join(tags) if tags else ""
            stat = "播放 %s · 时长 %s" % (_fmt_views(v.get("viewCount")), _fmt_dur(v.get("duration")))
            vod["vod_content"] = "\n".join([x for x in (desc, head, stat) if x])
            rows = lod.get("episodes") or []
            if rows:
                parts = []
                for i, ep in enumerate(rows):
                    eid = ep.get("id") or ""
                    if not eid:
                        continue
                    no = ep.get("episode") or (i + 1)
                    nm = str(ep.get("name") or "").split("·")[-1].strip() or ("第%d集" % no)
                    parts.append((nm, eid))
                if parts:
                    eps = parts
        except Exception:
            pass
        vod["vod_play_from"], vod["vod_play_url"] = self._play_payload(eps, vid)
        if eps:
            self._warm_async(eps[0][1])
        return vod

    def _series_detail(self, sid):
        vod = {"vod_id": "series:" + sid, "vod_name": "", "vod_pic": "", "vod_remarks": "",
               "vod_content": "", "vod_year": "", "vod_area": "",
               "vod_play_from": "肉视频", "vod_play_url": ""}
        eps = []
        try:
            lod = _loader(_get_html("/s/" + sid))
            s = lod.get("series") or {}
            vod["vod_name"] = s.get("nameZh") or s.get("name") or sid
            vod["vod_pic"] = _PROXY.img_url(s.get("coverImageUrl"))
            vod["vod_remarks"] = s.get("epLabel") or ""
            tags = s.get("tags") or []
            vod["vod_content"] = "\n".join([x for x in (
                s.get("description") or "",
                ("标签：" + " / ".join(tags)) if tags else "",
                "播放 %s · %s" % (_fmt_views(s.get("viewCount")), vod["vod_remarks"]),
            ) if x])
            created = str(s.get("createdAt") or "")
            if created[:4].isdigit():
                vod["vod_year"] = created[:4]
            rows = lod.get("episodes") or []
            for i, ep in enumerate(rows):
                eid = ep.get("id") or ""
                if not eid:
                    continue
                no = ep.get("episode") or (i + 1)
                nm = str(ep.get("name") or "").split("·")[-1].strip() or ("第%d集" % no)
                eps.append((nm, eid))
        except Exception:
            pass
        vod["vod_play_from"], vod["vod_play_url"] = self._play_payload(eps)
        if eps:
            self._warm_async(eps[0][1])
        return vod

    # ---------------- 搜索 ----------------
    def searchContent(self, key, quick, pg=1):
        result = {"list": [], "page": 1, "pagecount": 0,
                  "limit": self.page_size, "total": 0}
        key = str(key or "").strip()
        try:
            pg = int(pg) if str(pg).isdigit() else 1
        except Exception:
            pg = 1
        result["page"] = pg
        if not key:
            return result
        _PROXY.ensure()
        try:
            lod = _loader(_get_html("/search?q=%s&page=%d" % (quote(key), pg)))
            items = [_vod_item(v) for v in (lod.get("videos") or []) if isinstance(v, dict)]
            if not items:
                items = [_series_item(s) for s in (lod.get("seriesList") or []) if isinstance(s, dict)]
            result["list"] = _dedup(items)
            result["pagecount"] = int(lod.get("totalPage") or 0)
            result["total"] = int(lod.get("totalVideoNum") or 0)
        except Exception:
            pass
        return result

    # ---------------- 播放 ----------------
    def playerContent(self, flag, id, vipFlags):
        vid = str(id or "").strip()
        if "$" in vid:
            vid = vid.split("$")[-1].strip()
        header = {"User-Agent": UA, "Referer": SITE + "/"}
        if vid.startswith("http"):
            parts = urlsplit(vid)
            path = parts.path
            if path.startswith("/rou/v/"):
                eid = path[len("/rou/v/"):]
                if eid.endswith(".m3u8"):
                    eid = eid[:-5]
                # 用户选了哪条线就按哪条线走：局域网那条不能又被打回 127.0.0.1
                host = parts.hostname or "127.0.0.1"
                port = _PROXY.ensure()
                if port is None:
                    return {"parse": 0, "url": SITE + "/api/hls/" + eid, "header": header}
                hp = "%s:%d" % (host, port)
                try:
                    _PROXY.build_playlist(eid, hp)
                except Exception:
                    pass
                return {"parse": 0, "url": "http://%s/rou/v/%s.m3u8" % (hp, eid), "header": header}
            return {"parse": 0, "url": vid, "header": header}
        if not vid:
            return {"parse": 0, "url": "", "header": header}
        port = _PROXY.ensure()
        if port is None:
            return {"parse": 0, "url": SITE + "/api/hls/" + vid, "header": header}
        try:
            _PROXY.build_playlist(vid)
        except Exception:
            pass
        return {"parse": 0, "url": "http://127.0.0.1:%d/rou/v/%s.m3u8" % (port, vid), "header": header}
