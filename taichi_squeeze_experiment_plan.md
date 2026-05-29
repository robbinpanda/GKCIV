# Taichi 捏捏软体仿真实验方案

## 0. 任务定位

本项目建议从“做一个看起来像捏捏的视频”改成“在统一捏压实验条件下，对比 PyBullet、MuJoCo、Taichi 对软体大变形接触的模拟效果”。三位队员分别实现一个引擎，我负责 Taichi。最终结果应同时包含：

- 统一场景下的视觉对比视频和关键帧。
- 力学曲线和恢复曲线等定量指标。
- 性能、稳定性、调参难度和实现复杂度对比。

Taichi 与 PyBullet、MuJoCo 的定位不同：Taichi 更像高性能物理仿真编程框架，不是一个固定软体引擎。因此 Taichi 部分可以实现不同物理方法，例如 MPM、FEM、mass-spring 或 PBD，并用同一套实验输入对比它们的效果。

## 1. 需要统一的实验输入

为了让不同引擎的结果有可比性，必须统一以下条件。否则视觉差异可能只是形状、尺寸、时间步或夹具不同造成的。

### 1.1 推荐统一物体

建议至少做两个几何体：

| 场景 | 几何体 | 尺寸 | 用途 |
|---|---|---:|---|
| A | 球体或椭球体 | 直径 50 mm | 最简单，适合看整体压缩、回弹和体积保持 |
| B | 圆角立方体 | 50 mm x 50 mm x 50 mm | 更接近捏捏玩具，能观察边角、局部褶皱和接触伪影 |
| C，可选 | 简化动物/星形/爱心 | 最大外径 50 mm | 展示复杂形状，但不作为主要定量比较 |

主实验不要一开始就用复杂模型。复杂模型适合最终展示，定量对比应以球体和圆角立方体为主。

### 1.2 推荐统一材料参数

使用 SI 单位，方便三个人互相对齐。

| 参数 | 建议值 | 说明 |
|---|---:|---|
| 密度 rho | 1000 kg/m^3 | 接近水/软胶量级 |
| 杨氏模量 E | 30 kPa、80 kPa 两档 | 软捏捏可以用低刚度；做两档能观察引擎对刚度变化的响应 |
| 泊松比 nu | 0.35 或 0.45 | 0.45 更接近近似不可压缩材料，但数值更难稳定 |
| 阻尼 | 统一调到“释放后 1-2 s 基本静止” | 不同引擎阻尼定义不同，建议用恢复曲线校准 |
| 摩擦系数 | 0.5 | 夹具和软体接触 |
| 重力 | 可关闭；若开启，统一 -9.81 m/s^2 | 捏压主实验建议先关闭重力 |

如果 PyBullet、MuJoCo、Taichi 的材料模型不能一一对应，就统一“现象级目标”：相同压缩深度下的峰值力、回弹时间、残余变形尽量接近，然后记录每个引擎实际使用的参数。

### 1.3 推荐统一夹具和动作

主实验使用两个刚性平板对物体进行对称挤压。

- 初始距离：略大于物体直径，例如 52 mm。
- 压缩深度：压到原始直径的 70%，即 50 mm 物体压到 35 mm。
- 动作过程：
  - 0.0-1.0 s：匀速压缩。
  - 1.0-1.5 s：保持最大压缩。
  - 1.5-2.5 s：匀速释放。
  - 2.5-4.0 s：自由恢复。
- 时间步：统一导出 240 fps 的记录；每个引擎内部可使用 substep，但必须记录实际 substep 数。

局部捏压可以作为第二实验：用两个小球形指尖或圆柱指尖从两侧挤压，观察局部凹陷和接触稳定性。

## 2. 除视觉效果外的对比参数

视觉效果很重要，但最好搭配以下指标。它们能说明不同仿真引擎和求解方法的差异。

### 2.1 力学响应

| 指标 | 计算方式 | 能说明什么 |
|---|---|---|
| 力-位移曲线 F-d | 记录夹板位移和接触反力 | 软硬程度、非线性响应、是否过度发硬 |
| 等效刚度 k | F-d 曲线前 20% 压缩段斜率 | 小变形区域的软硬 |
| 峰值反力 | 最大压缩时的接触力 | 同样压缩量下谁更硬 |
| 滞回面积 | 加载曲线和卸载曲线围成面积 | 能量耗散、阻尼效果 |
| 接触力抖动 | 接触力时间序列标准差或高频波动 | 接触求解是否稳定 |

### 2.2 形变和恢复

