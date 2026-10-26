Generated on the Brev Isaac launchable (Isaac Sim 6.0.1); paths are on that machine.

# Digital Twin Map: CSI Fluid Mixing Station (Card 6)

This document provides a plain-English reference for the CSI Digital Twin (`csi_digital_twin_v1`), explaining its file layout, main scene, cameras, compatibility, and rendering workflow.

---

## 1. Directory and File Breakdown

The digital twin is located at `/workspace/project/twin/csi_digital_twin_v1/`. Here is what every file and folder does:

| Path | Purpose (Plain English) |
| :--- | :--- |
| `csi_line.usda` | **The Main Scene.** A text-based USD file that references all four stations together into the complete production line. |
| `README.md` | Organizers' documentation explaining units (meters, Z-up), coordinates, camera settings, animation frames, and quick-start commands. |
| **`cameras/`** | **Virtual camera configurations (JSON files).** |
| `cameras/FillCam.json` | Settings for the `vial_fill` camera: 640×480 resolution, ~41 mm focal length, pinhole projection (no distortion), and timeline animation bounds (frames 1–686). |
| `cameras/CapSealCam.json` | Settings for the `cap_seal` camera: 640×480 resolution, rendered with overscan (768×576) to simulate optical barrel distortion matching the physical robot inspection camera. |
| **`stations/`** | **3D models for each physical segment of the factory line.** |
| `stations/fill_station/fill_station.usda` | The fill station scene. Contains the pre-recorded dispensing animation (frames 1–686 at 30 fps) controlling when the liquid stream appears and rises in the vial. |
| `stations/fill_station/geometry/fill_station.usdc` | Binary USD file containing the actual 3D geometry (nozzles, vial holders, brackets, and vials). |
| `stations/fill_station/geometry/textures/color_B7C6CE.exr` | High dynamic range image texture applied to fill station metallic/plastic surfaces. |
| `stations/tray_inspection/tray_inspection.usdc` | Binary USD file for the robot cap/seal inspection station, inspection trays, and vials. |
| `stations/magnemover/magnemover.usdc` | Binary USD file for the MagneMover magnetic conveyor track and puck carts. |
| `stations/facility/facility.usdc` | Binary USD file for the plant environment (concrete floor, walls, structures, and dome lighting). |
| `stations/facility/textures/color_84847F.exr` | High dynamic range texture for the facility environment lighting and background. |
| **`previews/`** | **Reference renders from the organizers.** |
| `previews/fill_station_rtx.png` | Example RTX path-traced render showing what the fill station camera looks like when rendered correctly. |
| `previews/tray_inspection_rtx.png` | Example RTX path-traced render of the tray inspection station. |
| **`tools/`** | **Helper scripts provided with the twin.** |
| `tools/render_example.py` | Reference Python script to launch Isaac Sim headless, load a stage, jump to an animation frame, and render an image using NVIDIA Replicator. |
| `tools/apply_lens.py` | Post-processing script that takes a raw render from `CapSealCam` and applies realistic lens distortion using OpenCV. |

---

## 2. Key Questions Answered

### Which file is the main scene?
* **`csi_line.usda`** is the main scene. It does not contain raw 3D polygon meshes itself; instead, it acts as the master conductor that links the four stations (`facility`, `magnemover`, `tray_inspection`, and `fill_station`) and positions them accurately on the factory floor.
* *Note on speed:* For tasks focusing only on the fill station, loading `stations/fill_station/fill_station.usda` directly is much faster (a few megabytes vs. ~700 MB for the entire plant).

### Where is the `vial_fill` camera located?
* The camera is named **`FillCam`**.
* In the full line (`csi_line.usda`), its USD prim path is:
  ```
  /CSI_Line/FillStation/FillStation_LocalRoot/FillCam/FillCam
  ```
* In the isolated station file (`stations/fill_station/fill_station.usda`), its USD prim path is:
  ```
  /FillStation/FillStation_LocalRoot/FillCam/FillCam
  ```
* Its optical settings are saved in `cameras/FillCam.json`. It is a pinhole camera producing standard 640×480 images without lens warping.

