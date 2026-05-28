import {
  Presentation,
  PresentationFile,
} from "file:///C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs";

const OUT_PATH = "/home/kaikai/vrp-research/s10479-018-3037-2_summary_presentation.pptx";
const W = 1280;
const H = 720;

const C = {
  bg: "#F3EEDD",
  ink: "#17313B",
  sub: "#53666D",
  teal: "#1D6B72",
  teal2: "#2D8C95",
  red: "#BF5A45",
  sand: "#E7D7B8",
  panel: "#FFF9EC",
  line: "#D2C3A5",
  white: "#FFFFFF",
};

const FONT = {
  title: "Microsoft YaHei",
  body: "Microsoft YaHei",
};

function addShape(slide, geometry, left, top, width, height, fill, line = null) {
  return slide.shapes.add({
    geometry,
    position: { left, top, width, height },
    fill,
    line: line ?? { width: 0, fill: fill },
  });
}

function addText(slide, text, opts = {}) {
  const shape = slide.shapes.add({
    geometry: opts.geometry || "rect",
    position: {
      left: opts.left ?? 0,
      top: opts.top ?? 0,
      width: opts.width ?? 200,
      height: opts.height ?? 60,
    },
    fill: opts.fill ?? "#00000000",
    line: opts.line ?? { width: 0, fill: "#00000000" },
  });
  shape.text = text;
  shape.text.fontSize = opts.fontSize ?? 24;
  shape.text.typeface = opts.typeface ?? FONT.body;
  shape.text.color = opts.color ?? C.ink;
  shape.text.bold = Boolean(opts.bold);
  shape.text.alignment = opts.align ?? "left";
  shape.text.verticalAlignment = opts.valign ?? "top";
  shape.text.insets = opts.insets ?? { left: 6, right: 6, top: 4, bottom: 4 };
  if (opts.autoFit) shape.text.autoFit = opts.autoFit;
  return shape;
}

function bg(slide, title, kicker, page) {
  slide.background.fill = C.bg;
  addShape(slide, "rect", 0, 0, W, 78, C.ink);
  addShape(slide, "rect", 0, 78, W, 2, C.teal2);
  addShape(slide, "roundRect", 980, -120, 360, 360, "#E8DDC1", { width: 0, fill: "#E8DDC1" });
  addShape(slide, "ellipse", 1090, 38, 110, 110, "#F6EFDF", { width: 0, fill: "#F6EFDF" });
  addText(slide, kicker, {
    left: 60, top: 22, width: 230, height: 22, fontSize: 16, color: "#C5DED9", bold: true,
  });
  addText(slide, title, {
    left: 60, top: 92, width: 860, height: 52, fontSize: 30, bold: true, color: C.ink,
  });
  addText(slide, `0${page}`.slice(-2), {
    left: 1168, top: 650, width: 60, height: 32, fontSize: 22, bold: true, color: C.teal, align: "right",
  });
  addShape(slide, "rect", 60, 650, 1040, 1.5, C.line, { width: 0, fill: C.line });
}

function bulletLines(items) {
  return items.map((x) => `• ${x}`).join("\n");
}

function card(slide, { left, top, width, height, title, body, accent = C.teal }) {
  addShape(slide, "roundRect", left, top, width, height, C.panel, { width: 1.2, fill: C.line });
  addShape(slide, "rect", left, top, 6, height, accent, { width: 0, fill: accent });
  addText(slide, title, {
    left: left + 20, top: top + 14, width: width - 34, height: 28, fontSize: 19, bold: true,
  });
  addText(slide, body, {
    left: left + 20, top: top + 46, width: width - 34, height: height - 58, fontSize: 15, color: C.sub,
  });
}

function metric(slide, { left, top, width, height, value, label, accent = C.red }) {
  addShape(slide, "roundRect", left, top, width, height, C.white, { width: 1, fill: "#DCCFB1" });
  addText(slide, value, {
    left: left + 18, top: top + 12, width: width - 28, height: 34, fontSize: 28, bold: true, color: accent,
  });
  addText(slide, label, {
    left: left + 18, top: top + 52, width: width - 28, height: height - 56, fontSize: 14, color: C.sub,
  });
}

function flowBox(slide, { left, top, width, height, title, body, fill = "#F8F2E4" }) {
  addShape(slide, "roundRect", left, top, width, height, fill, { width: 1.2, fill: C.line });
  addText(slide, title, {
    left: left + 18, top: top + 14, width: width - 28, height: 28, fontSize: 18, bold: true,
  });
  addText(slide, body, {
    left: left + 18, top: top + 48, width: width - 28, height: height - 60, fontSize: 15, color: C.sub,
  });
}

