# Taichi 捏捏实验改进方案 (IMPROVEMENT_PLAN)

> 版本：v1.1 — Agent 执行手册
> 目标：在统一实验条件下，系统对比 Taichi 框架下 5 种软体模拟配置（MPM-NeoHookean / MPM-Corotated / FEM-NeoHookean / FEM-Corotated / PBD），输出高质量视觉结果和可解释的定量指标，形成可与 PyBullet / MuJoCo 队友对接的标准化实验规范。

---

## 0. 环境要求（必须遵守）

### 0.1 Conda 环境

**所有代码执行、测试、渲染必须在名为 `GKCIV` 的 conda 环境中进行。**

```powershell
# 激活环境
conda activate GKCIV

# 若环境未创建，使用项目根目录的 environment.yml
conda env create -f environment.yml
conda activate GKCIV
```

> **注意**：Windows PowerShell 中 `conda activate` 后不能直接用 `&&` 连接命令。正确方式是：
> ```powershell
> conda activate GKCIV
> python -m taichi_squeeze.src.simulate_mpm3d ...
> ```
> 或使用 `conda run -n GKCIV python ...`。

### 0.2 已安装的依赖

`environment.yml` 中已包含：

```yaml
dependencies:
  - python=3.11
  - pip
  - pyvista          # 3D 渲染
  - trimesh          # 网格处理
  - scikit-image     # Marching Cubes
  - scipy            # 科学计算
  - pip:
      - taichi
      - numpy
      - pandas
      - matplotlib
      - imageio
      - opencv-python
```

若新增依赖，必须同时更新 `environment.yml`。

### 0.3 Taichi 后端

当前开发机使用 **CPU 后端**（`arch=ti.cpu`）。GPU 后端（`ti.cuda` / `ti.vulkan`）仅在 5060 机器上测试，不要在本机默认启用。

---

## 1. 当前代码状态（重要）

用户已清理旧文件，**当前保留的核心代码**如下：

```
Final_Project_GKCIV/
  environment.yml                     # 已更新，含 pyvista/trimesh/scikit-image/scipy
  IMPROVEMENT_PLAN.md               # 本文件
  taichi_squeeze/
    src/
      __init__.py
      metrics.py                    # METRIC_COLUMNS 定义
      render3d.py                   # matplotlib 3D scatter 渲染（待升级到 PyVista）
      simulate_mpm3d.py             # MPM 3D 求解器（已接入本构切换）
      simulate_fem3d.py             # FEM 3D 求解器（已接入本构切换）
      simulate_pbd3d.py             # PBD 3D 求解器（无本构切换）
      constitutive.py               # 【新增】Neo-Hookean + Corotated 双本构模型
    analysis/
      __init__.py
      compare_curves.py             # 分析脚本（待扩展新指标）
  outputs/                            # 实验输出目录
```

**已删除的旧文件**（不要恢复）：
- `taichi_squeeze_experiment_plan.md`
- `taichi_squeeze/IMPROVEMENT_PLAN.md`
- `taichi_squeeze/configs/*.json`（所有旧配置）
- `taichi_squeeze/src/simulate_mpm.py`（2D MPM）
- `taichi_squeeze/src/render.py`（2D 渲染）
- `report/` 和 `report_20s/` 目录（旧报告）
- `proposal-捏捏.pdf`

---

## 2. 实验矩阵总览

| 编号 | 求解器 | 本构模型 | 场景数 | 刚度档 | 总实验数 |
|---|---|---|---|---|---|
| 1 | MPM | Neo-Hookean | 2 | 2 | 4 |
| 2 | MPM | Corotated | 2 | 2 | 4 |
| 3 | FEM | Neo-Hookean | 2 | 2 | 4 |
| 4 | FEM | Corotated | 2 | 2 | 4 |
| 5 | PBD | — (基于约束) | 2 | 2 | 4 |
| **合计** | | | | | **20 组** |

> PBD 基于几何约束投影，不对应连续介质本构模型，因此无本构切换。配置文件中写 `"constitutive_model": "none"` 以保持 schema 统一。

---

## 3. 统一实验规范（团队对接标准）

### 3.1 标准场景

| 场景 ID | 几何体 | 尺寸 | 用途 |
|---|---|---|---|
| `sphere_40mm` | 球体 | 直径 0.04 m | 最简单，力学曲线最干净 |
| `cube_40mm` | 立方体 | 0.04×0.04×0.04 m | 与 40 mm 球体使用相同夹板行程，观察边角变形 |

### 3.2 统一材料参数（两档刚度）

| 参数 | 软档 (Soft) | 硬档 (Hard) |
|---|---|---|
| 密度 ρ | 1000 kg/m³ | 1000 kg/m³ |
| 杨氏模量 E | 30 kPa | 80 kPa |
| 泊松比 ν | 0.35 | 0.35 |
| 阻尼 | 释放后约 5.0 s 基本静止 | 同上 |
| 摩擦系数 μ | 0.5 | 0.5 |
| 重力 g | 0 m/s² | 0 m/s² |

