# Repository Review - 2026-05-31

## Scope

本次审查覆盖当前仓库的两个阶段：

- Phase 1: `taichi_squeeze/` 的 20 组 Taichi 软体挤压仿真、`outputs/` 结果、`docs/phase1/EXPERIMENT_REPORT.md` 和 `docs/phase1/IMPROVEMENT_PLAN.md`
- Phase 2: `taichi_blender_squeeze/` 与 `docs/phase2/TAICHI_BLENDER_RENDER_PLAN.md`

对比参考：

- https://github.com/jason-huang03/SPH_Project
- https://github.com/Tbl0x7D6/ACG-Project

本机当前未检测到 `blender` 可执行文件，因此 Phase 2 只能做代码与计划审查，不能确认实际 `.blend`、PNG 或 MP4 输出。

## Directory Cleanup

已把阶段文档从根目录收拢到 `docs/`：

```text
docs/
  phase1/
    EXPERIMENT_REPORT.md
    EXPERIMENT_REPORT.pdf
    IMPROVEMENT_PLAN.md
  phase2/
    TAICHI_BLENDER_RENDER_PLAN.md
  reviews/
    REPOSITORY_REVIEW_2026-05-31.md
```

根目录现在主要保留运行入口、环境文件、两个代码包和 `outputs/`。同时 `.gitignore` 已补充 `taichi_blender_squeeze/outputs/`，避免第二阶段导出的 mesh、blend、frames 误提交。

## Executive Judgment

短答案：当前方向可以接近两个参考仓库的“后处理渲染思路”，但如果不先修 Phase 1 的时间步一致性、数据指标和 mesh 重建质量，Blender 渲染出来很难稳定达到参考项目的观感。

SPH_Project 的亮点是明确的后处理链路：仿真导出粒子/PLY，中间用 SplashSurf 做表面重建，最终用 Blender 和场景资源渲染。ACG-Project 也把 simulation、mesh export、Blender 脚本、FFmpeg 视频生成拆开，并且包含平滑、细分、降采样等 mesh 后处理工具。当前仓库 Phase 2 的方向与它们一致，但实现仍是最小可用版本：没有 Blender 实测，没有高级 surface smoothing，没有 HDRI/贴图资产，没有帧率一致性校验。

## Critical Findings

### P0 - MPM/PBD 的仿真时间步与视频帧时间不一致

位置：

- `taichi_squeeze/src/simulate_mpm3d.py:390-392`
- `taichi_squeeze/src/simulate_pbd3d.py:361-364`
- `taichi_squeeze/configs/mpm3d_*`
- `taichi_squeeze/configs/pbd3d_*`

仿真循环用 `t = frame / fps` 推进夹板位置，又用 `sub_t = t + substep_id * dt` 做子步。但配置要求每帧物理时间应约等于 `1 / fps = 0.0166667s`。

实际检查结果：

```text
MPM: dt=0.0001, substeps=10, dt*substeps=0.001s, 只覆盖 1/60 帧时间的 6%
PBD: dt=0.001, substeps=10, dt*substeps=0.010s, 只覆盖 1/60 帧时间的 60%
FEM: dt=0.0003472222, substeps=48, dt*substeps≈0.0166667s, 基本匹配
```

影响：

- MPM/PBD 的速度、接触力、恢复行为和最终残余变形都不可信。
- MPM 导出的 Blender 几何会按“夹板时间”跳帧运动，但内部物体动力学只演化了很少物理时间。
- 当前 `EXPERIMENT_REPORT` 中对 MPM/PBD 的性能、力学、恢复结论需要重跑后再写。

建议：

- 所有 solver 强制校验 `abs(dt * substeps_per_frame - 1/fps) < tolerance`，不满足就报错。
- 如果 MPM 需要小 `dt=1e-4` 才稳定，应把 `substeps_per_frame` 提到约 167，或把导出/报告中的时间轴改成真实累计仿真时间。

### P0 - 当前 Phase 1 数据结论不够可靠

位置：

- `outputs/analysis/run_summary_metrics.csv`
- `outputs/analysis/force_displacement.png`
- `outputs/analysis/volume_ratio_time.png`
- `docs/phase1/EXPERIMENT_REPORT.md`

