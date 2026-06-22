# 灾后道路修复与应急救灾车辆路径优化研究综述

## 摘要

近年来，极端天气、地震和城市内涝等灾害频发，常造成道路中断、通行能力下降和救援物资配送困难，使灾后道路修复与应急救灾车辆路径优化逐渐成为应急物流和交通运输领域的研究热点。然而，现有方法仍缺乏对道路状态演化、多源实时信息、抢修资源与配送资源同步调度，以及效率、公平和需求满足等多目标关系的统一刻画，传统车辆路径模型也难以完整反映受损路网下设施选址、道路修复、物资配送和多模式运输之间的耦合机制。针对上述问题，本文梳理了灾后道路修复与应急救灾车辆路径优化关键技术的研究进展，为进一步构建面向动态灾害场景的协同优化模型提供文献基础和问题参照。综述发现，相关研究已由单一效率导向逐步转向兼顾时效性、需求满足和公平性的多目标优化；由常规车辆路径问题扩展到道路网络恢复、选址-路径协同、修复-配送集成优化、不确定信息处理和卡车-无人机等多模式协同配送。但现有研究仍存在道路状态表达偏静态、模型要素集成不足、实时重调度机制不完善、典型灾害案例和可复现实验基准不足等问题。未来，面向多目标和集成协同优化，应构建状态感知、动态更新、修复-配送联动的路网恢复与救援配送机制，针对道路损毁、需求波动和资源受限条件下的路径重构问题，融合鲁棒优化、随机规划、在线优化和数据驱动算法，有望提升灾后救援系统的响应效率、公平性和可验证性。

**关键词**：应急物流；车辆路径优化；道路修复；协同优化；动态路网；不确定性；多模式运输

## Abstract

In recent years, frequent extreme weather events, earthquakes, and urban flooding have made post-disaster road repair and emergency relief vehicle routing a growing research focus in emergency logistics and transportation studies. However, existing methods still lack an integrated representation of road-state evolution, multi-source real-time information, synchronized scheduling of repair and delivery resources, and the trade-offs among efficiency, equity, and demand satisfaction. Conventional vehicle routing models are also insufficient for capturing the coupled decisions among facility location, road restoration, relief distribution, and multimodal transportation on damaged networks. To address these issues, this review synthesizes key technical advances in post-disaster road repair and emergency relief vehicle routing optimization, providing a structured basis for future collaborative optimization models in dynamic disaster contexts. The review shows that research objectives have shifted from single efficiency-oriented measures toward multi-objective optimization that incorporates timeliness, demand fulfillment, and equity. Meanwhile, the problem scope has expanded from standard vehicle routing to network restoration, location-routing coordination, integrated repair-distribution optimization, uncertainty handling, and multimodal delivery such as truck-drone collaboration. Nevertheless, current studies still face limitations in dynamic road-state modeling, comprehensive factor integration, real-time rescheduling, disaster-specific case analysis, and reproducible computational benchmarks. Future research should develop state-aware, dynamically updated, and repair-distribution coordinated mechanisms for network recovery and relief delivery. By combining robust optimization, stochastic programming, online optimization, and data-driven algorithms for routing under road damage, demand fluctuation, and resource constraints, future models may improve the efficiency, equity, and verifiability of post-disaster relief systems.

**Keywords**: emergency logistics; vehicle routing; road repair; collaborative optimization; dynamic networks; uncertainty; multimodal transportation

## 1. 引言

自然灾害发生后，救援物资能否及时送达受灾点，直接关系到灾害响应效率和受灾群体的基本生活保障。与常规物流配送相比，应急救灾车辆路径优化具有更强的时间紧迫性、资源稀缺性和信息不完备性。道路、桥梁、隧道等交通基础设施一旦受损，配送车辆不仅要面对需求量和服务优先级变化，还要在可达性下降、绕行距离增加和通行时间不确定的条件下重新规划路径。

车辆路径优化最初主要服务于常规物流配送中的路线安排问题，其理论基础可追溯到旅行商问题中“如何以较短路径访问一组节点”的基本思想。1959 年，Dantzig and Ramser 在成品油配送背景下提出“卡车调度问题”，研究从一个油品终端向多个服务站配送时，如何在车辆容量和需求约束下安排车队路线，这一研究通常被视为现代车辆路径问题（vehicle routing problem, VRP）的开端。经典 VRP 主要解决给定仓库、需求点和完整路网条件下的车辆服务顺序与行驶路径安排问题。灾后救援场景与常规配送不同，需求点可能临时变化，道路可能中断或限行，车辆路径不再只是距离和成本最小化问题，而是与可达性恢复、配送时效和受灾点服务公平直接相关。

