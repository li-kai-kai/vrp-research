# Framework And Workflow

## Table Of Contents

- Argument spine
- Abstract frame
- Chapter roles
- Domestic and foreign research status framework
- Common method-chain variants
- Chapter-level writing workflow
- Review checklist

## Argument Spine

Use this thesis-level logic:

`现实背景 -> 管理问题 -> 既有研究不足 -> 本文切入 -> 数据/材料 -> 方法链 -> 结果 -> 建议/价值`

The four sample theses repeatedly narrow the gap in three ways:

- Factor gap: prior work considers observable factors but does not sufficiently consider latent psychological, behavioral, infrastructure, or dynamic factors.
- Method gap: prior work relies on qualitative analysis, simple statistics, static analysis, or a single model; the thesis adds a combined model chain.
- Object/context gap: prior work studies a broader group or different region; the thesis studies a specific group, building, city, industry, or scenario.

When drafting, turn the gap into a method decision:

- If the gap is "latent factors are ignored", use questionnaire, SEM/MIMIC, HCM, or similar latent-variable modeling.
- If the gap is "factor relationships are unclear", use expert scoring, DEMATEL-ISM, SEM, or path analysis.
- If the gap is "dynamic effects are ignored", use SD or simulation.
- If the gap is "regional coupling/effect lacks quantification", use indicator system, entropy weight, coupling coordination, VAR, Granger, impulse response, or variance decomposition.

## Abstract Frame

Write the Chinese abstract in 5 compact blocks:

1. Background and problem: explain the practical setting and why it matters.
2. Gap: state 1-2 shortcomings in existing studies.
3. Research design: name object, data, and method chain.
4. Main work and results: use `首先 / 其次 / 最后` or `第一 / 第二 / 第三` to summarize each research step and finding.
5. Value: state theoretical support, decision basis, management reference, or policy/design implication.

Keep the abstract concrete. Include sample size, period, region, model names, fit or error comparison, and key findings only if the user provides them.

## Chapter Roles

### Chapter 1: 绪论

Function: justify the topic and announce the route.

Recommended sections:

- 研究背景、目的及意义.
- 国内外研究现状及述评.
- 研究内容及方法.
- 技术路线.
- 创新点, if required.

Write the literature review as `topic clusters -> representative methods/findings -> limitations -> this study's response`. End the review with a concise commentary paragraph that names the research gap and leads directly to the research content.

See "Domestic and foreign research status framework" below for the recurring advisor-style pattern.

### Chapter 2: 相关概念与理论基础

Function: define the conceptual and theoretical base for later modeling.

Use this order:

1. Define key concepts in the user's topic.
2. Introduce supporting theories.
3. Introduce model foundations or calculation principles.
4. End with why these concepts/theories support the subsequent empirical chapters.

Do not turn Chapter 2 into a second literature review. It should explain the tools and conceptual boundaries used later.

### Chapter 3: Data, Questionnaire, Indicators, Or Factor System

Function: convert the research problem into measurable variables.

Choose the relevant modules:

- Questionnaire design: object, variable dimensions, item source, pre-survey, formal survey, sample description, reliability/validity.
- Indicator system: selection principles, literature/expert sources, Delphi or expert scoring, screening criteria, final indicators, consistency/authority tests.
- Scenario/simulation setup: object selection, scene attributes, parameter source, evaluation indicators.
- Factor/intervention system: factor identification, theoretical basis, expert scoring, relationship matrix, hierarchy/path preparation.

End Chapter 3 by stating how the data or indicators support Chapter 4.

### Chapter 4: Core Model Or Mechanism

Function: quantify the main mechanism.

Common ingredients:

- Hypothesis or model framework.
- Variable definition and model equation/path.
- Estimation or calculation process.
- Fit, reliability, validity, or diagnostic test.
- Result interpretation with direction, strength, and practical meaning.

This chapter should not only report significant variables. It should explain what the results reveal about the mechanism.

### Chapter 5: Empirical, Simulation, Effect, Or Strategy Analysis

Function: deepen, compare, or translate Chapter 4.

Typical uses:

- Compare baseline and improved models.
- Run simulation or dynamic analysis based on Chapter 4 parameters.
- Analyze key indicators, secondary factors, impulse responses, congestion/effect paths, or intervention intensity.
- Propose management, policy, design, or safety measures grounded in results.

Write recommendations after the analysis, not before it.

### Chapter 6: Conclusion And Outlook

Function: close the research chain.

Use this order:

1. Briefly restate the research object and method chain.
2. Number conclusions in the same order as the research content chapters.
3. Give suggestions only where the thesis has evidence.
4. State limitations honestly: sample scope, region, time period, model assumptions, variables not included, data availability, simulation simplifications.
5. Propose future work: more variables, broader samples, updated data, comparative regions, improved models, dynamic/longitudinal validation.

## Domestic And Foreign Research Status Framework

Do not default to separate "foreign research" and "domestic research" blocks. The recurring pattern is topic-based synthesis: mix domestic and foreign literature under research themes, then write a concentrated commentary that exposes the gap and leads to the thesis method chain.

Use one of these section structures:

```text
1.2 国内外研究现状
1.2.1 [研究对象/影响因素]相关研究
1.2.2 [研究方法/模型]相关研究
1.2.3 [干预策略/仿真/评价指标]相关研究
1.2.4 国内外研究现状述评
```

For behavior-choice topics:

```text
1.2 国内外研究现状及述评
1.2.1 [行为/选择]影响因素研究
1.2.2 [行为/选择]研究方法综述
1.2.3 国内外研究现状述评
```

For mechanism-and-intervention topics:

```text
1.2 国内外研究现状
1.2.1 [核心问题]影响因素研究
1.2.2 [核心问题]研究方法
1.2.3 [核心问题]干预/管理策略研究
1.2.4 综述评述
```

Write each subsection with this internal order:

1. State why this research direction matters and what angles scholars use.
2. Summarize representative literature as `author + method/viewpoint + finding`.
3. Synthesize the common understanding or progress.
4. Transition to the remaining limitation related to the thesis.

Write the final commentary as three gap types:

1. Factor gap: prior studies focus on observable factors but insufficiently consider latent, psychological, behavioral, infrastructure, interaction, or dynamic factors.
2. Method gap: prior studies rely on qualitative analysis, simple statistics, a single model, or static analysis; systematic quantification, combined models, or simulation are still insufficient.
3. Object/context gap: prior studies focus on other groups, regions, industries, buildings, or scenarios; empirical analysis of the user's object is limited.

End the commentary by mapping the gaps to the thesis design:

```text
基于上述不足，本文以[研究对象]为研究对象，引入[方法1]、[方法2]和[方法3]，系统分析[核心问题]的影响机理，并在此基础上提出相应的管理建议。
```

## Common Method-Chain Variants

### Questionnaire + Latent Variable + Choice Model

Structure:

`questionnaire -> descriptive statistics -> reliability/validity -> SEM/MIMIC -> latent variable fitted values -> Logit/HCM comparison -> prediction or policy`

Good for behavior choice, intention, route choice, return-home choice, safety psychology, and similar topics.

### DEMATEL-ISM + SEM + SD

Structure:

`literature/theory factors -> expert scoring -> DEMATEL-ISM hierarchy -> path hypotheses -> SEM validation -> SD simulation -> intervention comparison -> management suggestions`

Good for unsafe behavior, intervention strategies, complex factor systems, and dynamic management effects.

### Indicator System + Coupling + VAR

Structure:

`indicator principles -> literature/expert screening -> entropy weight -> comprehensive index -> coupling coordination -> VAR tests -> impulse/variance analysis -> policy recommendations`

Good for regional coordination, industry coupling, infrastructure effects, and time-series policy analysis.

### Behavioral Model + Simulation

Structure:

`questionnaire/scene data -> latent/model estimation -> baseline model -> improved model -> simulation platform -> output indicators -> comparison -> design/management measures`

Good for evacuation, traffic, emergency management, and behavior process simulation.

## Chapter-Level Writing Workflow

For every chapter, draft in four passes:

1. Opening paragraph: state the chapter's task and connection to the previous chapter.
2. Method/material paragraphs: describe data, concepts, variables, models, or procedures in the order they are used.
3. Result paragraphs: report what was found and explain why it matters.
4. Chapter summary: use `本章首先...其次...最后...` and end with the support it provides for the next chapter.

For each result paragraph, use this micro-structure:

`result statement -> statistical/model evidence -> mechanism explanation -> practical implication`

For each suggestion paragraph, use this micro-structure:

`target object -> evidence basis -> concrete measure -> expected effect`

## Review Checklist

- Does Chapter 1 end with a clear gap and method response?
- Does Chapter 2 define only concepts/theories used later?
- Does Chapter 3 show where the data/variables/indicators come from?
- Does Chapter 4 contain model specification, tests, and interpretation?
- Does Chapter 5 deepen or translate results rather than repeat Chapter 4?
- Do conclusions follow the same order as research content?
- Are all numbers, samples, years, coefficients, software outputs, and citations sourced from user material?
- Are suggestions traceable to results?
- Is the expression formal but not inflated?
