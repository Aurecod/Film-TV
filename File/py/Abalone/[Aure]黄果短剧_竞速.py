#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
黄果短剧 spider（单源双后端竞速版，huangguoai.com 官网）

双后端并行竞速（谁快走谁）：
  API 后端   : /api/videos?sort=new|hot, /api/videos/{id}, /api/videos/{id}/play, /api/search
  页面后端   : 解析 / 首页, /ai-*/{page}/, /tag/{slug}/page/{N}/, /video/{id}/, /search/video/{kw}/

分类以原网站为准（动态 /api/tags，失败用 FALLBACK_GROUPS）：
  latest(最新, API sort=new) / hot(热门, API sort=hot)
  AI成人短剧/AI成人漫剧/AI换脸/AI魔改（页面 data-channel-panel 分区）
  9 个题材分类组（tab 不带 type_flag → 多列；组内标签 folder 卡 vod_tag=folder → 点击进 /tag/{slug}/）
"""

import sys
import os
import re
import json
import time
import queue
import threading
import urllib.request
import urllib.parse
import urllib.error
from urllib.parse import quote, unquote, urlencode
import http.cookiejar
import gzip
import zlib
import ssl
import base64

try:
    from base.spider import Spider as SpiderBase
except ImportError:
    class SpiderBase(object):
        def getCache(self, key):
            return None
        def setCache(self, key, value):
            return "fail"
        def delCache(self, key):
            return "fail"

SITE = "https://huangguoai.com"
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
IMG_KEY = b"f5d965df75336270"
IMG_IV = b"97b60394abc2fbe1"

AI_CHANNELS = [
    ("ai-duanju", "AI成人短剧"),
    ("ai-manju", "AI成人漫剧"),
    ("ai-huanlian", "AI换脸"),
    ("ai-mogai", "AI魔改"),
]

PANELS = [("latest", "最新"), ("hot", "最热"), ("original", "原创"), ("random", "随机")]

FALLBACK_GROUPS = [
    ("djtc", "短剧题材", [
        ("xingzhuan", "性转", 35602),
        ("huangdao", "荒岛", 33422),
        ("xiangcun", "乡村", 25922),
        ("xiaoyuan", "校园", 23762),
        ("dushi", "都市", 20143),
        ("youxi", "游戏", 16059),
        ("gufeng", "古风", 12842),
        ("sangshi", "丧尸", 9451),
        ("xiandai", "现代", 8255),
        ("chaonengli", "超能力", 6554),
        ("danvzhu", "大女主", 5014),
        ("yiyuan", "医院", 4772),
        ("yulequan", "娱乐圈", 4731),
        ("zhichang", "职场", 3976),
        ("fanzui", "犯罪", 3675),
        ("dananzhu", "大男主", 1813),
        ("minguo", "民国", 914),
        ("naodong", "脑洞", 758),
        ("xuanyi", "悬疑", 334),
        ("gongting", "宫廷", 289),
        ("jiefang", "街访", 32),
    ]),
    ("jiakong", "短剧架空", [
        ("xitong", "系统", 31805),
        ("chongsheng", "重生", 27167),
        ("mori", "末日", 22104),
        ("xiuxian", "修仙", 15810),
        ("chuanyue", "穿越", 15083),
        ("xianxia", "仙侠", 4792),
        ("wuxia", "武侠", 3105),
        ("xuanhuan", "玄幻", 1669),
        ("qihuan", "奇幻", 1637),
        ("lingyi", "灵异", 1631),
        ("kehuan", "科幻", 680),
    ]),
    ("nanpin", "短剧男频", [
        ("hougong", "后宫", 14448),
        ("zhuixu", "赘婿", 3692),
        ("nixi", "逆袭", 1756),
        ("quanmou", "权谋", 170),
        ("mengzhai", "萌宅", 48),
    ]),
    ("nvpin", "短剧女频", [
        ("bazong", "霸总", 4083),
        ("haomen", "豪门", 2771),
        ("tianchong", "甜宠", 1233),
        ("nuelian", "虐恋", 667),
    ]),
    ("djll", "短剧伦理", [
        ("luanlun", "乱伦", 54050),
        ("ntr", "ntr", 31063),
        ("lvmao", "绿帽", 29024),
        ("shunv", "熟女", 28201),
        ("sm", "sm", 25290),
        ("gongxi", "公媳", 2143),
        ("nianxia", "年下", 712),
        ("shusao", "叔嫂", 198),
    ]),
    ("gyk", "短剧共用库", [
        ("muzi", "母子", 130637),
        ("nantong", "男同", 33611),
        ("tongxue", "同学", 28993),
        ("mingxing", "明星", 26772),
        ("wanghong", "网红", 21668),
        ("nvtong", "女同", 16975),
        ("funv", "父女", 12299),
        ("jiedi", "姐弟", 10577),
        ("xiongmei", "兄妹", 8665),
        ("zhibo", "直播", 2502),
        ("tongshi", "同事", 1657),
        ("mgdsj", "魔改电视剧", 1269),
        ("mgdy", "魔改电影", 289),
    ]),
    ("appearance", "成人外貌", [
        ("juru", "巨乳", 33281),
        ("renqi", "人妻", 20065),
        ("heisi", "黑丝", 13779),
        ("yanjing", "眼镜", 8915),
        ("baisi", "白丝", 4434),
        ("yujie", "御姐", 3159),
        ("yuzu", "玉足", 2670),
        ("duanfa", "短发", 2321),
        ("qingchun", "清纯", 2257),
        ("baihu", "白虎", 2218),
        ("fengman", "丰满", 1942),
        ("rousi", "肉丝", 1728),
        ("shuangmawei", "双马尾", 1427),
        ("wenshen", "纹身", 1336),
        ("meiru", "美乳", 1307),
        ("pinru", "贫乳", 1013),
        ("meitui", "美腿", 894),
        ("gaoyanzhi", "高颜值", 681),
        ("changtui", "长腿", 540),
        ("jiaoxiao", "娇小", 538),
        ("waiguoren", "外国人", 497),
        ("mawei", "马尾", 323),
        ("youmao", "有毛", 315),
        ("mitaotun", "蜜桃臀", 258),
        ("qiaotun", "翘臀", 237),
        ("lengyan", "冷艳", 217),
        ("hunxue", "混血", 134),
        ("tianmei", "甜美", 123),
        ("luozu", "裸足", 115),
        ("miaotiao", "苗条", 106),
        ("fenxue", "粉穴", 83),
        ("majiaxian", "马甲线", 63),
        ("gaotiao", "高挑", 59),
        ("baixi", "白皙", 37),
        ("changfa", "长发", 26),
        ("xiyao", "细腰", 25),
        ("ziranxiong", "自然胸", 4),
        ("zhongxiong", "中胸", 3),
        ("dayanjing", "大眼睛", 2),
    ]),
    ("play", "成人玩法", [
        ("luoli", "萝莉", 37008),
        ("luchu", "露出", 14201),
        ("huanqi", "换妻", 13486),
        ("zujiao", "足交", 11689),
        ("nuli", "奴隶", 9416),
        ("3p", "3P", 4818),
        ("neishe", "内射", 4294),
        ("shuangfei", "双飞", 4277),
        ("koubao", "口爆", 3746),
        ("koujiao", "口交", 3310),
        ("dapigu", "打屁股", 2836),
        ("qunjiao", "群交", 2697),
        ("zhifu", "制服", 2552),
        ("houru", "后入", 2095),
        ("shenhou", "深喉", 1993),
        ("yanshe", "颜射", 1738),
        ("rujiao", "乳交", 1541),
        ("chaochui", "潮吹", 1458),
        ("qicheng", "骑乘", 1160),
        ("tianyin", "舔阴", 1037),
        ("shewen", "舌吻", 802),
        ("lunlkiu", "轮流", 683),
        ("chezhen", "车震", 626),
        ("mengyan", "蒙眼", 507),
        ("shoujiao", "手交", 272),
        ("juesebanyan", "角色扮演", 188),
        ("tiangang", "舔肛", 157),
        ("tuijiao", "腿交", 119),
        ("taitui", "抬腿", 89),
        ("zhengchangwei", "正常位", 47),
        ("bianyuankongzhi", "边缘控制", 32),
        ("kousai", "口塞", 28),
        ("ceru", "侧入", 28),
        ("tunjiao", "臀交", 28),
        ("zhanlihouru", "站立后入", 26),
        ("waishe", "外射", 7),
        ("luxiangplay", "录像play", 4),
        ("zhongchuhoujixu", "中出后继续", 3),
        ("fuwowei", "俯卧位", 2),
        ("jingziplay", "镜子play", 0),
    ]),
    ("changjing", "成人场景", [
        ("sushe", "宿舍", 25968),
        ("bangonshi", "办公室", 6466),
        ("ktv", "KTV", 3384),
        ("jianshenfang", "健身房", 2885),
        ("jiaoshi", "教室", 1898),
        ("jiuba", "酒吧", 1462),
        ("yewai", "野外", 1447),
        ("jiudian", "酒店", 679),
        ("dianti", "电梯", 432),
        ("minsu", "民宿", 218),
        ("haibian", "海边", 185),
        ("tingchechang", "停车场", 117),
        ("youyongchi", "游泳池", 115),
        ("sheyingpeng", "摄影棚", 110),
        ("xishoujian", "洗手间", 47),
    ]),
]


class Spider(SpiderBase):

    def __init__(self):
        super(Spider, self).__init__()
        self.siteName = "黄果短剧"
        self.siteUrl = SITE
        self.options = {}
        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE
        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj),
            urllib.request.HTTPSHandler(context=self.ctx))
        self._cache = {}
        self._groups_cache = None
        self._groups_ts = 0

    def init(self, extend=""):
        if isinstance(extend, dict):
            self.options = extend
        elif extend:
            try:
                self.options = json.loads(extend)
            except Exception:
                self.options = {}
        return True

    def getName(self):
        return self.siteName

    def isVideoFormat(self, url):
        low = (url or "").lower()
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".mkv", ".ts"))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self.options = {}

    def action(self, action):
        return {"msg": "ok"}

    # ---------------- HTTP ----------------

    def _fetch(self, target_url, referer="", timeout=15):
        if not target_url:
            return {"code": 0, "text": "", "bytes": b"", "err": ""}
        headers = {
            "User-Agent": UA,
            "Referer": referer or (self.siteUrl + "/"),
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        for attempt in range(2):
            try:
                req = urllib.request.Request(target_url, headers=headers)
                with self.opener.open(req, timeout=timeout) as resp:
                    code = resp.getcode()
                    raw = resp.read()
                    enc = getattr(resp, "headers", {}).get("Content-Encoding", "")
                    if raw.startswith(b"\x1f\x8b") or enc == "gzip":
                        raw = gzip.decompress(raw)
                    elif enc == "deflate":
                        try:
                            raw = zlib.decompress(raw)
                        except Exception:
                            raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                    try:
                        text = raw.decode("utf-8")
                    except Exception:
                        text = raw.decode("latin1", errors="ignore")
                    return {"code": code, "text": text, "bytes": raw, "err": ""}
            except urllib.error.HTTPError as e:
                err_raw = b""
                try:
                    err_raw = e.read()
                except Exception:
                    pass
                return {"code": e.code, "text": "", "bytes": err_raw, "err": str(e)}
            except Exception as e:
                if attempt == 0:
                    continue
                return {"code": -1, "text": "", "bytes": b"", "err": str(e)}
        return {"code": -1, "text": "", "bytes": b"", "err": "timeout"}

    def _get_html(self, path, ttl=60):
        url = path if path.startswith("http") else self.siteUrl + path
        if ttl:
            hit = self._cache.get(url)
            if hit and time.time() - hit[1] < ttl:
                return hit[0]
        res = self._fetch(url)
        if not res.get("text"):
            return ""
        if ttl:
            self._cache[url] = (res["text"], time.time())
        return res["text"]

    def _api_get(self, path, params=None):
        url = self.siteUrl + path
        if params:
            url += "?" + urlencode(params)
        res = self._fetch(url)
        text = res.get("text", "")
        if not text:
            return {}
        try:
            d = json.loads(text)
        except Exception:
            return {}
        if isinstance(d, dict) and d.get("data") is not None:
            return d.get("data")
        return d

    # ---------------- 图片代理 ----------------

    def _proxy_pic(self, pic_url):
        p = str(pic_url or "").strip()
        if not p:
            return "https://dummyimage.com/600x800/1e293b/ffffff.png?text=NO_COVER"
        low = p.lower()
        if any(k in low for k in (".m3u8", ".mp4", ".flv", ".mkv", ".ts", "m3u8", "mp4")):
            return "https://dummyimage.com/600x800/1e293b/ffffff.png?text=NO_COVER"
        if p.startswith("//"):
            p = "https:" + p
        elif p.startswith("/"):
            p = self.siteUrl + p
        try:
            proxy = self.getProxyUrl()
        except Exception:
            proxy = ""
        if not proxy:
            return p
        enc = quote(base64.b64encode(p.encode("utf-8")).decode("utf-8"), safe="")
        sep = "&" if "?" in proxy else "?"
        return "%s%surl=%s&type=img" % (proxy, sep, enc)

    def localProxy(self, params):
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except Exception:
                params = {}
        raw_url = unquote(params.get("url", "")).strip()
        if not raw_url:
            return [404, "text/plain; charset=utf-8", "Missing url parameter"]
        ptype = params.get("type", "").strip().lower()
        if ptype == "img":
            try:
                raw_url = base64.b64decode(unquote(raw_url).encode("utf-8")).decode("utf-8")
            except Exception:
                pass
        res = self._fetch(raw_url, referer=self.siteUrl + "/")
        raw_bytes = res.get("bytes", b"")
        if not raw_bytes:
            return [404, "text/plain; charset=utf-8", "Empty image stream"]

        def try_decrypt_aes(data):
            try:
                from Crypto.Cipher import AES
                cipher = AES.new(IMG_KEY, AES.MODE_CBC, IMG_IV)
                dec = cipher.decrypt(data)
                pad = dec[-1]
                if 0 < pad <= 16 and dec[-pad:] == bytes([pad]) * pad:
                    dec = dec[:-pad]
                return dec
            except Exception:
                return None

        def detect_and_return(img_bytes):
            if img_bytes.startswith(b"\xff\xd8"):
                i = img_bytes.rfind(b"\xff\xd9")
                if i >= 0:
                    img_bytes = img_bytes[:i + 2]
                return [200, "image/jpeg", img_bytes]
            if img_bytes.startswith(b"\x89PNG"):
                i = img_bytes.rfind(b"IEND")
                if i >= 0:
                    img_bytes = img_bytes[:i + 8]
                return [200, "image/png", img_bytes]
            if img_bytes.startswith(b"GIF8"):
                return [200, "image/gif", img_bytes]
            if img_bytes.startswith(b"RIFF") and img_bytes[8:12] == b"WEBP":
                return [200, "image/webp", img_bytes]
            return None

        ret = detect_and_return(raw_bytes)
        if ret:
            return ret
        dec = try_decrypt_aes(raw_bytes)
        if dec:
            ret = detect_and_return(dec)
            if ret:
                return ret
        return [res.get("code") or 200, "image/jpeg", raw_bytes]

    # ---------------- 竞速 ----------------

    def _race(self, fns, ok=None, timeout=18):
        ok = ok or (lambda r: bool(r))
        q = queue.Queue()

        def worker(fn):
            try:
                q.put(("ok", fn()))
            except Exception as e:
                q.put(("err", e))

        ts = [threading.Thread(target=worker, args=(fn,), daemon=True) for fn in fns]
        for t in ts:
            t.start()
        last = None
        deadline = time.time() + timeout
        done = 0
        while done < len(ts):
            remain = deadline - time.time()
            if remain <= 0:
                break
            try:
                tag, r = q.get(timeout=remain)
            except queue.Empty:
                break
            done += 1
            if tag == "ok" and not isinstance(r, Exception) and ok(r):
                return r
            if tag == "ok" and not isinstance(r, Exception):
                last = r
        if last is not None:
            return last
        return {"list": []}

    def _ok_list(self, r):
        return isinstance(r, dict) and bool(r.get("list"))

    def _ok_detail(self, r):
        if not isinstance(r, dict) or not r.get("list"):
            return False
        v = r["list"][0]
        return bool(v.get("vod_name")) and bool(v.get("vod_play_url"))

    def _ok_play(self, r):
        return isinstance(r, dict) and bool(r.get("url"))

    # ---------------- 分类（以原网站为准）----------------

    def _groups(self):
        now = time.time()
        if self._groups_cache and now - self._groups_ts < 3600:
            return self._groups_cache
        groups = []
        d = self._api_get("/api/tags")
        cats = d.get("categories") if isinstance(d, dict) else None
        if isinstance(cats, list):
            for c in cats:
                code = str(c.get("code") or "").strip()
                name = str(c.get("name") or "").strip()
                tags = []
                for t in (c.get("tags") or []):
                    slug = str(t.get("slug") or "").strip()
                    tn = str(t.get("name") or "").strip()
                    if slug and tn:
                        tags.append((slug, tn, int(t.get("hot_score") or 0)))
                if code and name and tags:
                    tags.sort(key=lambda x: -x[2])
                    groups.append((code, name, tags))
        if not groups:
            groups = FALLBACK_GROUPS
        self._groups_cache = groups
        self._groups_ts = now
        return groups

    def homeContent(self, filter):
        classes = [
            {"type_id": "latest", "type_name": "最新"},
            {"type_id": "hot", "type_name": "热门"},
        ]
        for c, n in AI_CHANNELS:
            classes.append({"type_id": c, "type_name": n})
        for code, name, _ in self._groups():
            classes.append({"type_id": "grp_" + code, "type_name": name})
        res = {"class": classes}
        if filter:
            ai_ids = {c for c, _ in AI_CHANNELS}
            filters = {}
            for c in classes:
                f = []
                if c["type_id"] in ai_ids:
                    f.append({"key": "panel", "name": "排序",
                              "value": [{"n": n, "v": k} for k, n in PANELS]})
                filters[c["type_id"]] = f
            res["filters"] = filters
        return res

    def _folder_cards(self, code):
        for c, name, tags in self._groups():
            if c != code:
                continue
            items = []
            for slug, tn, score in tags:
                items.append({
                    "vod_id": "f_tag_" + slug,
                    "vod_name": tn,
                    "vod_pic": self.siteUrl + "/static/web/images/cover-placeholder.png?v=20261027005",
                    "vod_remarks": "热度 %d" % score if score else "",
                    "vod_tag": "folder",
                })
            return {"page": 1, "pagecount": 1, "limit": len(items), "total": len(items), "list": items}
        return {"page": 1, "pagecount": 1, "limit": 0, "total": 0, "list": []}

    def homeVideoContent(self):
        return self._race([self._api_home, self._page_home], ok=self._ok_list)

    def categoryContent(self, tid, pg, filter, extend):
        extend = extend or {}
        page = int(pg or 1)
        tid = str(tid).strip()
        panel = (extend.get("panel") or "").strip()

        if tid.startswith("grp_"):
            return self._folder_cards(tid[4:])
        if tid.startswith("f_tag_"):
            return self._page_tag(tid[6:], page)
        if tid in ("latest", "hot"):
            return self._api_sort("new" if tid == "latest" else "hot", page)
        if tid in {c for c, _ in AI_CHANNELS}:
            return self._page_ai(tid, page, panel)
        return self._page_tag(tid, page)

    def searchContent(self, key, quick, pg="1"):
        del quick
        kw = str(key or "").strip()
        if not kw:
            return {"page": 1, "pagecount": 1, "limit": 0, "total": 0, "list": []}
        page = int(pg or 1)
        return self._race([lambda: self._api_search(kw, page),
                           lambda: self._page_search(kw, page)], ok=self._ok_list)

    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        vid = str(raw_id).strip()
        return self._race([lambda: self._api_detail(vid),
                           lambda: self._page_detail(vid)], ok=self._ok_detail)

    def playerContent(self, flag, id, vipFlags):
        del flag, vipFlags
        raw = str(id or "").strip()
        parts = raw.split(":")
        vid = parts[0]
        ep = parts[1] if len(parts) > 1 else "1"
        return self._race([lambda: self._api_play(vid, ep),
                           lambda: self._page_play(vid, ep)], ok=self._ok_play)

    # ---------------- API 后端 ----------------

    def _to_vod(self, it):
        if not it:
            return None
        vid = str(it.get("id") or it.get("video_id") or "").strip()
        if not vid:
            return None
        title = str(it.get("title") or vid).strip()
        raw_pic = str(it.get("cover") or it.get("coverUrl") or "").strip()
        tags = it.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in re.split(r"[,，|/、\s]+", tags) if t.strip()]
        else:
            tags = [str(t).strip() for t in tags if str(t).strip()]
        tag_str = ",".join(tags[:3])
        finished = it.get("is_finished")
        ep = it.get("total_episodes") or it.get("episode_count") or ""
        if finished is True or str(finished) in ("1", "true", "finished"):
            status = "完结"
        elif ep:
            status = "更新至%s集" % ep
        else:
            status = ""
        if tag_str and status:
            remark = "%s | %s" % (tag_str, status)
        else:
            remark = tag_str or status or self.siteName
        vod = {
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": self._proxy_pic(raw_pic),
            "vod_remarks": remark,
        }
        desc = str(it.get("description") or it.get("intro") or "").strip()
        if desc:
            vod["vod_content"] = desc
        return vod

    def _api_sort(self, sort, page):
        d = self._api_get("/api/videos", {"sort": sort, "limit": 20, "page": page})
        items = d.get("items") if isinstance(d, dict) else []
        pag = d.get("pagination") if isinstance(d, dict) else {}
        pages = int(pag.get("pages") or 1) if isinstance(pag, dict) else 1
        v_list = [v for v in (self._to_vod(it) for it in (items or [])) if v]
        return {
            "page": page,
            "pagecount": max(pages, page if len(v_list) >= 20 else page - 1),
            "limit": 20,
            "total": int(pag.get("total") or 9999) if isinstance(pag, dict) else 9999,
            "list": v_list,
        }

    def _api_home(self):
        d = self._api_get("/api/videos", {"sort": "new", "limit": 30, "page": 1})
        items = d.get("items") if isinstance(d, dict) else None
        v_list = []
        seen = set()
        for it in (items or []):
            v = self._to_vod(it)
            if v and v["vod_id"] not in seen:
                seen.add(v["vod_id"])
                v_list.append(v)
        return {"list": v_list[:30]}

    def _api_detail(self, vid):
        d = self._api_get("/api/videos/%s" % vid)
        if not isinstance(d, dict) or d.get("id") is None:
            return {"list": []}
        title = str(d.get("title") or vid).strip()
        raw_pic = str(d.get("cover") or d.get("coverUrl") or "").strip()
        raw_desc = str(d.get("description") or "").strip()
        raw_desc = re.sub(r"<[^>]+>", "", raw_desc).strip()
        tags = d.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in re.split(r"[,，|/、\s]+", tags) if t.strip()]
        else:
            tags = [str(t).strip() for t in tags if str(t).strip()]
        cat = d.get("category")
        if isinstance(cat, dict) and cat.get("name") and cat["name"] not in tags:
            tags = [cat["name"]] + tags
        tag_str = ",".join(tags[:4])
        author = d.get("author")
        actor = str(author.get("name") or "").strip() if isinstance(author, dict) else ""
        eps = d.get("episodes") if isinstance(d.get("episodes"), list) else []
        play_urls = []
        for ep in eps:
            n = str(ep.get("ep_num") or ep.get("sort") or "").strip()
            if not n:
                continue
            t_name = str(ep.get("title") or ("第%s集" % n)).strip()
            t_name = t_name.replace("$", "").replace("#", "")
            play_urls.append("%s$%s:%s" % (t_name, vid, n))
        if not play_urls:
            total_cnt = int(d.get("total_episodes") or d.get("episode_count") or 1)
            for i in range(1, total_cnt + 1):
                play_urls.append("第%s集$%s:%s" % (i, vid, i))
        finished = d.get("is_finished")
        status = "完结" if finished is True or str(finished) in ("1", "true", "finished") else "连载"
        remark = "全%d集" % len(play_urls)
        if tag_str:
            remark = "%s | %s" % (remark, tag_str)
        vod = {
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": self._proxy_pic(raw_pic),
            "vod_actor": actor or "未知",
            "vod_director": "",
            "vod_remarks": remark,
            "vod_content": raw_desc,
            "vod_play_from": "黄果专线",
            "vod_play_url": "#".join(play_urls),
        }
        return {"list": [vod]}

    def _api_play(self, vid, ep):
        d = self._api_get("/api/videos/%s/play" % vid, {"ep": ep})
        video_url = ""
        if isinstance(d, dict):
            video_url = str(d.get("video_url") or "").strip()
        return {"parse": 0, "playUrl": "", "url": video_url,
                "header": {"User-Agent": UA, "Referer": self.siteUrl + "/"}}

    def _api_search(self, kw, page):
        d = self._api_get("/api/search", {"q": kw, "page": page})
        items = d.get("items") if isinstance(d, dict) else []
        pag = d.get("pagination") if isinstance(d, dict) else {}
        v_list = [v for v in (self._to_vod(it) for it in (items or [])) if v]
        pages = int(pag.get("pages") or 1) if isinstance(pag, dict) else 1
        return {"page": page, "pagecount": pages, "limit": len(v_list),
                "total": int(pag.get("total") or len(v_list)) if isinstance(pag, dict) else len(v_list),
                "list": v_list}

    # ---------------- 页面后端 ----------------

    def _page_home(self):
        html = self._get_html("/", ttl=30)
        v_list = self._parse_card_blocks(html)
        seen, out = set(), []
        for v in v_list:
            if v["vod_id"] not in seen:
                seen.add(v["vod_id"])
                out.append(v)
        return {"list": out}

    def _page_ai(self, channel, page, panel):
        panel = panel or "latest"
        path = "/%s/" % channel if page == 1 else "/%s/%d/" % (channel, page)
        html = self._get_html(path, ttl=30)
        seg = self._panel_seg(html, panel)
        v_list = self._parse_card_blocks(seg if seg is not None else html)
        if panel == "latest":
            m = re.search(r'data-pages="(\d+)"', html)
            pages = int(m.group(1)) if m else (page + 1 if len(v_list) >= 20 else page)
        else:
            pages = 1
        return {"page": page, "pagecount": pages, "limit": 20, "total": 9999, "list": v_list}

    def _page_tag(self, slug, page):
        if page == 1:
            path = "/tag/%s/" % slug
        else:
            path = "/tag/%s/page/%d/" % (slug, page)
        html = self._get_html(path, ttl=30)
        v_list = self._parse_tag_page(html)
        m = re.search(r'data-pages="(\d+)"', html)
        pages = int(m.group(1)) if m else (page + 1 if len(v_list) >= 20 else page)
        return {"page": page, "pagecount": pages, "limit": 20, "total": 9999, "list": v_list}

    def _page_detail(self, vid):
        html = self._get_html("/video/%s/" % vid, ttl=0)
        if not html:
            return {"list": []}
        name = self._one(r'<h1[^>]*>([^<]+)</h1>', html) or vid
        hist = self._one(r'data-history="([^"]+)"', html)
        desc, tags, ep_total = "", [], ""
        if hist:
            try:
                h = json.loads(hist.replace("&#34;", '"').replace("&quot;", '"').replace("&amp;", "&"))
                desc = h.get("desc") or ""
                t = h.get("tags") or ""
                tags = [x.strip() for x in re.split(r"[,，]", t) if x.strip()]
                ep_total = h.get("episode") or ""
            except Exception:
                pass
        pic = self._one(r'hg-web-detail__poster.*?data-src="([^"]+)"', html, re.S) \
              or self._one(r'data-src="(https://pic\.drleao\.cn/[^"]+)"', html)
        eps = sorted({int(x) for x in re.findall(r'data-ep-id="(\d+)"', html)})
        if not eps:
            eps = [1]
        play = "#".join("第%d集$%s:%d" % (n, vid, n) for n in eps)
        actor = self._one(r'/author/\d+/">([^<]+)</a>', html)
        remark = ep_total or ("共%d集" % len(eps))
        if tags:
            remark = "%s | %s" % (remark, ",".join(tags[:4]))
        vod = {
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": self._proxy_pic(pic),
            "vod_actor": actor or "未知",
            "vod_director": "",
            "vod_remarks": remark,
            "vod_content": desc,
            "vod_play_from": "黄果短剧",
            "vod_play_url": play,
        }
        return {"list": [vod]}

    def _page_play(self, vid, ep):
        ep = int(ep or 1)
        path = "/video/%s/" % vid if ep <= 1 else "/video/%s/ep-%d/" % (vid, ep)
        html = self._get_html(path, ttl=0)
        url = self._m3u8(html)
        return {"parse": 0, "playUrl": "", "url": url,
                "header": {"User-Agent": UA, "Referer": self.siteUrl + "/"}}

    def _page_search(self, kw, page):
        kwq = quote(str(kw), safe="")
        if page == 1:
            path = "/search/video/%s/" % kwq
        else:
            path = "/search/video/%s/%d/" % (kwq, page)
        html = self._get_html(path, ttl=0)
        v_list = self._parse_tag_page(html)
        m = re.search(r'data-pages="(\d+)"', html)
        pages = int(m.group(1)) if m else (page + 1 if len(v_list) >= 20 else page)
        return {"page": page, "pagecount": pages, "limit": len(v_list),
                "total": pages * 20, "list": v_list}

    # ---------------- HTML 解析 ----------------

    def _parse_tag_page(self, html):
        start = html.find("hg-card-grid")
        if start >= 0:
            end = html.find("hg-pager", start)
            zone = html[start:end if end > start else len(html)]
        else:
            zone = html
        return self._parse_card_blocks(zone)

    def _parse_card_blocks(self, zone):
        out = []
        for block in re.split(r'<div class="hg-drama-card"', zone)[1:]:
            block = block.split('<div class="hg-drama-card"')[0]
            if 'data-track-id' not in block[:200]:
                continue
            m_id = re.search(r'href="/video/(\d+)/"', block)
            if not m_id:
                continue
            vid = m_id.group(1)
            m_title = re.search(r'hg-drama-card__title"><a href="/video/\d+/">([^<]+)<', block)
            title = (m_title.group(1).strip() if m_title else vid)
            m_pic = re.search(r'data-src="([^"]+)"', block)
            pic = m_pic.group(1) if m_pic else ""
            m_desc = re.search(r'hg-drama-card__desc">([^<]*)</p>', block)
            desc = (m_desc.group(1).strip() if m_desc else "")
            tags = re.findall(r'href="/tag/[a-z0-9-]+/">([^<]+)<', block)
            m_ep = re.search(r'data-ep-base="([^"]+)"', block)
            ep = m_ep.group(1).strip() if m_ep else ""
            tag_str = ",".join(tags[:3])
            if tag_str and ep:
                remark = "%s | %s" % (tag_str, ep)
            else:
                remark = tag_str or ep or self.siteName
            vod = {
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": self._proxy_pic(pic),
                "vod_remarks": remark,
            }
            if desc:
                vod["vod_content"] = desc
            out.append(vod)
        return out

    def _panel_seg(self, html, panel):
        starts = [(m.start(), m.group(1) or m.group(2)) for m in re.finditer(
            r'hg-card-grid[^>]*data-channel-panel="(\w+)"|<template data-panel-cards="(\w+)"', html)]
        for i, (pos, key) in enumerate(starts):
            if key != panel:
                continue
            end = starts[i + 1][0] if i + 1 < len(starts) else len(html)
            seg = html[pos:end]
            if "hg-drama-card" in seg:
                return seg
        return None

    def _m3u8(self, html):
        if not html:
            return ""
        for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
            try:
                data = json.loads(m.group(1))
            except Exception:
                continue
            for it in (data.get("@graph") or [data]):
                if not isinstance(it, dict):
                    continue
                if it.get("@type") == "VideoObject":
                    u = str(it.get("contentUrl") or "")
                    if ".m3u8" in u:
                        return self._unesc(u)
        m = re.search(r'data-play-src="([^"]+\.m3u8[^"]*)"', html)
        if m:
            return self._unesc(m.group(1))
        m = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', html)
        return self._unesc(m.group(1)) if m else ""

    def _one(self, pat, html, flags=0):
        m = re.search(pat, html or "", flags)
        return self._unesc(m.group(1)) if m else ""

    def _unesc(self, s):
        s = str(s)
        s = (s.replace("&amp;", "&").replace("&quot;", '"').replace("&#34;", '"')
             .replace("&lt;", "<").replace("&gt;", ">")
             .replace("&#39;", "'").replace("&#x27;", "'").replace("\\u0026", "&"))
        return s
