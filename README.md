# 盖塔机器人大决战 · 简体中文实验补丁源码

**Getter Robo Daikessen! (PS1 / SLPS-02232) — experimental Simplified Chinese translation and independent rebuild tools.**

本项目以机器翻译为基础，整理剧情、界面、人物与机体术语，并把中文字库和译文回填到日版游戏。当前对应 **v0.1.2-experimental**，供继续校对和修复；不是全流程验证的正式汉化版。

仓库包含 Python 提取、字体、回写和校验工具，最终译文、术语表、字体来源及许可、构建说明和验证记录。原盘、完整汉化镜像、原生解包资源、BIOS、模拟器和机器翻译缓存不在仓库中。

## 当前范围

- 已处理 1,885 类剧情、战斗及资源内名称文本，共 29,964 个位置，以及 963 处核心字段。
- 以机器翻译为基础，做过人名、机体名、武器名、界面、控制码和超长句的定向修订；没有完成逐句人工审校。
- 使用 1,450 个自定义中文字形，保留原日文字形和 12×12 字格。
- 结构检查包括字段预算、完整 EXE/VFS 读回、修改扇区 EDC/ECC，以及未修改原始扇区的一致性。

四处与资源增长有关的固定加载缓冲区已调整，字体指令经过独立检查。具体范围及限制见 [交付复核](docs/release_review_v0.1.2.md) 和 [字体检查](docs/font_review.md)。

## 已做运行测试

使用 SwanStation 软件渲染、解释器和 OpenBIOS，通过正常控制器输入检查了首章的部分流程：

- 从最终版冷启动，进入角色能力表、开场剧情、战术地图、武器及任务条件菜单。
- 正常触发学校过场，追加友军并返回地图。
- 敌方攻击演出、HP 变化和战斗后地图返回。
- 玩家主动选择武器攻击，敌方 HP 从 1520 降至 1200，显示 31 经验值并返回地图。
- 游戏内存档写入独立原生记忆卡；结束模拟器进程后，在新进程中通过游戏自身的“读取”菜单载入，战斗后 HP 数据保持。

模拟器即时状态只用于到达匹配版本的测试位置；存档结论来自游戏自身的记忆卡读写，不是把即时状态载入当作游戏读档。见 [追加测试报告](docs/extended_runtime_qa_v0.1.2.txt) 和 [详细验证记录](verification/extended_runtime_qa_v0.1.2.json)。

**仍有日文及其他未完成内容：**影片、部分图片文字、伤害位图 `ダメージ`、默认自定义姓名 `アキラ`、经验值提示中的混合姓名 `早乙女ミチル`，以及空存档槽的 `Empty`。部分机翻确认提示仍生硬。后续章节、全部分支、全部战斗情境和完整语义尚未验证。

## 本地重建

需要自行准备下列原始日版 BIN（或只含一个 BIN 的 ZIP）：

| 项目 | 值 |
| --- | --- |
| 游戏版本 | 日版原始 SLPS-02232 |
| BIN 大小 | 663,111,120 字节 |
| SHA256 | `08f189c914fa753af0ba690579712636f1d8b21eb7777c89b6fc10041c725807` |

建议 Python 3.11+、独立虚拟环境和至少 2 GiB 工作空间。所有命令从仓库根目录运行：

```sh
python3 -m venv .venv
# macOS / Linux
source .venv/bin/activate
python -m pip install -r requirements-build.txt

python -X utf8 tools/prepare_getter_source.py "/path/to/original.bin"
python -X utf8 tools/getter_font.py \
  --texts work/font/combined_reviewed.jsonl \
  --font incoming/Cubic11/Cubic_11.ttf \
  --output work/font/build-reviewed-v2 --write

python -X utf8 tools/build_getter_zh.py \
  --scenario-mt work/translation/scenario.zh_CN.reviewed.jsonl \
  --core-mt work/translation/core.zh_CN.reviewed.jsonl \
  --font-build work/font/build-reviewed-v2 \
  --vfs-lookup-proof verification/vfs_lookup_proof.json \
  --version v0.1.2-experimental --report work/rebuild/dryrun.json
```

