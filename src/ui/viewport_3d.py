"""
3D Viewport Pro — Embedded PyQt6 QOpenGLWidget using PyOpenGL with VBOs.
Supports 360° unclamped freelook camera, dynamic near/far clipping planes,
procedural infinite ground grid, object-centric standard views, and floating view controls.
"""

import math
import numpy as np
from typing import Optional
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtCore import Qt, QPointF, pyqtSignal
from PyQt6.QtGui import QMouseEvent, QWheelEvent, QCursor
from PyQt6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QPushButton, QWidget, QFrame, QLabel
)
from OpenGL.GL import *
from OpenGL.GLU import *
import trimesh


class OpenGLViewport(QOpenGLWidget):
    """Native OpenGL widget for 3D mesh rendering using VBOs, VAOs, and 360° Unclamped Freelook Camera"""
    candidate_switched = pyqtSignal(int)  # Emits selected candidate index

    def __init__(self, parent=None):
        super().__init__(parent)

        # Camera state
        self.distance = 400.0
        self.rot_x = 35.264
        self.rot_y = -45.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.last_mouse_pos = QPointF()
        self._is_panning = False

        # Candidate disambiguation state
        self.candidate_count = 1
        self.current_candidate_idx = 0

        # VAO and VBO buffers
        self._vao = None
        self._vbo_vertices = None
        self._vbo_normals = None
        self._vbo_faces = None
        self._vbo_edges = None

        self.num_indices = 0
        self.num_edge_vertices = 0

        # Render and Section view modes
        self.render_mode = 'shaded_with_edges'  # 'shaded', 'shaded_with_edges'
        self.section_enabled = False
        self.section_axis = 'X'
        self.section_pos = 0.0

        # Current mesh and Multi-Part Assembly meshes
        self.mesh: Optional[trimesh.Trimesh] = None
        self.part_meshes: Dict[str, trimesh.Trimesh] = {}
        self.part_colors: Dict[str, Tuple[float, float, float, float]] = {}
        self.part_offsets: Dict[str, Tuple[float, float, float]] = {}
        self.selected_part_id: Optional[str] = None

        # Build floating overlay toolbar for object-centric standard views
        self._setup_overlay_toolbar()

    def _setup_overlay_toolbar(self):
        """Create floating overlay toolbar for object-centric standard views and candidate HUD"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        overlay_frame = QFrame(self)
        overlay_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(30, 30, 30, 210);
                border: 1px solid #3C3C3C;
                border-radius: 6px;
            }
            QPushButton {
                background-color: #2D2D2D;
                color: #D4D4D4;
                border: 1px solid #3C3C3C;
                border-radius: 3px;
                padding: 3px 6px;
                font-size: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #007ACC;
                color: #FFFFFF;
                border-color: #007ACC;
            }
        """)

        btn_layout = QHBoxLayout(overlay_frame)
        btn_layout.setContentsMargins(6, 4, 6, 4)
        btn_layout.setSpacing(4)

        views = [
            ('Top', 'top'),
            ('Bottom', 'bottom'),
            ('Front', 'front'),
            ('Back', 'back'),
            ('Left', 'left'),
            ('Right', 'right'),
            ('Iso', 'iso'),
            ('Fit All', 'fit')
        ]

        for label, view_key in views:
            btn = QPushButton(label)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda checked, v=view_key: self.fit_object_to_view(v))
            btn_layout.addWidget(btn)

        layout.addWidget(overlay_frame)

        # Candidate Disambiguation HUD Frame (Module 2)
        self.candidate_frame = QFrame(self)
        self.candidate_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(20, 40, 60, 230);
                border: 1px solid #00E5FF;
                border-radius: 6px;
            }
            QLabel {
                color: #00E5FF;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton {
                background-color: #0F52BA;
                color: #FFFFFF;
                border: 1px solid #00E5FF;
                border-radius: 3px;
                padding: 3px 8px;
                font-size: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #00E5FF;
                color: #000000;
            }
        """)
        c_layout = QHBoxLayout(self.candidate_frame)
        c_layout.setContentsMargins(8, 4, 8, 4)
        c_layout.setSpacing(6)

        self.candidate_label = QLabel("Multiple 3D Solutions (1 of 1)")
        c_layout.addWidget(self.candidate_label)

        self.prev_cand_btn = QPushButton("◀ Prev")
        self.prev_cand_btn.clicked.connect(self._prev_candidate)
        c_layout.addWidget(self.prev_cand_btn)

        self.next_cand_btn = QPushButton("Next ▶")
        self.next_cand_btn.clicked.connect(self._next_candidate)
        c_layout.addWidget(self.next_cand_btn)

        layout.addWidget(self.candidate_frame)
        self.candidate_frame.hide()  # Hidden by default until ambiguous solutions detected

    def set_candidates(self, count: int, current: int = 0):
        """Update candidate count and visibility"""
        self.candidate_count = count
        self.current_candidate_idx = current
        if count > 1:
            self.candidate_label.setText(f"Multiple 3D Solutions ({current + 1} of {count})")
            self.candidate_frame.show()
        else:
            self.candidate_frame.hide()

    def _prev_candidate(self):
        if self.candidate_count > 1:
            self.current_candidate_idx = (self.current_candidate_idx - 1) % self.candidate_count
            self.candidate_label.setText(f"Multiple 3D Solutions ({self.current_candidate_idx + 1} of {self.candidate_count})")
            self.candidate_switched.emit(self.current_candidate_idx)

    def _next_candidate(self):
        if self.candidate_count > 1:
            self.current_candidate_idx = (self.current_candidate_idx + 1) % self.candidate_count
            self.candidate_label.setText(f"Multiple 3D Solutions ({self.current_candidate_idx + 1} of {self.candidate_count})")
            self.candidate_switched.emit(self.current_candidate_idx)

    @staticmethod
    def _compute_crease_aware_normals(mesh: trimesh.Trimesh, crease_angle_deg: float = 25.0):
        """
        Compute crease-aware split vertex normals for CAD rendering:
        - Flattens faces into unrolled vertex buffers (F * 3, 3).
        - For each face corner (face f, vertex v), averages the face normals of adjacent faces
          sharing vertex v ONLY if the dihedral angle between the face normal and adjacent face normal <= crease_angle_deg.
        - Planar faces and sharp edges (> crease_angle_deg) receive exact perpendicular face normals [0,0,1],
          completely eliminating Gouraud ear-clipping diagonal crease artifacts across flat faces.
        - Smooth curved features (cylinders, fillets with adjacent angle <= crease_angle_deg) retain smooth shading.
        """
        faces = mesh.faces  # (F, 3)
        face_normals = mesh.face_normals.astype(np.float32)  # (F, 3)
        num_faces = len(faces)
        
        unrolled_vertices = mesh.vertices[faces].reshape(-1, 3).astype(np.float32)
        
        num_vertices = len(mesh.vertices)
        vertex_faces = [[] for _ in range(num_vertices)]
        for f_idx, face in enumerate(faces):
            for v_idx in face:
                vertex_faces[v_idx].append(f_idx)
                
        cos_crease = float(np.cos(np.radians(crease_angle_deg)))
        unrolled_normals = np.zeros_like(unrolled_vertices, dtype=np.float32)
        
        for f_idx in range(num_faces):
            fn = face_normals[f_idx]
            face = faces[f_idx]
            for corner_idx, v_idx in enumerate(face):
                adj_f_indices = vertex_faces[v_idx]
                if len(adj_f_indices) == 1:
                    unrolled_normals[f_idx * 3 + corner_idx] = fn
                    continue
                    
                accum_normal = np.zeros(3, dtype=np.float32)
                for adj_f in adj_f_indices:
                    adj_fn = face_normals[adj_f]
                    if np.dot(fn, adj_fn) >= cos_crease:
                        accum_normal += adj_fn
                        
                norm = float(np.linalg.norm(accum_normal))
                if norm > 1e-6:
                    unrolled_normals[f_idx * 3 + corner_idx] = accum_normal / norm
                else:
                    unrolled_normals[f_idx * 3 + corner_idx] = fn
                    
        return unrolled_vertices, unrolled_normals

    def set_mesh(self, mesh: trimesh.Trimesh):
        """Update viewport mesh, compute crease-aware split normals, detect sharp edges, and upload to GPU VBOs/VAOs"""
        self.mesh = mesh
        self.makeCurrent()

        # Clear existing buffers
        self._cleanup_vbo()

        if mesh is None or len(mesh.vertices) == 0:
            self.num_indices = 0
            self.doneCurrent()
            self.update()
            return

        # Compute crease-aware split vertex normals
        unrolled_vertices, unrolled_normals = self._compute_crease_aware_normals(mesh, crease_angle_deg=25.0)
        vertices = unrolled_vertices.flatten()
        normals = unrolled_normals.flatten()
        self.num_indices = len(unrolled_vertices)

        # Identify sharp feature edges (face adjacency angle > 25 degrees)
        try:
            angles = mesh.face_adjacency_angles
            sharp_mask = angles > np.radians(25.0)
            sharp_edges = mesh.face_adjacency_edges[sharp_mask]
            if len(sharp_edges) > 0:
                edge_vertices = mesh.vertices[sharp_edges].astype(np.float32).flatten()
                self.num_edge_vertices = len(edge_vertices) // 3
            else:
                self.num_edge_vertices = 0
        except Exception as e:
            print(f"Error computing adjacency edges: {e}")
            self.num_edge_vertices = 0

        # Generate and populate GPU buffers
        self._vbo_vertices, self._vbo_normals = glGenBuffers(2)

        # Vertices VBO
        glBindBuffer(GL_ARRAY_BUFFER, self._vbo_vertices)
        glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_STATIC_DRAW)

        # Normals VBO
        glBindBuffer(GL_ARRAY_BUFFER, self._vbo_normals)
        glBufferData(GL_ARRAY_BUFFER, normals.nbytes, normals, GL_STATIC_DRAW)

        # Edge lines VBO
        if self.num_edge_vertices > 0:
            self._vbo_edges = glGenBuffers(1)
            glBindBuffer(GL_ARRAY_BUFFER, self._vbo_edges)
            glBufferData(GL_ARRAY_BUFFER, edge_vertices.nbytes, edge_vertices, GL_STATIC_DRAW)

        glBindBuffer(GL_ARRAY_BUFFER, 0)

        # Compile states into a Vertex Array Object (VAO)
        self._vao = glGenVertexArrays(1)
        glBindVertexArray(self._vao)

        # Bind vertices in VAO
        glBindBuffer(GL_ARRAY_BUFFER, self._vbo_vertices)
        glVertexPointer(3, GL_FLOAT, 0, None)
        glEnableClientState(GL_VERTEX_ARRAY)

        # Bind normals in VAO
        glBindBuffer(GL_ARRAY_BUFFER, self._vbo_normals)
        glNormalPointer(GL_FLOAT, 0, None)
        glEnableClientState(GL_NORMAL_ARRAY)

        # Unbind VAO & Buffers
        glBindVertexArray(0)
        glBindBuffer(GL_ARRAY_BUFFER, 0)

        # Auto-center camera around the new mesh
        self.fit_object_to_view('fit')

        self.doneCurrent()
        self.update()

    def fit_object_to_view(self, view_name: str = 'iso'):
        """Fit camera to target object bounding box and snap angle"""
        if self.mesh is not None and len(self.mesh.vertices) > 0:
            centroid = self.mesh.centroid
            min_pt, max_pt = self.mesh.bounds
            diagonal = float(np.linalg.norm(max_pt - min_pt))

            # Pan camera to focus on mesh centroid
            self.pan_x = -centroid[0]
            self.pan_y = -centroid[1]

            # Compute required distance using field of view (45 deg)
            fov_rad = np.radians(45.0)
            fit_dist = (diagonal / (2.0 * np.tan(fov_rad / 2.0))) * 1.35
            self.distance = max(fit_dist, 40.0)

            # Update section plane position
            self.section_pos = float(centroid[0] if self.section_axis == 'X' else (centroid[1] if self.section_axis == 'Y' else centroid[2]))
        else:
            self.pan_x = 0.0
            self.pan_y = 0.0
            self.distance = 400.0

        # Snap camera angle to standard orthographic or isometric orientation
        if view_name == 'top':
            self.rot_x = 90.0
            self.rot_y = 0.0
        elif view_name == 'bottom':
            self.rot_x = -90.0
            self.rot_y = 0.0
        elif view_name == 'front':
            self.rot_x = 0.0
            self.rot_y = 0.0
        elif view_name == 'back':
            self.rot_x = 0.0
            self.rot_y = 180.0
        elif view_name == 'left':
            self.rot_x = 0.0
            self.rot_y = 90.0
        elif view_name == 'right':
            self.rot_x = 0.0
            self.rot_y = -90.0
        elif view_name == 'iso':
            self.rot_x = 35.264
            self.rot_y = -45.0

        self.update()

    def snap_front(self):
        self.fit_object_to_view('front')

    def snap_side(self):
        self.fit_object_to_view('right')

    def snap_top(self):
        self.fit_object_to_view('top')

    def snap_iso(self):
        self.fit_object_to_view('iso')

    def _cleanup_vbo(self):
        """Delete GPU VAO and VBO buffers"""
        if self._vao is not None:
            glDeleteVertexArrays(1, [self._vao])
            self._vao = None

        buffers_to_delete = []
        if self._vbo_vertices is not None:
            buffers_to_delete.extend([self._vbo_vertices, self._vbo_normals])
            self._vbo_vertices = None
            self._vbo_normals = None

        if self._vbo_edges is not None:
            buffers_to_delete.append(self._vbo_edges)
            self._vbo_edges = None

        if buffers_to_delete:
            glDeleteBuffers(len(buffers_to_delete), buffers_to_delete)

        self.num_indices = 0
        self.num_edge_vertices = 0

    def initializeGL(self):
        """Setup initial OpenGL rendering state"""
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glEnable(GL_LIGHT1)
        glEnable(GL_NORMALIZE)
        glEnable(GL_COLOR_MATERIAL)

        # Clear color: dark charcoal
        glClearColor(0.12, 0.12, 0.12, 1.0)
        glShadeModel(GL_SMOOTH)

        # Light 0: Front-Left direction
        glLightfv(GL_LIGHT0, GL_AMBIENT, [0.2, 0.2, 0.2, 1.0])
        glLightfv(GL_LIGHT0, GL_DIFFUSE, [0.8, 0.8, 0.8, 1.0])
        glLightfv(GL_LIGHT0, GL_SPECULAR, [0.5, 0.5, 0.5, 1.0])

        # Light 1: Back-Right direction
        glLightfv(GL_LIGHT1, GL_AMBIENT, [0.0, 0.0, 0.0, 1.0])
        glLightfv(GL_LIGHT1, GL_DIFFUSE, [0.4, 0.4, 0.4, 1.0])
        glLightfv(GL_LIGHT1, GL_SPECULAR, [0.3, 0.3, 0.3, 1.0])

    def _update_projection_matrix(self):
        """Dynamically update OpenGL projection matrix based on camera distance (Infinite 3D Space)"""
        w = max(self.width(), 1)
        h = max(self.height(), 1)
        aspect = float(w) / float(h)

        # Dynamic near and far clipping planes scale with camera distance
        near_clip = max(0.05, self.distance * 0.02)
        far_clip = max(10000.0, self.distance * 2000.0)

        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45.0, aspect, near_clip, far_clip)
        glMatrixMode(GL_MODELVIEW)

    def paintGL(self):
        """Clear viewport, update dynamic clipping projection matrix, render grid and 3D model"""
        self._update_projection_matrix()

        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

        # Camera transformation matrix (unclamped 360-degree freelook)
        glTranslatef(0.0, 0.0, -self.distance)
        glRotatef(self.rot_x, 1.0, 0.0, 0.0)
        glRotatef(self.rot_y, 0.0, 1.0, 0.0)
        glTranslatef(self.pan_x, self.pan_y, 0.0)

        # Setup directional lights
        glLightfv(GL_LIGHT0, GL_POSITION, [1.0, 1.0, 1.0, 0.0])
        glLightfv(GL_LIGHT1, GL_POSITION, [-1.0, 0.5, -1.0, 0.0])

        # Enable clipping planes if Section View is active
        if self.section_enabled:
            if self.section_axis == 'X':
                eq = [1.0, 0.0, 0.0, -self.section_pos]
            elif self.section_axis == 'Y':
                eq = [0.0, 1.0, 0.0, -self.section_pos]
            else:
                eq = [0.0, 0.0, 1.0, -self.section_pos]
            glEnable(GL_CLIP_PLANE0)
            glClipPlane(GL_CLIP_PLANE0, eq)
        else:
            glDisable(GL_CLIP_PLANE0)

        # 1. Render procedural infinite floor grid
        self._draw_procedural_grid()

        # 2. Render 3D model mesh
        glEnable(GL_LIGHTING)
        if self.section_enabled:
            glEnable(GL_CLIP_PLANE0)

        self._draw_mesh()
        glDisable(GL_CLIP_PLANE0)

    def _draw_procedural_grid(self):
        """Render a dynamic procedural infinite ground grid centered around camera target"""
        glDisable(GL_LIGHTING)
        glDisable(GL_CLIP_PLANE0)

        step = 10.0          # Minor lines every 10mm
        major_step = 100.0   # Major lines every 100mm
        extent = 2500.0      # Grid half-extent around camera target

        # Camera target position
        target_x = -self.pan_x
        target_z = 0.0

        # Snap origin to nearest step interval
        snap_x = math.floor(target_x / step) * step
        snap_z = math.floor(target_z / step) * step

        min_x = snap_x - extent
        max_x = snap_x + extent
        min_z = snap_z - extent
        max_z = snap_z + extent

        glLineWidth(1.0)
        glBegin(GL_LINES)

        # Lines parallel to X-axis (varying Z)
        z_curr = math.floor(min_x / step) * step
        while z_curr <= max_z:
            if abs(z_curr) < 0.01:
                glColor3f(0.8, 0.2, 0.2)  # Red X-axis line
            elif abs(z_curr % major_step) < 0.01:
                glColor3f(0.32, 0.32, 0.32)  # Major grid line
            else:
                glColor3f(0.18, 0.18, 0.18)  # Minor grid line

            glVertex3f(min_x, 0.0, z_curr)
            glVertex3f(max_x, 0.0, z_curr)
            z_curr += step

        # Lines parallel to Z-axis (varying X)
        x_curr = math.floor(min_x / step) * step
        while x_curr <= max_x:
            if abs(x_curr) < 0.01:
                glColor3f(0.2, 0.2, 0.8)  # Blue Z-axis line
            elif abs(x_curr % major_step) < 0.01:
                glColor3f(0.32, 0.32, 0.32)  # Major grid line
            else:
                glColor3f(0.18, 0.18, 0.18)  # Minor grid line

            glVertex3f(x_curr, 0.0, min_z)
            glVertex3f(x_curr, 0.0, max_z)
            x_curr += step

        glEnd()

    def set_assembly_meshes(
        self,
        part_meshes: Dict[str, trimesh.Trimesh],
        part_colors: Optional[Dict[str, Tuple[float, float, float, float]]] = None
    ):
        """Register discrete part meshes and color identifiers for multi-body assembly rendering"""
        self.part_meshes = part_meshes or {}
        self.part_colors = part_colors or {}
        if self.part_meshes:
            # Combine meshes for initial camera framing
            combined = trimesh.util.concatenate(list(self.part_meshes.values()))
            self.set_mesh(combined)
        self.update()

    def set_part_offsets(self, offsets: Dict[str, Tuple[float, float, float]]):
        """Set dynamic 3D translation offsets for Exploded Assembly View"""
        self.part_offsets = offsets or {}
        self.update()

    def set_selected_part_id(self, part_id: Optional[str]):
        """Synchronize BOM table selection with 3D viewport highlight tint (Guardrail #3)"""
        self.selected_part_id = part_id
        self.update()

    def _draw_mesh(self):
        """Bind and render meshes with support for exploded multi-body components and selection highlighting"""
        if self.part_meshes:
            # Multi-body assembly render pass
            for pid, pmesh in self.part_meshes.items():
                offset = self.part_offsets.get(pid, (0.0, 0.0, 0.0))
                rgba = self.part_colors.get(pid, (0.7, 0.75, 0.8, 1.0))

                glPushMatrix()
                glTranslatef(float(offset[0]), float(offset[1]), float(offset[2]))

                # Apply selection highlight tint if selected
                if pid == self.selected_part_id:
                    ambient = [0.0, 0.8, 0.9, 1.0]
                    diffuse = [0.0, 0.9, 1.0, 1.0]
                    glColor3f(0.0, 0.9, 1.0)
                else:
                    ambient = [rgba[0] * 0.5, rgba[1] * 0.5, rgba[2] * 0.5, 1.0]
                    diffuse = [rgba[0], rgba[1], rgba[2], 1.0]
                    glColor3f(rgba[0], rgba[1], rgba[2])

                glMaterialfv(GL_FRONT, GL_AMBIENT, ambient)
                glMaterialfv(GL_FRONT, GL_DIFFUSE, diffuse)

                # Render part triangles
                glBegin(GL_TRIANGLES)
                for f in pmesh.faces:
                    for v_idx in f:
                        if len(pmesh.vertex_normals) > v_idx:
                            glNormal3fv(pmesh.vertex_normals[v_idx])
                        glVertex3fv(pmesh.vertices[v_idx])
                glEnd()

                glPopMatrix()

        elif self.num_indices > 0 and self._vao is not None:
            ambient = [0.35, 0.35, 0.35, 1.0]
            diffuse = [0.69, 0.69, 0.69, 1.0]
            specular = [0.4, 0.4, 0.4, 1.0]
            shininess = 32.0

            glMaterialfv(GL_FRONT, GL_AMBIENT, ambient)
            glMaterialfv(GL_FRONT, GL_DIFFUSE, diffuse)
            glMaterialfv(GL_FRONT, GL_SPECULAR, specular)
            glMaterialf(GL_FRONT, GL_SHININESS, shininess)
            glColorMaterial(GL_FRONT, GL_DIFFUSE)

            glColor3f(0.69, 0.69, 0.69)

            if self.render_mode == 'shaded_with_edges':
                glEnable(GL_POLYGON_OFFSET_FILL)
                glPolygonOffset(1.0, 1.0)

            glBindVertexArray(self._vao)
            glDrawArrays(GL_TRIANGLES, 0, self.num_indices)
            glBindVertexArray(0)

            if self.render_mode == 'shaded_with_edges':
                glDisable(GL_POLYGON_OFFSET_FILL)

                if self._vbo_edges is not None and self.num_edge_vertices > 0:
                    glDisable(GL_LIGHTING)
                    glEnableClientState(GL_VERTEX_ARRAY)

                    glBindBuffer(GL_ARRAY_BUFFER, self._vbo_edges)
                    glVertexPointer(3, GL_FLOAT, 0, None)

                    glColor3f(0.0, 0.0, 0.0)
                    glLineWidth(1.5)
                    glDrawArrays(GL_LINES, 0, self.num_edge_vertices)

                    glBindBuffer(GL_ARRAY_BUFFER, 0)
                    glDisableClientState(GL_VERTEX_ARRAY)
                    glEnable(GL_LIGHTING)

    def resizeGL(self, width: int, height: int):
        """Update viewport matrix on resize"""
        self._update_projection_matrix()

    # 360° Unclamped Mouse Controls
    def mousePressEvent(self, event: QMouseEvent):
        """Start rotation or viewport panning from the corresponding mouse button."""
        self.last_mouse_pos = event.position()
        if event.button() == Qt.MouseButton.MiddleButton:
            self._is_panning = True
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        """Rotate with left drag and pan with middle or right drag."""
        dx = event.position().x() - self.last_mouse_pos.x()
        dy = event.position().y() - self.last_mouse_pos.y()
        self.last_mouse_pos = event.position()

        if event.buttons() & Qt.MouseButton.LeftButton:
            # Unclamped 360-degree rotation in all directions
            self.rot_x = (self.rot_x + dy * 0.4) % 360.0
            self.rot_y = (self.rot_y + dx * 0.4) % 360.0
            self.update()

        elif event.buttons() & (Qt.MouseButton.MiddleButton | Qt.MouseButton.RightButton):
            # Pan camera (sensitivity scales with distance)
            sensitivity = 0.002 * self.distance
            self.pan_x += dx * sensitivity
            self.pan_y -= dy * sensitivity
            self.update()

        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        """Restore the normal cursor after middle-button viewport panning."""
        if event.button() == Qt.MouseButton.MiddleButton:
            self._is_panning = False
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        event.accept()

    def wheelEvent(self, event: QWheelEvent):
        """Infinite zoom camera distance on mouse scroll wheel"""
        zoom_factor = 1.15
        if event.angleDelta().y() > 0:
            self.distance /= zoom_factor
        else:
            self.distance *= zoom_factor

        self.distance = max(0.5, min(50000.0, self.distance))
        self.update()
        event.accept()

    def cleanup(self):
        """Free GPU VAO and VBO resources on widget close"""
        self.makeCurrent()
        self._cleanup_vbo()
        self.doneCurrent()
