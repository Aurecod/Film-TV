# coding=utf-8
# !/usr/bin/python
"""
喜福网短剧 - FongMi Spider
- 站: minidrama.contentchina.com
- API: https://minidrama-api.contentchina.com
- 播放: 阿里云 VOD GetPlayInfo, HMAC-SHA1 签名
"""

import requests
import hashlib
import hmac
import base64
import json
import uuid
import time
from datetime import datetime, timezone
from urllib.parse import quote

from base.spider import Spider

# ==================== 常量 ====================
XURL = "https://minidrama-api.contentchina.com"

# API 请求头（走 contentchina 后端 API）
HEADER_API = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/50.0.2661.87 Safari/537.36',
}

# 播放器使用：视频域是公共直链，只需要一个 UA
HEADER_PLAYER = {
    'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
}

UA_BROWSER = HEADER_API['User-Agent']


# ==================== 工具函数 ====================
def _api_get(path, params=None, tries=3):
    """带重试的 GET，返回 response.json()。"""
    url = f"{XURL}{path}"
    last_err = None
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=HEADER_API, timeout=15)
            r.encoding = "utf-8"
            return r.json()
        except Exception as e:
            last_err = e
            time.sleep(0.4 * (i + 1))
    raise last_err


def _hmac_sha1_b64(key_str, data_str):
    """HMAC-SHA1 -> base64 string。"""
    sig = hmac.new(
        key_str.encode('utf-8'),
        data_str.encode('utf-8'),
        hashlib.sha1,
    ).digest()
    return base64.b64encode(sig).decode('utf-8')