随着物流系统由单一仓库配送扩展到多仓库、多集散点和多级网络，单独优化车辆路径又暴露出新的局限：如果仓库或应急设施位置选择不合理，即使后续路径安排最优，整体配送效率和服务覆盖仍可能偏低。选址-路径问题（location-routing problem, LRP）正是在这一背景下产生，它把设施选址这一战略或战术决策，与车辆路径这一运营决策放在同一框架中处理。Nagy and Salhi (2007) 通过综述选址-路径问题的模型类型和求解方法指出，选址与路径存在明显相互依赖关系，二者分开求解可能导致系统性次优；但该类综述主要面向一般物流系统，对灾后路网损毁、需求快速变化和救援时效约束讨论不足。为将 LRP 引入应急救援情境，代颖等（2012）以震后应急物资配送为对象，综合考虑模糊需求、动态需求、需求限制期、受损路网动态恢复、不同类型容量受限车辆和需求可拆分配送，采用机会约束规划构建模糊动态定位-路径模型，并设计两阶段启发式算法，通过算例验证模型可行性。该研究说明 LRP 能够同时回答“配送中心在哪里启用”和“车辆如何配送”，但道路恢复过程在模型中更多作为外部动态条件进入，尚未充分解释道路抢修决策本身如何改变选址和路径方案。在此基础上，王晶、曲冲冲、易显强（2017）将道路修复条件纳入灾后应急资源配送 LRP，把障碍道路修复与设施选址、资源配送和车辆路径联合考虑，使研究进一步从“设施在哪里启用、车辆怎么走”推进到“道路如何恢复后再配送”的协同决策。

道路修复研究的加入，使灾后救援车辆路径优化由“在既定路网上找路”转向“在不断变化的受损路网上协同决策”。Jiang and Yuan (2019) 采用综述方法总结大规模灾害应急物流研究，指出动态需求、基础设施损毁和多主体协调是制约救援效率的核心问题，但其贡献主要在于宏观归纳挑战，并未建立道路修复与车辆路径的具体优化模型。Celik (2016) 则从人道主义行动中的网络恢复问题出发，梳理道路、通信、电力等基础设施恢复的研究框架，强调基础设施恢复对后续救援活动的支撑作用；不过，该研究更偏向网络恢复问题分类，尚未充分展开物资配送路径与修复队调度之间的同步关系。针对受损路网下路径选择问题，王晶、易显强、张玲（2014）定义了物资配送路线的风险度量值，建立考虑道路可靠性的应急资源配送路线优化模型，并通过算法给出风险条件下的配送路线方案，说明道路可靠性会直接改变路径选择结果；但道路在该研究中主要表现为可靠性或风险参数，道路如何修复、修复后可靠性如何变化仍不够清楚。为回应这一不足，王晶、易显强、朱建明（2016）进一步引入道路中断和通行可靠性降低，构建道路修复与可靠路径选择集成优化模型，以最大化配送效率为目标，采用多吸引子粒子群算法并结合仿真验证模型有效性。该研究将“修路”和“选路”放入同一模型，是从可靠路径选择走向修复-配送集成的重要推进；但其灾情信息仍主要依赖设定情景和仿真参数，现实灾害中受灾人口位置、需求规模和道路状态如何快速获取仍是问题。张梦玲等（2021）因此引入手机定位数据获取灾民分布、位置、灾害影响和物资需求等信息，建立道路修复与物资配送集成优化的混合整数线性规划模型，并设计启发式算法，通过算例比较有无手机定位数据条件下的救援结果，说明多源数据能够提高道路修复和物资配送决策的精准性。上述研究形成了从“道路可靠性影响路径选择”到“道路修复与路径选择集成”，再到“数据驱动的修复-配送协同”的递进脉络。

