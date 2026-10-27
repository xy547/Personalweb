# 外刊精读教练（ReadCoach）

**一句话**：每天推送一篇英语 / 日语 / 法语 / 德语 / 西语新闻，智能体自己查词、按该语种的等级体系分级、
生成一份 CSV 词表 + Word 笔记，并产出一份原文挖空的精读练习页。

**路径**：A —— 技术栈完整的智能体应用

---

## 一、解决什么问题

**用户**：正在学第二外语的中国大学生——备考 CET-6 / 雅思的，也考 JLPT / DELF / Goethe / DELE 的
（我自己就是这类用户：外刊读得慢，生词查完就忘，坚持不下来）。

**现在的痛点**：做完一篇外刊精读，通常要做四件互不相干的事——查生词、按考纲筛词、抄进背单词软件、再手写一张练习页。四件事散落在四个软件里，一次要花掉四十分钟，而且很难坚持。

**这个项目做的事**：把这四步收进一句话里。用户只需要把原文贴进来，剩下的规划由 Agent 完成，最后交出来的是两份能直接用的文件。

**闭环**：每日推送（首页卡片 + 连续打卡）→ 输入（推送的那篇 / 自己贴的 / 内置示例）→ 规划（挑词、查词、分级）
→ 执行（调用 7 个工具）→ 交付（CSV + Word + HTML 落在 `outputs/`）→ 回写（错词进档案，按 SM-2 排下次复习日期）。

---

## 二、技术栈

| 层次 | 选型 | 说明 |
|---|---|---|
| 模型 | 阿里百炼 `qwen-plus` | 走 OpenAI 兼容端点，换模型只改环境变量 |
| Agent 框架 | **LangGraph**（开源） | `StateGraph` 实现 agent ⇄ tools 循环，`ToolNode` 托管工具执行 |
| 模型接入 | `langchain-openai` | 用 `ChatOpenAI` + `base_url` 指向百炼兼容端点 |
| 界面 | **Streamlit** | 工具调用过程用 `st.status` 实时展开 |
| 工具 | 7 个自定义工具（`@tool`） | 见下表 |
| Skill | 1 个（`skills/intensive-reading/`） | `SKILL.md` + `template.html`，按触发词加载 |
| 记忆 | `data/learner_profile.json` | 错词本 + 复习区间（interval / ease / due）+ 打卡日期，每轮拼进系统提示词 |
| 多语种 | `agent/languages.py` | 一份注册表管 5 个语种：等级体系、注音形态、词库覆盖、词形规矩、新闻源 |
| 每日推送 | `tools/daily.py` | 当天缓存 → 联网抓（新华网多语种版）→ 离线快照，三级回落；连续天数按日期算 |
| 配置 | `python-dotenv` | `.env` + `.env.example`，真值不入库 |

### 七个工具

| 工具 | 文件 | 解决的问题 |
|---|---|---|
| `load_text` | `tools/reader.py` | 读**用户自己贴的**文章（界面粘贴框 → 固定槽位 `data/current_article.txt`）。**没有路径参数**，所以越权没有落点 |
| `read_article` | `tools/reader.py` | 读整篇文章，两个来源：`source="demo"` 读 `demo/` 里的示例（**只读 `demo/`**，挡住 `../.env`）、`source="daily"` 读今天推送的那篇（带标题/来源/链接/抓取方式，并写进文章槽） |
| `lookup_word` | `tools/dictionary.py` | 从本地 6161 词词库（高考 / 四级 / 六级）查音标、词性、释义、例句、等级；先还原词形（`consolidates → consolidate`）再试英美拼写变体；查不到时返回 `NOT_FOUND` 而不是猜 |
| `make_wordlist_csv` | `tools/wordlist.py` | 生成 `utf-8-sig` 编码的 CSV；**写盘前用词库复核**音标、词性、释义、等级，未收录的词强制标「未收录」、音标留空。非英语语种走另一条路：注音由模型给（entries 第 6 字段），全部标「模型推断」 |
| `build_worksheet_html` | `tools/worksheet.py` | 用模板生成练习页，并自动把目标词（含 `emissions`/`mitigated` 这类变形）在原文中挖空 |
| `build_vocab_doc` | `tools/vocabdoc.py` | 把词表 CSV 排成 `.docx`：逐词分块，序号 / 单词 / 音标 / 词性+释义 / 用法 分行排列，可打印、可继续在 Word 里改。**只做版式，不新增内容** |
| `record_mistakes` | `tools/memory.py` | 记录复习结果：没记住的写 `words`（间隔归零、明天重来），记住的写 `known`（间隔按 1→3→×ease 递推），并把 `due` 日期返回给模型 |

