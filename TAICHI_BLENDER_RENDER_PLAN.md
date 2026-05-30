# Blender 捏捏仿真高质量视频执行计划

生成日期：2026-05-30

## 0. 目标重定义

本计划的目标不是再做一版科研分析图，而是制作一个 **视觉效果优先的 Blender 捏捏仿真成片**：

- 看起来像真实柔软的“捏捏”玩具。
- 模型、材质、灯光、镜头、动画节奏都要好看。
- 物理运动来自 Taichi 的 MPM 仿真，保证不是手工乱做。
- Blender 负责最终 3D 模型重建、材质、灯光、镜头和视频渲染。

参考风格：

- 用户提供的 B 站参考视频：
  - `https://www.bilibili.com/video/BV1Fc411x7xy/`
  - `https://www.bilibili.com/video/BV1W7fmBpEKL/`
- 预期观感：软糯、Q 弹、半写实、产品展示感强，而不是 Matplotlib/科研图风格。

## 1. 技术路线总览

最终采用：

```text
Taichi MPM 仿真 -> 导出逐帧粒子/夹板数据 -> 重建连续软体表面 -> Blender 高质量渲染
```

分工如下：

| 模块 | 作用 |
|---|---|
| Taichi | 负责 MPM 软体运动、压缩/释放、夹板轨迹 |
| Python 后处理 | 粒子云转连续表面网格，导出 mesh sequence |
| Blender | 创建好看的捏捏模型、夹板、场景、灯光、相机、材质、视频 |

Blender 不作为物理求解器使用。它只接收 Taichi 输出的形变几何，并把它渲染得更真实、更漂亮。

## 2. 选用哪一组 Taichi 仿真

主方案使用：

```text
mpm3d_cube_40mm_soft_corotated
```

对应配置：

```text
taichi_squeeze/configs/mpm3d_cube_40mm_soft_corotated.json
```

理由：

| 项目 | 说明 |
|---|---|
| MPM | 体积保持最稳定，适合做连续软体视觉展示 |
| soft | 软材质变形更明显，更像捏捏玩具 |
| corotated | 当前结果稳定，与 Neo-Hookean 差异很小 |
| cube_40mm | 立方体被挤压时轮廓变化明显，比球体更容易看出“捏”的动作 |
| 无穿透 | 当前结果中夹板穿透为 0，适合做干净视频 |

备选方案：

```text
mpm3d_sphere_40mm_soft_corotated
```

球体更像水球/果冻，但压缩视觉变化弱一些。建议第一版主视频用 cube，第二版补 sphere 作为对照镜头。

## 3. 当前环境检查

当前命令行中没有检测到 `blender`：

```powershell
blender --version
```

返回：

```text
blender : 无法将“blender”项识别为 cmdlet...
```

因此第一步需要完成以下任一项：

1. 安装 Blender，并把 `blender.exe` 加入 PATH。
2. 或在脚本/配置中写明 Blender 绝对路径，例如：

```powershell
"C:\Program Files\Blender Foundation\Blender 4.3\blender.exe"
```

建议使用 Blender 4.x。优先使用 Eevee Next 做快速预览，最终镜头可以使用 Cycles。

## 4. 视觉目标

### 4.1 软体外观

软体应该像一个柔软的硅胶/橡胶捏捏玩具：

| 项目 | 建议 |
|---|---|
| 颜色 | 糖果蓝、奶油粉、半透明果冻蓝三选一 |
| 材质 | 半哑光橡胶或轻微半透明硅胶 |
| 粗糙度 | 0.45-0.65 |
| 次表面散射 | 轻微开启，增强软糯感 |
| 表面 | 连续光滑，不显示粒子点 |
| 轮廓 | 保留圆润边缘和压缩后的鼓胀感 |

### 4.2 夹板外观

夹板不再用科研图里的灰色矩形，而要做成高质量透明亚克力压板：

| 项目 | 建议 |
|---|---|
| 材质 | 半透明磨砂亚克力 / 透明玻璃 |
| 颜色 | 淡粉或淡灰 |
| 边缘 | 加厚倒角，边缘高光明显 |
| 透明度 | 0.25-0.45 |
| 作用 | 既能看出挤压，又不遮挡软体 |

### 4.3 场景外观

| 项目 | 建议 |
|---|---|
| 地面 | 浅灰或暖白 matte plane |
| 背景 | 干净棚拍背景，避免科研坐标轴 |
| 灯光 | 大面积 softbox 主光 + 弱补光 + 轮廓光 |
| 相机 | 低角度 3/4 产品镜头 |
| 焦距 | 70-100 mm，减少透视畸变 |
| 景深 | 轻微 DOF，焦点在软体中心 |

## 5. 动画目标

最终视频建议 8-12 秒，节奏比原始 6.5 秒实验稍微更“展示化”：

| 时间段 | 内容 |
|---|---|
| 0-1 s | 初始状态，夹板靠近但不接触，给观众看清模型 |
| 1-3 s | 缓慢压缩到最大形变 |
| 3-4 s | 保持最大压缩，强调鼓胀和软糯 |
| 4-6 s | 释放回弹 |
| 6-8 s | 轻微余振或停留 hero frame |

可以从 390 帧 Taichi 结果中重映射时间，而不一定按原始 60 fps 原速播放。

推荐最终输出：

| 项目 | 建议 |
|---|---|
| 分辨率 | 1920 × 1080 |
| 帧率 | 30 fps |
| 时长 | 8-12 s |
| 格式 | H.264 MP4 |
| 另存 | 5 张关键帧 PNG |

## 6. 关键技术步骤

