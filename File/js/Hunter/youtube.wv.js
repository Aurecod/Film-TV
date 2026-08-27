/**
 * @config
 * timeout: 30
 * blockImages: false
 * returnType: dom
 * debug: false
 *
 */

var siteUrl = 'https://m.youtube.com';

/* ==================== 共用纯计算 ==================== */

function safeText(v) {
    return String(v == null ? '' : v).replace(/\s+/g, ' ').trim();
}

function firstId(ids) {
    return Array.isArray(ids) ? String(ids[0] || '') : String(ids == null ? '' : ids);
}

function cleanPlayName(value, fallback) {
    var name = safeText(value || fallback || '').replace(/[$#]/g, ' ');
    return name || '第1集';
}

function packPlayId(data) {
    return 'wvplay:' + encodeURIComponent(JSON.stringify(data || {}));
}

function unpackPlayId(value) {
    var raw = String(value || '');
    if (raw.indexOf('wvplay:') !== 0) return { type: 'url', url: raw };
    var payload = raw.slice(7);
    try {
        var d = JSON.parse(payload);
        if (d && typeof d === 'object') return d;
    } catch (e) {}
    try {
        var d2 = JSON.parse(decodeURIComponent(payload));
        if (d2 && typeof d2 === 'object') return d2;
    } catch (e2) {}
    return {};
}

function extractVideoId(input) {
    var s = String(input || '');
    var m = s.match(/[?&]v=([A-Za-z0-9_-]{11})/) || s.match(/youtu\.be\/([A-Za-z0-9_-]{11})/)
        || s.match(/\/(?:embed|shorts|live)\/([A-Za-z0-9_-]{11})/) || s.match(/^([A-Za-z0-9_-]{11})$/);
    return m ? m[1] : '';
}

function normalizeCrTid(tid) {
    if (tid && typeof tid === 'object') return String(tid.id || tid.name || '');
    var raw = String(tid || '').trim();
    if (!raw) return '';
    try { raw = decodeURIComponent(raw); } catch (e) {}
    if (raw.charAt(0) === '{' && raw.charAt(raw.length - 1) === '}') {
        try { var d = JSON.parse(raw); raw = String(d.id || d.name || ''); } catch (e2) {}
    }
    return raw;
}

function richLink(name, routeId) {
    var text = safeText(name);
    var id = String(routeId || '').trim();
    if (!text || !id) return text;
    return '[a=cr:' + JSON.stringify({ id: id, name: text }) + '/]' + text + '[/a]';
}

/* ---------- 搜索筛选 sp 编码（protobuf -> base64url） ---------- */

function pbVarint(arr, v) {
    v = Math.floor(Number(v) || 0);
    while (v >= 0x80) { arr.push((v & 0x7f) | 0x80); v >>>= 7; }
    arr.push(v);
}

/**
 * opts.upload: 1小时内/2今天/3本周/4本月/5今年
 * opts.dur: 1短(<4min) / 2长(>20min)
 * opts.sort: 1评分 / 2上传日期 / 3观看次数
 */
function buildSp(opts) {
    opts = opts || {};
    var root = [];
    var flt = [];
    if (opts.upload) { pbVarint(flt, 1 << 3); pbVarint(flt, opts.upload); }
    if (opts.dur) { pbVarint(flt, 3 << 3); pbVarint(flt, opts.dur); }
    if (opts.sort) { pbVarint(root, 1 << 3); pbVarint(root, opts.sort); }
    if (flt.length) {
        pbVarint(root, (2 << 3) | 2);
        pbVarint(root, flt.length);
        for (var i = 0; i < flt.length; i++) root.push(flt[i]);
    }
    if (!root.length) return '';
    var chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';
    var out = '';
    for (var j = 0; j < root.length; j += 3) {
        var b0 = root[j];
        var b1 = j + 1 < root.length ? root[j + 1] : 0;
        var b2 = j + 2 < root.length ? root[j + 2] : 0;
        out += chars.charAt(b0 >> 2)
            + chars.charAt(((b0 & 3) << 4) | (b1 >> 4))
            + (j + 1 < root.length ? chars.charAt(((b1 & 15) << 2) | (b2 >> 6)) : '')
            + (j + 2 < root.length ? chars.charAt(b2 & 63) : '');
    }
    return out;
}

/* ==================== 常量 ==================== */

var IT_KEY = 'AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8';

var COMMON_FILTERS = [
    {
        key: 'upload', name: '上传时间',
        value: [
            { n: '全部', v: '' }, { n: '一小时内', v: '1' }, { n: '今天', v: '2' },
            { n: '本周', v: '3' }, { n: '本月', v: '4' }, { n: '今年', v: '5' }
        ]
    },
    {
        key: 'dur', name: '时长',
        value: [
            { n: '全部', v: '' }, { n: '4分钟以内', v: '1' }, { n: '20分钟以上', v: '2' }
        ]
    },
    {
        key: 'sort', name: '排序',
        value: [
            { n: '相关度', v: '' }, { n: '最高评分', v: '1' },
            { n: '上传日期', v: '2' }, { n: '观看次数', v: '3' }
        ]
    }
];

/* ==================== 我的入口、分类配置与 action ==================== */

var MINE_TID = '__mine__';
var HISTORY_TID = '__mine_history__';
var SUBSCRIPTIONS_TID = '__mine_subscriptions__';
var CATEGORY_ACTION_ID = 'yt_category_config';
var CATEGORY_VISIBLE_ACTION_ID = 'yt_category_visible';
var STYLE_ACTION_ID = 'yt_list_style';
var RECOMMEND_ACTION_ID = 'yt_show_recommend';
var CFG_KEY = 'yt_wv_cfg_v2';
var _cfgMem = null;

var DEFAULT_CATEGORIES = [
    { type_id: 'drama', type_name: '漫剧', keyword: '漫剧', style: 1 },
    { type_id: 'all', type_name: '全部', keyword: '热门', style: 2 },
    { type_id: 'music', type_name: '音乐', keyword: '音乐', style: 2 },
    { type_id: 'movie', type_name: '电影', keyword: '电影', style: 2 }
];

var STYLE_OPTIONS = [
    { key: 'normal', name: '双列', style: { type: 'rect', ratio: 0.75 } },
    { key: 'wide', name: '大图', style: { type: 'rect', ratio: 1.78 } },
    { key: 'list', name: '列表', style: { type: 'list' } }
];

/** 从 host.cache 读取配置，脚本重新加载后仍保留用户设置。 */
function cfgRead() {
    if (_cfgMem) return _cfgMem;
    var raw = '';
    try { raw = host.cache.get(CFG_KEY, ''); } catch (e) {}
    try {
        var data = JSON.parse(raw || 'null');
        if (data && typeof data === 'object') { _cfgMem = data; return data; }
    } catch (e2) {}
    _cfgMem = {};
    return _cfgMem;
}

function cfgWrite(data) {
    _cfgMem = data || {};
    try { host.cache.set(CFG_KEY, JSON.stringify(_cfgMem)); } catch (e) {}
}

function normalizeCategories(value) {
    var items = [];
    if (Array.isArray(value)) {
        for (var i = 0; i < value.length; i++) {
            var item = value[i];
            if (!item || typeof item !== 'object') continue;
            var name = safeText(item.name || item.type_name);
            var keyword = safeText(item.keyword || item.type_id || name);
            var style = Number(item.style);
            if (style !== 1 && style !== 2 && style !== 3) style = 0;
            if (name && keyword && name !== '我的' && keyword !== MINE_TID) items.push({
                type_id: safeText(item.type_id || ('custom:' + encodeURIComponent(keyword))),
                type_name: name,
                keyword: keyword,
                style: style
            });
        }
    }
    return items;
}

function configuredCategories() {
    var cfg = cfgRead();
    var custom = normalizeCategories(cfg.categories);
    return custom.length ? custom : DEFAULT_CATEGORIES.slice();
}

function visibleCategories() {
    var categories = configuredCategories();
    var visible = cfgRead().visible;
    if (!Array.isArray(visible)) return categories;
    var result = categories.filter(function (item) { return visible.indexOf(item.type_id) >= 0; });
    return result.length ? result : categories;
}

function categoryConfigText() {
    return configuredCategories().map(function (item) {
        return item.type_name + '=' + item.keyword + (item.style ? ',' + item.style : '');
    }).join(';');
}

function parseCategoryConfig(text) {
    var raw = String(text == null ? '' : text).replace(/\r/g, '\n').trim();
    if (!raw) return [];
    if (raw.charAt(0) === '[') {
        try { return normalizeCategories(JSON.parse(raw)); } catch (e) {}
    }
    var result = [];
    var matcher = /([^,;\n=]+)=([^,;\n]+?)(?:,(1|2|3))?(?=,|;|\n|$)/g;
    var match;
    while ((match = matcher.exec(raw)) !== null) {
        var name = safeText(match[1]);
        var keyword = safeText(match[2]);
        var style = Number(match[3] || 0);
        if (!name || !keyword || name === '我的' || keyword === MINE_TID) continue;
        result.push({
            type_id: 'custom:' + encodeURIComponent(keyword),
            type_name: name,
            keyword: keyword,
            style: style
        });
    }
    return result;
}

function getListStyle() {
    var cfg = cfgRead();
    for (var i = 0; i < STYLE_OPTIONS.length; i++) {
        if (STYLE_OPTIONS[i].key === cfg.listStyle) return STYLE_OPTIONS[i].style;
    }
    return STYLE_OPTIONS[0].style;
}

function getCategoryStyle(categoryId) {
    var categories = configuredCategories();
    for (var i = 0; i < categories.length; i++) {
        if (categories[i].type_id !== categoryId) continue;
        // 分类明确指定 1/2/3 时拥有最高优先级；只有 0 才回退到全局列表样式。
        var specified = Number(categories[i].style);
        if (specified === 1) return STYLE_OPTIONS[0].style;
        if (specified === 2) return STYLE_OPTIONS[1].style;
        if (specified === 3) return STYLE_OPTIONS[2].style;
        break;
    }
    return getListStyle();
}

function applyCategoryStyle(list, categoryId) {
    var style = getCategoryStyle(categoryId);
    for (var i = 0; i < list.length; i++) list[i].style = style;
    return list;
}

function folderItem(id, name, remark) {
    return { vod_id: id, vod_name: name, vod_tag: 'folder', vod_pic: '', vod_remarks: remark || '', style: { type: 'list' } };
}

function actionItem(config, remark) {
    return { vod_id: JSON.stringify(config), vod_name: config.title || config.actionId, vod_tag: 'action', vod_remarks: remark || '', style: { type: 'list' } };
}

function isYoutubeLoggedIn() {
    try {
        var cookie = String(host.cookies.get('https://www.youtube.com/') || '');
        return /(?:^|;)\s*(?:SID|SSID|HSID|APISID|SAPISID|LOGIN_INFO|__Secure-3PSID)=/i.test(cookie);
    } catch (e) {
        return false;
    }
}

function currentVisibleCategoryText() {
    return visibleCategories().map(function (item) { return item.type_name; }).join('、') || '无';
}

function currentStyleText() {
    var cfg = cfgRead();
    for (var i = 0; i < STYLE_OPTIONS.length; i++) {
        if (STYLE_OPTIONS[i].key === cfg.listStyle) return STYLE_OPTIONS[i].name;
    }
    return STYLE_OPTIONS[0].name;
}

function mineMenu() {
    var loginUrl = 'https://www.youtube.com/signin';
    var loggedIn = isYoutubeLoggedIn();
    var cfg = cfgRead();
    var categories = configuredCategories();
    var visible = Array.isArray(cfg.visible) ? visibleCategories().map(function (item) { return item.type_id; }) : null;
    return [
        actionItem({ actionId: 'yt_login', type: 'webview', title: '账号登录', url: loginUrl, height: -180, textZoom: 90 }, loggedIn ? '当前已登录' : '当前未登录'),
        folderItem(HISTORY_TID, '历史记录', '查看所有历史记录'),
        folderItem(SUBSCRIPTIONS_TID, '我的订阅', '查看我订阅的up主'),
        actionItem({ actionId: CATEGORY_ACTION_ID, type: 'input', id: 'categories', title: '分类设置',
            tip: '格式：名称=关键词,style;名称=关键词,style', value: categoryConfigText(),
            msg: '当前分类：' + categories.map(function (item) { return item.type_name; }).join('、')
                + '；style: 1双列 2大图 3列表' },
            '当前分类：' + categories.map(function (item) { return item.type_name; }).join('、')),
        actionItem({ actionId: CATEGORY_VISIBLE_ACTION_ID, type: 'select', title: '显示分类',
            msg: '激活表示显示，取消激活表示隐藏；“我的”始终显示',
            option: categories.map(function (item) {
                var selected = !Array.isArray(visible) || visible.indexOf(item.type_id) >= 0;
                return { name: item.type_name, action: item.type_id, selected: selected };
            }) }, '当前显示：' + currentVisibleCategoryText()),
        actionItem({ actionId: STYLE_ACTION_ID, type: 'menu', title: '列表样式',
            option: STYLE_OPTIONS.map(function (item) { return { name: item.name, action: item.key }; }),
            selectedIndex: Math.max(0, STYLE_OPTIONS.findIndex(function (item) { return item.key === cfg.listStyle; })) }, '当前样式：' + currentStyleText()),
        actionItem({ actionId: RECOMMEND_ACTION_ID, type: 'menu', title: '显示推荐',
            option: [{ name: '开', action: 'on' }, { name: '关', action: 'off' }],
            selectedIndex: cfg.showRecommend === false ? 1 : 0 },
            cfg.showRecommend === false ? '关' : '开')
    ];
}

/** action 输入框/菜单回调：保存分类和非“我的”分类的列表样式。 */
async function action(actionStr) {
    var data = {};
    try { data = JSON.parse(actionStr || '{}'); } catch (e) { data = {}; }
    var actionId = data.action || '';
    var value = data.value && typeof data.value === 'object' ? data.value : {};
    var cfg = cfgRead();
    if (actionId === CATEGORY_ACTION_ID) {
        var categories = parseCategoryConfig(value.categories || '');
        if (!categories.length) return '分类设置未保存：至少需要一个分类';
        cfg.categories = categories;
        cfgWrite(cfg);
        return '分类设置已保存，刷新首页生效';
    }
    if (actionId === CATEGORY_VISIBLE_ACTION_ID) {
        var selected = safeText(value.select || '').split(',').filter(function (item) { return item; });
        var allowed = configuredCategories().map(function (item) { return item.type_id; });
        selected = selected.filter(function (item) { return allowed.indexOf(item) >= 0; });
        if (!selected.length) return '至少显示一个分类，设置未保存';
        cfg.visible = selected;
        cfgWrite(cfg);
        return '显示分类已保存，刷新首页生效';
    }
    if (actionId === STYLE_ACTION_ID) {
        var style = safeText(value.menu || value.style || 'rect');
        cfg.listStyle = STYLE_OPTIONS.some(function (item) { return item.key === style; }) ? style : 'rect';
        cfgWrite(cfg);
        return '列表样式已保存，刷新分类页面生效';
    }
    if (actionId === RECOMMEND_ACTION_ID) {
        cfg.showRecommend = safeText(value.menu || '') !== 'off';
        cfgWrite(cfg);
        return '显示推荐已保存，刷新详情页面生效';
    }
    return '';
}



var routes = {
    homeContent: function () { return false; },
    homeVideoContent: function () { return false; },
    categoryContent: function () { return false; },
    detailContent: function () { return false; },
    recommendContent: function () { return false; },
    searchContent: function () { return false; },
    playerContent: function () { return false; }
};

/* ==================== WebView：InnerTube 请求与解析 ==================== */

var _itContext = {
    client: { clientName: 'MWEB', clientVersion: '2.20240726.00.00', clientScreen: 'WATCH', hl: 'zh-CN', gl: 'US' }
};

async function innertube(endpoint, body) {
    var payload = body || {};
    if (!payload.context) payload.context = _itContext;
    var res = await fetch(siteUrl + '/youtubei/v1/' + endpoint + '?key=' + IT_KEY + '&prettyPrint=false', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error('innertube ' + endpoint + ' HTTP ' + res.status);
    return res.json();
}

function runsToString(node) {
    if (!node) return '';
    if (typeof node === 'string') return safeText(node);
    if (node.simpleText) return safeText(node.simpleText);
    if (Array.isArray(node.runs)) {
        var out = '';
        for (var i = 0; i < node.runs.length; i++) out += (node.runs[i] && node.runs[i].text) || '';
        return safeText(out);
    }
    if (typeof node.content === 'string') return safeText(node.content);
    return '';
}

function bestThumb(thumbs) {
    if (!Array.isArray(thumbs) || !thumbs.length) return '';
    var best = thumbs[0];
    for (var i = 0; i < thumbs.length; i++) {
        if ((thumbs[i].width || 0) >= (best.width || 0)) best = thumbs[i];
    }
    return best.url ? (best.url.charAt(0) === '/' ? 'https://i.ytimg.com' + best.url : best.url) : '';
}

function mapVideoNode(node, seen) {
    if (!node || typeof node !== 'object' || seen[node.videoId]) return null;
    var title = runsToString(node.title) || runsToString(node.headline);
    if (!node.videoId || !title) return null;
    seen[node.videoId] = true;
    var remarks = runsToString(node.lengthText)
        || runsToString(node.shortViewCountText)
        || runsToString(node.publishedTimeText)
        || '';
    return {
        vod_id: packPlayId({ type: 'video', vid: node.videoId }),
        vod_name: title,
        vod_pic: bestThumb(node.thumbnail && node.thumbnail.thumbnails),
        vod_remarks: remarks,
        // 壳端按 Vod.style 决定网格/列表，不能只返回 Result.style。
        style: getListStyle()
    };
}

/** 递归收集响应树中的视频节点（命中 videoId 即停止下钻） */
function collectFromTree(root, seen) {
    var found = [];
    function walk(value) {
        if (!value || typeof value !== 'object') return;
        if (Array.isArray(value)) {
            for (var i = 0; i < value.length; i++) walk(value[i]);
            return;
        }
        if (typeof value.videoId === 'string' && /^[A-Za-z0-9_-]{11}$/.test(value.videoId) && (value.title || value.headline)) {
            var mapped = mapVideoNode(value, seen);
            if (mapped) found.push(mapped);
            return;
        }
        for (var key in value) {
            if (Object.prototype.hasOwnProperty.call(value, key)) walk(value[key]);
        }
    }
    walk(root);
    return found;
}

function collectContinuationToken(root) {
    var token = '';
    function walk(value) {
        if (token || !value || typeof value !== 'object') return;
        if (Array.isArray(value)) {
            for (var i = 0; i < value.length; i++) walk(value[i]);
            return;
        }
        var c = value.continuationItemRenderer;
        if (c && c.continuationEndpoint && c.continuationEndpoint.continuationCommand) {
            token = c.continuationEndpoint.continuationCommand.token || '';
            return;
        }
        for (var key in value) {
            if (Object.prototype.hasOwnProperty.call(value, key)) walk(value[key]);
        }
    }
    walk(root);
    return token;
}

/* ---------- 通用分页（token 会话缓存 + 失效重推进） ---------- */

function tokGet(key) {
    try { return JSON.parse(window.sessionStorage.getItem(key) || 'null'); } catch (e) { return null; }
}

function tokSet(key, val) {
    try { window.sessionStorage.setItem(key, JSON.stringify(val)); } catch (e2) {}
}

/**
 * 通用续页请求。返回 { res, hasMore }：
 * 第1页直接请求并缓存续页 token；后续页优先用缓存 token，
 * 缓存失效时从第1页重新逐页推进到目标页。
 * req(cont) 接收 { continuation }，无 continuation 表示首页请求。
 */
async function pagedToken(key, match, page, req) {
    if (page === 1) {
        var r1 = await req({});
        var n1 = collectContinuationToken(r1);
        tokSet(key, { m: match, page: 1, token: n1 });
        return { res: r1, hasMore: !!n1 };
    }
    var ctx = tokGet(key);
    var same = ctx && ctx.m === match && ctx.token;
    var token = same ? ctx.token : '';
    var cur = same ? (ctx.page || 1) : 0;
    if (!token) {
        var f = await req({});
        token = collectContinuationToken(f);
        cur = 1;
    }
    while (token && cur < page - 1) {
        var mid = await req({ continuation: token });
        token = collectContinuationToken(mid);
        cur++;
    }
    if (!token) return { res: null, hasMore: false };
    var rp = await req({ continuation: token });
    var nx = collectContinuationToken(rp);
    tokSet(key, { m: match, page: page, token: nx });
    return { res: rp, hasMore: !!nx };
}

/** 解析章节标记：优先从 playerOverlays 解析，若无则从简介 Description 中正则解析 */
function collectChapters(pr, desc) {
    var out = [];
    try {
        var map = pr && pr.playerOverlays && pr.playerOverlays.playerOverlayRenderer
            && pr.playerOverlays.playerOverlayRenderer.decoratedPlayerBarRenderer
            && pr.playerOverlays.playerOverlayRenderer.decoratedPlayerBarRenderer.decoratedPlayerBarRenderer
            && pr.playerOverlays.playerOverlayRenderer.decoratedPlayerBarRenderer.decoratedPlayerBarRenderer.playerBar
            && pr.playerOverlays.playerOverlayRenderer.decoratedPlayerBarRenderer.decoratedPlayerBarRenderer.playerBar.multiMarkersPlayerBarRenderer
            && pr.playerOverlays.playerOverlayRenderer.decoratedPlayerBarRenderer.decoratedPlayerBarRenderer.playerBar.multiMarkersPlayerBarRenderer.markersMap;
        if (map && map.length) {
            for (var i = 0; i < map.length; i++) {
                var chs = map[i] && map[i].value && map[i].value.chapters;
                if (!chs || !chs.length) continue;
                for (var j = 0; j < chs.length; j++) {
                    var cr = chs[j] && chs[j].chapterRenderer;
                    if (!cr || cr.timeRangeStartMillis === undefined) continue;
                    var title = runsToString(cr.title);
                    if (title) out.push({ title: title, ms: Number(cr.timeRangeStartMillis) });
                }
                if (out.length) return out;
            }
        }
    } catch (e) {}

    // 兜底：从简介中提取带时间戳的章节 (如 00:00:00《座位》 / 03:44 歌名)
    if (desc && typeof desc === 'string') {
        var re = /(?:^|\s)(?:(?:(\d{1,2}):)?(\d{1,2}):(\d{2}))\s*([^\d\n\r:][^\n\r]*?)(?=(?:\s+(?:(?:\d{1,2}:)?\d{1,2}:\d{2})|$))/g;
        var m;
        while ((m = re.exec(desc)) !== null) {
            var h = m[1] ? parseInt(m[1], 10) : 0;
            var min = parseInt(m[2], 10) || 0;
            var s = parseInt(m[3], 10) || 0;
            var sec = h * 3600 + min * 60 + s;
            var cTitle = m[4].trim();
            if (cTitle) out.push({ title: cTitle, ms: sec * 1000 });
        }
    }
    return out;
}

function pagedSearch(query, page, ext) {
    var sp = buildSp({ upload: ext.upload, dur: ext.dur, sort: ext.sort });
    return pagedToken('yt_search', query + '|' + sp, page, function (cont) {
        var body = { query: query };
        if (cont.continuation) body.continuation = cont.continuation;
        else if (sp) body.params = sp;
        return innertube('search', body);
    });
}

/* ==================== WebView 大方法 ==================== */

async function homeContent(filter) {
    // “我的”固定为首页首项，不参与分类设置隐藏；其余分类来自 host.cache。
    var classList = [{ type_id: MINE_TID, type_name: '我的' }].concat(visibleCategories());

    var filters = {};
    for (var i = 1; i < classList.length; i++) {
        filters[classList[i].type_id] = COMMON_FILTERS;
    }
    filters[MINE_TID] = [];
    return { class: classList, filters: filters };
}

async function homeVideoContent() {
    if (cfgRead().showRecommend === false) return { list: [] };
    // 匿名状态下首页 browse 接口不返回视频列表（实测），直接热词搜索
    try {
        var fb = await innertube('search', { query: '热门音乐 热门视频' });
        return { list: collectFromTree(fb, {}) };
    } catch (e) {
        return { list: [] };
    }
}

function CATEGORY_KEYWORD(id) {
    var categories = configuredCategories();
    for (var i = 0; i < categories.length; i++) {
        if (categories[i].type_id === id) return categories[i].keyword;
    }
    if (String(id).indexOf('custom:') === 0) {
        try { return decodeURIComponent(String(id).slice(7)); } catch (e) {}
    }
    return id || '热门';
}

function domVideoList(doc) {
    var list = [];
    var seen = {};
    if (!doc || !doc.querySelectorAll) return list;
    var links = doc.querySelectorAll('a[href]');
    for (var i = 0; i < links.length; i++) {
        var link = links[i];
        var href = String(link.getAttribute('href') || link.href || '');
        var vid = extractVideoId(href);
        if (!vid || seen[vid]) continue;
        var title = safeText(link.getAttribute('title') || link.getAttribute('aria-label') || link.textContent);
        var image = link.querySelector ? link.querySelector('img') : null;
        var pic = image ? String(image.getAttribute('src') || image.src || '') : '';
        if (!title) title = 'YouTube 视频 ' + vid;
        seen[vid] = true;
        list.push({
            vod_id: packPlayId({ type: 'video', vid: vid }),
            vod_name: title,
            vod_pic: pic,
            vod_remarks: '',
            style: { type: 'list' }
        });
    }
    return list;
}

async function feedContent(url) {
    var result = { page: 1, pagecount: 1, limit: 0, total: 0, style: { type: 'list' }, list: [] };
    try {
        var response = await fetch(url);
        var doc = response && response.doc;
        if (!doc && response && response.text) {
            var html = await response.text();
            doc = new DOMParser().parseFromString(html || '', 'text/html');
        }
        result.list = domVideoList(doc);
        result.limit = result.total = result.list.length;
    } catch (e) {}
    return result;
}

async function categoryContent(tid, pg, filter, extend) {
    var routeId = normalizeCrTid(tid);
    var page = parseInt(pg) || 1;
    var ext = extend || {};
    var result = { page: page, pagecount: page, limit: 0, total: 0, list: [] };

    if (routeId === MINE_TID) {
        return { page: 1, pagecount: 1, limit: 0, total: 0, style: { type: 'list' }, list: mineMenu() };
    }
    if (routeId === HISTORY_TID) return feedContent('https://m.youtube.com/feed/history');
    if (routeId === SUBSCRIPTIONS_TID) return feedContent('https://m.youtube.com/feed/subscriptions');

    try {
        var info;
        if (routeId.indexOf('channel:') === 0) {
            // 频道关联查询：browse videos 标签页
            var bid = routeId.slice(8);
            info = await pagedToken('yt_ch_' + bid, '', page, function (cont) {
                var body = { browseId: bid, params: 'EgZ2aWRlb3PyBgQKAjoA' };
                if (cont.continuation) body.continuation = cont.continuation;
                return innertube('browse', body);
            });
        } else if (routeId.indexOf('tag:') === 0) {
            info = await pagedSearch(routeId.slice(4), page, ext);
        } else {
            // 分类可能已被隐藏，仍允许通过 richLink 直达；未知 id 按关键词搜索
            info = await pagedSearch(CATEGORY_KEYWORD(routeId), page, ext);
        }
        if (info.res) result.list = applyCategoryStyle(collectFromTree(info.res, {}), routeId);
        if (info.hasMore) result.pagecount = page + 1;
        result.style = getListStyle();
        result.limit = result.total = result.list.length;
    } catch (e) {
        result.list = [];
        result.limit = result.total = 0;
    }
    return result;
}

async function detailContent(ids) {
    var rawId = firstId(ids);
    var playData = unpackPlayId(rawId);
    var vid = String(playData.vid || '') || extractVideoId(playData.url || rawId);
    if (!vid) return { list: [] };

    var out = {
        vod_id: packPlayId({ type: 'video', vid: vid }),
        vod_name: 'YouTube 视频',
        vod_pic: '',
        vod_year: '',
        vod_remarks: '',
        vod_content: '',
        vod_actor: '',
        vod_play_from: 'WvPlayer',
        vod_play_url: ''
    };

    // 章节列表（合集视频的分格进度条），无章节时退化为单集
    var chapters = [];
    var pr0 = null;
    try {
        pr0 = await innertube('player', { videoId: vid });
    } catch (e0) {}

    try {
        var pr = pr0 || await innertube('player', { videoId: vid });
        var vd = pr && pr.videoDetails;
        var micro = pr && pr.microformat && pr.microformat.playerMicroformatRenderer;
        if (vd) {
            out.vod_name = safeText(vd.title) || out.vod_name;
            out.vod_pic = bestThumb(vd.thumbnail && vd.thumbnail.thumbnails);
            out.vod_content = safeText(vd.shortDescription);
            // 作者：频道关联查询（InnerTube browse 已验证可用）
            var author = safeText(vd.author);
            out.vod_actor = vd.channelId ? richLink(author, 'channel:' + vd.channelId) : author;
        }
        if (micro) {
            if (!out.vod_pic) out.vod_pic = bestThumb(micro.thumbnail && micro.thumbnail.thumbnails);
            var pub = String(micro.publishDate || '');
            if (pub) out.vod_year = pub.slice(0, 4);
            var views = Number((vd && vd.viewCount) || micro.viewCount || 0);
            out.vod_remarks = views >= 10000 ? Math.round(views / 10000) + '万次观看'
                : (views ? views + '次观看' : '');
        }

        // 解析章节：优先 API playerOverlays，兜底 Description 正则提取
        chapters = collectChapters(pr, out.vod_content);

        // 标签：关键词搜索已验证可按标签返回作品
        var keywords = (vd && vd.keywords) || [];
        var tagLinks = [];
        for (var ki = 0; ki < Math.min(keywords.length, 8); ki++) {
            var kw2 = safeText(keywords[ki]);
            if (kw2) tagLinks.push(richLink(kw2, 'tag:' + kw2));
        }
        if (tagLinks.length) {
            out.vod_content += (out.vod_content ? '\n' : '') + '标签：' + tagLinks.join(' ');
        }
    } catch (e) {}

    // 剧集：有章节时逐节列出（每节带起始秒，播放时 seek），末尾附完整版；无章节时单集
    var playId = packPlayId({ type: 'video', vid: vid });
    var parts = [];
    for (var ci = 0; ci < chapters.length; ci++) {
        var ch = chapters[ci];
        var endMs = chapters[ci + 1] ? chapters[ci + 1].ms : 0;
        parts.push({
            name: cleanPlayName((ci + 1) + '. ' + ch.title, '第' + (ci + 1) + '节'),
            id: packPlayId({ type: 'video', vid: vid, t: Math.floor(ch.ms / 1000), te: endMs ? Math.floor(endMs / 1000) : 0 })
        });
    }
    if (parts.length > 1) {
        parts.push({ name: cleanPlayName('完整版', '完整版'), id: playId });
    } else {
        parts = [{ name: cleanPlayName(out.vod_name, '第1集'), id: playId }];
    }
    var urls = [];
    for (var pi = 0; pi < parts.length; pi++) urls.push(parts[pi].name + '$' + parts[pi].id);
    out.vod_play_url = urls.join('#');
    return { list: [out] };
}

async function recommendContent(ids, pg) {
    if (cfgRead().showRecommend === false) return { list: [] };
    var currentId = firstId(ids);
    var page = Math.max(1, parseInt(pg, 10) || 1);
    var data = unpackPlayId(currentId);
    var vid = data.vid || extractVideoId(data.url || currentId);
    if (!vid) return { list: [] };

    try {
        var info = await pagedToken('yt_rec_' + vid, '', page, function (cont) {
            return cont.continuation
                ? innertube('next', { continuation: cont.continuation })
                : innertube('next', { videoId: vid });
        });
        var list = info.res ? collectFromTree(info.res, {}) : [];
        // 过滤当前影片自身
        list = list.filter(function (item) {
            return unpackPlayId(item.vod_id).vid !== vid;
        });
        var result = { list: list };
        if (info.hasMore) {
            result.page = page;
            result.pagecount = page + 1;
        }
        return result;
    } catch (e) {
        return { list: [] };
    }
}

async function searchContent(key, quick, pg) {
    var page = parseInt(pg) || 1;
    var keyword = safeText(key || '');
    var result = { page: page, pagecount: page, limit: 0, total: 0, list: [] };
    if (!keyword) return result;

    try {
        var info = await pagedSearch(keyword, page, {});
        if (info.res) result.list = collectFromTree(info.res, {});
        if (info.hasMore) result.pagecount = page + 1;
        result.limit = result.total = result.list.length;
    } catch (e) {
        result.list = [];
        result.limit = result.total = 0;
    }
    return result;
}

/* ==================== 播放 ==================== */

/**
 * 直链受签名/限速约束无法稳定获取，
 * 使用 wvplayer 挂载官方嵌入播放器 /embed 页（已验证可播放）。
 * - 章节集：start/end 参数直接定位到该节区间
 * - 净化：隐藏顶栏、暂停推荐浮层、片尾推荐与左右控制条，仅保留设置齿轮 + 底部进度条
 * - 下移：设置齿轮 translateY(36px) 避开宿主右上角图标
 * - 声音：轮询 unMute() + video.muted 兜底，自动取消默认静音
 */
async function playerContent(flag, id, vipFlags) {
    var raw = firstId(id);
    var data = unpackPlayId(raw);
    var vid = data.vid || extractVideoId(data.url || raw);
    if (!vid) return {};

    // 基础参数沿用已验证可播放的组合；章节定位仅追加官方支持的 start/end 秒数参数
    var q = '?autoplay=1&playsinline=1&rel=0&modestbranding=1';
    var st = Math.floor(Number(data.t) || 0);
    var en = Math.floor(Number(data.te) || 0);
    if (st > 0) q += '&start=' + st;
    if (en > st) q += '&end=' + en;

    return {
        type: 'wvplayer',
        url: siteUrl.replace('//m.', '//www.') + '/embed/' + vid + q,
        headers: {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
            'Referer': 'https://m.youtube.com/'
        },
        playerSelector: 'body',
        selectors: ['#movie_player video', 'video'],
        /* Wv2 不读取 style 字段，改为在页面脚本中动态注入 CSS。 */
        /* 起播兜底：桌面分支点 ytp 播放按钮，delhi 分支仅在未播放时点播放图标或直接 video.play() */
        click: "(function(){var n=0;var t=setInterval(function(){"
            + "var v=document.querySelector('video');"
            + "if(v&&v.videoWidth>0&&v.readyState>=2&&!v.paused){clearInterval(t);return;}"
            + "var b=document.querySelector('.ytp-large-play-button,#movie_player .ytp-play-button');"
            + "if(b)b.click();"
            + "else{var p=document.querySelector('button.player-control-play-pause-icon');if(p&&(!v||v.paused))p.click();}"
            + "if(v&&v.paused)v.play();"
            + "if(++n>=10)clearInterval(t);},1500);})();",
        /* 自动取消静音 + 起播合并轮询：unMute API 优先，video.muted 兜底，
           delhi 分支仅在标签为「取消静音」时点击音量按钮避免误静音 */
        script: "(function(){"
            + "var css='body,html{overflow:hidden!important;background:#000!important;margin:0!important;padding:0!important}"
            + "creator-endscreen,ytw-player-seek-overlay,player-user-edu-tooltip,yt-bigboard{display:none!important}"
            + "player-fullscreen-action-menu,player-fullscreen-top-controls,.fullscreen-controls{display:none!important}"
            + "embedded-player-video-details,volume-controls,yt-closed-captions-toggle-button{display:none!important}"
            + "[aria-label=\"静音\"],[aria-label=\"取消静音\"],[title=\"静音\"],[title=\"取消静音\"]{display:none!important}"
            + "player-middle-controls{display:none!important}"
            + "player-time-display,.ytwPlayerBottomControlsFullscreenButtonWrapper{display:none!important}"
            + "button.player-settings-icon{transform:translateY(36px)!important;z-index:2147483647!important}"
            + "yt-progress-bar,.watch-page-progress-bar,.ytPlayerProgressBarHost,[aria-label=\"进度滑块\"]{display:none!important;visibility:hidden!important}"
            + ".ytp-chrome-top,.ytp-pause-overlay,.ytp-ce-element,.ytp-cards-button,"
            + ".ytp-paid-content-overlay,.ytp-gradient-top,.ytp-left-controls,.ytp-subtitles-button,"
            + ".ytp-miniplayer-button,.ytp-size-button,.ytp-youtube-button{display:none!important}"
            + ".ytp-settings-button{transform:translateY(36px)!important;z-index:2147483647!important}';"
            + "var old=document.getElementById('ys-youtube-wv-style');"
            + "if(old)old.remove();"
            + "var st=document.createElement('style');st.id='ys-youtube-wv-style';st.textContent=css;"
            + "(document.head||document.documentElement).appendChild(st);"
            + "function hideExtraControls(){"
            + "var fixed=['volume-controls','.ytdVolumeControlsHost','.ytdVolumeControlsMuteIconButtonContainer','yt-progress-bar','.watch-page-progress-bar','.ytPlayerProgressBarHost','[aria-label=\"进度滑块\"]','[aria-label=\"静音\"]','[aria-label=\"取消静音\"]','[title=\"静音\"]','[title=\"取消静音\"]'];"
            + "for(var i=0;i<fixed.length;i++){var xs=document.querySelectorAll(fixed[i]);for(var j=0;j<xs.length;j++)xs[j].style.setProperty('display','none','important');}"
            + "var bs=document.querySelectorAll('button,[role=\"button\"]');"
            + "for(var k=0;k<bs.length;k++){var b=bs[k];var label=((b.getAttribute('aria-label')||'')+' '+(b.getAttribute('title')||'')+' '+(b.textContent||'')).replace(/\\s+/g,' ').trim();"
            + "if(label.length<=48&&/(?:^|\\s)(?:AI|AI生成|人工智能|生成内容|由AI生成)(?:$|\\s)/i.test(label)&&!/(设置|settings)/i.test(label))b.style.setProperty('display','none','important');}"
            + "var ts=document.querySelectorAll('span,div,p');for(var ti=0;ti<ts.length;ti++){var tv=(ts[ti].textContent||'').replace(/\\s+/g,' ').trim();if(tv.length<=32&&/(AI生成|AI\\s*生成|人工智能|生成内容|由AI生成)/i.test(tv)){var parent=ts[ti].closest?ts[ti].closest('button,[role=\"button\"]'):null;(parent||ts[ti]).style.setProperty('display','none','important');}}"
            + "}"
            + "hideExtraControls();"
            + "window.__ysHideYoutubeExtraControls=hideExtraControls;"
            + "})();"
            + "(function(){var n=0;var t=setInterval(function(){"
            + "if(window.__ysHideYoutubeExtraControls)window.__ysHideYoutubeExtraControls();"
            + "var xs=document.querySelectorAll('volume-controls,yt-progress-bar,.watch-page-progress-bar,.ytPlayerProgressBarHost,[aria-label=\"进度滑块\"],[aria-label=\"静音\"],[aria-label=\"取消静音\"]');for(var xi=0;xi<xs.length;xi++)xs[xi].style.setProperty('display','none','important');"
            + "var bs=document.querySelectorAll('button,[role=\"button\"]');for(var bi=0;bi<bs.length;bi++){var bl=((bs[bi].getAttribute('aria-label')||'')+' '+(bs[bi].getAttribute('title')||'')+' '+(bs[bi].textContent||'')).replace(/\\s+/g,' ').trim();if(bl.length<=48&&/(?:^|\\s)(?:AI|AI生成|人工智能|生成内容|由AI生成)(?:$|\\s)/i.test(bl)&&!/(设置|settings)/i.test(bl))bs[bi].style.setProperty('display','none','important');}"
            + "var mp=document.querySelector('#movie_player');"
            + "var v=document.querySelector('#movie_player video')||document.querySelector('video');"
            + "if(mp&&mp.isMuted&&mp.isMuted()&&mp.unMute){mp.unMute();if(mp.setVolume)mp.setVolume(100);}"
            + "if(v&&v.muted){var mb=document.querySelector('.ytp-unmute,button[aria-label=\"取消静音\"]');if(mb)mb.click();v.muted=false;if(v.volume===0)v.volume=1;}"
            + "if(v&&v.videoWidth>0&&v.readyState>=2&&v.paused){if(mp&&mp.playVideo)mp.playVideo();else v.play();}"
            + "if(v&&!v.paused&&!v.muted){clearInterval(t);return;}"
            + "if(++n>=30)clearInterval(t);},1000);})();",
        timeout: 60
    };
}
