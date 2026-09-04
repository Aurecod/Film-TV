# -*- coding: utf-8 -*-
# ============================================================
# 适配 https://flos-ubn-669t.xflooow8s701.cc 的 TVBox 爬虫脚本
# 网站：51吃瓜网 (MacCMS)
# 功能：首页 / 分类 / 详情 / 播放 / 搜索
# ============================================================

import re
import json
import html
import urllib.request
import urllib.parse
import ssl
from urllib.parse import urljoin, quote, unquote

try:
    ssl._create_default_https_context = ssl._create_unverified_context
except AttributeError:
    pass

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        def init(self, extend=""): pass
        def homeContent(self, filter): pass
        def homeVideoContent(self): pass
        def categoryContent(self, tid, pg, filter, extend): pass
        def detailContent(self, ids): pass
        def playerContent(self, flag, id, vipFlags=None): pass
        def searchContent(self, key, quick, pg='1'): pass
        def isVideoFormat(self, url): pass
        def manualVideoCheck(self): pass
        def localProxy(self, param): pass


def clean_text(text):
    if not text:
        return ""
    text = html.unescape(str(text))
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def fix_url(url, host):
    if not url:
        return ""
    url = url.strip()
    if url.startswith('//'):
        return 'https:' + url
    if url.startswith('/'):
        return urljoin(host, url)
    if url.startswith(('http://', 'https://')):
        return url
    return urljoin(host, '/' + url)


