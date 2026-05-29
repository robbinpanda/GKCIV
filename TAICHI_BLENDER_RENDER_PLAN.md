# Taichi + Blender Realistic Rendering Follow-Up Plan

生成日期：2026-05-30

## 1. 结论

可以使用 **Taichi + Blender** 获得更逼真的结果，但建议把二者分工明确：

- **Taichi**：继续负责软体动力学仿真、接触、材料模型、指标输出。
- **Blender**：只负责高质量离线渲染，包括材质、灯光、相机、夹板外观、阴影和视频输出。

不建议把 Blender 作为物理求解器使用。Blender 的刚体/软体系统不适合替代当前 Taichi 实验矩阵，否则会破坏实验可比性。

## 2. 推荐选用的 Taichi 结果

推荐使用：

```text
outputs/mpm3d_cube_40mm_soft_corotated
```

选择理由：

| 指标 | 结果 | 说明 |
|---|---:|---|
| 求解器 | MPM | 连续介质方法，适合表现软体大变形 |
| 本构模型 | Corotated | 数值稳健，结果与 Neo-Hookean 接近 |
| 几何 | 40 mm cube | 压缩变形比球体更明显，适合展示 |
| 峰值力 | 约 54.02 N | 有清晰力学响应 |
| 最小体积比 | 约 0.9999 | 体积保持最好 |
| 最大穿透 | 0 mm | 接触稳定 |

备选：

- `outputs/mpm3d_sphere_40mm_soft_corotated`：更适合做光滑球形软体展示，但形变视觉冲击弱于立方体。
- 不建议优先使用 PBD：速度快但反力是 pseudo-force，物理解释弱。
- 不建议优先使用 FEM：当前 50% 强压缩下部分组存在失稳，作为 Blender 主展示风险较高。

## 3. 当前缺口

现有全量运行输出了：

- `metrics.csv`
- PNG 帧
- `preview.gif`
- `used_config.json`

但 Blender 高质量渲染还需要 **逐帧几何数据**，例如：

- MPM 粒子位置：`positions/frame_0000.npz`
- 夹板位置：`plates.csv`
- 可选速度/应变/颜色标量：用于材质或热力图

因此下一步需要给选中的 Taichi run 增加几何导出功能。只需要对选中的最佳组导出，不必对全部 20 组导出。

## 4. 推荐技术路线

### 路线 A：粒子球渲染，最快可落地

Taichi 导出每帧粒子位置，Blender 中把每个粒子实例化为小球。

优点：

- 实现简单。
- 与当前仿真数据最一致。
- 不需要复杂重建。

缺点：

- 仍然能看出颗粒感。
- 不像连续橡胶表面。

适合用途：

- 方法展示。
- debug 视频。
- 粒子法 MPM 的可视化说明。

### 路线 B：粒子云重建表面，推荐用于最终展示

Taichi 导出粒子位置，Python 后处理把粒子云转成体素密度场，再用 Marching Cubes 重建表面网格。Blender 读取每帧 `.obj` / `.ply` / `.glb` 网格序列进行渲染。

优点：

- 视觉效果更像连续软体。
- 可添加橡胶材质、次表面散射、柔和阴影。
- 更适合最终报告或答辩视频。

缺点：

- 需要调体素分辨率、平滑强度和表面阈值。
- 网格序列文件较大。

推荐参数起点：

| 项目 | 建议 |
|---|---|
| 体素分辨率 | 96³ 或 128³ |
| 粒子核半径 | 1.5-2.5 × 粒子间距 |
| 表面平滑 | Taubin/Laplacian 1-3 次 |
| 导出帧率 | 30 fps 或从 60 fps 隔帧 |
| 输出格式 | `.ply` 或 `.obj` 序列 |

### 路线 C：Blender Metaball / Geometry Nodes

把粒子导入 Blender 后用 metaball 或 Geometry Nodes 合并成软体表面。

优点：

- 可以直接在 Blender 中调外观。
- 视觉上容易得到柔软融合效果。

缺点：

- 大量粒子会很慢。
- 脚本和 Blender 版本依赖较强。
- 可重复性不如 Python 网格重建。

不建议作为第一版主路线。

## 5. 建议实施步骤

### Step 1：为选中 MPM run 增加几何导出

新增 CLI 参数：

```powershell
python -m taichi_squeeze.src.simulate_mpm3d `
  --config taichi_squeeze/configs/mpm3d_cube_40mm_soft_corotated.json `
  --export-geometry `
  --no-render
