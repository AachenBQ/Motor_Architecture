# Infineon Third-Party Packages

Vendored package:

- `iLLD_1_0_1_20_0_TC37A/`

Source on this machine:

```text
C:\Infineon\AURIX-Studio-1.10.16\build_system\bundled-artefacts-repo\project-initializer\tricore-tc3xx\1.16-17\iLLDs\Full_Set\iLLD_1_0_1_20_0__TC37A.zip
```

Package metadata copied from ADS:

- `tc3xx_project_initializer_1.16_package.json`
- `versionName`: `1.16`
- package revision: `17`
- `illd_version`: `1.0.1.20.0`

Why TC37A: the project targets the TC375 Lite kit, which is part of the TC37x
family. The ADS bundle also contains TC37AED and other derivatives, but TC37A is
the non-emulation-device package that matches this board class.

Refresh procedure:

1. Install or update AURIX Development Studio.
2. Check the TC3xx project initializer `package.json` and confirm the iLLD
   version.
3. Replace `iLLD_1_0_1_20_0_TC37A/` with the matching TC37A zip contents.
4. Copy the matching TC37A startup/linker templates into
   `firmware/bsp/tc37a_ads/`.
5. Re-run the host smoke tests so the FreeRTOS/SimpleFOC side stays clean.
