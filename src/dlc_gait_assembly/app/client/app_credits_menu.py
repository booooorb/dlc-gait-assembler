"""Build attribution actions and open the associated project and partner links."""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMenu


class AppCreditsMenu:
    """AppCreditsMenu operates on its explicitly supplied MainWindow view."""

    def __init__(self, view):
        self.view = view

    @staticmethod
    def _build_credit_actions(credits_menu: QMenu) -> None:
        for label, citation, url in CREDIT_LINKS:
            action = credits_menu.addAction(label)
            action.setToolTip(citation)
            action.setStatusTip(citation)
            action.triggered.connect(
                lambda _checked=False, destination=url: QDesktopServices.openUrl(QUrl(destination))
            )


CREDIT_LINKS = (
    ("Mouse artwork — SciDraw", "Mouse illustration from SciDraw", "https://scidraw.io/drawing/mouse-09d7b739"),
    (
        "ALMA — Aljović et al. (2022)",
        "A deep learning-based toolbox for Automated Limb Motion Analysis (ALMA) in murine models of neurological disorders",
        "https://doi.org/10.1038/s42003-022-03077-6",
    ),
    (
        "RustLab1 — Weber et al. (2022)",
        "Deep learning-based behavioral profiling of rodent stroke recovery",
        "https://doi.org/10.1186/s12915-022-01434-9",
    ),
    (
        "SingleBehaviorLab — Aljović et al. (2026)",
        "SingleBehavior Lab: behavioral sequencing and phenotyping with lightweight task specific adaptation (bioRxiv preprint)",
        "https://doi.org/10.64898/2026.04.15.718696",
    ),
    (
        "DeepLabCut — Mathis et al. (2018)",
        "DeepLabCut: markerless pose estimation of user-defined body parts with deep learning",
        "https://doi.org/10.1038/s41593-018-0209-y",
    ),
)
