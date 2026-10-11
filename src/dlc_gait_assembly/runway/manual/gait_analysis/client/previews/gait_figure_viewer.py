"""Present generated gait figures at enlarged size and release closed dialogs."""

from dlc_gait_assembly.shared.client.qt_svg_preview import SvgPreviewDialog


class GaitFigureViewer:
    def __init__(self, parent, reader):
        self.parent, self.reader = parent, reader
        self.dialog = None

    def show(self, path):
        if path is None or path.suffix.lower() != ".svg":
            return
        try:
            data = self.reader.svg_bytes(path)
        except OSError:
            return
        if self.dialog is not None:
            self.dialog.close()
        dialog = SvgPreviewDialog(path.stem, ((path.name, data),), self.parent)
        self.dialog = dialog
        dialog.finished.connect(lambda _result: self._closed(dialog))
        dialog.show()

    def _closed(self, dialog):
        if self.dialog is dialog:
            self.dialog = None
