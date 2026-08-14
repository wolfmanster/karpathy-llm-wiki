# Zotero–MinerU 同步集成

这是外层仓库中的独立集成组件，不修改 `MinerU-GUI` 上游子模块。

组件包括：

- `zotero_mineru_sync/`：一次性 `zotero-mineru-sync` Python 命令、协议、校验、锁和 SQLite 状态。
- `zotero-plugin/`：Zotero bootstrap 插件及纯 JavaScript 适配层。

所有运行数据必须位于本组件目录中。命令行未指定 `--data-root` 时使用
`zotero-mineru-sync/runtime/`；在 Zotero 插件中必须显式设置这个项目内目录，插件不会写入
`%LOCALAPPDATA%`、Zotero 数据目录或其他用户目录。开发和测试数据固定写入项目内的
`.testdata/`（该目录已被 Git 忽略）。

示例：

```powershell
Set-Location MinerU-GUI
python -m venv .venv
.\.venv\Scripts\python -m pip install -e '.[mineru]'
.\.venv\Scripts\python -m pip install -e ..\zotero-mineru-sync
.\.venv\Scripts\python -m zotero_mineru_sync ..\zotero-mineru-sync\.testdata\requests\request.json --data-root ..\zotero-mineru-sync\.testdata\runtime
```

插件设置中的同步命令应指向 `MinerU-GUI\.venv\Scripts\zotero-mineru-sync.exe`，输出根目录应设为
`zotero-mineru-sync\runtime`（或另一个本组件内的目录）。测试不得向项目目录外创建脚本、数据库、profile、日志或归档。
