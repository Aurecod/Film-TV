# -*- coding: utf-8 -*-
# 色情探针 (pornprobe.com) - FongMi TV Python spider
# WordPress (retrotube 主题) 成人视频站; 列表/详情在本机站, 播放是 Pornhub / XVideos 嵌入,
# playerContent 时实时解析源站签名地址 (PH mediaDefinitions / XV setVideoHLS, 地址几分钟过期, 不缓存)
# 解析全用正则 (不用 pyquery, 真机大页面会静默失效)
from base.spider import Spider as BaseSpider
import json
import re
import time
from html import unescape
from urllib.parse import quote


class Spider(BaseSpider):

    def init(self, extend=""):
        pass

    def getName(self):
        return '色情探针'

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def destroy(self):
        pass

    host = 'https://pornprobe.com'

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36',
        'Referer': 'https://pornprobe.com/',
    }

    ph_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36',
        'Referer': 'https://www.pornhub.com/',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }

    # 站内真实分类 (2026-10-21 实测导航 36 个); '' 为首页最新
    classes = [
        ('', '最新'),
        ('hdgq', 'HD高清视频'), ('zgsq', '中国色情'), ('yzr', '亚洲人'), ('omsq', '欧美色情'),
        ('rbr', '日本人'), ('sr', '素人'), ('whmx', '网红明星'), ('zrsp', '真人实拍'),
        ('dnz', '大奶子'), ('dpg', '大屁股'), ('djb', '大鸡巴'), ('xsm', '学生妹'),
        ('qsn', '青少年'), ('fqsn', '风情少女'), ('sv', '18岁'), ('gzyz', '公众野战'),
        ('nszc', '内射中出'), ('houru', '后入'), ('zkw', '劲爆重口味'), ('vt', '女同'),
        ('vxgc', '女性高潮'), ('sj', '射精'), ('amsp', '按摩视频'), ('kbxa', '捆绑性爱'),
        ('xyza', '校园做爱'), ('nt', '男同'), ('cbkj', '粗暴口交'), ('cbxa', '粗暴性爱'),
        ('qjpd', '群交派对'), ('dfj', '自慰'), ('tx', '舔穴'), ('sqdm', '色情动漫'),
        ('jsby', '角色扮演'), ('prnv', '贫乳女人'), ('jfmv', '金发美女'), ('ys', '颜射'),
    ]

    # ---------- 基础 ----------
    def gethtml(self, url, headers=None, timeout=25):
        # 全程走 App 自带 self.fetch (Pornhub 源对设备网络路径敏感, 原生 requests 在真机时有时无);
        # 失败只补一次, 避免放大请求量
        for attempt in (0, 1):
            if attempt:
                time.sleep(2)
            try:
                rsp = self.fetch(url, headers=headers or self.headers, timeout=timeout)
                txt = rsp.text or ''
                if txt:
                    return txt
            except Exception as e:
                print(f'gethtml 失败({url}) 第{attempt + 1}次: {e}')
        return ''

    def _pagecount(self, html, pg, got):
        nums = [int(n) for n in re.findall(r'/page/(\d+)/', html)]
        if nums:
            return max(nums)
        return pg if got < 60 else pg + 1

    def _parse_list(self, html):
        # 只解析主列表区 (class="videos-list" 到翻页/侧栏为止), 避免把侧栏推荐 widget 的
        # <article> 也算进来 (首页/翻页会出现 101 条且跨页重复, 实测教训)
        start = html.find('class="videos-list"')
        if start >= 0:
            ends = [p for p in (html.find(m, start + 10) for m in
                                ('class="videos-list"', 'class="pagination"', '<aside', 'id="secondary"', '<footer', '<section id="block-')) if p > start]
            html = html[start:min(ends)] if ends else html[start:]
        # 按 <article 分块解析; 字段: 帖子URL/标题/封面/时长
        videos = []
        seen = set()
        for block in re.split(r'<article\b', html)[1:]:
            m = re.search(r'href="(https://pornprobe\.com/[a-z0-9]+/\d+\.html/)"', block)
            if not m:
                continue
            url = m.group(1)
            if url in seen:
                continue
            seen.add(url)
            tm = re.search(r'href="' + re.escape(url) + r'"\s+title="([^"]+)"', block)
            if tm:
                name = unescape(tm.group(1)).strip()
            else:
                sm = re.search(r'entry-header">\s*<span>(.*?)</span>', block, re.S)
                name = unescape(re.sub(r'<[^>]+>', '', sm.group(1))).strip() if sm else ''
            pm = re.search(r'data-main-thumb="([^"]+)"', block) or re.search(r'class="video-main-thumb"[^>]*src="([^"]+)"', block) or re.search(r'src="(https://pornprobe\.com/wp-content/uploads/[^"]+)"', block)
            pic = re.sub(r'\s+', '', pm.group(1)) if pm else ''
            dm = re.search(r'class="duration">.*?([\d]+:[\d]{2}(?::[\d]{2})?)', block, re.S)
            videos.append({
                'vod_id': url,
                'vod_name': name,
                'vod_pic': pic,
                'vod_remarks': dm.group(1) if dm else '',
            })
        return videos

    # ---------- FongMi 接口 ----------
    # 站内真实排序筛选 (分类页 #filters 实测: ?filter= 切参数后顺序确实不同; 首页无此筛选不挂)
    sort_filter = [{'key': 'filter', 'name': '排序', 'value': [
        {'n': '最新', 'v': 'latest'}, {'n': '最热', 'v': 'popular'},
        {'n': '最多观看', 'v': 'most-viewed'}, {'n': '最长', 'v': 'longest'},
        {'n': '随机', 'v': 'random'},
    ]}]

    def homeContent(self, filter=False):
        filters = {tid: self.sort_filter for tid, name in self.classes if tid}
        return {'class': [{'type_id': tid, 'type_name': name} for tid, name in self.classes], 'filters': filters}

    def homeVideoContent(self):
        html = self.gethtml(self.host + '/')
        return {'list': self._parse_list(html)} if html else {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if str(pg).isdigit() else 1
        if tid:
            url = f'{self.host}/category/{tid}/' + (f'page/{pg}/' if pg > 1 else '')
            fv = (extend or {}).get('filter', '') if isinstance(extend, dict) else ''
            if fv in ('latest', 'popular', 'most-viewed', 'longest', 'random'):
                url += f'?filter={fv}'
        else:
            url = self.host + '/' + (f'page/{pg}/' if pg > 1 else '')
        html = self.gethtml(url)
        if not html:
            return {'page': pg, 'pagecount': pg, 'limit': 60, 'total': 0, 'list': []}
        videos = self._parse_list(html)
        # 首页是陈列页 (6 个分区, /page/2/ 返回同一页), 最新只取第一个分区且只有 1 页
        pc = 1 if not tid else self._pagecount(html, pg, len(videos))
        return {'page': pg, 'pagecount': pc, 'limit': 60, 'total': pc * 60, 'list': videos}

    def searchContent(self, key, quick, pg='1'):
        pg = int(pg) if str(pg).isdigit() else 1
        url = (f'{self.host}/page/{pg}/?s=' if pg > 1 else f'{self.host}/?s=') + quote(str(key))
        html = self.gethtml(url)
        if not html:
            return {'list': [], 'page': pg, 'pagecount': pg}
        videos = self._parse_list(html)
        return {'list': videos, 'page': pg, 'pagecount': self._pagecount(html, pg, len(videos))}

    def detailContent(self, ids):
        url = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        if not str(url).startswith(self.host):
            return {'list': []}
        html = self.gethtml(str(url))
        if not html:
            return {'list': []}
        # 不存在的帖子 WP 返回 404 页 (有 og:title 但无播放器), 无播放器一律当不存在
        if 'responsive-player' not in html and '<iframe' not in html:
            return {'list': []}
        tm = re.search(r'property="og:title" content="([^"]+)"', html) or re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
        name = unescape(re.sub(r'<[^>]+>', '', tm.group(1))).strip() if tm else ''
        name = re.sub(r'\s*[–—-]\s*色情探针.*$', '', name).strip()
        pm = re.search(r'property="og:image" content="([^"]+)"', html)
        pic = pm.group(1) if pm else ''
        cm = re.search(r'class="entry-content"[^>]*>(.*?)</div>\s*<(?:footer|div class="entry-meta|nav)', html, re.S) or re.search(r'property="og:description" content="([^"]*)"', html)
        content = ''
        if cm:
            content = unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', cm.group(1)))).strip()[:500]
        cats = []
        for c in re.findall(r'href="https://pornprobe\.com/category/[a-z0-9]+/"[^>]*>([^<]+)</a>', html):
            c = unescape(c).strip()
            if c and c not in cats and 'related' not in c:
                cats.append(c)
        dm = re.search(r'class="duration">.*?([\d]+:[\d]{2}(?::[\d]{2})?)', html, re.S)
        vod = {
            'vod_id': str(url),
            'vod_name': name,
            'vod_pic': pic,
            'vod_remarks': dm.group(1) if dm else '',
            'vod_content': content,
            'type_name': ','.join(cats[:3]),
            'vod_play_from': '播放',
            'vod_play_url': '播放$' + str(url),
        }
        if not name:
            return {'list': []}
        return {'list': [vod]}

    # ---------- 播放解析 ----------
    def _alive_m3u8(self, url, headers):
        try:
            rsp = self.fetch(url, headers=headers, timeout=12)
            txt = rsp.text or ''
            return txt.lstrip().startswith('#EXTM3U')
        except Exception:
            return False

    def _media_definitions(self, html):
        # 优先 ,"isVertical" 界定的正则; 不中时按括号配平扫出整个数组 (键序因视频而异)
        m = re.search(r'"mediaDefinitions":\s*(\[.*?\]),\s*"isVertical"', html, re.S)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass
        i = html.find('"mediaDefinitions"')
        if i < 0:
            return []
        j = html.find('[', i)
        if j < 0:
            return []
        depth = 0
        in_str = False
        esc = False
        for k in range(j, len(html)):
            c = html[k]
            if in_str:
                if esc:
                    esc = False
                elif c == '\\':
                    esc = True
                elif c == '"':
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c == '[':
                depth += 1
            elif c == ']':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(html[j:k + 1])
                    except Exception:
                        return []
        return []

    def _play_pornhub(self, viewkey):
        html = self.gethtml(f'https://www.pornhub.com/view_video.php?viewkey={viewkey}', headers=self.ph_headers)
        if not html:
            return ''
        arr = self._media_definitions(html)
        cands = []
        for it in arr:
            u = (it.get('videoUrl') or '').strip()
            q = str(it.get('quality') or '')
            if u and q.isdigit():
                cands.append((int(q), u))
        cands.sort(reverse=True)
        for q, u in cands:
            if self._alive_m3u8(u, self.ph_headers):
                return u
        return cands[0][1] if cands else ''

    def _play_xvideos(self, embed_id):
        html = self.gethtml(f'https://www.xvideos.com/embedframe/{embed_id}', headers=self.ph_headers)
        if not html:
            return ''
        mh = re.search(r"setVideoHLS\('([^']+)'\)", html)
        if mh and self._alive_m3u8(mh.group(1), self.ph_headers):
            return mh.group(1)
        m = re.search(r"setVideoUrlHigh\('([^']+)'\)", html) or re.search(r"setVideoUrlLow\('([^']+)'\)", html)
        if m:
            return m.group(1)
        return mh.group(1) if mh else ''

    def playerContent(self, flag, id, vipFlags):
        empty = {'parse': 0, 'playUrl': '', 'url': '', 'header': ''}
        url = str(id)
        html = self.gethtml(url)
        if not html:
            return dict(empty, msg='详情页获取失败')
        fm = re.search(r'<iframe[^>]+src="(https?://[^"]+)"', html)
        src = fm.group(1) if fm else ''
        play = ''
        if 'pornhub.com/embed/' in src:
            vk = src.rstrip('/').split('/')[-1]
            play = self._play_pornhub(vk)
        elif 'xvideos.com/embedframe/' in src:
            eid = src.rstrip('/').split('/')[-1]
            play = self._play_xvideos(eid)
        if not play:
            # 兜底: 页面内直链文件
            dm = re.search(r'(https?://[^"\']+\.(?:m3u8|mp4)[^"\']*)', html)
            if dm:
                play = dm.group(1)
        if not play:
            return dict(empty, msg='未能解析播放地址(源站可能已删或换源)')
        return {'parse': 0, 'playUrl': '', 'url': play, 'header': json.dumps(self.ph_headers)}
