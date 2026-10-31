# -*- coding: utf-8 -*-
# FongMi/TVBox Python Spider - 免费少女 teri14.cc
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
    def getName(self): return '免费少女'
    def getDependence(self): return []

    def init(self, extend=''):
        self.host = 'https://teri14.cc'
        self.headers = {'User-Agent':'Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36','Accept':'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8','Referer':self.host + '/'}
        self.groups = {
            '1': {'name':'各类视频','items':[('5','日本无码'),('6','日本有码'),('8','无码破解'),('86','性感写真'),('88','日本综艺')]},
            '26': {'name':'限时免费少女','items':[]},
            '28': {'name':'动漫主题馆','items':[('32','精选动漫'),('33','极速观看动画')]},
            '27': {'name':'传媒原创','items':[]},
            '35': {'name':'国产视频','items':[('36','极速国产精品')]},
            '29': {'name':'欧美西方','items':[('30','极速免费欧美')]}
        }
        self.classes = [{'type_id':k,'type_name':v['name']} for k,v in self.groups.items()]
        self.sorts = [{'n':'最新','v':'time'},{'n':'最热','v':'hits'},{'n':'评分','v':'score'}]
        self.filters = {}
        for k,v in self.groups.items():
            fs = []
            if v.get('items'):
                fs.append({'key':'cate','name':'分类','value':[{'n':'全部','v':''}] + [{'n':name,'v':tid} for tid,name in v['items']]})
            fs.append({'key':'by','name':'排序','value':[{'n':'默认','v':''}] + self.sorts})
            self.filters[k] = fs

    def homeContent(self, filter): return {'class': self.classes, 'filters': self.filters if filter else {}}
    def homeVideoContent(self): return {'list': self.parseList(self.host + '/')}

    def categoryContent(self, tid, pg, filter, extend):
        pg = str(pg or '1')
        ext = extend or {}
        real_tid = ext.get('cate') or str(tid)
        by = ext.get('by') or ''
        if by:
            url = self.host + ('/index.php/vod/show/by/%s/id/%s.html' % (by, real_tid) if pg == '1' else '/index.php/vod/show/by/%s/id/%s/page/%s.html' % (by, real_tid, pg))
        else:
            url = self.host + ('/index.php/vod/type/id/%s.html' % real_tid if pg == '1' else '/index.php/vod/type/id/%s/page/%s.html' % (real_tid, pg))
        vods = self.parseList(url)
        return {'list': vods, 'page': int(pg), 'pagecount': 999999 if vods else int(pg), 'limit': 32, 'total': 999999 if vods else 0}

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
                title = self.clean(self.find1(txt, r'<div[^>]+class=["\'][^"\']*video-active-desc-title[^"\']*["\']>([\s\S]*?)</div>') or self.find1(txt, r'<title[^>]*>([\s\S]*?)(?:正片|在线观看|-)'))
                if not pic: pic = self.find1(txt, r'<img[^>]*?\sdata-src=["\']([^"\']+)') or self.find1(txt, r'<img[^>]*?\ssrc=["\']([^"\']+)')
            except Exception as e:
                self.log('详情解析失败 %s' % e)
        if not title: title = '视频'
        vod = {'vod_id':vid,'vod_name':title,'vod_pic':self.fix(pic),'type_name':'','vod_year':'','vod_area':'','vod_remarks':'直连','vod_actor':'','vod_director':'','vod_content':title,'vod_play_from':'高清','vod_play_url':'播放$%s' % vid}
        return {'list':[vod]}

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
                        if data.get('encrypt') in (1, '1'): url = unquote(url)
                        elif data.get('encrypt') in (2, '2'):
                            import base64
                            url = unquote(base64.b64decode(url).decode('utf-8','ignore'))
                    except Exception as e: self.log('player json失败 %s' % e)
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
            blocks = re.findall(r'<a[^>]+href=["\']([^"\']*?/index\.php/vod/play/id/\d+[^"\']*)["\'][^>]*class=["\'][^"\']*video-item-col[^"\']*["\'][\s\S]*?</a>', txt, re.I)
            if blocks:
                for href0 in blocks:
                    pass
            # 以 a.video-item-col 为主，避免把头部推荐链接误入
            for m in re.finditer(r'<a[^>]+href=["\']([^"\']*?/index\.php/vod/play/id/\d+[^"\']*)["\'][^>]*class=["\'][^"\']*video-item-col[^"\']*["\'][\s\S]*?</a>', txt, re.I):
                block = m.group(0); href = self.fix(m.group(1))
                if not href or href in seen: continue
                name = self.clean(self.find1(block, r'<div[^>]+class=["\'][^"\']*video-desc-content[^"\']*["\'][^>]*>([\s\S]*?)</div>') or self.find1(block, r'alt=["\']([^"\']+)'))
                pic = self.fix(self.find1(block, r'<img[^>]*?\sdata-src=["\']([^"\']+)') or self.find1(block, r'<img[^>]*?\sdata-original=["\']([^"\']+)') or self.find1(block, r'<img[^>]*?\ssrc=["\']([^"\']+)'))
                if 'loading' in pic or 'placeholder' in pic: pic = ''
                remark = self.clean(self.find1(block, r'<div[^>]+class=["\'][^"\']*right[^"\']*["\'][^>]*>([\s\S]*?)</div>')) or '直连'
                if not name: continue
                seen.add(href)
                vods.append({'vod_id':href+'|$|'+quote(name)+'|$|'+pic, 'vod_name':name, 'vod_pic':pic, 'vod_remarks':remark})
            if not vods:
                for m in re.finditer(r'<a[^>]+href=["\']([^"\']*?/index\.php/vod/play/id/\d+[^"\']*)["\'][\s\S]*?<img[^>]+data-src=["\']([^"\']+)["\'][\s\S]*?<div[^>]+class=["\'][^"\']*video-desc-content[^"\']*["\'][^>]*>([\s\S]*?)</div>', txt, re.I):
                    href,pic,name = self.fix(m.group(1)), self.fix(m.group(2)), self.clean(m.group(3))
                    if href and href not in seen and name:
                        seen.add(href); vods.append({'vod_id':href+'|$|'+quote(name)+'|$|'+pic,'vod_name':name,'vod_pic':pic,'vod_remarks':'直连'})
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
    def playHeader(self, url): return {'User-Agent': self.headers['User-Agent'], 'Referer': self.host + '/'}
    def localProxy(self, param): return [404, 'text/plain', b'']
    def manualVideoCheck(self): return True
    def liveContent(self, url): return None
    def action(self, action): return None
    def destroy(self): return None

spider = Spider()