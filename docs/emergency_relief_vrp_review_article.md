# 灾后道路修复与应急救灾车辆路径优化研究综述：从静态路网到容量渐进恢复

## 摘要

灾后道路损毁会显著改变救援物资配送的可达性、通行时间和车辆路径选择，使应急救灾车辆路径优化从固定路网下的路径规划问题转变为受损路网恢复过程中的协同决策问题。围绕这一主题，本文基于已整理文献材料和核心参考文献，对应急物流与救援车辆路径优化、道路修复与网络恢复、道路修复-救援配送协同、不确定性与滚动重优化、多车型通行约束以及智能优化算法等研究进行叙述性综述。研究发现，现有文献已较充分地讨论道路修复队调度、救援物资配送、公平性目标和鲁棒优化方法，但多数模型仍将道路状态简化为“不可通行/修复后可通行”，对抢修过程中的临时抢通、限行和容量逐步恢复等中间状态刻画不足。未来研究可进一步将道路修复进度、动态容量、车型通行阈值和需求公平性纳入统一模型，并通过 NSGA-II 与 ALNS 等混合算法提高复杂多目标问题的求解质量。本文旨在为灾后道路修复与救援配送协同优化研究提供系统梳理，并为后续模型构建和算法设计提供参考。

**关键词**：应急物流；车辆路径优化；道路修复；容量渐进恢复；多车型配送；NSGA-II；ALNS

## Abstract

Post-disaster road damage changes the accessibility, travel time, and routing feasibility of relief distribution. As a result, emergency relief vehicle routing is no longer a routing problem on a fixed network, but a coordinated decision problem embedded in the restoration process of a damaged road network. Based on compiled literature materials and core references, this review synthesizes research on emergency logistics and relief routing, road restoration and repair crew scheduling, integrated road repair and relief distribution, uncertainty and rolling optimization, heterogeneous vehicle accessibility, and metaheuristic solution methods. The review shows that prior studies have made substantial progress in repair crew scheduling, relief distribution planning, equity-oriented objectives, and robust optimization. However, many models still represent damaged roads as either unavailable or fully repaired, leaving limited space for modeling temporary passability, restricted traffic, and gradual capacity recovery during the repair process. Future research should integrate repair progress, dynamic road capacity, vehicle-specific accessibility thresholds, and demand satisfaction equity within a unified modeling framework. Hybrid algorithms combining NSGA-II and ALNS may further improve solution quality for such complex multi-objective problems. This review provides a structured synthesis for future research on coordinated post-disaster road repair and relief vehicle routing.

**Keywords**: emergency logistics; vehicle routing; road restoration; gradual capacity recovery; heterogeneous fleet; NSGA-II; ALNS

## 1. 引言

自然灾害发生后，救援物资能否及时送达受灾点，直接关系到灾害响应效率和受灾群体的基本生活保障。与常规物流配送相比，应急救灾车辆路径优化具有更强的时间紧迫性、资源稀缺性和不确定性。灾后需求往往在短时间内快速变化，道路、桥梁和通信等基础设施也可能遭受不同程度损毁。道路网络一旦受损，车辆路径选择不再只是成本最小化问题，而是与道路可达性、通行能力、抢修进度和救援公平性密切相关。

已有应急物流研究表明，灾害响应阶段不仅涉及物资分配和车辆调度，还受到基础设施受损、动态需求和多主体协同等因素影响。Jiang and Yuan (2019) 将基础设施损毁、动态信息和资源短缺概括为大规模灾害应急物流中的重要挑战。Celik (2016) 从网络恢复与修复角度指出，道路、通信和电力等基础设施恢复是人道主义行动中的关键运筹问题。这些研究说明，灾后车辆路径优化不能脱离道路网络恢复过程单独讨论。

道路修复与救援配送协同优化正是在这一背景下形成的研究方向。早期研究多分别处理道路恢复和物资配送，随后逐渐出现将维修队排班、道路修复顺序、救援物资分配和车辆路径安排纳入统一模型的研究。Yan and Shih (2009) 较早将应急道路修复与后续救援配送纳入同一优化框架；Li and Teo (2019) 进一步建立多周期道路修复与救援物流双层规划模型，并以汶川地震路网为案例进行验证。后续研究又从维修队与救援车辆同步调度、随机修复时间、异质维修队、多类型道路损坏和不确定环境等方面对该问题进行拓展。

