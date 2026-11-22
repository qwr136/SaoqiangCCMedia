# SaoqiangCCMedia 构建兼容修复

## 基线
- 用户提供 `SaoqiangCCMedia-3.1415926-source.zip`；完整逐文件 SHA256/git blob 清单见 `upstream-source.json`。
- 原源码仅以归档身份确认，未提供上游 Git commit。`VALIDATION.txt` 是上游历史说明，其 deb 哈希不同于此次崩溃包，不冒充本轮验证。
- 原作：Saoqiang；构建修复维护：Xiaofei。沿用已发布包 `com.saoqiang.ccmedia`、面板/六模块 bundle ID、SQCCM 类名和配置域，避免升级变成另一插件。新项目的 com.minis 命名规则不用于破坏已有包身份。
- 原配置和媒体路径/兼容行为保持，不顺手迁移用户数据。`Shared`、`Module/SQCCMModule.m`、`Preferences/SQCCMPreferences.m` 以及原资源逐字冻结。

## 可证故障及修复范围
原故障包的面板在首个分组标题 `控制中心视频模块 3.1415926` 的 retain 路径异常。其 arm64e CFString 类指针使用未认证绑定；寄存器符合系统 ISA 认证路径。源码 `specifiers` 使用静态 NSString 常量，没有发现该调用点的提前释放。原构建入口使用可替换的 Linux LLVM19/ld 组合，原验库只查 CPU subtype 与“存在签名”，未检查 CFString ISA 认证契约。

修复路径：所有七个 bundle 统一交由固定 RootHide Theos / SDK、受控 Apple Xcode 16.4 编译链接；在实际 deb 二进制上强制验证所有 CFString ISA 的 DA key、address diversity 与 0x6ae1 discriminator，以及真实签名页哈希。仅改标题、改架构标签或重签名不算修复。

保留原 `.m/.h` 行为，废弃分阶段 Linux 发布入口（原实现仅留 `legacy-build-native.py.txt` 供追溯）。补全 `roothide` 依赖；本包是 ControlCenter/PreferenceBundle，不是注入 dylib，不为凑模板额外添加 Substrate Hook。

## 版本
Debian 修订从故障包 `3.1415926-1` 升级为 `3.1415926-2`，上游功能版本/面板标题仍为 `3.1415926`。不把新仓库首次 run 号变成 0.10 而降级原包。

## 验证边界
1. 源码/包门禁：测试测试器的拒绝路径，生产代码冻结及资源身份。
2. Apple 真实编译 + 实际 deb 的七个 arm64e 二进制、依赖、CFString ISA、签名核验。
3. iOS Simulator 真实 UIKit + Preferences 测试替身：执行实际生产面板源码的构造/配置/单元复用；不是 iOS16 真机私有 Preferences，也不模拟 PAC 硬件认证。
4. 最终用户设备：仍需在原 RootHide/iOS16.5 点开面板和六模块验证；静态认证正确与模拟器通过不等于设备已验收。

原始 crash/设备标识、用户媒体、密钥或令牌不进入公开仓库；无自动 Release/tag。
