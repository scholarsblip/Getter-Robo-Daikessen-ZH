# Official OpenBIOS test image

A 512 KiB OpenBIOS image was obtained from the current official PCSX-Redux distribution for Getter emulator testing. No retail Sony BIOS was downloaded, and this research did not change or run the existing emulator.

- Local ROM: `incoming/openbios/openbios.bin`
- Size: **524,288 bytes**
- SHA256: `992a0369a55ca20308fe03acaa7e376a11b815b2b29e688d7a9451f2f41f2a34`
- MD5: `a89a013bfa75f80d6b3a892d42b8f74a`
- Offset 1 signature: `00 08 3C 3F`, matching the PCSX-ReARMed BIOS-detection signature identified by the battle QA agent.

The [official OpenBIOS compatibility document](https://github.com/pcsx-redux/nugget/blob/main/openbios/COMPATIBILITY.md) explicitly lists **PCSX ReARMed** as compatible. The [official README](https://github.com/pcsx-redux/nugget/blob/main/openbios/README.md) says `openbios.bin` is usable in emulators or a replacement ROM chip. These are general compatibility statements; they do not prove Getter passes its first FMV or battle under the current emulator.

The official Redux [macOS CI workflow](https://github.com/grumpycoders/pcsx-redux/blob/fe007000b1e74fe658aa85a4e85b5d89723d0c31/.github/workflows/macos-build.yml) builds OpenBIOS, injects it into the application resources, and publishes through AppDistrib. The [publisher manifest for build 379](https://distrib.app/storage/manifests/pcsx-redux/dev-macos-arm/manifest-379.json) identifies Redux changeset `fe007000b1e74fe658aa85a4e85b5d89723d0c31`. Its pinned nugget submodule is [`7f9651226bedd29af6545883db27c9a556d05faa`](https://github.com/pcsx-redux/nugget/tree/7f9651226bedd29af6545883db27c9a556d05faa/openbios).

The downloaded DMG is 49,959,169 bytes, SHA256 `47f8c77f74f20f89c8959603496da9c886c8c3fe41ea9f20cd0ae96dffe84b84`. All publisher-provided MD5, SHA1 and SHA3-256 checks matched. The package was mounted read-only without opening the application; only its BIOS and version metadata were copied, then the mount was detached. The ROM was copied from `PCSX-Redux.app/Contents/Resources/share/pcsx-redux/resources/openbios.bin`. Its pinned official boot source contains the MIT license notice, saved alongside it as `OpenBIOS_LICENSE_MIT.txt`.

Full provenance and retained primary documents are in `incoming/openbios/provenance.json`. The battle QA agent received the ROM path and hash for isolated cold-boot testing. This document records acquisition and static acceptance only; that agent owns runtime results.