尽管相关研究已取得较多成果，现有模型仍存在一个重要简化：道路状态常被处理为二元可达状态，即道路在修复前不可通行、修复后恢复通行。该处理便于建模和求解，却难以反映真实灾后道路抢修中的阶段性恢复过程。受损道路可能在完全修复之前已经具备有限通行能力，例如清障后小型车辆可低速通过，单车道限行后中型车辆可通过，桥梁或路基加固后大型车辆才可通行。因此，将道路状态由二元可达扩展为容量随修复进度渐进恢复，是进一步提升灾后救援车辆路径模型现实适用性的一个重要方向。

本文围绕灾后道路修复与应急救灾车辆路径优化展开叙述性综述。全文重点回答三个问题：第一，现有研究如何处理应急车辆路径、道路修复和救援配送之间的关系；第二，道路状态、需求公平性和不确定性在既有模型中如何被刻画；第三，面向容量渐进恢复和多车型通行约束，未来研究可从哪些方向深化模型和算法。

## 2. 应急物流与救援车辆路径优化

应急物流是灾害响应系统的重要组成部分，其核心任务是在时间、资源和信息受限的条件下，将救援物资从供应点及时配送到受灾点。与商业物流不同，应急物流的目标不只是降低运输成本，还包括缩短响应时间、提高需求满足率、降低受灾点等待损失，并在不同区域之间保持基本公平。Jiang and Yuan (2019) 的综述显示，应急物流研究已经涵盖需求评估、设施选址、库存预置、车辆调度和多主体协同等多个方面。

在车辆路径优化层面，应急救援场景要求模型同时考虑效率、效果和公平性。Huang, Smilowitz, and Balcik (2012) 指出，救援路径模型不能只追求总成本或总行驶时间最小化，因为这种目标可能导致偏远或交通条件较差的受灾点长期得不到服务。其研究从效率、效果和公平性三个维度构建救援路径模型，为后续应急 VRP 中的公平性目标设计提供了重要基础。

Li and Teo (2019) 在多周期道路修复与救援物流模型中引入最大相对满意度思想，试图提高不同需求点之间的满足公平性。该方法能够避免最差需求点服务水平过低，但对等待时间、短缺持续时间和道路恢复滞后造成的累积损失刻画仍较有限。换言之，最大最小满足率可以表达终期公平，却不一定充分反映救援过程公平。对于灾后动态救援而言，一个需求点在最终得到满足之前可能已经经历较长时间的物资短缺，这种过程性损失需要在模型中得到进一步表达。

因此，应急救灾车辆路径优化的研究已经从常规 VRP 的路径成本问题扩展为多目标协调问题。路径优化需要同时处理车辆容量、配送时间、需求满足、公平性和道路可达性等因素。随着研究场景从完整路网转向受损路网，道路修复过程对车辆路径的影响也逐渐成为不可回避的建模对象。

## 3. 灾后道路修复与网络恢复优化

道路修复与网络恢复研究主要关注灾后如何安排维修队修复受损道路，以尽快恢复路网连通性、关键节点可达性或网络运行能力。Celik (2016) 将网络恢复与修复问题纳入人道主义运筹管理研究框架，指出道路、桥梁和交通基础设施恢复是保障后续救援行动的重要前提。该类研究为道路修复问题提供了较清晰的建模逻辑，即通过优化维修队作业顺序和移动路径，降低需求节点与供应节点之间的断连时间。

Maya Duque, Dolinskaya, and Sörensen (2016) 研究网络修复队调度与路径问题，重点解决维修队作业顺序和路径安排对需求节点可达时间的影响。Kasaei and Salman (2016) 从弧路由角度研究灾后道路网络连通性恢复，Akbari and Salman (2017) 进一步讨论多车辆同步弧路由问题，用于恢复灾后网络连通性。这些研究表明，道路恢复不仅取决于修复哪些路段，还取决于维修队如何移动、多个修复任务如何排序，以及不同修复任务之间是否存在同步关系。

随着模型复杂度提高，维修队异质性也受到关注。Moreno, Alem, Gendreau, and Munari (2020) 提出异质多维修队调度与路径问题，强调不同维修队在能力、效率和适用任务方面可能存在差异。该研究将需求节点与源点断连时间作为重要目标，体现出道路恢复研究由单一维修资源向多资源协同调度发展的趋势。

道路修复研究为救援配送协同优化提供了上层决策基础，但其局限也较明显。多数道路修复模型主要关注网络连通性、可达时间或维修队路径，并不直接安排救援物资配送。也就是说，这类模型能够回答“先修哪条路、由谁修、何时修”的问题，却不能完整回答“道路恢复过程如何改变车辆配送路径、需求满足率和公平性”的问题。因此，道路修复模型需要与救援配送模型进一步耦合。

