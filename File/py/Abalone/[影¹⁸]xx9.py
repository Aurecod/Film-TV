

import sys
import json
import time
import base64
import threading
import urllib.parse

from base.spider import Spider

try:
    from Crypto.Cipher import AES
except Exception:
    from Cryptodome.Cipher import AES


class Spider(Spider):

    # ---- 站点常量 ----
    GATEWAY = "https://pl5kjl.jas49cht5sqrwet.xyz/fast-endecode/main/request"
    GATEWAY_POOL = [
        "https://pl5kjl.jas49cht5sqrwet.xyz/fast-endecode/main/request",
        "https://pl5kjl.m93abv5upsv4s8f.xyz/fast-endecode/main/request",
        "https://api.y7hvaad8g.xyz/fast-endecode/main/request",
    ]

    # time%10 -> AES key（index 2 稳定可用，固定使用）
    KEYS = {
        0: "G7i3OPcfNhBnAYpc",
        1: "84UZNK33cSVylz6Y",
        2: "jeSWRcTwHyAKwJDB",
        3: "i1hvJx9vuRt5zEBS",
        4: "1Yy1KOa75R7cnmkg",
        6: "T0RVp7KIPamrtQ33",
        8: "ugvseZc5Kkj8ecmV",
        9: "G7i3OPcfNhBnAYpc",
    }
    REM = 2  # 固定使用 time%10==2 对应的密钥

    ADS_CODE = "DFH"

    # 播放线路（vuex.app.allConfig.h5_play_line）
    PLAY_LINES = [
        ("国线1", "https://rr.rxjhwl.com"),
        ("国线2", "https://ww.wealwelloa.com"),
        ("国线3", "https://cc.cloudworki.com"),
        ("国线4", "https://gg.gmdalian.com"),
        ("海线1", "https://allmusiclub.almusiclub.com"),
    ]

    PIC_BASE = "https://qv1tx2.shoupingxz.com"

    UA = ("Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")

    # 专题分类（id -> title），作为 categoryContent 的分类来源
    THEMES = [
        ("27", "国产精选"), ("9", "主播剧情"), ("26", "业余素人"),
        ("47", "第一视角"), ("7", "欧美精选"), ("35", "日韩精选"),
        ("41", "粉嫩处女"), ("66", "偷窥偷拍监控"), ("50", "网爆偷拍泄密"),
        ("39", "AV精选"), ("40", "职业探花"), ("55", "网红裸舞"),
        ("59", "抖音风合集"), ("36", "动漫精选"), ("67", "街拍街射"),
        ("42", "明星AI换脸"), ("15", "经典老片"), ("16", "成人综艺"),
        ("24", "恐怖科幻伦理"), ("19", "官方推荐"),
    ]

    def init(self, extend=""):
        self._jwt = None
        self._jwt_ts = 0
        self._access = None
        self._access_ts = 0
        self._pic_cache = {}
        self._pic_cache_lock = threading.Lock()
        self._pic_proxy_base = ""
        return

    def _rnd(self, n):
        import random
        cs = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
        return "".join(random.choice(cs) for _ in range(n))

    def getName(self):
        return "xx9"

    def isVideoFormat(self, url):
        return ".m3u8" in url or ".mp4" in url

    def manualVideoCheck(self):
        return False

    def destroy(self):
        return

    # ================= 加密辅助 =================
    def _pad(self, b):
        n = 16 - (len(b) % 16)
        return b + bytes([n]) * n

    def _unpad(self, b):
        if not b:
            return b
        return b[:-b[-1]]

    def _enc(self, obj, key):
        raw = json.dumps(obj, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        c = AES.new(key.encode('utf-8'), AES.MODE_ECB)
        return base64.b64encode(c.encrypt(self._pad(raw))).decode()

    def _dec(self, b64, key):
        c = AES.new(key.encode('utf-8'), AES.MODE_ECB)
        raw = self._unpad(c.decrypt(base64.b64decode(b64)))
        return raw.decode('utf-8')

    def _mktime(self):
        t = int(time.time() * 1000)
        return t - (t % 10) + self.REM

    # ================= 网关请求 =================
    def _call(self, uri, method, params=None, body=None, use_jwt=True, use_access=False, _retry=True):
        key = self.KEYS[self.REM]
        t = self._mktime()
        plain = {"method": method, "uri": uri}
        if body is not None:
            plain["body"] = body
        else:
            plain["params"] = params if params is not None else {}
        payload = {"data": self._enc(plain, key), "time": t}
        headers = {
            "Content-Type": "application/json",
            "User-Agent": self.UA,
            "Origin": "https://xx9.com",
            "Referer": "https://xx9.com/",
        }
        if use_jwt:
            jwt = self._get_jwt()
            if jwt:
                headers["jwtToken"] = jwt
        if use_access:
            acc = self._get_access()
            if acc:
                headers["accessToken"] = acc

        text = None
        for gw in self.GATEWAY_POOL:
            try:
                rsp = self.post(gw, json=payload, headers=headers)
                text = rsp.text
                if text:
                    break
            except Exception:
                continue
        if not text:
            return {}
        try:
            j = json.loads(text)
        except Exception:
            return {}
        # 响应可能是明文，也可能是 {data:<密文>, time:..} 加密包
        if isinstance(j, dict) and isinstance(j.get("data"), str) and j.get("data") and ("time" in j):
            try:
                j = json.loads(self._dec(j["data"], key))
            except Exception:
                return j
        # accessToken 为空(1032)/过期(1019) -> 刷新后重试一次
        if use_access and _retry and isinstance(j, dict):
            code = str(j.get("code") or "")
            if code in ("1032", "1019"):
                self._access = None
                self._access_ts = 0
                return self._call(uri, method, params=params, body=body,
                                  use_jwt=use_jwt, use_access=use_access, _retry=False)
        return j

    def _get_jwt(self):
        now = time.time()
        if self._jwt and (now - self._jwt_ts) < 3600:
            return self._jwt
        try:
            r = self._call("app/jwt-token", 1, params={"adsCode": self.ADS_CODE}, use_jwt=False)
            jwt = r.get("result") if isinstance(r, dict) else None
            if jwt:
                self._jwt = jwt
                self._jwt_ts = now
        except Exception:
            pass
        return self._jwt

    def _get_access(self):
        now = time.time()
        # accessToken 缓存 30 分钟
        if self._access and (now - self._access_ts) < 1800:
            return self._access
        try:
            body = {
                "osType": "h5",
                "sign": self._rnd(32),
                "machineCode": "chrome",
                "version": "xx9.com",
            }
            r = self._call("user/register/free", 2, body=body, use_jwt=True, use_access=False)
            res = r.get("result") if isinstance(r, dict) else None
            acc = res.get("accessToken") if isinstance(res, dict) else None
            if acc:
                self._access = acc
                self._access_ts = now
        except Exception:
            pass
        return self._access

    # ================= 工具 =================
    def _proxy_base(self):
        if getattr(self, "_pic_proxy_base", None):
            return self._pic_proxy_base
        base = ""
        for arg in (True, False):
            try:
                u = str(self.getProxyUrl(local=arg) or "")
                if "://" not in u:
                    continue
                from urllib.parse import urlparse
                p = urlparse(u)
                if p.netloc:
                    base = "%s://%s%s" % (p.scheme, p.netloc, p.path.rstrip("/"))
                    break
            except Exception:
                continue
        if base:
            self._pic_proxy_base = base
        return base

    def _pic_url(self, u):
        # 图片走本地代理（因为 CDN 返回的是 XOR 编码字节，直接加载必失败）
        if not u:
            return ""
        full = u if u.startswith("http") else self.PIC_BASE + u
        base = self._proxy_base()
        if not base:
            return full
        enc = base64.urlsafe_b64encode(full.encode("utf-8")).decode("utf-8").rstrip("=")
        return "%s?type=pic&url=%s" % (base, enc)

    def _decode_pic(self, raw):
        # xx9 CDN: 首字节是 XOR key，之后每字节 XOR key
        if not raw or len(raw) < 4:
            return raw
        key = raw[0]
        return bytes([b ^ key for b in raw[1:]])

    def _pic(self, p):
        if not p:
            return ""
        return self._pic_url(p)

    def _vod_list_item(self, it):
        vid = it.get("id") or it.get("vodId")
        title = it.get("title") or ""
        pic = self._pic(it.get("vodPic") or it.get("gif") or "")
        dur = it.get("vodDuration")
        remark = ""
        if isinstance(dur, int) and dur > 0:
            m, s = divmod(dur, 60)
            remark = "%d:%02d" % (m, s)
        tags = it.get("tags")
        if not remark and isinstance(tags, list) and tags:
            remark = " ".join(tags[:3])
        return {
            "vod_id": str(vid),
            "vod_name": title,
            "vod_pic": pic,
            "vod_remarks": remark,
        }

    def _search(self, params):
        r = self._call("cms/vod/search", 2, params=params)
        data = r.get("data") if isinstance(r, dict) else None
        items = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("list") or data.get("records") or []
        total = r.get("total") if isinstance(r, dict) else 0
        return items, (total or 0)

    # ================= 首页 =================
    def homeContent(self, filter):
        classes = [{"type_id": tid, "type_name": name} for tid, name in self.THEMES]
        filters = {}
        sort_filter = {
            "key": "sort",
            "name": "排序",
            "value": [
                {"n": "最新", "v": "1"},
                {"n": "最热", "v": "2"},
            ],
        }
        for tid, _ in self.THEMES:
            filters[tid] = [sort_filter]
        result = {
            "class": classes,
            "filters": filters,
        }
        try:
            result["list"] = self.homeVideoContent().get("list", [])
        except Exception:
            result["list"] = []
        return result

    def homeVideoContent(self):
        items, _ = self._search({
            "themeIds": self.THEMES[0][0],
            "page": 1, "pageSize": 30,
            "explore": False, "sortType": 1,
        })
        return {"list": [self._vod_list_item(it) for it in items]}

    # ================= 分类 =================
    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg)
        except Exception:
            page = 1
        sort_type = 1
        if isinstance(extend, dict):
            sv = extend.get("sort")
            if sv:
                try:
                    sort_type = int(sv)
                except Exception:
                    sort_type = 1
        page_size = 30
        items, total = self._search({
            "themeIds": str(tid),
            "page": page, "pageSize": page_size,
            "explore": False, "sortType": sort_type,
        })
        vod = [self._vod_list_item(it) for it in items]
        pagecount = 9999
        if total:
            pagecount = (int(total) + page_size - 1) // page_size
        return {
            "list": vod,
            "page": page,
            "pagecount": pagecount,
            "limit": page_size,
            "total": int(total) if total else len(vod),
        }

    # ================= 详情 =================
    def detailContent(self, ids):
        vid = ids[0]
        r = self._call("cms/vod/detail/%s" % vid, 1, params={"needCdnAuth": True}, use_access=True)
        res = r.get("result") if isinstance(r, dict) else None
        if isinstance(res, dict):
            vod = res.get("vod", res)
        else:
            vod = res if isinstance(res, dict) else {}
        if not vod:
            return {"list": []}

        title = vod.get("title") or ""
        pic = self._pic(vod.get("vodPic") or "")
        intro = vod.get("vodIntro") or ""
        tags = vod.get("tags")
        if isinstance(tags, list):
            tag_str = ",".join(tags)
        else:
            tag_str = ""
        dur = vod.get("vodDuration")
        remark = ""
        if isinstance(dur, int) and dur > 0:
            m, s = divmod(dur, 60)
            remark = "时长 %d:%02d" % (m, s)

        full = vod.get("vodFullPlayUrl")
        n_parts = len(full) if isinstance(full, list) and full else 1

        # 每条线路一个 from，剧集用 # 分隔，播放 id 编码为 "vid|addrIndex"
        froms = []
        urls = []
        for name, _domain in self.PLAY_LINES:
            eps = []
            if n_parts <= 1:
                eps.append("正片$%s|0" % vid)
            else:
                for i in range(n_parts):
                    eps.append("P%d$%s|%d" % (i + 1, vid, i))
            froms.append(name)
            urls.append("#".join(eps))

        vod_obj = {
            "vod_id": str(vid),
            "vod_name": title,
            "vod_pic": pic,
            "vod_remarks": remark,
            "vod_content": intro or tag_str,
            "vod_tag": tag_str,
            "vod_play_from": "$$$".join(froms),
            "vod_play_url": "$$$".join(urls),
        }
        return {"list": [vod_obj]}

    # ================= 搜索 =================
    def searchContent(self, key, quick, pg="1"):
        try:
            page = int(pg)
        except Exception:
            page = 1
        items, _ = self._search({
            "title": key,
            "page": page, "pageSize": 30,
            "explore": False, "sortType": 1,
        })
        return {"list": [self._vod_list_item(it) for it in items]}

    # ================= 播放 =================
    def playerContent(self, flag, id, vipFlags):
        # id 形如 "vid|addrIndex"；flag 为线路名，用于选择域名
        vid = id
        idx = 0
        if "|" in id:
            vid, sidx = id.split("|", 1)
            try:
                idx = int(sidx)
            except Exception:
                idx = 0

        domain = None
        for name, dom in self.PLAY_LINES:
            if name == flag:
                domain = dom
                break
        if not domain:
            domain = self.PLAY_LINES[0][1]

        play_url = ""
        try:
            r = self._call("cms/vod/detail/%s" % vid, 1, params={"needCdnAuth": True}, use_access=True)
            res = r.get("result") if isinstance(r, dict) else None
            vod = res.get("vod", res) if isinstance(res, dict) else {}
            full = vod.get("vodFullPlayUrl")
            addr = None
            if isinstance(full, list) and full:
                if idx >= len(full):
                    idx = 0
                addr = full[idx].get("addr")
            if not addr:
                addr = vod.get("preview")
            if addr:
                play_url = domain + addr
        except Exception:
            play_url = ""

        return {
            "parse": 0,
            "playUrl": "",
            "url": play_url,
            "header": {
                "User-Agent": self.UA,
                "Referer": "https://xx9.com/",
            },
        }

    def localProxy(self, param):
        # FongMi 传过来的 param 可能是 dict / URL / JSON str / query string
        # 本源只做图片代理，收到 url 就按 pic 处理
        p = self._param(param)
        enc_url = (p.get("url") or "").strip()
        if not enc_url:
            return [404, "text/plain", ""]
        raw = self._d64(enc_url)
        if not raw:
            return [404, "image/png", b""]
        # 兼容 FongMi 直接把裸 URL 传过来的情况
        if raw.startswith("/"):
            full = self.PIC_BASE + raw
        elif raw.startswith("http"):
            full = raw
        else:
            full = self.PIC_BASE + "/" + raw.lstrip("/")
        return self._fetch_pic_bytes(full)

    def _param(self, param):
        if isinstance(param, dict):
            return dict(param)
        if isinstance(param, (list, tuple)) and param:
            return self._param(param[0])
        s = str(param or "").strip()
        if not s:
            return {}
        if s.startswith("{"):
            try:
                return json.loads(s)
            except Exception:
                pass
        q = s
        if "?" in q:
            q = q.split("?", 1)[1]
        try:
            out = {}
            for k, v in urllib.parse.parse_qs(q, keep_blank_values=True).items():
                out[k] = v[0] if v else ""
            if q and not out:
                out["url"] = q
            return out
        except Exception:
            return {}

    def _fetch_pic_bytes(self, full):
        # 缓存
        cache = getattr(self, "_pic_cache", None)
        if cache is None:
            cache = {}
            self._pic_cache = cache
        lock = getattr(self, "_pic_cache_lock", None) or threading.Lock()
        with lock:
            hit = cache.get(full)
            if hit and time.time() - hit[1] < 3600:
                return hit[0]
        # HTTP 优先（HTTPS 有 TLS handshake 问题），HTTPS 备用
        cands = []
        if full.startswith("https://"):
            cands.append("http://" + full[len("https://"):])
            cands.append(full)
        elif full.startswith("http://"):
            cands.append(full)
            cands.append("https://" + full[len("http://"):])
        else:
            cands.append(full)
        headers = {
            "User-Agent": self.UA,
            "Accept": "image/*,*/*;q=0.8",
            "Accept-Encoding": "identity",
            "Referer": "https://xx9.com/",
        }
        result = None
        for u in cands:
            for _ in range(2):
                try:
                    r = self.fetch(u, headers=headers, timeout=10, verify=False)
                    if r.status_code == 200:
                        data = r.content or b""
                        if len(data) < 4:
                            continue
                        dec = self._decode_pic(data)
                        if self._is_image(dec):
                            ct = self._mime(dec)
                            result = [200, ct, dec, {"Content-Type": ct}]
                            break
                        if self._is_image(data):
                            ct = self._mime(data)
                            result = [200, ct, data, {"Content-Type": ct}]
                            break
                except Exception:
                    time.sleep(0.15)
                    continue
            if result:
                break
        if result is None:
            result = [404, "image/png", b""]
        with lock:
            cache[full] = (result, time.time())
            if len(cache) > 200:
                for k, _ in sorted(cache.items(), key=lambda kv: kv[1][1])[:60]:
                    cache.pop(k, None)
        return result

    @staticmethod
    def _is_image(b):
        if not b or len(b) < 4:
            return False
        if b[:8] == b"\x89PNG\r\n\x1a\n":
            return True
        if b[:2] == b"\xff\xd8":
            return True
        if b[:4] == b"GIF8":
            return True
        if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
            return True
        return False

    @staticmethod
    def _mime(b):
        if not b:
            return "image/png"
        if b[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        if b[:2] == b"\xff\xd8":
            return "image/jpeg"
        if b[:4] == b"GIF8":
            return "image/gif"
        if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
            return "image/webp"
        return "image/png"

    @staticmethod
    def _d64(s):
        s = str(s or "").strip().replace(" ", "+")
        for dec in (base64.urlsafe_b64decode, base64.b64decode):
            try:
                return dec(s + "=" * (-len(s) % 4)).decode("utf-8")
            except Exception:
                continue
        return ""
