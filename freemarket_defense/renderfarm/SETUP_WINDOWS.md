# Render agent -- Windows 11 mini PC setup

Target: AMD Ryzen 7640HS / Radeon 760M iGPU / 16 GB RAM, rendering Blender jobs overnight.
Transport is this git repository: jobs come in as `renderfarm/jobs/<job_id>/`, the agent pushes
back small `claims/`, `progress/`, `done.json` files. Frames never go through git.

## 0. What you end up with

```
C:\renderfarm\
  VAS\                                  shallow clone of the repo (branch from config)
    freemarket_defense\renderfarm\
      agent.py            the agent (loop / --bench / --once / --dry-run)
      config.json         your local config (git-ignored)
      start_agent.bat     start (also used by the scheduled task)
      stop_agent.bat      stop
      bench.bat           benchmark
      logs\agent.log      what it is doing (rotates at 5 MB x 5)
      jobs\<id>\frames\   rendered PNGs (git-ignored)
  outbox\<id>\*.zip       zipped frames when rclone is not configured (<= 1.9 GB parts)
```

## 1. Install the tools (10 minutes)

Open **PowerShell as Administrator** (Start > type "powershell" > right-click > Run as administrator).

1. **Git for Windows**
   ```powershell
   winget install --id Git.Git -e --source winget
   ```
   (or download from https://git-scm.com/download/win; keep the defaults, they include *Git Credential
   Manager*, which does the GitHub browser login on the first push.)

