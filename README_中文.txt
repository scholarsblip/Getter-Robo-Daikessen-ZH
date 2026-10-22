《盖塔机器人大决战！》v0.1.2 简体中文实验补丁源码包

本包供继续审校、修复字形和重建实验补丁。包含最终 reviewed 中文语料、术语及逐行修订表、提取/编码/回写工具、字体源文件及许可、小型验证记录。没有原盘、BIN/CUE、原生 VFS/PAC/图片资源、BIOS、模拟器、旧版原型或机器翻译缓存。原生资源须从自己准备的原盘在本地提取。

本包对应 1885 类剧情/战斗/资源内名称文本、29964 个实际文本位置和 963 处核心字段。机器翻译后只做了定向审核；未完成逐句审校、位图及影片文字汉化、全部战斗与全流程验证。当前状态请先看 README.md、docs/extended_runtime_qa_v0.1.2.txt 和 docs/PATCH_README_中文.txt；部分 verification 记录是较早的验证快照。

支持的原盘

SLPS-02232 日版原始 MODE2/2352 BIN
大小：663111120 字节
SHA256：08f189c914fa753af0ba690579712636f1d8b21eb7777c89b6fc10041c725807

所有命令从解压后的源码根目录执行。建议使用 Python 3.11 或更新版本和独立虚拟环境；补丁应用助手本身最低支持 Python 3.9。完整提取、依赖与新镜像请预留至少 2 GiB 空间。下例中的原盘路径需替换成实际路径。

1. 安装构建依赖

python3 -m venv .venv

macOS/Linux 激活：source .venv/bin/activate
Windows PowerShell 激活：.venv\Scripts\Activate.ps1

python -m pip install -r requirements-build.txt

纯提取、补丁应用及控制码检查只使用 Python 标准库；生成字体需要 NumPy 和 Pillow。离线重建不需再调用翻译服务。命令中的 -X utf8 可确保 Windows 上也按 UTF-8 读取中文语料。

2. 准备本地原生资源（不修改输入原盘）

只校验、不写入：
python -X utf8 tools/prepare_getter_source.py "/路径/日版原盘.bin" --verify-only

完整准备：
python -X utf8 tools/prepare_getter_source.py "/路径/日版原盘.bin"

也接受只含一个 BIN 的 ZIP。工具创建全新的 work/source，校验原盘和 ISO 核心文件，提取 VFS/PAC，重新生成权威 core/scenario 语料，并与 verification/reference_source_corpora.json 对比。已有 work/source 时拒绝覆盖；需要重做时请先自行备份并换走旧目录。中途出错会清理此次独立暂存目录。原盘保持原样。

字体工具按源码根目录读取 work/source，因此直接使用上述默认输出位置。

3. 生成字体 v2

python -X utf8 tools/getter_font.py --texts work/font/combined_reviewed.jsonl --font incoming/Cubic11/Cubic_11.ttf --output work/font/build-reviewed-v2 --write

combined_reviewed.jsonl 是本版确定字形编号的输入。Cubic11 缺失的六个字形从随包文泉驿 12px BDF 读取。若修改译文，请同步更新此文件，确保全部新增字符入表。可将两份 reviewed JSONL 中的 id 和 zh_CN 重新汇集后生成一个新的字体输入，再全面重建；不要在已有镜像里只替换字形编号。

可选的独立字体指令检查（需先完成上述原盘和字体准备）：
python -X utf8 tools/review_font_hook.py
报告写入 verification/font_v2_review.generated.json。该检查模拟 MIPS 分支/加载延迟及启动 BSS 清零，不能代替真实 GPU、模拟器或整场游戏测试。

4. 检查并重建新镜像

先做干运行：
python -X utf8 tools/build_getter_zh.py --scenario-mt work/translation/scenario.zh_CN.reviewed.jsonl --core-mt work/translation/core.zh_CN.reviewed.jsonl --font-build work/font/build-reviewed-v2 --vfs-lookup-proof verification/vfs_lookup_proof.json --version v0.1.2-experimental --report work/rebuild/dryrun.json

