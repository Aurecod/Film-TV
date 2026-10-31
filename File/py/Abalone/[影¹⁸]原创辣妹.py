# -*- coding: utf-8 -*-
# 作者：蜗牛大叔
import re
import sys
sys.path.append('..')
from base.spider import Spider

class Spider(Spider):
    def init(self, extend=""):
        self.host = 'https://www.yclm01.sbs'
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': self.host + '/',
        }

    def getName(self):
        return '原创辣妹'

    def isVideoFormat(self, url):
        if not url:
            return False
        return bool(re.search(r'\.(m3u8|mp4|flv|ts|mkv|avi|mov)(\?|$)', str(url), re.I))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def _get(self, url):
        try:
            r = self.fetch(url, headers=self.headers)
            if r and len(r.text) > 500:
                return r.text
        except Exception:
            pass
        return ''

    CATS = [
        ('20', '视频一区'), ('21', '视频二区'), ('22', '视频三区'), ('23', '视频四区'),
        ('24', '国产精品'), ('25', '国产乱伦'), ('26', '国产传媒'), ('27', '黑料不打烊'),
        ('28', '国产自拍'), ('29', '网红主播'), ('30', '探花系列'), ('31', '三级电影'),
        ('32', '人妻熟女'), ('33', '日本无码'), ('34', '美乳巨乳'), ('35', '强制侵犯'),
        ('36', '制服诱惑'), ('37', '绝色佳人'), ('38', '风俗泡泡浴'), ('39', '家庭乱伦'),
        ('40', 'AV解说'), ('41', '少女萝莉'), ('42', 'SM调教'), ('43', '绝顶潮吹'),
        ('44', '魔镜系列'), ('45', '时间停止'), ('46', '催眠洗脑'), ('47', '电车痴汉'),
        ('48', '淫欲痴女'), ('49', '韩国主播'), ('50', '泰国风情'), ('51', 'OnlyFans'),
        ('52', 'AI换脸'), ('53', '漫改系列'), ('54', '欧美精品'),
    ]

    def homeContent(self, filter=None):
        return {'class': [{'type_id': c[0], 'type_name': c[1]} for c in self.CATS]}

    def _parse_list(self, h):
        vids = []
        seen = set()
        for m in re.finditer(
            r'<article class="media-card">\s*<a class="thumb" href="/index\.php/vod/detail/id/(\d+)\.html">'
            r'<img src="([^"]+)" alt="([^"]*)"[^>]*>(?:<span>([^<]*)</span>)?',
            h
        ):
            vid, pic, title = m.group(1), m.group(2), m.group(3)
            if vid in seen:
                continue
            seen.add(vid)
            vids.append({
                'vod_id': vid,
                'vod_name': title.strip(),
                'vod_pic': pic,
                'vod_remarks': (m.group(4) or '').strip(),
            })
        return vids

    def homeVideoContent(self):
        h = self._get(self.host + '/')
        return {'list': self._parse_list(h)}

    def categoryContent(self, tid, pg, filter=None, extend=None):
        pg = int(pg)
        if pg == 1:
            url = f'{self.host}/index.php/vod/type/id/{tid}.html'
        else:
            url = f'{self.host}/index.php/vod/type/id/{tid}/page/{pg}.html'
        h = self._get(url)
        return {'list': self._parse_list(h), 'page': pg, 'pagecount': 9999, 'limit': 30, 'total': 999999}

    def detailContent(self, ids):
        vid = ids[0] if isinstance(ids, (list, tuple)) else ids
        h = self._get(f'{self.host}/index.php/vod/detail/id/{vid}.html')
        name = ''
        m = re.search(r'<h1[^>]*>([^<]+)</h1>', h)
        if m:
            name = m.group(1).strip()
        pic = ''
        pm = re.search(r'<a class="thumb" href="[^"]*"><img src="([^"]+)" alt="' + re.escape(name[:12]), h) if name else None
        if pm:
            pic = pm.group(1)

        froms, urls = [], []
        for blk in re.finditer(r'<div class="play-list">(.*?)</div>', h, re.S):
            b = blk.group(1)
            nm = re.search(r'<strong>([^<]+)</strong>', b)
            eps = []
            for m in re.finditer(
                r'href="(/index\.php/vod/play/id/\d+/sid/\d+/nid/(\d+)\.html)"[^>]*>(.*?)</a>',
                b, re.S
            ):
                url, nid, txt = m.group(1), m.group(2), m.group(3)
                ep = re.sub(r'<[^>]+>', '', txt).replace('▶', '').strip() or f'第{nid}集'
                eps.append(f'{ep}${url}')
            if eps:
                froms.append(nm.group(1).strip() if nm else '线路')
                urls.append('#'.join(eps))
        # 兜底：无 play-list 块时直接收集全部播放链接
        if not urls:
            links = sorted(set(re.findall(r'href="(/index\.php/vod/play/id/\d+/sid/\d+/nid/\d+\.html)"', h)))
            if links:
                froms.append('正片')
                urls.append('正片$' + links[0] if len(links) == 1 else
                            '#'.join(f'第{i+1}集${u}' for i, u in enumerate(links)))
        vod = {
            'vod_id': vid,
            'vod_name': name,
            'vod_pic': pic,
            'vod_play_from': '$$$'.join(froms),
            'vod_play_url': '$$$'.join(urls),
        }
        return {'list': [vod]}

    def searchContent(self, key, quick=False, pg=1):
        pg = int(pg)
        from urllib.parse import quote
        url = f'{self.host}/index.php/vod/search/wd/{quote(key)}.html'
        if pg > 1:
            url = f'{self.host}/index.php/vod/search/wd/{quote(key)}/page/{pg}.html'
        h = self._get(url)
        return {'list': self._parse_list(h), 'page': pg}

    def playerContent(self, flag, id, vipFlags=None):
        url = ''
        play_page = ''
        if id:
            full = id if str(id).startswith('http') else self.host + str(id)
            if re.search(r'\.(m3u8|mp4)(\?|$)', full):
                url = full
            else:
                play_page = full
                h = self._get(full)
                m = re.search(r'<source[^>]+src="([^"]+)"', h, re.I) \
                    or re.search(r'<video[^>]+src="([^"]+)"', h, re.I)
                if m:
                    url = m.group(1)
                if not url:
                    mb = re.search(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', h)
                    if mb:
                        url = mb.group(0)
        header = dict(self.headers)
        if play_page:
            header['Referer'] = play_page
        return {'parse': 0, 'url': url, 'header': header}

    def localProxy(self, param):
        pass
