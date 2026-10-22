#!/usr/bin/env python3
"""Concise manual review for the second half of overflowing scenario fields."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1]
R=json.loads((ROOT/'work/translation/scenario.remaining_overflow.draft.json').read_text())
T={
86:'$f59a$s00%2昆虫军团%0$s13「$s30你们……$s80$s13$s80$s13$s30嘎嘎……$s80$s13$s30永远别想$s80$s13$s30踏入宇宙！」',
87:'$f59a$s00%2昆虫军团%0$s13「$s30嘎嘎……$s80$s13$s80$s13$s30这只是……$s80$s13$s30开始！」',
88:'$f59a$s80$s13$s30嘎嘎…$s80$s13$s80$s13$s80$s13$s30战斗将$s80$s13$s80$s13$s30继续…',
89:'$f59a$s30人类…$s80$s13$s30叽$s80$s13$s30叽……$s80$s13$s80$s13$s80$s13$s30灭绝！」',
90:'$m13b$s00%2シャトナー%0$s13「街道…$s80$s13$s05我的街道…！」',
91:'$f21a$s00%2早乙女%0$s13「……这确实$s80$s13不是普通的龙卷风。',
92:'$f28d$s00%2俄军兵A%0$s13「$s80$s13$s05！」',
93:'$f29a$s00%2俄军兵B%0$s13「$s05！……」',
94:'$f30a$s00%2俄军司令%0$s13「$s80$s13$s05……好！$s80$s13$s05开始变形倒数！」',
95:'$f32e$s00%2改造高尔%0$s13「$s05！……什么！？$s80$s13$s80$s13$s80$s13$s05…我、$s80$s13我究竟……！？',
96:'$m05b$s00%2翔%0$s13「$s05唔……！」',
97:'$m61b$s00%2$n%0$s13「……威力超乎想象！」',
98:'$m06d$s00%2凯%0$s13「$s05唔……$s80$s13太刺眼，什么都看不见……$s80$s13$s05敌人怎样了！？$s80$s13$s05高尔呢！？」',
99:'$f50a$s13…来…$s80$s13$s80$s13鬼！」',
100:'$f19a$s00%2舰长%0$s13「$s20好！$s80$s13$s80$s13$s20阿拉斯加战线的最大决战开始了！」',
101:'$f19a$s00%2舰长%0$s13「$s05ジャック没事吧！」',
102:'$f19a$s00%2舰长%0$s13「还剩2时51分」',
103:'$f19a$s00%2舰长%0$s13「…$s80$s13$s05做得到吗？」',
104:'$m00d$s00%2龙马%0$s13「$s05交给我！」',
105:'$m05d$s00%2翔%0$s13「前方，$s80$s13休想再迈出一步！」',
106:'$f48b$s00%2罗刹%0$s13「$s80$s13$s05怎么回事！」',
107:'$s13%2结局动画1。在北极，却不知为何升起了朝阳……',
108:'$m01b$s00%2隼人%0$s13「简直像在赤道……\\n$s80$s13虽说地轴偏移，这种大气异常仍很反常……」',
109:'$m02b$s00%2武藏%0$s13「$s80$s13$s05什么！$s80$s13$s05那巨大的黑影是！？」',
110:'$m05b$s00%2翔%0$s13「$s05什么!?」',
111:'$f50a$s00%2兰多%0$s13「$s80$s13这声音……$s80$s13橘博士……$/好久不见……你还活着啊……」',
112:'$f00a$s00%2龙马%0$s13「博士，$s80$s13这艘船究竟是！？」',
113:'$f02a$s00%2武藏%0$s13「可是$s80$s13怎么又是$s80$s13宇宙飞船……\\n！？」',
114:'$f06b$s00%2凯%0$s13「怎么可能！」',
115:'$f18f$s00%2枫%0$s13「$s05虫啊！」',
116:'$f21b$s00%2早乙女%0$s13「$s05怎么了！？」',
117:'$f17b$s00%2椿%0$s13「难、$s80$s13$s05难道……」',
118:'$m02b$s00%2武藏%0$s13「这声音！$s80$s13是刚才的头目！？」',
119:'$m04b$s00%2号%0$s13「$s05几百年后！？」',
120:'$f54a$s00%2ギィムバグ%0$s13「$s20在这里，$s80$s13$s20这个空间、$s80$s13$s20这个时间就能赢！',
121:'$f54d$s00%2ギィムバグ%0$s13「$s05没用！$s80$s13$s05没用！$s80$s13没用！$s80$s13$s20压倒性力量！$s80$s13$s20面对战力差距，$s80$s13$s20尽管惊愕吧！」',
122:'$m06d$s00%2凯%0$s13「$s20可恶！$s80$s13$s80$s13这么多敌人，就没办法了吗！」',
123:'为对抗「恐龙帝国」而制造、正在测试的新型盖塔机器人。',
124:'历经恶战的各型盖塔机器人。',
125:'爬虫兵A',126:'爬虫兵B',127:'百鬼兵A',128:'百鬼兵B',129:'角冲锋',130:'颈突刺',131:'护卫机发射',132:'铁棒殴击',133:'破坏立足',134:'针冲锋',135:'亚空之玉',136:'蛇旋光！',137:'修罗爆雷！',
138:'热血沸腾了！！',139:'来吧！上啊！',140:'可恶，竟在这里被击败……',141:'喝啊啊啊！',142:'唔！！',143:'呼……呼……',
144:'看见了吧！机器人就该这样用！',145:'呜…呜…。',146:'敢小看我这老头，就让你吃苦头！',147:'……可恶，竟要死在这种地方。',148:'真顽强的家伙！',
149:'Oh！和哥哥联手就无敌最强！',150:'呀啊啊啊！！',151:'……怎、怎么会……我大意了！',152:'唔…！！',153:'唔！',154:'可恶！',155:'龙卷投掷！',156:'空间飞翔！',
157:'……我、我们的青春啊！！',158:'爬虫兵A',159:'咕嘎啊啊啊！',160:'爬虫兵B',161:'百鬼兵A',162:'百鬼兵B',163:'……怎么会，我、我竟败给这群废物……',
164:'唔…',165:'妨碍我们的家伙，杀无赦！',166:'可恶…',168:'蚁地狱',169:'呜…呜…',170:'……怎、怎么会……我大意了',
}
if len(R)!=171:raise ValueError('Unexpected overflow set')
from getter_font import make_plan,encode
from translate_corpus import control_pattern
out={};errors=[]
for index,target in T.items():
 r=R[index];p=make_plan([target]);size=len(encode(target,p));row={'controls':[]}
 # Exact game-command matching is independently enforced by the assembler.
 pattern=control_pattern({'controls':[]})
 if pattern.findall(r['ja'])!=pattern.findall(target):errors.append({'index':index,'reason':'controls','ja':pattern.findall(r['ja']),'zh':pattern.findall(target)})
 if size>r['budget']:errors.append({'index':index,'reason':'budget','size':size,'budget':r['budget']})
 out[r['id']]=target
(ROOT/'work/glossary/scenario_short_review_B.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
(ROOT/'work/glossary/scenario_short_review_B.report.json').write_text(json.dumps({'reviewed':len(out),'errors':errors,'excluded_binary_candidate':'getter_f3736888e17ebef4c534'},ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'reviewed':len(out),'errors':errors},ensure_ascii=False))
