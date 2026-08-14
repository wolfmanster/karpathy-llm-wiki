# Zotero–MinerU 同步集成

这是外层仓库中的独立集成组件，不修改 `MinerU-GUI` 上游子模块。

组件包括：

- `zotero_mineru_sync/`：一次性 `zotero-mineru-sync` Python 命令、协议、校验、锁和 SQLite 状态。
- `zotero-plugin/`：Zotero bootstrap 插件及纯 JavaScript 适配层。

最终用户的默认运行数据位于 `%LOCALAPPDATA%\ZoteroMinerU`。开发和测试不得使用该默认目录，
所有测试数据固定写入项目内的 `.testdata/`（该目录已被 Git 忽略）。

示例：

```powershell
Set-Location zotero-mineru-sync
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .
.\.venv\Scripts\python -m zotero_mineru_sync .testdata\requests\request.json --data-root .testdata\runtime
```

插件设置中的同步命令应指向项目内虚拟环境生成的
`.venv\Scripts\zotero-mineru-sync.exe`。测试不得向项目目录外创建脚本、数据库、profile、日志或归档。
