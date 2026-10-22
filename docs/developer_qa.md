# 开发测试与录屏

这些前端直接通过 libretro API 使用你自行准备的兼容核心。它们只发送普通控制器按键、保存匹配版本的模拟器状态、读取诊断数据或录制游戏输出，不注入游戏 RAM。不要把即时状态载入等同于游戏自身的记忆卡读档。

主诊断前端：`tools/qa_getter.py`。独立存档测试前端：`tools/qa_save_frontend.py`，额外接受 `--save-dir`。连续录屏前端：`tools/record_getter.py`，额外接受 `--ffmpeg`、`--record-output` 和 `--record-every`。

本版已用 SwanStation 1.0.0 cc94ebc 的软件渲染、解释器模式及 OpenBIOS 测试。核心和固件不在仓库中，按自身平台配置路径；不要把别的版本即时状态加载进改动后的镜像。

示例（替换路径为自己的文件）：

```sh
python tools/qa_getter.py "/path/to/patched.cue" \
  --core "/path/to/swanstation_libretro.dylib" \
  --system-dir "/path/to/firmware" \
  --option swanstation_GPU_Renderer=Software \
  --option swanstation_CPU_ExecutionMode=Interpreter \
  --option swanstation_BIOS_PathNTSCJ=openbios.bin \
  --frames 1800 --output work/qa/example
```

按键计划是普通 JSON：

```json
[{"start": 60, "end": 65, "buttons": ["a"]}]
```

`a` 对应 PS 手柄圆圈，`b` 对应叉号。其他映射见前端的 `buttons` 字典。使用 `--schedule plan.json` 加载计划。

原生记忆卡测试采用官方核心选项 `swanstation_MemoryCards_Card1Type=PerGameTitle` 与独立 `--save-dir`；实际数据由游戏自己的存档/读取菜单写入、读取 `.mcd`。不要把生成的个人进度或记忆卡提交到代码仓库。

录屏前端会把实际视频刷新和原始游戏音频交给本地 FFmpeg，不捕获桌面。原生分辨率变化按核心报告的 4:3 显示比例统一为 640×480；默认每两帧采样一个视频帧，保留原模拟时间，输出原游戏立体声音频。它要求 NumPy、Pillow 和支持 H264/AAC 的 FFmpeg。所有运行输出放在忽略的 `work/qa/` 下。

这些前端提供原始开发入口，并非完整图形模拟器。现有运行验证限于具体核心、配置和首章场景，不能保证其他平台/核心或后续关卡。
