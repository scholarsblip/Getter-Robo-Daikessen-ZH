# Getter Robo Daikessen! Korean patch: primary release recovered

Checked 2026-10-22 (Asia/Shanghai). Target is PlayStation Getter Robo Daikessen!, Japanese serial SLPS-02232. Getter work resumed after the user cancelled the intervening SRW F Final task.

## Primary source and current version

- Author: **한마루 / HanMaru**.
- Author's release page: https://gagnonjung.github.io/patch_release/getter-robo-daikessen/
- Author's workshop index: https://gagnonjung.github.io/patch_release/
- Current version: **v1.12**, released **2026-10-07**. Earlier v1.11 (2026-09-29) is superseded.
- Primary public download: https://drive.google.com/file/d/1DkLuEzffLvnbTeno_9eHtFRGa282RdsI/view
- Supporting directory: https://retrodb.info/krpatch/5379/겟타로보-대결전
- The initial `/krpatch/3130/` directory URL aggregates all versions and now displays 1.12; it must not be treated as a frozen 1.11 page.

The directory's outbound link uses a JavaScript proof-of-work intermediary. That intermediary was not reverse-engineered or solved. A normal web search independently located the author's public GitHub Pages workshop, whose download link leads directly to Google Drive. No Baidu access, account login, payment or third-party contact was used.

## Downloaded artifact and verification

Local archive:

`incoming/korean_patch/20261007_10_Getter_Robo_Daikessen_KO_v1.12_xdelta_windows.zip`

- Size: **193,861,203 bytes**.
- SHA-256: **4121f87775ae04e23352a03b83a93afcfcb8cbb5e608773214d16dc4749ce28b**.
- Matches the author's published ZIP checksum exactly.
- ZIP CRC test passed for all 11 members.
- Every one of the 10 entries in the archive's `SHA256SUMS.txt` matched its actual member bytes.
- No original or patched game BIN is present in the archive.

Actual patch member: `Getter_Robo_Daikessen_KO_v1.12.xdelta`

- Uncompressed size: **193,922,786 bytes**.
- SHA-256: **45f8c090c9053224ca046ca5b6b222eb961c7a0b077b5e36a007c3bf581e2d6a**.
- Standard VCDIFF magic/version `D6 C3 C4 00`; the author's package supplies Xdelta 3.2.0 for Windows.
- Kept inside the ZIP to avoid an unnecessary second 194 MB copy. It can be extracted when the main task is ready to apply it with a trusted local Xdelta decoder.

Readme, release notes, hashes, batch/PowerShell scripts, CUE and Xdelta notices were extracted into `incoming/korean_patch/reference/` for **static inspection only**. Neither the bundled executable nor the patch scripts were executed, and no patch was applied by this research subtask.

Machine-readable member inventory and verification:

`incoming/korean_patch/archive_verification.json`

## Required original and expected Korean output

The readme and PowerShell script agree on all values:

| Item | Value |
| --- | --- |
| Original filename | `Getter Robo Daikessen! (Japan).bin` |
| Original size | `663111120` bytes |
| Original MD5 | `73fe5c7c386984ac14956766019e63b1` |
| Original SHA-256 | `08f189c914fa753af0ba690579712636f1d8b21eb7777c89b6fc10041c725807` |
| Expected Korean MD5 | `2f934ac5c1516c8c31992c703195c220` |
| Expected Korean SHA-256 | `8ba744a190b947d53ba06f8a4396aca36ae01444b13b6a046a772240aa78d6ec` |

v1.12 is a cumulative patch for the Japanese original, **not** an upgrade patch for a v1.11 Korean BIN. The distributed CUE describes a single MODE2/2352 track at INDEX 01 00:00:00. The official scripts verify original/output hashes and choose an unused output name.

## Coverage and practical limitations

The author reports Korean story/battle dialogue, choices, names/techniques, system UI, image labels and movie subtitles. The patch also adds a Korean name-entry keyboard, relocates its engine, and maps the Korean name 겐키 to the original female-protagonist hidden condition.

v1.12 adds three previously omitted episode-title images in episodes 9 and 15. The readme reports static/disc/Xdelta replay checks, fixed PAC payload windows and sector EDC/ECC validation. These are **author-reported** results; this subtask verified the archive and its manifests, not gameplay.

The readme explicitly leaves these checks/issues open:

- Natural runtime display of the new episode-title images.
- The first actual display of the hidden Genki model change.
- Text overlap in weapon-detail windows is **not fixed** by v1.12.

These known issues are useful test targets for an independent Chinese version.

## Licensing and available source/tools

The ZIP includes Xdelta 3.2.0 Windows, full Apache License 2.0 text, upstream README and version/hash provenance. That Apache license concerns **Xdelta**, not a blanket license for the Korean translation or its graphics. The Korean readme identifies the work as unofficial and retains the original game's rights; it does not provide an explicit broad derivative/relicensing grant for all localization assets.

The public repository https://github.com/gagnonjung/patch_release contains the workshop website and site-publishing utilities. Its complete public tree was inspected (152 entries); `getter-robo-daikessen/` contains only `index.html`. No Getter text corpus, font codec, PAC compressor or localization build pipeline was found there. The package's readable `.bat` / `.ps1` scripts are patch applicators, not the localization source toolchain.