### Step 0：确认 Blender 可执行文件

新增配置文件：

```text
blender/blender_config.json
```

内容示例：

```json
{
  "blender_exe": "C:/Program Files/Blender Foundation/Blender 4.3/blender.exe",
  "render_engine": "CYCLES",
  "resolution": [1920, 1080],
  "fps": 30
}
```

### Step 1：给 MPM 增加几何导出

给 `simulate_mpm3d.py` 增加参数：

```powershell
python -m taichi_squeeze.src.simulate_mpm3d `
  --config taichi_squeeze/configs/mpm3d_cube_40mm_soft_corotated.json `
  --export-geometry `
  --no-render
```

输出：

```text
outputs/mpm3d_cube_40mm_soft_corotated/
  geometry/
    particles_0000.npz
    particles_0001.npz
    ...
    plates.csv
```

每帧 `particles_XXXX.npz`：

```text
positions: float32[N, 3]
```

`plates.csv`：

```text
frame,t,left_plate,right_plate,plate_y_min,plate_y_max,plate_z_min,plate_z_max
```

### Step 2：粒子云重建为连续软体表面

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

推荐方法：

1. 读取 MPM 粒子。
2. 构建体素密度场。
3. 使用 Marching Cubes 提取表面。
4. 使用 Taubin 或 Laplacian 平滑。
5. 导出 `.ply` 或 `.obj` 网格序列。

推荐参数：

| 项目 | 起点 |
|---|---|
| 体素分辨率 | 96³ |
| 粒子核半径 | 2.0 × 粒子平均间距 |
| 表面阈值 | 先自动估计，再人工微调 |
| 平滑 | 2 次 |
| 导出帧率 | 30 fps，可从原始 60 fps 隔帧 |

### Step 3：制作 Blender 场景脚本

新增脚本：

```text
blender/create_squishy_scene.py
```

职责：

- 清空默认场景。
- 导入 mesh sequence。
- 创建透明亚克力夹板，并按 `plates.json` 设置逐帧位置。
- 创建软体材质。
- 创建地面、背景、灯光和相机。
- 输出 `.blend` 文件。

输出：

```text
outputs/blender/scene/squishy_mpm_cube.blend
```

### Step 4：关键帧预览

先只渲染 5 张关键帧，不直接渲完整视频：

| 帧 | 含义 |
|---:|---|
| 0 | 初始未接触 |
| 60 | 最大压缩 |
| 90 | 保持结束 |
| 150 | 释放结束 |
| 389 | 最终恢复 |

输出：

```text
outputs/blender/preview_keyframes/
  key_0000.png
  key_0060.png
  key_0090.png
  key_0150.png
  key_0389.png
```

验收标准：

1. 初始帧夹板没有接触软体。
2. 最大压缩帧形变明显。
3. 软体表面连续光滑，不显示粒子颗粒。
4. 夹板透明但不遮挡主体。
5. 相机角度能看清两块板和软体间距。

### Step 5：渲染完整视频

命令形式：

```powershell
blender -b outputs/blender/scene/squishy_mpm_cube.blend -o outputs/blender/final/frame_#### -F PNG -a
```

或用脚本：

```powershell
python blender/render_blender_video.py
```

最终输出：

```text
outputs/blender/final/
  frame_0001.png
  frame_0002.png
  ...
  squishy_mpm_cube_blender.mp4
```

## 7. 不建议的方向

### 7.1 不建议直接用 Blender soft body 重新模拟

原因：

- 与 Taichi 实验不再同源。
- 参数不可比。
- 很难保证与 metrics 对应。
- 可能好看，但会削弱“仿真引擎实验”的可信度。

如果使用 Blender 内置 soft body，只能作为视觉参考，不作为实验结果。

### 7.2 不建议继续用粒子点渲染作为最终片

粒子点能解释 MPM，但不像真实捏捏玩具。最终成片必须是连续表面。

### 7.3 不建议一次性渲完整 390 帧

先做关键帧预览。关键帧不好看，完整视频只会更浪费时间。

## 8. 最小可行闭环

第一轮只做 5 帧：

```text
导出 5 帧 MPM 粒子
-> 重建 5 帧 mesh
-> Blender 渲染 5 张关键帧
-> 人工确认风格
```

通过后再扩展到完整视频。

## 9. 文件结构建议

```text
Final_Project_GKCIV/
  blender/
    blender_config.json
    create_squishy_scene.py
    render_blender_video.py
  taichi_squeeze/
    tools/
      export_blender_mesh_sequence.py
  outputs/
    mpm3d_cube_40mm_soft_corotated/
      geometry/
    blender/
      mpm_cube_soft_corotated_mesh/
      preview_keyframes/
      scene/
      final/
```

## 10. 下一步执行顺序

1. 安装或定位 Blender 可执行文件。
2. 给 MPM 增加 `--export-geometry`。
3. 导出 `mpm3d_cube_40mm_soft_corotated` 的 5 个关键帧粒子数据。
4. 实现粒子云到 mesh 的重建脚本。
5. 写 Blender 场景脚本，做材质、灯光、相机和夹板动画。
6. 渲染 5 张关键帧。
7. 确认风格后渲染完整视频。

## 11. 成功标准

最终结果应满足：

- 一眼能看出是柔软捏捏玩具被透明夹板压缩。
- 视频不是科研散点图，而是完整 3D 产品级渲染。
- 软体表面连续、圆润、带真实光泽。
- 夹板运动与 Taichi 的 50% 压缩协议一致。
- 报告中可以明确说明：视频由 Taichi MPM 数据驱动，Blender 仅用于视觉渲染。
