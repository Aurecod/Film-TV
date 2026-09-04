import sys

sys.dont_write_bytecode = True

import hashlib
import importlib.util
import inspect
import json
import os
import queue
import threading
import time
from collections import OrderedDict
from copy import deepcopy
from urllib.parse import urlparse, parse_qs, urlencode

try:
    import requests
except Exception:
    requests = None

from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    PATH_1 = "/storage/emulated/0/Film-TV/File/py/Abalone"
    PATH_2 = "F:\\模拟共享\\Film-TV\\File\\py\\Abalone"
    CACHE_DIR_NAME = ".spider_cache"
    INDEX_NAME = "classes_index.json"
    LOG_NAME = "agg_debug.log"
    FAST_PLACEHOLDER = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
    ID_SEP = "|||"
    PROXY_TAG = "agg_py"

    MAX_CACHE_SIZE = 60

    def __init__(self):
        super().__init__()
        self.scan_paths = []
        self.cache_dir = None
        self.SELF_NAME = None
        self.extend_config = {}

        self.global_lock = threading.RLock()
        self.spider_cache = OrderedDict()      
        self.spider_base_url = {}
        self._load_locks = {}
        self._health = {}
        self._class_index = None
        self._index_dirty = False
        self._index_lock = threading.RLock()
        self._index_saved = 0.0
        self._files_cache = None
        self._files_ts = 0.0
        self._warming = set()
        self._warm_lock = threading.RLock()
        self._log_lock = threading.Lock()
        self._probe_fail = {}
        self.session = requests.Session() if requests else None
        self._initialized = False
        self.load_timeout = 8.0
        self.class_timeout = 8.0
        self.list_timeout = 8.0
        self.detail_timeout = 12.0
        self.play_timeout = 20.0
        self.proxy_timeout = 8.0
        self.sniff_timeout = 2.0
        self.home_budget = 4.0
        self.home_workers = 16
        self.search_budget = 12.0
        self.search_workers = 16
        self.search_limit = 200
        self.warm_budget = 180.0
        self.warm_workers = 8
        self.warm_item = 25.0    
        self.index_flush_gap = 3.0   
        self.fail_threshold = 2
        self.cool_down = 180.0
        self.probe_retry = 2
        self.evict_grace = 5.0
        self.retry_times = 0
        self.max_inflight = 160
        self.reserve_inflight = 32
        self.debug = False
        self._inflight = 0
        self._slot_lock = threading.Lock()

    def init(self, extend=None):
        cfg = {}
        if isinstance(extend, str) and extend.strip():
            try:
                cfg = json.loads(extend)
            except Exception:
                cfg = {}
        elif isinstance(extend, dict):
            cfg = extend
        if not isinstance(cfg, dict):
            cfg = {}
        cfg.setdefault('hls_proxy', False)
        self.extend_config = cfg

        def num(key, default):
            try:
                return float(cfg.get(key, default))
            except Exception:
                return default

        def integer(key, default):
            try:
                return max(1, int(cfg.get(key, default)))
            except Exception:
                return default

        self.load_timeout = num('load_timeout', self.load_timeout)
        self.class_timeout = num('class_timeout', self.class_timeout)
        self.list_timeout = num('list_timeout', self.list_timeout)
        self.detail_timeout = num('detail_timeout', self.detail_timeout)
        self.play_timeout = num('play_timeout', self.play_timeout)
        self.proxy_timeout = num('proxy_timeout', self.proxy_timeout)
        self.sniff_timeout = num('sniff_timeout', self.sniff_timeout)
        self.home_budget = num('home_budget', self.home_budget)
        self.search_budget = num('search_budget', self.search_budget)
        self.warm_budget = num('warm_budget', self.warm_budget)
        self.warm_item = num('warm_item', self.warm_item)
        self.index_flush_gap = num('index_flush_gap', self.index_flush_gap)
        self.cool_down = num('cool_down', self.cool_down)
        self.evict_grace = num('evict_grace', self.evict_grace)
        self.home_workers = integer('home_workers', self.home_workers)
        self.warm_workers = integer('warm_workers', self.warm_workers)
        self.search_workers = integer('search_workers', self.search_workers)
        self.search_limit = integer('search_limit', self.search_limit)
        self.fail_threshold = integer('fail_threshold', self.fail_threshold)
        self.probe_retry = integer('probe_retry', self.probe_retry)
        self.max_inflight = integer('max_inflight', self.max_inflight)
        self.reserve_inflight = integer('reserve_inflight', self.reserve_inflight)
        try:
            self.retry_times = max(0, int(cfg.get('retry_times', self.retry_times)))
        except Exception:
            self.retry_times = 0
        self.debug = bool(cfg.get('debug', False))
        self.scan_paths = []
        for p in (self.PATH_1, self.PATH_2):
            if p and os.path.isdir(p) and p not in self.scan_paths:
                self.scan_paths.append(p)
        if not self.scan_paths:
            try:
                self.scan_paths.append(os.path.dirname(os.path.abspath(__file__)))
            except Exception:
                self.scan_paths.append(".")

        main_path = self.scan_paths[0]
        self.cache_dir = os.path.join(main_path, self.CACHE_DIR_NAME)
        try:
            if not os.path.isdir(self.cache_dir):
                os.makedirs(self.cache_dir)
        except Exception:
            pass
        try:
            self.SELF_NAME = os.path.basename(inspect.getfile(inspect.currentframe()))
        except Exception:
            self.SELF_NAME = None

        if not self._initialized:
            self._initialized = True
            self._spawn(self._clean_orphan_cache)
            self._spawn(self._warm_all)
        self._log('INIT paths=%s' % self.scan_paths)

    def _warm_all(self):
        try:
            todo = [p for p in self._list_files() if self._index_get(p) is None]
            if todo:
                self._warm_async(todo)
        except Exception:
            pass

    def getName(self):
        return "智能聚合"

    def destroy(self):
        try:
            self._index_save(force=True)
        except Exception:
            pass
        with self.global_lock:
            items = [v[0] for v in self.spider_cache.values()]
            self.spider_cache.clear()
            self.spider_base_url.clear()
        for inst in items:
            self._spawn(self._safe_destroy, inst)
        if self.session:
            try:
                self.session.close()
            except Exception:
                pass

    def _safe_destroy(self, inst):
        try:
            if hasattr(inst, 'destroy'):
                inst.destroy()
        except Exception:
            pass

    def _log(self, msg):
        if not self.debug or not self.cache_dir:
            return
        try:
            line = "%s %s\n" % (time.strftime('%H:%M:%S'), msg)
            with self._log_lock:
                with open(os.path.join(self.cache_dir, self.LOG_NAME), 'a', encoding='utf-8') as f:
                    f.write(line)
        except Exception:
            pass

    def _spawn(self, fn, *args):
        try:
            t = threading.Thread(target=fn, args=args, daemon=True)
            t.start()
            return t
        except Exception:
            return None

    def _guard(self, fn, timeout, *args, **kwargs):
        priority = bool(kwargs.pop('priority', False))
        try:
            timeout = float(timeout)
        except Exception:
            timeout = 1.0
        if timeout <= 0:
            timeout = 0.2

        if not self._take_slot(priority):
            self._log('BUSY inflight=%d priority=%s' % (self._inflight, priority))
            return None, 'busy'

        box = {}
        done = threading.Event()

        def run():
            try:
                box['v'] = fn(*args, **kwargs)
            except BaseException as e:
                box['e'] = e
            finally:
                done.set()
                self._free_slot()

        try:
            t = threading.Thread(target=run, daemon=True)
            t.start()
        except Exception:
            self._free_slot()
            return None, 'thread'

        if not done.wait(timeout):
            return None, 'timeout'
        if 'e' in box:
            return None, 'error'
        return box.get('v'), 'ok'

    def _take_slot(self, priority):
        cap = self.max_inflight + self.reserve_inflight if priority else self.max_inflight
        with self._slot_lock:
            if self._inflight >= cap:
                return False
            self._inflight += 1
            return True

    def _free_slot(self):
        with self._slot_lock:
            if self._inflight > 0:
                self._inflight -= 1

    def _call(self, py_path, fn, timeout, retry, *args, **kwargs):
        attempts = max(0, int(retry)) + 1
        status = 'error'
        for i in range(attempts):
            value, status = self._guard(fn, timeout, *args, **kwargs)
            if status == 'ok':
                self._mark(py_path, True)
                return value, status
            if status != 'error':
                break
        self._mark(py_path, False)
        self._log('CALL_FAIL %s %s' % (os.path.basename(py_path or '?'), status))
        return None, status

    def _cooling(self, py_path):
        with self.global_lock:
            h = self._health.get(py_path)
            return bool(h and h.get('until', 0) > time.time())

    def _mark(self, py_path, ok):
        if not py_path:
            return
        with self.global_lock:
            h = self._health.setdefault(py_path, {'fail': 0, 'until': 0})
            if ok:
                h['fail'] = 0
                h['until'] = 0
            else:
                h['fail'] += 1
                if h['fail'] >= self.fail_threshold:
                    h['fail'] = 0
                    h['until'] = time.time() + self.cool_down
                    self._log('COOLDOWN %s %.0fs' % (os.path.basename(py_path), self.cool_down))

    def _fan_out(self, items, fn, workers, budget, attempted=None, per_item=None):
        if not items:
            return []
        q = queue.Queue()
        for it in items:
            q.put(it)
        out = []
        lock = threading.Lock()
        deadline = time.time() + max(1.0, budget)

        def worker():
            while True:
                remaining = deadline - time.time()
                if remaining <= 0.2:
                    return
                try:
                    it = q.get_nowait()
                except queue.Empty:
                    return
                if attempted is not None:
                    with lock:
                        attempted.add(it)
                slice_ = remaining if per_item is None else min(remaining, per_item)
                try:
                    r = fn(it, slice_)
                except Exception:
                    r = None
                if r is not None:
                    with lock:
                        out.append((it, r))

        threads = []
        for _ in range(min(max(1, workers), len(items))):
            t = self._spawn(worker)
            if t:
                threads.append(t)
        for t in threads:
            t.join(max(0.0, deadline - time.time()))
        with lock:
            return list(out)

    def _list_files(self):
        now = time.time()
        with self.global_lock:
            if self._files_cache is not None and now - self._files_ts < 3.0:
                return list(self._files_cache)

        seen = set()
        files = []
        for path in self.scan_paths:
            try:
                names = sorted(os.listdir(path))
            except Exception:
                continue
            for f in names:
                if not f.endswith('.py') or f.startswith('__'):
                    continue
                if self.SELF_NAME and f == self.SELF_NAME:
                    continue
                if f in seen:
                    continue
                full = os.path.join(path, f)
                if not os.path.isfile(full):
                    continue
                seen.add(f)
                files.append(full)

        with self.global_lock:
            self._files_cache = files
            self._files_ts = now
        return list(files)

    def _mtime(self, path):
        try:
            return os.path.getmtime(path)
        except Exception:
            return 0.0

    def _index_path(self):
        return os.path.join(self.cache_dir, self.INDEX_NAME) if self.cache_dir else None

    def _index_load(self):
        with self._index_lock:
            if self._class_index is not None:
                return self._class_index
            data = {}
            p = self._index_path()
            if p and os.path.exists(p):
                try:
                    with open(p, 'r', encoding='utf-8') as f:
                        raw = json.load(f)
                    if isinstance(raw, dict):
                        data = raw
                except Exception:
                    data = {}
            if not data:
                data = self._index_migrate()
            self._class_index = data
            return data

    def _index_migrate(self):
        data = {}
        if not self.cache_dir:
            return data
        for py_path in self._list_files():
            key = hashlib.md5(py_path.encode()).hexdigest()
            old = os.path.join(self.cache_dir, key + '.json')
            if not os.path.exists(old):
                continue
            try:
                with open(old, 'r', encoding='utf-8') as f:
                    d = json.load(f)
                classes = self._sanitize_classes(d.get('classes'))
                if classes and not (len(classes) == 1 and classes[0].get('type_id') == 'auto'):
                    data[key] = {'mtime': d.get('mtime', 0), 'classes': classes}
            except Exception:
                continue
        if data:
            self._index_dirty = True
        return data

    def _index_entry(self, py_path):
        idx = self._index_load()
        key = hashlib.md5(py_path.encode()).hexdigest()
        with self._index_lock:
            item = idx.get(key)
        if not isinstance(item, dict):
            return None
        if abs(float(item.get('mtime', 0)) - self._mtime(py_path)) > 0.001:
            return None
        return item

    def _index_get(self, py_path):
        item = self._index_entry(py_path)
        if not item:
            return None
        classes = item.get('classes')
        return classes if isinstance(classes, list) else None

    def _index_put(self, py_path, classes):
        idx = self._index_load()
        key = hashlib.md5(py_path.encode()).hexdigest()
        with self._index_lock:
            idx[key] = {'mtime': self._mtime(py_path), 'classes': classes,
                        'name': os.path.basename(py_path)}
            self._index_dirty = True
        self._index_flush_soon()

    def _index_put_fail(self, py_path):
        idx = self._index_load()
        key = hashlib.md5(py_path.encode()).hexdigest()
        with self._index_lock:
            item = idx.get(key)
            prev = item.get('fail', 0) if isinstance(item, dict) else 0
            if isinstance(item, dict) and isinstance(item.get('classes'), list):
                return
            idx[key] = {'mtime': self._mtime(py_path), 'fail': int(prev) + 1,
                        'name': os.path.basename(py_path)}
            self._index_dirty = True
        self._index_flush_soon()

    def _index_flush_soon(self):
        now = time.time()
        with self._index_lock:
            if now - self._index_saved < self.index_flush_gap:
                return
            self._index_saved = now
        self._index_save()

    def _index_drop_fail(self, py_path):
        idx = self._index_load()
        key = hashlib.md5(py_path.encode()).hexdigest()
        with self._index_lock:
            item = idx.get(key)
            if isinstance(item, dict) and item.get('fail') and 'classes' not in item:
                del idx[key]
                self._index_dirty = True

    def _index_save(self, force=False):
        p = self._index_path()
        if not p:
            return
        with self._index_lock:
            if not self._index_dirty and not force:
                return
            data = dict(self._class_index or {})
            self._index_dirty = False
        try:
            tmp = p + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, p)
        except Exception:
            pass

    def _clean_orphan_cache(self):
        if not self.cache_dir or not os.path.isdir(self.cache_dir):
            return
        valid = set()
        for py_path in self._list_files():
            valid.add(hashlib.md5(py_path.encode()).hexdigest())
        idx = self._index_load()
        with self._index_lock:
            for key in [k for k in idx.keys() if k not in valid]:
                del idx[key]
                self._index_dirty = True
        try:
            for f in os.listdir(self.cache_dir):
                if not f.endswith('.json') or f == self.INDEX_NAME:
                    continue
                if f[:-5] not in valid:
                    try:
                        os.remove(os.path.join(self.cache_dir, f))
                    except Exception:
                        pass
        except Exception:
            pass
        self._index_save()

    def _load_lock(self, py_path):
        with self.global_lock:
            lk = self._load_locks.get(py_path)
            if lk is None:
                lk = threading.Lock()
                self._load_locks[py_path] = lk
            return lk

    def _cached_instance(self, py_path):
        with self.global_lock:
            item = self.spider_cache.get(py_path)
            if not item:
                return None
            inst, mtime, _ = item
            if abs(mtime - self._mtime(py_path)) > 0.001:
                del self.spider_cache[py_path]
                self.spider_base_url.pop(py_path, None)
                return None
            item[2] = time.time()
            self.spider_cache.move_to_end(py_path)
            return inst

    def _get_spider(self, py_path, timeout=None, allow_cooling=True, priority=False):
        inst = self._cached_instance(py_path)
        if inst is not None:
            if self._over_cap():
                self._trim_cache()
            return inst
        if not allow_cooling and self._cooling(py_path):
            return None

        lk = self._load_lock(py_path)
        if not lk.acquire(timeout=0.05):
            deadline = time.time() + max(0.5, float(timeout or self.load_timeout))
            while time.time() < deadline:
                inst = self._cached_instance(py_path)
                if inst is not None:
                    return inst
                time.sleep(0.05)
            return None
        try:
            inst = self._cached_instance(py_path)
            if inst is not None:
                return inst
            value, status = self._call(py_path, self._do_load,
                                       timeout or self.load_timeout, 0, py_path,
                                       priority=priority)
            if status != 'ok' or value is None:
                self._log('LOAD_FAIL %s %s' % (os.path.basename(py_path), status))
                return None
            return value
        finally:
            try:
                lk.release()
            except Exception:
                pass

    def _do_load(self, py_path):
        mod_name = 'aggm_' + hashlib.md5(py_path.encode()).hexdigest()[:10]
        self._purge_module(mod_name)
        spec = importlib.util.spec_from_file_location(mod_name, py_path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        try:
            spec.loader.exec_module(mod)
        except BaseException:
            self._purge_module(mod_name)
            raise

        cls = self._pick_class(mod, mod_name)
        if cls is None:
            self._purge_module(mod_name)
            return None

        instance = cls()
        self._init_child(instance)

        base = self._detect_base(instance)
        with self.global_lock:
            if base:
                self.spider_base_url[py_path] = base
            self.spider_cache[py_path] = [instance, self._mtime(py_path), time.time()]
            self.spider_cache.move_to_end(py_path)
        self._trim_cache()
        return instance

    def _over_cap(self):
        with self.global_lock:
            return len(self.spider_cache) > self.MAX_CACHE_SIZE

    def _trim_cache(self):
        old, fresh = [], 0
        now = time.time()
        with self.global_lock:
            while len(self.spider_cache) > self.MAX_CACHE_SIZE:
                key, victim = next(iter(self.spider_cache.items()))
                del self.spider_cache[key]
                self.spider_base_url.pop(key, None)
                if now - victim[2] > self.evict_grace:
                    old.append(victim[0])
                else:
                    fresh += 1
        for v in old:
            self._spawn(self._safe_destroy, v)
        return len(old) + fresh

    def _pick_class(self, mod, mod_name):
        candidates = []
        for name in dir(mod):
            try:
                obj = getattr(mod, name)
            except Exception:
                continue
            if not isinstance(obj, type):
                continue
            if getattr(obj, '__module__', None) != mod_name:
                continue
            if not hasattr(obj, 'homeContent'):
                continue
            candidates.append(obj)
        if not candidates:
            return None
        for c in candidates:
            if c.__name__ == 'Spider':
                return c
        return candidates[0]

    def _init_child(self, instance):
        if not hasattr(instance, 'init'):
            return
        try:
            sig = inspect.signature(instance.init)
            params = [p for p in sig.parameters.values() if p.name != 'self']
            required = [p for p in params
                        if p.default is inspect.Parameter.empty
                        and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
        except Exception:
            params, required = [None], []

        payload = json.dumps(self.extend_config, ensure_ascii=False)
        trials = []
        if params:
            trials.append((payload,))
            trials.append((self.extend_config,))
        if not required:
            trials.append(tuple())
        for args in trials:
            try:
                instance.init(*args)
                return
            except TypeError:
                continue
            except Exception:
                return

    def _detect_base(self, instance):
        for attr in ('siteUrl', 'site_url', 'host', 'HOST', 'base_url', 'baseUrl',
                     'domain', 'root_url', 'home', 'api'):
            try:
                val = getattr(instance, attr, None)
            except Exception:
                continue
            if isinstance(val, str) and val.startswith(('http://', 'https://')):
                base = val.rstrip('/')
                parsed = urlparse(base)
                if parsed.path and parsed.path != '/':
                    if len(parsed.path) > 3 and not parsed.path.startswith(
                            ('/images', '/img', '/pics', '/static', '/api')):
                        base = '%s://%s' % (parsed.scheme, parsed.netloc)
                return base
        return None

    def _purge_module(self, mod_name):
        prefix = mod_name + '.'
        for name in list(sys.modules.keys()):
            if name == mod_name or name.startswith(prefix):
                try:
                    del sys.modules[name]
                except Exception:
                    pass

    def _method(self, spider, name):
        if spider is None:
            return None
        fn = getattr(spider, name, None)
        return fn if callable(fn) else None

    def _trim_args(self, fn, args):
        try:
            sig = inspect.signature(fn)
            params = [p for p in sig.parameters.values() if p.name != 'self']
            if any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in params):
                return args
            positional = [p for p in params
                          if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
            return args[:len(positional)]
        except Exception:
            return args

    def _fix_url(self, url, spider=None, py_path=None):
        if not url or not isinstance(url, str):
            return ''
        url = url.strip()
        if not url or url.startswith(('data:', 'magnet:')):
            return url
        low = url.lower()
        if low.startswith(('http://', 'https://')):
            return url
        if any(k in low for k in ('loading', 'placeholder', 'blank.')):
            return self.FAST_PLACEHOLDER

        base = None
        if spider is not None:
            base = self._detect_base(spider)
        if not base and py_path:
            with self.global_lock:
                base = self.spider_base_url.get(py_path)
        if not base:
            return url
        if url.startswith('//'):
            return '%s:%s' % (urlparse(base).scheme, url)
        if url.startswith('/'):
            return base + url
        return '%s/%s' % (base, url)

    def _wrap_proxy(self, url, py_path):
        if not isinstance(url, str) or 'do=py' not in url:
            return url
        try:
            parsed = urlparse(url)
            qs = parse_qs(parsed.query, keep_blank_values=True)
            if qs.get(self.PROXY_TAG):
                return url
            flat = [(k, v[0]) for k, v in qs.items()]
            flat.append((self.PROXY_TAG, os.path.basename(py_path)))
            netloc = parsed.netloc or '127.0.0.1:9978'
            return '%s://%s%s?%s' % (parsed.scheme or 'http', netloc,
                                     parsed.path or '/proxy', urlencode(flat))
        except Exception:
            return url

    def _wrap_pic(self, pic, py_path):
        return self._wrap_proxy(pic, py_path)

    def _normalize_vod(self, v, py_path, spider=None):
        if not isinstance(v, dict):
            return None
        vid = v.get('vod_id') or v.get('id') or v.get('vod_name') or v.get('title')
        vid = str(vid) if vid is not None else ''
        if not vid:
            return None
        if not vid.startswith(py_path + self.ID_SEP):
            v['vod_id'] = '%s%s%s' % (py_path, self.ID_SEP, vid)

        if not v.get('vod_name'):
            v['vod_name'] = (v.get('title') or v.get('name') or v.get('vod_title')
                             or v.get('vod_sub_title') or '未命名')
        if not v.get('vod_remarks'):
            v['vod_remarks'] = v.get('remark') or v.get('vod_remark') or ''

        pic = v.get('vod_pic') or v.get('pic') or ''
        if pic:
            pic = self._wrap_proxy(self._fix_url(pic, spider, py_path), py_path)
            v['vod_pic'] = pic
        else:
            v['vod_pic'] = self.FAST_PLACEHOLDER
        return v

    def _normalize_list(self, res, py_path, spider):
        if not isinstance(res, dict):
            return None
        items = res.get('list')
        if not isinstance(items, list):
            return None
        out = []
        for v in items:
            nv = self._normalize_vod(v, py_path, spider)
            if nv:
                out.append(nv)
        res['list'] = out
        return res

    @staticmethod
    def _sanitize_classes(classes):
        if not isinstance(classes, list):
            return []
        out = []
        for c in classes:
            if not isinstance(c, dict):
                continue
            tid = c.get('type_id', c.get('type_ id'))
            name = c.get('type_name') or c.get('name')
            if tid is None or not name:
                continue
            out.append({'type_id': str(tid), 'type_name': str(name)})
        return out

    def homeContent(self, filter):
        files = self._list_files()
        if not files:
            return {'class': [], 'list': []}

        classes = []
        filters = {}
        fresh = []
        stale = []

        for py_path in files:
            classes.append({'type_id': py_path,
                            'type_name': os.path.basename(py_path)[:-3]})
            cached = self._index_get(py_path)
            if cached is None:
                (stale if self._probe_missed(py_path) else fresh).append(py_path)
            elif cached:
                filters[py_path] = self._make_filter(cached)

        if fresh:
            tried = set()
            got = self._fan_out(fresh, self._probe_classes,
                                self.home_workers, self.home_budget,
                                attempted=tried, per_item=self.class_timeout)
            for py_path, cls in got:
                if cls:
                    filters[py_path] = self._make_filter(cls)
            for py_path in fresh:
                if py_path not in tried:
                    with self.global_lock:
                        self._probe_fail.pop(py_path, None)
                    self._index_drop_fail(py_path)
            self._index_save()

        rest = [p for p in (fresh + stale) if p not in filters]
        if rest:
            self._warm_async(rest)

        return {'class': classes, 'filters': filters, 'list': []}

    def homeVideoContent(self):
        return {'list': []}

    def _probe_missed(self, py_path):
        with self.global_lock:
            if self._probe_fail.get(py_path, 0) >= self.probe_retry:
                return True
        item = self._index_entry(py_path)
        return bool(item and int(item.get('fail', 0)) >= self.probe_retry)

    def _make_filter(self, sub_classes):
        return [{
            'key': 'sub',
            'name': '分类',
            'value': [{'n': c['type_name'], 'v': c['type_id']} for c in sub_classes],
        }]

    def _probe_classes(self, py_path, remaining=None, priority=False, cap=None):
        cached = self._index_get(py_path)
        if cached is not None:
            return cached
        limit = float(cap or self.class_timeout)
        budget = limit if remaining is None else max(1.0, min(limit, remaining - 0.2))
        deadline = time.time() + budget
        spider = self._get_spider(py_path, timeout=self._left(deadline),
                                  allow_cooling=False, priority=priority)
        fn = self._method(spider, 'homeContent')
        if fn is None:
            self._probe_mark(py_path, False)
            return None
        args = self._trim_args(fn, (True,))
        res, status = self._call(py_path, fn, self._left(deadline), self.retry_times,
                                 *args, priority=priority)
        if status != 'ok' or not isinstance(res, dict):
            self._probe_mark(py_path, False)
            return None
        classes = self._sanitize_classes(res.get('class'))
        self._index_put(py_path, classes)
        self._probe_mark(py_path, True)
        return classes

    def _probe_mark(self, py_path, ok):
        with self.global_lock:
            if ok:
                self._probe_fail.pop(py_path, None)
            else:
                self._probe_fail[py_path] = self._probe_fail.get(py_path, 0) + 1
        if not ok:
            self._index_put_fail(py_path)

    def _warm_async(self, paths):
        with self._warm_lock:
            todo = [p for p in paths if p not in self._warming]
            if not todo:
                return
            self._warming.update(todo)

        def job():
            try:
                self._fan_out(todo, self._probe_warm,
                              self.warm_workers, self.warm_budget,
                              per_item=self.warm_item)
                self._index_save()
            finally:
                with self._warm_lock:
                    self._warming.difference_update(todo)
                self._trim_cache()
        self._spawn(job)

    def _probe_warm(self, py_path, remaining=None):
        r = self._probe_classes(py_path, remaining=remaining, cap=self.warm_item)
        self._trim_cache()
        return r

    def categoryContent(self, tid, pg, filter, extend):
        deadline = time.time() + self.list_timeout
        py_path, sub_tid = self._split_tid(tid)
        if not py_path or not os.path.exists(py_path):
            return self._empty_list(pg)

        spider = self._get_spider(py_path, timeout=self._left(deadline), priority=True)
        if spider is None:
            return self._empty_list(pg)

        if isinstance(extend, dict) and extend.get('sub'):
            sub_tid = str(extend['sub'])
        if not sub_tid:
            cached = self._index_get(py_path)
            if cached is None:
                half = max(1.0, self._left(deadline) * 0.5)
                cached = self._probe_classes(py_path, remaining=half + 0.2,
                                             priority=True) or []
            sub_tid = cached[0]['type_id'] if cached else ''

        ext = deepcopy(extend) if isinstance(extend, dict) else {}
        ext.pop('sub', None)

        fn = self._method(spider, 'categoryContent')
        if fn is None:
            return self._empty_list(pg)
        args = self._trim_args(fn, (sub_tid, str(pg), filter, ext))
        res, status = self._call(py_path, fn, self._left(deadline), self.retry_times,
                                 *args, priority=True)
        out = self._normalize_list(res, py_path, spider)
        if out is None or not out['list']:
            alt = self._home_video(py_path, spider, deadline)
            if alt:
                return {'list': alt, 'page': 1, 'pagecount': 1,
                        'limit': len(alt), 'total': len(alt)}
            return self._empty_list(pg)
        out.setdefault('page', int(pg) if str(pg).isdigit() else 1)
        return out

    def _home_video(self, py_path, spider, deadline):
        if deadline - time.time() < 1.0:
            return None
        fn = self._method(spider, 'homeVideoContent')
        if fn is None:
            return None
        res, status = self._call(py_path, fn, self._left(deadline), 0, priority=True)
        out = self._normalize_list(res, py_path, spider)
        return out['list'] if out and out['list'] else None

    @staticmethod
    def _left(deadline, floor=1.0):
        return max(floor, deadline - time.time())

    def _split_tid(self, tid):
        tid = str(tid or '')
        if self.ID_SEP in tid:
            a, b = tid.split(self.ID_SEP, 1)
            return a, b
        return tid, ''

    @staticmethod
    def _empty_list(pg=1):
        try:
            page = int(pg)
        except Exception:
            page = 1
        return {'list': [], 'page': page, 'pagecount': page, 'limit': 0, 'total': 0}

    def detailContent(self, array):
        if not array:
            return {'list': []}
        raw = str(array[0])
        if self.ID_SEP not in raw:
            return {'list': []}
        deadline = time.time() + self.detail_timeout
        py_path, real_id = raw.split(self.ID_SEP, 1)
        spider = self._get_spider(py_path, timeout=self._left(deadline), priority=True)
        fn = self._method(spider, 'detailContent')
        if fn is None:
            return {'list': []}

        res, status = self._call(py_path, fn, self._left(deadline), self.retry_times,
                                 [real_id], priority=True)
        if status == 'error':
            res, status = self._call(py_path, fn, self._left(deadline), 0,
                                     real_id, priority=True)
        if not isinstance(res, dict) or not isinstance(res.get('list'), list) or not res['list']:
            return {'list': []}

        vod = res['list'][0]
        if not isinstance(vod, dict):
            return {'list': []}
        if not self._normalize_vod(vod, py_path, spider):
            return {'list': []}
        vod['vod_play_url'] = self._tag_play_url(vod.get('vod_play_url'), py_path, spider)
        return {'list': [vod]}

    def _tag_play_url(self, play_url, py_path, spider):
        if not isinstance(play_url, str) or not play_url:
            return ''
        prefix = py_path + self.ID_SEP
        lines = []
        for line in play_url.split('$$$'):
            parts = []
            for part in line.split('#'):
                if not part:
                    continue
                if '$' in part:
                    title, pid = part.split('$', 1)
                else:
                    title, pid = part, part
                if not pid.startswith(prefix):
                    pid = prefix + pid
                title = title.replace('#', ' ').replace('$', ' ').strip() or '播放'
                parts.append('%s$%s' % (title, pid))
            lines.append('#'.join(parts))
        return '$$$'.join(lines)

    def playerContent(self, flag, id, vipFlags):
        raw = str(id or '')
        if self.ID_SEP not in raw:
            return {'parse': 0, 'url': raw, 'header': {}}
        deadline = time.time() + self.play_timeout
        py_path, real_id = raw.split(self.ID_SEP, 1)
        spider = self._get_spider(py_path, timeout=self._left(deadline), priority=True)
        fn = self._method(spider, 'playerContent')
        if fn is None:
            return {'parse': 0, 'url': real_id, 'header': {}}

        args = self._trim_args(fn, (self._strip_prefix(flag, py_path), real_id, vipFlags))
        res, status = self._call(py_path, fn, self._left(deadline), self.retry_times,
                                 *args, priority=True)
        if isinstance(res, dict) and (res.get('url') or res.get('playUrl')):
            return self._tag_player_result(res, py_path)
        if isinstance(res, str) and res:
            return {'parse': 0, 'url': res, 'header': {}}
        return {'parse': 0, 'url': real_id if real_id.startswith('http') else '', 'header': {}}

    def _strip_prefix(self, value, py_path):
        v = str(value or '')
        pre = py_path + self.ID_SEP
        return v[len(pre):] if v.startswith(pre) else v

    def _tag_player_result(self, res, py_path):
        url = res.get('url')
        if isinstance(url, str):
            res['url'] = self._wrap_proxy(url, py_path)
        elif isinstance(url, list):
            res['url'] = [self._wrap_proxy(u, py_path) if isinstance(u, str) else u
                          for u in url]
        elif isinstance(url, dict):
            vals = url.get('values')
            if isinstance(vals, list):
                for item in vals:
                    if isinstance(item, dict) and isinstance(item.get('v'), str):
                        item['v'] = self._wrap_proxy(item['v'], py_path)
        if isinstance(res.get('playUrl'), str):
            res['playUrl'] = self._wrap_proxy(res['playUrl'], py_path)
        if isinstance(res.get('subs'), list):
            for s in res['subs']:
                if isinstance(s, dict) and isinstance(s.get('url'), str):
                    s['url'] = self._wrap_proxy(s['url'], py_path)
        return res

    MEDIA_EXT = ('.m3u8', '.mp4', '.mkv', '.flv', '.avi', '.mov', '.ts',
                 '.mpd', '.m4a', '.mp3', '.wmv', '.rmvb', '.webm', '.m3u')

    def isVideoFormat(self, url):
        raw = str(url or '')
        if not raw:
            return False
        if self.ID_SEP in raw:
            py_path, real = raw.split(self.ID_SEP, 1)
            if self._ask_sniff(self._cached_instance(py_path), real):
                return True
            return self._is_media(real)
        with self.global_lock:
            insts = [v[0] for v in self.spider_cache.values()]
        for inst in insts:
            if self._ask_sniff(inst, raw):
                return True
        return self._is_media(raw)

    def _ask_sniff(self, inst, url):
        if not self._overrides(inst, 'isVideoFormat'):
            return False
        fn = self._method(inst, 'isVideoFormat')
        if fn is None:
            return False
        v, status = self._guard(fn, self.sniff_timeout, url)
        return bool(v) if status == 'ok' else False

    def manualVideoCheck(self):
        with self.global_lock:
            insts = [v[0] for v in self.spider_cache.values()]
        for inst in insts:
            if not self._overrides(inst, 'manualVideoCheck'):
                continue
            fn = self._method(inst, 'manualVideoCheck')
            if fn is None:
                continue
            v, status = self._guard(fn, self.sniff_timeout)
            if status == 'ok' and v:
                return True
        return False

    @staticmethod
    def _overrides(inst, name):
        if inst is None:
            return False
        own = getattr(type(inst), name, None)
        if own is None:
            return False
        base = getattr(BaseSpider, name, None)
        return own is not base

    def _is_media(self, url):
        raw = str(url or '').split('?')[0].split('#')[0].lower()
        return raw.endswith(self.MEDIA_EXT)

    def searchContent(self, key, quick, pg='1'):
        key = (key or '').strip()
        if not key:
            return {'list': []}

        files = self._list_files()
        alive = [p for p in files if not self._cooling(p)]
        if not alive:
            alive = files
        if not alive:
            return {'list': []}

        workers = min(max(self.search_workers,
                          int(len(alive) / max(1.0, self.search_budget / self.list_timeout)) + 1),
                      64)

        def job(py_path, remaining):
            return self._search_one(py_path, key, quick, pg, remaining)

        got = self._fan_out(alive, job, workers, self.search_budget,
                            per_item=self.list_timeout)

        seen = set()
        merged = []
        for _, items in sorted(got, key=lambda kv: kv[0]):
            for v in items:
                vid = v.get('vod_id')
                if vid and vid not in seen:
                    seen.add(vid)
                    merged.append(v)
        self._log('SEARCH %s sources=%d/%d hit=%d' % (key, len(got), len(alive), len(merged)))
        return {'list': merged[:self.search_limit]}

    def _search_one(self, py_path, key, quick, pg, remaining):
        deadline = time.time() + max(1.0, remaining - 0.2)
        spider = self._get_spider(py_path, timeout=self._left(deadline),
                                  allow_cooling=False)
        fn = self._method(spider, 'searchContent')
        if fn is None:
            return None
        args = self._trim_args(fn, (key, quick, str(pg)))
        res, status = self._call(py_path, fn, self._left(deadline), 0, *args)
        out = self._normalize_list(res, py_path, spider)
        if not out or not out['list']:
            return None
        return out['list']

    def searchContentPage(self, key, quick, pg='1'):
        return self.searchContent(key, quick, pg)

    def localProxy(self, params):
        if not isinstance(params, dict):
            return None
        if params.get('do') != 'py':
            return None

        owner = params.get(self.PROXY_TAG)
        if owner:
            target = self._resolve_owner(owner)
            if not target:
                return None
            inner = dict(params)
            inner.pop(self.PROXY_TAG, None)
            deadline = time.time() + self.proxy_timeout
            spider = self._get_spider(target, timeout=self._left(deadline), priority=True)
            fn = self._method(spider, 'localProxy')
            if fn is None:
                return None
            res, _ = self._call(target, fn, self._left(deadline), 0, inner, priority=True)
            return res

        with self.global_lock:
            items = sorted(self.spider_cache.items(), key=lambda kv: kv[1][2], reverse=True)
        deadline = time.time() + self.proxy_timeout
        for py_path, item in items:
            if time.time() >= deadline:
                break
            fn = self._method(item[0], 'localProxy')
            if fn is None:
                continue
            res, _ = self._call(py_path, fn, self._left(deadline, floor=0.5), 0,
                                params, priority=True)
            if res is not None:
                return res
        return None

    def _resolve_owner(self, name):
        name = os.path.basename(str(name))
        with self.global_lock:
            for path in self.spider_cache.keys():
                if os.path.basename(path) == name:
                    return path
        for path in self._list_files():
            if os.path.basename(path) == name:
                return path
        return None