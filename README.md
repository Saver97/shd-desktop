# SHD Desktop

适用于 Windows 10/11 x64 的桌面整理与日常助手。将桌面图标放进可折叠分框，集中管理日程、便签、天气和音乐，并通过 ISAC 或强尼·银手对话执行日常操作。支持全境封锁与赛博朋克 2077 两套可切换皮肤。

当前源码版本：**1.0.11**。

## 下载与启动

从 [1.0.11 Release](https://github.com/Saver97/shd-desktop/releases/tag/v1.0.11) 下载 **SHDDesktop-1.0.11.exe**，包含双皮肤、自定义标题栏和桌面右键子菜单。也可按下方步骤从源码运行或构建。

单文件版放在固定目录后双击运行，无需安装 Python；首次启动会在当前用户的 `%LOCALAPPDATA%\SHDDesktop\Runtime` 缓存运行组件。

升级时先从托盘选择“退出 SHD Desktop”，再启动新版本，让已整理的桌面图标正常恢复。新版在桌面空白处右键的 **SHD Desktop** 子菜单中提供“打开终端”“新建便签”“一键整理桌面”。Windows 11 可能需要先点“显示更多选项”。

## 功能

| 模块 | 可以做什么 |
| --- | --- |
| 桌面分框 | 新建多个分框，拖动、缩放、折叠和吸附；图标支持 Windows 文件右键菜单及 Delete 键删除到回收站；按文件类型一键整理，保存并切换场景，撤销整理操作 |
| 日程与便签 | 创建提醒、批量管理日程；便签支持富文本右键编辑、颜色、透明度、置顶、锁定、提醒、分组和回收区 |
| ISAC / 强尼·银手 | 随皮肤切换助手人设，在独立窗口对话；保存多个 API 配置与模型，支持 Chat Completions / Responses，并可调用日程、便签、天气、分框和音乐功能 |
| 天气 | 保存多个地区并切换，查看天气图标与未来四天预报 |
| QQ 音乐 | 搜索歌曲和歌单、扫码登录、播放与续播；可用内容受账号和版权权限限制 |
| 皮肤与窗口 | 全境封锁烟黑橙 / 2077 黄黑青；配套图标、界面文案与自定义标题栏；支持预览、取消和保存 |
| Windows 集成 | 托盘、桌面右键子菜单、日程／天气／音乐桌面组件显隐开关、可选开机启动、全局快捷查找和单实例运行 |

### 桌面整理的两种分框

- **桌面整理分框**只管理图标的显示与位置，不移动桌面文件。隐藏分框或正常退出程序后，图标会回到 Windows 桌面。
- **文件夹分框**关联实际目录；拖入文件会移动到该目录，同名目标会跳过，不覆盖。
- 拖回桌面可取消图标分组；一键整理只处理尚未分组的桌面项目。若 Windows 开启“自动排列图标”，图标恢复后可能无法回到原先的精确坐标。

## 皮肤与助手

在控制台打开 **设置 → 外观与快捷键 → 皮肤与助手**：

| 皮肤 | 视觉与界面 | 助手与称呼 |
| --- | --- | --- |
| 全境封锁 | 烟黑底、橙色状态线、白色标题，保留原版图标与文案 | ISAC，称呼用户为 **Agent** |
| 赛博朋克 2077 | 亮黄切角边框、深色底板、青色反馈与机械图标；委托日志、神经链路等主题文案 | 强尼·银手，称呼用户为 **V** |

修改时即时预览，取消可恢复；保存后下次启动沿用。保存人设切换会中断当前回复并开启新对话，模型配置和用户数据保留。模型需自行配置 API 地址、密钥与模型名。

控制台和模型配置窗口采用配套标题栏，提供最小化、关闭、双击最大化与还原，并接入系统拖动和边缘缩放。外观设置还可调整底板不透明度、字号、分框图标尺寸和快速查找快捷键。

### 整理与删除

- 桌面右键 → **SHD Desktop → 一键整理桌面**：按类型将尚未分组的项目归入虚拟分框，程序未运行时会自动启动。
- 分框内选中项目后，右键选择“删除到回收站”或按 **Delete**，支持多选与确认。取消或失败会保留分组。
- 删除快捷方式只删除快捷方式；删除实际文件或目录会操作对应项目。便签回收区与 Windows 文件回收站相互独立。

## 数据与恢复

布局、日程、便签、模型配置和音乐状态保存在当前用户的 `%LOCALAPPDATA%\SHDDesktop`，不会打入发布包。密钥和音乐登录凭据使用 Windows DPAPI 保存。程序会维护布局备份；异常退出后再次启动会尝试恢复桌面图标。

若程序无法正常打开，可在 PowerShell 中运行：

```powershell
.\SHDDesktop-1.0.11.exe --restore-desktop-icons
```

详细改动见 [发布记录](RELEASE_NOTES.md)。

## 源码结构

| 路径 | 内容 |
| --- | --- |
| `app.py` | Python 入口与桌面面板控制器 |
| `shd_desktop/desktop`、`shd_desktop/integration` | 图标整理、场景、Windows 右键、热键与启动集成 |
| `shd_desktop/ai`、`shd_desktop/music`、`shd_desktop/notes` | 助手人设与模型调用、播放器与便签 |
| `shd_desktop/ui`、`shd_desktop/data` | 控制台、外观、日程与天气 |
| `assets`、`tests`、`tools`、`packaging`、`docs` | 资源、测试、辅助脚本、打包和文档 |

更多说明见 [架构文档](docs/ARCHITECTURE.md) 和 [产品设计](docs/产品设计.md)。

## 从源码运行

在 Windows PowerShell 中执行：

```powershell
git clone https://github.com/Saver97/shd-desktop.git
cd shd-desktop
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

运行回归检查：

```powershell
.\.venv\Scripts\python.exe tools\run_tests.py
```

构建单文件 EXE：

```powershell
python -m venv .venv-release
.\.venv-release\Scripts\python.exe -m pip install -r requirements-build.txt
.\build.ps1
```

构建结果位于 `release-candidate/1.0.11`。公开下载采用单文件 EXE；当前本地封版的 SHA256 见 [封版基准](docs/design/封版基准.md)。

## 使用说明

QQ 音乐接口依赖社区项目，登录、限流和播放权限由服务端决定。Windows 10 实机、显示器热插拔及 Explorer 重启后的行为仍需在试用设备上复核。第三方组件及用途限制见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。本仓库暂未为项目源码设置许可证。
