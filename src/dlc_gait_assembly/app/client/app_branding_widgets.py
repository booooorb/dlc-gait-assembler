"""Render application and partner logos, credits buttons, and menu illustrations."""

from __future__ import annotations

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    QUrl,
    Signal,
)
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.app.client.app_page_contracts import ToolSpec
from dlc_gait_assembly.runway.manual.business.manual_stage_definitions import MANUAL_STAGE_ICONS
from dlc_gait_assembly.shared.client.theme.theme_icon_provider import interface_icon
from dlc_gait_assembly.shared.client.theme.theme_menu_graphics import menu_icon
from dlc_gait_assembly.shared.infrastructure.packaged_resource_reader import resource_exists, resource_path

MAIN_MENU_LOGO_HEIGHT = 24
MAIN_MENU_LOGO_MAX_WIDTH = 104
BRAND_LOGO_HEIGHT = 34
BRAND_LOGO_MAX_WIDTH = 160
BRAND_LOGO_FILENAMES = {
    "light": "DLC-Gait-Assembler-logo-light-original-clean.png",
    "dark": "DLC-Gait-Assembler-logo-dark-original-clean.png",
}
PARTNER_WEBSITES = {"choforcelab.png": "https://www.choforcelab.ca", "NERVES_Logo.png": "https://nerves.bme.utah.edu"}
MAIN_MENU_ICON_ASSET_DIR = resource_path("icons")


def navigation_icon(icon_name: str, color: str) -> QIcon:
    names = {
        "automated": "player-play",
        "runway": "route",
        "profiles": "folders",
        "manual": "adjustments-horizontal",
        "ladder": "ladder",
    }
    return menu_icon(names[icon_name], color, 18)


