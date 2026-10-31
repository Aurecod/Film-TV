#!/usr/bin/python
# coding=utf-8
import sys
import re
import concurrent.futures
from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    

    def init(self, extend=""):
        self.session = Session()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://waptap.com/',
            'Origin': 'https://waptap.com',
            'Connection': 'keep-alive',
        }
        self.session.headers.update(self.headers)

        retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

        self.api_base = "https://api.waptap.com/v1/media"
        self.base_params = {
            'show_adult_content': '4',
            'filter_content_gender': 'female,male',
            'type': 'feed-v3'
        }

        # 缓存每页的视频元数据（不含 url 或含临时 url，详情页会实时刷新）
        self.page_cache = {}
        self.MAX_CACHE_SIZE = 50 # 由于每次请求5页，稍微调大缓存上限

        # 定义每个合集包含的 API 页数
        self.group_size = 5

    def getName(self):
        return "Waptap"

    def homeContent(self, filter):
        result = {}
        categories = {
            "🔥 推荐": "recommended",
        }
        result['class'] = [{'type_id': v, 'type_name': k} for k, v in categories.items()]
        result['filters'] = {}
        return result

    def _fetch_video_list(self, tid, page, use_cache=True):
        """获取指定页的视频列表，返回包含完整信息的列表（含 video_id 和实时 url）"""
        cache_key = f"{tid}_{page}"
        if use_cache and cache_key in self.page_cache:
            return self.page_cache[cache_key].copy()

        params = self.base_params.copy()
        params['page'] = page

        try:
            response = self.session.get(self.api_base, params=params, timeout=15)
            if response.status_code != 200:
                print(f"Waptap 请求失败: {response.status_code}")
                return []
            data = response.json()
            if data.get('code') != 200:
                print(f"Waptap API 错误: {data.get('status')}")
                return []

            items = data.get('data', {}).get('items', [])
            if not items:
                return []

            video_list = []
            for item in items:
                file_data = item.get('file_data', {})
                video_url = file_data.get('url', '')
                if not video_url:
                    continue

                title = item.get('description', '无标题')
                if not title or title.strip() == '':
                    title = f"视频 {item.get('_id', '')[-6:]}"
                title = re.sub(r'\s+', ' ', title).strip()

                cover = file_data.get('cover_url', item.get('cover', ''))
                video_id = item.get('_id', '')

                video_list.append({
                    "name": title,
                    "url": video_url,
                    "pic": cover,
                    "video_id": video_id,
                    "duration": file_data.get('duration', 0),
                    "like_count": item.get('like_count', 0),
                    "visit_count": item.get('visit_count', 0)
                })

            if use_cache:
                if len(self.page_cache) >= self.MAX_CACHE_SIZE:
                    keys_to_remove = list(self.page_cache.keys())[:self.MAX_CACHE_SIZE // 2]
                    for k in keys_to_remove:
                        del self.page_cache[k]
                self.page_cache[cache_key] = video_list

            return video_list
        except Exception as e:
            print(f"_fetch_video_list 异常 (页码:{page}): {e}")
            return []

    def _get_total_pages(self):
        """获取总页数（通过请求第一页的 _meta）"""
        try:
            params = self.base_params.copy()
            params['page'] = 1
            resp = self.session.get(self.api_base, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                meta = data.get('data', {}).get('_meta', {})
                return meta.get('page_count', 1)
        except Exception as e:
            print(f"获取总页数失败: {e}")
        return 1

    def categoryContent(self, tid, pg, filter, extend):
        result = {}
        ui_page = int(pg) if pg else 1
        sort = tid

        # 计算对应的 API 起始页 (例如 UI第1页 -> API第1页)
        start_api_page = (ui_page - 1) * self.group_size + 1
        end_api_page = ui_page * self.group_size

        # 分类页只需获取这一组的第一页来展示封面，避免请求阻塞
        video_list = self._fetch_video_list(sort, start_api_page, use_cache=True)
        if not video_list:
            return self._empty_result(ui_page)

        first_pic = video_list[0].get('pic', '') if video_list else ''
        
        # 重新计算总页数，将 API 的总页数转换为 UI 组合后的总页数
        total_api_pages = self._get_total_pages()
        total_ui_pages = (total_api_pages + self.group_size - 1) // self.group_size

        # 将 UI 页码传入详情页
        vid = f"collection|{sort}|{ui_page}"
        vlist = [{
            'vod_id': vid,
            'vod_name': f"Waptap 合集 {ui_page} (页{start_api_page}-{end_api_page})",
            'vod_pic': first_pic,
            'vod_remarks': f"天空飘来 {self.group_size} 个字，那都不是事。"
        }]

        result['list'] = vlist
        result['page'] = ui_page
        result['total'] = total_ui_pages
        result['limit'] = 1
        return result

    def detailContent(self, ids):
        vid = ids[0]
        if not vid.startswith("collection|"):
            return {'list': []}
        parts = vid.split('|')
        if len(parts) != 3:
            return {'list': []}
        _, tid, ui_page_str = parts
        ui_page = int(ui_page_str)

        start_api_page = (ui_page - 1) * self.group_size + 1
        end_api_page = ui_page * self.group_size

        video_list = []
        
        # 使用多线程并发获取 5 页的数据，大幅降低详情页解析延迟
        results_map = {p: [] for p in range(start_api_page, end_api_page + 1)}
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.group_size) as executor:
            future_to_page = {
                executor.submit(self._fetch_video_list, tid, p, use_cache=False): p 
                for p in range(start_api_page, end_api_page + 1)
            }
            
            for future in concurrent.futures.as_completed(future_to_page):
                p = future_to_page[future]
                try:
                    results_map[p] = future.result()
                except Exception as e:
                    print(f"多线程获取第{p}页详情失败: {e}")

        # 按照页码顺序将多线程的结果拼接到主列表中
        for p in range(start_api_page, end_api_page + 1):
            if results_map[p]:
                video_list.extend(results_map[p])
            else:
                # 兜底：尝试从缓存获取
                cache_key = f"{tid}_{p}"
                cached = self.page_cache.get(cache_key, [])
                video_list.extend(cached)

        if not video_list:
            print(f"Waptap 详情页无数据: {vid}")
            return {'list': []}

        # 转义标题中的分隔符 $ 和 #，防止破坏选集格式
        def escape_title(t):
            t = t.replace('$', '￥')
            t = t.replace('#', '＃')
            return t

        play_urls = []
        for i, v in enumerate(video_list, 1):
            # 为防止名字重复导致部分播放器选集覆盖，加入序号
            name_text = escape_title(v['name'][:60] if len(v['name']) > 60 else v['name'])
            name = f"{i:02d}. {name_text}"
            
            combined_url = f"{v['url']}|{v.get('video_id', '')}"
            play_urls.append(f"{name}${combined_url}")

        vod_play_url = "#".join(play_urls)
        first = video_list[0]
        vod = {
            'vod_id': vid,
            'vod_name': f"Waptap 合集 {ui_page}",
            'vod_pic': first['pic'],
            'vod_content': f"本合集包含了 API 第 {start_api_page} 到 {end_api_page} 页的数据，共收集 {len(video_list)} 个短视频。",
            'vod_play_from': 'Waptap',
            'vod_play_url': vod_play_url,
            'vod_player': '短'
        }
        return {'list': [vod]}

    def playerContent(self, flag, id, vipFlags):
        """
        id 可能为：原始URL 或 原始URL|video_id
        """
        original_url = id
        video_id = None
        if '|' in id:
            parts = id.split('|')
            original_url = parts[0]
            if len(parts) > 1:
                video_id = parts[1]

        player_headers = {
            'User-Agent': self.headers['User-Agent'],
            'Referer': 'https://waptap.com/',
            'Origin': 'https://waptap.com',
            'Accept': 'video/mp4,video/webm,video/*;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'identity',
            'Connection': 'keep-alive',
        }

        final_url = original_url
        if video_id:
            fresh_url = self._refresh_video_url(video_id)
            if fresh_url:
                final_url = fresh_url
                print(f"刷新视频链接成功: {video_id} -> {fresh_url[:80]}...")
            else:
                print(f"刷新视频链接失败，使用原链接: {video_id}")

        return {
            'parse': 0,
            'url': final_url,
            'header': player_headers,
            'content-type': 'video/mp4'
        }

    def _refresh_video_url(self, video_id):
        """根据视频ID尝试获取最新直链"""
        try:
            url = f"https://api.waptap.com/v1/media/{video_id}"
            resp = self.session.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('code') == 200:
                    file_data = data.get('data', {}).get('file_data', {})
                    new_url = file_data.get('url')
                    if new_url:
                        return new_url
        except Exception as e:
            print(f"刷新视频链接异常: {e}")
        return None

    def _empty_result(self, page):
        return {
            'list': [],
            'page': page,
            'total': 0,
            'limit': 1
        }
