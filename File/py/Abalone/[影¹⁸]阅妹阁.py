# coding=utf-8
"""阅妹阁聚合（阅姝阁站群）· TVBox/FongMi Python 插件 · 纯标准库
挂法: {"name":"🔞阅妹阁聚合","type":3,"api":"./File/py/Abalone/ymg.py"}
extend: {"sites":"kanpian41,kanpian89","off":"kanpian96","timeout":20,"gwkey":"可选网关钥匙"}
"""
import base64
import gzip
import hashlib
import hmac
import json
import re
import threading
import time
import urllib.parse
import urllib.request

try:
    from base.spider import Spider as _Spider
except Exception:
    class _Spider(object):
        pass

UA = ('Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/131.0.0.0 Mobile Safari/537.36')
PER = 24
FERNET_KEY = 'NyGRG56A8i5J2JMqh7da83r2MMfgbM7Ppw1aCF8YnAY='
DEF_API = 'sm-api.wieuc.com'
DEF_IMG = 'hm-img.hdstfb.com'
LINE_NAME = ['线路1', '线路2', '海外专线']
LINE_HOST = ['hm-vip.hdstfb.com', 'hm-img.hdstfb.com', 'hm-img.aa66cc.live']

SITES = [
    {'key': 'kanpian41', 'name': '41看片', 'family': 'wieuc', 'site': 6, 'chan': 'gj-41',
     'entrance': 'https://asdon.417712.xyz:8283/?nb=gj&bm=41&ml=kp', 'group': '看片站群'},
    {'key': 'kanpian89', 'name': '89看片', 'family': 'wieuc', 'site': 2, 'chan': 'gj-89',
     'entrance': 'https://traxks.894402.xyz:8283/?nb=gj&bm=89&ml=kp', 'group': '看片站群'},
    {'key': 'kanpian96', 'name': '96看片', 'family': 'wieuc', 'site': 18, 'chan': 'gj-96',
     'entrance': 'https://ygfsop.964870.xyz:8283/?nb=gj&bm=96&ml=kp', 'group': '看片站群'},
]

# 加密采集网关族：extend.gwkey 填钥匙后自动点亮
GW_SITES = [
    {'key': 'gw_dsp91', 'name': 'DSP91', 'mod': 'dsp91', 'host': 'api3.gdapi1.com', 'path': 'api.php'},
    {'key': 'gw_qp', 'name': 'Qp站', 'mod': 'qp', 'host': 'api1.gdapi1.com', 'path': 'api.php'},
    {'key': 'gw_mimei', 'name': '迷妹漫画', 'mod': 'mimei', 'host': 'api3.zpcapiz3.com', 'path': 'api.php'},
    {'key': 'gw_xjsp', 'name': '香蕉视频', 'mod': 'xjsp', 'host': 'api2.zpcapiz2.com', 'path': 'api.php'},
    {'key': 'gw_byfm', 'name': 'ByFm', 'mod': 'byfm', 'host': 'api2.zpcapikd.cc', 'path': ''},
    {'key': 'gw_xbk', 'name': 'Xbk', 'mod': 'xbk', 'host': 'api2.piifvly.com', 'path': 'api.php'},
    {'key': 'gw_cgw', 'name': '吃瓜网', 'mod': 'cgw', 'host': 'sapi02.gg-gv.com', 'path': 'api.php'},
    {'key': 'gw_hxsp', 'name': 'HxSp', 'mod': 'hxsp', 'host': 'api1.bmvjxkdfz.cc', 'path': 'pwa.php'},
    {'key': 'gw_qysq', 'name': 'QySq', 'mod': 'qysq', 'host': 'api3.rcbvmajq.cc', 'path': 'pwa.php'},
]


