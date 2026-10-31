from base.spider import Spider
import requests
import re
import time
import hashlib
import urllib.parse
from urllib.parse import urlencode
import json

API_BASE = "https://api.bilibili.com"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
    'Referer': 'https://www.bilibili.com/',
    
}
TIMEOUT = 10
MAX_RETRIES = 3

CLASS_LIST = [
    {"type_name": "AI短剧", "type_id": "AI短剧"},
    {"type_name": "番剧", "type_id": "番剧"},
    {"type_name": "纪录片", "type_id": "纪录片"},
    {"type_name": "音乐", "type_id": "音乐"},
    {"type_name": "科技数码", "type_id": "科技数码"},
    {"type_name": "直播", "type_id": "直播"},
]

FILTER_COMMON = [
    {
        "key": "order",
        "name": "排序",
        "value": [
            {"n": "最多点击", "v": "click"},
            {"n": "最新发布", "v": "pubdate"},
            {"n": "最多弹幕", "v": "dm"},
            {"n": "最多收藏", "v": "stow"}
        ]
    },
    {
        "key": "duration",
        "name": "时长",
        "value": [
            {"n": "全部", "v": "0"},
            {"n": "60分钟以上", "v": "4"},
            {"n": "30~60分钟", "v": "3"},
            {"n": "10~30分钟", "v": "2"},
            {"n": "10分钟以下", "v": "1"}
        ]
    }
]

FILTERS = {
    "AI短剧": FILTER_COMMON,
    "番剧": FILTER_COMMON,
    "纪录片": FILTER_COMMON,
    "音乐": FILTER_COMMON,
    "科技数码": FILTER_COMMON,
    "直播": []
}

