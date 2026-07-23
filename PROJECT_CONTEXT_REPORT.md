# Python CAD Pro — Complete Project Architecture, Logic, and Backend Technical Report

> **Target Audience:** AI Coding Assistants, System Architects, Core Developers  
> **Repository Name:** `python-cad-pro`  
> **Language / Frameworks:** Python 3.13+, PyQt6, OpenGL (PyOpenGL), Trimesh, Shapely, NumPy, Pytest  
> **Core Purpose:** Professional 2D Orthographic CAD Drafting & Real-Time CSG 3D Solid Model Reconstruction Engine

---

## 1. Executive Summary & System Vision

**Python CAD Pro** is an engineering-grade Computer-Aided Design (CAD) desktop application built in Python and PyQt6. It provides a **Unified 2D Drafting Sheet** for standard engineering graphics (Top View, Front View, Left/Right Hand Side Views) and automatically reconstructs fully watertight 3D solid CAD models using **Constructive Solid Geometry (CSG)**.

Key capabilities include:
1. **Unified 2D Infinite Canvas:** Single interactive drafting scene with pre-initialized 4-quadrant orthographic regions (Top, Front, LHS/RHS Views).
2. **Explicit Mathematical Guardrails:** Bottom-left region origins, strict canvas Y-inversion, RHS view mirroring, and automated depth/alignment validation.
3. **CSG 3D Reconstruction Pipeline:** Multi-threaded asynchronous extrusion using 4x4 homogeneous transformation matrices, subtractive interior features (holes/slots), and 3D boolean intersection via `trimesh` and `shapely`.
4. **Interactive 3D OpenGL Viewport:** Orbit/pan/zoom camera with shaded mesh rendering, wireframe overlays, lighting, and origin axes.

---

## 2. System Architecture & Component Mapping

```
                             +-------------------------------+
                             |    main.py (App Launcher)     |
                             +---------------+---------------+
                                             |
                                             v
                             +---------------+---------------+
                             | MainWindow (PyQt6 QMainWindow)|
                             +-------+---------------+-------+
                                     |               |
             +-----------------------+               +-----------------------+
             |                                                               |
             v                                                               v
+------------+------------------+                          +-----------------+-----------------+
|  DrawingCanvas (2D PyQt6 Scene)|                          |   GLViewport (3D PyOpenGL Canvas) |
|  - Infinite 4-Quadrant View   |                          |   - Orbit / Pan / Zoom Camera     |
|  - Snap Engine (Grid/Object)  |                          |   - Shaded & Wireframe Mesh Render|
|  - Dynamic Cursor HUD         |                          +-----------------+-----------------+
|  - 45° Miter Guide Line       |                                            ^
+------------+------------------+                                            |
             |                                                               | (finished_reconstruction)
             v                                                               |
+------------+------------------+                          +-----------------+-----------------+
|    CADEngine (State & Math)   |==== (Triggers Signal) ===>| ReconstructionWorker (QThread)  |
|  - Shapes & Layer Management  |                          |  - Profile Extraction (Shapely) |
|  - Active View Mode Selector  |                          |  - 4x4 Transformation Matrices  |
|  - ViewRegion Guardrails      |                          |  - CSG Intersection (Trimesh)   |
|  - Alignment Validation Math  |                          |  - Watertight Repair Safeguards |
+-------------------------------+                          +---------------------------------+
```

### Module File Map

