#!/usr/bin/python
import json
import os
import re
import socket
import time
from urllib.parse import urlparse, urljoin, quote, urlunparse

import requests

from base.spider import Spider


class Spider(Spider):
    FAIL_LIMIT = 3
    COOLDOWN = 300

    def _init_heal(self, extend=None):
        seeds = []
        if isinstance(extend, dict):
            for k in ("host", "api", "domain", "url"):
                v = str(extend.get(k) or "").strip().rstrip("/")
                if v.startswith("http"):
                    seeds.append(v)
        envv = str(os.environ.get(self.ENV_KEY or "___NONE___") or "").strip().rstrip("/")
        if envv.startswith("http"):
            seeds.append(envv)
        pool = []
        for u in seeds + list(self.POOL):
            if u and u not in pool:
                pool.append(u)
        self.pool = pool
        self.dead = {}
        self.fails = {}
        self.host = self.host if getattr(self, "host", "") and self.host in pool else (pool[0] if pool else "")
        if not hasattr(self, "_booting"):
            self._booting = False

    def _site_ok(self, txt):
        if not txt:
            return False
        low = txt[:4000].lower()
        return not any(x in low for x in ("just a moment", "attention required",
                                          "enable javascript and cookies",
                                          "<title>301", "<title>403", "<title>404"))

    def _mirror_re(self):
        return None

    def _harvest(self, txt):
        rx = self._mirror_re()
        if not rx or not txt:
            return
        try:
            for m in rx.findall(txt)[:20]:
                o = self._origin(m if str(m).startswith("http") else "https://" + str(m))
                if o and o not in self.pool and len(self.pool) < 12:
                    self.pool.append(o)
        except Exception:
            pass

    @staticmethod
    def _origin(url):
        try:
            p = urlparse(str(url))
            return urlunparse((p.scheme or "https", (p.netloc or "").lower(), "", "", "", ""))
        except Exception:
            return ""

    def _cooling(self, origin):
        return self.dead.get(origin, 0) > time.time()

    def _mark(self, origin, ok):
        if ok:
            self.fails[origin] = 0
            self.dead.pop(origin, None)
            return
        n = self.fails.get(origin, 0) + 1
        self.fails[origin] = n
        if n >= self.FAIL_LIMIT:
            self.dead[origin] = time.time() + self.COOLDOWN
            if hasattr(self, "log"):
                try:
                    self.log("%s 熔断 %ds" % (origin, self.COOLDOWN))
                except Exception:
                    pass

    def _rewrite(self, url, origin):
        try:
            p = urlparse(str(url))
            if not p.netloc:
                return origin + str(url)
            q = urlparse(origin)
            return urlunparse((q.scheme, q.netloc, p.path, "", p.query, ""))
        except Exception:
            return url

    def _ensure_host(self, force=False):
        if getattr(self, "_booting", False):
            return bool(getattr(self, "host", ""))
        if not getattr(self, "pool", None):
            self._init_heal(None)
        self._booting = True
        try:
            if self.host and not force and not self._cooling(self.host):
                return True
            if force and self.host:
                self.dead[self.host] = time.time() + self.COOLDOWN
            self.host = ""
            for cand in list(self.pool):
                if self._cooling(cand):
                    continue
                got = self._probe_origin(cand)
                if got:
                    self.host = got
                    try:
                        self.headers["Referer"] = got + "/"
                    except Exception:
                        pass
                    if got not in self.pool:
                        self.pool.insert(0, got)
                    self._mark(got, True)
                    return True
            return False
        finally:
            self._booting = False

    def _probe_origin(self, base):
        url = base.rstrip("/") + getattr(self, "PROBE_PATH", "/")
        for _ in range(3):
            txt = self._once(url, tries=1, referer=base + "/")
            if not txt:
                return ""
            self._harvest(txt)
            if self._site_ok(txt):
                fin = self._origin(getattr(self, "_final_origin", "") or url)
                if fin and fin != self._origin(base) and fin not in self.pool and len(self.pool) < 12:
                    self.pool.insert(0, fin)
                return self._origin(base) or base
            nxt = self._jump(txt)
            if not nxt or not nxt.startswith("http") or self._origin(nxt) == self._origin(url):
                return ""
            url = nxt
        return ""

    @staticmethod
    def _jump(txt):
        if not txt or len(txt) > 6000:
            return ""
        m = re.search(r'location\.replace\(\s*["\']([^"\']+)', txt) or \
            re.search(r'\bhref="(https?://[^"]+)"', txt)
        return m.group(1) if m else ""

    def _throttle(self, gap=0.5):
        delta = time.time() - getattr(self, "_last", 0)
        if delta < gap:
            time.sleep(gap - delta)
        self._last = time.time()

    def _once(self, url, tries=2, referer=None, as_json=False, timeout=22):
        hdr = dict(self.headers)
        if referer:
            hdr["Referer"] = referer if referer.startswith("http") else \
                (getattr(self, "host", "") or "") + "/" + referer.lstrip("/")
        last = None
        for i in range(max(1, tries)):
            self._throttle(0.5 + 0.4 * i)
            try:
                r = self.session.get(url, headers=hdr, timeout=timeout, verify=False,
                                     proxies=self._proxies(), allow_redirects=True)
                if as_json:
                    if r.status_code == 200:
                        try:
                            d = r.json()
                            self._final_origin = self._origin(getattr(r, "url", "") or url)
                            return d
                        except Exception as e:
                            last = "非 JSON"
                    elif r.status_code in (403, 404, 410):
                        return ""
                    elif r.status_code in (429, 500, 502, 503, 504):
                        last = "HTTP %s" % r.status_code
                else:
                    if r.status_code == 200:
                        if not r.encoding or r.encoding.upper() == "ISO-8859-1":
                            r.encoding = r.apparent_encoding or "utf-8"
                        if r.text and len(r.text) > 200:
                            self._final_origin = self._origin(getattr(r, "url", "") or url)
                            return r.text
                        last = "响应过短"
                    elif r.status_code in (403, 404, 410):
                        return ""
                    else:
                        last = "HTTP %s" % r.status_code
            except Exception as e:
                last = e
            time.sleep(1.0 * (i + 1))
        self._note_fail(url, last)
        return ""

    def _note_fail(self, url, last=None):
        o = self._origin(url)
        if o:
            hard = isinstance(last, Exception) or any(
                k in str(last or "") for k in
                ("Connection", "SSL", "Timed out", "timeout", "reset by peer", "Name or service"))
            for _ in range(self.FAIL_LIMIT if hard else 1):
                self._mark(o, False)
        if hasattr(self, "log"):
            try:
                self.log("%s 请求失败 %s %s" % (getattr(self, "name", "?"), url, last))
            except Exception:
                pass

    def _heal_get(self, url, referer=None, as_json=False, tries=2):
        if not getattr(self, "pool", None):
            self._init_heal(None)
        if not self.host and not self._ensure_host():
            return ({} if as_json else "")
        tried = []
        order = [self.host] + [o for o in self.pool if o != self.host]
        for origin in order:
            if origin in tried or self._cooling(origin):
                continue
            tried.append(origin)
            target = self._rewrite(url, origin) if urlparse(str(url)).netloc else origin + "/" + str(url).lstrip("/")
            ref = (referer if (referer or "").startswith("http")
                   else origin + "/" + str(referer or "/").lstrip("/"))
            out = self._once(target, tries=tries, referer=ref, as_json=as_json)
            if out:
                if as_json and not isinstance(out, (dict, list)):
                    self._mark(origin, False)
                    continue
                if not self._site_ok(out):
                    self._mark(origin, False)
                    continue
                if origin != self.host:
                    self.host = origin
                    try:
                        self.headers["Referer"] = origin + "/"
                    except Exception:
                        pass
                self._mark(origin, True)
                if not as_json:
                    self._harvest(out)
                return out
        return ({} if as_json else "")

    def _heal_play(self, url):
        if not self._is_media(url):
            return ""
        got = self._probe_media(url)
        if got:
            return got
        for strip in (True, False):
            try:
                p = urlparse(url)
                keep = "" if strip else "&".join(
                    kv for kv in (p.query or "").split("&")
                    if kv.split("=")[0].lower() not in ("auth_key", "md5", "expires", "sign", "token", "t"))
                alt = urlunparse((p.scheme, p.netloc, p.path, "", keep, ""))
            except Exception:
                continue
            if alt and alt != url:
                got = self._probe_media(alt)
                if got:
                    return got
            if strip:
                break
        return ""

    POOL = ["https://bad.news", "https://www.bad.news", "https://lvv2.com"]
    ENV_KEY = "BADNEWS_HOST"
    PROBE_PATH = "/dm"

    def _site_ok(self, txt):
        if not txt or "Just a moment" in txt[:3000] or "Attention Required" in txt[:3000]:
            return False
        return bool(any(x in txt for x in ("/dm/play/id-", "data-tid=", "post-card", "/tag/porn")))

    def getName(self):
        return "BadNews"

    def init(self, extend=""):
        _ext = extend if isinstance(extend, dict) else {}
        self._init_heal(_ext)
        self.name = "BadNews"
        self.host = "https://bad.news"
        self.headers = {
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": self.host + "/",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self._proxy = None
        self._codes = {}
        self._names = {}
        self._ext_proxy = self._pick_proxy_from(extend)

        self.categories = [
            {"type_id": "dm", "type_name": "H动漫库"},
            {"type_id": "tag:porn", "type_name": "短视频"},
            {"type_id": "tag:long-porn", "type_name": "长视频"},
            {"type_id": "sort:new", "type_name": "最新"},
            {"type_id": "sort:hot", "type_name": "热门"},
            {"type_id": "sort:better", "type_name": "精选"},
            {"type_id": "sort:score", "type_name": "高分"},
        ]
        self.filter_map = {
            "dm": [{
                "key": "槽",
                "name": "分类",
                "value": [
                    {"n": "全部动漫", "v": "dm"},
                    {"n": "3D动画", "v": "dmtype:3D"},
                    {"n": "同人作品", "v": "dmtype:同人"},
                    {"n": "Cosplay", "v": "dmtype:Cosplay"},
                ],
            }, {
                "key": "标签",
                "name": "标签",
                "value": [{"n": t, "v": "dmtag:" + t} for t in [
                    "无码", "JK", "巨乳", "颜射", "口交", "内射", "肛交", "强制",
                    "调教", "女僕", "乳交", "群交", "百合", "近亲", "后宫",
                    "BDSM", "3D", "1080p", "同人", "Cosplay",
                ]],
            }]
        }

    @staticmethod
    def _pick_proxy_from(extend):
        if isinstance(extend, str) and extend.strip().startswith("{"):
            try:
                extend = json.loads(extend)
            except Exception:
                extend = {}
        if not isinstance(extend, dict):
            return None
        p = extend.get("proxy") or extend.get("proxyUrl") or ""
        return str(p).strip() or None

    def _proxies(self):
        if self._proxy is not None:
            return self._proxy
        if getattr(self, "_probed", False):
            return None
        cand = self._ext_proxy or os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY") \
            or os.environ.get("https_proxy") or ""
        if not cand:
            for port in (7890, 7891, 1080, 1087, 10809, 20171, 20172, 24780):
                try:
                    s = socket.create_connection(("127.0.0.1", port), timeout=0.35)
                    s.close()
                    cand = "http://127.0.0.1:%d" % port
                    break
                except Exception:
                    continue
        self._probed = True
        self._proxy = {"http": cand, "https": cand} if cand else {}
        return self._proxy or None

    def _get(self, url, referer=None, tries=2):
        return self._heal_get(url, referer=referer, tries=tries)

    def _post(self, url, data):
        try:
            r = self.session.post(url, data=data, headers=self.headers, timeout=20,
                                  verify=False, proxies=self._proxies())
            return r.json() if r.ok else {}
        except Exception:
            return {}

    def _fix(self, url):
        if not url:
            return ""
        url = url.strip()
        if url.startswith("//"):
            return "https:" + url
        return url if url.startswith("http") else urljoin(self.host + "/", url)

    @staticmethod
    def _clean(txt):
        txt = " ".join((txt or "").split())
        return re.sub(r"[#$]", " ", txt).strip()

    @staticmethod
    def _is_media(url):
        return (urlparse(url or "").scheme in ("http", "https")
                and bool(re.search(r"\.(?:m3u8|mp4|flv|mkv|ts)(?:$|[?#])",
                                   urlparse(url).path, re.I)))

    def _probe_media(self, url):
        if not self._is_media(url):
            return ""
        try:
            r = self.session.get(url, headers={**self.headers, "Range": "bytes=0-4095"},
                                 timeout=15, verify=False, stream=True,
                                 proxies=self._proxies())
            data = next(r.iter_content(4096), b"")
            ctype = (r.headers.get("Content-Type") or "").lower()
            if not r.ok:
                return ""
            if re.search(r"\.m3u8(?:$|[?#])", urlparse(r.url).path, re.I):
                return r.url if b"#EXTM3U" in data else ""
            return r.url if ("video/" in ctype or data[4:12].find(b"ftyp") >= 0) else ""
        except Exception:
            return ""

    def _media_alive(self, url):
        try:
            r = self.session.get(url, headers={**self.headers, "Range": "bytes=0-2047"},
                                 timeout=12, verify=False, stream=True,
                                 proxies=self._proxies())
            code = r.status_code
            try:
                r.close()
            except Exception:
                pass
            if code in (404, 410, 451):
                return False
            if code in (401, 403):
                return None
            return None if code >= 500 else True
        except Exception:
            return None

    def _last_page(self, html, path):
        nums = [int(x) for x in re.findall(
            r'href="%s/page-(\d{1,6})"' % re.escape(path), html or "")]
        return max(nums) if nums else 0

    def _vod(self, vid, name, pic, remark=""):
        pic = self._fix(pic)
        if pic.startswith("http://") and "img.lvv2.com" in pic:
            pic = pic.replace("http://", "https://")
        return {
            "vod_id": vid,
            "vod_name": self._clean(name) or "未命名",
            "vod_pic": pic,
            "vod_remarks": remark or "",
            "vod_tag": "class",
            "vod_play_from": "",
            "vod_play_url": "",
        }

    def _parse_posts(self, html, base_path, pg):
        out, seen = [], set()
        if not html:
            return out
        blocks = re.split(r'<div\s+class="link\s+show[^"]*"', html)[1:]
        for blk in blocks:
            try:
                m = re.search(r'data-tid="(\d+)"', blk)
                if not m:
                    continue
                tid = m.group(1)
                src, poster = "", ""
                for vt in re.findall(r"<video\b[^>]*>", blk):
                    ds = re.search(r'data-source="([^"]+)"', vt)
                    if not ds:
                        continue
                    did = re.search(r'data-id="(\d+)"', vt)
                    pm = re.search(r'poster="([^"]+)"', vt)
                    if not src:
                        src, poster = ds.group(1), (pm.group(1) if pm else "")
                    if did and did.group(1) == tid:
                        src, poster = ds.group(1), (pm.group(1) if pm else "")
                        break
                if not src:
                    continue
                title = ""
                mt = re.search(r'<a\s+class="title"[^>]*>([\s\S]{1,300}?)</a>', blk)
                if mt:
                    title = self._clean(re.sub(r"<[^>]+>", " ", mt.group(1)))
                if not title or re.search(r"(?i)^(watch\s*video|看视频|视频)$", title):
                    au = re.search(r'class="author"[^>]*>([\s\S]{1,80}?)</a>', blk)
                    au = self._clean(re.sub(r"<[^>]+>", "", au.group(1))) if au else "匿名"
                    tm = re.search(r'<time[^>]*title="([\d\-: ]+)"', blk)
                    title = "%s %s" % (au, (tm.group(1)[:10] if tm else tid))
                pic = poster
                if not pic:
                    mp = re.search(r'data-echo="(https?://[^"]+)"', blk)
                    pic = mp.group(1) if mp else ""
                dur = ""
                md = re.search(r'<div class="ct-time">\s*<span>\s*([0-9:]{4,9})', blk)
                if md:
                    dur = md.group(1)
                dom = re.search(r'/domain/([\w.\-]+)', blk)
                v = self._vod("t:" + tid, title, pic, " ".join(x for x in [dur, dom.group(1) if dom else ""] if x))
                if v["vod_id"] not in seen:
                    seen.add(v["vod_id"])
                    self._codes[v["vod_id"]] = self._fix(src)
                    self._names[v["vod_id"]] = v["vod_name"]
                    out.append(v)
            except Exception:
                continue
        return out

    def _parse_dm(self, html):
        out, seen = [], set()
        for blk in re.findall(r'<article\b[\s\S]*?</article>', html or ""):
            try:
                mid = re.search(r'/dm/play/id-(\d+)', blk)
                if not mid:
                    continue
                pid = mid.group(1)
                if pid in seen:
                    continue
                seen.add(pid)
                name = ""
                mn = re.search(r'<a\s+class="title"[^>]*title="([^"]{1,200})"', blk)
                if mn:
                    name = mn.group(1)
                else:
                    ma = re.search(r'<img[^>]*\balt="([^"]{1,200})"', blk)
                    name = ma.group(1) if ma else "动漫 " + pid
                mp = re.search(r'data-echo="(https?://[^"]+)"', blk)
                out.append(self._vod("dm:" + pid, name, mp.group(1) if mp else "", "H动漫"))
            except Exception:
                continue
        return out

    ALT = {"dm": ["/dm/", "/dm/type/q-3D/", "/dm/tag/\u65e0\u7801/"],
           "post": ["/sort-hot/", "/tag/porn/", "/tag/long-porn/"]}

    def _route(self, tid, extend):
        if isinstance(extend, str) and extend.strip().startswith("{"):
            try:
                extend = json.loads(extend)
            except Exception:
                extend = {}
        if not isinstance(extend, dict):
            extend = {}
        for key in ("槽", "标签", "type", "tag"):
            val = extend.get(key)
            if isinstance(val, str) and val.strip():
                tid = val.strip()
                break
        tid = str(tid or "dm").strip()
        if tid.startswith("dmtype:"):
            return "/dm/type/q-" + quote(tid.split(":", 1)[1], safe="")
        if tid.startswith("dmtag:"):
            return "/dm/tag/" + quote(tid.split(":", 1)[1], safe="")
        if tid == "dm":
            return "/dm"
        if tid.startswith("tag:"):
            return "/tag/" + quote(tid.split(":", 1)[1], safe="")
        if tid.startswith("sort:"):
            return "/sort-" + quote(tid.split(":", 1)[1], safe="")
        if tid.startswith("t:"):
            return "/t/" + tid.split(":", 1)[1]
        return "/sort-hot"

    @staticmethod
    def _paged(path, pg):
        return path if pg <= 1 else path.rstrip("/") + "/page-%d" % pg

    def homeContent(self, filter=False):
        res = {"class": self.categories, "list": [], "filters": self.filter_map}
        try:
            if filter:
                return res
        except Exception:
            pass
        res["list"] = self._parse_posts(self._get(self.host + "/sort-hot"), "/sort-hot", 1)[:20]
        return res

    def homeVideoContent(self):
        return {"list": self._parse_posts(self._get(self.host + "/sort-hot"), "/sort-hot", 1)[:24]}

    def categoryContent(self, tid, pg, filter=None, extend=None):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        pg = max(1, pg)
        path = self._route(tid, extend)
        html = self._get(self._fix(self._paged(path, pg)))
        is_dm = (tid in ("dm",) or str(tid).startswith(("dmtype", "dmtag")) or bool(
            isinstance(extend, dict) and any(str(v).startswith("dm") for v in
                                             [extend.get("槽"), extend.get("标签")] if v)))
        items = self._parse_dm(html) if is_dm else self._parse_posts(html, path, pg)
        if not items and pg == 1:
            for alt in self.ALT.get("dm" if is_dm else "post", []):
                h2 = self._get(self._fix(alt))
                it2 = self._parse_dm(h2) if is_dm else self._parse_posts(h2, alt, 1)
                if it2:
                    html, items, path = h2, it2, alt
                    break
        last = self._last_page(html, path.rstrip("/"))
        pagecount = max(last, pg if items else pg - 1, 1)
        return {
            "list": items,
            "page": pg,
            "pagecount": pagecount,
            "limit": len(items) or 20,
            "total": pagecount * (len(items) or 20),
        }

    def detailContent(self, ids):
        if isinstance(ids, (list, tuple)):
            ids = [str(i).strip() for i in ids if str(i).strip()]
        else:
            ids = [i.strip() for i in str(ids or "").split(",") if i.strip()]
        res = {"list": []}
        for vid in ids:
            try:
                if vid.startswith("dm:"):
                    item = self._detail_dm(vid[3:])
                elif vid.startswith("t:"):
                    item = self._detail_post(vid[2:])
                elif vid.startswith("/dm/play/"):
                    item = self._detail_dm(re.sub(r"\D", "", vid) or "")
                else:
                    item = self._detail_post(re.sub(r"\D", "", vid) or "")
                if item:
                    res["list"].append(item)
            except Exception:
                continue
        return res

    def _detail_dm(self, pid):
        if not pid:
            return None
        url = self.host + "/dm/play/id-" + pid
        html = self._get(url)
        if not html:
            return None
        name = ""
        mn = re.search(r'<h1\s+class="title"[^>]*>([\s\S]{1,300}?)</h1>', html)
        if mn:
            name = self._clean(re.sub(r"<[^>]+>", " ", mn.group(1)))
        if not name:
            mt = re.search(r"<title>([^<]{2,120})</title>", html)
            name = self._clean(mt.group(1)).replace(" - bad.news 动漫影院", "") if mt else "动漫 " + pid
        pic = ""
        for pat in (r'property="og:image"\s+content="([^"]+)"',
                    r'name="twitter:image"\s+content="([^"]+)"',
                    r'data-echo="(https?://[^"]+)"'):
            mp = re.search(pat, html)
            if mp:
                pic = mp.group(1)
                break
        desc = ""
        md = re.search(r'<p class="desc[^"]*"[^>]*>([\s\S]{1,1500}?)</p>', html)
        if md:
            desc = self._clean(re.sub(r"<[^>]+>", " ", md.group(1)))[:600]
        tags = re.findall(r'/dm/tag/([^"\'<>]{1,40})"', html)
        area = "H动漫"
        return {
            "vod_id": "dm:" + pid,
            "vod_name": name or ("动漫 " + pid),
            "vod_pic": self._fix(pic),
            "vod_content": desc or "本站数据来自互联网，请勿相信播放过程中的任何广告。",
            "vod_class": " ".join(tags[:8]),
            "vod_type": area,
            "vod_area": area,
            "vod_year": "",
            "vod_actor": "",
            "vod_director": "",
            "vod_remarks": "H动漫",
            "vod_play_from": "BadNews动漫",
            "vod_play_url": "正片$dm:" + pid,
        }

    def _detail_post(self, tid):
        if not tid:
            return None
        url = self.host + "/t/" + tid
        html = self._get(url)
        if not html:
            return None
        main, extra = "", []
        for vt in re.findall(r"<video\b[^>]*>", html):
            ds = re.search(r'data-source="([^"]+)"', vt)
            if not ds:
                continue
            u = self._fix(ds.group(1))
            did = re.search(r'data-id="(\d+)"', vt)
            if did and did.group(1) == tid and not main:
                main = u
            elif u not in extra:
                extra.append(u)
        if not main:
            cand = [self._fix(x) for x in re.findall(r'data-source="([^"]+)"', html)]
            cand = [x for x in cand if self._is_media(x)]
            main = cand[0] if cand else ""
        if not main:
            return None
        urls, seen = [], set()
        urls.append("本片$" + main)
        seen.add(main)
        for i, u in enumerate(extra[:9], 1):
            if u not in seen:
                urls.append("片段%d$%s" % (i, u))
                seen.add(u)
        name = ""
        for pat in (r'<meta\s+property="og:title"\s+content="([^"]{2,200})"',
                    r"<title>([^<]{2,200})</title>",
                    r'<h3\s+class="title"[^>]*>([\s\S]{1,300}?)</h3>'):
            mt = re.search(pat, html)
            if mt:
                name = self._clean(re.sub(r"<[^>]+>", " ", mt.group(1)))
                if name:
                    break
        if (not name or re.search(r"(?i)^(watch\s*video|看视频|视频)$", name)
                or name.startswith("欢迎访问")):
            name = self._names.get("t:" + tid, "") or ("推文视频 " + tid)
        pic = ""
        mp = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', html) or \
            re.search(r'data-echo="(https?://[^"]+)"', html)
        if mp:
            pic = mp.group(1)
        desc = ""
        md = re.search(r'<div class="post_body|<div class="content"[^>]*>([\s\S]{1,800}?)</div>', html)
        if md:
            desc = self._clean(re.sub(r"<[^>]+>", " ", md.group(1)))[:500]
        return {
            "vod_id": "t:" + tid,
            "vod_name": name or ("推文视频 " + tid),
            "vod_pic": self._fix(pic),
            "vod_content": desc or url,
            "vod_type": "推文视频",
            "vod_area": "Twitter",
            "vod_year": "",
            "vod_actor": "",
            "vod_director": "",
            "vod_remarks": "%dP" % len(urls),
            "vod_play_from": "BadNews推文",
            "vod_play_url": "#".join(urls),
        }

    def searchContent(self, key, quick=False, pg="1"):
        try:
            pg = max(1, int(pg))
        except Exception:
            pg = 1
        wd = str(key or "").strip()
        res = {"list": [], "page": pg, "pagecount": pg, "limit": 20, "total": 0}
        if not wd:
            return res
        q = quote(wd, safe="")
        dm_path, post_path = "/dm/search/q-" + q, "/search/t-porn/q-" + q
        dm_html = self._get(self._fix(self._paged(dm_path, pg)))
        post_html = self._get(self._fix(self._paged(post_path, pg)))
        dm_items = self._parse_dm(dm_html)
        post_items = self._parse_posts(post_html, post_path, pg)
        items, seen = [], set()
        for v in dm_items + post_items:
            if v["vod_id"] not in seen:
                seen.add(v["vod_id"])
                items.append(v)
        last = max(self._last_page(dm_html, dm_path), self._last_page(post_html, post_path))
        res.update({
            "list": items,
            "pagecount": max(last, pg if items else 1, 1),
            "limit": len(items) or 20,
            "total": max(last, 1) * (len(items) or 20),
        })
        return res

    def playerContent(self, flag, id, vipFlags=None):
        raw = str(id or "").strip()
        out = {"parse": 0, "url": "", "jx": 0, "header": dict(self.headers)}
        if not raw:
            return out
        if raw.startswith("dm:"):
            html = self._get(self.host + "/dm/play/id-" + raw[3:])
            m = re.search(r"data-source=[\"']([^\"']+)[\"']", html)
            cand = self._fix(m.group(1)) if m else ""
        elif raw.startswith("t:"):
            item = self._detail_post(raw[2:])
            first = (item or {}).get("vod_play_url", "").split("#")[0]
            cand = first.split("$", 1)[1] if "$" in first else ""
        elif self._is_media(raw):
            cand = raw
        elif raw.startswith("http"):
            return {"parse": 1, "url": raw, "jx": 0, "header": dict(self.headers)}
        else:
            cand = self._codes.get(raw, "")
        url = self._heal_play(cand)
        if not url and self._is_media(cand) and self._media_alive(cand) is not False:
            url = cand
        if url:
            out["url"] = url
            out["header"] = {"User-Agent": self.headers["User-Agent"]}
            return out
        page = self.host + ("/dm/play/id-" + raw[3:] if raw.startswith("dm:")
                            else "/t/" + raw[2:] if raw.startswith("t:") else "/")
        return {"parse": 1, "url": page, "jx": 0,
                "header": {"User-Agent": self.headers["User-Agent"],
                           "Referer": self.host + "/"}}

    def localProxy(self, param=None):
        return [404, "text/plain", b"not found", {}]

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        return self._is_media(url)

    def getDependence(self):
        return []

    def doRequest(self, url, key=""):
        return self._get(self._fix(url))