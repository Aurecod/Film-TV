# coding=utf-8
"""糯米短剧2 TVBox py 源 (v4 - 签名协议版)
网站: https://2563.mggr2.com   API: https://4f1232983465fdg.jdvxgik.com/api/web/v1
"""
import sys
sys.path.append('..')
import json
import base64
import hashlib
import random
import subprocess
import tempfile
import time

from base.spider import Spider


class Spider(Spider):
    name = "糯米短剧2"
    host = "https://2563.mggr2.com"
    api_host = "https://4f1232983465fdg.jdvxgik.com"
    api = api_host + "/api/web/v1"
    AES_KEY = b"eC2gG2gM0bH4aF1l"
    # 前端写死的服务端强制分页大小: 实测 pageSize 传 8/50 都回 24 条
    PAGE_SIZE = 24
    # 游客 token 字符集 (webpack e1bd 模块, 21 位)
    TOKEN_ALPHA = "useandom-26T198340PX75pxJACKVERYMINDBUSHWOLF_GQZbfghjklqvwyzrict"
    UA = "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36"

    # 动态域名 (init / 各方法入口刷新)
    static_domain = ""      # 封面域
    video_domain = ""       # 国内 m3u8 域
    video_domain_out = ""   # 国外 m3u8 域
    version = ""

    def getName(self):
        return self.name

    # ---------------- 动态域名 ----------------
    def _load_config(self):
        try:
            if getattr(self, "_cfg_ts", 0) and time.time() - self._cfg_ts < 1800:
                return True
            data = self._post("/config/load", {"plat": "pc"})
            cfg = (data or {}).get("config") or {}
            self.static_domain = str(cfg.get("static_domain") or self.static_domain).rstrip("/")
            self.video_domain = str(cfg.get("video_domain") or self.video_domain).rstrip("/")
            self.video_domain_out = str(cfg.get("video_domain_out") or self.video_domain_out).rstrip("/")
            self.version = str(cfg.get("version") or self.version)
            self._cfg_ts = time.time()
            return bool(self.static_domain or self.video_domain)
        except Exception as e:
            print("[nm-diag] config/load error:", e)
            return bool(self.static_domain or self.video_domain)

    def init(self, extend=""):
        try:
            if isinstance(extend, dict):
                data = extend
            else:
                data = json.loads(extend) if extend else {}
            if isinstance(data, dict):
                self.api_host = str(data.get("api_host") or self.api_host).rstrip("/")
                self.api = self.api_host + "/api/web/v1"
        except Exception:
            pass
        self._guest_token = ""
        self._load_config()
        return {}

    # ---------------- 游客 token ----------------
    def _token(self):
        if not getattr(self, "_guest_token", ""):
            self._guest_token = "".join(
                random.choice(Spider.TOKEN_ALPHA) for _ in range(21))
        return self._guest_token

    # ---------------- 签名协议 ----------------
    @staticmethod
    def _urlenc(v):
        """精确对齐 JS URLSearchParams(form-urlencoded): 字母数字 * - . 原样, 空格->+, 其余按 UTF-8 字节百分号编码"""
        out = []
        for b in str(v).encode("utf-8"):
            if (48 <= b <= 57) or (65 <= b <= 90) or (97 <= b <= 122) or b in (42, 45, 46):
                out.append(chr(b))
            elif b == 32:
                out.append("+")
            else:
                out.append("%%%02X" % b)
        return "".join(out)

    @classmethod
    def _query_str(cls, obj):
        """对齐前端 URLSearchParams 序列化: 顶层键排序(值按原序嵌套), 数组按下标;
        值经 JS String() 语义 (数字直转, null->'null')。"""
        pairs = []

        def walk(prefix, o):
            if isinstance(o, dict):
                for k in o:
                    walk("%s[%s]" % (prefix, k) if prefix else str(k), o[k])
            elif isinstance(o, list):
                for i, v in enumerate(o):
                    walk("%s[%s]" % (prefix, i) if prefix else str(i), v)
            else:
                if o is None:
                    pairs.append((prefix, "null"))
                elif isinstance(o, bool):
                    pairs.append((prefix, "true" if o else "false"))
                else:
                    pairs.append((prefix, str(o)))
        walk("", obj)
        return "&".join("%s=%s" % (cls._urlenc(k), cls._urlenc(v)) for k, v in pairs)

    def _signed_body(self, payload):
        """payload -> {"encrypt_data": b64(AES(JSON(排序payload+signature)))}"""
        token = self._token()
        p = {k: payload.get(k) for k in sorted(payload.keys())}
        q = self._query_str(p)
        t = int(str(int(time.time() * 1000)) + str(random.randint(100, 999)))
        s = hashlib.md5((q + str(t) + token + Spider.AES_KEY.decode()).encode("utf-8")).hexdigest().lower()
        p["signature"] = json.dumps({"t": t, "s": s}, separators=(",", ":"))
        plain = json.dumps(p, ensure_ascii=False)
        ct = None
        try:
            from Crypto.Cipher import AES
            from Crypto.Util.Padding import pad
            ct = base64.b64encode(AES.new(self.AES_KEY, AES.MODE_ECB).encrypt(pad(plain.encode("utf-8"), 16))).decode()
        except Exception:
            ct = None
        if ct is None:
            raise RuntimeError("AES 加密不可用(无 pycryptodome)")
        return json.dumps({"encrypt_data": ct}, ensure_ascii=False)

    # ---------------- AES-ECB 解密 (响应 data 段) ----------------
    @staticmethod
    def _aes_decrypt(encrypted_b64):
        if not encrypted_b64:
            return None
        key = Spider.AES_KEY
        try:
            ct = base64.b64decode(encrypted_b64 + "=" * ((4 - len(encrypted_b64) % 4) % 4))
            if len(ct) < 16 or len(ct) % 16:
                return None
            try:
                from Crypto.Cipher import AES
                from Crypto.Util.Padding import unpad
                return unpad(AES.new(key, AES.MODE_ECB).decrypt(ct), 16).decode("utf-8")
            except Exception:
                pass
            # openssl 子进程兜底
            with tempfile.NamedTemporaryFile(delete=False) as f:
                f.write(ct)
                enc_file = f.name
            dec_file = enc_file + ".out"
            subprocess.run(['openssl', 'enc', '-d', '-aes-128-ecb', '-K', key.hex(),
                            '-in', enc_file, '-out', dec_file],
                           capture_output=True, timeout=15)
            dec = open(dec_file, 'rb').read()
            n = dec[-1]
            if 1 <= n <= 16:
                dec = dec[:-n]
            return dec.decode("utf-8")
        except Exception as e:
            print('[nm-diag] AES decrypt error:', e)
        return None

    # ---------------- 传输层: 三级降级 POST ----------------
    def _post(self, path, data=None, diag=None):
        url = self.api + path
        headers = {"User-Agent": self.UA,
                   "Content-Type": "application/json;charset=utf-8",
                   "Authorization": "Bearer " + self._token(),
                   "Referer": self.host + "/", "Origin": self.host}
        body = self._signed_body(data or {})
        errs = []
        try:
            rsp = self.post(url, headers=headers, data=body, timeout=15)
            return self._wrap(rsp, path, diag)
        except Exception as e:
            errs.append("P1:" + str(e)[:24])
        try:
            rsp = self.fetch(url, headers=headers, data=body, method="POST", timeout=15)
            return self._wrap(rsp, path, diag)
        except Exception as e:
            errs.append("P2:" + str(e)[:24])
        try:
            import requests
            rsp = requests.post(url, data=body.encode("utf-8"), headers=headers, timeout=15)
            return self._wrap(rsp, path, diag)
        except Exception as e:
            errs.append("P3:" + str(e)[:24])
        if diag is not None:
            diag.append("传输层 " + " ".join(errs))
        return {}

    def _wrap(self, rsp, path, diag):
        obj = None
        if hasattr(rsp, "json"):
            try:
                obj = rsp.json()
            except Exception:
                obj = None
        if obj is None:
            text = rsp.content if hasattr(rsp, "content") else (rsp.text if hasattr(rsp, "text") else str(rsp))
            if isinstance(text, bytes):
                text = text.decode("utf-8", "ignore")
            obj = json.loads(text)
        code = obj.get("code")
        if code != 10000:
            if diag is not None:
                diag.append("code=%s %s" % (code, str(obj.get("msg", ""))[:24]))
            return {}
        raw = obj.get("data")
        if isinstance(raw, str) and raw:
            dec = self._aes_decrypt(raw)
            if dec:
                try:
                    return json.loads(dec)
                except Exception:
                    if diag is not None:
                        diag.append("响应解析失败")
            elif diag is not None:
                diag.append("AES解密失败")
            return {}
        return raw if isinstance(raw, dict) else {}

    # ---------------- 首页 / 分类 ----------------
    def homeContent(self, filter=None):
        self._load_config()
        result = {"filters": {}}
        diag = []
        classes = [
            {"type_id": "hot", "type_name": "热播剧"},
            {"type_id": "new", "type_name": "新剧"},
            {"type_id": "vip", "type_name": "VIP专享"},
        ]
        try:
            tags = self._post("/tags/list", {}, diag)
            for t in (tags.get("list") or [])[:60]:
                tid = str(t.get("id") or "")
                tname = str(t.get("t") or t.get("name") or "").strip()
                if tid and tname:
                    classes.append({"type_id": "tag_" + tid, "type_name": tname})
        except Exception as e:
            print('homeContent tags error:', e)
        result['class'] = classes
        home = self._post("/pc-video/home", {}, diag)
        vids = []
        for grp in ["tvList", "aiList", "videoList", "list"]:
            for it in (home.get(grp) or []):
                if isinstance(it, dict):
                    vids.append(it)
        result['list'] = [self._to_vod(v) for v in vids if v.get("id")]
        result['list'] = [v for v in result['list'] if v.get("vod_name")]
        if not result['list'] and diag:
            self._append_diag(result, "首页", diag)
        return result

    def homeVideoContent(self):
        try:
            data = self._post("/video/list", {"pageNum": 1})
            vids = [self._to_vod(i) for i in (data.get("list") or [])]
            return {'list': [v for v in vids if v.get("vod_name")]}
        except Exception as e:
            print('homeVideoContent error:', e)
            return {'list': []}

    def categoryContent(self, tid, pg="1", filter=None, extend=None):
        self._load_config()
        result = {'list': [], 'page': pg, 'pagecount': 1, 'limit': self.PAGE_SIZE, 'total': 0}
        diag = []
        try:
            page = max(1, int(pg) if pg else 1)
            t = str(tid)
            if t.startswith("tag_"):
                tag_id = t[4:]
                body = {"pageNum": page, "tag": int(tag_id) if tag_id.isdigit() else tag_id,
                        "type": "", "board": ""}
            elif t in ("new", "vip"):
                body = {"pageNum": page, "type": t, "board": ""}
            else:
                body = {"pageNum": page}
            data = self._post("/video/list", body, diag)
            vids = [self._to_vod(i) for i in (data.get("list") or [])]
            vids = [v for v in vids if v.get("vod_name")]
            total = int(data.get("total") or 0)
            result['list'] = vids
            result['page'] = page
            # 服务端固定每页 24 条 (pageSize 参数被忽略), pagecount 按 24 算
            result['pagecount'] = max(1, (total + self.PAGE_SIZE - 1) // self.PAGE_SIZE) if total else page
            result['total'] = total
            if not vids and diag:
                self._append_diag(result, "分类 " + t, diag)
        except Exception as e:
            print('categoryContent error:', e)
            self._append_diag(result, "分类 " + str(tid), ["异常 " + str(e)[:40]])
        return result

    # ---------------- 详情 ----------------
    def detailContent(self, array):
        self._load_config()
        result = {'list': []}
        diag = []
        try:
            vod_id = str(array[0] if isinstance(array, list) and array else array)
            if not vod_id:
                return result
            data = self._post("/video/detail-info", {"id": vod_id, "from": "home"}, diag)
            info = (data.get("info") or {}) if isinstance(data, dict) else {}
            if not info:
                # 列表兜底 (个别接口异常时)
                for p in range(1, 4):
                    ld = self._post("/video/list", {"pageNum": p})
                    for it in (ld.get("list") or []):
                        if str(it.get("id")) == vod_id:
                            info = it
                            break
                    if info:
                        break
            if not info:
                self._append_diag(result, "详情 " + vod_id[:12], diag or ["详情无数据"])
                return result
            ep = self._build_episodes(vod_id, info)
            # 双线路: 国内 $$$ 国外 (播放域都可达, 播放器内 #EXT-X-KEY 为绝对路径, 自动按 m3u8 域解析)
            vod = {
                "vod_id": vod_id,
                "vod_name": str(info.get("title") or ""),
                "vod_pic": self._pic(info.get("cover")),
                "vod_remarks": "全{}集".format(info.get("sets") or len(ep)),
                "vod_content": (info.get("summary") or "")[:300],
                "vod_play_from": "糯米国内$$$糯米国外",
                "vod_play_url": "$$$".join([
                    "#".join(ep),           # 国内线路
                    "#".join(ep),         # 国外线路
                ]),
            }
            result['list'] = [vod]
        except Exception as e:
            print('detailContent error:', e)
            self._append_diag(result, "详情", ["异常 " + str(e)[:40]])
        return result

    def _build_episodes(self, vod_id, info):
        eps = []
        set_list = info.get("setList") or []
        if set_list:
            for item in set_list:
                index = item.get("i")
                if index is not None:
                    eps.append("第{}集${}|{}".format(index, vod_id, index))
        else:
            total_sets = int(info.get("sets") or 0)
            for i in range(1, min(total_sets + 1, 201)):
                eps.append("第{}集${}|{}".format(i, vod_id, i))
        return eps

    # ---------------- 搜索 ----------------
    def searchContent(self, key, quick=False, pg="1"):
        self._load_config()
        result = {'list': [], 'page': pg, 'pagecount': 1, 'limit': self.PAGE_SIZE, 'total': 0}
        diag = []
        try:
            key = str(key or "")
            if len(key) < 2:
                return result
            page = max(1, int(pg) if pg else 1)
            data = self._post("/search/list",
                               {"text": key, "pageNum": page, "pageSize": self.PAGE_SIZE, "plat": "pc"}, diag)
            vids = [self._to_vod(i) for i in (data.get("list") or [])]
            vids = [v for v in vids if v.get("vod_name")]
            total = int(data.get("total") or 0)
            result['list'] = vids
            result['page'] = page
            result['pagecount'] = max(1, (total + self.PAGE_SIZE - 1) // self.PAGE_SIZE) if total else page
            result['total'] = total
            if not vids and diag:
                self._append_diag(result, "搜索 " + key[:8], diag)
        except Exception as e:
            print('searchContent error:', e)
            self._append_diag(result, "搜索", ["异常 " + str(e)[:40]])
        return result

    # ---------------- 播放 ----------------
    def playerContent(self, flag, id, vipFlags=None):
        self._load_config()
        text = str(id or "")
        if "|" not in text:
            return {"parse": 0, "url": "", "header": {"User-Agent": self.UA, "Referer": self.host + "/"}}
        vod_id, set_no = text.rsplit("|", 1)
        diag = []
        try:
            data = self._post("/video/set-info",
                               {"id": vod_id, "set": int(set_no) if set_no.isdigit() else set_no}, diag)
            info = (data.get("info") or {}) if isinstance(data, dict) else {}
            path = str(info.get("url_m3u8") or info.get("url_mp4") or "").strip()
            if not path:
                # 无直链 (VIP 集/接口异常): 回退 H5 详情页
                url_h5 = "%s/#/detail/%s/%s" % (self.host, vod_id, set_no)
                return {"parse": 1, "url": url_h5, "jx": 0,
                        "header": {"User-Agent": self.UA, "Referer": self.host + "/"}}
            # 线路选择: flag 含"国外" -> video_domain_out, 否则国内; 国内域为空时用国外域兜底
            if "国外" in str(flag):
                url = self._play_url(path, prefer_out=True)
            else:
                url = self._play_url(path, prefer_out=False)
            return {"parse": 0, "url": url, "jx": 0,
                    "header": {"User-Agent": self.UA, "Referer": self.host + "/"}}
        except Exception as e:
            print('playerContent error:', e)
            return {"parse": 1, "url": text, "jx": 0,
                    "header": {"User-Agent": self.UA, "Referer": self.host + "/"}}

    def _play_url(self, path, prefer_out=False):
        """m3u8/mp4 相对路径(无 leading slash) -> 绝对 URL。"""
        if path.startswith("http"):
            return path
        suffix = path if path.startswith("/") else "/" + path
        doms = ([self.video_domain_out, self.video_domain, self.api_host]
                if prefer_out else [self.video_domain, self.video_domain_out, self.api_host])
        doms = [d for d in doms if d]
        return (doms[0] if doms else self.api_host).rstrip("/") + suffix

    def isVideoFormat(self, url):
        u = str(url or "").lower()
        return ".m3u8" in u or ".mp4" in u

    def localProxy(self, param):
        return [404, "text/plain", ""]

    def action(self, action):
        try:
            self._load_config()
            if action in ("checkUpdate", "getUpdate"):
                return {"version": self.version or "1", "force": 0,
                        "desc": "糯米短剧2 v" + (self.version or "1")}
        except Exception as e:
            print("action error:", e)
        return {}

    # ---------------- 工具 ----------------
    def _to_vod(self, item):
        return {
            "vod_id": str(item.get("id") or ""),
            "vod_name": str(item.get("title") or ""),
            "vod_pic": self._pic(item.get("cover")),
            "vod_remarks": "全{}集".format(item.get("sets") or ""),
        }

    def _pic(self, value):
        value = str(value or "").strip()
        if not value:
            return ""
        if value.startswith("http"):
            return value
        base = self.static_domain or self.api_host
        suffix = value if value.startswith("/") else "/" + value
        return base.rstrip("/") + suffix

    def _append_diag(self, result, where, diag):
        msgs = " | ".join(str(m) for m in (diag or []))
        if not msgs:
            msgs = "未知(无接口返回)"
        card = {
            "vod_id": "diag-" + str(abs(hash(where))),
            "vod_name": "【诊断】%s" % where,
            "vod_pic": "",
            "vod_remarks": msgs[:100],
            "vod_content": "见备注。P1/P2/P3=传输层(壳post/fetch/requests), code=xxx=接口返回码, 家用网正常。",
        }
        lst = result.get("list")
        if isinstance(lst, list):
            lst.insert(0, card)


if __name__ == '__main__':
    spider = Spider()
    spider.init("")
    print("host:", spider.host, "api:", spider.api)
    print("static:", spider.static_domain, "| video:", spider.video_domain,
          "| out:", spider.video_domain_out, "| ver:", spider.version)
    h = spider.homeContent(None)
    print("class 数:", len(h.get("class", [])), "| 首页 list:", len(h.get("list", [])))