## 4. 道路修复与救援配送协同优化

道路修复与救援配送协同优化试图在同一决策框架中处理道路恢复和物资配送两类任务。Yan and Shih (2009) 较早指出，道路修复计划会直接影响后续救援配送效率，若将修路和配送分开决策，可能导致系统整体效率下降。该研究将应急道路修复和救援配送纳入统一优化框架，为后续协同模型奠定了基础。

Li and Teo (2019) 是该方向的重要代表。其研究构建了灾后多周期道路修复与救援物流双层规划模型，上层安排维修队道路修复排班，下层在每一期可用路网上进行救援物资分配和路径优化。模型兼顾需求满足公平性和配送时间，并以汶川地震路网作为案例进行验证。该研究的贡献在于将多周期修复排班、受损路网变化和救援配送路径纳入同一框架，使道路修复对救援配送的影响能够被模型显式表达。

后续研究继续拓展这一思路。Shin, Kim, and Moon (2019) 研究灾后维修队与救援车辆的一体化调度，强调道路修复活动和救援车辆运行之间的同步关系。Akbari and Sayarshad (2022) 将道路恢复队与救援配送队进行协同规划，并考虑随机修复时间和非短视决策。Veysmoradi, Eydi, and Vahdani (2024) 进一步将多类型道路损坏、异质维修队和不确定环境纳入救援物资配送与道路网络修复规划，说明该领域已经从确定性集成模型向多约束综合模型发展。

相关中文研究也从道路修复条件下的应急资源配送 LRP、手机定位数据驱动的道路修复与物资配送集成优化、多周期鲁棒选址-路径模型等方面进行了拓展。根据已整理资料，王晶、曲冲冲、易显强（2017）研究道路修复条件下灾后应急资源配送 LRP，张梦玲等（2021）利用手机定位数据研究突发事件下道路修复和物资配送集成优化，孙华丽、任雨欣、田庭宁（2026）研究考虑道路修复的多周期应急设施选址-路径鲁棒优化。这些研究说明，道路修复与救援配送协同优化已经具有较充分的研究基础。

由此可见，单纯提出“考虑道路修复的应急配送”已难以构成充分创新。未来研究需要进一步深入到道路状态如何表达、修复过程如何影响车辆类型选择、实时信息如何更新以及算法如何处理复杂耦合结构等更具体的问题。

## 5. 不确定性与滚动重优化

灾后救援决策具有高度不确定性。道路损毁程度、修复时间、受灾点需求量、车辆可用性和物资供应量都可能在救援过程中不断变化。Caunhye, Aydin, and Duzgun (2020) 研究不确定修复时间下的鲁棒灾后路线恢复问题，提出基于修复时间排序的决策规则，并将两阶段鲁棒优化问题转化为单阶段混合整数规划问题。该研究说明，在修复时间难以准确估计的情况下，鲁棒优化能够提高道路恢复方案的稳定性。

Akbari, Salman, and Yücel (2021) 进一步从在线优化角度研究灾后道路恢复问题。其核心观点是，受损道路的实际修复时间往往只有在维修队到达现场后才能准确获知，因此恢复决策需要随着现场信息逐步揭示而动态调整。与事前设定固定情景的模型相比，在线优化更接近灾后救援中的真实决策过程。

在道路修复与救援配送协同场景中，不确定性不仅影响修复排班，也影响配送路径。若某条道路修复时间延长，下层配送车辆可能需要改变服务顺序或改用替代路径。若某一受灾点需求量上升，维修队和配送车辆可能需要优先恢复通往该区域的关键路段。张梦玲等（2021）利用手机定位数据估计灾民分布和需求，为实时信息进入修复-配送协同优化提供了一个例证。

基于这些研究，滚动重优化可被视为连接不确定性建模和实际救援调度的重要机制。滚动重优化并不要求在初始时刻准确预测所有参数，而是在每个救援周期根据现场反馈、道路巡查、无人机侦察或移动定位数据更新道路状态、需求量和剩余资源，再重新生成维修队排班和配送路径方案。这种“信息更新-状态修正-方案调整”的过程更符合灾后边抢修、边配送、边评估的实际特征。

## 6. 道路容量渐进恢复与多车型通行约束

