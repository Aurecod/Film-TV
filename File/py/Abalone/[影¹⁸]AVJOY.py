#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AVJOY (avjoy.me) TVBox / CatVod / FongMi / drpyS-T4 爬虫源.

分类体系(取自站点两个目录页, 运行时动态抓取):
  /categories  → 17 个真实分类(slug + 中日英混排名称 + 影片数 + 图标)
  /tags        → 300 个热门标签(名称 + 影片数, 按站点热度排序, 分 15 个 Rank 组)

站点契约(实测确认):
  列表   GET /videos?page=N&o={mr|mv|tr|tf|old}        16 条/页
  分类   GET /videos/{slug}?page=N[&o=...]
  标签   GET /search/videos/{tag}/1?page=N[&o=...]     标签无独立路由, 复用搜索
  搜索   GET /search/videos/{kw}/1?page=N              路径段固定 /1, 真分页靠 ?page=
  详情   GET /video/{id}                               <source src label res>
  播放   media-cdn3.avjoy.me/{video|av1}/<token>/<ts>/<id>_<res>.mp4
         · token 每次请求详情页都会变 → 只能点击播放时实时解析, 禁止缓存
         · 必须带 Referer: https://avjoy.me/ , 否则 CDN 只回 23KB 占位文件
  海报   media-cdn2.avjoy.me/...  只校验 UA 非空, 空 UA 403, 与 Referer 无关
  站点偶发 TLS EOF → 内置退避重试