基于上述研究基础，灾后道路修复、救援物资配送与车辆路径优化构成本文的分析主线。具体章节安排如下：第一，**应急物资配送与车辆路径优化**，梳理救援配送目标由时间、距离等效率指标向需求满足和公平性指标扩展的过程；第二，**灾后道路修复与路网恢复**，归纳道路修复顺序、修复队调度和关键节点可达性恢复等研究；第三，**道路修复-物资配送-路径优化协同**，分析道路修复结果对物资分配、车辆路径重构和配送时序安排的影响；第四，**动态信息、不确定性与研究展望**，讨论道路状态、需求信息和修复时间不确定条件下的模型扩展及后续研究方向。上述安排有助于呈现受损路网条件下道路恢复、物资分配、车辆行驶和救援绩效评价之间的关联。

## 2. 应急物资配送与车辆路径优化

应急物流的基本任务是在有限时间内将救援物资从储备点、集散点或配送中心送达受灾区域。早期路径优化研究多以总运输时间、总成本或最晚到达时间最小化为目标，这类目标形式便于建模和求解，但难以充分体现灾后救援中的公共性和人道主义属性。实际救援中，偏远区域、道路受损严重区域或需求更紧迫区域若长期得不到服务，即使系统总体运输时间较短，也可能造成明显的区域不公平。

Huang, Smilowitz, and Balcik (2012) 从效率、效果和公平性三个维度构建救援路径模型，指出应急配送不能只追求总成本最优，还应关注不同受灾点的服务均衡。曲冲冲等（2018）在震后应急物资动态配送中同时考虑时效性和公平性，并将多种运输方式、多时段配送中心选址和路径安排纳入多目标规划模型。该类研究推动应急 VRP 从“车辆如何走得更短”转向“物资如何更及时、更均衡地覆盖需求点”。

在动态灾害场景中，公平性还具有过程属性。若某一需求点最终得到补给，但在前几个救援周期长期处于短缺状态，其救援体验和社会损失并不能由终期满足率完全表达。Li and Teo (2019) 在道路修复与救援物流模型中引入需求满足公平性，体现了从配送结果公平向多周期救援公平拓展的趋势。张玲、李继昭（2023）从道路可靠性、需求不确定和公平性出发，研究应急救灾选址-路径随机优化问题，也说明公平性目标正在与道路可靠性和随机条件结合。

总体看，应急救援车辆路径优化的目标体系经历了由单目标效率优化向多目标综合优化的转变。路径方案不仅要考虑车辆行驶距离和配送时间，还要兼顾需求满足率、服务优先级、等待损失和区域公平性。这一转变为后续道路修复与救援配送协同优化提供了目标函数基础。

## 3. 灾后道路修复与路网恢复

道路修复与网络恢复研究主要回答灾后应先修复哪些路段、维修队如何移动、关键节点何时恢复可达等问题。Maya Duque, Dolinskaya, and Sörensen (2016) 研究网络修复队调度与路径问题，强调维修队作业顺序对需求节点可达时间的影响；Kasaei and Salman (2016) 以弧路由形式研究道路网络连通性恢复；Akbari and Salman (2017) 则将多车辆同步作业引入灾后网络连通性恢复。上述研究为后续道路修复模型提供了基本框架，即通过维修队路径和任务排序优化，缩短关键需求点与供应点之间的断连时间。

## 4. 道路修复-物资配送-路径优化协同

随着研究推进，单纯修复路网并不能完整解释救援系统绩效。道路修复的价值最终需要通过物资配送、人员转运或医疗救援等任务体现，因此修复排班与配送路径之间存在明显耦合。Yan and Shih (2009) 较早将应急道路修复和后续救援配送纳入统一调度框架；Li and Teo (2019) 构建多周期道路网络修复与救援物流优化模型，上层安排道路修复，下层在各周期可用路网上进行物资分配和路径规划。Shin, Kim, and Moon (2019) 进一步研究维修队与救援车辆的一体化调度，强调修复活动和配送活动在时间上的同步。

近年研究进一步将集成优化推进到动态扰动和分布鲁棒决策情景。Veysmoradi, Eydi, and Vahdani (2025) 在余震和其他扰动下讨论道路修复与救援配送活动的重调度和同步，说明灾后方案需要在既有修复-配送计划基础上快速调整。Bai et al. (2026) 则从道路恢复与救援物资配送协同出发，采用分布鲁棒优化处理需求、恢复能力和路网连通性变化等不确定因素，使道路修复队路径、配送车队方案和物资分配之间形成更紧密的决策关联。