---

## 三、目录结构

```
readcoach/
├── app.py                        # Streamlit 入口，只管界面
├── config.py                     # 路径、模型参数、写盘权限边界
├── agent/
│   ├── graph.py                  # LangGraph 状态图
│   ├── languages.py              # 语种注册表（5 语种：等级体系 / 注音 / 词库覆盖 / 新闻源）
│   └── prompts.py                # 三层提示词组装（常驻 / 技能 / 档案 / 语种规矩）
├── tools/                        # 七个工具 + lexicon.py 词库共享层 + daily.py 每日推送
├── skills/intensive-reading/
│   ├── SKILL.md                  # 精读六步流程与输出纪律
│   └── template.html             # 练习页版式，改版式不动代码
├── data/
│   ├── lexicon.json              # 英语词库（6161 条：高考 3671 / 四级 1304 / 六级 1174，含音标；49 条手写例句）
│   ├── learner_profile.json      # 学习者档案（语种 + 目标等级 + 错词本 + 复习区间 + 打卡日期，虚构样例）
│   ├── articles/<lang>/          # 离线快照池：5 语种各 2～3 篇真实抓取的正文（带原始 URL）
│   └── cache/daily/<lang>/       # 当天抓取结果缓存，同一天同一语种只抓一次
├── demo/
│   ├── article_sample.txt        # 内置演示文章（read_article 读）
│   └── paste_sample.txt          # 自贴文章的备用文本，演示前粘进粘贴框（load_text 读）
├── outputs/                      # Agent 唯一可写目录
├── scripts/
│   ├── build_lexicon.py          # 从开源 CET 词表重建 lexicon.json（可复现）
│   ├── rehearse.py               # 按演示顺序跑 7 条话术，日志写 logs/
│   ├── build_pptx.py             # 由 HTML 版式重建 答辩幻灯片.pptx（坐标 1:1 照抄）
│   ├── pptx_kit.py               # 上面那个脚本用的画布小工具（文字/卡片/代码块/表格）
│   ├── fetch_pool.py             # 抓 5 个语种的离线快照（答辩教室没网时的兜底）
│   └── reset_demo.py             # 演示前重置：清产物、还原档案
├── 答辩幻灯片.pptx                # 答辩用 PPT：12 页 16:9，文字可编辑，备注栏带逐字稿
├── 答辩幻灯片.html                # 项目介绍幻灯片（单文件，离线可开）
├── 代码解读.pptx                  # 十段关键代码的讲解课件：13 页 16:9，文字可编辑
├── 代码解读.html                  # 同一份课件的网页版（单文件，离线可开）
├── start.bat                     # Windows 一键启动
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## 四、环境要求

- **Windows 10 / 11**
- **Python 3.10 及以上**（开发与验证使用 3.13）
- 可访问 `dashscope.aliyuncs.com` 的网络
- 一个阿里百炼 API Key（有免费额度）

检查版本：

```bat
python --version
```

如果低于 3.10，或者提示找不到命令，先装 Python 3.11+ 并勾选 "Add python.exe to PATH"。

---

## 五、安装与启动（Windows）

### 方式一：一键启动（推荐）

双击项目根目录的 `start.bat`。它会自动建虚拟环境、装依赖、复制 `.env`，然后打开记事本让你填 Key。

### 方式二：手动三条命令

```bat
cd /d D:\readcoach
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

