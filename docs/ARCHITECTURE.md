# 源码结构

`app.py` 是唯一的 Python 程序入口，负责启动 Qt、建立单实例通道以及装配桌面面板、控制台和托盘。功能代码位于 `shd_desktop/`，按用户能看到的模块和系统边界分组：

- `desktop/`：桌面图标分组、位置、吸附、场景与屏幕变化恢复。
- `integration/`：Windows 桌面右键、开机启动、全局热键和单实例转发。
- `ai/`：ISAC 聊天窗口、模型配置与受限工具调用。
- `music/`、`notes/`：播放器和便签。
- `ui/`：控制台、外观、天气图形与快速查找。
- `data/`：日程存储和天气客户端。
- `resources.py`：源码运行和打包运行共用的资源路径。

`assets/` 存放本项目图标，`tests/` 是可逐项运行的回归脚本，`tools/` 是测试入口、图标生成与性能脚本，`packaging/` 存放 PyInstaller 规格、单文件启动器与封版脚本，`docs/design/` 保存设计与历史验证记录。

## 运行与验证

从仓库根目录运行 `python app.py`。使用 `python tools/run_tests.py` 执行全部回归脚本；也可用 `python -m tests.test_notes` 单独执行。测试用临时目录保存用户数据，截图生成在 `tests/` 并由 Git 忽略。`build.ps1` 构建单文件 EXE；其输出目录由 Git 忽略。

公开发布仅保留 `v1.0.4` 标签和单文件 EXE；此前的开发过程仍可从 Git 提交历史追溯。