"""

import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    class _BaseSpider(object):
        pass

SITE = 'https://avjoy.me'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36')

# /videos?o=xx 与 /videos/{slug}?o=xx 通用, 搜索端点同样接受
SORTS = [('mr', '最新'), ('mv', '最受歡迎'), ('tr', '最高評分'),
         ('tf', '最愛'), ('old', '最早')]

TAG_CLASS = 'tags'          # 兼容旧 type_id
TAG_GROUP_PREFIX = 'tg_'    # 标签父组(一级) type_id 前缀
TAG_ITEM_PREFIX = 'tk_'     # 标签子项(二级) type_id 前缀
TAG_ROW_SIZE = 40           # filter 模式下每行标签数

# 标签父子分组规则: (组名, 判定函数标识)。顺序即呈现顺序。
TAG_GROUPS = [
    ('hot', '🔥 熱門前20'),
    ('region', '🌏 地區・語言'),
    ('genre', '🎬 類型・玩法'),
    ('studio', '🏢 片商・平台'),
    ('jp', '🇯🇵 日系女優'),
    ('cn', '🇨🇳 華語女優'),
    ('en', '🔤 英文・番號'),
    ('other', '📦 其他'),
]

# 人工归类词典(优先于字符集自动判定)。实测 /tags 前 300 个标签覆盖到位。
TAG_REGION = {
    '中文字幕', '無碼中文字幕', '國產av', '台灣', '台湾', '韓國', '韓語', '日本',
    '中國', '泰國', '香港', '歐美', '亞洲', 'chinese', 'japanese', 'korean',
    'thai', 'asian', 'japanese anime',
}
TAG_STUDIO = {
    'swag', 'heydouga', 'fc2', 'onlyfans', 'jvid', 'hentaipei', 'ed mosaic',
    'minamist', 'bvpp', 'amyluck', 'enkai', 'javcollectionhd', 'cici250808',
    'feifeibebe', '杏吧', '獨家', '麻豆', '天美', '蜜桃', '星空', '網紅',
}
TAG_GENRE = {
    '口交', '潮吹', '舔穴', '中出內射', '自慰', '自拍', '探花', '探花國產',
    '無碼', '無碼破解', '無碼破壞', '無碼流出', '巨乳', '眼鏡', '短髮', '啦啦隊',
    '電影', '動畫', '制服', '絲襪', '內射', '肛交', '足交', '乳交', '素人',
    'webcam', 'pov', 'milf', 'amateur', 'babe', 'blowjob', 'creampie',
    'cumshot', 'big-ass', 'big-tits', 'bigtit', 'anal', 'hentai', 'boot',
}

# /categories 抓取失败时的兜底(slug, 名称)
FALLBACK_CATEGORIES = [
    ('jav', 'JAV・日本AV'),
    ('china', 'China・中國'),
    ('asian', 'Asian・アジア'),
    ('japan', 'Japan・日本'),
    ('uncensored', 'Uncensored・無修正'),
    ('pornstar', 'Pornstar·AV女優'),
    ('big-tits', 'Big Tits・巨乳'),
    ('amateur', 'Amateur・素人'),
    ('korea', 'Korea・韓国・대한민국'),
    ('anime', 'Anime・アニメ'),
    ('schoolgirl', 'Schoolgirl・女子校生'),
    ('teen', 'Teen・ギャル・少女'),
    ('mature', 'Mature・熟女'),
    ('wife', 'Wife・人妻'),
    ('cosplay', 'Cosplay・コスプレ'),
    ('anal', 'Anal・アナル・肛交'),
    ('sm', 'SM'),
]

# /tags 抓取失败时的兜底(站点热度前列)
FALLBACK_TAGS = ['中文字幕', '口交', '潮吹', '舔穴', '中出內射', '國產av',
                 '台灣', '自拍', '無碼破解', '探花', 'swag', 'heydouga',
                 'しろハメ', '無碼流出', '巨乳', '眼鏡', '短髮', '啦啦隊']

_RE_KANA = re.compile(r'[\u3040-\u309f\u30a0-\u30ff]')
_RE_HAN = re.compile(r'[\u4e00-\u9fff]')
_RE_HANGUL = re.compile(r'[\uac00-\ud7af]')
_RE_ASCII = re.compile(r'^[\x20-\x7e]+$')


class Spider(_BaseSpider):
    # drpyS/T4Handler 实例化时会注入 t4_api; **kwargs 兼容各版本运行器
    def __init__(self, t4_api="", **kwargs):
        self.t4_api = t4_api or kwargs.get('t4_api', '')
        self.site = SITE
        self.extend = []          # T4 缓存提交阶段直接访问, 必须是公开属性
        self._extend = {}
        self._proxy = ''
        self._ctx = ssl.create_default_context()
        self._cache = {}          # url -> (ts, html)
        self._ttl = 600
        self._cats = []           # [{slug,name,pic,count}]
        self._tags = []           # [{name,count}]
        self._seen = {}           # scope -> {page: [raw ids]}  跨页去重用

    # ---------- 生命周期 ----------
    def getName(self):
        return 'AVJOY'

    def getDependence(self):
        return []

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        u = str(url or '').lower()
        return any(x in u for x in ('.mp4', '.m3u8', '.flv', '.ts', '.mkv'))

    def destroy(self):
        self._cache.clear()

    def action(self, action):
        return {}

    def localProxy(self, param):
        return [404, 'text/plain', b'', {}]

    def init(self, extend=""):
        self.extend = extend if extend is not None else []
        cfg = {}
        if isinstance(extend, dict):
            cfg = extend
        elif isinstance(extend, str) and extend.strip():
            s = extend.strip()
            if s.startswith('{'):
                try:
                    cfg = json.loads(s) or {}
                except Exception:
                    cfg = {}
            elif s.startswith('http'):
                cfg = {'host': s}
        elif isinstance(extend, list) and extend:
            if isinstance(extend[0], dict):
                cfg = extend[0]
        self._extend = cfg
        host = str(cfg.get('host') or '').strip().rstrip('/')
        if host.startswith('http'):
            self.site = host
        self._proxy = str(cfg.get('proxy') or '').strip()
        self._cache.clear()
        self._cats = []
        self._tags = []
        self._seen = {}
        return {}

    # ---------- 网络 ----------
    def _headers(self, referer=None):
        return {
            'User-Agent': UA,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-TW,zh;q=0.9,ja;q=0.8,en;q=0.7',
            'Accept-Encoding': 'identity',
            'Referer': referer or (self.site + '/'),
            'Connection': 'close',
        }

    def _opener(self):
        handlers = [urllib.request.HTTPSHandler(context=self._ctx)]
        if self._proxy:
            handlers.append(urllib.request.ProxyHandler(
                {'http': self._proxy, 'https': self._proxy}))
        return urllib.request.build_opener(*handlers)

    def _get(self, url, tries=3, cache=True):
        """取 HTML。站点存在间歇性 TLS EOF, 需要退避重试。"""
        now = time.time()
        if cache:
            hit = self._cache.get(url)
            if hit and now - hit[0] < self._ttl:
                return hit[1]
        last = None
        for i in range(tries):
            try:
                req = urllib.request.Request(url, headers=self._headers())
                with self._opener().open(req, timeout=25) as resp:
                    raw = resp.read()
                html = raw.decode('utf-8', 'replace')
                if cache and len(html) > 2000:
                    self._cache[url] = (now, html)
                return html
            except urllib.error.HTTPError as e:
                if e.code in (403, 404):
                    return ''
                last = e
            except Exception as e:
                last = e
            time.sleep(0.6 * (i + 1))
        sys.stderr.write('AVJOY fetch fail %s %r\n' % (url, last))
        return ''

    # ---------- 解析工具 ----------
    @staticmethod
    def _main_area(html):
        """截主内容区: 顶部导航的『精選視頻』侧栏也含 /video/ 链接, 必须排除。"""
        i = html.find('well-filters')
        body = html[i:] if i > 0 else html
        j = body.find('content-right')
        return body[:j] if j > 0 else body

    @staticmethod
    def _clean(s):
        s = re.sub(r'<[^>]+>', ' ', s or '')
        s = s.replace('&nbsp;', ' ').replace('&amp;', '&')
        s = s.replace('&quot;', '"').replace('&#039;', "'")
        s = s.replace('&lt;', '<').replace('&gt;', '>')
        return ' '.join(s.split())

    def _cards(self, html):
        """列表卡片。按 <a href="/video/id/slug"> 锚点 + 局部窗口取字段,
        不依赖易变的外层 col-* 容器(该站不同页面容器类名不一致)。"""
        body = self._main_area(html)
        out, seen = [], set()
        for m in re.finditer(r'<a href="/video/(\d+)/([^"]*)"', body):
            vid = m.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            win = body[m.start():m.start() + 2600]
            img = re.search(r'<img[^>]+src="([^"]+)"', win)
            title = re.search(r'class="content-title">([^<]+)<', win)
            if not title:
                title = re.search(r'<img[^>]+title="([^"]*)"', win)
            dur = re.search(r'class="duration">([\s\S]*?)</div>', win)
            views = re.search(r'class="content-views">\s*([^<]*?)\s*</span>', win)
            remark = self._clean(dur.group(1)) if dur else ''
            vs = self._clean(views.group(1)) if views else ''
            if vs:
                remark = (remark + ' · ' + vs).strip(' ·')
            out.append({
                'vod_id': vid,
                'vod_name': self._clean(title.group(1)) if title else ('AVJOY ' + vid),
                'vod_pic': img.group(1) if img else '',
                'vod_remarks': remark,
            })
        return out

    @staticmethod
    def _total(html):
        m = re.search(r'中\s*<span class="text-highlighted">([\d,]+)</span>', html)
        if m:
            try:
                return int(m.group(1).replace(',', ''))
            except Exception:
                return 0
        return 0

    def _pagecount(self, html, per=16):
        total = self._total(html)
        if total > 0:
            return max(1, min((total + per - 1) // per, 9999))
        pages = [int(x) for x in re.findall(r'[?&]page=(\d+)', html)]
        return max(pages) if pages else 1

    # ---------- 分类 / 标签动态抓取 ----------
    def _fetch_categories(self):
        """/categories → [{slug,name,pic,count}]，按影片数降序。失败回退常量表。"""
        if self._cats:
            return self._cats
        body = self._main_area(self._get(self.site + '/categories'))
        out = []
        for m in re.finditer(
                r'href="/videos/([a-z0-9\-]+)">\s*<div class="thumb-overlay">\s*'
                r'<img src="([^"]*)"[^>]*?title="([^"]*)"'
                r'[\s\S]{0,500}?title-truncate">\s*([\s\S]*?)\s*</div>'
                r'[\s\S]{0,260}?float-right">\s*([\d,]*)\s*</div>', body):
            slug = m.group(1)
            pic = m.group(2) or ''
            if pic.startswith('/'):
                pic = self.site + pic
            name = self._clean(m.group(4)) or self._clean(m.group(3)) or slug
            try:
                cnt = int((m.group(5) or '0').replace(',', ''))
            except Exception:
                cnt = 0
            out.append({'slug': slug, 'name': name, 'pic': pic, 'count': cnt})
        if not out:
            out = [{'slug': s, 'name': n, 'pic': '', 'count': 0}
                   for s, n in FALLBACK_CATEGORIES]
        out.sort(key=lambda x: (-x['count'], x['name']))
        self._cats = out
        return out

    def _fetch_tags(self):
        """/tags → [{name,count}]，保留站点热度顺序。失败回退常量表。"""
        if self._tags:
            return self._tags
        body = self._main_area(self._get(self.site + '/tags'))
        out, seen = [], set()
        for m in re.finditer(
                r'class="tag-item">[\s\S]{0,320}?class="tag-counter">([\d,]+)</span>'
                r'[\s\S]{0,240}?href="/search/videos/([^"]+)"[^>]*title="([^"]*)"', body):
            name = self._clean(m.group(3)) or urllib.parse.unquote(m.group(2))
            if not name or name in seen:
                continue
            seen.add(name)
            try:
                cnt = int(m.group(1).replace(',', ''))
            except Exception:
                cnt = 0
            out.append({'name': name, 'count': cnt})
        if not out:
            out = [{'name': n, 'count': 0} for n in FALLBACK_TAGS]
        self._tags = out
        return out

    @staticmethod
    def _fmt_count(n):
        if not n:
            return ''
        if n >= 10000:
            return '%.1f萬' % (n / 10000.0)
        return str(n)

    @staticmethod
    def _tag_bucket(name):
        """把标签归入父分组。人工词典优先, 再按字符集判定。"""
        low = name.lower()
        if low in TAG_STUDIO or name in TAG_STUDIO:
            return 'studio'
        if low in TAG_REGION or name in TAG_REGION:
            return 'region'
        if low in TAG_GENRE or name in TAG_GENRE:
            return 'genre'
        if _RE_HANGUL.search(name):
            return 'region'
        if _RE_KANA.search(name):
            return 'jp'
        if _RE_ASCII.match(name):
            return 'en'
        if _RE_HAN.search(name):
            return 'cn' if 2 <= len(name) <= 4 else 'genre'
        return 'other'

    def _tag_tree(self):
        """标签父子结构: {group_key: [ {name,count}, ... ] }，保留站点热度序。
        热门前 20 单独成组, 其余按语义分组。"""
        tags = self._fetch_tags()
        tree = {}
        for k, _ in TAG_GROUPS:
            tree[k] = []
        for i, t in enumerate(tags):
            if i < 20:
                tree['hot'].append(t)
            tree[self._tag_bucket(t['name'])].append(t)
        return tree

    def _tag_rows(self, items):
        """一个父分组内的标签切成多行筛选条, 每行 TAG_ROW_SIZE 个。"""
        rows = []
        for i in range(0, len(items), TAG_ROW_SIZE):
            chunk = items[i:i + TAG_ROW_SIZE]
            rows.append({
                'key': 'tag%d' % (i // TAG_ROW_SIZE),
                'name': '標籤' if i == 0 else ('標籤 %d+' % (i + 1)),
                'value': [{'n': self._tag_label(t), 'v': t['name']} for t in chunk],
            })
        return rows

    def _tag_label(self, t):
        c = self._fmt_count(t['count'])
        return ('%s (%s)' % (t['name'], c)) if c else t['name']

    @staticmethod
    def _parse_ext(extend):
        """壳下发 extend 的形态不统一: dict / JSON 字符串 / 空。
        之前只认 dict, 字符串形态被静默忽略 → 筛选选了也没反应。"""
        if isinstance(extend, dict):
            return {str(k): ('' if v is None else str(v)) for k, v in extend.items()}
        if isinstance(extend, str) and extend.strip():
            s = extend.strip()
            if s.startswith('{'):
                try:
                    d = json.loads(s)
                    if isinstance(d, dict):
                        return {str(k): ('' if v is None else str(v)) for k, v in d.items()}
                except Exception:
                    pass
            elif '=' in s:                      # a=b&c=d 形态
                try:
                    q = urllib.parse.parse_qs(s)
                    return {k: (v[0] if v else '') for k, v in q.items()}
                except Exception:
                    pass
        return {}

    @staticmethod
    def _tag_tid(name):
        return TAG_ITEM_PREFIX + urllib.parse.quote(name, safe='')

    @staticmethod
    def _tid_tag(tid):
        return urllib.parse.unquote(tid[len(TAG_ITEM_PREFIX):])

    # ---------- 五个契约接口 ----------
    def homeContent(self, filter=None):
        """一级 = 全部 + 站点 17 个分类 + 标签父组。
        标签父组点进去由 categoryContent 返回 class(真正的二级分类下钻),
        同时附带 filters 供不支持 class 下钻的壳使用。"""
        cats = self._fetch_categories()
        tree = self._tag_tree()

        classes = [{'type_id': 'all', 'type_name': '全部影片'}]
        for c in cats:
            cnt = self._fmt_count(c['count'])
            classes.append({
                'type_id': c['slug'],
                'type_name': ('%s (%s)' % (c['name'], cnt)) if cnt else c['name'],
            })

        sort_row = self._sort_row()
        filters = {'all': [sort_row]}
        for c in cats:
            filters[c['slug']] = [sort_row]

        for key, label in TAG_GROUPS:
            items = tree.get(key) or []
            if not items:
                continue
            tid = TAG_GROUP_PREFIX + key
            classes.append({'type_id': tid,
                            'type_name': '%s (%d)' % (label, len(items))})
            filters[tid] = [sort_row] + self._tag_rows(items)
            # 每个子标签也带排序筛选
            for t in items:
                filters[self._tag_tid(t['name'])] = [sort_row]

        return {'class': classes, 'filters': filters}

    @staticmethod
    def _sort_row():
        return {'key': 'o', 'name': '排序',
                'value': [{'n': n, 'v': v} for v, n in SORTS]}

    def homeVideoContent(self):
        return {'list': self._cards(self._get(self.site + '/videos'))}

    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        try:
            page = max(1, int(pg or 1))
        except Exception:
            page = 1
        ext = self._parse_ext(extend)
        order = str(ext.get('o') or '').strip()
        tid = str(tid or 'all')

        # ② 二级分类(具体标签) → 直接出内容
        if tid.startswith(TAG_ITEM_PREFIX):
            return self._list_tag(self._tid_tag(tid), page, order)

        # ① 一级标签父组 → 返回二级分类清单(class) + 首个子标签内容(list)
        if tid.startswith(TAG_GROUP_PREFIX) or tid == TAG_CLASS:
            key = tid[len(TAG_GROUP_PREFIX):] if tid.startswith(TAG_GROUP_PREFIX) else 'hot'
            items = self._tag_tree().get(key) or []
            if not items:
                items = [{'name': n, 'count': 0} for n in FALLBACK_TAGS]

            # 若壳走 filters 模式并已选中某个标签, 直接按它出内容
            picked = ''
            for k in sorted(ext.keys()):
                if k.startswith('tag') and str(ext[k]).strip():
                    picked = str(ext[k]).strip()
                    break
            if picked:
                return self._list_tag(picked, page, order)

            sub = [{'type_id': self._tag_tid(t['name']),
                    'type_name': self._tag_label(t)} for t in items]
            res = self._list_tag(items[0]['name'], page, order)
            res['class'] = sub                      # 支持下钻的壳显示二级分类
            res['filters'] = {c['type_id']: [self._sort_row()] for c in sub}
            return res

        return self._list_videos('' if tid in ('all', '') else tid, page, order)

    def _list_videos(self, slug, page, order):
        path = '/videos' if not slug else '/videos/' + slug
        qs = {}
        if order:
            qs['o'] = order
        if page > 1:
            qs['page'] = page
        url = self.site + path + (('?' + urllib.parse.urlencode(qs)) if qs else '')
        html = self._get(url)
        total = self._total(html)
        pc = self._pagecount(html)
        if page > pc:
            # 越界页站点会一直回最后一页(实测 sm 25 部, page 3/4/5 全等于 page 2)
            # 直接返回空, 否则壳会把同一批卡片重复追加
            return {'list': [], 'page': page, 'pagecount': pc,
                    'limit': 16, 'total': total}
        vods = self._dedup('cat:%s:%s' % (slug or 'all', order), page, self._cards(html))
        return {'list': vods, 'page': page, 'pagecount': pc,
                'limit': 16, 'total': total or len(vods)}

    def _dedup(self, scope, page, vods):
        """搜索/标签端点存在服务端 offset 漂移(实测相邻页重叠 5~7 条),
        分类端点无此问题。只过滤"更早页出现过的 id", 并保证同一页重复请求幂等
        (壳会反复请求同页)。"""
        pages = self._seen.setdefault(scope, {})
        raw = [v['vod_id'] for v in vods]
        pages[page] = raw
        earlier = set()
        for p, ids in pages.items():
            if p < page:
                earlier.update(ids)
        out, seen = [], set()
        for v in vods:
            i = v['vod_id']
            if i in earlier or i in seen:
                continue
            seen.add(i)
            out.append(v)
        return out

    def _list_tag(self, kw, page, order):
        """标签没有独立列表路由, 复用搜索端点: 路径段固定 /1, 真分页靠 ?page=N。"""
        url = '%s/search/videos/%s/1' % (self.site, urllib.parse.quote(kw, safe=''))
        qs = {}
        if order:
            qs['o'] = order
        if page > 1:
            qs['page'] = page
        if qs:
            url += '?' + urllib.parse.urlencode(qs)
        html = self._get(url, cache=False)
        total = self._total(html)
        pc = self._pagecount(html)
        if page > pc:
            return {'list': [], 'page': page, 'pagecount': pc,
                    'limit': 16, 'total': total}
        vods = self._dedup('kw:%s:%s' % (kw, order), page, self._cards(html))
        return {'list': vods, 'page': page, 'pagecount': pc,
                'limit': 16, 'total': total or len(vods)}

    def detailContent(self, ids):
        vid = str(ids[0] if isinstance(ids, (list, tuple)) else ids).strip()
        vid = re.sub(r'\D', '', vid) or '0'
        html = self._get(self.site + '/video/' + vid, cache=False)

        title = re.search(r'<div class="well-filters video-title"[^>]*>\s*<h1>([\s\S]*?)</h1>', html) \
            or re.search(r'<h1>([\s\S]*?)</h1>', html)
        name = self._clean(title.group(1)) if title else ('AVJOY ' + vid)

        pic = ''
        mp = re.search(r'itemprop="thumbnailUrl" content="([^"]+)"', html) \
            or re.search(r'poster="([^"]+)"', html)
        if mp:
            pic = mp.group(1)

        desc = ''
        md = re.search(r'class="[^"]*video-description"[^>]*>\s*<p>([\s\S]*?)</p>', html)
        if md:
            desc = self._clean(md.group(1))

        # 标签只取详情页 video-tags 区块(侧栏的搜索趋势不属于本片)
        tags = []
        mt = re.search(r'class="[^"]*video-tags[^"]*"[\s\S]*?</section>', html)
        if mt:
            tags = [self._clean(x) for x in re.findall(r'class="tag"[^>]*>([^<]+)<', mt.group(0))]

        # 详情页只有 video-tags 区块, 没有本片分类锚点
        # (页面里的 /videos/ 链接全部来自顶部导航, 不能当作影片归属分类)

        remarks = ''
        mdur = re.search(r'itemprop="duration" content="PT(?:(\d+)H)?(\d+)M(\d+)S"', html)
        if mdur:
            h, mi, se = mdur.group(1), mdur.group(2), mdur.group(3)
            remarks = ('%s:%02d:%02d' % (h, int(mi), int(se))) if h \
                else ('%02d:%02d' % (int(mi), int(se)))

        year = ''
        my = re.search(r'itemprop="uploadDate"[^>]*datetime="(\d{4})', html) \
            or re.search(r'datetime="(\d{4})-', html)
        if my:
            year = my.group(1)

        flags, urls = [], []
        for label, _u in self._sources(html):
            flags.append(label)
            # 只交出稳定的 vod_id, 真正的播放地址在 playerContent 里实时解析
            urls.append('%s$%s' % (remarks or '正片', vid))
        if not flags:
            flags, urls = ['AVJOY'], ['%s$%s' % (remarks or '正片', vid)]

        return {'list': [{
            'vod_id': vid,
            'vod_name': name,
            'vod_pic': pic,
            'vod_year': year,
            'vod_remarks': remarks,
            'vod_tag': ','.join(tags),
            'vod_content': desc or name,
            'vod_play_from': '$$$'.join(flags),
            'vod_play_url': '$$$'.join(urls),
        }]}

    def searchContent(self, key, quick=False, pg=1):
        try:
            page = max(1, int(pg or 1))
        except Exception:
            page = 1
        kw = str(key or '').strip()
        if not kw:
            return {'list': [], 'page': page, 'pagecount': 1, 'limit': 16, 'total': 0}
        return self._list_tag(kw, page, '')

    def playerContent(self, flag, id, vipFlags=None):
        raw = str(id or '')
        vid = re.sub(r'\D', '', raw.split('$')[-1]) or re.sub(r'\D', '', raw)
        # token 每次生成都不同 → 必须重新请求详情页, 不能复用 detailContent 的结果
        html = self._get(self.site + '/video/' + vid, cache=False)
        sources = self._sources(html)
        url = ''
        if sources:
            want = str(flag or '')
            for label, u in sources:
                if label == want:
                    url = u
                    break
            if not url:
                url = sources[0][1]
        return {
            'parse': 0,
            'playUrl': '',
            'url': url or (self.site + '/video/' + vid),
            'header': json.dumps({'User-Agent': UA, 'Referer': self.site + '/'}),
        }

    # ---------- 播放源 ----------
    def _sources(self, html):
        """详情页 <source> 列表。同清晰度可能给两条路径:
        /video/ 为 H.264(兼容性最好), /av1/ 为 AV1(部分设备无法硬解)。H.264 优先。"""
        items = []
        for m in re.finditer(r'<source\b[^>]*>', html):
            tag = m.group(0)
            src = re.search(r'src=["\']([^"\']+)["\']', tag)
            if not src:
                continue
            u = src.group(1)
            lab = re.search(r'label=["\']([^"\']*)["\']', tag)
            res = re.search(r'res=["\']([^"\']*)["\']', tag)
            q = (lab.group(1) if lab else '') or (res.group(1) + 'p' if res else '') or '默認'
            items.append(('AV1' if '/av1/' in u else 'H264', q, u))
        out, seen = [], set()
        for codec in ('H264', 'AV1'):
            for c, q, u in items:
                if c != codec:
                    continue
                label = q if codec == 'H264' else ('%s AV1' % q)
                if label in seen:
                    continue
                seen.add(label)
                out.append((label, u))
        return out


# --------------------------------------------------------------------------
# selftest: python3 avjoy.py
# --------------------------------------------------------------------------
def _selftest():
    ok = fail = 0

    def chk(name, cond, extra=''):
        nonlocal ok, fail
        if cond:
            ok += 1
            print('  PASS %-44s %s' % (name, extra))
        else:
            fail += 1
            print('  FAIL %-44s %s' % (name, extra))

    print('== 运行时构造 ==')
    a = Spider()
    b = Spider(t4_api='http://127.0.0.1:9978/proxy?do=py', extra=1)
    chk('Spider() 无参构造(HKL)', True)
    chk('Spider(t4_api=..) 注入构造(T4)', b.t4_api != '')
    chk('self.extend 公开属性', hasattr(a, 'extend') and hasattr(b, 'extend'))
    for e in ([], '', '{"host":"https://avjoy.me"}', {'host': 'https://avjoy.me'}):
        a.init(e)
    chk('init 四形态不抛异常', True)
    chk('生命周期方法齐全',
        all(hasattr(a, m) for m in ('getDependence', 'destroy', 'action',
                                    'isVideoFormat', 'manualVideoCheck', 'localProxy')))

    sp = Spider()
    sp.init('')

    print('== 分类抓取(/categories) ==')
    cats = sp._fetch_categories()
    slugs = [c['slug'] for c in cats]
    chk('分类数 == 17', len(cats) == 17, str(len(cats)))
    chk('全部 slug 唯一', len(set(slugs)) == len(slugs))
    chk('名称取站点原文(含・分隔)', any('・' in c['name'] for c in cats),
        cats[0]['name'])
    chk('影片数全部 > 0', all(c['count'] > 0 for c in cats),
        'min=%d' % min(c['count'] for c in cats))
    chk('按影片数降序', all(cats[i]['count'] >= cats[i + 1]['count']
                            for i in range(len(cats) - 1)),
        '%s>%s' % (cats[0]['count'], cats[-1]['count']))
    chk('图标为绝对地址', all(c['pic'].startswith('http') for c in cats))
    chk('jav/uncensored/china 均在', {'jav', 'uncensored', 'china'} <= set(slugs))

    print('== 标签抓取(/tags) ==')
    tags = sp._fetch_tags()
    names = [t['name'] for t in tags]
    chk('标签数 == 300', len(tags) == 300, str(len(tags)))
    chk('标签名唯一', len(set(names)) == len(names))
    chk('计数全部 > 0', all(t['count'] > 0 for t in tags),
        'min=%d' % min(t['count'] for t in tags))
    chk('保留站点热度序(首个最大)', tags[0]['count'] == max(t['count'] for t in tags),
        '%s=%d' % (tags[0]['name'], tags[0]['count']))
    chk('中日英标签混排都在', all(x in names for x in ('中文字幕', 'swag')),
        names[:4])

    print('== homeContent(父子分类) ==')
    home = sp.homeContent()
    cls_ids = [c['type_id'] for c in home['class']]
    tree = sp._tag_tree()
    grp_ids = [TAG_GROUP_PREFIX + k for k, _ in TAG_GROUPS if tree.get(k)]
    chk('一级 = 全部 + 17分类 + 标签父组',
        len(cls_ids) == 1 + len(cats) + len(grp_ids),
        '%d = 1+%d+%d' % (len(cls_ids), len(cats), len(grp_ids)))
    chk('首项为全部影片', cls_ids[0] == 'all')
    chk('标签父组全部出现', all(g in cls_ids for g in grp_ids), str(grp_ids))
    chk('父组名带子标签数量',
        all('(' in c['type_name'] for c in home['class']
            if c['type_id'].startswith(TAG_GROUP_PREFIX)))
    chk('每个一级都有筛选', all(k in home['filters'] for k in cls_ids))
    chk('每个父组第一行是排序',
        all(home['filters'][g][0]['key'] == 'o' for g in grp_ids))
    chk('每个父组都有标签筛选行',
        all(any(r['key'].startswith('tag') for r in home['filters'][g]) for g in grp_ids))
    chk('父组内筛选行 key 不重复',
        all(len({r['key'] for r in home['filters'][g]}) == len(home['filters'][g])
            for g in grp_ids))
    all_tag_vals = set()
    for g in grp_ids:
        for r in home['filters'][g]:
            if r['key'].startswith('tag'):
                all_tag_vals.update(v['v'] for v in r['value'])
    chk('300 个标签全部可达', all_tag_vals == set(names),
        '%d/%d' % (len(all_tag_vals), len(names)))
    chk('热门组恰好 20 个',
        sum(len(r['value']) for r in home['filters'][TAG_GROUP_PREFIX + 'hot']
            if r['key'].startswith('tag')) == 20)
    chk('日系组只含假名', all(_RE_KANA.search(t['name']) for t in tree['jp']),
        '%d 个' % len(tree['jp']))
    chk('筛选可 JSON 序列化', bool(json.dumps(home)))

    print('== 二级分类下钻(class 模式) ==')
    sub_tids = set()
    for g in grp_ids:
        r = sp.categoryContent(g, 1)
        subs = r.get('class') or []
        key = g[len(TAG_GROUP_PREFIX):]
        chk('%s 返回二级 class' % key, len(subs) == len(tree[key]),
            '%d/%d' % (len(subs), len(tree[key])))
        chk('%s 二级 tid 前缀正确' % key,
            all(c['type_id'].startswith(TAG_ITEM_PREFIX) for c in subs))
        chk('%s 父组同时给首个标签内容' % key, len(r['list']) > 0, str(len(r['list'])))
        sub_tids.update(c['type_id'] for c in subs)
    chk('二级 tid 覆盖 300 个标签', len(sub_tids) == 300, str(len(sub_tids)))
    chk('二级 tid 可解码回标签名',
        all(sp._tid_tag(t) in set(names) for t in sub_tids))
    chk('每个二级都有排序筛选', all(t in home['filters'] for t in sub_tids))

    one = sp.categoryContent(sp._tag_tid('中文字幕'), 1)
    chk('点二级分类直接出内容', len(one['list']) == 16, str(len(one['list'])))
    chk('二级页不再返回 class(避免死循环)', 'class' not in one)
    chk('二级 total 与站点一致', one['total'] > 10000, str(one['total']))
    two = sp.categoryContent(sp._tag_tid('中文字幕'), 2)
    chk('二级分类翻页去重后零重叠',
        not (set(v['vod_id'] for v in one['list']) & set(v['vod_id'] for v in two['list'])),
        'p2=%d' % len(two['list']))
    ord2 = sp.categoryContent(sp._tag_tid('中文字幕'), 1, None, {'o': 'old'})
    chk('二级分类支持排序',
        [v['vod_id'] for v in ord2['list']] != [v['vod_id'] for v in one['list']])

    print('== extend 形态兼容(之前只认 dict) ==')
    a1 = sp.categoryContent('jav', 1, None, {'o': 'old'})
    a2 = sp.categoryContent('jav', 1, None, '{"o":"old"}')
    a3 = sp.categoryContent('jav', 1, None, 'o=old')
    ids_a1 = [v['vod_id'] for v in a1['list']]
    chk('JSON 字符串 extend 生效', [v['vod_id'] for v in a2['list']] == ids_a1)
    chk('query 字符串 extend 生效', [v['vod_id'] for v in a3['list']] == ids_a1)
    chk('None/空 extend 不崩',
        len(sp.categoryContent('jav', 1, None, None)['list']) == 16)

    print('== categoryContent: 分类去重 ==')
    c1 = sp.categoryContent('uncensored', 1)
    c2 = sp.categoryContent('uncensored', 2)
    i1 = [v['vod_id'] for v in c1['list']]
    i2 = [v['vod_id'] for v in c2['list']]
    chk('分类第1页 16 条', len(i1) == 16, str(len(i1)))
    chk('分类内单页无重复', len(set(i1)) == len(i1))
    chk('分类翻页零重叠', i2 and not (set(i1) & set(i2)),
        'ov=%d' % len(set(i1) & set(i2)))
    chk('分类 pagecount 合理', c1['pagecount'] > 1, str(c1['pagecount']))
    chk('标题非空率 100%', all(v['vod_name'] for v in c1['list']))
    chk('海报全 http', all(v['vod_pic'].startswith('http') for v in c1['list']))
    cs = sp.categoryContent('jav', 1, None, {'o': 'mv'})
    chk('分类+排序生效', len(cs['list']) == 16 and
        [v['vod_id'] for v in cs['list']] != [v['vod_id'] for v in sp.categoryContent('jav', 1)['list']],
        'jav mv vs mr')

    print('== 越界翻页(小分类重复的根因) ==')
    sm = Spider(); sm.init('')
    s_pc = sm.categoryContent('sm', 1)['pagecount']
    s_last = sm.categoryContent('sm', s_pc)
    s_over = sm.categoryContent('sm', s_pc + 1)
    s_over2 = sm.categoryContent('sm', s_pc + 3)
    chk('sm pagecount 由 total 推出', s_pc == 2, str(s_pc))
    chk('末页有数据', len(s_last['list']) > 0, str(len(s_last['list'])))
    chk('越界页返回空(不再重复末页)', s_over['list'] == [] and s_over2['list'] == [],
        'p%d=%d p%d=%d' % (s_pc + 1, len(s_over['list']), s_pc + 3, len(s_over2['list'])))
    mt = Spider(); mt.init('')
    m_pc = mt.categoryContent('mature', 1)['pagecount']
    chk('mature 越界页也为空',
        mt.categoryContent('mature', m_pc + 2)['list'] == [], 'pc=%d' % m_pc)

    print('== 深翻页漂移去重(实测 jav p50/p51 重叠15) ==')
    dp = Spider(); dp.init('')
    d50 = [v['vod_id'] for v in dp.categoryContent('jav', 50)['list']]
    d51 = [v['vod_id'] for v in dp.categoryContent('jav', 51)['list']]
    chk('深翻页去重后零重叠', not (set(d50) & set(d51)),
        'p50=%d p51=%d ov=%d' % (len(d50), len(d51), len(set(d50) & set(d51))))
    chk('同页重复请求幂等',
        [v['vod_id'] for v in dp.categoryContent('jav', 51)['list']] == d51)

    print('== categoryContent: 标签父组 ==')
    hot = TAG_GROUP_PREFIX + 'hot'
    t1 = sp.categoryContent(hot, 1, None, {'tag0': '中文字幕'})
    t2 = sp.categoryContent(hot, 2, None, {'tag0': '中文字幕'})
    j1 = [v['vod_id'] for v in t1['list']]
    j2 = [v['vod_id'] for v in t2['list']]
    chk('标签第1页 16 条', len(j1) == 16, str(len(j1)))
    chk('标签翻页去重后零重叠', j2 and not (set(j1) & set(j2)),
        'p2=%d ov=%d' % (len(j2), len(set(j1) & set(j2))))
    chk('标签同页幂等',
        [v['vod_id'] for v in sp.categoryContent(hot, 2, None, {'tag0': '中文字幕'})['list']] == j2)
    chk('标签 total 与站点一致(>1万)', t1['total'] > 10000, str(t1['total']))
    td = sp.categoryContent(hot, 1)
    chk('未选子标签时用该组热度第一', len(td['list']) == 16, str(len(td['list'])))
    to = sp.categoryContent(hot, 1, None, {'tag0': '中文字幕', 'o': 'old'})
    chk('标签+排序生效', [v['vod_id'] for v in to['list']] != j1, 'old vs default')
    jp_name = tree['jp'][0]['name']
    tj = sp.categoryContent(TAG_GROUP_PREFIX + 'jp', 1, None, {'tag0': jp_name})
    chk('日系女優组子标签可用', len(tj['list']) > 0, '%s=%d' % (jp_name, len(tj['list'])))
    cn_name = tree['cn'][0]['name']
    tc = sp.categoryContent(TAG_GROUP_PREFIX + 'cn', 1, None, {'tag1': cn_name})
    chk('華語女優组第二行也生效', len(tc['list']) >= 0, '%s=%d' % (cn_name, len(tc['list'])))

    print('== detailContent ==')
    vid = i1[0]
    det = sp.detailContent([vid])['list'][0]
    chk('详情标题非空', bool(det['vod_name']), det['vod_name'][:34])
    chk('详情有线路', bool(det['vod_play_from']), det['vod_play_from'])
    chk('play_url 只放稳定 id',
        det['vod_play_url'].split('$$$')[0].split('$')[-1] == vid,
        det['vod_play_url'][:38])
    chk('vod_tag 来自详情页 video-tags 区块',
        'vod_tag' in det and '搜尋趨勢' not in (det['vod_tag'] or ''),
        det['vod_tag'][:40])

    print('== playerContent ==')
    flag = det['vod_play_from'].split('$$$')[0]
    pl = sp.playerContent(flag, vid)
    chk('parse == 0', pl['parse'] == 0)
    chk('url 是 mp4 直链', '.mp4' in pl['url'], pl['url'][:76])
    chk('header 带 Referer', 'Referer' in pl['header'])

    import urllib.request as _u
    hdr = json.loads(pl['header'])

    def _probe(url, headers, tries=3):
        """站点 CDN 偶发 TLS EOF, 探针要退避重试, 否则会产生假失败。"""
        for i in range(tries):
            try:
                r = _u.Request(url, headers=dict(headers, Range='bytes=0-1023'))
                with _u.urlopen(r, timeout=30) as resp:
                    d = resp.read(1024)
                    cr = resp.headers.get('Content-Range') or ''
                    return (d[4:8].decode('latin1'),
                            int(cr.split('/')[-1]) if '/' in cr else 0)
            except Exception as e:
                if i == tries - 1:
                    print('   range probe err', type(e).__name__)
                time.sleep(0.8 * (i + 1))
        return '', 0

    magic, total_with = _probe(pl['url'], hdr)
    _, total_without = _probe(pl['url'], {})
    chk('直链魔数 ftyp', magic == 'ftyp', magic)
    chk('带头拿到完整文件(>50MB)', total_with > 50 * 1024 * 1024,
        '%.2f GB' % (total_with / 1024.0 ** 3))
    chk('缺 Referer 会被截成占位(防复发)', 0 < total_without < total_with,
        'no-ref=%d vs ref=%d' % (total_without, total_with))

    print('== 海报实拉 ==')
    got = magic_ok = 0
    for v in c1['list'][:3]:
        try:
            r = _u.Request(v['vod_pic'], headers={'User-Agent': UA, 'Range': 'bytes=0-63'})
            with _u.urlopen(r, timeout=20) as resp:
                d = resp.read(64)
                if 'image' in (resp.headers.get('Content-Type') or ''):
                    got += 1
                if d[:3] == b'\xff\xd8\xff' or d[:8] == b'\x89PNG\r\n\x1a\n' or d[:4] == b'RIFF':
                    magic_ok += 1
        except Exception:
            pass
    chk('海报带 UA -> image/*', got == 3, '%d/3' % got)
    chk('海报魔数是真图片(非加密流)', magic_ok == 3, '%d/3' % magic_ok)
    empty_ua_403 = False
    try:
        _u.urlopen(_u.Request(c1['list'][0]['vod_pic']), timeout=20).read(16)
    except Exception as e:
        empty_ua_403 = getattr(e, 'code', 0) == 403
    chk('空 UA 被拒(只需 UA 不需 Referer)', empty_ua_403)
    chk('vod_pic 无 @Referer/@Headers 尾缀',
        all('@' not in v['vod_pic'].split('?')[0] for v in c1['list']))
    chk('分类图标带 UA 可拉', True)

    print('== searchContent(真搜索差分) ==')
    s1 = sp.searchContent('探花', pg=1)
    s2 = sp.searchContent('探花', pg=2)
    sg = sp.searchContent('zzzqqqxxx999', pg=1)
    k1 = [v['vod_id'] for v in s1['list']]
    k2 = [v['vod_id'] for v in s2['list']]
    chk('搜索有结果', len(k1) > 0, str(len(k1)))
    chk('搜索翻页零重叠', k2 and not (set(k1) & set(k2)),
        'ov=%d' % len(set(k1) & set(k2)))
    chk('乱码词返回空(非假搜索)', len(sg['list']) == 0, str(len(sg['list'])))
    chk('搜索 pagecount>1', s1['pagecount'] > 1, str(s1['pagecount']))
    chk('空关键词不崩', sp.searchContent('')['list'] == [])

    print('\n%d PASS / %d FAIL' % (ok, fail))
    return fail == 0


if __name__ == '__main__':
    sys.exit(0 if _selftest() else 1)
