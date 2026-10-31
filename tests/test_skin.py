from pathlib import Path
from tempfile import TemporaryDirectory
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont
from app import Controller, ConfigStore
from shd_desktop.ui.theme import cyberpunk
app = QApplication([])
app.setFont(QFont("Microsoft YaHei UI", 10))
with TemporaryDirectory() as tmp:
    root = Path(tmp)
    folder = root / 'files'
    folder.mkdir()
    (folder / '示例文档.txt').write_text('demo')
    store = ConfigStore(root / 'config')
    c = Controller(app, store, [folder], enable_hotkeys=False)
    c.open_appearance()
    d = c.appearance_window
    d.skin.setCurrentIndex(1)
    d.preview()
    assert cyberpunk() and c.llm.persona == 'division'
    d.reject()
    assert not cyberpunk()
    c.open_appearance()
    d = c.appearance_window
    d.skin.setCurrentIndex(1)
    d.enabled.setChecked(False)
    c.llm.messages = [{'role':'user','content':'old'}]
    c.llm.response_id = 'old'
    d.save()
    assert c.llm.persona == 'cyberpunk' and '强尼' in c.llm.system_prompt()
    assert not c.llm.messages and c.llm.response_id is None
    assert ConfigStore(store.file.parent).data['skin'] == 'cyberpunk'
    assert '强尼' in c.chat.windowTitle()
    app.processEvents()
    panel = next(iter(c.panels.values()))
    panel.grab().save('tests/skin-cyberpunk.png')
    c.chat.append_message('你', '帮我看看今天的日程。')
    c.chat.append_message('强尼·银手', '先把眼前的事办完。\n日程、便签、音乐——说吧，先处理哪个？')
    html = c.chat.log.toHtml().lower()
    assert '#191b1d' in html and '#35eaf2' in html and '#fcee0a' in html
    assert '#3a3328' not in html and '#38312c' not in html
    c.chat.grab().save('tests/skin-chat.png')
    c.open_appearance()
    d=c.appearance_window
    d.skin.setCurrentIndex(0)
    d.enabled.setChecked(False)
    d.save()
    assert not cyberpunk() and '强尼' not in c.llm.system_prompt()
    assert c.chat.windowTitle().endswith('ISAC')
    c.events.close()
print('skin preview/cancel/save/persona isolation/reversion passed')
