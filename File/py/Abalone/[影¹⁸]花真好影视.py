# -*- coding: utf-8 -*-
# FongMi/TVBox Python Spider - 花真好影视 hzhys.shop
import re, json
from urllib.parse import urljoin, quote, unquote
try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        def fetch(self, url, headers=None, timeout=10):
            import requests, urllib3
            urllib3.disable_warnings()
            return requests.get(url, headers=headers, timeout=timeout, verify=False)
        def log(self, msg): print(msg)

class Spider(BaseSpider):
    def getName(self): return '花真好影视'
    def getDependence(self): return []

    def init(self, extend=''):
        self.host = 'https://www.hzhys.shop'
        self.headers = {'User-Agent':'Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36','Accept':'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8','Referer':self.host + '/'}
        self.classes = [
            {'type_id':'20','type_name':'热门视频'}, {'type_id':'21','type_name':'国产色情'},
            {'type_id':'22','type_name':'日本无码'}, {'type_id':'23','type_name':'自拍偷拍'},
            {'type_id':'24','type_name':'欧美精品'}, {'type_id':'25','type_name':'卡通动漫'},
            {'type_id':'26','type_name':'传媒原创'}, {'type_id':'27','type_name':'国产直播'},
            {'type_id':'28','type_name':'日本有码'}, {'type_id':'29','type_name':'吃瓜爆料'},
            {'type_id':'30','type_name':'伦理三级'}
        ]
        vals = [{'n':'按时间','v':'time'}, {'n':'按人气','v':'hits'}, {'n':'按评分','v':'score'}]
        self.filters = {c['type_id']:[{'key':'by','name':'排序','value':vals}] for c in self.classes}

    def homeContent(self, filter): return {'class': self.classes, 'filters': self.filters if filter else {}}
    def homeVideoContent(self): return {'list': self.parseList(self.host + '/')}

    def categoryContent(self, tid, pg, filter, extend):
        pg = str(pg or '1')
        by = (extend or {}).get('by') or 'time'
        if by and by != 'time':
            url = self.host + ('/index.php/vod/show/by/%s/id/%s.html' % (by, tid) if pg == '1' else '/index.php/vod/show/by/%s/id/%s/page/%s.html' % (by, tid, pg))
        else:
            url = self.host + ('/index.php/vod/show/id/%s.html' % tid if pg == '1' else '/index.php/vod/show/id/%s/page/%s.html' % (tid, pg))
        vods = self.parseList(url)
        return {'list': vods, 'page': int(pg), 'pagecount': 999999 if vods else int(pg), 'limit': 30, 'total': 999999 if vods else 0}

    def detailContent(self, ids):
        vid = ids[0]
        title, pic = '', ''
        if '|$|' in vid:
            parts = vid.split('|$|')
            vid = parts[0]
            title = unquote(parts[1]) if len(parts) > 1 else ''
            pic = parts[2] if len(parts) > 2 else ''
        vod_play_from, vod_play_url = '高清', ''
        try:
            txt = self.html(vid)
            if not title:
                title = self.clean(self.find1(txt, r'<h1[^>]*>([\s\S]*?)</h1>') or self.find1(txt, r'<title[^>]*>([\s\S]*?)(?:详情|在线观看|-)'))
            if not pic:
                pic = self.find1(txt, r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)') or self.find1(txt, r'<img[^>]*?\ssrc=["\']([^"\']+)')
            plays = []
            main = self.find1(txt, r'<div[^>]+class=["\'][^"\']*vod_play_list[^"\']*["\'][\s\S]*?</div>') or txt
            for m in re.finditer(r'<a[^>]+href=["\']([^"\']*?/index\.php/vod/play/id/\d+[^"\']*)["\'][^>]*>([\s\S]*?)</a>', main, re.I):
                href = self.fix(m.group(1)); name = self.clean(m.group(2)) or '播放'
                if href and href not in [x.split('$')[-1] for x in plays]: plays.append('%s$%s' % (name, href))
            if plays: vod_play_url = '#'.join(plays)
        except Exception as e:
            self.log('详情解析失败 %s' % e)
        if not title: title = '视频'
        if not vod_play_url: vod_play_url = '播放$%s' % vid
        vod = {'vod_id':vid,'vod_name':title,'vod_pic':self.fix(pic),'type_name':'','vod_year':'','vod_area':'','vod_remarks':'高清','vod_actor':'','vod_director':'','vod_content':title,'vod_play_from':vod_play_from,'vod_play_url':vod_play_url}
        return {'list':[vod]}

    def searchContent(self, key, quick, pg='1'):
        pg = str(pg or '1')
        path = '/index.php/vod/search.html?wd=' + quote(key or '') if pg == '1' else '/index.php/vod/search/page/%s/wd/%s.html' % (pg, quote(key or ''))
        vods = self.parseList(self.host + path)
        return {'list': vods, 'page': int(pg), 'total': len(vods)}

    def playerContent(self, flag, id, vipFlags):
        url = id
        try:
            if not self.isMedia(url):
                txt = self.html(id)
                m = re.search(r'var\s+player_\w+\s*=\s*(\{[\s\S]*?\})\s*</script>', txt, re.I)
                if m:
                    data = json.loads(m.group(1)); url = data.get('url') or id
                if not self.isMedia(url):
                    url = self.find1(txt, r'(https?://[^"\'<>\s]+?\.(?:m3u8|mp4)[^"\'<>\s]*)') or url
        except Exception as e:
            self.log('播放解析失败 %s' % e)
        if self.isMedia(url): return {'parse':0, 'url':url, 'header':self.playHeader(url)}
        return {'parse':1, 'url':id, 'header':self.headers}

    def parseList(self, url):
        try:
            txt = self.html(url)
            if self.isNoResult(txt): return []
            vods, seen = [], set()
            for m in re.finditer(r'<li>\s*<div[^>]+class=["\'][^"\']*li_li[^"\']*["\'][\s\S]*?</li>', txt, re.I):
                block = m.group(0)
                href = self.fix(self.find1(block, r'<a[^>]+href=["\']([^"\']*?/index\.php/vod/detail/id/\d+[^"\']*)'))
                if not href or href in seen: continue
                name = self.clean(self.find1(block, r'<p[^>]+class=["\']name["\'][\s\S]*?<a[^>]*>([\s\S]*?)</a>') or self.find1(block, r'title=["\']([^"\']+)') or self.find1(block, r'alt=["\']([^"\']+)'))
                pic = self.fix(self.find1(block, r'<img[^>]*?\sdata-src=["\']([^"\']+)') or self.find1(block, r'<img[^>]*?\sdata-original=["\']([^"\']+)') or self.find1(block, r'<img[^>]*?\ssrc=["\']([^"\']+)'))
                if not name: continue
                seen.add(href)
                vods.append({'vod_id':href+'|$|'+quote(name)+'|$|'+pic, 'vod_name':name, 'vod_pic':pic, 'vod_remarks':'高清'})
            return vods
        except Exception as e:
            self.log('列表解析失败 %s %s' % (url, e)); return []

    def html(self, url):
        r = self.fetch(url, headers=self.headers, timeout=15)
        return r.content.decode('utf-8','ignore') if hasattr(r,'content') else getattr(r,'text','')
    def fix(self, url): return urljoin(self.host + '/', (url or '').replace('&amp;','&').strip()) if url else ''
    def find1(self, txt, pat):
        m = re.search(pat, txt or '', re.I); return m.group(1) if m else ''
    def clean(self, s):
        s = re.sub(r'<[^>]+>', ' ', s or ''); s = re.sub(r'\s+', ' ', s).strip(); return s[:120]
    def isMedia(self, url): return bool(re.search(r'\.(m3u8|mp4)(\?|$)', url or '', re.I))
    def isNoResult(self, txt): return bool(re.search(r'没有找到|暂无数据|搜索无结果|未找到|404 Not Found', txt or '', re.I))
    def playHeader(self, url): return {'User-Agent': self.headers['User-Agent'], 'Referer': self.host + '/'}
    def localProxy(self, param): return [404, 'text/plain', b'']
    def manualVideoCheck(self): return True
    def liveContent(self, url): return None
    def action(self, action): return None
    def destroy(self): return None

spider = Spider()