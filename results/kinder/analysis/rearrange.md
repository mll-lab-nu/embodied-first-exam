**一句话**：rearrange 要把纸盒和罐子分别放到碗沿岛台长边的两侧，各离碗中心 4–13 cm。搬运本身不难：full 读坐标、在 `robot_pinch_site` 上做 IK，约 4.1 min 就存下过的轨迹。limited 难在看和抓：底座相机开局只看到岛台侧板，得靠 spec 的 FK 加腕部 RGB-D 找物体、自己试出夹爪抓取点，罐子一抬高就滑，放下时又撞碗沿侧倒。ep11 第 419 步通过，约在 49 min，离时限约 11 min。

## GPT-6 Luna
### limited
- **找物体用了 12.6 min（ep0–3）**：开局底座相机整幅暗灰（0.76 min "The base camera is returning a uniform dark frame"）。它把底座挪到岛台两头、伸出腕部相机扫，看到的都是岛台侧面和地面。5.66 min 起它的 IK 把关节变换乘反了顺序，12.63 min 才发现（"the joint transforms were applied in reverse"）；修好后，13.14 min 第一个观察位姿就看到了罐子和碗，此后底座一步没动。
- **标定抓取又用了约 14 min（ep4–9）**：spec 没有夹爪抓取点。17.61 min 腕部相机正对罐子合爪，落空（0.984）；18.35 min 从 FK 推出抓取点在相机"下方"约 5.6 cm，这才夹住（0.379）。之后罐子抬高一点就滑（ep5 抬到相机 z 0.76、ep6 抬到 0.767 都滑掉），ep8 下探低了 2.2 cm 又落空。31.69 min 下探点挪了约 8 mm、改成分段低抬："The can now stays between the fingers"。
- **ep9 一局两件都搬了，差在罐子**：罐子平移到碗左侧时碰到碗沿，读数跳到 0.96，罐子侧倒；纸盒一次夹起，放到了碗右侧。41.38 min："The can is upright no longer and sits just beyond the left-side distance limit"；它两次去夹侧倒的罐子，都没夹住。
- **写成开环脚本后第二局就过**：46.88 min 把量到的坐标写进 `gen.py`，不再看图。ep10 罐子下探用的是记下的关节角，合爪落空；48.17 min 改成按相机坐标逐段下探，ep11 第 419 步 `success`，这时纸盒还夹在手里、罐子侧倒贴着碗。还剩 39 次 reset，卡住它的是 60 min 而不是 reset。
### full
- **真值加现成的抓取点**：读到碗、纸盒、罐子的坐标；只 grep 到 `_check_goals` 的位置，放哪边按说明里 "the side the can now stands on" 和起始布局推出。IK 用 `mj_jacSite` 驱动 `robot_pinch_site`。
- **只失败一次就定型**：2.68 min 抬起时松了爪，纸盒掉回原处；改成保持闭合，纸盒抬到 z 0.717。3.68 min 写成 `gen.py`：先纸盒后罐子，夹起后举到 z 0.75 越过碗，放在碗中心沿 y ±11.5 cm 处。
- **离失败很远**：约 4.1 min 存下过的轨迹，第 421 步成功（罐子还夹着），两次回放一致，5.4 min 结束。
### 两种模式
- **full 说明任务的物理不难，limited 的时间都花在感知和抓取上**：full 约 4.1 min 就有过的轨迹。limited 找物体 12.6 min（其中约 7 min 是它自己乘反的 FK），标定抓取约 14 min，ep9 试整套又用了 16.6 min，49 min 才过。
- **搬法不同，收尾一样**：full 抓取点准，举到 z 0.75 越过碗；limited 罐子抬高一点就滑，只能分段低抬、从碗远侧绕过去，ep9、ep11 罐子都在碗边侧倒。两边成功时，第二件都还夹在手里。

## 改进意见
- **`spec()` 仍没有夹爪抓取点**：这次 17.61 min 腕部相机正对罐子合爪落空，18.35 min 它才从相机位姿和第 7 关节轴推出偏移（`gen.py` 注释 "The camera sits 5.6 cm above the gripper center in its local up direction"），ep8 下探高度差 2.2 cm 又落空。full 用的是模型里的 `robot_pinch_site`。这和 overview 已列的一条相同：在 `spec()["arm"]` 里补上抓取点在各关节为 0 时的位置和开合方向。
