# coding=utf-8
"""
凤梨音乐 (flmp3.pro) TVBox 音乐爬虫
- 列表：全部歌曲 song.html?page=N / 首页最新、热门 tab / 搜索
- 播放：/api/playurl.php?id={id} 直接返回真实播放地址（无需验证码）
- 二级分类：一级"推荐歌单" -> 二级[最新音乐, 热门音乐]（站无原生二级，按此映射）
- 域名跟踪：init 时探测备用域名，主域名失效自动切换可用域名
- 注意：该站"音乐合集"(heji)为网盘打包资源，不可在线播放，故不纳入可播分类
- 作者：繁星四月
"""
import sys
import re
import requests

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    # 可在此扩展备用域名，域名变更时自动探测可用项
    DOMAINS = [
        "www.flmp3.pro",
        "flmp3.pro",
    ]
    REFERER = "https://www.flmp3.pro/"

    def getName(self):
        return "凤梨音乐"

    def init(self, extend=""):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        })
        self._base = self._probe_base()
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass

    def destroy(self):
        if hasattr(self, 'session'):
            self.session.close()

    # ---------- 域名跟踪 ----------
    def _probe_base(self):
        """依次探测备用域名，返回第一个可用的站点 base，找不到则回退默认"""
        for dom in self.DOMAINS:
            base = f"https://{dom}"
            try:
                r = self.session.get(base, timeout=8, verify=False)
                if r.status_code == 200 and "凤梨" in r.text:
                    self.log(f"域名跟踪生效: {base}")
                    return base
            except Exception:
                continue
        return f"https://{self.DOMAINS[0]}"

    def _get(self, path, params=None, headers=None):
        url = path if path.startswith("http") else self._base + path
        try:
            headers = headers or {}
            return self.session.get(
                url, params=params, headers=headers,
                timeout=15, verify=False,
            )
        except Exception as e:
            self.log(f"请求失败 {url}: {e}")
            return None

    # ---------- 首页/分类 ----------
    def homeContent(self, filter):
        classes = [
            {"type_id": "recommend", "type_name": "推荐歌单"},
            {"type_id": "all", "type_name": "全部歌曲"},
        ]
        return {"class": classes, "filters": {}}

    def categoryContent(self, tid, pg, filter, ext):
        # 一级目录：推荐歌单 -> 返回二级分类([最新, 热门])
        if tid == "recommend":
            return self._recommend_dir()
        if tid in ("new", "hot"):
            return self._home_songs(tid)
        if tid == "all":
            return self._all_songs(pg)
        return {"list": [], "page": pg, "pagecount": 0}

    def _recommend_dir(self):
        """二级分类目录"""
        items = [
            {"type_id": "new", "type_name": "最新音乐"},
            {"type_id": "hot", "type_name": "热门音乐"},
        ]
        video_list = [
            {
                "vod_id": it["type_id"],
                "vod_name": it["type_name"],
                "vod_remarks": "二级分类",
                "vod_tag": "folder",
            }
            for it in items
        ]
        return {"list": video_list, "page": "1", "pagecount": 1}

    def _home_songs(self, which):
        r = self._get("/")
        if not r:
            return {"list": [], "page": "1", "pagecount": 0}
        html = r.text
        # 定位首页 tab 区的 class="list" 容器
        idx = html.find('class="list"')
        if idx < 0:
            return self._all_songs("1")
        seg = html[idx:]
        # 拆分 item 面板：第一个面板(最新,on) + 其余面板(热门)
        items = re.split(r'<div class="item', seg)
        panel = None
        if which == "new":
            panel = items[1] if len(items) > 1 else seg
        else:
            panel = "\n".join(items[2:]) if len(items) > 2 else seg
        return self._parse_cards(panel)

    def _all_songs(self, pg):
        page = int(pg) if pg and str(pg).isdigit() else 1
        r = self._get("/song.html", params={"page": page})
        if not r:
            return {"list": [], "page": pg, "pagecount": 0}
        return self._parse_cards(r.text, page)

    # ---------- 列表解析 ----------
    def _parse_cards(self, html, page=1):
        result = []
        # 卡片：<a href="/song/ID.html"><div class="pic"><img src=封面><h3>歌名<p>歌手
        for m in re.finditer(r'href="(/song/(\d+)\.html)"', html):
            sid = m.group(2)
            start = max(0, m.start() - 60)
            chunk = html[start:m.end() + 500]
            name, singer, pic = self._extract_card(chunk)
            # 兜底：全文取该段内的标题/封面
            if not name:
                nm = re.search(r'<h3[^>]*>(.*?)</h3>', chunk, re.S)
                name = re.sub(r'<[^>]+>', '', nm.group(1)).strip() if nm else f"歌曲{sid}"
            if not pic:
                im = re.search(r'<img src="([^"]+)"', chunk)
                pic = im.group(1) if im else ""
            result.append({
                "vod_id": sid,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": singer,
            })
        # 去重(按id)
        seen, uniq = set(), []
        for it in result:
            if it["vod_id"] not in seen:
                seen.add(it["vod_id"])
                uniq.append(it)
        pagecount = 1
        if re.search(r'\?page=(\d+)', html):
            pages = [int(x) for x in re.findall(r'\?page=(\d+)', html)]
            pagecount = max(0, max(pages))
        return {
            "list": uniq,
            "page": str(page),
            "pagecount": pagecount if pagecount else 1,
        }

    def _extract_card(self, chunk):
        nm = re.search(r'<h3[^>]*>(.*?)</h3>', chunk, re.S)
        name = re.sub(r'<[^>]+>', '', nm.group(1)).strip() if nm else ""
        # 歌手：紧邻 img 后的一段 <p>..</p> 或 img alt
        singer = ""
        pt = re.findall(r'<p[^>]*>(.*?)</p>', chunk, re.S)
        for p in pt:
            txt = re.sub(r'<[^>]+>', '', p).strip()
            if txt and "格式" not in txt and "歌手" not in txt:
                singer = txt
                break
        im = re.search(r'<img src="([^"]+)"', chunk)
        pic = im.group(1) if im else ""
        return name, singer, pic

    # ---------- 搜索 ----------
    def searchContent(self, key, quick, pg="1"):
        r = self._get("/search.html", params={"keyword": key})
        if not r:
            return {"list": [], "page": pg, "pagecount": 0}
        return self._parse_cards(r.text)

    # ---------- 详情 ----------
    def detailContent(self, ids):
        sid = ids[0]
        # 解析详情页补充歌名/歌手/封面
        name, singer, pic = self._get_song_meta(sid)
        play_url = self._get_play_url(sid)
        remarks = "可试听" if play_url else "暂无播放"

        # 选集里保存歌曲id（不直接存真实URL，避免过期）：
        # 播放时 playerContent 取到 sid 再实时请求 playurl 生成新地址
        vod_play_from = "MP3"
        vod_play_url = f"MP3${sid}" if play_url else f"暂无资源${sid}"

        vod = {
            "vod_id": sid,
            "vod_name": name,
            "vod_pic": pic,
            "vod_actor": singer,
            "vod_remarks": remarks,
            "vod_content": f"歌手：{singer}",
            "vod_play_from": vod_play_from,
            "vod_play_url": vod_play_url,
        }
        return {"list": [vod]}

    def _get_song_meta(self, sid):
        r = self._get(f"/song/{sid}.html")
        if not r:
            return f"歌曲{sid}", "", ""
        html = r.text
        nm = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
        name = re.sub(r'<[^>]+>', '', nm.group(1)).strip() if nm else f"歌曲{sid}"
        singer_m = re.search(r'歌手：\s*<a[^>]*>(.*?)</a>', html, re.S)
        singer = re.sub(r'<[^>]+>', '', singer_m.group(1)).strip() if singer_m else ""
        im = re.search(r'<img src="([^"]+)"[^>]*>', html)
        pic = im.group(1) if im else ""
        return name, singer, pic

    # ---------- 播放 ----------
    def playerContent(self, flag, id, vipFlags):
        sid = id
        if "$" in sid:
            _, sid = sid.split("$", 1)
        header = {
            "User-Agent": self.session.headers["User-Agent"],
            "Referer": self.REFERER,
        }
        # 直接是 url（兼容）或歌曲id（实时拉取新地址）
        if str(sid).startswith("http"):
            return {"parse": 0, "url": sid, "header": header}
        if not str(sid).isdigit():
            return {"parse": 0, "url": "", "msg": "无效地址"}
        url = self._get_play_url(sid)
        if not url:
            return {"parse": 0, "url": "", "msg": "获取播放地址失败"}
        return {"parse": 0, "url": url, "header": header}

    def _get_play_url(self, sid):
        """GET /api/playurl.php?id=xx -> 直接返回真实播放URL字符串"""
        r = self._get(
            "/api/playurl.php",
            params={"id": sid},
            headers={"Referer": self._base + f"/song/{sid}.html"},
        )
        if not r or r.status_code != 200:
            return ""
        text = (r.text or "").strip()
        if text.startswith("http://") or text.startswith("https://"):
            return text
        return ""

    def localProxy(self, params):
        return None