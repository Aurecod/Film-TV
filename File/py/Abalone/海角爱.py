# -*- coding: utf-8 -*-
# 海角爱 (haijiaolove.xyz) — 修复版 2026-10-09
# 修复点:
#  1. 视频 CDN (ssrr.org/Cloudflare) 强校验 Referer 必须是播放页域名,
#     旧版写死 v.haijiaolove.xyz -> 403 -> body 全空 -> 无法播放。
#     现在把真实播放页 URL 作为 Referer 透传 (播放链接里的 r 参数)。
#  2. localProxy 按 FongMi 契约返回列表 [code, ctype, bytes, headers, base64flag],
#     并支持 Range 分片; 端口占用时的回落地址改用 getProxyUrl() (do=py 路由),
#     旧版 proxy://do=fd 会被路由到 jar 直接失败。
#  3. 上游文件大小未知 (s=0) 时先探测真实大小, 不再只回 64KB。
#  4. 分块 1MB -> 4MB, 减少上游请求数; 未知大小响应改 Connection: close。
import re
import json
import base64
import hashlib
import socket
import ssl
import gzip
from urllib.parse import quote, urlparse, urljoin

try:
    from base.spider import Spider as _Base
except ImportError:
    class _Base:
        def fetch(self, url, headers=None, **kw):
            import requests as rq
            kw.pop('timeout', None)
            r = rq.get(url, headers=headers, timeout=15, **kw)
            r.encoding = 'utf-8'
            return r

HOST = "https://www.haijiaolove.xyz"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
CATEGORIES = {
    "zjgx": "最近更新", "hjmz": "海角母子", "hjjd": "海角姐弟",
    "hjfn": "海角父女", "hjsz": "海角嫂子", "hjwf": "海角人妻",
    "origin": "海角原创", "hjsets": "海角合集",
    "hjhj": "合集大全", "hjrq": "热剧推荐", "hjyc": "原创精选",
}
WP_CAT = {"hjhj": 357, "hjrq": 355, "hjyc": 323}
ENCRYPT_HEAD = 65536          # 前 64KB 为 AES-CTR 加密, 其余明文
CHUNK = 4 * 1048576           # 上游单次拉取 4MB


