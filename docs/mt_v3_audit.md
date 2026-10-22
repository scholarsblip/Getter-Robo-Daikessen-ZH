# Machine baseline v3 targeted audit

Current outputs are `work/translation/scenario.zh_CN.machine.v3.jsonl` (1,886 rows, 71,415 Japanese source characters) and `work/translation/core.zh_CN.machine.v3.jsonl` (967 rows). Original text, offsets, raw bytes and occurrence/reference metadata remain in each record. These are machine baselines; a full semantic or in-game review is not claimed.

The core row `SLPS_022.32:073690` intentionally remains `げんき`: a verified binary comparison uses this exact Japanese name to unlock a hidden reward. This functional trigger must retain original bytes `82b082f182ab`; it is not missing translation. The preservation record is `work/glossary/core_row_preserve_overrides.zh_CN.json`.

The earlier v2 split prose at names and line/timing controls. This caused isolated Japanese particles and verb endings to be mistranslated. v3 translates complete prose, joining hard wraps before translation. Stable entity/variable markers preserve names without removing grammatical context. Nonsemantic visual/timing/linebreak controls are restored monotonically between matching semantic anchors; placement is therefore approximate and still needs actual scene/layout checks. Their original sequence is verified separately.

The corpus's actual weapon/unit labels use `disc_exact_overrides.zh_CN.json` (213 unique weapons, 102 unique units). Speaker aliases now consistently use 达人, 罗刹, 兰多 and 信一. Foreign names without a settled project choice remain Japanese and appear in `pending_entity_review`; 165 scenario rows have such a flag. Provisional unit transliterations in the disc-label map remain documented in its separate audit and are not claimed as official Chinese names.

Eight scenario rows received targeted manual repairs, saved in `work/glossary/scenario_row_review_overrides.zh_CN.json`. They fix six command-adjacency/semantic problems, an incorrect neck-strike label, and a mistranslated English-accent joke. A truncated long speech was also repaired in the segment cache; its complete marker sequence was revalidated. `prose_review_overrides.zh_CN.json` contains the boarding sentence and two turn-count messages. Reapplying the pipeline with a changed glossary/configuration requires reapplying these targeted reviews before building.

Final targeted checks passed for all 1,886 scenario rows using the builder-style greedy control parser. All 967 core rows passed the pipeline control check. No unintended Unicode format characters remain. The audited bad outputs 屁、鸬鹚、罗濑津、兰道、新一、真一、Getter、Blai、Zill and 真正的演习 no longer appear in scenario v3. This is an issue-focused audit, not proof that every machine sentence is idiomatic or correct.

Machine-readable evidence: `work/translation/v3_targeted_audit.json`. Scenario output SHA256: `de518e1ef2e338cd43e4bf58a9783152d203ce1568bf18dce6f6086dd58198fe`.
