# -*- coding: utf-8 -*-
# FongMi/TVBox Python Spider - lu上天 lst29.life
import re, json, html
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
    def getName(self): return 'lu上天'
    def getDependence(self): return []

    def init(self, extend=''):
        self.host = 'https://lst29.life'
        self.headers = {'User-Agent':'Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36','Accept':'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8','Referer':self.host + '/'}
        self.classes = [
            {'type_id':'44','type_name':'国产AV'},
            {'type_id':'47','type_name':'中文字幕'},
            {'type_id':'45','type_name':'日本AV'},
            {'type_id':'46','type_name':'欧美情色'},
            {'type_id':'48','type_name':'色情动漫'},
            {'type_id':'75','type_name':'异域风情'}
        ]
        self.filters = {c['type_id']:[{'key':'by','name':'排序','value':[{'n':'默认','v':''},{'n':'最新','v':'time'},{'n':'最热','v':'hits'},{'n':'评分','v':'score'}]}] for c in self.classes}

    def homeContent(self, filter): return {'class': self.classes, 'filters': self.filters if filter else {}}
    def homeVideoContent(self): return {'list': self.parseList(self.host + '/')}

    def categoryContent(self, tid, pg, filter, extend):
        pg = str(pg or '1'); by = (extend or {}).get('by') or ''
        if by:
            url = self.host + ('/index.php/vod/show/by/%s/id/%s.html' % (by, tid) if pg == '1' else '/index.php/vod/show/by/%s/id/%s/page/%s.html' % (by, tid, pg))
        else:
            url = self.host + ('/index.php/vod/type/id/%s.html' % tid if pg == '1' else '/index.php/vod/type/id/%s/page/%s.html' % (tid, pg))
        vods = self.parseList(url)
        return {'list': vods, 'page': int(pg), 'pagecount': 999999 if vods else int(pg), 'limit': 36, 'total': 999999 if vods else 0}

    def detailContent(self, ids):
        vid = ids[0]; title, pic = '', ''
        if '|$|' in vid:
            parts = vid.split('|$|'); vid = parts[0]
            title = unquote(parts[1]) if len(parts) > 1 else ''
            pic = parts[2] if len(parts) > 2 else ''
        if not title:
            try:
                txt = self.html(vid)
                title = self.clean(self.find1(txt, r'<h1[^>]*>([\s\S]*?)</h1>') or self.find1(txt, r'<h3[^>]*class=["\'][^"\']*uk-margin-remove[^"\']*["\'][^>]*>([\s\S]*?)</h3>') or self.find1(txt, r'<title[^>]*>([\s\S]*?)(?:-|在线观看|播放)'))
                if not pic: pic = self.find1(txt, r'<img[^>]*?\ssrc=["\']([^"\']+)["\'][^>]*?alt=["\']%s' % re.escape(title[:10])) or self.find1(txt, r'<img[^>]*?\ssrc=["\']([^"\']+)["\']')
            except Exception as e: self.log('详情解析失败 %s' % e)
        if not title: title = '视频'
        return {'list':[{'vod_id':vid,'vod_name':title,'vod_pic':self.fix(pic),'type_name':'','vod_year':'','vod_area':'','vod_remarks':'直连','vod_actor':'','vod_director':'','vod_content':title,'vod_play_from':'高清','vod_play_url':'播放$%s' % vid}]}

    def searchContent(self, key, quick, pg='1'):
        pg = str(pg or '1')
        path = '/index.php/vod/search/wd/%s.html' % quote(key or '') if pg == '1' else '/index.php/vod/search/page/%s/wd/%s.html' % (pg, quote(key or ''))
        vods = self.parseList(self.host + path)
        return {'list': vods, 'page': int(pg), 'total': len(vods)}

    def playerContent(self, flag, id, vipFlags):
        url = id
        try:
            if not self.isMedia(url):
                txt = self.html(id)
                m = re.search(r'var\s+player_\w+\s*=\s*(\{[\s\S]*?\})\s*</script>', txt, re.I)
                if m:
                    try:
                        data = json.loads(m.group(1)); url = data.get('url') or id
                        enc = str(data.get('encrypt','0'))
                        if enc == '1': url = unquote(url)
                        elif enc == '2':
                            import base64
                            url = unquote(base64.b64decode(url).decode('utf-8','ignore'))
                    except Exception as e: self.log('player json失败 %s' % e)
                if not self.isMedia(url):
                    url = self.find1(txt, r'(https?://[^"\'<>\s]+?\.m3u8[^"\'<>\s]*)') or self.find1(txt, r'(https?://[^"\'<>\s]+?\.mp4[^"\'<>\s]*)') or url
        except Exception as e: self.log('播放解析失败 %s' % e)
        if self.isMedia(url): return {'parse':0, 'url':url, 'header':self.playHeader(url)}
        return {'parse':1, 'url':id, 'header':self.headers}

    def parseList(self, url):
        try:
            txt = self.html(url)
            if self.isNoResult(txt): return []
            vods, seen = [], set()
            # 标准卡片：movie-card / uk-card
            cards = re.findall(r'<div[^>]+class=["\'][^"\']*movie-card[^"\']*["\'][\s\S]*?</div>\s*</div>\s*</div>', txt, re.I)
            if not cards:
                cards = re.findall(r'<a[^>]+href=["\'][^"\']*?/index\.php/vod/play/id/\d+[^"\']*["\'][\s\S]*?</a>', txt, re.I)
            for block in cards:
                href = self.fix(self.find1(block, r'<a[^>]+href=["\']([^"\']*?/index\.php/vod/play/id/\d+[^"\']*)'))
                if not href or href in seen: continue
                name = self.clean(self.find1(block, r'<img[^>]+alt=["\']([^"\']+)') or self.find1(block, r'<h[1-6][^>]*>([\s\S]*?)</h[1-6]>') or self.find1(block, r'title=["\']([^"\']+)'))
                pic = self.fix(self.find1(block, r'<img[^>]*?\sdata-src=["\']([^"\']+)') or self.find1(block, r'<img[^>]*?\ssrc=["\']([^"\']+)'))
                if not name: continue
                seen.add(href)
                vods.append({'vod_id':href+'|$|'+quote(name)+'|$|'+pic, 'vod_name':name, 'vod_pic':pic, 'vod_remarks':'直连'})
            return vods
        except Exception as e:
            self.log('列表解析失败 %s %s' % (url, e)); return []

    def html(self, url):
        r = self.fetch(url, headers=self.headers, timeout=15)
        raw = r.text if hasattr(r,'text') else r.content.decode('utf-8','ignore')
        raw = raw.strip()
        # 该站响应为 JSON 字符串包裹的 HTML："<!DOCTYPE html>..."
        if len(raw) > 1 and raw[0] == '"':
            try: raw = json.loads(raw)
            except Exception: pass
        return html.unescape(raw)
    def fix(self, url): return urljoin(self.host + '/', (url or '').replace('&amp;','&').strip()) if url else ''
    def find1(self, txt, pat):
        m = re.search(pat, txt or '', re.I); return m.group(1) if m else ''
    def clean(self, s):
        s = re.sub(r'<[^>]+>', ' ', s or ''); s = re.sub(r'&nbsp;|\s+', ' ', s).strip(); return s[:120]
    def isMedia(self, url): return bool(re.search(r'\.(m3u8|mp4)(\?|$)', url or '', re.I))
    def isNoResult(self, txt): return bool(re.search(r'没有找到|暂无数据|搜索无结果|未找到|404 Not Found', txt or '', re.I))
    def playHeader(self, url): return {'User-Agent': self.headers['User-Agent'], 'Referer': self.host + '/'}
    def localProxy(self, param): return [404, 'text/plain', b'']
    def manualVideoCheck(self): return True
    def liveContent(self, url): return None
    def action(self, action): return None
    def destroy(self): return None

spider = Spider()