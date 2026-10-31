from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from shd_desktop.integration.recycle import recycle_items
from shd_desktop.desktop.desktop_groups import DesktopGroups, file_attributes, HIDE_BITS, set_visibility


class Store:
    def save(self):
        pass


with TemporaryDirectory() as temp:
    root = Path(temp)
    path = root / 'delete.txt'
    panel = {'kind': 'virtual', 'items': [{'path': str(path), 'original_bits': 0}]}
    store = Store()
    store.data = {'panels': [panel]}
    groups = DesktopGroups(store, [root], positions=object())
    path.write_text('test')
    set_visibility(path, None)
    with patch('shd_desktop.integration.recycle.shell.SHFileOperation', return_value=(0, True)):
        assert not recycle_items([path], 0, groups, panel)
    assert path.exists() and file_attributes(path) & HIDE_BITS == HIDE_BITS
    assert len(panel['items']) == 1
    with patch('shd_desktop.integration.recycle.shell.SHFileOperation', return_value=(5, False)):
        assert recycle_items([path], 0, groups, panel)
    assert path.exists() and file_attributes(path) & HIDE_BITS == HIDE_BITS
    def deleted(*args):
        assert not file_attributes(path) & HIDE_BITS
        path.unlink()
        return 0, False
    with patch('shd_desktop.integration.recycle.shell.SHFileOperation', side_effect=deleted):
        assert not recycle_items([path], 0, groups, panel)
    assert not panel['items']
print('recycle: cancellation, failure and successful group cleanup passed')
