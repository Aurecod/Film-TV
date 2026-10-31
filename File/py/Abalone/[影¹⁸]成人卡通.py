#!/usr/bin/env python3

import sys
import os
import re
import json
import base64
import time
import threading
import html as html_lib
import urllib.request
import urllib.parse
from urllib.parse import urlparse, quote, unquote
import http.cookiejar
import gzip
import zlib
import ssl

try:
    from base.spider import Spider as SpiderBase
except ImportError:
    class SpiderBase(object):
        def getCache(self, key): return None
        def setCache(self, key, value): return "fail"
        def delCache(self, key): return "fail"

BRAND_NAME = u"蝴蝶影视"
BRAND_ACTOR = u"🦋 TG群: @tvshare23"
BRAND_DIRECTOR = u"🦋 蝴蝶影视"

def format_remarks(brand="蝴蝶影视", meta=""):
    clean_meta = str(meta or "").strip()
    clean_meta = re.sub(r"[\r\n\t]+", " ", clean_meta).strip()
    if clean_meta:
        return "%s | %s" % (brand, clean_meta)
    return brand

# 完整還原的全量靜態分類庫
RAW_ALL_CATS = [
    ("3D性感", "categories/217/3d"), ("动漫色情", "categories/447/hentai"), ("娇小性感", "categories/583/petite"),
    ("3D卡通诱惑", "categories/218/3d-cartoon"), ("扶她激情", "categories/407/futanari"), ("浴缸暧昧", "categories/250/bath"),
    ("无码直击", "categories/725/uncensored"), ("欲火焚身", "categories/458/horny"), ("老爹角色", "categories/352/daddy"),
    ("漫画风情", "categories/197/manga"), ("动漫诱惑", "categories/231/anime"), ("处女初体验", "categories/739/virgin"),
    ("叔叔禁忌", "categories/726/uncle"), ("制服诱惑", "categories/730/uniform"), ("捆绑调教", "categories/254/bdsm"),
    ("Angels", "categories/183/angels"), ("精灵宝可梦", "categories/94/pokemon"), ("疯狂性爱", "categories/337/crazy"),
    ("迪士尼风", "categories/33/disney"), ("青春少女", "categories/700/teen"), ("丝袜诱惑", "categories/678/stockings"),
    ("学生妹子", "categories/684/student"), ("可爱小骚", "categories/222/adorable"), ("手动快感", "categories/444/handjob"),
    ("奴隶调教", "categories/658/slave"), ("巨屌猛男", "categories/266/big-cock"), ("Giants", "categories/170/giants"),
    ("大屌", "categories/321/cock"), ("病人角色", "categories/579/patient"), ("小穴", "categories/605/pussy"),
    ("孕妇", "categories/595/pregnant"), ("群交狂欢", "categories/569/orgy"), ("毛绒性癖", "categories/406/furry"),
    ("后庭猛插", "categories/235/assfucking"), ("肥胖身材", "categories/384/fat"), ("非亲妹妹", "categories/549/not-sister"),
    ("青春肉体", "categories/761/young"), ("巨乳诱惑", "categories/268/big-tits"), ("Animations", "categories/185/animations"),
    ("亚洲风情", "categories/233/asian"), ("双重插入", "categories/365/double-penetration"), ("家庭乱伦", "categories/5/family"),
    ("性爱游戏", "categories/409/game"), ("舔屁眼", "categories/620/rimjob"), ("修长美腿", "categories/493/legs"),
    ("继母诱惑", "categories/13/stepmom"), ("可爱妹子", "categories/351/cute"), ("成熟风韵", "categories/514/mature"),
    ("丰满胸部", "categories/708/tits"), ("口交快感", "categories/276/blowjob"), ("体内射精", "categories/338/creampie"),
    ("性感妈咪", "categories/530/mommy"), ("生化危机", "categories/46/resident-evil"), ("性感诱惑", "categories/643/sexy"),
    ("激烈做爱", "categories/404/fucking"), ("非亲儿子", "categories/550/not-son"), ("奶奶风韵", "categories/431/grandmother"),
    ("绝色美女", "categories/257/beautiful"), ("家庭主妇", "categories/461/housewife"), ("舔弄快感", "categories/496/lick"),
    ("老男人魅力", "categories/563/old-man"), ("激烈硬核", "categories/445/hardcore"), ("老奶奶欲", "categories/432/granny"),
    ("禁忌刺激", "categories/692/taboo"), ("后门快感", "categories/229/anal"), ("情人激情", "categories/503/lover"),
    ("赤裸诱惑", "categories/538/naked"), ("学生妹", "categories/632/schoolgirl"), ("粗暴干法", "categories/624/rough"),
    ("医生扮演", "categories/361/doctor"), ("医院情欲", "categories/459/hospital"), ("自制激情", "categories/454/homemade"),
    ("34号规则", "categories/69/rule-34"), ("满口快感", "categories/533/mouthful"), ("性感熟女", "categories/519/milf"),
    ("激情四射", "categories/578/passionate"), ("淫水直流", "categories/370/dripping"), ("户外野性", "categories/571/outdoor"),
    ("紧致身材", "categories/706/tight"), ("第一次体验", "categories/391/first-time"), ("哥特风情", "categories/429/goth"),
    ("朋友开房", "categories/403/friend"), ("美胸晃动", "categories/282/boobs"), ("酒店私密", "categories/460/hotel"),
    ("健身性爱", "categories/394/fitness"), ("圣诞性感", "categories/309/christmas"), ("震动快感", "categories/737/vibrator"),
    ("偷窥刺激", "categories/740/voyeur"), ("One Piece", "categories/162/one-piece"), ("娇小胸部", "categories/663/small-tits"),
    ("老板调戏", "categories/285/boss"), ("健身房欲", "categories/435/gym"), ("乳汁喷射", "categories/521/milk"),
    ("气球性感", "categories/245/balloon"), ("警察制服", "categories/589/police"), ("老师诱惑", "categories/699/teacher"),
    ("露肉挑逗", "categories/395/flashing"), ("潮吹高潮", "categories/676/squirting"), ("成熟女士", "categories/486/lady"),
    ("短裙撩人", "categories/656/skirt"), ("纹身诱惑", "categories/697/tattoo"), ("液体狂欢", "categories/499/liquid-lunch"),
    ("热吻缠绵", "categories/483/kissing"), ("渔网装诱惑", "categories/392/fishnets"), ("私人空间", "categories/599/private"),
    ("多汁诱人", "categories/479/juicy"), ("短发辣妹", "categories/647/short-hair"), ("丰满身材", "categories/350/curvy"),
    ("劳拉·克劳馥", "categories/29/lara-croft"), ("两女一男", "categories/388/ffm"), ("全裸诱惑", "categories/551/nude"),
    ("换妻狂欢", "categories/690/swingers"), ("完整影片", "categories/405/full-movie"), ("湿滑小穴", "categories/747/wet-pussy"),
    ("私处特写", "categories/258/beaver"), ("新娘诱惑", "categories/290/bride"), ("打屁股戏", "categories/671/spanking"),
    ("色情诱惑", "categories/376/erotic"), ("射精", "categories/343/cum"), ("人妖风情", "categories/718/transsexual"),
    ("面部射精", "categories/381/facial"), ("私处特写", "categories/736/vagina"), ("角色扮演", "categories/621/roleplay"),
    ("大臀翘臀", "categories/263/big-ass"), ("口交窒息", "categories/408/gagging"), ("紧窄小穴", "categories/707/tight-pussy"),
    ("现场秀", "categories/10/show"), ("偷窥", "categories/743/watching"), ("捆绑束缚", "categories/280/bondage"),
    ("性爱机器", "categories/505/machine"), ("宝贝性感", "categories/242/babe"), ("熟女猎手", "categories/332/cougar"),
    ("黑人辣妹", "categories/274/black"), ("Demons", "categories/180/demons"), ("顺从调戏", "categories/687/submissive"),
    ("沙滩风情", "categories/255/beach"), ("极端玩法", "categories/380/extreme"), ("怪物奇趣", "categories/531/monster"),
    ("婚礼性爱", "categories/745/wedding"), ("Fictional Characters", "categories/174/fictional-characters"),
    ("假阳具戏", "categories/680/strapon"), ("女主支配", "categories/386/femdom"), ("泳池激情", "categories/591/pool"),
    ("色情明星", "categories/592/pornstar"), ("侧身热辣", "categories/651/sideways"), ("纤细腰肢", "categories/664/small-waist"),
    ("精选合集", "categories/329/compilation"), ("吞精诱惑", "categories/689/swallow"), ("邻家女孩", "categories/419/girl-next-door"),
    ("伪娘诱惑", "categories/206/femboy"), ("女同性恋", "categories/494/lesbian"), ("眼镜诱惑", "categories/423/glasses"),
    ("自慰高潮", "categories/513/masturbation"), ("纤瘦尤物", "categories/655/skinny"), ("绿帽癖", "categories/341/cuckold"),
    ("老熟风韵", "categories/561/old"), ("群交狂欢", "categories/410/gangbang"), ("黑肤辣妹", "categories/372/ebony"),
    ("偷情", "categories/305/cheating"), ("人妻", "categories/751/wife"), ("意外性爱", "categories/221/accident"),
    ("人妖魅惑", "categories/487/ladyboy"), ("自慰快感", "categories/476/jerking-off"), ("比基尼性感", "categories/270/bikini"),
    ("人妖魅惑", "categories/646/shemale"), ("日本风情", "categories/474/japanese"), ("搞笑模仿", "categories/576/parody"),
    ("翘臀诱惑", "categories/234/ass"), ("高潮爆发", "categories/568/orgasm"), ("淘气挑逗", "categories/542/naughty"),
    ("大学风骚", "categories/324/college"), ("跨种族激情", "categories/470/interracial"), ("公共场所", "categories/601/public"),
    ("巨根震撼", "categories/532/monster-cock"), ("羞辱快感", "categories/463/humiliation"), ("伪娘", "categories/3/sissy"),
    ("后入式", "categories/362/doggystyle"), ("老少配对", "categories/562/old-and-young"), ("机器人性爱", "categories/19/robot"),
    ("异装癖", "categories/339/crossdressing"), ("模拟人生", "categories/23/sims"), ("张开诱惑", "categories/411/gaping"),
    ("漫画风", "categories/327/comic"), ("深喉口交", "categories/354/deepthroat"), ("窒息快感", "categories/308/choking"),
    ("黑人大屌", "categories/264/big-black-cock"), ("修女禁忌", "categories/553/nun"), ("精灵诱惑", "categories/192/elf"),
    ("传教士体位", "categories/524/missionary"), ("森林野战", "categories/402/forest"), ("情趣玩具", "categories/716/toys"),
    ("复古风情", "categories/616/retro"), ("内射阴道", "categories/345/cum-in-pussy"), ("口交快感", "categories/567/oral"),
    ("男同热恋", "categories/414/gay"), ("源代码动画", "categories/68/sfm"), ("拳交", "categories/393/fisting"),
    ("外星人奇遇", "categories/225/alien"), ("口交快感", "categories/688/sucking"), ("感官享受", "categories/640/sensual"),
    ("手指插入", "categories/390/fingering"), ("呻吟销魂", "categories/527/moaning"), ("纯真诱惑", "categories/466/innocent"),
    ("黑发辣妹", "categories/291/brunette"), ("性感女仆", "categories/506/maid"), ("复古情色", "categories/738/vintage"),
    ("性感装扮", "categories/572/outfit"), ("邻居诱惑", "categories/544/neighbors"), ("红发辣妹", "categories/613/redhead"),
    ("多毛诱惑", "categories/441/hairy"), ("保姆诱惑", "categories/243/babysitter"), ("美国老爸", "categories/21/american-dad"),
    ("第一人称视角", "categories/594/pov"), ("多人狂欢", "categories/434/group"), ("乡村野战", "categories/333/country"),
    ("色情按摩", "categories/510/massage"), ("圆润翘臀", "categories/293/bubble-butt"), ("性幻想", "categories/382/fantasy"),
    ("一对一", "categories/11/1on1"), ("变态玩法", "categories/482/kinky"), ("多人颜射", "categories/294/bukkake"),
    ("水族性感", "categories/26/aqua"), ("巨大震撼", "categories/462/huge"), ("书呆子性感", "categories/545/nerd"),
    ("护士诱惑", "categories/554/nurse"), ("双性恋混战", "categories/273/bisexual"), ("乳头挑逗", "categories/547/nipples"),
    ("双人玩法", "categories/364/double"), ("已婚偷情", "categories/508/married"), ("分享激情", "categories/644/share"),
    ("支配调教", "categories/363/domination"), ("浪漫氛围", "categories/622/romantic"), ("指导调教", "categories/468/instruction"),
    ("放荡骚货", "categories/661/slut"), ("凌乱狂野", "categories/660/sloppy"), ("舔阴", "categories/348/cunilingus"),
    ("湿润诱惑", "categories/746/wet"), ("丰满尤物", "categories/253/bbw"), ("骑乘快感", "categories/619/riding"),
    ("真实体验", "categories/612/reality"), ("太空激情", "categories/54/space"), ("独秀自慰", "categories/669/solo"),
    ("乳交快感", "categories/709/titty-fuck"), ("女上位", "categories/336/cowgirl"), ("阴唇特写", "categories/606/pussy-lips"),
    ("足部恋", "categories/385/feet"), ("迷你短裙", "categories/522/miniskirt"), ("节日狂欢", "categories/452/holiday"),
    ("性工作者", "categories/600/prostitute"), ("胸上射精", "categories/347/cum-on-tits"), ("内裤诱惑", "categories/574/panties"),
    ("特殊癖好", "categories/387/fetish"), ("办公室激情", "categories/559/office"), ("舔阴狂热", "categories/534/muff-diving"),
    ("老公偷情", "categories/465/husband"), ("脸上射精", "categories/346/cum-on-face"), ("车震", "categories/299/car"),
    ("古铜肌肤", "categories/695/tanned"), ("尖叫高潮", "categories/635/screaming"), ("光滑无毛", "categories/645/shaved"),
    ("暗室口交", "categories/424/gloryhole"), ("尼龙性感", "categories/556/nylon"), ("全能戏剧", "categories/76/total-drama"),
    ("拉伸挑逗", "categories/682/stretching"), ("乳胶紧身", "categories/489/latex"), ("菊花紧致", "categories/236/asshole"),
    ("沐浴性感", "categories/251/bathing"), ("性感内衣", "categories/497/lingerie"), ("男友偷欢", "categories/288/boyfriend"),
    ("漂亮妹子", "categories/596/pretty"), ("拍打刺激", "categories/657/slap"), ("大胸妹", "categories/1/oppai"),
    ("连裤袜性感", "categories/575/pantyhose"), ("厕所偷情", "categories/711/toilet"), ("龙珠", "categories/52/dragon-ball"),
    ("快速干炮", "categories/608/quickie"), ("监狱风", "categories/598/prison"), ("天然美胸", "categories/540/natural-tits"),
    ("春野樱", "categories/125/sakura-haruno"), ("角色扮演", "categories/331/costumes"), ("街头激情", "categories/681/street"),
    ("丰满阴部", "categories/267/big-pussy"), ("肌肉猛男", "categories/535/muscular"), ("教室激情", "categories/316/classroom"),
    ("勾引挑逗", "categories/637/seduction"), ("臀部游戏", "categories/237/assplay"), ("厨房激情", "categories/484/kitchen"),
    ("派对狂热", "categories/577/party"), ("透视诱惑", "categories/638/see-through"), ("女生接吻", "categories/421/girls-kissing"),
    ("农场激情", "categories/610/ranch"), ("守望先锋", "categories/44/overwatch"), ("上班偷欢", "categories/240/at-work"),
    ("假阳具", "categories/358/dildo"), ("自慰指导", "categories/477/jerk-off-instructions"), ("情侣性爱", "categories/334/couple"),
    ("小公主", "categories/597/princess"), ("男男热恋", "categories/204/yaoi"), ("风骚婊子", "categories/750/whore"),
    ("搅拌机动画", "categories/67/blender-animation"), ("床上缠绵", "categories/259/bed"), ("内衣诱惑", "categories/728/underwear"),
    ("League of Legends", "categories/164/league-of-legends"), ("张开诱惑", "categories/674/spreading"),
    ("丰满肉感", "categories/208/thick"), ("紧身裤诱惑", "categories/492/leggings"), ("秘书诱惑", "categories/636/secretary"),
    ("运动型男", "categories/239/athletic"), ("万圣节欲", "categories/442/halloween"), ("放屁癖", "categories/383/farting"),
    ("Heroes", "categories/158/heroes"), ("拉丁辣妹", "categories/490/latina"), ("DC漫画", "categories/40/dc-comics"),
    ("卧室激情", "categories/260/bedroom"), ("软色挑逗", "categories/668/softcore"), ("高跟性感", "categories/446/heels"),
    ("敏感小豆", "categories/317/clit"), ("性爱打斗", "categories/389/fight"), ("瑜伽性爱", "categories/760/yoga"),
    ("完美身材", "categories/581/perfect-body"), ("前戏挑逗", "categories/401/foreplay"), ("情绪化妹子", "categories/374/emo"),
    ("小腹诱惑", "categories/262/belly"), ("无毛诱惑", "categories/438/hairless"), ("舌头挑逗", "categories/712/tongue"),
    ("Marvel", "categories/161/marvel"), ("饱满诱惑", "categories/602/puffy"), ("最终幻想", "categories/66/final-fantasy"),
    ("下垂奶子", "categories/627/saggy-tits"), ("食物性戏", "categories/399/food"), ("女友私密", "categories/417/girlfriend"),
    ("捆绑快感", "categories/705/tied-up"), ("火影激情", "categories/198/naruto"), ("偷窥刺激", "categories/675/spying"),
    ("小巧阳具", "categories/662/small-cock"), ("Succubus", "categories/179/succubus"), ("Villains", "categories/167/villains"),
    ("男主支配", "categories/507/maledom"), ("浴室偷情", "categories/252/bathroom"), ("死或生", "categories/50/dead-or-alive"),
    ("D.Va", "categories/124/d.va"), ("脱衣诱惑", "categories/683/striptease"), ("蒂法·洛克哈特", "categories/117/tifa-lockhart"),
    ("女女激情", "categories/420/girl-on-girl"), ("传奇故事", "categories/70/legend"), ("性感模特", "categories/528/model"),
    ("被骗上床", "categories/720/tricked"), ("访谈挑逗", "categories/471/interview"), ("女王驾到", "categories/202/queen"),
    ("金发尤物", "categories/275/blonde"), ("大嘴骚货", "categories/4/big-mouth"), ("抖臀挑逗", "categories/238/ass-shaking"),
    ("牛仔热辣", "categories/475/jeans"), ("高个子", "categories/693/tall"), ("阳具挑逗", "categories/580/penis"),
    ("健身性爱", "categories/752/workout"), ("乳头穿孔", "categories/585/pierced-nipples"), ("身体穿孔", "categories/586/piercing"),
    ("神奇女侠", "categories/31/wonder-woman"), ("安全套play", "categories/330/condom"), ("粪便癖好", "categories/211/scat"),
    ("害羞挑逗", "categories/649/shy"), ("网络摄像头", "categories/744/webcam"), ("丰满肉感", "categories/310/chubby"),
    ("偷拍刺激", "categories/448/hidden"), ("七大罪", "categories/88/seven-deadly-sins"), ("娜美", "categories/128/nami"),
    ("热舞诱惑", "categories/353/dancing"), ("柔体性感", "categories/397/flexible"), ("性瘾狂热", "categories/557/nympho"),
    ("手铐诱惑", "categories/443/handcuffs"), ("鞭打调教", "categories/749/whipping"), ("兔女郎", "categories/295/bunny"),
    ("阿狸", "categories/126/ahri"), ("日向雏田", "categories/131/hinata-hyuga"), ("淫荡刺激", "categories/539/nasty"),
    ("香蕉挑逗", "categories/246/banana"), ("黄瓜自慰", "categories/342/cucumber"), ("修剪私处", "categories/721/trimmed-pussy"),
    ("被剥削", "categories/379/exploited"), ("69互玩", "categories/219/69"), ("性爱竞赛", "categories/328/competition"),
    ("猛男干将", "categories/195/fuckerman"), ("塞尔达传说", "categories/71/the-legend-of-zelda"), ("超级马里奥", "categories/84/super-mario"),
    ("情妇调教", "categories/525/mistress"), ("南方公园", "categories/22/south-park"), ("兽人狂热", "categories/14/orcs"),
    ("意外暴露", "categories/566/oops"), ("走错洞了", "categories/756/wrong-hole"), ("天使", "categories/136/mercy"),
    ("抖奶诱惑", "categories/287/bouncing-boobs"), ("星球大战", "categories/38/star-wars"), ("蒙面刺激", "categories/509/masked"),
    ("我的英雄学院", "categories/73/my-hero-academia"), ("The Incredibles", "categories/177/the-incredibles"),
    ("另类玩法", "categories/227/alternative"), ("人妖诱惑", "categories/9/trap"), ("碧蓝航线", "categories/60/azur-lane"),
    ("射精高潮", "categories/478/jizz"), ("强迫play", "categories/7/forced"), ("亲爱的弗兰克斯", "categories/48/darling-in-the-franxx"),
    ("零二", "categories/132/zero-two"), ("Sonic", "categories/176/sonic"), ("啦啦队长", "categories/306/cheerleader"),
    ("长发诱惑", "categories/500/long-hair"), ("名人色情", "categories/36/famous"), ("性感女神", "categories/426/goddess"),
    ("按摩浴缸", "categories/473/jacuzzi"), ("Dragons", "categories/182/dragons"), ("挺翘诱人", "categories/582/perky"),
    ("互动性爱", "categories/469/interactive"), ("这个美好的世界", "categories/62/konosuba"), ("少年泰坦", "categories/80/teen-titans"),
    ("游艇激情", "categories/759/yacht"), ("女尊男卑", "categories/302/cfnm"), ("雨中狂热", "categories/55/rain"),
    ("放松一下", "categories/614/relax"), ("粗暴性爱", "categories/292/brutal"), ("猛烈抽插", "categories/369/drilled"),
    ("裙底风光", "categories/734/upskirt"), ("入室盗贼", "categories/296/burglar"), ("体操性感", "categories/436/gymnast"),
    ("木乃伊性感", "categories/12/mummy"), ("交叉磨蹭", "categories/633/scissoring"), ("捆绑包裹", "categories/753/wrapped-bondage"),
    ("少年骇客", "categories/77/ben-10"), ("沙滩野战", "categories/256/beach-sex"), ("一拳超人", "categories/81/one-punch-man"),
    ("龙卷（恐怖龙卷）", "categories/112/tatsumaki-(tornado-of-terror)"), ("银河战士", "categories/61/metroid"),
    ("月下狂欢", "categories/200/moon"), ("傻白甜骚货", "categories/271/bimbo"), ("两男一女", "categories/526/mmf"),
    ("丧尸激情", "categories/16/zombie"), ("Death", "categories/172/death"), ("镜前激情", "categories/523/mirror"),
    ("水手装诱惑", "categories/628/sailor"), ("主人调教", "categories/512/master"), ("街头勾引", "categories/456/hooker"),
    ("走运艳遇", "categories/504/lucky"), ("脱衣挑逗", "categories/729/undressing"), ("刀剑神域", "categories/64/sword-art-online-(sao)"),
    ("臣服快感", "categories/686/submission"), ("涂油滑腻", "categories/560/oiled"), ("出租车激情", "categories/698/taxi"),
    ("布尔玛", "categories/138/bulma"), ("自然野性", "categories/541/nature"), ("丁字裤诱惑", "categories/704/thong"),
    ("摔跤性爱", "categories/754/wrestling"), ("火焰纹章", "categories/86/fire-emblem"), ("惊艳性感", "categories/228/amazing"),
    ("名人艳照", "categories/301/celebrity"), ("死神", "categories/85/bleach"), ("运动热辣", "categories/673/sport"),
    ("摩擦挑逗", "categories/433/grinding"), ("大学风骚", "categories/731/university"), ("鬼灭之刃", "categories/83/demon-slayer"),
    ("胡蝶忍", "categories/105/shinobu-kocho"), ("斯普拉遁", "categories/82/splatoon"), ("Griffins", "categories/186/griffins"),
    ("斩服少女", "categories/87/kill-la-kill"), ("龙子杀生丸", "categories/99/ryuko-matoi"), ("玛丽·萝丝", "categories/135/marie-rose"),
    ("牙套妹子", "categories/289/braces"), ("修长玉腿", "categories/501/long-legs"), ("影院偷欢", "categories/313/cinema"),
    ("晒痕性感", "categories/694/tan-lines"), ("丑女反差", "categories/724/ugly"), ("复仇性爱", "categories/617/revenge"),
    ("酒吧激情", "categories/247/bar"), ("同学情欲", "categories/315/classmate"), ("性感魅力", "categories/422/glamour"),
    ("亲密接触", "categories/472/intimate"), ("阿姨风骚", "categories/241/aunt"), ("受罚调教", "categories/603/punished"),
    ("X战警", "categories/79/x-men"), ("瑞克和莫蒂荒唐", "categories/212/rick-and-morty"), ("摆姿势", "categories/593/posing"),
    ("尼尔机械纪元", "categories/45/nier-automata"), ("哺乳诱惑", "categories/485/lactating"), ("怪诞小镇", "categories/43/gravity-falls"),
    ("正义联盟", "categories/25/justice-league"), ("书呆子骚气", "categories/283/bookworm"), ("紧身短裤", "categories/648/shorts"),
    ("鲍赛特", "categories/109/bowsette"), ("性感裙装", "categories/368/dress"), ("祢豆子", "categories/110/nezuko"),
    ("Clowns", "categories/171/clowns"), ("小丑扮演", "categories/320/clown"), ("醉酒性爱", "categories/371/drunk"),
    ("瑞雯", "categories/113/raven"), ("堡垒之夜", "categories/65/fortnite"), ("野狼欲望", "categories/216/wolf"),
    ("沙漠热浪", "categories/59/sand"), ("老女人风情", "categories/564/old-woman"), ("东方风情", "categories/570/oriental"),
    ("Family Guy", "categories/152/family-guy"), ("意外翻车", "categories/427/goes-wrong"), ("列车激情", "categories/717/train"),
    ("兽人狂野", "categories/205/yiff"), ("Erza Scarlet", "categories/143/erza-scarlet"), ("肿胀私处", "categories/691/swollen-pussy"),
    ("史酷比风", "categories/6/scooby-doo"), ("阿卡丽KDA", "categories/107/akali-kda"), ("超人幻想", "categories/17/superman"),
    ("Avengers", "categories/165/avengers"), ("异国风情", "categories/400/foreign"), ("手套性感", "categories/425/gloves"),
    ("自舔快感", "categories/639/self-sucking"), ("磨豆腐快感", "categories/719/tribbing"), ("熟睡偷窥", "categories/659/sleeping"),
    ("双胞胎诱惑", "categories/723/twins"), ("瓶子挑逗", "categories/286/bottle"), ("阳光下的刺激", "categories/56/sunny"),
    ("萨姆斯·艾兰", "categories/141/samus-aran"), ("哈莉奎茵性感", "categories/207/harley-quinn"),
    ("爱丽丝·盖恩斯巴勒", "categories/114/aerith-gainsborough"), ("阿凡达风", "categories/39/avatar"),
    ("科拉传奇", "categories/75/korra"), ("蝙蝠侠幻想", "categories/30/batman"), ("冒险时光", "categories/74/adventure-time"),
    ("克莱尔·雷德菲尔德", "categories/120/claire-redfield"), ("红白黑黄", "categories/49/rwby"),
    ("露西·哈特菲莉亚", "categories/106/lucy-heartfilia"), ("Fairytale", "categories/173/fairytale"),
    ("头套玩法", "categories/455/hood"), ("纲手", "categories/121/tsunade"), ("卷发妹", "categories/349/curly"),
    ("Titans", "categories/169/titans"), ("Spider Man", "categories/154/spider-man"), ("Metal", "categories/189/metal"),
    ("脱衣诱惑", "categories/318/clothes-off"), ("黄金雨癖", "categories/428/golden-shower"), ("生日狂欢", "categories/272/birthday"),
    ("女上男下", "categories/418/girl-fucks-guy"), ("按摩女郎", "categories/511/masseuse"), ("长靴诱惑", "categories/284/boots"),
    ("街头搭讪", "categories/584/pickup"), ("霞", "categories/137/kasumi"), ("Valkyrie", "categories/178/valkyrie"),
    ("超级英雄", "categories/32/superhero"), ("结城明日奈", "categories/119/asuna-yuuki"), ("裸体主义者", "categories/552/nudist"),
    ("花园性爱", "categories/412/garden"), ("Ladybug", "categories/187/ladybug"), ("史莱姆诱惑", "categories/58/slime"),
    ("跪地诱惑", "categories/565/on-her-knees"), ("巧克力涂身", "categories/307/chocolate"), ("表亲禁忌", "categories/335/cousin"),
    ("野兽交", "categories/37/beast"), ("吉尔·瓦伦丁", "categories/122/jill-valentine"), ("Green Lanterns", "categories/184/green-lanterns"),
    ("哈利波特魔法欲", "categories/203/harry-potter"), ("恶魔高校", "categories/63/high-school-dxd"),
    ("Akeno Himejima", "categories/142/akeno-himejima"), ("无性爱挑逗", "categories/548/no-sex"), ("香黛", "categories/51/shantae"),
    ("笼子play", "categories/298/cage"), ("真实感", "categories/2/realistic"), ("星火", "categories/98/starfire"),
    ("Superpowers", "categories/153/superpowers"), ("真人快打", "categories/35/mortal-combat"),
    ("巨乳幻想", "categories/41/kyonyuu-fantasy"), ("性感脚趾", "categories/710/toes"), ("皮革性感", "categories/491/leather"),
    ("芭蕾舞女郎", "categories/244/ballerina"), ("忍者神龟", "categories/92/turtles-ninja"), ("富豪玩法", "categories/618/rich"),
    ("极品少女", "categories/757/xs-girls"), ("羞辱玩法", "categories/360/disgrace"), ("Pony", "categories/160/pony"),
    ("露比·罗丝", "categories/134/ruby-rose"), ("两女一男", "categories/517/mff"), ("双马尾萌系", "categories/587/pigtails"),
    ("丑闻曝光", "categories/630/scandal"), ("Professor", "categories/150/professor"), ("全洞开发", "categories/226/all-holes"),
    ("18号安卓", "categories/116/android-18"), ("屋顶激战", "categories/623/rooftop-sex"), ("雪地激情", "categories/667/snow"),
    ("凌乱性爱", "categories/516/messy"), ("大胸诱惑", "categories/457/hooters"), ("丰满大胸", "categories/515/melons"),
    ("湿身T恤", "categories/748/wet-t-shirt"), ("上空诱惑", "categories/713/topless"), ("独家内容", "categories/377/exclusive"),
    ("纤细美男", "categories/722/twink"), ("紧身弹力", "categories/670/spandex"), ("超女诱惑", "categories/18/superwoman"),
    ("电梯激情", "categories/373/elevator"), ("阿拉伯之夜", "categories/27/arabian-nights"), ("马尾俏皮", "categories/590/ponytail"),
    ("多彩性爱", "categories/325/colorful"), ("马兽癖", "categories/8/horse"), ("兔女郎热舞", "categories/194/rabbit"),
    ("兔子玩具", "categories/609/rabbit-toy"), ("军装激情", "categories/232/army"), ("Hulk", "categories/156/hulk"),
    ("未来世界", "categories/53/future"), ("时尚性感", "categories/685/stylish"), ("猛男诱惑", "categories/464/hunk"),
    ("插入刺激", "categories/467/insertion"), ("机车辣妹", "categories/269/biker"), ("辛普森风", "categories/20/simpsons"),
    ("丰满肉感", "categories/588/plump"), ("Deadpool", "categories/151/deadpool"), ("淫荡脏污", "categories/359/dirty"),
    ("爷爷性爱", "categories/430/grandfather"), ("音乐助兴", "categories/536/music"), ("拉头发戏", "categories/439/hair-pulling"),
    ("梦中情人", "categories/367/dream-girl"), ("口红诱惑", "categories/498/lipstick"), ("赤脚诱惑", "categories/248/barefoot"),
    ("美人鱼诱惑", "categories/28/mermaid"), ("橡胶情趣", "categories/625/rubber"), ("经典老片", "categories/314/classic"),
    ("尿布癖", "categories/357/diaper"), ("艾达·王", "categories/129/ada-wong"), ("剧情性爱", "categories/679/storyline"),
    ("自慰快感", "categories/741/wanking"), ("游客艳遇", "categories/715/tourist"), ("维奥莱特·帕尔", "categories/104/violet-parr"),
    ("狼人狂暴", "categories/215/werewolf"), ("怪异刺激", "categories/210/weird"), ("井上织姬", "categories/103/orihime-inoue"),
    ("奇幻仙境", "categories/196/wonderland"), ("未来家庭", "categories/72/futurama"), ("Bender", "categories/145/bender"),
    ("香烟挑逗", "categories/312/cigarette"), ("抽烟性感", "categories/665/smoking"), ("Evils", "categories/181/evils"),
    ("布莱克·贝拉多娜", "categories/123/blake-belladonna"), ("送货小哥", "categories/355/delivery-boy"),
    ("疼痛快感", "categories/573/pain"), ("变性美女", "categories/702/tgirl"), ("汤姆与杰瑞", "categories/90/tom-and-jerry"),
    ("Universal Pictures", "categories/163/universal-pictures"), ("丛林野性", "categories/481/jungle"),
    ("黛米", "categories/118/demi"), ("互相自慰", "categories/537/mutual-masturbation"), ("公交车", "categories/297/bus"),
    ("黑影", "categories/133/sombra"), ("尼尔2B型", "categories/127/yorha-no-2-type-b"), ("Philip J Fry", "categories/147/philip-j-fry"),
    ("贫民区风", "categories/415/ghetto"), ("船上激情", "categories/277/boat"), ("贴身热舞", "categories/488/lap-dance"),
    ("淫荡骚气", "categories/611/raunchy"), ("瞳", "categories/115/hitomi"), ("Warcraft", "categories/191/warcraft"),
    ("甜蜜糖果", "categories/209/candy"), ("摩登原始人", "categories/24/flintstones"), ("吊带性感", "categories/413/garter-belt"),
    ("小穴拉伸", "categories/607/pussy-stretching"), ("屁股被干爆", "categories/356/destroyed-ass"),
    ("双阴插入", "categories/366/double-vaginal"), ("前女友", "categories/378/ex-girlfriend"), ("街头流浪", "categories/453/homeless"),
    ("嬉皮风骚", "categories/449/hippy"), ("努鲁按摩", "categories/555/nuru-massage"), ("教堂禁忌", "categories/311/church"),
    ("性爱告白", "categories/642/sex-confessions"), ("猫咪打架", "categories/300/catfight"), ("德克斯特", "categories/93/dexter"),
    ("吉普赛风", "categories/437/gypsy"), ("娇小身材", "categories/518/midget"), ("军装诱惑", "categories/520/military"),
    ("肉棒崇拜", "categories/323/cock-worship"), ("愤怒性爱", "categories/230/angry"), ("发型性感", "categories/440/hairstyle"),
    ("女主支配", "categories/495/lezdom"), ("弓箭手激情", "categories/213/archer"), ("Ayane", "categories/144/ayane"),
    ("朋克风", "categories/604/punk"), ("衣服撕裂", "categories/319/clothes-ripped"), ("真空吸力", "categories/735/vacuum"),
    ("强势猛干", "categories/223/aggressive"), ("窒息快感", "categories/666/smother"), ("肌肉猛男", "categories/278/bodybuilder"),
    ("空姐制服", "categories/677/stewardess"), ("Twisted", "categories/188/twisted"), ("抓痕刺激", "categories/634/scratches"),
    ("Guardians of the Galaxy", "categories/166/guardians-of-the-galaxy"), ("高雄", "categories/100/takao"),
    ("肥胖诱惑", "categories/558/obese"), ("Cosmo Boy", "categories/168/cosmo-boy"), ("希尔达", "categories/78/hilda"),
    ("地下室私密", "categories/249/basement"), ("Soldiers", "categories/190/soldiers"), ("超大尺寸", "categories/758/xxl"),
    ("哭泣快感", "categories/340/crying"), ("搞笑性感", "categories/654/silly"), ("巫师", "categories/47/the-witcher"),
    ("希里", "categories/130/ciri"), ("金·波塞尔", "categories/101/kim-possible"), ("Minions", "categories/175/minions"),
    ("缎面性感", "categories/629/satin"), ("空中性爱", "categories/398/flight"), ("老鼠癖", "categories/34/mouse"),
    ("跳动巨乳", "categories/480/jumping-tits"), ("恶魔诱惑", "categories/214/deamons"), ("紧张刺激", "categories/546/nervous"),
    ("美少女战士", "categories/201/sailor-moon"), ("大恶司女战士猎手", "categories/42/daiakuji-the-xena-buster"),
    ("窥阴器趣", "categories/672/speculum"), ("施虐快感", "categories/626/sadism"), ("灌肠玩法", "categories/375/enema"),
    ("水下激情", "categories/727/underwater"), ("硅胶丰满", "categories/652/silicone"), ("叶妮芙", "categories/139/yennefer"),
    ("搞笑色情", "categories/326/comedy"), ("皱纹熟女", "categories/755/wrinkled"), ("Leela", "categories/146/leela"),
    ("修理工诱惑", "categories/615/repairman"), ("射后放屁", "categories/344/cum-farting"), ("精准挑逗", "categories/696/targeted"),
    ("妈妈与少年", "categories/529/mom-and-boy"), ("Amy Wong", "categories/148/amy-wong"), ("大阴蒂诱惑", "categories/265/big-clit"),
    ("仓库偷情", "categories/742/warehouse"), ("诗乃（朝田诗乃）", "categories/96/sinon-(asada-shino)"),
    ("三星小助手Sam", "categories/111/samsung-sam"), ("平胸诱惑", "categories/396/flat-chested"), ("海绵宝宝", "categories/89/sponge-bob"),
    ("布雷默顿", "categories/108/bremerton"), ("废弃老屋激情", "categories/220/abandoned-house"), ("外星飞船", "categories/57/ufo"),
    ("丝滑诱惑", "categories/653/silk"), ("阴茎环", "categories/322/cock-ring"), ("啤酒助兴", "categories/261/beer"),
    ("爱宕", "categories/140/atago"), ("骷髅魅影", "categories/193/skeleton"), ("捆绑紧缚", "categories/451/hogtied"),
    ("身体彩绘", "categories/279/body-painting"), ("触手怪戏", "categories/701/tentacle"), ("性爱狂欢", "categories/641/sex"),
    ("科琳", "categories/102/corrin"), ("学生弟弟", "categories/631/schoolboy"), ("小偷被抓", "categories/703/thief-caught"),
    ("机场偷情", "categories/224/airport"), ("Other Planet", "categories/157/other-planet"), ("Iron Man", "categories/155/iron-man"),
    ("梅林", "categories/95/merlin"), ("佩罗娜", "categories/97/perona"), ("长指甲性感", "categories/502/long-nails")
]
# 自動依據分類名稱（中文）排序
RAW_ALL_CATS.sort(key=lambda x: x[0])

