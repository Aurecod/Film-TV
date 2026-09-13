# -*- coding: utf-8 -*-
"""
红果短剧 - FongMi Type3 Python Spider
网站: https://hongguoduanju.com (ByteDance/抖音旗下短剧站)
数据来源: SSR 页面内嵌的 _ROUTER_DATA JSON
"""
import json
import re
import time
import base64

import requests

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        pass

NAME = "红果短剧"
HOSTS = ["https://hongguoduanju.com"]
UA = "Mozilla/5.0 (Linux; Android 13; Pixel) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
PAGE_SIZE = 20
CACHE_TTL = 30
STYLE = {"type": "rect", "ratio": 0.75}   # 短剧竖版封面


class Spider(BaseSpider):

    def __init__(self):
        self.hosts = list(HOSTS)
        self.host = self.hosts[0]
        self.name = NAME
        self.headers = {"User-Agent": UA, "Referer": self.host + "/", "Accept": "*/*"}
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self._cache = {}
        self._good_host = None
        self._categories = None
        self._router_cache = {}

    def init(self, extend=""):
        if extend:
            try:
                cfg = json.loads(extend)
                site = (cfg.get("site") or cfg.get("url") or "").strip().rstrip("/")
                if site:
                    self.hosts = [site] + [h for h in self.hosts if h != site]
                    self.host = self.hosts[0]
            except Exception:
                pass

    def getName(self):
        return self.name

    def getDependence(self):
        return []

    def destroy(self):
        pass

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4|flv|mkv|ts)(\?|$)", str(url)))

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return ""

    # ---------- 首页 ----------
    def homeContent(self, filter):
        classes = self._classes()
        return {
            "class": classes,
            "filters": self._filters(classes),
            "list": [self._vod(x) for x in self._home_items()],
        }

    def homeVideoContent(self):
        return {"list": []}

    # ---------- 分类 ----------
    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        extend = extend or {}
        items = []
        try:
            data = self._fetch_category(tid, pg)
            items = self._list(data)
        except Exception:
            items = []
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": 9999 if len(items) >= PAGE_SIZE else pg,
            "limit": PAGE_SIZE,
            "total": 999999,
        }

    # ---------- 详情 ----------
    def detailContent(self, ids):
        vid = str(ids[0])
        try:
            data = self._fetch_detail(vid)
            detail = self._extract_detail(data)
        except Exception:
            return {"list": []}
        if not isinstance(detail, dict):
            return {"list": []}

        # vid_list 包含所有集的 vid
        vid_list = detail.get("vid_list", [])
        eps_info = detail.get("series_episode_info", {})
        episode_cnt = eps_info.get("episode_cnt", len(vid_list))

        play = []
        for i, ep_vid in enumerate(vid_list[:episode_cnt], 1):
            title = f"第{i}集"
            play.append(f"{title}${vid}|{ep_vid}")
        if not play and vid:
            play = [f"正片${vid}|"]

        vod = {
            "vod_id": vid,
            "vod_name": detail.get("series_name") or vid,
            "vod_pic": detail.get("series_cover") or "",
            "type_name": "",
            "vod_year": "",
            "vod_area": "",
            "vod_remarks": f"共{episode_cnt}集",
            "vod_actor": ", ".join([c.get("name", "") for c in detail.get("celebrities", [])]) if detail.get("celebrities") else "",
            "vod_director": "",
            "vod_content": detail.get("series_intro") or "",
            "vod_play_from": self.name,
            "vod_play_url": "#".join(play),
        }
        return {"list": [vod]}

    # ---------- 搜索 ----------
    def searchContent(self, key, quick, pg="1"):
        pg = self._int(pg, 1)
        try:
            data = self._fetch_search(key, pg)
            items = self._list(data)
        except Exception:
            items = []
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": 9999 if len(items) >= PAGE_SIZE else pg,
            "limit": PAGE_SIZE,
            "total": 999999,
        }

    # ---------- 播放 ----------
    def playerContent(self, flag, id, vipFlags):
        # id 格式: series_id|vid
        parts = str(id).split("|", 1)
        series_id = parts[0]
        vid = parts[1] if len(parts) > 1 else ""
        url = ""
        try:
            url = self._fetch_play_url(series_id, vid)
        except Exception:
            url = ""
        return {
            "parse": 0,
            "url": url,
            "header": {"User-Agent": UA, "Referer": self.host + "/"},
        }

    # ================= 内部工具 =================
    def _fetch_html(self, path):
        """抓取页面 HTML 并提取 _ROUTER_DATA"""
        ck = path
        hit = self._router_cache.get(ck)
        if hit and time.time() - hit[1] < CACHE_TTL:
            return hit[0]

        hosts = list(self.hosts)
        if self._good_host in hosts:
            hosts.remove(self._good_host)
            hosts.insert(0, self._good_host)

        for h in hosts:
            try:
                url = h + path
                r = self.session.get(url, timeout=10, verify=False)
                r.raise_for_status()
                html = r.text

                # 提取 _ROUTER_DATA
                start = html.find('_ROUTER_DATA = ')
                if start < 0:
                    continue
                start += len('_ROUTER_DATA = ')
                depth = 0
                in_string = False
                escape = False
                end = -1
                for i, ch in enumerate(html[start:]):
                    if escape:
                        escape = False
                        continue
                    if ch == '\\':
                        escape = True
                        continue
                    if ch == '"' and not escape:
                        in_string = not in_string
                        continue
                    if not in_string:
                        if ch == '{':
                            depth += 1
                        elif ch == '}':
                            depth -= 1
                            if depth == 0:
                                end = start + i + 1
                                break
                if end < 0:
                    continue
                json_str = html[start:end]
                data = json.loads(json_str)
                self._good_host = h
                if h != self.host:
                    self.host = h
                self._router_cache[ck] = (data, time.time())
                return data
            except Exception:
                continue
        return {}

    def _fetch_category(self, tid, pg):
        """抓取分类页: /category/{tid}?page={pg}"""
        if pg == 1:
            path = f"/category/{tid}"
        else:
            path = f"/category/{tid}?page={pg}"
        return self._fetch_html(path)

    def _fetch_detail(self, series_id):
        """抓取详情页"""
        path = f"/detail?series_id={series_id}"
        return self._fetch_html(path)

    def _fetch_search(self, key, pg):
        """搜索"""
        path = f"/search?keyword={requests.utils.quote(key)}&page={pg}"
        return self._fetch_html(path)

    def _fetch_play_url(self, series_id, vid):
        """抓取播放页获取视频真实 URL"""
        if not vid:
            return ""
        path = f"/player/{series_id}/{vid}"
        data = self._fetch_html(path)
        try:
            loader = data.get("loaderData", {})
            for key, val in loader.items():
                if key.startswith("player_") and isinstance(val, dict):
                    vpi = val.get("video_player_info", {})
                    return vpi.get("main_url", "")
        except Exception:
            pass
        return ""

    def _extract_detail(self, data):
        """从 router data 提取详情数据"""
        if not isinstance(data, dict):
            return {}
        loader = data.get("loaderData", {})
        for key, val in loader.items():
            if key == "detail_page" and isinstance(val, dict):
                return val.get("seriesDetail", {})
        return {}

    def _classes(self):
        if self._categories is not None:
            return self._categories

        arr = []
        try:
            # 从首页获取分类导航
            data = self._fetch_html("/")
            loader = data.get("loaderData", {})
            for key, val in loader.items():
                if "category" in key and isinstance(val, dict):
                    selector_list = val.get("selectorList", [])
                    for sel in selector_list:
                        items = sel.get("items", [])
                        for it in items:
                            tag = it.get("selector_item_id", "")
                            name = it.get("show_name", "")
                            if tag and name:
                                arr.append({"type_id": tag, "type_name": name, "style": STYLE})
                    break
        except Exception:
            pass

        # 兜底固定分类（大分类：真人短剧、漫剧、AI短剧、漫画）
        if not arr:
            arr = [
                {"type_id": "real-drama", "type_name": "真人短剧", "style": STYLE},
                {"type_id": "comic-drama", "type_name": "漫剧", "style": STYLE},
                {"type_id": "ai-drama", "type_name": "AI短剧", "style": STYLE},
                {"type_id": "comic", "type_name": "漫画", "style": STYLE},
            ]

        self._categories = arr
        return arr

    def _filters(self, classes):
        common = [{"key": "order", "name": "排序", "value": [
            {"n": "默认", "v": ""}, {"n": "最新", "v": "new"}, {"n": "最热", "v": "hot"}]}]
        return {c["type_id"]: common for c in classes}

    def _home_items(self):
        try:
            data = self._fetch_html("/")
            loader = data.get("loaderData", {})
            page = loader.get("page", {})
            items = []
            for sec in page.get("homeSections", []):
                series_list = sec.get("seriesList", [])
                items.extend(series_list)
            return items
        except Exception:
            pass
        return []

    def _vod(self, item):
        item = item or {}
        vid = str(item.get("series_id") or item.get("id") or item.get("vod_id") or "")
        return {
            "vod_id": vid,
            "vod_name": item.get("series_name") or item.get("name") or item.get("title") or vid,
            "vod_pic": self._pic(item),
            "vod_remarks": item.get("episode_right_text") or item.get("update_label") or item.get("remarks") or "",
            "style": STYLE,
        }

    def _pic(self, item):
        for k in ("series_cover", "cover", "cover_url", "img", "pic", "thumb", "vod_pic", "poster_url"):
            v = item.get(k)
            if v:
                return v
        return ""

    def _list(self, data):
        """从 router data 中提取列表数据"""
        if not isinstance(data, dict):
            return []
        loader = data.get("loaderData", {})
        for key, val in loader.items():
            if isinstance(val, dict):
                # category pages: recommendList (category_$, category_layout, etc.)
                if "recommendList" in val and isinstance(val["recommendList"], list):
                    return val["recommendList"]
                # search pages: searchList
                if "searchList" in val and isinstance(val["searchList"], list):
                    return val["searchList"]
                # generic fallbacks
                for k in ("list", "items", "records", "data"):
                    v = val.get(k)
                    if isinstance(v, list):
                        return v
        return []

    def _int(self, x, d=0):
        try:
            return int(x)
        except Exception:
            return d