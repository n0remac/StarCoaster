# Raspberry Pi assessment

**Observed:** 2026-10-07. **Status:** Initial review; no installation or implementation performed.

## Host environment

| Item | Observation |
| --- | --- |
| Hardware | Raspberry Pi 5 Model B Rev 1.1; 4 CPU cores; about 8 GiB RAM |
| OS | Debian GNU/Linux 12 (bookworm), 64-bit ARM (`aarch64`) |
| Root storage | About 29 GiB total, 1.3 GiB available at assessment time |
| Attached storage | About 916 GiB volume mounted at `/media/pi/media1`, with 771 GiB available; writable on the host, exposed read-only inside this workspace's sandbox |
| Found tools | GCC/G++ 12, Ninja, Docker, Git, Lua |
| Not found on `PATH` | Java/Javac, Go, CMake, Protobuf compiler |

The available space on the root filesystem is insufficient for a Recoil source build and Fabric development caches. The USB drive itself is writable: its kernel log shows a read/write mount, write protection is off, and `/media/pi/media1/rts-bridge` was created successfully with elevated access on 2026-10-07. This workspace's sandbox presents that mount as read-only. Before implementation, arrange a writable workspace path on the drive or use approved out-of-sandbox build commands. Keep bulky source, build artifacts, caches, and test worlds there.

For the first Minecraft experiment, run the Fabric dedicated server, Recoil headless process, and bridge coordinator on the Pi. Connect from a separate Minecraft client. This is a proposed test layout, not a measured capacity claim.

## Findings that affect the design

1. **Use the simulation-capable headless target.** Recoil's `engine-headless` runs the game simulation. Its `engine-dedicated` relays game traffic without simulating. [Recoil guide](https://recoilengine.org/docs/guides/getting-started/headless-and-dedicated/)
2. **ARM64 is recognized but needs validation on this Pi.** Recoil's build configuration recognizes ARM64; its current build guidance calls for C++23 with GCC 13 or Clang 17 or newer. This Pi currently has GCC 12. [Build guidance](https://github.com/beyond-all-reason/RecoilEngine/blob/master/AGENTS.md), [CMake configuration](https://github.com/beyond-all-reason/RecoilEngine/blob/master/CMakeLists.txt)
3. **The gateway is the first experiment.** Recoil documents socket access for LuaUI/LuaMenu and messaging between LuaUI and synchronized LuaRules. It does not establish that a headless LuaUI widget provides a reliable, nonblocking bridge on this Pi. [Recoil communication guide](https://recoilengine.org/docs/guides/wupget/)
4. **Persistence needs its own proof.** Recoil maintainers have described engine save/load as insufficient for seamless synchronized continuation. Do not assume a generic engine snapshot can restore an interrupted bridge session. [Recoil save/load discussion](https://github.com/beyond-all-reason/RecoilEngine/discussions/2704)
5. **Minecraft terrain needs conversion.** Recoil uses its own map units and heightmap grid. A terrain message alone is not a navigable Recoil map. Begin with an offline-generated fixed battlefield. [Recoil units of measurement](https://recoilengine.org/articles/units-of-measurement/)

## Open decisions for implementation planning

- How will the project obtain routine writable workspace access to `/media/pi/media1/rts-bridge` for source, build artifacts, Gradle caches, and test worlds?
- Which exact Recoil revision and toolchain will be pinned after a successful ARM64 headless build?
- Does a LuaUI socket relay load and operate reliably in a headless session? If so, how are external commands safely delivered to synchronized LuaRules?
- Does the requirement that every cross-process link use gRPC permit a small local relay transport between Recoil and the coordinator? If not, what native gateway is needed?
- What Recoil state can be reconstructed after restart, and what must the coordinator journal?
- Which Minecraft/Fabric/JDK versions will be pinned after the Recoil gateway is proven?

The initial acceptance criteria in the specification cover several phases. Phase 0 should have its own pass/fail gate: a headless Recoil simulation runs on the Pi, an external command changes a unit's behavior, unit state is exported, and measured queue growth and tick timing remain acceptable during a controlled disconnect.
