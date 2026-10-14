# Server-side security recommendations

This is scoped to what `PickUP.cs` actually does (see `analysis.md` §4): a forged **driver sync** that teleports the sender's vehicle under an on-foot target with an upward velocity, repeated every frame while LMB is held.

## 1. Who does what

| Action | Where it happens | Does the server accept it? |
|---|---|---|
| Target selection, ESP box, HUD | Cheater's client only | Invisible to the server |
| `/pickup`, `/RES` | Cheater's client only (SAMPFUNCS local hook) | Never sent |
| Forged vehicle position and velocity | Client → server (`DRIVER_SYNC`, packet ID 200) | **Yes, by default.** Stock SA-MP trusts the driver's in-car sync, stores it (`GetVehiclePos` changes) and relays it to everyone streamed in |
| Target being pushed or launched | **The victim's own client** simulates the collision, then sends its own (genuine) on-foot sync | Yes, it looks like legitimate movement from the victim |
| Fall damage or death of the victim | Victim's client | `OnPlayerDeath` reason is usually 54 (fall) or vehicle-related, so **the cheater isn't credited**. Don't rely on kill logs to find them. |
| Money, weapons, scores | Not touched | The packet copies the cheater's genuine health, armor and weapon fields unchanged. **There's no money or stat manipulation in this script.** |

So the only thing the server has to reject is **the forged vehicle position and velocity in the incoming driver sync**. If that's dropped before it's relayed, other clients never see the fake car, and the attack does nothing.

## 2. What the server can check

Signatures, from strongest to weakest. All of them come straight from the bytecode:

1. **Position oscillation.** Real and forged syncs alternate within milliseconds. The vehicle jumps between point A (real) and point B (under a player), sometimes hundreds of meters apart, many times a second. Real vehicles can't do this.
2. **Displacement versus elapsed time.** Distance from the last accepted position divided by Δt is far above any vehicle's top speed (cap at ~70 m/s for land vehicles, ~120 m/s for aircraft, plus some lag allowance).
3. **Landing inside an on-foot player.** The forged position is exactly 0.9 m below a non-paused, on-foot player (horizontal distance about 0).
4. **Exact velocity constant.** Velocity is exactly `(0.08, 0.10, 0.10)`. This is a strong fingerprint for *this build*, but trivial to change, so treat it as a logging signal, not your only check.
5. Velocity that doesn't match displacement. A tiny reported velocity combined with a huge position jump is suspicious.

## 3. Recommended implementation

### 3a. Drop the packet before it's relayed (best)

Use a packet-level hook such as [Pawn.RakNet](https://github.com/katursis/Pawn.RakNet) on SA-MP 0.3.7, or the equivalent sync-validation event on open.mp. Returning `0` drops the packet, so it's never applied or relayed. This is a sketch. Check the API names against your plugin version, and tune the thresholds on a test server.

```pawn
#include <Pawn.RakNet>

const DRIVER_SYNC = 200;
static Float:gLastVX[MAX_PLAYERS], Float:gLastVY[MAX_PLAYERS], Float:gLastVZ[MAX_PLAYERS];
static gLastVTick[MAX_PLAYERS], gVehWarp[MAX_PLAYERS];

IPacket:DRIVER_SYNC(playerid, BitStream:bs)
{
    new data[PR_InCarSync];
    BS_IgnoreBits(bs, 8);
    BS_ReadInCarSync(bs, data);

    new now = GetTickCount(), dt = now - gLastVTick[playerid];
    new Float:x = data[PR_position][0], Float:y = data[PR_position][1], Float:z = data[PR_position][2];

    if (gLastVTick[playerid] != 0 && dt < 1000)
    {
        new Float:dist = VectorSize(x - gLastVX[playerid], y - gLastVY[playerid], z - gLastVZ[playerid]);
        new Float:maxDist = 5.0 + 0.08 * float(dt); // ~80 m/s + slack; tune per vehicle class

        if (dist > maxDist)
        {
            gVehWarp[playerid]++;
            LogVehicleWarp(playerid, data[PR_vehicleId], dist, dt, x, y, z,
                data[PR_velocity][0], data[PR_velocity][1], data[PR_velocity][2]);
            if (gVehWarp[playerid] >= 3) OnSuspectedSyncForgery(playerid); // kick/ban/flag for staff
            return 0; // DROP — do not apply or relay
        }
    }
    gLastVX[playerid] = x; gLastVY[playerid] = y; gLastVZ[playerid] = z;
    gLastVTick[playerid] = now;
    return 1;
}
```

Reset `gLastVTick[playerid] = 0` whenever **your own scripts** move the player or vehicle. That means `SetVehiclePos`, `SetPlayerPos` while driving, `PutPlayerInVehicle`, spawns, interiors and vehicle respawns. Otherwise legitimate admin teleports will trigger the check. Also reset it in `OnPlayerStateChange` and `OnPlayerDisconnect`.

Updating the "last position" only on accepted packets is what defeats the oscillation pattern. The forged packet gets dropped, and the next genuine one passes.

### 3b. Without a RakNet plugin (weaker)

In `OnPlayerUpdate`, when the player is the driver, compare `GetVehiclePos` against the last value from the previous call using the same displacement-over-time rule. Returning `0` stops the update from being relayed to other players. Unlike 3a, though, the server has already stored the new position, so `GetVehiclePos` and anything in your own logic that reads it (zones, races, checkpoints) will see the forged value once. Verify that behavior on your server version before relying on it.

### 3c. Proximity correlation (extra evidence for staff review)

When a driver-sync jump is flagged, record which on-foot players are within ~2 m of the forged position. Over the next ~2 seconds, look for the victim's Z rising sharply or a fall-reason death. A forged jump that lands inside a player followed by that player being flung is close to conclusive evidence, and it also tells you who the victims were.

## 4. Logging

Log the following for every flagged packet:

- Time, attacker player ID, name and IP, and vehicle ID/model
- The last accepted position, the forged position, `dt` and the computed speed
- Reported velocity. Note an exact `(0.08, 0.10, 0.10)` match with a "PickUP signature" tag
- The nearest on-foot player and their distance to the forged position
- A rate counter (flags per 10 s). PickUP gives dozens per second while LMB is held, whereas lag spikes give isolated single events

## 5. Operational notes

- **Don't kick on the first event.** Packet loss and lag can cause single-teleport false positives. Drop the packet silently and escalate after repeated hits within a short window, as in the code sketch.
- **Test on a private/local server** with your own accounts. Spawn a vehicle, use a second client as the on-foot target, and confirm the hook flags and drops the warp. Don't test against public players.
- **Client-side anti-cheat** (detecting CLEO, SAMPFUNCS or `PickUP.cs` on the client) is a separate layer the cheater controls, and it's easily bypassed. The server-side check above is what actually stops the effect.
- The same check also blocks the wider family of "vehicle teleport", "car shooter" and "invisible ram" sync forgeries, not just this script.
