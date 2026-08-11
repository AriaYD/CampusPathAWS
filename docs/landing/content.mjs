/**
 * 宣传页文案（简体 + 英文两份**源**）。
 *
 * 繁体是**生成物**：`bun apps/web/scripts/build-landing.mjs` 用 OpenCC(cn→hk)
 * 从简体转出来，与 `bun run i18n:hant` 同一纪律——**禁止手写繁体**。
 *
 * 内容取自 `docs/CampusPath_产品介绍_2026-08-10.md`（用户 2026-08-10 审定），
 * 章节顺序照 scivia.ai/consilium 的说服链路：
 * Hero → 做什么 → 痛点 → 给谁用 → 能得到什么 → 记忆 → 对比 → 怎么用 →
 * 技术 → 谁说了算 → 数字 → CTA。
 *
 * **数字纪律**：这里出现的每个数值都必须能在产物里查到。契约数是
 * `make contracts` 的实测输出（2026-08-10：177 类型 / 92 路径 / 111 操作），
 * 不是从旧文档抄的。
 */

export const APP_URL =
  "https://campuspath-web-786160486093.asia-east2.run.app";

/** 演示口令。用户 2026-08-10 明确要求印在 CTA 旁边——见 README「线上环境」。 */
export const PASSCODE = "OceanMeetsTheSky!";