| File Path | Description & Responsibility |
| :--- | :--- |
| `main.py` | Application entry point; initializes `QApplication` and `MainWindow`. |
| `src/engine/cad_engine.py` | Core data model, shape primitives, `ViewRegion` definitions, layer management, centroid assignment, local coordinate transformation, and alignment math validation. |
| `src/ui/canvas.py` | `QGraphicsView` 2D drafting sheet canvas. Handles mouse/keyboard input, preview rendering, snap engine (grid & object), ortho lock (`Shift`), dynamic cursor HUD, infinite quadrant visual overlays, and 45° Miter line rendering. |
| `src/ui/toolbar.py` | Vertical left-side control panel. Contains tool buttons (`Select`, `Region`, `Line`, `Rectangle`, `Circle`, `Polygon`), **ACTIVE VIEW** mode selector (`Auto`, `Front View`, `Top View`, `LHS View`, `RHS View`), and **ACTIVE LAYER** dropdown (`Visible`, `Hidden`, `Construction`). |
| `src/ui/main_window.py` | Top-level window hosting the splitter view, menu bars, console output, status bar, and signal-slot bindings between 2D canvas, CAD engine, and 3D reconstructor worker. |
| `src/ui/viewport_3d.py` | `QOpenGLWidget` displaying the reconstructed 3D solid model. Provides smooth ArcBall rotation, pan, zoom, lighting shaders, and axis indicators. |
| `src/reconstruction/reconstructor.py` | `QThread` background worker executing CPU-intensive CSG reconstruction. Assembles 2D profiles into Shapely polygons, extrudes them into 3D meshes, applies 4x4 coordinate transformation matrices, computes boolean intersections, and performs watertight repairs. |
| `tests/test_reconstruction.py` | Automated Pytest unit test suite covering shape operations, region origins, Y-inversion, centroid routing, depth alignment validation, and 3D CSG reconstruction. |

---

## 3. Core CAD Data Model & Geometric Primitives (`cad_engine.py`)

### 1. Shape Primitives & Layer System
All drafting geometries inherit from the `Shape` base class and belong to a specific CAD layer:
- **`Visible` Layer (`#00FFFF` Cyan):** Primary solid boundary outlines. Rendered with solid lines (`Qt.PenStyle.SolidLine`).
- **`Hidden` Layer (`#00FFFF` Cyan, Dashed):** Subtractive interior features (pocket cuts, through-holes, slots). Rendered with dashed lines (`[4, 2]`).
- **`Construction` Layer (`#555555` Dark Gray):** Alignment guidelines. Ignored during 3D reconstruction.

#### Primitive Data Structures:
- **`Line`:** `start: (x, y)`, `end: (x, y)`
- **`Rectangle`:** `rect: (x, y, width, height)`
- **`Circle`:** `center: (x, y)`, `radius: float`
- **`Arc`:** `center: (x, y)`, `radius: float`, `start_angle: float`, `end_angle: float`
- **`Polygon`:** `points: List[(x, y)]`
- **`Dimension`:** `start_pt`, `end_pt`, `label_pt`, `text`

### 2. View Regions & Mathematical Guardrails (`ViewRegion`)
Each view region on the 2D sheet is represented by a `ViewRegion` object:
- **`view_type`:** `'top'`, `'front'`, `'left_side'`, `'right_side'`
- **`bounds`:** `(min_x, min_y, max_x, max_y)`

#### Guardrail Rules:
1. **Bottom-Left Origin:** In 2D canvas space (where Y increases downwards), the local origin $(X_0, Y_0)$ for any finite `ViewRegion` is defined at the **bottom-left corner**: `(min_x, max_y)`. For infinite default quadrants, the origin is `(0.0, 0.0)`.
2. **Infinite Quadrant Boundaries:**
   - **Top View (Top-Left Quadrant):** $X \in (-\infty, 0], Y \in (-\infty, 0]$
   - **Front View (Bottom-Left Quadrant):** $X \in (-\infty, 0], Y \in [0, \infty)$
   - **LHS / RHS View (Bottom-Right Quadrant):** $X \in [0, \infty), Y \in [0, \infty)$
   - **45° Miter Space (Top-Right Quadrant):** $X \in [0, \infty), Y \in (-\infty, 0]$

---

## 4. Coordinate Transformation & Alignment Math

