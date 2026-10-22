#!/usr/bin/env python3
"""Build the independently researched Getter Daikessen Chinese glossary."""
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    'ak_chars': {'url': 'https://akurasu.net/wiki/Getter_Robo:_Daikessen!/Characters', 'role': 'Game-specific playable character identities; Japanese and English spellings'},
    'ak_units': {'url': 'https://akurasu.net/wiki/Getter_Robo:_Daikessen!/Units', 'role': 'Game-specific units and form identities'},
    'jp_game': {'url': 'https://srw.wiki.cre.jp/wiki/ゲッターロボ大決戦!', 'role': 'Game-specific cast, factions, pilot abilities and differences from other Getter/SRW games'},
    'faq': {'url': 'https://gamefaqs.gamespot.com/ps/575892-getter-robo-daikessen/faqs/5126', 'role': 'PS1 game-specific units and weapons; romanization is not authoritative Japanese orthography'},
    'bili': {'url': 'https://www.bilibili.com/bangumi/media/md2352/', 'role': 'Licensed mainland Chinese Getter series and character usage'},
    'cn_collab': {'url': 'https://www.taptap.cn/moment/750110259372099156', 'role': 'Licensed Chinese Getter collaboration usage; names only, not this game mechanics'},
    'cn_collab2': {'url': 'https://www.taptap.cn/moment/760247527227263278', 'role': 'Licensed Chinese usage including 车弁庆, 盖塔皇帝, 盖塔射线 and 闪光烈阳弹'},
    'gou_cn': {'url': 'https://bgm.tv/character/99254', 'role': 'Secondary mainland usage of 一文字号'},
    'gai_jp': {'url': 'https://srw.wiki.cre.jp/wiki/大道剴', 'role': 'Original Japanese spelling is 大道剴'},
    'gai_oldcn': {'url': 'https://bbs.newwise.com/thread-382800-1-1.html', 'role': 'Secondary older Chinese usage 大道凯; not an official Chinese naming source'},
    'zan': {'url': 'https://w.atwiki.jp/aniwotawiki/pages/6331.html', 'role': 'Japanese original Zan team names 水樹茜, 秋山椿, 柴崎楓'},
    'cn_liger': {'url': 'https://jiangsheng.net/build/html/games/srw4/units/getter_robo.html', 'role': 'Secondary Chinese convention 盖塔狮虎; not Daikessen mechanics'},
    'cn_poseidon': {'url': 'https://jiangsheng.net/build/html/games/srw4/units/unit_data_ps.html', 'role': 'Secondary Chinese conventions 盖塔狮虎 and 盖塔海皇'},
    'cn_weapons': {'url': 'https://bkso.baidu.com/item/真盖塔机器人世界最后之日/9269799', 'role': 'Secondary Chinese weapon-name conventions; no claim of official Daikessen localization'},
}
entries = []

def add(category, ja, zh, en=None, status='project_translation', presence=None,
        translation=None, alternatives=None, notes='', auto=True, ja_verified=True):
    entry = {
        'id': f'{category}_{sum(e["category"] == category for e in entries)+1:03d}',
        'category': category, 'ja': ja, 'en': en, 'zh_CN': zh,
        'alternatives': alternatives or [], 'status': status,
        'presence_sources': presence or [], 'translation_sources': translation or [],
        'notes': notes, 'auto_eligible': auto and status != 'provisional',
        'ja_field_verified': ja_verified,
    }
    entries.append(entry)

def rows(category, data, presence, status='project_translation', translation=None):
    for line in data.strip().splitlines():
        ja, zh, *en = line.split('|')
        add(category, ja, zh, en[0] if en else None, status, presence, translation)