def _mk_tables():
    exp = [0] * 512
    log = [0] * 256
    x = 1
    for i in range(255):
        exp[i] = x
        log[x] = i
        hi = x & 0x80
        t = ((x << 1) & 0xFF) ^ (0x1B if hi else 0)
        x = x ^ t
    for i in range(255, 512):
        exp[i] = exp[i - 255]

    def mul(a, b):
        if a == 0 or b == 0:
            return 0
        return exp[log[a] + log[b]]

    def inv(a):
        return 0 if a == 0 else exp[255 - log[a]]

    def rotl(v, n):
        return ((v << n) | (v >> (8 - n))) & 0xFF

    sbox = [0] * 256
    for i in range(256):
        v = inv(i)
        sbox[i] = (v ^ rotl(v, 1) ^ rotl(v, 2) ^ rotl(v, 3) ^ rotl(v, 4) ^ 0x63) & 0xFF
    rsbox = [0] * 256
    for i, v in enumerate(sbox):
        rsbox[v] = i

    def gmul(a, b):
        if a == 0 or b == 0:
            return 0
        return exp[log[a] + log[b]]

    return sbox, rsbox, gmul


_SBOX, _RSBOX, _gmul = _mk_tables()
_RCON = (0x00, 0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36)


def _key_expand(key):
    nk = len(key) // 4
    nr = nk + 6
    w = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    for i in range(nk, 4 * (nr + 1)):
        t = list(w[i - 1])
        if i % nk == 0:
            t = t[1:] + t[:1]
            t = [_SBOX[b] for b in t]
            t[0] ^= _RCON[i // nk]
        elif nk > 6 and i % nk == 4:
            t = [_SBOX[b] for b in t]
        w.append([w[i - nk][j] ^ t[j] for j in range(4)])
    return w, nr


def _aes_cbc_decrypt(data, key, iv):
    if len(key) not in (16, 24, 32):
        raise ValueError('bad key len %d' % len(key))
    if len(iv) != 16 or not data or len(data) % 16:
        raise ValueError('bad iv/ct len')
    w, nr = _key_expand(key)
    out = bytearray()
    prev = iv
    for off in range(0, len(data), 16):
        blk = data[off:off + 16]
        st = [[blk[r + 4 * c] for c in range(4)] for r in range(4)]
        for c in range(4):
            for r in range(4):
                st[r][c] ^= w[nr * 4 + c][r]
        for rnd in range(nr - 1, 0, -1):
            for r in range(1, 4):
                st[r] = st[r][-r:] + st[r][:-r]
            for r in range(4):
                for c in range(4):
                    st[r][c] = _RSBOX[st[r][c]]
            for c in range(4):
                for r in range(4):
                    st[r][c] ^= w[rnd * 4 + c][r]
            for c in range(4):
                a = [st[r][c] for r in range(4)]
                st[0][c] = _gmul(a[0], 14) ^ _gmul(a[1], 11) ^ _gmul(a[2], 13) ^ _gmul(a[3], 9)
                st[1][c] = _gmul(a[0], 9) ^ _gmul(a[1], 14) ^ _gmul(a[2], 11) ^ _gmul(a[3], 13)
                st[2][c] = _gmul(a[0], 13) ^ _gmul(a[1], 9) ^ _gmul(a[2], 14) ^ _gmul(a[3], 11)
                st[3][c] = _gmul(a[0], 11) ^ _gmul(a[1], 13) ^ _gmul(a[2], 9) ^ _gmul(a[3], 14)
        for r in range(1, 4):
            st[r] = st[r][-r:] + st[r][:-r]
        for r in range(4):
            for c in range(4):
                st[r][c] = _RSBOX[st[r][c]]
        for c in range(4):
            for r in range(4):
                st[r][c] ^= w[c][r]
        dec = bytes(st[r][c] for c in range(4) for r in range(4))
        out.extend(bytes(dec[i] ^ prev[i] for i in range(16)))
        prev = blk
    pad = out[-1]
    if 1 <= pad <= 16 and out[-pad:] == bytes([pad]) * pad:
        out = out[:-pad]
    return bytes(out)


def _b64d(s):
    s = str(s or '').strip().replace('-', '+').replace('_', '/')
    s += '=' * (-len(s) % 4)
    return base64.b64decode(s)


def _fernet(tok, key_b64=None):
    try:
        key = _b64d(key_b64 or FERNET_KEY)
        raw = _b64d(tok)
        if not raw or (raw[0] & 0xFF) != 0x80 or len(raw) < 57 or len(key) < 32:
            return ''
        if not hmac.compare_digest(hmac.new(key[:16], raw[:-32], hashlib.sha256).digest(), raw[-32:]):
            return ''
        return _aes_cbc_decrypt(raw[25:-32], key[16:32], raw[9:25]).decode('utf-8', 'replace')
    except Exception:
        return ''


def _mime_of(b):
    if not b or len(b) < 4:
        return 'application/octet-stream'
    if b[0:2] == b'\xff\xd8':
        return 'image/jpeg'
    if b[0:4] == b'\x89PNG':
        return 'image/png'
    if b[0:4] == b'RIFF' and b[8:12] == b'WEBP':
        return 'image/webp'
    if b[0:3] == b'GIF':
        return 'image/gif'
    if b[0:2] == b'BM':
        return 'image/bmp'
    return 'application/octet-stream'


def _unbundle(b):
    if not b or len(b) < 16:
        return None, None
    if b[0:4] != b'gAAA':
        m = _mime_of(b)
        return (m, b) if m.startswith('image/') else (None, None)
    sep = b.find(b'@@@', 4)
    if sep <= 0:
        return None, None
    try:
        head = _fernet(b[:sep].decode('latin-1'))
        if not head.startswith('data:'):
            return None, None
        semi = head.find(';')
        comma = head.find('base64,')
        if semi < 6 or comma < 6:
            return None, None
        img = base64.b64decode(head[comma + 7:].encode('latin-1') + b[sep + 3:])
        if len(img) < 64:
            return None, None
        return (head[5:semi] or _mime_of(img)), img
    except Exception:
        return None, None


class Spider(_Spider):

    def __init__(self, *args, **kwargs):
        self.timeout = 20
        self.api = DEF_API
        self.img = DEF_IMG
        self.lines = list(LINE_HOST)
        self.gwkey = ''
        self.sites = [dict(s) for s in SITES]
        self._status = {}
        self._grp = {}
        self._lock = threading.Lock()
        self._resolved = {}
        self._res_locks = {}
        self._mix_cache = {}

    def init(self, extend=''):
        ext = {}
        if extend:
            try:
                ext = json.loads(extend) if str(extend).strip().startswith('{') else {}
            except Exception:
                ext = {}
        if ext.get('api'):
            self.api = str(ext['api']).replace('https://', '').replace('http://', '').split('/')[0]
        if ext.get('gwkey'):
            self.gwkey = str(ext['gwkey']).strip()
        if ext.get('timeout'):
            try:
                self.timeout = max(6, int(ext['timeout']))
            except Exception:
                pass
        on = str(ext.get('sites') or '').strip()
        off = str(ext.get('off') or '').strip()
        if on:
            want = set(x.strip() for x in on.split(',') if x.strip())
            self.sites = [s for s in self.sites if s['key'] in want]
        if off:
            bad = set(x.strip() for x in off.split(',') if x.strip())
            self.sites = [s for s in self.sites if s['key'] not in bad]
        if self.gwkey:
            for g in GW_SITES:
                d = dict(g)
                d['family'] = 'maccms'
                d['group'] = '采集网关'
                self.sites.append(d)
        try:
            self._prewarm()
        except Exception:
            pass

    def getName(self):
        return '阅妹阁聚合'

    def getDependence(self):
        return []

    def destroy(self):
        self._grp.clear()
        self._status.clear()

    def isVideoFormat(self, url):
        u = str(url or '').lower()
        return '.m3u8' in u or '.mp4' in u

    def manualVideoCheck(self):
        return False

    @staticmethod
    def _to_int(v, d=0):
        try:
            return int(str(v).strip() or d)
        except Exception:
            try:
                return int(float(str(v).strip() or 0))
            except Exception:
                return d

    def _proxy_pic(self, pic, sid='', vid='', cf=None):
        # siteKey 保证多 py 站时 do=py 路由回本站（默认路由最近使用的 py 站会串台）
        if not pic:
            return ''
        if not pic.startswith('http'):
            pic = 'https://' + ((cf or {}).get('img') or self.img) + pic
        try:
            base = self.getProxyUrl()
        except Exception:
            base = ''
        if not base:
            return pic
        sk = str(getattr(self, 'siteKey', '') or '')
        skq = '&siteKey=' + urllib.parse.quote(sk) if sk else ''
        return (base + '&url=' + urllib.parse.quote(pic, safe='')
                + '&s=' + urllib.parse.quote(str(sid or ''))
                + '&v=' + str(vid or '') + skq)

    def _http(self, url, want='text', timeout=None):
        try:
            h = {'User-Agent': UA, 'Accept': '*/*', 'Accept-Encoding': 'gzip'}
            if want == 'img':
                h['Accept'] = 'image/avif,image/webp,image/*,*/*;q=0.8'
            req = urllib.request.Request(url, headers=h)
            try:
                import ssl
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                r = urllib.request.urlopen(req, timeout=timeout or self.timeout, context=ctx)
            except Exception:
                r = urllib.request.urlopen(req, timeout=timeout or self.timeout)
            raw = r.read()
            if r.headers.get('Content-Encoding') == 'gzip':
                try:
                    raw = gzip.decompress(raw)
                except Exception:
                    pass
            if want == 'bytes':
                return raw
            return raw.decode('utf-8', 'replace')
        except Exception:
            return b'' if want == 'bytes' else ''

    def fetch_bytes(self, url):
        return self._http(url, 'bytes', 12) or None

    def api_get(self, path):
        url = path if str(path).startswith('http') else ('https://' + self.api + path)
        t = self._http(url)
        if not t or len(t) < 8:
            return {}
        try:
            o = json.loads(t)
        except Exception:
            return {}
        if not isinstance(o, dict):
            return {}
        x = o.get('x-data') or o.get('data')
        if not x or not isinstance(x, str) or not x.startswith('gAAAAA'):
            return o
        p = _fernet(x, self.gwkey or None)
        if not p:
            return {}
        try:
            return json.loads(p)
        except Exception:
            return {}

    @staticmethod
    def _items(r):
        d = (r or {}).get('data')
        if isinstance(d, list):
            return d
        if isinstance(d, dict):
            return d.get('items') or []
        return []

    @staticmethod
    def _data(r):
        d = (r or {}).get('data')
        return d if isinstance(d, dict) else (r or {})

    def _cfg_fallback(self, st):
        return {'api': self.api, 'site': self._to_int(st.get('site')),
                'img': self.img, 'lines': list(self.lines), 'ok': False}

    def _resolve(self, st, nowait=False):
        k = st.get('key') or st.get('entrance')
        with self._lock:
            if k in self._resolved:
                return self._resolved[k]
            lk = self._res_locks.setdefault(k, threading.Lock())
        if nowait:
            if not lk.acquire(timeout=0):
                return self._cfg_fallback(st)
        else:
            lk.acquire()
        try:
            with self._lock:
                if k in self._resolved:
                    return self._resolved[k]
            out = self._cfg_fallback(st)
            try:
                b = self._http(st['entrance'], timeout=10)
                m = re.search(r'\[[^\]]*"([A-Za-z0-9+/=]{20,})"[^\]]*\]', b or '')
                if not m:
                    raise ValueError('hop0')
                nxt = base64.b64decode(m.group(1)).decode('utf-8', 'replace')
                b1 = self._http(nxt, timeout=10)
                m2 = re.search(r'decode\("([A-Za-z0-9+/=]+)"\)\s*\.split\("\|"\)\s*,\s*channel\s*=\s*"([^"]+)"', b1 or '')
                if not m2:
                    raise ValueError('hop1')
                host = base64.b64decode(m2.group(1)).decode('utf-8', 'replace').split('|')[0].rstrip('/')
                chan = m2.group(2)
                b2 = self._http(host + '/home?channel=' + chan, timeout=10)
                m3 = re.search(r"window\.CONFIG\s*=\s*'([^']+)'", b2 or '')
                if not m3:
                    raise ValueError('config')
                cfg = json.loads(_fernet(m3.group(1)))
                out['api'] = str(cfg.get('api_url') or '').strip() or out['api']
                out['img'] = str(cfg.get('video_img_url') or '').strip() or out['img']
                sid = self._to_int(cfg.get('site_id'))
                if sid > 0:
                    out['site'] = sid
                out['name'] = str(cfg.get('site_name') or '')
                out['ok'] = True
            except Exception:
                pass
            with self._lock:
                self._resolved[k] = out
            return out
        finally:
            lk.release()

    def _prewarm(self):
        def worker(st):
            try:
                self._resolve(st)
            except Exception:
                pass
        try:
            ths = [threading.Thread(target=worker, args=(s,)) for s in self.sites
                   if s.get('family') == 'wieuc']
            for t in ths:
                t.daemon = True
                t.start()
        except Exception:
            for s in self.sites:
                if s.get('family') == 'wieuc':
                    worker(s)

    def site_of(self, key):
        for s in self.sites:
            if s['key'] == key:
                return s
        return None

    def cfg_of(self, st):
        if st.get('family') == 'wieuc':
            return self._resolve(st, nowait=True)
        return {'api': st.get('host'), 'site': 0, 'img': '', 'lines': [], 'ok': True}

    def _static_classes(self):
        cls = [{'type_name': '🔥全站聚合·最新', 'type_id': 'all'},
               {'type_name': '💥全站聚合·热门', 'type_id': 'hots'}]
        for st in self.sites:
            if st.get('family') != 'wieuc':
                continue
            status = self._status.get(st['key'])
            if status == 'ok':
                name = '🟢' + st['name']
            elif status:
                name = '🔴' + st['name'] + ' ' + str(status)[:24]
            else:
                name = st['name']
            cls.append({'type_name': name, 'type_id': st['key']})
        return cls

    def _ensure_filters(self, wait=4):
        if getattr(self, '_flt_done', False):
            return
        if not getattr(self, '_flt_started', False):
            self._flt_started = True
            try:
                threading.Thread(target=self._load_filters, daemon=True).start()
            except Exception:
                self._load_filters()
        t0 = time.time()
        while not getattr(self, '_flt_done', False) and time.time() - t0 < wait:
            time.sleep(0.2)

    def _load_filters(self):
        flt, grp = {}, {}
        lock = threading.Lock()

        def worker(st):
            try:
                cf = self.cfg_of(st)
                items = self._items(self.api_get('/api/vod/tag_group?site_id=%d' % cf['site']))
                vals = []
                for o in items:
                    if not isinstance(o, dict):
                        continue
                    if self._to_int(o.get('purpose')) == 8 or self._to_int(o.get('tag_type'), 1) in (2, 3):
                        continue
                    nm = str(o.get('name') or '').strip()
                    tags = [t for t in (o.get('tag') or []) if isinstance(t, dict) and self._to_int(t.get('id')) > 0]
                    if not nm or not tags:
                        continue
                    gid = 'g%s' % o.get('id')
                    with lock:
                        grp[(st['key'], gid)] = ','.join(str(t['id']) for t in tags)
                    vals.append({'n': '%s · 全部' % nm, 'v': gid})
                    for t in tags[:40]:
                        vals.append({'n': '%s · %s' % (nm, t.get('name') or ''), 'v': 't%s' % t['id']})
                if vals:
                    with lock:
                        flt[st['key']] = [{'key': 'tag', 'name': '分类', 'value': [{'n': '全部', 'v': ''}] + vals}]
            except Exception:
                pass

        try:
            ths = [threading.Thread(target=worker, args=(s,)) for s in self.sites
                   if s.get('family') == 'wieuc']
            for t in ths:
                t.daemon = True
                t.start()
            t_end = time.time() + self.timeout + 6
            for t in ths:
                left = t_end - time.time()
                if left <= 0:
                    break
                t.join(timeout=left)
        except Exception:
            for s in self.sites:
                if s.get('family') == 'wieuc':
                    worker(s)
        with self._lock:
            self._grp = grp
            self._flt = flt
        self._flt_done = True

    def _card(self, st, it, cf):
        if not isinstance(it, dict):
            return None
        vid = str(it.get('id') or '').strip()
        nm = str(it.get('name') or '').strip()
        if not vid or not nm:
            return None
        pic = self._proxy_pic(str(it.get('pic') or ''), st['key'], vid, cf)
        parts = []
        dur = self._to_int(it.get('duration'))
        if dur > 0:
            parts.append('%02d:%02d' % (dur // 60, dur % 60))
        for t in (it.get('tag') or [])[:2]:
            if isinstance(t, dict) and t.get('name'):
                parts.append(str(t['name']))
        if self._to_int(it.get('is_paid')) == 1:
            parts.append('💎')
        parts.append(st['name'])
        return {'vod_id': '%s|%s' % (st['key'], vid), 'vod_name': nm,
                'vod_pic': pic, 'vod_remarks': ' · '.join(parts)}

    def _cards(self, st, r, cf):
        out = []
        for it in self._items(r):
            c = self._card(st, it, cf)
            if c:
                out.append(c)
        return out

    def _list(self, st, tid, page, tag):
        cf = self.cfg_of(st)
        if st.get('family') != 'wieuc':
            self._status[st['key']] = '非本站族'
            return []
        try:
            q = '/api/vod/video?page=%d&per_page=%d&site_id=%d' % (page, PER, cf['site'])
            if tid == 'hot':
                q = '/api/vod/video/top/hits?site_id=%d' % cf['site']
            if tag:
                q += '&tag=' + urllib.parse.quote(str(tag))
            r = self.api_get(q)
            cards = self._cards(st, r, cf)
            if cards:
                self._status[st['key']] = 'ok'
            elif not r:
                self._status[st['key']] = '接口无响应(网络/DNS/证书?)'
            else:
                self._status[st['key']] = '接口无数据'
            return cards
        except Exception as e:
            self._status[st['key']] = '%s:%s' % (type(e).__name__, str(e)[:16])
            return []

    def homeContent(self, filter=False):
        try:
            root = {'class': self._static_classes(), 'list': []}
            if filter:
                self._ensure_filters(wait=2)
                root['filters'] = dict(getattr(self, '_flt', {}) or {})
            try:
                root['list'] = self._mix(1, 30, wait=3)
            except Exception:
                pass
            return root
        except Exception as e:
            return {'class': [{'type_name': '⚠️插件异常 %s %s' % (type(e).__name__, str(e)[:60]),
                               'type_id': '_err'}], 'list': []}

    def _mix(self, page, cap, tid='new', wait=None):
        if wait is None:
            wait = min(self.timeout, 12) + 2
        key = (page, cap, tid)
        now = time.time()
        cached = (getattr(self, '_mix_cache', {}) or {}).get(key)
        if cached and now - cached[0] < 30 and cached[2]:
            return cached[1]
        sts = [s for s in self.sites if s.get('family') == 'wieuc']
        results, lock = {}, threading.Lock()

        def worker(st):
            try:
                cards = self._list(st, tid, page, '')
                with lock:
                    results[st['key']] = cards
            except Exception:
                with lock:
                    results[st['key']] = []

        ths = []
        try:
            ths = [threading.Thread(target=worker, args=(s,)) for s in sts]
            for t in ths:
                t.daemon = True
                t.start()
        except Exception:
            for s in sts:
                worker(s)
            ths = []
        t_end = time.time() + wait
        for t in ths:
            left = t_end - time.time()
            if left <= 0:
                break
            t.join(timeout=left)
        seen, out = set(), []
        for st in sts:
            for c in results.get(st['key'], []):
                if c['vod_name'] in seen:
                    continue
                seen.add(c['vod_name'])
                out.append(c)
                if len(out) >= cap:
                    break
        if len(results) == len(sts):
            with self._lock:
                self._mix_cache = {key: (time.time(), out, True)}
        return out

    def homeVideoContent(self):
        try:
            return {'list': self._mix(1, 30)}
        except Exception:
            return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = max(1, int(str(pg or '1').strip()))
        except Exception:
            page = 1
        tid = str(tid or '')
        tag = ''
        if isinstance(extend, dict):
            v = str(extend.get('tag') or '').strip()
            if v.startswith('t') and len(v) > 1:
                tag = v[1:]
        if tid in ('all', 'hots'):
            out = self._mix(page, 9999, 'hot' if tid == 'hots' else 'new')
            n = len([s for s in self.sites if s.get('family') == 'wieuc'])
            return {'page': page, 'pagecount': 9999 if len(out) >= n * PER else page,
                    'limit': len(out), 'total': 106019 * max(n, 1), 'list': out}
        st = self.site_of(tid)
        if not st:
            return {'page': page, 'pagecount': page, 'limit': 0, 'total': 0, 'list': []}
        if tag and not tag.isdigit():
            tag = self._grp.get((tid, tag), '')
        cf = self.cfg_of(st)
        if st.get('family') == 'wieuc':
            q = '/api/vod/video?page=%d&per_page=%d&site_id=%d' % (page, PER, cf['site'])
            if tag:
                q += '&tag=' + urllib.parse.quote(str(tag))
            r = self.api_get(q)
            lst = self._cards(st, r, cf)
            if not lst and page == 1:
                status = self._status.get(st['key']) or ('接口无响应' if not r else '无数据')
                lst = [{'vod_id': '_err', 'vod_name': '⚠️' + str(status),
                        'vod_pic': '', 'vod_remarks': '网络问题或站点临时故障，稍后重试'}]
            d = self._data(r)
            pages = self._to_int(d.get('pages')) or (page + 1 if len(lst) >= PER else page)
            total = self._to_int(d.get('total')) or len(lst)
            return {'page': page, 'pagecount': min(pages, 5000), 'limit': len(lst), 'total': total, 'list': lst}
        return {'page': page, 'pagecount': page, 'limit': 0, 'total': 0, 'list': []}

    def detailContent(self, ids):
        try:
            target = ''
            if isinstance(ids, (list, tuple)) and ids:
                target = str(ids[0] or '').strip()
            else:
                target = str(ids or '').strip()
            if '|' not in target:
                return {'list': []}
            skey, vid = target.split('|', 1)
            vid = ''.join(c for c in vid if c.isdigit())[:12]
            st = self.site_of(skey)
            if not st or not vid:
                return {'list': []}
            cf = self.cfg_of(st)
            if st.get('family') != 'wieuc':
                return {'list': []}
            d = self._data(self.api_get('/api/vod/video/%s?site_id=%d' % (vid, cf['site'])))
            if not d:
                return {'list': []}
            nm = str(d.get('name') or '').strip() or (st['name'] + ' ' + vid)
            pic = self._proxy_pic(str(d.get('pic') or ''), skey, vid, cf)
            tags = ' '.join('#' + str((t or {}).get('name') or '') for t in (d.get('tag') or [])
                            if isinstance(t, dict) and t.get('name'))
            dur = self._to_int(d.get('duration'))
            play = str(d.get('play_url') or '').strip()
            vod = {'vod_id': target, 'vod_name': nm, 'vod_pic': pic,
                   'vod_remarks': '%s · %s' % (st['name'], st.get('group') or ''),
                   'vod_year': str(d.get('pubdate') or '')[:4],
                   'type_name': tags,
                   'vod_content': ('【站源】阅妹阁聚合 · %s（族：%s）\n'
                                   '【取数】接口信封 Fernet，源内已解；游客身份直取，无登录/会员校验\n'
                                   '【取流】HLS 标准 AES-128（enc.key 明文，非 DRM）\n' % (st['name'], st.get('family'))
                                   + ('【时长】%02d:%02d\n' % (dur // 60, dur % 60) if dur else '')
                                   + ('【标签】%s\n' % tags.strip() if tags.strip() else '')
                                   + ('【简介】%s' % str(d.get('description') or '')))}
            if play:
                froms, urls = [], []
                for i, host in enumerate(cf.get('lines') or LINE_HOST):
                    u = play if play.startswith('http') else ('https://' + host + play)
                    froms.append(LINE_NAME[i] if i < len(LINE_NAME) else ('线路%d' % (i + 1)))
                    urls.append('正片$' + u)
                vod['vod_play_from'] = '$$$'.join(froms)
                vod['vod_play_url'] = '$$$'.join(urls)
            else:
                vod['vod_play_from'] = LINE_NAME[0]
                vod['vod_play_url'] = '暂无$https://' + cf['api'] + '/api/vod/video/' + vid
            return {'list': [vod]}
        except Exception:
            return {'list': []}

    def searchContent(self, key, quick, pg='1'):
        kw = str(key or '').strip()
        if not kw:
            return {'list': []}
        try:
            page = max(1, int(str(pg or '1').strip()))
        except Exception:
            page = 1
        res, seen, tot = [], set(), [0]
        lock = threading.Lock()

        def worker(st):
            try:
                cf = self.cfg_of(st)
                if st.get('family') != 'wieuc':
                    return
                q = '/search/vod/?search=%s&page=%d&per_page=%d&site_id=%d' % (
                    urllib.parse.quote(kw), page, PER, cf['site'])
                r = self.api_get(q)
                t = self._to_int(self._data(r).get('total'))
                with lock:
                    if t > tot[0]:
                        tot[0] = t
                for c in self._cards(st, r, cf):
                    with lock:
                        if c['vod_name'] in seen:
                            continue
                        seen.add(c['vod_name'])
                        res.append(c)
            except Exception:
                pass

        ths = []
        try:
            ths = [threading.Thread(target=worker, args=(s,)) for s in self.sites
                   if s.get('family') == 'wieuc']
            for t in ths:
                t.daemon = True
                t.start()
        except Exception:
            for s in self.sites:
                if s.get('family') == 'wieuc':
                    worker(s)
            ths = []
        t_end = time.time() + self.timeout + 4
        for t in ths:
            left = t_end - time.time()
            if left <= 0:
                break
            t.join(timeout=left)
        if not res and page == 1:
            res = [{'vod_id': '_err', 'vod_name': '⚠️无结果(接口无响应或确无此内容)',
                    'vod_pic': '', 'vod_remarks': '换个关键词试试'}]
        return {'page': page, 'pagecount': page + 1 if len(res) >= PER else page,
                'limit': len(res), 'total': tot[0] or len(res), 'list': res[:120]}

    def fresh_pic(self, skey, vid):
        st = self.site_of(skey)
        if not st or st.get('family') != 'wieuc':
            return ''
        cf = self.cfg_of(st)
        d = self._data(self.api_get('/api/vod/video/%s?site_id=%d' % (str(vid), cf['site'])))
        p = str(d.get('pic') or '')
        if p and not p.startswith('http'):
            p = 'https://' + (cf.get('img') or self.img) + p
        return p

    def playerContent(self, flag, id, vipFlags=None):
        u = str(id or '').strip()
        if '$' in u:
            u = u.split('$')[-1]
        if u.startswith('http'):
            return {'parse': 0, 'playUrl': '', 'url': u,
                    'header': json.dumps({'User-Agent': UA, 'Referer': 'https://' + self.img + '/'})}
        if '|' in u:
            skey, vid = u.split('|', 1)
            st = self.site_of(skey)
            if st and st.get('family') == 'wieuc':
                cf = self.cfg_of(st)
                d = self._data(self.api_get('/api/vod/video/%s?site_id=%d' %
                                            (''.join(c for c in vid if c.isdigit())[:12], cf['site'])))
                p = str(d.get('play_url') or '').strip()
                if p:
                    full = p if p.startswith('http') else ('https://' + cf['lines'][0] + p)
                    return {'parse': 0, 'playUrl': '', 'url': full,
                            'header': json.dumps({'User-Agent': UA, 'Referer': 'https://' + cf['img'] + '/'})}
        return {'parse': 0, 'playUrl': '', 'url': u, 'header': json.dumps({'User-Agent': UA})}

    def localProxy(self, param):
        # FongMi 契约：必须返回 [code, content_type, content, header, base64flag] 列表
        def _fail(code):
            return [code, '', '', None, 0]
        try:
            p = param if isinstance(param, dict) else {}
            if isinstance(param, str):
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(param).query)
                p = {k: v[0] for k, v in qs.items()}
            u = str(p.get('url') or p.get('u') or '')
            sid = str(p.get('s') or '')
            vid = str(p.get('v') or '')
            if not u.startswith('http'):
                return _fail(404)
            raw = self.fetch_bytes(u)
            if not raw and sid and vid:
                fresh = self.fresh_pic(sid, vid)
                if fresh and fresh != u:
                    raw = self.fetch_bytes(fresh)
            mime, img = _unbundle(raw or b'')
            if img is None:
                return _fail(502)
            return [200, mime, 'data:%s;base64,%s' % (mime, base64.b64encode(img).decode('ascii')), None, 1]
        except Exception:
            return _fail(500)