### 1. Canvas Y-Inversion & Axis Mapping
Computer graphics canvas Y-axis increases downwards, whereas 3D CAD coordinate space Y-axis increases upwards.
When converting absolute canvas coordinates $(Abs_X, Abs_Y)$ into local 2D view coordinates $(Local_X, Local_Y)$:

#### Front View & Side Views (XY / ZY Planes):
$$\begin{aligned}
Local\_X &= Abs\_X - X_0 \\
Local\_Y &= -(Abs\_Y - Y_0) = Y_0 - Abs\_Y
\end{aligned}$$

#### Top View (XZ Plane):
For the Top View, local vertical canvas movement maps to 3D Depth ($Z$-axis):
$$\begin{aligned}
Local\_X &= Abs\_X - X_0 \\
Local\_Z &= -(Abs\_Y - Y_0) = Y_0 - Abs\_Y
\end{aligned}$$

#### Right-Side View (RHS) Mirroring Math:
For a Right-Side View (looking from the right side back toward the left), the horizontal axis is reversed:
$$Local\_X = X_0 - Abs\_X$$

---

### 2. Centroid-Based Shape Assignment (`assign_shape_to_region`)
When the user draws a shape in `Auto (Centroid)` mode, the engine calculates the 2D centroid $(C_x, C_y)$ of the primitive:
- **Line:** $C_x = \frac{x_1 + x_2}{2}, C_y = \frac{y_1 + y_2}{2}$
- **Rectangle:** $C_x = x + \frac{w}{2}, C_y = y + \frac{h}{2}$
- **Circle / Arc:** $C_x = cx, C_y = cy$
- **Polygon:** $C_x = \frac{\sum x_i}{N}, C_y = \frac{\sum y_i}{N}$

The engine evaluates $C_x, C_y$ against quadrant boundaries:
- If $C_x \le 0$ and $C_y \le 0 \implies \text{'top'}$
- If $C_x \le 0$ and $C_y \ge 0 \implies \text{'front'}$
- If $C_x \ge 0$ and $C_y \ge 0 \implies \text{'side'}$ (LHS / RHS)

If an explicit **Active View Mode** is selected in the toolbar (`Front View`, `Top View`, `LHS View`, `RHS View`), shapes are directly assigned to that view regardless of cursor placement.

---

### 3. Engineering Graphics Alignment & Validation Math (`validate_alignment`)
Before running 3D CSG reconstruction, `CADEngine.validate_alignment(tolerance=5.0)` verifies geometric consistency across orthographic projections:

1. **Width Alignment (Top View vs. Front View):**
   $$\text{Top\_Width} = \max(X_{\text{top}}) - \min(X_{\text{top}})$$
   $$\text{Front\_Width} = \max(X_{\text{front}}) - \min(X_{\text{front}})$$
   $$\Delta_{\text{width}} = |\text{Top\_Width} - \text{Front\_Width}| \le 5.0$$

2. **Height Alignment (Front View vs. Side View):**
   $$\text{Front\_Height} = \max(Y_{\text{front}}) - \min(Y_{\text{front}})$$
   $$\text{Side\_Height} = \max(Y_{\text{side}}) - \min(Y_{\text{side}})$$
   $$\Delta_{\text{height}} = |\text{Front\_Height} - \text{Side\_Height}| \le 5.0$$

3. **Depth Validation (Top View Depth vs. Side View Depth):**
   $$\text{Top\_Depth} = \text{Top\_Region\_Height} = \max(Y_{\text{top}}) - \min(Y_{\text{top}})$$
   $$\text{Side\_Depth} = \text{Side\_Region\_Width} = \max(X_{\text{side}}) - \min(X_{\text{side}})$$
   $$\Delta_{\text{depth}} = |\text{Top\_Depth} - \text{Side\_Depth}| \le 5.0$$

---

## 5. Unified 2D Canvas & UI Interaction (`canvas.py`)