function arrow(slide, left, top, width, height, text) {
  addShape(slide, "rightArrow", left, top, width, height, C.teal2, { width: 0, fill: C.teal2 });
  addText(slide, text, {
    left, top: top + 7, width, height: height - 10, fontSize: 14, bold: true, color: C.white, align: "center",
  });
}

const presentation = Presentation.create({ slideSize: { width: W, height: H } });

presentation.theme.colorScheme = {
  name: "paper-summary",
  themeColors: {
    accent1: C.teal,
    accent2: C.red,
    bg1: C.bg,
    tx1: C.ink,
    bg2: C.panel,
    tx2: C.sub,
  },
};

// Slide 1
{
  const slide = presentation.slides.add();
  slide.background.fill = C.ink;
  addShape(slide, "ellipse", 880, -120, 500, 500, "#244A56", { width: 0, fill: "#244A56" });
  addShape(slide, "ellipse", 980, 60, 260, 260, "#2B6A72", { width: 0, fill: "#2B6A72" });
  addShape(slide, "rect", 60, 86, 86, 8, C.sand);
  addText(slide, "论文重点提炼与汇报版演示", {
    left: 60, top: 118, width: 600, height: 42, fontSize: 22, color: "#D9E7E3", bold: true,
  });
  addText(slide, "灾后多周期道路修复与救援物流优化", {
    left: 60, top: 184, width: 710, height: 120, fontSize: 36, color: C.white, bold: true,
  });
  addText(slide, "基于论文《Post-disaster multi-period road network repair: work scheduling and relief logistics optimization》", {
    left: 60, top: 314, width: 760, height: 54, fontSize: 18, color: "#D6E2DF",
  });
  addShape(slide, "roundRect", 60, 430, 660, 150, "#F6EFDF", { width: 0, fill: "#F6EFDF" });
  addText(slide, "一句话结论", {
    left: 88, top: 452, width: 180, height: 26, fontSize: 18, bold: true, color: C.teal,
  });
  addText(slide, "这篇论文证明：把“修路排班”和“救援配送”联动优化，能在灾后黄金 72 小时内更快恢复网络可达性，并支持更公平、可执行的物资投送。", {
    left: 88, top: 490, width: 590, height: 68, fontSize: 20, color: C.ink,
  });
  addText(slide, "来源文件：s10479-018-3037-2.pdf", {
    left: 60, top: 640, width: 360, height: 24, fontSize: 14, color: "#C7D6D2",
  });
  slide.speakerNotes.setText("封面。重点是把论文的学术表达翻译成管理层可理解的价值陈述。");
}

// Slide 2
{
  const slide = presentation.slides.add();
  bg(slide, "执行摘要", "EXECUTIVE SUMMARY", 2);
  card(slide, {
    left: 60, top: 164, width: 272, height: 178,
    title: "问题",
    body: "灾后物资未必短缺，但道路中断会让供给到不了需求点；单独做道路修复或单独做物流分配，都可能造成联动失效。",
  });
  card(slide, {
    left: 354, top: 164, width: 272, height: 178,
    title: "方法",
    body: "论文提出多周期双层规划：上层安排维修队修复顺序以提升累计可达性，下层在该约束下做物资分配与运输路径优化。",
    accent: C.red,
  });
  card(slide, {
    left: 648, top: 164, width: 272, height: 178,
    title: "证据",
    body: "作者在随机生成网络与汶川地震案例上验证模型；给出更新频率、网络拓扑差异和维修队配置的敏感性结论。",
  });
  card(slide, {
    left: 942, top: 164, width: 278, height: 178,
    title: "结论",
    body: "方法在应急响应时限内可求得可用方案，并指出 8 或 12 小时的信息更新节奏更现实，城乡网络策略也应区别设计。",
    accent: C.red,
  });
  metric(slide, { left: 60, top: 390, width: 180, height: 120, value: "72h", label: "研究采用灾后黄金 72 小时作为规划期" });
  metric(slide, { left: 258, top: 390, width: 180, height: 120, value: "14.93%", label: "汶川案例中，规划期内修复完成度提升" });
  metric(slide, { left: 456, top: 390, width: 180, height: 120, value: "104.7s", label: "汶川案例在 8 线程笔记本上的求解时间" });
  metric(slide, { left: 654, top: 390, width: 180, height: 120, value: "8/12h", label: "论文建议的较优信息更新周期" });
  addShape(slide, "roundRect", 860, 390, 360, 220, "#EFE4CA", { width: 0, fill: "#EFE4CA" });
  addText(slide, "管理含义", {
    left: 886, top: 414, width: 160, height: 28, fontSize: 19, bold: true,
  });
  addText(slide, bulletLines([
    "先修“能快速重连供需节点”的断点，而不是平均派工",
    "更新过快会增加计算与执行压力，过慢又会错过窗口",
    "农村网络要提高冗余度，城市网络要增加维修队规模",
  ]), {
    left: 886, top: 454, width: 300, height: 132, fontSize: 15, color: C.sub,
  });
  slide.speakerNotes.setText("摘要页对应论文摘要、引言与结论。");
}