当前数据中 FEM 多组出现 `min_width=0`、`volume_ratio=0`、负体积或 38 mm 级穿透；MPM 的 Neo-Hookean 与 Corotated 曲线几乎重合；PBD 的力是约束修正伪力。这些现象本身可以作为“数值稳定性观察”，但不能支撑强物理结论。

观感上，最终 GIF 的差异是有的：MPM cube 压缩明显，FEM 失稳明显，PBD 更像弹簧点阵。但作为最终报告展示，当前对比图例重复、曲线颜色只按 solver 分组，读者很难看清具体是哪一组实验。

建议：

- 先修时间步一致性，然后重跑 20 组。
- 图例至少包含 `solver + shape + material + model`。
- 最终展示建议做 5 列横排关键帧或视频：MPM-NH / MPM-CR / FEM-NH / FEM-CR / PBD，同场景同帧号对齐。

### P1 - MPM 配置中的阻尼参数没有生效

位置：

- `taichi_squeeze/src/simulate_mpm3d.py:160`
- `taichi_squeeze/configs/mpm3d_*`

MPM 代码读取的是 `grid_velocity_damping`，但配置文件写的是 `velocity_damping`。结果是 MPM 实际阻尼为 0。报告中关于 MPM 恢复不足、残余应变大的判断可能被这个参数错配放大。

建议：

- 统一字段名，或兼容读取 `grid_velocity_damping` 和 `velocity_damping`。
- 报告中写明 MPM 使用的是 grid damping 还是 particle damping。

### P1 - FEM 的大压缩失稳没有被隔离为失败样本

位置：

- `taichi_squeeze/src/simulate_fem3d.py:268-305`
- `taichi_squeeze/src/constitutive.py:88-96`
- `outputs/analysis/run_summary_metrics.csv`

FEM 目前是显式积分加四面体网格，50% 挤压下大量组出现单元翻转、塌缩或负体积。Taichi 版 corotated stress 没有对 `det(R)<0` 做反射修正，Neo-Hookean 在 `J` 被 clamp 后仍会对接近奇异的 `F.inverse()` 敏感。

建议：

- 在 `metrics.csv` 增加 `min_detF`、`inverted_tet_count`。
- 任何 `min_volume_ratio <= 0` 或 `max_penetration_m` 过大的 FEM 组，在报告中标为 failed/unstable，不参与平均值。
- 若要把 FEM 做成可信对比，需要更高质量 tet mesh、隐式/半隐式积分，或更温和压缩协议。

### P1 - Phase 2 默认帧率与 Phase 1 不一致

位置：

- `taichi_blender_squeeze/blender/create_squishy_scene.py:26`
- `taichi_blender_squeeze/configs/blender_config.example.json`

Phase 1 是 60 fps、390 帧、6.5 秒。Blender 脚本默认 `--fps 30`，配置示例也是 30 fps。如果导入 0 到 389 帧并按 30 fps 渲染，成片会变成约 13 秒，速度变慢一倍。

建议：

- 默认改为 60 fps，或明确把 390 帧重采样到 30 fps。
- `render_blender_video.py` 与 `create_squishy_scene.py` 应共用同一个 config。

### P1 - Blender 配置文件的大部分字段没有被使用

位置：

- `taichi_blender_squeeze/blender/render_blender_video.py:88-96`
- `taichi_blender_squeeze/blender/create_squishy_scene.py:249-274`
- `taichi_blender_squeeze/configs/blender_config.example.json`

示例配置里有 `render_engine`、`device_type`、`samples`、材质参数，但 `render_blender_video.py` 基本只读取 `blender_exe` 和 `fps`；`create_squishy_scene.py` 使用命令行默认值，未读取该 config。

影响：

- 计划写得像可配置流水线，代码实际是硬编码流水线。
- 安装 Blender 后，用户可能以为改 JSON 会生效，但实际不会。

建议：

- 新增 `--config` 到 `create_squishy_scene.py`。
- 把 engine、samples、resolution、fps、材质、相机、输出路径都从 JSON 读取。

## 3D Axis and Relative Orientation

Phase 1 坐标约定整体是自洽的：

- `x`: 左右夹板挤压方向
- `y`: 高度方向
- `z`: 深度方向

