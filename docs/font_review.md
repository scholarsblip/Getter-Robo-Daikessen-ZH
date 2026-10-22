# Independent Getter font hook review

## V2 review supersedes the original cave assessment

The first cave at `0x80083400` was subsequently found by the parent to lie inside startup BSS clearing at `0x800833B0..0x8008B7A8`. The earlier instruction-level test did not execute startup; its cave assessment was insufficient. Do not use that original layout.

The reviewed v2 binary reclaims the original native Japanese mapping data at `0x800807F4..0x8008108C`, wholly below the BSS clear. It delta-encodes the three native maps (441/441/209 entries) into 1,172 bytes and stores lookup code, descriptors and data in 1,736 of the region's 2,200 bytes. Its SHA256 is `a88cc39442f8fed37a11e3bc186467c4112c0166eb3da348bf18576decfe8fe5` (`work/font/build-reviewed-v2/SLPS_022.32.font-only`).

Independent v2 tests passed all 1,091 original Japanese entries, all 3,276 Chinese indices and 17 invalid/fallback cases, modeling branch delay slots and one-instruction MIPS load delays. Callee-saved register assertions passed. Duplicate Japanese codes `0x8E9F` and `0x90AB` resolve to their earlier page, as in the original table search; `0x8140` spaces use the unchanged simple-symbol path. The original startup zero loop was executed in the model: all BSS bytes were cleared and every byte of the new cave survived unchanged.

The initializer's branch at `0x8005205C` now unconditionally skips the old native-map registration loop and resumes at `0x80052098`; preceding symbol/kana setup remains byte-identical. A scan of the original EXE and 32 binary overlays found only three direct references into the reclaimed maps: the entries at `0x8008077C/780/784` consumed by that skipped initializer. No additional direct LUI/address-construction or GP references outside the old map data were found. Indirect or dynamically computed references cannot be exhaustively excluded by this static scan.

No blocking v2 issue was found. Runtime/GPU/gameplay verification is still required. Reproducible instruction test: `work/comp3/font_v2_review.py`; results: `work/comp3/font_v2_review.json`.

## Earlier instruction review, retained for traceability

Reviewed the current `tools/getter_font.py` against original Japanese SLPS-02232, SHA256 `edc4b01e09708d64db21430ed341e4fb222799089a2ca360f329a8fe15f5bb8b`, on 2026-10-22. No source or font tool was modified during review.

No blocking compiled-MIPS, register-preservation, descriptor or texture-coordinate error was found. This is a static and instruction-level review, not a claim of successful gameplay or final visual approval.

The original EXE's helper at `0x8004DCF4` accepts lead bytes `0x81..0x9F` and `0xE0..0xFC`; the custom `0xEB..0xFC` codes therefore pass that original byte-width classifier. The lookup hook correctly validates trails `0x40..0xFC` except `0x7F`, computes 188 trails per lead, rejects unused codes beyond the plan's character count, and returns to `0x8004DAE0` with the displaced `andi a3,t0,255` reproduced. The original character code and incoming position registers remain available on fallback.

The custom index divides into 1,092 cells per plane, then pages of 441/441/210 cells. The descriptor index is `(plane * 3 + page) * 8`. Original descriptors use texture pages 30, 29 and 11 with page 11's V origin 128. Maximum U/V values remain within the original 252×252, 252×252 and 252×120 textures. The generated descriptors reproduce those coordinates and 21 columns. The nine descriptors select Chinese bitplanes 1–3; existing Japanese descriptors select bitplane 0.

The draw proxy reads the caller's fifth argument at the original `sp+0x10`, includes load-delay NOPs, reproduces the displaced `sp -= 0x28` and `sw s3,sp+0x1C`, then resumes at `0x8004D6E4`. It clears only the old palette-row bits 18–19 when the descriptor selects the new CLUT range; the horizontal four-colour selection in bits 16–17 remains intact. Callee-saved registers, GP and stack are preserved by the generated paths. HI/LO and temporary registers are call-clobbered, as in the original drawing routines.

The new CLUT rectangle is x896..959, y508..511. Native kanji j0/j1 textures end at y507. Other setup fonts occupy x960 and above or end earlier. The original 64×4 `fnt_clut.tim` rectangle is x960..1023, y505..508, so the two palette rectangles do not intersect. The new four foreground colours equal the first entries of the original main palette's four columns. The original is monochrome-normalized intentionally; shade gradients and the old optional palette-row effects are not retained for these kanji sheets.

The code cave file offset `0x73C00` maps to `0x80083400`; it is inside the original loaded payload ending at file offset `0x74000`. Original bytes in that cave are zero. Generated code plus descriptors is 360 bytes, below its 1,024-byte reserved limit. Hook addresses and the three native descriptor CLUT addresses match the original bytes checked by the tool.

An independent small MIPS interpreter enumerated 29,696 lookup cases using character counts 1, 188, 1,092 and 3,276, and every trail byte for leads `0xE0..0xFC`. All 4,557 valid custom dispatches and 25,139 fallback cases matched the separately calculated descriptor/cell results; callee-saved register assertions passed. Another 32 palette-proxy boundary cases passed. Machine-readable results are in `work/comp3/font_mips_review.json`. This interpreter does not model the GPU, cache, hardware execution timing, resource load order, or all game call sites.

Before releasing a patch, confirm the actual Chinese font's complete character coverage, observe boot/menu/dialogue/battle text in an emulator, and verify that other runtime font-table initialization does not restore the old native descriptor CLUTs after this patch. The fourth currently zero-initialized font range was not shown to be active in this review; the three known loaded kanji sheets are the ones patched.
