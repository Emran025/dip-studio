"""Thin UI composition shell. Business behavior stays in application use cases."""

from PySide6.QtWidgets import QLabel, QMainWindow


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setCentralWidget(QLabel("DIP Studio"))
