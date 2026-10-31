# -*- coding: utf-8 -*-
# FongMi/TVBox Python Spider - 338TV
# 只动态获取最新网址；分类/筛选本地写死；init/homeContent 零网络

import re, json, time, html
from urllib.parse import urljoin, quote
import requests, urllib3
urllib3.disable_warnings()

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        def fetch(self,*a,**k): return None

class Spider(BaseSpider):
    def __init__(self):
        self.base = 'https://338tv1.xyz'
        self.entry = 'https://338tv1.xyz/main.html'
        self.host = self.base
        self.host_time = 0
        self.headers = {'User-Agent':'Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36','Accept':'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8','Accept-Language':'zh-CN,zh;q=0.9'}
        self.classes = [
            {'type_id':'28','type_name':'短视频'}, {'type_id':'25','type_name':'黑料'},
            {'type_id':'29','type_name':'综艺'}, {'type_id':'41','type_name':'人兽'},
            {'type_id':'42','type_name':'二次元'}, {'type_id':'37','type_name':'AV解说'},
            {'type_id':'43','type_name':'同性恋'}, {'type_id':'14','type_name':'猎奇'},
            {'type_id':'24','type_name':'338原创'}, {'type_id':'31','type_name':'欧美'},
            {'type_id':'39','type_name':'日韩'}, {'type_id':'26','type_name':'国产'},
            {'type_id':'27','type_name':'偷拍'}, {'type_id':'30','type_name':'动漫'},
            {'type_id':'34','type_name':'经典三级'}, {'type_id':'35','type_name':'制片厂'},
            {'type_id':'36','type_name':'明星淫梦'}, {'type_id':'38','type_name':'强奸乱伦'},
            {'type_id':'32','type_name':'福利姬'}, {'type_id':'13','type_name':'制服诱惑'}]
        self.filters = {c['type_id']:[{'key':'sort','name':'排序','value':[{'n':'最新','v':''}]}] for c in self.classes}

    def log(self,msg):
        try: print('[338TV] %s' % msg)
        except Exception: pass
    def getName(self): return '338TV'
    def getDependence(self): return []
    def init(self, extend=''): return None
    def destroy(self): return None
    def homeContent(self, filter): return {'class':self.classes,'filters':self.filters if filter else {}}
    def getHomeContent(self, filter): return self.homeContent(filter)
    def siteInfo(self): return {'current':self.host,'entry':self.entry,'route':'vodtype/vodplay-dplayer','home':'zero-network'}

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
            r=self.req(self.entry,timeout=10); txt=self.textOf(r); final=(getattr(r,'url','') or self.entry)
            for x in re.findall(r'https?://(?:www\.)?338tv[0-9a-z.-]*\.[a-z]{2,}',txt+' '+final,re.I): candidates.append(x.rstrip('/'))
        except Exception as e: self.log('入口探测失败 %s %s'%(self.entry,e))
        seen=[]
        for c in candidates:
            c=c.rstrip('/')
            if c and c not in seen: seen.append(c)
        for h in seen:
            try:
                r=self.req(h+'/main.html',timeout=10); txt=self.textOf(r)
                if r.status_code<400 and ('338TV' in txt or '/index.php/vodplay/' in txt):
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
        vods,seen=[],set()
        blocks=re.findall(r'(<div[^>]+class=["\'][^"\']*vod-item[^"\']*["\'][\s\S]*?)(?=<div[^>]+class=["\'][^"\']*(?:abk-item\s+)?vod-item|</div>\s*</div>\s*</div>|<div class="pagination"|$)',txt,re.I)
        if not blocks:
            blocks=re.findall(r'(<a[^>]+href=["\'][^"\']*/index\.php/vodplay/\d+-\d+-\d+\.html["\'][\s\S]{0,1000}?</a>)',txt,re.I)
        for b in blocks:
            try:
                if 'downurl' in b or 'kcg1748' in b: continue
                m=re.search(r'href=["\']([^"\']*/index\.php/vodplay/(\d+)-\d+-\d+\.html)["\']',b,re.I)
                if not m: continue
                url=self.absUrl(m.group(1))
                if url in seen: continue
                seen.add(url)
                name=''
                for pat in [r'class=["\'][^"\']*vod-title[^"\']*["\'][^>]*>([\s\S]{0,260}?)</a>', r'title=["\']([^"\']+)["\']', r'alt=["\']([^"\']+)["\']']:
                    nm=re.search(pat,b,re.I)
                    if nm:
                        name=self.clean(nm.group(1)); break
                if not name: name='338TV-%s'%m.group(2)
                pic=''
                pm=re.search(r'<img[^>]+(?:data-original|data-src|src)=["\']([^"\']+)["\']',b,re.I)
                if pm: pic=self.absUrl(pm.group(1))
                remark=''
                rm=re.search(r'class=["\'][^"\']*vod-duration[^"\']*["\'][^>]*>([\s\S]{0,80}?)</',b,re.I)
                if rm: remark=self.clean(rm.group(1))
                vods.append({'vod_id':url,'vod_name':name,'vod_pic':pic,'vod_remarks':remark})
            except Exception as e: self.log('列表单条失败 %s'%e)
        return vods

    def homeVideoContent(self):
        try:
            txt=self.textOf(self.req(self.getHost()+'/main.html',timeout=15))
            return {'list':self.parseList(txt)[:24]}
        except Exception as e:
            self.log('首页视频失败 %s'%e); return {'list':[]}

    def categoryContent(self,tid,pg,filter,extend):
        try: pg=int(pg or 1)
        except Exception: pg=1
        try:
            host=self.getHost(); tid=str(tid)
            url='%s/index.php/vodtype/%s.html'%(host,tid) if pg<=1 else '%s/index.php/vodtype/%s-%s.html'%(host,tid,pg)
            vods=self.parseList(self.textOf(self.req(url,timeout=15)))
            return {'list':vods,'page':pg,'pagecount':pg+1 if vods else pg,'limit':30,'total':999999 if vods else 0}
        except Exception as e:
            self.log('分类失败 tid=%s pg=%s %s'%(tid,pg,e)); return {'list':[],'page':pg,'pagecount':1,'limit':30,'total':0}

    def searchContent(self,key,quick,pg='1'):
        try:
            host=self.getHost(); key=str(key or '').strip(); page=int(pg or 1)
            url='%s/index.php/ajax/suggest?mid=1&wd=%s&page=%s'%(host,quote(key),page)
            r=self.req(url,timeout=12); data=json.loads(self.textOf(r))
            vods=[]
            for it in data.get('list',[]) or []:
                try:
                    vid=str(it.get('id') or '')
                    name=self.clean(it.get('name') or it.get('vod_name') or '')
                    pic=it.get('pic') or it.get('vod_pic') or ''
                    if not vid: continue
                    vods.append({'vod_id':'%s/index.php/vodplay/%s-1-1.html'%(host,vid),'vod_name':name or ('338TV-'+vid),'vod_pic':self.absUrl(pic),'vod_remarks':self.clean(it.get('remarks') or it.get('type_name') or '')})
                except Exception: pass
            return {'list':vods}
        except Exception as e:
            self.log('搜索失败 %s %s'%(key,e)); return {'list':[]}
    def searchContentPage(self,key,quick,pg): return self.searchContent(key,quick,pg)

    def detailContent(self,ids):
        try:
            url=ids[0] if isinstance(ids,list) else ids
            txt=self.textOf(self.req(url,timeout=15))
            name=''
            m=re.search(r'<h1[^>]*>([\s\S]{0,300}?)</h1>',txt,re.I)
            if m: name=self.clean(m.group(1))
            if not name:
                m=re.search(r'<title[^>]*>([\s\S]*?)(?:-|_)?在线观看',txt,re.I)
                if m: name=self.clean(m.group(1))
            pic=''
            pm=re.search(r'pic\s*:\s*["\']([^"\']+)["\']',txt,re.I)
            if not pm: pm=re.search(r'<img[^>]+(?:data-original|data-src|src)=["\']([^"\']+\.(?:jpg|jpeg|png|webp|gif)[^"\']*)["\']',txt,re.I)
            if pm: pic=self.absUrl(pm.group(1))
            content=name
            cm=re.search(r'<div[^>]+class=["\'][^"\']*vod-content[^"\']*["\'][^>]*>([\s\S]{0,800}?)</div>',txt,re.I)
            if cm: content=self.clean(cm.group(1)) or name
            vod={'vod_id':url,'vod_name':name or '338TV','vod_pic':pic,'type_name':'','vod_content':content,'vod_play_from':'338TV','vod_play_url':'播放$%s'%url}
            return {'list':[vod]}
        except Exception as e:
            self.log('详情失败 %s'%e); return {'list':[]}

    def playerContent(self,flag,id,vipFlags):
        try:
            if self.isMedia(id): return {'parse':0,'url':id,'header':self.headers}
            txt=self.textOf(self.req(id,timeout=15))
            play=''
            m=re.search(r'url\s*:\s*["\']([^"\']+\.(?:m3u8|mp4)[^"\']*)["\']',txt,re.I)
            if m: play=m.group(1)
            if not play:
                m=re.search(r'(https?://[^"\'<>\s]+\.(?:m3u8|mp4)[^"\'<>\s]*)',txt,re.I)
                if m: play=m.group(1)
            play=self.absUrl(play) if play else id
            return {'parse':0 if self.isMedia(play) else 1,'url':play,'header':self.headers}
        except Exception as e:
            self.log('播放失败 %s'%e); return {'parse':1,'url':id,'header':self.headers}
    def isMedia(self,u): return bool(re.search(r'\.(m3u8|mp4)(\?|$)',str(u),re.I))

spider=Spider()