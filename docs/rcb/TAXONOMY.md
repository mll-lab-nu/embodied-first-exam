# Taxonomy (task.toml `[metadata]`, closed sets — extend by PR)

| Field | Values |
|---|---|
| `simulator` | `robosuite` · `libero` · `robotwin` (RoboTwin 2.0 = SAPIEN 3 + CuRobo) · `robowits` (RoboWits on Genesis) · `robolab` (NVIDIA RoboLab on Isaac Lab) · `behavior` (BEHAVIOR-1K) · `maniskill` · … |
| `robot` | `franka-panda` · `franka-robotiq-2f85` · `aloha-agilex` · `marvin-bimanual` · `r1pro` · … |
| `family` | free-form slug naming the scene/goal, shared by its instances (e.g. `cube_stack`) |
| `task_type` | `trajectory` · `policy` |
| `tier` | `privileged` · `perception` |
| `difficulty` | `easy` · `medium` · `hard` · `extreme` (RoboPaint records the measured axes next to it, e.g. `line_complexity`, `stroke_count`, `structure`) |
| `instance_seed` | optional, informational |
| `mode`, `protocol` | limited twins only: `mode = "limited"`, `protocol = "rcb-limited/2.0"` |

Folder slug: `<simulator>-<family-with-dashes>-i<NN>` for instance tasks (RoboTwin tasks: `robotwin_2_0_<robotwin_task_name>`,
keeping RoboTwin's own task name); `[task].name = "robot-coding-bench/<slug>"`.
RoboPaint tasks: `robopaint-<family>-<target>-i<NN>` (families `line`, `kaishu`, `lettering`, `acrylic`, `oil`; Chinese targets by
pinyin, the codepoint appended on a collision, e.g. `robopaint-kaishu-shu-66f8-i00`; a multi-character work joins the pinyin of its
characters), limited twins `...-limited`; `[metadata].family = "robopaint_<family>_<target>"` (dashes -> underscores).