### 1. 45° Miter Line Geometry
In standard technical drawing layout, depth is projected between the Top View (top-left) and Side View (bottom-right) using a 45° miter line placed in the empty **Top-Right Quadrant** ($X \ge 0, Y \le 0$).

- **Origin:** Sheet origin $(0.0, 0.0)$.
- **Ray Direction:** Extends at 45 degrees UP and RIGHT into the top-right quadrant:
  $$\text{Ray}(t) = (0 + t, 0 - t) \quad \text{for } t \ge 0$$
- **Toggle Control:** Can be toggled on/off via `View -> Show 45° Miter Guide Line`.

### 2. Snap Engine & Ortho Lock
- **Grid Snap:** Snaps cursor coordinates to the nearest grid step (default $10.0\text{ mm}$).
- **Object Snap (OSNAP):** Snaps to key geometric handles within $12\text{ px}$:
  - Endpoints (`endpoint`)
  - Midpoints (`midpoint`)
  - Centers (`center`)
  - Quadrant points (`quadrant`)
- **Ortho Lock (`Shift` Key):** Constrains drawing to strict horizontal or vertical lines ($0^\circ, 90^\circ, 180^\circ, 270^\circ$).
  - *Fix Implemented:* Casts `mapFromScene(cursor_pos)` to `QPointF` to prevent PyQt6 type mismatch crashes.

---

## 6. 3D CSG Reconstruction Engine (`reconstructor.py`)

### 1. Asynchronous Execution Pipeline
The reconstruction process runs in a background `QThread` (`ReconstructionWorker`) to maintain 60 FPS UI responsiveness:

```
[2D Local Shapes] ---> [Shapely Profile Extraction] ---> [Linear Extrusion]
                                                                  |
                                                                  v
[3D Watertight Solid] <--- [CSG Intersection & Repair] <--- [4x4 Homogeneous Matrix]
```

### 2. Profile Extraction & Subtractive Feature Assembly (`_extract_view_profile`)
1. Primitives on the `Visible` layer are converted to Shapely `Polygon` or `MultiPolygon` objects and combined via `shapely.ops.unary_union(visible_polys)`.
2. Primitives on the `Hidden` layer are converted to subtractive shapes and removed from the outer boundary:
   $$\text{Final\_Profile} = \text{Union}(\text{Visible}) \setminus \text{Union}(\text{Hidden})$$

---

### 3. 4x4 Homogeneous Transformation Matrices
Each extruded view is transformed from local 2D extrusion space $(u, v, w)$ into unified 3D coordinate space $(X, Y, Z)$ using 4x4 homogeneous transformation matrices:

#### 1. Top View Extrusion (Extruded along Y-axis by $H_y = Y_{\max} - Y_{\min}$):
To preserve counter-clockwise (CCW) winding order under reflection, vertical coordinate input is mirrored before extrusion ($v \to -v$).
$$\begin{bmatrix} X \\ Y \\ Z \\ 1 \end{bmatrix} = 
\begin{bmatrix}
1.0 & 0.0 & 0.0 & 0.0 \\
0.0 & 0.0 & 1.0 & Y_{\min} \\
0.0 & -1.0 & 0.0 & 0.0 \\
0.0 & 0.0 & 0.0 & 1.0
\end{bmatrix}
\begin{bmatrix} u \\ v \\ w \\ 1 \end{bmatrix}$$

#### 2. Front View Extrusion (Extruded along Z-axis by $H_z = Z_{\max} - Z_{\min}$):
$$\begin{bmatrix} X \\ Y \\ Z \\ 1 \end{bmatrix} = 
\begin{bmatrix}
1.0 & 0.0 & 0.0 & 0.0 \\
0.0 & 1.0 & 0.0 & 0.0 \\
0.0 & 0.0 & 1.0 & Z_{\min} \\
0.0 & 0.0 & 0.0 & 1.0
\end{bmatrix}
\begin{bmatrix} u \\ v \\ w \\ 1 \end{bmatrix}$$

