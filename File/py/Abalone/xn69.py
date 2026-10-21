# -*- coding: utf-8 -*-
# ============ TVBox_spider_蜘蛛框架.py 生成器产物 ============
# 站点: https://xn--69-6tia3cb.net (หีหี69.net, 泰文 WordPress 成人站)
# 本文件 = 生成器原件模板 + 站点事实插槽填充 + 成人站全量脱敏档 v2
# 结构说明: 保留模板原件的 cat_scope/cat_href_re/list_scope/detail_tpl/play_tpl/
#           m3u8_var/search_tpl/page_mode 探测插槽与全部方法签名, 按本站实测填参
# 站点事实:
#   - WordPress 自定义主题, SSR 直出, Cloudflare CDN, UA 直连 200 零盾
#   - 分类: nav 9 个, 路由 /category/{slug}/, 翻页 /category/{slug}/page/N/
#     首页分页 /page/N/ (115 页)
#   - 卡片: <a class="post-video" href="{site}/{slug}/{id}/" title="{标题}">
#           <img class="lazy" data-src="{318x180封面}"> <h3>{标题}</h3>
#   - 详情: h1 标题, og:image 封面, og:description 描述,
#           uuid 在 itemprop=embedURL / .responsive-player iframe: lumierecore.com/{uuid}
#   - 取流: POST https://px.lumierecore.com/api/proxy/{uuid} (body={}, CT: application/json, 无鉴权)
#           → {"baseUrl":..., "masterUrl":"https://{桶}/hls/{uuid}/master.jpeg.m3u8"}
#           master 无 EXT-X-KEY 无加密, 分片 .jpeg 伪装 TS → 直通播放
#   - 搜索: ?s={key}, 翻页 /page/N/?s={key}
# ★ 版本兼容: 禁 Python 3.9+ API; 分隔符 $=名称/地址 #=选集 $$$=线路
# ★ 链路策略 v5: 纯直连单线路(用户要求剔除本地代理; 本站零盾直通, localProxy 保留为模板接口不再启用)
import re, json, base64
try:
    import requests as _requests
except Exception:
    _requests = None


