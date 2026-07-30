# Motor Architecture Codex notes

## Live Motor Studio debugging

When the user asks to diagnose a running upper-computer/device session, use the
in-process bridge instead of opening the serial port from a second process:

```powershell
cd upper_computer
python -m motor_control.codex_client status
python -m motor_control.codex_client diagnostics
python -m motor_control.codex_client logs --limit 100
```

Run `python -m motor_control.codex_client --help` for the complete command
list. The bridge is available only while Motor Studio is running.

- Start with `status`, then inspect device info, build config, diagnostics,
  logs, and recent history.
- Read/query/connect actions and stop actions are available in read-only mode.
- Never request enable, PID/target changes, or open-loop start unless the user
  explicitly asked for live control and has armed the 10-minute Codex control
  window in the GUI.
- If firmware reports that the real power stage is enabled, enable/start also
  requires the user's explicit power-stage confirmation.
- On uncertain state, send `quick-stop`; use `emergency-stop` when device state
  or communications cannot be trusted.
- Do not weaken firmware heartbeat, current, voltage, temperature, nFAULT, or
  physical emergency-stop protection through this bridge.

Full usage and safety details are in `upper_computer/CODEX_DEBUG.md`.

## AURIX Development Studio ownership

- All AURIX Development Studio (ADS) operations belong to the user. Never
  launch, control, or automate ADS, including `AURIX-studio.exe`,
  `AURIX-studioc.exe`, IDE/headless builds, Clean/Build, download, flash,
  debug, resume, or stop-debug actions.
- Codex may inspect source code, existing build artifacts, maps, logs, and
  compiler output, and may tell the user exactly which ADS operation to run.
  Wait for the user to run it and provide the result.
- While waiting for any external process, build, debug step, or long-running
  command to finish, do not emit interim commentary or progress messages.
  Respond only when it finishes, fails, times out, the user asks for status,
  or user input is required.
