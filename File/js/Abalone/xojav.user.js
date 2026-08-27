// ==UserScript==
// @name         XOJAV
// @namespace    gmspider
// @version      2025.08.24
// @description  XOJAV GMSpider (重构版: 通用选择器 + 首页专用解析)
// @author       Luomo (refactored by Minis)
// @match        https://xojav.tv/*
// @require      https://cdn.jsdelivr.net/npm/jquery@3.7.1/dist/jquery.slim.min.js
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
        GMSpiderArgs.fArgs = [true];
    }
    Object.freeze(GMSpiderArgs);

    // ---------------- 通用列表解析 ----------------
    function parseItems($boxes) {
        const list = [];
        $boxes.each(function () {
            const $box = $(this);
            const $a = $box.find(".card-video__title a, .card-video__img a, a").first();
            const href = $a.attr("href");
            if (!href) return;
            const url = new URL(href, location.origin);
            const slug = url.pathname.split('/').filter(Boolean).pop()?.toUpperCase();
            const title = $box.find(".card-video__img img").attr("alt") ||
                $box.find(".card-video__title").text().trim() ||
                $box.find("img").attr("alt") || "";
            const pic = $box.find(".card-video__img img").data("src") ||
                $box.find("img").data("src") || $box.find("img").attr("src") || "";
            const remarks = [
                "👁️" + $box.find(".card-video__stats .num:first, .views, .view-count").first().text().trim(),
                "❤️" + $box.find(".card-video__fav-button .num, .fav-count, .like-count").first().text().trim()
            ].filter(Boolean).join(" ");
            const year = $box.find(".card-video__duration, .duration, .time").first().text().trim();
            if (title && slug) {
                list.push({vod_id: slug, vod_name: title, vod_pic: pic, vod_remarks: remarks, vod_year: year});
            }
        });
        return list;
    }

    function getPageCount() {
        const txt = $('.pagination__list li[class] .pagination__item:last, .pagination .page-item:last, .pagination li:last').text().trim();
        const n = parseInt(txt.replace(/[^0-9]/g, ''));
        return isNaN(n) ? 1 : n;
    }

    // ---------------- 首页专用解析 ----------------
    function parseHome() {
        const list = [];
        // 首页卡片
        parseItems($(".card-video, .video-card, .thumbnail")).forEach(v => list.push(v));
        // 去重
        const seen = new Set();
        return list.filter(v => seen.has(v.vod_id) ? false : seen.add(v.vod_id));
    }

    // ---------------- Spider ----------------
    const GmSpider = {
        homeContent: function (filter) {
            const result = {
                class: [
                    {type_id: "latest-updates?sort_by=release_at", type_name: "最近更新"},
                    {type_id: "categories/taiwan-av?sort_by=release_at", type_name: "台湾AV"},
                    {type_id: "stars?sort_by=stars", type_name: "近期最佳"},
                    {type_id: "hot?sort_by=views", type_name: "热门"},
                    {type_id: "categories?", type_name: "所有分类"},
                ],
                filters: {
                    "categories/taiwan-av?sort_by=release_at": [{
                        key: "sort_by", name: "排序", value: [
                            {n: "近期最佳", v: "&sort_by=stars"},
                            {n: "观看数", v: "&sort_by=views"},
                            {n: "最近更新", v: "&sort_by=release_at"}
                        ]
                    }],
                    "categories?": [{
                        key: "sort_by", name: "排序", value: [
                            {n: "近期最佳", v: "&sort_by=stars"},
                            {n: "观看数", v: "&sort_by=views"},
                            {n: "最近更新", v: "&sort_by=release_at"}
                        ]
                    }]
                },
                list: parseHome()
            };
            return result;
        },

        categoryContent: function (tid, pg, filter, extend) {
            const result = {list: [], pagecount: 1};

            if (tid === "categories?") {
                // 分类目录
                $(".padding-bottom-xl, .category-section, .cat-list").each(function () {
                    const remarks = $(this).find(".title--listing, .section-title, h3, h4").first().text().trim();
                    $(this).find(".card-cat-v2, .cat-item, .category-card").each(function () {
                        const $a = $(this).find(".card-cat-v2__link, a").first();
                        const href = $a.attr("href");
                        if (!href) return;
                        const url = new URL(href, location.origin);
                        const parts = url.pathname.split('/').filter(Boolean);
                        if (parts.length < 3) return;
                        result.list.push({
                            vod_id: parts[1] + "/" + parts[2] + "?sort_by=release_at",
                            vod_name: $(this).find(".card-cat-v2__title h4, .title, .name, h4").first().text().trim(),
                            vod_pic: $(this).find("img").attr("src") || $(this).find("img").data("src") || "",
                            vod_remarks: remarks,
                            vod_tag: "folder",
                            style: {type: "rect", ratio: 0.7}
                        });
                    });
                });
                result.pagecount = 1;
            } else {
                // 视频列表
                result.list = parseItems($(".card-video, .video-card, .thumbnail"));
                result.pagecount = getPageCount();
            }
            return result;
        },

        detailContent: function (ids) {
            const slug = ids[0];
            const categories = [], tags = [];

            $(".content-details__meta a, .meta a, .tags a, .categories a").each(function () {
                const $a = $(this);
                const href = $a.attr("href");
                if (!href) return;
                const url = new URL(href, location.origin);
                const parts = url.pathname.split('/').filter(Boolean);
                if (parts.length < 3) return;
                const id = parts[1] + "/" + parts[2] + "?sort_by=release_at";
                const name = $a.text().trim();
                if (!name) return;
                if (parts[1] === "categories") {
                    categories.push(`[a=cr:{"id":"${id}","name":"${name}"}/]${name}[/a]`);
                } else {
                    tags.push(`[a=cr:{"id":"${id}","name":"${name}"}/]${name}[/a]`);
                }
            });

            const vod = {
                vod_id: slug,
                vod_name: slug.toUpperCase(),
                vod_year: $(".content-details__meta time, .meta time, .release-date, .date").first().text().trim(),
                vod_remarks: categories.join(" "),
                vod_actor: tags.join(" "),
                vod_content: $(".content-details__title, .title, h1").first().text().trim(),
                vod_play_from: "XOJAV",
                vod_play_url: (typeof unsafeWindow !== "undefined" && unsafeWindow.stream)
                    ? "720P$" + unsafeWindow.stream
                    : ""
            };
            return {list: [vod]};
        },

        searchContent: function (key, quick, pg) {
            const result = {list: [], pagecount: 1};
            const $boxes = $(".card-video, .video-card, .thumbnail");
            result.list = parseItems($boxes);
            const totalTxt = $('.title--sub-title, .search-result-count, .total-count').text().replace(/[^0-9]/g, "");
            const total = parseInt(totalTxt) || 0;
            result.pagecount = Math.ceil(total / 24) || 1;
            return result;
        }
    };

    $(document).ready(function () {
        if ($("#cf-wrapper").length > 0) {
            console.log("源站不可用:" + $('title').text());
            if (typeof GM_toastLong === "function") GM_toastLong("源站不可用:" + $('title').text());
        } else {
            const result = GmSpider[GMSpiderArgs.fName](...GMSpiderArgs.fArgs);
            if (typeof GmSpiderInject !== 'undefined') {
                GmSpiderInject.SetSpiderResult(JSON.stringify(result));
            }
        }
    });
})();