// Slide 3
{
  const slide = presentation.slides.add();
  bg(slide, "问题为何必须联动考虑", "PROBLEM FRAMING", 3);
  addText(slide, "论文的核心判断：真正的瓶颈是“道路可达性”，不是单纯的物资总量。", {
    left: 60, top: 152, width: 1020, height: 34, fontSize: 22, bold: true,
  });
  flowBox(slide, {
    left: 60, top: 228, width: 260, height: 176,
    title: "道路受损",
    body: "灾后节点/路段被阻断，旅行时间大幅增加，部分需求点暂时不可达。",
  });
  arrow(slide, 332, 284, 86, 40, "导致");
  flowBox(slide, {
    left: 430, top: 228, width: 260, height: 176,
    title: "配送失灵",
    body: "物资、车辆和路线安排即使充分，也可能因为路径不存在或代价过高而无法兑现。",
    fill: "#F6E7E0",
  });
  arrow(slide, 702, 284, 86, 40, "倒逼");
  flowBox(slide, {
    left: 800, top: 228, width: 420, height: 176,
    title: "必须做联动优化",
    body: "上层决定修哪条、何时修、由谁修；下层同步调整供给点分配与运输路径，避免“两张表各管一半”。",
  });
  card(slide, {
    left: 60, top: 450, width: 560, height: 154,
    title: "上层决策主体：应急指挥中心（ECC）",
    body: "目标是提升规划期内的累计网络可达性，核心动作包括受损节点分配、维修队路由和多周期修复顺序。",
  });
  card(slide, {
    left: 650, top: 450, width: 570, height: 154,
    title: "下层决策主体：配送中心管理者",
    body: "在给定修复策略下，追求更公平的物资满足度，同时压缩配送总耗时，并随网络状态变化周期性调整。",
    accent: C.red,
  });
  slide.speakerNotes.setText("对应引言与第3节问题定义。强调上下层职责分离但目标耦合。");
}

// Slide 4
{
  const slide = presentation.slides.add();
  bg(slide, "模型与求解方法", "MODEL AND ALGORITHM", 4);
  flowBox(slide, {
    left: 60, top: 170, width: 338, height: 220,
    title: "上层目标",
    body: bulletLines([
      "按周期安排维修队与修复顺序",
      "最大化规划期内累计可达性 Z(X,T)",
      "优先恢复供需节点之间的连通性",
    ]),
  });
  flowBox(slide, {
    left: 470, top: 170, width: 338, height: 220,
    title: "下层目标",
    body: bulletLines([
      "最大化最小满足度（公平分配）",
      "最小化物资送达总时间",
      "在每个周期根据网络状态重算路径",
    ]),
    fill: "#F6E7E0",
  });
  flowBox(slide, {
    left: 880, top: 170, width: 340, height: 220,
    title: "求解策略",
    body: bulletLines([
      "MRSD 处理公平分配",
      "稳态并行遗传算法 HSSPGA 处理上层复杂组合优化",
      "适配中大规模、不同拓扑的网络实例",
    ]),
  });
  arrow(slide, 400, 255, 56, 34, "约束");
  arrow(slide, 812, 255, 56, 34, "求解");
  addShape(slide, "roundRect", 60, 446, 1160, 152, "#EADFC6", { width: 0, fill: "#EADFC6" });
  addText(slide, "关键建模元素", {
    left: 86, top: 470, width: 180, height: 30, fontSize: 20, bold: true,
  });
  addText(slide, bulletLines([
    "规划期固定为 72 小时；每个周期长度由 η 决定，代表信息互换/更新节奏。",
    "累计可达性同时考虑救援物流与普通交通流，并用权重 ρ 调整二者相对重要性。",
    "作者将问题建模为多周期双层规划，指出其本质上是 NP-hard，难以用精确算法快速求解。",
  ]), {
    left: 86, top: 512, width: 1090, height: 76, fontSize: 16, color: C.sub,
  });
  slide.speakerNotes.setText("对应第4节与第5节。简化公式，仅保留管理层真正需要的逻辑。");
}

