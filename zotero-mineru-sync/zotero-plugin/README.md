# Zotero 插件组件

`bootstrap.js` 是 Zotero 7 官方 bootstrap 生命周期入口；它通过 `loadSubScript()` 加载 `runtime.js`。`src/` 中的重复集合、防抖、请求构造和设置模块不依赖 Zotero，可单独测试。

插件只处理个人库顶层文献的 PDF 子附件，解析配置固定为 `pipeline + CPU`；可在设置页指定 CPU 线程数，0 表示沿用 MinerU 默认值。启用时做一次全库扫描，后续由 Zotero 通知触发 15 秒 trailing debounce。请求文件先写入临时文件，再原子移动到 `requests/`；同步子进程退出后才释放运行状态。

安装时将此目录打包为 `.xpi`（目录内容位于压缩包根部），在 Zotero 的 Tools → Plugins 中安装，然后在 Zotero Preferences → Zotero–MinerU 中填写项目内虚拟环境生成的 `zotero-mineru-sync` 可执行文件路径。Python 组件必须安装在本项目内的虚拟环境中：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .
```

开发和测试阶段的请求、结果、SQLite 状态、日志和归档统一放在项目内 `.testdata/`；最终用户未显式配置时才使用 `%LOCALAPPDATA%\ZoteroMinerU`。
