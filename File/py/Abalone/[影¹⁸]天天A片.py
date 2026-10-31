# -*- coding: utf-8 -*-
# FongMi/TVBox Python Spider - 天天A片 ttap21.life
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
    def getName(self): return '天天A片'
    def getDependence(self): return []

    def init(self, extend=''):
        self.host = 'https://ttap21.life'
        self.headers = {'User-Agent':'Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36','Accept':'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8','Referer':self.host + '/'}
        self.groups = {
            '71': {'name':'一区','items':[('62','乱伦侵犯'),('60','国产自拍'),('44','国产AV'),('63','色情主播'),('67','偷拍偷窥'),('65','探花约炮'),('66','麻豆传媒')]},
            '72': {'name':'二区','items':[('46','日本无码'),('68','AV解说'),('61','日韩自拍'),('47','日本有码'),('48','中文字幕')]},
            '73': {'name':'三区','items':[('64','三级伦理'),('79','异域风情'),('70','黑料吃瓜'),('49','欧美情色'),('50','成人动漫')]},
            '74': {'name':'四区','items':[('75','黑丝诱惑'),('76','cosplay'),('78','反差母狗'),('69','另类视频'),('77','骑兵破解')]},
            '80': {'name':'五区','items':[('81','强奸迷奸'),('82','SM调教'),('83','口交自慰'),('84','群交多P'),('85','学生萝莉'),('86','素人特摄')]}
        }
        self.classes = [{'type_id':k,'type_name':v['name']} for k,v in self.groups.items()]
        self.filters = {}
        for k,v in self.groups.items():
            self.filters[k] = [{'key':'cate','name':'分类','value':[{'n':'全部','v':''}] + [{'n':name,'v':tid} for tid,name in v['items']]}]

    def homeContent(self, filter): return {'class': self.classes, 'filters': self.filters if filter else {}}
    def homeVideoContent(self): return {'list': self.parseList(self.host + '/')}

    def categoryContent(self, tid, pg, filter, extend):
        pg = str(pg or '1')
        real_tid = (extend or {}).get('cate') or self.firstChild(tid)
        url = self.host + ('/index.php/vod/type/id/%s.html' % real_tid if pg == '1' else '/index.php/vod/type/id/%s/page/%s.html' % (real_tid, pg))
        vods = self.parseList(url)
        return {'list': vods, 'page': int(pg), 'pagecount': 999999 if vods else int(pg), 'limit': 45, 'total': 999999 if vods else 0}

    def detailContent(self, ids):
        vid = ids[0]
        title, pic = '', ''
        if '|$|' in vid:
            parts = vid.split('|$|')
            vid = parts[0]
            title = unquote(parts[1]) if len(parts) > 1 else ''
            pic = parts[2] if len(parts) > 2 else ''
        if not title:
            try:
                txt = self.html(vid)
                title = self.clean(self.find1(txt, r'<h1[^>]*>([\s\S]*?)</h1>') or self.find1(txt, r'<title[^>]*>([\s\S]*?)(?:正片|在线观看|-)'))
                if not pic: pic = self.find1(txt, r'<img[^>]*?\sdata-src=["\']([^"\']+)') or self.find1(txt, r'<img[^>]*?\ssrc=["\']([^"\']+)')
            except Exception as e:
                self.log('详情解析失败 %s' % e)
        if not title: title = '视频'
        vod = {'vod_id':vid,'vod_name':title,'vod_pic':self.fix(pic),'type_name':'','vod_year':'','vod_area':'','vod_remarks':'直连','vod_actor':'','vod_director':'','vod_content':title,'vod_play_from':'高清','vod_play_url':'播放$%s' % vid}
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
                    try:
                        data = json.loads(m.group(1)); url = data.get('url') or id
                    except Exception: pass
                if not self.isMedia(url):
                    url = self.find1(txt, r'(https?://[^"\'<>\s]+?\.m3u8[^"\'<>\s]*)') or self.find1(txt, r'(https?://[^"\'<>\s]+?\.mp4[^"\'<>\s]*)') or url
        except Exception as e:
            self.log('播放解析失败 %s' % e)
        if self.isMedia(url): return {'parse':0, 'url':url, 'header':self.playHeader(url)}
        return {'parse':1, 'url':id, 'header':self.headers}

    def parseList(self, url):
        try:
            txt = self.html(url)
            if self.isNoResult(txt): return []
            vods, seen = [], set()
            blocks = re.findall(r'<div[^>]+class=["\'][^"\']*cell\s+video-listing[^"\']*["\'][\s\S]*?</div>\s*</div>\s*</div>', txt, re.I)
            if not blocks:
                blocks = re.findall(r'<div[^>]+class=["\'][^"\']*video-listing[^"\']*["\'][\s\S]*?</h4>[\s\S]*?</div>', txt, re.I)
            for block in blocks:
                href = self.fix(self.find1(block, r'<a[^>]+href=["\']([^"\']*?/index\.php/vod/play/id/\d+[^"\']*)'))
                if not href or href in seen: continue
                name = self.clean(self.find1(block, r'<h4[^>]+class=["\'][^"\']*av_data_title[^"\']*["\'][\s\S]*?<a[^>]*>([\s\S]*?)</a>') or self.find1(block, r'alt=["\']([^"\']+)'))
                pic = self.fix(self.find1(block, r'<img[^>]*?\sdata-src=["\']([^"\']+)') or self.find1(block, r'<img[^>]*?\sdata-original=["\']([^"\']+)') or self.find1(block, r'<img[^>]*?\ssrc=["\']([^"\']+)'))
                if 'placeholder' in pic or 'loading' in pic: pic = ''
                if not name: continue
                seen.add(href)
                vods.append({'vod_id':href+'|$|'+quote(name)+'|$|'+pic, 'vod_name':name, 'vod_pic':pic, 'vod_remarks':'直连'})
            return vods
        except Exception as e:
            self.log('列表解析失败 %s %s' % (url, e)); return []

    def firstChild(self, tid):
        g = self.groups.get(str(tid)); return g['items'][0][0] if g and g.get('items') else str(tid)
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