#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import re
import json
import base64
import html as html_lib
import urllib.request
import urllib.parse
from urllib.parse import urlparse, quote, unquote
import http.cookiejar
import gzip
import zlib
import ssl
import time
import socket
import threading

try:
    from base.spider import Spider as SpiderBase
except ImportError:
    class SpiderBase(object):
        def getCache(self, key): return None
        def setCache(self, key, value): return "fail"
        def delCache(self, key): return "fail"

def format_remarks(brand="蘑菇视频", meta=""):
    clean_meta = str(meta or "").strip()
    clean_meta = re.sub(r"[\r\n\t]+", " ", clean_meta).strip()
    if clean_meta:
        return "%s | %s" % (brand, clean_meta)
    return brand

def clean_label(text):
    t = str(text or "").strip()
    t = re.sub(r"[\$#\r\n\t]+", " ", t)
    return t.strip()


# ============================================================
# AutoDNS —— 无视梯子状态的自动路由
# ------------------------------------------------------------
# 目标：不管当前设备有没有开 VPN，都让源站域名能通。
# 策略：
#   1) 系统 DNS 优先（快速、少绕路）
#   2) 系统 DNS 拿到 0.0.0.0 / :: / 空 → 视为污染，走 DoH
#   3) 系统 DNS 完全解析失败 → 直接走 DoH
#   4) 通过 DoH 拿到真实 IP 后缓存 10 分钟
#   5) 全局 monkey-patch socket.getaddrinfo：任何库发起的
#      DNS 都自动走 AutoDNS（urllib / requests 都受益）
#   6) _fetch 内再加一层 IP 直连兜底（SNI 保留原域名），
#      即使 monkey-patch 没生效也能救活
# ============================================================

AUTO_DNS_CACHE_TTL = 600  # 10 分钟

_BAD_ADDRS = ("0.0.0.0", "0.0.0.0/8", "127.0.0.0", "127.0.0.1", "::", "::1")

_DOH_ENDPOINTS = [
    ("https://223.5.5.5/resolve?name={h}&type=A", "AliDNS"),
    ("https://doh.pub/dns-query?name={h}&type=A", "TencentDoH"),
    ("https://1.1.1.1/dns-query?name={h}&type=A", "CloudflareDoH"),
    ("https://dns.google/resolve?name={h}&type=A", "GoogleDoH"),
    ("https://8.8.8.8/resolve?name={h}&type=A", "GoogleDoH-Direct"),
    ("https://doh.opendns.com/dns-query?name={h}&type=A", "OpenDNSDoH"),
]


class AutoDNS(object):
    """跨 DNS 自动解析：系统 → 多个 DoH。线程安全 + 缓存。"""

    def __init__(self):
        self._cache = {}
        self._lock = threading.Lock()
        self._ctx = ssl.create_default_context()
        self._ctx.check_hostname = False
        self._ctx.verify_mode = ssl.CERT_NONE
        self._doh_opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=self._ctx))

    def resolve(self, host):
        if not host or host.startswith("["):
            return []
        with self._lock:
            hit = self._cache.get(host)
            if hit and (time.time() - hit[0]) < AUTO_DNS_CACHE_TTL:
                return hit[1]

        ips = self._resolve_inner(host)
        if ips:
            with self._lock:
                self._cache[host] = (time.time(), ips)
        return ips

    def invalidate(self, host):
        with self._lock:
            self._cache.pop(host, None)

    def _resolve_inner(self, host):
        # 1) 系统 DNS
        try:
            infos = socket.getaddrinfo(
                host, 443, socket.AF_INET, socket.SOCK_STREAM)
            ips = [i[4][0] for i in infos
                   if i and len(i) > 4
                   and isinstance(i[4], tuple) and i[4]
                   and isinstance(i[4][0], str)
                   and i[4][0] not in _BAD_ADDRS]
            if ips:
                return list(dict.fromkeys(ips))
        except Exception:
            pass
        # 2) DoH 兜底
        return self._doh_resolve(host)

    def _doh_resolve(self, host):
        for tmpl, _name in _DOH_ENDPOINTS:
            try:
                url = tmpl.format(h=host)
                req = urllib.request.Request(url, headers={
                    "Accept": "application/dns-json",
                    "User-Agent": "curl/8.0",
                })
                try:
                    with self._doh_opener.open(req, timeout=4) as r:
                        raw = r.read()
                except urllib.error.HTTPError as e:
                    if e.code >= 500:
                        continue
                    raw = e.read()
                data = json.loads(raw.decode("utf-8", "ignore"))
                ans = data.get("Answer") or []
                ips = [a["data"] for a in ans
                       if a.get("type") == 1
                       and a.get("data")
                       and a["data"] not in _BAD_ADDRS]
                if ips:
                    return list(dict.fromkeys(ips))
            except Exception:
                continue
        return []


# 全局 AutoDNS 实例（模块级）
_autodns = AutoDNS()

_orig_getaddrinfo = socket.getaddrinfo


