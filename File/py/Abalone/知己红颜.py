#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import re
import json
import base64
import html as html_lib
import urllib.request
import urllib.parse
from urllib.parse import urlparse, quote, unquote
import http.cookiejar
import gzip
import zlib
import ssl

try:
    from base.spider import Spider as SpiderBase
except ImportError:
    class SpiderBase(object):
        def getCache(self, key): return None
        def setCache(self, key, value): return "fail"
        def delCache(self, key): return "fail"

def _unescape(text):
    s = str(text or "")
    if "&" not in s:
        return s
    s = s.replace("&nbsp;", " ")
    s = s.replace("&quot;", '"').replace("&#39;", "'").replace("&apos;", "'")
    s = s.replace("&lt;", "<").replace("&gt;", ">")
    s = s.replace("&amp;", "&")
    return s

def format_remarks(brand="蝴蝶影视", meta=""):
    clean_meta = re.sub(r"[\r\n\t]+", " ", str(meta or "")).strip()
    return "%s | %s" % (brand, clean_meta) if clean_meta else brand

def clean_label(text):
    t = str(text or "").strip()
    t = re.sub(r"<[^>]+>", " ", t)
    t = _unescape(t)
    t = re.sub(r"[\r\n\t\$#]+", " ", t)
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip()

def clean_pic(url):
    u = str(url or "").strip().replace("\\/", "/")
    if not u or u.startswith("data:"):
        return ""
    low = u.lower()
    for bad in ("lazyload", "loading", "placeholder", "blank.gif", "wechat-tip", "/logo"):
        if bad in low:
            return ""
    return u

def fixed_int(value, default=1):
    try:
        n = int(str(value or default).strip())
    except Exception:
        n = default
    return n if n >= 1 else default

