# Taichi 捏捏实验改进方案 (IMPROVEMENT_PLAN)

> 版本：v1.0
> 目标：在统一实验条件下，系统对比 Taichi 框架下 5 种软体模拟配置（MPM-NeoHookean / MPM-Corotated / FEM-NeoHookean / FEM-Corotated / PBD），输出高质量视觉结果和可解释的定量指标，形成可与 PyBullet / MuJoCo 队友对接的标准化实验规范。

---

## 1. 实验矩阵总览

| 配置 | 求解器 | 本构模型 | 可切换？ | 场景数 | 刚度档 | 总实验数 |
|---|---|---|---|---|---|---|
| 1 | MPM | Neo-Hookean | 是 | 2 | 2 | 4 |
| 2 | MPM | Corotated | 是 | 2 | 2 | 4 |
| 3 | FEM | Neo-Hookean | 是 | 2 | 2 | 4 |
| 4 | FEM | Corotated | 是 | 2 | 2 | 4 |
| 5 | PBD | — (基于约束) | 否 | 2 | 2 | 4 |
| **合计** | | | | | | **20 组** |

> 注：PBD 基于几何约束投影，不对应连续介质本构模型，因此无本构切换。

---

## 2. 统一实验规范（团队对接标准）

### 2.1 标准场景定义

所有实验必须至少完成以下 **2 个基准场景**，场景参数写入独立 JSON Schema，三种求解器共享同一套几何与运动协议。

| 场景 ID | 几何体 | 尺寸 | 用途 |
|---|---|---|---|
| `sphere_40mm` | 球体 | 直径 0.04 m | 最简单，力学曲线最干净，无几何奇点干扰 |
| `cube_50mm` | 圆角立方体 | 0.05×0.05×0.05 m | 更接近真实捏捏，可观察边角褶皱、局部凹陷和接触稳定性 |

> 复杂形状（动物/星形/爱心）仅作为最终展示素材，不参与主定量对比。

### 2.2 统一材料参数（两档刚度）

| 参数 | 软档 (Soft) | 硬档 (Hard) | 说明 |
|---|---|---|---|
| 密度 ρ | 1000 kg/m³ | 1000 kg/m³ | 水 / 软胶量级 |
| 杨氏模量 E | 30 kPa | 80 kPa | 软捏捏用低刚度；两档对比可观察求解器对刚度变化的响应 |
| 泊松比 ν | 0.35 | 0.35 | 先固定，避免高 ν 导致显式求解不稳定，干扰本构对比 |
| 阻尼 | 释放后约 5.0 s 基本静止 | 同上 | 真实捏捏回弹慢（5–10 s），延长观察窗口 |
| 摩擦系数 μ | 0.5 | 0.5 | 夹具与软体接触面 |
| 重力 g | 0 m/s² | 0 m/s² | 捏压主实验关闭重力，消除自由下落干扰 |

> 若 ν = 0.45 导致不稳定，报告中说明原因并保留 0.35 的结果。

### 2.3 统一夹具与运动协议（更新版）

恢复时间延长至 **5.0 s**，总仿真时长约 **6.5 s**，更贴近真实捏捏回弹节奏。

| 阶段 | 时间区间 | 动作描述 |
|---|---|---|
| 压缩 | 0.0 – 1.0 s | 匀速压缩至原始直径的 70% |
| 保持 | 1.0 – 1.5 s | 保持最大压缩，观察稳态力 |
| 释放 | 1.5 – 2.5 s | 匀速释放夹板 |
| 恢复 | 2.5 – 6.5 s | 自由回弹，观察残余形变与阻尼衰减 |
| 初始夹板间距 | 物体直径 × 1.05 | |
| 最小夹板间距 | 物体直径 × 0.70 | |

### 2.4 统一记录与导出标准

| 项目 | 建议值 |
|---|---|
| 内部仿真导出帧率 | 60 fps |
| 渲染保存策略 | 每帧保存 PNG，后期可合成 GIF / MP4 |
| 单帧仿真总时长 | 6.5 s → 390 帧 @ 60fps |
| 时间步记录 | 必须记录实际 `dt`、`substeps_per_frame` |
| 总能量记录 | 每帧记录动能 + 弹性能 |

---

## 3. 新增本构模型模块 (Phase 1)

### 3.1 设计目标

- 为 **MPM** 和 **FEM** 提供可切换的 **Neo-Hookean** 与 **Corotated Linear** 两种弹性模型。
- PBD 不引入本构模型，但配置文件中保留字段 `"constitutive_model": "none"` 以保持 schema 统一。
- 所有本构方程在报告和代码注释中显式写出，避免“没有本构模型”的批评。

### 3.2 模块结构

新建 `taichi_squeeze/src/constitutive.py`：

