# Tianji Marvin fixed dual-arm simulation asset

The real product is Tianji Marvin Pro with two M6S CCS696 arms on a fixed rigid bracket, not a wheeled Gento platform.
Manufacturer product reference: https://en.tianjizn.com/products/marvin-pro/

Geometry, joint frames, collision meshes, ranges, and torque limits are from the complete TianjiMarvin asset released by DexForce:
https://huggingface.co/datasets/DexForceAI/embodichain_data/blob/48317bd8733182f36d306cc2a7a60ae5e47ed2c9/robot_assets/TianjiMarvin.zip
ZIP MD5: af91dbcc352fae3469a3190d0c6e1756.
The dataset metadata declares Apache-2.0. The archive itself contains no license text. A snapshot of the license metadata is retained, together with the standard Apache-2.0 text from the associated EmbodiChain repository.

The ACD archive uses mesh-derived inertias with arm-link masses around 0.001 kg; these are not credible robot masses. Converted model arm inertials are copied from matching local link frames of Genesis Intelligence's public Tianji bimanual description, which declares MIT in its dataset metadata:
https://huggingface.co/datasets/Genesis-Intelligence/assets/blob/deffbe1685e5ce6aa289efdd541f762f1eb3353f/dual_arms_primitives.urdf
The source inertias remain intact in robot_acd.urdf. The generated PROVENANCE.json records every replacement. Public simulation asset parameters are not certified manufacturer system identification.

Visualization mesh format is changed from GLB to STL; source submesh transforms and base color factors are preserved. The ACD collision OBJ files contain disconnected convex parts. Each part becomes a separate STL and collision geom, preserving their convex decomposition instead of filling cavities with a single MuJoCo hull. The high-resolution archive and original URDFs are retained. Position gains, damping, and armature are explicit prototype controller parameters. Joint ranges and torque limits remain the source URDF values. Four self-collision exclusions cover only assembly-adjacent shoulder mount and compact wrist housing pairs whose released meshes overlap. All other robot self-collision remains enabled. No wheel or free-base joints, tool welds, or hand actuators are added by this conversion.