围绕道路修复与应急资源配送的协同关系，王晶、曲冲冲、易显强（2017）研究道路修复条件下灾后应急资源配送 LRP，将障碍道路修复与选址-路径决策联系起来；张梦玲等（2021）利用手机定位数据估计灾民分布和需求，研究突发事件下道路修复与物资配送集成优化；袁涛等（2021）在考虑道路损毁情况的应急物流 LRP 中，将道路损毁、多级网络和设施定位纳入同一问题框架。孙华丽、李泽平、马腾（2023）从道路修复联合应急设施选址-路径角度构建鲁棒优化模型，孙华丽、任雨欣、田庭宁（2026）进一步研究考虑道路修复的多周期应急设施选址-路径鲁棒优化。

由此可见，“道路修复+救援配送”已经不是一个尚未被覆盖的空白议题。现有研究已经涉及多周期修复、选址-路径协同、维修队与配送队联合调度、鲁棒优化和真实灾害案例等内容。后续研究需要在既有基础上进一步说明具体问题边界，例如道路状态如何更新、需求信息如何获取、抢修资源是否异质、以及模型结果如何服务实际调度，而不能仅将“考虑道路修复”本身作为主要贡献。

## 5. 动态信息、不确定性与研究展望

灾后救援决策的难点之一在于信息持续变化。道路损毁程度、修复时间、受灾点需求、车辆可用性和物资供应量往往无法在初始阶段准确掌握。Caunhye, Aydin, and Duzgun (2020) 在不确定修复时间下研究鲁棒灾后路线恢复问题，说明道路恢复方案需要抵御修复时间偏差带来的风险。Akbari, Shiri, and Salman (2021) 从在线优化角度研究灾后道路恢复，指出道路实际修复时间可能只有在维修队到达现场后才能获知，因此决策需要随现场信息逐步更新。Ren et al. (2026) 进一步从道路塌方情形出发构建多阶段随机规划模型，说明道路损毁状态和容量变化可以作为跨周期救援配送网络的重要随机状态进入模型。

在协同优化场景中，不确定性同时影响上层修复和下层配送。若某条道路修复延迟，配送车辆可能需要改走替代路线；若某一受灾点需求上升，抢修优先级和配送顺序也可能随之调整。张梦玲等（2021）将手机定位数据用于估计受灾人群分布，为多源信息进入道路修复-物资配送模型提供了案例支撑。Gong et al. (2025) 的预印本研究进一步从无人机灾后道路评估角度讨论实时道路损毁信息获取，说明道路状态识别本身也会影响后续修复和配送决策。滚动决策、在线优化和实时数据融合因而成为连接理论模型与灾害响应实践的重要方向。

动态路网还推动多模式运输研究发展。道路受损严重时，单一地面车辆配送可能无法覆盖所有受灾点，卡车-无人机协同、地面车辆与航空运输协同、以及多级转运网络逐渐受到关注。Yang et al. (2025) 针对灾后救援中的卡车与无人机协同运输建立两阶段随机优化模型，考虑卡车行驶时间不确定并基于北京房山极端降雨灾害数据进行实验；刘兴等（2026）研究灾后路况时空不确定条件下的卡车-无人机协同应急配送路径优化；刘长石等（2023）讨论通行受限情景下需求可拆分的卡车-多无人机协同配送；曲冲冲等（2018）的模型也体现出多阶段、多运输方式参与震后物资保障的思路。这些研究表明，多模式运输并非简单增加车辆种类，而是为了应对道路中断、通行受限和需求紧急程度差异。

算法方面，灾后道路修复与救援配送问题通常具有混合整数、多周期、多目标和强耦合特征。精确算法有助于刻画问题结构和求解小规模算例，启发式、元启发式和分解方法则更常用于较大规模场景。算法选择本身并不等同于研究贡献，关键在于算法能否回应道路状态变化、维修队调度、车辆路径重构和需求公平性等问题结构，并通过基准算例、敏感性分析和对比实验说明其适用边界。

综合已有研究，灾后道路修复与应急救灾车辆路径优化已经形成较为完整的研究基础。相关成果覆盖网络恢复、维修队路径、在线优化、协同调度、道路可靠性、道路修复条件下的 LRP、手机定位数据驱动的集成优化、多周期鲁棒选址-路径和卡车-无人机协同配送等方向。将这些研究放在同一主题脉络下可以发现，当前领域的主要问题已从“是否考虑道路修复”转向“如何更真实地刻画灾后动态决策过程”。

