// ==UserScript==
// @name         Jable
// @namespace    gmspider
// @version      2025.08.24.3
// @description  Jable GMSpider (首页专用解析 + 通用列表解析)
// @author       Luomo (fixed by Minis)
// @match        https://jable.tv/*
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

    // ---------------- 通用列表解析(分类/搜索/标签/女优页共用) ----------------
    function parseItems($boxes) {
        const list = [];
        $boxes.each(function () {
            const $box = $(this);
            const $a = $box.find(".img-box a").first();
            const href = $a.attr("href");
            if (!href) return;
            const url = new URL(href);
            if (url.hostname !== "jable.tv") return;
            const slug = url.pathname.split('/').filter(Boolean).pop().toUpperCase();
            const title = $box.find(".title").text().trim();
            const pic = $box.find(".img-box img").data("src") || $box.find(".img-box img").attr("src");
            const dur = $box.find(".absolute-bottom-right .label").text().trim();
            const nums = $box.find(".sub-title").text().match(/([\d\s,]+)\s*<\/svg>.*?<svg[^>]*>([\d\s,]+)/);
            const views = nums ? nums[1].replace(/[^\d]/g, '') : "";
            const likes = nums ? nums[2].replace(/[^\d]/g, '') : "";
            const remarks = [
                views ? "👁" + views : "",
                likes ? "❤" + likes : "",
                dur
            ].filter(Boolean).join(" ");
            list.push({
                vod_id: slug,
                vod_name: title,
                vod_pic: pic,
                vod_remarks: remarks,
                vod_year: dur
            });
        });
        return list;
    }

    function getPageCount($doc) {
        const $last = $doc.find(".pagination .page-item:last");
        const txt = $last.text().trim();
        const n = parseInt(txt);
        return isNaN(n) ? 1 : n;
    }

    // ---------------- 首页专用解析(轮播图 + 各分区) ----------------
    function parseHome() {
        const list = [];
        // 1) 顶部大轮播
        $(".jable-carousel:first .video-img-box").each(function () {
            const $box = $(this);
            const $a = $box.find(".img-box a").first();
            const href = $a.attr("href");
            if (!href) return;
            const url = new URL(href);
            if (url.hostname !== "jable.tv") return;
            const slug = url.pathname.split('/').filter(Boolean).pop().toUpperCase();
            const title = $box.find(".title").text().trim();
            const pic = $box.find(".img-box img").data("src") || $box.find(".img-box img").attr("src");
            const dur = $box.find(".absolute-bottom-right .label").text().trim();
            list.push({vod_id: slug, vod_name: title, vod_pic: pic, vod_remarks: "", vod_year: dur});
        });
        // 2) 各分区轮播(最近更新/全新上市/热门/动态)
        $(".jable-carousel:not(:first) .video-img-box").each(function () {
            const $box = $(this);
            const $a = $box.find(".img-box a").first();
            const href = $a.attr("href");
            if (!href) return;
            const url = new URL(href);
            if (url.hostname !== "jable.tv") return;
            const slug = url.pathname.split('/').filter(Boolean).pop().toUpperCase();
            const title = $box.find(".title").text().trim();
            const pic = $box.find(".img-box img").data("src") || $box.find(".img-box img").attr("src");
            const dur = $box.find(".absolute-bottom-right .label").text().trim();
            const nums = $box.find(".sub-title").text().match(/([\d\s,]+)\s*<\/svg>.*?<svg[^>]*>([\d\s,]+)/);
            const views = nums ? nums[1].replace(/[^\d]/g, '') : "";
            const likes = nums ? nums[2].replace(/[^\d]/g, '') : "";
            const remarks = [views ? "👁" + views : "", likes ? "❤" + likes : "", dur].filter(Boolean).join(" ");
            list.push({vod_id: slug, vod_name: title, vod_pic: pic, vod_remarks: remarks, vod_year: dur});
        });
        // 3) 普通网格列表(最新更新第一组等)
        parseItems($(".video-img-box").has(".detail").has("img")).forEach(v => list.push(v));
        // 去重
        const seen = new Set();
        return list.filter(v => seen.has(v.vod_id) ? false : seen.add(v.vod_id));
    }

    // ---------------- Spider ----------------
    const GmSpider = {
        // ---------- 首页 ----------
        homeContent: function (filter) {
            return {
                class: [
                    {type_id: "latest-updates", type_name: "🆕 最近更新"},
                    {type_id: "hot", type_name: "🔥 热门影片"},
                    {type_id: "new-release", type_name: "💿 全新上市"},
                    {type_id: "categories/chinese-subtitle", type_name: "🀄 中文字幕"},
                    {type_id: "categories", type_name: "📚 主题&标签"},
                ],
                filters: {
                    "latest-updates": [{key: "sort_by", name: "排序", value: [
                        {n: "近期最佳", v: "&sort_by=post_date_and_popularity"},
                        {n: "最近更新", v: "&sort_by=post_date"},
                        {n: "最多观看", v: "&sort_by=video_viewed"},
                        {n: "最高收藏", v: "&sort_by=most_favourited"}
                    ]}],
                    "new-release": [{key: "sort_by", name: "排序", value: [
                        {n: "近期最佳", v: "&sort_by=post_date_and_popularity"},
                        {n: "最近更新", v: "&sort_by=post_date"},
                        {n: "最多观看", v: "&sort_by=video_viewed"},
                        {n: "最高收藏", v: "&sort_by=most_favourited"}
                    ]}],
                    "hot": [{key: "sort_by", name: "热度", value: [
                        {n: "所有时间", v: "&sort_by=video_viewed"},
                        {n: "本月热门", v: "&sort_by=video_viewed_month"},
                        {n: "本周热门", v: "&sort_by=video_viewed_week"},
                        {n: "今日热门", v: "&sort_by=video_viewed_today"}
                    ]}],
                    "categories/chinese-subtitle": [{key: "sort_by", name: "排序", value: [
                        {n: "近期最佳", v: "&sort_by=post_date_and_popularity"},
                        {n: "最近更新", v: "&sort_by=post_date"},
                        {n: "最多观看", v: "&sort_by=video_viewed"},
                        {n: "最高收藏", v: "&sort_by=most_favourited"}
                    ]}],
                    "categories": [{key: "sort_by", name: "排序", value: [
                        {n: "近期最佳", v: "&sort_by=post_date_and_popularity"},
                        {n: "最近更新", v: "&sort_by=post_date"},
                        {n: "最多观看", v: "&sort_by=video_viewed"},
                        {n: "最高收藏", v: "&sort_by=most_favourited"}
                    ]}]
                },
                list: parseHome()
            };
        },

        // ---------- 分类列表(直接解析当前页) ----------
        categoryContent: function (tid, pg, filter, extend) {
            if (tid === "categories") {
                const list = [];
                $("#list_categories_video_categories_list .video-img-box").each(function () {
                    const $a = $(this).find("a").first();
                    const parts = new URL($a.attr("href")).pathname.split('/').filter(Boolean);
                    list.push({
                        vod_id: parts[0] + "/" + parts[1],
                        vod_name: $(this).find("h4").text().trim(),
                        vod_pic: $(this).find("img").attr("src"),
                        vod_remarks: $(this).find(".absolute-center span").text().trim(),
                        vod_tag: "folder",
                        style: {type: "rect", ratio: 1}
                    });
                });
                $(".app-nav .title-box:gt(0)").each(function () {
                    const remark = $(this).text().trim();
                    $(this).next(".row").find(".tag").each(function () {
                        const parts = new URL($(this).attr("href")).pathname.split('/').filter(Boolean);
                        list.push({
                            vod_id: parts[0] + "/" + parts[1],
                            vod_name: $(this).text().trim(),
                            vod_remarks: remark,
                            vod_tag: "folder",
                        });
                    });
                });
                return {list, pagecount: 1};
            }
            const $boxes = $(".video-img-box").has(".detail").has("img");
            return {list: parseItems($boxes), pagecount: getPageCount($(document))};
        },

        // ---------- 详情 ----------
        detailContent: function (ids) {
            const slug = ids[0];
            const actors = [];
            $(".video-info .info-header .models .model").each(function () {
                const $a = $(this);
                const parts = new URL($a.attr("href")).pathname.split('/').filter(Boolean);
                const id = parts[0] + "/" + parts[1];
                const name = $a.find(".rounded-circle").data("original-title") || $a.text().trim();
                actors.push(`[a=cr:{"id":"${id}","name":"${name}"}/]${name}[/a]`);
            });
            const cats = [], tags = [];
            $(".video-info .info-header .tags a").each(function () {
                const $a = $(this);
                const parts = new URL($a.attr("href")).pathname.split('/').filter(Boolean);
                if (parts.length < 2) return;
                const id = parts[0] + "/" + parts[1];
                const name = $a.text().trim();
                const link = `[a=cr:{"id":"${id}","name":"${name}"}/]#${name}[/a]`;
                if (parts[0] === "categories") cats.push(link);
                else tags.push(link);
            });
            const from = $(".video-info .info-header .header-right h6")
                .clone().children().remove().end().text().trim() || "高清原片";
            const hlsUrl = (typeof unsafeWindow !== "undefined" && unsafeWindow.hlsUrl)
                ? unsafeWindow.hlsUrl : "";
            const poster = $("#player").attr("poster") ||
                $(".video-img-box img").first().data("src") || "";
            const date = $(".video-info .info-header .inactive-color").text().trim();
            const views = $(".video-info .info-header .mr-3:first").text().trim();
            return {
                list: [{
                    vod_id: slug,
                    vod_name: slug.toUpperCase(),
                    vod_pic: poster,
                    vod_year: "更新於 " + views + " " + date,
                    vod_remarks: from,
                    vod_actor: actors.join(" ") + " " + cats.join(" "),
                    vod_content: $(".video-info h4").first().text().trim() + "\n" + tags.join(" "),
                    vod_play_from: "Jable_" + from,
                    vod_play_url: hlsUrl ? "第1集$" + hlsUrl : ""
                }]
            };
        },

        // ---------- 搜索 ----------
        searchContent: function (key, quick, pg) {
            const $boxes = $(".video-img-box").has(".detail").has("img");
            return {list: parseItems($boxes), pagecount: getPageCount($(document))};
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