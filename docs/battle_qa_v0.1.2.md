# Final v0.1.2 runtime QA

> 这是较早一轮构建/运行验证的快照。后续玩家主动攻击和游戏内存档/读档结果见 [追加测试报告](extended_runtime_qa_v0.1.2.txt)。

The final image was cold booted for 26,000 frames with SwanStation 1.0.0 cc94ebc, Software renderer, Interpreter CPU, and explicit OpenBIOS. No original or earlier-build states or RAM injection were used. Firmware hashes/options and all screenshot paths are recorded in `work/qa/final_v0.1.2.json`.

Passed: Chinese character setup/ability table, first story, first tactical battle map, target and terrain labels, weapon list/details, global menu and mission conditions. HP883/883 and EN49/49 matched original.

The follow-up used ordinary controller input and states created from that same final image. It ended turns, flew Eagle onto Hayato school and chose Wait, played the school-entry FMV, advanced Chinese story with additional machines, and returned normally to the tactical map. The school event and subsequent map transition were visually inspected.

**Actual battle animation verified.** One additional normal End Turn from `final_attempt/s13/end.state` triggered enemy attacks. Screenshots in `work/qa/translated_v0.1.2/one_turn/s2/` show Giant Bear hit (frame_000300, HP805/937), BT23 in combat (frame_000600, HP1055/1133), Jaguar hit (frame_000900, HP637/769), and normal tactical return (frame_001800). These are rendered 3D combat scenes with unit names, HP bars, damage values and pilot portraits/dialogue. No crash or new rendering defect was observed.

**Known residual battle translation coverage:** the speaker label `アキラ` remains Japanese in frame_000600, and the effect label `ダメージ` remains Japanese. Other inspected battle unit names and pilot dialogue are Chinese. This is an experimental translation, not a claim that every battle graphic/string is translated.

Continue from `work/qa/translated_v0.1.2/one_turn/s2/end.state`, on the free tactical cursor after those attacks. Player-initiated attack confirmation, later chapters and complete translation semantics have not been verified.