export const zhHans = {
  htmlLang: "zh-Hans",
  brand: "CampusPath",
  brandSub: "校园成长路径",
  nav: [
    ["what", "做什么"],
    ["pain", "痛点"],
    ["who", "给谁用"],
    ["value", "能得到什么"],
    ["memory", "记忆"],
    ["how", "怎么用"],
    ["tech", "技术"],
  ],
  cta: "试用 CampusPath",
  /** 窄屏顶栏用的短标签——全称在 390px 上会溢出视口右缘（实测 437 > 390）。 */
  ctaShort: "试用",
  ctaHint: "体验口令",
  hero: {
    kicker: "面向在校本科生 · 由大学部署",
    title: "一个目标 → 一条今天就能走的路，每一步都说得出为什么",
    lead:
      "以学生「你想成为谁」为中心的成长规划系统，与校方的资源效能分析构成双闭环：" +
      "把目标拆成能力小目标，倒推成从今天到未来的每一步行动；学生的真实行动变成证据与记忆，" +
      "再用这些新证据校准下一轮路径。而这些反馈同时回到学校，让资源投到真正缺的地方。",
    stats: [
      ["1,534", "门真实抓取的课程"],
      ["93", "个信息源（85 个真实抓取）"],
      ["13/13", "条评测红线通过"],
    ],
  },
  sections: [
    {
      id: "what",
      kicker: "我们做什么",
      title: "一个学生校园成长规划操作系统，不是又一个活动聚合网站",
      body: [
        "你设一个主目标和一个候选目标，系统从最新的几十份真实岗位数据里拆解出要什么能力，" +
          "再从全校海量资源里挑出补得上缺口的活动、课程和机会，排进你真实有空的时段。",
        "产出的是**一条带版本、带依据、随变化滚动更新的路径**，不是一份聊完就关掉的建议清单。",
        "CampusPath 不替代导师、Career Center、学院顾问或 LMS——它是学校资源、外部机会" +
          "与学生个人发展之间的发现、匹配与编排层。",
      ],
      cards: [
        {
          title: "对学生",
          body:
            "把长期方向倒推成当下可执行、且不挤压生活的路径；每条建议都说明补什么差距、" +
            "形成什么证据、为什么是现在。",
        },
        {
          title: "对学校",
          body:
            "把已经投入巨大成本、触达效率却很低的资源，变成**可测量、可改进、可归因**的成长资产；" +
            "并第一次看到「资源池覆盖不了学生的哪些真实需求」。",
        },
        {
          title: "「学校资源」的口径",
          body:
            "**凡是因为学生的在校身份而能拿到的机会，都算学校资源**——校友内推、企业来校招聘、" +
            "合作方名额、跨校联盟活动。所以我们不分校内校外，只分：**是否发现、是否够格、是否用上**。",
        },
      ],
    },
    {
      id: "pain",
      kicker: "痛点",
      title: "学生不是缺资源，而是难以把海量资源转化成自己的成长路径",
      body: [
        "一所大学里，每个学院有自己的活动，几百个社团各办各的，还有协会、实验室、研究中心、校企合作。" +
          "这些机会散落在不同部门的官网上——**每个官网的架构还都不一样**。你得先找到真正的活动页，" +
          "然后经常回去看，才不会错过。",
        "对一个课业本来就很重的学生来说，这基本做不到，除非你自己搭一套全量采集系统。" +
          "而且即使看到了，也常常撞上自己的时间，或者报完才发现根本不是自己想要的。",
      ],
      table: {
        head: ["成本", "具体是什么"],
        rows: [
          ["发现成本", "不知道有哪些可信机会"],
          ["理解成本", "看到了，却不知道具体资格与价值"],
          ["规划成本", "不知道课程、经历和机会如何形成有依赖关系的路径"],
          ["执行成本", "收藏很多，但没有转成行动、材料和日历"],
          ["纠偏成本", "做完没有沉淀，系统下次仍重复安排无效或不适合的事"],
          ["容量管理成本", "不知道成长任务如何排进真实日历，容易冲突、过载或挤压休息"],
        ],
      },
      note:
        "还有一件更隐蔽的事：活动宣传通常只说「有什么」，很少说「适合谁、能补什么差距、" +
        "时间投入值不值」；而学生做完之后的真实体验，几乎从不回到下一轮推荐和学校的资源改进里。",
    },
    {
      id: "who",
      kicker: "给谁用",
      title: "主界面给学生，另一半给学校",
      body: [
        "**五类目标导向人群**——按「想走向哪里」划分，不是给学生永久贴标签。" +
          "一个学生可以同时持有两个候选方向，并随实践改变权重。",
      ],
      table: {
        head: ["模式", "典型目标", "系统重点"],
        rows: [
          ["就业与职业发展", "进入目标企业、行业、岗位或公共服务领域", "岗位要求、技能证据、项目、实习、作品与招聘节奏"],
          ["学术与深造", "读研、读博、进入研究领域、寻找导师", "课程基础、研究方法、实验室、科研经历与申请时间线"],
          ["创业与创新", "创办项目、验证需求、加入孵化器或组建团队", "问题发现、比赛、原型、用户验证、导师、资金与团队"],
          ["兴趣与个人成长", "艺术、体育、语言、公益、创作或其他长期兴趣", "能力成长、社群、作品、体验质量，不强迫职业化"],
          ["探索与方向未定", "暂时迷茫，希望通过实践逐步认识自己", "低成本、多样化的探索实验；用实际体验更新目标信心"],
        ],
      },
      // 用户 2026-08-11 在产品介绍文档里加的那段整合前提，原样搬过来：
      // 这不是免责声明，是**部署条件**——评委读完「校方那一半」就会问它。
      callout: {
        title: "接入前提",
        body:
          "这个平台需要接入学校系统才能发挥完整作用：学生的教学系统、教务系统" +
          "（取大一到大四的教学计划安排）、Career Center 系统（顾问预约与 Job & Internship）、" +
          "学校及各学院部门的官网 API（订阅资源活动页更新）、心理咨询室系统" +
          "（咨询预约与紧急联系），以及其他校内系统。",
      },
      note:
        "国际身份、经济条件、照护责任、健康与精力、通勤、语言、无障碍需求不是**「第六类人」**，" +
        "而是每一种发展模式都必须尊重的个人约束——通过可插拔的 Context Pack 注入已有流程，" +
        "不复制一套新 Agent。",
      cards: [
        {
          title: "Career Center 管理员",
          body:
            "授予/撤销投稿权限、管理审核队列与政策、配置连接器与凭据轮换。" +
            "不能读学生私人档案、反思或日历，也看不到反馈者身份。",
        },
        {
          title: "Publisher（社团 / 实验室 / 学院）",
          body:
            "Career Center 管理员端可授权部门负责人投稿权限，" +
            "在授权组织与有效期内创建并提交投稿。不能直接公开发布、不能绕过审核、不能代表未授权组织。",
        },
        {
          title: "职业发展咨询顾问",
          body: "只看学生**主动预约**的会面与想聊的主题，会后最多发 5 条关键建议。学生的反思原文、成绩、日历一律 403。",
        },
        {
          title: "心理咨询室协调员",
          body: "只接收学生同意或主动请求的最小化关怀联系。不能查看完整日历，也不能把容量信号当成诊断。",
        },
      ],
    },
    {
      id: "value",
      kicker: "你能得到什么",
      title: "六件在别处拿不到的事",
      cards: [
        {
          title: "四态资格，不是「能 / 不能」",
          body:
            "大一学生看到只限大三的实习，不会被静默过滤掉，而是标为「未来可申请」，" +
            "并告诉你这一年该补什么。四态：现在合格 / 未来可达 / 信息不足 / 本轮不适用。",
        },
        {
          title: "每条建议都说得出为什么",
          body: "补什么差距、形成什么证据、为什么是现在。拆解出来的每一条都能点开溯源到岗位原文，不是模型编的。",
        },
        {
          title: "个性化之外仍可自主发现",
          body:
            "资讯广场展示校方**全部审核通过的资源**，可见性不由 AI 排序决定。" +
            "任一条目都能点「为什么没推荐我」，给出规则引擎签发的凭据式解释。",
        },
        {
          title: "先看真实容量，再安排任务",
          body:
            "日历默认只读忙闲，不读事件标题。规划前先算课程、已有安排、睡眠与三餐保护块、" +
            "可支配时间和缓冲，只在你真的有空的格子里排。",
        },
        {
          title: "从推荐走到行动的闭环",
          body: "材料、日历、提醒、状态和替代方案连成一条；活动做完写反思，自动沉淀为**成长证据**。",
        },
        {
          title: "不会一味 push 你",
          body:
            "睡眠被挤压且负荷持续偏高时，系统会预警而不是继续往日历里塞东西。" +
            "这条安全护栏链路**零大模型**——判定归阈值，文案归固定模板。",
        },
      ],
    },
    {
      id: "memory",
      kicker: "越用越懂你",
      title: "它记住的不是你点了什么，是你为什么改主意",
      body: [
        "学生从入学到毕业会连续用四年甚至更久。系统必须记住：已修课程与项目、" +
          "**你明确拒绝过的方向和原因**、哪些活动对你高价值哪些低价值、你做过的目标变更和取舍、" +
          "你的节奏与精力偏好，以及哪些技能你已经拿到了、不该再重复安排。",
      ],
      table: {
        head: ["层", "存什么", "更新规则"],
        rows: [
          ["L0 当前档案", "学业、经历、成果、技能、目标、偏好、容量与约束的**当前有效状态**", "只由权威来源或学生确认更新，每次变更留档案变更事件"],
          ["L1 事件时间线", "参加、申请、完成、放弃、反馈、计划版本等事件", "**只追加**；错了用更正事件处理，不改历史"],
          ["L2 语义记忆", "从经历里提炼的兴趣、模式与上下文", "带来源、时间、置信度与过期策略"],
          ["L3 证据与笔记", "你的原始笔记、作品、证书、反思原文与附件", "**你拥有**；默认不向校方共享"],
        ],
      },
      cards: [
        {
          title: "记忆的安全规矩",
          body:
            "区分「学生原话」「系统推断」「外部事实」，不把推断伪装成事实；新旧冲突时**保留时间线**、" +
            "用 supersedes 表示更新，**不静默覆盖**；不把短期情绪写成永久性格标签。",
        },
        {
          title: "你随时可以反悔",
          body: "任何一条记忆都能搜索、纠正、锁定、删除、导出、暂停。读取时只召回与当前任务相关的最小上下文。",
        },
        {
          title: "反思三轨分开建模",
          body:
            "你发生了什么变化 / 你想长期保留什么 / 活动本身是否兑现宣传——这是三件事。" +
            "混在一起，学校就永远收不到有用的信号。",
        },
        {
          title: "倒逼学生真的去总结",
          body:
            "反思必须先绑定一个具体对象才能创建，防止泛泛而谈。预约顾问的会面还有一层：" +
            "写完并保存这次会面的反思，才能看到顾问给你的关键建议。",
        },
      ],
      note:
        "**关键设计：个人不适配与全局低质是分开的。**「太基础」「太难」走个人契合标签，" +
        "只调整你自己的推荐难度，**不惩罚这个活动**；「宣传夸大、内容空泛」达到样本阈值后" +
        "才降低该届次的置信度并进入复核。",
    },
    {
      id: "compare",
      kicker: "和市面上的产品有什么不同",
      title: "别人给你一段回复，我们给你一条路径",
      table: {
        head: ["产品类型", "它们的重心", "CampusPath 的区别"],
        rows: [
          ["LinkedIn", "职业身份、网络、职位与内容", "连接课程、先修、校内资源、学生负荷与长期成长路径：把机会变成校园行动"],
          ["Handshake", "大学生职位、实习、雇主、招聘活动", "不止展示机会，还把课程、研究、比赛、社团和实习组合成有依赖关系的动态能力路径"],
          ["职业测评产品", "兴趣、价值观、职业匹配", "测评只是输入：系统通过真实实践持续验证，而不是一次测完就定型"],
          ["简历 / 面试工具", "简历反馈、面试学习与模拟", "覆盖进入申请阶段之前数月或数年的能力建设与证据积累"],
          ["通用 AI Career Coach", "对话建议、简历与职业问答", "有真实来源、资格状态、工具调用、长期记忆、时间约束、行动闭环和可量化评测"],
        ],
      },
      note:
        "最短的一句话：别人给你一段回复，我们给你一条能落实到每日日历、能追溯来源、" +
        "会随你变化滚动更新的路径，并且把结果回流给学校。",
    },
    {
      id: "how",
      kicker: "怎么用",
      title: "一条真的闭合的环，学生端与校方端互为对方的输入",
      steps: [
        {
          title: "开通与授权",
          body:
            "接入学校教务系统；授权个人日历（**默认只读忙闲，不读事件正文**）。" +
            "系统这才知道你的在校学业课程状态、真实有多少时间。",
        },
        {
          title: "建立成长档案",
          body:
            "上传简历，系统确定性解析后直接整理进「我的成长档案」总览，并弹窗逐条列出新增内容" +
            "供你自行核对，任何一条都能当场撤销。国际生可在这里勾选「我是国际生」，" +
            "一个版本化的 Context Pack 会注入后续所有环节。",
        },
        {
          title: "目标工作室",
          body:
            "设一个主目标 + 一个候选目标，设定两者的推进配比，点「开始规划」。后台三段式跑：" +
            "**采集真实岗位数据 → 分析比对 → 目标拆解**。拆解结果分三层：",
          bullets: [
            "**软实力——**口才、领导力、影响力、团队协作；",
            "**硬实力——**绩点与核心课绩点要求；",
            "**个人真实硬件实力——**比赛与奖项、项目与论文、实习经历、证书与软件。",
          ],
          tail:
            "每一条都能点开看它来自哪份岗位描述。系统同时给出两个目标的**共享缺口**与**分叉点**" +
            "——共享的先做，两条路都不亏。",
        },
        {
          title: "发现",
          bullets: [
            "**资讯广场：**全校、各学院、社团、协会、实验室、教授、校企的机会都在这里，" +
              "按十大主办方类别与主题、年级、资格、线上线下、截止时间等标签筛。" +
              "已过期的归入独立分组并明确标注，不会混在「现在可以报名」里，也不会被推荐给你。",
            "**为你推荐：**基于你的档案 + 目标拆解 + 记忆里的偏好挑出来的，每张卡写明**为什么推荐你**。" +
              "四态资格在卡片上直接可见。",
          ],
        },
        {
          title: "规划与批准",
          body:
            "报名的活动进入行动中心。系统按**未来两周 / 一个月 / 一学期 / 一学年**四档跨度铺开，" +
            "并自动倒排提前量——大型比赛提前一两周到一个月准备、等级证书提前一两个月、" +
            "语言类考试提前一年，就出现在对应跨度的日程里。" +
            "**规划完先弹窗给你审批**，说明依据（你的目标、你的档案、记忆里的偏好），" +
            "你批准了才写进日历。日历是周/月网格且**本身就是编辑器**：随时改时间、" +
            "加睡眠与三餐保护块、加缓冲。改完是否重排，也问你。",
          bullets: [
            "你还可以按照个人的精力水平和时间空闲程度，自行设置规划安排的三档不同强度：" +
              "轻负荷、均衡、进取。",
            "行动中心里还有**选修课推荐**：必修按培养方案载入不做推荐，选修按你的档案、" +
              "目标与所需技能推荐，附课程全名、简介、先修原文与教务系统跳转链接。",
          ],
        },
        {
          title: "护栏（安全护栏零大模型）",
          body:
            "睡眠**只看你自己声明的睡眠窗口**和日历里占用它的安排——没声明就不推断，" +
            "如实显示「数据覆盖 0 天」。**绝不从「日历上有空档」反推你在睡觉或在运动。**" +
            "判定是一个纯计数模型（下列为实现中的实测阈值）：**过劳日** = 有效睡眠不足 7 小时" +
            "且当天学习工作超过 11 小时；滚动 14 天内合格日 ≥ 10 天 → **第一层预警**；" +
            "滚动 28 天内合格日 ≥ 20 天 → **第二层要求填两份量表**。",
          bullets: [
            "两份量表是 ISI（失眠严重程度）与 PSS-10（压力自评），用来区分「熬夜是个人习惯」" +
              "还是「学业压力造成的」——这个区分很重要，两者该给的支持完全不同。",
            "轻度 → 提示可联系你自己填写的辅导员；中度失眠或压力值偏高 → 引导预约心理咨询室时段。",
            "最上面还有第三层：**紧急求助**按钮，跳过全部排队直连学校心理咨询专员" +
              "（如有无端恶意占用，每学期 2 次，第 3 次停用一学期——但停用的响应里仍然附上热线）。",
          ],
          tail:
            "提醒**最多两次**，只对学生可见，默认不进任何校方后台；" +
            "非紧急的校方触达必须有你预先同意或当次主动请求。",
        },
        {
          title: "反思与沉淀",
          body:
            "活动结束后写反思与四维评分。写完，活动自动归档为**成长证据**进入「成长动态跟踪」，" +
            "挂在对应的能力细则下。这一步同时产生北极星指标 VGA（Verified Growth Actions）" +
            "——**它不奖励点击、收藏、报名或忙碌本身**，只数真正做成并留下证据的行动。",
        },
        {
          title: "回到学校（闭环的另一半）",
          bullets: [
            "Career Center 管理端统一注册并监控所有信息源，看得到每个源的健康度，" +
              "每天定时抓一次，也可以一键实时抓；",
            "社团负责人、实验室、教授通过投稿台提交活动 → 进入审核队列 → 批准后才进资讯广场；",
            "批准的活动**自带二维码**下发给主办方，活动开始时激活，到场的人扫码签到；",
            "于是学校拿到几组真实数据：**谁真的来了**（签到）和**他们怎么评价**（匿名四维评分）等等；",
            "由此看清：哪类活动更受欢迎、哪些活动质量高、真实好评率多少、" +
              "**哪些领域有缺口、哪些专业的资源不够**；",
            "报告按周 / 月 / 学期 / 学年自动生成，也可以随时手动生成一份；",
            "活动结束两个月统计冻结、自动下架并归档。",
          ],
        },
      ],
      note:
        "**闭环合上了**：学生从海量资源里精准找到匹配自己目标的活动 → 参加 → 写反思 → " +
        "沉淀成证据推动下一轮规划；而这些反馈同时回到学校，让学校及时看到学生的真实需求与" +
        "趋势变化，据此补缺口、给高质量活动倾斜资源。**互利，双向推动。**",
    },
    {
      id: "tech",
      kicker: "技术架构",
      title: "双平面 + 契约先行：类型不允许的数据，物理上流不过去",
      body: [
        "**语义平面：**6 个语义 Agent（编排 / 学生上下文 / 学业 / 目标缺口 / 机会抽取 / 路径规划）" +
          "——**唯一允许调模型的那一层**。",
        "**确定性平面：**9 个**零大模型**的服务（规则与约束、容量与日历、Wellbeing 文案生成、状态与记忆、" +
          "行动与同意、匿名聚合、事件监控与重规划、发布审核审计、连接器与目录）。判定、阈值、资格、" +
          "容量全在这一侧，可复现、可审计。",
        "两个平面之间的每一次数据交换都由**数据契约类型**定形。",
      ],
      table: {
        head: ["#", "六条架构红线：每条都有对应的自动化测试，测试不过构建就失败"],
        rows: [
          ["1", "路径规划 Agent 是唯一做取舍的 Agent；其余只出事实与候选，输出类型里根本没有排序字段"],
          ["2", "Wellbeing 安全护栏判断**零大模型**——判定归阈值，文案归固定模板；构建期禁止 import 模型 SDK"],
          ["3", "日历凭据不进任何模型上下文——止步于容量服务，由类型层强制"],
          ["4", "机会抽取 Agent 的工具白名单只有两个；外部内容作为数据块传入，永不拼进 system prompt"],
          ["5", "每个计划条目必带规则引擎签发的校验凭据，缺失即被 API 拒绝"],
          ["6", "私人反思原文到校方聚合的路径在类型层不存在——不是「我们不传」，是传不过去"],
        ],
      },
      cards: [
        {
          title: "Google 生态里的位置",
          body:
            "ADK 负责 Agent、工具、顺序/并行工作流与记忆；两个运行时部署在 Vertex AI Agent Engine；" +
            "Cloud Run 跑学生 App API、适配器与定时任务；Moodle 沙箱通过自研**只读 MCP** 接入；" +
            "日历走 Workspace API 的分项授权。",
        },
        {
          title: "模型可以换（架构承诺）",
          body:
            "全系统的模型出口收敛在**一个适配点**上，Agent 层依赖的是一个只有单个方法的抽象接口。" +
            "换型号是部署配置，不改一行代码；换供应商（校方自有模型、其他云厂商、本地私有部署）" +
            "只需为这个接口提供一个实现——6 个 Agent、9 个确定性服务、全部**数据契约类型**与红线测试**零改动**。",
        },
        {
          title: "确定性平面不受影响",
          body:
            "资格判定、容量计算、健康阈值、隐私抑制这些最需要稳定与可审计的部分**本来就不调模型**，" +
            "不受任何模型更换影响。产品价值不依赖某一个特定模型——学校要用什么模型，是学校的决定。",
        },
      ],
    },
    {
      id: "control",
      kicker: "谁说了算",
      title: "系统给排序，你来拍板",
      cards: [
        {
          title: "学生自主",
          body:
            "你可以拒绝、修改、暂停、锁定任何一条路径；写日历、发消息、申请机会都需要你明确批准；" +
            "探索型学生不会被逼着提前确定唯一职业目标。",
        },
        {
          title: "档案由你确认",
          body:
            "证书、LMS 记录和 Agent 反思可以提出档案更新建议，但不能无提示地改写你的档案；" +
            "「学生自报」「系统观察」「来源验证」始终分开标注。",
        },
        {
          title: "证据优先于模型自信",
          body: "资格、截止日期、项目要求必须指向来源；不确定时显示「需要确认」，而不是编一个答案。",
        },
        {
          title: "校方只看聚合，不能下钻到人",
          body:
            "任何视图的样本量低于阈值一律显示 Insufficient evidence 并抑制该格，**不显示看似精确的数字**；" +
            "界面上没有「查看构成这个数字的学生」的入口，后端也不提供这种查询。",
        },
      ],
      note:
        "这个产品不是什么：不是保证进入某家公司或学校的成功预测器；不是替学生做不可逆人生决定的" +
        "自动决策系统；不是用活动数量或简历长度衡量成长的系统；不是医疗器械、心理诊断工具或" +
        "自杀风险预测系统；不是仅凭日历空档就向学校报告学生的监控工具。",
    },
    {
      id: "numbers",
      kicker: "真实的数字",
      title: "以香港科技大学的公开数据为例，下列均为实测值",
      table: {
        head: ["项", "数值"],
        rows: [
          ["真实抓取的课程目录", "58 个学科 1,534 门课，先修表达式保留来源原文"],
          ["信息源注册表", "93 个源，其中 85 个是真实抓取，8 个为演示用合成源——两者在界面上一眼可分"],
          ["**数据契约类型**", "177 个（92 条路径 / 111 个操作），前后端与 Agent 全部从同一份契约生成类型"],
          ["评测红线", "13 条 BLOCKER 全部通过（违反即失败）"],
          ["量化目标", "12 项中 11 项达标——未达标的那一项在报告里如实标红，不藏"],
          ["对照基线", "5 项，全确定性可复现"],
        ],
      },
      note:
        "判定类指标要求双跑逐字节一致，且 Gold Label 与引擎**故意分开实现**——用同一份代码生成标签" +
        "又用它评测，等于自己给自己打分。学生、成绩、日历、机会与投稿数据一律为合成数据，" +
        "页面全站标注 Synthetic / Demo Data；已核实为真实公开来源的条目另有「官方」标记，两者不混。",
      cards: [
        {
          title: "现在还没做的，也写在这里",
          body:
            "当前以「本科生毕业后进入求职」这条线为主；第二个 Career Path Pack（博士毕业进产业）" +
            "只预留了接口，**未交付**，前端不显示、不宣称；国际学生 Context Pack 已安装但状态是" +
            "「待政策复核」，复核通过前求值结果一律为「需要确认」；真实日历 OAuth 在演示中使用夹具数据。",
        },
        {
          title: "不宣称我们没有基线的事",
          body:
            "不能在没有真实基线的情况下宣称已经提高就业率或学业成果。上面所有目标都是试点假设。",
        },
      ],
    },
  ],
  ctaBand: {
    title: "打开你的成长路径？",
    body: "以学生身份从一个目标开始。走完 目标 → 发现 → 规划 → 批准 → 反思，带走一条能溯源的路径。",
    note: "演示环境用合成数据，随时可以重来。",
  },
  footer: {
    synthetic: "Synthetic / Demo Data · 学生、成绩、日历与机会数据均为合成",
    note: "本页内容取自产品介绍文档（2026-08-10）。产品定义以完整说明书为准；本页与实现不一致时以实现为准。",
  },
};

