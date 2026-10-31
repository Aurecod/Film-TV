# -*- coding: utf-8 -*-
# FongMi/TVBox Python Spider - 快乐星球 klxq809.xyz
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
    def getName(self): return '快乐星球'
    def getDependence(self): return []

    def init(self, extend=''):
        self.host = 'https://klxq809.xyz'
        self.headers = {'User-Agent':'Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36','Accept':'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8','Referer':self.host + '/'}
        self.classes = [
            {'type_id':'1','type_name':'国产情色'}, {'type_id':'2','type_name':'日本无码'},
            {'type_id':'3','type_name':'AV明星'}, {'type_id':'4','type_name':'中文字幕'},
            {'type_id':'5','type_name':'网红主播'}, {'type_id':'6','type_name':'成人动漫'},
            {'type_id':'7','type_name':'欧美情色'}, {'type_id':'8','type_name':'国模私拍'},
            {'type_id':'9','type_name':'长腿丝袜'}, {'type_id':'10','type_name':'邻家人妻'},
            {'type_id':'11','type_name':'三级伦理'}, {'type_id':'12','type_name':'精品推荐'}
        ]
        self.filters = {c['type_id']:[{'key':'by','name':'排序','value':[{'n':'默认','v':''},{'n':'最高人气','v':'hits'},{'n':'最多点赞','v':'up'}]}] for c in self.classes}

    def homeContent(self, filter): return {'class': self.classes, 'filters': self.filters if filter else {}}
    def homeVideoContent(self): return {'list': self.parseList(self.host + '/')}

    def categoryContent(self, tid, pg, filter, extend):
        pg = str(pg or '1'); by = (extend or {}).get('by') or ''
        if by:
            url = self.host + ('/index.php/vod/show/by/%s/id/%s.html' % (by, tid) if pg == '1' else '/index.php/vod/show/by/%s/id/%s/page/%s.html' % (by, tid, pg))
        else:
            url = self.host + ('/index.php/vod/type/id/%s.html' % tid if pg == '1' else '/index.php/vod/type/id/%s/page/%s.html' % (tid, pg))
        vods = self.parseList(url)
        return {'list':vods,'page':int(pg),'pagecount':999999 if vods else int(pg),'limit':32,'total':999999 if vods else 0}

    def detailContent(self, ids):
        vid = ids[0]; title, pic = '', ''
        if '|$|' in vid:
            ps = vid.split('|$|'); vid = ps[0]
            title = unquote(ps[1]) if len(ps)>1 else ''
            pic = ps[2] if len(ps)>2 else ''
        if not title:
            try:
                txt = self.html(vid)
                m = re.search(r'var\s+player_\w+\s*=\s*(\{[\s\S]*?\})\s*</script>', txt, re.I)
                if m:
                    data = json.loads(m.group(1)); title = ((data.get('vod_data') or {}).get('vod_name') or '')
                if not title: title = self.clean(self.find1(txt, r'<title[^>]*>([\s\S]*?)(?:-|在线观看|播放)'))
                if not pic: pic = self.find1(txt, r'<img[^>]*?\sdata-src=["\']([^"\']+)') or self.find1(txt, r'<img[^>]*?\ssrc=["\']([^"\']+)')
            except Exception as e: self.log('详情解析失败 %s' % e)
        if not title: title = '视频'
        return {'list':[{'vod_id':vid,'vod_name':title,'vod_pic':self.fix(pic),'type_name':'','vod_year':'','vod_area':'','vod_remarks':'直连','vod_actor':'','vod_director':'','vod_content':title,'vod_play_from':'高清','vod_play_url':'播放$%s' % vid}]}

    def searchContent(self, key, quick, pg='1'):
        pg = str(pg or '1')
        path = '/index.php/vod/search/wd/%s.html' % quote(key or '') if pg == '1' else '/index.php/vod/search/page/%s/wd/%s.html' % (pg, quote(key or ''))
        vods = self.parseList(self.host + path)
        return {'list':vods,'page':int(pg),'total':len(vods)}

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
        if self.isMedia(url): return {'parse':0,'url':url,'header':self.playHeader(url)}
        return {'parse':1,'url':id,'header':self.headers}

    def parseList(self, url):
        try:
            txt = self.html(url)
            if self.isNoResult(txt): return []
            vods, seen = [], set()
            blocks = re.findall(r'<div[^>]+class=["\'][^"\']*video-img-box[^"\']*["\'][\s\S]*?</div>\s*</div>', txt, re.I)
            if not blocks:
                blocks = re.findall(r'<a[^>]+href=["\'][^"\']*?/index\.php/vod/play/id/\d+[^"\']*["\'][\s\S]*?</a>', txt, re.I)
            for block in blocks:
                href = self.fix(self.find1(block, r'<a[^>]+href=["\']([^"\']*?/index\.php/vod/play/id/\d+[^"\']*)'))
                if not href or href in seen: continue
                name = self.clean(self.find1(block, r'<h6[^>]+class=["\'][^"\']*title[^"\']*["\'][\s\S]*?<a[^>]*>([\s\S]*?)</a>') or self.find1(block, r'<img[^>]+alt=["\']([^"\']+)'))
                pic = self.fix(self.find1(block, r'<img[^>]*?\sdata-src=["\']([^"\']+)') or self.find1(block, r'<img[^>]*?\ssrc=["\']([^"\']+)'))
                if 'placeholder' in pic or 'loading' in pic: pic = ''
                remark = self.clean(self.find1(block, r'<span[^>]+class=["\'][^"\']*label[^"\']*["\'][^>]*>([\s\S]*?)</span>')) or 'HD'
                if not name: continue
                seen.add(href)
                vods.append({'vod_id':href+'|$|'+quote(name)+'|$|'+pic,'vod_name':name,'vod_pic':pic,'vod_remarks':remark})
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
        s = re.sub(r'<[^>]+>', ' ', s or ''); s = re.sub(r'&nbsp;|\s+', ' ', s).strip(); return s[:120]
    def isMedia(self, url): return bool(re.search(r'\.(m3u8|mp4)(\?|$)', url or '', re.I))
    def isNoResult(self, txt): return bool(re.search(r'没有找到|暂无数据|搜索无结果|未找到|404 Not Found', txt or '', re.I))
    def playHeader(self, url): return {'User-Agent':self.headers['User-Agent'],'Referer':self.host + '/'}
    def localProxy(self, param): return [404,'text/plain',b'']
    def manualVideoCheck(self): return True
    def liveContent(self, url): return None
    def action(self, action): return None
    def destroy(self): return None

spider = Spider()