// ==UserScript==
// @name         MissAV
// @namespace    cod
// @version      2026.09.01
// @description  missav.ws spider for Cod.jar (FongMi TV)
// @author       cod
// @match        https://missav.ws/*
// @match        https://*.missav.ws/*
// @grant        unsafeWindow
// ==/UserScript==

// ---------------------------------------------------------------------------
// 契约（由 Cod.jar 注入的 CodSpider 提供）
//   CodSpider.fName   本次要执行的方法名
//   CodSpider.fArgs   参数数组
//   CodSpider.submit(obj)  交回结果（对象或字符串都可）
//   CodSpider.fail(msg)    报错，让 Java 侧立刻结束而不是干等超时
//
// 站点关键事实（2026-09-01 实测）：
//   1. URL 里的 /dmNNN/ 段是随机的，**不能写死**，站点会 302 到带前缀的地址。
//      所有内链都给出绝对地址（https://missav.ws/en/<slug>），直接取即可。
//   2. 列表卡片统一是 div.thumbnail.group，首页/分类/搜索/演员页全都一样，
//      所以只需要一个 parseList()。
//   3. 封面在 img[data-src]（lozad 懒加载），src 是 1px 占位图 —— 取 data-src。
//   4. 播放地址由页面里的 p,a,c,k,e,d 打包脚本解出，域名 surrit.com。
//      直接抓那个地址在外部请求会 403（Cloudflare），所以播放走 type:"match"，
//      让页面的 hls.js 自己请求，Java 侧嗅探。
// ---------------------------------------------------------------------------