class Spider:
    def __init__(self):
        self.site = "https://xn--69-6tia3cb.net"
        self.name = "xn--69-6tia3cb"
        self.header = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 13; SM-S9080) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            "Referer": self.site,
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        self.s = self.session = self.sess = _requests.Session() if _requests else None
        self._extend = {}
        self._home = None
        # ---- 站点结构（生成时按真实源码探测, 以下为本站实测插槽）----
        self.cat_scope = None                              # 分类抓取范围: None=全页; 本站在导航与页脚均含, 全页去重
        self.cat_href_re = '<a[^>]+href="([^"]*category/[^"]+)"[^>]*>(?:<[^>]+>)*([^<]{1,20}?)</a>'  # 仅分类链接
        self.list_scope = None                             # 无统一 ul/li 容器, 卡片为 div.loop-video
        self.detail_tpl = None                             # vod_id 即详情页完整 URL, 无需拼装
        self.play_tpl = None                               # 本站播放为单 uuid 播放器, 见 playerContent
        self.m3u8_var = None                               # 无页面内 m3u8 变量, 取流走 lumierecore proxy API
        self.search_tpl = 'https://xn--69-6tia3cb.net/?s={key}'
        self.page_mode = ('url', 115)

    def getDependence(self):
        return []

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        if not url:
            return False
        u = str(url).lower()
        return u.endswith((".m3u8", ".mp4", ".flv", ".mkv", ".ts", ".avi")) or "m3u8" in u

    def destroy(self):
        pass

    def action(self, action):
        return {}

    def progressVideo(self):
        return {}

    def setVideoFlags(self, flags):
        pass

    def _get(self, url, referer=None, timeout=12):
        """★ 铁律: 仅 urllib 抓取(requests 在部分壳/机连接 CDN 会挂死不触发超时 → 整体卡死)"""
        h = dict(self.header)
        if referer:
            h["Referer"] = referer
        try:
            import urllib.request
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", "ignore")
        except Exception:
            return ""

    def _post_json(self, url, payload=None, timeout=12):
        """POST JSON(body 默认 {}) 返回文本; 仅 urllib(requests 挂死隐患, 已弃用)"""
        body = b'{}' if payload is None else json.dumps(payload).encode('utf-8')
        h = dict(self.header)
        h["Content-Type"] = "application/json"
        try:
            import urllib.request
            req = urllib.request.Request(url, data=body, headers=h, method='POST')
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", "ignore")
        except Exception:
            return ""

    def _u(self, u):
        if not u:
            return u
        u = u.strip()
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("http"):
            return u
        if u.startswith("/"):
            m = re.match(r"(https?://[^/]+)", self.site)
            return (m.group(1) if m else self.site) + u
        return self.site.rstrip("/") + "/" + u.lstrip("/")

    def _cats(self):
        if self._home is None:
            self._home = self._get(self.site)
        html = self._home
        out = []
        seen = set()
        if self.cat_scope:
            m = re.search(self.cat_scope, html, re.S)
            seg = m.group(1) if m else html
        else:
            seg = html
        for hm in re.finditer(self.cat_href_re, seg, re.S):
            href, name = hm.group(1), re.sub(r"<[^>]+>", "", hm.group(2)).strip()
            if not name:
                continue
            name = re.sub(r"\s+", " ", name)
            if len(name) > 12 or name in seen:
                continue
            if any(w in name for w in ("首页", "登录", "注册", "会员", "充值", "APP", "下载", "搜索", "排行", "最新", "热门", "专题", "资讯", "留言", "求片")):
                continue
            seen.add(name)
            out.append({"type_id": self._u(href), "type_name": name})
        return out

    def _items(self, html, base=None):
        out = []
        seen = set()
        base = base or self.site
        if self.list_scope:
            m = re.search(self.list_scope, html, re.S)
            seg = m.group(1) if m else html
        else:
            seg = html
        # ---- 本站卡片: <a class="post-video" href title> <img data-src> <h3> ----
        found_any = False
        for am in re.finditer(r'<a\s+class="post-video"[^>]*href="([^"]+)"[^>]*title="([^"]*)"', seg):
            found_any = True
            href, title = am.group(1), am.group(2)
            if href in seen or 'javascript' in href:
                continue
            start, end = am.start(), seg.find('</a>', am.start())
            block = seg[start:end] if end > start else ''
            im = re.search(r'<img[^>]+data-src="([^"]+)"', block)
            name = _html_unescape(title).strip()
            if not name:
                hm = re.search(r'<h3[^>]*>(.*?)</h3>', block, re.S)
                if hm:
                    name = _html_unescape(re.sub(r"<[^>]+>", "", hm.group(1))).strip()
            if not name or _blocked(name):                # ★ 成人站全量脱敏: 命中即丢弃
                continue
            seen.add(href)
            out.append({
                "vod_id": self._u(href),
                "vod_name": name,
                "vod_pic": self._u(im.group(1)) if im else "",
                "vod_remarks": "",
            })
        if found_any:
            return out
        # ---- 普通 <li> 泛化(其他站型兼容) ----
        for bm in re.finditer(r"<li[^>]*>([\s\S]{50,900}?)</li>", seg):
            block = bm.group(1)
            hm = re.search(r'href="([^"]+)"', block)
            im = re.search(r'<img[^>]+(?:data-original|data-src|src)="([^"]+)"', block)
            tm = re.search(r'(?:title|alt)="([^"]+)"', block)
            if not (hm and tm):
                continue
            vid = self._u(hm.group(1))
            if vid in seen:
                continue
            seen.add(vid)
            out.append({
                "vod_id": vid,
                "vod_name": _html_unescape(tm.group(1)).strip(),
                "vod_pic": self._u(im.group(1)) if im else "",
                "vod_remarks": "",
            })
        if not out:
            for am in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>\s*<img[^>]+(?:data-original|data-src|src)="([^"]+)"[^>]*>', html):
                if am.group(1) in seen:
                    continue
                seen.add(am.group(1))
                out.append({"vod_id": self._u(am.group(1)), "vod_name": "", "vod_pic": self._u(am.group(2)), "vod_remarks": ""})
        return out

    def init(self, extend=""):
        self._extend = {}
        if isinstance(extend, dict):
            self._extend = extend
        elif isinstance(extend, str) and extend.strip():
            try:
                e = json.loads(extend)
                if isinstance(e, dict):
                    self._extend = e
            except Exception:
                pass
        if isinstance(self._extend, dict) and self._extend.get('host'):
            h2 = str(self._extend.get('host')).rstrip('/') + '/'
            self.site = h2
            self.header['Referer'] = h2
        try:
            t = self._get(self.site)
            if t:
                self._home = t
        except Exception:
            pass

    def homeContent(self, filter=None):
        cats = self._cats()
        html = self._home if self._home is not None else self._get(self.site)
        vod_list = self._items(html)
        r = {"class": cats, "list": vod_list, "filters": {}}
        return r

    def homeVideoContent(self):
        if self._home is None:
            self._home = self._get(self.site)
        return {"list": self._items(self._home)}

    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1
        url = self._cat_url(tid, pg)
        html = self._get(url)
        if not html:
            return {"list": [], "page": pg, "pagecount": 1, "limit": 24, "total": 0}
        vod_list = self._items(html)
        pagecount = 1
        total = len(vod_list)
        m = re.search(r"共\s*(\d+)\s*页", html)
        if m:
            pagecount = int(m.group(1))
        # ---- WordPress /page/N/ 分页(本站) ----
        if m is None:
            mx = pg
            for pm in re.finditer(r'[?/]page/(\d+)/?[?"]', html):
                try:
                    n = int(pm.group(1))
                    if n > mx:
                        mx = n
                except Exception:
                    pass
            for pm in re.finditer(r'[?&]paged=(\d+)', html):
                try:
                    n = int(pm.group(1))
                    if n > mx:
                        mx = n
                except Exception:
                    pass
            if mx > 9999:
                mx = pg
            pagecount = mx
        return {"list": vod_list, "page": pg, "pagecount": pagecount, "limit": 24, "total": total}

    def _cat_url(self, tid, pg):
        t = str(tid)
        if t.startswith("http"):
            if "{" in t:
                return t.replace("{id}", str(pg))
            if re.search(r"[?&]page=", t):
                return re.sub(r"page=\d+", "page=%d" % pg, t)
            # ---- WordPress 分类翻页: /category/{slug}/page/N/ ----
            if "/category/" in t and pg > 1:
                return t.rstrip("/") + "/page/" + str(pg) + "/"
            return t.rstrip("/") + "/" if not t.endswith("/") else t
        if self.detail_tpl and "{id}" in t:
            return t
        return self.site.rstrip("/") + "/list/" + t + ".html?page=%d" % pg

    def detailContent(self, ids):
        vid = ids
        if isinstance(ids, (list, tuple)):
            vid = ids[0] if ids else ""
        vid = str(vid).strip()
        url = self._u(vid) if vid.startswith(("/", "http")) else None
        if url is None and self.detail_tpl:
            url = self.site.rstrip("/") + self.detail_tpl.format(id=vid)
        if url is None:
            return {"list": []}
        html = self._get(url)
        if not html:
            return {"list": []}
        title = ""
        tm = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S) or re.search(r"<title[^>]*>([^<]{2,60})</title>", html)
        if tm:
            title = _html_unescape(re.sub(r"<[^>]+>", "", tm.group(1))).strip()
        if not title:
            tm = re.search(r'<meta[^>]+property="og:title"[^>]*content="([^"]+)"', html)
            if tm:
                title = _html_unescape(tm.group(1)).strip()
                # 去站点后缀 " - หีหี69.com ..."
                m2 = re.search(r'\s+[-–—|]\s+[\u0e00-\u0e7f0-9a-zA-Z ]*\.?com.*$', title)
                if m2:
                    title = title[:m2.start()].strip()
        title = title.strip()
        if not title or _blocked(title):                  # ★ 脱敏: 命中穿空
            return {"list": []}
        # 封面: 本站 og:image 为详情原图(页头 logo 会先命中通用 img 正则, 故优先 og:image)
        im = re.search(r'property="og:image" content="([^"]+)"', html) or \
             re.search(r'<img[^>]+(?:data-original|data-src|src)="([^"]+)"[^>]*(?:class="[^"]*pic[^"]*")?', html)
        pic = self._u(im.group(1)) if im else ""
        dm = re.search(r'<p[^>]*class="[^"]*(?:desc|content|intro)[^"]*"[^>]*>([\s\S]{10,2000}?)</p>', html) or \
             re.search(r'property="og:description" content="([^"]+)"', html)
        desc = _html_unescape(re.sub(r"<[^>]+>", "", dm.group(1))).strip() if dm else ""
        # ---- 播放源: 本站单 uuid 播放器, 地址用 lumierecore.com/{uuid} 占位, playerContent 取流 ----
        play_from, play_url = "", ""
        uuid = ""
        seg = ""
        pm = re.search(r'<div class="responsive-player"[^>]*>([\s\S]*?)</div>', html)
        if pm:
            seg = pm.group(1)
        um = re.search(r'lumierecore\.com/([0-9a-fA-F-]{36})', seg)
        if not um:
            um = re.search(r'itemprop="embedURL"[^>]*content="https://lumierecore\.com/([0-9a-fA-F-]{36})"', html)
        if not um:
            um = re.search(r'lumierecore\.com/([0-9a-fA-F-]{36})', html)
        if um:
            uuid = um.group(1)
        if uuid:
            # ★ 播放地址必须以视频扩展名(.m3u8)结尾: 多数壳端按扩展名判定视频格式,
            #   裸 https://lumierecore.com/{uuid} 会被判非法地址 → "视频加载失败"
            # ★ 纯直连单线路(已剔除本地代理): master 经 POST 取流后直发,
            #   分片 .jpeg 伪装 TS 由壳端按 m3u8 正常拉取, CDN 动态桶由 _proxy_master 换稳桶兜底
            ustr = "https://lumierecore.com/" + uuid + "/index.m3u8"
            play_from = "直连"
            play_url = ustr
        return {"list": [{"vod_id": vid, "vod_name": title, "vod_pic": pic,
                           "vod_content": desc, "vod_play_from": play_from,
                           "vod_play_url": play_url}]}

    def searchContent(self, key, quick=False, pg="1"):
        if not self.search_tpl:
            return {"list": []}
        try:
            from urllib.parse import quote
            url = self.search_tpl.replace("{key}", quote(str(key)))
            if "{pg}" in url:
                url = url.replace("{pg}", str(pg))
        except Exception:
            return {"list": []}
        html = self._get(url)
        if not html:
            return {"list": []}
        return {"list": self._items(html), "page": 1, "pagecount": 1, "limit": 24, "total": 0}

    def _proxy_master(self, uuid):
        """★ 本站取流: POST px.lumierecore.com/api/proxy/{uuid} → masterUrl (无鉴权)
        该 API 仅支持 POST(GET 405), 失败重试一次(CND 抖动用), 仍失败返回空"""
        u = str(uuid or "").strip()
        if not u:
            return ""
        api = "https://px.lumierecore.com/api/proxy/" + u
        # ★ 动态桶不稳(同一 uuid 可能返回不同 CDN 桶/代理槽, 部分桶慢/超时):
        #   多轮重试换桶, 并对返回 master 做可达性探测, 宁取可拉取的稳桶
        for attempt in range(4):
            try:
                txt = self._post_json(api, timeout=8)
                if not txt:
                    continue
                d = json.loads(txt)
                if not isinstance(d, dict):
                    continue
                mu = d.get("masterUrl") or d.get("url") or d.get("playUrl") or ""
                mu = str(mu).strip()
                if mu:
                    # ★ 必须实测可达才交付: 动态桶不稳+部分桶慢/超时, 播放器拿到死桶必失败;
                    #   可达性探测用 HEAD/首字节流, 落后换下一轮重新取流(换桶)
                    if self._reachable(mu):
                        return mu
            except Exception:
                continue
        return ""

    def _reachable(self, u, timeout=8):
        """快速可达性探测(master 首字节 200 即视为桶可用); 仅用 urllib(requests 挂死隐患)"""
        if not u or not u.startswith("http"):
            return False
        h = dict(self.header)
        try:
            import urllib.request
            req = urllib.request.Request(u, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status < 400
        except Exception:
            return False

    def playerContent(self, flag, ids, vipFlags=None):
        url = ids
        if isinstance(ids, (list, tuple)):
            url = ids[0] if ids else ""
        url = str(url or "").strip()
        if not url:
            return {"parse": 0, "url": "", "header": dict(self.header)}
        if not url.startswith("http"):
            url = self._u(url)
        u = url.lower()
        # ---- 本站优先: lumierecore.com/{uuid} → POST proxy 取 master ----
        #   (地址已伪装成 .../uuid/index.m3u8 供壳端扩展名判定, 必须在本分支取流, 不能走 m3u8 直连短路)
        um = re.search(r'lumierecore\.com/([0-9a-fA-F-]{36})', url)
        if um:
            master = self._proxy_master(um.group(1))
            if not master:
                return {"parse": 0, "url": "", "header": dict(self.header)}
            # ★ 纯直连: master 直发(带 Referer/UA 防 CDN 校验失败); 本地代理线路已剔除
            return {"parse": 0, "url": master, "header": dict(self.header)}
        if u.endswith((".m3u8", ".mp4", ".flv", ".mkv", ".ts", ".avi")) or "m3u8" in u:
            return {"parse": 0, "url": url, "header": dict(self.header)}
        html = self._get(url, referer=self.site)
        if not html:
            return {"parse": 0, "url": "", "header": dict(self.header)}
        found = ""
        if self.m3u8_var and self.m3u8_var != "regex":
            m = re.search(r'var\s+%s\s*=\s*["\']([^"\']+)' % re.escape(self.m3u8_var), html)
            if m:
                found = m.group(1)
        if not found:
            m = re.search(r'var\s+now\s*=\s*["\']([^"\']+)', html) or \
                re.search(r'<source[^>]+src=["\']([^"\']+)', html) or \
                re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', html)
            if m:
                found = m.group(1)
        if not found:
            return {"parse": 0, "url": "", "header": dict(self.header)}
        found = found.strip()
        if found.startswith("//"):
            found = "https:" + found
        elif not found.startswith("http"):
            found = self._u(found)
        return {"parse": 0, "url": found, "header": dict(self.header)}

    def localProxy(self, param):
        # ★ 四壳协议(dict 形态): {'code','content'(bytes),'headers'} blrtv v3 验证:
        #   str/list content 会装载失败黑屏, content 必须 bytes
        # ★ 传参兼容(blrtv 已验证形态 + 扩展): 壳端可能传
        #   ① "url=xxx" / "res=xxx" query 串  ② proxy://do=parse&res=xxx
        #   ③ 完整本地代理 URL http://127.0.0.1:{port}/proxy?url=xxx
        #   ④ dict{"url": ...} 且值可能为以上任意形态  ⑤ 裸 CDN URL
        p = param
        if isinstance(p, str):
            t = p.strip()
            if t[:1] in ("{", "["):            # ★ JSON 字符串传参 → dict
                try:
                    import json as _json
                    p = _json.loads(t)
                except Exception:
                    pass
        if isinstance(p, dict):
            s = str(p.get("url") or p.get("res") or p.get("u") or p.get("fd") or p.get("parse") or "").strip()
        elif isinstance(p, (bytes, bytearray)):
            s = bytes(p).decode("utf-8", "ignore").strip()
        else:
            s = str(p or "").strip()
        if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):   # 剥成对引号
            s = s[1:-1]
        # 统一解析: 先剥外层代理参数(不做形态假设), 再 unquote
        if "://do=parse&res=" in s:            # proxy://do=parse&res=xxx | http://127.0.0.1:port/proxy?url=xxx 兼容
            s = s.split("://do=parse&res=", 1)[-1]
        elif "/proxy?" in s and "url=" in s:   # 完整本地代理 URL /proxy?url=xxx
            s = s.split("url=", 1)[-1]
        elif "res=" in s:                      # res=xxx
            s = s.split("res=", 1)[-1]
        elif "url=" in s:                      # url=xxx
            s = s.split("url=", 1)[-1]
        if "&" in s:
            s = s.split("&", 1)[0]
        s = unquote(unquote(s)) if "%" in s else s
        if not s.startswith(("http", "//")):
            return {"code": 403, "content": b"", "headers": {}}
        if s.startswith("//"):
            s = "https:" + s
        try:
            if ".m3u8" in s.lower():
                return self._rewrite_m3u8(s)
            return self._fetch_bytes(s)
        except Exception:
            return {"code": 403, "content": b"", "headers": {}}

    def _fetch_bytes(self, u):
        # ★ 铁律: 仅用 urllib 抓取(requests 在本机/壳端对 CDN 连接会挂死不触发超时
        #   → 本地代理全坏; urllib 超时可靠且已验证可正常拉取 master/子流/分片)
        h = dict(self.header)
        try:
            import urllib.request
            req = urllib.request.Request(u, headers=h)
            with urllib.request.urlopen(req, timeout=15) as resp:
                ct = resp.headers.get("Content-Type") or "application/octet-stream"
                if any(x in u.lower() for x in (".ts", ".jpeg", ".jpg", ".m4s")):
                    ct = "video/mp2t"
                return {"code": 200, "content": resp.read(), "headers": {"Content-Type": ct}}
        except Exception:
            return {"code": 403, "content": b"", "headers": {}}

    def _rewrite_m3u8(self, u):
        """★ 播放链本地重写: master(#EXT-X-STREAM-INF 子流) 与 子流(#EXTINF 分片) 全转
        proxy 相对代拉, 强制正确 Content-Type, 规避 CDN 动态桶直连与 .jpeg 伪装误判
        ★ 铁律: 仅用 urllib 抓取(requests 挂死不触发超时 → 代理全坏, 已弃用)"""
        h = dict(self.header)
        body = ""
        try:
            import urllib.request
            req = urllib.request.Request(u, headers=h)
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read().decode("utf-8", "ignore")
        except Exception:
            return {"code": 403, "content": b"", "headers": {}}
        origin = re.match(r"https?://[^/]+", u)
        origin = origin.group(0) if origin else ""
        base = u.rsplit("/", 1)[0] + "/"
        out = []
        lines = body.splitlines()
        i = 0
        n = len(lines)
        while i < n:
            ln = lines[i].strip()
            if not ln:
                i += 1
                continue
            if ln.startswith("#EXT-X-STREAM-INF"):     # master: 下一行 = 子流地址
                out.append(ln)
                nxt = lines[i + 1].strip() if i + 1 < n else ""
                if nxt:
                    if nxt.startswith("//"):
                        nxt = "https:" + nxt
                    elif nxt.startswith("/"):
                        nxt = origin + nxt
                    elif not nxt.startswith("http"):
                        nxt = base + nxt
                    out.append("proxy?url=" + quote(nxt, safe=""))
                    i += 2
                    continue
            elif ln.startswith("#EXTINF"):             # 子流: 下一行 = 分片地址
                out.append(ln)
                nxt = lines[i + 1].strip() if i + 1 < n else ""
                if nxt and not nxt.startswith("#"):
                    if nxt.startswith("//"):
                        nxt = "https:" + nxt
                    elif nxt.startswith("/"):
                        nxt = origin + nxt
                    elif not nxt.startswith("http"):
                        nxt = base + nxt
                    out.append("proxy?url=" + quote(nxt, safe=""))
                    i += 2
                    continue
            out.append(ln)
            i += 1
        # ★ 铁律: content 必须 bytes(四壳通吃 str 会装载失败黑屏)
        return {"code": 200, "content": "\n".join(out).encode("utf-8"),
                "headers": {"Content-Type": "application/vnd.apple.mpegurl"}}


