#coding=utf-8
import urllib.request
import urllib.parse
import re
import ssl
import gzip

from base.spider import Spider

class Spider(Spider):
    def getName(self):
        return "Hanime1（免翻）"

    def init(self, extend=""):
        """
        模块 1：初始化与防失联模块
        """
        self.siteUrl = "https://www.hanime999.cc" 
        
        cached_node = self.getCache("custom_domain_cache")
        if cached_node:
            self.siteUrl = cached_node
            
        self.auth_cookie = "x-index-auth=authed"
        
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Accept-Encoding": "gzip, deflate",
            "Cookie": self.auth_cookie,
            "Referer": self.siteUrl + "/"
        }

    def _fetch_html(self, url):
        """
        内部辅助方法：处理网络请求与 Gzip 脱壳
        """
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        req = urllib.request.Request(url, headers=self.headers)
        try:
            resp = urllib.request.urlopen(req, context=context, timeout=15)
            data = resp.read()
            if resp.info().get('Content-Encoding', '').lower() == 'gzip':
                data = gzip.decompress(data)
            return data.decode('utf-8', errors='ignore')
        except Exception:
            return ""

    def homeContent(self, filter):
        """
        模块 2：分类路由模块 (首页映射)
        """
        result = {}
        classes = [
            {"type_name": "里番", "type_id": "裏番"},
            {"type_name": "泡面番", "type_id": "泡麵番"},
            {"type_name": "Motion Anime", "type_id": "Motion Anime"},
            {"type_name": "3DCG", "type_id": "3DCG"},
            {"type_name": "2.5D", "type_id": "2.5D"},
            {"type_name": "AI生成", "type_id": "AI生成"},
            {"type_name": "MMD", "type_id": "MMD"},
            {"type_name": "Cosplay", "type_id": "Cosplay"},
            {"type_name": "新番预告", "type_id": "新番預告"},
            {"type_name": "2D动画", "type_id": "2D動畫"}
        ]
        
        result['class'] = classes
        return result

    def categoryContent(self, tid, pg, filter, extend):
        """
        模块 3：UI卡片解析模块 (终极万能切片法：极速+全兼容)
        """
        result = {}
        encoded_tid = urllib.parse.quote(tid)
        target_url = f"{self.siteUrl}/search?genre={encoded_tid}&page={pg}"
        html = self._fetch_html(target_url)
        
        videos = []
        seen_ids = set()
        
        # 极速核心：用所有视频共有的 URL 标识直接切碎网页
        blocks = html.split('/watch?v=')
        
        # block[0] 是网页头部，直接从 block[1] 开始遍历
        for block in blocks[1:]:
            # 切片后，开头紧接着的就是视频 ID
            id_match = re.match(r'^([^"&]+)', block)
            if not id_match:
                continue
            vod_id = id_match.group(1)
            
            # 去重：防止同一个视频在源码里出现多次
            if vod_id in seen_ids:
                continue
            seen_ids.add(vod_id)
            
            # 性能优化：稍微放大一点切片范围到 1200 字，防止长内容被腰斩
            chunk = block[:1200]
            
            pic = ""
            pic_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', chunk, re.IGNORECASE)
            if pic_match:
                pic = pic_match.group(1)
                
            # 4. 抓标题：改为更强壮的 [^<]+ 匹配，只抓纯文本，无视结尾标签是否残缺
            title = ""
            t_match_b = re.search(r'home-rows-videos-title[^>]*>\s*([^<]+)', chunk)
            if t_match_b:
                title = t_match_b.group(1).strip()
            else:
                t_match_a = re.search(r'class="title"[^>]*>\s*([^<]+)', chunk)
                if t_match_a:
                    title = t_match_a.group(1).strip()
                    
            if not title:
                title = "未知标题"


                
                        # 5. 抓取真实徽章信息 (不造假，有什么显什么)
            remarks_list = []
            
            # 抓时长 (如: 10:09)
            duration_match = re.search(r'class="duration"[^>]*>\s*([^<]+)\s*</div>', chunk)
            if duration_match:
                remarks_list.append(duration_match.group(1).strip())
                
            # 抓播放量 (如: 4.4万次)
            views_match = re.search(r'class="stat-item">\s*([0-9\.]+万?次)\s*</div>', chunk)
            if views_match:
                remarks_list.append(views_match.group(1).strip())
                
            # 拼接显示：如果有数据就用" | "隔开，如果全都没有（如里番）就直接留空，保持 UI 清爽
            remarks = " | ".join(remarks_list)

                
            # 【高级技巧：ID透传】把标题和图片绑在 ID 上一起传给详情页
            packed_id = f"{vod_id}@@@{title}@@@{pic}"
            
            videos.append({
                "vod_id": packed_id,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": remarks
            })

            
        result['list'] = videos
        result['page'] = pg
        result['pagecount'] = 9999
        result['limit'] = 90
        result['total'] = 999999
        return result


    def detailContent(self, array):
        """
        模块 4：播放直连模块 (ID透传终极版，100%同步封面标题)
        """
        try:
            if not hasattr(self, 'siteUrl') or not hasattr(self, 'headers'):
                self.init()

            if isinstance(array, str):
                raw_id = array
            else:
                try:
                    raw_id = str(array[0])
                except Exception:
                    raw_id = str(array)
                    
            # 1. 拆包透传数据：分离出真正的 ID、封面标题、封面图片
            passed_title = ""
            passed_pic = ""
            if "@@@" in raw_id:
                parts = raw_id.split("@@@")
                vod_id = parts[0]
                if len(parts) > 1: passed_title = parts[1]
                if len(parts) > 2: passed_pic = parts[2]
            else:
                vod_id = raw_id
                
            target_url = f"{self.siteUrl}/watch?v={vod_id}"
            html = self._fetch_html(target_url)

            # 2. 直接使用透传过来的封面标题！只有在透传失败时才去网页里捞
            if passed_title:
                title = passed_title
            else:
                title_match = re.search(r'<title>(.*?)</title>', html)
                title = re.split(r'&nbsp;-|-', title_match.group(1))[0].strip() if title_match else vod_id

            # 3. 直接使用透传过来的封面图片
            if passed_pic:
                pic = passed_pic
            else:
                pic_match = re.search(r'<meta property="og:image" content="([^"]+)"', html)
                pic = pic_match.group(1) if pic_match else ""

            # 提取直链并智能解析分辨率
            source_matches = re.findall(r'<source[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
            
            parsed_links = []
            for link in set(source_matches):
                # 从链接中提取画质标识 (如 1080p, 720p)
                res_match = re.search(r'(\d+p)', link, re.IGNORECASE)
                if res_match:
                    quality = res_match.group(1).upper() # 自动转为大写，比如 1080P
                    # 提取出纯数字(如1080)，用来做排序权重
                    weight = int(res_match.group(1)[:-1])
                else:
                    quality = "默认画质"
                    weight = 0
                
                parsed_links.append((weight, quality, link))
                
            # 根据数字权重，将画质从高到低排序 (保证 1080P 永远在最前面)
            parsed_links.sort(key=lambda x: x[0], reverse=True)
            
            play_list = []
            for item in parsed_links:
                play_list.append(f"{item[1]}${item[2]}")
                
            play_url = "#".join(play_list)
            if not play_url:
                play_url = "解析失败$http://错误.mp4"


            vod = {
                "vod_id": vod_id,
                "vod_name": title,  # 这里用的就是 100% 纯正的封面标题！
                "vod_pic": pic,
                "vod_type": "通用分类",
                "vod_year": "",      
                "vod_area": "",      
                "vod_actor": "",     
                "vod_remarks": "高清",
                "vod_director": "YJ-Gemini",
                "vod_content": "",
                "vod_play_from": "YJ-Gemini 专线",
                "vod_play_url": play_url
            }
            
            return {'list': [vod]}
            
        except Exception as e:
            return {
                'list': [{
                    "vod_id": "error",
                    "vod_name": f"【底层崩溃，请截图】报错原因: {str(e)}",
                    "vod_pic": "",
                    "vod_type": "诊断模式",
                    "vod_remarks": "致命异常",
                    "vod_director": f"参数类型: {type(array)}",
                    "vod_play_from": "系统级诊断追踪",
                    "vod_play_url": "点我看报错$http://error.mp4"
                }]
            }


    def searchContent(self, key, quick, pg="1"):
        """
        模块 5：搜索模块 (终极万能切片法同理)
        """
        result = {}
        encoded_key = urllib.parse.quote(key)
        target_url = f"{self.siteUrl}/search?query={encoded_key}&page={pg}"
        html = self._fetch_html(target_url)
        
        videos = []
        seen_ids = set()
        
        blocks = html.split('/watch?v=')
        for block in blocks[1:]:
            id_match = re.match(r'^([^"&]+)', block)
            if not id_match:
                continue
            vod_id = id_match.group(1)
            
            if vod_id in seen_ids:
                continue
            seen_ids.add(vod_id)
            
            # 性能优化：稍微放大一点切片范围到 1200 字，防止长内容被腰斩
            chunk = block[:1200]
            
            pic = ""
            pic_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', chunk, re.IGNORECASE)
            if pic_match:
                pic = pic_match.group(1)
                
            # 4. 抓标题：改为更强壮的 [^<]+ 匹配，只抓纯文本，无视结尾标签是否残缺
            title = ""
            t_match_b = re.search(r'home-rows-videos-title[^>]*>\s*([^<]+)', chunk)
            if t_match_b:
                title = t_match_b.group(1).strip()
            else:
                t_match_a = re.search(r'class="title"[^>]*>\s*([^<]+)', chunk)
                if t_match_a:
                    title = t_match_a.group(1).strip()
                    
            if not title:
                title = "未知标题"


                
                        # 5. 抓取真实徽章信息 (不造假，有什么显什么)
            remarks_list = []
            
            # 抓时长 (如: 10:09)
            duration_match = re.search(r'class="duration"[^>]*>\s*([^<]+)\s*</div>', chunk)
            if duration_match:
                remarks_list.append(duration_match.group(1).strip())
                
            # 抓播放量 (如: 4.4万次)
            views_match = re.search(r'class="stat-item">\s*([0-9\.]+万?次)\s*</div>', chunk)
            if views_match:
                remarks_list.append(views_match.group(1).strip())
                
            # 拼接显示：如果有数据就用" | "隔开，如果全都没有（如里番）就直接留空，保持 UI 清爽
            remarks = " | ".join(remarks_list)

                
            # 【高级技巧：ID透传】把标题和图片绑在 ID 上一起传给详情页
            packed_id = f"{vod_id}@@@{title}@@@{pic}"
            
            videos.append({
                "vod_id": packed_id,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": remarks
            })

            
        result['list'] = videos
        result['page'] = pg
        return result


    def playerContent(self, flag, id, vipFlags):
        """
        模块 6：解密引擎与防盗链模块
        """
        result = {}
        
        play_headers = {
            "User-Agent": self.headers["User-Agent"],
            "Referer": self.headers["Referer"], 
            "Cookie": self.headers["Cookie"]
        }
        
        result["parse"] = 0
        result["playUrl"] = ""
        result["url"] = id
        result["header"] = play_headers
        return result
