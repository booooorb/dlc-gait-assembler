"""Display review stickplots and manage enlarged preview dialogs."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget

from dlc_gait_assembly.shared.client.theme.theme_application_styles import stylesheet as _dependency_theme_stylesheet
from dlc_gait_assembly.shared.infrastructure.svg_preview_sanitizer import qt_safe_svg_bytes


class AutomaticReviewStickplotPanel:
    """AutomaticReviewStickplotPanel operates on its explicitly supplied AutomatedPipelineProfilesWidget view."""

    def __init__(self, view):
        self.view = view

    def _open_large_stickplot_preview(self) -> None:
        if self.view._pipeline_stickplot_path is None or not self.view.review_artifacts.exists(
            self.view._pipeline_stickplot_path
        ):
            self._show_large_review_dialog(
                PipelineTextPreviewDialog(
                    "Generated stickplot preview",
                    "No ALMA or RustLab1 stickplot has been generated for this review.",
                    self.view,
                )
            )
            return
        self._show_large_review_dialog(
            PipelineImagePreviewDialog(
                "Generated stickplot preview",
                self.view._pipeline_stickplot_path,
                self.view,
                artifacts=self.view.review_artifacts,
            )
        )

    def _show_large_review_dialog(self, dialog: QDialog) -> None:
        if self.view._large_review_dialog is not None:
            self.view._large_review_dialog.close()
        self.view._large_review_dialog = dialog
        dialog.finished.connect(lambda _result, closed_dialog=dialog: self._large_review_closed(closed_dialog))
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _large_review_closed(self, dialog: QDialog) -> None:
        if self.view._large_review_dialog is dialog:
            self.view._large_review_dialog = None


class AspectRatioImageLabel(QLabel):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._source_pixmap = QPixmap()
        self._source_svg_data: bytes | None = None

    def setPixmap(self, pixmap: QPixmap) -> None:
        self._source_svg_data = None
        self._source_pixmap = pixmap
        self._render_pixmap()

    def load_image_data(self, data: bytes, suffix: str) -> bool:
        if suffix.casefold() == ".svg":
            try:
                svg_data = qt_safe_svg_bytes(data)
            except OSError:
                return False
            renderer = QSvgRenderer(QByteArray(svg_data))
            if not renderer.isValid():
                return False
            renderer.setAspectRatioMode(Qt.KeepAspectRatio)
            self._source_svg_data = svg_data
            self._source_pixmap = QPixmap()
        else:
            pixmap = QPixmap()
            pixmap.loadFromData(data)
            if pixmap.isNull():
                return False
            self._source_svg_data = None
            self._source_pixmap = pixmap
        self._render_pixmap()
        return True

    def _render_pixmap(self) -> None:
        target = self.contentsRect().size()
        if target.isEmpty():
            return
        if self._source_svg_data is not None:
            rendered = render_svg_pixmap(
                self._source_svg_data, target, device_pixel_ratio=max(1.0, self.devicePixelRatioF())
            )
            QLabel.setPixmap(self, rendered)
            return
        if self._source_pixmap.isNull():
            QLabel.setPixmap(self, QPixmap())
            return
        QLabel.setPixmap(self, self._source_pixmap.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._render_pixmap()


def render_svg_pixmap(svg_data: bytes, target_size: QSize, *, device_pixel_ratio: float = 1.0) -> QPixmap:
    """Render SVG at the requested logical size and display pixel ratio."""
    ratio = max(1.0, float(device_pixel_ratio))
    physical_size = QSize(max(1, round(target_size.width() * ratio)), max(1, round(target_size.height() * ratio)))
    pixmap = QPixmap(physical_size)
    pixmap.fill(Qt.transparent)
    renderer = QSvgRenderer(QByteArray(qt_safe_svg_bytes(svg_data)))
    renderer.setAspectRatioMode(Qt.KeepAspectRatio)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    renderer.render(painter, QRectF(0, 0, physical_size.width(), physical_size.height()))
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


class DoubleClickLabel(AspectRatioImageLabel):
    clicked = Signal()
    double_clicked = Signal()

    def sizeHint(self) -> QSize:
        return QSize(240, 78)

    def minimumSizeHint(self) -> QSize:
        return QSize(0, 0)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        self.double_clicked.emit()
        event.accept()


class PipelineImagePreviewDialog(QDialog):
    def __init__(self, title: str, image_path: Path, parent: QWidget | None = None, *, artifacts):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(720, 500)
        self.resize(960, 680)
        layout = QVBoxLayout(self)
        heading = QLabel(title)
        heading.setObjectName("LargeVideoPreviewTitle")
        layout.addWidget(heading)
        self.preview = AspectRatioImageLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setObjectName("LargeImagePreview")
        layout.addWidget(self.preview, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setStyleSheet(
            _dependency_theme_stylesheet(
                "\n                QLabel#LargeVideoPreviewTitle {\n                    color: {theme.TEXT};\n                    font-size: 14px;\n                    font-weight: 650;\n                }\n                QLabel#LargeImagePreview {\n                    background: white;\n                    border: 1px solid {theme.BORDER};\n                }\n                "
            )
        )
        self.image_loaded = self.preview.load_image_data(artifacts.image_bytes(image_path), image_path.suffix)
        if not self.image_loaded:
            self.preview.setText("Could not render this generated image.")


class PipelineTextPreviewDialog(QDialog):
    def __init__(self, title: str, details: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(620, 360)
        layout = QVBoxLayout(self)
        heading = QLabel(title)
        heading.setObjectName("LargeVideoPreviewTitle")
        layout.addWidget(heading)
        preview = QLabel(details)
        preview.setObjectName("LargeVideoPreview")
        preview.setAlignment(Qt.AlignCenter)
        preview.setWordWrap(True)
        layout.addWidget(preview, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setStyleSheet(
            _dependency_theme_stylesheet(
                "\n                QLabel#LargeVideoPreviewTitle {\n                    color: {theme.TEXT};\n                    font-size: 14px;\n                    font-weight: 650;\n                }\n                QLabel#LargeVideoPreview {\n                    background: {theme.CANVAS};\n                    border: 1px solid {theme.BORDER};\n                    color: {theme.CANVAS_TEXT};\n                    padding: 24px;\n                }\n                "
            )
        )
