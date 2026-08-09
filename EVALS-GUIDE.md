# LLMOps 评测接入 — 交接清单(给网站 agent)

目的:给 findability-api 接上**具名 LLMOps 工具**的真实用例,让简历上的
"Ragas / 评测" 关键词有可验证载体。产出的核心是**数字**(检索命中率、
faithfulness 等),它们会变成简历 bullet——所以每个数字都要可复现。

铁律沿用 HANDOFF.md:实测为准、key 只经 --env-file(GEMINI 在 belt-api/.env,
ANTHROPIC 在 leaselens-service/.env)、任何输出/git 文件不见 key 明文、
PROGRESS.md 落盘。本仓库(findability-api)是你的,直接 commit main。

## 任务一:golden set(评测数据集)

- [ ] `evals/golden.jsonl`:25–30 条,每条 {question, reference_answer,
      expected_citations:[node ids]}。问题从 corpus.json 的真实内容出发
      (作品、角色、方法、技术栈),覆盖:直答型 / 跨项目关联型 / 语料外
      应拒答型(expected_citations 为空,reference = 拒答)≥5 条 / 中文问题 ≥3 条
- [ ] reference_answer 只依据 corpus 写,不引入外部事实;写完整体过一遍
      标注在 PROGRESS(Jerry 可抽查)

## 任务二:检索指标(无 LLM 判官,先跑这个)

- [ ] `evals/run_retrieval.py`:对每条 golden 的 question 做 embedding →
      Chroma top-k → 计算 **hit-rate@3 / hit-rate@5 / MRR**(expected_citations
      是否被召回及排名)
- [ ] 输出 `evals/report-retrieval.md`(总表 + 逐条明细);基线数字记入 PROGRESS

## 任务三:Ragas(具名工具主菜)

- [ ] `evals/run_ragas.py`:对每条 golden 走真实 /ask 管线(或内部函数),
      收集 answer + retrieved contexts → **Ragas** 算 faithfulness、
      answer_relevancy、context_precision、context_recall
- [ ] Ragas 的判官 LLM 用现有 key 配(langchain-anthropic 或
      langchain-google-genai 包装;**不开任何新账号**);judge 模型选便宜档,
      单次全量运行成本控制在几美元内,跑前在 PROGRESS 估一笔账
- [ ] 拒答型条目单独统计:应拒答的是否真拒了(拒答正确率)
- [ ] 输出 `evals/report-ragas.md`:每指标均值 + 最差 3 条的逐条分析
- [ ] **如指标暴露真实问题**(如某类问题 faithfulness 低):修 prompt 或检索参数
      (k、阈值),重跑,记录 before → after——这个 delta 是简历最想要的东西;
      如基线本来就高,如实记录(13 节点小语料,高是正常的,别硬修)

## 任务四(可选加分,按此优先级)

- [ ] **评测进 CI**:golden 问题的 query embeddings 离线预计算存进仓库
      (`evals/golden-embeddings.json`)→ GitHub Actions workflow 在 push 时
      跑纯向量数学的检索指标(**零 key、零成本**),指标跌破阈值则 fail。
      这一步同时强化 CI/CD 叙事
- [ ] **Tracing**:优先 **Arize Phoenix**(开源本地起,OTel 接入,无需新账号)
      给 /ask 管线加 trace,截图存 evals/;若 Jerry 主动提供 LangSmith 账号 key
      则改接 LangSmith(**不许代注册账号**,铁律)

## 完成报告(给 Jerry,转简历会话)

- 数字包:golden set 规模、hit-rate@3/@5、MRR、四项 Ragas 均值、拒答正确率、
  (如有)before→after delta、(如有)CI 状态徽章 & Phoenix 截图路径
- 一句话口径素材:每个工具在这个系统里实际干了什么
- 简历措辞由简历会话决定,报告只给事实