```python
# 伪代码示意
@ti.func
def neo_hookean_stress(F: ti.Matrix, mu: ti.f32, la: ti.f32) -> ti.Matrix:
    """
    Neo-Hookean 弹性模型：
    W = mu/2 * (I1 - 3) - mu * ln(J) + la/2 * (ln(J))^2
    PK1: P = mu * (F - F^{-T}) + la * ln(J) * F^{-T}
    """
    ...

@ti.func
def corotated_stress(F: ti.Matrix, mu: ti.f32, la: ti.f32) -> ti.Matrix:
    """
    Corotated Linear 弹性模型：
    P = 2*mu*(F - R) + la*(J - 1)*J*F^{-T}
    其中 F = R * S (极分解)
    """
    ...
```

### 3.3 集成方式

- **MPM3D**：在 `substep` kernel 中，将当前写死的应力计算替换为 `constitutive_stress(F, mu, la, model_type)` 调用。
- **FEM3D**：在 `compute_forces` 中，同样通过 `model_type` 参数切换应力计算。
- **JSON 配置**：新增字段 `"constitutive_model": "neo_hookean" | "corotated"`。
- **PBD**：`"constitutive_model": "none"`，报告中说明 PBD 基于约束投影而非连续介质力学。

---

## 4. 新增定量对比指标 (Phase 2)

在现有 `metrics.csv` 基础上，扩展以下指标。它们能更深刻地区分不同本构模型和求解器的行为差异。

| 指标 | 符号 | 计算方式 | 适用求解器 | 能说明什么 |
|---|---|---|---|---|
| **等效刚度** | $k_{eq}$ | F-d 曲线前 20% 压缩段线性拟合斜率 | MPM, FEM | 小变形区域软硬程度 |
| **峰值反力** | $F_{max}$ | 最大压缩时的 `plate_force_n` | MPM, FEM | 同样压缩量下谁更硬 |
| **滞回面积** | $A_{hys}$ | `trapz` 加载曲线与卸载曲线围成面积 | MPM, FEM | 能量耗散、阻尼效果、数值耗散大小 |
| **恢复时间** | $T_{95}$ | 释放后高度回到 95% 初始高度所需时间 | 全部 | 回弹速度，真实捏捏约 5–10 s |
| **能量漂移** | $\Delta E$ | \|(E_kin + E_elastic)_final - initial\| | 全部 | 数值稳定性，是否能量爆炸或过度耗散 |
| **接触力抖动** | $\sigma_F$ | 保持阶段 `plate_force_n` 的标准差 | MPM, FEM | 接触求解是否稳定、是否有高频震荡 |
| **Chamfer 距离** | $D_C$ | 当前粒子云与初始形状最近点平均距离 | 全部 | 复杂几何恢复程度，形状保真度 |
| **体积保持率均值** | $\bar{V}$ | 全程 `volume_ratio` 平均值 | MPM, FEM | 近似不可压缩软胶效果 |
| **体积保持率方差** | $\sigma_V^2$ | 全程 `volume_ratio` 方差 | MPM, FEM | 体积波动大小，数值稳定性 |

> **PBD 的力曲线**：报告中单独标注为“位置修正估算值（pseudo-force）”，不纳入与 MPM/FEM 的力-位移直接对比。PBD 的优势应体现在恢复曲线、Chamfer 距离、稳定性上。

---

## 5. 渲染升级：PyVista 高质量 60fps 输出 (Phase 3)

### 5.1 新增依赖

在 `environment.yml` 中加入：

```yaml
- pyvista
- trimesh
- scikit-image
```

> 三者均可在 conda 环境下通过 `conda install -c conda-forge pyvista trimesh scikit-image` 安装。

### 5.2 渲染策略

**推荐方案：PyVista 粒子球 + 环境光渲染**

- 每个粒子渲染为一个半透明小球体（`glyph`），`opacity=0.35`，`color=#ff6b6b`。
- 叠加方向光 + 环境光，夹板用灰色半透明面片。
- 统一背景色 `#f8f9fa`（浅灰白），避免 matplotlib 默认白底造成的视觉疲劳。
- 统一相机参数，写入独立 `camera.json`：
  - 位置：`elev=20, azim=-60`
  - 焦距：自动适配物体包围盒
  - 分辨率：960 × 720

**进阶方案（可选）：Marching Cubes 等值面**

- 对粒子云做密度场重建（网格计数或高斯核）。
- 用 `skimage.measure.marching_cubes` 提取等值面。
- 用 PyVista 渲染连续表面，更像真实软胶。
- 工作量较大，作为 Phase 3 的扩展任务。

### 5.3 输出规范

- 所有 5 种配置使用完全相同的 `camera.json` 和 `color_scheme.json`。
- 每帧输出 960×720 PNG。
- 合成 60 fps GIF，支持 1×5 横向并排对比（MPM-NH | MPM-CR | FEM-NH | FEM-CR | PBD）。
- 视频下方叠加实时高度、力、时间数值。

---

## 6. 跨引擎对接规范 (Phase 7)

即使队友尚未完成 PyBullet / MuJoCo，我们也先定义好标准，确保后续数据可以直接合并。

### 6.1 CSV 字段标准

与当前 `metrics.py` 的 `METRIC_COLUMNS` 完全一致：

