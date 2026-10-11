"""Select processed or labeled review videos and open the shared media-preview player."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
)

from dlc_gait_assembly.runway.automatic.business.automatic_execution_contracts import ReviewArtifact
from dlc_gait_assembly.runway.automatic.review.client.automatic_review_stickplot_panel import PipelineTextPreviewDialog
from dlc_gait_assembly.shared.client.media_preview_dialog import MediaPreviewDialog, MediaPreviewSource


class AutomaticReviewVideoController:
    """AutomaticReviewVideoController operates on its explicitly supplied AutomatedPipelineProfilesWidget view."""

    def __init__(self, view):
        self.view = view

    def _add_real_review_video_item(self, target: QListWidget, artifact: ReviewArtifact) -> None:
        path = artifact.path
        title = artifact.title or path.name
        view = artifact.view or "Full frame"
        details = f"View: {view}"
        item = QListWidgetItem(f"{title}  —  {details}")
        item.setData(Qt.UserRole, str(path))
        item.setData(Qt.UserRole + 1, details)
        item.setData(Qt.UserRole + 2, title)
        item.setData(Qt.UserRole + 4, view)
        item.setToolTip("Double-click to inspect this generated video.")
        target.addItem(item)

    def _open_pipeline_review_video(self, item: QListWidgetItem) -> None:
        if item.data(Qt.UserRole + 3) == "component_header":
            return
        title = str(item.data(Qt.UserRole + 2) or item.text().splitlines()[0])
        details = str(item.data(Qt.UserRole + 1) or "")
        (review_sources, selected_index) = self._pipeline_review_sources(item)
        try:
            if review_sources:
                dialog: QDialog = MediaPreviewDialog(
                    review_sources[selected_index].path,
                    self.view,
                    review_sources=review_sources,
                    initial_source_index=selected_index,
                    media_access=self.view.media_access,
                )
            else:
                dialog = PipelineTextPreviewDialog(
                    title, f"{details}\n\nNo generated video exists in UI preview mode.", self.view
                )
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self.view, "Could not preview video", str(exc))
            return
        self.view.review_stickplot._show_large_review_dialog(dialog)

    def _pipeline_review_sources(self, selected_item: QListWidgetItem) -> tuple[tuple[MediaPreviewSource, ...], int]:
        selected_list = selected_item.listWidget()
        if selected_list is self.view.pipeline_review_video_list:
            review_lists = (("All regions", self.view.pipeline_review_video_list),)
        else:
            review_lists = tuple(self.view.pipeline_component_video_lists.items())
        sources: list[MediaPreviewSource] = []
        selected_index = 0
        for fallback_view, review_list in review_lists:
            for row in range(review_list.count()):
                item = review_list.item(row)
                if item.data(Qt.UserRole + 3) == "component_header":
                    continue
                path_text = str(item.data(Qt.UserRole) or "")
                path = Path(path_text) if path_text else None
                if path is None or not self.view.review_artifacts.exists(path):
                    continue
                source = MediaPreviewSource(
                    path=path,
                    title=str(item.data(Qt.UserRole + 2) or item.text().splitlines()[0]),
                    details=str(item.data(Qt.UserRole + 1) or ""),
                    view_name=str(item.data(Qt.UserRole + 4) or fallback_view),
                )
                if item is selected_item:
                    selected_index = len(sources)
                sources.append(source)
        return (tuple(sources), selected_index)