class Spider(BaseSpider):

    def __init__(self):
        super().__init__()
        self.host = "https://flos-ubn-669t.xflooow8s701.cc"
        self.name = "xfl_spider"
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    def init(self, extend=""):
        if extend and extend.startswith("http"):
            self.host = extend.rstrip("/")

    def getName(self):
        return self.name

    def isVideoFormat(self, url):
        return any(x in url for x in [".m3u8", ".mp4", ".flv", ".ts"])

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        return [200, "video/MP2T", b"", {}]

    def _fetch(self, url, referer=None):
        if not url.startswith(('http://', 'https://')):
            url = urljoin(self.host, url)

        try:
            headers = {"User-Agent": self.user_agent}
            if referer:
                headers["Referer"] = referer

            req = urllib.request.Request(url, headers=headers)
            r = urllib.request.urlopen(req, timeout=15)
            return r.read().decode('utf-8', errors='ignore')
        except Exception as e:
            print(f"[{self.name}] 请求失败: {e}")
            return ""

    # ============================================================
    # 解析视频列表
    # ============================================================

    def _parse_video_items(self, html_text):
        """从HTML中解析视频列表项"""
        if not html_text:
            return []

        videos = []
        
        # 找到 appel-max 容器
        start_match = re.search(r'<div[^>]*class="[^"]*appel-max[^"]*"[^>]*>', html_text)
        if start_match:
            start_pos = start_match.end()
            depth = 0
            end_pos = start_pos
            i = start_pos
            while i < len(html_text):
                if html_text[i:i+4] == '<div':
                    depth += 1
                    i += 4
                elif html_text[i:i+6] == '</div>':
                    if depth == 0:
                        end_pos = i + 6
                        break
                    depth -= 1
                    i += 6
                else:
                    i += 1
            
            if end_pos > start_pos:
                container_content = html_text[start_pos:end_pos]
                
                # 匹配 /voddetail/数字/ 格式
                li_pattern = r'<li[^>]*>.*?<a[^>]*href="/voddetail/(\d+)/"[^>]*>.*?<img[^>]*src="([^"]*)"[^>]*alt="([^"]*)"[^>]*>.*?<h5>.*?<a[^>]*>(.*?)</a>.*?</h5>'
                matches = re.findall(li_pattern, container_content, re.DOTALL)
                
                print(f"[_parse_video_items] 匹配到 {len(matches)} 个视频项")
                
                for match in matches:
                    try:
                        if len(match) == 4:
                            vid, pic, alt, title = match
                            title = clean_text(title or alt)
                            pic = fix_url(pic, self.host)
                            
                            if vid and title:
                                videos.append({
                                    "vod_id": vid,
                                    "vod_name": title,
                                    "vod_pic": pic,
                                    "vod_remarks": ""
                                })
                    except Exception as e:
                        print(f"解析单个视频失败: {e}")
                        continue
                
                if videos:
                    return videos
        
        # 备用方法
        ul_match = re.search(r'<ul[^>]*class="[^"]*thumbnail-group[^"]*"[^>]*>(.*?)</ul>', html_text, re.DOTALL)
        if ul_match:
            ul_content = ul_match.group(1)
            li_pattern = r'<li[^>]*>.*?<a[^>]*href="/voddetail/(\d+)/"[^>]*>.*?<img[^>]*src="([^"]*)"[^>]*alt="([^"]*)"[^>]*>.*?<h5>.*?<a[^>]*>(.*?)</a>.*?</h5>'
            matches = re.findall(li_pattern, ul_content, re.DOTALL)
            
            for match in matches:
                try:
                    if len(match) == 4:
                        vid, pic, alt, title = match
                        title = clean_text(title or alt)
                        pic = fix_url(pic, self.host)
                        
                        if vid and title:
                            videos.append({
                                "vod_id": vid,
                                "vod_name": title,
                                "vod_pic": pic,
                                "vod_remarks": ""
                            })
                except Exception as e:
                    print(f"解析单个视频失败: {e}")
                    continue
        
        return videos

    # ============================================================
    # 首页分类（所有子分类展平为一级分类）
    # ============================================================

    def homeContent(self, filter):
        # 所有分类展平为一级分类
        classes = [
            # 视频一区
            {"type_id": "45", "type_name": "视频一区"},
            {"type_id": "55", "type_name": "国产乱伦"},
            {"type_id": "50", "type_name": "无码流出"},
            {"type_id": "51", "type_name": "日本高清"},
            {"type_id": "52", "type_name": "中文字幕"},
            {"type_id": "53", "type_name": "欧美极品"},
            {"type_id": "54", "type_name": "动漫精品"},
            {"type_id": "56", "type_name": "SM变态"},
            {"type_id": "57", "type_name": "自拍偷拍"},
            # 视频二区
            {"type_id": "46", "type_name": "视频二区"},
            {"type_id": "49", "type_name": "国产精品"},
            {"type_id": "65", "type_name": "国产热瓜"},
            {"type_id": "64", "type_name": "主播诱惑"},
            {"type_id": "63", "type_name": "良家少女"},
            {"type_id": "61", "type_name": "淫荡熟女"},
            {"type_id": "62", "type_name": "三级伦理"},
            {"type_id": "58", "type_name": "旗袍风情"},
            {"type_id": "59", "type_name": "岛国小女"},
            # 视频三区
            {"type_id": "47", "type_name": "视频三区"},
            {"type_id": "68", "type_name": "剧情解说"},
            {"type_id": "71", "type_name": "网红黑料"},
            {"type_id": "73", "type_name": "暴++小学生"},
            {"type_id": "70", "type_name": "同性世界"},
            {"type_id": "72", "type_name": "国产高清"},
            {"type_id": "69", "type_name": "美乳妹妹"},
            {"type_id": "67", "type_name": "黑料网曝"},
            {"type_id": "66", "type_name": "国产探花"},
            # 传媒系列
            {"type_id": "202", "type_name": "麻豆传媒"},
            {"type_id": "205", "type_name": "天美传媒"},
            {"type_id": "206", "type_name": "果冻传媒"},
            {"type_id": "207", "type_name": "91制片厂"},
            {"type_id": "208", "type_name": "蜜桃传媒"},
            {"type_id": "209", "type_name": "精东影业"},
            {"type_id": "210", "type_name": "皇家华人"},
            {"type_id": "223", "type_name": "星空传媒"},
            # 女优系列
            {"type_id": "401", "type_name": "梦乃爱华"},
            {"type_id": "402", "type_name": "波多野结衣"},
            {"type_id": "404", "type_name": "河北彩花"},
            {"type_id": "409", "type_name": "桃乃木香奈"},
            {"type_id": "412", "type_name": "相泽南"},
            {"type_id": "414", "type_name": "Miru"},
            {"type_id": "419", "type_name": "木下日葵"},
            {"type_id": "429", "type_name": "明里紬"},
            # 日本番号
            {"type_id": "301", "type_name": "200GANA"},
            {"type_id": "302", "type_name": "300MIUM"},
            {"type_id": "308", "type_name": "300MAAN"},
            {"type_id": "309", "type_name": "300NTK"},
            {"type_id": "313", "type_name": "336KNB"},
            {"type_id": "329", "type_name": "AARM"},
            {"type_id": "345", "type_name": "DVAJ"},
            {"type_id": "326", "type_name": "MUDR"},
            # 探花系列
            {"type_id": "513", "type_name": "探花-酒店"},
            {"type_id": "514", "type_name": "探花-小宝寻花"},
            {"type_id": "516", "type_name": "91系列"},
            {"type_id": "515", "type_name": "午夜寻花"},
            {"type_id": "501", "type_name": "91沈先生"},
            {"type_id": "502", "type_name": "文轩探花"},
            {"type_id": "503", "type_name": "千人斩"},
            {"type_id": "509", "type_name": "李寻欢探花"},
        ]
        
        return {
            "class": classes,
            "filters": {}
        }

    # ============================================================
    # 首页推荐视频
    # ============================================================

    def homeVideoContent(self):
        result = {"list": [], "page": 1, "pagecount": 1, "limit": 24, "total": 0}
        html_text = self._fetch("/")
        if html_text:
            result["list"] = self._parse_video_items(html_text)
            result["total"] = len(result["list"])
        return result

    # ============================================================
    # 分类页视频列表
    # ============================================================

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": int(pg), "pagecount": 1, "limit": 24, "total": 0}

        if int(pg) <= 1:
            url = f"/vodtype/{tid}/"
        else:
            url = f"/vodtype/{tid}-{pg}/"

        print(f"[{self.name}] 请求分类页: {url}")

        html_text = self._fetch(url)
        if not html_text:
            return result

        videos = self._parse_video_items(html_text)
        result["list"] = videos

        page_info = re.search(r'共\d+条数据,当前(\d+)/(\d+)页', html_text)
        if page_info:
            result["pagecount"] = int(page_info.group(2))
        else:
            page_links = re.findall(r'/vodtype/\d+-(\d+)/', html_text)
            if page_links:
                result["pagecount"] = max([int(p) for p in page_links])
            else:
                result["pagecount"] = 1

        result["total"] = len(videos)
        return result

    # ============================================================
    # 详情页 (只提取标题和封面，播放地址指向播放页)
    # ============================================================

    def detailContent(self, ids):
        vid = ids[0] if isinstance(ids, list) else ids
        result = {"list": []}

        if not vid:
            return result

        detail_url = f"/voddetail/{vid}/"
        html_text = self._fetch(detail_url)

        if not html_text:
            return result

        # 提取标题
        title = f"视频 {vid}"
        title_match = re.search(r'<h1[^>]*>(.*?)</h1>', html_text)
        if not title_match:
            title_match = re.search(r'<title>(.*?)</title>', html_text)
        if title_match:
            title = clean_text(title_match.group(1))

        # 提取封面图
        pic = ""
        pic_match = re.search(r'<img[^>]*class="[^"]*detail-poster[^"]*"[^>]*src="([^"]+)"', html_text)
        if not pic_match:
            pic_match = re.search(r'<img[^>]*src="([^"]+)"[^>]*alt="[^"]*"', html_text)
        if pic_match:
            pic = fix_url(pic_match.group(1), self.host)

        # 关键：vod_play_url 指向播放页
        play_url = f"/vodplay/{vid}-1-1/"

        vod_data = {
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": pic,
            "vod_content": "",
            "vod_play_from": "默认线路",
            "vod_play_url": f"默认线路${play_url}",
        }

        result["list"].append(vod_data)
        return result

    # ============================================================
    # 播放页解析 (提取真实的 m3u8 地址)
    # ============================================================

    def playerContent(self, flag, id, vipFlags=None):
        result = {"parse": 0, "playUrl": "", "url": "", "header": ""}

        if self.isVideoFormat(id):
            result["url"] = id
            result["header"] = json.dumps({
                "Referer": self.host + "/",
                "User-Agent": self.user_agent
            })
            return result

        if not id.startswith('http'):
            id = urljoin(self.host, id)

        print(f"[{self.name}] 请求播放页: {id}")

        html_text = self._fetch(id)
        if not html_text:
            result["url"] = id
            return result

        # 方法1：贪心匹配 player_aaaa
        player_pattern = r'player_aaaa\s*=\s*(\{.*?\});'
        player_match = re.search(player_pattern, html_text, re.DOTALL)
        
        if player_match:
            try:
                json_str = player_match.group(1)
                json_str = json_str.replace('\\/', '/')
                player_data = json.loads(json_str)
                play_url = player_data.get('url', '')
                
                if play_url:
                    result["url"] = play_url
                    result["header"] = json.dumps({
                        "Referer": self.host + "/",
                        "User-Agent": self.user_agent
                    })
                    print(f"[{self.name}] ✅ 提取到播放地址: {play_url}")
                    return result
            except json.JSONDecodeError as e:
                print(f"[{self.name}] JSON 解析失败: {e}")
                url_match = re.search(r'"url"\s*:\s*"([^"]+)"', player_match.group(1))
                if url_match:
                    play_url = url_match.group(1).replace('\\/', '/')
                    if play_url:
                        result["url"] = play_url
                        result["header"] = json.dumps({
                            "Referer": self.host + "/",
                            "User-Agent": self.user_agent
                        })
                        print(f"[{self.name}] ✅ 正则提取到播放地址: {play_url}")
                        return result

        # 方法2：直接用正则提取 url 字段（兜底）
        url_match = re.search(r'"url"\s*:\s*"([^"]+)"', html_text)
        if url_match:
            play_url = url_match.group(1).replace('\\/', '/')
            if play_url:
                result["url"] = play_url
                result["header"] = json.dumps({
                    "Referer": self.host + "/",
                    "User-Agent": self.user_agent
                })
                print(f"[{self.name}] ✅ 兜底提取到播放地址: {play_url}")
                return result

        # 方法3：直接匹配 m3u8 地址
        m3u8_pattern = r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)'
        m3u8_match = re.search(m3u8_pattern, html_text)
        if m3u8_match:
            play_url = m3u8_match.group(1)
            result["url"] = play_url
            result["header"] = json.dumps({
                "Referer": self.host + "/",
                "User-Agent": self.user_agent
            })
            print(f"[{self.name}] ✅ 直接匹配到 m3u8: {play_url}")
            return result

        print(f"[{self.name}] ❌ 未能提取到播放地址，返回原始 URL")
        result["url"] = id
        return result

    # ============================================================
    # 搜索功能
    # ============================================================

    def searchContent(self, key, quick, pg="1"):
        result = {"list": [], "page": int(pg), "pagecount": 1, "limit": 24, "total": 0}
        
        if not key:
            return result

        search_url = f"/vodsearch/-------------/?wd={quote(key)}"
        if int(pg) > 1:
            search_url += f"&page={pg}"

        html_text = self._fetch(search_url)
        if html_text:
            videos = self._parse_video_items(html_text)
            result["list"] = videos
            result["total"] = len(videos)

            page_info = re.search(r'共\d+条数据,当前(\d+)/(\d+)页', html_text)
            if page_info:
                result["pagecount"] = int(page_info.group(2))
            else:
                page_links = re.findall(r'page=(\d+)', html_text)
                if page_links:
                    result["pagecount"] = max([int(p) for p in page_links])

        return result