```csv
engine,solver,scene,frame,t,dt,substeps,particles,grid_res,squeeze_disp_m,plate_force_n,height_m,width_m,volume_ratio,residual_strain,max_penetration_m,kinetic_energy,elastic_energy,wall_ms
```

> 某个引擎拿不到的字段填空，并在报告里说明原因。

### 6.2 命名与配置规范

| 项目 | 规范 |
|---|---|
| 场景命名 | `{shape}_{size}_{stiffness}`，如 `sphere_40mm_soft`、`cube_50mm_hard` |
| 输出目录 | `outputs/{engine}_{solver}_{scene}/` |
| 相机参数 | 共享 `camera.json` |
| 颜色方案 | 共享 `color_scheme.json` |
| 材料对照表 | 记录各引擎实际使用的参数（因为不同引擎参数定义可能不同） |

### 6.3 对接交付物

- `CROSS_ENGINE_SPEC.md`：完整规范文档
- `camera.json`：统一相机参数
- `color_scheme.json`：统一配色
- `template_metrics.csv`：空表模板，字段和格式示例

---

## 7. 报告结构重写建议 (Phase 6)

按以下逻辑重新组织报告，突出“本构模型对比”和“方法差异”两条主线：

1. **研究目标**
   - 不是“哪个画面最好看”，而是“同一框架下，不同物理方法（MPM/FEM/PBD）和不同本构模型（Neo-Hookean/Corotated）对软体大变形、接触、回弹的定量影响”。
2. **统一实验设置**
   - 场景、材料（两档刚度）、夹具、运动协议（延长恢复时间）。
3. **五种配置实现方法**
   - 分别说明 MPM-NeoHookean、MPM-Corotated、FEM-NeoHookean、FEM-Corotated、PBD 的求解流程和本构方程。
4. **本构模型对比**
   - Neo-Hookean vs Corotated 在 MPM 和 FEM 中的差异：力-位移斜率、滞回面积、体积保持、回弹时间。
5. **求解器对比**
   - MPM vs FEM vs PBD：稳定性、穿透、恢复、能量漂移、性能。
6. **定量结果**
   - 力-位移、滞回、等效刚度、恢复曲线、体积保持、能量、Chamfer 距离、性能。
7. **视觉结果**
   - 关键帧 + 60fps 并排视频 + 人工评价表。
8. **讨论**
   - 本构模型对结果的影响。
   - 不同求解器的取舍。
   - 参数敏感性与调参难度。
   - 与 PyBullet / MuJoCo 对接时的预期差异和注意事项。
9. **结论**
   - 针对“捏捏软体”给出方法-本构组合建议。

---

## 8. 执行阶段与时间表

| 阶段 | 任务 | 预计工作量 | 优先级 |
|---|---|---|---|
| **Phase 1** | 新建 `constitutive.py`，实现 Neo-Hookean / Corotated 双模型；MPM3D / FEM3D 接入配置切换 | 0.5 天 | P0 |
| **Phase 2** | 扩展 `metrics.py` 字段；在 `analysis/compare_curves.py` 中实现滞回面积、T95、能量漂移、Chamfer 距离等新指标计算与绘图 | 0.5 天 | P0 |
| **Phase 3** | 升级 `render3d.py`：引入 PyVista，统一相机/配色，输出 60fps 高质量 PNG 序列和 GIF | 1 天 | P1 |
| **Phase 4** | 生成全部 20 组实验的统一 JSON 配置（5 求解器 × 2 场景 × 2 刚度），验证 schema 一致性 | 0.5 天 | P0 |
| **Phase 5** | 批量运行 20 组实验，生成 `metrics.csv`、分析图表、并排视频 | 1–2 天 | P0 |
| **Phase 6** | 重写 `report.md`，按新结构组织，突出本构对比和求解器对比 | 1 天 | P1 |
| **Phase 7** | 编写 `CROSS_ENGINE_SPEC.md`、`camera.json`、`color_scheme.json`，与队友对接 | 0.5 天 | P2 |

---

## 9. 待确认问题

本方案已根据你的反馈做了以下调整：

1. ✅ **恢复时间延长至 5.0 s**（总时长 6.5 s），更贴近真实捏捏。
2. ✅ **引入 PyVista 渲染**，依赖通过 conda-forge 安装。
3. ✅ **两档刚度（30 kPa / 80 kPa）全部执行**。
4. ✅ **两个基准场景（sphere / cube）全部执行**。
5. ✅ **5 种配置对比**：MPM-NeoHookean、MPM-Corotated、FEM-NeoHookean、FEM-Corotated、PBD。

**最后需要你确认两点**：

- **PBD 的体积计算**：当前 PBD 没有 `volume_ratio`。是否给 PBD 加一个近似体积估计（如凸包体积或 3D alpha shape），让 5 条曲线都能在体积保持图上出现？
- **开始执行**：确认本方案无误后，我将从 **Phase 1（本构模型模块）** 开始逐步执行，每完成一个 Phase 会向你汇报结果。
