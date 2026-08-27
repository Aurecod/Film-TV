// ==UserScript==
// @name         123av
// @namespace    gmspider
// @version      2025.08.25
// @description  123av GMSpider - 原版框架 + 新版站点结构适配
// @author       Luomo (adapted by Minis)
// @match        https://*.123av.com/*
// @match        https://123av.com/*
// @require      https://cdn.jsdelivr.net/npm/jquery@3.7.1/dist/jquery.slim.min.js
// @grant        unsafeWindow
// @grant        GM_log
// @grant        GM_toastLong
// ==/UserScript==

(function () {
    const GMSpiderArgs = {};
    if (typeof GmSpiderInject !== 'undefined') {
        let args = JSON.parse(GmSpiderInject.GetSpiderArgs());
        GMSpiderArgs.fName = args.shift();
        GMSpiderArgs.fArgs = args;
    } else {
        GMSpiderArgs.fName = "homeContent";
        GMSpiderArgs.fArgs = [];
    }
    Object.freeze(GMSpiderArgs);

    const GmSpider = (function () {
        const filter = {
            key: "filter", name: "过滤",
            value: [{n: "全部", v: ""}, {n: "单个女演员", v: "&filter=single_actress"}]
        };
        const filterWithoutSort = [filter];
        const defaultFilter = [filter, {
            key: "sort", name: "排序方式",
            value: [
                {n: "最近更新", v: "&sort=recent_update"},
                {n: "发布时间", v: "&sort=release_date"},
                {n: "动态", v: "&sort=trending"},
                {n: "今日最好", v: "&sort=most_viewed_today"},
                {n: "本周最好", v: "&sort=most_viewed_week"},
                {n: "本月最好", v: "&sort=most_viewed_month"},
                {n: "观看次数最多", v: "&sort=most_viewed"},
                {n: "最喜欢", v: "&sort=most_favourited"}
            ]
        }];

        // ---------- 新版站点解析 ----------

        // 视频卡片（列表页 .grid > div.card / 首页 .featured）
        function pageList() {
            let itemList = [];
            $(".grid > div.card, .featured-swiper .featured, .rec__section > div").each(function () {
                const $card = $(this);
                const href = $card.find('a[href*="/v/"]').attr("href");
                if (!href) return;
                const code = (href.match(/\/v\/([a-zA-Z0-9_-]+)/i) || [])[1];
                if (!code) return;
                let name = $card.find(".card__link").text().trim();
                if (!name) name = $card.find(".featured__title").text().trim();
                if (!name) name = $card.find("h3").first().text().trim();
                if (!name) return;
                let pic = $card.find("img").attr("src") || $card.find("img").data("src") || "";
                if (pic.startsWith("/")) pic = "https://123av.com" + pic;
                itemList.push({
                    vod_id: code.toLowerCase(),
                    vod_name: name,
                    vod_pic: pic,
                    vod_year: $card.find("[class*='dur']").first().text().trim()
                });
            });
            return itemList;
        }

        // 目录页 (.ggrid a)：类别/女演员/制作商/系列/标签
        function gridFolders() {
            let list = [];
            $(".ggrid a[href]").each(function () {
                const href = $(this).attr("href");
                const parts = href.split("/").filter(Boolean);   // ["en","genres","solowork"]
                if (parts.length < 3) return;
                list.push({
                    vod_id: parts.slice(1).join("/"),            // "genres/solowork"
                    vod_name: $(this).text().replace(/\s+/g, " ").trim(),
                    vod_tag: "folder",
                    style: {type: "rect", ratio: 1}
                });
            });
            return list;
        }

        // 抽屉导航里的子项兜底
        function drawerFolders(type) {
            let list = [];
            $(".drawer__nav a, .drawer.is-open a").each(function () {
                const href = $(this).attr("href");
                if (!href || href.indexOf("/" + type + "/") < 0) return;
                const parts = href.split("/").filter(Boolean);
                if (parts.length < 3) return;
                list.push({
                    vod_id: parts.slice(1).join("/"),
                    vod_name: $(this).text().replace(/\s+/g, " ").trim(),
                    vod_tag: "folder",
                    style: {type: "rect", ratio: 2}
                });
            });
            return list;
        }

        function pageCount() {
            // pager 里的最大页码
            let max = 0;
            $(".pager a[href*='page='], .pager option").each(function () {
                const t = this.tagName === "OPTION" ? $(this).text() : $(this).attr("href");
                const m = String(t).match(/page=(\d+)/) || String(t).match(/^(\d+)$/);
                if (m) max = Math.max(max, parseInt(m[1]));
            });
            // 兜底：总数/24
            if (!max) {
                const t = $(".pagehead__count").text().replace(/,/g, "").match(/(\d+)/);
                if (t) max = Math.ceil(parseInt(t[1]) / 24);
            }
            return max || 1;
        }

        return {
            homeContent: function () {
                let result = {
                    class: [
                        {type_id: "new", type_name: "新发布"},
                        {type_id: "hot", type_name: "热门"},
                        {type_id: "recent", type_name: "最近"},
                        {type_id: "censored", type_name: "有码"},
                        {type_id: "uncensored", type_name: "无码"},
                        {type_id: "uncensored-leaked", type_name: "无码泄露"},
                        {type_id: "genres", type_name: "类别"},
                        {type_id: "actresses", type_name: "女演员"},
                        {type_id: "makers", type_name: "制作商"},
                        {type_id: "series", type_name: "系列"},
                        {type_id: "tags", type_name: "标签"}
                    ],
                    filters: {
                        "new": filterWithoutSort,
                        "hot": defaultFilter,
                        "recent": filterWithoutSort,
                        "censored": defaultFilter,
                        "uncensored": defaultFilter,
                        "uncensored-leaked": defaultFilter,
                        "genres": defaultFilter,
                        "actresses": defaultFilter,
                        "makers": defaultFilter,
                        "series": defaultFilter,
                        "tags": defaultFilter
                    },
                    list: []
                };
                const itemList = pageList();
                result.list = itemList.filter((item, index) => {
                    return itemList.findIndex(i => i.vod_id === item.vod_id) === index;
                });
                return result;
            },

            categoryContent: function (tid, pg, filter, extend) {
                let result = {list: [], page: pg, pagecount: 0};

                // 1. 视频列表页（new/hot/recent/有码/无码/无码泄露 + 二级目录的视频列表）
                const videos = pageList();
                if (videos.length > 0) {
                    result.list = videos.filter((item, index) => {
                        return videos.findIndex(i => i.vod_id === item.vod_id) === index;
                    });
                    result.pagecount = pageCount();
                    return result;
                }

                // 2. 目录页 (.ggrid)：类别/女演员/制作商/系列/标签
                const folders = gridFolders();
                if (folders.length > 0) {
                    result.list = folders;
                    result.pagecount = 1;
                    return result;
                }

                // 3. 抽屉兜底
                const type = String(tid).split("/")[0];
                result.list = drawerFolders(type);
                result.pagecount = 1;
                return result;
            },

            detailContent: function (ids) {
                const slug = ids[0];
                let detail = {};
                $(".watch__block li, .meta-item").each(function () {
                    const txt = $(this).text().replace(/\s+/g, " ").trim();
                    const idx = txt.indexOf(":");
                    if (idx < 1) return;
                    const key = txt.substring(0, idx).trim();
                    const val = txt.substring(idx + 1).trim();
                    const links = [];
                    $(this).find("a").each(function () {
                        links.push('[a=cr:{"id":"' + $(this).attr("href") + '","name":"' + $(this).text().trim() + '"}/]' + $(this).text().trim() + "[/a]");
                    });
                    detail[key] = links.length > 0 ? links : val;
                });

                let name = $(".watch__headinfo h1").first().text().trim();
                if (!name) name = $("h1").first().text().trim();
                if (!name) name = slug.toUpperCase();

                const vod = {
                    vod_id: slug,
                    vod_name: name,
                    vod_pic: $('meta[property="og:image"]').attr("content") || "",
                    vod_year: formatDetail(detail, "Release date", "发布日期"),
                    vod_remarks: formatDetail(detail, "Genres", "类型"),
                    vod_director: formatDetail(detail, "Maker", "制作者"),
                    vod_actor: formatDetail(detail, "Cast", "演员"),
                    vod_content: name,
                    // ★ 原版播放机制：webview 类型 + ext.replace 驱动 loadUrl 模板替换
                    vod_play_data: [{
                        from: "123AV",
                        media: [{
                            name: "720P",
                            type: "webview",
                            ext: {
                                replace: {vod_id: slug}
                            }
                        }]
                    }]
                };
                return {list: [vod]};
            },

            playerContent: function (flag, id, vipFlags) {
                // WebView 已加载详情页(playerContent.loadUrl + ext.replace.vod_id)
                // 返回 match → GM.jar 按 ext.playUrlMatch 嗅探 iframe 里的 v.m3u8 请求
                return {
                    type: "match"
                };
            },

            searchContent: function (key, quick, pg) {
                const result = {list: [], page: pg, pagecount: 0};
                const itemList = pageList();
                result.list = itemList.filter((item, index) => {
                    return itemList.findIndex(i => i.vod_id === item.vod_id) === index;
                });
                result.pagecount = pageCount();
                return result;
            }
        };

        function formatDetail(detail, ...keys) {
            let format = "";
            for (let key of keys) {
                format += key in detail ? (Array.isArray(detail[key]) ? detail[key].join(" ") : detail[key]) : "";
            }
            return format;
        }
    })();

    $(document).ready(function () {
        let result = "";
        if ($("#cf-wrapper").length > 0) {
            if (typeof GM_toastLong !== "undefined") GM_toastLong("源站不可用:" + $("title").text());
        } else if ($("#body .btn-primary").text() === "Click here to continue") {
            window.location = $("#body .btn-primary").attr("href");
        } else {
            result = GmSpider[GMSpiderArgs.fName](...GMSpiderArgs.fArgs);
        }
        if (typeof GmSpiderInject !== "undefined") {
            GmSpiderInject.SetSpiderResult(JSON.stringify(result));
        }
    });
})();
