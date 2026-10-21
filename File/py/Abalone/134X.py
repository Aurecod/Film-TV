# coding=utf-8
# //@name:134X
# //@version:4
try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        def getName(self): return ""
        def init(self, extend=""): pass
        def homeContent(self, filter=None): return {}
        def homeVideoContent(self): return {}
        def categoryContent(self, tid, pg, filter=None, extend=None): return {}
        def detailContent(self, ids): return {}
        def searchContent(self, key, quick=False, pg="1"): return {}
        def playerContent(self, flag, id, vipFlags=None): return {}
        def localProxy(self, param): return [404, "text/plain", ""]
        def getDependence(self): return ""
        def isVideoFormat(self, url): return False
        def manualVideoCheck(self): return False

import re, time, gzip, zlib, ssl, http.cookiejar, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote, urljoin, urlparse

SKIP_NAME_KEYS = ("萝莉", "幼女", "小学生", "儿童", "未成年", "幼幼", "初中", "小孩", "女童")


class Spider(BaseSpider):
    def getName(self):
        return "134X"

    def init(self, extend=""):
        self.host = "https://134x.com"
        self.ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        self.headers = {
            "User-Agent": self.ua,
            "Referer": self.host + "/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
        }
        self._ctx = ssl._create_unverified_context()
        self._cj = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=self._ctx),
            urllib.request.HTTPCookieProcessor(self._cj),
        )
        self._play_cache = {}
        self._poster_cache = {}
        self._cursor_cache = {}

    def getDependence(self):
        return ""

    def _req(self, path, headers=None, retry=2):
        url = path if str(path).startswith("http") else (self.host + str(path))
        hdrs = dict(self.headers)
        if headers:
            hdrs.update(headers)
        for i in range(retry):
            try:
                req = urllib.request.Request(url, headers=hdrs)
                with self._opener.open(req, timeout=15) as resp:
                    raw = resp.read()
                    enc = (resp.headers.get("Content-Encoding") or "").lower()
                    if enc == "gzip" or (len(raw) >= 2 and raw[0] == 0x1F and raw[1] == 0x8B):
                        try:
                            raw = gzip.decompress(raw)
                        except Exception:
                            pass
                    elif enc == "deflate":
                        try:
                            raw = zlib.decompress(raw)
                        except Exception:
                            try:
                                raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                            except Exception:
                                pass
                    return raw.decode("utf-8", "ignore")
            except Exception:
                time.sleep(0.2 * (i + 1))
        return ""

    def _req_bytes(self, url, headers=None):
        hdrs = {
            "User-Agent": self.ua,
            "Referer": "https://twitter.com/",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        }
        if headers:
            hdrs.update(headers)
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with self._opener.open(req, timeout=15) as resp:
                raw = resp.read()
                ctype = resp.headers.get("Content-Type") or "image/jpeg"
                return raw, ctype
        except Exception:
            return b"", ""

    def _unescape_js(self, s):
        if not s:
            return ""
        return (s.replace("\\n", "\n").replace("\\t", "\t")
                .replace('\\"', '"').replace("\\/", "/"))

    def _bad(self, name):
        return any(k in (name or "") for k in SKIP_NAME_KEYS)

    def _proxy_url(self, url, typ="img"):
        if not url:
            return ""
        try:
            if hasattr(self, "getProxyUrl") and self.getProxyUrl():
                base = self.getProxyUrl()
                return base + ("&" if "?" in base else "?") + "url=" + quote(url, safe="") + "&type=" + typ
        except Exception:
            pass
        return url

    def _make_title(self, author, screen, text, remarks):
        """优先中文剧名；纯表情/@ 则用 作者+时长。"""
        t = (text or "").replace("\n", " ")
        t = re.sub(r"https?://t\.co/\w+", "", t)
        t = re.sub(r"\s+", " ", t).strip()
        # 去掉首尾纯表情/@ 噪音后是否还有有效中文/字母数字
        cjk = re.findall(r"[\u4e00-\u9fffA-Za-z]{2,}", t)
        # 过滤掉只是用户名的
        meaningful = [x for x in cjk if x.lower() not in (
            (screen or "").lower(), "sentoyun", "sentodan", "sentofen", "sentohua",
            "woshuaibao", "wsdsbs",
        )]
        if meaningful and len(t) >= 4:
            # 有实质文本
            title = t
            # 去掉开头的表情符号块
            title = re.sub(r"^[\U0001F300-\U0001FAFF\u2600-\u27BF\s]+", "", title).strip()
            if len(title) >= 4:
                return title[:80]
        author = (author or "").strip() or (screen or "").strip() or "134X"
        if remarks:
            return "{} · {}".format(author, remarks)
        if screen:
            return "{} (@{})".format(author, screen)
        return author

    def homeContent(self, filter=None):
        return {
            "class": [
                {"type_id": "popular", "type_name": "热门"},
                {"type_id": "featured", "type_name": "精选"},
                {"type_id": "search_av", "type_name": "AV"},
                {"type_id": "search_jav", "type_name": "JAV"},
                {"type_id": "search_fc2", "type_name": "FC2"},
            ],
            "filters": {},
        }

    def homeVideoContent(self):
        return self.categoryContent("popular", "1", False, {})

    def categoryContent(self, tid, pg, filter=None, extend=None):
        try:
            page_i = int(pg) if str(pg).isdigit() else 1
            tid = str(tid or "popular").strip()
            path = self._build_path(tid, page_i)
            html = self._req(path)
            tweets = self._parse_ssr(html or "")
            videos = self._to_list(tweets)
            m = re.search(r'nextCursor:"([^"]+)"', html or "")
            if m:
                self._cursor_cache["{}:{}".format(tid, page_i)] = m.group(1)
            has_more = bool(m) or len(videos) >= 15
            pagecount = page_i + 1 if has_more else max(page_i, 1)
            return {
                "page": page_i,
                "pagecount": pagecount,
                "limit": 20,
                "total": pagecount * 20,
                "list": videos,
            }
        except Exception:
            return {"page": 1, "pagecount": 1, "limit": 0, "total": 0, "list": []}

    def _build_path(self, tid, page_i):
        if tid == "popular":
            base = "/popular"
        elif tid == "featured":
            base = "/featured"
        elif tid.startswith("search_"):
            q = tid[7:] or "av"
            base = "/search?q={}".format(quote(q))
        else:
            base = "/popular"
        if page_i <= 1:
            return base
        prev_key = "{}:{}".format(tid, page_i - 1)
        cursor = self._cursor_cache.get(prev_key, "")
        if not cursor:
            for p in range(1, page_i):
                path = base if p == 1 else self._path_with_cursor(
                    base, p, self._cursor_cache.get("{}:{}".format(tid, p - 1), "")
                )
                html = self._req(path)
                m = re.search(r'nextCursor:"([^"]+)"', html or "")
                if m:
                    self._cursor_cache["{}:{}".format(tid, p)] = m.group(1)
            cursor = self._cursor_cache.get(prev_key, "")
        return self._path_with_cursor(base, page_i, cursor)

    def _path_with_cursor(self, base, page_i, cursor):
        if not cursor:
            return base + ("&" if "?" in base else "?") + "page={}".format(page_i)
        return base + ("&" if "?" in base else "?") + "page={}&cursor={}&direction=next".format(
            page_i, quote(cursor, safe="")
        )

    def _parse_ssr(self, html):
        tweets = []
        if not html:
            return tweets
        pat = re.compile(
            r'name:"((?:\\.|[^"\\])*)",screenName:"((?:\\.|[^"\\])*)",profileImage:"((?:\\.|[^"\\])*)",'
            r'tweetId:"(\d+)",text:"((?:\\.|[^"\\])*)",media:"((?:\\.|[^"\\])*)"'
            r'[\s\S]{0,200}?durationMillis:(\d+)',
            re.S,
        )
        seen = set()
        for m in pat.finditer(html):
            tid = m.group(4)
            if tid in seen:
                continue
            seen.add(tid)
            tweets.append({
                "name": self._unescape_js(m.group(1)),
                "screenName": self._unescape_js(m.group(2)),
                "profileImage": m.group(3),
                "tweetId": tid,
                "text": self._unescape_js(m.group(5)),
                "media": m.group(6).replace("\\u0026", "&"),
                "durationMillis": int(m.group(7) or 0),
            })
        if tweets:
            return tweets
        for m in re.finditer(
            r'tweetId:"(\d+)",text:"((?:\\.|[^"\\])*)",media:"((?:\\.|[^"\\])*)"',
            html,
        ):
            tid = m.group(1)
            if tid in seen:
                continue
            seen.add(tid)
            tweets.append({
                "name": "",
                "screenName": "",
                "profileImage": "",
                "tweetId": tid,
                "text": self._unescape_js(m.group(2)),
                "media": m.group(3).replace("\\u0026", "&"),
                "durationMillis": 0,
            })
        return tweets

    def _fmt_dur(self, ms):
        try:
            sec = int(ms or 0) // 1000
            if sec <= 0:
                return ""
            h, sec = divmod(sec, 3600)
            mm, sec = divmod(sec, 60)
            if h:
                return "{:d}:{:02d}:{:02d}".format(h, mm, sec)
            return "{:d}:{:02d}".format(mm, sec)
        except Exception:
            return ""

    def _to_list(self, tweets):
        videos = []
        need_poster = []
        for t in tweets:
            tid = str(t.get("tweetId") or "")
            if not tid:
                continue
            remarks = self._fmt_dur(t.get("durationMillis"))
            title = self._make_title(
                t.get("name") or "",
                t.get("screenName") or "",
                t.get("text") or "",
                remarks,
            )
            if self._bad(title):
                continue
            media = t.get("media") or ""
            if media:
                self._play_cache[tid] = media
            # 封面：缓存 > 真实海报 > 头像原图
            pic = self._poster_cache.get(tid, "")
            if not pic:
                av = t.get("profileImage") or ""
                if av:
                    # 用原图，避免 _400x400 在部分图挂掉
                    pic = re.sub(r"_(?:normal|bigger|mini|x96|reasonably_small)\.", ".", av)
            need_poster.append(tid)
            videos.append({
                "vod_id": tid,
                "vod_name": title,
                "vod_pic": self._proxy_url(pic) if pic else "",
                "vod_remarks": remarks,
            })
        # 并行补真实视频封面（短超时）
        posters = self._fetch_posters_batch(need_poster)
        for v in videos:
            tid = v["vod_id"]
            if tid in posters and posters[tid]:
                self._poster_cache[tid] = posters[tid]
                v["vod_pic"] = self._proxy_url(posters[tid])
        return videos

    def _fetch_posters_batch(self, tids):
        out = {}
        if not tids:
            return out

        def one(tid):
            if tid in self._poster_cache and self._poster_cache[tid]:
                return tid, self._poster_cache[tid]
            html = self._req("/video/{}".format(tid), retry=1)
            if not html:
                return tid, ""
            m = re.search(r'https://pbs\.twimg\.com/amplify_video_thumb/[^"\s]+', html)
            if m:
                return tid, m.group(0)
            m = re.search(r'property="og:image"\s+content="(https://pbs\.twimg\.com/[^"]+)"', html)
            if m:
                return tid, m.group(1)
            m = re.search(r'property="og:image"\s+content="(https://[^"]+)"', html)
            if m:
                return tid, m.group(1)
            return tid, ""

        try:
            with ThreadPoolExecutor(max_workers=6) as ex:
                futs = [ex.submit(one, tid) for tid in tids]
                for f in as_completed(futs, timeout=12):
                    try:
                        tid, pic = f.result()
                        if pic:
                            out[tid] = pic
                    except Exception:
                        pass
        except Exception:
            for tid in tids[:8]:
                try:
                    k, pic = one(tid)
                    if pic:
                        out[k] = pic
                except Exception:
                    pass
        return out

    def detailContent(self, ids):
        try:
            if not ids:
                return {"list": []}
            tid = str(ids[0] if isinstance(ids, (list, tuple)) else ids).strip()
            m = re.search(r"(\d{10,})", tid)
            if m:
                tid = m.group(1)
            html = self._req("/video/{}".format(tid))
            name = ""
            # og:description 常含作者与时长，title 仍可能是表情
            dm = re.search(r'property="og:description"\s+content="([^"]+)"', html or "")
            tm = re.search(r'property="og:title"\s+content="([^"]+)"', html or "")
            if dm:
                desc = dm.group(1)
                # 「中文字幕 AV (@CU_JAV) 發佈的…時長 1 小時 25 分鐘。正文」
                mm = re.match(r"^(.+?)\s*\(@([^)]+)\)\s*發佈的", desc)
                body = ""
                bm = re.search(r"分鐘[。.](.*)$", desc)
                if bm:
                    body = bm.group(1).strip()
                author = mm.group(1).strip() if mm else ""
                screen = mm.group(2).strip() if mm else ""
                name = self._make_title(author, screen, body or (tm.group(1) if tm else ""), "")
            if not name and tm:
                name = re.sub(r"｜.*$", "", tm.group(1)).strip()
            if not name:
                m2 = re.search(r"<title>([^<]+)</title>", html or "")
                if m2:
                    name = re.sub(r"｜.*$", "", m2.group(1)).strip()
            if self._bad(name):
                return {"list": []}
            pic = self._poster_cache.get(tid, "")
            if not pic:
                pm = re.search(r'https://pbs\.twimg\.com/amplify_video_thumb/[^"\s]+', html or "")
                if pm:
                    pic = pm.group(0)
                else:
                    pm = re.search(r'property="og:image"\s+content="([^"]+)"', html or "")
                    if pm:
                        pic = pm.group(1)
                if pic:
                    self._poster_cache[tid] = pic
            play = self._play_cache.get(tid, "")
            if not play:
                mm = re.search(r'(https://video\.twimg\.com/[^"\s]+\.mp4[^"\s]*)', html or "")
                if mm:
                    play = mm.group(1).replace("&amp;", "&")
                else:
                    hm = re.search(r'(https://video\.twimg\.com/[^"\s]+\.m3u8[^"\s]*)', html or "")
                    if hm:
                        play = hm.group(1).replace("&amp;", "&")
                if play:
                    self._play_cache[tid] = play
            return {
                "list": [{
                    "vod_id": tid,
                    "vod_name": name or tid,
                    "vod_pic": self._proxy_url(pic) if pic else "",
                    "vod_content": name,
                    "vod_play_from": "线路1",
                    "vod_play_url": "正片$" + tid,
                }]
            }
        except Exception:
            return {"list": []}

    def searchContent(self, key, quick=False, pg="1"):
        try:
            if self._bad(key):
                return {"list": [], "page": 1, "pagecount": 1, "limit": 0, "total": 0}
            page_i = int(pg) if str(pg).isdigit() else 1
            if page_i == 1:
                html = self._req("/search?q={}".format(quote(key)))
            else:
                html = self._req(self._build_path("search_" + key, page_i))
            tweets = self._parse_ssr(html or "")
            videos = self._to_list(tweets)
            m = re.search(r'nextCursor:"([^"]+)"', html or "")
            if m:
                self._cursor_cache["search_{}:{}".format(key, page_i)] = m.group(1)
            has_more = bool(m) or len(videos) >= 15
            pagecount = page_i + 1 if has_more else page_i
            return {
                "list": videos,
                "page": page_i,
                "pagecount": pagecount,
                "limit": 20,
                "total": pagecount * 20,
            }
        except Exception:
            return {"list": [], "page": 1, "pagecount": 1, "limit": 0, "total": 0}

    def playerContent(self, flag, id, vipFlags=None):
        header = {
            "User-Agent": self.ua,
            "Referer": "https://twitter.com/",
        }
        raw = str(id or "").strip()
        if raw.startswith("http"):
            return {"parse": 0, "jx": 0, "url": raw, "header": header}
        m = re.search(r"(\d{10,})", raw)
        tid = m.group(1) if m else raw
        play = self._play_cache.get(tid, "")
        if not play:
            self.detailContent([tid])
            play = self._play_cache.get(tid, "")
        if not play:
            return {"parse": 0, "jx": 0, "url": "", "header": header}
        return {"parse": 0, "jx": 0, "url": play, "header": header}

    def localProxy(self, param):
        try:
            if not isinstance(param, dict):
                return [404, "text/plain", ""]
            url = param.get("url") or ""
            typ = (param.get("type") or "").lower()
            if not url:
                return [404, "text/plain", ""]
            # 图片代理：带 Twitter Referer，解决壳内封面裂图
            if typ in ("img", "image", "pic", "jpg", "jpeg", "png", "webp") or any(
                x in url for x in ("pbs.twimg.com", "amplify_video_thumb", "profile_images", "media/")
            ):
                data, ctype = self._req_bytes(url)
                if not data:
                    return [502, "text/plain", "img fetch failed"]
                if not ctype or "text" in ctype:
                    ctype = "image/jpeg"
                return [200, ctype, data]
            # m3u8
            text = self._req(url, headers={
                "User-Agent": self.ua,
                "Referer": "https://twitter.com/",
                "Accept": "*/*",
            })
            if not text:
                return [502, "text/plain", "fetch failed"]
            if "#EXT-X-STREAM-INF" in text and "#EXTINF" not in text:
                for line in text.splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        sub = line if line.startswith("http") else urljoin(url, line)
                        text = self._req(sub, headers={
                            "User-Agent": self.ua,
                            "Referer": "https://twitter.com/",
                            "Accept": "*/*",
                        })
                        url = sub
                        break
            return [200, "application/vnd.apple.mpegurl", self._clean_m3u8(text or "", url)]
        except Exception as e:
            return [500, "text/plain", str(e)[:200]]

    def _clean_m3u8(self, content, base_url=""):
        if not content or "#EXTM3U" not in content:
            return content
        parsed = urlparse(base_url)
        base_origin = "{}://{}".format(parsed.scheme, parsed.netloc)
        base_dir = base_url.rsplit("/", 1)[0] + "/"
        out = []
        for line in content.splitlines():
            s = line.strip()
            if not s:
                continue
            if s.startswith("#EXT-X-KEY") or s.startswith("#EXT-X-MAP"):
                mk = re.search(r'URI="([^"]+)"', s)
                if mk:
                    uri = mk.group(1)
                    if uri.startswith("/") and not uri.startswith("//"):
                        s = s.replace('URI="{}"'.format(uri), 'URI="{}"'.format(base_origin + uri))
                    elif not uri.startswith("http"):
                        s = s.replace('URI="{}"'.format(uri), 'URI="{}"'.format(urljoin(base_dir, uri)))
                out.append(s)
            elif s.startswith("#"):
                out.append(s)
            else:
                if s.startswith("http"):
                    out.append(s)
                elif s.startswith("/"):
                    out.append(base_origin + s)
                else:
                    out.append(urljoin(base_dir, s))
        return "\n".join(out)

    def isVideoFormat(self, url):
        u = url or ""
        return ".m3u8" in u or ".mp4" in u

    def manualVideoCheck(self):
        return False
