// ==UserScript==
// @name         MissAV
// @namespace    gmspider
// @version      2025.08.24
// @description  MissAV GMSpider (重构版: 选择器通用化, 直接解析当前页)
// @author       Luomo (refactored by Minis)
// @match        https://missav.*/*
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

    // ---------------- 工具 ----------------
    function getCategoryFromUrl(url) {
        return url.split('/cn/').at(1) || url.split('/').filter(Boolean).pop();
    }

    function parseItems($boxes) {
        const list = [];
        $boxes.each(function () {
            const $box = $(this);
            const $a = $box.find("a").first();
            const href = $a.attr("href");
            if (!href) return;
            const slug = getCategoryFromUrl(href);
            const title = $box.find(".text-secondary, .title, h3, h4").first().text().trim() ||
                $box.find("img").attr("alt") || "";
            const pic = $box.find("img").data("src") || $box.find("img").attr("src") || "";
            const year = $box.find(".absolute, .duration, .year, .right-1, .left-1").first().text().trim();
            const remarks = $box.find(".left-1, .badge, .tag").first().text().trim();
            if (title) {
                list.push({vod_id: slug, vod_name: title, vod_pic: pic, vod_year: year, vod_remarks: remarks});
            }
        });
        return list;
    }

    function getPageCount() {
        const txt = $("#price-currency, .pagination .page-item:last, .pagination li:last").text().trim();
        const n = parseInt(txt.replace(/[^0-9]/g, ''));
        return isNaN(n) ? 1 : n;
    }

    // ---------------- Spider ----------------
    const GmSpider = {
        homeContent: function (filter) {
            const defaultFilter = [
                {
                    key: "filter", name: "过滤", value: [
                        {n: "所有", v: ""},
                        {n: "单人作品", v: "&filters=individual"},
                        {n: "多人作品", v: "&filters=multiple"},
                        {n: "中文字幕", v: "&filters=chinese-subtitle"}
                    ]
                },
                {
                    key: "sort", name: "排序方式", value: [
                        {n: "发行日期", v: "&sort=released_at"},
                        {n: "最近更新", v: "&sort=published_at"},
                        {n: "收藏数", v: "&sort=saved"},
                        {n: "今日浏览数", v: "&sort=today_views"},
                        {n: "本周浏览数", v: "&sort=weekly_views"},
                        {n: "本月浏览数", v: "&sort=monthly_views"},
                        {n: "总浏览数", v: "&sort=views"}
                    ]
                }
            ];
            const result = {
                class: [
                    {type_id: "new", type_name: "所有影片"},
                    {type_id: "madou", type_name: "麻豆传媒"},
                    {type_id: "chinese-subtitle", type_name: "中文字幕"},
                    {type_id: "uncensored-leak", type_name: "无码流出"},
                    {type_id: "actresses/ranking", type_name: "热门女优"},
                    {type_id: "makers", type_name: "发行商"},
                    {type_id: "genres", type_name: "类型"},
                ],
                filters: {
                    "new": defaultFilter,
                    "madou": defaultFilter,
                    "chinese-subtitle": defaultFilter,
                    "uncensored-leak": defaultFilter,
                    "actresses/ranking": defaultFilter,
                    "makers": defaultFilter,
                    "genres": defaultFilter
                },
                list: []
            };
            // 首页推荐区
            const $boxes = $(".gap-5 .thumbnail, .video-item, .card-video, .thumbnail-item");
            result.list = parseItems($boxes);
            return result;
        },

        categoryContent: function (tid, pg, filter, extend) {
            const result = {list: [], pagecount: 1};

            if (tid === "actresses/ranking") {
                // 女优排行榜
                $(".gap-4 .space-y-4, .actress-item, .actress-card").each(function () {
                    const $a = $(this).find("a").first();
                    const href = $a.attr("href");
                    if (!href) return;
                    result.list.push({
                        vod_id: getCategoryFromUrl(href),
                        vod_name: $(this).find(".truncate, .name, .title").first().text().trim(),
                        vod_pic: $(this).find("img").attr("src") || $(this).find("img").data("src") || "",
                        vod_remarks: $(this).find(".text-sm, .count, .badge").first().text().trim(),
                        vod_tag: "folder",
                        style: {type: "rect", ratio: 1}
                    });
                });
                result.pagecount = 1;
            } else if (tid === "makers" || tid === "genres") {
                // 发行商/类型目录
                const categoryList = (title) => {
                    if (title) {
                        $(`nav .relative a.group span:contains('${title}')`).parents(".relative:first").find(".py-1 a").each(function () {
                            result.list.push({
                                vod_id: getCategoryFromUrl($(this).attr("href")),
                                vod_name: $(this).text().trim(),
                                vod_remarks: title,
                                vod_tag: "folder",
                                style: {type: "rect", ratio: 2}
                            });
                        });
                    }
                };
                if (pg == 1) {
                    categoryList("国产 AV");
                    categoryList("无码影片");
                    categoryList("素人");
                }
                // 兜底：页面上的分类卡片
                if (result.list.length === 0) {
                    $(".gap-4 div, .genre-item, .category-item").each(function () {
                        const $a = $(this).find("a").first();
                        const href = $a.attr("href");
                        if (!href) return;
                        result.list.push({
                            vod_id: getCategoryFromUrl(href),
                            vod_name: $(this).find(".text-nord13, .title, .name").first().text().trim(),
                            vod_remarks: $(this).find(".text-nord10 a, .count").first().text().trim(),
                            vod_tag: "folder",
                            style: {type: "rect", ratio: 2}
                        });
                    });
                }
                result.pagecount = 1;
            } else {
                // 普通视频列表
                const $boxes = $(".gap-5 .thumbnail, .video-item, .card-video, .thumbnail-item, .box-item");
                result.list = parseItems($boxes);
                result.pagecount = getPageCount();
            }
            return result;
        },

        detailContent: function (ids) {
            const slug = ids[0];
            const detail = {};
            // 解析详情信息
            $(".space-y-2:not(.list-disc) .text-secondary, .detail-item, .meta-item").each(function () {
                const $item = $(this);
                const key = $item.find("span:first, .key, dt").first().text().replace(":", "").trim();
                const $links = $item.find("a");
                if ($links.length === 0) {
                    detail[key] = $item.find("span:first, .key, dt").first().remove().end().text().trim();
                } else {
                    detail[key] = [];
                    $links.each(function () {
                        const id = getCategoryFromUrl($(this).attr("href"));
                        const name = $(this).text().trim();
                        detail[key].push(`[a=cr:{"id":"${id}","name":"${name}"}/]${name}[/a]`);
                    });
                }
            });

            const format = (keys) => keys.map(k => detail[k]).filter(Boolean).join(" ");
            const vod = {
                vod_id: slug,
                vod_name: slug.toUpperCase(),
                vod_pic: $("head link[as=image], meta[property='og:image']").attr("href") || $("meta[property='og:image']").attr("content") || "",
                vod_year: $("#space-y-2 time, .release-date, .date").text().trim(),
                vod_remarks: format(["类型", "标签", "genre"]),
                vod_actor: format(["女优", "演员", "actress", "actor"]),
                vod_content: $('a.items-center:contains("显示更多"), .description, .content').length > 0
                    ? $('meta[name=description]').attr('content') || $('meta[property="og:title"]').attr('content') || ''
                    : '',
                vod_play_from: "MissAV",
                vod_play_url: (typeof hls !== "undefined" && hls.url) ? "多视轨$" + hls.url : ""
            };
            return {list: [vod]};
        },

        searchContent: function (key, quick, pg) {
            // 真正去搜索页
            const result = {list: [], pagecount: 1};
            const $boxes = $(".gap-5 .thumbnail, .video-item, .card-video, .thumbnail-item");
            result.list = parseItems($boxes);
            result.pagecount = getPageCount();
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