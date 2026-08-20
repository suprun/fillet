import os
from qgis.testing import start_app
app = start_app()

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QImage, QPainter
from qgis.PyQt.QtSvg import QSvgRenderer

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
svg_path = os.path.join(base_dir, "icon.svg")
png_path = os.path.join(base_dir, "icon.png")

renderer = QSvgRenderer(svg_path)
img = QImage(96, 96, QImage.Format_ARGB32_Premultiplied)
img.fill(Qt.transparent)

painter = QPainter(img)
painter.setRenderHint(QPainter.Antialiasing, True)
painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
painter.setRenderHint(QPainter.TextAntialiasing, True)
renderer.render(painter)
painter.end()

img.save(png_path, "PNG")
print(f"Generated {png_path} ({img.width()}x{img.height()})")
