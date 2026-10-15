"""Image view showing a video frame in full, with numbered boxes drawn on top.

- The whole frame is fitted to the view ("Fit"); the mouse wheel zooms, dragging moves the image.
- Boxes are given in video pixels; they are drawn with a constant line width on screen, and
  their numbers stay readable at any zoom.
- The mouse is only used to look at the image, never to edit boxes (box editing with the
  mouse is a TODO).
"""

import cv2
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene, QGraphicsSimpleTextItem, QGraphicsView

BOX_COLOUR = QColor(0, 200, 0)
SELECTED_COLOUR = QColor(255, 140, 0)
LOST_COLOUR = QColor(230, 0, 0)


def bgr_to_pixmap(frame):
    """Convert an OpenCV BGR image (numpy array) to a QPixmap."""
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    height, width = rgb.shape[:2]
    image = QImage(rgb.data, width, height, 3 * width, QImage.Format_RGB888)
    return QPixmap.fromImage(image.copy())       # copy: the QImage must not keep pointing at the numpy array


class FrameView(QGraphicsView):
    """Shows one frame and a list of boxes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(QBrush(QColor(60, 60, 60)))
        self.pixmap_item = None
        self.box_items = []
        self.fit_on_resize = True     # keep fitting the frame until the user zooms

    def set_frame(self, frame):
        """Show a new frame (BGR numpy array) and fit it to the view."""
        self.scene.clear()
        self.box_items = []
        self.pixmap_item = self.scene.addPixmap(bgr_to_pixmap(frame))
        self.scene.setSceneRect(QRectF(self.pixmap_item.pixmap().rect()))
        self.fit()

    def update_frame(self, frame):
        """Replace the image but keep the current zoom (used for the live preview)."""
        if self.pixmap_item is None:
            self.set_frame(frame)
        else:
            self.pixmap_item.setPixmap(bgr_to_pixmap(frame))

    def set_boxes(self, boxes, selected=None, colours=None):
        """Draw `boxes` (list of Box) numbered 1, 2, …

        `selected`: index of the box to highlight (orange), or None.
        `colours`: optional list of QColor, one per box (overrides the default green).
        """
        for item in self.box_items:
            self.scene.removeItem(item)
        self.box_items = []
        for i, box in enumerate(boxes):
            if colours is not None:
                colour = colours[i]
            else:
                colour = SELECTED_COLOUR if i == selected else BOX_COLOUR
            pen = QPen(colour, 3 if i == selected else 2)
            pen.setCosmetic(True)                         # same width on screen at any zoom
            rect = self.scene.addRect(QRectF(box.x, box.y, box.w, box.h), pen)
            label = QGraphicsSimpleTextItem(str(i + 1))
            label.setBrush(QBrush(colour))
            font = label.font()
            font.setPointSize(14)
            font.setBold(True)
            label.setFont(font)
            label.setFlag(QGraphicsItem.ItemIgnoresTransformations)   # readable at any zoom
            label.setPen(QPen(QColor(0, 0, 0), 0.7))         # thin dark outline: readable on light and dark areas
            label.setPos(box.x + box.w + 3, box.y)          # number drawn just right of the box, not over the mark
            self.scene.addItem(label)
            self.box_items += [rect, label]

    def fit(self):
        """Show the whole frame."""
        if self.pixmap_item is not None:
            self.fitInView(self.pixmap_item, Qt.KeepAspectRatio)
            self.fit_on_resize = True

    def zoom(self, factor):
        self.scale(factor, factor)
        self.fit_on_resize = False

    def wheelEvent(self, event):
        """Mouse wheel: zoom in/out around the cursor."""
        self.zoom(1.25 if event.angleDelta().y() > 0 else 0.8)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.fit_on_resize:
            self.fit()
