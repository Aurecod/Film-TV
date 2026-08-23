import sys
sys.dont_write_bytecode = True

import os
import json
import hashlib
import urllib.request
import urllib.parse
from base.spider import Spider

class Spider(Spider):
    PY_PATH_1 = "/storage/emulated/0/Film-TV/File/py/Abalone"
    PY_PATH_2 = "F:\\模拟共享\\Film-TV\\File\\py\\Abalone"
    HTML_PATH_1 = "/storage/emulated/0/Film-TV/File/html/Abalone"
    HTML_PATH_2 = "F:\\模拟共享\\Film-TV\\File\\html\\Abalone"

    REGISTRY_PATH = "/storage/emulated/0/Film-TV/Abalone.json"
    GENERATED_PREFIX = "local_"

    ICON_SCAN = "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI2NCIgaGVpZ2h0PSI2NCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IiM0Q0FGNTAiIHN0cm9rZS13aWR0aD0iMiIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIj48Y2lyY2xlIGN4PSIxMSIgY3k9IjExIiByPSI4Ii8+PGxpbmUgeDE9IjIxIiB5MT0iMjEiIHgyPSIxNi42NSIgeTI9IjE2LjY1Ii8+PC9zdmc+"
    ICON_CLEAR = "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI2NCIgaGVpZ2h0PSI2NCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IiNFNTM3MzciIHN0cm9rZS13aWR0aD0iMiIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIj48cG9seWxpbmUgcG9pbnRzPSIzIDYgNSA2IDIxIDYiLz48cGF0aCBkPSJNMTkgNnYxNGEyIDIgMCAwIDEtMiAySDdhMiAyIDAgMCAxLTItMlY2bDMgMEg0Ii8+PHBhdGggZD0iTTEwIDExdjYiLz48cGF0aCBkPSJNMTQgMTF2NiIvPjwvc3ZnPg=="

    def init(self, extend=""):
        self.py_paths = []
        if os.path.exists(self.PY_PATH_1):
            self.py_paths.append(self.PY_PATH_1)
        if os.path.exists(self.PY_PATH_2) and self.PY_PATH_2 not in self.py_paths:
            self.py_paths.append(self.PY_PATH_2)

        self.html_paths = []
        if os.path.exists(self.HTML_PATH_1):
            self.html_paths.append(self.HTML_PATH_1)
        if os.path.exists(self.HTML_PATH_2) and self.HTML_PATH_2 not in self.html_paths:
            self.html_paths.append(self.HTML_PATH_2)

        # ===== 新增：从 extend 读取目标 JSON 路径 =====
        self.target_path = self.REGISTRY_PATH
        if extend:
            ext = extend.strip().strip('"').strip("'").replace("file://", "")
            if ext.lower() == "auto":
                detected = self._detect_active_json()
                if detected:
                    self.target_path = detected
            elif ext:
                self.target_path = ext

        # 确保目录存在
        d = os.path.dirname(self.target_path)
        if d and not os.path.exists(d):
            try:
                os.makedirs(d)
            except:
                pass

    def getName(self):
        return "写入器 (PY+HTML)"

    def _to_superscript(self, num):
        superscript_map = {
            '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
            '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹'
        }
        return ''.join(superscript_map[ch] for ch in str(num))

    def homeContent(self, filter):
        auto_items = self._get_injected_sites_raw()
        py_count, html_count = self._count_injected_types(auto_items)
        py_sup = self._to_superscript(py_count)
        html_sup = self._to_superscript(html_count)
        class_name = f"已写入站点:   html{html_sup}   py{py_sup}"
        classes = [{"type_id": "injected", "type_name": class_name}]
        return {"class": classes, "list": []}

    def _count_injected_types(self, items):
        py = 0
        html = 0
        for item in items:
            if item.get("homePage"):
                html += 1
            else:
                py += 1
        return py, html

    def categoryContent(self, tid, pg, filter, extend):
        if tid == "injected":
            items = [
                {"vod_id": "__inject__", "vod_name": "写入", "vod_remarks": "扫描目录，写入所有站点", "vod_pic": self.ICON_SCAN, "action": "inject"},
                {"vod_id": "__clear__", "vod_name": "清除", "vod_remarks": "移除所有写入站点", "vod_pic": self.ICON_CLEAR, "action": "clear"}
            ]
            return self._paged_result(items, pg)
        else:
            return {"list": []}

    def detailContent(self, array):
        return {"list": []}

    def action(self, action):
        if action == "inject":
            return self._action_inject()
        elif action == "clear":
            return self._action_clear()
        else:
            return {"code": 0, "msg": "未知操作"}

    def searchContent(self, key, quick, pg="1"):
        key = key.lower()
        items = []
        all_paths = self.py_paths + self.html_paths
        for path in all_paths:
            if not os.path.exists(path):
                continue
            for f in os.listdir(path):
                if key in f.lower() and (f.endswith(".py") or f.endswith(".html")) and not f.startswith("__"):
                    items.append({"vod_id": hashlib.md5(f.encode()).hexdigest()[:16], "vod_name": f, "vod_remarks": "文件", "vod_pic": ""})
        return self._paged_result(items, pg)

    def playerContent(self, flag, id, vipFlags):
        return {"parse": 0, "url": ""}

    def destroy(self):
        pass

    # --------------------- 核心 ---------------------
    def _load_target(self):
        if not os.path.exists(self.target_path):
            return {"sites": []}
        try:
            with open(self.target_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    return {"sites": []}
                if "sites" not in data:
                    data["sites"] = []
                return data
        except:
            return {"sites": []}

    def _save_target(self, data):
        with open(self.target_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _is_generated(self, site):
        return site.get("key", "").startswith(self.GENERATED_PREFIX)

    def _get_injected_sites_raw(self):
        data = self._load_target()
        return [s for s in data.get("sites", []) if self._is_generated(s)]

    def _detect_active_json(self):
        try:
            for port in range(9978, 9999):
                try:
                    req = urllib.request.Request(
                        f"http://127.0.0.1:{port}/manage/configs",
                        headers={"Accept": "application/json"}
                    )
                    with urllib.request.urlopen(req, timeout=0.5) as resp:
                        data = json.loads(resp.read().decode())
                        for item in data.get("items", []):
                            if item.get("type") == 0 and item.get("active"):
                                url = item.get("url", "")
                                if url.startswith("file://"):
                                    return url[7:]
                                elif os.path.exists(url):
                                    return url
                except Exception:
                    continue
        except Exception:
            pass
        return None

    def _build_site(self, file_path, ext):
        full_name = os.path.basename(file_path)          # 含扩展名
        base_name = os.path.splitext(full_name)[0]       # 不含扩展名
        key = self.GENERATED_PREFIX + base_name          # "local_文件名"
        
        # ---- 改为相对路径 ----
        # 获取配置文件所在目录的绝对路径
        target_dir = os.path.dirname(os.path.abspath(self.target_path))
        # 计算相对路径
        rel_path = os.path.relpath(file_path, target_dir)
        # 统一为 Unix 风格斜杠，并添加 "./"
        file_url = "./" + rel_path.replace(os.sep, "/")
        # 如果相对路径为空（即文件就在配置目录下），则直接 "./文件名"
        if rel_path == ".":
            file_url = "./" + full_name
        # ---------------------

        if ext == '.py':
            display_name = full_name[:-3] + "ᵖʸ" if full_name.endswith(".py") else full_name + "ᵖʸ"
            site = {
                "key": key,
                "name": display_name,
                "type": 3,
                "api": file_url,
                "searchable": 1,
                "quickSearch": 1,
                "filterable": 1,
                "order_num": 0,
                "style": {"type": "rect"},
                "ext": ""
            }
        else:  # html
            display_name = full_name[:-5] + "ʰᵗᵐˡ" if full_name.endswith(".html") else full_name + "ʰᵗᵐˡ"
            site = {
                "key": key,
                "name": display_name,
                "type": 3,
                "homePage": file_url
            }
        return site

    def _action_inject(self):
        data = self._load_target()
        sites = data.get("sites", [])
        manual = [s for s in sites if not self._is_generated(s)]
        new_sites = []

        # HTML 优先
        for path in self.html_paths:
            if not os.path.exists(path):
                continue
            for f in os.listdir(path):
                if f.endswith(".html") and not f.startswith("__"):
                    full_path = os.path.join(path, f)
                    new_sites.append(self._build_site(full_path, '.html'))

        # Py 其次
        for path in self.py_paths:
            if not os.path.exists(path):
                continue
            for f in os.listdir(path):
                if f.endswith(".py") and not f.startswith("__"):
                    full_path = os.path.join(path, f)
                    new_sites.append(self._build_site(full_path, '.py'))

        data["sites"] = new_sites + manual
        self._save_target(data)
        self._reload_app()

        count = len(new_sites)
        target = os.path.basename(self.target_path)
        return {"code": 0, "msg": f"✅ 已写入 {count} 个站点到 {target}（HTML + Py，已置顶）\n⚠️ FongMi 请手动点「配置地址」刷新"}

    def _action_clear(self):
        data = self._load_target()
        data["sites"] = [s for s in data.get("sites", []) if not self._is_generated(s)]
        self._save_target(data)
        self._reload_app()
        return {"code": 0, "msg": "🗑 已移除所有写入站点\n⚠️ FongMi 请手动点「配置地址」刷新"}

    def _reload_app(self):
        try:
            for port in range(9978, 9999):
                try:
                    req = urllib.request.Request(f"http://127.0.0.1:{port}/manage/configs", headers={"Accept": "application/json"})
                    with urllib.request.urlopen(req, timeout=0.5) as resp:
                        data = json.loads(resp.read().decode())
                        items = data.get("items", [])
                        for item in items:
                            if item.get("type") == 0 and item.get("active"):
                                url = item.get("url", "")
                                if url:
                                    reload_req = urllib.request.Request(
                                        f"http://127.0.0.1:{port}/manage/config/use?type=0&url={urllib.parse.quote(url)}"
                                    )
                                    urllib.request.urlopen(reload_req, timeout=0.5)
                                    return
                except Exception:
                    continue
        except Exception:
            pass

    def _paged_result(self, items, pg):
        return {"list": items, "page": 1, "pagecount": 1, "total": len(items)}