首先，道路状态表达仍有提升空间。网络恢复和修复队调度研究多以连通性恢复、需求节点可达时间或受损弧修复顺序为核心，例如 Maya Duque et al. (2016)、Kasaei and Salman (2016)、Akbari and Salman (2017) 以及 Moreno et al. (2020) 的研究为修复队调度提供了基础模型；Li and Teo (2019)、Shin et al. (2019)、Akbari and Sayarshad (2022)、Veysmoradi et al. (2024, 2025) 和 Bai et al. (2026) 则进一步将修复排班与配送路径、物资分配或资源调度联系起来。上述研究已经突破了单纯道路恢复问题，但道路状态在许多模型中仍主要通过修复完成、连通性变化、修复时间或情景容量来表达。现实灾后路网往往存在限速、限载、单向放行、局部绕行和临时管制等情况，后续研究可进一步区分“路网连通性恢复”“道路服务能力恢复”和“车辆路径可行性恢复”三类问题，以避免不同研究对象之间的概念混用。

其次，信息更新机制仍需与模型结构结合。Caunhye et al. (2020) 和 Bai et al. (2026) 分别从鲁棒优化和分布鲁棒优化角度处理修复时间、需求和路网连通性等不确定因素，Akbari et al. (2021) 则强调道路实际修复时间会随现场作业逐步揭示。张梦玲等（2021）利用手机定位数据估计受灾人群分布，Gong et al. (2025) 的预印本研究讨论无人机灾后道路评估，Yang et al. (2025) 将卡车行驶时间不确定纳入卡车-无人机协同调度。这些研究说明多源信息正在进入模型，但道路巡查、移动通信、无人机侦察、抢修反馈和需求上报的时效性、误差和覆盖范围并不相同。多源数据如何转化为可用于路径优化的路网状态、需求状态和资源状态，仍需要更清楚的状态识别和不确定性处理机制。

再次，特定灾害案例研究和可复现实验仍显不足。Li and Teo (2019) 使用汶川地震路网验证道路修复与救援物流模型，Yang et al. (2025) 采用北京房山极端降雨灾害数据测试卡车-无人机协同方案，张梦玲等（2021）和 Gong et al. (2025) 的预印本研究分别展示了手机定位数据和无人机评估在灾后信息获取中的作用。这些案例增强了模型现实指向，但不同论文中的路网规模、需求设定、修复时间、车辆参数和灾害类型并不完全一致，导致结果横向比较较难。地震、洪涝、泥石流和城市内涝对道路损毁形式、桥隧中断方式和临时通行条件的影响也存在差异，后续研究若能建立开放的灾后路网算例、统一的数据假设和多算法对比框架，将有助于提高该领域研究的可积累性。

最后，相关研究展望仍需以既有文献证据为基础。现有成果已经覆盖道路恢复、修复队调度、修复-配送集成、不确定优化、在线决策和多模式运输等方向，因而后续讨论不宜简单地把“道路修复与配送路径结合”视为研究空白，而应进一步说明具体边界：道路状态是连通性、容量、通行时间还是车型可达性；信息更新来自现场抢修、移动定位还是无人机识别；配送资源、抢修资源和设施选址之间是否同步决策；政府应急部门、道路抢修主体、物资供应方和配送队伍之间的信息传递与决策权责如何协调。只有在这些边界被清楚界定后，新的模型变量、算法组合或指标设计才更容易形成可验证的研究贡献。

## 6. 结论

本文围绕灾后道路修复、救援物资配送和车辆路径优化之间的关系，对应急物资配送与车辆路径优化、灾后道路修复与路网恢复、道路修复-物资配送-路径优化协同，以及动态信息和不确定性处理等研究进行了梳理。综合已有文献，可以形成以下认识。

第一，应急救灾车辆路径优化已经由常规运输时间或成本最小化问题，逐步扩展为兼顾时效性、需求满足、公平性和道路可靠性的多目标决策问题。道路受损条件下，车辆路径方案不仅取决于车辆容量和服务顺序，还受到道路可达性、修复时序和需求紧迫程度的共同影响。

第二，道路修复与救援配送协同优化已经形成较为明确的研究基础。现有研究已涉及道路网络恢复、修复队调度、选址-路径协同、多周期物资分配、鲁棒优化和在线决策等内容，说明“考虑道路修复”本身不宜再被简单视为研究空白。后续研究更需要明确道路状态、抢修资源、配送资源和设施选址之间的具体耦合关系。