### 3.3 统一夹具与运动协议

总仿真时长 **6.5 s**（60 fps → 390 帧）。

| 阶段 | 时间区间 | 动作 |
|---|---|---|
| 压缩 | 0.0 – 1.0 s | 匀速压缩至原始直径的 50% |
| 保持 | 1.0 – 1.5 s | 保持最大压缩 |
| 释放 | 1.5 – 2.5 s | 匀速释放 |
| 恢复 | 2.5 – 6.5 s | 自由回弹 |
| 初始间距 | 物体直径 × 1.05 | |
| 最小间距 | 物体直径 × 0.50 | |

接触容差必须小于初始单侧余隙；当前推荐 `contact_skin_m = 0.00025`，40 mm 物体初始板面间距为 42 mm，考虑两侧 skin 后仍保留约 0.75 mm 单侧有效余隙。

### 3.4 统一导出标准

| 项目 | 值 |
|---|---|
| 帧率 | 60 fps |
| 总帧数 | 390 帧（6.5 s） |
| 渲染 | 每帧 PNG，后期合成 GIF/MP4 |
| 分辨率 | 960 × 720 |

---

## 4. Phase 执行指南（按顺序执行）

### Phase 1：本构模型模块（已完成，待冒烟测试）

**状态**：代码已写，冒烟测试被用户中断，需要重新验证。

**已完成**：
- ✅ 新建 `taichi_squeeze/src/constitutive.py`
- ✅ MPM3D 接入本构切换（`constitutive_model` 字段 + kernel 分支）
- ✅ FEM3D 接入本构切换（`compute_forces` 参数 + 应力/能量统一）
- ✅ 能量计算 `compute_energy` 也切换了对应本构的能量密度

**待验证**：
- 跑 `--frames 10 --no-render` 冒烟测试（MPM/FEM 各一种配置）
- 写一个新 JSON 配置测试 `neo_hookean` 切换是否生效

**冒烟测试命令**：
```powershell
conda activate GKCIV

# MPM 默认 corotated
python -m taichi_squeeze.src.simulate_mpm3d --config taichi_squeeze/configs/sphere_3d_40mm_soft.json --frames 10 --no-render

# FEM 默认 corotated
python -m taichi_squeeze.src.simulate_fem3d --config taichi_squeeze/configs/sphere_3d_40mm_fem.json --frames 10 --no-render
```

> 注意：所有旧 JSON 配置已被用户删除，需要先重建。见 Phase 4。

---

### Phase 2：扩展定量指标

**目标**：在 `metrics.py` 和 `analysis/compare_curves.py` 中新增以下指标。

| 指标 | 计算方式 | 脚本位置 |
|---|---|---|
| 等效刚度 $k_{eq}$ | F-d 曲线前 20% 段线性拟合 | `compare_curves.py` |
| 峰值反力 $F_{max}$ | 最大 `plate_force_n` | 已有，直接读取 |
| 滞回面积 $A_{hys}$ | `trapz` 加载-卸载围成面积 | `compare_curves.py` |
| 恢复时间 $T_{95}$ | 释放后高度回到 95% 初始高度时间 | `compare_curves.py` |
| 能量漂移 $\Delta E$ | \|$(E_{kin}+E_{elastic})_{final} - initial$\| | `compare_curves.py` |
| 接触力抖动 $\sigma_F$ | 保持阶段 `plate_force_n` 标准差 | `compare_curves.py` |
| Chamfer 距离 $D_C$ | 当前粒子云与初始形状最近点平均距离 | 新增函数，写入 `metrics.py` 或后处理 |
| 体积保持率统计 | 均值 / 方差 | `compare_curves.py` |

**PBD 特殊处理**：
- `plate_force_n` 是位置修正估算值（pseudo-force），报告里单独标注，不直接与 MPM/FEM 比力大小。
- PBD 当前无 `volume_ratio`。方案：用 `scipy.spatial.ConvexHull` 估算凸包体积作为近似体积比。

---

### Phase 3：渲染升级

**目标**：把 `render3d.py` 从 matplotlib scatter 升级到 PyVista 高质量渲染。

**策略**：
1. 新建 `taichi_squeeze/src/render_pyvista.py`，实现 `render_frame_pyvista()`。
2. 每个粒子渲染为小球体（`glyph`），半透明，叠加方向光。
3. 统一相机参数从 `camera.json` 读取。
4. 每帧 960×720 PNG。
5. 合成 60 fps GIF / MP4。
6. 并排视频：1×5（MPM-NH | MPM-CR | FEM-NH | FEM-CR | PBD）。

**依赖已装**：`pyvista`, `trimesh`, `scikit-image`

---

### Phase 4：生成 20 组统一 JSON 配置

**目标**：为 5 求解器 × 2 场景 × 2 刚度 = 20 组实验生成完整配置。

**配置目录**：`taichi_squeeze/configs/`

**命名规范**：`{solver}_{scene}_{stiffness}.json`

