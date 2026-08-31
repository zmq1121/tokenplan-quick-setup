# tokenplan-setup (npm)

腾讯云 Token Plan 一键接入 CLI 的 npm 分发入口。

## 使用

```bash
npx tokenplan-setup            # 交互式安装
npx tokenplan-setup doctor     # 环境诊断（只读）
npx tokenplan-setup uninstall  # 还原配置
```

## 工作原理

npm 包内只有两个东西：

- `bin/tokenplan-setup.js` — Node 入口，检测 Python 3 后 spawn 主脚本，透传参数与退出码
- `lib/setup.command` — 安装器主逻辑（单文件 Python 脚本，与仓库根目录的 `setup.command` 完全一致）

主逻辑零依赖（纯 Python 标准库），Node wrapper 零 npm 依赖。

## 构建与发布

```bash
cd npm
cp ../setup.command lib/setup.command   # 同步主脚本
npm pack                                # 本地验证
npm publish                             # 发布（需先在 npmjs.com 注册包名）
```

发布前务必执行 `cp ../setup.command lib/setup.command`，确保 `lib/` 里是最新主脚本。

## 版本策略

主脚本每次有意义变更（新工具/新套餐/修复）时升一个版本：

- 补丁修复：0.0.x
- 新工具/新功能：0.x.0