第三，现有文献在道路状态过程化表达、多源信息更新、典型灾害案例和可复现实验基准方面仍有深化空间。后续研究可进一步区分路网连通性恢复、道路服务能力恢复和车辆路径可行性恢复，将实时道路状态、需求变化和抢修反馈转化为可用于优化模型的信息，并在统一算例和典型灾害数据基础上比较不同模型与算法的适用边界。通过这些工作，灾后道路修复与应急救灾车辆路径优化研究才能在既有集成模型基础上形成更具解释力和可验证性的知识积累。

## 参考文献

Akbari, V., & Salman, F. S. (2017). Multi-vehicle synchronized arc routing problem to restore post-disaster network connectivity. *European Journal of Operational Research, 257*(2), 625-640. https://doi.org/10.1016/j.ejor.2016.07.043

Akbari, V., & Sayarshad, H. R. (2022). Integrated and coordinated relief logistics and road recovery planning problem. *Transportation Research Part D: Transport and Environment, 111*, 103433. https://doi.org/10.1016/j.trd.2022.103433

Akbari, V., Shiri, D., & Salman, F. S. (2021). An online optimization approach to post-disaster road restoration. *Transportation Research Part B: Methodological, 150*, 1-25. https://doi.org/10.1016/j.trb.2021.05.017

Bai, Q., Zhou, C., Ren, X., Yang, Z., & Zhou, Z. (2026). Coordinating road recovery and supply distribution in emergency services: A distributionally robust optimisation approach. *European Journal of Operational Research, 333*(3), 762-776. https://doi.org/10.1016/j.ejor.2026.01.031

Caunhye, A. M., Aydin, N. Y., & Duzgun, H. S. (2020). Robust post-disaster route restoration. *OR Spectrum, 42*(4), 1055-1087. https://doi.org/10.1007/s00291-020-00601-0

Celik, M. (2016). Network restoration and recovery in humanitarian operations: Framework, literature review, and research directions. *Surveys in Operations Research and Management Science, 21*(2), 47-61. https://doi.org/10.1016/j.sorms.2016.12.001

Dantzig, G. B., & Ramser, J. H. (1959). The truck dispatching problem. *Management Science, 6*(1), 80-91. https://doi.org/10.1287/mnsc.6.1.80

Gong, H., Sheu, J. B., Wang, Z., Yang, X., & Yan, R. (2025). A unified model for multi-task drone routing in post-disaster road assessment. *arXiv preprint arXiv:2510.21525*. https://arxiv.org/abs/2510.21525

Huang, M., Smilowitz, K., & Balcik, B. (2012). Models for relief routing: Equity, efficiency and efficacy. *Transportation Research Part E: Logistics and Transportation Review, 48*(1), 2-18. https://doi.org/10.1016/j.tre.2011.05.004

Jiang, Y., & Yuan, Y. (2019). Emergency logistics in a large-scale disaster context: Achievements and challenges. *International Journal of Environmental Research and Public Health, 16*(5), 779. https://doi.org/10.3390/ijerph16050779

Kasaei, M., & Salman, F. S. (2016). Arc routing problems to restore connectivity of a road network. *Transportation Research Part E: Logistics and Transportation Review, 95*, 177-206. https://doi.org/10.1016/j.tre.2016.09.012

Li, S., & Teo, K. L. (2019). Post-disaster multi-period road network repair: Work scheduling and relief logistics optimization. *Annals of Operations Research, 283*, 1345-1385. https://doi.org/10.1007/s10479-018-3037-2

Maya Duque, P. A., Dolinskaya, I. S., & Sörensen, K. (2016). Network repair crew scheduling and routing for emergency relief distribution problem. *European Journal of Operational Research, 248*(1), 272-285. https://doi.org/10.1016/j.ejor.2015.06.026

Moreno, A., Alem, D., Gendreau, M., & Munari, P. (2020). The heterogeneous multicrew scheduling and routing problem in road restoration. *Transportation Research Part B: Methodological, 141*, 24-58. https://doi.org/10.1016/j.trb.2020.09.002

Nagy, G., & Salhi, S. (2007). Location-routing: Issues, models and methods. *European Journal of Operational Research, 177*(2), 649-672. https://doi.org/10.1016/j.ejor.2006.04.004

Ren, J., Zheng, W., Wu, Y., Li, X., Dong, Y., Kang, Y., Zhong, P., & Zhu, R. (2026). A multi-stage stochastic programming model for relief distribution networks considering road collapse. *Operations Research Perspectives, 16*, 100386. https://doi.org/10.1016/j.orp.2026.100386

