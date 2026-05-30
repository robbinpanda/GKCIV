# Reference Notes

This stage follows the architecture of the two Bilibili-linked open-source projects without vendoring their code.

## Tbl0x7D6/ACG-Project

Observed structure:

- Simulation entry scripts at the repository root.
- `materials/`, `objects/`, and `utils/` for reusable simulation and mesh utilities.
- `render/` for Blender scene files, textures, and environment maps.
- Mesh export through PLY sequences, followed by Blender rendering.

Borrowed idea for this project:

- Keep simulation data generation separate from Blender rendering.
- Export intermediate meshes so visual work can be iterated without rerunning physics.
- Treat Blender as a high-quality renderer rather than the physics source.

## jason-huang03/SPH_Project

Observed structure:

- Scene-driven simulation.
- Particle output followed by surface reconstruction.
- Blender rendering from reconstructed geometry.
- Clear separation among prepare scene, simulation, post-processing, and rendering.

Borrowed idea for this project:

- Use a staged pipeline: geometry export, surface reconstruction, scene construction, preview keyframes, final render.
- Keep generated data under an isolated output tree.
- Prefer a small keyframe preview before full-video rendering.