add('character', 'アキラ', '阿基拉', 'Akira', 'provisional', ['ak_chars', 'jp_game'], notes='可自定义名的男主角；音译仅作占位，不虚构汉字姓名。', auto=False)
add('character', 'ケイ', '凯', 'Kei', 'provisional', ['ak_chars', 'jp_game'], notes='可自定义名的女主角；不自动改成早乙女溪或南风溪。', auto=False)
rows('character', '''流竜馬|流龙马|Ryouma Nagare
神隼人|神隼人|Hayato Jin
巴武蔵|巴武藏|Musashi Tomoe
早乙女達人|早乙女达人|Tatsuhito Saotome''', ['ak_chars', 'jp_game'], 'licensed_cn_usage', ['bili'])
add('character', '車弁慶', '车弁庆', 'Benkei Kuruma', 'licensed_cn_usage', ['jp_game'], ['cn_collab2'])
add('character', '早乙女ミチル', '早乙女美智流', 'Michiru Saotome', 'provisional', ['ak_chars', 'jp_game'], alternatives=['早乙女美智琉', '早乙女米琪露'], notes='日文身份已确认；简中存在多种音译，暂用项目译名，待用户或既有字幕规范确定。', auto=False)
add('character', '早乙女博士', '早乙女博士', 'Professor Saotome', 'licensed_cn_usage', ['jp_game'], ['cn_collab'])
add('character', '一文字號', '一文字号', 'Gou Ichimonji', 'common_zh', ['ak_chars', 'jp_game'], ['gou_cn'])
rows('character', '''橘翔|橘翔|Shou Tachibana
古田|古田|Furuta
橘博士|橘博士|Professor Tachibana
水樹茜|水树茜|Akane Mizuki
秋山椿|秋山椿|Tsubaki Akiyama
柴崎楓|柴崎枫|Kaede Shibasaki
橘信一|橘信一|Shinichi Tachibana
竜二|龙二|Ryuji''', ['jp_game'], 'kanji_simplification', ['jp_game', 'zan'])
add('character', '大道剴', '大道剀', 'Gai Daidou', 'provisional', ['ak_chars', 'jp_game'], ['gai_jp', 'gai_oldcn'], ['大道凯'], '剴的规范简体为剀；旧汉化常用凯。未确认授权简中译名，自动表暂不应用。', False)
for ja, zh, en in [
    ('ジャック・キング', '杰克·金', 'Jack King'),
    ('メリー・キング', '玛丽·金', 'Mary King'),
    ('シュワルツ', '施瓦茨', 'Schwartz Koff'),
    ('ジョン・ランバート', '约翰·兰伯特', 'John Lambert'),
    ('ボブ・ホスナー', '鲍勃·霍斯纳', 'Bob Hosner'),
    ('サム・ホスナー', '萨姆·霍斯纳', 'Sam Hosner'),
    ('リンダ・ティラミス', '琳达·提拉米斯', 'Linda Tiramisu'),
    ('ヒム・シャトナー', '希姆·沙特纳', 'Heim Shatner'),
]:
    add('character', ja, zh, en, 'provisional', ['ak_chars', 'jp_game'], notes='角色确实登场；中文音译为项目占位，未找到授权简中命名。', auto=False)
add('character', 'テキサス艦長', '得克萨斯舰长', 'Captain Texas', presence=['ak_chars', 'jp_game'], notes='职务称呼，Texas统一译为得克萨斯。')
rows('character', '''地底魔王ゴール|地底魔王高尔|Emperor Gore
バット将軍|巴特将军|General Bat
キャプテン・ニオン|尼昂队长|Captain Nion
ブライ大帝|布莱大帝|Emperor Burai
プロフェッサーランドウ|兰多教授|Professor Rando
ラセツ男爵|罗刹男爵|Baron Rasetsu
改造ゴール|改造高尔|Modified Gore
改造バット将軍|改造巴特将军|Modified General Bat
改造ブライ|改造布莱|Modified Burai
ギィムバグ軍曹|吉姆巴格军曹|Sergeant Giimubagu''', ['jp_game'])
entries[-5]['notes'] = '本作称男爵，不能套用其他作品的罗刹伯爵。'
entries[-1]['status'] = 'provisional'
entries[-1]['auto_eligible'] = False
entries[-1]['notes'] = '本作最终敌人；中文音译为临时项目译名。'

