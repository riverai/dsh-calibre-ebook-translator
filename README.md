# dsh-preset-book-translator（书籍翻译模式）

DeepSeek Harness (dsh 0.2.x) 的自定义 Agent 模式：分块整书翻译，
带跨会话持久术语表与记忆胶囊。

## 安装

    dsh plugin --profile web add file:<本目录的完整路径>

（或把本目录推到 GitHub 后让别人执行 `dsh plugin --profile web add github:<用户名>/dsh-preset-book-translator`）

安装后重启 `dsh web`，模式选择器里会出现"书籍翻译模式"。