### 配置 Key

```bat
copy .env.example .env
notepad .env
```

把 `DASHSCOPE_API_KEY=` 后面换成你自己的 Key（获取地址：<https://bailian.console.aliyun.com/> → API-KEY 管理），保存关闭。

### 启动

```bat
.venv\Scripts\python -m streamlit run app.py
```

浏览器会自动打开 <http://localhost:8501>。端口被占用时：

```bat
.venv\Scripts\python -m streamlit run app.py --server.port 8502
```

### 验证安装（离线自检，不需要 Key）

```bat
.venv\Scripts\python selftest.py
```

18 项检查覆盖：工具注册、越权读写拦截、CSV 的 BOM 与等级纠正、字段对齐、挖空变形匹配、英美拼写变体归一、Word 版式导出、错词本写回与复习排期。
全部输出 `✓` 才算环境正常。这一条也是答辩时证明「工具真的在干活、而不是模型凭空说话」的凭据。

### 演示前重置（重要）

```bat
.venv\Scripts\python scripts\reset_demo.py
```

清空 `outputs/`（保留 `.gitkeep`）、把 `learner_profile.json` 还原成虚构初始样例、删除 `data/session.json`。
**演示前必跑**，否则上一轮的产物会和新产物混在一起，讲「这次生成了什么」时自己都分不清。

加 `--keep` 可以只看会动哪些文件，不实际删除。

### 彩排七条话术

```bat
.venv\Scripts\python scripts\rehearse.py
```

按演示顺序跑完下面 7 条话术，把工具调用轨迹、最终回复、耗时写进 `logs/rehearse_<时间戳>.md`。
只想跑某一条：`scripts\rehearse.py 3`。

---

## 六、推荐演示话术（7 条，前 5 条是主线，第 6、7 条是这一版新加的）

1. **主路径**
   > 帮我精读 demo 里那篇校园碳排的文章，挑出 8 个 CET-6 生词

   实测（2026-10-26）：`read_article` ×2（第一次猜的文件名不存在，工具报错并列出可用文件，它自己改参数重试）
   → 8 次 `lookup_word` → 1 次 `make_wordlist_csv` → 1 次 `build_worksheet_html`，
   共 **12 次工具调用、16～25 步、40～50 秒**，产出 2 个文件、8 处挖空。每次有 2～3 个词不在词库，
   会被标为「未收录 / 模型推断」。

2. **只做词表（验证工具可单独调用）**
   > 把这几个词做成一份 CSV 词表，我要导到 Excel 里背：mitigate, incentive, cumulative, viable

3. **验证长期记忆生效**
   > 我的错词本里现在有哪些词？

   预期：能说出 `mitigate(3次)`、`incentive(2次)`，注意这些是**上一轮会话**写进 JSON 的，不是当前对话记的。

4. **验证记忆回写**
   > 我这次又把 mitigate 和 incentive 记混了，帮我记下来

   预期：调用 `record_mistakes`，侧边栏错词本的次数随之变化。

5. **验证边界（加分项，教师爱问）**
   > 帮我把这篇文章翻译成中文，我要抄到作业里交

   预期：Agent 拒绝代写，改为提供段落结构提纲。

6. **贴自己的文章（这一版新增，最值得演示）**
   > 把 `demo/paste_sample.txt` 粘进界面上的「粘贴自己的文章」框，点「用这篇开始精读」

   预期：`load_text` 读固定槽位 `data/current_article.txt`，整篇换成睡眠与记忆的题材，照样出词表和练习页。
   要点：这个工具**没有路径参数**，所以「能读用户材料」和「读不到 `.env`」两件事同时成立。

7. **验证复习调度（这一版新增）**
   > 今天该复习哪几个词？

   预期：按 `due` 排序列出到期词；随后说「mitigate 又记混了」，`record_mistakes` 返回的 `due` 是明天，
   侧边栏到期日当场变化。日期由代码算，模型只能抄。

---

## 七、关键代码在哪（现场指认用）

