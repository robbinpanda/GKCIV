# Taichi Blender Squeeze

独立于 `taichi_squeeze/` 的 Blender 捏捏视频制作流水线。

目标是用上一阶段已经验证过的 Taichi MPM 结果驱动软体形变，再用 Blender 做产品级渲染。这个目录只写自己的输出到 `taichi_blender_squeeze/outputs/`，不会修改上一阶段的 `taichi_squeeze/` 或根目录 `outputs/`。

## Pipeline

```text
Taichi MPM key/full-frame export
  -> particle NPZ + plate CSV
  -> surface reconstruction PLY sequence, mapped from Taichi (x,y,z) to Blender (x,z,y)
  -> Blender scene + acrylic plates + soft rubber material
  -> keyframe preview / final MP4
```

参考架构：

- `Tbl0x7D6/ACG-Project`：simulation -> mesh export -> Blender scripts。
- `jason-huang03/SPH_Project`：particle export -> surface reconstruction -> Blender rendering。

## Current Target

默认使用：

```text
taichi_squeeze/configs/mpm3d_cube_40mm_soft_corotated.json
```

推荐先做 5 帧关键帧闭环：

```powershell
conda activate GKCIV

python -m taichi_blender_squeeze.export_mpm_geometry `
  --config taichi_squeeze/configs/mpm3d_cube_40mm_soft_corotated.json `
  --keyframes 0,60,90,150,389

python -m taichi_blender_squeeze.reconstruct_surface `
  --input taichi_blender_squeeze/outputs/geometry/mpm3d_cube_40mm_soft_corotated `
  --output taichi_blender_squeeze/outputs/meshes/mpm3d_cube_40mm_soft_corotated_keyframes `
  --resolution 96
```

Blender 安装并可用后：

```powershell
blender -b --python taichi_blender_squeeze/blender/create_squishy_scene.py -- `
  --mesh-dir taichi_blender_squeeze/outputs/meshes/mpm3d_cube_40mm_soft_corotated_keyframes `
  --plates-json taichi_blender_squeeze/outputs/meshes/mpm3d_cube_40mm_soft_corotated_keyframes/plates.json `
  --output-blend taichi_blender_squeeze/outputs/blender/scene/squishy_mpm_cube.blend `
  --render-keyframes
```

完整视频阶段建议先把几何导出改成 `--frame-stride 1`，再运行：

```powershell
python -m taichi_blender_squeeze.blender.render_blender_video `
  --config taichi_blender_squeeze/configs/blender_config.example.json `
  --blend taichi_blender_squeeze/outputs/blender/scene/squishy_mpm_cube.blend
```

## What Is Missing

本地当前没有可用的 `blender` 命令，因此 Blender 脚本还没有执行测试。需要：

- 安装 Blender 4.x，或把 `blender.exe` 写入 `configs/blender_config.example.json`。
- 如果要借用参考仓库的 HDRI/模型/贴图，需要手动确认许可证并放入 `taichi_blender_squeeze/assets/`。
- 当前脚本先生成程序化软体材质、夹板、灯光和相机，不依赖外部 3D 模型。
