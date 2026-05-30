# Taichi + Blender 捏捏仿真视频执行计划

生成日期：2026-05-30

## 0. 目标

这一阶段不再继续改上一阶段的 `taichi_squeeze/` 实验代码，也不删除或重跑根目录 `outputs/`。

新目标是单独做一个视觉优先的 Blender 成片流水线：

- 物理运动来自上一阶段效果最稳定的 Taichi MPM 软体仿真。
- Blender 负责连续表面、材质、透明夹板、灯光、相机和最终视频。
- 所有新代码和新输出都隔离在 `taichi_blender_squeeze/`。
- 先做 5 张关键帧预览，确认好看后再做完整视频。

## 1. 参考项目

参考用户给出的两个 B 站开源仓库：

- `Tbl0x7D6/ACG-Project`: <https://github.com/Tbl0x7D6/ACG-Project>
- `jason-huang03/SPH_Project`: <https://github.com/jason-huang03/SPH_Project>

从它们借鉴的不是具体代码，而是工程结构：

| 参考点 | 本项目对应做法 |
|---|---|
| simulation 和 render 分离 | Taichi 只导出几何，Blender 只做视觉 |
| mesh/particle 中间结果 | 先导出 particle NPZ，再重建 PLY mesh sequence |
| Blender 脚本化渲染 | 用 `blender/create_squishy_scene.py` 自动建场景 |
| 先预览再成片 | 先渲染关键帧，满意后再完整渲染 |
| 资产目录独立 | HDRI、贴图、模型放 `taichi_blender_squeeze/assets/` |

## 2. 当前新目录结构

```text
taichi_blender_squeeze/
  __init__.py
  README.md
  references.md
  export_mpm_geometry.py
  reconstruct_surface.py
  assets/
    README.md
  blender/
    create_squishy_scene.py
    render_blender_video.py
  configs/
    blender_config.example.json
  outputs/                  # 运行后生成，已在本目录 .gitignore 中忽略
```

这个结构与上一阶段隔离：不需要修改 `taichi_squeeze/src/simulate_mpm3d.py`，也不会把 Blender 产物写到根目录 `outputs/`。

## 3. 选用的仿真组

默认使用：

```text
taichi_squeeze/configs/mpm3d_cube_40mm_soft_corotated.json
```

理由：

| 项目 | 说明 |
|---|---|
| MPM | 软体连续形变最稳定，适合转成表面 mesh |
| cube_40mm | 捏压效果比球更明显，更接近“捏捏玩具”展示 |
| soft | 变形足够明显 |
| corotated | 当前实验中稳定且无明显穿透 |
| 50% 压缩 | 视觉效果比 70% 更强，已经在上一阶段计划中修正 |

备选镜头：

```text
taichi_squeeze/configs/mpm3d_sphere_40mm_soft_corotated.json
```

球可以作为第二镜头或对照镜头，但主成片建议先用 cube。

## 4. 执行流水线

### Step 1: 导出 MPM 粒子和夹板轨迹

关键帧预览：

```powershell
python -m taichi_blender_squeeze.export_mpm_geometry `
  --config taichi_squeeze/configs/mpm3d_cube_40mm_soft_corotated.json `
  --keyframes 0,60,90,150,389
```

输出：

```text
taichi_blender_squeeze/outputs/geometry/mpm3d_cube_40mm_soft_corotated/
  particles_0000.npz
  particles_0060.npz
  particles_0090.npz
  particles_0150.npz
  particles_0389.npz
  plates.csv
  metrics.csv
  used_config.json
  export_config.json
```

完整视频时把 `--keyframes` 换成 `--frame-stride 1` 或 `--frame-stride 2`。

### Step 2: 粒子云重建连续表面

```powershell
python -m taichi_blender_squeeze.reconstruct_surface `
  --input taichi_blender_squeeze/outputs/geometry/mpm3d_cube_40mm_soft_corotated `
  --output taichi_blender_squeeze/outputs/meshes/mpm3d_cube_40mm_soft_corotated_keyframes `
  --resolution 96
```

输出：

```text
taichi_blender_squeeze/outputs/meshes/mpm3d_cube_40mm_soft_corotated_keyframes/
  mesh_0000.ply
  mesh_0060.ply
  mesh_0090.ply
  mesh_0150.ply
  mesh_0389.ply
  plates.json
  reconstruction_config.json
