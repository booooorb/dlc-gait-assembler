from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QStackedWidget, QTabBar, QTabWidget

from dlc_gait_assembly.gui import theme


class SlidingTabBar(QTabBar):
    """Tab bar with one accent indicator that glides to the active tab."""

    def __init__(self, accent: str | None = None, parent=None):
        super().__init__(parent)
        self._accent = accent
        self._active_row = True
        self._indicator = QRect()
        self._indicator_animation = QPropertyAnimation(self, b"indicatorGeometry", self)
        self._indicator_animation.setDuration(220)
        self._indicator_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.currentChanged.connect(self._animate_indicator)

    def get_indicator_geometry(self) -> QRect:
        return self._indicator

    def set_indicator_geometry(self, geometry: QRect) -> None:
        self._indicator = geometry
        self.update()

    indicatorGeometry = Property(QRect, get_indicator_geometry, set_indicator_geometry)

    def set_active_row(self, active: bool) -> None:
        self._active_row = bool(active)
        self.setProperty("activeRow", self._active_row)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def _target_geometry(self, index: int) -> QRect:
        if index < 0 or index >= self.count():
            return QRect()
        rect = self.tabRect(index)
        return QRect(rect.x(), self.height() - 3, rect.width(), 3)

    def _animate_indicator(self, index: int) -> None:
        target = self._target_geometry(index)
        self._indicator_animation.stop()
        if self._indicator.isNull() or not self.isVisible():
            self._indicator = target
            self.update()
            return
        self._indicator_animation.setStartValue(self._indicator)
        self._indicator_animation.setEndValue(target)
        self._indicator_animation.start()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._indicator = self._target_geometry(self.currentIndex())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._indicator_animation.state() != QPropertyAnimation.State.Running:
            self._indicator = self._target_geometry(self.currentIndex())

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._indicator.isNull() or not self._active_row:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QColor(Qt.transparent))
        painter.setBrush(QColor(self._accent or theme.TOOL_1))
        painter.drawRoundedRect(self._indicator, 1.5, 1.5)


def install_sliding_tab_bar(tab_widget: QTabWidget, accent: str | None = None) -> SlidingTabBar:
    """Install the shared animated selection bar before tabs are added."""
    bar = SlidingTabBar(accent, tab_widget)
    tab_widget.setTabBar(bar)
    return bar


class CurrentPageStackedWidget(QStackedWidget):
    """A stack whose hidden pages cannot force the whole window to grow."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.currentChanged.connect(lambda _index: self.updateGeometry())

    def sizeHint(self) -> QSize:
        current = self.currentWidget()
        return current.sizeHint() if current is not None else super().sizeHint()

    def minimumSizeHint(self) -> QSize:
        return QSize(0, 0)