def _install_autodns():
    """把 socket.getaddrinfo 替换成 AutoDNS 兜底版本。幂等。"""
    if getattr(socket.getaddrinfo, "_autodns_patched", False):
        return

    def patched(host, port, family=0, type_=0, proto=0, flags=0):
        skip = (
            host is None
            or not isinstance(host, str)
            or host in ("localhost", "localhost.localdomain", "")
            or host.startswith("127.")
            or host == "127.0.0.1"
            or host.startswith("[")
        )
        try:
            result = _orig_getaddrinfo(host, port, family, type_, proto, flags)
            if skip:
                return result
            if isinstance(result, list) and result:
                cleaned = [r for r in result
                           if not (isinstance(r, tuple) and len(r) > 4
                                   and isinstance(r[4], tuple)
                                   and isinstance(r[4][0], str)
                                   and r[4][0] in _BAD_ADDRS)]
                if cleaned:
                    return cleaned
        except Exception:
            pass

        if skip:
            raise socket.gaierror("no such host: %r" % (host,))

        ips = _autodns.resolve(host)
        if ips:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))
                    for ip in ips]
        raise socket.gaierror("AutoDNS failed for %r" % (host,))

    patched._autodns_patched = True
    socket.getaddrinfo = patched


try:
    _install_autodns()
except Exception:
    pass


def _split_url(url):
    """把 URL 拆成 (scheme, host, port, path, params, query, frag) 等。"""
    try:
        p = urlparse(url)
        if not p.hostname:
            return None
        port = p.port or (443 if p.scheme == "https" else 80)
        return (p.scheme, p.hostname, port, p.path or "/", p.params or "",
                p.query or "", p.fragment or "",
                p.username, p.password)
    except Exception:
        return None