```

建议输出：

```text
outputs/mpm3d_cube_40mm_soft_corotated/
  geometry/
    particles_0000.npz
    particles_0001.npz
    ...
    plates.csv
```

每个 `.npz` 至少包含：

```text
positions: float32[N, 3]
```

`plates.csv` 包含：

```text
frame,t,left_plate,right_plate,plate_y_min,plate_y_max,plate_z_min,plate_z_max
```

### Step 2：实现粒子云到表面网格

新增脚本：

```text
taichi_squeeze/tools/export_blender_mesh_sequence.py
```

输入：

```text
outputs/mpm3d_cube_40mm_soft_corotated/geometry/
```

输出：

```text
outputs/blender/mpm_cube_soft_corotated_mesh/
  mesh_0000.ply
  mesh_0001.ply
  ...
  plates.json
```

处理流程：

1. 读取粒子位置。
2. 构建体素密度场。
3. 使用 `skimage.measure.marching_cubes` 提取表面。
4. 使用 `trimesh` 平滑和导出。
5. 同步导出夹板几何参数。

### Step 3：编写 Blender 渲染脚本

新增脚本：

```text
blender/render_sequence.py
```

功能：

- 导入 mesh 序列。
- 创建两块透明/磨砂夹板。
- 创建软体橡胶材质。
- 设置相机、灯光、地面和阴影。
- 渲染 PNG 序列和 MP4。

建议风格：

| 对象 | 材质 |
|---|---|
| 软体 | 蓝色半哑光橡胶，roughness 0.45-0.65 |
| 夹板 | 半透明磨砂亚克力或金属边框玻璃 |
| 地面 | 浅灰 matte plane |
| 灯光 | 大面积 area light + 弱补光 |
| 相机 | 3/4 视角，固定焦距，避免透视夸张 |

### Step 4：只渲染关键帧预览

先不要直接渲染 390 帧全片。先选 5 个关键帧：

| 帧 | 时间 | 含义 |
|---:|---:|---|
| 0 | 0.0 s | 初始未接触 |
| 60 | 1.0 s | 最大压缩 |
| 90 | 1.5 s | 保持结束 |
| 150 | 2.5 s | 释放结束 |
| 389 | 6.48 s | 最终恢复 |

确认关键帧无误后，再渲染完整视频。

### Step 5：最终视频输出

建议输出：

```text
outputs/blender/final/
  mpm_cube_soft_corotated_blender.mp4
  keyframes/
    frame_0000.png
    frame_0060.png
    frame_0090.png
    frame_0150.png
    frame_0389.png
```

视频参数：

| 项目 | 建议 |
|---|---|
| 分辨率 | 1920 × 1080 |
| 帧率 | 30 fps |
| 渲染器 | Eevee Next 或 Cycles |
| 采样 | 64-128 samples |
| 格式 | H.264 MP4 |

## 6. 风险与判断标准

### 风险

- 表面重建可能过度平滑，掩盖 MPM 粒子真实状态。
- 粒子云边界可能有噪声，需要调 kernel 半径和体素阈值。
- Blender 全帧渲染可能比仿真本身更慢。
- 如果只渲染漂亮视频而不保留 metrics，会削弱实验可信度。

### 判断标准

Blender 结果必须满足：

1. 初始帧夹板不接触物体。
2. 最大压缩帧板间距为 20 mm。
3. 软体不穿透夹板。
4. 视频中的变形趋势与原始 Matplotlib/GIF 一致。
5. 报告中明确说明：Blender 是渲染增强，不改变 Taichi 仿真数据。

## 7. 推荐排期

| 阶段 | 任务 | 预计时间 |
|---|---|---:|
| 1 | MPM geometry export | 0.5 天 |
| 2 | 粒子云重建 mesh 序列 | 0.5-1 天 |
| 3 | Blender 材质/灯光/相机脚本 | 0.5-1 天 |
| 4 | 关键帧审查与参数调整 | 0.5 天 |
| 5 | 全序列渲染与报告补图 | 0.5-1 天 |

建议先做最小闭环：

```text
Taichi 选中组导出 5 帧粒子 -> 重建 5 帧 mesh -> Blender 渲染 5 张关键帧
```

如果这 5 张关键帧比当前 Matplotlib/GIF 明显更清楚，再投入时间渲染完整视频。