class Spider(Spider):
    def getName(self):
        return "哔哩哔哩"

    def init(self, extend):
        self.live_areas_cache = None

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def _fix_pic_url(self, url):
        if not url:
            return ''
        url = url.strip()
        if url.startswith('//'):
            return 'https:' + url
        if url.startswith('http://'):
            return url.replace('http://', 'https://')
        return url

    def _get_wbi_keys(self):
        try:
            url = f"{API_BASE}/x/web-interface/nav"
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if resp.status_code != 200:
                return None, None
            data = resp.json()
            if data.get('code') != 0:
                return None, None
            wbi_img = data.get('data', {}).get('wbi_img', {})
            img_url = wbi_img.get('img_url', '')
            sub_url = wbi_img.get('sub_url', '')
            img_key = img_url.split('/')[-1].split('.')[0] if img_url else ''
            sub_key = sub_url.split('/')[-1].split('.')[0] if sub_url else ''
            return img_key, sub_key
        except Exception:
            return None, None

    def _encrypt_wbi(self, params, img_key, sub_key):
        if not img_key or not sub_key:
            return params
        mix_key = sub_key[:4] + img_key[:4]
        sorted_params = sorted(params.items())
        query = urlencode(sorted_params)
        sign = hashlib.md5((query + mix_key).encode()).hexdigest()
        params['w_rid'] = sign
        params['wts'] = int(time.time())
        return params

    def _wbi_request(self, url, params=None):
        if params is None:
            params = {}
        img_key, sub_key = self._get_wbi_keys()
        if img_key and sub_key:
            params = self._encrypt_wbi(params, img_key, sub_key)
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
            return resp
        except Exception:
            return None

    def _get_live_areas(self):
        if self.live_areas_cache:
            return self.live_areas_cache
        try:
            url = "https://api.live.bilibili.com/room/v1/Area/getList"
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if resp.status_code != 200:
                return []
            data = resp.json()
            if data.get('code') != 0:
                return []
            raw = data.get('data', [])
            areas = []
            if isinstance(raw, list):
                areas = raw
            elif isinstance(raw, dict):
                areas = raw.get('list', [])
            result = []
            for a in areas:
                if 'id' in a and 'name' in a:
                    result.append({'id': str(a['id']), 'name': a['name']})
            self.live_areas_cache = result
            return result
        except Exception:
            return []

    def _build_live_filter(self):
        areas = self._get_live_areas()
        if not areas:
            areas = [{'id': '0', 'name': '全部'}]
        order_value = [
            {"n": "人气排序", "v": "online"},
            {"n": "最新开播", "v": "live_time"}
        ]
        priority_names = ["影视", "音乐", "赛事", "游戏"]
        priority_areas = []
        other_areas = []
        for a in areas:
            if a['name'] in priority_names:
                priority_areas.append(a)
            else:
                other_areas.append(a)
        sorted_areas = priority_areas + other_areas
        area_value = [{"n": a['name'], "v": a['id']} for a in sorted_areas]
        return [
            {"key": "order", "name": "排序", "value": order_value},
            {"key": "area", "name": "分区", "value": area_value}
        ]

    def homeContent(self, filter):
        FILTERS['直播'] = self._build_live_filter()
        return {
            "class": CLASS_LIST,
            "filters": FILTERS
        }

    def homeVideoContent(self):
        return {'list': []}

    def _search_videos(self, keyword, page=1, order='click', duration='0'):
        try:
            page = int(page) if page else 1
            params = {
                'keyword': keyword,
                'page': page,
                'search_type': 'video'
            }
            if order and order != '0':
                params['order'] = order
            if duration and duration != '0':
                params['duration'] = duration

            url = f"{API_BASE}/x/web-interface/wbi/search/type"
            resp = self._wbi_request(url, params)
            if not resp or resp.status_code != 200:
                resp = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
                if resp.status_code != 200:
                    return {'list': [], 'page': page, 'pagecount': 1, 'limit': 0, 'total': 0}

            data = resp.json()
            if data.get('code') != 0:
                return {'list': [], 'page': page, 'pagecount': 1, 'limit': 0, 'total': 0}

            result = data.get('data', {}).get('result', [])
            videos = []
            for item in result:
                try:
                    bvid = item.get('bvid', '')
                    if not bvid:
                        continue
                    title = re.sub(r'<em[^>]*>|</em>', '', item.get('title', '无标题'))
                    videos.append({
                        "vod_id": bvid,
                        "vod_name": title,
                        "vod_pic": self._fix_pic_url(item.get('pic', '')),
                        "vod_remarks": self._format_duration(item.get('duration', 0)),
                        "vod_content": item.get('description', '')[:50]
                    })
                except Exception:
                    continue

            page_info = data.get('data', {}).get('page', {})
            total = page_info.get('total', 0) if isinstance(page_info, dict) else 0
            pages = page_info.get('pages', 1) if isinstance(page_info, dict) else 1

            return {
                'list': videos,
                'page': page,
                'pagecount': pages,
                'limit': len(videos),
                'total': total
            }
        except Exception:
            return {'list': [], 'page': page, 'pagecount': 1, 'limit': 0, 'total': 0}

    def _get_live_list(self, page=1, ext=None):
        if ext is None:
            ext = {}
        area = ext.get('area', '0')
        order = ext.get('order', 'online')
        try:
            page = int(page) if page else 1
            url = "https://api.live.bilibili.com/room/v1/Area/getRoomList"
            params = {
                'area_id': int(area),
                'page': page,
                'page_size': 20
            }
            resp = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
            if resp.status_code != 200:
                if area != '0':
                    return self._get_live_list(page, {'area': '0', 'order': order})
                else:
                    return {'list': []}
            data = resp.json()
            if data.get('code') != 0:
                if area != '0':
                    return self._get_live_list(page, {'area': '0', 'order': order})
                else:
                    return {'list': []}

            raw_data = data.get('data', [])
            rooms = []
            if isinstance(raw_data, dict):
                rooms = raw_data.get('list', [])
                total = raw_data.get('total', 0)
            elif isinstance(raw_data, list):
                rooms = raw_data
                total = len(rooms)
            else:
                if area != '0':
                    return self._get_live_list(page, {'area': '0', 'order': order})
                else:
                    return {'list': []}

            if not rooms:
                if area != '0':
                    return self._get_live_list(page, {'area': '0', 'order': order})
                else:
                    return {'list': []}

            videos = []
            for room in rooms:
                try:
                    roomid = room.get('roomid') or room.get('room_id')
                    if not roomid:
                        continue
                    title = room.get('title', '无标题')
                    cover = room.get('cover', room.get('cover_url', ''))
                    uname = room.get('uname', '')
                    online = room.get('online', room.get('online_count', 0))
                    vod_id = f"live_{roomid}"
                    videos.append({
                        "vod_id": vod_id,
                        "vod_name": title,
                        "vod_pic": self._fix_pic_url(cover),
                        "vod_remarks": f"在线 {online} 人",
                        "vod_content": f"主播: {uname}",
                        "vod_play_from": "直播",
                        "vod_play_url": f"live:{roomid}"
                    })
                except Exception:
                    continue

            total = total if total > 0 else len(rooms) * 10
            return {
                'list': videos,
                'page': page,
                'pagecount': (total + 19) // 20 if total > 0 else 1,
                'limit': len(videos),
                'total': total
            }
        except Exception:
            if area != '0':
                return self._get_live_list(page, {'area': '0', 'order': order})
            else:
                return {'list': []}

    def categoryContent(self, cid, pg, filter, ext):
        if ext is None:
            ext = {}
        if isinstance(ext, str):
            try:
                ext = json.loads(ext)
            except:
                ext = {}

        if cid == "直播":
            return self._get_live_list(pg, ext)

        order = ext.get('order', 'click')
        duration = ext.get('duration', '0')
        return self._search_videos(cid, pg, order, duration)

    def detailContent(self, ids):
        vod_id = ids[0]
        if not vod_id:
            return {'list': []}

        if vod_id.startswith('live_'):
            roomid = vod_id.replace('live_', '')
            return {
                'list': [{
                    "vod_id": vod_id,
                    "vod_name": "B站直播",
                    "vod_pic": "",
                    "vod_play_from": "直播",
                    "vod_play_url": f"live:{roomid}"
                }]
            }

        return self._video_detail(vod_id)

    def _video_detail(self, bvid):
        try:
            view_url = f"{API_BASE}/x/web-interface/view?bvid={bvid}"
            resp = requests.get(view_url, headers=HEADERS, timeout=TIMEOUT)
            if resp.status_code != 200:
                return {'list': []}
            view_data = resp.json()
            if view_data.get('code') != 0:
                return {'list': []}
            vinfo = view_data.get('data', {})

            title = vinfo.get('title', '')
            pic = self._fix_pic_url(vinfo.get('pic', ''))
            desc = vinfo.get('desc', '')
            author = vinfo.get('owner', {}).get('name', '')
            type_name = "未知分类"

            pages = vinfo.get('pages', [])
            if not pages:
                pages = [{'cid': vinfo.get('cid', 0), 'part': '完整视频'}]

            quality_map = {"超清": 80, "高清": 64, "标清": 32, "流畅": 16}
            play_from = []
            play_url = []
            avid = vinfo.get('aid', 0)

            for qname, qn in quality_map.items():
                urls = []
                for page in pages:
                    cid = page.get('cid', 0)
                    part_name = page.get('part', f'P{len(urls)+1}')
                    play_req_url = f"{API_BASE}/x/player/playurl?avid={avid}&cid={cid}&qn={qn}&type=json"
                    urls.append(f"{part_name}${play_req_url}")
                play_from.append(qname)
                play_url.append("#".join(urls))

            VOD = {
                "vod_id": bvid,
                "vod_name": title,
                "vod_pic": pic,
                "vod_actor": author,
                "type_name": type_name,
                "vod_remarks": f"共{len(pages)}P",
                "vod_content": desc,
                "vod_play_from": "$$$".join(play_from),
                "vod_play_url": "$$$".join(play_url)
            }
            return {'list': [VOD]}
        except Exception:
            return {'list': []}

    def playerContent(self, flag, id, vipFlags):
        if id.startswith('live:'):
            roomid = id.replace('live:', '')
            try:
                live_url = "https://api.live.bilibili.com/room/v1/Room/playUrl"
                params = {'cid': roomid, 'platform': 'h5'}
                resp = requests.get(live_url, params=params, headers=HEADERS, timeout=TIMEOUT)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get('code') == 0:
                        play_info = data.get('data', {})
                        if play_info.get('play_url'):
                            return {"parse": 0, "playUrl": '', "url": play_info['play_url'], "header": HEADERS}
                        durl = play_info.get('durl', [])
                        if durl and len(durl) > 0 and durl[0].get('url'):
                            return {"parse": 0, "playUrl": '', "url": durl[0]['url'], "header": HEADERS}

                live_url2 = "https://api.live.bilibili.com/xlive/web-room/v1/index/getRoomPlayInfo"
                params2 = {'room_id': roomid, 'platform': 'web', 'quality': 4}
                resp2 = requests.get(live_url2, params=params2, headers=HEADERS, timeout=TIMEOUT)
                if resp2.status_code == 200:
                    data2 = resp2.json()
                    if data2.get('code') == 0:
                        play_info2 = data2.get('data', {})
                        for key in ['play_url', 'live_url', 'url']:
                            if play_info2.get(key):
                                return {"parse": 0, "playUrl": '', "url": play_info2[key], "header": HEADERS}
                        durl2 = play_info2.get('durl', [])
                        if durl2 and len(durl2) > 0 and durl2[0].get('url'):
                            return {"parse": 0, "playUrl": '', "url": durl2[0]['url'], "header": HEADERS}
                        stream_info = play_info2.get('stream_info', {})
                        if stream_info and stream_info.get('play_url'):
                            return {"parse": 0, "playUrl": '', "url": stream_info['play_url'], "header": HEADERS}
            except Exception:
                pass
            return {"parse": 0, "playUrl": '', "url": 'about:blank', "header": HEADERS}

        for attempt in range(MAX_RETRIES):
            try:
                resp = requests.get(id, headers=HEADERS, timeout=TIMEOUT)
                if resp.status_code != 200:
                    continue
                data = resp.json()
                if data.get('code') != 0:
                    continue
                dash = data.get('data', {}).get('dash', {})
                if dash:
                    video_list = dash.get('video', [])
                    if video_list:
                        play_url = video_list[0].get('baseUrl', '')
                        if play_url:
                            return {"parse": 0, "playUrl": '', "url": play_url, "header": HEADERS}
                durl = data.get('data', {}).get('durl', [])
                if durl:
                    play_url = durl[0].get('url', '')
                    if play_url:
                        return {"parse": 0, "playUrl": '', "url": play_url, "header": HEADERS}
            except Exception:
                time.sleep(1)
        return {"parse": 0, "playUrl": '', "url": 'about:blank', "header": HEADERS}

    def searchContent(self, key, quick, pg=1):
        result = self._search_videos(key, pg, order='click')
        return result

    def _format_duration(self, seconds):
        if not seconds:
            return "00:00"
        if isinstance(seconds, str):
            if ':' in seconds:
                parts = seconds.split(':')
                try:
                    if len(parts) == 2:
                        m, s = int(parts[0]), int(parts[1])
                    elif len(parts) == 3:
                        h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
                        return f"{h}:{m:02d}:{s:02d}"
                    else:
                        return seconds
                    if m >= 60:
                        h = m // 60
                        m = m % 60
                        return f"{h}:{m:02d}:{s:02d}"
                    else:
                        return f"{m:02d}:{s:02d}"
                except:
                    return seconds
            else:
                try:
                    seconds = int(seconds)
                except:
                    return seconds
        try:
            seconds = int(seconds)
        except:
            return str(seconds)
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"