# Getter Robo Daikessen! PS1 technical research

2026-10-22. Target: original Japanese **SLPS-02232**.

## Confirmed identity and source fingerprint

[PSX Data Center](https://psxdatacenter.com/games/J/G/SLPS-02232.html) identifies the title as Getter Robo the Big Battle / Getter Robo Daikessen!, Techno Soft, Bandai Visual, 1999-09-09, SLPS-02232, one data track. The budget rerelease is SLPS-03017; do not assume identical file offsets.

The independent Korean patch author's [primary release page](https://gagnonjung.github.io/patch_release/getter-robo-daikessen/) specifies this original:

- `Getter Robo Daikessen! (Japan).bin`
- 663,111,120 bytes
- MD5 `73FE5C7C386984AC14956766019E63B1`
- SHA256 `08F189C914FA753AF0BA690579712636F1D8B21EB7777C89B6FC10041C725807`

These are a useful comparison fingerprint. The current downloaded source must still be checked; serial and size alone are insufficient verification.

## Public localization research leads

The [HanMaru workshop](https://gagnonjung.github.io/patch_release/) has a Korean patch release, latest v1.12 on 2026-10-07. The primary page says it translates story and combat dialogue, menus, moves, choices, title/result/name-entry graphics, episode titles and video captions. It describes VFS readback and EXE synchronization checks. This establishes that an archive or virtual-file-system layer is involved, but does not document its structure.

The Korean patch is not a public permissively licensed translation toolchain. Its release has restrictions on modifying/porting or redistributing that patch. Work here uses the original Japanese game and independent helpers; any public source code must be checked on its own terms before reuse. Do not rehost its patch or Korean assets.

[RetroDB](https://retrodb.info/krpatch/3130/%EA%B2%9F%ED%83%80%EB%A1%9C%EB%B3%B4-%EB%8C%80%EA%B2%B0%EC%A0%84) is a secondary directory. It now lists v1.12, superseding the earlier v1.11 lead. Cached signed redirect links returned 410; the primary workshop avoids that dependency.

The author's public GitHub repositories include [psxforge](https://github.com/gagnonjung/psxforge), [emucap](https://github.com/gagnonjung/emucap), and [kr-patch-qa](https://github.com/gagnonjung/kr-patch-qa). **psxforge is a PSIO disc-library organizer and image merger, not a Getter archive/text tool.** Its inspected tree contains README, `psxforge.py`, `psio_manager.py`, and maintenance batch files. emucap and kr-patch-qa trees contain no Getter-named files. No Getter-specific source/tooling has been verified from these repositories. The workshop's site repository contains release HTML and preview graphics, not the game's translation engine source.

Targeted exact-title/serial GitHub repository searches did not find a Getter-specific extractor. English/Japanese searches for compression, archive, font, and binary-edit documentation did not find a confirmed format specification. Generic Technosoft compression or another PS1 title's encoding must not be treated as compatible without inspecting this game's data.

## Terminology references

[Akurasu units](https://akurasu.net/wiki/Getter_Robo%3A_Daikessen%21/Units) and [characters](https://akurasu.net/wiki/Getter_Robo%3A_Daikessen%21/Characters) provide Japanese names alongside romanized/English names. These can help check entity identity, not dictate Chinese terminology or serve as evidence about binary formats.

## Next binary work

1. Inspect the original ISO directory, executable, and resource signatures.
2. Locate VFS tables and verify all entries before extracting candidate text containers.
3. Determine compression from executable routines or reliable round trips.
4. Extract scenario text with raw bytes, control codes and all pointer references retained.
5. Verify the character/font map before translating placeholders or changing a glyph slot.

No scenario extraction claim is made before the disc resources are available.
