# -*- coding: utf-8 -*-
# FongMi/TVBox Python Spider - 搜搜啪 www.sosopa.cc
import re, json
from urllib.parse import urljoin, quote, unquote
try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        def fetch(self, url, headers=None, timeout=10):
            import requests
            return requests.get(url, headers=headers, timeout=timeout, verify=False)
        def log(self, msg): print(msg)

class Spider(BaseSpider):
    def getName(self): return '搜搜啪'
    def getDependence(self): return []

    def init(self, extend=''):
        self.host = 'https://www.sosopa.cc'
        self.headers = {'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36', 'Accept':'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', 'Referer':'https://www.sosopa.cc/'}
        self.picHeaders = {'User-Agent':self.headers['User-Agent'], 'Accept':'image/avif,image/webp,image/apng,image/*,*/*;q=0.8'}
        self.groups = {
            '1': {'name':'中文传媒', 'items':[('45','传媒-麻豆传媒'),('46','传媒-精东影业'),('47','传媒-蜜桃传媒'),('48','传媒-果冻传媒'),('72','传媒-糖心传媒'),('73','传媒-乐播传媒'),('74','传媒-葫芦影业'),('2','传媒-星空无限传媒'),('3','传媒-SA国际传媒'),('15','传媒-情欲国潮'),('20','传媒-性视界传媒'),('21','传媒-天美传媒'),('22','传媒-皇家华人'),('23','传媒-扣扣传媒'),('24','传媒-91传媒'),('25','传媒-杏吧传媒'),('26','传媒-起点传媒'),('27','传媒-CCAV成人头条'),('28','传媒-渡边传媒'),('29','传媒-辣椒原创')]},
            '2': {'name':'明星网黄', 'items':[('54','玩偶姐姐'),('55','台湾粉红兔'),('79','刘玥'),('80','小二先生'),('81','白菜妹妹'),('82','地雷系'),('83','唐伯虎'),('84','鸡教练'),('85','粉色情人'),('86','冉冉学姐'),('87','黑椒盖饭'),('88','水冰月'),('89','捅主任'),('90','御梦子'),('91','小欣奈'),('92','桥本香菜'),('93','柚子猫'),('94','台北娜娜'),('95','饼干姐姐')]},
            '3': {'name':'国产', 'items':[('58','国产-网红'),('59','国产-户外'),('60','国产-吃瓜'),('61','国产-台湾JVID'),('16','国产-自拍'),('17','国产-偷拍'),('18','国产-其他')]},
            '4': {'name':'日本AV', 'items':[('49','日本-中文字幕'),('50','日本-无码流出'),('51','日本-高清有码'),('52','日本-东京热'),('53','日本-一本道'),('30','日本-其他'),('31','日本-女优')]},
            '5': {'name':'动漫', 'items':[('56','动漫-黄漫'),('57','动漫-里番中字')]},
            '6': {'name':'欧美AV', 'items':[('62','欧美-高清无码'),('63','欧美-高清有码'),('64','欧美-中文字幕')]},
            '7': {'name':'小众口味', 'items':[('65','恐怖色情'),('66','重口味'),('67','小众女同'),('68','TS人妖'),('69','SM虐待'),('70','其他口味')]}
        }
        self.classes = [{'type_id': k, 'type_name': v['name']} for k, v in self.groups.items()]
        self.filters = {}
        for k, v in self.groups.items():
            self.filters[k] = [{'key':'cate','name':'分类','value':[{'n':'全部','v':''}] + [{'n':name,'v':tid} for tid, name in v['items']]}]

    def homeContent(self, filter): return {'class': self.classes, 'filters': self.filters if filter else {}}
    def homeVideoContent(self): return {'list': self.parseList(self.host + '/')}

    def categoryContent(self, tid, pg, filter, extend):
        pg = str(pg or '1')
        real_tid = (extend or {}).get('cate') or self.firstChild(tid)
        url = self.host + ('/index.php/vod/type/id/%s.html' % real_tid if pg == '1' else '/index.php/vod/type/id/%s/page/%s.html' % (real_tid, pg))
        vods = self.parseList(url)
        return {'list': vods, 'page': int(pg), 'pagecount': 999999 if vods else int(pg), 'limit': 16, 'total': 999999 if vods else 0}

    def detailContent(self, ids):
        vid = ids[0]
        title, pic = '', ''
        if '|$|' in vid:
            parts = vid.split('|$|')
            vid = parts[0]
            title = unquote(parts[1]) if len(parts) > 1 else ''
            pic = parts[2] if len(parts) > 2 else ''
        try:
            txt = '' if (title and pic) else self.html(vid)
            if not title:
                title = self.clean(self.find1(txt, r'<h1[^>]*>([\s\S]*?)</h1>') or self.find1(txt, r'<title[^>]*>在线播放([\s\S]*?)(?:HD|高清| - )'))
            if not title:
                m = re.search(r'var\s+player_\w+\s*=\s*(\{[\s\S]*?\})\s*</script>', txt, re.I)
                if m: title = (json.loads(m.group(1)).get('vod_data') or {}).get('vod_name','')
            if not pic:
                pic = self.find1(txt, r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)') or self.find1(txt, r'<img[^>]+data-src=["\']([^"\']+)') or self.find1(txt, r'<img[^>]+src=["\']([^"\']+)')
        except Exception as e:
            self.log('详情解析失败 %s' % e)
        if not title: title = self.clean(vid.split('/')[-1]) or '视频'
        vod = {'vod_id':vid, 'vod_name':title, 'vod_pic':self.fix(pic), 'type_name':'', 'vod_year':'', 'vod_area':'', 'vod_remarks':'直连', 'vod_actor':'', 'vod_director':'', 'vod_content':title, 'vod_play_from':'高清资源', 'vod_play_url':'播放$%s' % vid}
        return {'list':[vod]}

    def searchContent(self, key, quick, pg='1'):
        url = self.host + '/index.php/vod/search.html?wd=' + quote(key or '')
        vods = self.parseList(url)
        return {'list': vods, 'page': int(pg or '1'), 'total': len(vods)}

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
            for m in re.finditer(r'<div[^>]+class=["\'][^"\']*thumbnail\s+group[^"\']*["\'][\s\S]*?</div>\s*</div>', txt, re.I):
                block = m.group(0)
                href = self.fix(self.find1(block, r'<a[^>]+href=["\']([^"\']*?/index\.php/vod/play/id/\d+[^"\']*)'))
                if not href or href in seen: continue
                seen.add(href)
                name = self.clean(self.find1(block, r'<div[^>]+class=["\'][^"\']*truncate[^"\']*["\'][\s\S]*?<a[^>]*>([\s\S]*?)</a>') or self.find1(block, r'alt=["\']([^"\']+)'))
                pic = self.fix(self.find1(block, r'<img[^>]+data-src=["\']([^"\']+)') or self.find1(block, r'<img[^>]+data-original=["\']([^"\']+)') or self.find1(block, r'<img[^>]+src=["\']([^"\']+)'))
                if name: vods.append({'vod_id':href+'|$|'+quote(name)+'|$|'+pic, 'vod_name':name, 'vod_pic':pic, 'vod_remarks':'直连'})
            if not vods:
                for m in re.finditer(r'<a[^>]+href=["\']([^"\']*?/index\.php/vod/play/id/\d+[^"\']*)["\'][^>]*>([\s\S]*?)</a>', txt, re.I):
                    href = self.fix(m.group(1)); name = self.clean(m.group(2))
                    if href not in seen and name:
                        seen.add(href); vods.append({'vod_id':href,'vod_name':name,'vod_pic':'','vod_remarks':'直连'})
            return vods
        except Exception as e:
            self.log('列表解析失败 %s %s' % (url, e)); return []


    def firstChild(self, tid):
        g = self.groups.get(str(tid))
        return g['items'][0][0] if g and g.get('items') else str(tid)

    def html(self, url):
        r = self.fetch(url, headers=self.headers, timeout=12)
        return r.content.decode('utf-8','ignore') if hasattr(r,'content') else getattr(r,'text','')
    def fix(self, url): return urljoin(self.host + '/', (url or '').replace('&amp;','&').strip()) if url else ''
    def find1(self, txt, pat):
        m = re.search(pat, txt or '', re.I); return m.group(1) if m else ''
    def clean(self, s):
        s = re.sub(r'<[^>]+>', ' ', s or ''); s = re.sub(r'\s+', ' ', s).strip(); return s[:120]
    def isMedia(self, url): return bool(re.search(r'\.(m3u8|mp4)(\?|$)', url or '', re.I))
    def isNoResult(self, txt): return bool(re.search(r'没有找到|暂无数据|搜索无结果|未找到|404 Not Found', txt or '', re.I))
    def playHeader(self, url): return {'User-Agent': 'Mozilla/5.0', 'Accept': '*/*'}
    def localProxy(self, param): return [404, 'text/plain', b'']
    def manualVideoCheck(self): return True
    def liveContent(self, url): return None
    def action(self, action): return None
    def destroy(self): return None

spider = Spider()