// Slide 5
{
  const slide = presentation.slides.add();
  bg(slide, "证据一：数值实验与敏感性分析", "EVIDENCE FROM COMPUTATIONAL TESTS", 5);
  metric(slide, { left: 60, top: 164, width: 200, height: 118, value: "4 组", label: "从小到超大规模的实例集合 S1-S4" });
  metric(slide, { left: 278, top: 164, width: 200, height: 118, value: "180", label: "每组组合实例数量" });
  metric(slide, { left: 496, top: 164, width: 200, height: 118, value: "3 / 4 / 5", label: "γ 表示稀疏、混合、城市型网络" });
  metric(slide, { left: 714, top: 164, width: 200, height: 118, value: "5%-50%", label: "ϑ 表示网络受损比例" });
  metric(slide, { left: 932, top: 164, width: 288, height: 118, value: "4 / 8 / 12 / 24h", label: "η 表示信息更新周期设定" });
  card(slide, {
    left: 60, top: 330, width: 360, height: 220,
    title: "发现 1：更新频率最敏感",
    body: "η 越小，意味着更频繁地更新修复与配送策略，通常能获得更细致的响应，但计算时间显著上升。论文指出 η 的影响大于受损比例 ϑ。",
  });
  card(slide, {
    left: 450, top: 330, width: 360, height: 220,
    title: "发现 2：网络类型决定策略差异",
    body: "农村网络更稀疏、替代路径更少，因此被修复的受损节点比例通常低于城市与混合网络；冗余度是关键短板。",
    accent: C.red,
  });
  card(slide, {
    left: 840, top: 330, width: 380, height: 220,
    title: "发现 3：可执行建议已经出现",
    body: "作者综合实验后建议：信息更新以每天 2-3 次更现实，即 8 小时或 12 小时；城市区域则应增配道路维修队伍。",
  });
  addText(slide, "论文的价值不只在“能解”，还在于给出了应急响应中的参数选择建议。", {
    left: 60, top: 592, width: 860, height: 26, fontSize: 18, bold: true, color: C.teal,
  });
  slide.speakerNotes.setText("对应第6节和结论段。");
}

// Slide 6
{
  const slide = presentation.slides.add();
  bg(slide, "证据二：汶川地震案例", "WENCHUAN CASE", 6);
  addShape(slide, "roundRect", 60, 154, 500, 458, "#F7F0E1", { width: 1, fill: C.line });
  addText(slide, "案例输入规模", {
    left: 86, top: 180, width: 180, height: 28, fontSize: 21, bold: true,
  });
  addText(slide, bulletLines([
    "3 个维修工作站/供给节点：都江堰、彭州、什邡",
    "35 个需求节点，16 个受损路段节点",
    "车辆分为 4 类，容量从 5 吨到 20 吨",
    "维修队能力统一，按 0.5 km/h 估算修复时长",
    "数据来自统计年鉴、交通部门和遥感/航拍信息",
  ]), {
    left: 86, top: 224, width: 430, height: 210, fontSize: 16, color: C.sub,
  });
  addText(slide, "案例结果", {
    left: 86, top: 456, width: 180, height: 28, fontSize: 21, bold: true,
  });
  addText(slide, bulletLines([
    "按 η = 8 小时求解，8 线程笔记本运行约 104.7 秒",
    "生成每个周期的维修队路由、物资分配和运输路径",
    "规划期结束前，受损道路修复完成度提升 14.93%",
    "论文展示的配送路径表明，可达需求点会随周期逐步扩展",
  ]), {
    left: 86, top: 500, width: 430, height: 102, fontSize: 16, color: C.sub,
  });
  addShape(slide, "roundRect", 600, 154, 620, 196, C.white, { width: 1, fill: "#DCCFB1" });
  addText(slide, "按周期展开的管理画面", {
    left: 626, top: 176, width: 220, height: 26, fontSize: 21, bold: true,
  });
  flowBox(slide, {
    left: 626, top: 220, width: 170, height: 92,
    title: "周期 1-2",
    body: "部分路径仍不可达，系统先确定优先修复点。",
  });
  flowBox(slide, {
    left: 824, top: 220, width: 170, height: 92,
    title: "周期 3-5",
    body: "节点 1→8 等路径开始恢复，可达区域扩大。",
    fill: "#F6E7E0",
  });
  flowBox(slide, {
    left: 1022, top: 220, width: 170, height: 92,
    title: "周期 6-9",
    body: "更多远端节点被接入，配送路径明显缩短。",
  });
  addShape(slide, "roundRect", 600, 388, 620, 224, "#EDE1C8", { width: 0, fill: "#EDE1C8" });
  addText(slide, "为什么这个案例重要", {
    left: 626, top: 414, width: 220, height: 26, fontSize: 21, bold: true,
  });
  addText(slide, bulletLines([
    "它不是只给出一个“最优值”，而是输出可执行的日程表、路由和供给方案。",
    "它表明该方法能在实际灾后决策窗口内完成计算，而不是只能离线研究。",
    "它把道路修复优先级与物流通路恢复直接关联起来，方便指挥中心解释为什么要先修某些断点。",
  ]), {
    left: 626, top: 458, width: 548, height: 124, fontSize: 16, color: C.sub,
  });
  addText(slide, "引用：Li & Teo (2019), Section 7.1-7.2, Fig. 9, Tables 13-18；详见末页“数据来源与引用”。", {
    left: 600, top: 620, width: 610, height: 30, fontSize: 12, color: C.sub,
  });
  slide.speakerNotes.setText("对应第7节案例与附录A。数据来源在新增末页展开，便于汇报时追溯。");
}