_SBOX = bytes([
    0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5, 0x30, 0x01, 0x67, 0x2b, 0xfe, 0xd7, 0xab, 0x76,
    0xca, 0x82, 0xc9, 0x7d, 0xfa, 0x59, 0x47, 0xf0, 0xad, 0xd4, 0xa2, 0xaf, 0x9c, 0xa4, 0x72, 0xc0,
    0xb7, 0xfd, 0x93, 0x26, 0x36, 0x3f, 0xf7, 0xcc, 0x34, 0xa5, 0xe5, 0xf1, 0x71, 0xd8, 0x31, 0x15,
    0x04, 0xc7, 0x23, 0xc3, 0x18, 0x96, 0x05, 0x9a, 0x07, 0x12, 0x80, 0xe2, 0xeb, 0x27, 0xb2, 0x75,
    0x09, 0x83, 0x2c, 0x1a, 0x1b, 0x6e, 0x5a, 0xa0, 0x52, 0x3b, 0xd6, 0xb3, 0x29, 0xe3, 0x2f, 0x84,
    0x53, 0xd1, 0x00, 0xed, 0x20, 0xfc, 0xb1, 0x5b, 0x6a, 0xcb, 0xbe, 0x39, 0x4a, 0x4c, 0x58, 0xcf,
    0xd0, 0xef, 0xaa, 0xfb, 0x43, 0x4d, 0x33, 0x85, 0x45, 0xf9, 0x02, 0x7f, 0x50, 0x3c, 0x9f, 0xa8,
    0x51, 0xa3, 0x40, 0x8f, 0x92, 0x9d, 0x38, 0xf5, 0xbc, 0xb6, 0xda, 0x21, 0x10, 0xff, 0xf3, 0xd2,
    0xcd, 0x0c, 0x13, 0xec, 0x5f, 0x97, 0x44, 0x17, 0xc4, 0xa7, 0x7e, 0x3d, 0x64, 0x5d, 0x19, 0x73,
    0x60, 0x81, 0x4f, 0xdc, 0x22, 0x2a, 0x90, 0x88, 0x46, 0xee, 0xb8, 0x14, 0xde, 0x5e, 0x0b, 0xdb,
    0xe0, 0x32, 0x3a, 0x0a, 0x49, 0x06, 0x24, 0x5c, 0xc2, 0xd3, 0xac, 0x62, 0x91, 0x95, 0xe4, 0x79,
    0xe7, 0xc8, 0x37, 0x6d, 0x8d, 0xd5, 0x4e, 0xa9, 0x6c, 0x56, 0xf4, 0xea, 0x65, 0x7a, 0xae, 0x08,
    0xba, 0x78, 0x25, 0x2e, 0x1c, 0xa6, 0xb4, 0xc6, 0xe8, 0xdd, 0x74, 0x1f, 0x4b, 0xbd, 0x8b, 0x8a,
    0x70, 0x3e, 0xb5, 0x66, 0x48, 0x03, 0xf6, 0x0e, 0x61, 0x35, 0x57, 0xb9, 0x86, 0xc1, 0x1d, 0x9e,
    0xe1, 0xf8, 0x98, 0x11, 0x69, 0xd9, 0x8e, 0x94, 0x9b, 0x1e, 0x87, 0xe9, 0xce, 0x55, 0x28, 0xdf,
    0x8c, 0xa1, 0x89, 0x0d, 0xbf, 0xe6, 0x42, 0x68, 0x41, 0x99, 0x2d, 0x0f, 0xb0, 0x54, 0xbb, 0x16])


def _xtime(a):
    return ((a << 1) ^ 0x1b) & 0xff if a & 0x80 else (a << 1) & 0xff


def _nr_for(klen):
    return 10 if klen == 16 else (12 if klen == 24 else 14)


