# -*- coding: utf-8 -*-
# 目标网站：https://www.ebonygalore.com/zh/
# 模板类型：自建中文聚合视频站
# 解析手法：lxml HTML 解析 + 预编译正则 + base64 外链还原
# 技术难点：Cloudflare 页面抓取、EPORNER 双源 fallback、分类/排序分页映射、播放 hash 生成
# 炼制方式：requests + lxml + re + json + base64
# 四元方悔血炼池 · 丙午年仲秋

import base64
import html
import json
import re
import time
from urllib.parse import parse_qs, quote, urljoin, urlsplit

import requests

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    # 本地验证环境没有 TVBox base 包；客户端内仍继承官方基类。
    class BaseSpider:
        pass


class Spider(BaseSpider):
    HOST = "https://www.ebonygalore.com"
    EPORNER_HOST = "https://www.eporner.com"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
    )
    searchable = True
    filterable = True

    CATEGORIES = [
        ("all", "全部"),
        ("ebony", "黑人"),
        ("japanese", "日本"),
        ("chinese", "中国"),
        ("anal", "肛交"),
        ("interracial", "跨种族"),
        ("homemade", "自制"),
        ("threesome", "三人行"),
        ("ebony-big-ass", "黑人大臀"),
        ("oriental", "东方"),
        ("uncensored", "无码"),
        ("ai-generated", "AI 生成"),
        ("4k-porn", "4K"),
        ("teens", "少女"),
        ("pov-porn", "主观视角"),
        ("lesbians", "女同"),
        ("asian", "亚洲"),
        ("redhead", "红发"),
        ("vr-porn", "VR"),
        ("mature", "熟女"),
        ("big-tits", "巨乳"),
        ("milf", "MILF"),
        ("hardcore", "硬核"),
        ("group-sex", "群交"),
        ("amateur", "业余"),
        ("orgy", "乱交"),
        ("gay", "男同"),
        ("swingers", "换偶"),
        ("latina", "拉丁"),
        ("footjob", "足交"),
        ("indian", "印度"),
        ("big-dick", "大屌"),
        ("hentai", "动漫"),
        ("shemale", "变性"),
        ("60fps", "60帧"),
        ("ai", "AI"),
        ("asmr", "ASMR"),
        ("bbw", "BBW"),
        ("bdsm", "BDSM"),
        ("big-ass", "大臀"),
        ("bisexual", "双性"),
        ("blonde", "金发"),
        ("blowjob", "口交"),
        ("bondage", "束缚"),
        ("brunette", "棕发"),
        ("bukkake", "颜射"),
        ("casting", "试镜"),
        ("compilation", "合集"),
        ("cosplay", "角色扮演"),
        ("creampie", "内射"),
        ("cuckold", "绿帽"),
        ("cumshot", "射精"),
        ("double-penetration", "双插"),
        ("fat", "肥女"),
        ("fetish", "恋物"),
        ("fisting", "拳交"),
        ("for-women", "女性向"),
        ("gloryhole", "欢洞"),
        ("handjob", "手交"),
        ("hd-1080p", "1080P"),
        ("hd-sex", "高清性爱"),
        ("hotel", "酒店"),
        ("hotwife", "人妻"),
        ("housewives", "主妇"),
        ("hq-porn", "高清"),
        ("indonesia", "印尼"),
        ("lingerie", "内衣"),
        ("massage", "按摩"),
        ("masturbation", "自慰"),
        ("nurse", "护士"),
        ("office", "办公室"),
        ("old-man", "老汉"),
        ("outdoor", "户外"),
        ("pawg", "PAWG"),
        ("petite", "娇小"),
        ("pinay", "菲律宾"),
        ("pornstar", "成人明星"),
        ("pregnant", "孕妇"),
        ("public", "公共"),
        ("small-tits", "贫乳"),
        ("squirt", "潮吹"),
        ("stepmom", "继母"),
        ("stepsister", "继姐"),
        ("striptease", "脱衣舞"),
        ("students", "学生"),
        ("toys", "玩具"),
        ("uncategorized", "未分类"),
        ("uniform", "制服"),
        ("vintage", "复古"),
        ("webcam", "摄像头"),
        ("sleep", "睡眠"),
        ("doctor", "医生"),
    ]

    EPORNER_SORTS = [
        ("latest", "最新"),
        ("top-weekly", "本周最热"),
        ("top-monthly", "本月最热"),
        ("most-viewed", "最多观看"),
        ("top-rated", "最高评分"),
        ("longest", "最长时长"),
        ("shortest", "最短时长"),
    ]

    _CARD_XPATH = (
        "//*[contains(concat(' ', normalize-space(@class), ' '), ' card ') and "
        "contains(concat(' ', normalize-space(@class), ' '), ' sub ')]"
    )
    _ITEM_LINK_XPATH = (
        ".//a[contains(concat(' ', normalize-space(@class), ' '), ' item-link ')]"
    )
    _PIC_XPATH = (
        ".//img[contains(concat(' ', normalize-space(@class), ' '), ' item-image ')]"
    )
    _SCORE_XPATH = (
        ".//*[contains(concat(' ', normalize-space(@class), ' '), ' item-score ')]"
    )
    _BADGE_XPATH = (
        ".//*[contains(concat(' ', normalize-space(@class), ' '), ' badge ')]"
    )
    _SOURCE_XPATH = (
        ".//*[contains(concat(' ', normalize-space(@class), ' '), ' "
        "item-source-rating-container ')]"
    )
    _EP_CARD_XPATH = (
        "//div[contains(concat(' ', normalize-space(@class), ' '), ' mb ')]"
        "[.//a[contains(@href, '/video-')]]"
    )
    _EP_TOTAL_RE = re.compile(r"We have ([0-9,]+) videos", re.I)
    _EP_VID_IN_HREF_RE = re.compile(r"/video-([A-Za-z0-9_-]+)/")

    _URL_INSIDE_B64 = re.compile(r"https?://[^\x00-\x20\x7f]+")
    _EP_HASH_RE = re.compile(
        r"""EP\.video\.player\.hash\s*=\s*['"]([0-9a-fA-F]{32})['"]"""
    )
    _EP_VID_RE = re.compile(
        r"""EP\.video\.player\.vid\s*=\s*['"]([A-Za-z0-9_-]+)['"]"""
    )
    _EP_POSTER_RE = re.compile(
        r"""EP\.video\.player\.poster\s*=\s*['"]([^'"]+)['"]"""
    )
    _TITLE_RE = re.compile(r"<title[^>]*>([\s\S]*?)</title>", re.I)
    _OG_IMAGE_RE = re.compile(
        r"""<meta[^>]+property=["']og:image["'][^>]+content=["']([^"']+)["']""",
        re.I,
    )
    _DIRECT_ATTR_RE = re.compile(
        r"""<(?:video|source)[^>]+src=["']([^"']+\.(?:mp4|m3u8)[^"']*)["']""",
        re.I,
    )
    _PAGE_ATTR_RE = re.compile(r"[?&]page=(\d+)")
    _EP_PAGE_PATH_RE = re.compile(r"/(?:cat|tag)/[^/]+/([0-9]+)(?:/|$)")

    def __init__(self):
        self.extend = ""
        self.session = None
        self._host_failed = False

    def init(self, extend=""):
        self.extend = str(extend or "").rstrip("/")
        self._host_failed = False
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Referer": self.HOST + "/zh/",
                "User-Agent": self.USER_AGENT,
            }
        )

    def destroy(self):
        if self.session is not None:
            try:
                self.session.close()
            except Exception:
                pass

    def getName(self):
        return "EbonyGalore"

    @staticmethod
    def _clean_text(value):
        if not value:
            return ""
        return html.unescape(" ".join(str(value).split()))

    @staticmethod
    def _base36(value):
        chars = "0123456789abcdefghijklmnopqrstuvwxyz"
        if value <= 0:
            return "0"
        result = ""
        while value:
            value, rem = divmod(value, 36)
            result = chars[rem] + result
        return result

    @staticmethod
    def _encode_eporner_hash(hash_hex):
        """EPORNER 将 32 位 hex 按 8 位分段并转为 base36 字符串。"""
        if not hash_hex or len(hash_hex) != 32:
            return ""
        return "".join(
            Spider._base36(int(hash_hex[i:i + 8], 16)) for i in range(0, 32, 8)
        )

    def _get(self, url, headers=None, referer=None):
        last_error = None
        for _ in range(2):
            try:
                request_headers = dict(headers or {})
                if referer:
                    request_headers["Referer"] = referer
                response = self.session.get(url, headers=request_headers, timeout=(10, 20))
                response.raise_for_status()
                response.encoding = response.apparent_encoding or "utf-8"
                return response.text
            except Exception as error:
                last_error = error
        return ""

    def _get_json(self, url, params=None, headers=None, referer=None):
        last_error = None
        for _ in range(2):
            try:
                request_headers = dict(headers or {})
                if referer:
                    request_headers["Referer"] = referer
                response = self.session.get(
                    url, params=params, headers=request_headers, timeout=(10, 20)
                )
                response.raise_for_status()
                return response.json()
            except Exception as error:
                last_error = error
        return None

    def _decode_out_url(self, value):
        if not value:
            return ""
        parsed = urlsplit(value)
        params = parse_qs(parsed.query, keep_blank_values=True)
        payload = (params.get("l") or [None])[0]
        if payload:
            try:
                padded = payload + "=" * (-len(payload) % 4)
                decoded = base64.b64decode(padded)
                text = decoded.decode("latin-1", "replace")
            except Exception:
                text = ""
            match = self._URL_INSIDE_B64.search(text)
            if match:
                return match.group(0)
        return value

    def _make_vod_id(self, link):
        target = self._decode_out_url(link)
        if not target:
            return "raw:" + base64.urlsafe_b64encode(link.encode("utf-8")).decode("ascii")
        try:
            parsed = urlsplit(target)
        except Exception:
            parsed = None
        if parsed and "eporner.com" in parsed.netloc.lower():
            video_match = re.search(r"/video-([A-Za-z0-9_-]+)", parsed.path or "")
            if video_match:
                return "eporner:" + video_match.group(1)
        encoded = base64.urlsafe_b64encode(target.encode("utf-8")).decode("ascii")
        return "out:" + encoded

    def _decode_vod_target(self, vod_id):
        if vod_id.startswith("out:"):
            try:
                return base64.urlsafe_b64decode(vod_id[4:].encode("ascii")).decode(
                    "utf-8", "replace"
                )
            except Exception:
                return ""
        if vod_id.startswith("url:"):
            try:
                return base64.urlsafe_b64decode(vod_id[4:].encode("ascii")).decode(
                    "utf-8", "replace"
                )
            except Exception:
                return ""
        return vod_id

    def _parse_pagecount(self, text, page):
        if not text:
            return max(1, int(page or 1))
        try:
            from lxml.html import fromstring

            root = fromstring(text)
            hrefs = root.xpath("//a[contains(@href, 'page=')]/@href")
            numbers = []
            for href in hrefs:
                numbers.extend(int(value) for value in self._PAGE_ATTR_RE.findall(str(href)))
        except Exception:
            numbers = []
        if numbers:
            pagecount = max(numbers)
        else:
            pagecount = max(1, int(page or 1))
        try:
            current = max(1, int(page))
        except Exception:
            current = 1
        return max(pagecount, current)

    def _parse_list_html(self, text):
        if not text:
            return []
        from lxml.html import fromstring

        try:
            root = fromstring(text)
        except Exception:
            return []

        items = []
        for card in root.xpath(self._CARD_XPATH):
            link_nodes = card.xpath(self._ITEM_LINK_XPATH)
            if not link_nodes:
                continue
            link = link_nodes[0]
            img_nodes = card.xpath(self._PIC_XPATH)
            img = img_nodes[0] if img_nodes else None

            name = (
                link.get("title")
                or (img.get("alt") if img is not None else None)
                or card.get("data-title")
                or ""
            )
            name = self._clean_text(name)
            pic = img.get("src") if img is not None else ""
            pic = urljoin(self.HOST, pic)
            href = link.get("href") or ""

            score_nodes = card.xpath(self._SCORE_XPATH)
            score = self._clean_text(score_nodes[0].text_content()) if score_nodes else ""
            badges = [
                self._clean_text(node.text_content())
                for node in card.xpath(self._BADGE_XPATH)
                if self._clean_text(node.text_content())
            ]
            source_nodes = card.xpath(self._SOURCE_XPATH)
            source = (
                self._clean_text(source_nodes[0].text_content()) if source_nodes else ""
            )

            remarks = " | ".join(part for part in (score, source, " ".join(badges)) if part)
            vod_id = self._make_vod_id(href)
            items.append(
                {
                    "vod_id": vod_id,
                    "vod_name": name,
                    "vod_pic": pic,
                    "vod_remarks": remarks[:120],
                }
            )
        return items

    def _parse_eporner_list_html(self, text):
        if not text:
            return []
        from lxml.html import fromstring

        try:
            root = fromstring(text)
        except Exception:
            return []

        items = []
        for card in root.xpath(self._EP_CARD_XPATH):
            link_nodes = card.xpath(".//a[contains(@href, '/video-')]")
            link = link_nodes[0] if link_nodes else None
            if link is None:
                continue
            img_nodes = card.xpath(".//img[(@data-src or @src)]")
            img = img_nodes[0] if img_nodes else None
            title = self._clean_text("".join(link.itertext()))
            if not title and img is not None:
                title = self._clean_text(img.get("alt") or "")
            pic = ""
            if img is not None:
                pic = (img.get("data-src") or img.get("src") or "").strip()
            href = (link.get("href") or "").strip()
            vid_match = self._EP_VID_IN_HREF_RE.search(href)
            vid = vid_match.group(1) if vid_match else ""
            if not vid:
                continue

            def text_of(xpath):
                nodes = card.xpath(xpath)
                return "".join(chunk for node in nodes for chunk in node.itertext()).strip()

            duration = text_of(
                ".//*[contains(concat(' ', normalize-space(@class), ' '), ' mbtim ')]"
            )
            rating = text_of(
                ".//*[contains(concat(' ', normalize-space(@class), ' '), ' mbrate ')]"
            )
            views = text_of(
                ".//*[contains(concat(' ', normalize-space(@class), ' '), ' mbvie ')]"
            )
            remarks = " | ".join(part for part in (duration, rating, views) if part)
            items.append(
                {
                    "vod_id": "eporner:" + vid,
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_remarks": remarks[:120],
                }
            )
        return items

    def _get_eporner_pagecount(self, text, per_page, current_page):
        total_match = self._EP_TOTAL_RE.search(text or "")
        try:
            total = int(total_match.group(1).replace(",", "")) if total_match else 0
        except Exception:
            total = 0
        if total and per_page:
            return max(1, (total + per_page - 1) // per_page)
        pagecount = self._parse_pagecount(text, current_page)
        try:
            current = max(1, int(current_page))
        except Exception:
            current = 1
        path_numbers = [int(value) for value in self._EP_PAGE_PATH_RE.findall(text or "")]
        if path_numbers:
            return max(pagecount, max(path_numbers), current)
        return max(pagecount, current)

    @staticmethod
    def _options_dict(filter, extend):
        options = extend if isinstance(extend, dict) else filter
        if isinstance(options, str):
            try:
                options = json.loads(options)
            except Exception:
                options = {}
        return options if isinstance(options, dict) else {}

    def _normalize_eporner_sort(self, value):
        text = str(value or "").strip().lower()
        if text in ("", "latest", "default", "new", "newest", "最新"):
            return ""
        for slug, name in self.EPORNER_SORTS:
            if text in (slug, name.lower(), name):
                return slug
        return ""

    def homeContent(self, filter):
        class_list = [
            {"type_id": slug, "type_name": name} for slug, name in self.CATEGORIES
        ]
        sort_filter = {
            "key": "sort",
            "name": "排序",
            "value": [{"v": slug, "n": name} for slug, name in self.EPORNER_SORTS],
        }
        filters = {item["type_id"]: [sort_filter] for item in class_list}
        return {"class": class_list, "list": [], "filters": filters}

    def homeVideoContent(self):
        text = ""
        if not self._host_failed:
            text = self._get(self.HOST + "/zh/")
        list_items = self._parse_list_html(text)
        if not list_items:
            if not text:
                self._host_failed = True
            text = self._get(self.EPORNER_HOST + "/", referer=self.EPORNER_HOST + "/")
            list_items = self._parse_eporner_list_html(text)
        return {"list": list_items}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = max(1, int(pg))
        except Exception:
            page = 1
        slug = str(tid or "")
        for index, (item_slug, _) in enumerate(self.CATEGORIES, start=1):
            if slug == str(index):
                slug = item_slug
                break
        if not slug:
            slug = "ebony"
        options = self._options_dict(filter, extend)
        sort_slug = self._normalize_eporner_sort(options.get("sort", ""))
        host_text = ""
        if not self._host_failed:
            try:
                url = f"{self.HOST}/zh/category/{slug}"
                if page > 1:
                    url += f"?page={page}"
                host_text = self._get(url)
            except Exception:
                host_text = ""
            if not host_text:
                self._host_failed = True
        list_items = self._parse_list_html(host_text)
        if list_items:
            return {
                "page": page,
                "pagecount": self._parse_pagecount(host_text, page),
                "limit": len(list_items) or 20,
                "total": 0,
                "list": list_items,
            }
        if sort_slug:
            if page > 1:
                ep_url = f"{self.EPORNER_HOST}/tag/{slug}/{page}/{sort_slug}/"
            else:
                ep_url = f"{self.EPORNER_HOST}/tag/{slug}/{sort_slug}/"
        else:
            ep_url = f"{self.EPORNER_HOST}/cat/{slug}/"
            if page > 1:
                ep_url += f"{page}/"
        ep_text = self._get(ep_url, referer=self.EPORNER_HOST + "/")
        ep_items = self._parse_eporner_list_html(ep_text)
        per_page = len(ep_items) or 125
        return {
            "page": page,
            "pagecount": self._get_eporner_pagecount(ep_text, per_page, page),
            "limit": per_page,
            "total": 0,
            "list": ep_items,
        }

    def searchContent(self, key, quick, pg="1"):
        try:
            page = max(1, int(pg))
        except Exception:
            page = 1
        text = ""
        if not self._host_failed:
            try:
                response = self.session.post(
                    self.HOST + "/zh/searching/by-form",
                    data={"search_query[query]": key},
                    allow_redirects=True,
                    timeout=(10, 20),
                )
                response.raise_for_status()
                response.encoding = response.apparent_encoding or "utf-8"
                text = response.text
            except Exception:
                text = ""
            if not text:
                self._host_failed = True
        list_items = self._parse_list_html(text)
        if not list_items:
            ep_url = f"{self.EPORNER_HOST}/search/{quote(str(key), safe='')}/"
            ep_text = self._get(ep_url, referer=self.EPORNER_HOST + "/")
            list_items = self._parse_eporner_list_html(ep_text)
        return {"list": list_items, "page": page}

    def detailContent(self, ids):
        vod_id = (ids or [""])[0]
        try:
            detail = self._build_detail(vod_id)
        except Exception:
            detail = None
        return {"list": [detail] if detail else []}

    def _build_detail(self, vod_id):
        if vod_id.startswith("eporner:"):
            vid = vod_id.split(":", 2)[1]
            return self._eporner_detail(vid)
        target = self._decode_vod_target(vod_id)
        if target:
            return self._generic_detail(target, vod_id)
        return None

    def _eporner_detail(self, vid):
        page_url = f"{self.EPORNER_HOST}/video-{vid}/"
        text = self._get(page_url, referer=self.EPORNER_HOST + "/")
        title = "EbonyGalore"
        poster = ""
        hash_hex = ""
        actual_vid = vid

        title_match = self._TITLE_RE.search(text)
        if title_match:
            title = self._clean_text(title_match.group(1))
            title = re.sub(r"\s*-\s*EPORNER\s*$", "", title, flags=re.I)

        poster_match = self._EP_POSTER_RE.search(text)
        if poster_match:
            poster = poster_match.group(1)
        if not poster:
            image_match = self._OG_IMAGE_RE.search(text)
            if image_match:
                poster = image_match.group(1)

        vid_match = self._EP_VID_RE.search(text)
        if vid_match:
            actual_vid = vid_match.group(1)
        hash_match = self._EP_HASH_RE.search(text)
        if hash_match:
            hash_hex = hash_match.group(1)

        play_url = ""
        if hash_hex:
            play_id = f"eporner:{actual_vid}:{hash_hex}"
            play_url = f"正片${play_id}"

        detail = {
            "vod_id": "eporner:" + actual_vid,
            "vod_name": title,
            "vod_pic": poster,
            "vod_play_from": "Eporner",
            "vod_play_url": play_url,
        }
        if not hash_hex:
            detail["vod_remarks"] = "播放参数获取失败"
        return detail

    def _generic_detail(self, target, vod_id):
        text = self._get(target, referer=self.HOST + "/zh/")
        title_match = self._TITLE_RE.search(text)
        title = self._clean_text(title_match.group(1)) if title_match else "外部视频"
        image_match = self._OG_IMAGE_RE.search(text)
        poster = image_match.group(1) if image_match else ""

        media_url = self._extract_direct_media(text)
        play_url = ""
        play_from = ""
        if media_url:
            encoded = base64.urlsafe_b64encode(media_url.encode("utf-8")).decode("ascii")
            play_url = f"正片$url:{encoded}"
            play_from = "直链"

        return {
            "vod_id": vod_id,
            "vod_name": title,
            "vod_pic": poster,
            "vod_play_from": play_from,
            "vod_play_url": play_url,
        }

    def _extract_direct_media(self, text):
        candidates = []
        for script in re.findall(
            r"""<script[^>]+type=["']application/ld\+json["'][^>]*>([\s\S]*?)</script>""",
            text,
            re.I,
        ):
            try:
                data = json.loads(script)
            except Exception:
                continue
            stack = [data]
            while stack:
                node = stack.pop()
                if isinstance(node, dict):
                    for value in node.values():
                        stack.append(value)
                elif isinstance(node, list):
                    stack.extend(node)
                elif isinstance(node, str):
                    if re.search(r"\.(?:mp4|m3u8)(?:\?|$)", node, re.I):
                        candidates.append(node)
        for match in self._DIRECT_ATTR_RE.findall(text):
            candidates.append(html.unescape(match))
        for candidate in candidates:
            if candidate.startswith("//"):
                candidate = "https:" + candidate
            elif candidate.startswith("/"):
                continue
            if candidate.startswith("http"):
                return candidate
        return ""

    def playerContent(self, flag, id, vipFlags):
        if id.startswith("eporner:"):
            return self._eporner_player(id)
        target = self._decode_vod_target(id)
        if target:
            return {
                "parse": 0,
                "url": target,
                "header": json.dumps(
                    {
                        "User-Agent": self.USER_AGENT,
                        "Referer": self.HOST + "/zh/",
                    }
                ),
            }
        return {"parse": 0, "url": id, "header": json.dumps({"User-Agent": self.USER_AGENT})}

    def _eporner_player(self, play_id):
        parts = play_id.split(":", 2)
        if len(parts) != 3:
            return {"parse": 0, "url": "", "header": "{}"}
        vid, hash_hex = parts[1], parts[2]
        hash_token = self._encode_eporner_hash(hash_hex)
        if not hash_token:
            return {"parse": 0, "url": "", "header": "{}"}

        api_url = f"{self.EPORNER_HOST}/xhr/video/{vid}"
        params = {
            "hash": hash_token,
            "domain": "www.eporner.com",
            "pixelRatio": "1",
            "playerWidth": "0",
            "playerHeight": "0",
            "fallback": "false",
            "embed": "true",
            "supportedFormats": "mp4",
            "_": str(int(time.time() * 1000)),
        }
        referer = f"{self.EPORNER_HOST}/video-{vid}/"
        data = self._get_json(api_url, params=params, referer=referer)
        media_url = ""
        if isinstance(data, dict):
            sources = data.get("sources") or {}
            mp4_sources = sources.get("mp4") or {}
            preferred = [
                "1080p HD",
                "720p HD",
                "480p",
                "360p",
                "240p",
                "1440p(2K) HD",
            ]
            for item in mp4_sources.values():
                if isinstance(item, dict) and item.get("src") and item.get("default") is True:
                    media_url = item["src"]
                    break
            if not media_url:
                for label in preferred:
                    item = mp4_sources.get(label) or {}
                    if item.get("src"):
                        media_url = item["src"]
                        break
            if not media_url:
                for item in mp4_sources.values():
                    if isinstance(item, dict) and item.get("src"):
                        media_url = item["src"]
                        break
            if not media_url:
                hls = sources.get("hls") or {}
                auto = hls.get("auto") or {}
                media_url = auto.get("src") or auto.get("srcFallback") or ""
        if not media_url:
            return {"parse": 0, "url": "", "header": "{}"}
        return {
            "parse": 0,
            "url": media_url,
            "header": json.dumps(
                {
                    "User-Agent": self.USER_AGENT,
                    "Referer": referer,
                    "Accept": "*/*",
                }
            ),
        }