#### 3. Side View Extrusion (Extruded along X-axis by $H_x = X_{\max} - X_{\min}$):
$$\begin{bmatrix} X \\ Y \\ Z \\ 1 \end{bmatrix} = 
\begin{bmatrix}
0.0 & 0.0 & 1.0 & X_{\min} \\
0.0 & -1.0 & 0.0 & 0.0 \\
1.0 & 0.0 & 0.0 & 0.0 \\
0.0 & 0.0 & 0.0 & 1.0
\end{bmatrix}
\begin{bmatrix} u \\ v \\ w \\ 1 \end{bmatrix}$$

---

### 4. CSG Boolean Intersection & Watertight Validation
1. Extruded meshes from all available views are combined via CSG boolean intersection:
   $$\text{Solid\_3D} = \text{Mesh}_{\text{top}} \cap \text{Mesh}_{\text{front}} \cap \text{Mesh}_{\text{side}}$$
2. **Defensive Mesh Validation Safeguards:**
   - Near-zero profile areas ($\text{Area} \le 10^{-6}$) are filtered prior to extrusion.
   - Every mesh undergoes strict 2D face array validation (`hasattr(mesh, 'faces') and len(mesh.faces) > 0 and mesh.faces.ndim == 2`).
   - Watertight repair is performed via `trimesh.repair.fill_holes()` and `trimesh.repair.fix_normals()`.
   - If negative volume is detected, face winding is inverted (`mesh.invert()`).

---

## 7. 3D OpenGL Viewport (`viewport_3d.py`)

The 3D model is rendered inside a `QOpenGLWidget` using PyOpenGL:
- **Rendering Modes:** Shaded surface with smooth lighting (`GL_LIGHTING`, `GL_LIGHT0`), ambient & specular reflection, and wireframe overlay (`GL_LINE_LOOP`).
- **Interactive Camera:**
  - **Left Mouse Click + Drag:** ArcBall 3D Orbit Rotation ($Rot_X, Rot_Y$).
  - **Right Mouse Click + Drag:** 2D Viewport Panning ($Pan_X, Pan_Y$).
  - **Mouse Wheel:** Smooth Zoom ($Dist_{min} = 1.0, Dist_{max} = 5000.0$).
- **Reference Axes:** RGB coordinate triad rendered at origin ($X$: Red, $Y$: Green, $Z$: Blue).

---

## 8. Automated Test Suite (`tests/test_reconstruction.py`)

The application is validated by 5 automated Pytest unit tests:
1. `test_shape_creation_and_to_dict`: Verifies primitive initialization, bounding box calculations, and dictionary serialization/deserialization.
2. `test_cad_engine_undo_redo`: Validates engine history stack, shape addition, and undo/redo state restoration.
3. `test_simple_box_reconstruction`: Tests CSG extrusion and 3D reconstruction of a rectangular prism.
4. `test_view_region_and_guardrails`: Tests `ViewRegion` bounds, centroid assignment, local Y-inversion, RHS mirroring, and infinite quadrant fallback.
5. `test_alignment_validation`: Verifies mathematical validation formulas for width, height, and depth tolerances.

**Run Test Command:**
```bash
.\venv\Scripts\python.exe -m pytest tests/test_reconstruction.py
```

---

## 9. Current System Status & Verification Summary

- **Pytest Results:** `5 passed in 1.79s` (100% clean pass rate).
- **Line Rendering:** Visible layer primitives render as solid cyan lines (`Qt.PenStyle.SolidLine`).
- **Shift Ortho Lock:** `QPointF` type casting resolves all PyQt6 event parameter exceptions.
- **Miter Line Positioning:** Correctly extends UP & RIGHT into the top-right quadrant from $(0, 0)$.
- **Reconstruction Robustness:** Defensive checks prevent 1D face array `IndexError` exceptions during trimesh repair.

---
*Report compiled for AI Model consumption and system architecture handoff.*