| 指标 | 计算方式 | 能说明什么 |
|---|---|---|
| 最大压缩率 | 1 - 当前高度 / 初始高度 | 形变幅度 |
| 残余形变 | 释放 1.5 s 后的高度误差或表面误差 | 是否能恢复原状 |
| 恢复时间 | 回到 95% 初始高度所需时间 | 回弹速度 |
| 体积保持率 | 当前体积 / 初始体积 | 近似不可压缩软胶效果 |
| 表面误差 | 与初始形状或参考形状的 Chamfer distance | 复杂几何恢复程度 |

### 2.3 数值稳定性

| 指标 | 记录方式 | 能说明什么 |
|---|---|---|
| 最大稳定时间步 | 逐渐增大 dt，观察是否爆炸或穿透 | 求解器稳定区域 |
| 穿透深度 | 软体进入夹板的最大深度 | 接触处理质量 |
| 能量漂移 | 动能、弹性能、耗散后的总能量趋势 | 数值耗散或能量爆炸 |
| 参数敏感性 | 改 E、nu、阻尼后是否需要大量重调 | 工程可用性 |

### 2.4 性能和工程成本

| 指标 | 记录方式 |
|---|---|
| 每步耗时 | ms/step，排除渲染和包含渲染各记录一次 |
| 实际 FPS | 交互运行帧率和离线导出帧率 |
| 粒子/节点/网格数量 | Taichi 记录 particles、grid；MuJoCo/PyBullet 记录 mesh/flex/body 数 |
| 内存占用 | 任务管理器或 Python psutil |
| 代码量 | 核心仿真代码行数，不含分析脚本 |
| 调参时间 | 从能跑到稳定好看的大致时间 |

## 3. Taichi 是否可以做多种物理方法

可以。Taichi 不是固定软体求解器，而是用 Python 写高性能并行 kernel 的框架，所以同一个 Taichi 项目可以实现不同软体方法。

推荐优先级如下：

| 方法 | 推荐程度 | 特点 | 适合本项目吗 |
|---|---|---|---|
| MLS-MPM / MPM | 高 | 适合大变形、软材料、接触；粒子和背景网格混合 | 很适合捏捏主实验 |
| mass-spring / PBD | 中 | 好写、快、视觉直观，但物理参数不够真实 | 适合作为 Taichi 内部第二效果对比 |
| FEM | 中 | 物理意义强，适合弹性体；但四面体网格和接触更麻烦 | 时间足够时可做 |

建议 Taichi 部分至少完成一个主方法：MLS-MPM 弹性体捏压。若时间允许，再做一个简化 mass-spring/PBD 版本。这样可以在报告中说明：“Taichi 作为框架，同一个平台下不同求解方法会带来不同视觉和物理表现。”

注意：如果加入 Taichi-MPM 和 Taichi-PBD 两个结果，应把它们标成“Taichi-MPM”和“Taichi-PBD”，不要简单说“Taichi 有两个结果”。否则会混淆“引擎差异”和“算法差异”。

## 4. CPU 是否够用，是否需要 CUDA

结论：

- 纯 CPU 可以做，尤其是 2D 原型、低分辨率 3D、离线导出短视频时完全可行。
- 如果只用 `ti.init(arch=ti.cpu)`，不需要安装 CUDA，也不依赖 NVIDIA 显卡。
- 4800U 可以作为开发和低分辨率实验机器使用；不要期待高分辨率 3D MPM 实时流畅。
- 5060 独显机器适合最终高分辨率 3D 或更高粒子数版本，但需要正确的 NVIDIA 驱动，并测试 Taichi 的 `ti.cuda` 或 `ti.vulkan` 后端。

建议工作流：

1. 在 4800U 上用 CPU 写通核心逻辑。
2. 粒子数先控制在 2D 128x128 或 3D 8000-30000 particles。
3. 最终展示视频如果 CPU 太慢，再迁移到 5060 机器跑 GPU。
4. GPU 后端优先尝试：

```python
import taichi as ti

ti.init(arch=ti.cpu)      # 最稳，CPU 版本
# ti.init(arch=ti.cuda)   # NVIDIA CUDA 后端
# ti.init(arch=ti.vulkan) # 跨平台 GPU 后端，可作为 CUDA 不稳定时的备选
```

Taichi 官方文档说明可以通过 `ti.init(arch=ti.cuda)` 指定 CUDA 后端，也可以用 `ti.gpu` 自动尝试 GPU 后端；如果选择 GPU 后端，需要系统中对应后端可用。官方安装页和 PyPI 页面显示 Taichi 可通过 `pip install taichi` 安装，并支持 CPU、CUDA、Vulkan、OpenGL、Metal 等后端。

