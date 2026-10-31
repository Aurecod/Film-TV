# coding=utf-8
import sys
sys.path.append('..')
from base.spider import Spider

import json
import re
import requests
from lxml import etree


class Spider(Spider):
    def getName(self):
        return "海角乱伦"

    def init(self, extend=""):
        self.host = "https://4tw3gy653a.bulunhufait.buzz"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 13; Pixel) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Mobile Safari/537.36",
            "Referer": self.host + "/",
        }
        try:
            import requests as req
            self.session = req.Session()
            self.session.headers.update(self.headers)
        except Exception:
            self.session = None

    # ==================== helpers ====================

    def _fetch(self, url, **kwargs):
        kwargs.setdefault("timeout", 15)
        kwargs.setdefault("verify", False)
        try:
            if self.session is not None:
                r = self.session.get(url, **kwargs)
            else:
                r = self.fetch(url, headers=self.headers, timeout=15, verify=False)
            r.encoding = "utf-8"
            return r
        except Exception:
            return None

    @staticmethod
    def _clean(title):
        return title.replace("$", "＄").replace("#", "＃")

    def _fix(self, u):
        if not u:
            return ""
        u = u.strip()
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("/"):
            return self.host + u
        return u

    def _detail(self, vid):
        url = f"{self.host}/voddetail/{vid}/"
        r = self._fetch(url)
        if r is None:
            return "", "", []
        try:
            tree = self.html(r.text)
            title = ""
            for t in tree.xpath('//div[contains(@class,"detail_right")]//h1/text() | //h1/text()'):
                t = t.strip()
                if t:
                    title = t
                    break
            pic = ""
            for src in tree.xpath('//div[contains(@class,"detail_left")]//img/@src | //div[contains(@class,"detail")]//img/@src'):
                if src:
                    pic = self._fix(src)
                    break
            plays = []
            for a in tree.xpath('//div[contains(@class,"play-group")]//a | //div[contains(@class,"play")]//a'):
                href = a.xpath('./@href')[0]
                m = re.search(r'/vodplay/(\d+)-(\d+)-(\d+)/', href)
                if m:
                    plays.append(f'{m.group(1)}@@@{m.group(2)}@@@{m.group(3)}')
            return title, pic, plays
        except Exception:
            return "", "", []

    def _list(self, url, pg="1"):
        pg = str(pg)
        if pg not in ("1", ""):
            if "/vodtype/" in url:
                url = url.rstrip("/") + f"/page/{pg}/"
            elif url.rstrip("/") == f"{self.host}/vod":
                url = f"{self.host}/vod/page/{pg}/"
            else:
                url = url.rstrip("/") + f"/page/{pg}/"
        r = self._fetch(url)
        if r is None:
            return {"list": [], "page": 1, "pagecount": 1, "limit": 0, "total": 0}
        try:
            tree = self.html(r.text)
            videos = []
            seen = set()
            for dl in tree.xpath('//dl[dt[contains(@class,"preview-item")]]'):
                try:
                    dt = dl.xpath('./dt[contains(@class,"preview-item")]')[0]
                    a = dt.xpath('./a')[0]
                    href = a.xpath('./@href')[0]
                    m = re.search(r'/voddetail/(\d+)/', href)
                    if not m:
                        continue
                    vid = m.group(1)
                    if vid in seen:
                        continue
                    seen.add(vid)
                    imgs = a.xpath('.//img/@data-original | .//img/@src')
                    raw_img = self._fix(imgs[0]) if imgs else ""
                    dd = dl.xpath('./dd')
                    name = ""
                    if dd:
                        for t in dd[0].xpath('.//h3/text() | .//a/text()'):
                            t = t.strip()
                            if t:
                                name = t
                                break
                    if name:
                        videos.append({
                            "vod_id": f"vod/{vid}",
                            "vod_name": self._clean(name),
                            "vod_pic": raw_img,
                            "vod_remarks": "",
                        })
                except Exception:
                    continue
            page = int(pg) if pg.isdigit() else 1
            pagecount = 9999 if videos else page
            return {"list": videos, "page": page, "pagecount": pagecount, "limit": len(videos), "total": len(videos)}
        except Exception:
            return {"list": [], "page": 1, "pagecount": 1, "limit": 0, "total": 0}

    # ==================== nav / filters ====================

    # 硬编码备选筛选表
    _FALLBACK_FILTERS = {
        "162": [{"key": "class", "name": "分类", "value": [
            {"n": "全部", "v": "162"},
            {"n": "国产区", "v": "383"},
            {"n": "视频五区", "v": "640"},
            {"n": "中文字幕", "v": "283"},
            {"n": "国产传媒", "v": "633"},
            {"n": "日本素人", "v": "161"},
            {"n": "兽耳系列", "v": "95"},
            {"n": "男同性恋", "v": "103"},
        ]}],
        "441": [{"key": "class", "name": "分类", "value": [
            {"n": "全部", "v": "441"},
            {"n": "国产精品", "v": "49"},
            {"n": "网曝门", "v": "411"},
            {"n": "巨乳美乳", "v": "355"},
            {"n": "国产自拍", "v": "417"},
            {"n": "大秀视频", "v": "38"},
            {"n": "素人自拍", "v": "80"},
            {"n": "熟女人妻", "v": "14"},
            {"n": "乱伦", "v": "55"},
        ]}],
        "32": [{"key": "class", "name": "分类", "value": [
            {"n": "全部", "v": "32"},
            {"n": "映画传媒", "v": "165"},
            {"n": "主播直播", "v": "64"},
            {"n": "反差母狗", "v": "629"},
            {"n": "美乳巨乳", "v": "392"},
            {"n": "过膝袜", "v": "98"},
            {"n": "探花系列", "v": "180"},
            {"n": "绝顶潮吹", "v": "402"},
            {"n": "短视频", "v": "171"},
        ]}],
        "347": [{"key": "class", "name": "分类", "value": [
            {"n": "全部", "v": "347"},
            {"n": "香蕉传媒", "v": "437"},
            {"n": "国产主播", "v": "3"},
            {"n": "网曝门", "v": "411"},
            {"n": "电车痴汉", "v": "407"},
            {"n": "糖心Vlog", "v": "441"},
            {"n": "无码专区", "v": "351"},
            {"n": "制服诱惑", "v": "612"},
            {"n": "传媒自拍", "v": "6"},
        ]}],
        "431": [{"key": "class", "name": "分类", "value": [
            {"n": "全部", "v": "431"},
            {"n": "香蕉传媒", "v": "437"},
            {"n": "颜射系列", "v": "32"},
            {"n": "短视频", "v": "171"},
            {"n": "热门事件", "v": "5"},
            {"n": "奥斯卡资源", "v": "296"},
            {"n": "制服诱惑", "v": "15"},
            {"n": "电车痴汉", "v": "407"},
            {"n": "熟女少妇", "v": "631"},
        ]}],
    }

    _CLASS_MAP = [
        {"type_id": "162", "type_name": "在线热播"},
        {"type_id": "441", "type_name": "必射仓库"},
        {"type_id": "32",  "type_name": "国产精品"},
        {"type_id": "347", "type_name": "无码中文"},
        {"type_id": "431", "type_name": "偷拍片库"},
    ]

    def _fetch_nav(self):
        if hasattr(self, '_nav_cache'):
            return self._nav_cache
        try:
            r = self._fetch(f"{self.host}/vodtype/162/")
            if r is None:
                return []
            tree = self.html(r.text)
            nav = []
            for dl in tree.xpath('//div[contains(@class,"menu")]//dl[dt/a][dd/a[@href]]'):
                try:
                    dt = dl.xpath('./dt/a')
                    parent = (dt[0].text or '').strip() if dt else ''
                    subs = []
                    for a in dl.xpath('./dd/a[@href]'):
                        href = (a.get('href') or '').strip()
                        name = (a.text or '').strip()
                        if not href or not name:
                            continue
                        m = re.search(r'/vodtype/(\d+)/', href)
                        if m:
                            subs.append({"type_id": m.group(1), "type_name": name})
                    if parent and subs:
                        nav.append({"parent": parent, "subs": subs})
                except Exception:
                    continue
            self._nav_cache = nav
            return nav
        except Exception:
            return []

    # ==================== 接口实现 ====================

    def homeContent(self, filter):
        try:
            nav = self._fetch_nav()
            name_to_subs = {}
            for block in nav:
                name_to_subs[block['parent']] = block['subs']

            classes = [dict(c) for c in self._CLASS_MAP]
            filters = {}
            for c in classes:
                subs = name_to_subs.get(c['type_name'], [])
                if not subs and c['type_id'] in self._FALLBACK_FILTERS:
                    fallback = self._FALLBACK_FILTERS[c['type_id']]
                    subs = [{"type_id": v['v'], "type_name": v['n']}
                            for v in fallback[0]['value'] if v['v'] != c['type_id']]
                if subs:
                    values = [{"n": "全部", "v": c['type_id']}]
                    for sub in subs:
                        values.append({"n": sub['type_name'], "v": sub['type_id']})
                    filters[c['type_id']] = [
                        {"key": "class", "name": "分类", "value": values}
                    ]
            return {"class": classes, "filters": filters}
        except Exception:
            filters = {}
            for c in self._CLASS_MAP:
                if c['type_id'] in self._FALLBACK_FILTERS:
                    filters[c['type_id']] = self._FALLBACK_FILTERS[c['type_id']]
            return {"class": [dict(c) for c in self._CLASS_MAP], "filters": filters}

    def homeVideoContent(self):
        try:
            return self._list(f"{self.host}/vod/")
        except Exception:
            return {"list": [], "page": 1, "pagecount": 1, "limit": 0, "total": 0}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            url = f"{self.host}/vodtype/{tid}/"
            return self._list(url, pg)
        except Exception:
            return {"list": [], "page": 1, "pagecount": 1, "limit": 0, "total": 0}

    def detailContent(self, ids):
        try:
            if not ids:
                return {"list": []}
            out = []
            for raw in ids:
                vid = raw.replace("vod/", "")
                title, pic, plays = self._detail(vid)
                if plays:
                    frm = "$$$".join([f"线路{i+1}" for i in range(len(plays))])
                    urls = "$$$".join([f"正片${p}" for p in plays])
                else:
                    frm = "线路1"
                    urls = f"正片${vid}@@@1@@@1"
                out.append({
                    "vod_id": f"vod/{vid}",
                    "vod_name": self._clean(title),
                    "vod_pic": pic,
                    "vod_play_from": frm,
                    "vod_play_url": urls,
                    "vod_tag": "",
                    "vod_remarks": "",
                })
            return {"list": out}
        except Exception:
            return {"list": []}

    def searchContent(self, key, quick, pg="1"):
        try:
            from urllib.parse import quote
            url = f"{self.host}/vodsearch/-------------/?wd={quote(key)}&page={pg}"
            return self._list(url, pg)
        except Exception:
            return {"list": [], "page": 1, "pagecount": 1, "limit": 0, "total": 0}

    def playerContent(self, flag, id, vipFlags):
        try:
            parts = id.split("@@@")
            if len(parts) != 3:
                return {"parse": 0, "url": "", "header": self.headers}
            vid, server, ep = parts
            play_url = f"{self.host}/vodplay/{vid}-{server}-{ep}/"
            r = self._fetch(play_url)
            if r is None:
                return {"parse": 0, "url": "", "header": self.headers}
            m = re.search(r'var player_data=(\{.*?\})</script>', r.text, re.DOTALL)
            if m:
                try:
                    pd = json.loads(m.group(1))
                    u = pd.get("url", "")
                    if u:
                        return {"parse": 0, "url": u, "header": self.headers}
                except Exception:
                    pass
            return {"parse": 0, "url": "", "header": self.headers}
        except Exception:
            return {"parse": 0, "url": "", "header": self.headers}

    def liveContent(self, url):
        return "[]"

    def action(self, action):
        return {"msg": "不支持"}

    def localProxy(self, param):
        return [404, "text/plain", ""]