// Slide 7
{
  const slide = presentation.slides.add();
  bg(slide, "从论文提炼出的决策建议", "DECISIONS", 7);
  card(slide, {
    left: 60, top: 162, width: 360, height: 164,
    title: "决策 1：修复顺序要围绕“重连价值”",
    body: "优先修复能让供给节点与高需求节点重新连通的关键断点，而不是平均地给每条损坏道路分配资源。",
  });
  card(slide, {
    left: 450, top: 162, width: 360, height: 164,
    title: "决策 2：把更新周期当成管理参数",
    body: "8 小时或 12 小时一轮的信息更新更现实，可在响应敏捷性与计算/执行成本之间取得平衡。",
    accent: C.red,
  });
  card(slide, {
    left: 840, top: 162, width: 380, height: 164,
    title: "决策 3：城乡网络要差异化配置",
    body: "农村更需要网络冗余与替代路径，城市更需要增加维修队规模以处理高密度受损路段。",
  });
  addShape(slide, "roundRect", 60, 374, 1160, 210, "#F7F0E1", { width: 1, fill: C.line });
  addText(slide, "建议转译成指挥动作", {
    left: 86, top: 400, width: 220, height: 28, fontSize: 21, bold: true,
  });
  addText(slide, bulletLines([
    "建立“受损点重连收益”清单：每个断点对应可恢复的需求节点、预计时间和替代路径变化。",
    "在应急指挥系统中预设 8h/12h 两档重规划节奏，避免临时讨论更新频率。",
    "对城市灾区预留额外道路抢修队；对山区/乡村灾区优先补齐脆弱单通道。",
    "让配送中心与修复调度共用一套网络状态数据，而不是各自维护独立台账。",
  ]), {
    left: 86, top: 444, width: 1084, height: 118, fontSize: 17, color: C.sub,
  });
  slide.speakerNotes.setText("本页是基于论文结论做的管理归纳，不是论文原文标题。");
}