道路状态刻画是现有研究进一步深化的重要方向。多数道路修复-配送模型将受损道路处理为“不可通行”和“修复后可通行”两类状态。该处理能够降低模型复杂度，却难以反映道路抢修中的阶段性恢复过程。现实中，一条道路在完全修复之前可能已经具备有限通行能力。例如，清障后小型车辆可以低速通行，单车道临时通车后中型车辆可以通过，桥梁加固或路基恢复后重型车辆才能通行。

道路韧性研究已经注意到道路损毁不一定等同于完全中断。Mao et al. (2021) 在道路网络灾后恢复优化中区分完全损坏和部分损坏：完全损坏意味着路段容量降为零，部分损坏则意味着容量下降但仍保留一定通行能力。该思路说明，道路容量是刻画灾后路网功能状态的重要变量。不过，道路韧性研究多服务于网络性能恢复评价，尚未充分嵌入多周期救援配送 VRP。

将容量渐进恢复引入道路修复-配送协同模型，可以更细致地表达抢修过程对配送决策的影响。若以 `p_a^t` 表示路段 `a` 在周期 `t` 的修复进度，以 `g(p_a^t)` 表示容量恢复函数，则路段当前容量可表示为 `C_a^t = C_a^0 g(p_a^t)`。在此基础上，不同车型可设置不同的最低通行进度阈值 `theta_v`。当 `p_a^t >= theta_v` 时，车型 `v` 可通过该路段；当 `p_a^t < theta_v` 时，该车型不可通过。这样，修复决策不仅决定道路何时完全打开，还决定每个周期可承载多少流量、哪些车型可走以及车辆通行时间如何变化。

这一建模思路也改变了多车型约束的含义。在常规 VRP 中，车型差异主要体现为载重、车辆数和行驶成本；在灾后受损路网中，车型差异还体现为道路可行性。小型车可能在道路临时抢通阶段率先进入受灾区域，大型车则在道路基本恢复后承担批量配送任务。将车型通行阈值与道路容量恢复函数结合，可以把“小车先送急需物资、大车后续批量补给”的救援逻辑转化为可计算的模型约束。

近年来，多车型配送、卡车-无人机协同和可变路网应急配送逐渐受到关注。相关研究说明，多模式运输在道路未完全恢复时具有现实意义。但若仅增加车辆种类或无人机配送，而不解释不同运输方式与道路恢复过程之间的耦合关系，模型创新仍然有限。更有价值的方向是将多车型选择嵌入道路容量渐进恢复机制，使车辆类型成为动态路网状态的一部分。

## 7. 优化算法：从单一启发式到混合多目标搜索

灾后道路修复与救援配送协同优化属于复杂组合优化问题。模型通常同时包含道路修复顺序、维修队分配、动态路网状态、多周期配送路径、车辆类型选择和多目标权衡。随着道路容量恢复和车型通行阈值被纳入模型，解空间进一步扩大，单一精确算法往往难以在较大规模算例中快速求得高质量解。

遗传算法和多目标进化算法在应急物流研究中已有较多应用。Deb et al. (2002) 提出的 NSGA-II 通过快速非支配排序、精英保留和拥挤距离机制获得多样化 Pareto 解集，适合处理救援效果、配送效率和公平性之间的冲突目标。对于灾后救援决策而言，Pareto 解集能够为决策者提供不同偏好的方案，而不是将多个目标强行合并为单一加权目标。

然而，单独使用 NSGA-II 也存在不足。道路修复与救援配送协同模型中的个体通常包含修复顺序、维修队任务分配、供需匹配优先级和车辆路径等多类结构。普通交叉和变异算子对局部路径结构、关键道路容量释放和低满意度需求点改善利用不足，容易出现后期收敛慢和局部改进弱的问题。Ropke and Pisinger (2006) 提出的 ALNS 通过多种破坏与修复算子自适应重构解结构，特别适合车辆路径、调度和分配类问题。Wang et al. (2023) 将多目标 ALNS-SA 用于应急物流网络优化，也说明 ALNS 类方法在复杂应急物流网络中具有较强适用性。

因此，将 NSGA-II 与 ALNS 结合具有较强的适用性。NSGA-II 可负责全局多目标搜索和 Pareto 解集多样性维护，ALNS 则可针对局部结构进行强化。例如，容量恢复导向算子可优先调整能释放关键道路通行能力的维修任务；低满意度需求点算子可围绕服务不足区域重构配送顺序；车型替换算子可在部分恢复路段上尝试以小型车替代重型车；维修队平衡算子可调整任务分配以减少关键道路修复延迟。通过这些定制算子，算法设计能够与道路容量渐进恢复和多车型通行约束形成对应关系。

