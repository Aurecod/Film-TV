# -*- coding: utf-8 -*-
# ============================================================
# ko4.ko43to.com:52000/video (Vv 站点) 影视壳 py 源  v1
# 适配: OK影视Pro(2) / FongMi(蜂蜜) / 影视仓 / 海阔 等
# ------------------------------------------------------------
# ★ 写作规范与 OK影视/TVBox 生态真实 py 源(tianquan.py 等)逐点对齐:
#   1) 类封装: sys.path.append('..') + from base.spider import Spider
#      + class Spider(BaseSpider)
#   2) 方法集: init / getName / homeContent / homeVideoContent /
#      categoryContent / detailContent(ids 为 list) / searchContent /
#      playerContent / manualVideoCheck / isVideoFormat / localProxy /
#      action / destroy
#   3) ★ playerContent 签名 (flag, id, vipFlags): flag=线路名,
#      id=vod_play_url 中 '$' 后的 value, vipFlags=平台旗标列表
#   4) 本 py 与 ko4.json 放在同一目录, 配置里 api 写 ./ko4.py
# 配置地址填 ko4.json 的直链(不填 py 链接):
#   {"sites":[{"key":"ko4","name":"Vv视频","type":3,
#              "api":"./ko4.py","searchable":1,...}]}
# ------------------------------------------------------------
# 站点接口(2026-09-19 实网逆向):
#   Web 层有 JS 反爬挑战(vv_challenge cookie), 但 JSON API 直接可用:
#     API 服务器(多台, 失败自动轮换, 见 _HOSTS):
#       列表  GET  /api/v2/home/public/video/list
#                 ?page=N&limit=20&type={last|good|hot|cate|label}&typeId=ID
#       分类  GET  /api/v2/home/public/video/cate/list?type=long
#       标签  GET  /api/v2/home/public/video/label/list?type=long
#       搜索  GET  /api/v2/home/public/video/search?keyword=K&page=N&limit=20
#       详情  GET  /api/v2/home/public/video/long/detail?id=ID
#       播放  GET  /api/v2/home/user/video/play/url?id=ID  (需 Bearer token)
#       游客登录 POST /api-user/v2/login/fingerprint
#                body={"fingerPrint": sha256("video-view:v1|"+uuid4)}
#       续期  POST /api-user/v2/login/refresh_token  body={"token": rt}
#   ★ 所有接口响应加密: data 为 base64url(XOR(key) 后的 JSON 文本)
#   ★ m3u8 播放直链需 Referer(ko4 站域), key/ts 分片免鉴权
#   ★ 播放 URL 由 play/url 下发(masterUrl/p480Url/p720Url 相对路径),
#     需拼 API 域; 签名带时间戳, 播放前实时获取
# ============================================================
import base64
import hashlib
import json
import math
import re
import sys
import time
import urllib.parse
import urllib.request
import uuid

# OKPro/FongMi 真实 py 源标配头: 确保能 import 到 base 包
try:
    sys.path.append('..')
    from base.spider import Spider as BaseSpider
except Exception:
    BaseSpider = object

# API 服务器列表(实网解密自页面 __API_URLS__, 顺序即前端优先级)
_HOSTS = [
    "https://mjs.5ntg79qy.com:51999",
    "https://mjs.w5i4ygkl.com:52000",
    "https://cns7.da625gu4.com:51666",
    "https://cns7.yz59n9ys.com:51666",
    "https://9sbg.33gl3vju.com:51888",
    "https://9sbg.egnomc4t.com:51888",
    "https://mjs.s6t7y6c8.com:25118",
]
_cur = [0]          # 当前生效的 API 服务器索引(请求失败时轮换)
_CHANNEL = "vvmmyjs"  # 页面注入 viewChannel 常量
_SITE_NAME = "Vv视频"
_SITE_REF = "https://ko4.ko43to.com:52000/"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
_TIMEOUT = 12

# 图片 CDN: cdn/index 返回 picUrl + bucket (spjq / spjq22)
_PIC_CDNS = [
    "https://spjq.huibaolian.xin/encryption-ts",
    "https://spjq22.huibaolian.xin/encryption-ts",
]

# 栏目(无 typeId)
_FAST = [
    ("last", "最近更新"),
    ("good", "每日精选"),
    ("hot", "热门推荐"),
]