```

当前实现使用密度场 + Marching Cubes，优先保证能在本地 Python 环境完成。后续如果追求更高质量，可以替换为 SplashSurf 或 Blender 内部 remesh/geometry nodes。

注意坐标系：Taichi 中 `y` 是高度，Blender 中 `z` 是高度。当前 PLY 导出和夹板场景脚本统一使用 `Taichi (x,y,z) -> Blender (x,z,y)`，避免相机和地面方向错位导致“物体浮在板子上方”的观感。

### Step 3: Blender 自动建场景

本地当前没有检测到可用 `blender` 命令，所以此步代码已写好，但未运行。

安装 Blender 并加入 PATH 后：

```powershell
blender -b --python taichi_blender_squeeze/blender/create_squishy_scene.py -- `
  --mesh-dir taichi_blender_squeeze/outputs/meshes/mpm3d_cube_40mm_soft_corotated_keyframes `
  --plates-json taichi_blender_squeeze/outputs/meshes/mpm3d_cube_40mm_soft_corotated_keyframes/plates.json `
  --output-blend taichi_blender_squeeze/outputs/blender/scene/squishy_mpm_cube.blend `
  --render-keyframes
```

脚本会创建：

- 半透明蓝色橡胶/硅胶软体材质。
- 透明磨砂亚克力夹板。
- 低角度 3/4 产品镜头。
- 大面积柔光主灯和轮廓光。
- matte studio floor。
- mesh sequence 可见性关键帧。
- 夹板位移动画。

### Step 4: 完整视频渲染

关键帧好看后再完整输出：

```powershell
python -m taichi_blender_squeeze.export_mpm_geometry `
  --config taichi_squeeze/configs/mpm3d_cube_40mm_soft_corotated.json `
  --frame-stride 1

python -m taichi_blender_squeeze.reconstruct_surface `
  --input taichi_blender_squeeze/outputs/geometry/mpm3d_cube_40mm_soft_corotated `
  --output taichi_blender_squeeze/outputs/meshes/mpm3d_cube_40mm_soft_corotated_full `
  --resolution 96
```

然后用 Blender 创建完整场景：

```powershell
blender -b --python taichi_blender_squeeze/blender/create_squishy_scene.py -- `
  --mesh-dir taichi_blender_squeeze/outputs/meshes/mpm3d_cube_40mm_soft_corotated_full `
  --plates-json taichi_blender_squeeze/outputs/meshes/mpm3d_cube_40mm_soft_corotated_full/plates.json `
  --output-blend taichi_blender_squeeze/outputs/blender/scene/squishy_mpm_cube.blend
```

渲染视频：

```powershell
python -m taichi_blender_squeeze.blender.render_blender_video `
  --config taichi_blender_squeeze/configs/blender_config.example.json `
  --blend taichi_blender_squeeze/outputs/blender/scene/squishy_mpm_cube.blend
```

## 5. 视觉验收标准

关键帧需要满足：

- 第 0 帧夹板靠近但不接触软体。
- 最大压缩帧明显显示 50% 压缩。
- 软体是连续光滑表面，不是粒子点云。
- 夹板透明但不遮挡主体形变。
- 相机能看清左右夹板和软体之间的关系。
- 整体观感接近产品级捏捏玩具渲染，而不是 Matplotlib 科研图。

## 6. 当前缺少的东西

| 缺项 | 影响 |
|---|---|
| Blender 可执行文件 | 无法在本地实际渲染 `.blend`、PNG 或 MP4 |
| 可选 HDRI/贴图/模型资产 | 当前可用程序化灯光和材质，但真实感上限不如精调资产 |
| 参考仓库资产许可确认 | 不能直接复制第三方 HDRI、模型、贴图进本仓库，除非确认 license 和 attribution |
| 关键帧人工审美调参 | 首次 Blender 渲染后还要微调相机、材质、灯光、surface 阈值 |

## 7. 不建议的改动

- 不建议用 Blender soft body 重新仿真，因为会和 Taichi 实验结果脱钩。
- 不建议把新代码塞回 `taichi_squeeze/`，否则会污染上一阶段已经验证过的实验。
- 不建议第一次就渲染完整视频，先看关键帧能节省大量时间。

## 8. 下一步

1. 安装 Blender 4.x，或把 `blender.exe` 绝对路径写入 `taichi_blender_squeeze/configs/blender_config.example.json`。
2. 运行 5 帧关键帧流水线。
3. 根据预览图微调 `reconstruct_surface.py` 的 `--threshold-ratio`、`--radius-scale` 和 Blender 材质/相机。
4. 确认效果后运行完整 mesh sequence 和完整视频渲染。
