# 一代悬浮 HUD 视觉调整

参考：Piotr Michalczyk 的《Tom Clancy's The DIVISION (User Interface)》作品。

- 原作页面：https://www.behance.net/gallery/45621303/Tom-Clancys-The-DIVISION-%28User-Interface%29
- 参考截图：references/division1-inventory-reference.webp
- 图片链接：https://mir-s3-cdn-cf.behance.net/project_modules/fs_webp/2975d545621303.583805eb79561.png

从截图中采用的布局特征：透明烟黑条带、无完整外框、较大且轻的白色标题、细分隔线、橙色活动状态和数值、小号操作提示。参考截图仅用于项目设计研究，不打入应用程序。

实现：桌面分框的整理操作进入文字“管理”菜单；展开和折叠保留直接入口，折叠后仍可管理。目录路径进入管理按钮提示。保留图标位图缓存和既有吸附逻辑。

桌面适配：文件图标和名称保持真实内容与正常比例；不加入透视倾斜、实时模糊、扫描动画，以维持拖动和展开的响应速度。