# ==================== Spider ====================
class Spider(Spider):

    def getName(self):
        return "喜福短剧"

    def init(self, extend):
        pass

    def isVideoFormat(self, url):
        return True

    def manualVideoCheck(self):
        pass

    # ---------- 首页分类 ----------
    def homeContent(self, filter):
        data = _api_get("/web/v1/home/categoryList", {"isLeft": "1"})
        cats = []
        try:
            for vod in data['data']['categories']:
                cats.append({
                    "type_id": str(vod['id']),
                    "type_name": "喜福·" + str(vod['name']),
                })
        except (KeyError, TypeError):
            pass
        return {"class": cats}

    def homeVideoContent(self):
        # 空实现：分类模式下不需要首页视频
        return {"list": [], "page": 1, "pagecount": 1, "limit": 0, "total": 0}

    # ---------- 分类列表 ----------
    def categoryContent(self, cid, pg, filter, ext):
        try:
            page = int(pg) if pg else 1
        except (ValueError, TypeError):
            page = 1
        data = _api_get("/web/v1/drama/list", {
            "pageSize": "24",
            "currentPage": str(page),
            "filterCategories[]": cid,
        })
        items = []
        try:
            for vod in data['data']['data']:
                total = vod.get('total') or 0
                items.append({
                    "vod_id": f"{vod['albumId']}@{total}",
                    "vod_name": vod.get('title', ''),
                    "vod_pic": vod.get('coverUrl', ''),
                    "vod_remarks": f"共{total}集",
                })
        except (KeyError, TypeError):
            pass
        return {
            "list": items,
            "page": page,
            "pagecount": 9999,
            "limit": 24,
            "total": 999999,
        }

    # ---------- 详情 ----------
    def detailContent(self, ids):
        try:
            raw_id = str(ids[0]) if ids else ""
            base_id, seq_num = raw_id.split("@", 1)
            total = int(seq_num)
        except (TypeError, ValueError, IndexError):
            return {"list": [], "msg": "无效的详情 id"}

        # 生成每一集的播放入口: 每集一个 id, label$内部id
        # FongMi 拆分: $$$ = 多线路, # = 多集, $ = label|url
        episodes = [f"{i}${base_id}@{i}" for i in range(1, total + 1)]
        play_url = "#".join(episodes)

        video_info = {
            "vod_id": raw_id,
            "vod_name": "喜福短剧",
            "vod_play_from": "喜福专线",
            "vod_play_url": play_url,
        }
        return {"list": [video_info]}

    # ---------- 播放解析 ----------
    def playerContent(self, flag, id, vipFlags):
        # 1. 拆 id: "435@1" -> ("435", "1")
        try:
            id = str(id or "")
            album_id, seq = id.split("@", 1)
            album_id = album_id.strip()
            seq = seq.strip()
            if not album_id or not seq:
                raise ValueError("empty part")
        except (ValueError, AttributeError):
            return {
                "parse": 0,
                "jx": 0,
                "msg": f"播放参数异常: {id!r}",
            }

        # 2. 拉播放凭据
        try:
            auth_data = _api_get("/web/v1/drama/play_auth", {
                "albumId": album_id,
                "seq": seq,
            })
        except Exception as e:
            return {"parse": 0, "jx": 0, "msg": f"获取播放凭据失败: {e}"}

        try:
            if auth_data.get('code') != 200:
                return {"parse": 0, "jx": 0, "msg": f"play_auth 返回 code={auth_data.get('code')}"}
            data = auth_data['data']
            video_id = data['vid']
            play_auth_b64 = data['playAuth']
            play_auth_json = base64.b64decode(play_auth_b64).decode('utf-8')
            cred = json.loads(play_auth_json)
        except (KeyError, ValueError, TypeError) as e:
            return {"parse": 0, "jx": 0, "msg": f"解析 playAuth 失败: {e}"}

        required = ('AccessKeyId', 'AccessKeySecret', 'SecurityToken')
        for k in required:
            if not cred.get(k):
                return {"parse": 0, "jx": 0, "msg": f"凭证缺失字段: {k}"}

        # 3. 构造阿里云 VOD 请求参数
        params = {
            'Action': 'GetPlayInfo',
            'Version': '2017-03-21',
            'Format': 'JSON',
            'AccessKeyId': cred['AccessKeyId'],
            'SecurityToken': cred['SecurityToken'],
            'VideoId': video_id,
            'AuthInfo': cred.get('AuthInfo', ''),
            'Timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'SignatureMethod': 'HMAC-SHA1',
            'SignatureVersion': '1.0',
            'SignatureNonce': str(uuid.uuid4()),
        }
        if 'PlayConfig' in cred:
            params['PlayConfig'] = json.dumps(cred['PlayConfig'])

        # 4. 规范化 query string
        sorted_params = sorted(params.items())
        canonical = "&".join(
            f"{quote(str(k), safe='')}={quote(str(v), safe='')}"
            for k, v in sorted_params
        )
        string_to_sign = f"GET&%2F&{quote(canonical, safe='')}"
        key = cred['AccessKeySecret'] + "&"
        sig_b64 = _hmac_sha1_b64(key, string_to_sign)

        # 5. 走 VOD 拿最终播放地址
        region = cred.get('Region') or 'cn-shanghai'
        vod_url = f"https://vod.{region}.aliyuncs.com/?{canonical}&Signature={quote(sig_b64, safe='')}"
        try:
            r = requests.get(vod_url, headers=HEADER_API, timeout=15)
            r.encoding = "utf-8"
            vod_data = r.json()
        except Exception as e:
            return {"parse": 0, "jx": 0, "msg": f"调用 GetPlayInfo 失败: {e}"}

        # 6. 提取播放地址：优先选 HD / 大文件那一档
        play_url = None
        try:
            plays = vod_data['PlayInfoList']['PlayInfo']
            if plays:
                # 按 size 排序，取大文件（原画）
                plays_sorted = sorted(plays, key=lambda p: int(p.get('Size') or 0), reverse=True)
                play_url = plays_sorted[0].get('PlayURL')
        except (KeyError, TypeError, ValueError):
            pass

        if not play_url:
            return {"parse": 0, "jx": 0, "msg": "未获取到播放地址"}

        # 7. 返回给 FongMi（关键：字段必须齐全）
        return {
            "parse": 0,   # 0 = 直链
            "jx": 0,      # 0 = 不走 VIP 解析
            "url": play_url,
            "header": HEADER_PLAYER,
        }

    # ---------- 搜索 ----------
    def searchContent(self, key, quick, pg="1"):
        try:
            page = int(pg) if pg else 1
        except (ValueError, TypeError):
            page = 1
        # 该站未提供独立搜索接口，走首页列表兜底
        data = _api_get("/web/v1/drama/list", {
            "pageSize": "24",
            "currentPage": str(page),
            "keyword": key or "",
        })
        items = []
        try:
            for vod in data['data']['data']:
                total = vod.get('total') or 0
                items.append({
                    "vod_id": f"{vod['albumId']}@{total}",
                    "vod_name": vod.get('title', ''),
                    "vod_pic": vod.get('coverUrl', ''),
                    "vod_remarks": f"共{total}集",
                })
        except (KeyError, TypeError):
            pass
        return {
            "list": items,
            "page": page,
            "pagecount": 9999,
            "limit": 24,
            "total": 999999,
        }

    def searchContentPage(self, key, quick, pg):
        return self.searchContent(key, quick, pg)

    # ---------- 本地代理 ----------
    def localProxy(self, params):
        # 直链播放，不走代理
        return None
