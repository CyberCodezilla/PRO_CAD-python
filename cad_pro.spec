# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller Specification for Python CAD Pro (V2.0 Industrial Release).
Bundles PyQt6, PyOpenGL, OpenCASCADE (OCP / build123d), Trimesh CSG, and CV pipelines.
Enforces User Guardrail #4: Explicit OCP dynamic binary library and data collection.
"""

import sys
import os
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files, collect_submodules

block_cipher = None

# Collect all dynamic DLLs and data assets for OpenCASCADE Python bindings (OCP)
ocp_binaries = collect_dynamic_libs('OCP')
ocp_datas = collect_data_files('OCP')

# Collect build123d and trimesh assets
build123d_datas = collect_data_files('build123d')
trimesh_datas = collect_data_files('trimesh')

all_datas = ocp_datas + build123d_datas + trimesh_datas
all_binaries = ocp_binaries

hidden_imports = [
    'PyQt6',
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    'PyQt6.QtOpenGL',
    'PyQt6.QtOpenGLWidgets',
    'OpenGL',
    'OpenGL.GL',
    'OpenGL.GLU',
    'build123d',
    'OCP',
    'trimesh',
    'manifold3d',
    'mapbox_earcut',
    'shapely',
    'cv2',
    'numpy',
    'scipy',
    'scipy.optimize'
]

# Add all submodules for complex C-extension packages
hidden_imports += collect_submodules('OCP')
hidden_imports += collect_submodules('build123d')
hidden_imports += collect_submodules('trimesh')

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PythonCADPro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PythonCADPro'
)