ZONE_MATRIX = [
    {
        "id": "zone_featured",
        "name": "🔥今日精选",
        "default": "route_home_featured",
        "subs": [
            {"n": "今日推荐", "v": "route_home_featured"},
            {"n": "顶级网黄", "v": "cate3"},
            {"n": "福利姬", "v": "cate4"},
            {"n": "传媒精选", "v": "cate6"},
            {"n": "JVID", "v": "cate7"},
            {"n": "锅锅酱", "v": "cate8"}
        ]
    },
    {
        "id": "zone_theme",
        "name": "💋热门主题",
        "default": "cate9",
        "subs": [
            {"n": "巨乳大奶", "v": "cate9"},
            {"n": "抖音风", "v": "cate10"},
            {"n": "樱花小猫", "v": "cate12"},
            {"n": "反差女友", "v": "cate13"},
            {"n": "调教性奴", "v": "cate15"},
            {"n": "ASMR", "v": "cate16"},
            {"n": "高潮自慰", "v": "cate18"},
            {"n": "露出野战", "v": "cate20"},
            {"n": "SWAG", "v": "cate21"},
            {"n": "绿帽淫妻", "v": "cate23"},
            {"n": "群交滥交", "v": "cate24"},
            {"n": "风骚少妇", "v": "cate25"},
            {"n": "AI女神", "v": "cate27"},
            {"n": "风骚母狗", "v": "cate28"},
            {"n": "断袖男同", "v": "cate29"},
            {"n": "原创短剧", "v": "cate30"},
            {"n": "足交口爆", "v": "cate31"},
            {"n": "炮桶小屋", "v": "cate32"},
            {"n": "无套内射", "v": "cate33"},
            {"n": "黑鬼长屌", "v": "cate34"},
            {"n": "女同百合", "v": "cate35"},
            {"n": "伪娘人妖", "v": "cate36"}
        ]
    },
    {
        "id": "zone_creator",
        "name": "💃网红达人",
        "default": "cate37",
        "subs": [
            {"n": "吴梦梦", "v": "cate37"},
            {"n": "网黄", "v": "cate38"},
            {"n": "umate原创", "v": "cate39"},
            {"n": "Naomii", "v": "cate40"},
            {"n": "YuiPeach", "v": "cate41"},
            {"n": "唐伯虎", "v": "cate42"},
            {"n": "饼干姐姐", "v": "cate43"},
            {"n": "台北娜娜", "v": "cate44"},
            {"n": "MASKU", "v": "cate45"},
            {"n": "Xreind", "v": "cate46"},
            {"n": "小桃酱", "v": "cate47"},
            {"n": "安安小晗", "v": "cate48"},
            {"n": "柚子猫", "v": "cate49"},
            {"n": "王梨奈", "v": "cate50"},
            {"n": "辛尤里", "v": "cate51"},
            {"n": "粉色情人", "v": "cate52"},
            {"n": "阿朱", "v": "cate53"},
            {"n": "奶咪", "v": "cate54"},
            {"n": "有根棒棒", "v": "cate55"},
            {"n": "不见星空", "v": "cate56"},
            {"n": "Kitty", "v": "cate57"},
            {"n": "妮可", "v": "cate58"},
            {"n": "Cos女神", "v": "cate59"},
            {"n": "玩偶姊姊", "v": "cate60"},
            {"n": "司雨", "v": "cate61"},
            {"n": "谭晓彤", "v": "cate62"},
            {"n": "刘玥", "v": "cate63"},
            {"n": "Vivian", "v": "cate64"},
            {"n": "多乙", "v": "cate65"},
            {"n": "朱可儿", "v": "cate66"},
            {"n": "周大萌", "v": "cate67"}
        ]
    },
    {
        "id": "zone_media",
        "name": "🎬传媒厂牌",
        "default": "cate69",
        "subs": [
            {"n": "麻豆传媒", "v": "cate69"},
            {"n": "蜜桃传媒", "v": "cate70"},
            {"n": "葫芦影业", "v": "cate71"},
            {"n": "香蕉视频", "v": "cate72"},
            {"n": "兔子先生", "v": "cate73"},
            {"n": "OnlyFans", "v": "cate74"},
            {"n": "91制片厂", "v": "cate75"},
            {"n": "ED Mosaic", "v": "cate76"},
            {"n": "IBiZa Media", "v": "cate77"},
            {"n": "SA国际传媒", "v": "cate78"},
            {"n": "乌托邦", "v": "cate79"},
            {"n": "大象传媒", "v": "cate80"},
            {"n": "天美传媒", "v": "cate81"},
            {"n": "扣扣传媒", "v": "cate82"},
            {"n": "性视界", "v": "cate83"},
            {"n": "星空传媒", "v": "cate84"},
            {"n": "映秀传媒", "v": "cate85"},
            {"n": "杏吧原版", "v": "cate86"},
            {"n": "果冻传媒", "v": "cate87"},
            {"n": "爱神传媒", "v": "cate88"},
            {"n": "爱豆传媒", "v": "cate89"},
            {"n": "精东影业", "v": "cate90"},
            {"n": "糖心Vlog", "v": "cate91"},
            {"n": "萝莉社", "v": "cate92"}
        ]
    },
    {
        "id": "zone_cos",
        "name": "🎀福利姬社",
        "default": "cate94",
        "subs": [
            {"n": "桥本香菜", "v": "cate94"},
            {"n": "米菲兔", "v": "cate95"},
            {"n": "捅主任", "v": "cate96"},
            {"n": "npxvip", "v": "cate97"},
            {"n": "Andm", "v": "cate98"},
            {"n": "liburin", "v": "cate99"},
            {"n": "谭晓彤", "v": "cate100"},
            {"n": "小水水", "v": "cate101"},
            {"n": "小鸟酱", "v": "cate102"},
            {"n": "HAMAR", "v": "cate103"},
            {"n": "铃木美子", "v": "cate104"},
            {"n": "占星猫", "v": "cate105"},
            {"n": "芋圆呀", "v": "cate106"},
            {"n": "小丁妹妹", "v": "cate107"},
            {"n": "米娜学姐", "v": "cate108"},
            {"n": "米胡桃", "v": "cate109"},
            {"n": "萌白酱", "v": "cate110"},
            {"n": "麻酥酥", "v": "cate111"},
            {"n": "白桃少女", "v": "cate112"},
            {"n": "八月未央", "v": "cate113"}
        ]
    },
    {
        "id": "zone_melon",
        "name": "🍉黑料吃瓜",
        "default": "cate115",
        "subs": [
            {"n": "网红大瓜", "v": "cate115"},
            {"n": "校园猛料", "v": "cate116"},
            {"n": "大奶孕妇", "v": "cate117"},
            {"n": "独家泄密", "v": "cate118"},
            {"n": "热门吃瓜", "v": "cate119"},
            {"n": "潜规则", "v": "cate120"},
            {"n": "反差泄露", "v": "cate121"},
            {"n": "裸贷风波", "v": "cate122"},
            {"n": "轮奸呀", "v": "cate123"},
            {"n": "饥渴新娘", "v": "cate124"},
            {"n": "强奸醉奸", "v": "cate125"},
            {"n": "迷奸", "v": "cate126"}
        ]
    },
    {
        "id": "zone_pornhub",
        "name": "🌐P站精选",
        "default": "cate128",
        "subs": [
            {"n": "AnnyWalker", "v": "cate128"},
            {"n": "MilaAzul", "v": "cate129"},
            {"n": "Comatozze", "v": "cate130"},
            {"n": "Honey", "v": "cate131"},
            {"n": "Luxury", "v": "cate132"},
            {"n": "kittyxk", "v": "cate133"},
            {"n": "JennyKitty", "v": "cate134"},
            {"n": "LeoLulu", "v": "cate135"},
            {"n": "PurpleB", "v": "cate136"},
            {"n": "MilaLioness", "v": "cate137"},
            {"n": "Pinklov", "v": "cate138"},
            {"n": "PornForce", "v": "cate139"},
            {"n": "Shinaryen", "v": "cate140"},
            {"n": "EvaElfie", "v": "cate141"},
            {"n": "Candy", "v": "cate142"},
            {"n": "Kenzie", "v": "cate143"},
            {"n": "CarlaCu", "v": "cate144"},
            {"n": "webto", "v": "cate145"},
            {"n": "SiaSib", "v": "cate146"}
        ]
    },
    {
        "id": "zone_flower",
        "name": "🔎探花寻芳",
        "default": "cate148",
        "subs": [
            {"n": "沈先生", "v": "cate148"},
            {"n": "赵总寻花", "v": "cate149"},
            {"n": "小天探花", "v": "cate150"},
            {"n": "换妻探花", "v": "cate151"},
            {"n": "七天探花", "v": "cate152"},
            {"n": "千人斩", "v": "cate153"},
            {"n": "午夜尋花", "v": "cate154"},
            {"n": "91大神", "v": "cate155"},
            {"n": "按摩会所", "v": "cate156"},
            {"n": "韩国嫖妓", "v": "cate157"},
            {"n": "陈先生", "v": "cate158"},
            {"n": "太子寻花", "v": "cate159"},
            {"n": "翼屌寻花", "v": "cate160"},
            {"n": "小宝寻花", "v": "cate161"},
            {"n": "文轩探花", "v": "cate162"}
        ]
    },
    {
        "id": "zone_taboo",
        "name": "🌪️逆天乱伦",
        "default": "cate164",
        "subs": [
            {"n": "兄妹情深", "v": "cate164"},
            {"n": "最爱岳母", "v": "cate165"},
            {"n": "淫荡儿媳", "v": "cate166"},
            {"n": "淫乱父女", "v": "cate167"},
            {"n": "照顾小侄女", "v": "cate168"},
            {"n": "师生恋情", "v": "cate169"},
            {"n": "母子情深", "v": "cate170"},
            {"n": "姐弟爱恋", "v": "cate171"},
            {"n": "调教嫂子", "v": "cate172"},
            {"n": "照顾小姨子", "v": "cate173"}
        ]
    },
    {
        "id": "zone_erotic",
        "name": "🔞精品三级",
        "default": "cate175",
        "subs": [
            {"n": "韩国三级", "v": "cate175"},
            {"n": "香港三级", "v": "cate176"},
            {"n": "台湾三级", "v": "cate177"},
            {"n": "欧洲情色", "v": "cate178"},
            {"n": "俄乌色情", "v": "cate179"},
            {"n": "越南菲律宾", "v": "cate180"},
            {"n": "印度情色", "v": "cate181"},
            {"n": "日本三级", "v": "cate182"},
            {"n": "美国色情", "v": "cate183"},
            {"n": "东南亚情色", "v": "cate184"}
        ]
    },
    {
        "id": "zone_live",
        "name": "📡火热直播",
        "default": "cate186",
        "subs": [
            {"n": "多人淫交", "v": "cate186"},
            {"n": "车震直播", "v": "cate187"},
            {"n": "日韩主播", "v": "cate188"},
            {"n": "户外直播", "v": "cate189"},
            {"n": "抖音网红", "v": "cate190"},
            {"n": "主播勾引", "v": "cate191"},
            {"n": "快手网红", "v": "cate192"},
            {"n": "对着你", "v": "cate193"},
            {"n": "AVOVE", "v": "cate194"},
            {"n": "MISSWAEM", "v": "cate195"},
            {"n": "妖骚蛇姬", "v": "cate196"},
            {"n": "大啵啵", "v": "cate197"},
            {"n": "虎牙辣妹", "v": "cate198"}
        ]
    },
    {
        "id": "zone_uniform",
        "name": "👗制服诱惑",
        "default": "cate200",
        "subs": [
            {"n": "古装诱惑", "v": "cate200"},
            {"n": "萝莉塔", "v": "cate201"},
            {"n": "空姐诱惑", "v": "cate202"},
            {"n": "丝袜诱惑", "v": "cate203"},
            {"n": "职场OL", "v": "cate204"},
            {"n": "清涩校服", "v": "cate205"},
            {"n": "三点泳装", "v": "cate206"},
            {"n": "JK短裙", "v": "cate207"},
            {"n": "女仆装", "v": "cate208"},
            {"n": "护士打针", "v": "cate209"},
            {"n": "国风旗袍", "v": "cate210"},
            {"n": "体操运动", "v": "cate211"},
            {"n": "其他制服", "v": "cate212"}
        ]
    },
    {
        "id": "zone_asia",
        "name": "🌸日韩精选",
        "default": "cate214",
        "subs": [
            {"n": "骑兵精选", "v": "cate214"},
            {"n": "高清优质", "v": "cate215"},
            {"n": "FC2高清", "v": "cate216"},
            {"n": "VR视觉", "v": "cate217"},
            {"n": "人妻巨乳", "v": "cate218"},
            {"n": "少女制服", "v": "cate219"},
            {"n": "药物迷奸", "v": "cate220"},
            {"n": "强暴系列", "v": "cate221"},
            {"n": "轮奸系列", "v": "cate222"},
            {"n": "筱田佑", "v": "cate223"},
            {"n": "森澤佳奈", "v": "cate224"},
            {"n": "三上悠亜", "v": "cate225"},
            {"n": "AkihoYoshizawa", "v": "cate226"},
            {"n": "神宮寺奈緒", "v": "cate227"},
            {"n": "藤森里穗", "v": "cate228"},
            {"n": "松本一香", "v": "cate229"},
            {"n": "乙爱丽丝", "v": "cate230"},
            {"n": "沙月芽衣", "v": "cate231"},
            {"n": "姬咲華", "v": "cate232"},
            {"n": "AliceOtsu", "v": "cate233"},
            {"n": "佐山愛", "v": "cate234"},
            {"n": "水果解說", "v": "cate235"}
        ]
    },
    {
        "id": "zone_west",
        "name": "🗽欧美洋马",
        "default": "cate237",
        "subs": [
            {"n": "推荐观看", "v": "cate237"},
            {"n": "颜值少女", "v": "cate238"},
            {"n": "网红洋马", "v": "cate239"},
            {"n": "CandyLove", "v": "cate240"},
            {"n": "丝袜制服", "v": "cate241"},
            {"n": "欧美剧情", "v": "cate242"},
            {"n": "AngelX", "v": "cate243"},
            {"n": "商场性交", "v": "cate244"},
            {"n": "情色按摩", "v": "cate245"},
            {"n": "捷克搭讪", "v": "cate246"},
            {"n": "肤若凝脂", "v": "cate247"},
            {"n": "SweetieFox", "v": "cate248"},
            {"n": "Morgpie", "v": "cate249"},
            {"n": "DianRider", "v": "cate250"},
            {"n": "BadCuteGirl", "v": "cate251"},
            {"n": "Ailish", "v": "cate252"},
            {"n": "SamanthaFlair", "v": "cate253"},
            {"n": "滥交群交", "v": "cate254"},
            {"n": "巨乳少女", "v": "cate255"},
            {"n": "黑人大屌", "v": "cate256"}
        ]
    },
    {
        "id": "zone_variety",
        "name": "🎭综艺娱乐",
        "default": "cate258",
        "subs": [
            {"n": "深夜保健室", "v": "cate258"},
            {"n": "王竹子教学", "v": "cate259"},
            {"n": "中指通一下", "v": "cate260"},
            {"n": "Misa米砂", "v": "cate261"},
            {"n": "小哥哥艾理", "v": "cate262"},
            {"n": "Dr.She", "v": "cate263"},
            {"n": "1G老湿", "v": "cate264"},
            {"n": "两性知识", "v": "cate265"},
            {"n": "麻豆综艺", "v": "cate266"},
            {"n": "户外搭讪", "v": "cate267"},
            {"n": "性愛大秀", "v": "cate268"},
            {"n": "女优训练营", "v": "cate269"},
            {"n": "情趣k歌房", "v": "cate270"},
            {"n": "小鹏奇啪行", "v": "cate271"},
            {"n": "性爱自修室", "v": "cate272"},
            {"n": "女神体育祭", "v": "cate273"},
            {"n": "屁孩日记", "v": "cate274"},
            {"n": "薇傲的性趣", "v": "cate275"},
            {"n": "一三蜜桃说", "v": "cate276"},
            {"n": "Carrie雨千", "v": "cate277"}
        ]
    },
    {
        "id": "zone_cinema",
        "name": "📽️影视影院",
        "default": "cate279",
        "subs": [
            {"n": "喜剧片", "v": "cate279"},
            {"n": "古装片", "v": "cate280"},
            {"n": "武侠片", "v": "cate281"},
            {"n": "枪战片", "v": "cate282"},
            {"n": "灾难片", "v": "cate283"},
            {"n": "冒险片", "v": "cate284"},
            {"n": "犯罪片", "v": "cate285"},
            {"n": "科幻片", "v": "cate286"},
            {"n": "动作片", "v": "cate287"},
            {"n": "恐怖片", "v": "cate288"}
        ]
    }
]