## 8. 研究不足与未来方向

综合现有研究，可以发现灾后道路修复与应急救灾车辆路径优化已经形成较为完整的研究基础，但仍存在若干值得深入的问题。

第一，道路状态刻画仍需从二元可达转向过程化表达。既有模型多关注道路修复完成后的可达性提升，较少刻画修复未完成但已具备部分通行能力的中间状态。未来研究可建立道路修复进度、容量恢复比例、通行时间和车型通行阈值之间的映射关系，使临时抢通、限行和逐步恢复能够进入车辆路径优化模型。

第二，公平性目标需要与道路恢复时序结合。现有研究已经关注最大最小满足率、需求紧迫度和匮乏成本等指标，但公平性往往作为配送结果指标单独存在。未来模型可进一步关注等待时间累积、道路恢复滞后造成的区域性服务差异，以及不同受灾点在多个救援周期内的动态满足过程。

第三，不确定性研究需要从静态情景走向滚动决策。鲁棒优化和随机优化能够处理部分参数不确定性，但灾后救援中的道路状态和需求信息会持续更新。未来研究可将在线优化、滚动重优化和实时数据融合纳入修复-配送协同框架，形成更接近实际响应过程的动态决策模型。

第四，维修资源和配送资源的异质性仍有深化空间。不同维修队可能具有不同设备、技能和修复效率，不同车辆可能具有不同载重、道路占用和通行门槛。未来研究可进一步考虑维修装备物资补给、抢修队能力匹配、多车型协同配送和多模式运输之间的耦合关系。

第五，算法研究应从“使用某种启发式”转向“面向问题结构的算法设计”。对于道路容量渐进恢复和多车型通行约束下的协同优化问题，算法算子应服务于模型特征。未来可通过消融实验比较标准 NSGA-II、容量恢复模型下的 NSGA-II、以及 NSGA-II + ALNS 混合算法，以检验模型创新和算法改进的实际贡献。

## 9. 结论

灾后道路修复与应急救灾车辆路径优化是应急物流、道路网络恢复和多目标组合优化交叉形成的重要研究领域。现有研究已经从救援配送路径优化、道路修复队调度、修复-配送协同、不确定性建模和多目标启发式算法等方面取得较多成果，为灾后救援决策提供了理论基础和方法支持。

本文综述表明，道路修复与救援配送协同优化已经不再是研究空白，未来研究的关键不在于简单地将道路修复和配送路径放入同一模型，而在于更准确地刻画道路恢复过程对车辆路径和需求满足的动态影响。道路容量渐进恢复和车型通行阈值能够弥补二元道路状态表达的不足，使模型更接近灾后道路抢通、限行和逐步恢复的实际过程。

在方法层面，NSGA-II 与 ALNS 的混合框架为求解该类复杂多目标问题提供了可行方向。若能够围绕关键道路容量释放、低满意度需求点改善、车型替换和维修队任务平衡设计局部改进算子，算法贡献将不再只是求解器替换，而是与模型结构形成对应。总体而言，将动态道路容量、车型通行约束、需求公平性和混合多目标算法纳入统一框架，是灾后道路修复与应急救灾车辆路径优化研究值得继续推进的方向。

## 参考文献

Akbari, V., & Salman, F. S. (2017). Multi-vehicle synchronized arc routing problem to restore post-disaster network connectivity. *European Journal of Operational Research, 257*(2), 625-640. https://doi.org/10.1016/j.ejor.2016.07.043

Akbari, V., & Sayarshad, H. R. (2022). Integrated and coordinated relief logistics and road recovery planning problem. *Transportation Research Part D: Transport and Environment, 111*, 103433. https://doi.org/10.1016/j.trd.2022.103433

Akbari, V., Salman, F. S., & Yücel, E. (2021). An online optimization approach to post-disaster road restoration. *Transportation Research Part B: Methodological, 150*, 1-25. https://doi.org/10.1016/j.trb.2021.05.017

Caunhye, A. M., Aydin, N. Y., & Duzgun, H. S. (2020). Robust post-disaster route restoration. *OR Spectrum, 42*(4), 1055-1087. https://doi.org/10.1007/s00291-020-00601-0

Celik, M. (2016). Network restoration and recovery in humanitarian operations: Framework, literature review, and research directions. *Surveys in Operations Research and Management Science, 21*(2), 47-61. https://doi.org/10.1016/j.sorms.2016.12.001