确认报告后写入独立新目录：
python -X utf8 tools/build_getter_zh.py --scenario-mt work/translation/scenario.zh_CN.reviewed.jsonl --core-mt work/translation/core.zh_CN.reviewed.jsonl --font-build work/font/build-reviewed-v2 --vfs-lookup-proof verification/vfs_lookup_proof.json --version v0.1.2-experimental --output work/output/rebuilt-v0.1.2 --write

工具默认只做干运行；--write 才生成镜像。输出目录必须不存在。使用生成的 CUE 启动。最终目标 BIN 应为 692250048 字节，SHA256：
855f4a1581f9509340f57b0ccb43170a1b3db7c0513c11d1db0f029a48ffe8cf

verification/font_plan.v0.1.2.json 记录本版字形映射；verification/build_summary_v0.1.2.json 保留最终构建关键检查。全量构建清单会在重建输出目录生成。若改动译文、字体或代码，目标哈希也会变化，必须重新检查并另设版本，不能继续冒用此哈希。

可选：使用自己准备的 xdelta3 制作差分

xdelta3 -e -s work/source/original.bin work/output/rebuilt-v0.1.2/Getter_Robo_Daikessen_ZH_v0.1.2-experimental.bin Getter_Robo_Daikessen_ZH_custom.xdelta

分享时只分享差分、源码和说明。相应 patch_manifest.json 必须使用实际原盘、补丁和目标文件的大小及 SHA256，配合 tools/apply_getter_patch.py 的完整回放验证；不要把原盘、BIOS、原生解包目录或生成的完整镜像推到代码仓库。

继续修改时

work/translation/*reviewed.jsonl 是本版实际构建输入，公开格式只含 id、zh_CN、source_text_sha256（可选 review）。source_text_sha256 是本地权威 ja 字符串按 UTF-8 编码的 SHA256。原始日文、偏移、控制码、原始预算、字节和出现位置从自己的原盘重新提取，保留在忽略的 work/source/。仅修改 zh_CN 并记录原因，不要更改 ID 或源文哈希来绕过验证。构建器核对哈希后使用本地原始元数据，并兼容历史含 ja 的本地格式。work/glossary/ 内保留官方/通行/项目/暂定名称和定向人工修订依据。临时音译不冒称官方名称。

げんき 隐藏口令和两处 ななし 默认姓名是参与原程序判断的原始字符串，构建器强制保留；有内部指针歧义的字段也保留。不要绕过此保护来提高表面覆盖率。新增字形、超长句、控制码位置、PAC 大小变化和缓冲区修订都需要重新检查；当前缓冲区上限只对已审查的增长范围有效。

tools/translate_corpus.py 提供可恢复的 Google 公共接口机器翻译，用于后续重新翻译，不是重建所必需。它会向外部服务发送待翻译的普通文本，服务可限速或失效。使用方法及审校限制见 docs/translation_pipeline.md、docs/mt_v3_audit.md。

tools/qa_getter.py 与 getter_core_log.c 是可选的开发诊断源文件；没有随包运行时或编译动态库。其历史目录、平台及模拟器选项需要根据自己的环境配置，不能据此认定完整游戏已通过测试。历史开发路径已整理为项目相对路径；实际构建路径由工具相对源码根目录确定。

许可及来源

Cubic11：incoming/Cubic11/OFL.txt（SIL OFL 1.1）。
文泉驿：incoming/WenQuanYi/COPYING、README（GPL v2 或更新版本及字体嵌入例外）。源码包保留原字体文件和许可。
本包没有选择覆盖项目自编工具/译文的新增开源许可证；公开可读不等于已授予任意再许可。游戏原始内容及角色的权利归各权利人。第三方韩文补丁的译文和字库未纳入本项目；相关资料仅作研究线索，见 docs/korean_patch_source.md。不得将本包理解为拥有原游戏或韩文补丁版权。

本仓库由 v0.1.2 实验源码包整理，另收录了后续主动攻击、游戏内存档/读档测试与录制前端源码。SOURCE_FILES.sha256.json 记录本次公开源码树各文件大小及哈希；最新运行范围请查看 README.md 和 docs/extended_runtime_qa_v0.1.2.txt。