rows('unit', '''イーグル号|雄鹰号|Eagle
ジャガー号|猎豹号|Jaguar
ベアー号|巨熊号|Bear
ゲッター1|盖塔1|Getter 1
ゲッター2|盖塔2|Getter 2
ゲッター3|盖塔3|Getter 3
ゲッター1+2|盖塔1+2|Getter 1+2
ゲッター2+3|盖塔2+3|Getter 2+3
ゲッター3+1|盖塔3+1|Getter 3+1
ドラゴン号|飞龙号|Dragon
ライガー号|狮虎号|Liger
ポセイドン号|波塞冬号|Poseidon
ゲッタードラゴン|盖塔龙|Getter Dragon
ゲットマシン１|盖塔战机1|Get Machine 1
ゲットマシン２|盖塔战机2|Get Machine 2
ゲットマシン３|盖塔战机3|Get Machine 3
ゲッター號|盖塔号|Getter Go
ゲッター翔|盖塔翔|Getter Sho
スーパーゲッター號|超级盖塔号|Super Getter Go
真イーグル号|真雄鹰号|Shin Eagle
真ジャガー号|真猎豹号|Shin Jaguar
真ベアー号|真巨熊号|Shin Bear
真ゲッター1|真盖塔1|Shin Getter 1
真ゲッター2|真盖塔2|Shin Getter 2
真ゲッター3|真盖塔3|Shin Getter 3
烈火号|烈火号|Rekka
紫電号|紫电号|Shiden
金剛号|金刚号|Kongou
ゲッター烈火|盖塔烈火|Getter Rekka
ゲッター紫電|盖塔紫电|Getter Shiden
ゲッター金剛|盖塔金刚|Getter Kongou
BT-23|BT-23|BT-23
レディコマンド|女郎指挥艇|Lady Command
テキサスマック|得克萨斯马克|Texas Mack
ステルバーα04|斯特尔巴α04|Stelber Alpha 04
ロボストーンT520|罗博斯通T520|Robostone T520
キングダム007|王国007|Kingdom 007
グスタフH24|古斯塔夫H24|Gustav H24
大型移動艦テキサス|大型移动舰得克萨斯|Texas
ボルガ80000|伏尔加80000|Volga 80000''', ['ak_units', 'jp_game'])
for e in entries:
    if e['ja'] in ('レディコマンド', 'テキサスマック', 'ステルバーα04', 'ロボストーンT520',
                    'キングダム007', 'グスタフH24', 'ボルガ80000'):
        e['status'] = 'provisional'
        e['auto_eligible'] = False
        e['notes'] = '单位身份及编号已核对；中文名为项目候选，未确认授权或稳定通行译名，暂不自动替换。'
add('unit', 'ゲッターライガー', '盖塔狮虎', 'Getter Liger', 'common_zh', ['ak_units'], ['cn_liger'], ['盖塔莱卡'])
add('unit', 'ゲッターポセイドン', '盖塔波塞冬', 'Getter Poseidon', 'project_translation', ['ak_units'], ['cn_poseidon'], ['盖塔海皇', '盖塔海神'], '本项目采用波塞冬以与战机名一致；海皇、海神为常见旧译。')
add('unit', 'ゲッター剴', '盖塔剀', 'Getter Gai', 'provisional', ['ak_units'], ['gai_jp', 'gai_oldcn'], ['盖塔凯'], '和大道剴相同的剴/剀/凯命名选择，暂不自动替换。', False)
add('unit', 'ブラックゲッター', '黑盖塔', 'Black Getter', 'licensed_cn_usage', ['ak_units', 'jp_game'], ['cn_collab'], notes='本作是备用零件组合的原创混合机，不自动套用OVA黑盖塔的设定。')
add('unit', 'ゲッターエンペラー', '盖塔皇帝', 'Getter Emperor', 'licensed_cn_usage', ['ak_units', 'jp_game'], ['cn_collab2'])
add('unit', '真ゲッタードラゴン', '真盖塔龙', 'Shin Getter Dragon', 'licensed_cn_usage', ['ak_units', 'jp_game'], ['cn_collab'], ['真龙'], '本作是人型最终阶段机，不自动缩成OVA形态称呼真龙。')
add('unit', 'クジラ2005D', '鲸鱼2005D', 'Kujira 2500D', 'provisional', ['ak_units', 'faq'], alternatives=['クジラ', 'Kujira 20051D'], notes='来源有2005D / 2500D / 20051D冲突；等待原盘确认型号。禁止自动替换或修正数字。', auto=False)