2. **Python 3.11 or newer**
   ```powershell
   winget install --id Python.Python.3.12 -e --source winget
   ```
   (or https://www.python.org/downloads/windows/ -- tick **"Add python.exe to PATH"**.)
   Check in a *new* PowerShell: `python --version` -> `Python 3.12.x`. If the Microsoft Store stub opens
   instead, run `Settings > Apps > Advanced app settings > App execution aliases` and switch off the two
   `python` aliases, then reinstall with "Add to PATH".

3. **Blender 4.2 LTS** -- download the Windows installer (`blender-4.2.x-windows-x64.msi`) from
   https://www.blender.org/download/lts/4-2/ and install with defaults. The executable is then at
   ```
   C:\Program Files\Blender Foundation\Blender 4.2\blender.exe
   ```
   That exact path goes into `config.json` (`"blender"`). If you install a different version the folder
   name changes (`Blender 4.5`), nothing else does. Do not use the Microsoft Store/Steam Blender: their
   `blender.exe` lives in an odd sandbox path and GPU drivers are harder to manage.

4. **AMD graphics driver** -- install the latest *AMD Software: Adrenalin Edition* for the Ryzen 7040
   series from https://www.amd.com/en/support (the Windows-Update driver works too, but is older).
   EEVEE needs a working OpenGL 4.3 / Vulkan driver; this is the whole reason to render on this box.

5. **rclone (optional, recommended)** -- uploads frames straight to Google Drive.
   ```powershell
   winget install --id Rclone.Rclone -e --source winget
   ```
   Then configure a Google Drive remote (one time, interactive):
   ```powershell
   rclone config
   # n (new remote) -> name: gdrive -> storage: drive -> client_id/secret: leave empty (Enter)
   # scope: 1 (full access) -> service_account_file: Enter -> advanced: n -> auto config: y
   # (a browser opens: sign in to the Google account that owns the Drive) -> team drive: n -> y, q
   rclone lsd gdrive:            # lists your Drive folders = works
   rclone mkdir gdrive:renderfarm
   ```
   Put `gdrive:renderfarm` into `config.json` as `rclone_remote`. Frames land in
   `My Drive/renderfarm/<job_id>/frames/`. Without rclone, frames are zipped to `C:\renderfarm\outbox\`.

6. **git-lfs (optional)** -- only if you decide to commit blends via LFS: `winget install GitHub.GitLFS`.
   The agent detects LFS pointer files and runs `git lfs pull` if LFS is installed; it is not required
   when you use `blend_url` jobs.

Close and reopen PowerShell (as Administrator) so PATH changes apply.

## 2. Run the installer

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
irm https://raw.githubusercontent.com/danengerer-sudo/VAS/claude/low-poly-helicopter-glb-d0l1zs/freemarket_defense/renderfarm/install.ps1 -OutFile $env:TEMP\install.ps1
& $env:TEMP\install.ps1
```
(if the repo is private, `irm` cannot fetch the script; clone first with
`git clone --depth 1 --filter=blob:none https://github.com/danengerer-sudo/VAS C:\renderfarm\VAS` -- Git
Credential Manager pops up a GitHub login -- and run
`powershell -ExecutionPolicy Bypass -File C:\renderfarm\VAS\freemarket_defense\renderfarm\install.ps1`.)

The installer asks for:

| prompt | what to enter |
|---|---|
| git branch | branch the cloud side pushes jobs to (`claude/low-poly-helicopter-glb-d0l1zs` for now) |
| worker name | unique per PC, e.g. `minipc1`, `minipc2` |
| blender.exe path | accept the detected `C:\Program Files\Blender Foundation\Blender 4.2\blender.exe` |
| rclone remote:path | `gdrive:renderfarm`, or empty to zip into outbox |
| bench_url | direct download link to `bench.blend` (can stay empty if the file is copied by hand) |
| poll interval | 5 minutes is fine |

It then:
* clones the repo shallow + blobless (`--depth 1 --filter=blob:none`) so the big library thumbnails
  are never downloaded; job blends are fetched on checkout only,
* writes `config.json`,
* registers Task Scheduler task **RenderfarmAgent** (runs `start_agent.bat` 1 min after logon, no time
  limit, restart on failure every 2 min up to 999 times, runs as your user so Blender sees the GPU),
* sets the power plan to never sleep / hibernate on AC (`powercfg`),
* offers to run the benchmark and start the agent.

Also set Windows to **log on automatically** after a reboot (otherwise the task waits at the login
screen after a Windows Update restart): `netplwiz` > untick "Users must enter a user name and
password" (if hidden: `HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\PasswordLess\Device\DevicePasswordLessBuildVersion = 0`),
or `Settings > Accounts > Sign-in options > "Require sign-in: Never"`.
Consider `Settings > Windows Update > Advanced options > Active hours` = 09:00-21:00 so it never reboots
mid-render at night.

### First push = GitHub login
The agent's first `git push` triggers Git Credential Manager: a browser window asks you to sign in to
GitHub and authorize. Do that once (run `bench.bat` right after install, it pushes a tiny file). The
token is stored in Windows Credential Manager. The GitHub account needs write access to the repo.

## 3. Daily use

| action | how |
|---|---|
| is it running? | `Get-ScheduledTask RenderfarmAgent` or look for the "renderfarm agent" console window; `type C:\renderfarm\VAS\freemarket_defense\renderfarm\logs\agent.log` |
| start by hand | double-click `start_agent.bat` (refuses to start twice) |
| stop | double-click `stop_agent.bat` -- kills agent + headless Blender; the chunk resumes from the last finished frame |
| disable autostart | `schtasks /Change /TN RenderfarmAgent /DISABLE` (`/ENABLE` to undo) |
| benchmark | `bench.bat` -> `bench\bench_result.json` is pushed; read it from any clone or `python status.py --bench` |
| update the agent | `git -C C:\renderfarm\VAS pull` (the agent itself pulls every poll, but python code only reloads on restart: run `stop_agent.bat`, then `start_agent.bat`) |
| manual frame upload | if `rclone_remote` is empty, upload `C:\renderfarm\outbox\<job_id>\*.zip` (each <= 1.9 GB) by hand |

`Ctrl-C` in the agent window stops cleanly: the running Blender is terminated, a half-written frame is
deleted, progress is pushed, and on restart the agent re-renders only the missing frames of its chunk.

## 4. How a job is processed (for debugging)

1. every `poll_minutes`: `git pull --rebase` on the configured branch,
2. for each `jobs/<id>/` (ordered by `priority`, then id) without `done.json`/`failed.json`:
   split `frame_start..frame_end` into `chunk`-frame chunks (240 default). Our own unfinished claims
   come first, then the first chunk nobody claims. A claim = our `claims/<worker>.json` listing the
   chunk with a UTC timestamp, committed and pushed; if two workers claim the same chunk the earlier
   timestamp wins and the loser yields. Claims older than `claim_stale_hours` with no progress are
   treated as free (crashed worker).
3. the blend: `jobs/<id>/<file>.blend` from git (LFS pointers are pulled), or `blend_url` downloaded
   once to `jobs/<id>/_dl/`,
4. Blender runs headless once per chunk, only for frames whose PNG is missing or < 1 KB:
   ```
   blender.exe -b <blend> --python-expr "<resolution, samples, persistent data, HIP/CPU>" -E BLENDER_EEVEE_NEXT -o jobs\<id>\frames\f_#### -F PNG -x 1 -f 1..240
   ```
   stdout goes to `jobs/<id>/logs/blender_<worker>.log`; each `Saved:` line is timed,
5. `progress/<worker>.json` is updated per frame locally and pushed every `push_minutes` (10),
6. when the chunk is complete its frames are uploaded (`rclone copy` to `<remote>/<id>/frames/`, or
   zipped to outbox), the chunk is marked `done` and pushed,
7. when every chunk of the job is `done`, `done.json` (frame count, total time, s/frame, workers) is
   pushed. Any exception while handling a job writes `failed.json` and the loop moves on.

## 5. GPU notes

* **EEVEE (`BLENDER_EEVEE_NEXT`) is the intended engine.** It renders through the GPU driver
  (OpenGL/Vulkan) automatically on Windows; nothing to configure. The Radeon 760M has ~1-2 TFLOPS and
  shares the 16 GB RAM, so keep scenes below ~6 GB of textures and expect 1080p/16 spp frames in the
  tens of seconds (run `bench.bat` to know).
* **CYCLES**: the agent's `--python-expr` tries `compute_device_type='HIP'` and falls back to CPU.
  Blender 4.2 HIP officially supports RDNA2/RDNA3 **discrete** cards (RX 6000/7000); the 760M (RDNA3
  iGPU, gfx1103) is **not on the supported list** and usually shows no HIP device, so Cycles will run on
  the 6-core CPU -- slow. Use Cycles only for small tests. If the AMD driver does expose HIP for the
  760M, the log shows `AGENT: cycles device HIP: [...]`.
* Running Blender in the background while someone uses the PC is fine; the GPU is shared.
* If EEVEE renders fail with GPU/driver errors (`GPU failed to find function`, `Vulkan`), update the
  Adrenalin driver, and as a last resort add `"blender_extra_args": ["--gpu-backend", "opengl"]` to
  `config.json`.

## 6. Running two mini PCs

Install on both with different `worker` names; they pull the same branch and share each job chunk by
chunk. Pushes are small text files; the rare push race is resolved by `pull --rebase` + retry, and
a logical double-claim is resolved by the earlier timestamp. Both upload to the same
`rclone_remote/<job_id>/frames/`, so the Drive folder ends up with the full sequence.

## 7. Troubleshooting

| symptom | fix |
|---|---|
| `config not found` | copy `config.example.json` to `config.json` or run `install.ps1` |
| `blender executable not found` | check the `"blender"` path; forward slashes are fine |
| job stays `QUEUED` | agent not running / branch mismatch (`"branch"` in config vs. where submit pushed) / `git pull` failing (see `logs\agent.log`) |
| `failed.json` with `blend not found` | the job has neither the blend file nor a working `blend_url` (Google Drive links need the `uc?export=download&id=` form and files > ~100 MB hit the virus-scan page; prefer Dropbox `?dl=1`, S3, or commit via LFS) |
| frames pink / missing textures | the blend was not packed on the cloud side (`File > External Data > Pack Resources`) |
| push rejected / auth error | run `git -C C:\renderfarm\VAS push` once by hand to redo the GitHub login |
| PC went to sleep | re-run `install.ps1 -NoTask` (re-applies powercfg) or check `powercfg /q` |
| `rclone` failed | run `rclone lsd gdrive:` by hand; re-auth with `rclone config reconnect gdrive:` |
