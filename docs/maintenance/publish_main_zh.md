# 按当前工作区与 `.gitignore` 覆盖远端 main

目标仓库：`git@github.com:LUIGIVAMPER/topogym.git`。

以下操作将远端 `main` 的文件树替换为当前 TopoGym 工作区中 Git 未忽略的文件，包含新增、修改和删除。
它保留当前开发分支的提交历史，并在本地备份发布前的远端 `main`；不会清空整个 Git 历史或删除其他远端分支。
原 `main` 独有的提交可能不再属于新 `main` 的祖先，但仍可从备份分支找回。

`.gitignore` 只影响未跟踪文件。仅运行 `git add .` 不会取消已跟踪文件；这里先清空索引，再按当前忽略规则重新加入。
`git rm --cached` 只移除索引记录，磁盘上的代码、运行结果和被忽略文件都保留。

## 1. 准备提交

在同一个 Bash 终端顺序运行。`set -euo pipefail` 使失败时停止，避免 fetch 失败后仍继续发布。
准备阶段不执行远端写入；从当前分支新建发布分支，无需先切换到旧 `main`。

```bash
set -euo pipefail
cd /home/jianwen/topogym

git remote -v
git fetch origin refs/heads/main
TOPOGYM_REMOTE_MAIN="$(git rev-parse FETCH_HEAD)"
TOPOGYM_PUBLISH_STAMP="$(date +%Y%m%d-%H%M%S)"
TOPOGYM_MAIN_BACKUP="backup/main-before-topogym-$TOPOGYM_PUBLISH_STAMP"

# 保留实际读取到的远端 main；后面的 lease 使用同一个提交。
git branch "$TOPOGYM_MAIN_BACKUP" "$TOPOGYM_REMOTE_MAIN"
git switch -c "publish/topogym-$TOPOGYM_PUBLISH_STAMP"

# 按当前磁盘内容重建索引；不删除工作区文件，不使用 git clean。
git rm -r --cached .
git add -A

# 应无输出：新的索引中不再包含被忽略文件。
test -z "$(git ls-files -ci --exclude-standard)"

# 查看相对远端 main 的完整变化，再检查暂存内容。
git diff --cached "$TOPOGYM_REMOTE_MAIN" --stat
git diff --cached --check
git status --short
```

确认暂存内容后，在同一个终端提交：

```bash
git commit -m "Publish current TopoGym simulator and Harbor benchmark"
```

如果 `git rm --cached` 因已有暂存内容与磁盘、HEAD 都不一致而拒绝操作，先保存那份仅存在于索引中的内容，
再处理；不要直接用强制参数丢掉它。本方案以当前磁盘文件为发布内容，不保留原来的部分暂存选择。
准备期间也应避免另一个会话修改要发布的文件。

## 2. 推送到远端 main

继续在同一终端运行，复用准备阶段的变量：

```bash
git push \
  --force-with-lease="refs/heads/main:$TOPOGYM_REMOTE_MAIN" \
  origin HEAD:refs/heads/main

# 拉取并核对远端文件树与刚发布的提交一致；无差异时不输出。
git fetch origin refs/heads/main
git diff --exit-code HEAD FETCH_HEAD
```

`HEAD:refs/heads/main` 明确将当前发布分支写入远端 `main`，不会误推到 `fem-ipc-migration`。
精确指定旧提交的 `--force-with-lease` 只允许替换刚刚读取到的远端状态；如果期间别人更新了 `main`，推送会拒绝。
遇到 lease 拒绝应先查看新增提交，不要换成 `--force`。如果启用了禁止强制推送的分支保护，需要按仓库规则处理。

本地原开发分支与本地 `main` 的指针不变；发布提交在新建的 `publish/topogym-<时间>` 分支上。
备份分支只在本地；如需另外在 GitHub 保留备份，可执行：

```bash
git push origin "$TOPOGYM_MAIN_BACKUP:$TOPOGYM_MAIN_BACKUP"
```

## 3. 当前忽略范围与文档验证

当前 `.gitignore` 排除虚拟环境、缓存、`.env` / `.secrets/`、`jobs/`、`exps/`、`runs/`、
`task_rollouts/`、旧生成任务和完整证明 evidence 等产物；保留 `.env.example`、当前 `tasks/`、
`demos/**/*.mp4`、源码/配置/文档及 `legacy/` 中未被单独忽略的归档源码。
因此这次发布也会包含正式 demo 视频与归档源码。

2026-09-29 文档修改前的只读盘点：约 6,403 个可发布文件，合计 1.55 GB，最大文件约 52.92 MiB，
没有超过 100 MiB 的当前文件。这里没有计算旧提交历史中的 blob；实际上传体积还取决于远端已有对象与压缩。
忽略规则不会从历史提交中抹除文件。

Harbor 静态检查（不运行物理或模型）：

```bash
source .venv-harbor/bin/activate
bash ci_checks/run_all.sh
```

这些 Git 指令是发布操作说明。编写文档时未切换分支、重建实际索引、创建提交或推送；
当时 `git ls-remote` 因 GitHub DNS 解析失败，未取得远端最新状态，因此实际发布前必须成功执行 fetch。
