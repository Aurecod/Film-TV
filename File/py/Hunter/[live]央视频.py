#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
兼容 IJK / ExoPlayer / MPV 三种播放器的 HLS 直播版本:
    - playlist 带 #EXT-X-PROGRAM-DATE-TIME, Exo/MPV 才能定位直播点
    - 带 #EXT-X-START:TIME-OFFSET=-15, 从直播点前 15 秒开始播
    - playlist 窗口 8 片 (~50 秒), 兼顾 IJK 小窗口特性与 Exo 最小窗口要求
    - 分片 URL 指向本地 /chunk/<slug>/<seq>.ts, 由本地实时转发
    - 后台每 2 秒刷新, playlist 请求不触发额外刷新 (避免 media-seq 跳变)
    - 每个频道带台标封面: 自动探测可用图源, 全部失败时由本地 /logo 兜底出图

协议: JCE PidTimeShift + bkliveinfo(cKey) 自动切换
仅标准库。
"""

import base64, gzip, json, os, random, re, struct, threading, time
import urllib.error, urllib.parse, urllib.request, uuid
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    from base.spider import Spider as SpiderBase
except ImportError:
    class SpiderBase(object):
        def getCache(self, key): return None
        def setCache(self, key, value): return "fail"
        def delCache(self, key): return "fail"


def format_remarks(brand="央视频", meta=""):
    clean_meta = str(meta or "").strip()
    clean_meta = re.sub(r"[\r\n\t]+", " ", clean_meta).strip()
    return ("%s | %s" % (brand, clean_meta)) if clean_meta else brand


# ================================================================ JCE 协议

class W:
    def __init__(self): self.b = bytearray()
    def head(self, typ, tag):
        if tag < 15: self.b.append(((tag & 0xf) << 4) | (typ & 0xf))
        else: self.b.append(0xf0 | (typ & 0xf)); self.b.append(tag)
    def byte(self, v, tag):
        v = int(v)
        if v == 0: self.head(12, tag)
        else: self.head(0, tag); self.b += struct.pack('>b', v)
    def short(self, v, tag):
        v = int(v)
        if -128 <= v <= 127: self.byte(v, tag)
        else: self.head(1, tag); self.b += struct.pack('>h', v)
    def int(self, v, tag):
        v = int(v)
        if -32768 <= v <= 32767: self.short(v, tag)
        else: self.head(2, tag); self.b += struct.pack('>i', v)
    def long(self, v, tag):
        v = int(v)
        if -2147483648 <= v <= 2147483647: self.int(v, tag)
        else: self.head(3, tag); self.b += struct.pack('>q', v)
    def float(self, v, tag): self.head(4, tag); self.b += struct.pack('>f', float(v))
    def double(self, v, tag): self.head(5, tag); self.b += struct.pack('>d', float(v))
    def string(self, s, tag):
        if s is None: return
        data = str(s).encode('utf-8')
        if len(data) > 255: self.head(7, tag); self.b += struct.pack('>i', len(data)); self.b += data
        else: self.head(6, tag); self.b.append(len(data)); self.b += data
    def bytes(self, data, tag):
        data = bytes(data); self.head(13, tag); self.head(0, 0); self.int(len(data), 0); self.b += data
    def struct(self, fn, tag): self.head(10, tag); fn(self); self.head(11, 0)
    def list(self, items, tag, wf): self.head(9, tag); self.int(len(items), 0)
    def out(self): return bytes(self.b)


class R:
    def __init__(self, data): self.d = memoryview(data); self.p = 0
    def rem(self): return len(self.d) - self.p
    def get(self, n):
        if self.p + n > len(self.d): raise EOFError
        b = self.d[self.p:self.p + n].tobytes(); self.p += n; return b
    def u8(self): return self.get(1)[0]
    def head(self):
        b = self.u8(); typ = b & 0xf; tag = (b & 0xf0) >> 4
        if tag == 15: tag = self.u8()
        return typ, tag
    def value(self, typ):
        if typ == 0: return struct.unpack('>b', self.get(1))[0]
        if typ == 1: return struct.unpack('>h', self.get(2))[0]
        if typ == 2: return struct.unpack('>i', self.get(4))[0]
        if typ == 3: return struct.unpack('>q', self.get(8))[0]
        if typ == 4: return struct.unpack('>f', self.get(4))[0]
        if typ == 5: return struct.unpack('>d', self.get(8))[0]
        if typ == 6: n = self.u8(); return self.get(n).decode('utf-8', 'replace')
        if typ == 7: n = struct.unpack('>i', self.get(4))[0]; return self.get(n).decode('utf-8', 'replace')
        if typ == 8: n = self._int(); return {self._fv(): self._fv() for _ in range(n)}
        if typ == 9: n = self._int(); return [self._fv() for _ in range(n)]
        if typ == 10: return self.struct()
        if typ == 11: return None
        if typ == 12: return 0
        if typ == 13: t, _ = self.head(); n = self._int(); return self.get(n)
        raise ValueError('type %d' % typ)
    def _fv(self): t, _ = self.head(); return self.value(t)
    def _int(self): t, _ = self.head(); return int(self.value(t))
    def struct(self):
        m = {}
        while self.rem() > 0:
            t, tag = self.head()
            if t == 11: break
            m[tag] = self.value(t)
        return m


VER_NAME, VER_CODE = '3.2.7.26212', '302070'
APP_ID, QMF_APP_ID, QMF_PLATFORM, BIZ_ID = '1200013', 10012, 1, 0
CHAN_ID = '10070'
GUID = ''.join(random.choice('0123456789abcdef') for _ in range(32))


def _qua(w):
    w.string(VER_NAME, 0); w.string(VER_CODE, 1)
    w.int(1080, 2); w.int(2400, 3); w.int(3, 4); w.string('12', 5)
    w.int(1, 6); w.int(1, 7); w.int(420, 8); w.string(CHAN_ID, 9)
    for i in range(10, 15): w.string('', i)
    w.struct(lambda ww: (ww.int(0, 0), ww.byte(0, 1), ww.string('', 2)), 15)
    w.string('', 16); w.string('', 17); w.string('', 18)
    w.struct(lambda ww: (ww.int(0, 0), ww.float(0, 1), ww.float(0, 2), ww.double(0, 3)), 19)
    w.string(GUID[:16], 20); w.string('Pixel 6', 21)
    w.int(1, 22)
    for i in range(23, 27): w.int(0, i)
    w.string('', 27); w.string('', 28); w.string(GUID, 29)


def _head(w, cmd, reqid):
    w.int(reqid, 0); w.int(cmd, 1)
    w.struct(lambda ww: _qua(ww), 2)
    w.string(APP_ID, 3); w.string(GUID, 4)
    w.list([], 5, None); w.struct(lambda ww: None, 6)
    w.list([], 7, None)
    w.int(0, 8); w.int(0, 9); w.int(0, 10)


def _wrap(cmd, body, reqid):
    w = W()
    w.struct(lambda ww: _head(ww, cmd, reqid), 0)
    w.bytes(body, 1)
    reqcmd = w.out()
    inner = bytearray([38]) + struct.pack('>i', len(reqcmd) + 17) + bytes([1]) + b'\x00' * 10 + reqcmd + bytes([40])
    comp = gzip.compress(bytes(inner))
    out = bytearray([19]) + struct.pack('>i', 0) + struct.pack('>H', 2) + struct.pack('>H', 65281)
    out += struct.pack('>H', cmd) + struct.pack('>H', 0) + struct.pack('>q', reqid)
    out += struct.pack('>i', 531) + struct.pack('>i', QMF_APP_ID) + struct.pack('>q', BIZ_ID)
    g = GUID.encode()[:32]; out += g + b'\x00' * (32 - len(g))
    out += struct.pack('>b', QMF_PLATFORM) + struct.pack('>i', int(VER_CODE)) + b'\x00' * 6
    out += bytes([0]) + struct.pack('>H', 0) + struct.pack('>H', 0)
    out += struct.pack('>i', len(inner)) + comp + bytes([3])
    struct.pack_into('>i', out, 1, len(out))
    return bytes(out)


def _unwrap(data):
    if data[:1] != b'\x13' or len(data) < 90: return None
    flags = struct.unpack('>i', data[21:25])[0]
    payload = data[89:-1]
    if flags & 2: payload = gzip.decompress(payload)
    if payload[:1] != b'&' or payload[-1:] != b'(': return None
    rc = R(payload[16:-1]).struct()
    return rc.get(1) or b''


class DeadHostError(RuntimeError):
    pass


def jce_timeshift_url(pid, sid, start, end, stream='fhd'):
    w = W()
    w.string(pid, 0); w.string(sid, 1); w.long(start, 2); w.long(end, 3); w.string(stream, 4)
    body = w.out()
    CMD = 25312
    reqid = int(time.time() * 1000) & 0x7fffffff
    packet = _wrap(CMD, body, reqid)
    req = urllib.request.Request('https://jacc.ysp.cctv.cn', data=packet, method='POST')
    req.add_header('Content-Type', 'application/octet-stream')
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read()
    resp_body = _unwrap(raw)
    if not resp_body: raise RuntimeError('bad response')
    m = R(resp_body).struct()
    err = m.get(0, 0)
    if err != 0: raise RuntimeError(m.get(1, 'errCode=%s' % err))
    url = m.get(2, '')
    if not url: raise RuntimeError('empty m3u8')
    if 'liverecord.video.cloud.cctv.com' in url:
        raise DeadHostError('dead cdn host')
    return url


# ================================================================ cKey + bkliveinfo

_CK_PLATFORM = 4330403
_CK_APPVER = 'V8.22.1035.3031'
_CK_TEA = bytes.fromhex('59b2f7cf725ef43c34fdd7c123411ed3')
_CK_GTEA = bytes.fromhex('110DBEC10C23E7D2E56A1CAD6914EF1B')
_CK_XOR = bytes([0x84, 0x2e, 0xed, 0x08, 0xf0, 0x66, 0xe6, 0xea, 0x48, 0xb4, 0xca, 0xa9, 0x91, 0xed, 0x6f, 0xf3])
_CK_GXOR = bytes([0xb3, 0xc9, 0x53, 0xa0, 0x69, 0x13, 0xad, 0x4d])


def _u32(v): return v & 0xFFFFFFFF


def _tea_blk(blk, key):
    y, z = struct.unpack('>2I', blk)
    k = struct.unpack('>4I', key)
    s = 0
    for _ in range(16):
        s = _u32(s + 0x9e3779b9)
        y = _u32(y + _u32(_u32(_u32(z << 4) + k[0]) ^ _u32(z + s) ^ _u32((z >> 5) + k[1])))
        z = _u32(z + _u32(_u32(_u32(y << 4) + k[2]) ^ _u32(y + s) ^ _u32((y >> 5) + k[3])))
    return struct.pack('>2I', y, z)


def _cksum(buf):
    v = 0
    for b in buf: v = (0x83 * v + b) & 0x7fffffff
    return v


def _tea_pkt(data, key):
    pad = (8 - ((len(data) + 10) % 8)) % 8
    plain = bytes([(os.urandom(1)[0] & 0xf8) | pad]) + os.urandom(pad) + os.urandom(2) + data + bytes(7)
    out, pp, pc = b'', bytes(8), bytes(8)
    for off in range(0, len(plain), 8):
        mixed = bytes(a ^ b for a, b in zip(plain[off:off + 8], pc))
        enc = _tea_blk(mixed, key)
        cipher = bytes(a ^ b for a, b in zip(enc, pp))
        out += cipher
        pp, pc = mixed, cipher
    return out


def _lp(s):
    d = s.encode() if isinstance(s, str) else s
    return struct.pack('>H', len(d)) + d


def _ck_guard(ts, guid):
    def tail(v):
        t = str(v); return t[-5:] if len(t) >= 5 else ''
    body = struct.pack('>I', ts) + _lp(tail(guid)) + _lp(tail('null')) + _lp(tail('null')) + _lp('-1')
    plain = _lp(body)
    enc = _tea_pkt(plain, _CK_GTEA) + struct.pack('>I', _cksum(plain))
    enc = bytes(a ^ _CK_GXOR[i & 7] for i, a in enumerate(enc))
    return enc.hex().upper()


def _ckey(channel_id):
    ts = int(time.time())
    guid = os.urandom(16).hex()
    guard = _ck_guard(ts, guid)
    uid = os.urandom(4).hex().upper()
    body = (bytes.fromhex('0000004200000004000004d2') + struct.pack('>I', _CK_PLATFORM)
            + struct.pack('>I', 0) + struct.pack('>I', ts) + _lp('dcgh')
            + _lp('_zj1A5Gh6QYcxWjIUGos2w==') + _lp(_CK_APPVER) + _lp(str(channel_id))
            + _lp(guid) + struct.pack('>I', 1) + struct.pack('>I', 1) + _lp(uid) + _lp('nil')
            + _lp('57eab0c4-2c58-44c6-8ae9-dd2757525dc5') + _lp('nil') + _lp('v0.1.000')
            + _lp('com.cctv.yangshipin.app.iphone') + _lp(str(_CK_PLATFORM))
            + _lp('ex_json_bus') + _lp('ex_json_vs') + _lp(guard))
    pkt = bytearray(struct.pack('>H', len(body)) + body)
    pkt[18:22] = struct.pack('>I', _cksum(bytes(pkt)))
    pkt = bytes(pkt)
    enc = _tea_pkt(pkt, _CK_TEA) + struct.pack('>I', _cksum(pkt))
    enc = bytes(a ^ _CK_XOR[i & 15] for i, a in enumerate(enc))
    b64 = base64.b64encode(enc).decode().replace('+', '_').replace('/', '-').rstrip('=')
    return {'cKey': '--01' + b64, 'guid': guid, 'ts': ts,
            'flowId': '%s_%d' % (uuid.uuid4().hex.upper(), _CK_PLATFORM)}


_BK_H264 = base64.b64encode(b'H(30:1080,60:1080|30:1080,60:1080)').decode()


def bk_playurls(channel_id, live_pid, defn='fhd'):
    t = _ckey(channel_id)
    q = urllib.parse.urlencode({
        'atime': '120', 'livepid': live_pid, 'cnlid': channel_id,
        'appVer': _CK_APPVER, 'app_version': '300090', 'caplv': '1', 'cmd': '2',
        'defn': defn, 'device': 'iPhone', 'encryptVer': '4.2', 'getpreviewinfo': '0',
        'hevclv': '0', 'lang': 'zh-Hans_CN', 'livequeue': '0', 'logintype': '1',
        'nettype': '1', 'newnettype': '1', 'newplatform': str(_CK_PLATFORM),
        'platform': str(_CK_PLATFORM), 'sdtfrom': 'v3021', 'spacode': '23',
        'spaudio': '1', 'spdemuxer': '6', 'spdrm': '2', 'spdynamicrange': '1',
        'spflv': '1', 'spflvaudio': '1', 'sphdrfps': '60', 'sphttps': '1',
        'spvcode': _BK_H264, 'spvideo': '4', 'stream': '1', 'system': '1',
        'sysver': 'ios18.2.1', 'uhd_flag': '0', 'cKey': t['cKey'], 'guid': t['guid'],
        'fntick': str(t['ts']), 'flowid': t['flowId'], 'playbacktime': '0',
    })
    req = urllib.request.Request('https://bkliveinfo.ysp.cctv.cn/?' + q,
                                 headers={'User-Agent': 'qqlive', 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=15) as r:
        p = json.loads(r.read().decode())
    if int(p.get('iretcode', -1)) != 0:
        raise RuntimeError('iretcode=%s %s' % (p.get('iretcode'), p.get('errinfo', '')))
    urls = []
    if p.get('playurl'): urls.append(p['playurl'])
    bu = p.get('backurl_list') or p.get('backurlList') or p.get('backurl')
    if isinstance(bu, list):
        for it in bu: urls.append(it if isinstance(it, str) else (it.get('url') or it.get('playurl') or ''))
    elif isinstance(bu, str):
        urls += [x for x in re.split(r'[;,]', bu) if x.strip()]
    urls = [u for u in dict.fromkeys(urls) if u and '.cctv.' in u]
    if not urls: raise RuntimeError('no playurl')
    urls.sort(key=lambda u: (0 if 'bklive-' in u else 1, u))
    return urls


# ================================================================ 频道表

CHANNELS = [
    ('cctv1', 'CCTV-1', '2024078201', '600001859', 'fhd'),
    ('cctv2', 'CCTV-2', '2024075401', '600001800', 'fhd'),
    ('cctv3', 'CCTV-3', '2024068501', '600001801', 'fhd'),
    ('cctv4', 'CCTV-4', '2029797101', '600001814', 'fhd'),
    ('cctv5', 'CCTV-5', '2024078401', '600001818', 'fhd'),
    ('cctv5p', 'CCTV-5+', '2024078001', '600001817', 'fhd'),
    ('cctv6', 'CCTV-6', '2013693901', '600108442', 'fhd'),
    ('cctv7', 'CCTV-7', '2024072001', '600004092', 'fhd'),
    ('cctv8', 'CCTV-8', '2029793001', '600001803', 'fhd'),
    ('cctv9', 'CCTV-9', '2024078601', '600004078', 'fhd'),
    ('cctv10', 'CCTV-10', '2024078701', '600001805', 'fhd'),
    ('cctv11', 'CCTV-11', '2027248701', '600001806', 'fhd'),
    ('cctv12', 'CCTV-12', '2027248801', '600001807', 'fhd'),
    ('cctv13', 'CCTV-13', '2029797201', '600001811', 'fhd'),
    ('cctv14', 'CCTV-14', '2027248901', '600001809', 'fhd'),
    ('cctv15', 'CCTV-15', '2027249001', '600001815', 'fhd'),
    ('cctv16', 'CCTV-16', '2027249101', '600098637', 'fhd'),
    ('cctv164k', 'CCTV-16 4K', '2027249301', '600099502', 'fhd'),
    ('cctv17', 'CCTV-17', '2027249401', '600001810', 'fhd'),
    ('cctv4k', 'CCTV-4K', '2029810301', '600002264', 'fhd'),
    ('cctv8k', 'CCTV-8K', '2026774101', '600156816', 'fhd'),
    ('cgtn', 'CGTN', '2024181701', '600014550', 'fhd'),
    ('cgtnfr', 'CGTN法语', '2024181801', '600084704', 'fhd'),
    ('cgtnru', 'CGTN俄语', '2024181901', '600084758', 'fhd'),
    ('cgtnar', 'CGTN阿拉伯语', '2024182001', '600084782', 'fhd'),
    ('cgtnes', 'CGTN西班牙语', '2024182101', '600084744', 'fhd'),
    ('cgtndoc', 'CGTN 纪录', '2024182301', '600084781', 'fhd'),
    ('cctvfyjc', 'CCTV 风云剧场', '2025637103', '600099658', 'shd'),
    ('cctvdyjc', 'CCTV 第一剧场', '2026874203', '600099655', 'shd'),
    ('cctvhjjc', 'CCTV 怀旧剧场', '2026874303', '600099620', 'shd'),
    ('bjws', '北京卫视', '2024052703', '600002309', 'fhd'),
    ('jsws', '江苏卫视', '2024171103', '600002521', 'fhd'),
    ('dfws', '东方卫视', '2024054503', '600002483', 'fhd'),
    ('zjws', '浙江卫视', '2024054703', '600002520', 'fhd'),
    ('hnws', '湖南卫视', '2024054803', '600002475', 'fhd'),
    ('hbws', '湖北卫视', '2024171203', '600002508', 'fhd'),
    ('gdws', '广东卫视', '2024060903', '600002485', 'fhd'),
    ('gxws', '广西卫视', '2024060703', '600002509', 'fhd'),
    ('hljws', '黑龙江卫视', '2029797003', '600002498', 'fhd'),
    ('hainanws', '海南卫视', '2024055603', '600002506', 'fhd'),
    ('cqws', '重庆卫视', '2024061103', '600002531', 'fhd'),
    ('szws', '深圳卫视', '2024061303', '600002481', 'fhd'),
    ('scws', '四川卫视', '2024061403', '600002516', 'fhd'),
    ('henanws', '河南卫视', '2029797303', '600002525', 'fhd'),
    ('dnws', '东南卫视', '2024061503', '600002484', 'fhd'),
    ('gzws', '贵州卫视', '2024061603', '600002490', 'fhd'),
    ('jxws', '江西卫视', '2024061703', '600002503', 'fhd'),
    ('lnws', '辽宁卫视', '2024171303', '600002505', 'fhd'),
    ('ahws', '安徽卫视', '2024171403', '600002532', 'fhd'),
    ('hebws', '河北卫视', '2024171503', '600002493', 'fhd'),
    ('sdws', '山东卫视', '2029787903', '600002513', 'fhd'),
    ('tjws', '天津卫视', '2019927003', '600152137', 'fhd'),
    ('jlws', '吉林卫视', '2025561503', '600190405', 'fhd'),
    ('saxws', '陕西卫视', '2029795103', '600190400', 'fhd'),
    ('nxws', '宁夏卫视', '2025608503', '600190737', 'fhd'),
    ('nmgws', '内蒙古卫视', '2025561203', '600190401', 'fhd'),
    ('ynws', '云南卫视', '2025561303', '600190402', 'fhd'),
    ('shanxiws', '山西卫视', '2025560803', '600190407', 'fhd'),
    ('qhws', '青海卫视', '2025559103', '600190406', 'fhd'),
    ('xizangws', '西藏卫视', '2025558003', '600190403', 'fhd'),
    ('xjws', '新疆卫视', '2019927403', '600152138', 'fhd'),
    ('cetv1', 'CETV-1', '2022823801', '600171827', 'fhd'),
    ('guoxue', '国学频道', '2029360403', '600213139', 'fhd'),
]

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'

WINDOW = 300
REFRESH_INTERVAL = 2
IDLE_TIMEOUT = 300
MAX_SEGS = 400
PLAYLIST_WINDOW = 8               # 8 片 (~50 秒), 兼顾 IJK 与 Exo/MPV
LOCAL_PORT_PREFERRED = 19876
LOCAL_PORT_RANGE = 50

CHANNEL_MAP = {c[0]: {'slug': c[0], 'name': c[1], 'sid': c[2], 'pid': c[3], 'defn': c[4]} for c in CHANNELS}

FORCE_BK = {'cctv11', 'cctv12', 'cctv14', 'cctv15', 'cctv16', 'cctv164k',
            'cctv17', 'cctv4k', 'cctvfyjc', 'cctvdyjc', 'cctvhjjc'}

BACKEND_CHANNELS = {
    'cctv1', 'cctv2', 'cctv3', 'cctv4', 'cctv5', 'cctv5p',
    'cctv7', 'cctv8', 'cctv9', 'cctv10', 'cctv11', 'cctv12',
    'cctv13', 'cctv14', 'cctv15', 'cctv16', 'cctv17',
    'cctv4k', 'cctv8k', 'cctv164k',
    'cgtn', 'cgtnfr', 'cgtnru', 'cgtnar', 'cgtnes', 'cgtndoc',
}

TRUE_4K_CHANNELS = {'cctv4k', 'cctv8k', 'cctv164k'}


# ================================================================ 频道台标 / 封面

# 台标图源 (fanmingming/live 仓库 tv/ 目录的多个镜像), 按顺序探测取第一个可用
LOGO_MIRRORS = [
    'https://cdn.jsdmirror.com/gh/fanmingming/live@main/tv/',
    'https://jsd.onmicrosoft.cn/gh/fanmingming/live@main/tv/',
    'https://gcore.jsdelivr.net/gh/fanmingming/live@main/tv/',
    'https://cdn.jsdelivr.net/gh/fanmingming/live@main/tv/',
    'https://ghproxy.net/https://raw.githubusercontent.com/fanmingming/live/main/tv/',
    'https://live.fanmingming.com/tv/',
]
LOGO_PROBE_FILE = 'CCTV1.png'      # 用于探测图源是否可用的样本文件
LOGO_TIMEOUT = 8                   # 单次请求超时 (秒)
LOGO_MODE = 'auto'                 # auto: 直链优先, 图源全挂则回落到本地出图; 也可强制 'direct' / 'local'

_LOGO_BASE = LOGO_MIRRORS[0]       # 探测完成前先用第一个镜像
_LOGO_DONE = threading.Event()
_LOGO_START_LOCK = threading.Lock()
_LOGO_STARTED = False
_LOGO_CACHE = {}                   # slug -> PNG bytes (本地出图缓存)
_LOGO_CACHE_LOCK = threading.Lock()

# 兜底封面: 320x180 PNG, 任何图源都取不到时使用, 保证卡片一定有封面
_LOGO_PLACEHOLDER = base64.b64decode((
    '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'))

# 仓库文件名与频道 slug 无法直接推导的, 在这里显式指定
_LOGO_OVERRIDE = {
    'cctv5p': 'CCTV5+.png',
    'cctv4k': 'CCTV4K.png',
    'cctv8k': 'CCTV8K.png',
    'cctv164k': 'CCTV16.png',        # 仓库无 "CCTV16 4K", 用 CCTV16 台标
    'cgtn': 'CGTN.png',
    'cgtnfr': 'CGTN法语.png',
    'cgtnru': 'CGTN俄语.png',
    'cgtnar': 'CGTN阿语.png',
    'cgtnes': 'CGTN西语.png',
    'cgtndoc': 'CGTN纪录.png',
    'cctvfyjc': '风云剧场.png',
    'cctvdyjc': '第一剧场.png',
    'cctvhjjc': '怀旧剧场.png',
    'cetv1': 'CETV1.png',
    'guoxue': '国学.png',
}


def _logo_file(slug, name=''):
    """slug -> 台标文件名, 找不到返回空串"""
    if slug in _LOGO_OVERRIDE:
        return _LOGO_OVERRIDE[slug]
    m = re.match(r'^cctv(\d+)$', slug)
    if m:
        return 'CCTV%s.png' % m.group(1)
    if name and slug.endswith('ws'):
        return name + '.png'          # 地方卫视: 仓库文件名就是频道中文名
    return ''


def _probe_logo_source():
    global _LOGO_BASE
    try:
        for base in LOGO_MIRRORS:
            try:
                req = urllib.request.Request(base + LOGO_PROBE_FILE, headers={
                    'User-Agent': UA, 'Referer': 'https://live.cctv.cn/'})
                with urllib.request.urlopen(req, timeout=LOGO_TIMEOUT) as r:
                    head = r.read(16)
                if head[:4] == b'\x89PNG':
                    _LOGO_BASE = base
                    _log('台标源: %s' % base)
                    return
            except Exception:
                continue
        _LOGO_BASE = ''
        _log('台标源全部不可用, 封面回落到本地出图')
    finally:
        _LOGO_DONE.set()


def _ensure_logo_source(wait=3.0):
    """启动一次图源探测, 最多等 wait 秒; 返回当前可用图源前缀 (空串表示都不可用)"""
    global _LOGO_STARTED
    with _LOGO_START_LOCK:
        if not _LOGO_STARTED:
            _LOGO_STARTED = True
            threading.Thread(target=_probe_logo_source, daemon=True).start()
    _LOGO_DONE.wait(wait)
    return _LOGO_BASE


def _local_logo_url(slug):
    port = _LOCAL_PORT
    return 'http://127.0.0.1:%d/logo/%s.png' % (port, slug) if port else ''


def _logo_url(slug, name=''):
    """返回可直接放进 vod_pic 的封面地址"""
    base = _ensure_logo_source()
    fname = _logo_file(slug, name)
    direct = (base + urllib.parse.quote(fname)) if (base and fname) else ''
    if LOGO_MODE == 'direct':
        return direct or _local_logo_url(slug)
    if LOGO_MODE == 'local':
        return _local_logo_url(slug) or direct
    return direct or _local_logo_url(slug)


def _fetch_logo_bytes(slug, name):
    """本地出图: 依次尝试各镜像抓台标, 全失败返回内置兜底封面"""
    fname = _logo_file(slug, name)
    if fname:
        bases = ([_LOGO_BASE] if _LOGO_BASE else []) + [b for b in LOGO_MIRRORS if b != _LOGO_BASE]
        q = urllib.parse.quote(fname)
        for base in bases:
            try:
                req = urllib.request.Request(base + q, headers={
                    'User-Agent': UA, 'Referer': 'https://live.cctv.cn/'})
                with urllib.request.urlopen(req, timeout=LOGO_TIMEOUT) as r:
                    data = r.read()
                if data[:4] == b'\x89PNG':
                    return data
            except Exception:
                continue
    return _LOGO_PLACEHOLDER


# ================================================================ 活流状态

class _ChannelState:
    def __init__(self, slug, name, sid, pid, defn):
        self.slug = slug
        self.name = name
        self.sid = sid
        self.pid = pid
        self.defn = defn
        self.lock = threading.Lock()
        self.segments = {}
        self.order = deque()
        self.seq = 0
        self.last_access = 0.0
        self.thread = None
        self.last_error = ''
        self.mode = 'bk' if slug in FORCE_BK else 'jce'
        self._starting = False


CHANNEL_STATE = {c[0]: _ChannelState(c[0], c[1], c[2], c[3], c[4]) for c in CHANNELS}


def _log(msg):
    try:
        print('[ysp] %s' % msg, flush=True)
    except Exception:
        pass


def _seg_key(url, pdt):
    if pdt:
        return 'pdt:' + pdt
    p = urllib.parse.urlsplit(url)
    return p.scheme + '://' + p.netloc + p.path


def _append_segments(ch, segs):
    with ch.lock:
        for dur, pdt, url in segs:
            key = _seg_key(url, pdt)
            if key in ch.segments:
                ch.segments[key][3] = url
                continue
            ch.seq += 1
            ch.segments[key] = [ch.seq, dur, pdt, url]
            ch.order.append(key)
        while len(ch.order) > MAX_SEGS:
            ch.segments.pop(ch.order.popleft(), None)
        ch.last_error = ''


def _parse_m3u8(text, base_url):
    segs, dur, pdt = [], 6.0, ''
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('#EXTINF:'):
            try:
                dur = float(line[len('#EXTINF:'):].split(',')[0])
            except ValueError:
                dur = 6.0
        elif line.startswith('#EXT-X-PROGRAM-DATE-TIME:'):
            pdt = line[len('#EXT-X-PROGRAM-DATE-TIME:'):]
        elif line and not line.startswith('#'):
            segs.append((dur, pdt, urllib.parse.urljoin(base_url, line)))
            pdt = ''
    return segs


def _jce_refresh(ch):
    now = int(time.time())
    m3u8_url = jce_timeshift_url(ch.pid, ch.sid, now - WINDOW, now, ch.defn)
    req = urllib.request.Request(m3u8_url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        text = r.read().decode('utf-8', 'replace')
    segs = _parse_m3u8(text, m3u8_url)
    if not segs:
        raise RuntimeError('empty playlist')
    _append_segments(ch, segs)
    return True


def _bk_refresh(ch):
    urls = bk_playurls(ch.sid, ch.pid, ch.defn)
    last_err = ''
    for u in urls:
        try:
            req = urllib.request.Request(u, headers={
                'User-Agent': UA,
                'Referer': 'https://live.cctv.cn/',
                'Accept': 'application/vnd.apple.mpegurl,application/json,*/*',
            })
            with urllib.request.urlopen(req, timeout=20) as r:
                text = r.read().decode('utf-8', 'replace')
                final = r.geturl()
            lines = text.splitlines()
            for i, ln in enumerate(lines):
                if ln.strip().startswith('#EXT-X-STREAM-INF'):
                    for j in range(i + 1, len(lines)):
                        s = lines[j].strip()
                        if s and not s.startswith('#'):
                            sub = urllib.parse.urljoin(final, s)
                            req2 = urllib.request.Request(sub, headers={'User-Agent': UA})
                            with urllib.request.urlopen(req2, timeout=20) as r2:
                                text = r2.read().decode('utf-8', 'replace')
                                final = r2.geturl()
                            break
                    break
            segs = _parse_m3u8(text, final)
            if segs:
                _append_segments(ch, segs)
                return True
        except Exception as e:
            last_err = '%s: %s' % (type(e).__name__, e)
            continue
    raise RuntimeError(last_err or 'bk playlist failed')


def _refresh_once(ch):
    try:
        if ch.mode == 'bk':
            return _bk_refresh(ch)
        try:
            return _jce_refresh(ch)
        except DeadHostError:
            ch.mode = 'bk'
            _log('%s JCE 坏域名, 切换 bkliveinfo' % ch.slug)
            return _bk_refresh(ch)
    except Exception as e:
        ch.last_error = ('%s: %s' % (type(e).__name__, e))[:120]
        return False


def _refresh_loop(ch):
    fails = 0
    while time.time() - ch.last_access < IDLE_TIMEOUT:
        ok = _refresh_once(ch)
        fails = 0 if ok else fails + 1
        time.sleep(REFRESH_INTERVAL if fails < 3 else 15)


def _ensure_channel(ch):
    ch.last_access = time.time()
    with ch.lock:
        if ch._starting:
            return
        need_fetch = not ch.segments
        need_thread = ch.thread is None or not ch.thread.is_alive()
        if need_fetch or need_thread:
            ch._starting = True
        else:
            return
    try:
        if need_fetch:
            _refresh_once(ch)
        if need_thread:
            ch.thread = threading.Thread(target=_refresh_loop, args=(ch,), daemon=True)
            ch.thread.start()
    finally:
        with ch.lock:
            ch._starting = False


# ================================================================ 本地 HTTP 服务

_LOCAL_PORT = None
_LOCAL_LOCK = threading.Lock()


class _LocalHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'ysp-live-spider'

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype='text/plain; charset=utf-8', extra=None, cache=False):
        data = body.encode('utf-8') if isinstance(body, str) else body
        try:
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Access-Control-Allow-Origin', '*')
            if cache:
                self.send_header('Cache-Control', 'public, max-age=86400')
            else:
                self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
                self.send_header('Pragma', 'no-cache')
                self.send_header('Expires', '0')
            if extra:
                for k, v in extra.items():
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def do_HEAD(self):
        path = urllib.parse.urlparse(self.path).path
        m = re.match(r'^/([\w]+)\.m3u8$', path)
        if m:
            self.send_response(200)
            self.send_header('Content-Type', 'application/vnd.apple.mpegurl')
            self.send_header('Cache-Control', 'no-cache, no-store')
            self.end_headers()
            return
        m = re.match(r'^/([\w]+)\.ts$', path)
        if m:
            self.send_response(200)
            self.send_header('Content-Type', 'video/mp2t')
            self.send_header('Cache-Control', 'no-cache, no-store')
            self.end_headers()
            return
        m = re.match(r'^/logo/([\w]+)\.png$', path)
        if m:
            self.send_response(200 if m.group(1) in CHANNEL_MAP else 404)
            self.send_header('Content-Type', 'image/png')
            self.send_header('Cache-Control', 'public, max-age=86400')
            self.end_headers()
            return
        self.send_response(404)
        self.end_headers()

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path

        if path == '/health':
            self._send(200, 'ok')
            return
        if path == '/diag':
            lines = []
            for slug, ch in CHANNEL_STATE.items():
                with ch.lock:
                    n = len(ch.order)
                lines.append('%s mode=%s segs=%d err=%s' % (slug, ch.mode, n, ch.last_error))
            lines.append('logo_source=%s' % (_LOGO_BASE or '(none)'))
            self._send(200, '\n'.join(lines) + '\n')
            return

        m = re.match(r'^/logo/([\w]+)\.png$', path)
        if m:
            self._serve_logo(m.group(1))
            return

        m = re.match(r'^/([\w]+)\.m3u8$', path)
        if m:
            self._serve_m3u8(m.group(1))
            return

        m = re.match(r'^/([\w]+)\.ts$', path)
        if m:
            self._serve_ts(m.group(1))
            return

        m = re.match(r'^/chunk/([\w]+)/(\d+)\.ts$', path)
        if m:
            self._serve_chunk(m.group(1), int(m.group(2)))
            return

        self._send(404, 'not found\n')

    # ---------- 台标 / 封面 ----------

    def _serve_logo(self, slug):
        info = CHANNEL_MAP.get(slug)
        if not info:
            self._send(404, 'unknown channel\n')
            return
        with _LOGO_CACHE_LOCK:
            data = _LOGO_CACHE.get(slug)
        if data is None:
            data = _fetch_logo_bytes(slug, info['name'])
            with _LOGO_CACHE_LOCK:
                _LOGO_CACHE[slug] = data
        self._send(200, data, 'image/png', cache=True)

    # ---------- HLS playlist ----------

    def _serve_m3u8(self, slug):
        ch = CHANNEL_STATE.get(slug)
        if not ch:
            self._send(404, 'unknown channel\n')
            return
        _ensure_channel(ch)

        # ★ 不在请求时刷新, 由后台线程负责, 避免 media-seq 跳变
        #   但也等待后台线程至少跑过一次, 保证有分片
        for _ in range(60):
            with ch.lock:
                if ch.order:
                    break
            time.sleep(0.2)

        with ch.lock:
            keys = list(ch.order)
            segs = [ch.segments[k] for k in keys if k in ch.segments]
            window = segs[-PLAYLIST_WINDOW:] if segs else []

        if not window:
            self._send(503, 'no data: %s\n' % (ch.last_error or 'fetching'))
            return

        ch.last_access = time.time()
        port = _LOCAL_PORT
        target = max(6, int(max(s[1] for s in window) + 0.5))

        out = [
            '#EXTM3U',
            '#EXT-X-VERSION:3',
            '#EXT-X-PLAYLIST-TYPE:EVENT',
            '#EXT-X-TARGETDURATION:%d' % target,
            '#EXT-X-MEDIA-SEQUENCE:%d' % window[0][0],
            '#EXT-X-DISCONTINUITY-SEQUENCE:0',
            '#EXT-X-START:TIME-OFFSET=-15.0',   # ★ 从直播点前 15 秒开始 (Exo/MPV)
        ]
        for seq, dur, pdt, _url in window:
            if pdt:
                out.append('#EXT-X-PROGRAM-DATE-TIME:' + pdt)   # ★ 加回 PDT
            out.append('#EXTINF:%.3f,' % dur)
            out.append('http://127.0.0.1:%d/chunk/%s/%d.ts' % (port, slug, seq))

        self._send(200, '\n'.join(out) + '\n', 'application/vnd.apple.mpegurl')

    # ---------- 分片转发 ----------

    def _serve_chunk(self, slug, seq):
        ch = CHANNEL_STATE.get(slug)
        if not ch:
            self._send(404, 'unknown\n')
            return

        ch.last_access = time.time()

        with ch.lock:
            url = None
            for k in ch.order:
                s = ch.segments.get(k)
                if s and s[0] == seq:
                    url = s[3]
                    break

        if not url:
            self._send(404, 'chunk expired\n')
            return

        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': UA,
                'Referer': 'https://live.cctv.cn/',
            })
            with urllib.request.urlopen(req, timeout=15) as r:
                body = r.read()
            self._send(200, body, 'video/mp2t')
        except urllib.error.HTTPError as e:
            self._send(e.code, 'chunk HTTP %d\n' % e.code)
        except Exception as e:
            self._send(502, 'chunk error: %s\n' % e)

    # ---------- TS 无限流中继 (备用) ----------

    def _serve_ts(self, slug):
        ch = CHANNEL_STATE.get(slug)
        if not ch:
            self._send(404, 'unknown\n')
            return
        _ensure_channel(ch)

        for _ in range(60):
            with ch.lock:
                if ch.order:
                    break
            time.sleep(0.25)
        else:
            self._send(503, 'no data\n')
            return

        try:
            self.send_response(200)
            self.send_header('Content-Type', 'video/mp2t')
            self.send_header('Transfer-Encoding', 'chunked')
            self.send_header('Cache-Control', 'no-cache, no-store')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
        except (BrokenPipeError, ConnectionResetError):
            return

        try:
            self.connection.settimeout(120)
        except Exception:
            pass

        def _write_chunk(data):
            if not data:
                return
            self.wfile.write(('%x\r\n' % len(data)).encode('ascii'))
            self.wfile.write(data)
            self.wfile.write(b'\r\n')

        with ch.lock:
            keys = list(ch.order)
            start_keys = keys[-2:] if len(keys) > 2 else keys
            start_segs = [(ch.segments[k][0], ch.segments[k][3]) for k in start_keys if k in ch.segments]
        last_seq = (min(s[0] for s in start_segs) - 1) if start_segs else 0

        empty = 0
        fail = 0
        try:
            while True:
                with ch.lock:
                    cur = [(s[0], s[3]) for k in ch.order
                           for s in [ch.segments.get(k)] if s and s[0] > last_seq]
                cur.sort(key=lambda x: x[0])
                if not cur:
                    empty += 1
                    if empty > 600:
                        break
                    time.sleep(0.3)
                    continue
                empty = 0
                for seq, url in cur:
                    try:
                        req = urllib.request.Request(url, headers={
                            'User-Agent': UA,
                            'Referer': 'https://live.cctv.cn/',
                        })
                        with urllib.request.urlopen(req, timeout=15) as r:
                            while True:
                                chunk = r.read(64 * 1024)
                                if not chunk:
                                    break
                                _write_chunk(chunk)
                        self.wfile.flush()
                        last_seq = seq
                        ch.last_access = time.time()
                        fail = 0
                    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                        return
                    except Exception:
                        fail += 1
                        last_seq = seq
                        if fail > 20:
                            return
                time.sleep(0.1)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        except Exception as e:
            _log('%s ts err %s' % (ch.slug, e))


def _ensure_local_server():
    global _LOCAL_PORT
    with _LOCAL_LOCK:
        if _LOCAL_PORT is not None:
            return _LOCAL_PORT
        ports = list(range(LOCAL_PORT_PREFERRED, LOCAL_PORT_PREFERRED + LOCAL_PORT_RANGE)) + [0]
        last_err = None
        for port in ports:
            try:
                srv = ThreadingHTTPServer(('127.0.0.1', port), _LocalHandler)
                srv.daemon_threads = True
                _LOCAL_PORT = srv.server_address[1]
                threading.Thread(target=srv.serve_forever, daemon=True).start()
                _log('本地服务已启动: http://127.0.0.1:%d/' % _LOCAL_PORT)
                return _LOCAL_PORT
            except OSError as e:
                last_err = e
                continue
        raise RuntimeError('无法绑定端口: %s' % last_err)


# ================================================================ Spider

class Spider(SpiderBase):
    def __init__(self):
        super(Spider, self).__init__()
        self.brandActor = "📺 央视频直播"
        self.brandDirector = "ysp-live"

    def init(self, extend=""):
        try:
            _ensure_local_server()
        except Exception as e:
            _log('本地服务启动失败: %s' % e)
        try:
            _ensure_logo_source(wait=0)   # 后台探测台标图源, 不阻塞
        except Exception:
            pass
        return True

    def getName(self): return "央视频直播"
    def isVideoFormat(self, url): return True
    def manualVideoCheck(self): return False
    def destroy(self): pass

    def homeContent(self, filter):
        return {"class": [
            {"type_name": "央视频道", "type_id": "cctv"},
            {"type_name": "卫视频道", "type_id": "satellite"},
            {"type_name": "CGTN",     "type_id": "cgtn"},
            {"type_name": "4K超清",    "type_id": "4k"},
            {"type_name": "付费剧场",  "type_id": "premium"},
            {"type_name": "其他",      "type_id": "other"},
        ], "filters": {}}

    def homeVideoContent(self): return {"list": []}

    def _classify(self, slug):
        cats = []
        if (re.match(r'^cctv\d', slug) or slug == 'cctv5p') and slug not in TRUE_4K_CHANNELS:
            cats.append('cctv')
        if slug in TRUE_4K_CHANNELS:
            cats.append('4k')
        if slug in ('cctvfyjc', 'cctvdyjc', 'cctvhjjc'):
            cats.append('premium')
        if slug.endswith('ws') or slug == 'cetv1':
            cats.append('satellite')
        if slug.startswith('cgtn'):
            cats.append('cgtn')
        if slug == 'guoxue':
            cats.append('other')
        return cats

    def _make_card(self, slug, name):
        tag = ''
        if slug in TRUE_4K_CHANNELS:
            tag = '真4K'
        elif slug in BACKEND_CHANNELS:
            tag = '高码率'
        return {"vod_id": slug, "vod_name": name, "vod_pic": _logo_url(slug, name),
                "vod_remarks": format_remarks("央视频", tag),
                "style": {"type": "rect", "ratio": 1.78}}

    def categoryContent(self, tid, pg, filter, extend):
        cards = [self._make_card(s, n) for s, n, _s, _p, _d in CHANNELS if tid in self._classify(s)]
        return {"page": 1, "pagecount": 1, "limit": len(cards), "total": len(cards), "list": cards}

    def detailContent(self, ids):
        slug = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        info = CHANNEL_MAP.get(slug)
        if not info:
            return {"list": []}
        try:
            _ensure_local_server()
            ch = CHANNEL_STATE.get(slug)
            if ch:
                _ensure_channel(ch)
        except Exception:
            pass
        full_desc = "【📺 央视频直播】\n频道: %s\nHLS 直播, 本地分片转发。" % info['name']
        escaped_desc = (full_desc.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        vod = {"vod_id": slug, "vod_name": info['name'], "vod_pic": _logo_url(slug, info['name']),
               "vod_actor": self.brandActor, "vod_director": self.brandDirector,
               "vod_remarks": format_remarks("央视频", "直播"),
               "vod_content": escaped_desc,
               "vod_play_from": "央视频",
               "vod_play_url": "超清$%s" % slug}
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        del flag, vipFlags
        slug = str(id).strip()
        if slug.startswith('http://') or slug.startswith('https://'):
            return {"parse": 0, "playUrl": "", "url": slug,
                    "header": {"User-Agent": UA, "Referer": "https://live.cctv.cn/"}}
        if slug not in CHANNEL_STATE:
            return {"parse": 0, "playUrl": "", "url": "", "header": {}}

        try:
            port = _ensure_local_server()
        except Exception:
            info = CHANNEL_MAP[slug]
            url = ''
            try:
                now = int(time.time())
                url = jce_timeshift_url(info['pid'], info['sid'], now - WINDOW, now, info['defn'])
            except Exception:
                pass
            return {"parse": 0, "playUrl": "", "url": url,
                    "header": {"User-Agent": UA, "Referer": "https://live.cctv.cn/"}}

        ch = CHANNEL_STATE[slug]
        _ensure_channel(ch)
        for _ in range(40):
            with ch.lock:
                if ch.order:
                    break
            time.sleep(0.5)

        return {
            "parse": 0,
            "playUrl": "",
            "url": "http://127.0.0.1:%d/%s.m3u8" % (port, slug),
            "header": {
                "User-Agent": UA,
                "Referer": "https://live.cctv.cn/",
            },
        }

    def searchContent(self, key, quick, pg="1"):
        del quick, pg
        key = (key or "").strip().lower()
        cards = []
        if key:
            for slug, name, _s, _p, _d in CHANNELS:
                if key in name.lower() or key in slug.lower():
                    cards.append(self._make_card(slug, name))
        return {"page": 1, "pagecount": 1, "limit": len(cards), "total": len(cards), "list": cards}

    def action(self, action): return {"msg": "ok"}
    def liveContent(self): return ""
    def localProxy(self, params): return [404, "text/plain; charset=utf-8", "Proxy not configured"]


# ================================================================ 本地调试

if __name__ == '__main__':
    import argparse, sys
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=LOCAL_PORT_PREFERRED)
    ap.add_argument('--once', action='store_true')
    ap.add_argument('--test-slug', default='cctv1')
    args = ap.parse_args()
    LOCAL_PORT_PREFERRED = args.port

    sp = Spider(); sp.init()
    print("homeContent:", json.dumps(sp.homeContent({}), ensure_ascii=False))
    cc = sp.categoryContent('cctv', 1, {}, {})
    print("cctv: %d 个频道" % cc['total'])
    dc = sp.detailContent([args.test_slug])
    if dc['list']:
        print("detail:", dc['list'][0]['vod_name'], dc['list'][0]['vod_play_url'])
    pc = sp.playerContent('', args.test_slug, [])
    print("playerContent:", json.dumps(pc, ensure_ascii=False))

    if args.once:
        time.sleep(3)
        try:
            with urllib.request.urlopen(pc['url'], timeout=10) as r:
                print(r.read().decode('utf-8', 'replace')[:800])
        except Exception as e:
            print("错误:", e)
        sys.exit(0)

    port = _LOCAL_PORT
    print("\n" + "=" * 60)
    print("常驻模式 (Ctrl+C 退出)")
    print("  m3u8 : http://127.0.0.1:%d/%s.m3u8" % (port, args.test_slug))
    print("  diag : http://127.0.0.1:%d/diag" % port)
    print("=" * 60)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass