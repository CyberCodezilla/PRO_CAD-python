# Python CAD Pro 📐⚡

[![Python 3.10+](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![OpenCASCADE Ready](https://img.shields.io/badge/Kernel-OpenCASCADE%20%7C%20Manifold3D-orange.svg)](https://dev.opencascade.org/)
[![Tests Passing](https://img.shields.io/badge/Tests-27%2F27%20Passed-brightgreen.svg)]()
[![STEP AP214](https://img.shields.io/badge/STEP-ISO%2010303--21%20AP214-blueviolet.svg)]()

> **Industrial-grade 2D drafting, parametric constraint solving, and intelligent 3D orthographic reconstruction.**  
> Transform standard 2D multi-view engineering drawings into watertight, manifold 3D solids and manufacturing-grade STEP models in real time.

<p align="center">
  <img src="https://github.com/user-attachments/assets/d73bca41-0067-4661-b0d6-74484ad682ba" alt="Python CAD Pro Orthographic to 3D Demonstration" width="92%" />
  <br>
  <em>Real-time orthographic multi-view 2D drafting seamlessly reconstructed into an artifact-free 3D solid model.</em>
</p>

---

## 🌟 What Problem Does Python CAD Pro Solve?

In traditional manufacturing and mechanical engineering, there is a massive friction point between **2D engineering blueprints** and **3D parametric CAD modeling**:

1. **Manual Re-Modeling Overhead**: Engineers receive 2D multi-view technical drawings (Top, Front, Side) and must manually recreate 3D parts feature-by-feature in expensive CAD software (SolidWorks, Siemens NX, CATIA).
2. **Orthographic Ambiguity**: Under-constrained 2D drawings often yield multiple topologically valid 3D solids (e.g. blind pockets vs through-holes vs wedges). Most CAD tools cannot detect or resolve these ambiguities.
3. **Viewport Triangulation Artifacts**: Standard polygon triangulation algorithms (ear-clipping) create diagonal crease bands and gradient shading across flat faces with internal holes.
4. **Heavy Kernel Bottlenecks**: Full B-Rep boolean operations freeze interactive user interfaces, while lightweight tools lack true ISO 10303 STEP export capabilities.

**Python CAD Pro solves this** with an automated, dual-kernel reconstruction pipeline that turns 2D orthographic sketches into validated 3D solid geometry and STEP AP214 assemblies instantly.

```
       2D Technical Drawings               Intelligent CAD Engine                 3D Manufacturing Output
  +-------------------------------+      +--------------------------+      +---------------------------+
  |  Quadrant II   |  Quadrant I  |      | - 2D Constraint Solver   |      | - Sub-50ms Realtime CSG   |
  |   FRONT VIEW   |  SIDE VIEW   | ---> | - ASME Y14.5 CAD Doctor  | ---> | - OpenCASCADE B-Rep STEP  |
  |----------------+--------------|      | - Ambiguity Disambiguator|      | - Seam-Free OpenGL 3D GPU |
  |  Quadrant III  |  Quadrant IV |      | - CCW Normal Normalizer  |      | - STL / OBJ / 3MF Export  |
  |    TOP VIEW    |  45° MITER   |      +--------------------------+      +---------------------------+
  +-------------------------------+
```

---

## 🚀 Key Architectural Features

### 1. Dual-Kernel 3D Reconstruction Engine
- **Real-Time Interactive CSG Kernel (Sub-50ms)**: Uses `shapely` for 2D profile compilation and `manifold3d` / `trimesh` for instant, non-blocking volumetric boolean preview as you draw.
- **Asynchronous OpenCASCADE B-Rep Kernel**: Runs in a dedicated background `QThread`, evaluating topological solid operations via OpenCASCADE Technology (`build123d` / `cadquery`) and producing exact boundary representation geometry.
- **ISO 10303 STEP AP214 Exporter**: Generates industry-standard STEP text files directly importable into SolidWorks, Siemens NX, and FreeCAD, with a built-in pure-Python fallback.

### 2. Standardized First-Angle / European Orthographic Layout
Full alignment with international engineering graphics standards:
- **Quadrant II (Top-Left)**: `Front View (XY Elevation Plane)` ($X \le 0, Y \le 0$)
- **Quadrant I (Top-Right)**: `Side View (ZY Profile Plane)` ($X \ge 0, Y \le 0$)
- **Quadrant III (Bottom-Left)**: `Top View (XZ Plan Plane)` ($X \le 0, Y \ge 0$)
- **Quadrant IV (Bottom-Right)**: `45° Miter Guide Ray` ($(0,0) \rightarrow (+t, +t)$)
- **Datum Inversion & Winding Normalization**: Automatic vertical coordinate inversion ($v = -p_y$) and `shapely.geometry.polygon.orient(poly, sign=1.0)` guarantee CCW orientation and positive volumetric orientation ($\text{Volume} > 0$).

### 3. Parametric 2D Geometric Constraint Solver
- SolveSpace C-API binding with a robust **Levenberg-Marquardt optimizer fallback**.
- Support for **Coincident, Horizontal, Vertical, Distance, Radius, and Tangent** constraints.
- Real-time visual glyph badges (`[H]`, `[V]`, `[T]`, `[D:50]`, `[R:25]`) displayed dynamically on the canvas.

### 4. ASME Y14.5 CAD Doctor & Topology Disambiguation
- **Diagnostic Rules Engine (Rules 1–14)**: Detects open contour micro-gaps, dangling endpoints, cross-view dimension mismatches, and improper layer assignments.
- **Multi-Topology Disambiguation**: Identifies ambiguous orthographic interpretations and generates alternative 3D solid candidates ($S_1, S_2, \dots$), selectable via an interactive **Candidate Switcher HUD** in the 3D viewport.

### 5. Crease-Aware Split Normal GPU Viewport (OpenGL 3.3+)
- **Artifact-Free Planar Faces**: Proprietary `_compute_crease_aware_normals` algorithm isolates planar faces from perpendicular pocket/hole walls, completely eliminating diagonal ear-clipping gradient bands on flat faces with cutouts.
- **Hardware-Accelerated VBO Streaming**: Direct GPU memory streaming via `glDrawArrays` and compiled Vertex Array Objects (VAOs).
- **Interactive Section Plane**: Real-time cross-section clipping along X, Y, or Z axes (`glClipPlane`).
- **360° Freelook Camera**: Unclamped turntable orbit, smooth panning, and 1-click standard snaps (Top, Bottom, Front, Back, Left, Right, Iso).

### 6. AI Blueprint & Raster CAD Vectorizer
- **Vectorized Zhang-Suen Thinning**: Fast NumPy morphological skeletonization for scanned blueprints and raster engineering sketches.
- **Feature Extraction & Repair**: Micro-gap snapping, collinear segment merging, and automated text/dimension annotation masking.
- **GNN Inference Bridge**: SketchGraph / Ortho2CAD bridge for inferring missing cross-view edges.

---

## 📦 Project Structure

```
python-cad-pro/
├── src/
│   ├── engine/                 # Core CAD data models, constraint solver, rules
│   │   ├── cad_engine.py       # Entity database, view regions, history stack
│   │   ├── constraint_solver.py # Levenberg-Marquardt parametric solver
│   │   └── rules_engine.py     # ASME Y14.5 validation & ambiguity detector
│   ├── reconstruction/         # 2D-to-3D reconstruction pipelines
│   │   ├── reconstructor.py    # Multi-threaded CSG boolean reconstructor
│   │   ├── brep_reconstructor.py # Asynchronous OpenCASCADE B-Rep kernel
│   │   └── step_exporter.py    # ISO 10303-21 STEP AP214 exporter
│   ├── cv/                     # Computer vision & vectorization
│   │   ├── ai_vectorizer.py    # Collinear merging, snapping, GNN bridge
│   │   └── onnx_vectorizer.py  # Vectorized morphological thinning & OCR mask
│   └── ui/                     # PyQt6 GUI & PyOpenGL rendering
│       ├── canvas.py           # 2D drafting canvas, snapping, 45° miter guide
│       ├── viewport_3d.py      # Crease-aware OpenGL 3D viewport with VBOs
│       ├── main_window.py      # Main application window, docks, command console
│       └── toolbar.py          # CAD action tools & layer switchers
├── tests/                      # Automated test suite (27 comprehensive unit tests)
│   ├── test_reconstruction.py  # Volumetric verification (box, cylinder, pipe)
│   ├── test_brep_step.py       # OpenCASCADE B-Rep volume & STEP validation
│   ├── test_constraint_solver.py # Parametric constraint math tests
│   ├── test_feature_blends.py  # 2D/3D fillet & chamfer execution tests
│   ├── test_onnx_vectorizer.py # Morphological thinning & masking tests
│   ├── test_ai_vectorizer.py   # Collinear merging & gap snapping tests
│   ├── test_ambiguity_disambiguation.py # Multi-topology candidate tests
│   └── test_quadrant_inversion_fix.py # Section 5.1 First-Angle coordinate tests
├── packaging/                  # Standalone deployment
│   ├── cad_pro.spec            # PyInstaller spec with OpenCASCADE DLL hooks
│   └── build_standalone.py     # Multi-platform distribution builder
├── main.py                     # Application entry point
└── requirements.txt            # Project dependencies
```

---

## 🛠️ Installation & Getting Started

### Prerequisites
- **Python 3.10+** (Tested on Python 3.10, 3.11, 3.12, 3.13)
- Windows 10/11, macOS, or Linux
- OpenGL 3.3+ compatible GPU

### 1. Clone the Repository
```bash
git clone https://github.com/CyberCodezilla/PRO_CAD-python.git
cd PRO_CAD-python
```

### 2. Create and Activate a Virtual Environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Launch Python CAD Pro
```bash
python main.py
```

---

## 📖 How to Use

### Basic 2D-to-3D Workflow
1. **Select an Orthographic View**: Use the View Mode toolbar to switch between **Front (XY)**, **Side (ZY)**, and **Top (XZ)** views.
2. **Draw Visible Profiles**: Select the **Rectangle**, **Line**, or **Circle** tool on the **Visible Layer (Cyan)** to draw the outer boundary of your part.
3. **Draw Holes & Pockets**: Switch to the **Hidden Layer (Dashed Amber)** to draw internal cutouts, boreholes, or through-slots.
4. **Add Constraints**: Select geometries and apply constraints (`Horizontal`, `Vertical`, `Distance`, `Tangent`) to lock dimensions.
5. **Real-Time 3D Mesh**: Watch the 3D solid reconstruct in real time in the right-hand viewport!
6. **Export Models**: Navigate to `File -> Export 3D Mesh` to save as **STEP AP214**, **STL**, **OBJ**, or **3MF**.

---

## ⌨️ AutoCAD-Style Command Console

The bottom command bar supports AutoCAD-compatible hotkeys and numerical offsets:

| Command | Action |
| :--- | :--- |
| `l` or `line` | Activate Line drafting tool |
| `rec` or `rect` | Activate Rectangle drafting tool |
| `c` or `circle` | Activate Circle drafting tool |
| `a` or `arc` | Activate 3-Point Arc tool |
| `p` or `polygon`| Activate Polygon tool |
| `d` or `dim` | Activate Associative Dimensioning tool |
| `s` or `select` | Activate Entity Selection / Transform tool |
| `dx,dy` | Relative coordinate offset input (e.g. `100,-50`) |
| `#x,y` | Absolute world coordinate placement (e.g. `#-200,150`) |
| `value` | Lock active segment length or circle radius to `value` |
| `undo` / `redo`| Undo or Redo database operations |
| `clear` | Clear active canvas geometry |

---

## 🧪 Automated Verification & Testing

The platform includes a test suite with **27 industrial-grade unit tests** verifying geometric accuracy, volumetric consistency, constraint solving, and STEP topology.

Run the test suite with:
```powershell
python -m pytest tests/ -v
```

```
============================= test session starts =============================
platform win32 -- Python 3.13.7, pytest-8.4.2, pluggy-1.6.0
collected 27 items

tests/test_ai_vectorizer.py::test_collinear_segment_merging PASSED       [  3%]
tests/test_ai_vectorizer.py::test_endpoint_micro_gap_snapping PASSED     [  7%]
tests/test_ai_vectorizer.py::test_gnn_missing_edge_inference PASSED      [ 11%]
tests/test_ambiguity_disambiguation.py::test_ambiguity_diagnostic_detection PASSED [ 14%]
tests/test_ambiguity_disambiguation.py::test_candidate_solid_generation PASSED [ 18%]
tests/test_brep_step.py::test_brep_box_reconstruction PASSED             [ 22%]
tests/test_brep_step.py::test_faceted_step_exporter_fallback PASSED      [ 25%]
tests/test_constraint_solver.py::test_horizontal_constraint PASSED       [ 29%]
tests/test_constraint_solver.py::test_vertical_constraint PASSED         [ 33%]
tests/test_constraint_solver.py::test_distance_constraint PASSED         [ 37%]
tests/test_constraint_solver.py::test_radius_constraint PASSED           [ 40%]
tests/test_constraint_solver.py::test_coincident_constraint PASSED       [ 44%]
tests/test_constraint_solver.py::test_tangent_constraint PASSED          [ 48%]
tests/test_feature_blends.py::test_2d_corner_blend_detection PASSED      [ 51%]
tests/test_feature_blends.py::test_3d_topological_fillet_execution PASSED [ 55%]
tests/test_feature_blends.py::test_fillet_oversize_graceful_fallback PASSED [ 59%]
tests/test_onnx_vectorizer.py::test_vectorized_zhang_suen_thinning PASSED [ 62%]
tests/test_onnx_vectorizer.py::test_text_and_annotation_masking PASSED   [ 66%]
tests/test_quadrant_inversion_fix.py::test_front_view_bottom_wheels_orientation PASSED [ 70%]
tests/test_reconstruction.py::test_box_reconstruction PASSED             [ 74%]
tests/test_reconstruction.py::test_cylinder_reconstruction PASSED        [ 77%]
tests/test_reconstruction.py::test_hollow_pipe_reconstruction PASSED     [ 81%]
tests/test_reconstruction.py::test_view_region_and_guardrails PASSED     [ 85%]
tests/test_reconstruction.py::test_alignment_validation PASSED           [ 88%]
tests/test_reconstruction.py::test_rules_engine_evaluations PASSED       [ 92%]
tests/test_reconstruction.py::test_third_angle_lhs_depth_mapping PASSED  [ 96%]
tests/test_reconstruction.py::test_offset_third_angle_profiles_share_the_same_depth_range PASSED [100%]

============================= 27 passed in 7.76s ==============================
```

---

## 🏗️ Standalone Binary Packaging

To bundle Python CAD Pro into a standalone executable:
```bash
python packaging/build_standalone.py
```
The resulting executable will be created in the `dist/` directory, bundling all Qt, OpenCASCADE, and PyOpenGL dynamic libraries automatically.

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome!  
Feel free to check the [issues page](https://github.com/CyberCodezilla/PRO_CAD-python/issues).

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

Developed with ❤️ by **[Sahil Rane (CyberCodezilla)](https://github.com/CyberCodezilla)**.