class Spider(SpiderBase):
    def __init__(self):
        super(Spider, self).__init__()
        self.siteUrl = "https://moguds.cc"
        self.cdnBase = "https://d2qyuoh1tjbp7d.cloudfront.net"
        self.brandActor = ""
        self.brandDirector = "蘑菇视频"
        self._ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        self.options = {}
        self._init_session()

    def _init_session(self):
        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE
        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj),
            urllib.request.HTTPSHandler(context=self.ctx)
        )

    def init(self, extend=""):
        if isinstance(extend, dict):
            self.options = extend
        elif extend:
            try:
                self.options = json.loads(extend)
            except Exception:
                self.options = {}

    def getName(self):
        return "蘑菇视频"

    def isVideoFormat(self, url):
        low = (url or "").lower()
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".mkv", ".avi", ".ts", ".mpd", "index.png"))

    def manualVideoCheck(self):
        return False

    def _fetch(self, target_url, data=None, referer=""):
        """统一请求入口：先走常规路径，失败后走 IP 直连兜底。"""
        if not target_url:
            return {"code": 0, "text": "", "bytes": b"", "err": "", "final_url": ""}
        if target_url.startswith("//"):
            target_url = "https:" + target_url
        elif target_url.startswith("/"):
            target_url = self.siteUrl + target_url

        try:
            _install_autodns()
        except Exception:
            pass

        result = self._fetch_internal(target_url, data, referer)

        if result is None or result.get("code", -1) != 200:
            try:
                fb = self._fetch_ip_direct(target_url, data, referer)
            except Exception:
                fb = None
            if fb is not None and fb.get("code", 0) > 0:
                return fb

        return result if result else {
            "code": -1, "text": "", "bytes": b"", "err": "empty", "final_url": target_url
        }

    def _fetch_internal(self, target_url, data=None, referer=""):
        """真正的 HTTP 请求。target_url 需为绝对 http(s) URL。"""
        headers = {
            "User-Agent": self._ua,
            "Referer": referer if referer else (self.siteUrl + "/"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "close"
        }

        req_data = None
        if data is not None:
            if isinstance(data, dict):
                req_data = urllib.parse.urlencode(data).encode("utf-8")
                headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
            elif isinstance(data, (bytes, str)):
                req_data = data.encode("utf-8") if isinstance(data, str) else data

        last_err = ""
        for attempt in range(3):
            try:
                req = urllib.request.Request(target_url, data=req_data, headers=headers)
                with self.opener.open(req, timeout=5) as resp:
                    code = resp.getcode()
                    final_url = resp.geturl()
                    raw = resp.read()
                    enc = getattr(resp, "headers", {}).get("Content-Encoding", "")
                    if raw.startswith(b"\x1f\x8b") or enc == "gzip":
                        raw = gzip.decompress(raw)
                    elif enc == "deflate":
                        try:
                            raw = zlib.decompress(raw)
                        except Exception:
                            raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                    try:
                        text = raw.decode("utf-8")
                    except Exception:
                        text = raw.decode("latin1", errors="ignore")
                    return {"code": code, "text": text, "bytes": raw, "err": "", "final_url": final_url}
            except urllib.error.HTTPError as e:
                last_err = "HTTP %s" % e.code
                if e.code in (451, 403, 429, 502, 503, 520, 521, 522) and attempt < 2:
                    self._init_session()
                    time.sleep(0.12)
                    continue
                err_raw = ""
                try:
                    err_raw = e.read().decode("utf-8", errors="ignore")
                except Exception:
                    pass
                return {"code": e.code, "text": err_raw, "bytes": b"", "err": str(e), "final_url": target_url}
            except Exception as e:
                last_err = str(e)
                if attempt < 2:
                    self._init_session()
                    time.sleep(0.12)
                    continue
                return {"code": -1, "text": "", "bytes": b"", "err": str(e), "final_url": target_url}

        return {"code": -1, "text": "", "bytes": b"", "err": last_err, "final_url": target_url}

    def _fetch_ip_direct(self, target_url, data=None, referer=""):
        """
        IP 直连兜底：AutoDNS 解析 → 把 URL 中的域名替换成 IP（保留 SNI）→ 逐个试。
        适用场景：DNS 被污染 / 返回 0.0.0.0 / 边缘 IP 区域封锁。
        """
        parts = _split_url(target_url)
        if not parts:
            return None
        scheme, host, port, path, params, query, frag, user, pw = parts
        if scheme != "https":
            return None

        ips = _autodns.resolve(host)
        if not ips:
            return None

        headers = {
            "User-Agent": self._ua,
            "Referer": referer if referer else (self.siteUrl + "/"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "close",
            "Host": host,
        }

        req_data = None
        if data is not None:
            if isinstance(data, dict):
                req_data = urllib.parse.urlencode(data).encode("utf-8")
                headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
            elif isinstance(data, (bytes, str)):
                req_data = data.encode("utf-8") if isinstance(data, str) else data

        url_no_frag = path + (("?" + query) if query else "")
        for ip in ips[:6]:
            try:
                direct_url = "https://%s%s" % (ip, url_no_frag)
                req = urllib.request.Request(direct_url, data=req_data, headers=headers)
                with self.opener.open(req, timeout=8) as resp:
                    code = resp.getcode()
                    final_url = resp.geturl()
                    raw = resp.read()
                    enc = getattr(resp, "headers", {}).get("Content-Encoding", "")
                    if raw.startswith(b"\x1f\x8b") or enc == "gzip":
                        raw = gzip.decompress(raw)
                    elif enc == "deflate":
                        try:
                            raw = zlib.decompress(raw)
                        except Exception:
                            raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                    try:
                        text = raw.decode("utf-8")
                    except Exception:
                        text = raw.decode("latin1", errors="ignore")
                    return {
                        "code": code,
                        "text": text,
                        "bytes": raw,
                        "err": "",
                        "final_url": final_url,
                    }
            except urllib.error.HTTPError as e:
                err_raw = ""
                try:
                    err_raw = e.read().decode("utf-8", errors="ignore")
                except Exception:
                    pass
                continue
            except Exception:
                continue
        return None

    def homeContent(self, filter):
        classes = []
        filters = {}
        for z in ZONE_MATRIX:
            classes.append({
                "type_name": z["name"],
                "type_id": z["id"]
            })
            if len(z["subs"]) > 1:
                filters[z["id"]] = [
                    {
                        "key": "sub",
                        "name": "细分分类",
                        "init": z["subs"][0]["v"],
                        "value": z["subs"]
                    }
                ]
        result = {"class": classes, "filters": filters}
        return result

    def homeVideoContent(self):
        return {"list": []}

    def _extract_clean_pic(self, inner_html):
        for attr in ("data-original", "data-src"):
            m = re.search(r'%s=["\']([^"\']+)["\']' % attr, inner_html, re.I)
            if m:
                cand = m.group(1).strip()
                if cand and not any(bad in cand.lower() for bad in ("loading.jpg", "loading.png", "placeholder", "default")):
                    if cand.startswith("/"):
                        return self.cdnBase + cand
                    return cand

        m_src = re.search(r'src=["\']([^"\']+)["\']', inner_html, re.I)
        if m_src:
            cand = m_src.group(1).strip()
            if cand and not any(bad in cand.lower() for bad in ("loading.jpg", "loading.png", "placeholder", "default")):
                if cand.startswith("/"):
                    return self.cdnBase + cand
                return cand

        return ""

    def _parse_video_cards(self, html):
        vod_list = []
        matches = re.finditer(r'<a[^>]+href=["\'](/video/\d+/?)[^"\']*["\'][^>]*>([\s\S]*?)</a>', html, re.I)
        seen_urls = set()

        for m in matches:
            v_url = m.group(1).strip()
            inner = m.group(2)
            if v_url in seen_urls:
                continue

            pic = self._extract_clean_pic(inner)

            title = ""
            title_m = re.search(r'(?:title=["\']([^"\']+)["\']|alt=["\']([^"\']+)["\']|<h\d[^>]*>([\s\S]*?)</h\d>)', inner, re.I)
            if title_m:
                title = re.sub(r'<[^>]+>', '', title_m.group(1) or title_m.group(2) or title_m.group(3) or "").strip()
            if not title:
                text_clean = re.sub(r'<[^>]+>', '', inner).strip()
                lines = [x.strip() for x in text_clean.splitlines() if len(x.strip()) > 3]
                if lines:
                    title = lines[0]

            dur_m = re.search(r'(\d{1,2}:\d{2}(?::\d{2})?)', inner)
            duration = dur_m.group(1) if dur_m else ""

            if v_url and (pic or title):
                seen_urls.add(v_url)
                vod_list.append({
                    "vod_id": v_url,
                    "vod_name": title if title else "",
                    "vod_pic": pic if pic.startswith("http") else (self.siteUrl + pic if pic else ""),
                    "vod_remarks": format_remarks("蘑菇视频", duration),
                    "style": {"type": "rect", "ratio": 1.78}
                })
        return vod_list

    def categoryContent(self, tid, pg, filter, extend):
        del filter
        zone_id = str(tid or "").strip("/")
        
        try:
            cur_page = int(str(pg or "1").strip())
        except Exception:
            cur_page = 1
        if cur_page < 1:
            cur_page = 1

        active_target = ""
        if isinstance(extend, dict) and extend.get("sub"):
            active_target = str(extend.get("sub")).strip()
        else:
            for z in ZONE_MATRIX:
                if z["id"] == zone_id:
                    active_target = z["default"]
                    break
        if not active_target:
            active_target = zone_id

        if active_target == "route_home_featured":
            target_path = "/" if cur_page == 1 else ("/page/%s/" % cur_page)
        else:
            if cur_page == 1:
                target_path = "/category/%s/" % active_target
            else:
                target_path = "/category/%s/%s/" % (active_target, cur_page)

        res = self._fetch(target_path)
        html = res.get("text", "")
        vod_list = self._parse_video_cards(html)

        has_more = len(vod_list) > 0
        calc_pagecount = cur_page + 1 if has_more else cur_page
        calc_total = (cur_page + 1) * 20 if has_more else cur_page * max(1, len(vod_list))

        return {
            "page": cur_page,
            "pagecount": calc_pagecount,
            "limit": 20,
            "total": calc_total,
            "list": vod_list
        }

    def _extract_play_stream(self, detail_html):
        m_data_url = re.search(r'id=["\']article-videos["\'][^>]*data-url=["\']([^"\']+)["\']', detail_html, re.I)
        if not m_data_url:
            m_data_url = re.search(r'data-url=["\']([^"\']+)["\'][^>]*id=["\']article-videos["\']', detail_html, re.I)
        if m_data_url:
            cand = m_data_url.group(1).strip()
            if cand:
                cand = cand.replace("\\u002F", "/").replace("\\/", "")
                if cand.startswith("//"):
                    cand = "https:" + cand
                elif cand.startswith("/"):
                    cand = self.cdnBase + cand
                elif not cand.startswith("http"):
                    cand = self.cdnBase + "/" + cand
                return cand

        m_js_url = re.search(r'(?:var\s+raw\s*=\s*|video_url\s*:\s*|url\s*:\s*)["\'](https?://[^\s"\'\$<>]+\.m3u8[^\s"\'\$<>]*)["\']', detail_html, re.I)
        if m_js_url:
            return m_js_url.group(1).replace("\\u002F", "/").replace("\\/", "")

        m_m3u8 = re.search(r'(https?://(?:(?!localhost|127\.0\.0\.1)[^\s"\'\$<>])+\.m3u8[^\s"\'\$<>]*)', detail_html, re.I)
        if m_m3u8:
            return m_m3u8.group(1).replace("\\u002F", "/").replace("\\/", "")

        m_mp4 = re.search(r'(https?://(?:(?!localhost|127\.0\.0\.1)[^\s"\'\$<>])+\.mp4[^\s"\'\$<>]*)', detail_html, re.I)
        if m_mp4:
            return m_mp4.group(1).replace("\\u002F", "/").replace("\\/", "")

        return ""

    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        detail_url = raw_id if raw_id.startswith("http") else (self.siteUrl + raw_id)
        res_d = self._fetch(detail_url)
        d_html = res_d.get("text", "")

        title_m = re.search(r'<title>(.*?)</title>', d_html, re.I | re.S)
        raw_title = title_m.group(1).strip() if title_m else "视频"
        main_title = re.sub(r'[-_].*$', '', raw_title).strip()

        real_stream = self._extract_play_stream(d_html)
        main_play_target = real_stream if real_stream else detail_url

        episodes = ["正片$%s@@@%s" % (main_play_target, quote(main_title))]

        rec_cards = self._parse_video_cards(d_html)
        seen_urls = set([raw_id, detail_url])
        rec_idx = 1
        poster_pic = ""

        for card in rec_cards:
            rec_id = card["vod_id"]
            if not poster_pic and card.get("vod_pic"):
                poster_pic = card["vod_pic"]
            if rec_id in seen_urls:
                continue
            seen_urls.add(rec_id)

            rec_title = card["vod_name"]
            clean_t = clean_label(rec_title)
            display_t = (clean_t[:20] + "...") if len(clean_t) > 20 else clean_t

            rec_full_url = self.siteUrl + rec_id if rec_id.startswith("/") else rec_id
            episodes.append("%02d·%s$%s@@@%s" % (rec_idx, display_t, rec_full_url, quote(rec_title)))
            rec_idx += 1
            if rec_idx > 24:
                break

        vod = {
            "vod_id": raw_id,
            "vod_name": main_title,
            "vod_pic": poster_pic,
            "vod_bg": poster_pic,
            "vod_background": poster_pic,
            "vod_banner": poster_pic,
            "vod_actor": self.brandActor,
            "vod_director": self.brandDirector,
            "vod_remarks": format_remarks("蘑菇视频", "全%s部连播" % len(episodes)),
            "vod_content": main_title,
            "vod_play_from": "蘑菇视频",
            "vod_play_url": "#".join(episodes)
        }
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        raw_val = str(id).strip()
        desc_title = ""
        if "@@@" in raw_val:
            target_page, raw_t = raw_val.split("@@@", 1)
            desc_title = unquote(raw_t)
        else:
            target_page = raw_val

        real_stream = target_page
        if not any(k in target_page.lower() for k in (".m3u8", ".mp4", ".ts")):
            res = self._fetch(target_page)
            cand = self._extract_play_stream(res.get("text", ""))
            if cand:
                real_stream = cand

        is_stream = any(k in real_stream.lower() for k in (".m3u8", ".mp4", ".ts"))
        result = {
            "parse": 0 if is_stream else 1,
            "playUrl": "",
            "url": real_stream,
            "header": {
                "User-Agent": self._ua,
                "Accept": "*/*",
                "Connection": "keep-alive"
            }
        }
        if desc_title:
            result["desc"] = desc_title
        return result

    def searchContent(self, key, quick, pg="1"):
        try:
            cur_page = int(str(pg or "1").strip())
        except Exception:
            cur_page = 1
        if cur_page < 1:
            cur_page = 1

        if cur_page == 1:
            search_url = "/search/%s/" % quote(key)
        else:
            search_url = "/search/%s/%s/" % (quote(key), cur_page)

        res = self._fetch(search_url)
        vod_list = self._parse_video_cards(res.get("text", ""))

        has_more = len(vod_list) > 0
        calc_pagecount = cur_page + 1 if has_more else cur_page
        calc_total = (cur_page + 1) * 20 if has_more else cur_page * max(1, len(vod_list))

        return {
            "page": cur_page,
            "pagecount": calc_pagecount,
            "limit": 20,
            "total": calc_total,
            "list": vod_list
        }

    def action(self, action):
        return {"msg": "ok"}

    def liveContent(self):
        return ""

    def localProxy(self, params):
        return [404, "text/plain; charset=utf-8", "Proxy not configured"]

    def destroy(self):
        self.options = {}