Deb, K., Pratap, A., Agarwal, S., & Meyarivan, T. (2002). A fast and elitist multiobjective genetic algorithm: NSGA-II. *IEEE Transactions on Evolutionary Computation, 6*(2), 182-197. https://doi.org/10.1109/4235.996017

Huang, M., Smilowitz, K., & Balcik, B. (2012). Models for relief routing: Equity, efficiency and efficacy. *Transportation Research Part E: Logistics and Transportation Review, 48*(1), 2-18. https://doi.org/10.1016/j.tre.2011.05.004

Jiang, Y., & Yuan, Y. (2019). Emergency logistics in a large-scale disaster context: Achievements and challenges. *International Journal of Environmental Research and Public Health, 16*(5), 779. https://doi.org/10.3390/ijerph16050779

Kasaei, M., & Salman, F. S. (2016). Arc routing problems to restore connectivity of a road network. *Transportation Research Part E: Logistics and Transportation Review, 95*, 177-206. https://doi.org/10.1016/j.tre.2016.09.012

Li, S., & Teo, K. L. (2019). Post-disaster multi-period road network repair: Work scheduling and relief logistics optimization. *Annals of Operations Research, 283*, 1345-1385. https://doi.org/10.1007/s10479-018-3037-2

Mao, X., Zhou, J., Yuan, C., & Liu, D. (2021). Resilience-based optimization of postdisaster restoration strategy for road networks. *Journal of Advanced Transportation, 2021*, 8871876. https://doi.org/10.1155/2021/8871876

Maya Duque, P. A., Dolinskaya, I. S., & Sörensen, K. (2016). Network repair crew scheduling and routing for emergency relief distribution problem. *European Journal of Operational Research, 248*(1), 272-285. https://doi.org/10.1016/j.ejor.2015.06.026

Moreno, A., Alem, D., Gendreau, M., & Munari, P. (2020). The heterogeneous multicrew scheduling and routing problem in road restoration. *Transportation Research Part B: Methodological, 141*, 24-58. https://doi.org/10.1016/j.trb.2020.09.002

Ropke, S., & Pisinger, D. (2006). An adaptive large neighborhood search heuristic for the pickup and delivery problem with time windows. *Transportation Science, 40*(4), 455-472. https://doi.org/10.1287/trsc.1050.0135

Shin, Y., Kim, S., & Moon, I. (2019). Integrated optimal scheduling of repair crew and relief vehicle after disaster. *Computers & Operations Research, 105*, 237-247. https://doi.org/10.1016/j.cor.2019.01.015

Veysmoradi, D., Eydi, A., & Vahdani, B. (2024). The planning of the distribution of relief items and road network repair through multiple heterogeneous crews and prioritizing damaged roads under a flexible and uncertain environment. *Computers & Industrial Engineering, 196*, 110481. https://doi.org/10.1016/j.cie.2024.110481

Wang, Y., Wang, X., Fan, J., Wang, Z., & Zhen, L. (2023). Emergency logistics network optimization with time window assignment. *Expert Systems with Applications, 214*, 119145. https://doi.org/10.1016/j.eswa.2022.119145

Yan, S., & Shih, Y. L. (2009). Optimal scheduling of emergency roadway repair and subsequent relief distribution. *Computers & Operations Research, 36*(6), 2049-2065. https://doi.org/10.1016/j.cor.2008.07.002

张梦玲, 王晶, 黄钧, 焦子豪. (2021). 基于手机定位数据的突发事件下道路修复和物资配送集成优化研究. *中国管理科学, 29*(3), 133-142. https://doi.org/10.16381/j.cnki.issn1003-207x.2021.03.13

孙华丽, 任雨欣, 田庭宁. (2026). 考虑道路修复的多周期应急设施选址-路径鲁棒优化研究. *中国管理科学*. 待核验卷期、页码与 DOI。

胡彦, 李晓萍, 胡青蜜. (2026). 考虑道路修复的应急设施选址-路径鲁棒优化. *系统科学与数学*. 待核验卷期、页码与 DOI。

王晶, 曲冲冲, 易显强. (2017). 道路修复条件下灾后应急资源配送 LRP 研究. *运筹与管理*. 待核验卷期、页码与 DOI。

> 注：中文文献条目中标注“待核验”的部分，正式投稿或提交学位论文前需依据知网、期刊官网或 DOI/CNKI 记录进一步核对卷期、页码和 DOI。