## 5. Taichi 实验全链路方案

### 5.1 目录结构

建议建立如下结构：

```text
taichi_squeeze/
  configs/
    sphere_50mm_soft.json
    cube_50mm_soft.json
  src/
    simulate_mpm.py
    simulate_pbd_optional.py
    metrics.py
    render.py
  outputs/
    taichi_mpm_sphere/
      frames/
      metrics.csv
      preview.mp4
    taichi_mpm_cube/
      frames/
      metrics.csv
      preview.mp4
  analysis/
    compare_curves.py
    plots/
```

### 5.2 环境配置

Windows PowerShell 示例：

```powershell
conda create -n GKCIV python=3.11 -y
conda activate GKCIV
python -m pip install --upgrade pip
python -m pip install taichi numpy pandas matplotlib imageio opencv-python
```

也可以使用项目中的 `environment.yml` 一次性创建隔离环境：

```powershell
conda env create -f environment.yml
conda activate GKCIV
```

验证 CPU 后端：

```powershell
python -c "import taichi as ti; ti.init(arch=ti.cpu); print(ti.__version__)"
```

如果在 5060 机器上测试 GPU：

```powershell
nvidia-smi
python -c "import taichi as ti; ti.init(arch=ti.cuda); print('cuda ok')"
python -c "import taichi as ti; ti.init(arch=ti.vulkan); print('vulkan ok')"
```

如果 CUDA 初始化失败，不影响 CPU 实验。可以先固定使用 `arch=ti.cpu` 完成项目主体。

### 5.3 Taichi-MPM 代码设计

核心数据：

- 粒子位置 `x[p]`
- 粒子速度 `v[p]`
- 形变梯度 `F[p]`
- 仿射速度场 `C[p]`
- 背景网格速度 `grid_v[i, j, k]`
- 背景网格质量 `grid_m[i, j, k]`
- 夹板位置 `plate_left(t)`、`plate_right(t)`

每个 substep 的流程：

1. 清空背景网格。
2. P2G：粒子质量、动量、弹性应力转移到网格。
3. 网格更新：加入外力、阻尼、夹板接触约束。
4. 记录夹板接触反力或接触冲量。
5. G2P：从网格回传粒子速度，更新位置和形变梯度。
6. 计算并记录体积、高度、宽度、动能、弹性能、运行耗时。

材料模型建议先用 Neo-Hookean 弹性模型。参数由 `E` 和 `nu` 转成 Lamé 参数：

```text
mu = E / (2 * (1 + nu))
lambda = E * nu / ((1 + nu) * (1 - 2 * nu))
```

如果 `nu = 0.45` 导致数值不稳定，先降到 `0.35`，并在报告里说明高泊松比对显式求解更困难。

### 5.4 可选 Taichi-PBD 或 mass-spring 版本

如果时间允许，做一个更简单的点阵弹簧模型：

- 把软体采样成规则点阵。
- 相邻点之间加结构弹簧、剪切弹簧、体积保持约束。
- 两侧夹板用位置约束或 penalty force。
- 输出同样的 `metrics.csv`。

这个版本的价值不是“更真实”，而是展示不同算法的取舍：

- PBD/mass-spring 更容易稳定和实时。
- MPM 更适合连续介质和大变形。
- PBD 的刚度参数通常不是严格物理单位，和 MuJoCo/PyBullet 对齐会更难。

### 5.5 数据记录格式

每次仿真输出一个 CSV：

```csv
engine,solver,scene,frame,t,dt,substeps,particles,grid_res,squeeze_disp_m,plate_force_n,height_m,width_m,volume_ratio,residual_strain,max_penetration_m,kinetic_energy,elastic_energy,wall_ms
taichi,mpm,sphere_50mm,0,0.000,0.004167,20,20000,64,0.000,0.000,0.050,0.050,1.000,0.000,0.000,0.000,0.000,12.4
```

三个人最好统一 CSV 字段。某个引擎拿不到的字段可以填空，但要说明原因。例如有些接触力可能只能近似估计。

### 5.6 分析脚本

分析脚本读取三个引擎的 CSV，输出以下图：

1. `force_displacement.png`：横轴压缩位移，纵轴接触反力。
2. `height_time.png`：物体高度随时间变化。
3. `volume_ratio_time.png`：体积保持率随时间变化。
4. `recovery_error_time.png`：释放后残余形变随时间变化。
5. `performance_ms_step.png`：每步耗时或每帧耗时。
6. `stability_table.md`：最大稳定时间步、是否穿透、是否爆炸、是否需要大量调参。

