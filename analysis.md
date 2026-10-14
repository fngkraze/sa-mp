# Analysis — `PickUP.cs` (Opcode.eXe / UGBASE.EU)

Offsets refer to `disassembly.txt`. "Verified" means it was traced through control flow in the bytecode. "Hypothesis" means it's inferred and not proven.

## TL;DR

**PickUP is a "vehicle launch" grief cheat.** While you sit in a vehicle:

1. Holding **RMB** auto-targets the on-foot player closest to a fixed screen point and draws a 3D box around them.
2. Holding **LMB** then makes the script send a **forged driver sync packet**. It's a copy of your real one with the vehicle **position overwritten to 0.9 m below the target's feet** and the **velocity forced upward/forward**.

Other clients see your car appear inside the target and physically shove or launch them. Your car never actually moves on your own screen. The script only lies in the outgoing packet.

The `op.bitq.eu` "update" URLs, the `CREATE_PLAYER` spam and the raw memory writes are **unreachable decoy/anti-decompile code** (Verified, see §6). The script has **no working network or HTTP functionality** apart from the SA-MP sync packet.

## 1. Initialization (Verified) — `0x0000–0x00A1`

```
0000 nop
loop: wait 0; if not SAMP_IS_AVAILABLE goto loop      ; 0002–0008  wait for SA-MP client
0B6D create D3D font "Arial Black" 20 → 31@, size 9 → 30@
0B71 load textures CLEO\MouseRight.png→29@, MouseLeft.png→28@, MouseIdle.png→26@
0B34 hook chat cmd "RES"    → @L0D66 (reload)
0B34 hook chat cmd "pickup" → @L0DB0 (toggle)
```

**Dependencies:** CLEO 4 (the `0AB1`/`0AB2` calls and the `0A8C`/`0A8D` memory opcodes), SAMPFUNCS (every `0AF8–0C0D` opcode), the three PNGs in `CLEO\`, and GTA SA 1.0 US (hard-coded addresses, §5).

## 2. Commands (Verified)

| Label | Command | Behavior |
|---|---|---|
| `L0DB0` | `/pickup` | Toggles `27@` between 0 and 1 and prints "PickUP: enabled/disabled." to local chat. Defaults to **off**, since locals start at 0. |
| `L0D66` | `/RES` | Prints "RELOADING.", unhooks "RES" and "PickUP", runs `0A92 STREAM_CUSTOM_SCRIPT "PickUP.cs"` (relaunches from local disk), then `004E` terminates. |

Both commands are local-only. SAMPFUNCS intercepts them, so they never reach the server.

## 3. Main loop `L00A2` (Verified)

```
loop:
  wait 0                                   ; runs every frame
  if 27@ != 1: goto loop                   ; disabled
  draw HUD box + "Pickup" + "Made by Opcode.eXe" at top-centre
  if not IS_CHAR_IN_ANY_CAR($PLAYER_ACTOR):
      draw MouseIdle; goto loop            ; L08D3
  if not IS_KEY_PRESSED(VK_RBUTTON=2):     ; 01D1
      draw MouseRight ("hold right")       ; L04FD
  else if not FindTarget() → 0@:           ; 01E0 CLEO_CALL L0AFB
      draw MouseIdle                       ; L04C7
  else:
      draw MouseLeft ("now click left")
      DrawTargetBox(0@)                    ; L0E5A
      top/bottom = model-dimension points of target  (L0AB3/L0A6B)
      DrawLineTargetToMyCar()              ; L09D0
      draw red line HUD → target
      if IS_KEY_PRESSED(VK_LBUTTON=1):     ; 02AE   ← payload, see §4
          SendForgedDriverSync(0@)
  [dead branch at 052C, see §6]
  goto loop