# 分类(type_id=数字, 来自 cate/list?type=long, 2026-09-19 实取17项)
_CATES = [
    ("347", "黑料"),
    ("263", "日本AV"),
    ("262", "国产"),
    ("266", "传媒"),
    ("343", "AV无码"),
    ("344", "AV中字"),
    ("342", "AI换脸"),
    ("341", "三级"),
    ("267", "动漫"),
    ("264", "欧美"),
    ("358", "麻豆"),
    ("345", "女主播"),
    ("346", "VR"),
    ("356", "擦边短剧"),
    ("357", "新闻"),
    ("269", "其他"),
    ("268", "热门"),
]

# 标签(type_id=数字, 来自 label/list?type=long 前段, 2026-09-19 实取)
_LABELS = [
    ("261", "多人运动"),
    ("262", "熟女"),
    ("263", "内衣"),
    ("287", "偶像艺人"),
    ("288", "恋物癖"),
    ("289", "恋乳癖"),
    ("290", "情侣"),
    ("291", "跳舞"),
    ("292", "花痴"),
    ("293", "偷窥"),
    ("294", "恋腿癖"),
    ("295", "性奴"),
    ("296", "姐妹"),
    ("297", "双性人"),
    ("298", "通奸"),
    ("299", "粗暴"),
    ("300", "学校作品"),
    ("301", "恶作剧"),
    ("302", "妄想"),
    ("303", "残忍画面"),
]

# token 缓存
_TOKEN = {"access": "", "refresh": "", "expire": 0.0}


class _ApiError(Exception):
    pass


def _decrypt(data, key):
    """站点统一加密: base64url -> XOR(key 循环) -> UTF-8 JSON 文本"""
    b = re.sub(r'[\r\n\s]+', '', data or '').replace('-', '+').replace('_', '/')
    b += '=' * (-len(b) % 4)
    raw = base64.b64decode(b)
    kb = key.encode('utf-8')
    out = bytes(c ^ kb[i % len(kb)] for i, c in enumerate(raw))
    return out.decode('utf-8', 'replace')


_requests = None
try:  # 优先 requests(壳子环境普遍内置), 缺失时回退 urllib
    import requests as _requests
    _HAS_REQ = True
except Exception:
    _HAS_REQ = False

_ssl_ctx = None


def _get_ssl_ctx():
    global _ssl_ctx
    if _ssl_ctx is None:
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        _ssl_ctx = ctx
    return _ssl_ctx


def _req(url, method="GET", body=None, headers=None):
    """单次 HTTP 请求, 返回 (bytes, status); 异常返回 (None, 0)"""
    hdrs = {
        "User-Agent": _UA,
        "Referer": _SITE_REF,
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
    }
    if headers:
        hdrs.update(headers)
    data = None
    if body is not None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode('utf-8')
    try:
        if _HAS_REQ and _requests is not None:
            # verify=False: 部分原厂 Android 证书链不全, 校验会整链失败
            r = _requests.request(method, url, data=data, headers=hdrs,
                                  timeout=_TIMEOUT, verify=False)
            return r.content, r.status_code
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        with urllib.request.urlopen(
                req, timeout=_TIMEOUT, context=_get_ssl_ctx()) as resp:
            return resp.read(), resp.status
    except Exception:
        return None, 0


def _api(path, auth=False, retry_refresh=True, method="GET", body=None):
    """请求 API 服务器集群并解密响应(带 token/重试/换服逻辑)。
    返回解密后的 dict; 失败返回 None。"""
    headers = None
    if auth:
        tok = _get_token()
        if not tok:
            return None
        headers = {"Authorization": "Bearer " + tok}
    for k in range(len(_HOSTS)):
        n = (_cur[0] + k) % len(_HOSTS)
        url = _HOSTS[n] + path
        content, status = _req(url, method=method, body=body, headers=headers)
        if status != 200 or not content:
            continue
        try:
            r = json.loads(content.decode('utf-8', 'replace'))
        except Exception:
            continue
        if r.get('code') == 401 and auth and retry_refresh:
            # token 失效 -> 强制刷新一次重试
            _TOKEN['access'] = ''
            _TOKEN['refresh'] = ''
            return _api(path, auth=auth, retry_refresh=False)
        if r.get('code') != 200:
            continue
        if isinstance(r.get('data'), str) and r.get('key'):
            try:
                r['data'] = json.loads(_decrypt(r['data'], r['key']))
            except Exception:
                continue
        _cur[0] = n  # 记住可用服务器
        return r
    return None