### Which Isaac Sim version does it expect, and does it match this machine?
* **Expected version:** In `README.md` (line 79), the twin specifies:
  > `Tested with: Isaac Sim 6.0.`
* **Installed machine version:** Reading `/isaac-sim/VERSION` reports:
  > `6.0.1-rc.7+release.42383.32955d8d.gl`
* **Verdict:** **Yes, it matches.** Version 6.0.1 is the release-candidate update of the Isaac Sim 6.0 branch and is fully compatible.

### How is the included render script meant to run?
The included script `tools/render_example.py` is executed through Isaac Sim's bundled Python runner (`/isaac-sim/python.sh`):

```bash
/isaac-sim/python.sh /workspace/project/twin/csi_digital_twin_v1/tools/render_example.py \
    --camera FillCam \
    --frame 686 \
    --out /workspace/project/renders/fill_686.png
```

**How it works step-by-step:**
1. Starts Isaac Sim in headless mode (`SimulationApp({"headless": True, "renderer": "PathTracing", ...})`).
2. Loads the USD stage (`csi_line.usda` or a station file).
3. Moves the virtual timeline to the specified frame number (the filling animation spans frames 1 to 686 at 30 fps; frame 1 is empty, frame 301 is mid-fill, frame 686 is fully filled).
4. Creates an NVIDIA Replicator render product targeting the camera prim.
5. Runs RTX path-tracing steps (`rep.orchestrator.step(...)`) to let light bounces converge.
6. Pulls the rendered RGB pixels from the GPU memory and saves them as a PNG via OpenCV.

---

## 3. Card 7 Updates: Liquid Modeling, Stripes Cause, and Patch Alignment

### What caused the horizontal stripes?
In the initial Card 6 test renders, the liquid inside the vial showed distinct horizontal stripes. In Card 7 Step 1, we rendered frame 686 with 4× more path-tracing samples (256 spp vs 64 spp). The stripes remained identical, proving they were not render noise.
Investigation revealed three root causes:
1. **Surface Opacity Shading:** The twin's original animated liquid (`stations/fill_station/geometry/fill_station.usdc`) used surface opacity rather than true physical volumetric absorption through the fluid depth.
2. **Background Structure Transmission:** The horizontal bars of the factory background and conveyor brackets behind the transparent vial were transmitted directly through the flat opacity shader.
3. **Geometry Overlap:** The animated liquid mesh was slightly wider than the inner glass vial wall, causing surface overlapping and z-fighting against the glass boundary.

### Replacing the liquid at render time (without editing organizers' files)
To maintain complete integrity of the organizers' digital twin files, we never edit the USDA or USDC files on disk. Instead, `scripts/set_liquid.py` dynamically modifies the USD stage in memory at render time:
1. Deactivates and hides the twin's pre-recorded animated liquid prim (`Fluid_Filling_A_FillStation_Geo`).
2. Creates a clean volumetric cylinder mesh positioned at the physical bottom cavity floor (`Z = 0.1311` inches) with radius `13.133 mm` (exactly `0.05 mm` inside the inner glass radius `13.183 mm` to prevent z-fighting).
3. Binds an NVIDIA OmniSurface MDL material configured with physical volumetric absorption (Beer–Lambert attenuation across the transmission depth of `26.27 mm`), parameterized by orange share, blue share, fill volume (10–80 mL), and vertical mixing stratification.

### Measurement patch coordinates (unchanged)
Because `FillCam` aligns with the physical station's `vial_fill` camera, our measurement patch coordinates sit at the exact same pixel positions in the twin as on the real camera:
- **`HIGH` patch:** $x \in [302, 318], \quad y \in [268, 288]$ (centered in front of the white paper backdrop).
- **`LOW` patch:** $x \in [302, 318], \quad y \in [352, 372]$ (centered in front of the dark conveyor).
- **`BLANK_HIGH` patch:** $x \in [410, 426], \quad y \in [268, 288]$ (on the neighbouring empty vial in the next starwheel pocket).
- **`BLANK_LOW` patch:** $x \in [410, 426], \quad y \in [352, 372]$ (on the neighbouring empty vial in the next starwheel pocket).

