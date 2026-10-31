# -*- coding: utf-8 -*-
try:
    import requests as _rq
except Exception:
    _rq = None
import re
import json
import time
try:
    from urllib import request as _ureq, parse as _uparse
except Exception:
    _ureq = None
    _uparse = None


def _q(s):
    try:
        return _uparse.quote(s)
    except Exception:
        return s


class Spider:
    def __init__(self):
        self.host = "https://ywatomiczenxgridhub.xyz"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            "Referer": self.host + "/",
        }

    def getName(self):
        return "欲望之眼"

    def getDependence(self):
        return []

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        if not url:
            return False
        u = url.lower()
        return u.endswith(".m3u8") or u.endswith(".mp4") or ".m3u8" in u

    def destroy(self):
        pass

    def action(self, action):
        return None

    def localProxy(self, params):
        return [200, "video/mp2t", "", {}]

    def init(self, extend=""):
        pass

    def _get(self, url, referer=None, timeout=15, retries=2):
        hd = dict(self.headers)
        if referer:
            hd["Referer"] = referer
        last = ""
        for _ in range(retries + 1):
            try:
                if _rq is not None:
                    r = _rq.get(url, headers=hd, timeout=timeout)
                    if r.status_code == 200 and r.text:
                        return r.text
                    last = r.text or ""
                elif _ureq is not None:
                    req = _ureq.Request(url, headers=hd)
                    with _ureq.urlopen(req, timeout=timeout) as r:
                        t = r.read().decode("utf-8", "ignore")
                        if t:
                            return t
                        last = t
            except Exception:
                time.sleep(0.5)
        return last

    def _cats(self):
        return [
            ["35", "中文字幕"],
            ["43", "国产视频"],
            ["53", "国产传媒"],
            ["29", "人妖"],
            ["47", "萝莉女孩"],
            ["23", "女同性爱"],            
            ["33", "日本女优"],
            ["55", "三级片"],
            ["39", "欧美视频"],
            ["31", "SM调教"],                                                          
            ["49", "顶级主播"],                     
        ]

    def _filters(self):
        return [
            {
                "key": "orderby",
                "name": "排序",
                "value": [
                    {"n": "最新", "v": "time"},
                    {"n": "最热", "v": "hits"},
                    {"n": "评分", "v": "score"},
                ],
            }
        ]

    def _items(self, html):
        out = []
        seen = set()
        for m in re.finditer(
            r'<a[^>]*class="model-list-item-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>\s*<div[^>]*class="model-list-item-lower"[^>]*>(.*?)</div>',
            html,
            re.S,
        ):
            try:
                href, upper, lower = m.group(1), m.group(2), m.group(3)
                if "/vod/play/id/" not in href:
                    continue
                url = href if href.startswith("http") else self.host + href
                if url in seen:
                    continue
                seen.add(url)
                img = re.search(r'<img[^>]*src="([^"]+)"', upper)
                pic = img.group(1) if img else ""
                dur = re.search(r'ModelListItemBadge[^"]*"\s*>\s*([^<]+)<', upper)
                remark = dur.group(1).strip() if dur else ""
                title = re.sub(r"<[^>]+>", "", lower).strip()
                if not title:
                    continue
                out.append(
                    {
                        "vod_id": url,
                        "vod_name": title,
                        "vod_pic": pic,
                        "vod_remarks": remark,
                    }
                )
            except Exception:
                continue
        return out

    def _pagecount(self, html, pg):
        pages = re.findall(r"/page/(\d+)\.html", html)
        if pages:
            try:
                return max(int(p) for p in pages)
            except Exception:
                pass
        return pg + 1

    def homeContent(self, filter=None):
        classes = [{"type_id": t, "type_name": n} for t, n in self._cats()]
        return {
            "class": classes,
            "filters": {t: self._filters() for t, _ in self._cats()},
            "list": [],
        }

    def homeVideoContent(self):
        html = self._get(self.host + "/")
        return {"list": self._items(html)}

    def _cat_url(self, tid, pg, orderby):
        pg = int(pg)
        base = self.host + "/index.php/vod/type/id/%s" % tid
        by = ("/by/%s" % orderby) if orderby and orderby != "time" else ""
        if pg <= 1:
            return base + by + ".html"
        return base + by + "/page/%d.html" % pg

    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        orderby = "time"
        try:
            ex = extend or {}
            if isinstance(ex, str):
                try:
                    ex = json.loads(ex)
                except Exception:
                    ex = {}
            v = ex.get("orderby")
            if isinstance(v, str) and v:
                orderby = v
        except Exception:
            pass
        html = self._get(self._cat_url(tid, pg, orderby), referer=self.host + "/")
        return {
            "list": self._items(html),
            "page": int(pg),
            "pagecount": self._pagecount(html, int(pg)),
            "limit": 48,
            "total": 999999,
        }

    def _player_info(self, play_url):
        html = self._get(play_url, referer=self.host + "/")
        info = {"name": "", "vclass": "", "m3u8": "", "pic": ""}
        if not html:
            return info
        m = re.search(r"var player_aaaa=\{(.*?)\};?\s*</script>", html, re.S)
        if m:
            try:
                d = json.loads("{" + m.group(1) + "}")
                vd = d.get("vod_data", {}) or {}
                info["name"] = vd.get("vod_name", "") or ""
                info["vclass"] = vd.get("vod_class", "") or ""
                info["m3u8"] = (d.get("url", "") or "").strip()
                if info["m3u8"]:
                    dpath = info["m3u8"].split("://", 1)[-1].split("/", 1)[-1].rsplit("/", 1)[0]
                    for im in re.finditer(r'<img[^>]*src="([^"]+)"', html):
                        src = im.group(1)
                        if dpath and dpath in src:
                            info["pic"] = src
                            break
            except Exception:
                pass
        return info

    def detailContent(self, ids):
        try:
            play_url = ids[0] if isinstance(ids, list) else ids
        except Exception:
            play_url = ""
        info = self._player_info(play_url) if play_url else {"name": "", "vclass": "", "m3u8": "", "pic": ""}
        vod = {
            "vod_id": play_url,
            "vod_name": info["name"] or "视频",
            "vod_pic": info["pic"],
            "type_name": info["vclass"],
            "vod_play_from": "欲望之眼",
            "vod_play_url": "第01集$" + play_url,
        }
        return {"list": [vod]}

    def searchContent(self, key, quick=False, pg="1"):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        url = self.host + "/index.php/vod/search/page/%d/wd/%s.html" % (pg, _q(key))
        html = self._get(url, referer=self.host + "/")
        return {
            "list": self._items(html),
            "page": pg,
            "pagecount": self._pagecount(html, pg),
            "limit": 48,
            "total": 999999,
        }

    def playerContent(self, flag, ids, vipFlags=None):
        try:
            play_url = ids[0] if isinstance(ids, list) else ids
        except Exception:
            play_url = ""
        if "$" in str(play_url):
            play_url = str(play_url).split("$")[-1]
        info = self._player_info(play_url) if play_url else {"m3u8": ""}
        url = info.get("m3u8", "")
        if url:
            return {
                "parse": 0,
                "url": url,
                "header": self.headers,
            }
        return {"parse": 1, "url": play_url, "header": self.headers}
