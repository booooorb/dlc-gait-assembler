from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QProxyStyle, QStyle

from dlc_gait_assembly.gui.main_window import MainWindow


TOOLTIP_WAKEUP_SPEEDUP = 2


class FastToolTipStyle(QProxyStyle):
    def styleHint(self, hint, option=None, widget=None, returnData=None) -> int:
        value = super().styleHint(hint, option, widget, returnData)
        if hint == QStyle.StyleHint.SH_ToolTip_WakeUpDelay:
            return max(1, value // TOOLTIP_WAKEUP_SPEEDUP)
        return value


def main() -> int:
    app = QApplication(sys.argv)
    fast_tooltip_style = FastToolTipStyle(app.style())
    app.setStyle(fast_tooltip_style)
    app._fast_tooltip_style = fast_tooltip_style
    window = MainWindow()
    window.show()
    return app.exec()