| 位置 | 看什么 |
|---|---|
| `agent/graph.py` | `StateGraph` 的三条边怎么连成 agent ⇄ tools 循环；为什么 `recursion_limit=60` |
| `config.py` 的 `safe_output_path()` | 权限隔离：模型给的 `filename` 是不可信输入，`resolve()` 后校验父目录 |
| `tools/worksheet.py` 的 `_mask()` | 挖空算法：按词长降序替换，生成 `s/es/ed/d/ing` 变体，并处理 e 结尾（`mitigate→mitigating`）与 y 结尾（`quantify→quantified`）的去 e 规则 |
| `tools/wordlist.py` 的 `_verify()` | 事实校验：模型编造的等级被词库覆盖，查不到的词强制标「未收录/模型推断」 |
| `agent/prompts.py` 的 `select_skill()` | Skill 按需加载，没命中触发词就完全不拼进上下文 |

---

## 八、相对课堂 demo 的改动

| 课堂 demo | 用了哪一块 | 本项目做了什么 |
|---|---|---|
| demo_1 | Streamlit 界面 | 保留 Streamlit，但界面层完全不写业务逻辑；新增 `st.status` 逐步展开工具调用 |
| demo_2 | OpenAI 兼容接口、工具调用、流式输出 | 全部用上；工具调用过程改成事件流（`yield`），界面边跑边显示 |
| demo_3 / demo_4 | 云端模型、密钥与环境变量管理 | `.env` + `.env.example`，`config.py` 统一读取并做缺失检测 |
| demo_5 | Agent 框架、Skills、长期记忆、WebUI | 框架从课堂版本换成 **LangGraph**；Skill 自建 `intensive-reading`；记忆落成可读的 JSON 档案 |

**增量部分（教师会重点看这块）**：

1. **七个工具全部自写**，课堂 demo 里没有对应实现；
2. **自建 Skill 目录**，`SKILL.md` 管流程、`template.html` 管版式，两者与 Python 代码解耦；
3. **写盘权限隔离** `safe_output_path()`，Agent 只能写 `outputs/`；
4. **挖空算法**（词形变体匹配），不是简单字符串替换；
5. **三层提示词组装**：常驻人设 / 按需技能 / 动态档案，互不污染；
6. **工具侧事实校验**：CSV 写盘前用词库复核等级，把模型编造的考纲等级拦下来。
7. **工具把「事实 + 表述约束」一起回传**：`make_wordlist_csv` 返回 `columns` 与 `reply_rule`，
   `record_mistakes` 返回写盘后的 `counts`、`schedule` 与 `integration`。实测模型会声称 CSV「含音标」
   （当时文件里根本没有音标列）、说错词「已同步进 App」（项目根本没接任何 App）、报次数时慢一格
   （用提示词里的旧快照推算）。**把事实写进工具返回值，比在提示词里反复叮嘱可靠得多。**
   后来音标这一列的修法很能说明思路：不是继续叮嘱模型别编，而是**让工具从词库填，模型碰不到这个字段**。
8. **复习调度（简化 SM-2）**：`record_mistakes` 不只记次数，还维护 `interval / ease / due / reps`，
   答错间隔归零、答对按 1→3→×ease 递推；系统提示词每轮注入「今日待复习」。日期由代码算，
   模型只能引用 `due` 字段，不能自己说「七天后」。
9. **多语种（对标多邻国的语种切换）**：`agent/languages.py` 是一份注册表，管 5 个语种各自的
   等级体系（CET / JLPT / DELF / Goethe / DELE）、注音形态（IPA / 假名＋罗马音）、词形规矩
   （法语名词带冠词、德语名词大写并带 der/die/das、日语动词给辞书形）与新闻源。
   **换语种不改一行业务代码**：提示词里的「语种规矩」、词表标题、Word 版式说明、界面话术
   全部按注册表取。
   最要紧的一条边界：**只有英语有可核验的本地词库**。其余语种 `lookup_word` 直接返回
   `NOT_SUPPORTED`（而不是伪装成 `NOT_FOUND`），词表工具的注音由模型给（entries 第 6 字段），
   Word 里每条都标「模型推断」，页脚写明「本语种暂无本地词库」。
   这是刻意的「宁可承认不行」：把英语的 6161 词词库说成「支持多语种查词」，是最容易被一句追问戳破的地方。
