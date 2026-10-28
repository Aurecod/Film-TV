# -*- coding: utf-8 -*-
"""
FongMi Type3 Python Spider — xojav.tv (XOJAV.TV)
协议依据：FongMi/TV@fongmi 分支源码 (chaquo/base/spider.py, app.py, bean/*.java)
站点结构逆向 (2026-10-28):
  - 非苹果CMS自定义站, 无 /api.php。列表/搜索/分类全部走 AJAX get_block 接口
    <page_url>?mode=async&format=json&function=get_block&block_id=<bid>&sort_by=<s>&from=<N>
  - 详情 /videos/<ID>: var stream = '...m3u8' 内嵌签名 m3u8 (token 有时效~2h, 每次请求刷新)
  - 封面 data-src 懒加载 (src=占位符), 必须取 data-src
  - 播放 m3u8 + 分片 .ts 均无需 Referer (裸连 200)
  - 无演员页(404) → 演员点击走本站搜索; 标签有真实 /tags/<slug> 页 → 标签点真实标签页
  - 分类: 一级 tab = 最近更新 + 热门影片 + 9 个分组 (按主题/衣著/身材/交合/玩法/剧情/角色/地点/杂项)
    分组 tab (type_flag=0, 普通分类) 点击 → 返回该组二级分类卡片 (folder 卡带图片+数量) → 点二级分类进视频列表
    /categories 页分组: 按主題=14 个 categories(带count), 其余 8 组=tags(图片 /tags/<dir>/<slug>.png)
  - style: 所有卡片不带 style, 排列由用户 JSON 配置统一控制; 分组 tab/演员/标签点击 payload 都用 type_flag=0
    (FongMi: type_flag=1 强制 Style.list() 单列; =0 用用户配置多列)
自测: python3 /var/minis/skills/Quss/scripts/test_spider.py <本文件>
"""
import json
import re
import time
import gzip
import urllib.request
from urllib.parse import quote, unquote

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        pass

NAME = "XOJAV"
HOST = "https://xojav.tv"
UA = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"

