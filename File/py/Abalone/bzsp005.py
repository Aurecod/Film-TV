# -*- coding: utf-8 -*-
# 作者：蜗牛大叔 (适配 FongMi/TVBox)
# 播放解析已替换为本站专用（来自 bzsp005播放页.py）：_parse_play / playerContent（player_aaaa 直出 m3u8）
import re
import json
import sys
import urllib.parse
import urllib.request
import ssl
sys.path.append('..')
from base.spider import Spider

import re
import urllib.parse

def _fix_key_uri(ln, playlist_url):
    """KEY 标签的相对 URI 改绝对，绝对的不动。"""
    s = ln.strip()
    if s.startswith("#EXT-X-KEY:"):
        m = re.search(r'URI="([^"]+)"', ln)
        if m and not m.group(1).lower().startswith("http"):
            absu = urllib.parse.urljoin(playlist_url, m.group(1))
            ln = ln.replace('URI="%s"' % m.group(1), 'URI="%s"' % absu)
    return ln



def _strip_ad(text, playlist_url):
    """去掉全部广告块（片头 + 片中），返回可直接播放的 m3u8 文本。

    广告识别（ZakaTV p007 招式：按分片路径统计时长）：
    广告分片和正片分片走不同路径。统计每条分片目录路径的总时长，
    时长占比最大的路径就是正片；其它路径的分片，在广告总时长不足
    全部时长一半时全部删除（防多 CDN 正片被误杀）。
    删完重建 MEDIA-SEQUENCE；DISCONTINUITY 按保留下来的分片块重建
    （两块正片之间只留一个）；KEY/MAP 等标签保留；分片与 KEY 的
    相对 URI 一律改绝对（2026-10-07 站方部分视频改走 t36/t27.cdn2020.com，
    分片为相对路径，不改绝对播放器按代理地址解析会 404）。

    实测样本（2026-10-08）：4 个块 = 9 广告(25.8s) + 2151 正片(6453.2s)
    + 9 广告(25.8s) + 2666 正片(7998.6s)，清理后总时长 14451.8s = 4:00:52。
    """
    text = (text or "").replace("\r", "")
    lines = text.split("\n")
    # 头部：第一个分片/#EXTINF 之前的所有标签行（EXTM3U/VERSION/KEY 等）必须保留
    head_end = len(lines)
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("#EXTINF") or (s and not s.startswith("#")):
            head_end = i
            break
    head = [_fix_key_uri(ln, playlist_url) for ln in lines[:head_end]]
    body = lines[head_end:]

    # 解析出所有分片：extinf 行号 / uri 行号 / 时长 / 绝对地址
    segs = []
    pending = None  # (extinf_idx, dur)
    for idx, ln in enumerate(body):
        s = ln.strip()
        if s.startswith("#EXTINF"):
            try:
                dur = float(s.split(":", 1)[1].split(",", 1)[0])
            except Exception:
                dur = 0.0
            pending = (idx, dur)
        elif pending is not None and s and not s.startswith("#"):
            eidx, dur = pending
            pending = None
            segs.append({"dur": dur,
                         "abs": urllib.parse.urljoin(playlist_url, s),
                         "extinf_idx": eidx, "uri_idx": idx})

    def _path(sg):
        return sg["abs"].rsplit("/", 1)[0]

    drop_idx = set()
    dropped = 0
    if segs:
        stat = {}
        for sg in segs:
            k = _path(sg)
            stat[k] = stat.get(k, 0.0) + sg["dur"]
        total = sum(stat.values())
        main_key = max(stat.items(), key=lambda x: x[1])[0]
        ad_dur = total - stat[main_key]
        if ad_dur > 0 and ad_dur < total * 0.5:
            for sg in segs:
                if _path(sg) != main_key:
                    drop_idx.add(sg["extinf_idx"])
                    drop_idx.add(sg["uri_idx"])
                    dropped += 1
        # 兜底：没触发按路径删时，沿用老逻辑只删片头短广告块
        if not drop_idx:
            cut = None
            for i, ln in enumerate(body):
                if ln.strip() == "#EXT-X-DISCONTINUITY":
                    cut = i
                    break
            if cut is not None:
                first_dur = sum(sg["dur"] for sg in segs if sg["uri_idx"] < cut)
                if 0 < first_dur <= 180:
                    for sg in segs:
                        if sg["uri_idx"] < cut:
                            drop_idx.add(sg["extinf_idx"])
                            drop_idx.add(sg["uri_idx"])
                            dropped += 1

    # 重建 body：跳过被删分片；DISCONTINUITY 按保留块重建；
    # 断点间隙里的 KEY/MAP 等标签缓存，等下一个保留分片时跟在 DISC 后面下发
    orig_disc = sum(1 for ln in body if ln.strip() == "#EXT-X-DISCONTINUITY")
    out = []
    need_disc = False
    emitted_seg = False
    pending_tags = []
    for idx, ln in enumerate(body):
        if idx in drop_idx:
            continue
        s = ln.strip()
        if s == "#EXT-X-DISCONTINUITY":
            need_disc = True
            continue
        if s.startswith("#EXTINF"):
            if need_disc and emitted_seg:
                out.append("#EXT-X-DISCONTINUITY")
            # 断点间隙里缓存的标签跟在 DISC 后面下发，相邻重复的去重
            for t in pending_tags:
                if not out or out[-1] != t:
                    out.append(t)
            pending_tags = []
            need_disc = False
            out.append(ln)
            continue
        if s.startswith("#"):
            ln = _fix_key_uri(ln, playlist_url)
            if need_disc:
                pending_tags.append(ln)
            else:
                out.append(ln)
            continue
        if s:
            # 分片 URI：相对路径一律改绝对，否则播放器按代理地址解析会 404
            out.append(urllib.parse.urljoin(playlist_url, s))
            emitted_seg = True
            continue
        out.append(ln)
    out.extend(pending_tags)

    text = "\n".join(head + out)
    if dropped:
        text = re.sub(r"#EXT-X-MEDIA-SEQUENCE:\d+",
                      "#EXT-X-MEDIA-SEQUENCE:%d" % dropped, text, count=1)
        new_disc = out.count("#EXT-X-DISCONTINUITY")
        if orig_disc > new_disc:
            def _dec_seq(m):
                v = int(m.group(1)) - (orig_disc - new_disc)
                return "#EXT-X-DISCONTINUITY-SEQUENCE:%d" % max(v, 0)
            text = re.sub(r"#EXT-X-DISCONTINUITY-SEQUENCE:(\d+)", _dec_seq,
                          text, count=1)
    return text



