# Binary report — `PickUP.cs`

## Identity

| Field | Value |
|---|---|
| Source repo | https://github.com/fngkraze/sa-mp/ |
| Commit | `715bb7de73eac208382e5617ea43183ba8a83505` ("Add files via upload", 2026-10-14) — only commit |
| File | `PickUP.cs` |
| Size | 23,411 bytes |
| SHA-256 | `c88f06d85d615bc33341e5bf8931bfcdd5cb32ca26f20acf850870971787c665` |
| Local copy (`Desktop\PickUP\PickUP.cs`) | byte-identical to repo copy (`cmp`) |

Companion files (same commit, also in `Desktop\PickUP`):

| File | SHA-256 |
|---|---|
| MouseIdle.png | `1426bd519b8cc70d2c0c564ee731577cdf53d9b248e310225a2d9c1fb0bfecbd` |
| MouseLeft.png | `1c53fde077eb2fe24d13e32c17f0053acd978dfe8b21041c5119a32d299caeb2` |
| MouseRight.png | `00450b3f983313b2a41d2c4bd7c2a9252831a2f5bb13a5e69771be4dcc919382` |
| readme.txt | `568c4c69d1eb56659ff374b623dd90672078eac3505fe87a549a05e075fbcdec` |

The original binary was never modified. A read-only copy was kept in the session scratchpad, and all analysis ran against that copy.

## Format

**A headerless CLEO custom script for GTA San Andreas, compiled with Sanny Builder.** Despite the `.cs` extension, this is not C# source.

| Range | Content |
|---|---|
| `0x0000–0x16CD` (5,838 B) | SCM bytecode. Starts directly with an opcode (`0000 NOP`), and has no main.scm-style `0002` jump header or segments. Jump targets are negative int32s (offsets relative to script start), as is standard for CLEO. |
| `0x03F9` (36 B), `0x041D` (35 B) | Raw data embedded inside the code region: two NUL-terminated URL strings. They're listed in the footer's `HEX` table, so the compiler emitted them from `hex … end` blocks. |
| `0x16CE–0x5B72` | Sanny Builder "extra info" footer |

### Footer (debug metadata)

The structure is `"HEX\0" u32 count, (u32 offset, u32 len)*` → `"VAR\0" u32 count, (name\0, u32 index)*` → `"FLAG\0" …` → `u32 footer_start (=0x16CE)` → `"__SBFTR\0"`.

- **HEX** has 2 entries: `(0x3F9, 0x24)` and `(0x41D, 0x23)`.
- **VAR** has 753 names, but they're the stock GTA SA `main.scm` global-variable names (`AMMU_*`, `BJACK_*`, `PLAYER_CHAR`, ...) that Sanny Builder adds from its `CustomVariables.ini`. The script itself only uses `$2` (`PLAYER_CHAR`) and `$3` (`PLAYER_ACTOR`). **The footer has no script-specific names, labels or source.**
- **No embedded source code was found.**

## Toolchain

| Tool | Notes |
|---|---|
| Sanny Builder | **Not installed** on this machine. No Sanny Builder CLI decompile was performed (see `unresolved.md`). |
| Sanny Builder opcode library | `sa.json` v1.67 from `sannybuilder/library` @ `34bedee0be2f57047ed8f0705c81f137ede3d3ce`, SHA-256 `d48bd2a9…003f303`. Provides the opcode names and parameter counts for default, CLEO, SAMPFUNCS and other extensions. |
| `tools/disasm.py` | Custom disassembler written for this analysis (Python 3, stdlib only). It parses the SB footer, skips the `HEX` regions, and decodes typed SCM parameters exactly. |

To reproduce:

```
python -I tools/disasm.py PickUP.cs sa.json disassembly.txt
```

### Decoder validation

- All 426 instructions decoded with **0 unknown opcodes**, and decoding ended exactly at `0x16CE` (the footer start). Opcode and parameter boundaries are therefore consistent end-to-end.
- Every jump and call target is the start of a decoded instruction (36 labels).
- Variadic opcodes (`0AB1 CLEO_CALL`, `0AB2 CLEO_RETURN`, `0AA5`/`0AA6`) are terminated by an `0x00` end-of-args byte. Spot-checked in the hex.
- In SA SCM every parameter carries its own type byte, so operand decoding doesn't depend on the opcode table. The table only supplies names and parameter counts.
