# `state` — `state.db` 的唯一写入者

承载 `legacy/transcript/src/transcript/store.py`。**全仓只有本包可以 `import sqlite3`**
（由 import-linter 契约强制），这是「仓储层收敛」从口号变成事实的那一步。

## 设计要点

- **分片是续跑单位**：任何一片落盘后进程被杀，重启都从已完成的分片接着跑。
- 每次调用开一个短连接（WAL 模式），避免线程池里的连接共享问题。
- **这里永远不存密钥**，只存路径、状态和度量；`update_task` 的字段白名单是第二道门。
- `schema` 不重建：沿用现有三张表 + 一个索引，启动时只做幂等加列迁移。

## 生命周期

- 终态集合恰好是 `{done, failed}`；`pending` / `running` / `cancelling` 都是非终态。
- `running_task_ids()` 给服务端判断「运行中但无实时进程」用 —— 前端不再自行推断。
- `update_task` 只接受白名单字段；`status` 只接受五个合法值，写错直接报错。
