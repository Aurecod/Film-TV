# -*- coding: utf-8 -*-
# 作者：蜗牛大叔
# 播放解析已替换为本站专用（来自 bzsp005播放页.py）：_parse_play / playerContent（player_aaaa 直出 m3u8）
import re
import sys
sys.path.append('..')
from base.spider import Spider


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

    def localProxy(self, param):
        pass