为了公平，曲线横轴优先用归一化压缩量：

```text
normalized_compression = squeeze_disp_m / initial_diameter_m
```

这样即使不同场景尺寸稍有差异，也能比较趋势。

### 5.7 视觉对比

视觉对比必须统一：

- 相同相机角度。
- 相同光照和背景。
- 相同物体颜色，或不同引擎用固定颜色。
- 相同导出帧率，例如 30 fps。
- 固定关键帧：初始、25% 压缩、50% 压缩、最大压缩、释放中、恢复结束。

最终视频建议做成 2 x 2 或 1 x 3 拼接：

```text
PyBullet | MuJoCo | Taichi-MPM
```

如果有 Taichi-PBD：

```text
PyBullet | MuJoCo
Taichi-MPM | Taichi-PBD
```

视觉评价可以用人工打分表，但要配合定量指标：

| 项目 | 评分 1-5 | 说明 |
|---|---:|---|
| 形变自然程度 |  | 是否像软胶被挤压 |
| 回弹自然程度 |  | 是否过快、过慢或抖动 |
| 接触稳定性 |  | 是否穿透、抖动、粘住 |
| 体积感 |  | 是否像不可压缩软体 |
| 表面质量 |  | 是否破碎、锯齿、粒子感过强 |

## 6. 建议实验日程

| 阶段 | 目标 | 产出 |
|---|---|---|
| 第 1 天 | 搭好 Taichi CPU 环境，跑通 2D 或低分辨率 3D MPM | 初版视频、可运行脚本 |
| 第 2 天 | 加入夹板捏压流程和 CSV 记录 | `metrics.csv` |
| 第 3 天 | 调材料参数，完成球体和圆角立方体 | 两个场景结果 |
| 第 4 天 | 写分析脚本，画力-位移、恢复、性能曲线 | 图表 |
| 第 5 天 | 与队友统一数据格式，拼接视频和写报告 | 对比表、最终视频 |
| 可选 | 加 Taichi-PBD 或 mass-spring | Taichi 内部算法对比 |

## 7. 最终报告建议结构

1. 研究目标：比较不同物理仿真引擎模拟捏捏软体的表现。
2. 统一实验设置：形状、尺寸、材料、夹具、动作、时间步。
3. 三个引擎实现方法：
   - PyBullet：软体/约束/接触设置。
   - MuJoCo：soft body/flex/mesh 设置。
   - Taichi：MPM 或 MPM + PBD。
4. 定量结果：
   - 力-位移曲线。
   - 回弹曲线。
   - 体积保持率。
   - 接触穿透和稳定性。
   - 运行性能。
5. 视觉结果：关键帧和视频拼接。
6. 讨论：
   - 哪个引擎更容易做出稳定结果。
   - 哪个引擎物理参数更可解释。
   - 哪个引擎视觉效果更自然。
   - Taichi 中不同算法带来的差异。
7. 结论：给出针对“捏捏软体”的引擎选择建议。

## 8. 对四个关键问题的简短回答

1. 可以对比的参数很多，不应只看视觉效果。推荐重点看力-位移曲线、等效刚度、滞回面积、回弹时间、残余形变、体积保持率、穿透深度、稳定时间步和每步耗时。形状和尺寸最好统一，至少统一球体和圆角立方体两个基础场景。
2. Taichi 可以使用不同物理方法。一个 Taichi 项目可以实现 MPM、FEM、mass-spring、PBD 等，因此可以出现 Taichi-MPM 和 Taichi-PBD 两种效果对比。但报告里要明确这是算法差异，不只是 Taichi 本身差异。
3. 纯 CPU 版本够做原型和低分辨率实验，不需要 CUDA。4800U 可以跑 CPU 版，但高分辨率 3D MPM 可能比较慢。5060 机器适合最终高粒子数结果，使用前测试 `ti.cuda` 或 `ti.vulkan`。
4. 全链路方案按“环境配置 - Taichi-MPM 实现 - 数据记录 - 图表分析 - 视频拼接 - 报告讨论”执行即可。优先保证统一实验条件和 CSV 输出，再追求视觉精细度。

## 9. 参考资料

- Taichi PyPI 页面：<https://pypi.org/project/taichi/>
- Taichi 全局后端设置文档：<https://docs.taichi-lang.org/docs/global_settings>
- Taichi 物理仿真示例文档：<https://docs.taichi-lang.org/docs/cloth_simulation>
- Taichi GitHub 仓库：<https://github.com/taichi-dev/taichi>
