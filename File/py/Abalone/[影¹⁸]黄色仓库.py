# -*- coding: utf-8 -*-
# FongMi/TVBox Python Spider - 黄色仓库
# 只动态获取最新网址；分类/筛选本地写死；init/homeContent 零网络

import re, json, time, html, base64
from urllib.parse import urljoin, quote, unquote
import requests, urllib3
urllib3.disable_warnings()

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        def fetch(self,*a,**k): return None

class Spider(BaseSpider):
    def __init__(self):
        self.base = 'https://ainijiu.sbs'
        self.host = self.base
        self.host_time = 0
        self.headers = {'User-Agent':'Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36','Accept':'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8','Accept-Language':'zh-CN,zh;q=0.9'}
        self.classes = [
            {'type_id':'20','type_name':'最新影片'}, {'type_id':'1','type_name':'中文字幕'},
            {'type_id':'2','type_name':'亚洲视频'}, {'type_id':'3','type_name':'欧美专区'},
            {'type_id':'4','type_name':'人妻熟女'}, {'type_id':'5','type_name':'成人动漫'}]
        self.filters = {c['type_id']:[{'key':'sort','name':'排序','value':[{'n':'最新','v':''}]}] for c in self.classes}

    def log(self,msg):
        try: print('[黄色仓库] %s' % msg)
        except Exception: pass
    def getName(self): return '黄色仓库'
    def getDependence(self): return []
    def init(self, extend=''): return None
    def destroy(self): return None
    def homeContent(self, filter): return {'class':self.classes, 'filters':self.filters if filter else {}}
    def getHomeContent(self, filter): return self.homeContent(filter)
    def siteInfo(self): return {'current':self.host, 'hint':self.base, 'route':'maccms-play-first', 'home':'zero-network'}

    def req(self,url,timeout=15): return requests.get(url,headers=self.headers,timeout=timeout,verify=False,allow_redirects=True)
    def textOf(self,r):
        if r is None: return ''
        if hasattr(r,'encoding') and not r.encoding: r.encoding='utf-8'
        try: return r.text
        except Exception:
            try: return r.content.decode('utf-8','ignore')
            except Exception: return str(r)

    def getHost(self, force=False):
        if not force and self.host and time.time()-self.host_time < 1800: return self.host
        candidates=[self.base]
        try:
            r=self.req(self.base+'/',timeout=10); txt=self.textOf(r); final=(getattr(r,'url','') or self.base).rstrip('/')
            for x in re.findall(r'https?://(?:www\.)?[a-z0-9.-]*(?:ainijiu|wykjyy)[a-z0-9.-]*\.[a-z]{2,}',txt+' '+final,re.I): candidates.append(x.rstrip('/'))
        except Exception as e: self.log('入口探测失败 %s %s'%(self.base,e))
        seen=[]
        for c in candidates:
            c=c.rstrip('/')
            if c and c not in seen: seen.append(c)
        for h in seen:
            try:
                r=self.req(h+'/',timeout=10); txt=self.textOf(r)
                if r.status_code<400 and ('黄色仓库' in txt or '/index.php/vod/play/' in txt):
                    self.host=h; self.host_time=time.time(); return self.host
            except Exception as e: self.log('候选域名不可用 %s %s'%(h,e))
        self.host=self.base; self.host_time=time.time(); return self.host

    def absUrl(self,u):
        if not u: return ''
        u=html.unescape(u).strip().replace('\\/','/')
        if u.startswith('//'): return 'https:'+u
        return urljoin(self.getHost().rstrip('/')+'/',u)
    def clean(self,s):
        s=html.unescape(str(s or ''))
        s=re.sub(r'<script[\s\S]*?</script>|<style[\s\S]*?</style>',' ',s,flags=re.I)
        s=re.sub(r'<[^>]+>',' ',s)
        return re.sub(r'\s+',' ',s).strip()

    def parseList(self,txt):
        vods,seen=[],set(); blocks=re.findall(r'(<li[\s\S]*?</li>)',txt,re.I)
        if not blocks: blocks=re.findall(r'(<a[^>]+href=["\'][^"\']*/index\.php/vod/play/id/\d+/sid/\d+/nid/\d+\.html["\'][\s\S]{0,1000}?</a>)',txt,re.I)
        for b in blocks:
            try:
                m=re.search(r'href=["\']([^"\']*/index\.php/vod/play/id/(\d+)/sid/\d+/nid/\d+\.html)["\']',b,re.I)
                if not m: continue
                url=self.absUrl(m.group(1))
                if url in seen: continue
                seen.add(url); name=''
                for pat in [r'<h4[\s\S]*?<a[^>]*(?:title=["\']([^"\']+)["\'])?[^>]*>([\s\S]{0,300}?)</a>[\s\S]*?</h4>', r'title=["\']([^"\']+)["\']', r'alt=["\']([^"\']+)["\']']:
                    nm=re.search(pat,b,re.I)
                    if nm:
                        name=self.clean(nm.group(1) or (nm.group(2) if len(nm.groups())>1 else ''))
                        if name: break
                if not name: name='黄色仓库-%s'%m.group(2)
                pic=''; pm=re.search(r'<img[^>]+(?:data-original|data-src|src)=["\']([^"\']+)["\']',b,re.I)
                if pm:
                    pic=self.absUrl(pm.group(1))
                    if 'lazyload' in pic or 'lazy' in pic: pic=''
                remark=''; rm=re.search(r'<p[^>]+class=["\'][^"\']*vodtitle[^"\']*["\'][^>]*>([\s\S]*?)</p>',b,re.I)
                if rm: remark=self.clean(rm.group(1))
                vods.append({'vod_id':url,'vod_name':name,'vod_pic':pic,'vod_remarks':remark})
            except Exception as e: self.log('列表单条失败 %s'%e)
        return vods

    def homeVideoContent(self):
        try: return {'list':self.parseList(self.textOf(self.req(self.getHost()+'/',timeout=15)))[:24]}
        except Exception as e: self.log('首页视频失败 %s'%e); return {'list':[]}

    def categoryContent(self,tid,pg,filter,extend):
        try: pg=int(pg or 1)
        except Exception: pg=1
        try:
            host=self.getHost(); tid=str(tid)
            if tid=='20': url=host+'/' if pg<=1 else '%s/index.php/vod/type/id/20/page/%s.html'%(host,pg)
            else: url='%s/index.php/vod/type/id/%s.html'%(host,tid) if pg<=1 else '%s/index.php/vod/type/id/%s/page/%s.html'%(host,tid,pg)
            vods=self.parseList(self.textOf(self.req(url,timeout=15)))
            return {'list':vods,'page':pg,'pagecount':pg+1 if vods else pg,'limit':20,'total':999999 if vods else 0}
        except Exception as e:
            self.log('分类失败 tid=%s pg=%s %s'%(tid,pg,e)); return {'list':[],'page':pg,'pagecount':1,'limit':20,'total':0}

    def searchContent(self,key,quick,pg='1'):
        try:
            host=self.getHost(); key=str(key or '').strip()
            for u in ['%s/index.php/vod/search.html?wd=%s'%(host,quote(key)), '%s/index.php/vod/search/wd/%s.html'%(host,quote(key))]:
                try:
                    r=self.req(u,timeout=12)
                    if r.status_code==200:
                        vods=self.parseList(self.textOf(r))
                        if vods: return {'list':vods}
                except Exception: pass
            out,seen=[],set()
            for c in self.classes:
                if len(out)>=24: break
                for v in self.categoryContent(c['type_id'],'1',False,{}).get('list',[]):
                    if v['vod_id'] in seen: continue
                    if not key or key in v.get('vod_name','') or key in v.get('vod_remarks',''):
                        seen.add(v['vod_id']); out.append(v)
                    if len(out)>=24: break
            if not out: out=self.categoryContent('20','1',False,{}).get('list',[])[:20]
            return {'list':out}
        except Exception as e:
            self.log('搜索失败 %s %s'%(key,e)); return {'list':[]}
    def searchContentPage(self,key,quick,pg): return self.searchContent(key,quick,pg)

    def parsePlayerJson(self,txt):
        m=re.search(r'player_\w+\s*=\s*(\{[\s\S]*?\})\s*</script>',txt,re.I)
        if not m: m=re.search(r'player_\w+\s*=\s*(\{[\s\S]{0,3000}?\})',txt,re.I)
        if not m: return {}
        raw=m.group(1)
        try: return json.loads(raw)
        except Exception:
            try: return json.loads(raw.replace('\\/','/'))
            except Exception: return {}

    def detailContent(self,ids):
        try:
            url=ids[0] if isinstance(ids,list) else ids; txt=self.textOf(self.req(url,timeout=15)); name=''
            m=re.search(r'<title[^>]*>\s*(?:在线播放)?([\s\S]*?)(?:\s+第\d+集)?\s*-\s*高清资源',txt,re.I)
            if m: name=self.clean(m.group(1))
            if not name:
                m=re.search(r'title=["\']([^"\']+)["\']',txt,re.I)
                if m: name=self.clean(m.group(1))
            pic=''; pm=re.search(r'<img[^>]+(?:data-original|data-src|src)=["\']([^"\']+\.(?:jpg|jpeg|png|webp)[^"\']*)["\']',txt,re.I)
            if pm: pic=self.absUrl(pm.group(1))
            typ=''; tm=re.search(r'<p[^>]+class=["\'][^"\']*vodtitle[^"\']*["\'][^>]*>([\s\S]*?)</p>',txt,re.I)
            if tm: typ=self.clean(tm.group(1)).split('-')[0].strip()
            plays=[]
            for p in re.findall(r'href=["\']([^"\']*/index\.php/vod/play/id/\d+/sid/\d+/nid/\d+\.html)["\']',txt,re.I):
                pu=self.absUrl(p)
                if pu not in plays: plays.append(pu)
            if url not in plays: plays.insert(0,url)
            return {'list':[{'vod_id':url,'vod_name':name or '黄色仓库','vod_pic':pic,'type_name':typ,'vod_content':name or '', 'vod_play_from':'黄色仓库','vod_play_url':'#'.join(['第%s集$%s'%(i+1,u) for i,u in enumerate(plays[:50])])}]}
        except Exception as e:
            self.log('详情失败 %s'%e); return {'list':[]}

    def playerContent(self,flag,id,vipFlags):
        try:
            if self.isMedia(id): return {'parse':0,'url':id,'header':self.headers}
            txt=self.textOf(self.req(id,timeout=15)); data=self.parsePlayerJson(txt); play=data.get('url') or ''
            enc=int(data.get('encrypt',0) or 0) if data else 0
            if enc==1: play=unquote(play)
            elif enc==2: play=unquote(base64.b64decode(play).decode('utf-8','ignore'))
            if not play:
                m=re.search(r'(https?://[^"\'<>\s]+\.(?:m3u8|mp4)[^"\'<>\s]*)',txt,re.I)
                if m: play=m.group(1)
            play=self.absUrl(play) if play else id
            return {'parse':0 if self.isMedia(play) else 1,'url':play,'header':self.headers}
        except Exception as e:
            self.log('播放失败 %s'%e); return {'parse':1,'url':id,'header':self.headers}
    def isMedia(self,u): return bool(re.search(r'\.(m3u8|mp4)(\?|$)',str(u),re.I))

spider=Spider()