# 分组定义: group_id -> (tab名, [(slug, name, img, count, type)])
#   type: category -> /categories/<slug> (按主題), tag -> /tags/<slug> (其余)
GROUPS = {
    "subject": ("按主题", [
        ("chinese-subtitle", "中文字幕", "https://cdn.18jav.tv/assets/images/categories/chinese-subtitle.jpg", "11144 部影片", "category"),
        ("uncensored", "無碼解放", "https://cdn.18jav.tv/assets/images/categories/uncensored.jpg", "10329 部影片", "category"),
        ("taiwan-av", "台灣AV", "https://cdn.18jav.tv/assets/images/categories/taiwan-av.jpg", "7794 部影片", "category"),
        ("jav", "日本AV", "https://cdn.18jav.tv/assets/images/categories/jav.jpg", "5553 部影片", "category"),
        ("uniform", "制服誘惑", "https://cdn.18jav.tv/assets/images/categories/uniform.jpg", "4364 部影片", "category"),
        ("roleplay", "角色劇情", "https://cdn.18jav.tv/assets/images/categories/roleplay.jpg", "4211 部影片", "category"),
        ("pantyhose", "絲襪", "https://cdn.18jav.tv/assets/images/categories/pantyhose.jpg", "3267 部影片", "category"),
        ("sex-only", "直接開啪", "https://cdn.18jav.tv/assets/images/categories/sex-only.jpg", "1190 部影片", "category"),
        ("bdsm", "主奴調教", "https://cdn.18jav.tv/assets/images/categories/bdsm.jpg", "1179 部影片", "category"),
        ("groupsex", "多P群交", "https://cdn.18jav.tv/assets/images/categories/groupsex.jpg", "1073 部影片", "category"),
        ("intrusion", "進犯", "https://cdn.18jav.tv/assets/images/categories/rape.jpg", "744 部影片", "category"),
        ("pov", "男友視角", "https://cdn.18jav.tv/assets/images/categories/pov.jpg", "675 部影片", "category"),
        ("hixxen-cam", "流出", "https://cdn.18jav.tv/assets/images/categories/hixxen-cam.jpg", "176 部影片", "category"),
        ("lesbian", "女同歡愉", "https://cdn.18jav.tv/assets/images/categories/lesbian.jpg", "106 部影片", "category"),
    ]),
    "clothes": ("衣著", [
        ("wedding-dress", "婚紗", "https://cdn.18jav.tv/assets_x/images/tags/clothes/wedding-dress.png", "", "tag"),
        ("swimsuit", "水着", "https://cdn.18jav.tv/assets_x/images/tags/clothes/swimsuit.png", "", "tag"),
        ("stockings", "吊帶襪", "https://cdn.18jav.tv/assets_x/images/tags/clothes/stockings.png", "", "tag"),
        ("sportswear", "運動裝", "https://cdn.18jav.tv/assets_x/images/tags/clothes/sportswear.png", "", "tag"),
        ("school-uniform", "校服", "https://cdn.18jav.tv/assets_x/images/tags/clothes/school-uniform.png", "", "tag"),
        ("pantyhose", "絲襪", "https://cdn.18jav.tv/assets_x/images/tags/clothes/pantyhose.png", "", "tag"),
        ("maid", "女僕", "https://cdn.18jav.tv/assets_x/images/tags/clothes/maid.png", "", "tag"),
        ("knee-socks", "過膝襪", "https://cdn.18jav.tv/assets_x/images/tags/clothes/knee-socks.png", "", "tag"),
        ("kimono", "和服", "https://cdn.18jav.tv/assets_x/images/tags/clothes/kimono.png", "", "tag"),
        ("kemonomimi", "獸耳", "https://cdn.18jav.tv/assets_x/images/tags/clothes/kemonomimi.png", "", "tag"),
        ("glasses", "眼鏡娘", "https://cdn.18jav.tv/assets_x/images/tags/clothes/glasses.png", "", "tag"),
        ("flesh-toned-pantyhose", "肉絲", "https://cdn.18jav.tv/assets_x/images/tags/clothes/flesh-toned-pantyhose.png", "", "tag"),
        ("fishnets", "漁網", "https://cdn.18jav.tv/assets_x/images/tags/clothes/fishnets.png", "", "tag"),
        ("cheongsam", "旗袍", "https://cdn.18jav.tv/assets_x/images/tags/clothes/cheongsam.png", "", "tag"),
        ("bunny-girl", "兔女郎", "https://cdn.18jav.tv/assets_x/images/tags/clothes/bunny-girl.png", "", "tag"),
        ("black-pantyhose", "黑絲", "https://cdn.18jav.tv/assets_x/images/tags/clothes/black-pantyhose.png", "", "tag"),
    ]),
    "body_type": ("身材", [
        ("tall", "長身", "https://cdn.18jav.tv/assets_x/images/tags/body_type/tall.png", "", "tag"),
        ("tattoo", "紋身", "https://cdn.18jav.tv/assets_x/images/tags/body_type/tattoo.png", "", "tag"),
        ("suntan", "黑肉", "https://cdn.18jav.tv/assets_x/images/tags/body_type/suntan.png", "", "tag"),
        ("small-tits", "貧乳", "https://cdn.18jav.tv/assets_x/images/tags/body_type/small-tits.png", "", "tag"),
        ("short-hair", "短髮", "https://cdn.18jav.tv/assets_x/images/tags/body_type/short-hair.png", "", "tag"),
        ("mature-woman", "熟女", "https://cdn.18jav.tv/assets_x/images/tags/body_type/mature-woman.png", "", "tag"),
        ("dainty", "嬌小", "https://cdn.18jav.tv/assets_x/images/tags/body_type/dainty.png", "", "tag"),
        ("hairless-pussy", "白虎", "https://cdn.18jav.tv/assets_x/images/tags/body_type/hairless-pussy.png", "", "tag"),
        ("girl", "少女", "https://cdn.18jav.tv/assets_x/images/tags/body_type/girl.png", "", "tag"),
        ("flexible-body", "軟體", "https://cdn.18jav.tv/assets_x/images/tags/body_type/flexible-body.png", "", "tag"),
        ("big-tits", "巨乳", "https://cdn.18jav.tv/assets_x/images/tags/body_type/big-tits.png", "", "tag"),
        ("beautiful-leg", "美腿", "https://cdn.18jav.tv/assets_x/images/tags/body_type/beautiful-leg.png", "", "tag"),
        ("beautiful-butt", "美尻", "https://cdn.18jav.tv/assets_x/images/tags/body_type/beautiful-butt.png", "", "tag"),
    ]),
    "acts": ("交合", [
        ("tit-wank", "乳交", "https://cdn.18jav.tv/assets_x/images/tags/acts/tit-wank.png", "", "tag"),
        ("squirting", "潮吹", "https://cdn.18jav.tv/assets_x/images/tags/acts/squirting.png", "", "tag"),
        ("spasms", "痙攣", "https://cdn.18jav.tv/assets_x/images/tags/acts/spasms.png", "", "tag"),
        ("kiss", "接吻", "https://cdn.18jav.tv/assets_x/images/tags/acts/kiss.png", "", "tag"),
        ("footjob", "腳交", "https://cdn.18jav.tv/assets_x/images/tags/acts/footjob.png", "", "tag"),
        ("facial", "顏射", "https://cdn.18jav.tv/assets_x/images/tags/acts/facial.png", "", "tag"),
        ("deep-throat", "深喉", "https://cdn.18jav.tv/assets_x/images/tags/acts/deep-throat.png", "", "tag"),
        ("cum-in-mouth", "口爆", "https://cdn.18jav.tv/assets_x/images/tags/acts/cum-in-mouth.png", "", "tag"),
        ("creampie", "中出", "https://cdn.18jav.tv/assets_x/images/tags/acts/creampie.png", "", "tag"),
        ("blowjob", "口交", "https://cdn.18jav.tv/assets_x/images/tags/acts/blowjob.png", "", "tag"),
        ("anal-sex", "肛交", "https://cdn.18jav.tv/assets_x/images/tags/acts/anal-sex.png", "", "tag"),
    ]),
    "plays": ("玩法", [
        ("tune", "調教", "https://cdn.18jav.tv/assets_x/images/tags/plays/tune.png", "", "tag"),
        ("torture", "刑具", "https://cdn.18jav.tv/assets_x/images/tags/plays/torture.png", "", "tag"),
        ("soapland", "泡姬", "https://cdn.18jav.tv/assets_x/images/tags/plays/soapland.png", "", "tag"),
        ("intrusion", "進犯", "https://cdn.18jav.tv/assets_x/images/tags/plays/intrusion.png", "", "tag"),
        ("quickie", "瞬間插入", "https://cdn.18jav.tv/assets_x/images/tags/plays/quickie.png", "", "tag"),
        ("piss", "放尿", "https://cdn.18jav.tv/assets_x/images/tags/plays/piss.png", "", "tag"),
        ("outdoor", "露出", "https://cdn.18jav.tv/assets_x/images/tags/plays/outdoor.png", "", "tag"),
        ("massage", "按摩", "https://cdn.18jav.tv/assets_x/images/tags/plays/massage.png", "", "tag"),
        ("masochism-guy", "男M", "https://cdn.18jav.tv/assets_x/images/tags/plays/masochism-guy.png", "", "tag"),
        ("insult", "凌辱", "https://cdn.18jav.tv/assets_x/images/tags/plays/insult.png", "", "tag"),
        ("gangbang", "多P", "https://cdn.18jav.tv/assets_x/images/tags/plays/gangbang.png", "", "tag"),
        ("gang-intrusion", "集團進犯", "https://cdn.18jav.tv/assets_x/images/tags/plays/gang-intrusion.png", "", "tag"),
        ("crapulence", "泥醉", "https://cdn.18jav.tv/assets_x/images/tags/plays/crapulence.png", "", "tag"),
        ("chizyo", "痴女", "https://cdn.18jav.tv/assets_x/images/tags/plays/chizyo.png", "", "tag"),
        ("chikan", "痴漢", "https://cdn.18jav.tv/assets_x/images/tags/plays/chikan.png", "", "tag"),
        ("breast-milk", "母乳", "https://cdn.18jav.tv/assets_x/images/tags/plays/breast-milk.png", "", "tag"),
        ("bondage", "綑綁", "https://cdn.18jav.tv/assets_x/images/tags/plays/bondage.png", "", "tag"),
        ("3p", "3P", "https://cdn.18jav.tv/assets_x/images/tags/plays/3p.png", "", "tag"),
        ("10-times-a-day", "一日十回", "https://cdn.18jav.tv/assets_x/images/tags/plays/10-times-a-day.png", "", "tag"),
    ]),
    "theme": ("剧情", [
        ("virginity", "童貞", "https://cdn.18jav.tv/assets_x/images/tags/theme/virginity.png", "", "tag"),
        ("ugly-man", "醜男", "https://cdn.18jav.tv/assets_x/images/tags/theme/ugly-man.png", "", "tag"),
        ("time-stop", "時間停止", "https://cdn.18jav.tv/assets_x/images/tags/theme/time-stop.png", "", "tag"),
        ("temptation", "誘惑", "https://cdn.18jav.tv/assets_x/images/tags/theme/temptation.png", "", "tag"),
        ("sex-beside-husband", "夫目前犯", "https://cdn.18jav.tv/assets_x/images/tags/theme/sex-beside-husband.png", "", "tag"),
        ("rainy-day", "下雨天", "https://cdn.18jav.tv/assets_x/images/tags/theme/rainy-day.png", "", "tag"),
        ("ntr", "NTR", "https://cdn.18jav.tv/assets_x/images/tags/theme/ntr.png", "", "tag"),
        ("love-potion", "媚藥", "https://cdn.18jav.tv/assets_x/images/tags/theme/love-potion.png", "", "tag"),
        ("hixxen-cam", "流出", "https://cdn.18jav.tv/assets_x/images/tags/theme/hixxen-cam.png", "", "tag"),
        ("kinship", "親屬", "https://cdn.18jav.tv/assets_x/images/tags/theme/kinship.png", "", "tag"),
        ("hypnosis", "催眠", "https://cdn.18jav.tv/assets_x/images/tags/theme/hypnosis.png", "", "tag"),
        ("giant", "巨漢", "https://cdn.18jav.tv/assets_x/images/tags/theme/giant.png", "", "tag"),
        ("black", "黑人", "https://cdn.18jav.tv/assets_x/images/tags/theme/black.png", "", "tag"),
        ("avenge", "復仇", "https://cdn.18jav.tv/assets_x/images/tags/theme/avenge.png", "", "tag"),
        ("age-difference", "年齡差", "https://cdn.18jav.tv/assets_x/images/tags/theme/age-difference.png", "", "tag"),
        ("affair", "出軌", "https://cdn.18jav.tv/assets_x/images/tags/theme/affair.png", "", "tag"),
    ]),
    "character": ("角色", [
        ("wife", "人妻", "https://cdn.18jav.tv/assets_x/images/tags/character/wife.png", "", "tag"),
        ("widow", "未亡人", "https://cdn.18jav.tv/assets_x/images/tags/character/widow.png", "", "tag"),
        ("team-manager", "球隊經理", "https://cdn.18jav.tv/assets_x/images/tags/character/team-manager.png", "", "tag"),
        ("teacher", "老師", "https://cdn.18jav.tv/assets_x/images/tags/character/teacher.png", "", "tag"),
        ("club-hostess-and-sex-worker", "風俗娘", "https://cdn.18jav.tv/assets_x/images/tags/character/club-hostess-and-sex-worker.png", "", "tag"),
        ("private-teacher", "家庭教師", "https://cdn.18jav.tv/assets_x/images/tags/character/private-teacher.png", "", "tag"),
        ("ol", "OL", "https://cdn.18jav.tv/assets_x/images/tags/character/ol.png", "", "tag"),
        ("nurse", "護士", "https://cdn.18jav.tv/assets_x/images/tags/character/nurse.png", "", "tag"),
        ("idol", "偶像", "https://cdn.18jav.tv/assets_x/images/tags/character/idol.png", "", "tag"),
        ("housewife", "家政婦", "https://cdn.18jav.tv/assets_x/images/tags/character/housewife.png", "", "tag"),
        ("fugitive", "逃犯", "https://cdn.18jav.tv/assets_x/images/tags/character/fugitive.png", "", "tag"),
        ("flight-attendant", "空姐", "https://cdn.18jav.tv/assets_x/images/tags/character/flight-attendant.png", "", "tag"),
        ("female-anchor", "主播", "https://cdn.18jav.tv/assets_x/images/tags/character/female-anchor.png", "", "tag"),
        ("doctor", "醫生", "https://cdn.18jav.tv/assets_x/images/tags/character/doctor.png", "", "tag"),
        ("detective", "搜查官", "https://cdn.18jav.tv/assets_x/images/tags/character/detective.png", "", "tag"),
        ("couple", "情侶", "https://cdn.18jav.tv/assets_x/images/tags/character/couple.png", "", "tag"),
    ]),
    "location": ("地点", [
        ("tram", "電車", "https://cdn.18jav.tv/assets_x/images/tags/location/tram.png", "", "tag"),
        ("toilet", "廁所", "https://cdn.18jav.tv/assets_x/images/tags/location/toilet.png", "", "tag"),
        ("swimming-pool", "泳池", "https://cdn.18jav.tv/assets_x/images/tags/location/swimming-pool.png", "", "tag"),
        ("store", "便利店", "https://cdn.18jav.tv/assets_x/images/tags/location/store.png", "", "tag"),
        ("school", "學校", "https://cdn.18jav.tv/assets_x/images/tags/location/school.png", "", "tag"),
        ("prison", "監獄", "https://cdn.18jav.tv/assets_x/images/tags/location/prison.png", "", "tag"),
        ("magic-mirror", "魔鏡號", "https://cdn.18jav.tv/assets_x/images/tags/location/magic-mirror.png", "", "tag"),
        ("library", "圖書館", "https://cdn.18jav.tv/assets_x/images/tags/location/library.png", "", "tag"),
        ("hot-spring", "溫泉", "https://cdn.18jav.tv/assets_x/images/tags/location/hot-spring.png", "", "tag"),
        ("gym-room", "健身房", "https://cdn.18jav.tv/assets_x/images/tags/location/gym-room.png", "", "tag"),
        ("first-night", "處女", "https://cdn.18jav.tv/assets_x/images/tags/location/first-night.png", "", "tag"),
        ("car", "汽車", "https://cdn.18jav.tv/assets_x/images/tags/location/car.png", "", "tag"),
        ("bathing-place", "洗浴場", "https://cdn.18jav.tv/assets_x/images/tags/location/bathing-place.png", "", "tag"),
    ]),
    "others": ("杂项", [
        ("video-recording", "錄像", "https://cdn.18jav.tv/assets_x/images/tags/others/video-recording.png", "", "tag"),
        ("variety-show", "綜藝", "https://cdn.18jav.tv/assets_x/images/tags/others/variety-show.png", "", "tag"),
        ("thanksgiving", "感謝祭", "https://cdn.18jav.tv/assets_x/images/tags/others/thanksgiving.png", "", "tag"),
        ("more-than-4-hours", "4小時以上", "https://cdn.18jav.tv/assets_x/images/tags/others/more-than-4-hours.png", "", "tag"),
        ("festival", "節日主題", "https://cdn.18jav.tv/assets_x/images/tags/others/festival.png", "", "tag"),
        ("debut-retires", "處女作/引退作", "https://cdn.18jav.tv/assets_x/images/tags/others/debut-retires.png", "", "tag"),
    ]),
}

