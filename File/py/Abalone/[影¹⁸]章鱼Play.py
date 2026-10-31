# -*- coding: utf-8 -*-
import re
import json
import html as _html
import requests
from base.spider import Spider
SITE = "https://www.zhangyuys.com"
API = SITE + "/api/v1/videos.php"
COL_API = SITE + "/api/v1/collections.php"
PLAY_BASE = "https://www.zhangyu.bar/h/%s/index.m3u8"
PIC_BASE = "https://www.zhangyu.bar/p/%s.jpg"
UA = ("Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")
TIMEOUT = 8
PER = 20

CATS = [
    ("all", "最新"),
    ("hot", "今日热门"),
    ("43", "真人"),
    ("1", "动画"),
    ("col", "合集"),
]


class Spider(Spider):

    def __init__(self):
        try:
            super().__init__()
        except TypeError:
            pass
        self.sitekey = ""
        self._cache = {}

    def getName(self):
        return "章鱼Play"

    def getDependence(self):
        return ""

    def init(self, extend=""):
        print(">>>>> 章鱼Play.init extend=", extend)
        cfg = {}
        try:
            if extend:
                cfg = json.loads(extend)
        except Exception:
            cfg = {}
        if not isinstance(cfg, dict):
            cfg = {}
        # siteKey 兜底：优先取内核注入的源 key（PyLoader.getSpider 在 init 前写入）
        self.sitekey = str(self.__dict__.get("siteKey", "") or "").strip()
        if not self.sitekey:
            self.sitekey = str(cfg.get("siteKey") or cfg.get("sitekey") or "").strip()
        self._cache = {}
        return None

    def destroy(self):
        return None

    def isVideoFormat(self, url):
        return False

    def isTextFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def playerContent(self, flag, id, vipFlags):
        """FongMi/OK影视 播放链路：由本方法返回最终播放地址与请求头。
        缺了它壳就拿不到播放地址（表现为点播放无反应/提示无地址）。"""
        print(">>>>> 章鱼Play.playerContent flag=%s id=%s" % (flag, str(id)[:100]))
        raw = str(id or "").strip()
        if raw.startswith("播放$") or raw.startswith("章鱼Play$"):
            raw = raw.split("$", 1)[1]
        if not raw.startswith("http"):
            return {"parse": 1, "url": SITE + "/", "header": {}}
        return {
            "parse": 0,
            "url": raw,
            "header": {"User-Agent": UA, "Referer": SITE + "/"},
        }

    # ------------------------------------------------------------- 请求层
    def _http(self, url, timeout=TIMEOUT):
        r = requests.get(url, headers={"User-Agent": UA, "Referer": SITE + "/"}, timeout=timeout)
        return r.text

    def _json(self, url):
        try:
            return json.loads(self._http(url))
        except Exception as e:
            print(">>>>> 章鱼Play _json ERR", url[:80], e)
            return None

    def _dur(self, sec):
        try:
            s = int(sec)
            m, s = divmod(s, 60)
            if m >= 60:
                h, m = divmod(m, 60)
                return "%d:%02d:%02d" % (h, m, s)
            return "%d:%02d" % (m, s)
        except Exception:
            return ""

    # ------------------------------------------------------------- 列表
    def _card(self, v):
        vid = v.get("video_id") or ""
        if not vid:
            return None
        col = v.get("collection") or {}
        rem = self._dur(v.get("duration")) or "HD"
        if col.get("title"):
            rem += " " + (col.get("episode_label") or "")
        return {
            "vod_id": vid,
            "vod_name": v.get("title") or vid,
            "vod_pic": PIC_BASE % vid,
            "vod_remarks": rem,
            "vod_content": (v.get("description") or "") or (col.get("title") or ""),
        }

    def _cards(self, j):
        out = []
        for v in (j.get("data") or {}).get("videos") or []:
            c = self._card(v)
            if c:
                out.append(c)
        return out

    def _pages(self, j):
        d = j.get("data") or {}
        total = d.get("total") or 0
        return max(1, -(-total // PER))

    # ------------------------------------------------------------- 首页
    def homeContent(self, filter):
        print(">>>>> 章鱼Play.homeContent")
        classes = [{"type_id": t, "type_name": n} for t, n in CATS]
        return {"class": classes, "filters": {}}

    def homeVideoContent(self):
        print(">>>>> 章鱼Play.homeVideoContent")
        j = self._json(API + "?sort=views_day&order=desc&per_page=%d&status=ready" % PER)
        return {"list": self._cards(j) if j else []}

    # ------------------------------------------------------------- 分类
    def categoryContent(self, tid, pg, filter, extend):
        print(">>>>> 章鱼Play.categoryContent tid=", tid, "pg=", pg)
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        if tid == "col":
            return self._collections()
        if tid == "all":
            q = "sort=upload"
        elif tid == "hot":
            q = "sort=views_day"
        elif str(tid).isdigit():
            q = "sort=upload&category_id=%s" % tid
        else:
            return {"list": []}
        url = "%s?%s&order=desc&per_page=%d&status=ready&page=%d" % (API, q, PER, pg)
        j = self._json(url)
        if not j:
            return {"list": []}
        return {"page": pg, "pagecount": self._pages(j), "limit": PER,
                "total": (j.get("data") or {}).get("total") or 0, "list": self._cards(j)}

    def _collections(self):
        """合集列表：collections.php 一次全量返回"""
        print(">>>>> 章鱼Play.collections")
        j = self._json(COL_API)
        if not j or not j.get("data"):
            return {"list": []}
        out = []
        for c in j["data"]:
            cid = c.get("id")
            if cid is None:
                continue
            out.append({
                "vod_id": "col_%s" % cid,
                "vod_name": c.get("title") or c.get("slug") or str(cid),
                "vod_pic": c.get("cover_url") or PIC_BASE % "",
                "vod_remarks": "%s集" % c.get("episode_count", 0),
                "vod_content": c.get("description") or "",
            })
        return {"page": 1, "pagecount": 1, "limit": len(out), "total": len(out), "list": out}

    # ------------------------------------------------------------- 详情
    def detailContent(self, ids):
        print(">>>>> 章鱼Play.detailContent ids=", ids)
        if not ids:
            return {"list": []}
        # ids 兼容 list / str 两种入参形态（写源总结 v9：主仓转 list，部分 fork 直传 str）
        if isinstance(ids, (list, tuple)):
            vid = ids[0]
        else:
            vid = str(ids)
        vid = str(vid).strip()
        if vid.startswith("col_"):
            return self._col_detail(vid[4:])
        name = self._title_from_page(vid) or vid
        return {"list": [{
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": PIC_BASE % vid,
            "type_name": "章鱼Play",
            "vod_play_from": "章鱼Play",
            "vod_play_url": "播放$" + PLAY_BASE % vid,
        }]}

    def _title_from_page(self, vid):
        """抓详情页取真实标题，失败返回 None"""
        try:
            t = self._http(SITE + "/" + vid + ".html")
            mt = re.search(r"<title>([^<]*)</title>", t)
            if mt:
                name = _html.unescape(mt.group(1))
                name = re.sub(r"\s*[-|]\s*章鱼Play.*$", "", name).strip()
                if name:
                    return name
        except Exception:
            pass
        return None

    def _col_detail(self, cid):
        print(">>>>> 章鱼Play.col_detail cid=", cid)
        url = "%s?collection_id=%s&sort=upload&order=asc&per_page=100&status=ready" % (API, cid)
        j = self._json(url)
        if not j:
            return {"list": []}
        eps = []
        for v in (j.get("data") or {}).get("videos") or []:
            vid = v.get("video_id")
            if not vid:
                continue
            col = v.get("collection") or {}
            label = col.get("episode_label") or v.get("title") or vid
            order = col.get("episode_order") or 0
            eps.append((order, label, PLAY_BASE % vid))
        eps.sort(key=lambda x: x[0])
        cj = self._json(COL_API)
        cname = None
        if cj and cj.get("data"):
            for c in cj["data"]:
                if str(c.get("id")) == str(cid):
                    cname = c.get("title") or c.get("slug")
                    break
        title = cname or ("合集%s" % cid)
        play = "".join("#%s$%s" % (re.sub(r"[#$]", " ", label), url) for _, label, url in eps)
        return {"list": [{
            "vod_id": "col_%s" % cid,
            "vod_name": title,
            "vod_pic": PIC_BASE % "",
            "type_name": "章鱼Play",
            "vod_play_from": "章鱼Play",
            "vod_play_url": play,
            "vod_content": "共%d集" % len(eps),
        }]}

    # ------------------------------------------------------------- 搜索
    def searchContent(self, key, quick, pg="1"):
        print(">>>>> 章鱼Play.searchContent key=", key)
        try:
            t = self._http(SITE + "/search.html?q=" + str(key))
        except Exception as e:
            print(">>>>> 章鱼Play.search ERR", e)
            return {"list": []}
        pat = re.findall(r'<a class="rec-card"[^>]*href="/([A-Za-z0-9]{8,})\.html"[^>]*title="([^"]*)"', t)
        out = []
        for vid, name in pat:
            out.append({
                "vod_id": vid,
                "vod_name": _html.unescape(name),
                "vod_pic": PIC_BASE % vid,
                "vod_remarks": "HD",
                "vod_content": "",
            })
        return {"list": out}


if __name__ == "__main__":
    s = Spider()
    s.init()
    h = s.homeContent(False)
    print("home classes:", [c["type_name"] for c in h["class"]])
    hv = s.homeVideoContent()
    print("homeVideo n:", len(hv["list"]), hv["list"][0]["vod_name"][:20] if hv["list"] else "NONE")
    c = s.categoryContent("all", 2, False, "")
    print("cat all p2: total=%s n=%s" % (c.get("total"), len(c["list"])))
    c = s.categoryContent("col", 1, False, "")
    print("cat col n:", len(c["list"]))
    d = s.detailContent(["1gsMDzF8LUFO"])
    print("detail:", d["list"][0]["vod_name"][:20], d["list"][0]["vod_play_url"][:60])
    d = s.detailContent(["col_74"])
    print("detail col eps:", len(d["list"][0]["vod_play_url"].split("#")) - 1)
    d2 = s.detailContent("1gsMDzF8LUFO")
    print("detail str ids ok:", d2["list"][0]["vod_id"] == "1gsMDzF8LUFO")
    sc = s.searchContent("古寺", False)
    print("search n:", len(sc["list"]))
