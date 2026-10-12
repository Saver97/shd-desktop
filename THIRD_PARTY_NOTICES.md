# 第三方组件与内网试用提示

本项目 1.0.2 运行包包含下列主要第三方组件，具体锁定版本见封版目录的 `requirements-lock-1.0.2.txt`。此文件记录发布前需要核对的事项，不代替公司的许可审查。

- **PySide6 / Qt for Python 6.11.2**：本次通过 PyPI 社区版构建。其许可选项包括 LGPLv3/GPLv3 和商业许可。公司应按实际使用与分发方式确认合规路径、相关许可文本和组件替换要求。官方资料：<https://doc.qt.io/qtforpython-6.11/commercial/index.html>。
- **QQMusicApi (`qqmusic-api-python`) 0.7.3**：仓库在 v0.7.3 标注 GPLv3 或更高版本，同时在 README 写有“请勿将其用于任何商业用途”。两处表述的关系需要公司确认；本内网试用版仅供公司内部员工试用，不应直接提供给客户或外部合作方。上游源码及说明：<https://github.com/l-1124/QQMusicApi/tree/v0.7.3>、<https://github.com/l-1124/QQMusicApi/blob/v0.7.3/README.md>。
- **PyInstaller 6.22.3**：仅用于构建 EXE；上游说明打包产物可按应用自身许可发布，但仍需遵守被打包依赖的许可。上游许可：<https://github.com/pyinstaller/pyinstaller/blob/develop/doc/license.rst>。

运行包不包含 `docs/design/references` 下的游戏界面参考图片，也不包含开发机的布局、日程、便签、模型密钥、聊天记录或音乐登录凭据。音乐服务与模型 API 由试用者自行登录或配置。
