# 控制中心视频模块 3.1415926-2 构建兼容修复

原作 Saoqiang，构建兼容修复维护 Xiaofei。原功能源码与资源不改，修复范围和验证分层见 [docs/repair.md](docs/repair.md)。

面向 iOS 16.5 RootHide。依赖 RootHide、CCSupport 与 PreferenceLoader。保持包名 `com.saoqiang.ccmedia`，从本次故障包 `3.1415926-1` 升级；旧配置归到模块 1。上游说明曾写“可从 5.2.0 升级”，但 Debian 版本排序不支持该说法，本修订不作此承诺。

## 使用

1. 安装 RootHide DEB 后重启 SpringBoard。
2. 在「设置 → 控制中心」分别添加「骚强媒体 1」至「骚强媒体 6」中需要的模块。
3. 在「设置 → 控制中心视频模块」进入对应编号，设置媒体、尺寸和透明度。支持从相册或文件导入，视频默认静音循环，关闭控制中心或熄屏时暂停。
4. 长（水平方向）与宽（垂直方向）分别为 1–4 格，共十六种组合，旧版尺寸保留。大尺寸实际排布受设备和 CCSupport 影响。
5. 点击媒体区域打开全屏预览，再点素材或空白处任意位置返回。旧版控制中心私有展开路径已停用；此处为新实现，需真机确认。每个配置页新增「模块圆角」0–60pt，默认22pt，只裁剪卡片，不裁剪全屏。
6. 设置页按参考的分组和控件排列重做。小组件提供原创数字时钟/日期，iDevice 风格为圆角黑边，未复制参考插件完整 HTML 小组件系统。内容模式、边距、像素风格、声音与不透明度均有运行时代码支持。本版移除卡片播放暂停按钮及底部标签，视频可见时自动循环；全屏复用原播放器并无动画返回。尺寸写入后主动通知 CCSupport 刷新，透明度单元隐藏系统标题避免叠字。其他模块文字变形原因尚未复现，不能声称已修复。
7. 若视频仍失败，保留错误截图（含错误域和代码），注明相册还是文件导入、是导入时失败还是卡片播放时失败。

## 构建

工程包含六个模块、一个偏好设置 bundle。公开仓库 Actions 使用 `toolchain-lock.json` 固定的 RootHide Theos/SDK 与兼容范围内 Apple Xcode 16.4；入口为 `sh build.sh roothide`。原自定义 Linux 分阶段编译入口已停用并归档，不能再用它发布此修复。

本地预检：`python3 scripts/toolchain.py static && python3 tests/run_tests.py -v`。macOS 构建先按锁准备工具，再运行 `python3 scripts/toolchain.py select-xcode`、`prepare`、`verify`。实际 deb 必须通过七个 arm64e bundle 的 CFString ISA PAC、代码页签名、依赖、资源和版本门禁。最低 iOS15，SDK目录16.5/实际metadata16.4。UIKit测试运行的是生产面板源码与测试专用Preferences替身，不代替目标设备PAC/私有框架验收。Actions仅上传artifact，不自动建tag/Release。

视频处理通过导入时保留文件容器和临时文件有效期，以及在进程内读取 RootHide 文件向 AVFoundation 提供数据来处理可能的路径/权限兼容问题。视频导入与播放、系统列表排布、生命周期均需在目标真机复测；本地构建不能代替这些测试。