def _aes_key_expand(key):
    nk = len(key) // 4
    w = [int.from_bytes(key[i:i + 4], 'big') for i in range(0, len(key), 4)]
    rcon = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36]
    for i in range(nk, 4 * (_nr_for(len(key)) + 1)):
        t = w[i - 1]
        if i % nk == 0:
            t = ((t << 8) | (t >> 24)) & 0xffffffff
            t = ((_SBOX[(t >> 24) & 0xff] << 24) | (_SBOX[(t >> 16) & 0xff] << 16) |
                 (_SBOX[(t >> 8) & 0xff] << 8) | _SBOX[t & 0xff]) ^ (rcon[i // nk - 1] << 24)
        elif nk > 6 and i % nk == 4:
            t = ((_SBOX[(t >> 24) & 0xff] << 24) | (_SBOX[(t >> 16) & 0xff] << 16) |
                 (_SBOX[(t >> 8) & 0xff] << 8) | _SBOX[t & 0xff])
        w.append(w[i - nk] ^ t)
    return w


def _aes_enc_block(key, block):
    w = _aes_key_expand(key)
    nr = _nr_for(len(key))
    s = [[block[r + 4 * c] for r in range(4)] for c in range(4)]

    def ark(rnd):
        for c in range(4):
            for r in range(4):
                s[c][r] ^= (w[rnd * 4 + c] >> (24 - 8 * r)) & 0xff

    def sb():
        for c in range(4):
            for r in range(4):
                s[c][r] = _SBOX[s[c][r]]

    def sr():
        for r in range(1, 4):
            tmp = [s[c][r] for c in range(4)]
            for c in range(4):
                s[c][r] = tmp[(c + r) % 4]

    def mc():
        for c in range(4):
            a = [s[c][r] for r in range(4)]
            s[c][0] = _xtime(a[0]) ^ (a[1] ^ _xtime(a[1])) ^ a[2] ^ a[3]
            s[c][1] = a[0] ^ _xtime(a[1]) ^ (a[2] ^ _xtime(a[2])) ^ a[3]
            s[c][2] = a[0] ^ a[1] ^ _xtime(a[2]) ^ (a[3] ^ _xtime(a[3]))
            s[c][3] = (a[0] ^ _xtime(a[0])) ^ a[1] ^ a[2] ^ _xtime(a[3])

    ark(0)
    for rnd in range(1, nr):
        sb(); sr(); mc(); ark(rnd)
    sb(); sr(); ark(nr)
    return bytes(s[c][r] for c in range(4) for r in range(4))


def _aes_ctr_decrypt(key, counter, data):
    ctr = int.from_bytes(counter, 'big')
    out = bytearray()
    for i in range(0, len(data), 16):
        ks = _aes_enc_block(key, ctr.to_bytes(16, 'big'))
        out += bytes(a ^ b for a, b in zip(data[i:i + 16], ks))
        ctr = (ctr + 1) & 0xffffffffffffffffffffffffffffffff
    return bytes(out)


def _decrypt_datas(html):
    d = re.search(r'const datas = "([^"]+)"', html).group(1)
    obj = json.loads(base64.b64decode(d).decode('latin1'))
    media = obj['media']
    key_str = '%s:%s:%s' % (obj['user_id'], obj['slug'], obj['md5_id'])
    aes_key = hashlib.md5(key_str.encode()).hexdigest().encode('utf-8')
    plain = _aes_ctr_decrypt(aes_key, aes_key[:16], media.encode('latin1'))
    return json.loads(plain.decode('utf-8'))


class Spider(_Base):
    def init(self, extend=""):
        self.host = HOST
        if isinstance(extend, str) and extend.startswith("http"):
            self.host = extend.rstrip("/")
        self.headers = {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept-Encoding": "identity",
            "Connection": "close",
        }
        self._px = None
        self._port = 0
        self._start_proxy()

    # ---------------- 本地回环代理 (真流式, 低内存) ----------------

    def _start_proxy(self):
        if self._px:
            return
        import threading
        import http.server
        outer = self
        from urllib.parse import urlparse as _up, parse_qs as _pqs, unquote as _uq

        class H(http.server.BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *a):
                pass

            def do_GET(self):
                try:
                    q = _up(self.path)
                    if q.path != '/fd':
                        self.send_error(404)
                        return
                    ps = _pqs(q.query)
                    u = _uq(ps.get('u', [''])[0])
                    k = _uq(ps.get('k', [''])[0])
                    ref = _uq(ps.get('r', [''])[0])
                    try:
                        total = int(ps.get('s', ['0'])[0]) or 0
                    except Exception:
                        total = 0
                    if not u or not k:
                        self.send_error(400)
                        return
                    if not total:
                        total = outer._upstream_size(u, ref)
                    rng = self.headers.get('Range')
                    s, e = 0, (total - 1) if total else None
                    if rng:
                        m = re.match(r'bytes=(\d+)-(\d*)', rng)
                        if m:
                            s = int(m.group(1))
                            if m.group(2):
                                e2 = int(m.group(2))
                                e = e2 if e is None else min(e, e2)
                    outer._log('REQ %s %s (total=%d)' % (rng or '-', u[:70], total))
                    if total and s >= total:
                        self.send_error(416)
                        return
                    if e is None and total:
                        e = total - 1
                    self.send_response(206 if rng else 200)
                    if total and e is not None:
                        self.send_header('Content-Range', 'bytes %d-%d/%d' % (s, e, total))
                        self.send_header('Content-Length', str(e - s + 1))
                    self.send_header('Accept-Ranges', 'bytes')
                    self.send_header('Content-Type', 'video/mp4')
                    conn_close = e is None  # 未知长度时不能 keep-alive
                    self.send_header('Connection', 'close' if conn_close else 'keep-alive')
                    self.end_headers()
                    key = hashlib.md5(k.encode()).hexdigest().encode()
                    iv = int.from_bytes(key[:16], 'big')
                    sent = 0
                    if s < ENCRYPT_HEAD:
                        a0 = s // 16 * 16
                        a1 = ENCRYPT_HEAD - 1 if (e is None or e >= ENCRYPT_HEAD - 1) else e
                        raw = outer._http_get_bin(u, 'bytes=%d-%d' % (a0, a1), referer=ref)
                        if raw:
                            plain = _aes_ctr_decrypt(key, (iv + a0 // 16).to_bytes(16, 'big'), raw)
                            buf = plain[s - a0:a1 - a0 + 1]
                            self.wfile.write(buf)
                            sent += len(buf)
                            self.wfile.flush()
                    cur = max(s, ENCRYPT_HEAD)
                    while e is None or cur <= e:
                        end = e if (e is not None and e - cur < CHUNK) else cur + CHUNK - 1
                        chunk = outer._http_get_bin(u, 'bytes=%d-%d' % (cur, end), referer=ref)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        sent += len(chunk)
                        self.wfile.flush()
                        cur = end + 1
                    if conn_close or (e is not None and sent != e - s + 1):
                        self.close_connection = True
                except (BrokenPipeError, ConnectionResetError, OSError):
                    self.close_connection = True
                except Exception as ex:
                    outer._log('HDLEXC %s' % str(ex)[:120])
                    try:
                        self.send_error(500)
                    except Exception:
                        pass

        for port in range(9979, 9989):
            try:
                srv = http.server.ThreadingHTTPServer(('127.0.0.1', port), H)
                self._px = srv
                self._port = port
                threading.Thread(target=srv.serve_forever, daemon=True).start()
                break
            except Exception:
                continue

    # ---------------- FongMi localProxy 契约: 返回列表 ----------------

    def localProxy(self, param):
        try:
            if isinstance(param, str):
                param = json.loads(param) if param.strip().startswith('{') else {}
            if not isinstance(param, dict):
                return None
            u = param.get('u', '')
            k = param.get('k', '')
            if not u or not k:
                return None
            ref = param.get('r', '')
            try:
                total = int(param.get('s') or 0) or 0
            except Exception:
                total = 0
            if not total:
                total = self._upstream_size(u, ref)
            rng = ''
            for pk, pv in param.items():
                if isinstance(pk, str) and pk.lower() == 'range' and pv:
                    rng = pv
                    break
            s, e = 0, (total - 1) if total else None
            m = re.match(r'bytes=(\d+)-(\d*)', rng) if rng else None
            if m:
                s = int(m.group(1))
                if m.group(2):
                    e2 = int(m.group(2))
                    e = e2 if e is None else min(e, e2)
            self._log('LPREQ %s (total=%d)' % (rng or '-', total))
            if total and s >= total:
                return [416, 'text/plain', b'range not satisfiable', {}, 0]
            body = self._fetch_slice(u, k, ref, s, e)
            hdrs = {'Accept-Ranges': 'bytes', 'Content-Type': 'video/mp4'}
            if rng:
                if total and e is not None:
                    hdrs['Content-Range'] = 'bytes %d-%d/%d' % (s, e, total)
                return [206, 'video/mp4', body, hdrs, 0]
            return [200, 'video/mp4', body, hdrs, 0]
        except Exception as ex:
            self._log('LPERR %s' % str(ex)[:120])
            return None

    def _fetch_slice(self, u, k, ref, s, e):
        key = hashlib.md5(k.encode()).hexdigest().encode()
        iv = int.from_bytes(key[:16], 'big')
        out = bytearray()
        if s < ENCRYPT_HEAD:
            a0 = s // 16 * 16
            a1 = ENCRYPT_HEAD - 1 if (e is None or e >= ENCRYPT_HEAD - 1) else e
            raw = self._http_get_bin(u, 'bytes=%d-%d' % (a0, a1), referer=ref)
            if raw:
                plain = _aes_ctr_decrypt(key, (iv + a0 // 16).to_bytes(16, 'big'), raw)
                out += plain[s - a0:]
        cur = max(s, ENCRYPT_HEAD)
        while e is None or cur <= e:
            end = e if (e is not None and e - cur < CHUNK) else cur + CHUNK - 1
            chunk = self._http_get_bin(u, 'bytes=%d-%d' % (cur, end), referer=ref)
            if not chunk:
                break
            out += chunk
            cur = end + 1
        return bytes(out)

    # ---------------- 上游下载 ----------------

    def _upstream_size(self, u, ref):
        """Range 探测上游文件真实大小 (s 参数缺失时用)。"""
        try:
            hd, _body = self._raw_get(u, headers={'Range': 'bytes=0-0'}, timeout=15)
            m = re.search(r'/(\d+)\s*$', hd.get('content-range', ''))
            if m:
                return int(m.group(1))
            if not hd.get('content-range') and hd.get('content-length'):
                return int(hd['content-length'])
        except Exception:
            pass
        return 0

    def _log(self, msg):
        try:
            with open('/sdcard/Download/hjl_proxy.log', 'a') as f:
                f.write(msg + '\n')
        except Exception:
            pass

    def _http_get_bin(self, url, rng=None, referer='', timeout=30, tries=3):
        p = urlparse(url)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        hdrs = dict(self.headers)
        hdrs['Host'] = p.netloc
        # CDN 强校验 Referer: 必须是播放页域名 (abyssplayer), 不能写死 www/v 站
        hdrs['Referer'] = referer or 'https://player.abyssplayer.com/'
        hdrs['Accept-Encoding'] = 'identity'
        if rng:
            hdrs['Range'] = rng
        req = 'GET %s HTTP/1.1\r\n%s\r\n\r\n' % (p.path + ('?' + p.query if p.query else ''),
                                                  '\r\n'.join('%s: %s' % (x, y) for x, y in hdrs.items()))
        import time as _time
        data = b''
        for attempt in range(1, tries + 1):
            try:
                with socket.create_connection((p.netloc, 443), timeout=timeout) as raw:
                    with ctx.wrap_socket(raw, server_hostname=p.netloc) as ss:
                        ss.sendall(req.encode())
                        while True:
                            chunk = ss.recv(262144)
                            if not chunk:
                                break
                            data += chunk
                head, _, body = data.partition(b'\r\n\r\n')
                code = int(head.split(b' ')[1]) if head else 0
                if code >= 400:
                    self._log('ERR %s %s -> %d (try %d)' % (rng, url[:60], code, attempt))
                    if attempt < tries:
                        _time.sleep(0.6 * attempt)
                        data = b''
                        continue
                    return b''
                if head.lower().find(b'transfer-encoding: chunked') >= 0:
                    body = self._unchunk(body)
                if head.lower().find(b'content-encoding: gzip') >= 0:
                    body = gzip.decompress(body)
                return body
            except Exception as e:
                self._log('NETERR %s %s -> %s (try %d)' % (rng, url[:60], str(e)[:80], attempt))
                data = b''
                if attempt < tries:
                    _time.sleep(0.6 * attempt)
        return b''

    def _http_get(self, host, path, headers=None, timeout=15, redir=0, sni=None):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        hdrs = dict(self.headers)
        hdrs['Host'] = host
        hdrs['Referer'] = "https://%s/" % host
        if headers:
            hdrs.update(headers)
        req = 'GET %s HTTP/1.1\r\n%s\r\n\r\n' % (path, '\r\n'.join('%s: %s' % (k, v) for k, v in hdrs.items()))
        data = b''
        with socket.create_connection((host, 443), timeout=timeout) as raw:
            with ctx.wrap_socket(raw, server_hostname=sni) as ss:
                ss.sendall(req.encode())
                while True:
                    chunk = ss.recv(65536)
                    if not chunk:
                        break
                    data += chunk
        head, _, body = data.partition(b'\r\n\r\n')
        if int(head.split(b' ')[1]) >= 400:
            return ''
        loc = re.search(br'Location: ([^\r\n]+)', head, re.I)
        if loc and redir < 5:
            newurl = urljoin('https://%s%s' % (host, path), loc.group(1).decode())
            np = urlparse(newurl)
            return self._http_get(np.netloc, np.path + ('?' + np.query if np.query else ''), headers=headers, redir=redir + 1, sni=sni)
        if head.lower().find(b'content-encoding: gzip') >= 0:
            body = gzip.decompress(body)
        return body.decode('utf-8', 'ignore')

    def _get(self, url, headers=None):
        try:
            p = urlparse(url)
            path = p.path or '/'
            if p.query:
                path += '?' + p.query
            return self._http_get(p.netloc, path, headers=headers, sni=p.netloc)
        except Exception:
            return ''

    # ---------------- TVBox/FongMi 接口 ----------------

    def getName(self):
        return "海角爱"

    def getDependence(self):
        return []

    def destroy(self):
        # 保持回环代理存活, 避免重新加载站点时中断正在播放的流
        pass

    def isVideoFormat(self, url):
        return bool(url and ('.fd' in url or '.m3u8' in url or '.mp4' in url))

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return ''

    def homeContent(self, filter=False):
        return {"class": [{"type_id": k, "type_name": v} for k, v in CATEGORIES.items()], "filters": {}, "type": "影视", "list": []}

    def homeVideoContent(self):
        return self.categoryContent("zjgx", 1, False, "")

    @staticmethod
    def _unchunk(body):
        if b'\r\n' not in body[:8]:
            return body
        out = bytearray()
        i = 0
        n = len(body)
        while i < n:
            j = body.find(b'\r\n', i)
            if j < 0:
                break
            try:
                sz = int(body[i:j].strip(), 16)
            except Exception:
                out += body[i:]
                break
            if sz == 0:
                break
            if j + 2 + sz > n:
                break
            out += body[j + 2:j + 2 + sz]
            i = j + 2 + sz + 2
        return bytes(out)

    def _raw_get(self, url, headers=None, timeout=20):
        p = urlparse(url)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        hdrs = dict(self.headers)
        hdrs['Host'] = p.netloc
        hdrs['Referer'] = 'https://%s/' % p.netloc
        if headers:
            hdrs.update(headers)
        req = 'GET %s HTTP/1.1\r\n%s\r\n\r\n' % (p.path + ('?' + p.query if p.query else ''),
                                                  '\r\n'.join('%s: %s' % (x, y) for x, y in hdrs.items()))
        data = b''
        try:
            with socket.create_connection((p.netloc, 443), timeout=timeout) as raw:
                with ctx.wrap_socket(raw, server_hostname=p.netloc) as ss:
                    ss.sendall(req.encode())
                    while True:
                        chunk = ss.recv(262144)
                        if not chunk:
                            break
                        data += chunk
        except Exception:
            return {}, b''
        head, _, body = data.partition(b'\r\n\r\n')
        hd = {}
        for ln in head.split(b'\r\n')[1:]:
            if b':' in ln:
                k, v = ln.split(b':', 1)
                hd[k.decode('latin1').lower().strip()] = v.decode('latin1').strip()
        if hd.get('transfer-encoding', '').lower() == 'chunked':
            body = self._unchunk(body)
        if hd.get('content-encoding', '').lower() == 'gzip':
            try:
                body = gzip.decompress(body)
            except Exception:
                pass
        return hd, body

    def _cat_wpjson(self, cid, pn):
        url = '%s/wp-json/wp/v2/posts?categories=%d&per_page=20&page=%d&_embed' % (self.host, cid, pn)
        hd, body = self._raw_get(url)
        vods = []
        try:
            posts = json.loads(body.decode('utf-8', 'ignore'))
            for p in posts:
                emb = p.get('_embedded', {}) or {}
                fm = (emb.get('wp:featuredmedia') or [{}])[0]
                pic = fm.get('source_url', '') if fm else ''
                vods.append({"vod_id": p.get('link', ''), "vod_name": p.get('title', {}).get('rendered', ''),
                             "vod_pic": pic, "vod_remarks": ""})
        except Exception:
            pass
        pc = 1
        try:
            pc = int(hd.get('x-wp-totalpages', '1') or '1')
        except Exception:
            pass
        return {"list": vods, "page": pn, "pagecount": max(pc, 1), "limit": 20, "total": max(pc, 1) * 20}

    def categoryContent(self, tid, pg=1, filter=False, extend=""):
        try:
            pn = max(1, int(str(pg)))
        except Exception:
            pn = 1
        if tid in WP_CAT:
            return self._cat_wpjson(WP_CAT[tid], pn)
        url = f"{self.host}/{tid}/" if pn == 1 else f"{self.host}/{tid}/?_page={pn}"
        text = self._get(url)
        vods = []
        pagecount = pn
        if text:
            for m in re.finditer(r'<a href="([^"]+?\.html)"[^>]*class="[^"]*pt-cv-href-thumbnail[^"]*"[^>]*>.*?data-cvpsrc="([^"]+)"[^>]*>', text, re.S):
                link, pic = m.group(1), m.group(2)
                mid = link.rsplit("/", 1)[-1]
                if link.startswith("/"):
                    link = self.host + link
                vods.append({"vod_id": link, "vod_name": mid, "vod_pic": self._pic_url(pic), "vod_remarks": ""})
            for m in re.finditer(r'class="pt-cv-title">\s*<a href="([^"]+?\.html)"[^>]*>([^<]+)</a>', text):
                link, name = m.group(1), m.group(2).strip()
                if link.startswith("/"):
                    link = self.host + link
                for v in vods:
                    if v["vod_id"] == link:
                        v["vod_name"] = name
                        break
            tp = re.search(r'data-totalpages="(\d+)"', text)
            if tp:
                pagecount = max(pagecount, int(tp.group(1)))
        return {"list": vods, "page": pn, "pagecount": pagecount, "limit": 20, "total": pagecount * 20}

    def detailContent(self, ids):
        try:
            vid = ids if isinstance(ids, str) else ids[0]
        except Exception:
            vid = ''
        vod = {"vod_id": vid, "vod_name": vid.rsplit("/", 1)[-1] if vid else "", "vod_pic": "", "vod_remarks": "",
               "vod_year": "", "vod_area": "", "vod_director": "", "vod_actor": "",
               "vod_content": "", "vod_play_from": "", "vod_play_url": ""}
        if not vid:
            return {"list": [vod]}
        url = vid if vid.startswith("http") else self.host + "/" + vid.lstrip("/")
        text = self._get(url)
        if not text:
            return {"list": [vod]}
        m = re.search(r'<h1[^>]*class="entry-title"[^>]*>([^<]+)</h1>', text)
        if m:
            vod["vod_name"] = m.group(1).strip()
        m = re.search(r'class="[^"]*attachment-large[^"]*"[^>]*src="([^"]+)"', text)
        if not m:
            m = re.search(r'<meta[^>]*property="og:image"[^>]*content="([^"]+)"', text)
        if not m:
            m = re.search(r'wp-post-image[^>]*src="([^"]+)"', text)
        if m:
            vod["vod_pic"] = self._pic_url(m.group(1))
        m = re.search(r'name="description" content="([^"]+)"', text)
        if not m:
            m = re.search(r'<meta[^>]*property="og:description"[^>]*content="([^"]+)"', text)
        if m:
            vod["vod_content"] = m.group(1)
        frames = re.findall(r'<iframe[^>]*src="([^"]+)"', text)
        seen = []
        for f in frames:
            if f.startswith('//'):
                f = 'https:' + f
            if not f.startswith('http'):
                f = 'https:' + f
            if f not in seen:
                seen.append(f)
        if seen:
            vod["vod_play_from"] = '$$$'.join('线路%d' % (i + 1) for i in range(len(seen)))
            vod["vod_play_url"] = '$$$'.join('%d集$%s' % (i + 1, u) for i, u in enumerate(seen))
        return {"list": [vod]}

    def searchContent(self, key, quick=False, pg="1"):
        text = self._get(self.host + "/?s=" + quote(str(key)))
        vods = []
        if text:
            for m in re.finditer(r'<article[^>]*id="post-\d+"[^>]*>.*?<a href="([^"]+?\.html)"[^>]*>.*?<img[^>]*src="([^"]+)"[^>]*>', text, re.S):
                link, pic = m.group(1), m.group(2)
                if link.startswith("/"):
                    link = self.host + link
                vods.append({"vod_id": link, "vod_name": link.rsplit("/", 1)[-1], "vod_pic": self._pic_url(pic), "vod_remarks": ""})
            for m in re.finditer(r'<h2[^>]*class="entry-title[^"]*"[^>]*>\s*<a href="([^"]+?\.html)"[^>]*>([^<]+)</a>', text, re.S):
                link, name = m.group(1), m.group(2).strip()
                if link.startswith("/"):
                    link = self.host + link
                for v in vods:
                    if v["vod_id"] == link:
                        v["vod_name"] = name
                        break
        return {"list": vods}

    def _play_url(self, fu, fk, fs, ref):
        """生成播放地址: 优先本地回环代理, 回落 FongMi 自带 proxy (do=py)。"""
        q = 'u=%s&k=%s&s=%s&r=%s' % (quote(fu, safe=''), quote(fk, safe=''), fs, quote(ref, safe=''))
        if self._port:
            return {"parse": 0, "url": 'http://127.0.0.1:%d/fd?%s' % (self._port, q)}
        try:
            return {"parse": 0, "url": self.getProxyUrl() + '&' + q}
        except Exception:
            return {"parse": 0, "url": 'proxy://do=py&' + q}

    def playerContent(self, flag, id, vipFlags=None):
        u = id if id.startswith("http") else self.host + id
        u = u.split('#')[0]
        if self.host in u and u.endswith('.html'):
            t = self._get(u)
            fr = re.findall(r'<iframe[^>]*src="([^"]+)"', t)
            if fr:
                u = fr[0]
                if u.startswith('//'):
                    u = 'https:' + u
        if 'abyssplayer.com' in u or 'haijiaolove.xyz/?v=' in u or 'v.haijiaolove.xyz' in u:
            src_url = u
            if 'haijiaolove.xyz/?v=' in u:
                src_url = re.sub(r'^https?://[^/]+', 'https://v.haijiaolove.xyz', u)
            try:
                text = self._get(src_url, headers={'Referer': 'https://www.haijiaolove.xyz/'})
                j = _decrypt_datas(text)
                mp4 = j.get('mp4', {}) or {}
                use = None
                for s0 in (mp4.get('sources') or []):
                    if s0.get('status') and s0.get('url') and s0.get('path'):
                        use = s0
                        break
                if not use:
                    fd = mp4.get('fristDatas') or []
                    if fd and fd[0].get('url'):
                        fu0 = fd[0]['url']
                        use = {'url': fu0.rsplit('/', 1)[0], 'path': fu0.rsplit('/', 1)[-1],
                               'size': fd[0].get('size') or 0}
                if use:
                    fu = use['url'].rstrip('/') + '/' + use['path'].lstrip('/')
                    fk = use['path'].split('/')[-1]
                    fs = str(use.get('size') or 0)
                    return self._play_url(fu, fk, fs, src_url)
            except Exception as ex:
                self._log('PLAYERERR %s' % str(ex)[:120])
        return {"parse": 1, "url": u, "header": self.headers}

    def _pic_url(self, url):
        return url.replace("http://", "https://") if url.startswith("http") else url

    def _pagecount(self):
        return 9999

    def _items(self):
        return []
