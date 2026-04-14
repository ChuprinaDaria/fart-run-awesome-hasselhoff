from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QApplication
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QPoint
from PyQt5.QtGui import QPixmap, QFont


class NaggerPopup(QWidget):
    """Custom notification popup with large image support."""

    def __init__(self, title: str, body: str, image_path: str = None,
                 timeout_ms: int = 8000, parent=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setStyleSheet("""
            QWidget#popup {
                background: #c0c0c0;
                border: 3px outset #dfdfdf;
            }
            QLabel#title {
                font-size: 14px;
                font-weight: bold;
                color: white;
                background: #000080;
                padding: 4px 8px;
            }
            QLabel#body {
                font-size: 12px;
                color: #000;
                padding: 8px;
                background: #ffffcc;
                border: 2px inset #808080;
            }
        """)
        self.setObjectName("popup")
        self.setFixedWidth(380)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)

        # Title bar (Win95 style)
        title_label = QLabel(title)
        title_label.setObjectName("title")
        layout.addWidget(title_label)

        # Image
        if image_path:
            img_label = QLabel()
            pixmap = QPixmap(image_path)
            if not pixmap.isNull():
                pixmap = pixmap.scaledToWidth(360, Qt.SmoothTransformation)
                if pixmap.height() > 250:
                    pixmap = pixmap.scaledToHeight(250, Qt.SmoothTransformation)
                img_label.setPixmap(pixmap)
                img_label.setAlignment(Qt.AlignCenter)
                img_label.setStyleSheet("padding: 4px; background: white; border: 2px inset #808080;")
                layout.addWidget(img_label)

        # Body text
        body_label = QLabel(body)
        body_label.setObjectName("body")
        body_label.setWordWrap(True)
        layout.addWidget(body_label)

        self.adjustSize()

        # Position: bottom-right corner of screen
        screen = QApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            x = geom.right() - self.width() - 20
            y = geom.bottom() - self.height() - 20
            self.move(x, y)

        # Auto-close timer
        QTimer.singleShot(timeout_ms, self._fade_close)

    def _fade_close(self):
        self.close()
        self.deleteLater()

    def mousePressEvent(self, event):
        """Click to dismiss."""
        self.close()
        self.deleteLater()
