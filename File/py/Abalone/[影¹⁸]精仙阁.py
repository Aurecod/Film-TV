# -*- coding: utf-8 -*-
"""
精仙阁 TVBox Spider
站点: https://fuwtrv.jxg2.buzz/ (首页 /jxg/)
形态: macCMS 风格模板站 · 服务端直渲染 · 无反爬 · 11 分类 · 单集直链
详情页即播放页: 媒体地址在内联 JS `const rawUrl = '...m3u8'`
详情页规律 /{vid}.html · 分类页 /vodtype/{tid}.html 翻页 /vodtype/{tid}-{pg}.html
搜索 /s/index.html?wd={key}
广告深度清洗: 播放流含片头/片中/片尾广告分片(异目录 Zse0Tpg8/9641kb + METHOD=NONE +
  DISCONTINUITY 标记, 另有亚秒级广告过渡帧); playerContent 经 _proxy_url 生成本地代理地址
  (统一走壳契约 do=py&type=stream&url=<b64> 协议, 基址取自壳注入 getProxyUrl/Proxy.getPort),
  壳回调 localProxy 实时清洗后以 [200, mime, bytes] 返回
  双线路: 线路1 去广告(本地代理) · 线路2 原画直链(壳不支持 py 代理时直接可播)
修复: 2026-09-29 根因=代理地址协议错误(旧 do=local 壳不路由) → 改 do=py
契约: class Spider 无继承 · 14 壳方法全实现 · 位置参数契约 · $/#/$$$ 分隔
      Python 层不调用 setCache/getCache
生成: 2026-09-28 · 结构经 live browser 逐字节核对 · 2026-09-29 加入 HLS 广告深度清洗
"""
import re
import json
import base64
import html as _html
import urllib.request
import urllib.parse
import urllib.error


