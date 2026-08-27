# -*- coding: utf-8 -*-
# 海角修复版 2026-08-25
# 本版: 解密中转页 appConfig 取真实线路 -> 并发测速 -> 多线路轮换重试
#       封面图经 localProxy 带浏览器头转发(规避图床对播放器UA/防盗链的拦截)
import json
import re
import sys
import time
import hashlib
import threading
import requests
from base64 import b64decode, b64encode
from urllib.parse import quote

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):

    LANDING = 'https://cg51.com'
    # 中转页解析失败时的兜底线路(历史可用)
    FALLBACK_LINES = [
        'https://better.xsafjha.com',
        'https://agenda.xsafjha.com',
        'https://bone.xsafjha.com',
        'https://www.51ql1.com',
    ]
    # 菜单里不作为分类展示的项(需登录/非视频列表页)
    SKIP_MENU = {'/follow/', '/tags/', '/authors_blogger/original/', '/authors/', '/consumers/'}

    def getName(self):
        return '海角社区'

    def init(self, extend="{}"):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }
        ext = {}
        try:
            ext = json.loads(extend) if extend else {}
        except Exception:
            ext = {}

        self.lines = []
        self.host = ''
        if isinstance(ext, dict) and ext.get('host'):
            h = ext['host'].rstrip('/')
            self.lines = [h]
            self.log(f'[海角] 使用extend指定host: {h}')
        else:
            cached = ''
            try:
                cached = (self.getCache('hj_host') or '').rstrip('/')
            except Exception:
                cached = ''
            if cached and self._alive(cached):
                self.lines = [cached]
                self.log(f'[海角] 使用缓存host: {cached}')
        if not self.lines:
            self._resolve_lines()
        if not self.lines:
            self.lines = list(self.FALLBACK_LINES)
        self.host = self.lines[0]
        self.headers.update({'Referer': f'{self.host}/', 'Origin': self.host})
        self.log(f'[海角] 初始化完成 lines={self.lines}')

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def destroy(self):
        pass

    # ---------------- 线路解析 ----------------

    def _alive(self, host):
        """快速校验host是否仍可用"""
        try:
            r = requests.head(host, headers=self.headers, timeout=3, allow_redirects=True)
            return r.status_code < 500
        except Exception:
            try:
                r = requests.get(host, headers=self.headers, timeout=4, stream=True)
                r.close()
                return r.status_code < 500
            except Exception:
                return False

    def _landing_cfg(self):
        """解密中转页 appConfig: base64 -> 前16字节iv + 密文, key=SHA256(key字串), AES-CBC"""
        html = requests.get(self.LANDING, headers=self.headers, timeout=10).text
        mdata = re.search(r'data:\s*"([^"]+)"', html)
        mkey = re.search(r'key:\s*"([^"]+)"', html)
        if not mdata or not mkey:
            raise Exception('中转页未找到appConfig')
        raw = b64decode(mdata.group(1))
        iv, ct = raw[:16], raw[16:]
        key = hashlib.sha256(mkey.group(1).encode()).digest()
        pt = self._aes_decrypt(ct, key, iv)
        cfg = json.loads(pt.decode('utf-8'))
        self.log(f'[海角] 中转页配置解密成功 main={cfg.get("main","")} lines={len(cfg.get("domain",[]))}')
        return cfg

    def _resolve_lines(self):
        candidates = []
        try:
            cfg = self._landing_cfg()
            for d in cfg.get('domain', []):
                if d.get('value'):
                    candidates.append(d['value'].rstrip('/'))
            if cfg.get('main'):
                candidates.append(cfg['main'].rstrip('/'))
            bk = cfg.get('backup_domain') or {}
            if bk.get('value'):
                candidates.append(bk['value'].rstrip('/'))
        except Exception as e:
            self.log(f'[海角] 中转页解析失败: {e}')
        seen = set()
        candidates = [c for c in candidates if not (c in seen or seen.add(c))]
        if not candidates:
            candidates = self.FALLBACK_LINES
        self.lines = self._probe_lines(candidates)
        if self.lines:
            try:
                self.setCache('hj_host', self.lines[0])
            except Exception:
                pass

    def _probe_lines(self, urls):
        """并发探测所有候选线路, 返回按延迟排序的可用列表"""
        results = {}
        lock = threading.Lock()

        def probe(url):
            t0 = time.time()
            final, ok = '', False
            try:
                r = requests.head(url, headers=self.headers, timeout=2.5, allow_redirects=True)
                if r.status_code >= 500:
                    raise Exception(str(r.status_code))
                final, ok = r.url.rstrip('/'), True
            except Exception:
                try:
                    r = requests.get(url, headers=self.headers, timeout=3.5, stream=True)
                    r.close()
                    final, ok = r.url.rstrip('/'), r.status_code < 500
                except Exception as e2:
                    self.log(f'[海角] 线路不可用 {url}: {e2}')
            delay = (time.time() - t0) * 1000
            with lock:
                if ok:
                    results[final] = min(results.get(final, 1e18), delay)

        ts = []
        for u in urls:
            t = threading.Thread(target=probe, args=(u,), daemon=True)
            t.start()
            ts.append(t)
        for t in ts:
            t.join(8)
        ranked = [u for u, _ in sorted(results.items(), key=lambda x: x[1])]
        self.log(f'[海角] 测速完成 可用线路: {[(u, int(d)) for u, d in sorted(results.items(), key=lambda x: x[1])]}')
        return ranked

    # ---------------- 请求(多线路轮换) ----------------

    def _rotate(self):
        if len(self.lines) > 1:
            self.lines.append(self.lines.pop(0))
            self.host = self.lines[0]
            self.headers['Referer'] = f'{self.host}/'
            self.headers['Origin'] = self.host
            self.log(f'[海角] 切换线路 -> {self.host}')

    def _get(self, path, retries=None):
        """path 以 / 开头, 自动套当前线路; 失败换线重试"""
        if path.startswith('http'):
            path = '/' + path.split('/', 3)[-1]
        total = retries if retries is not None else max(2, len(self.lines))
        last = None
        for i in range(total):
            url = self.host + path
            try:
                r = requests.get(url, headers=self.headers, timeout=15)
                if r.status_code == 200 and len(r.text) > 1000:
                    return r.text
                last = Exception(f'HTTP {r.status_code} len={len(r.text)}')
                self.log(f'[海角] 异常响应 {url[:60]}: {last}')
            except Exception as e:
                last = e
                self.log(f'[海角] 请求失败 {url[:60]}: {e}')
            self._rotate()
        raise last or Exception('全部线路请求失败')

    CARD_SPLIT = '<div class="xqbj-list-rows">'
    CARD_ANCHOR = re.compile(r'<a href="(?:https?://[^"/]+)?(/(?:archives|community)/\d+/)"([^>]*)>')
    RANK_MARK = 'rank-card'

    @staticmethod
    def _clean_pic(u):
        if not u:
            return ''
        return u.strip().strip('`').replace('\\/', '/')

    @staticmethod
    def _aes_decrypt(data, key, iv):
        """AES-CBC + PKCS7, 兼容 pycryptodome / cryptography"""
        try:
            from Crypto.Cipher import AES
            pt = AES.new(key, AES.MODE_CBC, iv).decrypt(data)
        except ImportError:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            d = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
            pt = d.update(data) + d.finalize()
        pad = pt[-1]
        if 0 < pad <= 16:
            pt = pt[:-pad]
        return pt

    @staticmethod
    def _e64(text):
        try:
            return b64encode(str(text).encode('utf-8')).decode('utf-8')
        except Exception:
            return ''

    @staticmethod
    def _d64(text):
        try:
            return b64decode(str(text).encode('utf-8')).decode('utf-8')
        except Exception:
            return ''

    def _proxied_pic(self, url):
        """封面经本地代理转发: 播放器自带加载器可能被图床拒(UA/防盗链/DNS), 走爬虫栈最稳"""
        url = self._clean_pic(url)
        if not url:
            return ''
        try:
            proxy = self.getProxyUrl()
        except Exception:
            proxy = ''
        if not proxy:
            return url
        sep = '&' if '?' in proxy else '?'
        return f'{proxy}{sep}url={self._e64(url)}&type=img'

    def _parse_cards(self, html):
        """新版卡片: div.xqbj-list-rows > a[href=/archives/n/ 或 /community/n/] + img[z-image-loader-url]
        排除侧栏排行榜(rank-card)与广告 placard"""
        videos = []
        seen = set()
        for seg in html.split(self.CARD_SPLIT)[1:]:
            vid = None
            attrs = ''
            for m in self.CARD_ANCHOR.finditer(seg):
                if self.RANK_MARK in m.group(2):
                    continue
                vid, attrs = m.group(1), m.group(2)
                break
            if not vid or vid in seen:
                continue
            seen.add(vid)
            mt = re.search(r'title="([^"]+)"', attrs)
            if not mt:
                mt = re.search(r'image-title[^>]*>\s*([^<]{4,})', seg)
            if not mt:
                mt = re.search(r'<h3[^>]*>\s*([\s\S]{4,}?)</h3>', seg)
            if not mt:
                continue
            pic = re.search(r'z-image-loader-url="`?([^`"\n]+?)`?"', seg)
            views = re.search(r'icon-view@3x-light[\s\S]*?tags-text">([^<]+)<', seg)
            date = re.search(r'is-desktop">\s*([0-9\-]+)\s*<', seg)
            videos.append({
                'vod_id': vid,
                'vod_name': re.sub(r'\s+', ' ', mt.group(1)).strip(),
                'vod_pic': self._proxied_pic(pic.group(1)) if pic else '',
                'vod_remarks': (date.group(1) if date else (views.group(1).strip() if views else '')),
                'style': {'type': 'rect', 'ratio': 1.33},
            })
        return videos

    def _parse_date_list(self, html, cap=150):
        """往期归档页: <li><div class="date">08-15</div><a href=/archives/n/ class=history-text><div class=subtitle><h3>标题
        兼容相对路径与带随机子域的绝对链接(归一化为path)"""
        videos = []
        seen = set()
        for m in re.finditer(r'<li[^>]*>\s*<div class="date">([^<]*)</div>\s*<a href="(?:https?://[^"/]+)?(/(?:archives|community)/\d+/)"[\s\S]*?<h3[^>]*>([\s\S]*?)</h3>', html):
            date, vid, title = m.group(1).strip(), m.group(2), re.sub(r'<[^>]+>', '', m.group(3))
            if vid in seen:
                continue
            seen.add(vid)
            videos.append({
                'vod_id': vid,
                'vod_name': re.sub(r'\s+', ' ', title).strip(),
                'vod_pic': '',
                'vod_remarks': date,
                'style': {'type': 'rect', 'ratio': 1.33},
            })
            if len(videos) >= cap:
                break
        return videos

    @staticmethod
    def _pagecount(html, default=9999):
        m = re.search(r'id="total"[^>]*>\s*<a href="[^"]*?(\d+)/?"[^>]*>\s*\d+\s*</a>', html)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass
        return default

    def _menu_classes(self, html):
        classes = []
        seen = set()
        for name, href in re.findall(r'aria-label="([^"]+)">\s*<a href="([^"]+)"', html):
            href = href.strip()
            if not href or href in seen or href in self.SKIP_MENU or href.startswith('#'):
                continue
            if not (href == '/' or href.startswith(('/category/', '/order/', '/communitys/', '/date/'))):
                continue
            seen.add(href)
            classes.append({'type_name': name.strip(), 'type_id': href})
        return classes

    # ---------------- 接口 ----------------

    def homeContent(self, filter):
        html = self._get('/')
        result = {'class': self._menu_classes(html)}
        result['list'] = self._parse_cards(html)
        return result

    def homeVideoContent(self):
        try:
            vs = self._parse_cards(self._get('/'))
            return {'list': vs[:5]} if vs else None
        except Exception:
            return None

    def _cat_path(self, tid, pg):
        tid = tid.strip() or '/'
        pg = int(pg) if str(pg).isdigit() else 1
        if tid == '/':
            return '/' if pg <= 1 else f'/page/{pg}/'
        base = tid.rstrip('/')
        if base.startswith('/category/') or base.startswith('/tag/') or base.startswith('/search'):
            return base if pg <= 1 else f'{base}/{pg}/'
        # /order/* /communitys/* /date/* 用 page/N
        return base if pg <= 1 else f'{base}/page/{pg}/'

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if str(pg).isdigit() else 1
        try:
            html = self._get(self._cat_path(tid, pg))
            if tid.strip().startswith('/date/'):
                videos = self._parse_date_list(html)
            else:
                videos = self._parse_cards(html)
            total = self._pagecount(html)
        except Exception as e:
            self.log(f'[海角] categoryContent异常: {e}')
            videos, total = [], 0
        return {'list': videos, 'page': pg, 'pagecount': max(total, pg), 'limit': 30, 'total': total * 30}

    def detailContent(self, ids):
        raw = ids[0]
        path = raw if raw.startswith('/') else '/' + raw.split('/', 3)[-1] if raw.startswith('http') else raw
        html = self._get(path)
        mh = re.search(r'<h1[^>]*>([\s\S]*?)</h1>', html)
        title = re.sub(r'<[^>]+>', '', mh.group(1)).strip() if mh else '未知标题'
        vod = {'vod_id': raw, 'vod_name': title, 'vod_play_from': '海角社区'}

        # 分类与标签 -> 可点击跳转链接
        cat = re.search(r'data-video_type_name="([^"]+)"', html)
        mtags = re.search(r'data-video_tag_name="([^"]+)"', html)
        tags = [t.strip() for t in mtags.group(1).split(',') if t.strip()] if mtags else []
        clist = []
        if cat:
            clist.append(cat.group(1))
        for t in tags:
            href = f'/tag/{quote(t)}/'
            clist.append('[a=cr:' + json.dumps({'id': href, 'name': t}) + '/]' + t + '[/a]')
        vod['vod_content'] = ' '.join(clist) if clist else title
        vod['vod_remarks'] = cat.group(1) if cat else ''

        # 封面: og:image 是默认占位图时, 取正文第一张内容图
        mog = re.search(r'property="og:image" content="([^"]+)"', html)
        cover = ''
        if mog and 'default' not in mog.group(1):
            cover = mog.group(1)
        if not cover:
            mfirst = re.search(r'z-image-loader-url="`?(https?://[^`"\n]+?)`?"', html)
            if mfirst:
                cover = mfirst.group(1)
        if cover:
            vod['vod_pic'] = self._proxied_pic(cover)

        # 分集: 每个 .videoplayer.dplayer 的 data-config JSON
        plist = []
        n = 0
        for cfg_s in re.findall(r"data-config='([^']+)'", html):
            try:
                j = json.loads(cfg_s)
                vu = j.get('video', {}).get('url', '')
                if not vu:
                    continue
                n += 1
                plist.append(f'视频{n}${vu}')
            except Exception:
                continue
        vod['vod_play_url'] = '#'.join(plist) if plist else f'可能没有视频${self.host}{path}'
        return {'list': [vod]}

    def searchContent(self, key, quick, pg="1"):
        pg = int(pg) if str(pg).isdigit() else 1
        base = f'/search/{quote(key)}'
        try:
            html = self._get(base if pg <= 1 else f'{base}/{pg}/')
            return {'list': self._parse_cards(html), 'page': pg}
        except Exception as e:
            self.log(f'[海角] searchContent异常: {e}')
            return {'list': [], 'page': pg}

    def playerContent(self, flag, id, vipFlags):
        return {'parse': 0, 'url': id,
                'header': {'User-Agent': self.headers['User-Agent'], 'Referer': f'{self.host}/'}}

    # 图床互为镜像(同路径同加密), 原域失败时轮换重试
    IMG_HOSTS = ['images1.xiaona.run', 'pic.xustgq.cn']

    def _img_candidates(self, url):
        cands = [url]
        m = re.match(r'(https?://)([^/]+)(/.*)', url)
        if m:
            for host in self.IMG_HOSTS:
                alt = m.group(1) + host + m.group(3)
                if alt not in cands:
                    cands.append(alt)
        return cands

    def localProxy(self, param):
        """封面图转发: 图床返回AES加密数据需解密; 多图床镜像轮换"""
        try:
            if param.get('type', '') == 'img':
                url = self._d64(param.get('url', ''))
                if url:
                    last = None
                    for u in self._img_candidates(url)[:3]:
                        try:
                            r = requests.get(u, headers=self.headers, timeout=10)
                            if r.status_code != 200 or not r.content:
                                last = Exception(f'HTTP {r.status_code}')
                                continue
                            raw = r.content
                            # 已是明文图片直接透传, 否则AES解密(与老版51吸瓜同key)
                            if raw[:2] == b'\xff\xd8' or raw[:4] == b'\x89PNG' or (len(raw) > 12 and raw[8:12] == b'WEBP'):
                                img = raw
                            else:
                                try:
                                    img = self._aes_decrypt(raw, b'f5d965df75336270', b'97b60394abc2fbe1')
                                except Exception:
                                    img = raw
                            ct = ('image/jpeg' if img[:2] == b'\xff\xd8' else
                                  'image/png' if img[:4] == b'\x89PNG' else
                                  'image/webp' if len(img) > 12 and img[8:12] == b'WEBP' else 'application/octet-stream')
                            return [200, ct, img]
                        except Exception as e:
                            last = e
                    self.log(f'[海角] 图片代理失败 {url[:80]}: {last}')
        except Exception as e:
            self.log(f'[海角] localProxy异常: {e}')
        return [404, 'text/plain', '']
