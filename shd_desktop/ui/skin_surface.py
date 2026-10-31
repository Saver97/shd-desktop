"""Reversible skin treatment for application chrome, never user content."""
from pathlib import Path
from PySide6.QtCore import QObject, QEvent, Qt
from PySide6.QtGui import QIcon, QIconEngine, QPixmap
from PySide6.QtWidgets import QLabel, QAbstractButton, QLineEdit, QTabWidget
from shd_desktop.ui.cyber_icons import category_pixmap

COPY = {
    'SHD Desktop · 控制台': '2077 · 夜之城控制终端',
    'SHD Desktop · 模型配置': '2077 · 神经链路配置',
    'SHD Desktop · 外观与快捷键': '2077 · 界面与快捷接入',
    'SHD Desktop · 快速查找': '2077 · 本地数据扫描',
    'SHD / DESKTOP': 'NIGHT CITY / TERMINAL',
    '任务日程': '委托日志', '区域天气': '城市气象',
    '日程': '委托', '便签': '备忘', '天气': '气象', '音乐': '电台',
    '快速查找': '数据扫描', '模型配置': '神经链路配置',
    '已保存的配置': '链路档案',
    '连接设置  //  日常聊天窗口可按配置选择模型': '神经链路 // 为强尼选择通信模型',
    '模型连接与配置档': '接入节点与链路档案',
    '保存配置': '保存链路', '新增配置': '新建链路',
    '当前模型': '接入模型', '新对话': '重启会话',
    '配置已保存': '链路档案已保存',
    '暂无待办日程': '暂无委托。享受这会儿清静。',
    '暂无天气数据': '气象信号尚未接入',
    '尚未选择地区': '选择城市接入气象',
    '选择地区后显示天气': '选定城市后读取气象数据',
    '尚未选择歌曲': '电台待机。挑首歌吧。',
    '新对话已开始': '新会话接通。说吧。',
    '就绪': '链路在线', '正在回复…': '强尼正在回应…',
    '请求失败': '链路请求失败', '已中断': '通信已中断',
    '输入消息或桌面指令…': '说吧，今天要办什么事？',
    '例如：明天 9 点提醒我开会；显示桌面文件夹；暂停音乐。': '强尼在线。查委托、记备忘、放首歌——先办哪件？',
    '输入图标、文件或分框名称…': '扫描本地：输入文件、应用或分框名称…',
    'HUD 外观  //  修改时预览，保存后下次启动沿用': '界面改装 // 即时预览，保存后沿用',
    '透明度作用于桌面分框、状态卡和 ISAC；文字保持清晰。': '调整分框、状态终端和强尼窗口的底板透明度。',
    '托盘和控制台也可打开快速查找。按 Esc 取消本次预览。': '托盘与控制终端均可扫描本地文件。Esc 撤销本次改装。',
    '恢复默认外观': '重置界面参数',
}


def active():
    from shd_desktop.ui.theme import cyberpunk
    return cyberpunk()


class SkinIcon(QIconEngine):
    def __init__(self, path):
        super().__init__()
        self.path = str(path)
        self.original = QIcon(self.path)

    def clone(self):
        return SkinIcon(self.path)

    def pixmap(self, size, mode, state):
        if active():
            return category_pixmap('', Path(self.path).name, max(size.width(), size.height()), '#FCEE0A')
        return self.original.pixmap(size, mode, state)

    def paint(self, painter, rect, mode, state):
        painter.drawPixmap(rect, self.pixmap(rect.size(), mode, state))


def skin_icon(path):
    return QIcon(SkinIcon(path))


def translate(obj, key, get, put):
    current = get()
    original = obj.property('_skin_original_' + key)
    rendered = obj.property('_skin_rendered_' + key)
    if original is None or current != rendered:
        original = current
    target = COPY.get(original, original) if active() else original
    obj.setProperty('_skin_original_' + key, original)
    obj.setProperty('_skin_rendered_' + key, target)
    if current != target:
        put(target)


def refresh_surface(widget):
    # File names, note titles, editable contents and model names are untouched.
    if isinstance(widget, (QLabel, QAbstractButton)) and widget.objectName() not in ('NoteHeader',):
        if widget.__class__.__name__ not in ('Header', 'ChatDragLabel'):
            translate(widget, 'text', widget.text, widget.setText)
    if isinstance(widget, QLineEdit):
        translate(widget, 'placeholder', widget.placeholderText, widget.setPlaceholderText)
    if widget.isWindow():
        translate(widget, 'title', widget.windowTitle, widget.setWindowTitle)
    if isinstance(widget, QTabWidget):
        for i in range(widget.count()):
            translate(widget, 'tab'+str(i), lambda i=i: widget.tabText(i), lambda v,i=i: widget.setTabText(i,v))
    for action in widget.actions():
        translate(action, 'text', action.text, action.setText)
    source = widget.property('_skin_icon_path')
    if source and isinstance(widget, QLabel):
        if widget.property('_skin_icon_active') != active():
            widget.setPixmap(skin_icon(source).pixmap(24,24))
            widget.setProperty('_skin_icon_active', active())


class SurfaceFilter(QObject):
    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Show, QEvent.Paint):
            from PySide6.QtWidgets import QWidget
            if isinstance(obj, QWidget):
                refresh_surface(obj)
        return False


def install(app):
    if not hasattr(app, '_skin_surface_filter'):
        app._skin_surface_filter = SurfaceFilter(app)
        app.installEventFilter(app._skin_surface_filter)
    for widget in app.allWidgets():
        refresh_surface(widget)


CHROME = '''
QMainWindow, QDialog { background:#0D1117; }
QToolBar#CenterToolbar { background:#FCEE0A; padding:9px 12px; border:2px solid #FCEE0A; }
QToolBar#CenterToolbar QLabel, QToolBar#CenterToolbar QToolButton,
QToolBar#CenterToolbar QComboBox { color:#111214; font-weight:700; }
QToolBar#CenterToolbar QToolButton:hover { background:#111214; color:#FCEE0A; }
QTabWidget#CenterTabs::pane { border:1px solid #807B0B; background:#0D1117; }
QTabWidget#CenterTabs QTabBar::tab { background:#161C23; color:#BFCBD1; border:1px solid #454814; padding:10px 20px; }
QTabWidget#CenterTabs QTabBar::tab:selected { background:#FCEE0A; color:#111214; font-weight:700; }
QLabel#HudSection { background:#FCEE0A; color:#111214; font-weight:700; padding:6px 12px; border:0; }
QPushButton { background:#151E26; border:1px solid #52616B; color:#D8E5E9; }
QPushButton:hover { background:#FCEE0A; color:#111214; border-color:#FCEE0A; }
QLineEdit, QComboBox, QPlainTextEdit, QListWidget { background:#101820; border:1px solid #3D6066; border-radius:0; }
QMenu { background:#101820; border:1px solid #FCEE0A; }
QMenu::item:selected { background:#FCEE0A; color:#111214; }
'''