class Spider:
    def __init__(self):
        self.host = 'https://fuwtrv.jxg2.buzz'
        self.home_url = self.host + '/jxg/'
        self.ua = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
        self.headers = {
            'User-Agent': self.ua,
            'Referer': self.host + '/',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }
        self.pic_referer = '@Referer=' + self.host + '/'
        self._proxy_port = 9978  # 兜底端口(TVBox 系 Server 起始端口)
        self.classes = [
            ('熟母少妇', '20'), ('网红直播', '21'), ('自拍偷拍', '22'),
            ('强奸乱伦', '23'), ('高清国产', '24'), ('韩国专区', '25'),
            ('日本有码', '26'), ('日本无码', '27'), ('欧美情色', '28'),
            ('动漫卡通', '29'), ('三级伦理', '30'),
        ]

    # ================= 内部工具 =================
    def _fetch(self, url, timeout=20):
        req = urllib.request.Request(url, headers=self.headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        for enc in ('utf-8', 'gbk', 'gb18030'):
            try:
                return data.decode(enc)
            except Exception:
                continue
        return data.decode('utf-8', 'ignore')

    def _clean(self, s):
        if not s:
            return ''
        s = _html.unescape(s)
        s = re.sub(r'<[^>]+>', '', s)
        return s.strip()

    def _parse_cards(self, html):
        """解析 .feature-post 视频卡片(首页/分类页/搜索页通用)"""
        items = []
        chunks = re.split(r'<div class="feature-post', html)
        for ch in chunks[1:]:
            ch = ch[:6000]
            m = re.search(r'<a href="/(\d+)\.html"[^>]*title="([^"]*)"', ch)
            if m:
                vid, title = m.group(1), m.group(2)
            else:
                m2 = re.search(r'<a href="/(\d+)\.html"', ch)
                if not m2:
                    continue
                vid = m2.group(1)
                t = re.search(r'class="post-title"[^>]*>([^<]+)<', ch)
                title = t.group(1) if t else ''
            title = self._clean(title)
            pic = ''
            pm = re.search(r'data-original="([^"]+)"', ch)
            if pm:
                pic = pm.group(1)
            else:
                sm = re.search(r'src="(https?://[^"]+)"', ch)
                if sm and not sm.group(1).startswith('data:'):
                    pic = sm.group(1)
            remark = ''
            rm = re.search(r'class="btn-l"[^>]*>\s*(?:<a[^>]*>)?([^<]+)', ch)
            if rm:
                remark = self._clean(rm.group(1))[:16]
            if vid and title:
                if pic and not pic.startswith('data:') and '@Referer=' not in pic:
                    pic = pic + self.pic_referer
                items.append({
                    'vod_id': vid,
                    'vod_name': title,
                    'vod_pic': pic,
                    'vod_remarks': remark,
                })
        # 按 vid 去重保序
        seen, out = set(), []
        for it in items:
            if it['vod_id'] not in seen:
                seen.add(it['vod_id'])
                out.append(it)
        return out

    def _parse_pagecount(self, html):
        m = re.search(r'>(\d+)\s*/\s*(\d+)<', html)
        if m:
            return m.group(1), m.group(2)
        return '1', '1'

    # ================= 壳接口(位置参数契约) =================
    def getName(self):
        return '精仙阁'

    def getDependence(self):
        return []

    def isVideoFormat(self, url):
        u = (url or '').lower()
        if '/proxy?' in u or 'key=hls/' in u:
            return True  # 本地广告清洗代理, 一律按视频流处理
        return u.endswith('.m3u8') or u.endswith('.mp4') or '.m3u8?' in u or '.mp4?' in u

    def manualVideoCheck(self):
        return {'code': 200, 'msg': 'ok'}

    def init(self, extend):
        return None

    def destroy(self):
        return None

    def homeContent(self, filter):
        html = self._fetch(self.home_url)
        classes = [{'type_id': tid, 'type_name': name} for name, tid in self.classes]
        items = self._parse_cards(html)
        return {'class': classes, 'list': items[:72], 'filters': {}}

    def homeVideoContent(self):
        return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg)
        if pg <= 1:
            url = '{0}/vodtype/{1}.html'.format(self.host, tid)
        else:
            url = '{0}/vodtype/{1}-{2}.html'.format(self.host, tid, pg)
        html = self._fetch(url)
        items = self._parse_cards(html)
        page, pagecount = self._parse_pagecount(html)
        return {
            'list': items,
            'page': page,
            'pagecount': pagecount,
            'limit': 90,
            'total': 999999,
        }

    def detailContent(self, ids):
        vid = ids[0]
        url = '{0}/{1}.html'.format(self.host, vid)
        html = self._fetch(url)
        title = ''
        m = re.search(r'<h1 class="heading-1"[^>]*>([^<]+)<', html)
        if m:
            title = self._clean(m.group(1))
        if not title:
            m2 = re.search(r'<title>([^-<]+)', html)
            title = self._clean(m2.group(1)) if m2 else vid
        pic = ''
        pm = re.search(r'(https?://[^"\']+/upload/vod/[^"\']+\.(?:jpg|jpeg|png|webp))', html)
        if pm:
            pic = pm.group(1) + self.pic_referer
        play_url = ''
        rm = re.search(r"const rawUrl = '([^']+\.m3u8[^']*)'", html)
        if rm:
            play_url = rm.group(1)
        else:
            fm = re.search(r'(https?://[^\s"\'$#]+\.m3u8(?:\?[^\s"\']*)?)', html)
            if fm:
                play_url = fm.group(1)
        vod = {
            'vod_id': vid,
            'vod_name': title,
            'vod_pic': pic,
            'vod_content': '',
            'vod_play_from': '精仙阁·去广告$$$精仙阁·原画',
            'vod_play_url': ('正片$%s$$$正片$%s' % (self._proxy_url(play_url), play_url)) if play_url else '',
        }
        return {'list': [vod]}

    def searchContent(self, key, quick, pg):
        q = urllib.parse.quote(key)
        url = '{0}/s/index.html?wd={1}'.format(self.host, q)
        html = self._fetch(url)
        items = self._parse_cards(html)
        page, pagecount = self._parse_pagecount(html)
        return {
            'list': items,
            'page': page,
            'pagecount': pagecount,
            'limit': 90,
            'total': 999999,
        }

    def _proxy_base(self):
        """取壳本地代理基址: 壳注入 getProxyUrl → base.spider → Java Proxy 反射 → 兜底端口。"""
        _fn = getattr(self, 'getProxyUrl', None)
        if callable(_fn):
            try:
                _u = _fn(True)
                if _u:
                    return str(_u).split('?')[0].rstrip('/')
            except Exception:
                pass
        try:
            from base.spider import Spider as _BaseSpider
            _u = _BaseSpider.getProxyUrl(self, True)
            if _u:
                return str(_u).split('?')[0].rstrip('/')
        except Exception:
            pass
        try:
            from java.lang import Class
            _port = Class.forName('com.github.catvod.Proxy').getMethod('getPort', []).invoke(None, [])
            if _port:
                return 'http://127.0.0.1:%s/proxy' % int(_port)
        except Exception:
            pass
        return 'http://127.0.0.1:%s/proxy' % self._proxy_port

    def _proxy_url(self, url):
        """按壳统一契约生成本地代理地址: /proxy?do=py&type=stream&url=<b64>。
        壳(OK影视/FongMi/TVBox)收到该请求会回调本类 localProxy 实时清洗广告。"""
        _base = self._proxy_base()
        _enc = base64.b64encode(url.encode('utf-8')).decode('ascii')
        return _base + '?do=py&type=stream&url=' + urllib.parse.quote(_enc, safe='')

    def playerContent(self, flag, id, vipFlags):
        # m3u8 直链走本地广告清洗代理; 已经是代理地址的不再二次包装
        _u = id if ('/proxy?' in id or id.startswith('http://127.0.0.1')) else self._proxy_url(id)
        return {
            'parse': 0,
            'url': _u,
            'header': {
                'User-Agent': self.ua,
                'Referer': self.host + '/',
            },
        }

    def _serve_clean_m3u8(self, url):
        try:
            body = self._hls_clean(url)
        except Exception:
            # 清洗失败兜底: 原样拉取并转绝对路径, 不中断播放
            try:
                raw = self._fetch(url)
                base = url.rsplit('/', 1)[0] + '/'
                body = '\n'.join(
                    urllib.parse.urljoin(base, l.strip()) if l.strip() and not l.strip().startswith('#') else l
                    for l in raw.splitlines()
                )
            except Exception:
                return [502, 'text/plain', b'fetch failed']
        data = body.encode('utf-8') if isinstance(body, str) else body
        return [200, 'application/vnd.apple.mpegurl', data]

    def localProxy(self, param):
        # 兼容字典 / JSON 字符串两种参数形态
        if isinstance(param, dict):
            _p = dict(param)
        elif isinstance(param, str):
            try:
                _p = json.loads(param) if param.strip() else {}
            except Exception:
                _p = {}
            if not isinstance(_p, dict):
                _p = {}
        else:
            _p = {}
        _do = str(_p.get('do') or '')
        # do=local 协议（影视仓/OK影视/123av 无继承源标准）: key=hls/<b64>
        if _do == 'local':
            _key = urllib.parse.unquote(str(_p.get('key') or _p.get('url') or _p.get('path') or ''))
            if _key.startswith('hls/'):
                _b64 = _key[4:].split('/')[0]
                try:
                    _url = base64.urlsafe_b64decode(_b64 + '=' * (-len(_b64) % 4)).decode('utf-8')
                except Exception:
                    return [400, 'text/plain', b'bad key']
                return self._serve_clean_m3u8(_url)
            return [404, 'text/plain', b'bad key']
        # do=py 协议（TVBox 壳 getProxyUrl 注入）: type=stream&url=<b64>
        _url = urllib.parse.unquote(str(_p.get('url') or ''))
        if _url:
            try:
                _raw = base64.b64decode(_url).decode('utf-8')
                if _raw.startswith(('http://', 'https://')):
                    _url = _raw
            except Exception:
                pass
        if _url and '.m3u8' in _url:
            return self._serve_clean_m3u8(_url)
        return [404, 'text/plain', b'not found']

    # ============ HLS 广告深度清洗 ============
    def _hls_clean(self, url):
        """拉取 m3u8 并深度清洗广告分片, 返回净化后的播放列表文本。
        广告指纹: 与正片不同目录的分片组 + METHOD=NONE + DISCONTINUITY 隔离。
        清洗后: 分片/KEY 全部转绝对地址, 去 DISCONTINUITY, 密钥归一, 序列号归零。"""
        raw = self._fetch(url)
        # 主列表 -> 跟随唯一 variant 进入媒体列表
        if '#EXT-X-STREAM-INF' in raw:
            m = re.search(r'#EXT-X-STREAM-INF[^\n]*\n\s*([^\s#][^\n]*)', raw)
            if m:
                return self._hls_clean(urllib.parse.urljoin(url, m.group(1).strip()))
        base = url.rsplit('/', 1)[0] + '/'
        lines = raw.splitlines()
        seg_idx = []
        for i, l in enumerate(lines):
            s = l.strip()
            if s and not s.startswith('#'):
                seg_idx.append((i, s))
        # 多数表决确定正片目录, 异目录分片即广告
        dirs = {}
        for _, s in seg_idx:
            d = urllib.parse.urljoin(base, s).rsplit('/', 1)[0]
            dirs[d] = dirs.get(d, 0) + 1
        main_dir = max(dirs, key=dirs.get) if dirs else ''
        keep = set()
        dur = {}  # 分片行号 -> EXTINF 时长
        last_inf = None
        for i, l in enumerate(lines):
            s = l.strip()
            if s.startswith('#EXTINF'):
                m = re.match(r'#EXTINF:([\d.]+)', s)
                last_inf = float(m.group(1)) if m else None
            elif s and not s.startswith('#'):
                if last_inf is not None:
                    dur[i] = last_inf
                last_inf = None
            elif s.startswith('#'):
                pass
        for i, s in seg_idx:
            if urllib.parse.urljoin(base, s).rsplit('/', 1)[0] != main_dir:
                continue  # 异目录广告组
            if dur.get(i, 999) < 1.0:
                continue  # 亚秒级广告过渡帧/填充片
            keep.add(i)
        out = []
        i = 0
        n = len(lines)
        while i < n:
            l = lines[i]
            s = l.strip()
            if s.startswith('#EXT-X-DISCONTINUITY'):
                i += 1
                continue
            if s.startswith('#EXT-X-MEDIA-SEQUENCE'):
                out.append('#EXT-X-MEDIA-SEQUENCE:0')
                i += 1
                continue
            if s.startswith('#EXT-X-KEY'):
                if 'METHOD=NONE' in s:
                    i += 1  # 广告组的空密钥, 丢弃
                    continue
                l = re.sub(r'URI="([^"]+)"',
                           lambda m: 'URI="%s"' % urllib.parse.urljoin(base, m.group(1)), l)
                out.append(l)
                i += 1
                continue
            if s.startswith('#EXTINF'):
                j = i + 1
                while j < n and not lines[j].strip():
                    j += 1
                if j < n and j in keep:
                    out.append(l)
                i += 1
                continue
            if s and not s.startswith('#'):
                if i in keep:
                    out.append(urllib.parse.urljoin(base, s))
                i += 1
                continue
            out.append(l)
            i += 1
        return '\n'.join(out) + '\n'

    def action(self, action):
        return None
