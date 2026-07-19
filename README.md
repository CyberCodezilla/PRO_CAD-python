# Python CAD Pro 📐🤖

**Python CAD Pro** is an industry-grade, professional desktop CAD application featuring an intelligent 2D-to-3D orthographic reconstruction pipeline. The application bridges the gap between 2D drafting and 3D modeling by allowing users to draw standard Top, Front, and Side orthographic projections, and automatically generating a watertight, manifold 3D mesh using Constructive Solid Geometry (CSG) Boolean intersections.

---

## 🚀 Key Features

### 1. Advanced 2D Drafting & Editing Tools
- **Standard CAD Primitives**: Draw lines, rectangles, circles, polygons, arcs, and dimensions.
- **Modification Tools**:
  - *Trim / Extend*: Trim lines back to intersecting entities or extend them forward to target geometries.
  - *Fillet / Chamfer*: Add corner radii (fillets) or bevels (chamfers) to profiles in atomic undoable database transactions.
  - *Offset*: Create normalized parallel copy profiles with verified winding directions.
- **Dynamic Cursor Input HUD**: A floating display near the cursor allows keyboard-entered lengths and angles.
- **Associative Dimensioning**: Annotations automatically update their measurements and labels when parent shapes are resized or moved.

### 2. Precise Snap Engine & Layout Guides
- **Object Snapping (OSNAP)**: Automatically snaps to endpoints, midpoints, circle centers, and polygon vertices within a 15px radius, featuring a yellow indicator square.
- **Grid Snapping**: Snaps coordinate placements to the nearest 10px grid intersection.
- **Ortho Mode**: Pressing `Shift` restricts line segment creation to horizontal and vertical axes (90-degree locks).
- **Cross-Canvas Projection Guidelines**: Moving the cursor in one orthographic tab projects dashed alignment guides to all other tabs to ensure exact coordinate drafting.

### 3. Engineering Graphics Layers
- **Visible Layer (Solid Cyan, 2.0px)**: Outlines the primary solid boundaries of the reconstructed part.
- **Hidden Layer (Dashed Yellow/Cyan, 2.0px)**: Outlines internal holes, pockets, or slots. Profiles on this layer are subtracted from visible profiles during 3D CSG reconstruction.
- **Construction Layer (Faint Grey, 1.0px)**: Auxiliary layout guides ignored during 3D reconstruction.

### 4. Professional PyOpenGL 3D Viewport
- **GPU-Accelerated VBOs & VAOs**: Bypasses deprecated display lists and immediate mode (`glBegin`/`glEnd`) using compiled **Vertex Array Objects** and **Vertex Buffer Objects** to pass numpy arrays directly to the GPU.
- **Shaded with Edges**: Automatically computes sharp contours (face adjacency angles $> 30^\circ$) and overlays clean black edges without z-fighting (using `glPolygonOffset`).
- **Section View Clipping**: A customizable clipping plane (`glClipPlane`) dynamically slices open the 3D model on X, Y, or Z axes.
- **Snapping Viewpoints**: One-click camera snaps for Front, Side, Top, and Isometric projections.

### 5. Multi-Threaded CSG Reconstruction Pipeline
- **Background Processing**: Runs heavy computational geometry operations in a thread-safe `QThread` subclass, passing meshes to the viewport via PyQt Signals to prevent GUI blocking.
- **Watertight Manifold Generation**: Uses `shapely` for 2D profile compilation, extrudes profiles along projection matrices, and performs 3D boolean intersections via `manifold3d` / `trimesh`.
- **Winding Order Corrections**: Mirrored coordinate matrices cancel coordinate reflections, resulting in CCW winding orientations and positive volumes without normal-inversion hacks.
- **Profile Closure Validation**: Highlights open endpoints (dangles) in bright red and blocks 3D reconstruction if profiles are not closed.

### 6. File I/O & Interoperability
- **Native JSON (`.pcad`)**: Save and load full project geometries, dimensions, and settings.
- **DXF Import/Export**: Powered by `ezdxf`. Read `$INSUNITS` scale factors (inches/feet/meters to mm) and parses complex `LWPOLYLINE` bulges into CAD `Arc` entities.
- **3D Mesh Export**: Export constructed solid models to **STL**, **OBJ**, and **3MF** formats.

---

## 🛠️ Project Structure

```
python-cad-pro/
├── src/
│   ├── engine/             # CAD database, shapes (Line, Circle, Arc, etc.), history
│   │   └── cad_engine.py
│   ├── reconstruction/     # QThread worker, CSG boolean operations, normal orientation
│   │   └── reconstructor.py
│   └── ui/                 # Viewport, graphics scene, docks, and menus
│       ├── canvas.py       # 2D View canvases, snapping, projection guides, HUD
│       ├── main_window.py  # Primary layout, docks, command console, I/O actions
│       ├── toolbar.py      # Active tool and layer toggles
│       └── viewport_3d.py  # PyOpenGL QOpenGLWidget, VAO, lighting, clipping, snaps
├── tests/
│   └── test_reconstruction.py  # Volumetric verification suite (cube, cylinder, pipe)
├── main.py                 # Application launcher and OpenGL profile format setups
├── requirements.txt        # Math, geometry, and graphics dependencies
└── README.md               # User guide and architectural overview
```

---

## 💻 AutoCAD-Style Command Console

You can enter commands directly into the bottom console bar:
*   `c` or `circle`: Select the Circle tool.
*   `l` or `line`: Select the Line tool.
*   `rec` or `rect`: Select the Rectangle tool.
*   `s` or `select`: Select the Select tool.
*   `p` or `polygon`: Select the Polygon tool.
*   `undo` / `redo`: Undo/redo the last operations.
*   `clear` / `cls`: Clear the active canvas drawing.
*   `help` / `?`: Show the user guide.
*   `dx,dy`: Relative coordinate offset input (e.g. `100,50`).
*   `#x,y`: Absolute coordinate input (e.g. `#0,100`).
*   `value`: Single number locks the active line segment to that length along the cursor direction, or sets the radius of a circle/arc.

---

## 📥 Installation & Setup

1. **Clone the Repository**:
```bash
git clone https://github.com/CyberCodezilla/PRO_CAD-python.git
cd PRO_CAD-python
```

2. **Create a Virtual Environment**:
```bash
python -m venv venv
```

3. **Activate the Virtual Environment**:
- **Windows**: `venv\Scripts\activate`
- **macOS/Linux**: `source venv/bin/activate`

5. **Install Dependencies**:
```bash
pip install -r requirements.txt
```

---

## 🏃 Running the Application

Launch the desktop interface:
```bash
python main.py
```

---

## 🧪 Running Automated Tests

Run the volumetric test suite:
```bash
python -m pytest -v
```

All reconstruction test cases (watertight block, cylinder, and hollow pipe) check the computed mesh's volume accuracy and watertight characteristics within strict tolerances.