def menu_asset_pixmap(name: str, size: int) -> QPixmap:
    """Load a reference-derived main-menu illustration at a crisp UI size."""
    source = load_menu_asset_pixmap(name)
    if source.isNull():
        return source
    return source.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def load_menu_asset_pixmap(name: str) -> QPixmap:
    """Load either a raster menu asset or an SVG at its native dimensions."""
    if name == "ladder-mouse":
        return ladder_menu_pixmap()
    if name == "runway-mouse":
        return runway_menu_pixmap()
    svg_path = MAIN_MENU_ICON_ASSET_DIR / f"{name}.svg"
    if resource_exists("icons", f"{name}.svg"):
        renderer = QSvgRenderer(str(svg_path))
        if not renderer.isValid():
            return QPixmap()
        source_size = renderer.defaultSize()
        pixmap = QPixmap(source_size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        return pixmap
    return QPixmap(str(MAIN_MENU_ICON_ASSET_DIR / f"{name}.png"))


def ladder_menu_pixmap() -> QPixmap:
    """Composite the replacement mouse over the original ladder perspective."""
    ladder = QPixmap(str(MAIN_MENU_ICON_ASSET_DIR / "ladder-runway.png"))
    mouse = QSvgRenderer(str(MAIN_MENU_ICON_ASSET_DIR / "ladder-mouse.svg"))
    if ladder.isNull() or not mouse.isValid():
        return QPixmap()
    canvas = QPixmap(ladder.size())
    canvas.fill(Qt.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    painter.drawPixmap(0, 0, ladder)
    mouse_width = round(canvas.width() * 0.47)
    mouse_height = round(mouse_width * mouse.defaultSize().height() / mouse.defaultSize().width())
    mouse_left = round((canvas.width() - mouse_width) / 2 + canvas.width() * 0.03)
    mouse_top = round(canvas.height() * 0.15)
    mouse.render(painter, QRectF(mouse_left, mouse_top, mouse_width, mouse_height))
    painter.end()
    return canvas.copy(QRect(0, 25, canvas.width(), 570))


def runway_menu_pixmap() -> QPixmap:
    """Composite the replacement mouse onto the original runway artwork."""
    runway = QPixmap(str(MAIN_MENU_ICON_ASSET_DIR / "runway-enclosure.png"))
    mouse = QSvgRenderer(str(MAIN_MENU_ICON_ASSET_DIR / "ladder-mouse.svg"))
    if runway.isNull() or not mouse.isValid():
        return QPixmap()
    canvas = QPixmap(runway.size())
    canvas.fill(Qt.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    painter.drawPixmap(0, 0, runway)
    mouse_width = round(canvas.width() * 0.47)
    mouse_height = round(mouse_width * mouse.defaultSize().height() / mouse.defaultSize().width())
    mouse_left = round((canvas.width() - mouse_width) / 2 + canvas.width() * 0.05)
    mouse_top = round(canvas.height() * 0.135)
    mouse.render(painter, QRectF(mouse_left, mouse_top, mouse_width, mouse_height))
    painter.end()
    return canvas


class MenuIllustrationLabel(QLabel):
    """Paint a clipped, aspect-fit illustration without changing layout hints."""

    def __init__(self, asset_name: str, accessible_name: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("WorkspaceChoiceIllustration")
        self.setAccessibleName(accessible_name)
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(178)
        self._source_pixmap = load_menu_asset_pixmap(asset_name)
        self.setPixmap(self._source_pixmap)
        self._zoom = 1.0

    def sizeHint(self) -> QSize:
        return QSize(360, 178)

    def paintEvent(self, event) -> None:
        if self._source_pixmap.isNull():
            super().paintEvent(event)
            return
        viewport = self.contentsRect()
        fitted = self._source_pixmap.size().scaled(viewport.size(), Qt.KeepAspectRatio)
        draw_size = QSize(round(fitted.width() * self._zoom), round(fitted.height() * self._zoom))
        target = QRect(QPoint(), draw_size)
        target.moveCenter(viewport.center())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setClipRect(viewport)
        painter.drawPixmap(target, self._source_pixmap)

    def _get_zoom(self) -> float:
        return self._zoom

    def _set_zoom(self, zoom: float) -> None:
        self._zoom = max(1.0, min(float(zoom), 1.05))
        self.update()

    zoom = Property(float, _get_zoom, _set_zoom)


class HoverPixmapLabel(QLabel):
    """A compact pixmap label that shares the menu-card hover zoom."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._source_pixmap = QPixmap()
        self._zoom = 1.0

    def setPixmap(self, pixmap: QPixmap) -> None:
        self._source_pixmap = pixmap
        super().setPixmap(pixmap)

    def paintEvent(self, event) -> None:
        if self._source_pixmap.isNull():
            super().paintEvent(event)
            return
        viewport = self.contentsRect()
        fitted = self._source_pixmap.size().scaled(viewport.size(), Qt.KeepAspectRatio)
        draw_size = QSize(round(fitted.width() * self._zoom), round(fitted.height() * self._zoom))
        target = QRect(QPoint(), draw_size)
        target.moveCenter(viewport.center())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setClipRect(viewport)
        painter.drawPixmap(target, self._source_pixmap)

    def _get_zoom(self) -> float:
        return self._zoom

    def _set_zoom(self, zoom: float) -> None:
        self._zoom = max(1.0, min(float(zoom), 1.05))
        self.update()

    zoom = Property(float, _get_zoom, _set_zoom)


class ManualMiniStage(QFrame):
    """Keyboard-accessible stage tile for the expanded manual menu."""

    clicked = Signal(str)

    def __init__(self, tool_id: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._tool_id = tool_id
        self.setFocusPolicy(Qt.StrongFocus)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit(self._tool_id)
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.clicked.emit(self._tool_id)
            event.accept()
            return
        super().keyPressEvent(event)


class WorkspaceChoiceCard(QFrame):
    """A setup card whose full visible surface acts as one accessible control."""

    clicked = Signal()
    _active_hover_card: WorkspaceChoiceCard | None = None

    def __init__(self, accessible_name: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAccessibleName(accessible_name)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self._hover_animation: QParallelAnimationGroup | None = None

    def _animate_illustration(self, zoom: float, duration: int) -> None:
        illustrations = self.findChildren(MenuIllustrationLabel) + self.findChildren(HoverPixmapLabel)
        if not illustrations:
            return
        if self._hover_animation is not None:
            self._hover_animation.stop()
        group = QParallelAnimationGroup(self)
        for illustration in illustrations:
            animation = QPropertyAnimation(illustration, b"zoom", group)
            animation.setDuration(duration)
            animation.setStartValue(illustration.zoom)
            animation.setEndValue(zoom)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            group.addAnimation(animation)
        self._hover_animation = group
        group.start()

    def enterEvent(self, event) -> None:
        previous = WorkspaceChoiceCard._active_hover_card
        if previous is not None and previous is not self:
            previous._reset_hover_immediately()
        WorkspaceChoiceCard._active_hover_card = self
        self._animate_illustration(1.05, 260)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        if WorkspaceChoiceCard._active_hover_card is self:
            WorkspaceChoiceCard._active_hover_card = None
        self._reset_hover_immediately()
        super().leaveEvent(event)

    def _reset_hover_immediately(self) -> None:
        if self._hover_animation is not None:
            self._hover_animation.stop()
        illustrations = self.findChildren(MenuIllustrationLabel) + self.findChildren(HoverPixmapLabel)
        for illustration in illustrations:
            illustration.zoom = 1.0

    def make_decorations_mouse_transparent(self, action_button: QPushButton) -> None:
        for child in self.findChildren(QWidget):
            if child is not action_button and (not isinstance(child, QPushButton)):
                child.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            if WorkspaceChoiceCard._active_hover_card is self:
                WorkspaceChoiceCard._active_hover_card = None
            self._reset_hover_immediately()
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.clicked.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class PartnerLogoLabel(QLabel):
    def __init__(self, filename: str):
        super().__init__()
        self.setObjectName("MainMenuLogo")
        self.setAccessibleName("Cho Force Lab logo" if filename == "choforcelab.png" else "NERVES Lab logo")
        self._website_url = QUrl(PARTNER_WEBSITES[filename])
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setToolTip(f"Open {self._website_url.host()} in your browser")
        self._plain_pixmap = QPixmap()
        self._outlined_pixmap = QPixmap()
        self._load_pixmaps(filename)
        self.apply_theme()

    def _load_pixmaps(self, filename: str) -> None:
        path = resource_path("branding", filename)
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return
        screen = QGuiApplication.primaryScreen()
        scale = max(1.0, screen.devicePixelRatio() if screen is not None else 1.0)
        scaled = pixmap.scaled(
            round(MAIN_MENU_LOGO_MAX_WIDTH * scale),
            round(MAIN_MENU_LOGO_HEIGHT * scale),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        outline_width = max(1, round(2 * scale))
        self._plain_pixmap = QPixmap(scaled)
        self._outlined_pixmap = pixmap_with_outline(scaled, QColor("#FFFFFF"), outline_width)
        self._plain_pixmap.setDevicePixelRatio(scale)
        self._outlined_pixmap.setDevicePixelRatio(scale)

    def apply_theme(self) -> None:
        pixmap = self._outlined_pixmap if theme.IS_DARK else self._plain_pixmap
        if pixmap.isNull():
            return
        self.setPixmap(pixmap)
        scale = pixmap.devicePixelRatio()
        self.setFixedSize(round(pixmap.width() / scale), round(pixmap.height() / scale))

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            QDesktopServices.openUrl(self._website_url)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            QDesktopServices.openUrl(self._website_url)
            event.accept()
            return
        super().keyPressEvent(event)


def pixmap_with_outline(source: QPixmap, color: QColor, width: int) -> QPixmap:
    width = max(1, width)
    silhouette = QPixmap(source.size())
    silhouette.fill(Qt.transparent)
    silhouette_painter = QPainter(silhouette)
    silhouette_painter.drawPixmap(0, 0, source)
    silhouette_painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    silhouette_painter.fillRect(silhouette.rect(), color)
    silhouette_painter.end()
    outlined = QPixmap(source.width() + width * 2, source.height() + width * 2)
    outlined.fill(Qt.transparent)
    painter = QPainter(outlined)
    for y_offset in range(-width, width + 1):
        for x_offset in range(-width, width + 1):
            if x_offset * x_offset + y_offset * y_offset <= width * width:
                painter.drawPixmap(width + x_offset, width + y_offset, silhouette)
    painter.drawPixmap(width, width, source)
    painter.end()
    return outlined


def main_menu_logo_label(filename: str) -> QLabel:
    return PartnerLogoLabel(filename)


class WorkflowStep(QFrame):
    clicked = Signal(str)

    def __init__(self, index: int, spec: ToolSpec):
        super().__init__()
        self._spec = spec
        self.setObjectName("WorkflowStep")
        self.setProperty("enabledStep", spec.enabled)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(107)
        if spec.enabled:
            self.setCursor(Qt.PointingHandCursor)
            if spec.description:
                self.setToolTip(spec.description)
        else:
            self.setToolTip("Not available yet.")
        self._build_ui(index, spec)

    def _build_ui(self, index: int, spec: ToolSpec) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(8)
        heading = QHBoxLayout()
        heading.setSpacing(10)
        self.graphic = QLabel()
        self.graphic.setObjectName("StepGraphic")
        self.graphic.setAlignment(Qt.AlignCenter)
        self.graphic.setFixedSize(40, 40)
        self.graphic.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        heading.addWidget(self.graphic)
        title = QLabel(spec.label)
        title.setObjectName("StepTitle")
        title.setProperty("enabledStep", spec.enabled)
        title.setWordWrap(True)
        title.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        heading.addWidget(title, 1)
        root.addLayout(heading)
        root.addStretch(1)
        open_button = QPushButton("Open" if spec.enabled else "Unavailable")
        open_button.setObjectName("OpenToolButton")
        open_button.setEnabled(spec.enabled)
        if spec.enabled:
            open_button.clicked.connect(lambda: self.clicked.emit(spec.id))
        root.addWidget(open_button, 0, Qt.AlignRight)
        self.apply_theme()

    def apply_theme(self) -> None:
        color = theme.TOOL_3 if self._spec.enabled else theme.BORDER
        self.graphic.setPixmap(interface_icon(MANUAL_STAGE_ICONS[self._spec.id], color, size=26).pixmap(26, 26))

    def mouseReleaseEvent(self, event) -> None:
        if self._spec.enabled and event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            self.clicked.emit(self._spec.id)
            event.accept()
            return
        super().mouseReleaseEvent(event)