def _get_token():
    """游客指纹登录/续期, 带内存缓存。返回 accessToken 或空串。"""
    now = time.time()
    if _TOKEN['access'] and _TOKEN['expire'] - now > 60:
        return _TOKEN['access']
    if _TOKEN['refresh']:
        r = _api("/api-user/v2/login/refresh_token?channel=" + _CHANNEL,
                 body={"token": _TOKEN['refresh']}, auth=False, method="POST")
        if r and isinstance(r.get('data'), dict) and r['data'].get('accessToken'):
            d = r['data']
            _TOKEN['access'] = d['accessToken']
            _TOKEN['expire'] = now + int(d.get('accessTokenTtl') or 1800)
            return _TOKEN['access']
        _TOKEN['refresh'] = ''
    # 无有效凭证 -> 指纹登录: SHA256("video-view:v1|" + seed)
    seed = str(uuid.uuid4())
    fp = hashlib.sha256(("video-view:v1|" + seed).encode('utf-8')).hexdigest()
    r = _api("/api-user/v2/login/fingerprint?channel=" + _CHANNEL,
             body={"fingerPrint": fp}, auth=False, method="POST")
    if r and isinstance(r.get('data'), dict) and r['data'].get('accessToken'):
        d = r['data']
        _TOKEN['access'] = d['accessToken']
        _TOKEN['refresh'] = d.get('refreshToken') or ''
        _TOKEN['expire'] = now + int(d.get('accessTokenTtl') or 1800)
    return _TOKEN['access']


def _pic(thumb):
    """拼图片 CDN 完整地址"""
    if not thumb:
        return ""
    if thumb.startswith('http'):
        return thumb
    for cdn in _PIC_CDNS:
        if cdn:
            return cdn + (thumb if thumb.startswith('/') else '/' + thumb)
    return thumb


def _vod(item):
    """API 列表项 -> 壳标准 vod 字段"""
    vid = str(item.get('id') or '')
    title = re.sub(r'\s+', ' ', str(item.get('title') or '')).strip()
    remark = str(item.get('classifyTitles') or item.get('labelTitles') or '')
    return {
        "vod_id": vid,
        "vod_name": title or ("视频 %s" % vid),
        "vod_pic": _pic(item.get('thumb')),
        "vod_remarks": remark,
        "vod_year": (item.get('createdAt') or '')[:4],
    }


def _parse_list(r):
    """解密后的列表响应 -> (vods, pagecount)"""
    d = r.get('data') or {}
    lst = d.get('list') or []
    vods = [_vod(x) for x in lst if x.get('id')]
    total = int(d.get('total') or 0)
    limit = 20
    pagecount = int(math.ceil(total / limit)) if total > 0 else 1
    pagecount = pagecount or 1
    return vods, pagecount, total


