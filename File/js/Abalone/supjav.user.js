// ==UserScript==
// @name         Supjav
// @namespace    gmspider
// @version      2025.08.24
// @description  Supjav GMSpider (重构版: 通用选择器 + cf_clearance 兼容)
// @author       Luomo (refactored by Minis)
// @match        https://supjav.com/*
// @require      https://cdn.jsdelivr.net/npm/jquery@3.7.1/dist/jquery.slim.min.js
// @grant        GM_cookie
// @grant        unsafeWindow
// ==/UserScript==
console.log(JSON.stringify(GM_info));
(function () {
    const GMSpiderArgs = {};
    if (typeof GmSpiderInject !== 'undefined') {
        let args = JSON.parse(GmSpiderInject.GetSpiderArgs());
        GMSpiderArgs.fName = args.shift();
        GMSpiderArgs.fArgs = args;
    } else {
        GMSpiderArgs.fName = "homeContent";
        GMSpiderArgs.fArgs = ["tag"];
    }
    Object.freeze(GMSpiderArgs);

    // ---------------- cf_clearance 处理 ----------------
    let cf_clearance = null;

    function initCfClearance() {
        if (cf_clearance) return;
        try {
            GM_cookie.list({name: "cf_clearance"}, function (cookies, error) {
                if (!error && cookies?.length > 0) {
                    cf_clearance = cookies[0].value;
                    localStorage.setItem("cf_clearance", cf_clearance);
                } else {
                    const cached = localStorage.getItem("cf_clearance");
                    if (cached) cf_clearance = cached;
                }
            });
        } catch (e) {
            const cached = localStorage.getItem("cf_clearance");
            if (cached) cf_clearance = cached;
        }
    }

    function formatImgUrl(url) {
        initCfClearance();
        if (!url) return "";
        if (cf_clearance) {
            return url + "@User-Agent=" + encodeURIComponent(navigator.userAgent) +
                "@Cookie=cf_clearance=" + encodeURIComponent(cf_clearance);
        }
        return url;
    }

    // ---------------- 通用列表解析 ----------------
    function parseItems($boxes) {
        const list = [];
        $boxes.each(function () {
            const $box = $(this);
            const $a = $box.find(".img, a").first();
            const href = $a.attr("href");
            if (!href) return;
            const url = new URL(href, location.origin);
            const slug = url.pathname.split('/').filter(Boolean).pop();
            const title = $a.attr("title") || $box.find(".title, h3, h4").first().text().trim();
            const pic = formatImgUrl($box.find("img").data("original") || $box.find("img").attr("src"));
            const remarks = $box.find(".date, .time").first().text().trim();
            const year = $box.find(".meta").children().remove().end().text().trim() ||
                $box.find(".year, .duration").first().text().trim();
            if (title && slug) {
                list.push({vod_id: slug, vod_name: title, vod_pic: pic, vod_remarks: remarks, vod_year: year});
            }
        });
        return list;
    }

    function getPageCount() {
        const txt = $(".pagination li").not(".next-page").last().text().trim();
        const n = parseInt(txt.replace(/[^0-9]/g, ''));
        return isNaN(n) ? 1 : n;
    }

    // ---------------- Spider ----------------
    const GmSpider = {
        homeContent: function (filter) {
            const defaultFilter = [{
                key: "sort", name: "排序", value: [
                    {n: "观看数", v: "views"},
                    {n: "更新时间", v: ""}
                ]
            }];
            const result = {
                class: [
                    {type_id: "popular", type_name: "热门"},
                    {type_id: "category/censored-jav", type_name: "有码"},
                    {type_id: "category/uncensored-jav", type_name: "无码"},
                    {type_id: "category/amateur", type_name: "素人"},
                    {type_id: "category/chinese-subtitles", type_name: "中文字幕"},
                    {type_id: "category/reducing-mosaic", type_name: "无码破解"},
                    {type_id: "category/english-subtitles", type_name: "英文字幕"},
                    {type_id: "tag", type_name: "类别"},
                ],
                filters: {popular: [{key: "sort", name: "时间", value: [
                    {n: "本月热门", v: "month"},
                    {n: "本周热门", v: "week"},
                    {n: "今日热门", v: ""}
                ]}]},
                list: []
            };
            result.class.forEach(item => {
                if (!result.filters[item.type_id]) result.filters[item.type_id] = defaultFilter;
            });
            result.list = parseItems($(".post, .video-item, .card-video, .thumbnail"));
            return result;
        },

        categoryContent: function (tid, pg, filter, extend) {
            const result = {list: [], pagecount: 1};

            if (tid === "tag") {
                // 标签目录
                $(".categorys .child, .tag-item, .category-item").each(function () {
                    const $a = $(this).find("a").first();
                    const href = $a.attr("href");
                    if (!href) return;
                    const url = new URL(href, location.origin);
                    const parts = url.pathname.split('/').filter(Boolean);
                    if (parts.length < 3) return;
                    const text = $(this).text().trim().split("(");
                    result.list.push({
                        vod_id: parts[1] + "/" + parts[2],
                        vod_name: text[0],
                        vod_remarks: (text[1] || "").replace(")", "").trim() + " 部影片",
                        vod_tag: "folder",
                        style: {type: "rect", ratio: 1}
                    });
                });
                result.pagecount = getPageCount();
            } else {
                // 视频列表
                result.list = parseItems($(".post, .video-item, .card-video, .thumbnail"));
                result.pagecount = getPageCount();
            }
            return result;
        },

        detailContent: function (ids) {
            const slug = ids[0];

            // 尝试点击播放服务器按钮
            try {
                $("#vserver, .video-server, .server-list").click();
            } catch (e) {}

            const vodActor = [], tags = [];
            // 女优/分类
            $(".post-meta .cats a, .meta .cats a, .actress a").each(function () {
                const $a = $(this);
                const href = $a.attr("href");
                if (!href) return;
                const id = new URL(href, location.origin).pathname.replace("/zh/", "");
                const name = $a.text().trim();
                vodActor.unshift(`[a=cr:{"id":"${id}","name":"${name}"}/]${name}[/a]`);
            });
            // 标签
            $(".post-meta .tags a, .meta .tags a, .tag a").each(function () {
                const $a = $(this);
                const href = $a.attr("href");
                if (!href) return;
                const id = new URL(href, location.origin).pathname.replace("/zh/", "");
                const name = $a.text().trim();
                tags.push(`[a=cr:{"id":"${id}","name":"${name}"}/]#${name}[/a]`);
            });

            // 视频标题清洗
            let vodContent = $(".post-meta .img, .video-info img, .poster").attr("alt") || "";
            let vodName = vodContent.replace("[无码破解]", "").trim();
            let match = vodName.match(/^[\w|-]+/);
            if (match) {
                vodName = match[0].includes("-") ? match[0] : vodContent.match(/^[\w]+\s[\w]+/)?.[0]?.replace(" ", "-") || vodName;
            }

            // 播放源
            const vodPlayData = [];
            const btnServers = $(".video-wrap .cd-server:first .btn-server, .video-wrap .btn-server, .server-btn").length > 0
                ? $(".video-wrap .cd-server:first .btn-server, .video-wrap .btn-server, .server-btn")
                : $(".btn-server");
            btnServers.each(function (i) {
                const from = $(this).text().trim() || `线路${i + 1}`;
                vodPlayData.push({
                    from: from,
                    media: [{
                        name: vodName,
                        type: "webview",
                        ext: {replace: {pathname: slug, link: i}}
                    }]
                });
            });

            return {
                list: [{
                    vod_id: slug,
                    vod_name: vodName,
                    vod_pic: formatImgUrl($(".post-meta .img, .video-info img, .poster").attr("src")),
                    vod_actor: vodActor.join(" "),
                    vod_remarks: tags.join(" "),
                    vod_content: vodContent,
                    vod_play_data: vodPlayData
                }]
            };
        },

        playerContent: function (flag, id, vipFlags) {
            const link = window.location.hash.split("#").at(1);
            const btns = document.querySelectorAll(".video-wrap .btn-server, .server-btn");
            if (btns[link]) btns[link].dispatchEvent(new Event("click"));
            return {type: "match"};
        },

        searchContent: function (key, quick, pg) {
            const result = {list: [], pagecount: 1};
            // 搜索页结构同列表
            result.list = parseItems($(".post, .video-item, .card-video, .thumbnail"));
            result.pagecount = getPageCount();
            return result;
        }
    };

    $(document).ready(function () {
        if ($(".loading-verifying").length > 0) {
            if (typeof GmSpiderInject !== 'undefined') GmSpiderInject.ShowWebview();
        }
    });
    $(unsafeWindow).on("load", function () {
        const result = GmSpider[GMSpiderArgs.fName](...GMSpiderArgs.fArgs);
        console.log(result);
        if (typeof GmSpiderInject !== 'undefined') {
            if (typeof GmSpiderInject.HideWebview === 'function') GmSpiderInject.HideWebview();
            GmSpiderInject.SetSpiderResult(JSON.stringify(result));
        }
    });
})();