先看干运行报告，再按 [完整重建说明](README_中文.txt) 使用 `--write` 生成新的输出目录。输入原盘保持不变；已有输出目录不会被覆盖。

未改动本版译文和构建输入时，目标 BIN 为 692,250,048 字节，SHA256：

```text
855f4a1581f9509340f57b0ccb43170a1b3db7c0513c11d1db0f029a48ffe8cf
```

变更译文、字体或代码后必须重新校验、另设版本和目标哈希。离线重建无需再次请求机器翻译服务。`tools/translate_corpus.py` 是可选的联网翻译工具，会向外部服务发送待译文本；见 [翻译流程](docs/translation_pipeline.md)。

## 继续校对与贡献

1. 公开的 `work/translation/*reviewed.jsonl` 只保留 `id`、`zh_CN`、`source_text_sha256`，以及可选的 `review`。原始日文、原始字节、预算、偏移和全部出现位置从自己的原盘在本地重新提取，不随公开译文重复分发。修改 `zh_CN` 时保留 ID 和源文哈希，并记录章节、理由及截图。
2. 人物、机体、武器等专名先核对 `work/glossary/` 的条目与依据，区分通行译名和暂定译名。
3. 新增字符要同步更新 `work/font/combined_reviewed.jsonl`，重新生成字库并完整重建，不能只替换旧镜像中的字形编号。
4. 让字段预算、控制码和资源大小检查通过，并用正常游戏操作回归相应场景。不要绕过隐藏口令或内部引用字段保护，也不要截断文本来消除溢出。

提交问题或修订时请附版本、目标 SHA256、模拟器/固件配置、章节和操作步骤。不要提交原盘、BIOS、完整镜像或原生解包资源。

`source_text_sha256` 是本地权威语料中原始 `ja` 字符串按 UTF-8 编码的 SHA256。构建器会核对这一绑定，随后始终使用本地提取的字段预算、原始字节及出现位置，并根据本地原文验证控制码和 printf 占位符。它仍兼容历史上含 `ja` 的本地译文格式，但公开提交请使用紧凑格式。重新运行按日文匹配的修订或联网翻译脚本时，应使用本地提取语料；不要为此把完整源文和字节元数据补回公开文件。

可选的诊断/录制源码是 `tools/qa_getter.py`、`tools/qa_save_frontend.py`、`tools/record_getter.py` 和 `getter_core_log.c`。模拟器核心、固件、FFmpeg 及编译出的动态库须自行配置；见 [开发测试与录屏](docs/developer_qa.md)。

## 许可与来源

- 字体来源及原许可保留在 [`incoming/Cubic11/OFL.txt`](incoming/Cubic11/OFL.txt) 和 [`incoming/WenQuanYi/`](incoming/WenQuanYi/)。文泉驿包含 GPL v2 或更新版本及字体嵌入例外。
- 当前没有为本项目自编工具和译文另行选择统一开源许可证；公开可读不等于授予任意再许可。本仓库不对原游戏内容或第三方字体主张所有权。
- 原游戏、角色及其他原始内容的权利归各权利人。第三方韩文补丁的译文和字库未纳入本项目；[研究线索](docs/korean_patch_source.md)不构成移植许可。

`SOURCE_FILES.sha256.json` 是这次公开源码树的文件清单，清单自身不参与其哈希列表。`verification/` 内部分报告是构建或特定测试时的快照，不代表全游戏已验证。

## English summary

This repository contains an experimental machine-assisted Simplified Chinese translation, reviewed terminology, font sources/notices, and independently written extraction/rebuild/validation tools for the original Japanese PS1 release SLPS-02232. The opening chapter has bounded UI, story, enemy/player combat and native memory-card save/load checks. FMVs, some graphics/names and other content remain untranslated; later routes and full linguistic proofreading are incomplete. Supply your own matching original image locally. No game image, native extracted assets, BIOS or emulator is included. See the license/source notes above before reuse.
