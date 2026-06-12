---
name: write-graduate-thesis
description: Draft, outline, revise, or diagnose Chinese graduate thesis writing, especially applied master's theses in engineering management, management science, safety management, transportation, construction, survey/modeling, SEM, HCM, SD, VAR, coupling coordination, simulation, or policy/management recommendation topics. Use when Codex needs to build a thesis framework, chapter outline, abstract, literature review commentary, research content and method section, chapter summary, conclusions, suggestions, or formal academic Chinese expression in a structured advisor-style master's thesis.
---

# Write Graduate Thesis

## Core Posture

Write as an applied Chinese master's thesis: steady, explicit, method-chain oriented, and evidence-led. Favor "problem - gap - method - result - implication" over rhetorical flourish.

Use this skill to help with:

- Full thesis frameworks and chapter outlines.
- Chinese abstract, introduction, literature review commentary, research content/method, technical route, innovation points, chapter summaries, conclusions, suggestions, and outlook.
- Rewriting informal notes into formal thesis prose.
- Checking whether a thesis chapter has the expected role, transitions, and evidence support.

Do not invent data, model results, coefficients, sample sizes, years, software outputs, or citations. If the user has not provided them, use `[待补充]` placeholders or ask for the missing values.

## Source Pattern

This skill is distilled from four OCR graduate theses under `downloads/xju/ocr/`. Ignore OCR noise such as watermarks, page headers, duplicate catalog fragments, broken English spacing, misread symbols, and out-of-order snippets. Preserve only recurring structure and expression patterns.

Common pattern:

1. Identify a practical management problem and a gap in existing studies.
2. Build a measurable framework through questionnaire, indicators, expert scoring, public data, or simulation scene.
3. Use one or more models to quantify mechanisms or effects.
4. Compare models, validate fit, or analyze dynamic/effect differences.
5. Convert findings into management/policy/design recommendations.
6. Close with limitations and future research.

## Workflow

1. Classify the thesis type:
   - Questionnaire + latent variables + choice model.
   - Influencing factors + DEMATEL-ISM + SEM + system dynamics.
   - Indicator system + entropy weight + coupling coordination + VAR.
   - Behavioral model + simulation comparison.
   - If unclear, use the generic six-chapter applied empirical frame.
2. Build the argument spine:
   `[background] -> [existing research gap] -> [research object] -> [data/source] -> [method chain] -> [main findings] -> [suggestions/value]`.
3. Draft the structure before prose. Keep every chapter responsible for one step in the chain.
4. Write paragraphs with explicit transitions: "首先 / 其次 / 再次 / 最后", "基于此", "在此基础上", "结果表明".
5. Verify that every conclusion traces back to a method/result and every suggestion traces back to a conclusion.

## Default Thesis Frame

Use this six-chapter frame unless the user's school template says otherwise:

1. **绪论**: background, purpose/significance, literature review and commentary, research content/methods, technical route, innovation points when needed.
2. **相关概念与理论基础**: define key concepts, review theories and model foundations, state why they support later chapters.
3. **数据/问卷/指标体系/影响因素构建**: describe object, data source, variable or indicator selection, questionnaire/scenario/expert process, descriptive analysis, reliability/validity or consistency tests.
4. **核心模型或机理分析**: build hypotheses, model equations/path, parameter estimation, fit tests, result interpretation.
5. **实证/仿真/影响因素/策略分析**: compare models, run dynamic simulation or robustness/effect analysis, identify key factors, propose targeted measures.
6. **结论与展望**: restate the method chain, list numbered conclusions, provide suggestions, then limitations and future work.

## Reference Use

Read `references/framework-and-workflow.md` when creating or evaluating a full thesis outline, chapter plan, abstract structure, or chapter responsibilities.

Read `references/chapter-writing-laws.md` when drafting, revising, or diagnosing a specific chapter or subsection, including research background, purpose/significance, research content, methods, technical route, innovation points, theory chapter, data/questionnaire/indicator chapter, model chapter, empirical/simulation chapter, conclusion, suggestions, or outlook.

Read `references/phrase-bank.md` when drafting or polishing Chinese academic prose, especially literature review commentary, research content, method descriptions, chapter summaries, conclusions, suggestions, and outlook.

## Style Rules

- Prefer `本文` when describing the written thesis and `本研究` when describing research actions. Use one consistently within a paragraph.
- Make gaps specific: "缺少某因素", "较少关注某关系", "缺乏系统量化", "局限于静态分析", "特定区域实证不足".
- Introduce methods as a chain, not a list: each method should produce an input for the next method.
- Use formal but plain verbs: `构建`, `测算`, `检验`, `识别`, `揭示`, `量化`, `对比分析`, `提出`.
- Keep applied value grounded: "为...提供理论支撑/决策依据/管理参考", but only after explaining what result supports it.
- Avoid empty claims such as "具有重要意义" unless followed by the concrete theoretical or practical value.
- When revising OCR-derived text, silently fix obvious OCR errors only when meaning is clear; otherwise mark `[疑似OCR错误]`.
