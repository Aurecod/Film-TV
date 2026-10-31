# -*- coding: utf-8 -*-
# FongMi/TVBox Python Spider - BOSSTV
# 规则：只动态获取最新网址；分类/筛选本地写死；init/homeContent 零网络

import re, json, time, html
from urllib.parse import urljoin, quote, unquote
import requests, urllib3
urllib3.disable_warnings()

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        def fetch(self, *args, **kwargs): return None

class Spider(BaseSpider):
    def __init__(self):
        self.base = 'https://bosstv901.xyz'
        self.host = self.base
        self.host_time = 0
        self.headers = {
            'User-Agent':'Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36',
            'Accept':'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language':'zh-CN,zh;q=0.9'
        }
        self.classes = [
            {'type_id':'1','type_name':'日韩无码'}, {'type_id':'2','type_name':'国产精品'},
            {'type_id':'3','type_name':'日韩精品'}, {'type_id':'4','type_name':'欧美精品'},
            {'type_id':'5','type_name':'自拍偷拍'}, {'type_id':'6','type_name':'中文字幕'},
            {'type_id':'7','type_name':'人妻系列'}, {'type_id':'8','type_name':'制服诱惑'},
            {'type_id':'9','type_name':'强奸乱伦'}, {'type_id':'10','type_name':'AV明星'},
            {'type_id':'11','type_name':'国产传媒'}, {'type_id':'12','type_name':'巨乳系列'},
            {'type_id':'13','type_name':'颜射系列'}, {'type_id':'14','type_name':'自慰系列'}
        ]
        self.filters = {c['type_id']:[{'key':'sort','name':'排序','value':[{'n':'最新','v':''}]}] for c in self.classes}

    def log(self, msg):
        try: print(msg)
        except Exception: pass

    def getName(self): return 'BOSSTV'
    def getDependence(self): return []
    def init(self, extend=''):
        # 首页分类入口零网络，动态域名只在真实取数据阶段执行
        return None
    def destroy(self): return None

    def homeContent(self, filter):
        return {'class': self.classes, 'filters': self.filters if filter else {}}
    def getHomeContent(self, filter):
        return self.homeContent(filter)

    def siteInfo(self):
        return {'current':self.host, 'hint':self.base, 'route':'maccms-html', 'home':'zero-network'}

    def req(self, url, timeout=15):
        r = requests.get(url, headers=self.headers, timeout=timeout, verify=False, allow_redirects=True)
        return r

    def textOf(self, r):
        if r is None: return ''
        if hasattr(r, 'encoding') and not r.encoding:
            r.encoding = 'utf-8'
        try: return r.text
        except Exception:
            try: return r.content.decode('utf-8', 'ignore')
            except Exception: return str(r)

    def getHost(self, force=False):
        if not force and self.host and time.time() - self.host_time < 1800:
            return self.host
        candidates = [self.base]
        try:
            r = self.req(self.base + '/', timeout=10)
            txt = self.textOf(r)
            final = (getattr(r, 'url', '') or self.base).rstrip('/')
            for x in re.findall(r'https?://(?:www\.)?bosstv[0-9a-z.-]*\.[a-z]{2,}', txt + ' ' + final, re.I):
                candidates.append(x.rstrip('/'))
        except Exception as e:
            self.log('BOSSTV入口探测失败 %s %s' % (self.base, e))
        seen = []
        for c in candidates:
            c = c.rstrip('/')
            if c and c not in seen: seen.append(c)
        for h in seen:
            try:
                r = self.req(h + '/', timeout=10)
                txt = self.textOf(r)
                if r.status_code < 400 and ('BOSSTV' in txt or '/index.php/vod/' in txt):
                    self.host = h
                    self.host_time = time.time()
                    return self.host
            except Exception as e:
                self.log('BOSSTV候选域名不可用 %s %s' % (h, e))
        self.host = self.base
        self.host_time = time.time()
        return self.host

    def absUrl(self, u):
        if not u: return ''
        u = html.unescape(u).strip().replace('\\/', '/')
        if u.startswith('//'): return 'https:' + u
        return urljoin(self.getHost().rstrip('/') + '/', u)

    def clean(self, s):
        s = html.unescape(str(s or ''))
        s = re.sub(r'<script[\s\S]*?</script>|<style[\s\S]*?</style>', '', s, flags=re.I)
        s = re.sub(r'<[^>]+>', ' ', s)
        s = re.sub(r'\s+', ' ', s).strip()
        return s

    def parseList(self, txt):
        vods, seen = [], set()
        blocks = re.findall(r'(<div[^>]+class=["\'][^"\']*vod-item-box[^"\']*["\'][\s\S]*?)(?=<div[^>]+class=["\'][^"\']*vod-item-box|</section>|<div class="pagination"|$)', txt, re.I)
        if not blocks:
            blocks = re.findall(r'(<a[^>]+href=["\'][^"\']*/index\.php/vod/detail/id/\d+\.html["\'][\s\S]{0,900}?</a>)', txt, re.I)
        for b in blocks:
            try:
                m = re.search(r'href=["\']([^"\']*/index\.php/vod/detail/id/(\d+)\.html)["\']', b, re.I)
                if not m: continue
                url = self.absUrl(m.group(1)); vid = url
                if vid in seen: continue
                seen.add(vid)
                pic = ''
                pm = re.search(r'(?:data-original|data-src|src)=["\']([^"\']+)["\']', b, re.I)
                if pm: pic = self.absUrl(pm.group(1))
                name = ''
                for pat in [r'alt=["\']([^"\']+)["\']', r'title=["\']([^"\']+)["\']', r'class=["\'][^"\']*vod-name[^"\']*["\'][^>]*>([\s\S]{0,200}?)</']:
                    nm = re.search(pat, b, re.I)
                    if nm:
                        name = self.clean(nm.group(1)); break
                if not name: name = 'BOSSTV-%s' % m.group(2)
                remark = ''
                rm = re.search(r'class=["\'][^"\']*(?:tag|remarks|pic-text|vod-time)[^"\']*["\'][^>]*>([\s\S]{0,120}?)</', b, re.I)
                if rm: remark = self.clean(rm.group(1))
                vods.append({'vod_id':vid,'vod_name':name,'vod_pic':pic,'vod_remarks':remark})
            except Exception as e:
                self.log('BOSSTV单条列表解析失败 %s' % e)
        return vods

    def homeVideoContent(self):
        try:
            txt = self.textOf(self.req(self.getHost() + '/', timeout=15))
            return {'list': self.parseList(txt)[:24]}
        except Exception as e:
            self.log('BOSSTV首页视频失败 %s' % e)
            return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg or 1)
        except Exception: pg = 1
        try:
            host = self.getHost()
            url = '%s/index.php/vod/type/id/%s.html' % (host, tid) if pg <= 1 else '%s/index.php/vod/type/id/%s/page/%s.html' % (host, tid, pg)
            txt = self.textOf(self.req(url, timeout=15))
            vods = self.parseList(txt)
            return {'list':vods, 'page':pg, 'pagecount':pg+1 if vods else pg, 'limit':24, 'total':999999 if vods else 0}
        except Exception as e:
            self.log('BOSSTV分类失败 tid=%s pg=%s %s' % (tid, pg, e))
            return {'list':[], 'page':pg, 'pagecount':1, 'limit':24, 'total':0}

    def searchContent(self, key, quick, pg='1'):
        try:
            host = self.getHost()
            url = '%s/index.php/vod/search.html?wd=%s' % (host, quote(key or ''))
            txt = self.textOf(self.req(url, timeout=15))
            return {'list': self.parseList(txt)}
        except Exception as e:
            self.log('BOSSTV搜索失败 %s %s' % (key, e))
            return {'list': []}

    def searchContentPage(self, key, quick, pg):
        return self.searchContent(key, quick, pg)

    def detailContent(self, ids):
        try:
            url = ids[0] if isinstance(ids, list) else ids
            txt = self.textOf(self.req(url, timeout=15))
            name = ''
            m = re.search(r'<title[^>]*>([\s\S]*?)(?:-|_)?BOSSTV[\s\S]*?</title>', txt, re.I)
            if m: name = self.clean(m.group(1)).replace('播放地址：','').replace('正在觀看：','')
            if not name:
                m = re.search(r'class=["\'][^"\']*title[^"\']*["\'][^>]*>([\s\S]{0,300}?)</', txt, re.I)
                if m: name = self.clean(m.group(1))
            pic = ''
            pm = re.search(r'(?:data-original|data-src|src)=["\']([^"\']+\.(?:jpg|jpeg|png|webp)[^"\']*)["\']', txt, re.I)
            if pm: pic = self.absUrl(pm.group(1))
            type_name = ''
            cm = re.search(r'vod_class["\']?\s*:\s*["\']([^"\']+)', txt, re.I)
            if cm:
                try: type_name = self.clean(cm.group(1).encode('utf-8').decode('unicode_escape'))
                except Exception: type_name = self.clean(cm.group(1))
            plays = []
            for p in re.findall(r'href=["\']([^"\']*/index\.php/vod/play/id/\d+/sid/\d+/nid/\d+\.html)["\']', txt, re.I):
                pu = self.absUrl(p)
                if pu not in plays: plays.append(pu)
            if not plays and '/index.php/vod/play/' in url:
                plays = [url]
            vod = {'vod_id':url, 'vod_name':name or 'BOSSTV', 'vod_pic':pic, 'type_name':type_name, 'vod_content':name or '', 'vod_play_from':'BOSSTV', 'vod_play_url':'#'.join(['第%s集$%s'%(i+1,u) for i,u in enumerate(plays)])}
            return {'list':[vod]}
        except Exception as e:
            self.log('BOSSTV详情失败 %s' % e)
            return {'list': []}

    def playerContent(self, flag, id, vipFlags):
        try:
            url = id
            if not re.search(r'/index\.php/vod/play/', url):
                d = self.detailContent([url]).get('list', [])
                if d and d[0].get('vod_play_url'):
                    url = d[0]['vod_play_url'].split('$',1)[-1].split('#')[0]
            txt = self.textOf(self.req(url, timeout=15)) if not self.isMedia(url) else ''
            play = ''
            if txt:
                m = re.search(r'player_\w+\s*=\s*(\{[\s\S]*?\})\s*</script>', txt, re.I)
                if not m:
                    m = re.search(r'player_\w+\s*=\s*(\{[\s\S]{0,3000}?\})', txt, re.I)
                if m:
                    raw = m.group(1)
                    try:
                        data = json.loads(raw)
                    except Exception:
                        data = json.loads(raw.encode('utf-8').decode('unicode_escape'))
                    play = data.get('url') or data.get('link_next') or ''
                    if data.get('encrypt') == 1:
                        play = unquote(play)
                    elif data.get('encrypt') == 2:
                        import base64
                        play = unquote(base64.b64decode(play).decode('utf-8','ignore'))
            if not play:
                m = re.search(r'(https?://[^"\'<>\s]+\.(?:m3u8|mp4)[^"\'<>\s]*)', txt or url, re.I)
                if m: play = m.group(1)
            play = self.absUrl(play) if play else url
            return {'parse':0 if self.isMedia(play) else 1, 'url':play, 'header':self.headers}
        except Exception as e:
            self.log('BOSSTV播放失败 %s' % e)
            return {'parse':1, 'url':id, 'header':self.headers}

    def isMedia(self, u):
        return bool(re.search(r'\.(m3u8|mp4)(\?|$)', str(u), re.I))

spider = Spider()