# Weapon identities occur in the PS1 guide. Japanese spellings below are
# standardized franchise forms; verify their exact in-disc spelling first.
weapon_rows = '''ゲッターカッター|盖塔切割刃|Getter Cutter
ゲッタートマホーク|盖塔战斧|Getter Tomahawk
トマホークブーメラン|战斧回旋镖|Tomahawk Boomerang
ゲッターマシンガン|盖塔机枪|Getter Machinegun
ゲッタービーム|盖塔射线|Getter Beam
ドリルアーム|钻头臂|Drill Arm
ゲッターアーム|盖塔臂|Getter Arm
ジェットドリル|喷射钻头|Jet Drill
ドリルストーム|钻头风暴|Drill Storm
ゲッタービジョン|盖塔幻影|Getter Vision
ゲッタースマッシュ|盖塔重击|Getter Smash
ゲッタークラッシュ|盖塔冲撞|Getter Crash
ゲッターミサイル|盖塔导弹|Getter Missile
大雪山おろし|大雪山崩落|Daisetsuzan Oroshi
ダブルトマホーク|双重战斧|Double Tomahawk
スピンカッター|旋转切割刃|Spin Cutter
マグフォースサンダー|磁力雷霆|Magforce Thunder
ソードトマホーク|剑刃战斧|Sword Tomahawk
ストリングアタック|钢索攻击|String Attack
ブレストボンバー|胸部爆弹|Breast Bomber
トルネードアタック|龙卷攻击|Tornado Attack
ハープーンキャノン|鱼叉炮|Harpoon Cannon
ブレストビーム|胸部光束|Breast Beam
インパクトキャノン|冲击炮|Impact Cannon
真ゲッタートマホーク|真盖塔战斧|Shin Getter Tomahawk
真ゲッタービーム|真盖塔射线|Shin Getter Beam
ストナーサンシャイン|闪光烈阳弹|Stoner Sunshine
真ゲッタービジョン|真盖塔幻影|Shin Getter Vision
真大雪山おろし|真大雪山崩落|Shin Daisetsuzan Oroshi
暗黒乱舞|暗黑乱舞|Ankoku Ranbu
真シャインスパーク|真闪光爆烈|Shin Shine Spark
エンペラービーム|皇帝射线|Emperor Beam'''
for line in weapon_rows.splitlines():
    ja, zh, en = line.split('|')
    trans = []
    status = 'project_translation'
    if en in ('Getter Beam', 'Shin Getter Beam'):
        status, trans = 'licensed_cn_usage', ['cn_collab2']
    elif en == 'Stoner Sunshine':
        status, trans = 'licensed_cn_usage', ['cn_collab2']
    elif 'Daisetsuzan' in en or en == 'Shin Shine Spark':
        status, trans = 'common_zh', ['cn_weapons']
    add('weapon', ja, zh, en, status, ['faq'], trans,
        notes='武器身份见本作攻略；日文为标准化名称，原盘精确拼写尚待核对。仅用英文完整字段匹配，日文字段暂不自动应用。', ja_verified=False)
for e in entries:
    if e['en'] == 'Getter Vision':
        e['notes'] += ' 本作是武器，不能按机战系列的被动分身技能处理。'
    if e['en'] == 'Getter Beam':
        e['notes'] += ' 本作通常为直线地图攻击；保留原控制码与攻击属性。'
    if 'Daisetsuzan' in (e['en'] or ''):
        e['notes'] += ' 与武藏或弁庆驾驶条件有关；词表不改变使用条件。'

rows('ability', '''反撃|反击|Counterattack
2回移動|二次移动|Move Twice
自爆|自爆|Self-Destruct
偵察|侦察|Reconnaissance
HP回復|HP回复|HP Recovery
復活|复活|Revival
移動補助|移动辅助|Movement Support
補修|修复|Repair
収集|收集|Collect
交換|交换|Swap
クリティカル|暴击|Critical
EN回復|EN回复|EN Recovery
逆境|逆境|Adversity
我慢|忍耐|Endure
移動溜め|移动蓄力|Movement Charge''', ['jp_game'])
for e in entries:
    if e['category'] == 'ability':
        e['notes'] = '本作的驾驶员「能力」，不当作通用机战精神指令。'
    if e['ja'] == '2回移動':
        e['notes'] += ' 隼人的二次移动在该回合不能攻击；不能翻译成二次行动。'
    if e['ja'] == '復活':
        e['notes'] += ' 一文字号的能力为自身复活，不擅加复活友军含义。'
    if e['ja'] == '収集':
        e['notes'] += ' 水树茜的能力提高盖塔动力单位自动EN回复，不误译成拾取物品。'
    if e['ja'] == '交換':
        e['notes'] += ' 柴崎枫与友军交换位置。'

