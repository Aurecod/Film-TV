# coding=utf-8
import sys
import re
import json
import base64
from urllib.parse import quote, urljoin, unquote

sys.path.append('..')
try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        pass

class Spider(BaseSpider):
    def __init__(self):
        self.extend = ""
        self.host = "https://fcjav.com"
        # 主分类结构：Movies, Genres, Actors, Studios, Labels, Directors (中文)
        self.classes = [
            {"type_id": "movies", "type_name": "电影"},
            {"type_id": "genres", "type_name": "分类"},
            {"type_id": "actors", "type_name": "女优"},
            {"type_id": "studios", "type_name": "片商"},
            {"type_id": "labels", "type_name": "厂牌"},
            {"type_id": "directors", "type_name": "导演"},
        ]
        # 筛选器：每个主分类下的子分类 (中文)
        self.filters = {
            "movies": [
                {"key": "genre", "name": "类型", "init": "all", "value": [
                    {"n": "全部", "v": "all"},
                    {"n": "业余", "v": "amateur"},
                    {"n": "有码", "v": "censored"},
                    {"n": "无码", "v": "uncensored"},
                ]},
                {"key": "quality", "name": "画质", "init": "all", "value": [
                    {"n": "全部", "v": "all"},
                    {"n": "高清", "v": "hd"},
                    {"n": "标清", "v": "sd"},
                ]},
                {"key": "year", "name": "年份", "init": "all", "value": [
                    {"n": "全部", "v": "all"},
                    {"n": "2026", "v": "2026"},
                    {"n": "2025", "v": "2025"},
                    {"n": "2024", "v": "2024"},
                    {"n": "2023", "v": "2023"},
                    {"n": "2022", "v": "2022"},
                    {"n": "2021", "v": "2021"},
                    {"n": "2020", "v": "2020"},
                    {"n": "2019", "v": "2019"},
                    {"n": "2018", "v": "2018"},
                    {"n": "2017", "v": "2017"},
                    {"n": "2016", "v": "2016"},
                ]},
                {"key": "sort", "name": "排序", "init": "desc", "value": [
                    {"n": "最新更新", "v": "desc"},
                    {"n": "最早更新", "v": "asc"},
                    {"n": "发行日期", "v": "release"},
                    {"n": "播放量", "v": "viewed"},
                    {"n": "点赞数", "v": "liked"},
                    {"n": "收藏数", "v": "favorite"},
                ]},
            ],
            "genres": [
                {"key": "genre", "name": "题材", "init": "amateur", "value": [
                    {"n": "业余", "v": "amateur"},
                    {"n": "肛交", "v": "anal"},
                    {"n": "AV女优", "v": "av-idol"},
                    {"n": "美少女", "v": "beautiful-girl"},
                    {"n": "美穴", "v": "beautiful-pussy"},
                    {"n": "大屁股", "v": "big-asses"},
                    {"n": "巨乳", "v": "big-tits"},
                    {"n": "口交", "v": "blowjob"},
                    {"n": "束缚", "v": "bondage"},
                    {"n": "颜射", "v": "bukkake"},
                    {"n": "出轨人妻", "v": "cheating-wife"},
                    {"n": "Cosplay", "v": "cosplay"},
                    {"n": "中出", "v": "creampie"},
                    {"n": "颜射", "v": "cumshot"},
                    {"n": "减薄马赛克", "v": "reducing-mosaic"},
                    {"n": "无码流出", "v": "uncensored-leaked"},
                ]},
            ],
            "actors": [
                {"key": "actor", "name": "女优", "init": "yui-hatano", "value": [
                    {"n": "波多野结衣", "v": "yui-hatano"},
                    {"n": "筱田优", "v": "yu-shinoda"},
                    {"n": "大槻响", "v": "hibiki-otsuki"},
                    {"n": "饭冈加奈子", "v": "kanako-iioka"},
                    {"n": "滨崎真绪", "v": "mao-hamasaki"},
                    {"n": "松本一香", "v": "ichika-matsumoto"},
                    {"n": "JULIA", "v": "julia"},
                    {"n": "水野朝阳", "v": "asahi-mizuno"},
                    {"n": "水月弥生", "v": "mizuki-yayoi"},
                    {"n": "新村明里", "v": "akari-niimura"},
                    {"n": "AIKA", "v": "aika"},
                ]},
            ],
            "studios": [
                {"key": "studio", "name": "片商", "init": "fc2ppv", "value": [
                    {"n": "FC2PPV", "v": "fc2ppv"},
                    {"n": "Madonna", "v": "madonna"},
                    {"n": "MOODYZ", "v": "moodyz"},
                    {"n": "S1 NO.1 STYLE", "v": "s1-no-1-style"},
                    {"n": "SOD Create", "v": "sod-create"},
                    {"n": "Attackers", "v": "attackers"},
                    {"n": "Prestige", "v": "prestige"},
                    {"n": "Idea Pocket", "v": "idea-pocket"},
                    {"n": "K M Produce", "v": "k-m-produce"},
                    {"n": "Venus", "v": "venus"},
                    {"n": "Fitch", "v": "fitch"},
                ]},
            ],
            "labels": [
                {"key": "label", "name": "厂牌", "init": "madonna", "value": [
                    {"n": "Madonna", "v": "madonna"},
                    {"n": "S1 NO.1 STYLE", "v": "s1-no-1-style"},
                    {"n": "MOODYZ DIVA", "v": "moodyz-diva"},
                    {"n": "Tissue", "v": "tissue"},
                    {"n": "HHH Group", "v": "hhh-group"},
                    {"n": "Das", "v": "das"},
                    {"n": "GLORY QUEST", "v": "glory-quest"},
                    {"n": "SOD star", "v": "sod-star"},
                    {"n": "Honnaka", "v": "honnaka"},
                    {"n": "OPPAI", "v": "oppai"},
                    {"n": "Fitch", "v": "fitch"},
                ]},
            ],
            "directors": [
                {"key": "director", "name": "导演", "init": "kitorune-kawaguchi", "value": [
                    {"n": "北条麻妃", "v": "kitorune-kawaguchi"},
                    {"n": "豆泽真太郎", "v": "mamezawa-mametarou"},
                    {"n": "三岛六三郎", "v": "mishima-rokusaburo"},
                    {"n": "龙西川", "v": "doragon-nishikawa"},
                    {"n": "强制", "v": "kyousei"},
                    {"n": "TAKE-D", "v": "take-d"},
                    {"n": "Torendei Yamaguchi", "v": "torendei-yamaguchi"},
                    {"n": "五右卫门", "v": "goemon"},
                    {"n": "赤井彗星", "v": "akai-suisei"},
                    {"n": "真崎奈绪", "v": "masaki-nao"},
                    {"n": "冰室", "v": "himurokku"},
                ]},
            ],
        }
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 14; 22127RK46C) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
            'Referer': self.host + '/',
        }

    def getName(self):
        return "FCJAV"

    def getDependence(self):
        return []

    def init(self, extend=""):
        self.extend = extend or ""
        if not hasattr(self, 'session') or self.session is None:
            import requests
            self.session = requests.Session()
        self.session.headers.update(self.headers)

    def _fetch(self, url, params=None, headers=None):
        try:
            h = dict(self.session.headers)
            if headers:
                h.update(headers)
            r = self.session.get(url, params=params, headers=h, timeout=15)
            r.encoding = r.apparent_encoding or 'utf-8'
            return r.text
        except Exception as e:
            self.log(f"GET {url} failed: {e}")
            return ""

    def _post(self, url, data, headers=None):
        try:
            h = dict(self.session.headers)
            h.update(headers or {})
            r = self.session.post(url, data=data, headers=h, timeout=15)
            r.encoding = r.apparent_encoding or 'utf-8'
            return r.text
        except Exception as e:
            self.log(f"POST {url} failed: {e}")
            return ""

    def _parse_list(self, html):
        videos = []
        if not html:
            return videos
        blocks = re.split(r'<div class="ml-item">', html)[1:]
        for b in blocks:
            m_link = re.search(r'href="(https?://[^"]*/v/[^"]+)"', b)
            if not m_link:
                continue
            link = m_link.group(1)
            vid = link.rstrip("/").split("/v/")[-1]
            m_title = re.search(r'<a[^>]+class="ml-mask[^"]*"[^>]*title="([^"]*)"', b)
            if not m_title:
                m_title = re.search(r'title="([^"]*)"', b)
            name = m_title.group(1).strip() if m_title else vid
            m_pic = re.search(r'data-original="([^"]+)"', b)
            if not m_pic:
                m_pic = re.search(r'<img[^>]+src="([^"]+)"', b)
            pic = m_pic.group(1) if m_pic else ""
            m_rem = re.search(r'class="mli-runtimes"[^>]*>([^<]+)<', b)
            if not m_rem:
                m_rem = re.search(r'class="mli-code"[^>]*>([^<]+)<', b)
            remark = m_rem.group(1).strip() if m_rem else ""
            videos.append({
                'vod_id': vid,
                'vod_name': name,
                'vod_pic': pic,
                'vod_remarks': remark,
            })
        return videos

    def homeContent(self, filter):
        html = self._fetch(self.host)
        videos = self._parse_list(html)
        return {'class': self.classes, 'filters': self.filters if filter else {}, 'list': videos}

    def homeVideoContent(self):
        html = self._fetch(self.host + '/movies')
        return {'list': self._parse_list(html)}

    def _build_cat_url(self, tid, pg, extend):
        p = int(pg or 1)
        tid = str(tid or "movies")
        base_url = self.host

        if tid == "movies":
            params = []
            if extend:
                if extend.get("genre") and extend["genre"] != "all":
                    params.append("genre=" + extend["genre"])
                if extend.get("quality") and extend["quality"] != "all":
                    params.append("quality=" + extend["quality"])
                if extend.get("year") and extend["year"] != "all":
                    params.append("year=" + extend["year"])
                if extend.get("sort") and extend["sort"] != "desc":
                    params.append("sort=" + extend["sort"])
            if params:
                base_url += "/movies?" + "&".join(params)
            else:
                base_url += "/movies"
            if p > 1:
                base_url += ("&pg=%d" % p)
            return base_url

        if tid == "genres":
            genre = extend.get("genre", "amateur") if extend else "amateur"
            base_url += "/genre/%s" % genre
            if p > 1:
                base_url += "/pg-%d" % p
            return base_url

        if tid == "actors":
            actor = extend.get("actor", "yui-hatano") if extend else "yui-hatano"
            base_url += "/actor/%s" % actor
            if p > 1:
                base_url += "/pg-%d" % p
            return base_url

        if tid == "studios":
            studio = extend.get("studio", "fc2ppv") if extend else "fc2ppv"
            base_url += "/studio/%s" % studio
            if p > 1:
                base_url += "/pg-%d" % p
            return base_url

        if tid == "labels":
            label = extend.get("label", "madonna") if extend else "madonna"
            base_url += "/label/%s" % label
            if p > 1:
                base_url += "/pg-%d" % p
            return base_url

        if tid == "directors":
            director = extend.get("director", "kitorune-kawaguchi") if extend else "kitorune-kawaguchi"
            base_url += "/director/%s" % director
            if p > 1:
                base_url += "/pg-%d" % p
            return base_url

        return base_url + "/movies"

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg or 1)
        url = self._build_cat_url(tid, page, extend)
        html = self._fetch(url)
        lst = self._parse_list(html)

        pagecount = 1
        pages = []
        m = re.search(r"<ul[^>]*class=['\"]pagination['\"][^>]*>[\s\S]*?</ul>", html or "")
        seg = m.group(0) if m else (html or "")
        for mm in re.finditer(r"pg[-=](\d+)", seg):
            try:
                pages.append(int(mm.group(1)))
            except Exception:
                pass
        if pages:
            pagecount = max(pages)
            if pagecount < page:
                pagecount = page
        else:
            m2 = re.search(r"of\s+(\d+)", seg)
            if m2:
                try:
                    pagecount = max(int(m2.group(1)), page)
                except Exception:
                    pagecount = page

        return {
            'list': lst,
            'page': page,
            'pagecount': pagecount,
            'limit': 24,
            'total': pagecount * 24,
        }

    def _clean_tail(self, text):
        return re.sub(r'\s+', ' ', text or '').strip()

    def _norm_ids(self, ids):
        if ids is None:
            return ""
        if isinstance(ids, (list, tuple)):
            if not ids:
                return ""
            ids = ids[0]
        if isinstance(ids, bytes):
            ids = ids.decode("utf-8", errors="ignore")
        return str(ids).strip()

    def detailContent(self, ids):
        raw = self._norm_ids(ids)
        if not raw:
            return {'list': []}
        vid = raw.split("|$|")[0]
        try:
            durl = vid if vid.startswith("http") else "%s/v/%s" % (self.host, vid)
            html = self._fetch(durl)
            if not html or len(html) < 500:
                return {'list': [{'vod_id': raw, 'vod_name': vid, 'vod_pic': '', 'vod_remarks': '解析中', 'vod_content': '', 'vod_play_from': '播放', 'vod_play_url': '播放$' + vid}]}

            name = ""
            m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
            if m:
                name = self._clean_tail(re.sub(r'<[^>]+>', '', m.group(1)))
                name = re.sub(r'^[A-Z0-9\-]+\s+', '', name)
            if not name:
                m = re.search(r'<title>(.*?)</title>', html, re.S)
                if m:
                    name = self._clean_tail(m.group(1))
                    name = re.sub(r'\s*[-|]\s*FCJAV.*$', '', name, flags=re.I)
                    name = re.sub(r'^[A-Z0-9\-]+\s+', '', name)
            if not name:
                name = vid

            pic = ""
            for pat in [r'og:image"\s+content="([^"]+)"', r'data-poster="([^"]+)"',
                        r'<img[^>]+class="cover"[^>]+src="([^"]+)"']:
                m = re.search(pat, html)
                if m:
                    pic = m.group(1)
                    break

            content = ""
            m = re.search(r'name="description"\s+content="([^"]*)"', html)
            if m:
                content = m.group(1)
            if not content:
                m = re.search(r'property="og:description"\s+content="([^"]*)"', html)
                if m:
                    content = m.group(1)

            remark = ""
            m = re.search(r'class="mli-runtimes"[^>]*>([^<]+)<', html)
            if m:
                remark = m.group(1).strip()

            eps = re.findall(r'class="switch-source[^"]*"\s+data-source="(\d+)"\s+data-id="(\d+)"[^>]*>[\s\S]*?</button>', html)
            if not eps:
                eps = re.findall(r'data-source="(\d+)"\s+data-id="(\d+)"', html)
            names = re.findall(r'class="switch-source[^"]*"[^>]*>[\s\S]*?</i>\s*([A-Za-z0-9]+)\s*</button>', html)

            film_id = ""
            m = re.search(r'filmId\s*=\s*(\d+)', html)
            if m:
                film_id = m.group(1)

            froms = []
            urls = []
            if eps:
                ep_list = []
                seen = set()
                for idx, (src, eid) in enumerate(eps):
                    if eid in seen:
                        continue
                    seen.add(eid)
                    ep_name = names[idx] if idx < len(names) else ("线路%d" % (idx + 1))
                    pid = "%s|%s|%s" % (src, eid, vid)
                    ep_list.append("%s$%s" % (ep_name, pid))
                if ep_list:
                    froms.append("播放")
                    urls.append("#".join(ep_list))

            if not froms:
                return {'list': [{'vod_id': raw, 'vod_name': name, 'vod_pic': pic, 'vod_remarks': remark or '解析中', 'vod_content': content, 'vod_play_from': '播放', 'vod_play_url': '播放$' + vid}]}

            vod = {
                'vod_id': raw,
                'vod_name': name,
                'vod_pic': pic,
                'vod_remarks': remark,
                'vod_content': content,
                'vod_play_from': '$$$'.join(froms),
                'vod_play_url': '$$$'.join(urls),
            }
            if len(vod['vod_play_from'].split("$$$")) != len(vod['vod_play_url'].split("$$$")):
                return {'list': [{'vod_id': raw, 'vod_name': name, 'vod_pic': pic, 'vod_remarks': remark or '解析中', 'vod_content': content, 'vod_play_from': '播放', 'vod_play_url': '播放$' + vid}]}
            return {'list': [vod]}
        except Exception as e:
            self.log({"detail": "exception", "ids": raw, "error": str(e)})
            return {'list': [{'vod_id': raw, 'vod_name': '未知标题', 'vod_pic': '', 'vod_remarks': '解析中', 'vod_content': '', 'vod_play_from': '播放', 'vod_play_url': '播放$' + vid}]}

    def searchContent(self, key, quick, pg="1"):
        page = int(pg or 1)
        kw = quote(str(key or "").strip())
        if page > 1:
            url = "%s/search/%s/pg-%d" % (self.host, kw, page)
        else:
            url = "%s/search/%s" % (self.host, kw)
        html = self._fetch(url)
        lst = self._parse_list(html)
        return {'list': lst, 'page': page}

    def _decode_player_enc(self, enc, pk):
        try:
            raw = base64.b64decode(enc)
            key = pk.encode("utf-8")
            out = bytes([raw[i] ^ key[i % len(key)] for i in range(len(raw))])
            return out.decode("utf-8", errors="ignore")
        except Exception as e:
            self.log({"decode_player_enc": "fail", "error": str(e)})
            return ""

    def _extract_play_url(self, iframe_html):
        if not iframe_html:
            return ""
        for pat in [r"var\s+urlPlay\s*=\s*'([^']+)'", r'var\s+urlPlay\s*=\s*"([^"]+)"',
                    r'"file"\s*:\s*"([^"]+)"', r"'file'\s*:\s*'([^']+)'"]:
            m = re.search(pat, iframe_html)
            if m and m.group(1):
                return m.group(1).strip()
        return ""

    def playerContent(self, flag, id, vipFlags):
        raw = str(id or "")
        if "$" in raw:
            raw = raw.split("$", 1)[1]

        film_id, eid, slug = "", "", ""
        if "|" in raw and not raw.startswith("http"):
            parts = raw.split("|")
            film_id = parts[0]
            eid = parts[1] if len(parts) > 1 else ""
            slug = parts[2] if len(parts) > 2 else ""
        elif raw.startswith("http"):
            if raw.endswith((".mp4", ".m3u8")):
                return {"parse": 0, "url": raw, "header": {"User-Agent": self.headers["User-Agent"]}}
            slug = raw.rstrip("/").split("/v/")[-1]
        else:
            slug = raw

        pt, pk = "", ""
        det = ""
        if slug:
            det = self._fetch("%s/v/%s" % (self.host, slug))
        if det:
            if not film_id:
                m = re.search(r'filmId\s*=\s*(\d+)', det)
                if m:
                    film_id = m.group(1)
                m = re.search(r'data-source="(\d+)"\s+data-id="(\d+)"', det)
                if m:
                    film_id = m.group(1)
                    if not eid:
                        eid = m.group(2)
            pt_m = re.search(r'__pt\s*=\s*"([^"]+)"', det)
            pk_m = re.search(r'__pk\s*=\s*"([^"]+)"', det)
            pt = pt_m.group(1) if pt_m else ""
            pk = pk_m.group(1) if pk_m else ""

        if not film_id or not pt or not pk:
            return {"parse": 1, "url": ("%s/v/%s" % (self.host, slug)) if slug else (self.host + "/movies"), "header": self.headers}

        ajax_headers = {
            "User-Agent": self.headers["User-Agent"],
            "Referer": ("%s/v/%s" % (self.host, slug)) if slug else (self.host + "/"),
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        body = "episode=%s&filmId=%s&pt=%s" % (eid, film_id, pt)
        resp = self._post(self.host + "/ajax/player", data=body, headers=ajax_headers)
        if not resp:
            return {"parse": 1, "url": ("%s/v/%s" % (self.host, slug)) if slug else (self.host + "/movies"), "header": self.headers}
        try:
            j = json.loads(resp)
        except Exception:
            return {"parse": 1, "url": ("%s/v/%s" % (self.host, slug)) if slug else (self.host + "/movies"), "header": self.headers}
        if j.get("error"):
            return {"parse": 1, "url": ("%s/v/%s" % (self.host, slug)) if slug else (self.host + "/movies"), "header": self.headers}

        iframe_html = ""
        if j.get("player_enc"):
            iframe_html = self._decode_player_enc(j.get("player_enc", ""), pk)
        elif j.get("player"):
            iframe_html = j.get("player", "")

        iframe_url = ""
        m = re.search(r'src="([^"]+)"', iframe_html or "")
        if m:
            iframe_url = m.group(1)

        play_url = ""
        if iframe_url:
            ih = self._fetch(iframe_url, headers={"User-Agent": self.headers["User-Agent"], "Referer": self.host + "/"})
            play_url = self._extract_play_url(ih)

        if play_url:
            return {"parse": 0, "url": play_url, "header": {"User-Agent": self.headers["User-Agent"], "Referer": self.host + "/"}}
        if iframe_url:
            return {"parse": 1, "url": iframe_url, "header": self.headers}
        return {"parse": 1, "url": ("%s/v/%s" % (self.host, slug)) if slug else (self.host + "/movies"), "header": self.headers}

    def localProxy(self, param):
        return [404, "text/plain", ""]