# block_id | sort_by 映射
BLOCK = {
    "latest":  ("list_videos_latest_videos_list", "release_at", "/latest-updates"),
    "hot":     ("list_videos_common_videos_list", "views",      "/hot"),
    "category":("list_videos_common_videos_list", "release_at", None),  # /categories/<slug>
    "tag":     ("list_videos_common_videos_list", "release_at", None),  # /tags/<slug>
    "search":  ("list_videos_videos_list_search_result", "most_relevant", None),
}

# 卡片正则 (列表 AJAX / 首页 HTML 通用)
P_CARD = re.compile(r'<div class="item card-video[^"]*">(.*?)</div>\s*</div>', re.S)
P_ID = re.compile(r'href="https?://xojav\.tv/videos/([^"/]+)"')
P_PIC = re.compile(r'data-src="(https://cdn\.18jav\.tv[^"]+)"')
P_DUR = re.compile(r'card-video__duration">([^<]+)<')
P_TITLE = re.compile(r'card-video__title">\s*<a[^>]*>\s*([^<]+?)\s*</a>', re.S)


class Spider(BaseSpider):

    # ---------- 生命周期 ----------
    def __init__(self):
        self.host = HOST
        self.name = NAME
        self._cache = {}
        self._cache_time = {}
        self.options = {}

    def init(self, extend=""):
        # 不发网络请求; 只解析配置
        if isinstance(extend, dict):
            cfg = extend
        elif extend:
            try:
                cfg = json.loads(extend)
            except Exception:
                cfg = {}
        else:
            cfg = {}
        if not isinstance(cfg, dict):
            return
        site = (cfg.get("site") or cfg.get("url") or "").strip().rstrip("/")
        if site and site.startswith("http"):
            self.host = site
        self.options = cfg

    def getName(self):
        return self.name

    def getDependence(self):
        return []

    def destroy(self):
        self._cache.clear()
        self._cache_time.clear()
        self.options = {}

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4|flv|mkv|ts)(\?|$)", str(url)))

    def manualVideoCheck(self):
        return False

    def liveContent(self, url):
        return ""

    def action(self, action):
        return {"msg": ""}

    # ---------- HTTP (urllib, 可靠超时) ----------
    def _fetch(self, url, timeout=12, referer=None):
        """GET 页面文本; gzip 解压; 失败返回 ''"""
        key = ("fetch", url)
        now = time.time()
        if key in self._cache_time and now - self._cache_time[key] < 20:
            return self._cache[key]
        h = {"User-Agent": UA, "Accept": "*/*", "Accept-Encoding": "gzip, deflate",
             "Referer": referer or (self.host + "/")}
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                enc = resp.headers.get("Content-Encoding", "")
                if "gzip" in enc:
                    raw = gzip.decompress(raw)
                text = raw.decode("utf-8", "ignore")
            self._cache[key] = text
            self._cache_time[key] = now
            return text
        except Exception:
            return ""

    def _ajax(self, page_url, block_id, sort_by, from_pg):
        """调 get_block AJAX 接口, 返回 (html, pagecount)"""
        if not page_url:
            return "", 0
        sep = "&" if "?" in page_url else "?"
        url = ("%s%smode=async&format=json&function=get_block&block_id=%s&sort_by=%s&from=%s"
               % (page_url, sep, block_id, sort_by, from_pg))
        html = self._fetch(url)
        if not html:
            return "", 0
        # 提取总页数 (pagination 里最大的 from:N)
        pages = re.findall(r'from:(\d+)', html)
        pc = max((int(p) for p in pages), default=0)
        return html, pc

    # ---------- 解析 ----------
    def _parse_cards(self, html):
        items = []
        seen = set()
        for blk in P_CARD.findall(html):
            m = P_ID.search(blk)
            if not m:
                continue
            vid = m.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            pic = P_PIC.search(blk)
            dur = P_DUR.search(blk)
            title = P_TITLE.search(blk)
            # 标题兜底: alt 属性
            if not title:
                ta = re.search(r'alt="([^"]+)"', blk)
                title = ta
            name = (title.group(1).strip() if title else vid)
            items.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": (pic.group(1) if pic else ""),
                "vod_remarks": (dur.group(1) if dur else ""),
                "vod_play_from": "正片",
                "vod_play_url": "",
            })
        return items

    def _fetch_videos(self, page_url, block_id, sort_by, pg):
        html, pc = self._ajax(page_url, block_id, sort_by, pg)
        items = self._parse_cards(html)
        if not pc:
            pc = 9999
        return items, pc

    def _classes(self):
        # 一级 tab: 最近更新 + 热门影片 + 9 个分组 (点进显示二级分类卡片)
        # 分组 tab 用 type_flag=0 (普通分类, 非资源夹) → FongMi folder=false
        #   → 二级分类卡片与二层视频都用用户 JSON 配置的 style (多列), 不被强制单列
        cls = [
            {"type_id": "latest", "type_name": "最近更新"},
            {"type_id": "hot", "type_name": "热门影片"},
        ]
        for gid, (tabname, items) in GROUPS.items():
            cls.append({"type_id": gid, "type_name": tabname})
        return cls

    def _group_cards(self, gid):
        """分组下的二级分类卡片 (资源夹 folder 卡, 带图片+数量, 点击进视频列表)"""
        _, items = GROUPS.get(gid, (None, []))
        cards = []
        for slug, name, img, count, ty in items:
            cards.append({
                "vod_id": "folder/%s/%s" % (ty, slug),
                "vod_name": name,
                "vod_pic": img,
                "vod_remarks": count,
                "vod_tag": "folder",
            })
        return cards

    def _clickable(self, kind, name):
        """FongMi BBCode: 点击跳 categoryContent(id)
        type_flag="0" → FongMi folder=false → 点击后页面用用户 JSON style(多列),
        不强制单列 (type_flag="1" 会强制 Style.list() 单列)"""
        try:
            payload = json.dumps({"id": "%s/%s" % (kind, quote(name, safe="")),
                                  "name": name, "type_flag": "0"}, ensure_ascii=False)
        except Exception:
            return name
        return "[a=cr:%s/]%s[/a]" % (payload, name)

    # ---------- 首页 ----------
    def homeContent(self, filter):
        classes = self._classes()
        items, pc = self._fetch_videos(self.host + "/latest-updates",
                                       BLOCK["latest"][0], BLOCK["latest"][1], 1)
        return {"class": classes, "list": items, "pagecount": pc}

    def homeVideoContent(self):
        items, pc = self._fetch_videos(self.host + "/latest-updates",
                                       BLOCK["latest"][0], BLOCK["latest"][1], 1)
        return {"list": items, "pagecount": pc}

    # ---------- 分类 ----------
    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg_i = int(pg)
        except Exception:
            pg_i = 1
        tid = (tid or "").strip()

        # 演员点击 → 本站搜索 (无演员页)
        if tid.startswith("actor/"):
            name = unquote(tid.split("/", 1)[1])
            return self._do_search(name, pg_i)

        # 标签点击 (详情页) → 真实标签页
        if tid.startswith("tag/"):
            slug = tid.split("/", 1)[1]
            return self._cat_videos(slug, pg_i, BLOCK["tag"], tag=True)

        # 二级分类 folder 卡点击 → 视频列表 (folder/cat/... 或 folder/tag/...)
        if tid.startswith("folder/"):
            parts = tid.split("/", 2)
            if len(parts) == 3 and parts[2]:
                ty, slug = parts[1], parts[2]
                if ty == "tag":
                    return self._cat_videos(slug, pg_i, BLOCK["tag"], tag=True)
                return self._cat_videos(slug, pg_i, BLOCK["category"])
            return {"class": [], "list": [], "pagecount": 1}

        # 分组 tab (按主题/衣著/.../杂项) → 返回该组二级分类卡片
        if tid in GROUPS:
            return {"class": [], "list": self._group_cards(tid), "pagecount": 1}

        if tid == "latest":
            return self._cat_videos(None, pg_i, BLOCK["latest"])
        if tid == "hot":
            return self._cat_videos(None, pg_i, BLOCK["hot"])
        if tid:
            return self._cat_videos(tid, pg_i, BLOCK["category"])
        return {"class": [], "list": [], "pagecount": 1}

    def _cat_videos(self, slug, pg, blk, tag=False):
        block_id, sort_by, path = blk
        if tag:
            page_url = self.host + "/tags/" + quote(slug, safe="")
        elif path:
            page_url = self.host + path
        else:
            page_url = self.host + "/categories/" + quote(slug, safe="")
        items, pc = self._fetch_videos(page_url, block_id, sort_by, pg)
        return {"class": [], "list": items, "pagecount": pc}

    # ---------- 搜索 ----------
    def searchContent(self, key, quick, pg="1"):
        try:
            pg_i = int(pg)
        except Exception:
            pg_i = 1
        return self._do_search(key, pg_i)

    def _do_search(self, key, pg):
        block_id, sort_by, _ = BLOCK["search"]
        page_url = self.host + "/search/" + quote(key, safe="") + "/"
        items, pc = self._fetch_videos(page_url, block_id, sort_by, pg)
        return {"class": [], "list": items, "pagecount": pc}

    # ---------- 详情 ----------
    def detailContent(self, ids):
        if isinstance(ids, list):
            vid = ids[0] if ids else ""
        else:
            vid = ids
        vid = (vid or "").strip()
        if not vid:
            return {"list": []}
        url = self.host + "/videos/" + quote(vid, safe="")
        html = self._fetch(url)
        if not html:
            return {"list": []}

        # 标题
        title = ""
        m = re.search(r'<meta property="og:title" content="([^"]*)"', html)
        if m:
            title = m.group(1).strip()
        if not title:
            m = re.search(r'<h2 class="content-details__title">([^<]+)</h2>', html)
            if m:
                title = m.group(1).strip()
        title = title or vid

        # 封面
        pic = ""
        m = re.search(r'<meta property="og:image" content="([^"]*)"', html)
        if m:
            pic = m.group(1).strip()

        # 演员 (video:actor) → 可点击搜索
        actors = re.findall(r'<meta property="video:actor" content="([^"]*)"', html)
        actors = [a for a in actors if a.strip()]
        vod_actor = "、".join(self._clickable("actor", a) for a in actors)

        # 标签 (真实 /tags/<slug> 页) → 可点击
        tags = []
        for m in re.finditer(r'href="https?://xojav\.tv/tags/([^"]+)"[^>]*>\s*([^<]+?)\s*<', html):
            slug, nm = m.group(1), m.group(2).strip()
            if slug and nm:
                tags.append((slug, nm))
        vod_tag = ""
        if tags:
            # id 用 slug (categoryContent 处理 tag/<slug>), 显示用名称
            def _tag_bb(slug, nm):
                try:
                    payload = json.dumps({"id": "tag/%s" % quote(slug, safe=""),
                                          "name": nm, "type_flag": "0"}, ensure_ascii=False)
                except Exception:
                    return nm
                return "[a=cr:%s/]%s[/a]" % (payload, nm)
            vod_tag = "、".join(_tag_bb(slug, nm) for slug, nm in tags)

        # 分类 (当前视频所属)
        cats = re.findall(r'href="https?://xojav\.tv/categories/([^"]+)"[^>]*>\s*([^<]+?)\s*<', html)
        type_name = ""
        if cats:
            type_name = cats[0][1].strip()

        # 观看数 → vod_remarks (主视频: <span>N 觀看</span>, 相关视频是嵌套 span 不匹配)
        remarks = ""
        m = re.search(r'<span>([\d,]+)\s*觀看</span>', html)
        if m:
            remarks = m.group(1).strip() + " 觀看"

        # 播放: 签名 m3u8 (var stream = '...')
        stream = ""
        m = re.search(r"var stream = '([^']+)'", html)
        if m:
            stream = m.group(1).strip()

        # 描述
        desc = title
        if actors:
            desc += "\n演員: " + ", ".join(actors)
        if tags:
            desc += "\n標籤: " + ", ".join(nm for slug, nm in tags)

        vod = {
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": pic,
            "type_name": type_name,
            "vod_remarks": remarks,
            "vod_actor": vod_actor,
            "vod_tag": vod_tag,
            "vod_content": desc,
            "vod_play_from": "正片",
            "vod_play_url": "正片$%s" % stream if stream else "",
        }
        return {"list": [vod]}

    # ---------- 播放 ----------
    def playerContent(self, flag, id, vipFlags):
        url = (id or "").strip()
        # 提取 URL 内时间戳 (有效期判据)
        m = re.search(r"/hls/[^/]+/(\d+)/", url)
        if m:
            try:
                exp = int(m.group(1))
                if exp - time.time() < 600:
                    url = self._refresh_stream(url)
            except Exception:
                pass
        if not url:
            return {}
        return {"parse": 0, "url": url, "header": {}}

    def _refresh_stream(self, old_url):
        """签名 m3u8 时效不足 → 重取详情页拿新鲜流"""
        m = re.search(r"/storage/([^/]+)/", old_url)
        if not m:
            return ""
        vid = m.group(1)
        html = self._fetch(self.host + "/videos/" + quote(vid, safe=""))
        if not html:
            return ""
        m = re.search(r"var stream = '([^']+)'", html)
        return m.group(1).strip() if m else ""