10. **每日推送 + 连续打卡**：`tools/daily.py` 按「当天缓存 → 联网抓 → 离线快照」三级回落取文，
    抓的是新华网多语种版（`div#detail` 正文容器统一，5 个语种共用一套解析）。
    同一天同一语种只抓一次（`data/cache/daily/<lang>/<date>.json`），快照池 `data/articles/<lang>/`
    里是真实抓下来的正文、带原始 URL——答辩教室断网也不会空白。
    连续天数按日期集合算（`compute_streak`），今天还没读时保留到昨天，不会零点归零。
    **「推送」不做成弹窗**：本地应用没有推送通道，硬造一个只会在演示时翻车；
    真正要解决的是「今天读什么、昨天断了没有」，所以做成首页的任务卡 + 打卡天数。

**一个实测到的问题（答辩可当案例讲）**：第一次跑主路径时，`structural` 和 `enforceable` 查词返回 `NOT_FOUND`，模型却在 CSV 里给它们填了 `CET-6`——只在提示词里写"不许编"是拦不住的。加入 `_verify()` 后重跑，这两个词被工具强制标为「未收录 / 模型推断」，模型也在回复里主动声明「含 3 个未收录词，建议同步查权威词典」。**校验放在代码里，不靠模型自觉**，这是工具存在的真正理由。

**另一个同类问题：产物路径与"到底写了没有"**（2026-10-26 修）

用户反馈"生成的文件名打不开"。查下来是三件事叠在一起，只有第三件是模型的问题：

1. 回复里只有 `outputs/xxx.csv` 这种**相对路径**，没有盘符。用户拿去资源管理器里找，必然找不到。
   → 工具回传 `absolute_path`，并在提示词里规定「说位置必须抄这一行」。
2. 侧边栏的「产出文件」列表写在脚本前部，**在发消息之前就渲染完了**，本轮新生成的文件不会出现。
   → 改成先占位、脚本末尾再填（Streamlit 是自上而下执行的）。
3. 模型会写它训练数据里的容器路径 `/home/ubuntu/outputs/xxx.csv`；更糟的是**没调写盘工具就在回复里说"两份文件已生成"**（实测两次，它会因为"上一轮生成过同名文件"而跳过执行）。
   → 出口处两道确定性检查：`normalize_output_paths()` 把任何"像产物路径的串"换成磁盘上真实存在的绝对路径；`snapshot_outputs()` 对比调用前后，**声称生成但没有新文件就当场警告并给出重跑按钮**。

这三条都不靠"提示词加一句嘱咐"解决——前两条是界面顺序和返回值设计问题，第三条是在程序出口做核对。**同样的思路可以复用到所有"模型说要交付某物"的场景。**

---

## 九、数据与合规

- 词库 `data/lexicon.json` 共 6161 条，由开源词表项目 **qwerty-learner**（MIT）的
  `GaoKao_3500 / CET4_T / CET6_T` 三份词表合并而成，可用 `scripts/build_lexicon.py` 复现；
  音标、词性、释义为原始词表数据，其中 49 条为手写补充并带自写例句。未经权威词典逐条校对，**仅供学习参考**。
- 学习者档案 `data/learner_profile.json` 是**虚构样例**，不含任何真实学号、手机号、成绩。
- 不代写作文/作业，不逐句翻译供抄写；界面底部提示「释义以权威词典为准」。
- `.env` 已在 `.gitignore` 中，仓库内只有 `.env.example` 占位符。**若曾误提交真实 Key，请立即在百炼控制台作废重签。**

---

## 十、已知不足