Phase 1 Matplotlib/PyVista 渲染也按 `x/y/z` 原样显示，夹板是垂直于 `x` 的盒体，跨越 `y/z`，这一点没有发现轴向颠倒。

Phase 2 的坐标转换：

- `taichi_blender_squeeze/reconstruct_surface.py:101-102` 使用 `Taichi (x,y,z) -> Blender (x,z,y)`。
- `taichi_blender_squeeze/blender/create_squishy_scene.py:161-180` 对夹板中心和尺寸也做了同样转换。

这个转换逻辑是正确方向：Blender 默认 `z-up`，所以 Taichi 高度 `y` 应映射到 Blender `z`。当前较大的风险不是轴错，而是镜头、地面、焦距和可见性动画都硬编码在 0.1 m 场景尺度上；一旦换尺寸或换场景，画面容易需要手调。

## Phase 2 Visual Potential

当前最有说服力的渲染候选是：

```text
taichi_squeeze/configs/mpm3d_cube_40mm_soft_corotated.json
```

理由成立但需要重新表述：它不是“物理最准确”，而是“在当前输出中视觉变形明显、无穿透、适合重建连续软体表面”。`mpm3d_sphere_40mm_soft_corotated` 可以作为第二镜头或恢复性对照，因为球体恢复视觉更自然，但压缩形变不如 cube 明显。

能否达到参考项目效果：

- 仅靠当前 `reconstruct_surface.py` 的高斯密度 + Marching Cubes，预计能明显超过 Matplotlib 点云，但离 SPH_Project 那种 SplashSurf + 精调 Blender 的流体级表面还有差距。
- 只渲染 5 个 keyframes 时，Blender 里会是 stop-motion mesh 切换；完整视频必须导出 `frame_stride=1` 或做好插值。
- 没有 HDRI、真实材质贴图、后期调色、motion blur 和 mesh smoothing 时，观感大概率是“干净的课程项目渲染”，还不到“公开视频 showcase”级别。

优先优化：

1. 修时间步一致性并重跑 MPM cube/sphere。
2. 在 surface reconstruction 后增加 Laplacian/Taubin smoothing 和法线重算。
3. Blender 默认改 60 fps，并把 config 真正接入。
4. 先渲染 5 张关键帧，检查 mesh 是否破洞、夹板是否挡主体、相机是否看清 50% 压缩。
5. 再跑完整 mesh sequence 和 MP4。

## Data and Report Quality

当前报告结论“MPM 体积保持最好、PBD 最快、FEM 大压缩不稳定”方向上合理，但证据强度不足。尤其是 MPM 的 `volume_ratio` 来自 `mean(J)`，不是实际几何体积；PBD 的 `ConvexHull` 体积会把凹陷形变包起来；FEM 的平均值混入失败组。

最终报告建议分成三层：

- `valid results`: 通过时间步、穿透、体积、detF 检查的结果
- `visual comparison`: GIF/关键帧效果，不强称物理准确
- `failure analysis`: FEM 翻转、PBD 体积损失、MPM 恢复不足

这样结论会更稳，也更像真实工程审查，而不是只挑好看的图。

## Verification Performed

- `python -m compileall -q taichi_squeeze taichi_blender_squeeze run_all.py generate_configs.py`: pass
- `where.exe blender`: failed, current machine cannot find Blender
- Checked all Phase 1 configs for `dt * substeps_per_frame` versus `1 / fps`: MPM and PBD fail, FEM passes
- Visually inspected `outputs/analysis/force_displacement.png`, `outputs/analysis/volume_ratio_time.png`, and MPM cube key frames

## Recommended Next Changes

1. Add a config validator and fail early on time-step mismatch.
2. Fix MPM damping field mismatch.
3. Re-run at least `mpm3d_cube_40mm_soft_corotated` and `mpm3d_sphere_40mm_soft_corotated` before committing to the Blender hero shot.
4. Add `min_detF` / failure flags for FEM.
5. Wire Blender JSON config into both scene creation and rendering.
6. Add mesh smoothing before Blender import.
7. Rewrite `docs/phase1/EXPERIMENT_REPORT.md` after the corrected rerun.