class Spider(SpiderBase):
    def __init__(self):
        super(Spider, self).__init__()
        self.siteName = "X红颜"
        self.siteUrl = "https://xhongyan.com"
        self.tgGroup = "https://t.me/tvshare23"
        self.brandActor = "🦋 TG群: @tvshare23"
        self.brandDirector = "🦋 蝴蝶影视"
        self.stream_exts = (".m3u8", ".mp4", ".flv", ".mkv", ".avi", ".ts", ".mpd")
        self.noise_titles = (
            "上一集", "下一集", "上集", "下集", "上一页", "下一页",
            "影片收藏", "下载视频", "立即播放", "播放", "收藏", "首页"
        )
        self._ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        self.options = {}

        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE

        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj),
            urllib.request.HTTPSHandler(context=self.ctx)
        )

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
        low = str(url or "").lower()
        if not low:
            return False
        if any(bad in low for bad in ("preview.mp4", "sample.mp4", "trailer.mp4", "native-ad", "stat.php")):
            return False
        return any(k in low for k in self.stream_exts)

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self.options = {}

    def _abs(self, url):
        u = str(url or "").strip().replace("\\/", "/")
        if not u:
            return ""
        if u.startswith("//"):
            return "https:" + u
        if not u.startswith("http"):
            return (self.siteUrl + u) if u.startswith("/") else (self.siteUrl + "/" + u)
        return u

    def _fetch(self, target_url, data=None, referer=""):
        if not target_url:
            return {"code": 0, "text": "", "bytes": b"", "err": "", "final_url": ""}
        target_url = self._abs(target_url)

        headers = {
            "User-Agent": self._ua,
            "Referer": referer if referer else (self.siteUrl + "/"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive"
        }

        req_data = None
        if data is not None:
            if isinstance(data, dict):
                req_data = urllib.parse.urlencode(data).encode("utf-8")
                headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
                headers["X-Requested-With"] = "XMLHttpRequest"
            elif isinstance(data, (bytes, str)):
                req_data = data.encode("utf-8") if isinstance(data, str) else data

        for attempt in range(2):
            try:
                req = urllib.request.Request(target_url, data=req_data, headers=headers)
                with self.opener.open(req, timeout=10) as resp:
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
                    return {"code": resp.getcode(), "text": text, "bytes": raw, "err": "", "final_url": resp.geturl()}
            except Exception as e:
                if attempt == 0:
                    continue
                return {"code": -1, "text": "", "bytes": b"", "err": str(e), "final_url": target_url}

        return {"code": -1, "text": "", "bytes": b"", "err": "timeout", "final_url": target_url}

    @staticmethod
    def _slice_json(text, start):
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        return ""

    @staticmethod
    def _cfg_url(url, encrypt):
        u = str(url or "").strip().replace("\\/", "/")
        if not u:
            return ""
        enc = str(encrypt or "0").strip()
        if enc in ("1", "2"):
            try:
                if enc == "2":
                    u = u[::-1]
                pad = len(u) % 4
                if pad:
                    u += "=" * (4 - pad)
                u = base64.b64decode(u).decode("utf-8", "ignore")
            except Exception:
                pass
        return u.strip()

    def _extract_stream_from_html(self, html_text):
        if not html_text:
            return ""
        norm = html_text.replace("\\/", "/").replace("\\u002F", "/").replace("\\u002f", "/")

        for m in re.finditer(r"(player_[a-zA-Z0-9_]+|mac_player)\s*=\s*\{", norm):
            blob = self._slice_json(norm, m.end() - 1)
            if not blob:
                continue
            try:
                cfg = json.loads(blob)
            except Exception:
                continue
            if not isinstance(cfg, dict):
                continue
            cand = self._cfg_url(cfg.get("url") or cfg.get("link") or "", cfg.get("encrypt", "0"))
            if cand and self.isVideoFormat(cand):
                return self._abs(cand)
            if cand and cand.startswith("/"):
                return self._abs(cand)

        m = re.search(r"""["']url["']\s*:\s*["'](\\?/[^"']+\.(?:mp4|m3u8|flv)[^"']*)["']""", norm, re.I)
        if m:
            return self._abs(m.group(1))

        m = re.search(r"""["']url["']\s*:\s*["']([^"']+/upload/[^"']+)["']""", norm, re.I)
        if m:
            return self._abs(m.group(1))

        m = re.search(r"""["'](?:url|video|src|file|play_url)["']\s*:\s*["']((?:https?:)?//[^"']+?\.(?:m3u8|mp4|flv)[^"']*)["']""", norm, re.I)
        if m:
            return self._abs(m.group(1))

        for ext in ("m3u8", "mp4", "flv"):
            m = re.search(r"""((?:https?:)?//[^\s"'<>\\]+?\.%s[^\s"'<>\\]*)""" % ext, norm, re.I)
            if m:
                return self._abs(m.group(1))

        return ""

    def _extract_pic_from_scope(self, scope):
        for attr in ("data-original", "data-src", "data-lazy-src", "data-echo", "src"):
            m = re.search(r"""%s=["']([^"']+)["']""" % attr, scope, re.I)
            if m:
                cand = clean_pic(_unescape(m.group(1)))
                if cand:
                    return self._abs(cand)

        m = re.search(r"""background-image\s*:\s*url\(\s*(?:&quot;|['"])?([^'")&]+)""", scope, re.I)
        if not m:
            m = re.search(r"""background-image\s*:\s*url\(\s*['"]?([^'")]+)""", scope, re.I)
        if m:
            cand = m.group(1).strip()
            cand = cand.replace("&quot;", "").replace('"', '').replace("'", "")
            if "%22" in cand:
                seg = cand.split("%22")
                if len(seg) > 1 and seg[1].strip():
                    cand = seg[1].strip()
            cand = clean_pic(_unescape(cand))
            if cand:
                return self._abs(cand)
        return ""

    def _parse_card_list(self, html_text):
        cards = []
        if not html_text:
            return cards

        seen_ids = set()

        for m in re.finditer(r"""<a\b([^>]*)>([\s\S]*?)</a>""", html_text, re.I):
            attrs = m.group(1) or ""
            inner = m.group(2) or ""
            scope = attrs + " " + inner

            id_m = re.search(r'href=["\'](?:/index\.php)?/vod/play/id/(\d+)/sid/\d+/nid/\d+\.html["\']', scope, re.I)
            if not id_m:
                id_m = re.search(r'/vod/(?:play|detail)/id/(\d+)', scope, re.I)
            if not id_m:
                continue

            vid = id_m.group(1)
            if vid in seen_ids:
                continue

            pic_url = self._extract_pic_from_scope(scope)

            alts = []
            for item in re.findall(r"""alt=["']([^"']*)["']""", scope, re.I):
                t = clean_label(item)
                if t and len(t) >= 2 and t not in self.noise_titles:
                    alts.append(t)

            raw_title = max(alts, key=len) if alts else ""
            if not raw_title:
                title_m = re.search(r'<span[^>]*class=["\'][^"\']*title[^"\']*["\'][^>]*>([\s\S]*?)</span>', scope, re.I)
                if not title_m:
                    title_m = re.search(r'title=["\']([^"\']+)["\']', scope, re.I)
                if title_m:
                    raw_title = clean_label(title_m.group(1))

            if not raw_title:
                continue

            seen_ids.add(vid)

            dur_rem = ""
            dur_m = re.search(r'id=["\']Duration["\'][^>]*>([\s\S]*?)</span>', scope, re.I)
            if dur_m:
                dur_rem = clean_label(dur_m.group(1))
            if not dur_rem:
                dm = re.search(r"(\d{1,3}:\d{2}(?::\d{2})?)", scope)
                if dm:
                    dur_rem = dm.group(1)
            if not dur_rem:
                rem_m = re.search(r'(\d{2}-\d{2})', scope)
                dur_rem = rem_m.group(1) if rem_m else ""

            cards.append({
                "vod_id": vid,
                "vod_name": raw_title,
                "vod_pic": pic_url,
                "vod_remarks": format_remarks("蝴蝶影视", dur_rem),
                "style": {"type": "rect", "ratio": 1.78}
            })

        return cards

    def homeContent(self, filter):
        classes = [
            {"type_id": "new", "type_name": "🔥 最新上架"},
            {"type_id": "cat_4", "type_name": "💃 素人业余"},
            {"type_id": "cat_1", "type_name": "🌟 网红私房"},
            {"type_id": "cat_2", "type_name": "🔞 网黄认证"},
            {"type_id": "cat_3", "type_name": "🎬 品牌专区"},
            {"type_id": "tags", "type_name": "🏷️ 标签大全"}
        ]

        result = {"class": classes}

        if filter:
            all_tags_raw = [
                "后入", "高颜值", "骑乘", "口交", "巨乳", "黑丝", "反差", "少妇", "大屁股", "自慰",
                "情侣", "女大学生", "人妻", "吃鸡", "粉嫩", "御姐", "内射", "假屁股", "白虎", "开裆",
                "美鲍", "清纯", "母狗", "玩具", "足交", "白丝", "白浆", "开苞", "露脸", "深喉",
                "3P", "调教", "群P", "吞精", "潮吹", "熟女", "女优", "高潮", "JK", "偷拍",
                "制服", "女同", "女奴", "幼女", "户外", "无套", "极品", "混血", "直播", "紧致",
                "网袜", "肛交", "自拍", "肥臀", "萝莉", "迷奸", "野战", "金发", "双飞", "嫩妹",
                "学生", "家庭", "强奸", "拘束", "捆绑", "援交", "极品尤物", "水多", "泄密", "漫展",
                "狗趴", "猫娘", "眼镜", "短裙", "空姐", "粗口", "纯情", "绑架", "网吧", "美乳",
                "美腿", "肉丝", "肛塞", "肥美", "自慰流白浆", "舞蹈", "蕾丝", "虐待", "虐恋", "被草",
                "裹胸", "裙底", "西装", "诱惑", "车震", "轮奸", "迷倒", "透视", "针管", "销魂",
                "阴蒂", "隔壁", "露奶", "露点", "青涩", "飞机", "马尾", "高跟", "高跟鞋", "黄播",
                "黑人", "黑皮", "SM", "SWAG", "andmlove", "cosplay", "chinese_bunny", "jk_0571",
                "littlesula", "npxvip", "saku_j", "miulino", "kiki", "Lin", "19cmfuck18girl",
                "Hime_Tsu", "LizyhS", "Miuzxc", "sunwall95", "yui_xin_tw", "Nami-OP", "Suxuuul7",
                "Candlelight", "HongKongDoll", "love_n_s", "RemuKira", "Selen_S", "XJX191",
                "上门", "下面有根棒棒糖", "不穿学姐", "乳交", "乳射", "交友", "代驾", "体型差",
                "体验生", "保洁", "假身", "侦探", "前女友", "包养", "北京小猫", "原神", "双性恋",
                "可爱", "台湾", "叫声小妹", "喷水", "喷射", "外国", "大奶", "女仆", "女教师",
                "女老师", "女神童童", "嫂子", "客房", "宿舍", "密友", "小Q小K", "小可爱", "小姨子",
                "小摇钱树", "小极品", "小猫", "少女", "尤物", "巨臀", "性爱魔盒", "情窦初开", "恋爱",
                "恶魔", "截击", "打拳", "找乐子", "报恩", "护士", "抽插", "按摩", "捷克", "探花",
                "接客", "教师", "撕烂", "新婚", "旅拍", "旅馆", "日韩", "早泄", "明星", "暗访",
                "木下日和", "极品女大", "极品女神", "极品少妇", "极品萝莉", "极品身材", "档案", "模特",
                "母子", "水疗", "求饶", "汗蒸", "沙发", "泰妹", "洋妞", "洗澡", "洛丽塔", "润滑",
                "清纯小妹", "温泉", "浴室", "满足", "潜规则", "激战", "激情", "潮喷", "爆乳", "爱液",
                "父女", "特殊", "狂操", "猛男", "玄关", "玩偶姐姐", "珍珠", "瑜伽", "男模", "痴女",
                "硬汉", "神似", "私拍", "穿刺", "童颜", "精灵", "糖心", "红唇", "约炮", "纽扣",
                "绳艺", "缅甸", "网拍", "美容院", "群交", "考研", "聘请", "胖次", "肉便器", "背德",
                "脱衣", "自曝", "舌吻", "艳母", "艾薇", "花魁", "苗条", "萌妹", "蓝天", "藤森里穗",
                "虐杀", "表妹", "裂帛", "裸聊", "警花", "诱人", "课后", "调情", "豪乳", "轮番",
                "迷醉", "透光", "酷刑", "醉酒", "野外", "金丝雀", "金莲", "钓鱼", "钢琴", "锁精",
                "闺蜜", "阳光", "阴毛", "隐秘", "雨衣", "韩漫", "音乐", "风情", "首尔", "香艳",
                "骚母狗", "魅魔", "麻豆", "黑吊", "黑帮", "黑料"
            ]

            sort_options = [
                {"n": "最新上架", "v": "time"},
                {"n": "人气最高", "v": "hits"}
            ]

            tag_options = []
            seen_t = set()
            for t in all_tags_raw:
                if t and t not in seen_t:
                    seen_t.add(t)
                    tag_options.append({"n": t, "v": t})

            filters_dict = {
                "new": [{"key": "by", "name": "排序", "value": sort_options}],
                "cat_4": [{"key": "by", "name": "排序", "value": sort_options}],
                "cat_1": [{"key": "by", "name": "排序", "value": sort_options}],
                "cat_2": [{"key": "by", "name": "排序", "value": sort_options}],
                "cat_3": [{"key": "by", "name": "排序", "value": sort_options}],
                "tags": [
                    {"key": "tag", "name": "标签", "value": tag_options},
                    {"key": "by", "name": "排序", "value": sort_options}
                ]
            }
            result["filters"] = filters_dict

        return result

    def homeVideoContent(self):
        res = self._fetch("%s/index.php/label/new.html" % self.siteUrl)
        cards = self._parse_card_list(res.get("text", ""))
        if not cards:
            res = self._fetch(self.siteUrl)
            cards = self._parse_card_list(res.get("text", ""))
        return {"list": cards[:24]}

    def categoryContent(self, tid, pg, filter, extend):
        del filter
        page = fixed_int(pg, 1)

        ext = extend or {}
        if isinstance(ext, str) and ext.strip():
            try:
                ext = json.loads(ext)
            except Exception:
                ext = {}

        sort_by = ext.get("by", "")
        sel_tag = ext.get("tag", "")
        tid_str = str(tid).strip()

        if tid_str == "new":
            if page <= 1 and (not sort_by or sort_by == "time"):
                url = "%s/index.php/label/new.html" % self.siteUrl
            else:
                by_val = "hits" if sort_by == "hits" else "time"
                url = "%s/index.php/vod/show/by/%s/id/0.html" % (self.siteUrl, by_val) if page <= 1 else "%s/index.php/vod/show/by/%s/id/0/page/%d.html" % (self.siteUrl, by_val, page)
        elif tid_str.startswith("cat_"):
            cid = tid_str.replace("cat_", "")
            if sort_by in ("time", "hits"):
                url = "%s/index.php/vod/show/by/%s/id/%s.html" % (self.siteUrl, sort_by, cid) if page <= 1 else "%s/index.php/vod/show/by/%s/id/%s/page/%d.html" % (self.siteUrl, sort_by, cid, page)
            else:
                url = "%s/index.php/vod/type/id/%s.html" % (self.siteUrl, cid) if page <= 1 else "%s/index.php/vod/type/id/%s/page/%d.html" % (self.siteUrl, cid, page)
        elif tid_str == "tags":
            target_tag = sel_tag if sel_tag else "后入"
            tag_quoted = quote(target_tag)
            url = "%s/index.php/vod/search/tag/%s.html" % (self.siteUrl, tag_quoted) if page <= 1 else "%s/index.php/vod/search/page/%d/tag/%s.html" % (self.siteUrl, page, tag_quoted)
        else:
            url = "%s/index.php/vod/type/id/%s.html" % (self.siteUrl, tid_str) if page <= 1 else "%s/index.php/vod/type/id/%s/page/%d.html" % (self.siteUrl, tid_str, page)

        res = self._fetch(url)
        cards = self._parse_card_list(res.get("text", ""))

        if not cards and tid_str.startswith("cat_"):
            cid = tid_str.replace("cat_", "")
            alt_url = "%s/index.php/vod/show/id/%s.html" % (self.siteUrl, cid) if page <= 1 else "%s/index.php/vod/show/id/%s/page/%d.html" % (self.siteUrl, cid, page)
            res_alt = self._fetch(alt_url)
            cards = self._parse_card_list(res_alt.get("text", ""))

        total_pages = page + 1 if len(cards) >= 15 else page
        return {
            "page": page,
            "pagecount": total_pages,
            "limit": 20,
            "total": 999 if len(cards) >= 15 else (page * 20),
            "list": cards
        }

    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        vid = str(raw_id).strip()

        play_page_url = "%s/index.php/vod/play/id/%s/sid/1/nid/1.html" % (self.siteUrl, vid)
        res = self._fetch(play_page_url)
        html_text = res.get("text", "")

        main_stream = self._extract_stream_from_html(html_text)

        title_m = re.search(r'<title>(.*?)</title>', html_text, re.I | re.S)
        raw_title = ""
        if title_m:
            raw_title = title_m.group(1).split("-")[0].strip()
        if not raw_title:
            raw_title = "超清正片 %s" % vid

        pic_url = self._extract_pic_from_scope(html_text)

        episodes = []
        if main_stream:
            episodes.append("正片$%s@@@%s" % (main_stream, quote(raw_title)))
        else:
            episodes.append("正片$%s@@@%s" % (play_page_url, quote(raw_title)))

        rec_blocks = re.findall(r'<a[^>]+href=["\'](?:/index\.php)?/vod/play/id/(\d+)/sid/\d+/nid/\d+\.html["\'][^>]*>([\s\S]*?)</a>', html_text, re.I)

        seen_rec = set([vid])
        rec_idx = 1

        for r_id, r_inner in rec_blocks:
            if r_id in seen_rec:
                continue

            t_sub = re.search(r'alt=["\']([^"\']+)["\']', r_inner, re.I)
            rec_title = clean_label(t_sub.group(1)) if t_sub else ""
            if not rec_title:
                t_sub_span = re.search(r'<span[^>]*class=["\'][^"\']*title[^"\']*["\'][^>]*>([\s\S]*?)</span>', r_inner, re.I)
                if t_sub_span:
                    rec_title = clean_label(t_sub_span.group(1))
            if not rec_title:
                rec_title = clean_label(r_inner)
            if not rec_title:
                continue

            seen_rec.add(r_id)

            dur_sub = re.search(r'id=["\']Duration["\'][^>]*>([\s\S]*?)</span>', r_inner, re.I)
            dur_tag = clean_label(dur_sub.group(1)) if dur_sub else ""

            rec_target_url = "%s/index.php/vod/play/id/%s/sid/1/nid/1.html" % (self.siteUrl, r_id)
            if dur_tag:
                label = "%02d·[%s]%s" % (rec_idx, dur_tag, rec_title[:14])
            else:
                label = "%02d·%s" % (rec_idx, rec_title[:18])

            episodes.append("%s$%s@@@%s" % (label, rec_target_url, quote(rec_title)))

            rec_idx += 1
            if rec_idx > 24:
                break

        desc_content = "🦋 蝴蝶影视专线直连 | 极速硬解秒播 | 官方交流群: @tvshare23"

        vod = {
            "vod_id": vid,
            "vod_name": raw_title,
            "vod_pic": pic_url,
            "vod_bg": pic_url,
            "vod_background": pic_url,
            "vod_banner": pic_url,
            "vod_actor": self.brandActor,
            "vod_director": self.brandDirector,
            "vod_remarks": format_remarks("蝴蝶影视", "全%s部连播" % len(episodes)),
            "vod_content": desc_content,
            "vod_play_from": "蝴蝶专线",
            "vod_play_url": "#".join(episodes)
        }
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        del flag, vipFlags
        raw_val = str(id).strip()
        desc_title = ""

        if "@@@" in raw_val:
            target, raw_title = raw_val.split("@@@", 1)
            desc_title = unquote(raw_title)
        else:
            target = raw_val

        real_url = ""
        if self.isVideoFormat(target) or "/upload/vod_file/" in target:
            real_url = self._abs(target)
        else:
            fetch_url = self._abs(target)
            res = self._fetch(fetch_url, referer=fetch_url)
            cand = self._extract_stream_from_html(res.get("text", ""))
            if cand:
                real_url = self._abs(cand)
            else:
                real_url = fetch_url

        is_stream = self.isVideoFormat(real_url) or "/upload/vod_file/" in real_url
        result = {
            "parse": 0 if is_stream else 1,
            "playUrl": "",
            "url": real_url,
            "header": {
                "User-Agent": self._ua,
                "Referer": self.siteUrl + "/",
                "Accept": "*/*",
                "Connection": "keep-alive"
            }
        }
        if desc_title:
            result["desc"] = desc_title

        return result

    def searchContent(self, key, quick, pg="1"):
        del quick
        page = fixed_int(pg, 1)

        search_url = "%s/index.php/vod/search/page/%d/wd/%s.html" % (self.siteUrl, page, quote(key))
        res = self._fetch(search_url)
        html_text = res.get("text", "")

        if not html_text:
            alt_url = "%s/index.php/vod/search.html?wd=%s&page=%d" % (self.siteUrl, quote(key), page)
            res = self._fetch(alt_url)
            html_text = res.get("text", "")

        cards = self._parse_card_list(html_text)
        return {
            "page": page,
            "pagecount": page + 1 if len(cards) >= 15 else page,
            "limit": 20,
            "total": 999 if len(cards) >= 15 else (page * 20),
            "list": cards
        }

    def action(self, action):
        return {"msg": "ok"}

    def liveContent(self):
        return ""

    def localProxy(self, params):
        return [404, "text/plain; charset=utf-8", "Proxy not configured"]