// Slide 8
{
  const slide = presentation.slides.add();
  bg(slide, "后续步骤", "NEXT STEPS", 8);
  flowBox(slide, {
    left: 60, top: 176, width: 260, height: 238,
    title: "短期可落地",
    body: bulletLines([
      "把现有道路、仓库、需求点数据整理成统一图网络",
      "定义优先级：生命救援、基本保障、常规恢复",
      "先做一次历史灾害场景回放验证",
    ]),
  });
  flowBox(slide, {
    left: 360, top: 176, width: 260, height: 238,
    title: "中期可增强",
    body: bulletLines([
      "纳入撤离疏散与多组织协同",
      "允许多个维修队并行处理同一受损点",
      "把直升机等多运输方式纳入模型",
    ]),
    fill: "#F6E7E0",
  });
  flowBox(slide, {
    left: 660, top: 176, width: 260, height: 238,
    title: "研究层面",
    body: bulletLines([
      "与其他启发式算法做性能对比",
      "考虑更强的不确定性与实时信息更新",
      "评估公平性与效率之间的权衡机制",
    ]),
  });
  flowBox(slide, {
    left: 960, top: 176, width: 260, height: 238,
    title: "交付物建议",
    body: bulletLines([
      "形成灾后 72 小时标准化修复-配送联动模板",
      "固定更新节奏、角色分工和指挥看板",
      "建立面向不同地区类型的预案参数库",
    ]),
    fill: "#EDF5F4",
  });
  addShape(slide, "roundRect", 60, 464, 1160, 120, "#EADFC6", { width: 0, fill: "#EADFC6" });
  addText(slide, "收尾信息", {
    left: 86, top: 488, width: 150, height: 28, fontSize: 20, bold: true,
  });
  addText(slide, "这份演示文稿基于原始 PDF 内容提炼，保留论文结论的同时，改写为更适合汇报、讨论和决策会使用的表达方式。", {
    left: 86, top: 528, width: 1060, height: 34, fontSize: 17, color: C.sub,
  });
  slide.speakerNotes.setText("后续步骤综合自论文未来研究方向与实际汇报需求。");
}

// Slide 9
{
  const slide = presentation.slides.add();
  bg(slide, "汶川案例：数据来源与引用", "DATA SOURCES", 9);
  addText(slide, "论文案例输入来自实地行政数据、公开地理信息、遥感/航拍估计与作者设定的规划参数。", {
    left: 60, top: 150, width: 1080, height: 32, fontSize: 21, bold: true,
  });
  card(slide, {
    left: 60, top: 210, width: 360, height: 150,
    title: "节点、供给与需求",
    body: "供给/维修工作站为都江堰、彭州、什邡；35 个需求节点及供需量列于附录 A 表 16。需求量由《四川统计年鉴 2008》人口数据与房屋倒塌比例估算，房屋倒塌比例可由卫星、红外和航拍技术预测。",
  });
  card(slide, {
    left: 460, top: 210, width: 360, height: 150,
    title: "道路连通与通行时间",
    body: "节点间连接关系和路段通行时间列于附录 A 表 16；论文说明各道路/链路的通行时间可由 Google Earth 获得。",
    accent: C.red,
  });
  card(slide, {
    left: 860, top: 210, width: 360, height: 150,
    title: "受损路段与修复时间",
    body: "16 个受损节点及对应道路 ID、相邻节点、通行时间和修复时间列于附录 A 表 17。修复时间由红外或航拍识别的受损道路长度除以维修队能力估算。",
  });
  card(slide, {
    left: 60, top: 392, width: 360, height: 150,
    title: "维修能力假设",
    body: "论文假设各维修队能力相同，均为 0.5 km/h；第 7.1 节说明案例选取三处维修工作站节点，并在附录 A 解释受损道路修复时间的计算逻辑。",
    accent: C.red,
  });
  card(slide, {
    left: 460, top: 392, width: 360, height: 150,
    title: "车辆资源",
    body: "车辆类型、容量、数量和占用 OD 流量列于附录 A 表 18；车辆数量与占用 OD 数据来自四川省交通运输厅公路局。",
  });
  card(slide, {
    left: 860, top: 392, width: 360, height: 150,
    title: "规划与实验参数",
    body: "论文采用灾后黄金 72 小时为规划期；汶川案例设置 η = 8 小时，并报告在 8 线程笔记本上运行 104.7 秒。案例结果见第 7.2 节及表 13-15。",
    accent: C.red,
  });
  addShape(slide, "roundRect", 60, 578, 1160, 54, "#EADFC6", { width: 0, fill: "#EADFC6" });
  addText(slide, "主引用：Li, S. & Teo, K. L. (2019). Post-disaster multi-period road network repair: work scheduling and relief logistics optimization. Annals of Operations Research, 283, 1345-1385. DOI: 10.1007/s10479-018-3037-2.", {
    left: 84, top: 592, width: 1112, height: 28, fontSize: 13, color: C.ink,
  });
  slide.speakerNotes.setText("本页集中列出汶川案例的模型输入来源。引用重点是第7.1节、第7.2节、附录A表16-18和图9。");
}

const pptx = await PresentationFile.exportPptx(presentation);
await pptx.save(OUT_PATH);

export { OUT_PATH };
