日期：2026-10-17
裁定来源：MODERNIZATION_BRIEF.md §7c Q12（「按建议删」）

## 已删除

| 路径 | 文件数 | 字节 | 恢复方式 |
|---|---|---|---|
| `src/transcript/web/static/workbench` | 13 | 204K | `git checkout HEAD -- src/transcript/web/static/workbench` |
| `spikes/workbench/.baseline` | 21 | 336K | `git checkout HEAD -- spikes/workbench/.baseline` |

两个目录都已受 git 跟踪（34 个文件），删除可完整恢复。

## 保留

`spikes/workbench/` 的其余部分（README、ABLATION、src、tools）保留为研究产物 ——
README 与 ABLATION 是这套实验的记录，.baseline 只是它用于打印行数表的第三份拷贝。

## 删除理由

- `src/transcript/web/static/workbench/`：13 文件 4,233 行，与 `spikes/workbench/src`+styles
  字节相同，但**没有任何路由挂载它**（`app.mount` 只暴露 `static/dist`），
`pyproject.toml` 也把它排除在 wheel 之外 —— 既不服务也不打包。
- `spikes/workbench/.baseline/`：同一份内容的第三份拷贝，只用于 ABLATION.md 的行数表。

## 复现的核验

```
# 全仓搜索引用（排除 legacy 快照与两份拷贝自身）：无命中
grep -rn 'static/workbench' --include='*.py' --include='*.ts' --include='*.tsx' \
     --include='*.js' --include='*.html' --include='*.toml' . | grep -v node_modules
# → 空
```