class Spider(BaseSpider):
    def init(self, config):
        self.config = config if config else {}
        self.filter = {}
        return True

    def getName(self):
        return _SITE_NAME

    def homeContent(self, filter):
        self.filter = filter or {}
        classes = []
        for tid, name in _FAST:
            classes.append({"type_id": tid, "type_name": name})
        for tid, name in _CATES:
            classes.append({"type_id": "cate:" + tid, "type_name": name})
        for tid, name in _LABELS:
            classes.append({"type_id": "label:" + tid, "type_name": name})
        return {"class": classes, "filters": {}}

    def homeVideoContent(self):
        return self.categoryContent("last", 1, "")

    def categoryContent(self, tid, pg, filter, ext=None):
        pg = int(pg or 1)
        tid = str(tid or '').strip()
        if tid.startswith('cate:'):
            vtype, tid2 = 'cate', tid[5:]
        elif tid.startswith('label:'):
            vtype, tid2 = 'label', tid[6:]
        else:
            vtype, tid2 = tid or 'last', '0'
        if vtype not in ('last', 'good', 'hot', 'cate', 'label'):
            vtype = 'last'
        path = ("/api/v2/home/public/video/list?page=%d&limit=20&type=%s"
                "&typeId=%s&channel=%s" % (pg, vtype, tid2, _CHANNEL))
        r = _api(path)
        if not r:
            return {"list": []}
        vods, pagecount, total = _parse_list(r)
        return {
            "list": vods,
            "page": pg,
            "pagecount": pagecount,
            "limit": 20,
            "total": total,
        }

    def detailContent(self, ids):
        if isinstance(ids, list):
            vid = ids[0] if ids else ""
        else:
            vid = str(ids or '')
        vid = re.sub(r'\D', '', vid)
        if not vid:
            return {"list": []}
        r = _api("/api/v2/home/public/video/long/detail?id=%s&channel=%s"
                 % (vid, _CHANNEL))
        if not r or not isinstance(r.get('data'), dict):
            return {"list": []}
        d = r['data']
        name = re.sub(r'\s+', ' ', str(d.get('title') or '')).strip()
        content = re.sub(r'<[^>]+>', '', str(d.get('content') or ''))
        content = re.sub(r'\s+', ' ', content).strip()
        vod = {
            "vod_id": vid,
            "vod_name": name or ("视频 %s" % vid),
            "vod_pic": _pic(d.get('thumb')),
            "type_name": str(d.get('classifyTitles') or _SITE_NAME),
            "vod_year": (d.get('createdAt') or '')[:4],
            "vod_area": "",
            "vod_remarks": str(d.get('labelTitles') or ''),
            "vod_actor": str(d.get('actor') or ''),
            "vod_director": "",
            "vod_content": content,
            "vod_play_from": "HLS",
            # value 存视频ID, playerContent 据 id 实时取最新播放签名
            "vod_play_url": "%s$%s" % (name or "视频", vid),
        }
        return {"list": [vod]}

    def searchContent(self, key, quick, pg=1, ext=None):
        if not key:
            return {"list": []}
        pg = int(pg or 1)
        kw = urllib.parse.quote(str(key).strip())
        r = _api("/api/v2/home/public/video/search?keyword=%s&page=%d"
                 "&limit=20&channel=%s" % (kw, pg, _CHANNEL))
        if not r:
            return {"list": []}
        vods, pagecount, total = _parse_list(r)
        return {
            "list": vods,
            "page": pg,
            "pagecount": pagecount,
            "limit": 20,
            "total": total,
        }

    def playerContent(self, flag, id, vipFlags=None):
        """官方签名 (flag, id, vipFlags)。
        播放签名带时间戳: 每次播放都即时请求 play/url 拿最新直链。"""
        vid = re.sub(r'\D', '', str(id or ''))
        if not vid:
            for cand in (str(flag or ''), str(vipFlags or '')):
                m = re.search(r'(\d{5,})', cand)
                if m:
                    vid = m.group(1)
                    break
        if not vid:
            return {}
        r = _api("/api/v2/home/user/video/play/url?id=%s&channel=%s"
                 % (vid, _CHANNEL), auth=True)
        if not r or not isinstance(r.get('data'), dict):
            return {}
        path = r['data'].get('masterUrl') or r['data'].get('p720Url') \
            or r['data'].get('p480Url')
        if not path:
            return {}
        if path.startswith('//'):
            url = "https:" + path
        elif path.startswith('/'):
            url = _HOSTS[_cur[0] % len(_HOSTS)] + path
        else:
            url = path
        return {
            "parse": 0,
            "url": url,
            "format": "application/x-mpegURL",  # 跳过播放器格式嗅探
            "header": {
                "User-Agent": _UA,
                "Referer": _SITE_REF,
            },
        }

    def manualVideoCheck(self):
        return []

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(m3u8|mp4)(\?|$)', url or '', re.I))

    def localProxy(self, param):
        return [200, "video/MP2T", "", ""]

    def action(self, action):
        return ""

    def destroy(self):
        return True


# ========== 顶层函数式转发(兼容影视仓/海阔等非类加载壳) ==========
def init(_=None):
    return True


def getName():
    return _SITE_NAME


def homeContent(filter=""):
    return Spider().homeContent(filter)


def homeVideoContent():
    return Spider().homeVideoContent()


def categoryContent(tid, pg, filter=" ", ext=None):
    return Spider().categoryContent(tid, pg, filter or {}, ext)


def detailContent(ids):
    return Spider().detailContent(ids)


def searchContent(key, quick="", pg=1, ext=None):
    return Spider().searchContent(key, quick, pg, ext)


def playerContent(flag, id, vipFlags=None):
    return Spider().playerContent(flag, id, vipFlags)


def manualVideoCheck():
    return []


def isVideoFormat(url):
    return Spider().isVideoFormat(url)


def localProxy(param):
    return [200, "video/MP2T", "", ""]


def action(action):
    return ""


def destroy():
    return True