export const en = {
  htmlLang: "en",
  brand: "CampusPath",
  brandSub: "Campus growth pathways",
  nav: [
    ["what", "What we do"],
    ["pain", "Pain points"],
    ["who", "Who it's for"],
    ["value", "What you get"],
    ["memory", "Memory"],
    ["how", "How it works"],
    ["tech", "Tech"],
  ],
  cta: "Try CampusPath",
  ctaShort: "Try",
  ctaHint: "Demo passcode",
  hero: {
    kicker: "For undergraduates · deployed by the university",
    title: "One goal → a path you can start walking today, and every step says why",
    lead:
      "A growth-planning system built around the student's own question — who do you want to become — " +
      "closed on the other side by the university's view of how well its resources actually land. " +
      "Goals become capability gaps, gaps become steps on a real calendar, actions become evidence, " +
      "and that evidence recalibrates the next round. The same feedback flows back to the school, " +
      "so resources go where the gaps really are.",
    stats: [
      ["1,534", "real courses, scraped"],
      ["93", "registered sources (85 real)"],
      ["13/13", "blocker checks passing"],
    ],
  },
  sections: [
    {
      id: "what",
      kicker: "What we do",
      title: "A growth-planning operating system for students — not another events aggregator",
      body: [
        "You set one primary goal and one candidate goal. The system reads dozens of live job postings, " +
          "works backwards to the capabilities they demand, then picks the activities, courses and " +
          "opportunities across campus that close those gaps — and schedules them into hours you actually have.",
        "What comes out is **a versioned, sourced path that keeps updating as you change**. Not a list of " +
          "suggestions you close and forget.",
        "CampusPath does not replace mentors, the Career Center, faculty advisors or the LMS. It is the " +
          "discovery, matching and orchestration layer between campus resources, outside opportunities " +
          "and a student's own development.",
      ],
      cards: [
        {
          title: "For students",
          body:
            "A long-range direction turned into steps you can take now without crowding out your life. " +
            "Every suggestion states which gap it closes, what evidence it produces, and why now.",
        },
        {
          title: "For the university",
          body:
            "Resources that cost a great deal and reach very few become **measurable, improvable and " +
            "attributable** growth assets — and, for the first time, you can see which real student needs " +
            "your resource pool does not cover.",
        },
        {
          title: "What counts as a campus resource",
          body:
            "**Anything a student can reach because of their enrolment**: alumni referrals, employers " +
            "recruiting on campus, partner quotas, inter-university events. So we don't split " +
            "on-campus from off-campus — only on discovered, eligible, and used.",
        },
      ],
    },
    {
      id: "pain",
      kicker: "Pain points",
      title: "Students aren't short of resources — they're short of a way to turn them into a path",
      body: [
        "Every school runs its own events. Hundreds of societies run theirs. So do associations, labs, " +
          "research centres and corporate partners. All of it sits on different departmental websites, " +
          "each with its own **structure**. You have to find the real listing page, then keep going back so you don't miss anything.",
        "For a student already carrying a full course load, that is not realistic — not unless you build " +
          "yourself a scraper. And even when you do see something, it often collides with your schedule, " +
          "or turns out to be the wrong thing only after you've signed up.",
      ],
      table: {
        head: ["Cost", "What it looks like"],
        rows: [
          ["Discovery", "Not knowing which credible opportunities exist"],
          ["Comprehension", "Seeing one, but not knowing the eligibility or the value"],
          ["Planning", "Not knowing how courses, experiences and opportunities depend on each other"],
          ["Execution", "Plenty saved, none of it turned into actions, materials or calendar entries"],
          ["Correction", "Nothing captured afterwards, so the next round repeats what didn't work"],
          ["Capacity", "No sense of how growth tasks fit a real calendar — collisions, overload, lost rest"],
        ],
      },
      note:
        "And something subtler: event promotion says what an event is, rarely who it suits, which gap it " +
        "closes, or whether the hours are worth it. Meanwhile what students actually experienced almost " +
        "never returns to the next round of recommendations, or to the school's decisions about resources.",
    },
    {
      id: "who",
      kicker: "Who it's for",
      title: "The main interface is for students; the other half is for the school",
      body: [
        "**Five goal-oriented modes** — grouped by where someone wants to go, not permanent labels. " +
          "A student can hold two candidate directions at once and shift the weighting as they act.",
      ],
      table: {
        head: ["Mode", "Typical goal", "What the system emphasises"],
        rows: [
          ["Employment", "A target company, industry, role or public service field", "Role requirements, skill evidence, projects, internships, portfolio, hiring rhythm"],
          ["Academia", "Master's, PhD, entering a research field, finding a supervisor", "Course foundations, research methods, labs, research experience, application timelines"],
          ["Entrepreneurship", "Starting something, validating demand, joining an incubator, building a team", "Problem discovery, competitions, prototypes, user validation, mentors, funding, team"],
          ["Personal interest", "Art, sport, language, public service, creative work", "Capability growth, community, output, quality of experience — no forced professionalisation"],
          ["Exploring", "Genuinely undecided, wanting practice to reveal direction", "Low-cost, varied experiments; lived experience updates interests and confidence"],
        ],
      },
      callout: {
        title: "What it needs to be plugged into",
        body:
          "The platform only reaches its full value once it is connected to university systems: the teaching " +
          "system, the academic registry (year-one to year-four programme plans), the Career Center system " +
          "(advisor booking and Job & Internship), the public APIs of the university and each school or " +
          "department (subscribing to resource and event updates), and the counselling service system " +
          "(appointments and emergency contact) — among others.",
      },
      note:
        "International status, finances, caregiving duties, health and energy, commuting, language and " +
        "accessibility needs are not **a sixth category of person**. They are personal constraints every mode " +
        "must respect — injected into existing flows through pluggable Context Packs, not by cloning a new agent.",
      cards: [
        {
          title: "Career Center admin",
          body:
            "Grants and revokes publishing rights, runs the review queue and policy, configures connectors " +
            "and rotates credentials. Cannot read student profiles, reflections or calendars, and never sees who left which feedback.",
        },
        {
          title: "Publisher (society / lab / school)",
          body: "The Career Center admin console grants publishing rights to a department lead, who then creates and submits listings within that authorised organisation and validity window. Cannot publish directly, bypass review, or act for an organisation they don't hold.",
        },
        {
          title: "Career advisor",
          body: "Sees **only the meetings a student booked** and what they want to discuss, then sends up to five key recommendations. Reflections, grades and calendars return 403.",
        },
        {
          title: "Wellbeing coordinator",
          body: "Receives only the minimal outreach a student consented to or requested. No full calendar access, and capacity signals are never treated as a diagnosis.",
        },
      ],
    },
    {
      id: "value",
      kicker: "What you get",
      title: "Six things you won't get elsewhere",
      cards: [
        {
          title: "Four eligibility states, not yes/no",
          body:
            "A first-year looking at a third-year internship isn't silently filtered out. It's marked " +
            "future-eligible, with what to build this year. Four states: eligible now, future-eligible, " +
            "insufficient information, not applicable this round.",
        },
        {
          title: "Every suggestion states its reason",
          body: "Which gap, what evidence, why now. Each line of a goal breakdown opens onto the job posting it came from — not something a model invented.",
        },
        {
          title: "Browsing survives personalisation",
          body:
            "The plaza shows **every approved resource**; visibility is not decided by AI ranking. Any listing " +
            "can be asked \"why wasn't this recommended to me\", and the answer is a credential issued by the rules engine.",
        },
        {
          title: "Real capacity first, tasks second",
          body:
            "The calendar reads **busy/free by default, not event titles**. Before planning, the system counts " +
            "classes, existing commitments, sleep and meal protection blocks, discretionary time and buffer — " +
            "and only schedules into hours you genuinely have.",
        },
        {
          title: "A loop from recommendation to action",
          body: "Materials, calendar, reminders, status and fallbacks all connect; write a reflection afterwards and it settles into **growth evidence**.",
        },
        {
          title: "It won't just push you",
          body:
            "When sleep is being squeezed and load stays high, the system warns instead of adding more. " +
            "That guardrail chain uses **no language model at all** — thresholds decide, fixed templates speak.",
        },
      ],
    },
    {
      id: "memory",
      kicker: "It learns you",
      title: "What it remembers isn't what you clicked — it's why you changed your mind",
      body: [
        "A student uses this for four years or more. So the system has to remember completed courses and " +
          "projects, the directions you explicitly turned down and why, which activities were worth your time " +
          "and which weren't, the goal changes and trade-offs you made, your rhythm and energy preferences, " +
          "and which skills you already have and shouldn't be scheduled for again.",
      ],
      table: {
        head: ["Layer", "What it holds", "Update rule"],
        rows: [
          ["L0 Canonical profile", "The current valid state of studies, experience, outcomes, skills, goals, preferences, capacity and constraints", "Updated only by authoritative sources or your confirmation; every change leaves a change event"],
          ["L1 Episodic timeline", "Attended, applied, completed, dropped, feedback, plan versions", "**Append-only**; mistakes are handled with correction events, never by editing history"],
          ["L2 Semantic memory", "Interests, patterns and context distilled from experience", "Carries source, time, confidence and an expiry policy"],
          ["L3 Evidence & notes", "Your raw notes, work, certificates, reflection text and attachments", "Yours; not shared with the school by default"],
        ],
      },
      cards: [
        {
          title: "The rules memory follows",
          body:
            "Student's own words, system inference and external fact stay distinguishable — inference is " +
            "never dressed up as fact. When old and new conflict, the **timeline is preserved** and the update " +
            "**supersedes rather than silently overwrites**. A passing mood never becomes a permanent trait.",
        },
        {
          title: "You can always take it back",
          body: "Any memory can be searched, corrected, locked, deleted, exported or paused. Recall pulls the minimum context the current task needs — never your whole history.",
        },
        {
          title: "Reflection has three separate tracks",
          body:
            "What changed in you, what you want to keep long term, and whether the event delivered what it " +
            "promised are three different things. Mixed together, the school never receives a usable signal.",
        },
        {
          title: "It makes students actually reflect",
          body:
            "A reflection has to be bound to a specific object before it can exist, which rules out saying " +
            "nothing at length. Advisor meetings add one more turn: write and save your reflection first, " +
            "and only then do you see what the advisor wrote for you.",
        },
      ],
      note:
        "A deliberate split: personal mismatch and genuine low quality are separate. \"Too basic\" and " +
        "\"too hard\" become a personal fit tag that adjusts your own difficulty and does not **penalise the " +
        "event**. \"Overstated, thin content\" only lowers that occurrence's confidence once it clears a sample threshold, and then it goes to review.",
    },
    {
      id: "compare",
      kicker: "How this is different",
      title: "Others hand you a reply; we hand you a path",
      table: {
        head: ["Product type", "Their centre of gravity", "Where CampusPath differs"],
        rows: [
          ["LinkedIn", "Professional identity, network, jobs and content", "Connects courses, prerequisites, campus resources and student load into a long-range path: opportunities become campus actions"],
          ["Handshake", "Student jobs, internships, employers, careers events", "Doesn't stop at listing: composes courses, research, competitions, societies and internships into a dependency-aware capability path"],
          ["Career assessments", "Interests, values, occupational fit", "The assessment is only an input — the system keeps validating it through real practice instead of fixing you in place after one test"],
          ["Résumé / interview tools", "Résumé feedback, interview prep and mock rounds", "Covers the months or years of capability building and evidence gathering before the application stage"],
          ["General AI career coaches", "Conversational advice, résumé and career Q&A", "Real sources, eligibility states, tool calls, long-term memory, time constraints, an action loop and measurable evaluation"],
        ],
      },
      note:
        "The short version: others give you a reply. We give you a path that lands on your calendar, " +
        "traces back to its sources, keeps updating as you change, and returns its results to the school.",
    },
    {
      id: "how",
      kicker: "How it works",
      title: "A loop that actually closes — each side is the other's input",
      steps: [
        {
          title: "Connect and consent",
          body:
            "Link the student information system; authorise your calendar (busy/free only by default, " +
            "never event bodies). Only then does the system know what you are enrolled in and how much " +
            "time you actually have.",
        },
        {
          title: "Build your profile",
          body:
            "Upload a résumé; deterministic parsing files it straight into your profile overview, then a " +
            "drawer lists every added line so you can check it — and undo any of them on the spot. " +
            "International students can tick that status here, and a versioned Context Pack flows into " +
            "everything downstream.",
        },
        {
          title: "Goal studio",
          body:
            "Set a primary goal, a candidate goal and the split between them, then press Start planning. " +
            "Three stages run in the background: **gather live job postings → compare → decompose**. " +
            "The breakdown has three tiers:",
          bullets: [
            "**Soft skills —** communication, leadership, influence, teamwork;",
            "**Hard academics —** GPA and the GPA required in core courses;",
            "**Demonstrable assets —** competitions and awards, projects and papers, internships, " +
              "certificates and tooling.",
          ],
          tail:
            "Every line opens to the job posting it came from. You also get the **shared gaps** and the **fork " +
            "points** between your two goals — do the shared work first, and neither path loses.",
        },
        {
          title: "Discover",
          bullets: [
            "**Information plaza:** everything from the university, its schools, societies, associations, labs, " +
              "professors and corporate partners sits here, filtered by ten organiser categories plus theme, " +
              "year, eligibility, format and deadline. Expired listings move into their own group, clearly " +
              "marked — they never sit among things you can still sign up for, and they are never recommended.",
            "**For You:** drawn from your profile + goal breakdown + the preferences in your memory, and every " +
              "card states **why it was recommended to you**. The four eligibility states are visible on the card.",
          ],
        },
        {
          title: "Plan, then approve",
          body:
            "Anything you sign up for lands in the action centre. Four ranges — **next two weeks, a month, " +
            "a term, a year** — with lead times worked backwards automatically: a week to a month for major " +
            "competitions, one to two months for certifications, a year for language exams, each appearing " +
            "in the range it belongs to. **The draft comes to you in a dialog first**, stating what it was built " +
            "on (your goals, your profile, the preferences in your memory), and only lands on your calendar " +
            "once you approve. The calendar is a week/month grid and **is itself the editor**: move things, add " +
            "sleep and meal protection blocks, add buffers. Whether an edit triggers a re-plan is also your call.",
          bullets: [
            "You can also set the planning intensity yourself — light, balanced or ambitious — according to " +
              "your energy and how much free time you have.",
            "The action centre also **recommends electives**: required courses are loaded from the programme " +
              "plan and never recommended, while electives are matched to your profile, goals and the skills " +
              "you need — with the full course title, description, the original prerequisite text and a link " +
              "into the registry.",
          ],
        },
        {
          title: "Guardrails, with no language model",
          body:
            "Sleep is read **only from the window you declared** and whatever occupies it — nothing is inferred " +
            "when you haven't declared, and it says \"0 days covered\" rather than guessing. An empty **calendar " +
            "slot is never taken as evidence that you slept or exercised.** The judgement is pure counting " +
            "(these are the thresholds in the build): **an overloaded day** means under 7 hours of effective " +
            "sleep and over 11 hours of study or work; 10 such days in a rolling 14 raise the **first-tier " +
            "warning**, 20 in a rolling 28 **ask you to complete two scales**.",
          bullets: [
            "The two scales are the ISI (insomnia severity) and PSS-10 (perceived stress), which separate " +
              "\"late nights are a habit\" from \"this is academic pressure\" — the distinction matters, " +
              "because the support each needs is completely different.",
            "Mild → you are pointed at the counsellor you named yourself; moderate insomnia or high stress " +
              "→ you are guided to book a counselling slot.",
            "Above all of that sits a third tier: **an emergency button** that skips every queue and reaches " +
              "the counselling service directly (against groundless misuse: twice a term, and a third use " +
              "suspends it for a term — though the suspension notice still carries the hotline).",
          ],
          tail:
            "**At most two reminders**, visible only to the student, and by default they reach no institutional " +
            "console; any non-urgent outreach from the university needs your prior consent or your own request.",
        },
        {
          title: "Reflect and accumulate",
          body:
            "Write a reflection and rate four dimensions. Once written, the activity files itself as growth " +
            "evidence into your growth tracker, attached to the specific capability it evidences. " +
            "This is also where the north-star metric VGA (Verified Growth Actions) comes from — **it rewards " +
            "neither clicks nor saves nor sign-ups nor busyness**, only things actually completed with evidence left behind.",
        },
        {
          title: "Back to the university (the other half of the loop)",
          bullets: [
            "The Career Center console registers and monitors every source, with health per source, " +
              "a scheduled daily crawl and a one-click live refresh;",
            "Society leads, labs and professors submit through the publisher desk → the review queue → " +
              "and only then does it reach the plaza;",
            "An approved listing **carries its own QR code**, handed to the organiser and activated when the " +
              "event starts; attendees scan to check in;",
            "So the university gets real data: **who actually turned up** (check-in) and **how they rated it** " +
              "(anonymous four-dimension scores), among others;",
            "From which: which kinds of activity draw people, which are high quality, the real favourable " +
              "rate, **where the gaps are and which programmes are under-resourced**;",
            "Reports generate weekly / monthly / per term / per year, and can be generated on demand;",
            "Two months after an event its statistics freeze, and it is delisted and archived.",
          ],
        },
      ],
      note:
        "**The loop closes**: a student finds, among thousands of listings, the ones that match their goal → " +
        "takes part → reflects → and that becomes evidence driving the next round of planning; the same " +
        "feedback returns to the university, showing real demand and how it is shifting, so gaps get filled " +
        "and good activities get more resource. **Both sides gain, and each pushes the other.**",
    },
    {
      id: "tech",
      kicker: "Under the hood",
      title: "Two planes, contracts first: data the types forbid physically cannot flow",
      body: [
        "**The semantic plane:** six agents (orchestration, student context, academics, goal gaps, opportunity " +
          "extraction, path planning) — **the only layer permitted to call a model**.",
        "**The deterministic plane:** nine services with no language model anywhere (rules and constraints, " +
          "capacity and calendar, wellbeing copy, state and memory, actions and consent, anonymous aggregation, " +
          "monitoring and re-planning, publishing review and audit, connectors and catalog). Every judgement, " +
          "threshold, eligibility decision and capacity calculation lives here — reproducible and auditable.",
        "Every exchange between the two planes is shaped by a **data contract type**.",
      ],
      table: {
        head: ["#", "Six architectural red lines — each has a test, and a failing test fails the build"],
        rows: [
          ["1", "The planning agent is the only one that makes trade-offs; the rest emit facts and candidates, and their output types have no ranking field at all"],
          ["2", "Wellbeing guardrails use no language model — thresholds judge, fixed templates speak; importing a model SDK at build time is forbidden"],
          ["3", "Calendar credentials never enter any model context — they stop at the capacity service, enforced by the type layer"],
          ["4", "The extraction agent has exactly two whitelisted tools; external content arrives as data and is never concatenated into a system prompt"],
          ["5", "Every plan item must carry a validation credential issued by the rules engine, or the API rejects it"],
          ["6", "There is no type-level path from private reflection text to school aggregates — not \"we don't send it\", but it cannot be sent"],
        ],
      },
      cards: [
        {
          title: "Where it sits in Google's stack",
          body:
            "ADK handles agents, tools, sequential and parallel workflows, and memory; two runtimes deploy to " +
            "Vertex AI Agent Engine; Cloud Run runs the student app API, adapters and scheduled jobs; the Moodle " +
            "sandbox connects through a **read-only MCP** we built; the calendar uses per-scope Workspace API grants.",
        },
        {
          title: "The model is replaceable (an architectural commitment)",
          body:
            "Every model call in the system converges on a **single adapter**, and the agent layer depends on an " +
            "abstract interface with one method. Changing model version is deployment config, not code. Changing " +
            "vendor — the university's own model, another cloud, an on-premise deployment — means writing one " +
            "implementation of that interface, with zero changes to the six agents, the nine deterministic " +
            "services, the contract types or the red-line tests.",
        },
        {
          title: "The deterministic plane doesn't move",
          body:
            "Eligibility, capacity, health thresholds and privacy suppression — the parts that most need to be " +
            "stable and auditable — **never call a model** in the first place, so no model change touches them. " +
            "The product's value doesn't rest on any one model. Which model to run is the university's decision.",
        },
      ],
    },
    {
      id: "control",
      kicker: "You're in charge",
      title: "The system ranks; you decide",
      cards: [
        {
          title: "Student autonomy",
          body:
            "You can reject, edit, pause or lock any path. Writing to your calendar, sending a message or " +
            "applying to something all need your explicit approval. Students who are still exploring are never " +
            "pushed to commit to a single career goal early.",
        },
        {
          title: "Your profile, your confirmation",
          body:
            "Certificates, LMS records and agent reflections can propose profile updates, but cannot rewrite " +
            "your profile without telling you. Self-reported, system-observed and source-verified stay labelled apart.",
        },
        {
          title: "Evidence outranks model confidence",
          body: "Eligibility, deadlines and programme requirements must point at a source. When it's uncertain, the answer is \"needs confirmation\", not an invented one.",
        },
        {
          title: "The school sees aggregates and cannot drill down",
          body:
            "Any cell below the sample threshold shows Insufficient evidence and is suppressed — never a number " +
            "that looks precise. There is no interface for \"show me the students behind this figure\", and the backend offers no such query.",
        },
      ],
      note:
        "What this product is not: a success predictor guaranteeing entry anywhere; an automated decision system " +
        "making irreversible life choices for a student; a system measuring growth by activity count or résumé " +
        "length; a medical device, psychological diagnostic or suicide-risk predictor; or a monitoring tool that " +
        "reports on students from calendar gaps alone.",
    },
    {
      id: "numbers",
      kicker: "The real numbers",
      title: "Measured against HKUST's public data — every figure below is an observed value",
      table: {
        head: ["Item", "Value"],
        rows: [
          ["Course catalog, really scraped", "1,534 courses across 58 subjects, prerequisite expressions kept as source text"],
          ["Source registry", "93 sources, 85 of them genuinely scraped and 8 synthetic for demos — distinguishable at a glance in the UI"],
          ["Data contract types", "177 types (92 paths / 111 operations); frontend, backend and agents all generate from the same contract"],
          ["Blocker checks", "13 of 13 passing (a violation is a failure)"],
          ["Quantified targets", "11 of 12 met — the one that isn't is flagged red in the report, not hidden"],
          ["Comparison baselines", "5, all deterministic and reproducible"],
        ],
      },
      note:
        "Judgement metrics must produce byte-identical results across two runs, and the gold labels are " +
        "implemented separately from the engine on purpose — generating labels with the same code you evaluate " +
        "with is marking your own homework. Student, grade, calendar, opportunity and submission data are all " +
        "synthetic, and every page is marked Synthetic / Demo Data; entries verified as real public sources carry an Official marker instead.",
      cards: [
        {
          title: "What isn't built yet, stated here too",
          body:
            "The current build centres on the undergraduate-to-employment line. A second career path pack " +
            "(doctorate into industry) has an interface reserved but is not delivered — the frontend neither " +
            "shows nor claims it. The international student Context Pack is installed but marked pending policy " +
            "review, so until it clears, every evaluation returns \"needs confirmation\". Real calendar OAuth uses fixtures in the demo.",
        },
        {
          title: "We don't claim what we have no baseline for",
          body:
            "Nothing here claims improved employment or academic outcomes — there is no real baseline to claim it against. Every target above is a pilot hypothesis.",
        },
      ],
    },
  ],
  ctaBand: {
    title: "Open your own path?",
    body: "Start as a student with a single goal. Walk goal → discover → plan → approve → reflect, and leave with a path you can trace.",
    note: "The demo runs on synthetic data — you can always start over.",
  },
  footer: {
    synthetic: "Synthetic / Demo Data · student, grade, calendar and opportunity data are all synthetic",
    note: "Drawn from the product overview document (2026-08-10). The full specification defines the product; where this page and the implementation disagree, the implementation wins.",
  },
};
