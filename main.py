"""
Python CAD Pro - Main Entry Point
Professional CAD application with 2D to 3D reconstruction
"""
import sys
import traceback
from PyQt6.QtWidgets import QApplication
from src.ui.main_window import MainWindow

def exception_hook(exc_type, exc_value, exc_tb):
    """Global exception hook to log unhandled errors to a file"""
    tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    try:
        with open("crash_log.txt", "w") as f:
            f.write("Unhandled exception caught by global hook:\n")
            f.write(tb_str)
    except Exception as io_err:
        print(f"Failed to write crash log: {io_err}", file=sys.stderr)
    print(tb_str, file=sys.stderr)
    sys.exit(1)

# Register the global exception hook
sys.excepthook = exception_hook

def main():
    """Application entry point"""
    try:
        app = QApplication(sys.argv)
        app.setApplicationName("Python CAD Pro")
        app.setOrganizationName("VIS Board")
        
        # Configure QSurfaceFormat for OpenGL Compatibility Profile
        from PyQt6.QtGui import QSurfaceFormat
        fmt = QSurfaceFormat()
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile)
        # Note: Explicitly setting version 3.3 can cause some drivers (like Intel HD Graphics)
        # to fall back to a Core Profile that doesn't support fixed-function features (e.g. GL_LIGHTING).
        # Removing this allows the driver to select the highest compatible context.
        # fmt.setVersion(3, 3)
        QSurfaceFormat.setDefaultFormat(fmt)
        
        # Create and show main window
        window = MainWindow()
        window.show()
        
        sys.exit(app.exec())
    except Exception as e:
        exception_hook(*sys.exc_info())

if __name__ == "__main__":
    main()