示例：
- `mpm3d_sphere_40mm_soft.json`
- `mpm3d_sphere_40mm_hard.json`
- `fem3d_cube_40mm_soft.json`
- `pbd3d_sphere_40mm_soft.json`

**每个配置必须包含**：
- `"constitutive_model"`: `"neo_hookean"` / `"corotated"` / `"none"`
- `"solver"`: `"mpm3d"` / `"fem3d"` / `"pbd3d"`
- 统一场景参数（尺寸、中心、密度、E、ν）
- 统一运动协议（压缩/保持/释放/恢复时间）
- 统一导出参数（fps=60, max_frames=390）
- 求解器特定参数（n_particles/n_grid、mesh_resolution、lattice_resolution、dt、substeps 等）

---

### Phase 5：批量运行实验

**目标**：跑完 20 组实验，生成 metrics.csv + PNG 帧。

**批量脚本**：写一个 `run_all.py` 自动遍历 `taichi_squeeze/configs/*.json`，依次调用对应 solver，并记录日志。

**注意事项**：
- FEM 计算慢（~300ms/frame），可酌情减少 substeps 或降低 mesh_resolution。
- 每跑完一组就 `git add outputs/` 里的结果，但不要频繁 commit（等一个 Phase 跑完再 commit）。

---

### Phase 6：重写报告

**目标**：按新结构写 `report.md`。

**报告结构**：
1. 研究目标
2. 统一实验设置
3. 五种配置实现方法 + 本构方程
4. 本构模型对比（Neo-Hookean vs Corotated）
5. 求解器对比（MPM vs FEM vs PBD）
6. 定量结果（力-位移、滞回、刚度、恢复、体积、能量、Chamfer）
7. 视觉结果（关键帧 + 60fps 并排视频）
8. 讨论（本构影响、求解器取舍、参数敏感性、跨引擎对接）
9. 结论

---

### Phase 7：跨引擎对接规范

**目标**：编写 `CROSS_ENGINE_SPEC.md`、`camera.json`、`color_scheme.json`，为 PyBullet / MuJoCo 队友提供标准。

**交付物**：
- `CROSS_ENGINE_SPEC.md`：字段定义、命名规范、单位约定
- `camera.json`：统一相机参数（elev, azim, zoom, resolution, bgcolor）
- `color_scheme.json`：软体颜色、夹板颜色、背景色
- `template_metrics.csv`：空 CSV 模板，字段示例

---

## 5. GitHub 提交规范

**用户要求**：每做完一个 Phase，确认功能正常后提交一次 GitHub。

**提交流程**：
```powershell
git add -A
git commit -m "feat: Phase X 描述"
git push origin main
```

**提交信息风格**：
- `feat:` 新功能/模块
- `fix:` 修复 bug
- `refactor:` 重构
- `chore:` 配置/依赖更新
- `docs:` 文档

**不要提交**：
- 巨大的 `outputs/` 目录（尤其是 PNG 帧序列）。在 `.gitignore` 中加入 `outputs/*/frames/`。
- 已编译的 PDF/视频二进制文件（如有）。

---

## 6. 已知问题与注意事项

1. **Taichi 1.7 的 `@ti.func` 不支持 `ti.Matrix` 类型注解**。`constitutive.py` 中的 `@ti.func` 参数已去掉类型注解，保持原样。
2. **Taichi kernel 中 if-else 分支内定义的变量在分支外不可见**。已用“先初始化再赋值”方式解决（如 `pf_ft = ti.Matrix.zero(...)`）。后续修改 kernel 时注意此限制。
3. **PBD 的力不是物理反力**。报告中必须明确标注为 pseudo-force，避免与 MPM/FEM 直接比较力大小。
4. **FEM 当前是 Python/NumPy 实现，未用 Taichi kernel 加速**。每帧 ~300ms，是性能瓶颈。Phase 5 批量运行时注意控制 mesh_resolution。
5. **Windows 路径含中文**。Taichi 1.7 关机时可能有 UnicodeDecodeError，已通过 `os._exit(0)` 规避，不要删除该代码。

---

## 7. 快速参考命令

```powershell
# 激活环境
conda activate GKCIV

# MPM 3D 短帧测试
python -m taichi_squeeze.src.simulate_mpm3d --config taichi_squeeze/configs/XXX.json --frames 10 --no-render

# FEM 3D 短帧测试
python -m taichi_squeeze.src.simulate_fem3d --config taichi_squeeze/configs/XXX.json --frames 10 --no-render

# PBD 3D 短帧测试
python -m taichi_squeeze.src.simulate_pbd3d --config taichi_squeeze/configs/XXX.json --frames 10 --no-render

# 生成分析图表
python -m taichi_squeeze.analysis.compare_curves --outputs outputs --contains sphere --out outputs/analysis_sphere

# Git 提交
git add -A
git commit -m "feat: Phase X 描述"
git push origin main
```

---

> **Agent 接手时请先阅读本文件，按 Phase 顺序执行，不要跳过。每完成一个 Phase 后向用户汇报并请求确认，然后提交 GitHub 再进入下一个 Phase。**
