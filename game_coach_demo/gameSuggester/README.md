# gameSuggester

这个目录对应 `Lesson02_student_worsheet.md` 中的 `game_suggester` 练习项目。当前已先按 worksheet 要求搭好文件结构，并把本节课的任务梳理成可执行清单。

## 目标

- 输入一个房间号
- 读取当前游戏状态
- 给出“下一步建议”

最低输出至少包含：

- 推荐落子位置
- 推荐输入值
- 推荐理由
- 风险提示
- 置信度

## 必须使用的接口

来源：`game_coach_demo/game_coach_game`

1. `GET /api/coach/snapshot/<room_code>`
   用于获取当前对局快照。
2. `POST /api/coach/evaluate_move`
   用于评估某一步是否合法以及可能影响。

说明：worksheet 明确要求建议必须建立在这两个接口之上，不能脱离当前游戏状态单独生成。

## 推荐目录结构

```text
gameSuggester/
├── app.py
├── templates/
│   └── index.html
├── static/
│   └── app.js
├── prompts/
│   └── suggest_prompt.md
├── logs/
│   └── test_log.md
└── README.md
```

## 开发任务拆解

1. 启动 `game_coach_game`，完成登录并进入房间。
2. 编写 suggester 页面或接口。
3. 支持输入房间号并展示建议结果。
4. 获取快照，至少拿到棋盘、当前回合、当前分数。
5. 先生成一个或多个候选建议。
6. 对候选建议调用 `evaluate_move` 做合法性与收益验证。
7. 如果结果不理想，修改 Prompt 或重新生成候选建议。
8. 展示最终建议，并写明理由与风险。

## Prompt 最低要求

1. 角色：游戏建议助手
2. 任务：给出下一步建议
3. 游戏状态：来自 `snapshot`
4. 输出格式：固定字段
5. 展示前必须经过 `evaluate_move` 验证

Prompt 模板已放在 [prompts/suggest_prompt.md](/c:/Users/Computer/Documents/GitHub/CuliuLLMEnginnering/game_coach_demo/gameSuggester/prompts/suggest_prompt.md)。

## 测试与记录要求

至少完成两轮测试：

1. 自测
2. 与其他同学或小组交叉测试

并在 [logs/test_log.md](/c:/Users/Computer/Documents/GitHub/CuliuLLMEnginnering/game_coach_demo/gameSuggester/logs/test_log.md) 中记录：

1. Prompt v1
2. 一次成功结果
3. 至少 2 个失败样例
4. 修改了哪些内容
5. 修改后的结果如何

## 课堂展示与课后任务

课堂展示建议说明：

1. `suggester` 完成了哪些功能
2. 两个教练接口分别如何使用
3. Prompt 的基本写法
4. 遇到了哪些失败情况
5. 优化后发生了哪些变化
6. 在真实对战中是否产生帮助

课后需要补充：

1. 整理代码并提交到 Git 仓库
2. 补充 `README.md`
3. 补充 Prompt 文档
4. 补充测试记录
5. 完成项目第一版内容

## 当前状态

- 已创建 worksheet 对应文件
- 已提供任务梳理页面：运行 `python app.py` 后访问 `http://127.0.0.1:5050`
- 尚未接入真实的 `snapshot` / `evaluate_move` 调用逻辑