Shin, Y., Kim, S., & Moon, I. (2019). Integrated optimal scheduling of repair crew and relief vehicle after disaster. *Computers & Operations Research, 105*, 237-247. https://doi.org/10.1016/j.cor.2019.01.015

Veysmoradi, D., Eydi, A., & Vahdani, B. (2024). The planning of the distribution of relief items and road network repair through multiple heterogeneous crews and prioritizing damaged roads under a flexible and uncertain environment. *Computers & Industrial Engineering, 196*, 110481. https://doi.org/10.1016/j.cie.2024.110481

Veysmoradi, D., Eydi, A., & Vahdani, B. (2025). Rescheduling and synchronization of relief operations in a dynamic and flexible environment considering aftershock effects. *Computers & Industrial Engineering, 208*, 111381. https://doi.org/10.1016/j.cie.2025.111381

Yan, S., & Shih, Y. L. (2009). Optimal scheduling of emergency roadway repair and subsequent relief distribution. *Computers & Operations Research, 36*(6), 2049-2065. https://doi.org/10.1016/j.cor.2008.07.002

Yang, X., Cao, W., Wang, K., Yin, H., Wu, J., & Wu, L. (2025). Integrated scheduling of truck and drone fleets for cargo transportation in post-disaster relief: A two-stage stochastic optimization approach. *Transportation Research Part E: Logistics and Transportation Review, 196*, 104015. https://doi.org/10.1016/j.tre.2025.104015

代颖, 马祖军, 朱道立, 方涛. (2012). 震后应急物资配送的模糊动态定位-路径问题. *管理科学学报, 15*(7), 60-70.

刘长石, 吴张, 马祖军, 周鲜成, 赵慎, 孙鹏. (2023). 通行受限下需求可拆分的应急物资卡车-多无人机协同配送路径优化. *系统科学与数学, 43*(11), 2930-2948. https://doi.org/10.12341/jssms23380

刘兴, 盛心誉, 郝墨卿, 徐泽水, 缑迅杰, 杨琴. (2026). 考虑灾后路况时空不确定的卡车-无人机协同应急配送路径优化. *中国管理科学*. 网络首发. https://doi.org/10.16381/j.cnki.issn1003-207x.2025.0834

曲冲冲, 王晶, 黄钧, 何明珂. (2018). 考虑时效与公平性的震后应急物资动态配送优化研究. *中国管理科学, 26*(6), 178-187. https://doi.org/10.16381/j.cnki.issn1003-207x.2018.06.018

孙华丽, 李泽平, 马腾. (2023). 道路修复联合应急设施选址-路径鲁棒优化研究. *系统工程理论与实践, 43*(9), 2701-2713. https://doi.org/10.12011/SETP2022-2617

孙华丽, 任雨欣, 田庭宁. (2026). 考虑道路修复的多周期应急设施选址-路径鲁棒优化研究. *中国管理科学*. 网络首发. https://doi.org/10.16381/j.cnki.issn1003-207x.2025.1960

王晶, 曲冲冲, 易显强. (2017). 道路修复条件下灾后应急资源配送 LRP 研究. *运筹与管理, 26*(12), 77-82.

王晶, 易显强, 张玲. (2014). 考虑道路可靠性的突发事件资源配送路线优化模型与算法. *系统科学与数学, 34*(9), 1128-1137. https://doi.org/10.12341/jssms12408

王晶, 易显强, 朱建明. (2016). 考虑道路修复的应急资源配送可靠路径选择问题研究. *运筹与管理, 25*(6), 99-104.

袁涛, 蔡佳, 郑磊, 户佐安. (2021). 考虑道路损毁情况的应急物流 LRP 研究. *铁道运输与经济, 43*(9), 30-37. https://doi.org/10.16668/j.cnki.issn.1003-1421.2021.09.06

张玲, 李继昭. (2023). 基于道路可靠性的应急救灾选址-路径随机优化问题研究. *系统科学与数学, 43*(10), 2480-2502. https://doi.org/10.12341/jssms22713

张梦玲, 王晶, 黄钧, 焦子豪. (2021). 基于手机定位数据的突发事件下道路修复和物资配送集成优化研究. *中国管理科学, 29*(3), 133-142. https://doi.org/10.16381/j.cnki.issn1003-207x.2021.03.13
