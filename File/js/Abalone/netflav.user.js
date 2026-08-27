// ==UserScript==
// @name         NETFLAV
// @namespace    gmspider
// @version      2025.08.24
// @description  NETFLAV GMSpider (重构版: 直接解析 NEXT_DATA + 兼容 React 渲染)
// @author       Luomo (refactored by Minis)
// @match        https://netflav.com/*
// @require      https://cdn.jsdelivr.net/npm/jquery@3.7.1/dist/jquery.slim.min.js
// @grant        unsafeWindow
// ==/UserScript==
console.log(JSON.stringify(GM_info));
if (typeof unsafeWindow.gmSpiderRunning === "undefined") {
    unsafeWindow.gmSpiderRunning = true;
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

        // ---------------- 从 NEXT_DATA 取数据 ----------------
        function getNextData() {
            try {
                return JSON.parse($("#__NEXT_DATA__").html());
            } catch (e) {
                return null;
            }
        }

        function getVideos(key, result) {
            const data = getNextData();
            if (!data) return [];
            const state = data.props.initialState[key];
            if (!state || !state.docs) return [];
            const vods = state.docs.map(media => ({
                vod_id: media.videoId,
                vod_name: media.title,
                vod_pic: media.preview?.length > 0 ? media.preview : media.preview_hp,
                vod_remarks: "👁️" + (media.views || 0),
            }));
            if (result) {
                result.list = vods;
                result.pagecount = state.pages || 1;
            }
            return vods;
        }

        // ---------------- Spider ----------------
        const GmSpider = {
            homeContent: function (filter) {
                const result = {
                    class: [
                        {type_id: "trending?", type_name: "最受欢迎"},
                        {type_id: "browse?", type_name: "年度精选"},
                        {type_id: "chinese-sub?", type_name: "中文字幕"},
                        {type_id: "all?genre=國產AV", type_name: "国产AV"},
                        {type_id: "censored?", type_name: "有码影片"},
                        {type_id: "uncensored?", type_name: "无码影片"},
                        {type_id: "genre?", type_name: "类别"},
                    ],
                    filters: {
                        "trending?": [{
                            key: "range", name: "时间", value: [
                                {n: "全部", v: ""},
                                {n: "本月", v: "&range=month&value=1"},
                                {n: "上个月", v: "&range=month&value=2"},
                                {n: "2个月前", v: "&range=month&value=3"},
                                {n: "3个月前", v: "&range=month&value=4"},
                                {n: "4个月前", v: "&range=month&value=5"},
                                {n: "5个月前", v: "&range=month&value=6"}
                            ]
                        }]
                    },
                    list: getVideos("trending")
                };
                return result;
            },

            categoryContent: function (tid, pg, filter, extend) {
                const result = {list: [], pagecount: 1};
                const data = getNextData();
                if (!data) return result;

                if (tid === "genre?") {
                    // 类别目录
                    $(".genre_item_container .genre_item, .genre-item").each(function () {
                        const href = $(this).attr("href");
                        if (!href) return;
                        result.list.push({
                            vod_id: href.substring(1),
                            vod_name: $(this).find("div, .name, .title").first().text().trim(),
                            vod_tag: "folder",
                            style: {type: "rect", ratio: 1}
                        });
                    });
                } else if (tid === "browse?") {
                    // 年度精选 + 片单
                    [2024, 2023, 2022, 2021, 2020, 2019].forEach(y => {
                        result.list.push({
                            vod_id: `${y}?`, vod_name: `${y}年度精选`, vod_remarks: "年度精选", vod_tag: "folder"
                        });
                    });
                    const shareList = data.props.initialState.randomShareList?.docs || [];
                    shareList.forEach(share => {
                        result.list.push({
                            vod_id: `share?c=${share.shareCode}`,
                            vod_name: share.shareCode,
                            vod_remarks: "片单",
                            vod_pic: share.srcs?.[0] || "",
                            vod_tag: "folder"
                        });
                    });
                } else {
                    // 视频列表（trending/chinese-sub/censored/uncensored/all）
                    const key = tid.split("?")[0].split("-")[0];
                    if ($.isNumeric(key)) {
                        // 片单详情页
                        const formatData = data;
                        const gridCount = $(".video_grid_container .grid_0_cell").length;
                        if (gridCount > 0) {
                            // React 组件渲染完成后会把数据挂到 window
                            if (unsafeWindow.gotItems && unsafeWindow.gotItems.length === gridCount) {
                                unsafeWindow.gotItems.forEach(media => {
                                    result.list.push({
                                        vod_id: media.videoId,
                                        vod_name: media.title,
                                        vod_pic: media.preview?.length > 0 ? media.preview : media.preview_hp,
                                        vod_remarks: media.duration,
                                    });
                                });
                            } else {
                                // 等待组件渲染完成
                                return new Promise(resolve => {
                                    unsafeWindow._gotHookFunction = resolve;
                                    unsafeWindow.itemCount = gridCount;
                                }).then(items => {
                                    items.forEach(media => {
                                        result.list.push({
                                            vod_id: media.videoId,
                                            vod_name: media.title,
                                            vod_pic: media.preview?.length > 0 ? media.preview : media.preview_hp,
                                            vod_remarks: media.duration,
                                        });
                                    });
                                    return result;
                                });
                            }
                        }
                    } else {
                        // 普通列表
                        getVideos(key, result);
                    }
                }
                return result;
            },

            detailContent: function (ids) {
                const data = getNextData();
                if (!data) return {list: []};
                const video = data.props.initialState.video?.data;
                if (!video) return {list: []};

                const vodActor = [];
                video?.actors?.forEach(actor => {
                    if (actor.startsWith("zh:")) {
                        const actress = actor.substring(3);
                        vodActor.push(`[a=cr:{"id":"all?actress=${actress}","name":"${actress}"}/]${actress}[/a]`);
                    }
                });

                const tags = [];
                video?.tags?.forEach(tag => {
                    if (tag.startsWith("zh:")) {
                        const genre = tag.substring(3);
                        tags.push(`[a=cr:{"id":"all?genre=${genre}","name":"${genre}"}/]${genre}[/a]`);
                    }
                });

                const vodPlayData = [];
                video?.srcs?.forEach((src, index) => {
                    vodPlayData.push({
                        from: `播放源${index + 1}`,
                        media: [{
                            name: video.category ?? video.code,
                            type: "webview",
                            ext: {replace: {vod_id: video.videoId, src: index + 1}}
                        }]
                    });
                });

                return {
                    list: [{
                        vod_id: video.videoId,
                        vod_name: video.code,
                        vod_pic: video.preview_hp,
                        vod_year: video.videoDate?.substring(0, 10) || '',
                        vod_remarks: tags.join(" "),
                        vod_actor: vodActor.join(" "),
                        vod_content: video.description || '',
                        vod_play_data: vodPlayData
                    }]
                };
            },

            playerContent: function (flag, id, vipFlags) {
                const link = window.location.hash.split("#").at(1);
                const btn = document.querySelector(`.videoiframe_source_container .videoiframe_source_tag:nth-child(${link})`);
                if (btn) btn.dispatchEvent(new Event("click"));
                return {type: "match"};
            },

            searchContent: function (key, quick, pg) {
                const result = {list: [], pagecount: 1};
                getVideos("search", result);
                return result;
            }
        };

        $(document).ready(async function () {
            let result = await GmSpider[GMSpiderArgs.fName](...GMSpiderArgs.fArgs);
            console.log(result);
            if (typeof GmSpiderInject !== 'undefined') {
                GmSpiderInject.SetSpiderResult(JSON.stringify(result));
            }
        });
    })();
} else {
    console.log("gmSpider run again");
}