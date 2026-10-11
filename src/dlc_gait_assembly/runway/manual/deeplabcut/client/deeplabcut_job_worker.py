"""Translate an injected command session's output and completion into Qt signals."""

from PySide6.QtCore import QThread, Signal


class DeepLabCutJobWorker(QThread):
    output_received = Signal(str)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, session, command, parent=None):
        super().__init__(parent)
        self.session, self.command = session, command

    def run(self):
        try:
            self.completed.emit(self.session.run(self.command, self.output_received.emit))
        except Exception as exc:
            self.failed.emit(str(exc))

    def send_input(self, text):
        self.session.write(text + "\n")

    def cancel(self):
        self.session.cancel()