(function () {
    'use strict';

    var $ = function (sel, root) {
        return (root || document).querySelector(sel);
    };
    var $$ = function (sel, root) {
        return Array.prototype.slice.call((root || document).querySelectorAll(sel));
    };
    var text = function (el) {
        return el ? (el.textContent || '').trim() : '';
    };
    var attr = function (el, name) {
        return el ? (el.getAttribute(name) || '') : '';
    };

    /** 从任意 missav 内链里取出 slug，自动剥掉随机的 /dmNNN/ 与语言段。 */
    function slugOf(href) {
        if (!href) return '';
        var m = href.match(/missav\.[a-z]+\/(?:dm\d+\/)?(?:[a-z]{2}(?:-[a-z]{2})?\/)?(.+)$/i);
        return m ? m[1].replace(/[?#].*$/, '') : '';
    }

    /** 列表卡片 -> vod。首页/分类/搜索/演员页共用一套模板。 */
    function parseList() {
        var out = [];
        $$('div.thumbnail.group').forEach(function (card) {
            var link = $('a[href*="missav."]', card);
            var slug = slugOf(attr(link, 'href'));
            if (!slug) return;

            var img = $('img[data-src]', card) || $('img', card);
            var titleLink = $('a.text-secondary', card) || link;
            var name = text(titleLink);
            // 标题以番号开头，去掉重复的番号让列表更干净
            var code = slug.split('/').pop().toUpperCase();
            if (name.indexOf(code) === 0) name = name.substring(code.length).trim();

            out.push({
                vod_id: slug,
                vod_name: code + (name ? ' ' + name : ''),
                vod_pic: attr(img, 'data-src') || attr(img, 'src'),
                vod_remarks: text($('span.absolute', card))
            });
        });
        return out;
    }

    /** 分页总数。站点的页码条只露前后几页，末尾那个才是真总数。 */
    function pageCount() {
        var max = 1;
        $$('a[href*="page="], nav a').forEach(function (a) {
            var m = attr(a, 'href').match(/[?&]page=(\d+)/);
            if (m) max = Math.max(max, parseInt(m[1], 10));
        });
        var input = $('input[name="page"]');
        if (input) max = Math.max(max, parseInt(attr(input, 'value') || '1', 10));
        return max;
    }

    /** 详情页元数据：按左侧标签名取值。标签是英文站固定文案。 */
    function metaOf(label) {
        var hit = null;
        $$('div.text-secondary').forEach(function (div) {
            if (hit) return;
            var span = $('span', div);
            if (span && text(span).replace(':', '') === label) hit = div;
        });
        if (!hit) return '';
        var values = [];
        $$('a, time, span.font-medium', hit).forEach(function (el) {
            var v = text(el);
            if (v && v.replace(':', '') !== label) values.push(v);
        });
        return values.join(',');
    }

    var Spider = {

        homeContent: function () {
            // 分类固定给站点真实入口，不做"推荐"猜测。
            // type_id 直接写站内路径段，categoryContent 的模板会拼进 URL。
            return {
                class: [
                    {type_id: 'new', type_name: '最近更新'},
                    {type_id: 'release', type_name: '今日新片'},
                    {type_id: 'uncensored-leak', type_name: '无码流出'},
                    {type_id: 'chinese-subtitle', type_name: '中文字幕'},
                    {type_id: 'genres/Hd', type_name: '高清'},
                    {type_id: 'genres/Creampie', type_name: '内射'},
                    {type_id: 'genres/Big%20Breasts', type_name: '巨乳'},
                    {type_id: 'genres/Wife', type_name: '人妻'},
                    {type_id: 'genres/Mature%20Woman', type_name: '熟女'},
                    {type_id: 'genres/Pretty%20Girl', type_name: '美少女'},
                    {type_id: 'genres/Orgy', type_name: '群交'},
                    {type_id: 'genres/VR', type_name: 'VR'}
                ],
                list: []
            };
        },

        categoryContent: function (tid, pg) {
            var page = parseInt(pg || '1', 10) || 1;
            return {
                list: parseList(),
                page: page,
                pagecount: pageCount(),
                limit: 12,
                total: 999999
            };
        },

        detailContent: function (ids) {
            var id = (ids && ids[0]) || '';
            var code = id.split('/').pop().toUpperCase();
            var poster = attr($('video.player'), 'data-poster')
                || attr($('meta[property="og:image"]'), 'content');

            return {
                list: [{
                    vod_id: id,
                    vod_name: code,
                    vod_pic: poster,
                    vod_year: metaOf('Release date'),
                    vod_area: metaOf('Maker'),
                    vod_remarks: metaOf('Series'),
                    vod_actor: metaOf('Actress'),
                    vod_director: metaOf('Maker'),
                    vod_content: text($('meta[property="og:description"]'))
                        || attr($('meta[property="og:description"]'), 'content')
                        || metaOf('Title'),
                    vod_play_data: [{
                        from: 'MissAV',
                        media: [{
                            name: '原画',
                            // 让 Java 侧嗅探 —— m3u8 直连会被 Cloudflare 403，
                            // 只有页面播放器自己发的请求才带得齐上下文。
                            type: 'match',
                            ext: {replace: {id: id}}
                        }]
                    }]
                }]
            };
        },

        // type:"match" 时 Java 侧只加载页面等嗅探，不会调这里；
        // 保留一个实现是为了让 ext.spider.playerContent 也能单独配置成 webview 型。
        playerContent: function () {
            return {type: 'match'};
        },

        searchContent: function (key, quick, pg) {
            var page = parseInt(pg || '1', 10) || 1;
            return {
                list: parseList(),
                page: page,
                pagecount: pageCount(),
                limit: 12,
                total: 999999
            };
        }
    };

    function run() {
        try {
            // CF 挑战页上**保持沉默** —— 既不 submit 也不 fail。
            //
            // Java 侧不做 DOM 轮询，它在等脚本交结果。挑战跑完后 CF 会跳转到
            // 真实页面，onPageStarted 再次触发、脚本再注入一次，那一次才交结果。
            // 这里若调 fail()，Java 的等待会提前结束，把这条自我恢复路径切断
            // —— 那正是"卡顿又不稳定"的来源。
            var challenged = $('#cf-wrapper')
                || $('#challenge-error-text')
                || $('.cf-turnstile')
                || $('[name="cf-turnstile-response"]')
                || /just a moment|checking your browser/i.test(document.title);
            if (challenged) {
                if (typeof GM_log === 'function') {
                    GM_log('cloudflare challenge in progress, waiting: ' + document.title);
                }
                return;
            }
            var fn = Spider[CodSpider.fName];
            if (!fn) {
                CodSpider.fail('unsupported function: ' + CodSpider.fName);
                return;
            }
            CodSpider.submit(fn.apply(Spider, CodSpider.fArgs || []));
        } catch (e) {
            CodSpider.fail(String(e && e.stack || e));
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', run);
    } else {
        run();
    }
})();
