# -*- coding: utf-8 -*-
# 红果黄剧 https://huangju.net
# API: https://api.huangju.net  JSON
# 播放: /play/{episodeId} → m3u8 + CloudFront 签名 Cookie
try:
    from base.spider import Spider as _BaseSpider
except Exception:
    class _BaseSpider(object):
        def getName(self):
            return ""

        def init(self, extend=""):
            pass


class Spider(_BaseSpider):
    def __init__(self):
        self.host = "https://huangju.net"
        self.api = "https://api.huangju.net"
        self.ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
        self.headers = {
            "User-Agent": self.ua,
            "Referer": self.host + "/",
            "Origin": self.host,
            "Accept": "application/json",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        # episodeId -> (url, cookie_header)
        self._play_cache = {}

    def getName(self):
        return "红果黄剧"

    def init(self, extend=""):
        pass

    def getDependence(self):
        return ""

    def isVideoFormat(self, url):
        u = str(url or "").lower()
        return any(x in u for x in (".m3u8", ".mp4", ".mkv"))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def localProxy(self, param):
        """代理 m3u8，附带 CloudFront 签名 Cookie"""
        try:
            import base64
            from urllib.parse import unquote

            raw = param.get("url") or param.get("path") or ""
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", "ignore")
            # 支持 base64 或明文
            try:
                if not raw.startswith("http"):
                    raw = base64.b64decode(raw).decode("utf-8", "ignore")
            except Exception:
                pass
            raw = unquote(raw)
            if not raw.startswith("http"):
                return [404, "text/plain", b"bad url"]
            # cookie 存在 play 缓存的近似匹配
            cookie = ""
            for k, v in list(self._play_cache.items()):
                if v and v[0] and (raw.split("?")[0] in v[0] or v[0].split("?")[0] in raw):
                    cookie = v[1] or ""
                    break
            body, ctype, final = self._fetch_bytes(
                raw,
                extra_headers={"Cookie": cookie} if cookie else {},
                as_text=True,
            )
            if not body or "#EXTM3U" not in body:
                return [502, "text/plain", b"m3u8 fail"]
            # 相对路径改写为绝对
            base = final.rsplit("/", 1)[0] + "/"
            lines = []
            for line in body.splitlines():
                s = line.strip()
                if s and not s.startswith("#") and not s.startswith("http"):
                    lines.append(base + s)
                else:
                    lines.append(line)
            out = "\n".join(lines)
            return [200, "application/vnd.apple.mpegurl", out.encode("utf-8")]
        except Exception:
            return [500, "text/plain", b"proxy error"]

    def homeContent(self, filter):
        classes = [{"type_id": "all", "type_name": "全部"}]
        cats = self._get_json("%s/categories" % self.api)
        if isinstance(cats, list):
            for c in cats:
                name = str(c.get("name") or "")
                slug = str(c.get("slug") or "")
                if not slug or not name:
                    continue
                if self._skip_minor(name) or self._skip_minor(slug):
                    continue
                # 跳过剧情关键词垃圾分类（超长 slug）
                if len(slug) > 40 or len(name) > 20:
                    continue
                if int(c.get("dramaCount") or 0) <= 0:
                    continue
                classes.append({"type_id": slug, "type_name": name})
        result = {"class": classes}
        if filter:
            result["filters"] = {c["type_id"]: [] for c in classes}
        return result

    def homeVideoContent(self):
        return self.categoryContent("all", "1", False, {})

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = max(1, int(pg or 1))
        except Exception:
            page = 1
        tid = str(tid or "all")
        if tid in ("all", "", "0"):
            url = "%s/dramas?page=%s&pageSize=24" % (self.api, page)
        else:
            url = "%s/dramas?page=%s&pageSize=24&category=%s" % (
                self.api,
                page,
                self._quote(tid),
            )
        data = self._get_json(url) or {}
        items = self._map_items(data.get("items") or [])
        total = int(data.get("total") or 0)
        page_size = int(data.get("pageSize") or 24) or 24
        pagecount = max(1, (total + page_size - 1) // page_size) if total else max(1, page)
        return {
            "list": items,
            "page": page,
            "pagecount": pagecount,
            "limit": page_size,
            "total": total or len(items),
        }

    def searchContent(self, key, quick, pg="1"):
        try:
            page = max(1, int(pg or 1))
        except Exception:
            page = 1
        q = str(key or "").strip()
        if not q:
            return {"list": [], "page": 1, "pagecount": 1, "limit": 0, "total": 0}
        url = "%s/dramas?page=%s&pageSize=24&q=%s" % (self.api, page, self._quote(q))
        data = self._get_json(url) or {}
        items = self._map_items(data.get("items") or [])
        total = int(data.get("total") or 0)
        page_size = int(data.get("pageSize") or 24) or 24
        pagecount = max(1, (total + page_size - 1) // page_size) if total else max(1, page)
        return {
            "list": items,
            "page": page,
            "pagecount": pagecount,
            "limit": page_size,
            "total": total or len(items),
        }

    def detailContent(self, ids):
        raw = str(ids[0] if ids else "").strip()
        if not raw:
            return {"list": []}
        # vod_id = "{slug}-{id}"
        data = self._get_json("%s/dramas/%s" % (self.api, raw))
        if not data or not data.get("id"):
            return {"list": []}
        name = data.get("title") or raw
        if self._skip_minor(name) or self._skip_minor(data.get("description") or ""):
            return {"list": []}
        pic = data.get("coverUrl") or data.get("coverHUrl") or ""
        desc = data.get("description") or data.get("seoDescription") or name
        eps = data.get("episodes") or []
        eps = [e for e in eps if e.get("playable") is not False]
        eps.sort(key=lambda x: int(x.get("epNo") or 0))
        if not eps:
            return {
                "list": [
                    {
                        "vod_id": raw,
                        "vod_name": name,
                        "vod_pic": pic,
                        "vod_content": desc,
                        "vod_play_from": "提示",
                        "vod_play_url": "暂无$0",
                    }
                ]
            }
        play = []
        for e in eps:
            eid = e.get("id")
            ep_no = e.get("epNo") or ""
            title = e.get("title") or ("第%s集" % ep_no)
            play.append("%s$%s" % (title, eid))
        return {
            "list": [
                {
                    "vod_id": raw,
                    "vod_name": name,
                    "vod_pic": pic,
                    "vod_content": desc,
                    "vod_remarks": "共%s集" % (data.get("totalEpisodes") or len(eps)),
                    "vod_play_from": "红果黄剧",
                    "vod_play_url": "#".join(play),
                }
            ]
        }

    def playerContent(self, flag, id, vipFlags):
        eid = str(id or "").strip()
        if not eid or eid == "0":
            return {"parse": 0, "jx": 0, "url": "", "msg": "无播放地址"}
        # 已是 m3u8
        if eid.startswith("http") and ".m3u8" in eid:
            return {
                "parse": 0,
                "jx": 0,
                "url": eid,
                "header": {
                    "User-Agent": self.ua,
                    "Referer": self.host + "/",
                    "Origin": self.host,
                },
            }
        url, cookie = self._resolve_play(eid)
        if not url:
            return {"parse": 0, "jx": 0, "url": "", "msg": "取链失败"}
        headers = {
            "User-Agent": self.ua,
            "Referer": self.host + "/",
            "Origin": self.host,
        }
        if cookie:
            headers["Cookie"] = cookie
        return {"parse": 0, "jx": 0, "url": url, "header": headers}

    # ---------- helpers ----------
    def _map_items(self, arr):
        items = []
        for it in arr or []:
            did = it.get("id")
            slug = it.get("slug") or ""
            title = it.get("title") or ""
            if not did:
                continue
            if self._skip_minor(title):
                continue
            vod_id = "%s-%s" % (slug, did) if slug else str(did)
            remarks = ""
            te = it.get("totalEpisodes")
            if te:
                remarks = "更新至%s集" % te
            items.append(
                {
                    "vod_id": vod_id,
                    "vod_name": title or vod_id,
                    "vod_pic": it.get("coverUrl") or "",
                    "vod_remarks": remarks,
                }
            )
        return items

    def _resolve_play(self, episode_id):
        if episode_id in self._play_cache:
            return self._play_cache[episode_id]
        # 用 curl 拿 Set-Cookie
        try:
            import subprocess
            import json
            import tempfile
            import os

            jar = tempfile.NamedTemporaryFile(delete=False, suffix=".jar")
            jar.close()
            cmd = [
                "curl",
                "-sL",
                "--max-time",
                "20",
                "-A",
                self.ua,
                "-H",
                "Accept: application/json",
                "-H",
                "Origin: %s" % self.host,
                "-H",
                "Referer: %s/" % self.host,
                "-c",
                jar.name,
                "-b",
                jar.name,
                "%s/play/%s" % (self.api, episode_id),
            ]
            out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
            data = json.loads(out.decode("utf-8", "ignore"))
            play_url = data.get("url") or ""
            cookie = self._jar_to_cookie(jar.name)
            try:
                os.unlink(jar.name)
            except Exception:
                pass
            if play_url:
                self._play_cache[episode_id] = (play_url, cookie)
                return play_url, cookie
        except Exception:
            pass
        # 回落 requests（可能无签名 cookie）
        data = self._get_json("%s/play/%s" % (self.api, episode_id)) or {}
        play_url = data.get("url") or ""
        if play_url:
            self._play_cache[episode_id] = (play_url, "")
            return play_url, ""
        return "", ""

    @staticmethod
    def _jar_to_cookie(path):
        try:
            parts = []
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.startswith("#") and not line.startswith("#HttpOnly_"):
                        continue
                    line = line.replace("#HttpOnly_", "", 1)
                    cols = line.strip().split("\t")
                    if len(cols) >= 7:
                        parts.append("%s=%s" % (cols[5], cols[6]))
            return "; ".join(parts)
        except Exception:
            return ""

    def _get_json(self, url):
        text = self._fetch(url)
        if not text:
            return None
        try:
            import json

            return json.loads(text)
        except Exception:
            return None

    def _fetch(self, url):
        try:
            import subprocess

            cmd = [
                "curl",
                "-sL",
                "--max-time",
                "20",
                "-A",
                self.ua,
                "-H",
                "Accept: application/json",
                "-H",
                "Origin: %s" % self.host,
                "-H",
                "Referer: %s/" % self.host,
                url,
            ]
            out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
            return out.decode("utf-8", "ignore")
        except Exception:
            pass
        try:
            import requests
            import urllib3

            urllib3.disable_warnings()
            r = requests.get(url, headers=self.headers, timeout=15, verify=False)
            if r.status_code == 200:
                return r.text
        except Exception:
            pass
        return ""

    def _fetch_bytes(self, url, extra_headers=None, as_text=False):
        try:
            import subprocess

            cmd = [
                "curl",
                "-sL",
                "--max-time",
                "20",
                "-A",
                self.ua,
                "-e",
                self.host + "/",
                "-H",
                "Origin: %s" % self.host,
                "-w",
                "\n%{http_code}\n%{url_effective}",
            ]
            if extra_headers:
                for k, v in extra_headers.items():
                    if v:
                        cmd.extend(["-H", "%s: %s" % (k, v)])
            cmd.append(url)
            out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
            text = out.decode("utf-8", "ignore")
            parts = text.rsplit("\n", 2)
            if len(parts) >= 3:
                body, code, final = parts[0], parts[1], parts[2]
            else:
                body, code, final = text, "0", url
            return (body if as_text else body.encode("utf-8")), code, final
        except Exception:
            return ("" if as_text else b""), "0", url

    @staticmethod
    def _skip_minor(name):
        n = (name or "").lower()
        keys = (
            "萝莉",
            "幼女",
            "小学生",
            "中学生",
            "高三",
            "校园",
            "学生",
            "loli",
            "underage",
            "未成年",
            "女童",
            "师生",
        )
        return any(k in n for k in keys)

    @staticmethod
    def _quote(s):
        try:
            from urllib.parse import quote

            return quote(str(s), safe="")
        except Exception:
            return str(s)
