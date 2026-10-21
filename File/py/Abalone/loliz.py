# -*- coding: utf-8 -*-
import sys, json, time
sys.path.append('..')
try:
    from base.spider import Spider as _B
except ImportError:
    class _B: pass
try:
    import requests
    try:
        from requests.packages.urllib3.exceptions import InsecureRequestWarning
        requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
    except Exception:
        pass
except ImportError:
    requests = None

U = "Mozilla/5.0 (Linux; Android 12; TFY-AN00 Build/HONORTFY-AN00; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/92.0.4515.105 Mobile Safari/537.36 uni-app Html5Plus/1.0 (Immersed/33.0)"
DOMAIN_API = "https://lwncnss3api.cc/api/getapi.php"

DOMAIN_TTL = 3600
DOMAIN_TIMEOUT = 5
FAIL_COOLDOWN = 300
MAX_ATTEMPTS = 3
API_TIMEOUT = 10
TOKEN_TTL = 1800
TOKEN_RETRY = 300

CDN_SUFFIXES = (
    '.cloudfront.net', '.cloudfront.com', '.amazonaws.com', '.amazonaws.com.cn',
    '.akamai.net', '.fastly.net', '.azureedge.net', '.akamaized.net',
    '.cdn77.org', '.googleusercontent.com', '.gvt1.com',
    '.cloudflare.net', '.cdn.cloudflare.net',
)

BACKUP_DOMAINS = [
    "dag29jmgma1g.site", "ldngksapi.cc", "lagh23ksapi.cc", "ldagwhdgpi.cc",
    "lwetasdf3api.cc", "lwasga289api.cc", "lw2wthchhaapi.cc",
    "lwncnss3api.cc", "lw23412gaapi.cc"
]


