# vPIN 前端 UI 设计规范（草案 v0.1）

> **目的**：在编码美化前，明确面向用户、信息架构与视觉风格。  
> **参考**：[蚂蚁密算](https://www.misuan.com/) 文档与控制台类产品（蚂蚁隐私计算服务平台 AntPPC、[隐语 SecretFlow 教学平台](https://www.secretflow.org.cn/zh-CN/community/course-cooperation)）。  
> **产品依据**：[`cp-snark-分层证明与RLC设计定稿.md`](./cp-snark-分层证明与RLC设计定稿.md)、`vpin-平台架构`、vPIN 论文。γ **必须在客户端**；证明覆盖范围须与定稿 §6 一致。

---

## 1. 产品定位（与蚂蚁密算的对照）

| 维度 | 蚂蚁密算 / AntPPC | vPIN（VDS-VPIN 工作台） |
|------|-------------------|-------------------------|
| 核心场景 | 多方数据协作：联邦学习、MPC 建模、PSI、SCQL 联合分析 | **单方客户端**持有密钥，对**远程模型**做隐私推理，并**本地验证** CP-SNARK |
| 信任模型 | 多机构对等、数据不出域 | 客户端 ↔ 推理服务端；验证方挑战 γ **必须在客户端** |
| 典型路径 | 项目 → 节点/数据授权 → 建模 → 投产 → 监控 | Setup → 模型承诺 → 数据配置 → 同态推理（含截断）→ 挑战 → 证明 → 验证 |
| 界面形态 | Web 管理控制台 + 项目子控制台（脚本/任务/数据分区） | **桌面客户端**（Tauri）+ 研究工作台，偏「实验会话」而非「多租户项目」 |
| 价值主张 | 数据可用不可见、合规流通、一站式建模 | **可验证的**隐私推理：密文计算 + 密码学证明可本地核验 |

**可借鉴（AntPPC 文档与控制台共性）**  
- 左侧主导航 + 顶栏上下文（项目/环境）  
- **步骤化向导**降低密码学门槛（参考多方安全建模「端到端」叙事）  
- **任务/脚本/结果**三栏式工作区（参考 SCQL 控制台：脚本文件 / 建模数据 / 任务管理）  
- 安全状态、证书、预算类指标 **卡片化、可扫读**  
- 术语旁附「说明/文档」入口（密算文档站风格）

**应差异化（避免做成 AntPPC 换皮）**  
- 不做「机构/节点/多方项目」为主轴，改为 **「推理会话 Session」** 为主轴  
- 突出 **协议阶段进度**（论文 6 步），而非通用 ML Pipeline  
- 桌面端：强调 **本地验证成功/失败** 的确定性反馈（客户端独有能力）  
- 视觉略偏 **研究型工具**（信息密度可控、可展开技术细节），而非纯企业运营大屏

---

## 2. 面向用户分析

### 2.1 核心用户（Primary）

#### A. 隐私 ML 研究员 / 博士生
- **目标**：复现论文实验、对比 AHE+CP-SNARK 行为、调试截断与证明  
- **特征**：熟悉 Python/Rust，能读协议文档；容忍一定技术细节  
- **痛点**：Mock 与真实协议状态不一致；不清楚当前处于 Setup 还是 Verify  
- **UI 诉求**：协议时间线、原始日志、witness/证明产物下载、可重复实验

#### B. 密码学 / 系统实现工程师
- **目标**：对接 `vpin-backend`、Tauri `invoke`、WSS 会话  
- **特征**：关心 API、状态机、错误码，而非营销文案  
- **痛点**：前后端阶段枚举不对齐；UI 掩盖失败原因  
- **UI 诉求**：每步 API 状态、连接/TLS/AHE 曲线 ID、可复制的 session_id

### 2.2 次要用户（Secondary）

#### C. 安全审计 / 合规查看者（只读）
- **目标**：查看验证报告、证明覆盖范围、隐私机制是否启用  
- **特征**：非日常操作；需要 **审计友好** 的只读视图与导出  
- **UI 诉求**：验证报告页、时间戳、算法/曲线版本、**证明覆盖范围明示**（架构文档要求不得过度宣称）

#### D. 教学实验学生（对标 SecretNote / 密算实践课）
- **目标**：按实验手册完成一次完整推理+验证  
- **特征**：密码学背景参差；需强引导  
- **UI 诉求**：向导模式、术语悬浮解释、示例模型/样例数据一键加载

### 2.3 非目标用户（本期不做优先适配）
- 多机构数据运营人员（AntPPC「机构资源管理员」）  
- 无技术背景的业务分析师（SCQL 自助分析）  
- 移动端轻量查询（桌面 Tauri 优先）

### 2.4 用户旅程（MVP 主路径）

```text
研究员打开客户端
  → 工作台：AHE 参数/预计算表就绪（Setup）
  → 模型中心：选择远程模型，校验 cm_W
  → 新建任务：上传/配置输入、隐私机制（AHE ∧ CP-SNARK）
  → 任务监控：会话阶段 + 截断轮次 + 资源
  → 安全中心 / 验证报告：本地 Verify 结果 + 证明摘要
```

与 AntPPC「项目 → 数据 → 建模 → 任务」类比，vPIN 是 **「会话 → 模型绑定 → 输入 → 推理 → 验证」**。

---

## 3. 信息架构（IA）

### 3.1 一级导航（已定方向，微调命名）

| 导航 | 职责 | 对标 AntPPC |
|------|------|-------------|
| **工作台** | 总览、Setup、快捷入口、当前会话摘要 | 管理控制台首页 |
| **模型中心** | 模型目录、cm_W、上传/注册 | 数据/模型资源 |
| **推理任务** | 新建任务（向导）、任务监控 | 建模任务 + 任务管理 |
| **安全中心** | 运行状态、验证报告、隐私预算（若启用 DP） | 数据安全配置 + 审计 |

### 3.2 二级模式

1. **向导模式（Wizard）**：新建任务、首次 Setup —— 面向学生/初次用户  
2. **控制台模式（Console）**：任务监控、日志 —— 面向研究员/工程师  
3. **审计模式（Audit）**：验证报告、只读导出 —— 面向审计  

同一页面可通过「简单 / 高级」开关切换信息密度（借鉴密算平台「可视化 vs IDE」分层，见 [AntPPC 产品功能](https://cn.aliyun.com/product/applicationservice/antppc)）。

### 3.3 全局组件（必须具备）

- **协议进度条**：Setup → Commit(W,x) → Infer → Challenge → Prove → Verify  
- **会话上下文条**：session_id、模型指纹、AHE 曲线、后端地址、连接状态  
- **安全状态徽章**：AHE 已启用 / CP-SNARK 已验证 / 证明覆盖范围（文案需合规）  
- **统一通知**：截断请求待处理、验证失败、网络断开  

---

## 4. 视觉风格定义

### 4.1 风格关键词

**可信 · 精密 · 冷静 · 可验证**

- **可信**：大面积留白、清晰层级，避免「黑客终端」纯黑风格  
- **精密**：等宽字体用于 session_id、哈希、cm_W；数据对齐栅格  
- **冷静**：低饱和背景 + 单一主色强调操作与安全态  
- **可验证**：成功/失败/进行中三色体系统一，**禁止仅用颜色**（需图标+文案）

### 4.2 与蚂蚁密算的视觉对齐与差异

| 元素 | 密算/AntPPC 倾向 | vPIN 建议 |
|------|------------------|-----------|
| 主色 | 企业蓝、阿里云系 | **深蓝 #0F172A（导航）+ 操作蓝 #2563EB**（与现 Naive 主题一致） |
| 背景 | 浅灰白控制台 | **浅渐变 `#F8FAFC → #EEF2FF`**，内容区白卡片 |
| 导航 | 白底或浅侧栏 | **深色侧栏**（研究工具感）+ 浅色内容区（对标 SecretPad/控制台分区） |
| 圆角 | 中等 4–8px | **8–14px**，卡片 14px，按钮 8–10px |
| 阴影 | 轻 shadow | **轻 elevation**，hover 略抬升（避免过重玻璃拟态） |
| 图标 | 线性图标 | **线性图标**（Ionicons / 自定义 SVG），安全类用 shield/check/lock |

### 4.3 设计 Token（实现用）

```css
/* 色彩 */
--color-primary:        #2563EB;
--color-primary-dark:   #1D4ED8;
--color-nav-bg:         #0F172A;
--color-nav-text:       #94A3B8;
--color-nav-active:     #93C5FD;

--color-success:        #16A34A;   /* Verify 通过 */
--color-warning:        #D97706;   /* 进行中 / 待截断 */
--color-error:          #DC2626;   /* Verify 失败 */
--color-info:           #0891B2;   /* AHE / 密码学信息 */

--color-surface:        #FFFFFF;
--color-bg:             #F8FAFC;
--color-border:         #E2E8F0;
--color-text-primary:   #0F172A;
--color-text-secondary: #64748B;

/* 字体 */
--font-sans:  "Inter", "PingFang SC", "Microsoft YaHei", sans-serif;
--font-mono:  ui-monospace, "Cascadia Code", Consolas, monospace;

/* 字号 */
--text-xs:   11px;   /* 徽章、辅助 */
--text-sm:   13px;   /* 表格、说明 */
--text-base: 14px;   /* 正文 */
--text-lg:   16px;   /* 小标题 */
--text-xl:   20px;   /* 页面标题 */
--text-2xl:  24px;   /* 工作台 Hero */

/* 间距（4px 基准） */
--space-1: 4px;  --space-2: 8px;  --space-3: 12px;
--space-4: 16px; --space-5: 24px; --space-6: 32px;

/* 布局 */
--header-height: 56px;
--sidebar-width: 240px;
--content-max-width: 1200px;
```

### 4.4 组件规范（Naive UI 映射）

| 场景 | 组件 | 说明 |
|------|------|------|
| 主按钮 | `NButton type="primary"` | 下一步、开始推理、确认验证 |
| 危险/中止 | `NButton type="error"` | 中止会话 |
| 次要 | `secondary` / `tertiary` | 下载密钥、导出报告 |
| 状态 | `NTag` + `NAlert` | Mock/正式、验证通过/失败 |
| 步骤 | `NSteps` | 新建任务、协议总览 |
| 数据 | `NDataTable` | 模型列表、任务列表 |
| 详情 | `NDescriptions` | 验证报告、模型元数据 |
| 进度 | `NProgress` | 推理阶段、截断轮次 |
| 技术日志 | `NCollapse` / `NCode` | 高级模式展开 |

主题覆盖集中在 `src/theme/naive-theme.js`，**不与** `public/vpin/css/theme.css` 双轨跑偏——最终应合并为单一 Token 源（建议后续抽到 `src/theme/tokens.css` 并给静态页引用构建产物）。

---

## 5. 关键页面 wire 说明

### 5.1 工作台
- **Hero**：产品名 + 一句话（可验证的隐私神经网络推理）  
- **协议步骤条**（当前完成到第几步）  
- **Setup 区**：AHE 密钥、预计算表（卡片并列，状态 Tag）  
- **快捷入口**：模型中心 / 新建任务 / 最近会话  

### 5.2 模型中心（对标「建模数据」区）
- 左：筛选（网络类型 A–E、精度、是否含 CP-SNARK）  
- 中：模型列表 + **cm_W 指纹** 列  
- 右（可选）：选中模型详情、承诺校验结果  

### 5.3 新建任务（向导，对标 AntPPC 端到端）
1. 选择模型（强制 cm_W 校验）  
2. 数据与预处理（定点精度、上传）  
3. 隐私机制（AHE / CP-SNARK 多选 + 说明）  
4. 确认并创建会话  

### 5.4 任务监控（对标「任务管理」）
- 会话列表：阶段、进度、耗时  
- 详情：截断轮次时间线、WSS 事件、资源占用  
- **待处理**：客户端截断请求高亮（vPIN 特有，AntPPC 无直接对应）  

### 5.5 安全中心 / 验证报告（对标「数据安全配置」+ 审计）
- 卡片：TEE（若未来）、AHE 曲线、CP-SNARK 状态  
- 验证报告：γ 摘要、verify 结果、**证明覆盖范围免责声明**  
- 导出 PDF/JSON  

---

## 6. 文案与合规 tone

- 主标语建议：**「隐私推理，结果可验证」**（对应论文 verifiable）  
- 避免：「绝对安全」「完全零泄露」—— 与架构文档「证明覆盖范围」一致  
- Mock 数据必须带 **`Mock` / `演示`** 标签（现首页已有，需全局统一）  
- 术语首次出现配简短 tooltip：AHE、CP-SNARK、cm_W、截断  

---

## 7. 实施路线图（设计 → 开发）

| 阶段 | 内容 | 产出 | 状态 |
|------|------|------|------|
| **D1** | 用户与风格定稿 | 本文档 | ✅ |
| **D2** | Token 单一源 + Naive 主题对齐 | `public/vpin/css/tokens.css`、`naive-theme.js` | ✅ |
| **D3** | 壳层：协议条 + 会话条 + session composable | `ProtocolProgressBar`、`SessionContextBar`、`useProtocolSession` | ✅ 初版 |
| **D3.5** | 隐语云模板对照 UI（浅色侧栏、任务列表/详情、占位 Tab） | 见 [模板对照实现说明](./vpin-frontend-模板对照实现说明.md) | ✅ |
| **D3.6** | 隐私样板间：服务须知→部署→排队→图像推理→密文抽屉 | `views/demo/*`、`useDemoStore`、`PrivacyEffectDrawer` | ✅ |
| **D4** | 向导化「新建任务」 | `TaskWizardView.vue` | 待做 |
| **D5** | 任务监控 / 验证报告 Vue 化 | 对接 backend API | 待做 |
| **D6** | 简单/高级模式 + 无障碍 | 键盘导航、aria-label | 待做 |

---

## 8. 参考链接

- [蚂蚁密算文档](https://www.misuan.com/zh-CN/docs/llm/latest/dbgofg2f8rlmqf93)  
- [蚂蚁隐私计算服务平台 AntPPC](https://cn.aliyun.com/product/applicationservice/antppc)  
- [AntPPC 多方安全分析控制台说明](https://help.aliyun.com/document_detail/364172.html)  
- [隐语 · 蚂蚁密算实践课程（SecretNote / 教学场景）](https://www.secretflow.org.cn/zh-CN/community/course-cooperation)  
- [Naive UI 主题定制](https://www.naiveui.com/zh-CN/os-theme/docs/customize-theme)

---

**文档状态**：草案 v0.1，待产品/研发评审后进入 D2 视觉稿或 Figma（可选）。
