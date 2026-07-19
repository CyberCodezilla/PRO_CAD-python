"""
3D Viewport - Embedded PyQt6 QOpenGLWidget using PyOpenGL with VBOs.
Supports arcball rotation, panning, zooming, dual directional lighting, and a reference floor grid.
"""
import numpy as np
from typing import Optional
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QMouseEvent, QWheelEvent
from OpenGL.GL import *
from OpenGL.GLU import *
import trimesh

class OpenGLViewport(QOpenGLWidget):
    """Native OpenGL widget for 3D mesh rendering using VBOs and VAOs"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Camera state
        self.distance = 400.0
        self.rot_x = 30.0
        self.rot_y = -45.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.last_mouse_pos = QPointF()
        
        # VAO and VBO buffers
        self._vao = None
        self._vbo_vertices = None
        self._vbo_normals = None
        self._vbo_faces = None
        self._vbo_edges = None
        self._vbo_grid = None
        
        self.num_indices = 0
        self.num_edge_vertices = 0
        self.grid_vertex_count = 0
        
        # Render and Section view modes
        self.render_mode = 'shaded_with_edges'  # 'shaded', 'shaded_with_edges'
        self.section_enabled = False
        self.section_axis = 'X'
        self.section_pos = 0.0
        
        # Current mesh
        self.mesh: Optional[trimesh.Trimesh] = None
        
    def set_mesh(self, mesh: trimesh.Trimesh):
        """Update viewport mesh, detect sharp edges, and upload data to GPU VBOs/VAOs"""
        self.mesh = mesh
        self.makeCurrent()
        
        # Clear existing buffers
        self._cleanup_vbo()
        
        if mesh is None or len(mesh.vertices) == 0:
            self.num_indices = 0
            self.doneCurrent()
            self.update()
            return
            
        # Convert mesh elements to correct numpy datatypes
        vertices = mesh.vertices.astype(np.float32).flatten()
        normals = mesh.vertex_normals.astype(np.float32).flatten()
        faces = mesh.faces.astype(np.uint32).flatten()
        
        self.num_indices = len(faces)
        
        # 1. Identify sharp edges (face adjacency angle > 30 degrees)
        try:
            angles = mesh.face_adjacency_angles
            sharp_mask = angles > np.radians(30.0)
            sharp_edges = mesh.face_adjacency_edges[sharp_mask]
            if len(sharp_edges) > 0:
                edge_vertices = mesh.vertices[sharp_edges].astype(np.float32).flatten()
                self.num_edge_vertices = len(edge_vertices) // 3
            else:
                self.num_edge_vertices = 0
        except Exception as e:
            print(f"Error computing adjacency edges: {e}")
            self.num_edge_vertices = 0
            
        # 2. Generate and populate GPU buffers
        self._vbo_vertices, self._vbo_normals, self._vbo_faces = glGenBuffers(3)
        
        # Vertices VBO
        glBindBuffer(GL_ARRAY_BUFFER, self._vbo_vertices)
        glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_STATIC_DRAW)
        
        # Normals VBO
        glBindBuffer(GL_ARRAY_BUFFER, self._vbo_normals)
        glBufferData(GL_ARRAY_BUFFER, normals.nbytes, normals, GL_STATIC_DRAW)
        
        # Faces Element Buffer
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self._vbo_faces)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, faces.nbytes, faces, GL_STATIC_DRAW)
        
        # Edge lines VBO (if sharp edges exist)
        if self.num_edge_vertices > 0:
            self._vbo_edges = glGenBuffers(1)
            glBindBuffer(GL_ARRAY_BUFFER, self._vbo_edges)
            glBufferData(GL_ARRAY_BUFFER, edge_vertices.nbytes, edge_vertices, GL_STATIC_DRAW)
            
        glBindBuffer(GL_ARRAY_BUFFER, 0)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0)
        
        # 3. Compile states into a Vertex Array Object (VAO)
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
        
        # Bind face indices in VAO
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self._vbo_faces)
        
        # Unbind VAO & Buffers
        glBindVertexArray(0)
        glBindBuffer(GL_ARRAY_BUFFER, 0)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0)
        
        # Auto-center camera around the new mesh
        self._center_camera_on_mesh()
        
        self.doneCurrent()
        self.update()
        
    def _center_camera_on_mesh(self):
        """Center the viewport camera based on mesh bounds"""
        if self.mesh is not None and len(self.mesh.vertices) > 0:
            center = self.mesh.centroid
            extents = self.mesh.extents
            
            # Pan camera to focus on mesh center
            self.pan_x = -center[0]
            self.pan_y = -center[1]
            
            # Distance scales with largest dimension to fit in view
            max_dim = max(extents)
            self.distance = max(max_dim * 2.2, 100.0)
            
            # Set default section plane pos to centroid
            self.section_pos = center[0] if self.section_axis == 'X' else (center[1] if self.section_axis == 'Y' else center[2])

    def _cleanup_vbo(self):
        """Delete GPU VAO and VBO buffers"""
        if self._vao is not None:
            glDeleteVertexArrays(1, [self._vao])
            self._vao = None
            
        buffers_to_delete = []
        if self._vbo_vertices is not None:
            buffers_to_delete.extend([self._vbo_vertices, self._vbo_normals, self._vbo_faces])
            self._vbo_vertices = None
            self._vbo_normals = None
            self._vbo_faces = None
            
        if self._vbo_edges is not None:
            buffers_to_delete.append(self._vbo_edges)
            self._vbo_edges = None
            
        if buffers_to_delete:
            glDeleteBuffers(len(buffers_to_delete), buffers_to_delete)
            
        self.num_indices = 0
        self.num_edge_vertices = 0

    def initializeGL(self):
        """Setup initial OpenGL rendering state"""
        # Lighting configurations
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glEnable(GL_LIGHT1)
        glEnable(GL_NORMALIZE)
        glEnable(GL_COLOR_MATERIAL)
        
        # Clear color: dark charcoal
        glClearColor(0.12, 0.12, 0.12, 1.0)
        
        # Shading model
        glShadeModel(GL_SMOOTH)
        
        # Light 1: Front-Left direction
        glLightfv(GL_LIGHT0, GL_AMBIENT, [0.2, 0.2, 0.2, 1.0])
        glLightfv(GL_LIGHT0, GL_DIFFUSE, [0.8, 0.8, 0.8, 1.0])
        glLightfv(GL_LIGHT0, GL_SPECULAR, [0.5, 0.5, 0.5, 1.0])
        
        # Light 2: Back-Right direction
        glLightfv(GL_LIGHT1, GL_AMBIENT, [0.0, 0.0, 0.0, 1.0])
        glLightfv(GL_LIGHT1, GL_DIFFUSE, [0.4, 0.4, 0.4, 1.0])
        glLightfv(GL_LIGHT1, GL_SPECULAR, [0.3, 0.3, 0.3, 1.0])
        
        # Compile reference floor grid to a VBO
        self._init_grid_vbo()

    def _init_grid_vbo(self):
        """Generate lines for reference coordinate floor grid using a single VBO"""
        grid_lines = []
        grid_size = 1000.0
        grid_step = 50.0
        floor_y = -80.0  # Faint floor positioning
        
        # Grid lines
        for x in np.arange(-grid_size, grid_size + 1.0, grid_step):
            grid_lines.extend([[x, floor_y, -grid_size], [x, floor_y, grid_size]])
        for z in np.arange(-grid_size, grid_size + 1.0, grid_step):
            grid_lines.extend([[-grid_size, floor_y, z], [grid_size, floor_y, z]])
            
        grid_data = np.array(grid_lines, dtype=np.float32).flatten()
        self.grid_vertex_count = len(grid_lines)
        
        self._vbo_grid = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self._vbo_grid)
        glBufferData(GL_ARRAY_BUFFER, grid_data.nbytes, grid_data, GL_STATIC_DRAW)
        glBindBuffer(GL_ARRAY_BUFFER, 0)

    def paintGL(self):
        """Clear viewport and render floor grid and 3D mesh via VBO pointers"""
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        
        # Camera transformation matrix
        glTranslatef(0.0, 0.0, -self.distance)
        glRotatef(self.rot_x, 1.0, 0.0, 0.0)
        glRotatef(self.rot_y, 0.0, 1.0, 0.0)
        glTranslatef(self.pan_x, self.pan_y, 0.0)
        
        # Setup directional light positions in camera-space/world-space
        glLightfv(GL_LIGHT0, GL_POSITION, [1.0, 1.0, 1.0, 0.0])
        glLightfv(GL_LIGHT1, GL_POSITION, [-1.0, 0.5, -1.0, 0.0])
        
        # Enable fixed-function OpenGL clipping planes if Section View is active
        if self.section_enabled:
            # Equation: Ax + By + Cz + D = 0
            if self.section_axis == 'X':
                eq = [1.0, 0.0, 0.0, -self.section_pos]
            elif self.section_axis == 'Y':
                eq = [0.0, 1.0, 0.0, -self.section_pos]
            else:  # Z axis
                eq = [0.0, 0.0, 1.0, -self.section_pos]
            glEnable(GL_CLIP_PLANE0)
            glClipPlane(GL_CLIP_PLANE0, eq)
        else:
            glDisable(GL_CLIP_PLANE0)
            
        # 1. Render floor grid (without lighting or clipping)
        glDisable(GL_LIGHTING)
        glDisable(GL_CLIP_PLANE0)
        self._draw_grid()
        
        # Re-enable rendering states for mesh
        glEnable(GL_LIGHTING)
        if self.section_enabled:
            glEnable(GL_CLIP_PLANE0)
            
        # 2. Render 3D model mesh
        self._draw_mesh()
        
        # Clear clip state
        glDisable(GL_CLIP_PLANE0)

    def _draw_grid(self):
        """Draw VBO grid lines"""
        if self._vbo_grid is not None and self.grid_vertex_count > 0:
            glEnableClientState(GL_VERTEX_ARRAY)
            glBindBuffer(GL_ARRAY_BUFFER, self._vbo_grid)
            glVertexPointer(3, GL_FLOAT, 0, None)
            
            glColor3f(0.22, 0.22, 0.22)
            glLineWidth(1.0)
            glDrawArrays(GL_LINES, 0, self.grid_vertex_count)
            
            glBindBuffer(GL_ARRAY_BUFFER, 0)
            glDisableClientState(GL_VERTEX_ARRAY)

    def _draw_mesh(self):
        """Bind Vertex Array Object (VAO) to render faces and edge overlays on GPU"""
        if self.num_indices > 0 and self._vao is not None:
            # Set metallic material properties
            ambient = [0.35, 0.35, 0.35, 1.0]
            diffuse = [0.69, 0.69, 0.69, 1.0]
            specular = [0.4, 0.4, 0.4, 1.0]
            shininess = 32.0
            
            glMaterialfv(GL_FRONT, GL_AMBIENT, ambient)
            glMaterialfv(GL_FRONT, GL_DIFFUSE, diffuse)
            glMaterialfv(GL_FRONT, GL_SPECULAR, specular)
            glMaterialf(GL_FRONT, GL_SHININESS, shininess)
            glColorMaterial(GL_FRONT, GL_DIFFUSE)
            
            # Draw shaded faces with polygon offset to prevent edge line z-fighting
            glColor3f(0.69, 0.69, 0.69)
            
            if self.render_mode == 'shaded_with_edges':
                glEnable(GL_POLYGON_OFFSET_FILL)
                glPolygonOffset(1.0, 1.0)
                
            # Render using the VAO (binds vertex VBO, normal VBO, and face indices VBO at once)
            glBindVertexArray(self._vao)
            glDrawElements(GL_TRIANGLES, self.num_indices, GL_UNSIGNED_INT, None)
            glBindVertexArray(0)
            
            if self.render_mode == 'shaded_with_edges':
                glDisable(GL_POLYGON_OFFSET_FILL)
                
                # Draw sharp edge lines from edges VBO
                if self._vbo_edges is not None and self.num_edge_vertices > 0:
                    glDisable(GL_LIGHTING)
                    glEnableClientState(GL_VERTEX_ARRAY)
                    
                    glBindBuffer(GL_ARRAY_BUFFER, self._vbo_edges)
                    glVertexPointer(3, GL_FLOAT, 0, None)
                    
                    # Crisp black lines for CAD outline feel
                    glColor3f(0.0, 0.0, 0.0)
                    glLineWidth(1.5)
                    glDrawArrays(GL_LINES, 0, self.num_edge_vertices)
                    
                    glBindBuffer(GL_ARRAY_BUFFER, 0)
                    glDisableClientState(GL_VERTEX_ARRAY)
                    glEnable(GL_LIGHTING)

    def resizeGL(self, width: int, height: int):
        """Set projection perspective matrix on window resize"""
        glViewport(0, 0, width, height)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        aspect = float(width) / max(height, 1)
        gluPerspective(45.0, aspect, 1.0, 10000.0)
        glMatrixMode(GL_MODELVIEW)

    # Standard Views Camera Snaps
    def snap_front(self):
        """Snap camera to Front View"""
        self.rot_x = 0.0
        self.rot_y = 0.0
        self.update()

    def snap_side(self):
        """Snap camera to Side View"""
        self.rot_x = 0.0
        self.rot_y = -90.0
        self.update()

    def snap_top(self):
        """Snap camera to Top View"""
        self.rot_x = 90.0
        self.rot_y = 0.0
        self.update()

    def snap_iso(self):
        """Snap camera to Isometric View"""
        self.rot_x = 35.264
        self.rot_y = -45.0
        self.update()

    # Viewport Mouse Controls
    def mousePressEvent(self, event: QMouseEvent):
        """Store mouse coordinates on click"""
        self.last_mouse_pos = event.position()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        """Rotate camera on Left-Click drag, pan camera on Right-Click drag"""
        dx = event.position().x() - self.last_mouse_pos.x()
        dy = event.position().y() - self.last_mouse_pos.y()
        self.last_mouse_pos = event.position()
        
        if event.buttons() & Qt.MouseButton.LeftButton:
            # Rotate camera
            self.rot_x += dy * 0.4
            self.rot_y += dx * 0.4
            self.rot_x = max(-90.0, min(90.0, self.rot_x))
            self.update()
            
        elif event.buttons() & Qt.MouseButton.RightButton:
            # Pan camera (pan speed sensitive to distance)
            sensitivity = 0.002 * self.distance
            self.pan_x += dx * sensitivity
            self.pan_y -= dy * sensitivity
            self.update()
            
        event.accept()

    def wheelEvent(self, event: QWheelEvent):
        """Zoom camera distance on mouse scroll wheel"""
        zoom_factor = 1.15
        if event.angleDelta().y() > 0:
            self.distance /= zoom_factor
        else:
            self.distance *= zoom_factor
            
        self.distance = max(5.0, min(5000.0, self.distance))
        self.update()
        event.accept()

    def cleanup(self):
        """Free GPU VAO and VBO resources on widget close"""
        self.makeCurrent()
        self._cleanup_vbo()
        if self._vbo_grid is not None:
            glDeleteBuffers(1, [self._vbo_grid])
            self._vbo_grid = None
        self.doneCurrent()
