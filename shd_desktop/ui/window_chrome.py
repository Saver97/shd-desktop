"""Theme-aware window decorations using native system move/resize."""
from PySide6.QtCore import Qt, QEvent, QObject
from PySide6.QtWidgets import QWidget, QLabel, QPushButton, QHBoxLayout, QVBoxLayout, QApplication
from shd_desktop.ui.theme import cyberpunk


class TitleBar(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.owner = window
        self.setObjectName('ThemedTitleBar')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(38)
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 4, 6, 4)
        row.setSpacing(4)
        self.title = QLabel(window.windowTitle())
        self.title.setAttribute(Qt.WA_TransparentForMouseEvents)
        row.addWidget(self.title, 1)
        window.windowTitleChanged.connect(self.title.setText)
        for text, tip, callback in [('—','最小化',window.showMinimized),
                                     ('□','最大化 / 还原',self.toggle_maximized),
                                     ('×','关闭',window.close)]:
            button = QPushButton(text)
            button.setToolTip(tip)
            button.setFixedSize(38,28)
            if text == '×':
                button.setObjectName('WindowClose')
            button.clicked.connect(callback)
            row.addWidget(button)
        self.apply_hud()

    def apply_hud(self):
        accent = '#FCEE0A' if cyberpunk() else '#F48A35'
        self.setStyleSheet(f'''
            QWidget#ThemedTitleBar {{ background:#101419; border-top:2px solid {accent};
                border-bottom:1px solid #394149; }}
            QLabel {{ color:{accent if cyberpunk() else '#EDF0F0'}; font-size:12px;
                font-weight:{700 if cyberpunk() else 400}; background:transparent; border:0; }}
            QPushButton {{ color:#DDE5E8; background:transparent; border:0; padding:0; font-size:17px; }}
            QPushButton:hover {{ color:#111214; background:{accent}; }}
            QPushButton#WindowClose:hover {{ background:#D83B4D; color:white; }}
        ''')

    def toggle_maximized(self):
        self.owner.showNormal() if self.owner.isMaximized() else self.owner.showMaximized()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.owner.windowHandle():
            self.owner.windowHandle().startSystemMove()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.toggle_maximized()


class ResizeFilter(QObject):
    def eventFilter(self, obj, event):
        if event.type() != QEvent.MouseButtonPress or not isinstance(obj, QWidget):
            return False
        window = obj.window()
        if not getattr(window, '_themed_titlebar', None) or window.isMaximized():
            return False
        if event.button() != Qt.LeftButton:
            return False
        point = window.mapFromGlobal(event.globalPosition().toPoint())
        edges = Qt.Edges()
        if point.x() < 6: edges |= Qt.LeftEdge
        if point.x() >= window.width()-6: edges |= Qt.RightEdge
        if point.y() < 6: edges |= Qt.TopEdge
        if point.y() >= window.height()-6: edges |= Qt.BottomEdge
        if edges and window.windowHandle():
            return window.windowHandle().startSystemResize(edges)
        return False


def install_titlebar(window):
    window.setWindowFlag(Qt.FramelessWindowHint, True)
    old_header = window.menuWidget()
    if old_header:
        old_header.setParent(None)
    wrapper = QWidget(window)
    layout = QVBoxLayout(wrapper)
    layout.setContentsMargins(0,0,0,0)
    layout.setSpacing(0)
    window._themed_titlebar = TitleBar(window)
    layout.addWidget(window._themed_titlebar)
    if old_header:
        layout.addWidget(old_header)
    window.setMenuWidget(wrapper)
    app = QApplication.instance()
    if not hasattr(app, '_window_resize_filter'):
        app._window_resize_filter = ResizeFilter(app)
        app.installEventFilter(app._window_resize_filter)
