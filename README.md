# dsh-preset-book-translator（书籍翻译模式）

DeepSeek Harness (dsh 0.2.x) 的自定义 Agent 模式：分块整书翻译，
带跨会话持久术语表与记忆胶囊。

## 安装

    dsh plugin --profile web add file:<本目录的完整路径>

（或把本目录推到 GitHub 后让别人执行 `dsh plugin --profile web add github:<用户名>/dsh-preset-book-translator`）

安装后重启 `dsh web`，模式选择器里会出现"书籍翻译模式"。

## 脚本自动部署

本插件包内置 `scripts/` 子目录，包含五个 Python 工具：
verify-chunk.py、apply-edits.py、glossary-append.py、scan-consistency.py、export-full.py。

翻译 Agent 在首次处理新工作区时会自动从包安装路径复制这些脚本到工作区根目录（即 `books/` 所在目录）。无需手动操作。

如需手动部署：把 `scripts/*.py` 复制到你的工作区根目录即可。
