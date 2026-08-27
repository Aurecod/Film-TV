import sys
sys.dont_write_bytecode = True

import os
import hashlib
import inspect
import importlib.util
import json
import threading
import time
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from collections import OrderedDict
from urllib.parse import urlparse, parse_qs, quote
import requests
from base.spider import Spider


class Spider(Spider):
    PATH_1 = "/storage/emulated/0/Film-TV/File/py/Abalone"
    PATH_2 = "F:\\模拟共享\\Film-TV\\File\\py\\Abalone"

    CACHE_DIR_NAME = ".spider_cache"
    MAX_CACHE_SIZE = 30
    FAST_PLACEHOLDER = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
    ID_SEP = "|||"

    def __init__(self):
        super().__init__()
        self.scan_paths = []
        self.cache_dir = None
        self.class_cache = {}
        self.spider_cache = OrderedDict()
        self.spider_base_url = {}
        self.global_lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=10)
        self.session = requests.Session()
        self.SELF_NAME = None
        self.extend_config = {}
        self._initialized = False
        self.list_timeout = 2.0
        self.detail_timeout = 5.0
        self.play_timeout = 12.0
        self.class_timeout = 2.0
        self.proxy_timeout = 5.0
        self.retry_times = 1

    def init(self, extend):
        cfg = {}
        if isinstance(extend, str):
            try:
                cfg = json.loads(extend)
            except:
                cfg = {}
        elif isinstance(extend, dict):
            cfg = extend
        cfg.setdefault('hls_proxy', False)
        self.extend_config = cfg
        self.list_timeout = cfg.get('list_timeout', 2.0)
        self.detail_timeout = cfg.get('detail_timeout', 5.0)
        self.play_timeout = cfg.get('play_timeout', 12.0)
        self.class_timeout = cfg.get('class_timeout', 2.0)
        self.proxy_timeout = cfg.get('proxy_timeout', 5.0)
        self.retry_times = cfg.get('retry_times', 1)

        self.scan_paths = []
        if os.path.exists(self.PATH_1):
            self.scan_paths.append(self.PATH_1)
        if os.path.exists(self.PATH_2) and self.PATH_2 not in self.scan_paths:
            self.scan_paths.append(self.PATH_2)
        if not self.scan_paths:
            self.scan_paths.append(os.path.dirname(os.path.abspath(__file__)))

        main_path = self.scan_paths[0] if self.scan_paths else "."
        self.cache_dir = os.path.join(main_path, self.CACHE_DIR_NAME)
        try:
            if not os.path.exists(self.cache_dir):
                os.makedirs(self.cache_dir)
            self.SELF_NAME = os.path.basename(inspect.getfile(inspect.currentframe()))
        except:
            pass

        if not self._initialized:
            self._clean_orphan_cache()
            self._initialized = True

    def getName(self):
        return "智能聚合"

    def _get_placeholder(self, seed=None):
        return self.FAST_PLACEHOLDER

    def _fix_url(self, url, spider=None, py_path=None):
        if not url or not isinstance(url, str):
            return ""
        url = url.strip()
        if url.startswith('data:'):
            return url
        lower = url.lower()
        if any(k in lower for k in ('loading', 'placeholder', 'blank')):
            return self.FAST_PLACEHOLDER

        base = None
        if spider:
            for attr in ('site_url', 'base_url', 'host', 'domain', 'root_url', 'api', 'home'):
                val = getattr(spider, attr, None)
                if val and isinstance(val, str) and val.startswith(('http://', 'https://')):
                    base = val.rstrip('/')
                    break
        if not base and py_path and py_path in self.spider_base_url:
            base = self.spider_base_url[py_path]
        if not base:
            return url

        if url.startswith(('http://', 'https://')):
            return url
        if url.startswith('//'):
            parsed = urlparse(base)
            return f"{parsed.scheme}:{url}"
        if url.startswith('/'):
            return f"{base}{url}"
        return f"{base}/{url}"

    def _looks_like_media_url(self, s):
        s = (s or '').strip()
        if not s:
            return False
        low = s.lower()
        return (s.startswith(('http://', 'https://', '//', '/'))
                or low.endswith(('.m3u8', '.mp4', '.flv', '.ts', '.mp3'))
                or '.m3u8?' in low or '.mp4?' in low)

    def _fix_play_id(self, pid, spider=None, py_path=None):
        """只对真实 URL/路径做绝对化补全；纯集数 id（如 12345|1）原样保留，
        避免被拼上子爬虫的 host 导致 playerContent 拿到污染 id。"""
        if self._looks_like_media_url(pid):
            return self._fix_url(pid, spider, py_path)
        return (pid or '').strip()

    def _normalize_vod(self, v, py_path, spider=None):
        vid = v.get('vod_id') or v.get('id')
        if vid:
            v['vod_id'] = f"{py_path}{self.ID_SEP}{vid}"
        else:
            v['vod_id'] = f"{py_path}{self.ID_SEP}{v.get('title', 'unknown')}"

        if not v.get('vod_name'):
            v['vod_name'] = (
                v.get('title') or v.get('name')
                or v.get('vod_title') or v.get('vod_sub_title')
                or "未命名"
            )

        if not v.get('vod_remarks'):
            v['vod_remarks'] = v.get('remark') or v.get('vod_remark') or ""

        pic = v.get('vod_pic')
        if not pic:
            pic = v.get('pic')
        if pic:
            pic = self._fix_url(pic, spider, py_path)
            if isinstance(pic, str) and '127.0.0.1:9978/proxy' in pic:
                try:
                    parsed = urlparse(pic)
                    qs = parse_qs(parsed.query)
                    real_url = qs.get('url', [''])[0]
                    if real_url:
                        py_name = os.path.basename(py_path)
                        pic = (
                            f"http://127.0.0.1:9978/proxy?do=py&action=pic"
                            f"&py={quote(py_name, safe='')}&url={quote(real_url, safe='')}"
                        )
                except Exception:
                    pass
            v['vod_pic'] = pic
        else:
            v['vod_pic'] = self.FAST_PLACEHOLDER
        return v

    def _call_with_timeout(self, func, timeout, retry, *args, **kwargs):
        attempts = retry + 1
        for _ in range(attempts):
            future = self._executor.submit(func, *args, **kwargs)
            try:
                return future.result(timeout=timeout)
            except TimeoutError:
                future.cancel()
                continue
            except Exception:
                future.cancel()
                continue
        return None

    def _safe_call(self, spider, method_name, timeout, retry, *args):
        if not hasattr(spider, method_name):
            return None
        func = getattr(spider, method_name)
        try:
            sig = inspect.signature(func)
            params = [p for p in sig.parameters.values() if p.name != 'self']
            has_varargs = any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in params)
            if not has_varargs:
                max_args = len(params)
                if len(args) > max_args:
                    args = args[:max_args]
        except Exception:
            pass

        if method_name == 'detailContent' and args and isinstance(args[0], list) and len(args[0]) == 1:
            res = self._call_with_timeout(func, timeout, retry, *args)
            if res is not None:
                return res
            return self._call_with_timeout(func, timeout, retry, args[0][0])

        return self._call_with_timeout(func, timeout, retry, *args)

    def _load_spider_instance(self, py_path):
        with self.global_lock:
            if py_path in self.spider_cache:
                inst, mtime = self.spider_cache[py_path]
                try:
                    current_mtime = os.path.getmtime(py_path)
                except Exception:
                    return None, "无法获取文件修改时间"
                if mtime == current_mtime:
                    self.spider_cache.move_to_end(py_path)
                    return inst, "OK"
                else:
                    del self.spider_cache[py_path]
                    if py_path in self.spider_base_url:
                        del self.spider_base_url[py_path]

        mod_name = f"m{hashlib.md5(py_path.encode()).hexdigest()[:8]}"
        self._purge_module_cache(mod_name)

        try:
            spec = importlib.util.spec_from_file_location(mod_name, py_path)
            if spec is None or spec.loader is None:
                return None, "无法创建模块 spec"
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            spec.loader.exec_module(mod)

            candidates = []
            for name in dir(mod):
                obj = getattr(mod, name)
                if (isinstance(obj, type) and
                    hasattr(obj, 'homeContent') and
                    obj.__module__ == mod_name):
                    candidates.append(obj)

            if not candidates:
                return None, "无爬虫类"

            cls = candidates[0] if len(candidates) == 1 else next(
                (c for c in candidates if c.__name__ != 'Spider'), candidates[0]
            )

            instance = cls()
            if hasattr(instance, 'init'):
                sig = inspect.signature(instance.init)
                params = [p for p in sig.parameters.values() if p.name != 'self']
                param_count = len(params)
                if param_count == 0:
                    instance.init()
                else:
                    try:
                        instance.init(json.dumps(self.extend_config))
                    except Exception:
                        try:
                            instance.init(self.extend_config)
                        except Exception:
                            instance.init()

            base = None
            for attr in ['base_url', 'host', 'domain', 'site_url', 'root_url', 'api', 'home']:
                val = getattr(instance, attr, None)
                if val and isinstance(val, str) and val.startswith(('http://', 'https://')):
                    base = val.rstrip('/')
                    break
            if base:
                parsed = urlparse(base)
                if parsed.path and parsed.path != '/':
                    path_len = len(parsed.path)
                    if path_len > 3 and not parsed.path.startswith(('/images', '/img', '/pics', '/static')):
                        base = f"{parsed.scheme}://{parsed.netloc}"
                self.spider_base_url[py_path] = base

            with self.global_lock:
                try:
                    file_mtime = os.path.getmtime(py_path)
                except Exception:
                    file_mtime = 0
                self.spider_cache[py_path] = (instance, file_mtime)
                self.spider_cache.move_to_end(py_path)
                if len(self.spider_cache) > self.MAX_CACHE_SIZE:
                    oldest = next(iter(self.spider_cache))
                    del self.spider_cache[oldest]
                    if oldest in self.spider_base_url:
                        del self.spider_base_url[oldest]

            return instance, "OK"

        except Exception as e:
            return None, f"加载失败: {str(e)}"

    def _purge_module_cache(self, mod_name):
        to_remove = [mod_name]
        prefix = mod_name + "."
        for name in list(sys.modules.keys()):
            if name == mod_name or name.startswith(prefix):
                to_remove.append(name)
        for name in to_remove:
            try:
                del sys.modules[name]
            except Exception:
                pass

    def _clean_orphan_cache(self):
        with self.global_lock:
            if not self.cache_dir or not os.path.exists(self.cache_dir):
                return
            valid_hashes = set()
            for p in self.scan_paths:
                if not os.path.exists(p):
                    continue
                try:
                    for f in os.listdir(p):
                        if f.endswith(".py") and not f.startswith("__"):
                            full_path = os.path.join(p, f)
                            valid_hashes.add(hashlib.md5(full_path.encode()).hexdigest() + ".json")
                except Exception:
                    pass
            for f in os.listdir(self.cache_dir):
                if f.endswith(".json") and f not in valid_hashes:
                    try:
                        os.remove(os.path.join(self.cache_dir, f))
                    except Exception:
                        pass

    def _get_classes(self, py_path):
        with self.global_lock:
            if py_path in self.class_cache:
                mtime, classes = self.class_cache[py_path]
                try:
                    if mtime == os.path.getmtime(py_path):
                        return classes
                except Exception:
                    pass

            cache_file = os.path.join(self.cache_dir, hashlib.md5(py_path.encode()).hexdigest() + ".json")
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if data.get('mtime') == os.path.getmtime(py_path):
                        self.class_cache[py_path] = (data['mtime'], data['classes'])
                        return data['classes']
                except Exception:
                    pass

        spider, status = self._load_spider_instance(py_path)
        if spider is None:
            default = [{'type_id': 'auto', 'type_name': '默认'}]
            with self.global_lock:
                try:
                    self.class_cache[py_path] = (os.path.getmtime(py_path), default)
                except Exception:
                    self.class_cache[py_path] = (0, default)
            return default

        res = self._safe_call(spider, 'homeContent', self.class_timeout, 1, {})
        if res and 'class' in res:
            classes = res['class']
        else:
            classes = [{'type_id': 'auto', 'type_name': '默认'}]

        with self.global_lock:
            try:
                file_mtime = os.path.getmtime(py_path)
            except Exception:
                file_mtime = 0
            self.class_cache[py_path] = (file_mtime, classes)
            try:
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump({'mtime': file_mtime, 'classes': classes}, f)
            except Exception:
                pass
        return classes

    def homeContent(self, filter):
        classes = []
        filters = {}
        for path in self.scan_paths:
            if not os.path.exists(path):
                continue
            try:
                files = [f for f in os.listdir(path) if f.endswith(".py") and not f.startswith("__") and f != self.SELF_NAME]
            except Exception:
                continue
            for f in files:
                full_path = os.path.join(path, f)
                display_name = f.replace(".py", "")
                classes.append({"type_id": full_path, "type_name": display_name})
                sub_classes = self._get_classes(full_path)
                filters[full_path] = [{
                    "key": "sub",
                    "name": "分类",
                    "value": [{"n": item['type_name'], "v": item['type_id']} for item in sub_classes]
                }]
        return {"class": classes, "filters": filters}

    def categoryContent(self, tid, pg, filter, extend):
        spider, status = self._load_spider_instance(tid)
        if spider is None:
            return {"list": []}

        if not extend or 'sub' not in extend:
            sub_classes = self._get_classes(tid)
            sub_tid = sub_classes[0]['type_id'] if sub_classes else 'auto'
        else:
            sub_tid = extend['sub']

        ext_copy = deepcopy(extend) if extend else {}
        res = self._safe_call(spider, 'categoryContent', self.list_timeout, self.retry_times,
                              sub_tid, pg, filter, ext_copy)
        if res is None or 'list' not in res:
            return {"list": []}

        for v in res['list']:
            self._normalize_vod(v, tid, spider)
        return res

    def detailContent(self, array):
        if not array or self.ID_SEP not in array[0]:
            return {"list": []}

        py_path, real_id = array[0].split(self.ID_SEP, 1)
        spider, status = self._load_spider_instance(py_path)
        if spider is None:
            return {"list": []}

        res = self._safe_call(spider, 'detailContent', self.detail_timeout, self.retry_times, [real_id])
        if res is None or 'list' not in res:
            return {"list": []}

        vod = res['list'][0]
        self._normalize_vod(vod, py_path, spider)

        if vod.get('vod_play_url'):
            lines = vod['vod_play_url'].split('$$$')
            processed_lines = []
            for line in lines:
                play_parts = []
                for part in line.split('#'):
                    if '$' in part:
                        title, pid = part.split('$', 1)
                        pid_fixed = self._fix_play_id(pid, spider, py_path)
                        if not pid_fixed.startswith(f"{py_path}{self.ID_SEP}"):
                            play_parts.append(f"{title}${py_path}{self.ID_SEP}{pid_fixed}")
                        else:
                            play_parts.append(f"{title}${pid_fixed}")
                    else:
                        part_fixed = self._fix_play_id(part, spider, py_path)
                        if not part_fixed.startswith(f"{py_path}{self.ID_SEP}"):
                            play_parts.append(f"{py_path}{self.ID_SEP}{part_fixed}")
                        else:
                            play_parts.append(part_fixed)
                processed_lines.append('#'.join(play_parts))
            vod['vod_play_url'] = '$$$'.join(processed_lines)

        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        if self.ID_SEP not in id:
            return {"parse": 0, "url": "error"}

        py_path, real_id = id.split(self.ID_SEP, 1)
        spider, status = self._load_spider_instance(py_path)
        if spider is None:
            return {"parse": 0, "url": "error"}

        if not hasattr(spider, 'playerContent'):
            return {"parse": 0, "url": "error"}

        try:
            sig = inspect.signature(spider.playerContent)
            params = [p for p in sig.parameters.values() if p.name != 'self']
            param_count = len(params)
        except Exception:
            param_count = 3

        try:
            if param_count >= 3:
                res = self._call_with_timeout(
                    spider.playerContent, self.play_timeout, self.retry_times,
                    flag, real_id, vipFlags
                )
            elif param_count >= 2:
                res = self._call_with_timeout(
                    spider.playerContent, self.play_timeout, self.retry_times,
                    flag, real_id
                )
            else:
                return {"parse": 0, "url": "error"}
        except Exception:
            return {"parse": 0, "url": "error"}

        if res is None:
            return {"parse": 0, "url": ""}
        return res

    def _safe_search(self, py_path, key, quick, pg):
        spider, status = self._load_spider_instance(py_path)
        if spider is None or not hasattr(spider, 'searchContent'):
            return []
        res = self._safe_call(spider, 'searchContent', self.list_timeout, self.retry_times,
                              key, quick, pg)
        if res and 'list' in res:
            return [self._normalize_vod(v, py_path, spider) for v in res['list']]
        return []

    def searchContent(self, key, quick, pg="1"):
        if not key:
            return {"list": []}

        all_files = []
        for path in self.scan_paths:
            if not os.path.exists(path):
                continue
            try:
                for f in os.listdir(path):
                    if f.endswith(".py") and not f.startswith("__") and f != self.SELF_NAME:
                        all_files.append(os.path.join(path, f))
            except Exception:
                continue

        if not all_files:
            return {"list": []}

        futures = {}
        for py_path in all_files:
            future = self._executor.submit(self._safe_search, py_path, key, quick, pg)
            futures[future] = py_path

        results = []
        total_timeout = self.list_timeout * (self.retry_times + 1) + 1
        deadline = time.time() + total_timeout

        for future in as_completed(futures):
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            try:
                data = future.result(timeout=min(self.list_timeout, remaining))
                if data:
                    results.extend(data)
            except Exception:
                continue

        for future in futures:
            if not future.done():
                future.cancel()

        seen = set()
        unique = []
        for v in results:
            vid = v.get('vod_id')
            if vid and vid not in seen:
                seen.add(vid)
                unique.append(v)
        return {"list": unique[:100]}

    def localProxy(self, params):
        if params.get('do') != 'py':
            return None

        action = params.get('action', '')
        py_name = params.get('py', '')

        if action == 'pic' and py_name:
            target_path = None
            for path in list(self.spider_cache.keys()):
                if os.path.basename(path) == py_name:
                    target_path = path
                    break
            if target_path is None:
                for path in self.scan_paths:
                    if not os.path.exists(path):
                        continue
                    candidate = os.path.join(path, py_name)
                    if os.path.exists(candidate):
                        target_path = candidate
                        break

            if target_path:
                spider, status = self._load_spider_instance(target_path)
                if spider and hasattr(spider, 'localProxy'):
                    try:
                        result = self._call_with_timeout(
                            spider.localProxy, self.proxy_timeout, 0, params
                        )
                        if result is not None:
                            return result
                    except Exception:
                        pass

        with self.global_lock:
            items = list(self.spider_cache.items())

        if not items:
            return None

        futures = {}
        for py_path, (spider, _) in items:
            if spider and hasattr(spider, 'localProxy'):
                future = self._executor.submit(spider.localProxy, params)
                futures[future] = py_path

        if not futures:
            return None

        deadline = time.time() + self.proxy_timeout
        for future in as_completed(futures):
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            try:
                result = future.result(timeout=max(0.1, remaining))
                if result is not None:
                    for f in futures:
                        if not f.done():
                            f.cancel()
                    return result
            except Exception:
                continue

        for future in futures:
            if not future.done():
                future.cancel()
        return None

    def destroy(self):
        try:
            self.session.close()
            for py_path, (inst, _) in list(self.spider_cache.items()):
                if hasattr(inst, 'destroy'):
                    try:
                        inst.destroy()
                    except Exception:
                        pass
            self.spider_cache.clear()
            self.class_cache.clear()
            self.spider_base_url.clear()
            self._executor.shutdown(wait=False)
        except Exception:
            pass