class Spider(_B):

    def init(self, e=""):
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": U,
            "Accept-Encoding": "gzip",
            "Content-Type": "application/x-www-form-urlencoded"
        })
        self.s.verify = False
        self.token = ""
        self.token_at = 0
        self.token_tried_at = 0
        self.domains = list(BACKUP_DOMAINS)
        self.domains_loaded_at = 0
        self.working_domains = []
        self.fail_time = {}

    def getName(self):
        return "萝莉岛"

    def isVideoFormat(self, u):
        return ".m3u8" in u or ".mp4" in u or "preview" in u

    def manualVideoCheck(self):
        return False

    @staticmethod
    def _ok_domain(d):
        if not isinstance(d, str):
            return False
        d = d.strip().lower()
        if len(d) < 5 or '.' not in d:
            return False
        if d.endswith(('.test', '.invalid', '.local', '.localhost', '.example')):
            return False
        return not any(d.endswith(s) for s in CDN_SUFFIXES)

    def _load_domains(self, force=False):
        if not force and self.domains and time.time() - self.domains_loaded_at < DOMAIN_TTL:
            return
        self._fetch_domains()

    def _fetch_domains(self):
        data = {}
        try:
            r = requests.get(DOMAIN_API, timeout=10, verify=False)
            if r.status_code == 200:
                data = r.json()
        except Exception as e:
            print('[DOMAIN] fetch failed:', e)

        pools = list(BACKUP_DOMAINS)
        if isinstance(data, dict) and data.get('code') == 200:
            for key in ('data', 'blackdomain'):
                v = data.get(key)
                if isinstance(v, str):
                    try:
                        v = json.loads(v)
                    except Exception:
                        v = [v]
                if isinstance(v, list):
                    pools.extend(v)

        self.domains = []
        seen = set()
        for d in pools:
            if not self._ok_domain(d) or d in seen:
                continue
            seen.add(d)
            self.domains.append(d)
        self.domains_loaded_at = time.time()
        print('[DOMAIN] {} candidates'.format(len(self.domains)))

    def _test_domain(self, domain):
        hdr = {"User-Agent": U}
        for proto in ('https', 'http'):
            url = '{}://{}/api/setapp.php'.format(proto, domain)
            try:
                r = self.s.get(url, timeout=DOMAIN_TIMEOUT, verify=False)
            except Exception:
                try:
                    r = requests.get(url, timeout=DOMAIN_TIMEOUT, verify=False, headers=hdr)
                except Exception:
                    continue
            try:
                if r.status_code == 200:
                    return True
            except Exception:
                continue
        return False

    def _find_working_domain(self):
        try:
            now = time.time()
            for d in list(self.working_domains):
                if now - self.fail_time.get(d, 0) <= FAIL_COOLDOWN:
                    continue
                if self._test_domain(d):
                    return d
                self.fail_time[d] = now
                self.working_domains.remove(d)

            self._load_domains()
            for d in self.domains:
                if d in self.working_domains:
                    continue
                if now - self.fail_time.get(d, 0) <= FAIL_COOLDOWN:
                    continue
                if self._test_domain(d):
                    self.working_domains.append(d)
                    print('[DOMAIN] working: {}'.format(d))
                    return d
                self.fail_time[d] = now

            print('[DOMAIN] none available')
            return None
        except Exception as e:
            print('[DOMAIN] probe error:', e)
            return None

    def _pick_domain(self):
        if not self.working_domains:
            return self._find_working_domain()
        d = self.working_domains.pop(0)
        self.working_domains.append(d)
        return d

    def _request_api(self, path, method='post', data=None, params=None):
        err = None
        try:
            for i in range(1, MAX_ATTEMPTS + 1):
                d = self._pick_domain()
                if not d:
                    self._load_domains(force=True)
                    d = self._pick_domain()
                    if not d:
                        print('[REQUEST] no domain for', path)
                        return None
                for proto in ('https', 'http'):
                    url = '{}://{}{}'.format(proto, d, path)
                    try:
                        if method.lower() == 'get':
                            r = self.s.get(url, params=params, timeout=API_TIMEOUT, verify=False)
                        else:
                            r = self.s.post(url, data=data, params=params,
                                            timeout=API_TIMEOUT, verify=False)
                        if r.status_code == 200:
                            return r
                        err = 'HTTP {}'.format(r.status_code)
                    except Exception as e:
                        err = repr(e)
                if d in self.working_domains:
                    self.working_domains.remove(d)
                if i < MAX_ATTEMPTS:
                    print('[REQUEST] attempt {}/{} failed: {}'.format(i, MAX_ATTEMPTS, err))
            print('[REQUEST] {} failed after {} attempts: {}'.format(path, MAX_ATTEMPTS, err))
            return None
        except Exception as e:
            print('[REQUEST] {} error: {}'.format(path, e))
            return None

    def _ensure_token(self):
        now = time.time()
        if self.token:
            if now - self.token_at < TOKEN_TTL:
                return
        elif now - self.token_tried_at < TOKEN_RETRY:
            return
        self._register()
        self.token_tried_at = now
        if self.token:
            self.token_at = now

    def _register(self):
        try:
            r = self._request_api('/api/newreg.php', 'post',
                data={"device": "android", "ntoken": "", "channel_code": "vbtQg9D8"})
            if not r:
                print('[REGISTER] request failed')
                return
            try:
                tok = (r.json().get('user') or {}).get('token', '')
            except Exception:
                tok = ''
            if tok:
                self.token = str(tok)
                print('[REGISTER] ok')
            else:
                print('[REGISTER] no token')
        except Exception as e:
            print('[REGISTER]', e)

    def homeContent(self, filter=False):
        try:
            self._ensure_token()
            r = self._request_api('/api/setapp.php', 'get')
            if not r:
                raise Exception('no response')
            try:
                data = r.json()
            except Exception as e:
                print('[HOME] json error:', e)
                return {"class": [], "filters": {}}
            classes, filters = [], {}
            for tab in (data.get('vodtab') or []) + (data.get('vodtaban') or []):
                if not isinstance(tab, dict):
                    continue
                tid = str(tab.get('type_id') or '')
                name = tab.get('type_name') or ''
                if not tid or not name:
                    continue
                classes.append({"type_id": tid, "type_name": name})
                vals = [{"n": "全部", "v": ""}]
                for t in (tab.get('vodtags') or []):
                    if isinstance(t, dict) and t.get('name'):
                        vals.append({"n": t.get('name'), "v": t.get('name')})
                if len(vals) > 1:
                    filters[tid] = [{"key": "class", "name": "标签", "value": vals}]
            return {"class": classes, "filters": filters if filter else {}}
        except Exception as e:
            print('[HOME]', e)
            return {"class": [], "filters": {}}

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg=1, filter=False, extend=None):
        if not extend:
            extend = {}
        if not tid:
            return {"list": [], "page": str(pg)}
        try:
            self._ensure_token()
            num = (int(pg) - 1) * 30
        except (TypeError, ValueError):
            num = 0
        payload = {
            "num": str(num),
            "pid": str(tid),
            "area": "全部",
            "vodclass": extend.get("class", "") or "",
            "vodyear": "全部",
            "sort": "1",
            "token": self.token
        }
        try:
            r = self._request_api('/api/vlist.php', 'post', data=payload)
            if not r:
                raise Exception('no response')
            try:
                data = r.json()
            except Exception as e:
                print('[CATEGORY] json error:', e)
                return {"list": []}
            videos = [{
                "vod_id": str(i.get("vod_id")),
                "vod_name": i.get("vod_name") or "",
                "vod_pic": i.get("vod_pic") or "",
                "vod_remarks": i.get("vod_class") or i.get("vod_remarks") or ""
            } for i in (data.get('list') or [])
                if isinstance(i, dict) and i.get('vod_id')]
            return {"list": videos, "page": str(pg)}
        except Exception as e:
            print('[CATEGORY]', e)
        return {"list": [], "page": str(pg)}

    def detailContent(self, ids):
        try:
            if not ids:
                return {"list": []}
            vid = str(ids[0] if isinstance(ids, (list, tuple)) else ids)
            if not vid:
                return {"list": []}
            self._ensure_token()
        except Exception as e:
            print('[DETAIL]', e)
            return {"list": []}
        try:
            r = self._request_api('/api/Get_vod_list.php', 'post',
                data={"id": vid, "token": self.token, "channel": ""})
            if not r:
                raise Exception('no response')
            try:
                data = r.json().get('data') or {}
            except Exception as e:
                print('[DETAIL] json error:', e)
                return {"list": []}
            if not isinstance(data, dict) or not data.get('vod_id'):
                return {"list": []}

            def s(v):
                return v if isinstance(v, str) else ('' if v is None else str(v))

            play = data.get('vod_play_url') or ('预览$' + (data.get('preview_url') or ''))
            remarks = s(data.get('vod_remarks')) or s(data.get('vod_class')) or ''
            if not remarks:
                ts = data.get('vod_time_add')
                if ts:
                    try:
                        remarks = time.strftime('%Y-%m-%d', time.localtime(int(ts)))
                    except (TypeError, ValueError):
                        pass
            return {"list": [{
                "vod_id": str(data.get('vod_id', vid)),
                "vod_name": s(data.get('vod_name')),
                "vod_pic": s(data.get('vod_pic')),
                "vod_remarks": remarks,
                "vod_content": s(data.get('vod_blurb')) or "暂无简介",
                "vod_play_from": "萝莉岛",
                "vod_play_url": play
            }]}
        except Exception as e:
            print('[DETAIL]', e)
        return {"list": []}

    def playerContent(self, flag, id, vipFlags=None):
        return {"parse": 0, "url": id, "header": json.dumps({"User-Agent": U})}

    def searchContent(self, key, quick=False, pg=1):
        return {"list": []}

    def localProxy(self, param):
        return [404, "application/json", "", "", False]