class Spider(SpiderBase):
    def __init__(self):
        super(Spider, self).__init__()
        self.defaultHost = "https://www.cartoonporno.cc"
        self.siteUrl = self.defaultHost
        self.navUrls = [
            "https://x99dh.vip",
            "https://x99dh.my",
            "https://x99dh.cc",
            "https://x99dh.one"
        ]
        self.siteName = "CartoonPorno"
        self.siteAlias = "免费精品动漫卡通视频"
        self.tgGroup = "https://t.me/tvshare23"
        self._ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        self.options = {}
        self._dynamic_cats = [] # 暫存動態抓取到的分類

        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE

        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj),
            urllib.request.HTTPSHandler(context=self.ctx)
        )
        self.route_lock = threading.Lock()

    def init(self, extend=""):
        if isinstance(extend, dict):
            self.options = extend
        elif extend:
            try:
                self.options = json.loads(extend)
            except Exception:
                self.options = {}

        cached_host = self.getCache("cartoonporno_fastest_host")
        if cached_host and str(cached_host).startswith("http"):
            self.siteUrl = str(cached_host).strip().rstrip("/")
        else:
            self.siteUrl = self.defaultHost
        return True

    def getName(self):
        return BRAND_NAME + u"·CartoonPorno"

    def isVideoFormat(self, url):
        low = (url or "").lower()
        if any(bad in low for bad in ("p320-180.mp4", "preview.mp4", "sample.mp4", "trailer.mp4", "55287.mp4")):
            return False
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".mkv", ".avi", ".ts", ".mpd", "index.png"))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self.options = {}

    def _to_base_domain(self, url):
        try:
            p = urllib.parse.urlparse(url.strip())
            if p.scheme and p.netloc:
                return "%s://%s" % (p.scheme, p.netloc)
        except Exception:
            pass
        return ""

    def _fetch_all_candidates(self):
        headers = {
            "User-Agent": self._ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        for nav in self.navUrls:
            text = ""
            try:
                req = urllib.request.Request(nav, headers=headers)
                with self.opener.open(req, timeout=3) as resp:
                    raw = resp.read()
                    enc = getattr(resp, "headers", {}).get("Content-Encoding", "")
                    if raw.startswith(b"\x1f\x8b") or enc == "gzip":
                        raw = gzip.decompress(raw)
                    elif enc == "deflate":
                        try:
                            raw = zlib.decompress(raw)
                        except Exception:
                            raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                    text = raw.decode("utf-8", errors="ignore")
            except Exception:
                continue

            if not text:
                continue

            b64_blocks = re.findall(r'["\']([A-Za-z0-9+/=]{100,})["\']', text)
            for b in b64_blocks:
                try:
                    dec = urllib.parse.unquote(base64.b64decode(b).decode("utf-8", errors="ignore"))
                    if "[" in dec and (self.siteName.lower() in dec.lower() or self.siteAlias in dec):
                        site_list = json.loads(dec)
                        for item in site_list:
                            name = item.get("name", "").strip()
                            desc = item.get("desc", "").strip()
                            if self.siteName.lower() in name.lower() or self.siteName.lower() in desc.lower() or self.siteAlias in name or self.siteAlias in desc:
                                cand_urls = []
                                if item.get("url"):
                                    cand_urls.append(item.get("url"))
                                for u_obj in item.get("urls", []):
                                    u = u_obj.get("url", "")
                                    if u and u not in cand_urls:
                                        cand_urls.append(u)
                                clean_cands = []
                                for cu in cand_urls:
                                    bd = self._to_base_domain(cu)
                                    if bd and bd not in clean_cands:
                                        clean_cands.append(bd)
                                if clean_cands:
                                    return clean_cands
                except Exception:
                    continue

        return [self.defaultHost]

    def _auto_select_fastest_route(self, force=False):
        with self.route_lock:
            now_ts = time.time()
            if not force:
                cached_host = self.getCache("cartoonporno_fastest_host")
                cached_time = self.getCache("cartoonporno_fastest_time")
                if cached_host and cached_time:
                    try:
                        if now_ts - float(cached_time) < 43200:
                            self.siteUrl = str(cached_host).strip().rstrip("/")
                            return self.siteUrl
                    except Exception:
                        pass

            candidates = self._fetch_all_candidates()
            if not candidates:
                self.siteUrl = self.defaultHost
                return self.siteUrl

            results = []
            res_lock = threading.Lock()

            def ping_node(node_url):
                t0 = time.time()
                try:
                    chk_req = urllib.request.Request(
                        node_url + "/videos?hl=zh",
                        headers={"User-Agent": self._ua, "Accept": "*/*"}
                    )
                    with self.opener.open(chk_req, timeout=2.5) as r:
                        if r.getcode() == 200:
                            cost = (time.time() - t0) * 1000
                            with res_lock:
                                results.append((cost, node_url))
                except Exception:
                    pass

            threads = []
            for node in candidates:
                t = threading.Thread(target=ping_node, args=(node,))
                t.daemon = True
                t.start()
                threads.append(t)

            for t in threads:
                t.join(timeout=2.5)

            if results:
                results.sort(key=lambda x: x[0])
                best_host = results[0][1]
            else:
                best_host = candidates[0]

            self.siteUrl = best_host
            self.setCache("cartoonporno_fastest_host", best_host)
            self.setCache("cartoonporno_fastest_time", str(now_ts))
            return self.siteUrl

    def _fetch(self, target_url, referer="", check_host=True, timeout=4):
        if not target_url:
            return {"code": 0, "text": "", "bytes": b"", "err": "", "final_url": ""}
        if target_url.startswith("//"):
            real_url = "https:" + target_url
        elif target_url.startswith("/"):
            real_url = self.siteUrl + target_url
        elif not target_url.startswith("http"):
            real_url = self.siteUrl + "/" + target_url
        else:
            real_url = target_url

        headers = {
            "User-Agent": self._ua,
            "Referer": referer if referer else (self.siteUrl + "/"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1"
        }

        try:
            req = urllib.request.Request(real_url, headers=headers)
            with self.opener.open(req, timeout=timeout) as resp:
                raw = resp.read()
                enc = getattr(resp, "headers", {}).get("Content-Encoding", "").lower()
                if raw.startswith(b"\x1f\x8b") or "gzip" in enc:
                    raw = gzip.decompress(raw)
                elif "deflate" in enc:
                    try:
                        raw = zlib.decompress(raw)
                    except Exception:
                        raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                try:
                    text = raw.decode("utf-8")
                except Exception:
                    text = raw.decode("latin1", errors="ignore")
                return {"code": resp.getcode(), "text": text, "bytes": raw, "err": "", "final_url": resp.geturl()}
        except urllib.error.HTTPError as e:
            if e.code in (404, 451, 500, 502, 503) and check_host:
                self.delCache("cartoonporno_fastest_host")
                self._auto_select_fastest_route(force=True)
                return self._fetch(target_url, referer=referer, check_host=False, timeout=timeout)
            return {"code": e.code, "text": "", "bytes": b"", "err": str(e), "final_url": real_url}
        except Exception as e:
            if check_host:
                self.delCache("cartoonporno_fastest_host")
                self._auto_select_fastest_route(force=True)
                return self._fetch(target_url, referer=referer, check_host=False, timeout=timeout)
            return {"code": -1, "text": "", "bytes": b"", "err": str(e), "final_url": real_url}

    def _fetch_dynamic_categories(self):
        """動態抓取全站所有最新分類"""
        if self._dynamic_cats:
            return self._dynamic_cats

        try:
            # 請求分類首頁
            res = self._fetch("/categories/?hl=zh", timeout=6)
            html = res.get("text", "")
            
            # 提取所有分類連結 (匹配如: href="/categories/217/3d/")
            pattern = r'href=["\']/(categories/\d+/[^/"\'?]+)[^>]*>([\s\S]*?)</a>'
            matches = re.findall(pattern, html, re.I)
            
            cats = []
            seen_routes = set()
            
            for route, text in matches:
                # 清理 HTML 標籤與多餘空白
                name = re.sub(r'<[^>]+>', '', text).strip()
                name = re.sub(r'\s+', ' ', name)
                
                if not name or route in seen_routes:
                    continue
                # 過濾異常的非分類字串
                if "javascript" in name.lower() or name.isdigit():
                    continue
                    
                seen_routes.add(route)
                cats.append((name, route))
            
            # 判斷抓取結果是否有效 (通常有 700+ 個)
            if len(cats) > 100:
                # 動態抓取結果也依照中文名稱排序
                cats.sort(key=lambda x: x[0])
                self._dynamic_cats = cats
                return cats
        except Exception:
            pass
            
        # 若發生網路異常導致抓取失敗，則退回使用原本已排序的備用靜態庫
        return RAW_ALL_CATS

    def _build_category_folders(self, cats):
        """將大量分類整理成 TVBox 可逐層進入的資料夾。"""
        groups = [
            ("全部分類", "all"),
            ("3D及CG", "3d"),
            ("動漫二次元", "anime"),
            ("同人角色", "char"),
            ("體態特徵", "physique"),
            ("角色扮演", "roleplay"),
            ("情境玩法", "scenes")
        ]

        kw_3d = ("3d", "sfm", "blender", "overwatch", "resident-evil", "final-fantasy", "dead-or-alive", "nier", "zelda", "fortnite", "league-of-legends", "warcraft", "sims")
        kw_anime = ("hentai", "anime", "manga", "dragon-ball", "naruto", "one-piece", "bleach", "demon-slayer", "one-punch-man", "pokemon", "dxd", "sao", "azur-lane", "kill-la-kill")
        kw_char = ("tifa", "android-18", "nami", "ahri", "hinata", "yorha", "sakura", "d.va", "lara", "ada-wong", "jill", "tsunade", "zero-two", "nezuko", "wonder-woman", "harley", "bulma", "asuna", "aerith", "samus", "yennefer", "ciri", "bowsette", "raven", "mercy", "shinobu", "sombra", "atago", "corrin")
        kw_physique = ("petite", "tits", "ass", "legs", "cock", "pussy", "bbw", "thick", "skinny", "fat", "brunette", "blonde", "redhead", "shaved", "hairy", "big-", "small-", "tall", "muscular")
        kw_roleplay = ("uniform", "student", "maid", "nurse", "teacher", "secretary", "stewardess", "police", "bunny", "housewife", "stepmom", "milf", "nun", "model", "babysitter", "doctor", "slave", "costume")

        result = {gid: [] for _, gid in groups}
        for item in cats:
            name, route = item
            low_r = route.lower()
            low_n = name.lower()
            opt = {"n": name, "v": route}

            if any(k in low_r or k in low_n for k in kw_3d):
                result["3d"].append(opt)
            elif any(k in low_r or k in low_n for k in kw_char):
                result["char"].append(opt)
            elif any(k in low_r or k in low_n for k in kw_anime):
                result["anime"].append(opt)
            elif any(k in low_r or k in low_n for k in kw_physique):
                result["physique"].append(opt)
            elif any(k in low_r or k in low_n for k in kw_roleplay):
                result["roleplay"].append(opt)
            else:
                result["scenes"].append(opt)

        result["all"] = [{"n": name, "v": route} for name, route in cats]
        return result

    def _folder_item(self, name, folder_id, count=None):
        suffix = ""
        if count is not None:
            suffix = " (%d)" % count
        return {
            "vod_id": "folder:%s" % folder_id,
            "vod_name": name + suffix,
            "vod_pic": "",
            "vod_remarks": "分類資料夾",
            "vod_tag": "folder",
            "style": {"type": "list", "ratio": 1.78}
        }

    def _category_folder_items(self, group_id):
        cats = self._fetch_dynamic_categories()
        grouped = self._build_category_folders(cats)
        items = grouped.get(group_id, grouped["all"])
        result = []
        for opt in items:
            result.append({
                "vod_id": "cat:%s" % opt["v"],
                "vod_name": opt["n"],
                "vod_pic": "",
                "vod_remarks": "進入分類",
                "vod_tag": "folder"
            })
        return result

    def homeContent(self, filter):
        classes = [
            {"type_id": "videos", "type_name": "全部视频"},
            {"type_id": "sec_3d", "type_name": "3D精选"},
            {"type_id": "sec_anime", "type_name": "二次元动漫"},
            {"type_id": "sec_char", "type_name": "同人角色"},
            {"type_id": "sec_physique", "type_name": "体态风情"},
            {"type_id": "sec_roleplay", "type_name": "角色扮演"},
            {"type_id": "sec_scenes", "type_name": "情境玩法"}
        ]

        # 不再把數百個分類塞進 TVBox Filter。
        # TVBox 只收到少量第一層資料夾，進入後再載入第二層分類。
        return {
            "class": classes,
            "filters": {}
        }

    def homeVideoContent(self):
        # 首頁熱門影片仍然保留原本的影片列表。
        res = self.categoryContent("videos", "1", True, {})
        return {"list": res.get("list", [])[:12]}

    def homeVideoContent(self):
        res = self.categoryContent("videos", "1", True, {})
        return {"list": res.get("list", [])[:12]}

    def categoryContent(self, tid, pg, filter, extend):
        slug = str(tid or "videos").strip("/")
        page_idx = int(pg or 1)
        extend_dict = extend or {}

        sort_val = extend_dict.get("s", "")
        chosen_cat = extend_dict.get("cat", "")

        # TVBox 資料夾導覽：folder:xxx / cat:categories/...
        if slug.startswith("folder:"):
            group_id = slug.split(":", 1)[1] or "all"
            folder_list = self._category_folder_items(group_id)
            return {
                "page": 1,
                "pagecount": 1,
                "limit": len(folder_list),
                "total": len(folder_list),
                "list": folder_list
            }

        if slug.startswith("cat:"):
            actual_route = slug.split(":", 1)[1].strip("/")
        elif chosen_cat:
            actual_route = chosen_cat.strip("/")
        elif slug in ("videos", "sec_3d", "sec_anime", "sec_char", "sec_physique", "sec_roleplay", "sec_scenes"):
            # 每個首頁分類都先顯示資料夾，而不是一次列出全部分類。
            group_map = {
                "videos": "all",
                "sec_3d": "3d",
                "sec_anime": "anime",
                "sec_char": "char",
                "sec_physique": "physique",
                "sec_roleplay": "roleplay",
                "sec_scenes": "scenes"
            }
            group_id = group_map[slug]
            return {
                "page": 1,
                "pagecount": 1,
                "limit": 1,
                "total": 1,
                "list": [self._folder_item(
                    "全部分類" if group_id == "all" else {
                        "3d": "3D及CG分類",
                        "anime": "動漫二次元分類",
                        "char": "同人角色分類",
                        "physique": "體態特徵分類",
                        "roleplay": "角色扮演分類",
                        "scenes": "情境玩法分類"
                    }.get(group_id, "分類") ,
                    group_id,
                    len(self._fetch_dynamic_categories()) if group_id == "all" else len(self._build_category_folders(self._fetch_dynamic_categories()).get(group_id, []))
                )]
            }
        else:
            actual_route = slug

        query_parts = ["hl=zh"]
        if sort_val:
            query_parts.append("s=%s" % quote(sort_val))
        if page_idx > 1:
            query_parts.append("page=%d" % page_idx)

        query_str = "&".join(query_parts)

        if actual_route == "videos":
            target_url = "/videos?%s" % query_str
        else:
            target_url = "/%s/?%s" % (actual_route, query_str)

        res = self._fetch(target_url, timeout=4)
        html_text = res.get("text", "")

        clean_html = re.sub(r'<header[\s\S]*?</header>', '', html_text, flags=re.I)
        clean_html = re.sub(r'<nav[\s\S]*?</nav>', '', clean_html, flags=re.I)
        clean_html = re.sub(r'<footer[\s\S]*?</footer>', '', clean_html, flags=re.I)

        raw_items = []
        if 'data-vid=' in clean_html:
            splits = re.split(r'(?=<[^>]+data-vid=[\'"][^\'"]+[\'"])', clean_html)
            raw_items = splits[1:] if len(splits) > 1 else []

        if not raw_items:
            raw_items = re.findall(r'(<(?:div|li|article)[^>]+class=["\'][^"\']*(?:item|video|thumb|card|col)[^"\']*["\'][\s\S]*?</(?:div|li|article)>)', clean_html, re.I)

        v_list = []
        for idx, block in enumerate(raw_items):
            vid_m = re.search(r'data-vid=["\'](\d+)["\']', block)
            vid = vid_m.group(1) if vid_m else ""

            data_s_m = re.search(r'data-s=["\']([^"\']+)["\']', block)
            data_i_m = re.search(r'data-i=["\']([^"\']+)["\']', block)
            data_u_m = re.search(r'data-u=["\']([^"\']+)["\']', block)
            data_q_m = re.search(r'data-q=["\']([^"\']+)["\']', block)

            href_m = re.search(r'<a[^>]+href=["\']([^"\']+)["\']', block)
            raw_href = href_m.group(1).strip() if href_m else ""

            if data_s_m and data_i_m and data_u_m:
                s_val = data_s_m.group(1).rstrip("/") + "/"
                i_val = data_i_m.group(1).strip("/")
                u_val = data_u_m.group(1).strip()
                q_val = data_q_m.group(1).strip() if data_q_m else "?hl=zh"
                detail_path = "%s%s%s%s" % (s_val, i_val, u_val, q_val)
            elif "/v-" in raw_href or "/v/" in raw_href:
                detail_path = raw_href
            else:
                detail_path = raw_href

            if not vid:
                url_num_m = re.search(r'/(\d+)[^/]*$', raw_href)
                vid = url_num_m.group(1) if url_num_m else ("%s_%d" % (slug, idx))

            title = ""
            title_m = re.search(r'title=["\']([^"\']+)["\']', block)
            if title_m:
                title = title_m.group(1).strip()
            if not title:
                alt_m = re.search(r'alt=["\']([^"\']+)["\']', block)
                if alt_m:
                    title = alt_m.group(1).strip()
            if not title:
                text_cand = re.findall(r'<a[^>]+>([\s\S]*?)</a>', block)
                for t in text_cand:
                    ct = re.sub(r'<[^>]+>', '', t).strip()
                    if len(ct) > 2:
                        title = ct
                        break

            pic = ""
            pic_m = re.search(r'<img[^>]+(?:data-src|data-original|src)=["\']([^"\']+)["\']', block, re.I)
            if pic_m:
                pic = pic_m.group(1).strip()
                if pic.startswith("//"):
                    pic = "https:" + pic
                elif pic.startswith("/"):
                    pic = urllib.parse.urljoin(self.siteUrl, pic)

            final_title = title or ("视频 %s" % vid)
            pack_id = "%s@@%s@@%s@@%s" % (vid, quote(final_title), quote(detail_path), quote(pic))

            duration = ""
            dur_m = re.search(r'(?:class=["\'][^"\']*(?:duration|time|length)[^"\']*["\'][^>]*>|>)\s*(\d{1,2}:\d{2}(?::\d{2})?)\s*<', block, re.I)
            if dur_m:
                duration = dur_m.group(1).strip()

            remarks = format_remarks(BRAND_NAME, duration)

            v_list.append({
                "vod_id": pack_id,
                "vod_name": final_title,
                "vod_pic": pic,
                "vod_remarks": remarks,
                "style": {"type": "rect", "ratio": 1.78}
            })

        return {
            "page": page_idx,
            "pagecount": page_idx + 1 if len(v_list) >= 20 else page_idx,
            "limit": len(v_list),
            "total": 9999,
            "list": v_list
        }

    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        parts = raw_id.split("@@")
        vid = parts[0] if len(parts) > 0 else raw_id
        title = unquote(parts[1]) if len(parts) > 1 else ("视频 %s" % vid)
        detail_path = unquote(parts[2]) if len(parts) > 2 else ""
        pic_url = unquote(parts[3]) if len(parts) > 3 else ""

        full_stream_url = ""

        if detail_path:
            res = self._fetch(detail_path, referer=self.siteUrl + "/videos?hl=zh", timeout=4)
            html_text = res.get("text", "")

            source_m = re.findall(r'<source[^>]+src=["\']([^"\']+)["\']', html_text, re.I)
            for cand in source_m:
                if not any(bad in cand.lower() for bad in ("p320-180.mp4", "preview", "sample")):
                    full_stream_url = cand.strip()
                    break

            if not full_stream_url:
                vsrc_m = re.findall(r'<video[^>]+src=["\']([^"\']+)["\']', html_text, re.I)
                for cand in vsrc_m:
                    if not any(bad in cand.lower() for bad in ("p320-180.mp4", "preview", "sample")):
                        full_stream_url = cand.strip()
                        break

            if not full_stream_url:
                mp4_matches = re.findall(r'["\'](https?://[^"\']+\.mp4[^"\']*)["\']', html_text, re.I)
                for cand in mp4_matches:
                    if not any(bad in cand.lower() for bad in ("p320-180.mp4", "preview", "sample")):
                        full_stream_url = cand.strip()
                        break

            if not full_stream_url:
                m3u8_matches = re.findall(r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', html_text, re.I)
                if m3u8_matches:
                    full_stream_url = m3u8_matches[0].strip()

        play_target = full_stream_url if full_stream_url else raw_id

        full_desc = (
            "【🔥 官方交流群: %s】\n"
            "【当前优选节点: %s】\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "片名: %s\n"
            "编号: %s\n"
            "线路: 蝴蝶专线 完整长片正片"
        ) % (self.tgGroup, self.siteUrl, title, vid)

        clean_pic = pic_url if (pic_url.startswith("http://") or pic_url.startswith("https://")) else ""

        return {
            "list": [{
                "vod_id": raw_id,
                "vod_name": title,
                "vod_pic": clean_pic,
                "vod_bg": clean_pic,
                "vod_background": clean_pic,
                "vod_banner": clean_pic,
                "vod_actor": BRAND_ACTOR,
                "vod_director": BRAND_DIRECTOR,
                "vod_remarks": format_remarks(BRAND_NAME, "HD完整正片"),
                "vod_content": full_desc.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"),
                "vod_play_from": "🦋 蝴蝶专线",
                "vod_play_url": "超清完整正片$%s" % play_target
            }]
        }

    def playerContent(self, flag, id, vipFlags):
        target_play_url = str(id).strip()

        if target_play_url.startswith("//"):
            target_play_url = "https:" + target_play_url
        elif target_play_url.startswith("/"):
            target_play_url = self.siteUrl + target_play_url

        if target_play_url.startswith("http"):
            low_u = target_play_url.lower()
            if ".m3u8" not in low_u and ".mp4" not in low_u and ".flv" not in low_u and ".mkv" not in low_u:
                sep = "&" if "?" in target_play_url else "?"
                target_play_url = target_play_url + sep + "format=.m3u8"

        headers = {
            "User-Agent": self._ua,
            "Referer": self.siteUrl + "/"
        }

        return {
            "parse": 0,
            "jx": 0,
            "url": target_play_url,
            "header": headers
        }

    def searchContent(self, key, quick, pg="1"):
        page_idx = int(pg or 1)
        search_url = "/search?q=%s&hl=zh" % quote(key)
        if page_idx > 1:
            search_url += "&page=%d" % page_idx

        res = self._fetch(search_url, timeout=4)
        html_text = res.get("text", "")

        clean_html = re.sub(r'<header[\s\S]*?</header>', '', html_text, flags=re.I)
        clean_html = re.sub(r'<nav[\s\S]*?</nav>', '', clean_html, flags=re.I)
        clean_html = re.sub(r'<footer[\s\S]*?</footer>', '', clean_html, flags=re.I)

        raw_items = []
        if 'data-vid=' in clean_html:
            splits = re.split(r'(?=<[^>]+data-vid=[\'"][^\'"]+[\'"])', clean_html)
            raw_items = splits[1:] if len(splits) > 1 else []

        if not raw_items:
            raw_items = re.findall(r'(<(?:div|li|article)[^>]+class=["\'][^"\']*(?:item|video|thumb|card|col)[^"\']*["\'][\s\S]*?</(?:div|li|article)>)', clean_html, re.I)

        v_list = []
        for idx, block in enumerate(raw_items):
            vid_m = re.search(r'data-vid=["\'](\d+)["\']', block)
            vid = vid_m.group(1) if vid_m else ""

            data_s_m = re.search(r'data-s=["\']([^"\']+)["\']', block)
            data_i_m = re.search(r'data-i=["\']([^"\']+)["\']', block)
            data_u_m = re.search(r'data-u=["\']([^"\']+)["\']', block)
            data_q_m = re.search(r'data-q=["\']([^"\']+)["\']', block)

            href_m = re.search(r'<a[^>]+href=["\']([^"\']+)["\']', block)
            raw_href = href_m.group(1).strip() if href_m else ""

            if data_s_m and data_i_m and data_u_m:
                s_val = data_s_m.group(1).rstrip("/") + "/"
                i_val = data_i_m.group(1).strip("/")
                u_val = data_u_m.group(1).strip()
                q_val = data_q_m.group(1).strip() if data_q_m else "?hl=zh"
                detail_path = "%s%s%s%s" % (s_val, i_val, u_val, q_val)
            elif "/v-" in raw_href or "/v/" in raw_href:
                detail_path = raw_href
            else:
                detail_path = raw_href

            if not vid:
                url_num_m = re.search(r'/(\d+)[^/]*$', raw_href)
                vid = url_num_m.group(1) if url_num_m else ("search_%d" % idx)

            title = ""
            title_m = re.search(r'title=["\']([^"\']+)["\']', block)
            if title_m:
                title = title_m.group(1).strip()
            if not title:
                alt_m = re.search(r'alt=["\']([^"\']+)["\']', block)
                if alt_m:
                    title = alt_m.group(1).strip()
            if not title:
                text_cand = re.findall(r'<a[^>]+>([\s\S]*?)</a>', block)
                for t in text_cand:
                    ct = re.sub(r'<[^>]+>', '', t).strip()
                    if len(ct) > 2:
                        title = ct
                        break

            pic = ""
            pic_m = re.search(r'<img[^>]+(?:data-src|data-original|src)=["\']([^"\']+)["\']', block, re.I)
            if pic_m:
                pic = pic_m.group(1).strip()
                if pic.startswith("//"):
                    pic = "https:" + pic
                elif pic.startswith("/"):
                    pic = urllib.parse.urljoin(self.siteUrl, pic)

            final_title = title or ("视频 %s" % vid)
            pack_id = "%s@@%s@@%s@@%s" % (vid, quote(final_title), quote(detail_path), quote(pic))

            duration = ""
            dur_m = re.search(r'(?:class=["\'][^"\']*(?:duration|time|length)[^"\']*["\'][^>]*>|>)\s*(\d{1,2}:\d{2}(?::\d{2})?)\s*<', block, re.I)
            if dur_m:
                duration = dur_m.group(1).strip()

            remarks = format_remarks(BRAND_NAME, duration)

            v_list.append({
                "vod_id": pack_id,
                "vod_name": final_title,
                "vod_pic": pic,
                "vod_remarks": remarks,
                "style": {"type": "rect", "ratio": 1.78}
            })

        return {
            "page": page_idx,
            "pagecount": page_idx + 1 if len(v_list) >= 20 else page_idx,
            "limit": len(v_list),
            "total": 9999,
            "list": v_list
        }

    def action(self, action):
        return {"msg": "ok"}

    def liveContent(self):
        return ""

    def localProxy(self, params):
        return [404, "text/plain; charset=utf-8", b"Proxy not configured"]