- **非英语语种没有本地词库**：日语/法语/德语/西语的释义、注音、等级全部由模型给出，
  文件里已逐条标注「模型推断」，但这意味着它们的可信度低于英语那一路。
  要做到和英语一样可核验，需要各语种的词表数据（JLPT / DELF / Goethe / DELE 官方词表），
  这一步没做——与其塞一份来路不明的词库装作能查，不如把边界写清楚。
- **非英语词表重排会丢等级标签**：等级不进 CSV（只有五列），英语重排时能按词库现查回来，
  其他语种没有词库可查，重排后标签会变成「未校验」。这是五列设计的直接代价。
- **每日推送依赖对方站点结构**：抓取靠 `div#detail` 这个容器，对方改版就要跟着改解析；
  真出现这种情况，`data/articles/` 里的快照仍能兜住演示。

- 词库是「考试词表」而不是真实词典：四六级词表收的是新增难词，派生词（`retrieval`、`coherence`、
  `reconstruction`）常常不在里面，此时只能退回「模型推断 + 明确标注」。接真实词典 API 能一次解决。
- 复习调度是简化 SM-2：只有两档结果（记住 / 没记住），没有四档评分，也没有跨设备同步。
- 会话历史只存文本，不保存工具调用中间态，因此重新打开后看不到上一轮的工具轨迹。
- 未做多用户隔离，`outputs/` 与档案是单例的，适合作业演示，不适合直接上线。
- 挖空只覆盖规则变形，不规则复数与不规则动词（如 `analysis → analyses`）会漏匹配。
- 词表 CSV 含五列（`word / phonetic / pos / cn / example`），音标由工具从词库填入，
  模型不参与这个字段；未收录词的音标留空，而不是让模型补一个。
  **等级与来源不写进 CSV**——它们在排版成 `.docx` 时按单词现查词库，变成〔CET-6〕
  这样的标签和「未收录」小字注。数据表保持干净，判断留在给人看的那份里。
- 未做句子级拆解：长难句的主干、从句、指代目前只能靠模型自由生成，不可核验。要做得可靠，
  得像 `_verify()` 一样给它一个结构化工具（`parse_sentence`），否则只是把幻觉换个地方放。
- 未使用 MCP：课程要求「≥2 个自定义工具 **或** 1 个 MCP 服务器」，本项目选前者。MCP 化无需改工具逻辑，挂一个 stdio server 即可。

---

## 十一、汇报材料

| 材料 | 位置 | 说明 |
|---|---|---|
| 答辩 PPT | `答辩幻灯片.pptx` | 12 页 16:9，PowerPoint / WPS 直接放映；**文字与表格都能改**，每页备注里是该页逐字稿（演讲者视图可直接念） |
| 项目介绍 HTML | `答辩幻灯片.html` | 同一个版式的网页版，双击即开。**无 CDN 依赖**，教室断网也能放 |
| 代码解读 PPT | `代码解读.pptx` | 13 页 16:9，由 `scripts/build_code_pptx.py` 从 HTML 重建，**代码块与批注都是可编辑文本框**，追问时直接翻页 |
| 代码解读 HTML | `代码解读.html` | 同一份课件的网页版，逐段拆十处关键实现：为什么这么写 / 逻辑 / 用到的知识 |
| 代码解读发言稿 | `docs/code-walkthrough.md` | 十段口播（每段 45–60 秒）+ 20 秒精简版 + 五个基础概念白话版 + 10 条追问 |
| 答辩逐字稿 | `docs/defense-script.md` | 4 分钟口播（每页标秒数）+ 4 分钟演示卡点 + 9 条问答预案 + 上台清单 |
| 录屏分镜 | `docs/record-script.md` | 3 分钟录屏，逐 15 秒拍什么、念什么 |
| 话术彩排日志 | `logs/rehearse_*.md` | 真实运行记录；演示出问题时可作为「刚才确实跑通过」的证据 |
| 离线自检 | `selftest.py` | 18 项检查，演示翻车时用来证明工具层是好的，问题在网络或模型侧 |

幻灯片操作：`←` `→` 或空格翻页，`F` 全屏，`Home` / `End` 跳首尾。滚轮也能翻。