```

Input is `0AB0 IS_KEY_PRESSED`. It's **level-triggered**, not edge-triggered, and the loop runs with `wait 0`. **So a forged packet goes out every frame for as long as LMB is held,** typically 30–100+ per second, depending on FPS.

### Target selection `L0AFB` (Verified)

```
28@ = 640.0                                      ; best distance
pool = *(0xB74490)  (CPools::ms_pPedPool)        ; 0B05
flags = *(pool+4)                                ; byte array of slot flags
for slot = 0..139:  handle = slot*256 + flag     ; 0B2D–0C32 (30@ += 256 until > 35584)
   if flag < 0 or flag >= 128: continue          ; free slot
   if not DOES_CHAR_EXIST(handle) or handle == $PLAYER_ACTOR: continue
   id = SAMP_GET_PLAYER_ID(handle)
   require: not SAMP_IS_PLAYER_PAUSED(id) and not IS_CHAR_IN_ANY_CAR(handle) and IS_CHAR_ON_SCREEN(handle)
   (sx,sy) = WorldToScreen(char pos)             ; L0C5C → CALL 0x70CE30 (CSprite::CalcScreenCoors), scaled to 640×448
   d = dist2D((320,100),(sx,sy))
   if d <= best: best=d; 15@=handle
return 15@ ; condition = DOES_CHAR_EXIST(15@)    ; 0C39–0C54
```

The condition result uses a trick. If a target exists it executes `0485 IS_PC_VERSION` (always true), otherwise `059A IS_AUSTRALIAN_GAME` (false on PC), which sets the `CLEO_CALL` condition flag.

**Targets are only real, unpaused, on-foot SA-MP players who are on screen.** Players in vehicles and AFK players are skipped.

### Target box `L0E5A` (Verified, except one write)

This draws a 12-edge 3D bounding box from `GET_MODEL_DIMENSIONS` corners (`L1556–L16A9`), in red `0xFFFF0000`.

At `0E6D–0E7D` it writes `float 2.0` to `pedPointer+300` (`+0x12C`) of the **target's local ped object**. This only changes local memory on the cheater's machine. The field's meaning isn't established (see `unresolved.md`).

## 4. Payload — forged driver sync (Verified) `0x02B9–0x0499`

```
02B9  33@ = 0                                        ; reset TIMERB (see §6)
02C0  myId = SAMP_GET_PLAYER_ID($PLAYER_ACTOR)
02C8  buf  = ALLOCATE_MEMORY(67)
02CF  SAMP_STORE_PLAYER_DRIVING_DATA(myId, buf)      ; copy of my last in-car sync
02D7  (x,y,z) = GET_OFFSET_FROM_CHAR_IN_WORLD_COORDS(target, 0, 0, -0.9)
02F4  *(float*)(buf+24) = x                          ; InCarSync.position
0300  *(float*)(buf+28) = y
030C  *(float*)(buf+32) = z
031C  [dead branch, §6]
046A  *(float*)(buf+36) = 0.08                       ; InCarSync.velocity
0478  *(float*)(buf+40) = 0.10
0486  *(float*)(buf+44) = 0.10                       ; +Z → upward
0494  SAMP_SEND_DRIVING_DATA(buf)                    ; sends DRIVER_SYNC to server
0499  FREE_MEMORY(buf)
049E  draw small red square at the target on screen
```

Offsets 24/28/32/36/40/44 match the SA-MP 0.3.x `INCAR_SYNC_DATA` layout. In that layout `vehicleId`(2), `lrKey`(2), `udKey`(2) and `keys`(2) are followed by `quat`(16) → `position` @24 → `velocity` @36. That layout is well documented, but this analysis infers it rather than verifying it against a SAMPFUNCS header.

**Everything else in the packet** (vehicle ID, keys, rotation, vehicle health, player health and armour, weapon, siren, trailer) is **copied unchanged** from the cheater's genuine last sync.

**What the server and other players see:** the cheater's vehicle appears under the target with an upward/forward velocity, then the next genuine sync puts it back. Because LMB is level-triggered, real and forged positions **alternate** every frame. The target's game client simulates a collision with a remote vehicle overlapping its ped, which pushes, lifts or flings the target ("picks them up"). This physics consequence is inferred from GTA/SA-MP remote-vehicle behavior and wasn't tested (see `unresolved.md`).

**What the cheater sees:** their own car doesn't move, since only the packet is changed.

## 5. Hard-coded game addresses (Verified as constants; meanings from GTA SA 1.0 US)

| Offset | Value | Meaning |
|---|---|---|
| `0B05` | `0xB74490` | `CPools::ms_pPedPool` |
| `0C7C` | `0x70CE30` | `CSprite::CalcScreenCoors` |
| `0CAC/0CBA` | `0xC17044 / 0xC17048` | `RsGlobal.maximumWidth/Height` |
| `0D41` (dead) | `0x5E01C0` | `CPed::GetBonePosition` |

These addresses only work on the **1.0 US EXE**, which is the version standard for SA-MP.

## 6. Dead and decoy code (Verified)

`33@` is not an ordinary variable. In CLEO, `32@` and `33@` are **TIMERA/TIMERB**, which the engine increments in milliseconds between script ticks. Only one instruction writes to it (`02B9`, which sets it to 0). Two checks compare it with `IS_FLOAT_LVAR_EQUAL_TO_NUMBER 33@ 1.3377777e29`, whose bit pattern is `0x6FD82131` = **1,876,435,249 ms ≈ 21.7 days**:

| Branch | Why it never runs | What it contains |
|---|---|---|
| `031C → 032D–0463` | `33@` was set to 0 at `02B9` in the same tick, with no `wait` in between, so the check is always false | `SCRIPT_NAME "UGBASE.EU"`; `0A8C WRITE_MEMORY` to addresses derived from `1@` and `30@` (here `30@` holds a **font handle**, which makes these writes meaningless); `FREE_DYNAMIC_LIBRARY 30@`; `GOSUB 30@`; the two **raw URL strings** placed inline as data; and `CALL_FUNCTION 30@` |
| `0530 → 0541–08C7` | Needs TIMERB to equal exactly 1,876,435,249. In practice that never happens: it means about 21.7 days without pressing LMB, and the timer would also have to land on that exact millisecond | `SCRIPT_NAME "@$@@$$"`, `SET_VEHICLE_TO_FADE_IN` with a texture handle, `wait 50000`, then 17 × `CREATE_PLAYER 0 … $2` (re-creates the local player) |

In addition, these code ranges have **no incoming references**:
- `0911–09BC`: after an unconditional `GOTO`. This includes `L0930`, a ping-compensated position predictor, which is only called from that dead `0911` call.
- `0D03–0D65`: a bone-position helper.
- `0E28–0E59`: an ARGB alpha helper.

These are probably leftovers from the author's shared include library.

**Conclusion (High confidence):** the `op.bitq.eu` URLs aren't used for anything. No opcode reads them as strings, and no HTTP or download opcode exists anywhere in the script. They sit in branches that can't run, next to nonsense such as jumping to a font handle. Their purpose is almost certainly to **break decompilers** (inline raw bytes inside code) and to mislead analysts. Whatever the intent, the reachability result stands either way.

## 7. External communication

| Kind | Present? | Evidence |
|---|---|---|
| SA-MP network | **Yes**: one forged `DRIVER_SYNC` per frame while active | `0494 0BC1` |
| HTTP/download | **No** (strings only, in dead code) | §6 |
| File I/O | Only the texture loads at init and the self-relaunch from local disk on `/RES` | `0B71`, `0A92` |
| Chat/RPC to server | **No**. The commands are hooked locally, and `0AF8` only writes to local chat | §2 |

## 8. Cleanup and error handling

There's no error handling. The ped-pool walk skips invalid slots, and target lookup failure is handled. `/RES` unhooks `"PickUP"` but hooked `"pickup"`. SAMPFUNCS command matching is probably case-insensitive (unverified). Textures and fonts are never released, and nothing is cleaned up on exit.
