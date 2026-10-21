# coding: utf-8
# ============================================================
# 站点：MoboReels 畅读热剧  https://www.moboreels.com/cn/
# 架构：Nuxt SSR，数据内联在 window.__NUXT__（JS 压缩 payload）
# 解析：纯 Python 解析（形参->实参 映射 + 变量替换），不依赖 node
# 内容类型：竖屏短剧
# 播放：播放页 detail.resolvedMediaUrl 为带签名直链（mp4/m3u8）
# 主域名：https://www.moboreels.com
# 最后验证：2026-09-24
# ============================================================
import re
from urllib.parse import quote, urljoin, unquote

from base.spider import Spider as BaseSpider


class Spider(BaseSpider):

    def __init__(self):
        self.host = "https://www.moboreels.com"
        self.lang = "cn"
        self.classes = [
            {"type_id": "逆袭", "type_name": "逆袭"},
            {"type_id": "现代言情", "type_name": "现代言情"},
            {"type_id": "总裁", "type_name": "总裁"},
            {"type_id": "反击", "type_name": "反击"},
            {"type_id": "都市生活", "type_name": "都市生活"},
            {"type_id": "复仇", "type_name": "复仇"},
            {"type_id": "穿越重生", "type_name": "穿越重生"},
            {"type_id": "逆袭反转", "type_name": "逆袭反转"},
            {"type_id": "豪门恩怨", "type_name": "豪门恩怨"},
            {"type_id": "甜宠", "type_name": "甜宠"},
            {"type_id": "现代都市", "type_name": "现代都市"},
            {"type_id": "隐藏身份", "type_name": "隐藏身份"},
            {"type_id": "王妃", "type_name": "王妃"},
            {"type_id": "战神", "type_name": "战神"},
            {"type_id": "宫斗", "type_name": "宫斗"},
            {"type_id": "东方玄幻", "type_name": "东方玄幻"},
            {"type_id": "重生", "type_name": "重生"},
            {"type_id": "虐恋", "type_name": "虐恋"},
            {"type_id": "家庭亲情", "type_name": "家庭亲情"},
            {"type_id": "系统", "type_name": "系统"},
            {"type_id": "乡村", "type_name": "乡村"},
            {"type_id": "神医", "type_name": "神医"},
            {"type_id": "大女主", "type_name": "大女主"},
            {"type_id": "萌宝", "type_name": "萌宝"},
            {"type_id": "断亲", "type_name": "断亲"},
            {"type_id": "打脸", "type_name": "打脸"},
            {"type_id": "古装权谋", "type_name": "古装权谋"},
            {"type_id": "闪婚", "type_name": "闪婚"},
            {"type_id": "先婚后爱", "type_name": "先婚后爱"},
            {"type_id": "轻喜剧", "type_name": "轻喜剧"},
        ]
        self.filters = {}
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            "Referer": self.host + "/",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

    def getName(self):
        return "畅读热剧"

    def getDependence(self):
        return []

    def init(self, extend=""):
        self.extend = extend or ""

    def getHomeContent(self, filter):
        return self.homeContent(filter)

    def homeContent(self, filter):
        return {"class": self.classes, "filters": self.filters if filter else {}}

    # ---------------- 网络 ----------------

    def _get(self, url, timeout=25):
        try:
            r = self.fetch(url, headers=self.headers, timeout=timeout)
            if r and getattr(r, "status_code", 0) == 200:
                txt = getattr(r, "text", "") or ""
                if txt and "/drama/" in txt:
                    return txt
        except Exception:
            pass
        try:
            import urllib.request
            req = urllib.request.Request(url, headers=self.headers)
            resp = urllib.request.urlopen(req, timeout=timeout)
            return resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            self.log({"get_fail": url, "err": type(e).__name__})
            return ""

    # ---------------- 纯 Python 解析 Nuxt 压缩 payload ----------------

    @staticmethod
    def _split_top(s):
        out = []; buf = ""; depth = 0; instr = None; esc = False
        for ch in s:
            if esc: buf += ch; esc = False; continue
            if ch == "\\": buf += ch; esc = True; continue
            if instr:
                buf += ch
                if ch == instr: instr = None
                continue
            if ch in "\"'": instr = ch; buf += ch; continue
            if ch in "([{": depth += 1; buf += ch; continue
            if ch in ")]}": depth -= 1; buf += ch; continue
            if ch == "," and depth == 0:
                out.append(buf.strip()); buf = ""; continue
            buf += ch
        if buf.strip(): out.append(buf.strip())
        return out

    @staticmethod
    def _extract_bracket(s, start):
        open_ch = s[start]
        close_ch = "]" if open_ch == "[" else "}"
        depth = 0; instr = None; esc = False
        for idx in range(start, len(s)):
            ch = s[idx]
            if esc: esc = False; continue
            if ch == "\\": esc = True; continue
            if instr:
                if ch == instr: instr = None
                continue
            if ch in "\"'": instr = ch; continue
            if ch == open_ch: depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0: return s[start:idx + 1]
        return ""

    @staticmethod
    def _get_objects(arr):
        objs = []; depth = 0; instr = None; esc = False; st = None
        for idx, ch in enumerate(arr):
            if esc: esc = False; continue
            if ch == "\\": esc = True; continue
            if instr:
                if ch == instr: instr = None
                continue
            if ch in "\"'": instr = ch; continue
            if ch == "{":
                if depth == 0: st = idx
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and st is not None:
                    objs.append(arr[st:idx + 1]); st = None
        return objs

    @staticmethod
    def _js_val(v):
        v = v.strip()
        if v == "true": return True
        if v == "false": return False
        if v == "null": return None
        if re.match(r"^-?\d+$", v): return int(v)
        if re.match(r"^-?\d+\.\d+$", v): return float(v)
        if v.startswith('"') and v.endswith('"'):
            return v[1:-1].replace("\\u002F", "/").replace("\\/", "/").replace('\\"', '"')
        return v

    def _obj_to_dict(self, o):
        s = o.strip()
        if s.startswith("{"): s = s[1:]
        if s.endswith("}"): s = s[:-1]
        d = {}
        for p in self._split_top(s):
            mm = re.match(r"\s*([a-zA-Z0-9_]+)\s*:\s*(.*)$", p, re.S)
            if not mm: continue
            d[mm.group(1)] = self._js_val(mm.group(2))
        return d

    def _parse_nuxt(self, html):
        i = html.find("window.__NUXT__=")
        if i < 0: return {}, ""
        k = html.find("</script", i)
        if k < 0: k = len(html)
        expr = html[i + len("window.__NUXT__="):k].strip().rstrip(";").rstrip()
        m = re.match(r"\(function\(([^)]*)\)\{(.*)\}\((.*)\)\)$", expr, re.S)
        if not m: return {}, ""
        params = [x.strip() for x in m.group(1).split(",")]
        body = m.group(2)
        args = self._split_top(m.group(3))
        return dict(zip(params, args)), body

    def _resolve_obj(self, o, vmap):
        def rep(mm):
            return mm.group(1) + vmap.get(mm.group(2), mm.group(2))
        return re.sub(r"([,{]\s*[a-zA-Z0-9_]+:)([a-zA-Z_$][a-zA-Z0-9_$]*)(?=\s*[,}])", rep, o)

    def _parse_episodes(self, html):
        vmap, body = self._parse_nuxt(html)
        if not vmap: return []
        idx = body.find("list:[")
        if idx < 0: return []
        arr = self._extract_bracket(body, idx + len("list:"))
        if not arr: return []
        eps = []
        for o in self._get_objects(arr):
            ro = self._resolve_obj(o, vmap)
            d = self._obj_to_dict(ro)
            eps.append({
                "episNum": d.get("episNum"),
                "mediaUrl": d.get("mediaUrl", ""),
                "isLock": d.get("isLock"),
                "coverUrl": d.get("coverUrl", ""),
            })
        return eps

    def _parse_series(self, html):
        vmap, body = self._parse_nuxt(html)
        if not vmap: return {}
        idx = body.find("series:{")
        if idx < 0: return {}
        o = self._extract_bracket(body, idx + len("series:"))
        if not o: return {}
        return self._obj_to_dict(self._resolve_obj(o, vmap))

    def _parse_detail_media(self, html):
        vmap, body = self._parse_nuxt(html)
        if not vmap: return ""
        idx = body.find("detail:{")
        if idx < 0: return ""
        o = self._extract_bracket(body, idx + len("detail:"))
        if not o: return ""
        d = self._obj_to_dict(self._resolve_obj(o, vmap))
        media = d.get("resolvedMediaUrl") or d.get("mediaUrl") or ""
        if not media or not re.match(r"^https?://", str(media)):
            m = re.search(r"resolvedMediaUrl:([a-zA-Z0-9_$]+)", o)
            if m: media = vmap.get(m.group(1), "")
            if not media or not re.match(r"^https?://", str(media)):
                m = re.search(r"mediaUrl:([a-zA-Z0-9_$]+)", o)
                if m: media = vmap.get(m.group(1), "")
        return media or ""

    # ---------------- DOM 卡片 ----------------

    def _parse_cards(self, html):
        items = []
        seen = set()
        if not html:
            return items
        pats = [
            re.compile(r'<a[^>]+href="(/drama/[^"]+)"[^>]*>(.*?)</a>', re.S),
            re.compile(r'<a[^>]+href="(/drama/[^"]+)"[^>]*>', re.S),
        ]
        for pat in pats:
            for m in pat.finditer(html):
                href = m.group(1)
                block = m.group(2) if m.lastindex and m.lastindex >= 2 else ""
                if href in seen:
                    continue
                seen.add(href)
                t = re.search(r'alt="([^"]+)"', block)
                title = t.group(1) if t else ""
                if not title:
                    t2 = re.search(r'class="[^"]*title[^"]*"[^>]*>([^<]+)<', block)
                    title = t2.group(1) if t2 else ""
                p = re.search(r'(?:data-src|src)="([^"]+)"', block)
                pic = p.group(1) if p else ""
                if pic:
                    pic = re.sub(r"\?imageMogr2.*$", "", pic)
                if not title:
                    title = unquote(href.split("/drama/")[-1]).rsplit("-", 1)[0]
                if not title:
                    continue
                items.append({
                    "vod_id": href,
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_remarks": "",
                })
            if items:
                break
        return items

    # ---------------- 首页 / 分类 / 搜索 ----------------

    def homeVideoContent(self):
        html = self._get(self.host + "/" + self.lang + "/")
        items = self._parse_cards(html)
        if not items and html:
            seen = set()
            for m in re.finditer(r'href="(/drama/[^"]+)"', html):
                href = m.group(1)
                if href in seen:
                    continue
                seen.add(href)
                title = unquote(href.split("/drama/")[-1]).rsplit("-", 1)[0]
                if not title:
                    continue
                items.append({
                    "vod_id": href,
                    "vod_name": title,
                    "vod_pic": "",
                    "vod_remarks": "",
                })
        return {"list": items}

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg or 1)
        tag = quote(str(tid), safe="")
        if page <= 1:
            url = "%s/%s/dramas/%s" % (self.host, self.lang, tag)
        else:
            url = "%s/%s/dramas/%s/page/%d" % (self.host, self.lang, tag, page)
        html = self._get(url)
        items = self._parse_cards(html)
        pagecount = page + 1
        m = re.search(r'(\d+)\s*/\s*(\d+)', html)
        if m:
            try:
                pagecount = int(m.group(2))
            except Exception:
                pass
        return {
            "list": items,
            "page": page,
            "pagecount": pagecount,
            "limit": 30,
            "total": pagecount * 30,
        }

    def searchContent(self, key, quick, pg="1"):
        k = quote(str(key), safe="")
        url = "%s/%s/search/%s" % (self.host, self.lang, k)
        html = self._get(url)
        return {"list": self._parse_cards(html), "page": int(pg)}

    # ---------------- 详情 ----------------

    @staticmethod
    def _norm_ids(ids):
        if ids is None:
            return ""
        if isinstance(ids, (list, tuple)):
            if not ids:
                return ""
            ids = ids[0]
        if isinstance(ids, bytes):
            ids = ids.decode("utf-8", errors="ignore")
        return str(ids).strip()

    def _skeleton(self, vid, title="", pic="", remarks=""):
        pid = str(vid).replace("$", "|")
        return {"list": [{
            "vod_id": vid,
            "vod_name": title or "未知标题",
            "vod_pic": pic or "",
            "vod_remarks": remarks or "",
            "vod_content": "",
            "vod_play_from": "畅读热剧",
            "vod_play_url": "第1集$" + pid,
        }]}

    def detailContent(self, ids):
        raw = self._norm_ids(ids)
        if not raw:
            return {"list": []}
        if raw.startswith("http"):
            url = raw
        else:
            url = urljoin(self.host + "/", raw.lstrip("/"))
        html = self._get(url)
        if not html:
            return self._skeleton(raw)

        series = self._parse_series(html) or {}
        eps = self._parse_episodes(html) or []

        name = series.get("seriesName") or ""
        if not name:
            m = re.search(r"<title>([^<]+)</title>", html)
            if m:
                name = re.sub(r"短剧.*$", "", m.group(1)).strip()
        cover = series.get("coverUrl") or ""
        desc = series.get("description") or ""
        total = series.get("allEpis") or len(eps)

        if not eps:
            return self._skeleton(raw, name, cover, desc)

        slug = raw.split("/drama/")[-1] if "/drama/" in raw else raw
        mslug = re.match(r"^(.*)-(\d+)$", slug)
        if mslug:
            title_enc, sid = mslug.group(1), mslug.group(2)
        else:
            title_enc, sid = slug, ""

        play_urls = []
        for ep in eps:
            num = ep.get("episNum")
            if num is None:
                continue
            try:
                num = int(num)
            except Exception:
                continue
            ep_url = "/episode/%s-%s-%02d" % (title_enc, sid, num) if sid else ""
            ep_url = ep_url.replace("$", "|")
            play_urls.append("第%d集$%s" % (num, ep_url))

        if not play_urls:
            return self._skeleton(raw, name, cover, desc)

        vod = {
            "vod_id": raw,
            "vod_name": name or "短剧",
            "vod_pic": cover,
            "vod_remarks": "共%s集" % str(total),
            "vod_content": desc,
            "vod_play_from": "畅读热剧",
            "vod_play_url": "#".join(play_urls),
        }
        return {"list": [vod]}

    # ---------------- 播放 ----------------

    def playerContent(self, flag, id, vipFlags):
        pid = str(id or "").strip()
        if not pid:
            return {"parse": 1, "url": "", "header": self.headers}

        if re.match(r"^https?://", pid):
            return {
                "parse": 0,
                "url": pid,
                "header": {
                    "User-Agent": self.headers["User-Agent"],
                    "Referer": self.host + "/",
                },
            }

        url = urljoin(self.host + "/", pid.lstrip("/"))
        html = self._get(url)
        if html:
            media = self._parse_detail_media(html)
            if media and re.match(r"^https?://", media):
                return {
                    "parse": 0,
                    "url": media,
                    "header": {
                        "User-Agent": self.headers["User-Agent"],
                        "Referer": self.host + "/",
                    },
                }
        return {"parse": 1, "url": url, "header": self.headers}

    def destroy(self):
        try:
            self.session = None
        except Exception:
            pass