rows('organization', '''恐竜帝国|恐龙帝国|Dinosaur Empire
百鬼帝国|百鬼帝国|Hundred Demon Empire
昆虫軍団|昆虫军团|Insect Army
ハチュウ人類|爬虫人类|Reptilian Humanoids
早乙女研究所|早乙女研究所|Saotome Laboratory
橘研究所|橘研究所|Tachibana Laboratory''', ['jp_game'], 'kanji_simplification')
rows('term', '''ゲッター線|盖塔射线|Getter Rays
反ゲッター線|反盖塔射线|Anti-Getter Rays
ゲッターエネルギー|盖塔能量|Getter Energy
能力|能力|Ability''', ['jp_game'])
entries[-2]['notes'] = '保留GE与EN的区分；不得把所有能量字段互换。'

# These are translation conventions, not claims of extracted UI coverage.
for ja, zh, en in [('移動','移动','Move'),('攻撃','攻击','Attack'),('防御','防御','Defend'),
                    ('回避','回避','Evade'),('待機','待机','Wait'),('射程','射程','Range'),
                    ('命中','命中','Hit'),('地形','地形','Terrain')]:
    add('ui', ja, zh, en, presence=[], notes='界面用语约定；尚未从原盘确认该完整字段的出现。', auto=False)

exact = {}
for e in entries:
    if not e['auto_eligible']:
        continue
    aliases = [e['en']]
    if e['ja_field_verified']:
        aliases.append(e['ja'])
    for alias in aliases:
        if alias:
            if alias in exact and exact[alias] != e['zh_CN']:
                raise ValueError(f'Ambiguous complete-field alias: {alias}')
            exact[alias] = e['zh_CN']

doc = {
    'game': 'Getter Robo Daikessen!', 'product_id': 'SLPS-02232',
    'language': 'zh-CN', 'version': '0.1-research', 'date': '2026-10-22',
    'scope': 'Entity glossary and UI conventions; not a full scenario translation or proof of in-disc text extraction.',
    'matching_rule': 'Exact complete-field entity matching only after identifying field type; never blind English/Japanese substring replacement.',
    'sources': SOURCES, 'entries': entries, 'exact_field_map': exact,
    'protected_tokens': ['BT-23', 'α04', 'T520', '007', 'H24', '80000', 'HP', 'EN', 'GE'],
    'counts': {'entries': len(entries), 'by_category': dict(Counter(e['category'] for e in entries)),
               'by_status': dict(Counter(e['status'] for e in entries)),
               'auto_eligible_entries': sum(e['auto_eligible'] for e in entries),
               'exact_field_aliases': len(exact)},
}
assert 100 <= len(entries) <= 200
assert len({e['id'] for e in entries}) == len(entries)
assert len({e['ja'] for e in entries}) == len(entries)
for e in entries:
    assert e['zh_CN']
    assert set(e['presence_sources'] + e['translation_sources']) <= SOURCES.keys()
    assert e['status'] != 'provisional' or not e['auto_eligible']
for key in ('アキラ', 'ケイ', '大道剴', 'ゲッター剴', 'クジラ2005D', 'Kujira 2500D', 'Kujira 20051D'):
    assert key not in exact
for key in ('流竜馬', '神隼人', '巴武蔵', '水樹茜', '秋山椿', '柴崎楓', '一文字號'):
    assert key in exact
assert 'ゲッタービーム' not in exact  # Exact Japanese in-disc field is unverified.
out = ROOT / 'work/glossary/canonical_zh.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(doc['counts'], ensure_ascii=False))
print('sha256', hashlib.sha256(out.read_bytes()).hexdigest())