class Spider(Spider):
    # 直连候选域名：www/https 直连被拦（不开代理没数据）时依次换裸域名与 http
    HOSTS = [
        'https://www.bzsp005.sbs',
        'https://bzsp005.sbs',
        'http://www.bzsp005.sbs',
        'http://bzsp005.sbs',
    ]

    def init(self, extend=""):
        self.host = self.HOSTS[0]
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': self.host + '/',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }
        # 可选代理（extend 里配了才用，且只作直连全失败后的兜底）：
        # {"proxy":"http://127.0.0.1:7890"} 或 {"http":...,"https":...}
        self.proxies = None
        if extend:
            try:
                import json
                cfg = json.loads(extend) if isinstance(extend, str) else extend
                if isinstance(cfg, dict):
                    p = cfg.get('proxy') or cfg.get('https') or cfg.get('http')
                    if p:
                        self.proxies = {'http': p, 'https': p}
            except Exception:
                pass

    def getName(self):
        return 'BZSP005'

    def isVideoFormat(self, url):
        if not url:
            return False
        return bool(re.search(r'\.(m3u8|mp4|flv|ts|mkv|avi|mov)(\?|$)', str(url), re.I))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    # ---------- 取数：框架 fetch → urllib 直连（显式无代理）→ 各候选域名 ----------
    @staticmethod
    def _looks_real(text):
        """拦住短页/拦截页：真实页应含站内链路或播放标记，避免拿到拦截页就误判成功"""
        if not text or len(text) < 200:
            return False
        low = text.lower()
        if '/index.php/vod/' in low or 'player_aaaa' in low or '.m3u8' in low:
            return True
        return '<title' in low and len(text) > 500

    def _candidates(self, url):
        """站内地址生成跨域名候选（已验证可用的域名排第一）；外站地址原样"""
        from urllib.parse import urlsplit, urlunsplit
        try:
            sp = urlsplit(url)
        except Exception:
            return [url]
        if not sp.hostname or 'bzsp005.sbs' not in sp.hostname:
            return [url]
        hosts = []
        for h in [self.host] + self.HOSTS:
            if h not in hosts:
                hosts.append(h)
        return [urlunsplit((urlsplit(h).scheme, urlsplit(h).netloc,
                             sp.path, sp.query, '')) for h in hosts]

    def _fetch_framework(self, url):
        try:
            try:
                r = self.fetch(url, headers=self.headers, timeout=15)
            except TypeError:
                r = self.fetch(url, headers=self.headers)
            if r and getattr(r, 'text', ''):
                return r.text
        except Exception:
            pass
        return ''

    def _fetch_direct(self, url, proxy=None):
        """urllib 直连：ProxyHandler({}) 显式绕开系统/环境代理设置，
        这是「不开代理」时 self.fetch 拿不到数据的关键兜底"""
        import ssl
        import gzip
        import urllib.request
        handlers = [urllib.request.ProxyHandler({'http': proxy, 'https': proxy})
                    if proxy else urllib.request.ProxyHandler({})]
        last = ''
        for ctx in (None, ssl._create_unverified_context()):
            try:
                if ctx is not None:
                    handlers.append(urllib.request.HTTPSHandler(context=ctx))
                opener = urllib.request.build_opener(*handlers)
                req = urllib.request.Request(url, headers=self.headers)
                with opener.open(req, timeout=15) as resp:
                    data = resp.read()
                    if data[:2] == b'\x1f\x8b':
                        data = gzip.decompress(data)
                    for enc in ('utf-8', 'gb18030'):
                        try:
                            return data.decode(enc)
                        except Exception:
                            continue
                    return data.decode('utf-8', 'ignore')
            except Exception as e:
                last = str(e)
                continue
        return ''

    def _get(self, url):
        best = ''
        for cand in self._candidates(url):
            for getter in (self._fetch_framework, self._fetch_direct):
                text = getter(cand)
                if text and len(text) > len(best):
                    best = text
                if self._looks_real(text):
                    # 记下可用域名，后续分类/详情/播放直接用它，不再逐个试
                    from urllib.parse import urlsplit
                    sp = urlsplit(cand)
                    if sp.hostname and 'bzsp005.sbs' in sp.hostname:
                        self.host = f'{sp.scheme}://{sp.netloc}'
                        self.headers['Referer'] = self.host + '/'
                    return text
        # 直连候选全军覆没且配了代理时，最后走代理试主域名（不开代理则跳过）
        if self.proxies:
            from urllib.parse import urlsplit
            sp = urlsplit(url)
            if sp.hostname and 'bzsp005.sbs' in sp.hostname:
                main = self.HOSTS[0] + sp.path + (('?' + sp.query) if sp.query else '')
                text = self._fetch_direct(main, proxy=self.proxies.get('https'))
                if self._looks_real(text):
                    return text
                if text and len(text) > len(best):
                    best = text
        # 实在不行把最长的响应交回解析层（短页由 >500 的旧门槛直接吞掉是没数据主因之一）
        return best if len(best) > 500 else (best if self._looks_real(best) else '')

    # ============ 播放页解析（本站专用，来自 bzsp005播放页.py） ============

    # ---------- 播放页解析 ----------
    @staticmethod
    def _clean_url(raw, encrypt='0'):
        """还原 player_aaaa.url：JS 转义、HTML 实体、MacCMS encrypt=1/2 编码"""
        if not raw:
            return ''
        url = str(raw).strip().strip('"').strip("'")
        if not url:
            return ''
        url = url.replace('\\/', '/')
        url = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), url)
        try:
            if str(encrypt) == '2':
                import base64
                from urllib.parse import unquote
                pad = '=' * (-len(url) % 4)
                decoded = base64.b64decode(url + pad).decode('utf-8', 'ignore')
                if decoded:
                    url = unquote(decoded).replace('\\/', '/')
            elif str(encrypt) == '1':
                from urllib.parse import unquote
                url = unquote(url)
        except Exception:
            pass
        url = url.replace('\\&', '&')
        import html as _html
        return _html.unescape(url).strip()

    def _abs_url(self, url):
        if not url:
            return ''
        if url.startswith('//'):
            return 'https:' + url
        if url.startswith('/'):
            return self.host + url
        return url

    def _parse_play(self, h):
        """解析播放页 HTML：优先 player_aaaa.url（直出 m3u8），
        依次退 video/source 标签、全文裸 m3u8/mp4"""
        if not h:
            return ''
        # 1) player_aaaa：不依赖其后紧跟 </script>（模板常带分号或其它 JS 会让旧正则落空）
        start = h.find('player_aaaa')
        if start >= 0:
            block = h[start:start + 8000]
            em = re.search(r'"encrypt"\s*:\s*"?(\d+)"?', block)
            encrypt = em.group(1) if em else '0'
            um = re.search(r'"url"\s*:\s*"((?:[^"\\]|\\.)*)"', block)
            if not um:
                um = re.search(r"'url'\s*:\s*'((?:[^'\\]|\\.)*)'", block)
            if um and um.group(1):
                url = self._clean_url(um.group(1), encrypt)
                if url:
                    return self._abs_url(url)
        # 2) video / source 标签（兼容单引号、属性换行）
        m = re.search(r'<source[^>]+src=["\']([^"\']+)["\']', h, re.I | re.S)
        if m:
            return self._abs_url(self._clean_url(m.group(1)))
        m = re.search(r'<video[^>]+src=["\']([^"\']+)["\']', h, re.I | re.S)
        if m:
            return self._abs_url(self._clean_url(m.group(1)))
        # 3) 全文裸地址：先反转义再找，避免 https:\/\/ 写法漏检或截断
        import html as _html
        text = _html.unescape(h.replace('\\/', '/'))
        m = re.search(r'https?://[^\s"\'<>]+\.m3u8(?:\?[^\s"\'<>]*)?', text, re.I)
        if m:
            return m.group(0)
        m = re.search(r'https?://[^\s"\'<>]+\.mp4(?:\?[^\s"\'<>]*)?', text, re.I)
        return m.group(0) if m else ''

    def playerContent(self, flag, id, vipFlags=None):
        """id 形态：vod_id 数字 / 「正片$」+详情或播放 URL / 相对播放路径 / 直链"""
        url = ''
        purl = ''
        referer = self.host + '/'
        raw = str(id).strip() if id else ''
        # detailContent 拼的是「正片$<详情URL>」：先剥线路名前缀再判断 id 形态
        # （旧逻辑先判 isdigit/http，「正片$123」这类会两头落空）
        part = raw.rsplit('$', 1)[-1].strip() if raw else ''
        if part:
            if re.search(r'\.(m3u8|mp4|flv|mkv|mov)(\?|#|$)', part, re.I):
                # 本身就是直链，不再当成网页去抓
                url = self._abs_url(self._clean_url(part))
            elif part.isdigit():
                purl = f'{self.host}/index.php/vod/play/id/{part}/sid/1/nid/1.html'
            elif part.startswith('http'):
                purl = part
            elif part.startswith('/'):
                purl = self.host + part
            elif 'vod/play/' in part or 'vod/detail/' in part:
                purl = self.host + '/' + part.lstrip('/')
        if purl and not url:
            referer = purl
            h = self._get(purl)
            url = self._parse_play(h)
            if not url and h:
                # 详情页等中间页：取站内播放页链接再解析一次
                pm = re.search(r'href=["\']([^"\']*vod/play/[^"\']*)["\']', h, re.I)
                if pm:
                    purl2 = pm.group(1).replace('&amp;', '&')
                    if not purl2.startswith('http'):
                        purl2 = self.host + '/' + purl2.lstrip('/')
                    if purl2 != purl:
                        referer = purl2
                        url = self._parse_play(self._get(purl2))
        headers = dict(self.headers)
        headers['Referer'] = referer
        # 去广告：走 localProxy（和爱看一致：header 用 json.dumps）
        if url and '.m3u8' in url:
            base = self.getProxyUrl() or ""
            if base:
                sep = "&" if "?" in base else "?"
                proxy_url = "%s%stype=ak_adfree&url=%s&referer=%s" % (
                    base, sep,
                    urllib.parse.quote(url, safe=""),
                    urllib.parse.quote(referer, safe=""))
                return {'parse': 0, 'playUrl': '', 'url': proxy_url,
                        'header': json.dumps({"User-Agent": self.headers["User-Agent"], "Referer": referer})}
        return {'parse': 0, 'playUrl': '', 'url': url, 'header': headers}

    def homeContent(self, filter=None):
        cats = [
            ('25', '口交颜射'),
            ('26', 'COS独家'),
            ('27', '约炮人妻'),
            ('28', '淫乱群交'),
            ('29', '成人动漫'),
            ('30', '国产原创'),
            ('31', '高清无码'),
            ('32', '强奸乱伦'),
            ('33', '人妻熟女'),
            ('34', '制服丝袜'),
            ('35', '巨乳美乳'),
            ('36', 'AV明星'),
        ]
        return {'class': [{'type_id': c[0], 'type_name': c[1]} for c in cats]}

    def homeVideoContent(self):
        # 旧版固定返回空列表，首页必然没数据；改为抓首页推荐
        h = self._get(self.host + '/')
        return {'list': self._parse_list(h)}

    def _parse_list(self, h):
        vids = []
        seen = set()
        for m in re.finditer(
            r'<dt><a href="/index\.php/vod/detail/id/(\d+)\.html" title="([^"]*)"[^>]*>\s*<img[^>]*src="([^"]+)"[^>]*alt="[^"]*"',
            h
        ):
            vid, title, pic = m.group(1), m.group(2), m.group(3)
            if vid in seen:
                continue
            seen.add(vid)
            score = ''
            ctx = h[m.end():m.end()+500]
            sm = re.search(r'评分:\s*([0-9.]+)', ctx)
            if sm:
                score = sm.group(1)
            vids.append({
                'vod_id': vid,
                'vod_name': title.strip(),
                'vod_pic': pic,
                'vod_remarks': score,
            })
        if vids:
            return vids
        # 宽松兜底：模板属性顺序/懒加载(data-src)变化时主正则会整页落空
        import html as _html
        for m in re.finditer(
            r'href=["\'](?:https?://[^"\']*)?/index\.php/vod/detail/id/(\d+)\.html["\']([^>]*)>(.*?)</a>',
            h, re.S
        ):
            vid = m.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            attrs, inner = m.group(2), m.group(3)
            ctx = inner + h[m.end():m.end() + 800]
            title = ''
            tm = re.search(r'title="([^"]+)"', attrs)
            if tm:
                title = tm.group(1)
            pic = ''
            im = re.search(r'<img[^>]+(?:data-src|data-original|src)=["\']([^"\']+)["\']', ctx, re.I)
            if im:
                pic = im.group(1)
                if not title:
                    am = re.search(r'<img[^>]+alt="([^"]*)"', ctx, re.I)
                    if am:
                        title = am.group(1)
            if not title:
                title = re.sub(r'<[^>]+>', '', inner).strip()
            score = ''
            sm = re.search(r'评分:\s*([0-9.]+)', ctx)
            if sm:
                score = sm.group(1)
            if title:
                vids.append({
                    'vod_id': vid,
                    'vod_name': _html.unescape(title).strip(),
                    'vod_pic': pic,
                    'vod_remarks': score,
                })
        return vids

    def categoryContent(self, tid, pg, filter=None, extend=None):
        pg = int(pg)
        if pg == 1:
            url = f'{self.host}/index.php/vod/type/id/{tid}.html'
        else:
            url = f'{self.host}/index.php/vod/type/id/{tid}/page/{pg}.html'
        h = self._get(url)
        return {'list': self._parse_list(h), 'page': pg, 'pagecount': 9999, 'limit': 48, 'total': 999999}

    def detailContent(self, ids):
        vid = ids[0] if isinstance(ids, (list, tuple)) else ids
        h = self._get(f'{self.host}/index.php/vod/detail/id/{vid}.html')
        name = ''
        m = re.search(r'<title>(.+?)详情介绍', h)
        if m:
            name = m.group(1).strip()
        if not name:
            m2 = re.search(r'<title>([^<]+)</title>', h)
            if m2:
                name = m2.group(1).strip()
        pic = ''
        im = re.search(r'<dt><a[^>]*>\s*<img[^>]*src="(https?://[^"]+)"', h)
        if im:
            pic = im.group(1)
        detail_url = f'{self.host}/index.php/vod/detail/id/{vid}.html'
        vod = {
            'vod_id': vid,
            'vod_name': name,
            'vod_pic': pic,
            'vod_play_from': '正片',
            'vod_play_url': f'正片${detail_url}',
        }
        return {'list': [vod]}

    def searchContent(self, key, quick=False, pg="1"):
        pg = int(pg)
        from urllib.parse import quote
        url = f'{self.host}/index.php/vod/search/wd/{quote(key)}.html'
        if pg > 1:
            url = f'{self.host}/index.php/vod/search/wd/{quote(key)}/page/{pg}.html'
        h = self._get(url)
        return {'list': self._parse_list(h), 'page': pg}

    def _proxy_base(self):
        try:
            if hasattr(self, "getProxyUrl"):
                base = self.getProxyUrl() or ""
                if base:
                    return base
        except Exception:
            pass
        return "http://127.0.0.1:9978/proxy?do=py"

    def localProxy(self, params):
        """下发去广告的 m3u8。FongMi 要求返回 [code, ctype, content, headers, base64flag]"""
        try:
            if not isinstance(params, dict):
                params = {}
            def _first(d, *ks):
                for k in ks:
                    v = d.get(k)
                    if v:
                        return v[0] if isinstance(v, list) else v
                return ""
            action = _first(params, "type", "do", "action")
            if action != "ak_adfree":
                return [404, "text/plain", "not found", {}, 0]
            m3u8_url = urllib.parse.unquote(_first(params, "url"))
            referer = urllib.parse.unquote(_first(params, "referer")) or self.host
            if not m3u8_url.startswith("http"):
                return [404, "text/plain", "bad url", {}, 0]
            h = {"User-Agent": self.headers["User-Agent"], "Referer": referer}
            req = urllib.request.Request(m3u8_url, headers=h)
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            r = urllib.request.urlopen(req, timeout=15, context=ctx)
            text = r.read().decode("utf-8", "ignore")
            if "#EXT-X-STREAM-INF" in text:
                mm = re.search(r"^(?!#)(.+\.m3u8.*)$", text, re.M)
                if mm:
                    sub = urllib.parse.urljoin(m3u8_url, mm.group(1).strip())
                    req2 = urllib.request.Request(sub, headers=h)
                    r2 = urllib.request.urlopen(req2, timeout=15, context=ctx)
                    text = r2.read().decode("utf-8", "ignore")
                    m3u8_url = sub
            # FongMi 要求：返回 [code, content_type, content, headers, base64flag]
            processed_text = _strip_ad(text, m3u8_url)
            return [200, "application/vnd.apple.mpegurl", processed_text, 
                    {"User-Agent": self.headers["User-Agent"], "Referer": referer}, 0]
        except Exception as e:
            return [500, "text/plain", "proxy error: %s" % e, {}, 0]