from urllib.parse import quote, unquote


def _html_unescape(s):
    import html as _h
    return _h.unescape(s) if s else s


# ============ ★ 成人站全量脱敏档 v2 (依记忆库 task-general-requirements 契约) ============
_BLOCK_KW = [
    # —— 未成年 / 幼态 ——
    '幼女', '幼齿', '萝莉', '未成年', '小学生', '中学生', '儿童', '小孩子', '女童', '男童',
    '正太', '少男', '童装', '稚嫩', '学生妹', '幼态', '童颜', '萝莉控', '幼幼', '幼交',
    # —— 非自愿 / 迷药 / 偷拍 ——
    '强奸', '轮奸', '迷奸', '下药', '迷药', '迷晕', '昏迷', '捡尸', '偷拍', '偷窥',
    '针孔', '试衣间', '更衣室', '厕所偷', '迷魂', '催情', '春药', '听话水', '乖乖水',
    '非自愿', '强上', '强暴', '霸王硬上弓',
    # —— 乱伦 / 近亲 ——
    '乱伦', '母子', '父女', '兄妹', '姐弟', '近亲',
    # —— 兽交 ——
    '兽交', '人兽', '动物交', '兽奸',
    # —— 违法事件 ——
    '门事件', '艳照门', '艳照',
    # —— 器官 / 行为 / 口味 / 道具 / 发行(直白词) ——
    '鸡巴', '肉棒', '阳具', '大屌', '龟头', '小穴', '骚穴', '肉缝', '后穴',
    '淫水', '爱液', '精液', '白浊', '奶子', '巨乳', '爆乳', '阴蒂',
    '口交', '肛交', '深喉', '口活', '口爆', '内射', '颜射', '射精',
    '潮吹', '打飞机', '自慰', '抽插', '乳交', '足交', '群交', '轮交',
    '发骚', '发浪', '浪叫', '娇喘',
    '跳蛋', '按摩棒', '假阳具', '肛塞', '情趣用品', '无码', '里番',
]
_BLOCK_VAR = [
    '骨科', '近亲相奸', '母子乱', '父女乱', '兄妹乱', '姐弟乱',
    '视奸', '迷魂水', '苍蝇水', '厕所偷窥', '走光偷拍',
    '牛头人', '绿帽', '群p', '多p', '双飞',
    '几把', '牛子', '品玉', '舔穴', '观音坐莲', '毒龙钻',
    '制服诱惑', '原味内裤', '开档', '成人片', '成人影片', '成人视频', 'av女优',
]
_BLOCK_ZW = '\u200b\u200c\u200d\ufeff\u2060\u00ad'
_BLOCK_SEP = '\u00b7\u2022.*-_=~|/\\+ \t\r\n\u3000\u3001\u3002'
_BLOCK_EMOJI = '\U0001F346\U0001F34C\U0001F952\U0001F414\U0001F351\U0001F4A6\U0001F445\U0001F336'
_BLOCK_ZW_RE = re.compile('[' + _BLOCK_ZW + ']')
_BLOCK_SEP_RE = re.compile('[' + re.escape(_BLOCK_SEP) + ']')
_BLOCK_ASCII_RE = re.compile(r'(?<![a-z0-9])(?:j8|jb|3p|4p|5p|ntr|lolita|loli)(?![a-z0-9])')


def _norm(text):
    import unicodedata as _u
    t = _u.normalize('NFKC', str(text))
    return _BLOCK_ZW_RE.sub('', t).lower()


def _blocked(text):
    """脱敏词命中判定(成人站全量档): 命中返回 True(丢弃); 抗 全角/零宽/间隔符/黑话/emoji 规避"""
    if not text:
        return False
    raw = str(text)
    if _BLOCK_ZW_RE.search(raw):
        return True
    t = _norm(raw)
    sq = _BLOCK_SEP_RE.sub('', t)
    for k in _BLOCK_KW:
        if k in t or k in sq:
            return True
    for k in _BLOCK_VAR:
        if k in t or k in sq:
            return True
    if _BLOCK_ASCII_RE.search(t):
        return True
    for e in _BLOCK_EMOJI:
        if e in raw:
            return True
    return False


def _clean_play_name(name):
    """清洗播放源名称中的四壳分隔符($=地址 / #=选集), 防标题含半角 $/# 被壳端拆段"""
    if not name:
        return name
    return str(name).replace('$', '\uff04').replace('#', '\uff03')